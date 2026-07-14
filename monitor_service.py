# monitor_service.py

import os
import time
import json
import logging
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET
from typing import List, Optional, Any, Set, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from gevent import spawn_later

import constants
import config_manager
import handler.emby as emby

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core_processor import MediaProcessor

logger = logging.getLogger(__name__)

# --- 全局队列和锁 ---
FILE_EVENT_QUEUE = set() 
QUEUE_LOCK = threading.Lock()
DEBOUNCE_TIMER = None
MEDIAINFO_DIR_SCAN_LOCK = threading.Lock()
MEDIAINFO_DIR_SCAN_TIMERS = {}
MEDIAINFO_DIR_SCAN_WINDOW_SECONDS = 600
MEDIAINFO_DIR_SCAN_LIMIT = 30
MEDIAINFO_UPLOAD_LOCK = threading.Lock()
MEDIAINFO_UPLOAD_TIMERS = {}
MEDIAINFO_UPLOAD_RECENT = {}
MEDIAINFO_UPLOAD_INFLIGHT = set()
MEDIAINFO_UPLOAD_DEDUPE_SECONDS = 300
MEDIAINFO_UPLOAD_LOG_DEDUPE_SECONDS = 120
DEBOUNCE_DELAY = 3 # 防抖延迟秒数
EMBY_BIND_QUEUE = set()
EMBY_BIND_LOCK = threading.Lock()
EMBY_BIND_TIMER = None
EMBY_BIND_DEBOUNCE_SECONDS = 3
EMBY_BIND_RETRY_COUNTS = {}
EMBY_BIND_MAX_RETRIES = 2
EMBY_BIND_RETRY_DELAY_SECONDS = 10
NFO_WRITE_LOCK = threading.Lock()
AUDIO_EXTENSIONS = {'.flac', '.m4a', '.mp3', '.aac', '.wav', '.ape', '.ogg', '.opus'}
MEDIA_PREP_LOCK = threading.Lock()
MEDIA_PREP_INFLIGHT = set()
MEDIA_PREP_RECENT = {}
MEDIA_PREP_DEDUPE_SECONDS = 30

# --- 全局队列抑制标志 ---
IS_PROCESSING_PAUSED = False

