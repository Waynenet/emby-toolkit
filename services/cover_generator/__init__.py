# services/cover_generator/__init__.py

import logging
import shutil
import yaml
import json
import random
import requests
import base64
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from gevent import spawn_later, sleep
from database import custom_collection_db, queries_db
import config_manager
import handler.emby as emby 
from extensions import UPDATING_IMAGES

# 静态
from .styles.style_single_1 import create_style_single_1
from .styles.style_single_2 import create_style_single_2
from .styles.style_single_3 import create_style_single_3
from .styles.style_multi_1 import create_style_multi_1
# 动态
from .styles.style_dynamic_1 import create_style_dynamic_1
from .styles.style_dynamic_2 import create_style_dynamic_2
from .styles.style_dynamic_3 import create_style_dynamic_3
from .styles.style_dynamic_multi_1 import create_style_dynamic_multi_1

logger = logging.getLogger(__name__)

class CoverGeneratorService:
    SORT_BY_DISPLAY_NAME = { "Random": "随机", "Latest": "最新添加" }

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._sort_by = self.config.get("sort_by", "Random")
        self._covers_output = self.config.get("covers_output")
        self._covers_input = self.config.get("covers_input")
        self._title_config_str = self.config.get("title_config", "")
        self._cover_style = self.config.get("cover_style", "single_1")
        self._multi_1_blur = self.config.get("multi_1_blur", False)
        self._multi_1_use_primary = self.config.get("multi_1_use_primary", True)
        self._single_use_primary = self.config.get("single_use_primary", False)
        self.data_path = Path(config_manager.PERSISTENT_DATA_PATH) / "cover_generator"
        self.covers_path = self.data_path / "covers"
        self.font_path = self.data_path / "fonts"
        self.covers_path.mkdir(parents=True, exist_ok=True)
        self.font_path.mkdir(parents=True, exist_ok=True)
        self.zh_font_path = None
        self.en_font_path = None
        self.zh_font_path_multi_1 = None
        self.en_font_path_multi_1 = None
        self._fonts_checked_and_ready = False

    def generate_for_library(self, emby_server_id: str, library: Dict[str, Any], item_count: Optional[int] = None, content_types: Optional[List[str]] = None, custom_collection_data: Optional[Dict] = None):
        sleep(0.5) 
        sort_by_name = self.SORT_BY_DISPLAY_NAME.get(self._sort_by, self._sort_by)
        logger.info(f"  ➜ 开始以排序方式: {sort_by_name} 为媒体库 '{library['Name']}' 生成封面...")
        self.__get_fonts()
        
        image_data_b64 = self.__generate_image_data(emby_server_id, library, item_count, content_types, custom_collection_data)
        if not image_data_b64:
            logger.error(f"  ➜ 为媒体库 '{library['Name']}' 生成封面图片失败。")
            return False
            
        success = self.__set_library_image(emby_server_id, library, image_data_b64)
        if success:
            logger.info(f"  ➜ 成功更新媒体库 '{library['Name']}' 的封面！")
        else:
            logger.error(f"  ➜ 上传封面到媒体库 '{library['Name']}' 失败。")
        return success

    def __generate_image_data(self, server_id: str, library: Dict[str, Any], item_count: Optional[int] = None, content_types: Optional[List[str]] = None, custom_collection_data: Optional[Dict] = None) -> str:
        library_name = library['Name']
        title = self.__get_library_title_from_yaml(library_name)
        custom_image_paths = self.__check_custom_image(library_name)
        if custom_image_paths:
            logger.info(f"  ➜ 发现媒体库 '{library_name}' 的自定义图片，将使用路径模式生成。")
            return self.__generate_image_from_path(library_name, title, custom_image_paths, item_count)
        
        if custom_collection_data and custom_collection_data.get('type') in ['list', 'ai_recommendation_global']:
            tmdb_image_data = self.__generate_from_local_tmdb_metadata(library_name, title, custom_collection_data, item_count)
            if tmdb_image_data:
                return tmdb_image_data

        logger.trace(f"  ➜ 未发现自定义图片，将从服务器 '{server_id}' 获取媒体项作为封面来源。")
        return self.__generate_from_server(server_id, library, title, item_count, content_types, custom_collection_data)

    def __generate_from_local_tmdb_metadata(self, library_name: str, title: Tuple[str, str], custom_collection_data: Dict, item_count: Optional[int]) -> Optional[str]:
        try:
            media_info_list = custom_collection_data.get('generated_media_info_json') or []
            if isinstance(media_info_list, str): media_info_list = json.loads(media_info_list)

            valid_emby_ids = [i for i in media_info_list if i.get('emby_id')]
            if len(valid_emby_ids) >= 3: return None

            candidates = [i for i in media_info_list if i.get('tmdb_id')]
            if not candidates: return None
            if self._sort_by == "Random": random.shuffle(candidates)
            
            limit = 1
            if self._cover_style in ['dynamic_1', 'dynamic_2', 'dynamic_3']: limit = 5
            elif self._cover_style == 'multi_1': limit = 9
            elif self._cover_style == 'dynamic_multi_1': limit = 18
            
            candidates = candidates[:limit]
            tmdb_ids = [str(item['tmdb_id']) for item in candidates]
            metadata_map = queries_db.get_missing_items_metadata(tmdb_ids)
            image_paths = []
            
            for tmdb_id in tmdb_ids:
                meta = metadata_map.get(tmdb_id)
                if meta and meta.get('poster_path'):
                    poster_path = meta['poster_path']
                    full_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                    save_name = f"tmdb_{tmdb_id}.jpg"
                    local_path = self.__download_external_image(full_url, library_name, save_name)
                    if local_path: image_paths.append(local_path)
            
            if not image_paths: return None
            
            subdir = self.covers_path / library_name
            if subdir.exists():
                for i in range(1, 20):
                    old_cache = subdir / f"{i}.jpg"
                    if old_cache.exists():
                        try: old_cache.unlink()
                        except Exception: pass

            return self.__generate_image_from_path(library_name, title, [str(p) for p in image_paths], item_count)

        except Exception as e:
            logger.error(f"  ➜ TMDB 海报兜底流程出错: {e}", exc_info=True)
            return None

    def __download_external_image(self, url: str, library_name: str, filename: str) -> Optional[Path]:
        subdir = self.covers_path / library_name
        subdir.mkdir(parents=True, exist_ok=True)
        filepath = subdir / filename
        if filepath.exists() and filepath.stat().st_size > 0: return filepath
        try:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(max_retries=3)
            session.mount('https://', adapter)
            proxies = config_manager.get_proxies_for_requests()
            if proxies: session.proxies.update(proxies)
            resp = session.get(url, stream=True, timeout=15)
            if resp.status_code == 200:
                with open(filepath, 'wb') as f:
                    shutil.copyfileobj(resp.raw, f)
                return filepath
        except Exception as e: pass
        return None

    def __generate_from_server(self, server_id: str, library: Dict[str, Any], title: Tuple[str, str], item_count: Optional[int] = None, content_types: Optional[List[str]] = None, custom_collection_data: Optional[Dict] = None) -> str:
        required_items_count = 1
        if self._cover_style in ['dynamic_1', 'dynamic_2', 'dynamic_3']: required_items_count = 5
        elif self._cover_style == 'multi_1': required_items_count = 9
        elif self._cover_style == 'dynamic_multi_1': required_items_count = 18

        items = self.__get_valid_items_from_library(server_id, library, required_items_count, content_types, custom_collection_data)
        if not items:
            logger.warning(f"  ➜ 在媒体库 '{library['Name']}' 中找不到任何带有可用图片的媒体项。")
            return None
            
        if self._cover_style in ['single_1', 'single_2', 'single_3']:
            image_url = self.__get_image_url(items[0])
            if not image_url: return None
            image_path = self.__download_image(server_id, image_url, library['Name'], 1)
            if not image_path: return None
            return self.__generate_image_from_path(library['Name'], title, [image_path], item_count)
        else:
            image_paths = []
            for i, item in enumerate(items[:required_items_count]):
                image_url = self.__get_image_url(item)
                if image_url:
                    path = self.__download_image(server_id, image_url, library['Name'], i + 1)
                    if path: image_paths.append(str(path))
            if not image_paths: return None
            return self.__generate_image_from_path(library['Name'], title, image_paths, item_count)

    def __get_valid_items_from_library(self, server_id: str, library: Dict[str, Any], limit: int, content_types: Optional[List[str]] = None, custom_collection_data: Optional[Dict] = None) -> List[Dict]:
        library_id = library.get("Id") or library.get("ItemId")
        library_name = library.get("Name")
        base_url = config_manager.APP_CONFIG.get('emby_server_url')
        api_key = config_manager.APP_CONFIG.get('emby_api_key')
        user_id = config_manager.APP_CONFIG.get('emby_user_id')

        config_limit = self.config.get('max_safe_rating', 8)
        is_whitelisted_library = any(keyword.lower() in library_name.lower() for keyword in ['R级', '限制', '成人', 'Adult', 'Porn', '18+'])
        safe_rating_limit = None if (is_whitelisted_library or config_limit >= 999) else config_limit

        if custom_collection_data and custom_collection_data.get('type') in ['filter', 'ai_recommendation']:
            try:
                definition = custom_collection_data.get('definition_json', {})
                rules = definition.get('rules', [])
                has_rating_rule = any(r.get('field') == 'unified_rating' for r in rules)
                current_limit = safe_rating_limit if not has_rating_rule else None
                db_sort_by = 'Random' if self._sort_by == 'Random' else 'DateCreated'
                
                items_from_db, _ = queries_db.query_virtual_library_items(
                    rules=rules, logic=definition.get('logic', 'AND'), user_id=user_id,
                    limit=limit, offset=0, sort_by=db_sort_by,
                    item_types=definition.get('item_type', ['Movie']),
                    target_library_ids=definition.get('target_library_ids'),
                    max_rating_override=current_limit 
                )
                return self.__fetch_emby_items_by_ids(items_from_db, base_url, api_key, user_id, limit)
            except Exception as e: pass

        custom_collection = custom_collection_data or custom_collection_db.get_custom_collection_by_emby_id(library_id)
        if custom_collection and custom_collection.get('type') in ['list', 'ai_recommendation_global']:
            try:
                media_info_list = custom_collection.get('generated_media_info_json') or []
                if isinstance(media_info_list, str): media_info_list = json.loads(media_info_list)
                valid_emby_ids = [str(item['emby_id']) for item in media_info_list if item.get('emby_id') and str(item.get('emby_id')).lower() != 'none']
                if valid_emby_ids:
                    if self._sort_by == "Random": random.shuffle(valid_emby_ids)
                    return self.__fetch_emby_items_by_ids([{'Id': i} for i in valid_emby_ids[:limit*2]], base_url, api_key, user_id, limit)
                fallback_items = emby.get_emby_library_items(
                    base_url=base_url, api_key=api_key, user_id=user_id, library_ids=[library_id],
                    media_type_filter="Movie,Series,Season,Episode", fields="Id,Name,Type,ImageTags,BackdropImageTags,PrimaryImageTag,PrimaryImageItemId",
                    limit=limit
                )
                return [item for item in fallback_items if self.__get_image_url(item)][:limit]
            except Exception as e: pass
        
        media_type_to_fetch = content_types or (['Movie', 'Series'] if library.get('Type') == 'BoxSet' else {'movies': ['Movie'], 'tvshows': ['Series'], 'music': ['MusicAlbum'], 'boxsets': ['Movie', 'Series'], 'mixed': ['Movie', 'Series'], 'audiobooks': ['AudioBook']}.get(library.get('CollectionType'), ['Movie', 'Series']))
        db_sort_by = 'Random' if self._sort_by == 'Random' else 'DateCreated'
        
        try:
            items_from_db, _ = queries_db.query_virtual_library_items(
                rules=[], logic='AND', user_id=None, limit=limit, offset=0,
                sort_by=db_sort_by, item_types=media_type_to_fetch,
                target_library_ids=[library_id], max_rating_override=safe_rating_limit 
            )
            if items_from_db: return self.__fetch_emby_items_by_ids(items_from_db, base_url, api_key, user_id, limit)
        except Exception as e: pass

        api_limit = limit * 5 if limit < 10 else limit * 2 
        all_items = emby.get_emby_library_items(
            base_url=base_url, api_key=api_key, user_id=user_id, library_ids=[library_id],
            media_type_filter=",".join(media_type_to_fetch), fields="Id,Name,Type,ImageTags,BackdropImageTags,DateCreated,PrimaryImageTag,PrimaryImageItemId",
            sort_by="Random" if self._sort_by == "Random" else "DateCreated", sort_order="Descending" if self._sort_by != "Random" else None,
            limit=api_limit, force_user_endpoint=True
        )
        if not all_items: return []
        valid_items = [item for item in all_items if self.__get_image_url(item)]
        if self._sort_by == "Random": random.shuffle(valid_items)
        return valid_items[:limit]

    def __fetch_emby_items_by_ids(self, items_from_db: List[Dict], base_url: str, api_key: str, user_id: str, limit: int) -> List[Dict]:
        if not items_from_db: return []
        url = f"{base_url.rstrip('/')}/Users/{user_id}/Items"
        headers = {"X-Emby-Token": api_key, "Content-Type": "application/json"}
        params = {'Ids': ",".join([str(item['Id']) for item in items_from_db]), 'Fields': "Id,Name,Type,ImageTags,BackdropImageTags,PrimaryImageTag,PrimaryImageItemId"}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            valid_items = [item for item in resp.json().get('Items', []) if self.__get_image_url(item)]
            if self._sort_by == "Random": random.shuffle(valid_items)
            return valid_items[:limit]
        except Exception: return []

    def __get_image_url(self, item: Dict[str, Any]) -> str:
        item_id = item.get("Id")
        if not item_id: return None
        primary_url, backdrop_url = None, None
        ptag = item.get("ImageTags", {}).get("Primary")
        if ptag: primary_url = f'/emby/Items/{item_id}/Images/Primary?tag={ptag}'
        else:
            ritem, rtag = item.get("PrimaryImageItemId"), item.get("PrimaryImageTag")
            if ritem and rtag: primary_url = f'/emby/Items/{ritem}/Images/Primary?tag={rtag}'
        btags = item.get("BackdropImageTags")
        if btags: backdrop_url = f'/emby/Items/{item_id}/Images/Backdrop/0?tag={btags[0]}'
        
        use_primary = (self._cover_style.startswith('single') or self._cover_style.startswith('dynamic_')) and self._single_use_primary or \
                      (self._cover_style.startswith('multi') or self._cover_style.startswith('dynamic_multi')) and self._multi_1_use_primary
        return primary_url or backdrop_url if use_primary else backdrop_url or primary_url

    def __download_image(self, server_id: str, api_path: str, library_name: str, count: int) -> Path:
        subdir = self.covers_path / library_name
        subdir.mkdir(parents=True, exist_ok=True)
        filepath = subdir / f"{count}.jpg"
        try:
            base_url = config_manager.APP_CONFIG.get('emby_server_url')
            api_key = config_manager.APP_CONFIG.get('emby_api_key')
            path_only, _, query_string = api_path.partition('?')
            path_parts = path_only.strip('/').split('/')
            image_tag = None
            if 'tag=' in query_string:
                image_tag = query_string.split('tag=')[1].split('&')[0]
            if len(path_parts) >= 4 and path_parts[1] == 'Items' and path_parts[3] == 'Images':
                item_id = path_parts[2]
                image_type = path_parts[4]
                success = emby.download_emby_image(
                    item_id=item_id, 
                    image_type=image_type, 
                    image_tag=image_tag,
                    save_path=str(filepath), 
                    emby_server_url=base_url, 
                    emby_api_key=api_key
                )
                if success: return filepath
            else:
                logger.error(f"  ➜ 无法从API路径解析有效的项目ID和图片类型: {api_path}")
        except Exception as e:
            logger.error(f"  ➜ 下载图片失败 ({api_path}): {e}", exc_info=True)
        return None

    def __generate_image_from_path(self, library_name: str, title: Tuple[str, str], image_paths: List[str], item_count: Optional[int] = None) -> str:
        logger.trace(f"  ➜ 正在为 '{library_name}' 从本地路径生成封面 (样式: {self._cover_style})...")
        font_size = (float(self.config.get("zh_font_size", 1)), float(self.config.get("en_font_size", 1)))
        blur = self.config.get("blur_size", 50)
        ratio = self.config.get("color_ratio", 0.8)
        
        if self._cover_style == 'single_1':
            return create_style_single_1(str(image_paths[0]), title, (str(self.zh_font_path), str(self.en_font_path)), font_size=font_size, blur_size=blur, color_ratio=ratio, item_count=item_count, config=self.config)
        elif self._cover_style == 'single_2':
            return create_style_single_2(str(image_paths[0]), title, (str(self.zh_font_path), str(self.en_font_path)), font_size=font_size, blur_size=blur, color_ratio=ratio, item_count=item_count, config=self.config)
        elif self._cover_style == 'single_3':
            return create_style_single_3(str(image_paths[0]), title, (str(self.zh_font_path), str(self.en_font_path)), font_size=font_size, blur_size=blur, color_ratio=ratio, item_count=item_count, config=self.config)
        
        elif self._cover_style == 'dynamic_1':
            return create_style_dynamic_1(image_paths, title, (str(self.zh_font_path), str(self.en_font_path)), font_size=font_size, blur_size=blur, color_ratio=ratio, item_count=item_count, config=self.config)
        elif self._cover_style == 'dynamic_2':
            return create_style_dynamic_2(image_paths, title, (str(self.zh_font_path), str(self.en_font_path)), font_size=font_size, blur_size=blur, color_ratio=ratio, item_count=item_count, config=self.config)
        elif self._cover_style == 'dynamic_3':
            return create_style_dynamic_3(image_paths, title, (str(self.zh_font_path), str(self.en_font_path)), font_size=font_size, blur_size=blur, color_ratio=ratio, item_count=item_count, config=self.config)
        
        z_multi = self.zh_font_path_multi_1 if self.zh_font_path_multi_1 and self.zh_font_path_multi_1.exists() else self.zh_font_path
        e_multi = self.en_font_path_multi_1 if self.en_font_path_multi_1 and self.en_font_path_multi_1.exists() else self.en_font_path
        f_multi = (str(z_multi), str(e_multi))
        sz_multi = (float(self.config.get("zh_font_size_multi_1", 1)), float(self.config.get("en_font_size_multi_1", 1)))
        blur_multi = self.config.get("blur_size_multi_1", 50)
        ratio_multi = self.config.get("color_ratio_multi_1", 0.8)
        lib_dir = self.covers_path / library_name
        
        if self._cover_style == 'multi_1':
            self.__prepare_multi_images(lib_dir, image_paths, 9)
            return create_style_multi_1(str(lib_dir), title, f_multi, font_size=sz_multi, is_blur=self._multi_1_blur, blur_size=blur_multi, color_ratio=ratio_multi, item_count=item_count, config=self.config)
        elif self._cover_style == 'dynamic_multi_1':
            self.__prepare_multi_images(lib_dir, image_paths, 18)
            return create_style_dynamic_multi_1(str(lib_dir), title, f_multi, font_size=sz_multi, is_blur=self._multi_1_blur, blur_size=blur_multi, color_ratio=ratio_multi, item_count=item_count, config=self.config)
            
        return None

    def __set_library_image(self, server_id: str, library: Dict[str, Any], image_data_b64: str) -> bool:
        library_id = library.get("Id") or library.get("ItemId")
        base_url = config_manager.APP_CONFIG.get('emby_server_url')
        api_key = config_manager.APP_CONFIG.get('emby_api_key')
        upload_url = f"{base_url.rstrip('/')}/Items/{library_id}/Images/Primary?api_key={api_key}"
        
        is_gif = image_data_b64.startswith('R0lG')
        ext = ".gif" if is_gif else ".jpg"
        headers = {"Content-Type": "image/jpeg"}

        if self._covers_output:
            try:
                save_path = Path(self._covers_output) / f"{library['Name']}{ext}"
                save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(image_data_b64))
                logger.info(f"  ➜ 封面已另存到: {save_path}")
            except Exception as e:
                logger.error(f"  ➜ 另存封面失败: {e}")

        try:
            if library_id:
                UPDATING_IMAGES.add(library_id)
                def _clear_flag(): UPDATING_IMAGES.discard(library_id)
                spawn_later(30, _clear_flag)
                
            response = requests.post(upload_url, data=image_data_b64, headers=headers, timeout=30)
            response.raise_for_status()
            logger.debug(f"  ➜ 成功上传封面到媒体库 '{library['Name']}'。")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"  ➜ 上传封面到媒体库 '{library['Name']}' 时发生网络错误: {e}")
            if e.response is not None:
                logger.error(f"  ➜ 响应状态: {e.response.status_code}, 响应内容: {e.response.text[:200]}")
            return False

    def __get_library_title_from_yaml(self, library_name: str) -> Tuple[str, str]:
        zh_title, en_title = library_name, ''
        if not self._title_config_str: return zh_title, en_title
        try:
            title_config = yaml.safe_load(self._title_config_str)
            if isinstance(title_config, dict) and library_name in title_config:
                titles = title_config[library_name]
                if isinstance(titles, list) and len(titles) >= 2: zh_title, en_title = titles[0], titles[1]
        except Exception: pass
        return zh_title, en_title

    def __prepare_multi_images(self, library_dir: Path, source_paths: List[str], count: int):
        library_dir.mkdir(parents=True, exist_ok=True)
        while len(source_paths) < count and len(source_paths) > 0:
            source_paths.append(random.choice(source_paths))
        for i in range(1, count + 1):
            target_path = library_dir / f"{i}.jpg"
            if not target_path.exists():
                source_to_copy = source_paths[i-1] if i-1 < len(source_paths) else random.choice(source_paths)
                shutil.copy(source_to_copy, target_path)

    def __check_custom_image(self, library_name: str) -> List[str]:
        if not self._covers_input: return []
        library_dir = Path(self._covers_input) / library_name
        if not library_dir.is_dir(): return []
        return sorted([str(p) for p in library_dir.iterdir() if p.suffix.lower() in [".jpg", ".jpeg", ".png"]])

    def __download_file(self, url: str, dest_path: Path):
        if dest_path.exists(): return
        try:
            proxies = config_manager.get_proxies_for_requests()
            response = requests.get(url, stream=True, timeout=60, proxies=proxies)
            response.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
        except Exception:
            if dest_path.exists(): dest_path.unlink()

    def __get_fonts(self):
        if self._fonts_checked_and_ready: return
        font_definitions = [
            {"target_attr": "zh_font_path", "filename": "zh_font.ttf", "local_key": "zh_font_path_local", "url_key": "zh_font_url"},
            {"target_attr": "en_font_path", "filename": "en_font.ttf", "local_key": "en_font_path_local", "url_key": "en_font_url"},
            {"target_attr": "zh_font_path_multi_1", "filename": "zh_font_multi_1.ttf", "local_key": "zh_font_path_multi_1_local", "url_key": "zh_font_url_multi_1"},
            {"target_attr": "en_font_path_multi_1", "filename": "en_font_multi_1.otf", "local_key": "en_font_path_multi_1_local", "url_key": "en_font_url_multi_1"}
        ]
        for font_def in font_definitions:
            font_path_to_set = None
            expected_font_file = self.font_path / font_def["filename"]
            if expected_font_file.exists(): font_path_to_set = expected_font_file
            local_path_str = self.config.get(font_def["local_key"])
            if local_path_str:
                local_path = Path(local_path_str)
                if local_path.exists(): font_path_to_set = local_path
            if not font_path_to_set:
                url = self.config.get(font_def["url_key"])
                if url:
                    self.__download_file(url, expected_font_file)
                    if expected_font_file.exists(): font_path_to_set = expected_font_file
            setattr(self, font_def["target_attr"], font_path_to_set)
        if self.zh_font_path and self.en_font_path: self._fonts_checked_and_ready = True