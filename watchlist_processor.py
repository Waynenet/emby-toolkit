# watchlist_processor.py

import time
import json
import os
import concurrent.futures
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import threading
from collections import defaultdict
# 导入我们需要的辅助模块
from database import connection, media_db, request_db, watchlist_db, user_db, settings_db
import constants
import utils
from ai_translator import AITranslator
import handler.tmdb as tmdb
import handler.emby as emby
import handler.moviepilot as moviepilot
import tasks.helpers as helpers
from services.subscribe_assistant.manager import SubscribeAssistantManager
import logging

logger = logging.getLogger(__name__)
# ✨✨✨ Tmdb状态翻译字典 ✨✨✨
TMDB_STATUS_TRANSLATION = {
    "Ended": "已完结",
    "Canceled": "已取消",
    "Returning Series": "连载中",
    "In Production": "制作中",
    "Planned": "计划中"
}
# ★★★ 内部状态翻译字典，用于日志显示 ★★★
INTERNAL_STATUS_TRANSLATION = {
    'Watching': '追剧中',
    'Paused': '已暂停',
    'Completed': '已完结',
    'Pending': '待定中'
}
# ★★★ 定义状态常量，便于维护 ★★★
STATUS_WATCHING = 'Watching'
STATUS_PAUSED = 'Paused'
STATUS_COMPLETED = 'Completed'
STATUS_PENDING = 'Pending'
def translate_status(status: str) -> str:
    """一个简单的辅助函数，用于翻译状态，如果找不到翻译则返回原文。"""
    return TMDB_STATUS_TRANSLATION.get(status, status)
def translate_internal_status(status: str) -> str:
    """★★★ 新增：一个辅助函数，用于翻译内部状态，用于日志显示 ★★★"""
    return INTERNAL_STATUS_TRANSLATION.get(status, status)

def _series_has_animation_genre(series_data: Dict[str, Any]) -> bool:
    for genre in series_data.get('genres') or []:
        if isinstance(genre, dict):
            try:
                if int(genre.get('id') or 0) == 16:
                    return True
            except (TypeError, ValueError):
                pass
            text = str(genre.get('name') or '').strip().lower()
        else:
            text = str(genre or '').strip().lower()

        if text in {'animation', 'animated'} or any(word in text for word in ('动画', '動漫', '动漫', 'anime', 'アニメ')):
            return True
    return False

def _watchlist_mp_wash_kwargs(watchlist_cfg: Dict[str, Any], *, force_full: bool = False) -> Dict[str, Optional[int]]:
    assistant = watchlist_cfg.get('subscribe_assistant') if isinstance(watchlist_cfg.get('subscribe_assistant'), dict) else {}
    best_version_type = str(assistant.get('best_version_type') or 'no').strip().lower()
    if force_full or best_version_type in ('tv', 'all'):
        return {'best_version': 1, 'best_version_full': 1}
    if best_version_type == 'tv_episode':
        return {'best_version': 1, 'best_version_full': None}
    return {'best_version': None, 'best_version_full': None}

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