class MediaFileHandler(FileSystemEventHandler):
    """
    文件系统事件处理器 (纯净版：仅监控媒体文件的新增和移动)
    """
    def __init__(self, extensions: List[str], exclude_dirs: List[str] = None):
        self.exclude_dirs = exclude_dirs or []
        self.extensions = []
        for ext in extensions:
            if not ext: continue
            clean_ext = ext.strip().lower().replace('*', '')
            if clean_ext:
                if not clean_ext.startswith('.'):
                    clean_ext = '.' + clean_ext
                self.extensions.append(clean_ext)
        
        logger.trace(f"  [实时监控] 已加载监控后缀: {self.extensions}")

    def _is_valid_media_file(self, file_path: str) -> bool:
        if str(file_path or '').lower().endswith('-mediainfo.json'):
            return True
        if os.path.exists(file_path) and os.path.isdir(file_path): 
            return False
        
        _, ext = os.path.splitext(file_path)
        if ext.lower() not in self.extensions: 
            return False
        
        filename = os.path.basename(file_path)
        if filename.startswith('.'): return False
        if filename.endswith(('.part', '.!qB', '.crdownload', '.tmp', '.aria2')): return False

        return True

    def on_created(self, event):
        if event.is_directory:
            self._handle_mediainfo_dir_update(event.src_path)
            return
        if not event.is_directory and str(event.src_path or '').lower().endswith('-mediainfo.json'):
            self._handle_mediainfo_update(event.src_path)
            return
        if not event.is_directory and self._is_valid_media_file(event.src_path):
            self._enqueue_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            self._handle_mediainfo_dir_update(event.src_path)
            return
        if not event.is_directory and str(event.src_path or '').lower().endswith('-mediainfo.json'):
            self._handle_mediainfo_update(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            self._handle_mediainfo_dir_update(event.dest_path)
            return
        if not event.is_directory and str(event.dest_path or '').lower().endswith('-mediainfo.json'):
            self._handle_mediainfo_update(event.dest_path)
            return
        if not event.is_directory and self._is_valid_media_file(event.dest_path):
            self._enqueue_file(event.dest_path)

    def _handle_mediainfo_update(self, file_path: str):
        if not file_path or _is_path_excluded(file_path, self.exclude_dirs):
            return
        try:
            from handler.shared_intro_service import shared_intro_enabled
            if not shared_intro_enabled():
                return
        except Exception:
            return
        norm_path = os.path.normpath(file_path)

        with MEDIAINFO_UPLOAD_LOCK:
            old_timer = MEDIAINFO_UPLOAD_TIMERS.get(norm_path)
            if old_timer:
                try:
                    old_timer.cancel()
                except Exception:
                    pass
            timer_ref = {}
            def _timer_runner():
                with MEDIAINFO_UPLOAD_LOCK:
                    if MEDIAINFO_UPLOAD_TIMERS.get(norm_path) is not timer_ref.get("timer"):
                        return
                    MEDIAINFO_UPLOAD_TIMERS.pop(norm_path, None)
                _run_mediainfo_intro_upload(norm_path)
            timer = threading.Timer(DEBOUNCE_DELAY, _timer_runner)
            timer_ref["timer"] = timer
            timer.daemon = True
            MEDIAINFO_UPLOAD_TIMERS[norm_path] = timer
            timer.start()

    def _handle_mediainfo_dir_update(self, dir_path: str):
        if not dir_path or _is_path_excluded(dir_path, self.exclude_dirs):
            return
        try:
            from handler.shared_intro_service import shared_intro_enabled
            if not shared_intro_enabled():
                return
        except Exception:
            return
        norm_dir = os.path.normpath(dir_path)

        def _runner():
            try:
                now = time.time()
                candidates = []
                if not os.path.isdir(norm_dir):
                    return
                with os.scandir(norm_dir) as it:
                    for entry in it:
                        if not entry.is_file():
                            continue
                        if not entry.name.lower().endswith('-mediainfo.json'):
                            continue
                        try:
                            mtime = entry.stat().st_mtime
                        except Exception:
                            continue
                        if now - mtime <= MEDIAINFO_DIR_SCAN_WINDOW_SECONDS:
                            candidates.append((mtime, entry.path))
                if not candidates:
                    return
                candidates.sort(reverse=True)
                logger.debug(f"  ➜ [共享片头] 目录变化，发现 {len(candidates)} 个最近更新的媒体信息文件。")
                for _mtime, path in candidates[:MEDIAINFO_DIR_SCAN_LIMIT]:
                    self._handle_mediainfo_update(path)
            finally:
                with MEDIAINFO_DIR_SCAN_LOCK:
                    MEDIAINFO_DIR_SCAN_TIMERS.pop(norm_dir, None)

        with MEDIAINFO_DIR_SCAN_LOCK:
            old_timer = MEDIAINFO_DIR_SCAN_TIMERS.get(norm_dir)
            if old_timer:
                try:
                    old_timer.cancel()
                except Exception:
                    pass
            timer = threading.Timer(DEBOUNCE_DELAY, _runner)
            timer.daemon = True
            MEDIAINFO_DIR_SCAN_TIMERS[norm_dir] = timer
            timer.start()

    def _enqueue_file(self, file_path: str):
        """新增/移动文件入队"""
        enqueue_file_actively(file_path)

def _is_path_excluded(file_path: str, exclude_paths: List[str]) -> bool:
    if not exclude_paths:
        return False
    norm_file = os.path.normpath(file_path).lower()
    for exc in exclude_paths:
        norm_exc = os.path.normpath(exc).lower()
        if norm_file == norm_exc or norm_file.startswith(norm_exc + os.sep):
            return True
    return False

def _intro_chapters_key(chapters: Any) -> tuple:
    key = []
    for item in chapters or []:
        if not isinstance(item, dict):
            continue
        try:
            ticks = int(item.get("StartPositionTicks") or 0)
        except Exception:
            ticks = 0
        key.append((str(item.get("MarkerType") or ""), ticks))
    return tuple(sorted(key))

def _shared_intro_skip_reason(reason: str) -> str:
    return {
        "no_intro_chapters": "未检测到片头章节",
        "sha1_not_found": "未找到本地 SHA1 缓存",
        "shared_center_disabled": "共享中心未启用",
        "shared_intro_disabled": "共享片头未启用",
    }.get(str(reason or ""), str(reason or "无需上传"))

def _should_log_mediainfo_intro_state(file_path: str, state_key: tuple, seconds: int = MEDIAINFO_UPLOAD_LOG_DEDUPE_SECONDS) -> bool:
    now = time.time()
    with MEDIAINFO_UPLOAD_LOCK:
        last_key, last_time = MEDIAINFO_UPLOAD_RECENT.get(file_path, (None, 0))
        if last_key == state_key and now - last_time <= seconds:
            return False
        MEDIAINFO_UPLOAD_RECENT[file_path] = (state_key, now)
        return True

def _run_mediainfo_intro_upload(file_path: str):
    basename = os.path.basename(file_path)
    dedupe_key = None
    try:
        from handler.shared_intro_service import (
            _load_json_file,
            extract_intro_chapters,
            sha1_for_mediainfo_path,
            upload_intro_for_mediainfo_path,
        )
        data = _load_json_file(file_path)
        chapters = extract_intro_chapters(data)
        if not chapters:
            if _should_log_mediainfo_intro_state(file_path, ("skip", "no_intro_chapters")):
                logger.debug(f"  ➜ [共享片头] 跳过：{basename}（未检测到片头章节）")
            return
        sha1 = sha1_for_mediainfo_path(file_path)
        if not sha1:
            if _should_log_mediainfo_intro_state(file_path, ("skip", "sha1_not_found")):
                logger.debug(f"  ➜ [共享片头] 跳过：{basename}（未找到本地 SHA1 缓存）")
            return

        chapter_key = _intro_chapters_key(chapters)
        dedupe_key = (sha1, chapter_key)
        now = time.time()
        with MEDIAINFO_UPLOAD_LOCK:
            last_key, last_time = MEDIAINFO_UPLOAD_RECENT.get(file_path, (None, 0))
            if last_key == dedupe_key and now - last_time <= MEDIAINFO_UPLOAD_DEDUPE_SECONDS:
                return
            if dedupe_key in MEDIAINFO_UPLOAD_INFLIGHT:
                return
            MEDIAINFO_UPLOAD_INFLIGHT.add(dedupe_key)

        res = upload_intro_for_mediainfo_path(file_path, reason='monitor_update')

        if res.get("ok"):
            with MEDIAINFO_UPLOAD_LOCK:
                MEDIAINFO_UPLOAD_RECENT[file_path] = (dedupe_key, now)
            logger.info(f"  ➜ [共享片头] 已上传：{basename}（SHA1 {sha1[:12]}，{len(chapters)} 个章节）")
            return

        if res.get("skipped"):
            logger.debug(f"  ➜ [共享片头] 跳过：{basename}（{_shared_intro_skip_reason(res.get('reason'))}）")
            return

        message = res.get("message") or res.get("reason") or "未知错误"
        center = res.get("center")
        if isinstance(center, dict):
            message = center.get("detail") or center.get("message") or message
        logger.warning(f"  ➜ [共享片头] 上传失败：{basename}（{message}）")
    except Exception as e:
        logger.warning(f"  ➜ [共享片头] 上传失败：{basename}（{e}）")
    finally:
        with MEDIAINFO_UPLOAD_LOCK:
            if dedupe_key:
                MEDIAINFO_UPLOAD_INFLIGHT.discard(dedupe_key)

def _is_etk_standard_strm(file_path: str) -> bool:
    if not str(file_path or '').lower().endswith('.strm'):
        return True
    try:
        if not os.path.exists(file_path) or os.path.getsize(file_path) <= 0:
            return False
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(2048).strip()
        return '/api/p115/play/' in content or '/api/p115/virtual-play/' in content
    except Exception as e:
        logger.warning(f"  ➜ [实时监控] 读取 STRM 失败，已跳过：{os.path.basename(file_path)}，原因：{e}")
        return False

def _filter_etk_standard_files(file_paths: List[str]) -> List[str]:
    valid = []
    for fp in file_paths or []:
        if _is_etk_standard_strm(fp):
            valid.append(fp)
        else:
            logger.warning(f"  ➜ [实时监控] 非 ETK 标准 STRM，已跳过：{os.path.basename(fp)}")
    return valid


def _write_minimal_tmdb_nfo(file_path: str, tmdb_id: str, media_type: str, title: str, processor) -> bool:
    if media_type == 'tv':
        media_dir = os.path.dirname(file_path)
        if processor._extract_season_from_path_or_text(os.path.basename(media_dir)) is not None:
            media_dir = os.path.dirname(media_dir)
        nfo_path = os.path.join(media_dir, 'tvshow.nfo')
        root_tag = 'tvshow'
    else:
        nfo_path = os.path.splitext(file_path)[0] + '.nfo'
        root_tag = 'movie'

    try:
        with NFO_WRITE_LOCK:
            changed = False
            if os.path.exists(nfo_path):
                tree = ET.parse(nfo_path)
                root = tree.getroot()
                if root.tag.lower() != root_tag:
                    logger.warning("  ➜ [入库预备] NFO 根节点不符合媒体类型，已保留原文件: %s", nfo_path)
                    return False
            else:
                root = ET.Element(root_tag)
                tree = ET.ElementTree(root)
                changed = True

            title_node = root.find('title')
            if title and title_node is None:
                title_node = ET.SubElement(root, 'title')
                title_node.text = str(title)
                changed = True

            unique_node = next(
                (node for node in root.findall('uniqueid') if str(node.get('type') or '').lower() == 'tmdb'),
                None,
            )
            if unique_node is None:
                unique_node = ET.SubElement(root, 'uniqueid', type='tmdb', default='true')
                unique_node.text = str(tmdb_id)
                changed = True
            elif str(unique_node.text or '').strip() != str(tmdb_id):
                unique_node.text = str(tmdb_id)
                unique_node.set('default', 'true')
                changed = True

            tmdb_node = root.find('tmdbid')
            if tmdb_node is None:
                tmdb_node = ET.SubElement(root, 'tmdbid')
                tmdb_node.text = str(tmdb_id)
                changed = True
            elif str(tmdb_node.text or '').strip() != str(tmdb_id):
                tmdb_node.text = str(tmdb_id)
                changed = True

            if changed:
                temp_path = nfo_path + '.etk-tmp'
                tree.write(temp_path, encoding='utf-8', xml_declaration=True)
                os.replace(temp_path, nfo_path)
                logger.debug("  ➜ [入库预备] 已写入 Emby 识别 NFO: %s (TMDb: %s)", nfo_path, tmdb_id)
        return True
    except Exception as e:
        logger.warning("  ➜ [入库预备] 写入简化 NFO 失败: %s -> %s", file_path, e)
        return False


def _identify_physical_media(file_path: str, processor):
    try:
        filename = os.path.basename(file_path)
        media_dir = os.path.dirname(file_path)
        folder_name = os.path.basename(media_dir)
        parent_name = os.path.basename(os.path.dirname(media_dir))
        season_num, episode_num = processor._extract_season_episode_from_path(file_path)
        is_season_dir = processor._extract_season_from_path_or_text(folder_name) is not None
        main_dir_name = parent_name if is_season_dir else folder_name
        forced_type = 'tv' if is_season_dir or (season_num is not None and episode_num is not None) else None

        def _existing_nfo_identity():
            nfo_candidates = [os.path.splitext(file_path)[0] + '.nfo']
            if forced_type == 'tv':
                series_dir = os.path.dirname(media_dir) if is_season_dir else media_dir
                nfo_candidates.insert(0, os.path.join(series_dir, 'tvshow.nfo'))
            for nfo_path in nfo_candidates:
                if not os.path.exists(nfo_path):
                    continue
                try:
                    root = ET.parse(nfo_path).getroot()
                    root_type = 'tv' if root.tag.lower() == 'tvshow' else 'movie' if root.tag.lower() == 'movie' else None
                    unique_node = next(
                        (node for node in root.findall('uniqueid') if str(node.get('type') or '').lower() == 'tmdb'),
                        None,
                    )
                    existing_id = str((unique_node.text if unique_node is not None else '') or root.findtext('tmdbid') or '').strip()
                    if root_type and existing_id.isdigit() and int(existing_id) > 0:
                        existing_title = root.findtext('title') or os.path.splitext(filename)[0]
                        logger.debug("  ➜ [入库预备] RAW 未命中，回退现有 NFO 身份: %s (TMDb: %s)", existing_title, existing_id)
                        return existing_id, root_type, existing_title
                except Exception as e:
                    logger.debug("  ➜ [入库预备] 读取现有 NFO 失败: %s -> %s", nfo_path, e)
            return None

        from handler.p115_service import _identify_media_enhanced
        _pick_code, sha1 = processor._extract_115_fingerprints(file_path, allow_api_fallback=False)

        tmdb_id, media_type, title = _identify_media_enhanced(
            filename,
            main_dir_name=main_dir_name,
            has_season_subdirs=is_season_dir,
            forced_media_type=forced_type,
            ai_translator=processor.ai_translator,
            use_ai=bool(processor.ai_translator and processor.config.get(constants.CONFIG_OPTION_AI_RECOGNITION, False)),
            is_folder=False,
            sha1=sha1,
        )
        tmdb_id = str(tmdb_id or '').strip()
        if not tmdb_id.isdigit() or int(tmdb_id) <= 0 or media_type not in {'movie', 'tv'}:
            return _existing_nfo_identity()
        logger.debug(
            "  ➜ [入库预备] 增强识别命中《%s》，TMDb: %s，类型: %s。",
            title or filename, tmdb_id, media_type,
        )
        return tmdb_id, media_type, title or os.path.splitext(filename)[0]
    except Exception as e:
        logger.warning("  ➜ [入库预备] 增强识别失败: %s -> %s", file_path, e)
        return None


def _generate_local_mediainfo(
    file_path: str,
    mediainfo_path: Optional[str] = None,
    *,
    cache_sha1: Optional[str] = None,
    cache_file_info: Optional[Dict[str, Any]] = None,
) -> bool:
    mediainfo_path = mediainfo_path or (os.path.splitext(file_path)[0] + '-mediainfo.json')
    if not cache_sha1 and os.path.exists(mediainfo_path) and os.path.getsize(mediainfo_path) > 0:
        return True
    if not shutil.which('ffprobe'):
        logger.error("  ➜ [入库预备] 容器内未找到 ffprobe，无法生成媒体信息。")
        return False

    try:
        command = [
            'ffprobe', '-v', 'error', '-show_format', '-show_streams', '-show_chapters',
            '-print_format', 'json', file_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        if result.returncode != 0:
            logger.warning(
                "  ➜ [入库预备] ffprobe 失败: %s -> %s",
                os.path.basename(file_path), (result.stderr or '').strip()[:300],
            )
            return False

        raw_probe = json.loads(result.stdout or '{}')
        from handler.p115_media_analyzer import P115MediaAnalyzerMixin
        formatted = P115MediaAnalyzerMixin()._build_emby_mediainfo_from_ffprobe(
            raw_probe,
            {'file_name': os.path.basename(file_path), 'size': os.path.getsize(file_path)},
        )
        if not formatted:
            logger.warning("  ➜ [入库预备] ffprobe 未解析出有效媒体流: %s", file_path)
            return False

        temp_path = mediainfo_path + '.etk-tmp'
        with open(temp_path, 'w', encoding='utf-8') as file_obj:
            json.dump(formatted, file_obj, ensure_ascii=False, indent=2)
        os.replace(temp_path, mediainfo_path)
        if cache_sha1:
            from handler.p115_service import P115CacheManager
            file_info = dict(cache_file_info or {})
            if not P115CacheManager.save_mediainfo_cache(
                str(cache_sha1).upper(),
                formatted,
                raw_ffprobe_json=raw_probe,
                file_info=file_info,
                fid=file_info.get('fid') or file_info.get('file_id') or file_info.get('id'),
                pick_code=file_info.get('pick_code') or file_info.get('pc') or file_info.get('pickcode'),
                file_name=file_info.get('file_name') or file_info.get('fn') or os.path.basename(file_path),
            ):
                logger.warning("  ➜ [入库预备] 媒体信息写入 p115_mediainfo_cache 失败: %s", file_path)
                return False
        logger.debug("  ➜ [入库预备] ffprobe 已生成媒体信息: %s", mediainfo_path)
        return True
    except subprocess.TimeoutExpired:
        logger.warning("  ➜ [入库预备] ffprobe 超时: %s", file_path)
        return False
    except Exception as e:
        logger.warning("  ➜ [入库预备] 生成媒体信息失败: %s -> %s", file_path, e)
        return False


def prepare_physical_files_for_binding(processor, file_paths: List[str]) -> List[str]:
    ready_paths = []
    for file_path in file_paths or []:
        identity = _identify_physical_media(file_path, processor)
        if not identity:
            logger.warning("  ➜ [入库预备] 无法识别媒体，已跳过 Emby 扫描: %s", file_path)
            continue
        tmdb_id, media_type, title = identity
        if not _write_minimal_tmdb_nfo(file_path, tmdb_id, media_type, title, processor):
            continue
        if not _generate_local_mediainfo(file_path):
            continue
        ready_paths.append(file_path)

    for file_path in ready_paths:
        enqueue_emby_binding(file_path)
    return ready_paths


def _prepare_strm_for_binding(processor, file_path: str):
    normalized_path = os.path.normpath(file_path)
    prepared = False
    try:
        identity = _identify_physical_media(file_path, processor)
        if not identity:
            logger.warning("  ➜ [STRM入库] 无法识别媒体，已跳过 Emby 扫描: %s", file_path)
            return
        tmdb_id, media_type, title = identity
        if not _write_minimal_tmdb_nfo(file_path, tmdb_id, media_type, title, processor):
            return
        enqueue_emby_binding(file_path)
        prepared = True
    finally:
        with MEDIA_PREP_LOCK:
            MEDIA_PREP_INFLIGHT.discard(normalized_path)
            if prepared:
                MEDIA_PREP_RECENT[normalized_path] = time.time()
            else:
                MEDIA_PREP_RECENT.pop(normalized_path, None)


def _enqueue_strm_preparation(processor, file_path: str) -> bool:
    normalized_path = os.path.normpath(file_path)
    now = time.time()
    with MEDIA_PREP_LOCK:
        if normalized_path in MEDIA_PREP_INFLIGHT:
            return False
        if now - MEDIA_PREP_RECENT.get(normalized_path, 0) <= MEDIA_PREP_DEDUPE_SECONDS:
            return False
        MEDIA_PREP_INFLIGHT.add(normalized_path)

    worker = threading.Thread(target=_prepare_strm_for_binding, args=(processor, file_path), daemon=True)
    worker.start()
    return True


def enqueue_emby_binding(file_path: str):
    """Batch media paths for active Emby Item ID discovery."""
    global EMBY_BIND_TIMER
    if not file_path or not os.path.isfile(file_path):
        return

    with EMBY_BIND_LOCK:
        EMBY_BIND_QUEUE.add(os.path.normpath(file_path))
        if EMBY_BIND_TIMER:
            EMBY_BIND_TIMER.cancel()
        EMBY_BIND_TIMER = threading.Timer(EMBY_BIND_DEBOUNCE_SECONDS, _process_emby_binding_queue)
        EMBY_BIND_TIMER.daemon = True
        EMBY_BIND_TIMER.start()


def _wait_for_mediainfo_sidecars(file_paths: List[str], timeout_seconds: float = 15.0) -> List[str]:
    pending = set(file_paths or [])
    ready = []
    deadline = time.time() + timeout_seconds
    while pending and time.time() < deadline:
        for path in list(pending):
            mediainfo_path = os.path.splitext(path)[0] + "-mediainfo.json"
            if os.path.exists(path) and os.path.exists(mediainfo_path):
                ready.append(path)
                pending.remove(path)
        if pending:
            time.sleep(0.25)

    for path in pending:
        logger.warning("  ➜ [主动入库] 未等到媒体信息侧车，跳过主动绑定: %s", path)
    return ready


def _process_emby_binding_queue():
    global EMBY_BIND_TIMER
    with EMBY_BIND_LOCK:
        file_paths = list(EMBY_BIND_QUEUE)
        EMBY_BIND_QUEUE.clear()
        EMBY_BIND_TIMER = None

    import extensions
    processor = extensions.media_processor_instance
    if not processor or not file_paths:
        return

    ready_paths = _wait_for_mediainfo_sidecars(file_paths)
    if not ready_paths:
        return

    base_url = processor.emby_url
    api_key = processor.emby_api_key
    user_id = processor.emby_user_id
    if not base_url or not api_key:
        return

    logger.info("  ➜ [主动入库] 通知 Emby 扫描 %s 个媒体文件，随后主动获取 Item ID。", len(ready_paths))
    emby.notify_emby_file_changes(ready_paths, base_url, api_key)
    found = emby.wait_for_emby_items_by_path(
        ready_paths,
        base_url,
        api_key,
        user_id,
        retry_delays=(0, 0.25, 0.5, 1, 2, 4, 8),
    )

    if found:
        from routes.webhook import dispatch_active_emby_items
        dispatch_active_emby_items(list(found.values()))

        with EMBY_BIND_LOCK:
            for path in ready_paths:
                normalized = emby._normalize_emby_media_path(path)
                if normalized in found:
                    EMBY_BIND_RETRY_COUNTS.pop(os.path.normpath(path), None)

    missing = [
        path for path in ready_paths
        if emby._normalize_emby_media_path(path) not in found
    ]
    if missing:
        retrying = []
        exhausted = []
        with EMBY_BIND_LOCK:
            for path in missing:
                normalized_path = os.path.normpath(path)
                attempts = EMBY_BIND_RETRY_COUNTS.get(normalized_path, 0) + 1
                if attempts <= EMBY_BIND_MAX_RETRIES:
                    EMBY_BIND_RETRY_COUNTS[normalized_path] = attempts
                    EMBY_BIND_QUEUE.add(normalized_path)
                    retrying.append(path)
                else:
                    EMBY_BIND_RETRY_COUNTS.pop(normalized_path, None)
                    exhausted.append(path)

            if retrying and EMBY_BIND_TIMER is None:
                EMBY_BIND_TIMER = threading.Timer(
                    EMBY_BIND_RETRY_DELAY_SECONDS,
                    _process_emby_binding_queue,
                )
                EMBY_BIND_TIMER.daemon = True
                EMBY_BIND_TIMER.start()

        if retrying:
            logger.warning(
                "  ➜ [主动入库] %s 个媒体文件暂未取得 Emby Item ID，%s 秒后重扫重试。",
                len(retrying), EMBY_BIND_RETRY_DELAY_SECONDS,
            )
        if exhausted:
            logger.error(
                "  ➜ [主动入库] %s 个媒体文件连续 %s 轮未取得 Emby Item ID，已停止自动重试。",
                len(exhausted), EMBY_BIND_MAX_RETRIES + 1,
            )

def enqueue_file_actively(file_path: str):
    """主动将文件推入监控队列"""
    global DEBOUNCE_TIMER
    if not _is_etk_standard_strm(file_path):
        logger.warning(f"  ➜ [实时监控] 非 ETK 标准 STRM，已跳过：{os.path.basename(file_path)}")
        return

    exclude_paths = config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_MONITOR_EXCLUDE_DIRS, [])
    if str(file_path or "").lower().endswith(".strm") and not _is_path_excluded(file_path, exclude_paths):
        processor = MonitorService.processor_instance
        if not processor:
            logger.warning("  ➜ [STRM入库] 核心处理器未就绪，已跳过: %s", os.path.basename(file_path))
            return
        if _enqueue_strm_preparation(processor, file_path):
            logger.debug("  ➜ [STRM入库] 加入识别/NFO 预备队列: %s", os.path.basename(file_path))
        return

    with QUEUE_LOCK:
        if file_path not in FILE_EVENT_QUEUE:
            logger.info(f"  ➜ [主动推送] 文件加入监控队列: {os.path.basename(file_path)}")
        
        FILE_EVENT_QUEUE.add(file_path)
        
        if DEBOUNCE_TIMER: DEBOUNCE_TIMER.kill()
        DEBOUNCE_TIMER = spawn_later(DEBOUNCE_DELAY, process_batch_queue)

def process_batch_queue():
    """处理新增/修改队列"""
    if not config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_MONITOR_ENABLED, False):
        with QUEUE_LOCK:
            FILE_EVENT_QUEUE.clear()
        return
        
    global DEBOUNCE_TIMER, IS_PROCESSING_PAUSED
    
    if IS_PROCESSING_PAUSED:
        with QUEUE_LOCK:
            if DEBOUNCE_TIMER: DEBOUNCE_TIMER.kill()
            DEBOUNCE_TIMER = spawn_later(5.0, process_batch_queue)
        return

    with QUEUE_LOCK:
        files_to_process = list(FILE_EVENT_QUEUE)
        FILE_EVENT_QUEUE.clear()
        DEBOUNCE_TIMER = None
    
    if not files_to_process: return
    
    processor = MonitorService.processor_instance
    if not processor: return

    exclude_paths = config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_MONITOR_EXCLUDE_DIRS, [])

    files_to_scrape = []
    files_to_refresh_only = []

    for file_path in files_to_process:
        if os.path.splitext(file_path)[1].lower() in AUDIO_EXTENSIONS:
            files_to_refresh_only.append(file_path)
        elif _is_path_excluded(file_path, exclude_paths):
            files_to_refresh_only.append(file_path)
        else:
            files_to_scrape.append(file_path)

    if files_to_scrape:
        logger.info(f"  ➜ [实时监控] 准备识别并入库 {len(files_to_scrape)} 个实体媒体文件。")
        threading.Thread(target=_handle_batch_file_task, args=(processor, files_to_scrape)).start()

    if files_to_refresh_only:
        logger.info(f"  ➜ [实时监控] 发现 {len(files_to_refresh_only)} 个文件命中排除路径，将跳过刮削直接刷新 Emby。")
        threading.Thread(target=_handle_batch_refresh_only_task, args=(files_to_refresh_only,)).start()