class WatchlistProcessor:
    """
    【V13 - media_metadata 适配版】
    - 所有数据库操作完全迁移至 media_metadata 表。
    - 读写逻辑重构，以 tmdb_id 为核心标识符。
    - 保留了所有复杂的状态判断逻辑，使其在新架构下无缝工作。
    """
    def __init__(self, config: Dict[str, Any], ai_translator=None, douban_api=None):
        if not isinstance(config, dict):
            raise TypeError(f"配置参数(config)必须是一个字典，但收到了 {type(config).__name__} 类型。")
        self.config = config
        self.tmdb_api_key = self.config.get("tmdb_api_key", "")
        self.emby_url = self.config.get("emby_server_url")
        self.emby_api_key = self.config.get("emby_api_key")
        self.emby_user_id = self.config.get("emby_user_id")
        self.local_data_path = self.config.get("local_data_path", "")
        self.ai_translator = ai_translator
        self.douban_api = douban_api
        self._stop_event = threading.Event()
        self.progress_callback = None
        logger.trace("WatchlistProcessor 初始化完成。")

    # --- 线程控制 ---
    def signal_stop(self): self._stop_event.set()
    def clear_stop_signal(self): self._stop_event.clear()
    def is_stop_requested(self) -> bool: return self._stop_event.is_set()
    def close(self): logger.trace("WatchlistProcessor closed.")

    # --- 数据库和文件辅助方法 ---
    def _read_local_json(self, file_path: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(file_path): return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception as e:
            logger.error(f"读取本地JSON文件失败: {file_path}, 错误: {e}")
            return None

    def _get_safe_series_name(self, series_data: Dict[str, Any]) -> str:
        """安全获取剧集名称，避免 item_name 为 None 导致日志/进度回调报错。"""
        if not isinstance(series_data, dict):
            return "未知剧集"

        for key in ("item_name", "title", "name", "original_title", "original_name"):
            value = series_data.get(key)
            if value is None:
                continue

            value = str(value).strip()
            if value and value.lower() not in ("none", "null"):
                return value

        tmdb_id = series_data.get("tmdb_id") or series_data.get("id")
        if tmdb_id:
            return f"TMDb {tmdb_id}"

        return "未知剧集"

    # ★★★ 核心修改 1: 重构统一的数据库更新函数 ★★★
    def _update_watchlist_entry(self, tmdb_id: str, item_name: str, updates: Dict[str, Any]):
        """【新架构】直接调用 DB 层更新，不再做字段映射。"""
        try:
            watchlist_db.update_watchlist_metadata(tmdb_id, updates)
            logger.info(f"  ➜ 成功更新数据库中 '{item_name}' 的追剧信息。")
        except Exception as e:
            logger.error(f"  更新 '{item_name}' 追剧信息时出错: {e}")

    # ★★★ 核心修改 2: 重构自动添加追剧列表的函数 ★★★
    def add_series_to_watchlist(self, item_details: Dict[str, Any]):
        """ 【V14 - 统一判定版】"""
        if item_details.get("Type") != "Series": return
        tmdb_id = item_details.get("ProviderIds", {}).get("Tmdb")
        item_name = item_details.get("Name")
        item_id = item_details.get("Id") 
        if not tmdb_id or not item_name or not item_id: return

        try:
            # 1. 调用 DB 层进行 Upsert，并拿到当前状态
            db_row = watchlist_db.upsert_series_initial_record(tmdb_id, item_name, item_id)
            
            if db_row:
                # 2. 构造判定数据 (字段名直接对齐数据库)
                series_data = {
                    'tmdb_id': tmdb_id,
                    'item_name': item_name,
                    'watching_status': db_row['watching_status'], # 👈 修复点：使用字符串 Key
                    'force_ended': db_row['force_ended'],
                    'emby_item_ids_json': db_row['emby_item_ids_json']
                }
                # 3. 立即触发一次判定流
                self._process_one_series(series_data)
                
        except Exception as e:
            logger.error(f"自动添加剧集 '{item_name}' 时出错: {e}")

    # --- 核心任务启动器  ---
    def run_regular_processing_task_concurrent(self, progress_callback: callable, tmdb_id: Optional[str] = None):
        """核心任务启动器，只处理活跃剧集。"""
        self.progress_callback = progress_callback
        task_name = "并发追剧更新"
        if tmdb_id: task_name = f"单项追剧更新 (TMDb ID: {tmdb_id})"
        
        self.progress_callback(0, "准备检查待更新剧集...")
        try:
            where_clause = ""
            if not tmdb_id: 
                today_str = datetime.now().date().isoformat()
                where_clause = f"""
                    WHERE watching_status IN ('{STATUS_WATCHING}', '{STATUS_PENDING}', '{STATUS_PAUSED}')
                """

            active_series = self._get_series_to_process(where_clause, tmdb_id=tmdb_id)
            
            if active_series:
                total = len(active_series)
                self.progress_callback(5, f"开始并发处理 {total} 部剧集...")
                
                processed_count = 0
                lock = threading.Lock()

                def worker_process_series(series: dict):
                    if self.is_stop_requested():
                        return "任务已停止"

                    series_name = self._get_safe_series_name(series)

                    try:
                        self._process_one_series(series)
                        return "处理成功"
                    except Exception as e:
                        logger.error(f"处理剧集 {series_name} 时发生错误: {e}", exc_info=False)
                        return f"处理失败: {e}"

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_series = {executor.submit(worker_process_series, series): series for series in active_series}
                    
                    for future in concurrent.futures.as_completed(future_to_series):
                        if self.is_stop_requested():
                            executor.shutdown(wait=False, cancel_futures=True)
                            break

                        series_info = future_to_series[future]
                        series_name = self._get_safe_series_name(series_info)

                        try:
                            result = future.result()
                            logger.trace(f"'{series_name}' - {result}")
                        except Exception as exc:
                            logger.error(f"任务 '{series_name}' 执行时产生未捕获的异常: {exc}")

                        with lock:
                            processed_count += 1
                        
                        progress = 5 + int((processed_count / total) * 95)
                        self.progress_callback(
                            progress,
                            f"剧集处理: {processed_count}/{total} - {series_name[:15]}..."
                        )
                
                if not self.is_stop_requested():
                    self.progress_callback(100, "追剧检查完成。")
            else:
                self.progress_callback(100, "没有需要处理的剧集，任务完成。")
            
        except Exception as e:
            logger.error(f"执行 '{task_name}' 时发生严重错误: {e}", exc_info=True)
            self.progress_callback(-1, f"错误: {e}")
        finally:
            self.progress_callback = None

    # --- 全量刷新已完结剧集任务 ---
    def refresh_completed_series_task(self, progress_callback: callable):
        """ 
        低频扫描所有已完结剧集。
        优化策略：
        1. 近期完结：全量刷新。
        2. 远古完结：轻量检查 TMDb，只有发现新季时才全量刷新。
        """
        self.progress_callback = progress_callback
        task_name = "全量刷新剧集"
        self.progress_callback(0, "准备开始预定检查...")
        
        try:
            # 获取配置
            watchlist_cfg = settings_db.get_setting('watchlist_config') or {}
            # 默认回溯 365 天
            revival_check_days = int(watchlist_cfg.get('revival_check_days', 365))
            
            completed_series = self._get_series_to_process(f"WHERE watching_status = '{STATUS_COMPLETED}' AND force_ended = FALSE")
            total = len(completed_series)
            if not completed_series:
                self.progress_callback(100, "没有需要检查的已完结剧集。")
                return

            logger.info(f"  ➜ 开始检查 {total} 部已完结剧集 (全量刷新回溯期: {revival_check_days}天)...")
            
            revived_count = 0
            skipped_count = 0
            today = datetime.now(timezone.utc).date()

            for i, series in enumerate(completed_series):
                if self.is_stop_requested(): break
                progress = 10 + int(((i + 1) / total) * 90)
                series_name = series.get('item_name') or "未知剧集"
                tmdb_id = series['tmdb_id']
                emby_ids = series.get('emby_item_ids_json', [])
                item_id = emby_ids[0] if emby_ids else None
                
                # --- 1. 判断是否属于“远古剧集” ---
                is_ancient = False
                last_air_date_local = None
                
                # 从本地数据库记录中解析最后播出日期
                last_ep_json = series.get('last_episode_to_air_json')
                if last_ep_json:
                    if isinstance(last_ep_json, str):
                        try: last_ep_json = json.loads(last_ep_json)
                        except: pass
                    
                    if isinstance(last_ep_json, dict) and last_ep_json.get('air_date'):
                        try:
                            last_air_date_local = datetime.strptime(last_ep_json['air_date'], '%Y-%m-%d').date()
                            days_since_ended = (today - last_air_date_local).days
                            if days_since_ended > revival_check_days:
                                is_ancient = True
                        except ValueError: pass

                # --- 2. 分流处理 ---
                
                if is_ancient:
                    # ★★★ 核心修复：轻量级检查逻辑 ★★★
                    # 只有当 TMDb 有新动态时，才放行到下方的全量刷新，否则 continue
                    self.progress_callback(progress, f"轻量检查: {series_name[:15]}... ({i+1}/{total})")
                    
                    try:
                        # 1. 轻量请求：只获取 Series 基础详情 (数据量小，速度快)
                        tmdb_basic = tmdb.get_tv_details(tmdb_id, self.tmdb_api_key)
                        if not tmdb_basic: continue

                        has_new_content = False
                        
                        # 2. 比对 A: 检查 TMDb 的最新播出日期是否晚于本地记录
                        tmdb_last_ep = tmdb_basic.get('last_episode_to_air')
                        if tmdb_last_ep and tmdb_last_ep.get('air_date'):
                            try:
                                tmdb_last_date = datetime.strptime(tmdb_last_ep['air_date'], '%Y-%m-%d').date()
                                # 如果 TMDb 的日期比本地新，说明有新集播出了
                                if last_air_date_local and tmdb_last_date > last_air_date_local:
                                    has_new_content = True
                                    logger.info(f"  ➜ [新季检测] 《{series_name}》发现新播出记录 ({tmdb_last_date} > {last_air_date_local})，触发全量刷新。")
                            except: pass

                        if not has_new_content:
                            try:
                                local_max_season = int(last_ep_json.get('season_number') or 0) if isinstance(last_ep_json, dict) else 0
                            except (TypeError, ValueError):
                                local_max_season = 0

                            for season_info in tmdb_basic.get('seasons') or []:
                                try:
                                    tmdb_season_num = int(season_info.get('season_number', 0))
                                except (TypeError, ValueError):
                                    continue

                                if tmdb_season_num <= local_max_season:
                                    continue

                                air_date_str = season_info.get('air_date')
                                if not air_date_str:
                                    continue

                                try:
                                    season_air_date = datetime.strptime(air_date_str, '%Y-%m-%d').date()
                                except ValueError:
                                    continue

                                days_diff = (season_air_date - today).days
                                if -30 <= days_diff <= 7:
                                    has_new_content = True
                                    logger.info(f"  ➜ [新季检测] 《{series_name}》第 {tmdb_season_num} 季已有开播日期 {air_date_str}，触发全量刷新。")
                                    break
                        
                        # 3. 决策：如果没有新内容，直接跳过后续所有逻辑
                        if not has_new_content:
                            skipped_count += 1
                            logger.info(f"  ➜ 《{series_name}》无新内容，跳过全量刷新。")
                            continue 
                        
                        # 如果代码走到这里，说明 has_new_content = True，将自然向下执行到第 3 步

                    except Exception as e:
                        logger.warning(f"  ➜ 轻量检查《{series_name}》失败: {e}")
                        continue
                else:
                    # 近期完结：直接全量刷新
                    self.progress_callback(progress, f"全量刷新: {series_name[:15]}... ({i+1}/{total})")

                # --- 3. 执行全量刷新 (合并后的逻辑) ---
                # 无论是“近期完结”还是“远古诈尸”，只要代码能跑到这里，
                # 就说明需要更新数据库、同步子集和刷新 Emby。
                
                refresh_result = self._refresh_series_metadata(tmdb_id, series_name, item_id)
                if not refresh_result: 
                    continue
                
                # 解包返回结果，供后续复活判定逻辑使用
                tmdb_details, _, emby_seasons_state = refresh_result

                # --- 4. 复活判定逻辑 ---
                
                # 计算本地已有的最大季号，以及该季的本地集数
                local_max_season = 0
                local_max_season_episodes = 0
                if emby_seasons_state:
                    valid_local_seasons = [s for s in emby_seasons_state.keys() if s > 0]
                    if valid_local_seasons:
                        local_max_season = max(valid_local_seasons)
                        local_max_season_episodes = len(emby_seasons_state[local_max_season])

                # 获取 TMDb 上的总季数
                tmdb_seasons = tmdb_details.get('seasons', [])
                valid_tmdb_seasons = [s for s in tmdb_seasons if s.get('season_number', 0) > 0]
                if not valid_tmdb_seasons: continue
                # 核心判断：遍历所有季，寻找“新季”或“集数增加的老季”
                for season_info in valid_tmdb_seasons:
                    new_season_num = season_info.get('season_number')
                    
                    # 条件1：这是全新的季
                    is_new_season = new_season_num > local_max_season
                    
                    # 条件2：这是一季打天下的老季，但 TMDb 的总集数 > 本地已有的集数
                    tmdb_ep_count = season_info.get('episode_count', 0)
                    is_updated_old_season = (new_season_num == local_max_season) and (tmdb_ep_count > local_max_season_episodes)

                    if is_updated_old_season and not _series_has_animation_genre(tmdb_details):
                        logger.info(f"  ➜ 《{series_name}》第 {new_season_num} 季集数增加，但非动画类型，跳过老季复活。")
                        continue

                    # 如果既不是新季，老季也没更新，直接跳过
                    if not (is_new_season or is_updated_old_season): 
                        continue

                    air_date_str = season_info.get('air_date')
                    
                    # ★ 关键修复：如果是老季更新，季的 air_date 可能是几年前，会被下方的时间锁拦截。
                    # 我们需要用最新一集的播出时间，或者强制设为今天以放行。
                    if is_updated_old_season:
                        last_ep = tmdb_details.get('last_episode_to_air')
                        if last_ep and last_ep.get('air_date'):
                            air_date_str = last_ep.get('air_date')
                        else:
                            air_date_str = today.strftime('%Y-%m-%d') # 兜底放行
                        # ... (日期推断逻辑保持不变) ...
                        if not air_date_str:
                            # 尝试深层查询
                            season_details_deep = tmdb.get_tv_season_details(tmdb_id, new_season_num, self.tmdb_api_key)
                            if season_details_deep:
                                air_date_str = season_details_deep.get('air_date')
                                if not air_date_str and 'episodes' in season_details_deep:
                                    episodes = season_details_deep['episodes']
                                    valid_dates = [e.get('air_date') for e in episodes if e.get('air_date')]
                                    if valid_dates: air_date_str = min(valid_dates)
                                if not season_info.get('poster_path'): season_info['poster_path'] = season_details_deep.get('poster_path')
                                if not season_info.get('overview'): season_info['overview'] = season_details_deep.get('overview')
                        
                    if not air_date_str: continue

                    try:
                        air_date = datetime.strptime(air_date_str, '%Y-%m-%d').date()
                        days_diff = (air_date - today).days

                        if -30 <= days_diff <= 7:
                            revived_count += 1
                            status_desc = "已开播" if days_diff <= 0 else f"{days_diff}天后开播"
                            logger.info(f"  ➜ 发现《{series_name}》第 {new_season_num} 季{status_desc}，触发复活订阅流程。")

                            if is_updated_old_season:
                                mp_wash_kwargs = _watchlist_mp_wash_kwargs(watchlist_cfg)
                                sub_success = moviepilot.subscribe_series_to_moviepilot(
                                    series_info={'tmdb_id': tmdb_id, 'title': series_name},
                                    season_number=new_season_num,
                                    config=self.config,
                                    **mp_wash_kwargs
                                )
                                if sub_success:
                                    watchlist_db.update_specific_season_total_episodes(
                                        tmdb_id,
                                        new_season_num,
                                        tmdb_ep_count,
                                        locked=False
                                    )
                                    watchlist_db.revive_completed_series_and_season(tmdb_id, new_season_num)
                                    season_info['episode_count'] = tmdb_ep_count
                                    self._update_watchlist_entry(tmdb_id, series_name, {
                                        "watchlist_tmdb_status": "Returning Series"
                                    })
                                    logger.info(f"  ➜ 已为动画《{series_name}》第 {new_season_num} 季直接提交 MoviePilot 订阅，并恢复追剧状态。")
                                else:
                                    logger.error(f"  ➜ 动画《{series_name}》第 {new_season_num} 季提交 MoviePilot 订阅失败。")
                                break

                            # 1. 构造媒体信息
                            season_tmdb_id = str(season_info.get('id'))
                            media_info = {
                                'tmdb_id': season_tmdb_id,
                                'item_type': 'Season',
                                'title': f"{series_name} - {season_info.get('name', f'第 {new_season_num} 季')}",
                                'release_date': air_date_str,
                                'poster_path': season_info.get('poster_path'),
                                'season_number': new_season_num,
                                'parent_series_tmdb_id': tmdb_id,
                                'overview': season_info.get('overview')
                            }

                            # ★★★ 修改点：定义专属的 source type，并区分开播状态 ★★★
                            source_data = {"type": "revived_season", "reason": "watchlist_revival", "item_id": tmdb_id}

                            if days_diff <= 0:
                                # 已开播：直接设为 WANTED (想看/立即订阅)
                                request_db.set_media_status_wanted(
                                    tmdb_ids=season_tmdb_id,
                                    item_type='Season',
                                    source=source_data,
                                    media_info_list=[media_info]
                                )
                            else:
                                # 未开播：设为 PENDING_RELEASE (待上映)
                                request_db.set_media_status_pending_release(
                                    tmdb_ids=season_tmdb_id,
                                    item_type='Season',
                                    source=source_data,
                                    media_info_list=[media_info]
                                )

                            # 仅更新 TMDb 状态元数据，保持数据新鲜度 (可选，不影响逻辑)
                            self._update_watchlist_entry(tmdb_id, series_name, {
                                "watchlist_tmdb_status": "Returning Series"
                            })

                            sub_status_desc = "立即订阅" if days_diff <= 0 else "待上映"
                            logger.info(f"  ➜ 已为《{series_name}》第 {new_season_num} 季提交订阅请求，状态：{sub_status_desc}。")
                            break
                    except ValueError: pass
                
                time.sleep(0.5) # 稍微减少一点 sleep，因为轻量检查很快
            
            final_message = f"复活检查完成。共扫描 {total} 部，跳过远古剧 {skipped_count} 部，复活 {revived_count} 部。"
            self.progress_callback(100, final_message)

        except Exception as e:
            logger.error(f"执行 '{task_name}' 时发生严重错误: {e}", exc_info=True)
            self.progress_callback(-1, f"错误: {e}")
        finally:
            self.progress_callback = None

    def _get_series_to_process(self, where_clause: str, tmdb_id: Optional[str] = None, include_all_series: bool = False) -> List[Dict[str, Any]]:
        """
        【V6 - 数据库统一版】
        - 无论是单项刷新还是批量刷新，统一调用 watchlist_db 接口。
        """
        
        # 1. 准备参数
        target_library_ids = None
        target_condition = None

        # 2. 如果是单项刷新 (tmdb_id 存在)
        if tmdb_id:
            # 单项刷新时，我们不需要 library_ids 和 where_clause
            # 因为我们就是想强制刷新这一部，不管它在哪个库，也不管它是什么状态
            pass 

        # 3. 如果是批量刷新
        else:
            # 获取配置的媒体库
            target_library_ids = self.config.get(constants.CONFIG_OPTION_EMBY_LIBRARIES_TO_PROCESS, [])
            if target_library_ids:
                logger.info(f"  ➜ 已启用媒体库过滤器 ({len(target_library_ids)} 个库)，正在数据库中筛选...")

            # 构建 SQL 条件片段
            conditions = []
            
            # 处理 include_all_series 逻辑
            if not include_all_series:
                conditions.append("watching_status != 'NONE'")
                
            # 处理传入的 where_clause (例如: "WHERE watching_status = 'Watching'")
            if where_clause:
                # 去掉 "WHERE" 前缀，只保留条件部分
                clean_clause = where_clause.replace('WHERE', '', 1).strip()
                if clean_clause:
                    conditions.append(clean_clause)
            
            target_condition = " AND ".join(conditions) if conditions else ""

        # 4. 统一调用数据库接口
        return watchlist_db.get_series_by_dynamic_condition(
            condition_sql=target_condition,
            library_ids=target_library_ids,
            tmdb_id=tmdb_id
        )

    def _save_local_json(self, relative_path: str, new_data: Dict[str, Any]):
        """
        保存数据到本地 JSON 缓存文件 (智能合并模式)。
        - ★★★ 智能保护：'series.json' 不更新 'name'，但 'season-*.json' 会更新 'name'。
        """
        if not self.local_data_path:
            return

        full_path = os.path.join(self.local_data_path, relative_path)
        filename = os.path.basename(full_path)
        
        # ★★★ 关键检查：如果文件不存在，直接放弃，绝不创建“残缺”文件 ★★★
        if not os.path.exists(full_path):
            logger.trace(f"  ➜ 本地缓存文件不存在，跳过更新: {filename}")
            return

        try:
            # 读取现有文件
            with open(full_path, 'r', encoding='utf-8') as f:
                final_data = json.load(f)

            # 定义要更新的字段 (TMDb 字段 -> JSON 字段)
            fields_to_update = {
                # --- 基础视觉与文本 ---
                "overview": "overview",           # 简介
                "poster_path": "poster_path",     # 海报
                "backdrop_path": "backdrop_path", # 背景
                "still_path": "still_path",       # 剧照
                "tagline": "tagline",             # 标语
                
                # --- 日期 ---
                "first_air_date": "release_date", # 首播日期 (Series)
                "air_date": "release_date",       # 播出日期 (Episode/Season)
                
                # --- ★★★ 新增：核心元数据 ★★★ ---
                "genres": "genres",                         # 类型 (对象数组)
                "keywords": "keywords",                     # 关键词 (对象结构)
                "content_ratings": "content_ratings",       # 分级信息 (对象结构)
                "origin_country": "origin_country",         # 产地 (字符串数组)
                "production_companies": "production_companies", # 制作公司 (对象数组)
                
                # --- ★★★ 新增：评分与状态 ★★★ ---
                "vote_average": "vote_average",   # 评分
                "vote_count": "vote_count",       # 评分人数
                "popularity": "popularity"        # 热度
            }

            # 差异化保护：只有非 series.json 才允许更新标题
            if 'series.json' not in filename:
                fields_to_update["name"] = "name"

            # 执行合并更新
            updated = False
            for tmdb_key, json_key in fields_to_update.items():
                if tmdb_key in new_data and new_data[tmdb_key] is not None:
                    # 只有值真的变了才更新，减少文件IO
                    if final_data.get(json_key) != new_data[tmdb_key]:
                        final_data[json_key] = new_data[tmdb_key]
                        updated = True

            # 只有发生变更时才写入
            if updated:
                with open(full_path, 'w', encoding='utf-8') as f:
                    json.dump(final_data, f, ensure_ascii=False, indent=4)
                logger.debug(f"  ➜ 已刷新本地元数据: {filename}")
            
        except Exception as e:
            logger.error(f"更新本地缓存文件失败: {full_path}, 错误: {e}")

    # --- 通用的元数据刷新辅助函数 ---
    def _refresh_series_metadata(self, tmdb_id: str, item_name: str, item_id: Optional[str]) -> Optional[tuple]:
        """
        通用辅助函数：
        1. ★★★ 调用 TMDb 聚合器并发获取所有数据 (Series + Seasons + Episodes) ★★★
        2. 更新本地 JSON 缓存
        3. 更新数据库基础字段 (Series)
        4. 通知 Emby 刷新元数据
        5. 同步所有季和集的元数据到数据库 (Seasons & Episodes)
        
        返回: (latest_series_data, all_tmdb_episodes, emby_seasons_state) 或 None
        """
        if not self.tmdb_api_key:
            logger.warning("  ➜ 未配置TMDb API Key，跳过元数据刷新。")
            return None

        # ==============================================================================
        # ★★★ 核心优化：直接调用 tmdb.py 中的并发聚合函数 ★★★
        # 这个函数内部已经实现了：
        # 1. 并发请求 (默认5线程)
        # 2. 按季获取 (一次请求拿一整季的集数据，不再一集一集请求)
        # 3. 自动重试和错误处理
        # ==============================================================================
        aggregated_data = tmdb.aggregate_full_series_data_from_tmdb(tmdb_id, self.tmdb_api_key, max_workers=5)

        if not aggregated_data:
            logger.error(f"  ➜ 无法聚合 '{item_name}' 的TMDb详情，元数据刷新中止。")
            return None

        # ======================================================================
        # ★★★ 核心优化：追剧专用轻量级翻译 (关闭演员翻译以加速) ★★★
        # ======================================================================
        if self.ai_translator:
            # 临时伪造配置，强行关闭演员/角色翻译 (因为追剧刷新本来就不会写入演员数据)
            refresh_config = self.config.copy()
            refresh_config[constants.CONFIG_OPTION_AI_TRANSLATE_ACTOR_ROLE] = False
            
            helpers.translate_tmdb_metadata_recursively(
                item_type='Series',
                tmdb_data=aggregated_data,
                ai_translator=self.ai_translator,
                item_name=item_name,
                tmdb_api_key=self.tmdb_api_key,
                config=refresh_config # <--- 使用伪造的配置
            )

        # ======================================================================
        # ★★★ 新增：统一构建 episodes_details 字典 (解决真假美猴王报错核心) ★★★
        # ======================================================================
        unified_episodes_dict = {}
        for season_details in aggregated_data.get('seasons_details', []):
            for ep in season_details.get('episodes', []):
                s_num = ep.get('season_number')
                e_num = ep.get('episode_number')
                if s_num is not None and e_num is not None:
                    unified_episodes_dict[f"S{s_num}E{e_num}"] = ep
                    
        # 兜底确保 poster_path 存在 (有些剧 TMDb 只返回 still_path)
        for ep_key, ep in unified_episodes_dict.items():
            if ep.get('still_path') and not ep.get('poster_path'):
                ep['poster_path'] = ep['still_path']

        # ======================================================================
        # ★★★ 核心修复：真假美猴王 (临时 ID 资产转移) ★★★
        # ======================================================================
        try:
            watchlist_db.transfer_dummy_episode_assets(tmdb_id, unified_episodes_dict)
        except Exception as e_dummy:
            logger.warning(f"  ➜ 临时 ID 资产转移时出错 (忽略并继续): {e_dummy}")

        # ======================================================================
        # ★★★ 老六专属：无简介笑话占位功能 (追剧刷新极简版) ★★★
        # ======================================================================
        if self.config.get("ai_joke_fallback", False) and self.ai_translator:
            jokes_to_generate = {}
            if not aggregated_data['series_details'].get("overview"):
                jokes_to_generate["main"] = item_name
                
            for ep_key, ep in unified_episodes_dict.items():
                if not ep.get("overview"):
                    jokes_to_generate[ep_key] = f"{item_name} {ep_key}"

            if jokes_to_generate:
                logger.info(f"  ➜ [老六模式] 追剧发现 {len(jokes_to_generate)} 处缺失简介，呼叫 AI...")
                generated_jokes = self.ai_translator.batch_generate_jokes(jokes_to_generate)
                if "main" in generated_jokes:
                    aggregated_data['series_details']["overview"] = generated_jokes["main"]
                for ep_key, ep in unified_episodes_dict.items():
                    if ep_key in generated_jokes:
                        ep["overview"] = generated_jokes[ep_key]

        # 解包数据并应用分级
        latest_series_data = aggregated_data['series_details']
        try:
            helpers.apply_rating_logic(latest_series_data, latest_series_data, 'Series')
        except Exception as e:
            pass
        
        # 2. 将 TMDb 最新数据写入本地 JSON
        self._save_local_json(f"override/tmdb-tv/{tmdb_id}/series.json", latest_series_data)

        # 3. 更新数据库 (Series 层级)
        content_ratings = latest_series_data.get("content_ratings", {}).get("results", [])
        official_rating_json = {'US': 'XXX'} if latest_series_data.get('adult') else {r.get("iso_3166_1"): r.get("rating") for r in content_ratings if r.get("iso_3166_1") and r.get("rating")}
        # 2. 处理类型 (Genres)
        genres_list = [{"id": g.get('id', 0), "name": utils.GENRE_TRANSLATION_PATCH.get(g.get('name'), g.get('name'))} for g in latest_series_data.get("genres", []) if isinstance(g, dict)]
        # 3. 处理关键词 (Keywords)
        keywords_json = [{"id": k["id"], "name": k["name"]} for k in latest_series_data.get("keywords", {}).get("results", [])]
        # 4. 处理制作公司 (Production Companies) 
        production_companies_json = [{"id": p["id"], "name": p["name"], "logo_path": p.get("logo_path")} for p in latest_series_data.get("production_companies", [])]
        # 5. 处理播出网络 (Networks)
        networks_json = [{"id": n["id"], "name": n["name"], "logo_path": n.get("logo_path")} for n in latest_series_data.get("networks", [])]
        # 6. 处理产地
        countries = latest_series_data.get("origin_country", [])
        countries_json = countries if isinstance(countries, list) else [countries]

        # 构造更新字典
        series_updates = {
            "original_title": latest_series_data.get("original_name"),
            "overview": latest_series_data.get("overview"),
            "poster_path": latest_series_data.get("poster_path"),
            "release_date": latest_series_data.get("first_air_date") or None,
            "release_year": int(latest_series_data.get("first_air_date")[:4]) if latest_series_data.get("first_air_date") else None,
            "original_language": latest_series_data.get("original_language"),
            "watchlist_tmdb_status": latest_series_data.get("status"),
            "total_episodes": latest_series_data.get("number_of_episodes", 0),
            "rating": latest_series_data.get("vote_average"),
            "official_rating_json": json.dumps(official_rating_json) if official_rating_json else None,
            "genres_json": json.dumps(genres_list) if genres_list else None,
            "keywords_json": json.dumps(keywords_json) if keywords_json else None,
            "production_companies_json": json.dumps(production_companies_json) if production_companies_json else None,
            "networks_json": json.dumps(networks_json) if networks_json else None,
            "countries_json": json.dumps(countries_json) if countries_json else None
        }
        media_db.update_media_metadata_fields(tmdb_id, 'Series', series_updates)
        logger.debug(f"  ➜ 已全量刷新 '{item_name}' 的 Series 元数据。")

        # 4. 处理季和集的数据 (保存 JSON + 收集列表)
        all_tmdb_episodes = list(unified_episodes_dict.values())
        for season_details in aggregated_data.get('seasons_details', []):
            season_num = season_details.get("season_number")
            if season_num is not None:
                self._save_local_json(f"override/tmdb-tv/{tmdb_id}/season-{season_num}.json", season_details)
                for ep in season_details.get("episodes", []):
                    ep_num = ep.get("episode_number")
                    if ep_num is not None:
                        self._save_local_json(f"override/tmdb-tv/{tmdb_id}/season-{season_num}-episode-{ep_num}.json", ep)

        # ★★★ 4.5 并发下载缺失的图片 ★★★
        try:
            import extensions
            if extensions.media_processor_instance:
                logger.debug(f"  ➜ 正在检查并下载 '{item_name}' 缺失的图片(含最新分集)...")
                extensions.media_processor_instance.download_images_from_tmdb(
                    tmdb_id=tmdb_id,
                    item_type='Series',
                    aggregated_tmdb_data=aggregated_data
                )
        except Exception as e_img:
            logger.warning(f"  ➜ 追剧刷新时下载图片失败: {e_img}")

        # 5. 通知 Emby 刷新元数据 
        if item_id:
            emby.refresh_emby_item_metadata(
                item_emby_id=item_id,
                emby_server_url=self.emby_url,
                emby_api_key=self.emby_api_key,
                user_id_for_ops=self.emby_user_id,
                replace_all_metadata_param=True,
                item_name_for_log=item_name
            )

        # 6. 同步季和集到数据库 
        emby_seasons_state = media_db.get_series_local_children_info(tmdb_id)
        
        try:
            # 注意：这里传入的 tmdb_seasons 应该是包含基础信息的列表
            # aggregated_data['series_details']['seasons'] 包含了季的基础信息（集数、海报等）
            # 而 seasons_list 包含了完整的集信息
            # sync_series_children_metadata 需要的是基础季列表和完整集列表
            media_db.sync_series_children_metadata(
                parent_tmdb_id=tmdb_id,
                seasons=latest_series_data.get("seasons", []), 
                episodes=all_tmdb_episodes,
                local_in_library_info=emby_seasons_state
            )
            logger.debug(f"  ➜ 已同步 '{item_name}' 的季/集元数据到数据库。")
        except Exception as e_sync:
            logger.error(f"  ➜ 同步 '{item_name}' 子项目数据库时出错: {e_sync}", exc_info=True)
        
        return latest_series_data, all_tmdb_episodes, emby_seasons_state
    
    # ★★★ 辅助方法：检查是否满足自动待定条件 ★★★
    def _check_auto_pending_condition(self, series_details: Dict[str, Any], auto_pending_cfg: Dict = None) -> bool:
        """
        检查剧集最新季是否满足“自动待定”条件。
        优化点：
        1. 使用 UTC 时间，避免时区误差。
        2. 逻辑与 helpers.py 保持一致 (Days <= Threshold AND Count <= Threshold)。
        3. 直接使用 series_details 中的 episode_count，无需额外 API 请求。
        """
        try:
            # 1. 获取配置
            if auto_pending_cfg is None:
                watchlist_cfg = settings_db.get_setting('watchlist_config') or {}
                auto_pending_cfg = watchlist_cfg.get('auto_pending', {})
            
            if not auto_pending_cfg.get('enabled', False):
                return False

            threshold_days = int(auto_pending_cfg.get('days', 30))
            threshold_episodes = int(auto_pending_cfg.get('episodes', 1))
            
            # 使用 UTC 时间
            today = datetime.now(timezone.utc).date()

            # 2. 获取季列表
            seasons = series_details.get('seasons', [])
            if not seasons: return False
            
            # 3. 找到“最新”的一季 (过滤掉第0季，按季号倒序取第一个)
            valid_seasons = sorted([s for s in seasons if s.get('season_number', 0) > 0], 
                                   key=lambda x: x['season_number'], reverse=True)
            
            if not valid_seasons: return False
            
            latest_season = valid_seasons[0]
            
            # 4. 核心判断
            air_date_str = latest_season.get('air_date')
            # 直接读取 TMDb 官方提供的该季总集数 (这是最准确的字段)
            episode_count = latest_season.get('episode_count', 0)

            if air_date_str:
                try:
                    air_date = datetime.strptime(air_date_str, '%Y-%m-%d').date()
                    days_diff = (today - air_date).days
                    
                    # 逻辑：
                    # 1. days_diff >= 0: 必须是已经开播的（未来的剧集由其他逻辑处理）
                    # 2. days_diff <= threshold_days: 开播时间在观察期内 (如30天)
                    # 3. episode_count <= threshold_episodes: 集数很少 (如只有1集)
                    # 只有同时满足这三点，才认为是“刚开播且信息不全”，需要待定
                    if (days_diff >= 0) and (days_diff <= threshold_days) and (episode_count <= threshold_episodes):
                        logger.info(f"  ➜ [自动待定] 触发: S{latest_season.get('season_number')} 上线{days_diff}天, 集数{episode_count} (阈值: {threshold_episodes})")
                        return True
                except ValueError:
                    pass
            
            return False
        except Exception as e:
            logger.warning(f"检查自动待定条件时出错: {e}")
            return False

    # ★★★ 辅助方法：同步状态给 MoviePilot ★★★
    def _sync_status_to_moviepilot(
        self,
        tmdb_id: str,
        series_name: str,
        series_details: Dict[str, Any],
        final_status: str,
        old_status: str = None,
        all_tmdb_episodes: Optional[List[Dict[str, Any]]] = None,
        real_next_episode: Optional[Dict[str, Any]] = None,
    ):
        """由订阅助手增强版统一同步 MoviePilot 订阅状态。"""
        try:
            SubscribeAssistantManager(self.config).sync_series(
                tmdb_id=tmdb_id,
                series_name=series_name,
                series_details=series_details,
                final_status=final_status,
                old_status=old_status,
                all_tmdb_episodes=all_tmdb_episodes or [],
                real_next_episode=real_next_episode or {},
            )
            return
        except Exception as assistant_error:
            logger.warning(f"  ➜ [订阅助手] 增强同步失败，已停止旧 MP 订阅策略回退: {assistant_error}", exc_info=True)

    def _check_season_consistency(self, tmdb_id: str, season_number: int, expected_episode_count: int) -> bool:
        """
        检查指定季的本地文件是否满足“无需洗版”的条件：
        1. 集数已齐 (本地集数 >= TMDb集数)
        2. 一致性达标 (分辨率、制作组、编码 必须完全统一)
        """
        try:
            with connection.get_db_connection() as conn:
                cursor = conn.cursor()
                # 获取该季所有集的文件资产信息
                sql = """
                    SELECT asset_details_json 
                    FROM media_metadata 
                    WHERE parent_series_tmdb_id = %s 
                      AND season_number = %s 
                      AND item_type = 'Episode'
                      AND in_library = TRUE
                """
                cursor.execute(sql, (tmdb_id, season_number))
                rows = cursor.fetchall()

            local_episode_count = len(rows)
            if expected_episode_count and local_episode_count < expected_episode_count:
                logger.info(
                    f"  ➜ [一致性检查] 第 {season_number} 季 本地集数不足: "
                    f"{local_episode_count}/{expected_episode_count}，不能视为完结达标。"
                )
                return False

            # 检查一致性 (分辨率、制作组、编码)
            resolutions = set()
            groups = set()
            codecs = set()

            for row in rows:
                assets = row.get('asset_details_json')
                if not assets: continue
                
                # 取主文件 (第一个)
                main_asset = assets[0]
                
                resolutions.add(main_asset.get('resolution_display', 'Unknown'))
                codecs.add(main_asset.get('codec_display', 'Unknown'))
                
                # 制作组处理：取第一个识别到的组，如果没有则标记为 Unknown
                raw_groups = main_asset.get('release_group_raw', [])
                group_name = raw_groups[0] if raw_groups else 'Unknown'
                groups.add(group_name)

            # 判定逻辑：所有集合长度必须为 1 (即只有一种规格)
            is_consistent = (len(resolutions) == 1 and len(groups) == 1 and len(codecs) == 1)
            
            if is_consistent:
                # 获取唯一的那个规格，用于日志展示
                res = list(resolutions)[0]
                grp = list(groups)[0]
                logger.info(f"  ➜ [一致性检查] 第 {season_number} 季 完美达标: [{res} / {grp}]，跳过洗版。")
                return True
            else:
                logger.info(f"  ➜ [一致性检查] 第 {season_number} 季 版本混杂，需要洗版。分布: 分辨率{resolutions}, 制作组{groups}, 编码{codecs}")
                return False

        except Exception as e:
            logger.error(f"  ➜ 检查 第 {season_number} 季 一致性时出错: {e}")
            return False # 出错默认不跳过，继续洗版以防万一

    def _close_completed_subscription_status(self, tmdb_id: str, series_name: str, final_status: str, allow_season_closeout: bool = False) -> int:
        """无洗版事务时，收口本地已集齐季的 ETK 订阅状态。"""
        if final_status != STATUS_COMPLETED and not allow_season_closeout:
            return 0
        try:
            with connection.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM media_metadata
                        WHERE parent_series_tmdb_id = %s
                          AND item_type IN ('Season', 'Episode')
                          AND active_washing = TRUE
                        """,
                        (str(tmdb_id),),
                    )
                    row = cursor.fetchone() or {}
                    active_count = _safe_int(row.get('count'))
                    if active_count > 0:
                        logger.info(
                            "  ➜ [订阅收口] 《%s》仍有 %s 条全集/分集洗版事务，保留订阅状态。",
                            series_name or tmdb_id,
                            active_count,
                        )
                        return 0

                    cursor.execute(
                        """
                        WITH season_stats AS (
                            SELECT
                                s.tmdb_id,
                                s.season_number,
                                s.subscription_status,
                                COALESCE(s.total_episodes, 0) AS total_episodes,
                                COUNT(e.tmdb_id) FILTER (WHERE e.in_library = TRUE) AS local_count
                            FROM media_metadata s
                            LEFT JOIN media_metadata e
                              ON e.parent_series_tmdb_id = s.parent_series_tmdb_id
                             AND e.item_type = 'Episode'
                             AND e.season_number = s.season_number
                            WHERE s.parent_series_tmdb_id = %s
                              AND s.item_type = 'Season'
                              AND s.season_number > 0
                            GROUP BY s.tmdb_id, s.season_number, s.subscription_status, s.total_episodes
                        ),
                        completed_subscribed_seasons AS (
                            SELECT tmdb_id
                            FROM season_stats
                            WHERE total_episodes > 0
                              AND local_count >= total_episodes
                              AND subscription_status IN ('REQUESTED', 'WANTED', 'SUBSCRIBED', 'PAUSED', 'PENDING_RELEASE')
                        ),
                        has_open_season AS (
                            SELECT 1
                            FROM season_stats
                            WHERE (
                                   total_episodes <= 0
                                OR local_count < total_episodes
                                OR (
                                      subscription_status IN ('REQUESTED', 'WANTED', 'SUBSCRIBED', 'PAUSED', 'PENDING_RELEASE')
                                  AND NOT (total_episodes > 0 AND local_count >= total_episodes)
                                )
                            )
                            LIMIT 1
                        )
                        UPDATE media_metadata
                        SET subscription_status = 'NONE',
                            subscription_sources_json = '[]'::jsonb,
                            ignore_reason = NULL
                        WHERE (
                              (tmdb_id = %s AND item_type = 'Series' AND %s AND NOT EXISTS (SELECT 1 FROM has_open_season))
                           OR (item_type = 'Season' AND tmdb_id IN (SELECT tmdb_id FROM completed_subscribed_seasons))
                        )
                          AND subscription_status IN ('REQUESTED', 'WANTED', 'SUBSCRIBED', 'PAUSED', 'PENDING_RELEASE')
                        """,
                        (str(tmdb_id), str(tmdb_id), final_status == STATUS_COMPLETED),
                    )
                    changed = cursor.rowcount
                    conn.commit()
            if changed > 0:
                logger.info(
                    "  ➜ [订阅收口] 《%s》已完结且无洗版事务，已清理 %s 条 ETK 订阅状态。",
                    series_name or tmdb_id,
                    changed,
                )
            return changed
        except Exception as e:
            logger.warning("  ➜ [订阅收口] 《%s》完结订阅状态收口失败：%s", series_name or tmdb_id, e, exc_info=True)
            return 0

    def _handle_auto_resub_ended(self, tmdb_id: str, series_name: str, season_number: int, episode_count: int):
        """旧 ETK 完结洗版入口已停用，MoviePilot 订阅由订阅助手增强版统一接管。"""
        logger.info(
            "  ➜ [订阅助手] 已拦截旧完结洗版入口：《%s》S%s 不再取消/重建 MoviePilot 订阅。",
            series_name,
            season_number,
        )

    # --- 尝试从豆瓣获取总集数 ---
    def _try_fetch_douban_episode_count(self, series_name: str, season_number: int, year: str, imdb_id: Optional[str] = None, season_name: Optional[str] = None) -> Optional[int]:
        """
        尝试从豆瓣获取剧集的总集数。
        策略：
        1. 优先使用 IMDb ID (如果提供)。
        2. 特殊季名优先：如果 TMDb 返回了特殊的季名（如“重返天南”），则优先尝试 "剧名 季名"。
        3. 默认搜索兜底：剧名+季号 / 剧名+第X季 (如 "乡村爱情18", "凡人修仙传 第8季")。
        """
        if not self.douban_api or not self.config.get(constants.CONFIG_OPTION_DOUBAN_ENABLE_ONLINE_API, True):
            return None

        import re
        try:
            search_candidates = []
            
            # ★★★ 物理斩断年份 ★★★
            # 只要是第2季及以上，直接把年份干掉，绝对不传给豆瓣！
            if season_number > 1:
                year = None
            
            # 1. 优先处理非标准季名 (例如 "重返天南")
            if season_name and season_number > 1:
                is_generic = bool(re.search(r'(第\s*[\d一二三四五六七八九十]+\s*季|Season\s*\d+)', season_name, re.IGNORECASE))
                if not is_generic:
                    search_candidates.append(f"{series_name} {season_name}")
            
            # 2. 补充标准搜索名称作为兜底
            if season_number > 1:
                search_candidates.append(f"{series_name}{season_number}")
                search_candidates.append(f"{series_name} 第{season_number}季")
            else:
                search_candidates.append(series_name)

            logger.debug(f"  ➜ [豆瓣辅助] 准备查询 《{series_name}》第 {season_number} 季。IMDb: {imdb_id}, 候选搜索: {search_candidates}, 年份: {year}")

            douban_id = None
            
            # 3. 依次使用候选词尝试匹配豆瓣条目
            for search_string in search_candidates:
                match_result = self.douban_api.match_info(
                    name=search_string, 
                    imdbid=imdb_id, 
                    mtype='tv', 
                    year=year,           # 这里如果是后续季，绝对是 None
                    season=season_number,
                    season_name=season_name
                )
                
                if match_result and match_result.get('id'):
                    douban_id = match_result['id']
                    logger.debug(f"  ➜ [豆瓣辅助] 匹配成功: '{search_string}' -> 豆瓣 ID: {douban_id}")
                    break
                else:
                    logger.debug(f"  ➜ [豆瓣辅助] 候选词 '{search_string}' 未匹配到条目，尝试下一个...")
            
            if not douban_id:
                return None
            
            # 4. 获取详情提取集数
            details = self.douban_api._get_subject_details(douban_id, "tv")
            
            if details and not details.get("error"):
                ep_count = details.get('episodes_count')
                if not ep_count and details.get('episodes_count_str'):
                     try: ep_count = int(details.get('episodes_count_str'))
                     except: pass
                
                if ep_count:
                    logger.debug(f"  ➜ [豆瓣辅助] 集数获取成功: ID {douban_id} ({details.get('title')}) -> {ep_count} 集")
                    return int(ep_count)
            
            return None

        except Exception as e:
            logger.warning(f"  ➜ 尝试从豆瓣获取集数失败 (《{series_name}》第 {season_number} 季): {e}")
            return None
    
    # ★★★ 核心处理逻辑：单个剧集的所有操作在此完成 ★★★
    def _process_one_series(self, series_data: Dict[str, Any]):
        tmdb_id = series_data.get('tmdb_id')
        if not tmdb_id:
            logger.warning(f"  ➜ 追剧记录缺少 tmdb_id，跳过。数据: {series_data}")
            return

        emby_ids = series_data.get('emby_item_ids_json', [])
        item_id = emby_ids[0] if emby_ids else None

        item_name = self._get_safe_series_name(series_data)
        series_data['item_name'] = item_name

        old_status = series_data.get('watching_status') 
        is_force_ended = bool(series_data.get('force_ended', False))
        
        logger.info(f"  ➜ 【追剧检查】正在处理: '{item_name}' (TMDb ID: {tmdb_id})")

        if not item_id:
            logger.warning(f"  ➜ 剧集 '{item_name}' 在数据库中没有关联的 Emby ID，跳过。")
            return

        # =====================================================================
        # ★★★ 神医联动兜底：追剧刷新前，反查 Emby 确认剧集组 ID 是否被外部修改 ★★★
        # =====================================================================
        try:
            emby_details = emby.get_emby_item_details(item_id, self.emby_url, self.emby_api_key, self.emby_user_id, fields="ProviderIds")
            if emby_details:
                emby_tmdb_eg = emby_details.get("ProviderIds", {}).get("TmdbEg")
                current_db_eg = watchlist_db.get_episode_group_id(str(tmdb_id))
                
                # 如果剧集组结构发生了任何改变 (包括新增、修改、取消)
                if emby_tmdb_eg != current_db_eg:
                    logger.info(f"  ➜ 💡 [神医联动] 追剧检查时，发现剧集组 ID 发生变更 ({current_db_eg} -> {emby_tmdb_eg})，正在同步到本地...")
                    watchlist_db.set_episode_group_id(str(tmdb_id), emby_tmdb_eg if emby_tmdb_eg else None)
                    
                    # ★★★ 呼叫核心处理器，强行重构底层物理数据库 ★★★
                    import extensions
                    if extensions.media_processor_instance:
                        logger.info(f"  ➜ 🔄 [结构坍塌重建] 正在召唤核心处理器，对《{item_name}》执行深度物理扫库重组...")
                        # force_full_update=True 会强制核心处理器去拉取新结构、查 Emby 硬盘并完美匹配在库状态
                        extensions.media_processor_instance.process_single_item(item_id, force_full_update=True)
                        logger.info(f"  ➜ 🔄 [结构坍塌重建] 物理数据库重组完毕，继续追剧判定逻辑。")
                        
        except Exception as e:
            logger.warning(f"  ➜ 追剧检查时，同步 Emby 剧集组信息失败: {e}")
        
        # --- 获取配置 ---
        watchlist_cfg = settings_db.get_setting('watchlist_config') or {}
        auto_pending_cfg = watchlist_cfg.get('auto_pending', {})

        # 调用通用辅助函数刷新元数据
        refresh_result = self._refresh_series_metadata(tmdb_id, item_name, item_id)
        if not refresh_result:
            return # 刷新失败，中止后续逻辑
        
        latest_series_data, all_tmdb_episodes, emby_seasons = refresh_result

        # ==================== 季总集数锁定过滤器 ====================
        # 如果总集数被锁定，我们需要剔除 TMDb 返回的“多余”集数
        # 这样后续的“下一集计算”和“缺集计算”就不会看到这些不存在的集了
        try:
            # 1. 获取所有季的锁定配置
            seasons_lock_map = watchlist_db.get_series_seasons_lock_info(tmdb_id)
            
            # 2. 获取豆瓣辅助修正开关配置
            enable_douban_correction = watchlist_cfg.get('douban_count_correction', False)
            
            # A. 确定最新季
            tmdb_seasons_list = latest_series_data.get('seasons', [])
            valid_tmdb_seasons = sorted(
                [s for s in tmdb_seasons_list if s.get('season_number', 0) > 0], 
                key=lambda x: x['season_number'], 
                reverse=True
            )
            
            if valid_tmdb_seasons:
                latest_season_info = valid_tmdb_seasons[0]
                latest_s_num = latest_season_info.get('season_number')
                current_tmdb_count = latest_season_info.get('episode_count', 0)
                
                # B. 检查锁定状态
                is_locked = False
                locked_count = 0
                if seasons_lock_map and latest_s_num in seasons_lock_map:
                    is_locked = seasons_lock_map[latest_s_num].get('locked', False)
                    locked_count = seasons_lock_map[latest_s_num].get('count', 0)
                
                # ★★★ 新增逻辑：动态破除锁定 (解决锁死不更新Bug) ★★★
                needs_douban_check = False
                enable_douban_correction = watchlist_cfg.get('douban_count_correction', False)
                
                if self.config.get(constants.CONFIG_OPTION_DOUBAN_ENABLE_ONLINE_API, True) and enable_douban_correction:
                    if not is_locked:
                        needs_douban_check = True
                    elif current_tmdb_count > locked_count:
                        # 核心破壁：TMDb集数变多了，说明加更了，必须去豆瓣重新核实！
                        logger.info(f"  ➜ [动态加更检测] 《{item_name}》第{latest_s_num}季 TMDb最新集数({current_tmdb_count}) > 锁定集数({locked_count})，触发重新核实...")
                        needs_douban_check = True

                # C. 执行豆瓣查询或更新
                if needs_douban_check:
                    release_date = latest_season_info.get('air_date') or latest_series_data.get('first_air_date')
                    year = release_date[:4] if release_date else ""
                    
                    target_imdb_id = None
                    if latest_s_num == 1:
                        external_ids = latest_series_data.get('external_ids', {})
                        target_imdb_id = external_ids.get('imdb_id')
                        
                    # 提取 TMDb 最新的季名称
                    latest_season_name = latest_season_info.get('name')
                    
                    douban_count = self._try_fetch_douban_episode_count(
                        series_name=item_name, 
                        season_number=latest_s_num, 
                        year=year,
                        imdb_id=target_imdb_id,
                        season_name=latest_season_name
                    )
                    
                    # 信任豆瓣权威数据，查到即锁定
                    if douban_count and douban_count > 0:
                        if is_locked and douban_count > locked_count:
                            logger.info(f"  ✨ [豆瓣修正更新] 豆瓣也已更新集数 ({locked_count} -> {douban_count})！正在更新锁定...")
                        elif douban_count != current_tmdb_count:
                            logger.info(f"  ✨ [豆瓣修正] 《{item_name}》第{latest_s_num}季 TMDb集数({current_tmdb_count}) -> 豆瓣集数({douban_count})。正在锁定...")
                        else:
                            logger.info(f"  ➜ [豆瓣锁定] 《{item_name}》第{latest_s_num}季 集数与豆瓣一致({douban_count})。正在锁定以防TMDb变动...")
                        
                        # 1. 更新数据库并锁定 (locked=True)
                        watchlist_db.update_specific_season_total_episodes(
                            tmdb_id, latest_s_num, douban_count, locked=True
                        )
                        
                        # 2. 立即更新内存中的数据
                        latest_season_info['episode_count'] = douban_count
                        if len(valid_tmdb_seasons) == 1:
                            latest_series_data['number_of_episodes'] = douban_count
                            
                        # 3. 刷新锁缓存
                        if not seasons_lock_map: seasons_lock_map = {}
                        seasons_lock_map[latest_s_num] = {'locked': True, 'count': douban_count}
                    else:
                        logger.debug(f"  ➜ [豆瓣辅助] 《{item_name}》第{latest_s_num}季 未获取到有效集数，跳过修正。")
                else:
                    if is_locked:
                        logger.debug(f"  ➜ 《{item_name}》第{latest_s_num}季 已锁定为 {locked_count} 集，无加更迹象，跳过豆瓣查询。")
                    else:
                        logger.debug(f"  ➜ 《{item_name}》第{latest_s_num}季 未锁定，且豆瓣修正未启用，跳过。")
            
            if seasons_lock_map:
                for season_obj in latest_series_data.get('seasons', []):
                    s_num = season_obj.get('season_number')
                    # 如果该季在锁定表中，且已启用锁定
                    if s_num in seasons_lock_map and seasons_lock_map[s_num].get('locked'):
                        locked_count = seasons_lock_map[s_num].get('count')
                        # 如果 TMDb 原生集数与锁定集数不一致，强制覆盖
                        if locked_count is not None and season_obj.get('episode_count') != locked_count:
                            logger.debug(f"  ➜ [元数据同步] 将 S{s_num} 的总集数由 TMDb({season_obj.get('episode_count')}) 修正为锁定值({locked_count})，以便正确判定完结。")
                            season_obj['episode_count'] = locked_count
                            
                            # 如果是单季剧，通常 series 级的 number_of_episodes 也需要修正
                            if len(valid_tmdb_seasons) == 1:
                                latest_series_data['number_of_episodes'] = locked_count
                filtered_episodes = []
                discarded_count = 0
                
                for ep in all_tmdb_episodes:
                    s_num = ep.get('season_number')
                    e_num = ep.get('episode_number')
                    
                    # 获取该季的锁定配置
                    lock_info = seasons_lock_map.get(s_num)
                    
                    # 判断逻辑：
                    # 如果该季存在锁定配置，且已开启锁定，且当前集号 > 锁定集数 -> 剔除
                    if (lock_info and 
                        lock_info.get('locked') and 
                        e_num is not None and 
                        e_num > (lock_info.get('count') or 0)):
                        
                        discarded_count += 1
                        # 仅在第一次剔除时打印详细日志，避免刷屏
                        if discarded_count == 1:
                            lock_count = lock_info.get('count') or 0
                            logger.info(f"  ➜ [分季锁定生效] S{s_num} 锁定为 {lock_count} 集，正在剔除 TMDb 多余集数 (如 S{s_num}E{e_num})...")
                        continue
                    
                    # 否则保留该集
                    filtered_episodes.append(ep)
                
                if discarded_count > 0:
                    logger.info(f"  ➜ 共剔除了 {discarded_count} 个不符合分季锁定规则的集。")
                    all_tmdb_episodes = filtered_episodes
            
            else:
                # 如果没查到任何季信息（罕见），就不做过滤
                pass

        except Exception as e:
            logger.error(f"  ➜ 执行分季锁定过滤时出错: {e}", exc_info=True)

        # 计算状态和缺失信息
        new_tmdb_status = str(latest_series_data.get("status") or "").strip()
        is_ended_on_tmdb = new_tmdb_status in ["Ended", "Canceled"]
        
        # 依然计算缺失信息，用于后续的“补旧番”订阅，但不影响状态判定
        real_next_episode_to_air = self._calculate_real_next_episode(all_tmdb_episodes, emby_seasons)
        missing_info = self._calculate_missing_info(latest_series_data.get('seasons', []), all_tmdb_episodes, emby_seasons)

        today = datetime.now(timezone.utc).date()
        last_episode_to_air = latest_series_data.get("last_episode_to_air")
        paused_until_date = None
        
        tmdb_seasons_list = latest_series_data.get('seasons', [])
        valid_tmdb_seasons = sorted(
            [s for s in tmdb_seasons_list if s.get('season_number', 0) > 0], 
            key=lambda x: x['season_number'], 
            reverse=True
        )

        local_latest_s_episodes = 0
        latest_s_total_episodes = 0
        latest_s_num = 0
        latest_season_local_state = "unknown"  # unknown / not_started / partial / complete

        if valid_tmdb_seasons:
            latest_s_info = valid_tmdb_seasons[0]
            latest_s_num = latest_s_info.get('season_number')
            latest_s_total_episodes = latest_s_info.get('episode_count', 0) or 0
            local_latest_s_episodes = len(emby_seasons.get(latest_s_num, set()))

            if local_latest_s_episodes <= 0:
                latest_season_local_state = "not_started"
            elif latest_s_total_episodes > 0 and local_latest_s_episodes >= latest_s_total_episodes:
                latest_season_local_state = "complete"
            else:
                latest_season_local_state = "partial"

            logger.debug(
                f"  ➜ [本地完结门槛] S{latest_s_num}: 本地 {local_latest_s_episodes}/{latest_s_total_episodes or '未知'}，"
                f"状态={latest_season_local_state}。"
            )

        is_local_latest_season_completed = latest_season_local_state == "complete"
        local_completed_season_numbers = []
        for season_info in valid_tmdb_seasons:
            s_num = _safe_int(season_info.get('season_number'))
            expected_count = _safe_int(season_info.get('episode_count'))
            if s_num > 0 and expected_count > 0 and len(emby_seasons.get(s_num, set())) >= expected_count:
                local_completed_season_numbers.append(s_num)
        has_local_completed_season = bool(local_completed_season_numbers)
        final_status = STATUS_COMPLETED if is_ended_on_tmdb else STATUS_WATCHING
        if is_ended_on_tmdb:
            logger.info(f"  ➜ [追剧判定] 《{item_name}》TMDb 状态={new_tmdb_status}，剧条目标记为“已完结”。")
        else:
            logger.info(f"  ➜ [追剧判定] 《{item_name}》TMDb 状态={new_tmdb_status or '未知'}，剧条目标记为“追剧中”。")
        if latest_s_num:
            logger.info(
                f"  ➜ [追剧判定] 《{item_name}》第 {latest_s_num} 季本地状态："
                f"{local_latest_s_episodes}/{latest_s_total_episodes or '未知'}，"
                f"{'已集齐' if is_local_latest_season_completed else '未集齐'}。"
            )

        # 手动强制完结
        if is_force_ended and final_status != STATUS_COMPLETED:
            final_status = STATUS_COMPLETED
            paused_until_date = None
            logger.warning(f"  ➜ [强制完结生效] 最终状态被覆盖为 '已完结'。")

        # 只有当内部状态是“追剧中”或“已暂停”时，才认为它在“连载中”
        is_truly_airing = final_status in [STATUS_WATCHING, STATUS_PAUSED, STATUS_PENDING]
        logger.info(f"  ➜ 最终判定 '{item_name}' 的真实连载状态为: {is_truly_airing} (内部状态: {translate_internal_status(final_status)})")

        # ======================================================================
        # ★★★ 完结自动洗版逻辑 (TG解耦 + 标志位驱动) ★★★
        # ======================================================================
        logger.debug(f"  ➜ [状态流转] 剧名: {item_name}, 旧状态: {translate_internal_status(old_status)}, 新状态: {translate_internal_status(final_status)}")
        
        # 定义一个变量，用于控制是否更新等待标志
        set_waiting_flag = None
        if (final_status == STATUS_COMPLETED or has_local_completed_season) and old_status in [STATUS_WATCHING, STATUS_PAUSED, STATUS_PENDING] and not is_force_ended:
            watchlist_cfg = settings_db.get_setting('watchlist_config') or {}
            if watchlist_cfg.get('auto_resub_ended', False):
                seasons = latest_series_data.get('seasons', [])
                valid_seasons = sorted([s for s in seasons if s.get('season_number', 0) > 0], key=lambda x: x['season_number'])
                
                if valid_seasons:
                    target_season = valid_seasons[-1]
                    last_s_num = target_season.get('season_number')
                    last_ep_count = target_season.get('episode_count', 0)
                    local_target_count = len(emby_seasons.get(last_s_num, set()))
                    
                    if local_target_count <= 0:
                        logger.info(f"  ➜ [完结洗版跳过] 《{item_name}》S{last_s_num} 本地 0 集，视为未追本季，不触发洗版/等待完结包。")
                    else:
                        logger.info(f"  ➜ [完结洗版] 《{item_name}》由 {translate_internal_status(old_status)} 转为完结，立即提交 MP 洗版。")
                        self._handle_auto_resub_ended(tmdb_id, item_name, last_s_num, last_ep_count)

        # 如果剧集恢复连载，必须清除等待标志，防止误判
        if final_status == STATUS_WATCHING and not has_local_completed_season:
            set_waiting_flag = False

        # 更新追剧数据库
        updates_to_db = {
            "watching_status": final_status, 
            "paused_until": paused_until_date.isoformat() if paused_until_date else None,
            "watchlist_tmdb_status": new_tmdb_status, 
            "watchlist_next_episode_json": json.dumps(real_next_episode_to_air) if real_next_episode_to_air else None,
            "watchlist_missing_info_json": json.dumps(missing_info),
            "last_episode_to_air_json": json.dumps(last_episode_to_air) if last_episode_to_air else None,
            "watchlist_is_airing": is_truly_airing
        }
        
        # ★ 将标志位合入数据库更新字典
        if set_waiting_flag is not None:
            updates_to_db['waiting_for_completed_pack'] = set_waiting_flag
        self._update_watchlist_entry(tmdb_id, item_name, updates_to_db)

        # ======================================================================
        # ★★★ 提前计算季的活跃状态 (供版本锁定使用) ★★★
        # ======================================================================
        active_seasons = set()
        # 规则 A: 如果有明确的下一集待播，该集所属的季肯定是活跃的
        if real_next_episode_to_air and real_next_episode_to_air.get('season_number'):
            active_seasons.add(real_next_episode_to_air['season_number'])
        # 规则 B: 如果有缺失的集（补番），这些集所属的季也是活跃的
        if missing_info.get('missing_episodes'):
            for ep in missing_info['missing_episodes']:
                if ep.get('season_number'): active_seasons.add(ep['season_number'])
        # 规则 C: 如果有整季缺失，且该季已播出，也视为活跃
        if missing_info.get('missing_seasons'):
            for s in missing_info['missing_seasons']:
                if s.get('air_date') and s.get('season_number'):
                    try:
                        s_date = datetime.strptime(s['air_date'], '%Y-%m-%d').date()
                        if s_date <= today: active_seasons.add(s['season_number'])
                    except ValueError: pass
        # 规则 D (兜底规则)
        valid_local_seasons = [s for s in emby_seasons.keys() if s > 0]
        if valid_local_seasons:
            active_seasons.add(max(valid_local_seasons))
        else:
            tmdb_seasons_list = latest_series_data.get('seasons', [])
            valid_tmdb_seasons = [s for s in tmdb_seasons_list if s.get('season_number', 0) > 0]
            if valid_tmdb_seasons:
                active_seasons.add(max(s['season_number'] for s in valid_tmdb_seasons))

        # 调用 DB 模块进行批量更新 (使用上面提前算好的 active_seasons)
        watchlist_db.sync_seasons_watching_status(tmdb_id, list(active_seasons), final_status)

        # ======================================================================
        # ★★★ MP 状态接管与同步 (自动待定 & 自动暂停) ★★★
        # ======================================================================
        self._sync_status_to_moviepilot(
            tmdb_id=tmdb_id, 
            series_name=item_name, 
            series_details=latest_series_data, 
            final_status=final_status,
            old_status=old_status,
            all_tmdb_episodes=all_tmdb_episodes,
            real_next_episode=real_next_episode_to_air,
        )
        self._close_completed_subscription_status(tmdb_id, item_name, final_status)

    # --- 统一的、公开的追剧处理入口 ★★★
    def process_watching_list(self, item_id: Optional[str] = None):
        if item_id:
            logger.trace(f"--- 开始执行单项追剧更新任务 (ItemID: {item_id}) ---")
        else:
            logger.trace("--- 开始执行全量追剧列表更新任务 ---")
        
        series_to_process = self._get_series_to_process(
            where_clause="WHERE status = 'Watching'", 
            item_id=item_id
        )

        if not series_to_process:
            logger.info("  ➜ 追剧列表中没有需要检查的剧集。")
            return

        total = len(series_to_process)
        logger.info(f"  ➜ 发现 {total} 部剧集需要检查更新...")

        for i, series in enumerate(series_to_process):
            if self.is_stop_requested():
                logger.info("  ➜ 追剧列表更新任务被中止。")
                break
            
            if self.progress_callback:
                progress = 10 + int(((i + 1) / total) * 90)
                self.progress_callback(progress, f"正在处理: {series['item_name'][:20]}... ({i+1}/{total})")

            self._process_one_series(series)
            time.sleep(1)

        logger.info("--- 追剧列表更新任务结束 ---")

    # --- 通过对比计算真正的下一待看集 ---
    def _calculate_real_next_episode(self, all_tmdb_episodes: List[Dict], emby_seasons: Dict) -> Optional[Dict]:
        """
        通过对比本地和TMDb全量数据，计算用户真正缺失的第一集。
        【修复版】忽略本地最大季号之前的“整季缺失”，只关注当前季或未来季。
        """
        # 1. 获取本地已有的最大季号 (用于判断什么是"旧季")
        valid_local_seasons = [s for s in emby_seasons.keys() if s > 0]
        max_local_season = max(valid_local_seasons) if valid_local_seasons else 0

        # 2. 获取TMDb上所有非特别季的剧集，并严格按季号、集号排序
        all_episodes_sorted = sorted([
            ep for ep in all_tmdb_episodes 
            if ep.get('season_number') is not None and ep.get('season_number') != 0
        ], key=lambda x: (x.get('season_number', 0), x.get('episode_number', 0)))
        
        # 3. 遍历这个完整列表
        for episode in all_episodes_sorted:
            s_num = episode.get('season_number')
            e_num = episode.get('episode_number')
            
            # ======================= ★★★ 核心修复逻辑 ★★★ =======================
            # 如果这一集所属的季号 < 本地已有的最大季号
            # 并且本地完全没有这一季 (emby_seasons中没有这个key)
            # 说明这是用户故意跳过的“旧季” (例如只追S2，不想要S1)
            # 此时直接 continue 跳过，不要把它当成“待播集”
            if max_local_season > 0 and s_num < max_local_season and s_num not in emby_seasons:
                continue
            # ===================================================================

            if s_num not in emby_seasons or e_num not in emby_seasons.get(s_num, set()):
                # 找到了！这才是基于用户当前进度的“下一集”
                # 可能是当前季的下一集，也可能是新的一季的第一集
                logger.info(f"  ➜ 找到本季缺失的下一集: S{s_num}E{e_num} ('{episode.get('name')}')。")
                return episode
        
        # 4. 如果循环完成，说明本地拥有TMDb上所有的剧集 (或者只缺了未来的)
        logger.info("  ➜ 本地媒体库已拥有当前进度所有剧集，无待播信息。")
        return None
    # --- 计算缺失的季和集 ---
    def _calculate_missing_info(self, tmdb_seasons: List[Dict], all_tmdb_episodes: List[Dict], emby_seasons: Dict) -> Dict:
        """
        【逻辑重生】计算所有缺失的季和集，不再关心播出日期。
        """
        missing_info = {"missing_seasons": [], "missing_episodes": []}
        
        tmdb_episodes_by_season = {}
        for ep in all_tmdb_episodes:
            s_num = ep.get('season_number')
            if s_num is not None and s_num != 0:
                tmdb_episodes_by_season.setdefault(s_num, []).append(ep)

        for season_summary in tmdb_seasons:
            s_num = season_summary.get('season_number')
            if s_num is None or s_num == 0: 
                continue

            # 如果本地没有这个季，则整个季都算缺失
            if s_num not in emby_seasons:
                missing_info["missing_seasons"].append(season_summary)
            else:
                # 如果季存在，则逐集检查缺失
                if s_num in tmdb_episodes_by_season:
                    for episode in tmdb_episodes_by_season[s_num]:
                        e_num = episode.get('episode_number')
                        if e_num is not None and e_num not in emby_seasons.get(s_num, set()):
                            missing_info["missing_episodes"].append(episode)
        return missing_info