def _handle_batch_file_task(processor, file_paths: List[str]):
    valid_files = _wait_for_files_stability(file_paths)
    valid_files = _filter_etk_standard_files(valid_files)
    if not valid_files: return
    prepare_physical_files_for_binding(processor, valid_files)

def _handle_batch_refresh_only_task(file_paths: List[str]):
    valid_files = _wait_for_files_stability(file_paths)
    valid_files = _filter_etk_standard_files(valid_files)
    if not valid_files: return
    
    config = config_manager.APP_CONFIG
    base_url = config.get(constants.CONFIG_OPTION_EMBY_SERVER_URL)
    api_key = config.get(constants.CONFIG_OPTION_EMBY_API_KEY)
    delay_seconds = config.get(constants.CONFIG_OPTION_MONITOR_EXCLUDE_REFRESH_DELAY, 0)

    if not base_url or not api_key:
        return

    if delay_seconds > 0:
        logger.info(f"  ➜ [实时监控-排除路径] 等待 {delay_seconds} 秒后通知 Emby 刷新...")
        time.sleep(delay_seconds)
        if not config.get(constants.CONFIG_OPTION_MONITOR_ENABLED, False):
            return

    logger.info(f"  ➜ [实时监控-排除路径] 正在向 Emby 发送 {len(valid_files)} 个文件的极速入库通知。")
    emby.notify_emby_file_changes(valid_files, base_url, api_key)

def _wait_for_files_stability(file_paths: List[str]) -> List[str]:
    """
    文件稳定性检测 (仅针对媒体文件)
    """
    valid_files = []
    pending_files = {fp: {'last_size': -1, 'stable_count': 0} for fp in file_paths if os.path.exists(fp)}
            
    for _ in range(60):
        if not pending_files: break
            
        for fp in list(pending_files.keys()):
            if not os.path.exists(fp):
                del pending_files[fp]
                continue
                
            try:
                size = os.path.getsize(fp)
                if fp.lower().endswith('.strm') and size > 0:
                    valid_files.append(fp)
                    del pending_files[fp]
                    continue
                
                if size > 0 and size == pending_files[fp]['last_size']:
                    pending_files[fp]['stable_count'] += 1
                else:
                    pending_files[fp]['stable_count'] = 0
                    
                pending_files[fp]['last_size'] = size
                if pending_files[fp]['stable_count'] >= 3:
                    valid_files.append(fp)
                    del pending_files[fp]
            except Exception:
                pass
                
        if pending_files:
            time.sleep(1)
            
    return valid_files

class MonitorService:
    processor_instance = None
    active_instance = None

    def __init__(self, config: dict, processor: 'MediaProcessor'):
        self.config = config
        self.processor = processor
        MonitorService.processor_instance = processor 
        MonitorService.active_instance = self
        
        self.observer: Optional[Any] = None
        self._observer_lock = threading.RLock()
        self._start_generation = 0
        self.enabled = self.config.get(constants.CONFIG_OPTION_MONITOR_ENABLED, False)
        self.paths = self.config.get(constants.CONFIG_OPTION_MONITOR_PATHS, [])
        self.extensions = self.config.get(constants.CONFIG_OPTION_MONITOR_EXTENSIONS, constants.DEFAULT_MONITOR_EXTENSIONS)
        self.exclude_dirs = self.config.get(constants.CONFIG_OPTION_MONITOR_EXCLUDE_DIRS, constants.DEFAULT_MONITOR_EXCLUDE_DIRS)

    def start(self):
        try:
            from handler.p115_upload_monitor import upload_monitor_enabled
            has_upload_monitor = upload_monitor_enabled()
        except Exception as e:
            logger.warning(f"  ➜ [115上传监控] 读取配置失败，已跳过启动: {e}")
            has_upload_monitor = False

        if (not self.enabled or not self.paths) and not has_upload_monitor:
            return

        with self._observer_lock:
            self._start_generation += 1
            generation = self._start_generation

        def _async_start():
            observer = Observer()
            started_paths = []
            if self.enabled and self.paths:
                event_handler = MediaFileHandler(self.extensions, self.exclude_dirs)
                for path in self.paths:
                    if os.path.exists(path) and os.path.isdir(path):
                        try:
                            observer.schedule(event_handler, path, recursive=True)
                            started_paths.append(path)
                        except Exception as e:
                            logger.error(f"  ➜ 无法监控目录 '{path}': {e}")

            upload_paths = []
            if has_upload_monitor:
                try:
                    from handler.p115_upload_monitor import schedule_upload_monitor
                    upload_paths = schedule_upload_monitor(observer, self.extensions)
                except Exception as e:
                    logger.error(f"  ➜ [115上传监控] 启动失败: {e}", exc_info=True)

            if started_paths or upload_paths:
                with self._observer_lock:
                    if generation != self._start_generation:
                        return
                    self.observer = observer
                    observer.start()
                logger.info(
                    f"  ➜ [实时监控] 服务已启动，媒体目录 {len(started_paths)} 个，"
                    f"115 上传目录 {len(upload_paths)} 个。"
                )

        threading.Thread(target=_async_start, name="MonitorServiceStarter", daemon=True).start()

    def stop(self):
        with self._observer_lock:
            self._start_generation += 1
            observer = self.observer
            self.observer = None
        if observer:
            try:
                observer.stop()
                if observer.is_alive():
                    observer.join()
            except RuntimeError:
                pass

    @classmethod
    def restart_active(cls):
        instance = cls.active_instance
        if not instance:
            return False
        instance.stop()
        instance.config = config_manager.APP_CONFIG
        instance.enabled = instance.config.get(constants.CONFIG_OPTION_MONITOR_ENABLED, False)
        instance.paths = instance.config.get(constants.CONFIG_OPTION_MONITOR_PATHS, [])
        instance.extensions = instance.config.get(
            constants.CONFIG_OPTION_MONITOR_EXTENSIONS,
            constants.DEFAULT_MONITOR_EXTENSIONS,
        )
        instance.exclude_dirs = instance.config.get(
            constants.CONFIG_OPTION_MONITOR_EXCLUDE_DIRS,
            constants.DEFAULT_MONITOR_EXCLUDE_DIRS,
        )
        instance.start()
        return True

def pause_queue_processing():
    global IS_PROCESSING_PAUSED
    IS_PROCESSING_PAUSED = True

def resume_queue_processing():
    global IS_PROCESSING_PAUSED, DEBOUNCE_TIMER
    IS_PROCESSING_PAUSED = False
    with QUEUE_LOCK:
        if FILE_EVENT_QUEUE:
            if DEBOUNCE_TIMER: DEBOUNCE_TIMER.kill()
            DEBOUNCE_TIMER = spawn_later(1, process_batch_queue)
