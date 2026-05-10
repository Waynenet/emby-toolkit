# core_processor.py

import os
import json
import time
import re
import copy
import random
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
import threading
from datetime import datetime, timezone
import time as time_module
import psycopg2
# 确保所有依赖都已正确导入
from handler.custom_collection import RecommendationEngine
import config_manager
from database.connection import get_db_connection
from database import media_db, maintenance_db, settings_db
import handler.emby as emby
import handler.tmdb as tmdb
from tasks.helpers import parse_full_asset_details, calculate_ancestor_ids, construct_metadata_payload, translate_tmdb_metadata_recursively
import utils
import constants
import logging
import actor_utils
from database.actor_db import ActorDBManager
from database.log_db import LogDBManager
from database.connection import get_db_connection as get_central_db_connection
from cachetools import TTLCache
from ai_translator import AITranslator
from watchlist_processor import WatchlistProcessor
from handler.douban import DoubanApi

logger = logging.getLogger(__name__)
try:
    from handler.douban import DoubanApi
    DOUBAN_API_AVAILABLE = True
except ImportError:
    DOUBAN_API_AVAILABLE = False
    class DoubanApi:
        def __init__(self, *args, **kwargs): pass
        def get_acting(self, *args, **kwargs): return {}
        def close(self): pass

def extract_tag_names(item_data):
    """
    兼容新旧版 Emby API 提取标签名。
    """
    tags_set = set()
    # 1. TagItems
    tag_items = item_data.get('TagItems')
    if isinstance(tag_items, list):
        for t in tag_items:
            if isinstance(t, dict):
                name = t.get('Name')
                if name: tags_set.add(name)
            elif isinstance(t, str) and t:
                tags_set.add(t)
    # 2. Tags
    tags = item_data.get('Tags')
    if isinstance(tags, list):
        for t in tags:
            if t: tags_set.add(str(t))
    return list(tags_set)

def is_valid_tmdb_id(tmdb_id) -> bool:
    """
    严格校验 TMDb ID 是否有效。
    拦截 None, '', '0', 'None', 'null' 以及非纯数字。
    """
    if not tmdb_id:
        return False
    id_str = str(tmdb_id).strip()
    if id_str in ['0', 'None', 'null', '']:
        return False
    if not id_str.isdigit():
        return False
    if int(id_str) <= 0:
        return False
    return True

def _read_local_json(file_path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(file_path):
        logger.warning(f"本地元数据文件不存在: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取本地JSON文件失败: {file_path}, 错误: {e}")
        return None

def _aggregate_series_cast_from_tmdb_data(series_data: Dict[str, Any], all_episodes_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    【新】从内存中的TMDB数据聚合一个剧集的所有演员。
    """
    logger.debug(f"  ➜ 【演员聚合】开始为 '{series_data.get('name')}' 从内存中的TMDB数据聚合演员...")
    aggregated_cast_map = {}

    # 1. 优先处理主剧集的演员列表
    main_cast = series_data.get("credits", {}).get("cast", [])
    for actor in main_cast:
        actor_id = actor.get("id")
        if actor_id:
            aggregated_cast_map[actor_id] = actor
    logger.debug(f"  ➜ 从主剧集数据中加载了 {len(aggregated_cast_map)} 位主演员。")

    # 2. 聚合所有分集的演员和客串演员
    for episode_data in all_episodes_data:
        credits_data = episode_data.get("credits", {})
        actors_to_process = credits_data.get("cast", []) + credits_data.get("guest_stars", [])
        
        for actor in actors_to_process:
            actor_id = actor.get("id")
            if actor_id and actor_id not in aggregated_cast_map:
                if 'order' not in actor:
                    actor['order'] = 999  # 为客串演员设置高order值
                aggregated_cast_map[actor_id] = actor

    full_aggregated_cast = list(aggregated_cast_map.values())
    full_aggregated_cast.sort(key=lambda x: x.get('order', 999))
    
    logger.info(f"  ➜ 共为 '{series_data.get('name')}' 聚合了 {len(full_aggregated_cast)} 位独立演员。")
    return full_aggregated_cast

class MediaProcessor:
    def __init__(self, config: Dict[str, Any], ai_translator=None, douban_api=None):
        # ★★★ 从 config 字典里解析出所有需要的属性 ★★★
        self.config = config

        # 初始化我们的数据库管理员
        self.actor_db_manager = ActorDBManager()
        self.log_db_manager = LogDBManager()

        self.douban_api = douban_api
        self.emby_url = self.config.get("emby_server_url")
        self.emby_api_key = self.config.get("emby_api_key")
        self.emby_user_id = self.config.get("emby_user_id")
        self.tmdb_api_key = self.config.get("tmdb_api_key", "")
        self.local_data_path = self.config.get("local_data_path", "").strip()

        self.ai_translator = ai_translator
        
        self._stop_event = threading.Event()
        self.processed_items_cache = self._load_processed_log_from_db()
        self.manual_edit_cache = TTLCache(maxsize=10, ttl=600)
        self._global_lib_guid_map = {}
        self._last_lib_map_update = 0
            
        logger.trace("核心处理器初始化完成。")

    # --- [优化版] 实时监控文件逻辑 (增加缓存跳过 & 支持批量延迟刷新) ---
    def process_file_actively(self, file_path: str, skip_refresh: bool = False) -> Optional[str]:
        """
        实时监控（优化版）：
        1. 识别 TMDb ID。
        2. 双向检查数据库和本地缓存，互补缺失数据。
        3. 生成本地覆盖缓存文件 (Override Cache)。
        4. (可选) 通知 Emby 刷新。
        
        Args:
            file_path: 文件路径
            skip_refresh: 是否跳过 Emby 刷新步骤 (用于批量处理时最后统一刷新)
            
        Returns:
            str: 该文件所属的父目录路径 (如果处理成功)，否则返回 None
        """
        folder_path = os.path.dirname(file_path)
        try:
            filename = os.path.basename(file_path)
            folder_name = os.path.basename(folder_path)
            grandparent_path = os.path.dirname(folder_path)
            grandparent_name = os.path.basename(grandparent_path)
            
            # =========================================================
            # 步骤 1: 识别信息
            # =========================================================
            tmdb_id = None
            search_query = None
            search_year = None

            tmdb_regex = r'(?:tmdb|tmdbid)[-_=\s]*(\d+)'
            match = re.search(tmdb_regex, folder_name, re.IGNORECASE)
            if not match:
                match = re.search(tmdb_regex, grandparent_name, re.IGNORECASE)
            if not match:
                match = re.search(tmdb_regex, filename, re.IGNORECASE)

            if match:
                temp_id = match.group(1)
                if is_valid_tmdb_id(temp_id):
                    tmdb_id = temp_id
                    logger.info(f"  ➜ [实时监控] 成功提取 TMDb ID: {tmdb_id}")
            if not tmdb_id:
                # 优化：先尝试从目录名提取搜索信息
                def is_season_folder(name: str) -> bool:
                    return bool(re.match(r'^(Season|S)\s*\d+|Specials', name, re.IGNORECASE))
                def extract_title_year(text: str):
                    year_regex = r'\b(19|20)\d{2}\b'
                    season_episode_regex = r'[sS](\d{1,2})[eE](\d{1,2})'
                    year_matches = list(re.finditer(year_regex, text))
                    se_match = re.search(season_episode_regex, text)
                    if year_matches:
                        last_year_match = year_matches[-1]
                        year = last_year_match.group(0)
                        raw_title = text[:last_year_match.start()]
                    elif se_match:
                        year = None
                        raw_title = text[:se_match.start()]
                    else:
                        year = None
                        raw_title = text
                    query = raw_title.replace('.', ' ').replace('_', ' ').strip(' -[]()')
                    return query, year

                # 首先尝试folder_name，但如果是季目录名，则换用grandparent_name
                if is_season_folder(folder_name):
                    search_query, search_year = extract_title_year(grandparent_name)
                else:
                    search_query, search_year = extract_title_year(folder_name)

                # 如果目录名都没提取到有效标题，再用filename
                if not search_query or search_query == '':
                    search_query, search_year = extract_title_year(os.path.splitext(filename)[0])

                logger.info(f"  ➜ [实时监控] 未找到ID，提取搜索信息: 标题='{search_query}', 年份='{search_year}'")

            # =========================================================
            # 步骤 2: 获取 TMDb 数据 (如果只有标题则搜索)
            # =========================================================
            if not tmdb_id and search_query:
                is_series_guess = bool(re.search(r'S\d+E\d+', filename, re.IGNORECASE))
                search_type = 'tv' if is_series_guess else 'movie'
                results = tmdb.search_media(search_query, self.tmdb_api_key, item_type=search_type, year=search_year)
                if results:
                    tmdb_id = str(results[0].get('id'))
                    logger.info(f"  ➜ [实时监控] 搜索匹配成功: {results[0].get('title') or results[0].get('name')} (ID: {tmdb_id})")
                else:
                    logger.warning(f"  ➜ [实时监控] 搜索失败，无法处理: {search_query}")
                    return None

            if not is_valid_tmdb_id(tmdb_id): 
                return None

            # 确定类型
            is_series = bool(re.search(r'S\d+E\d+', filename, re.IGNORECASE))
            item_type = "Series" if is_series else "Movie"

            # =========================================================
            # 极速查重 (利用文件名比对)
            # =========================================================
            try:
                # 获取该 TMDb ID 下所有已入库的文件名 (含电影和所有分集)
                known_files = media_db.get_known_filenames_by_tmdb_id(tmdb_id)
                current_filename = os.path.basename(file_path)
                
                if current_filename in known_files:
                    logger.info(f"  ➜ [实时监控] 文件已完美入库 ({current_filename})，直接跳过。")
                    return file_path # 即使跳过处理，也返回路径以便后续刷新检查
            except Exception as e:
                logger.warning(f"  ➜ [实时监控] 查重失败，将继续常规流程: {e}")

            # =========================================================
            # ★★★ 核心升级：数据库与缓存双向互补检查 ★★★
            # =========================================================
            should_skip_full_processing = False
            
            # 1. 路径准备
            cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
            base_override_dir = os.path.join(self.local_data_path, "override", cache_folder_name, str(tmdb_id))
            main_json_filename = "all.json" if item_type == "Movie" else "series.json"
            main_json_path = os.path.join(base_override_dir, main_json_filename)
            file_exists = os.path.exists(main_json_path)

            # 2. 数据库查询 (获取完整元数据 + 演员表)
            db_record = None
            db_actors = []
            
            with get_central_db_connection() as conn:
                cursor = conn.cursor()
                # A. 查主表
                cursor.execute(f"SELECT * FROM media_metadata WHERE tmdb_id = %s AND item_type = %s", (str(tmdb_id), item_type))
                row = cursor.fetchone()
                if row:
                    db_record = dict(row)
                    # B. 查演员 (如果主表存在)
                    if db_record.get('actors_json'):
                        try:
                            raw_actors = db_record['actors_json']
                            # ★★★ 修复：兼容 list 和 str 两种类型 ★★★
                            if isinstance(raw_actors, str):
                                actors_link = json.loads(raw_actors)
                            else:
                                actors_link = raw_actors

                            # 提取 tmdb_id 列表
                            actor_tmdb_ids = [a['tmdb_id'] for a in actors_link if 'tmdb_id' in a]
                            if actor_tmdb_ids:
                                # 批量查询演员详情
                                placeholders = ','.join(['%s'] * len(actor_tmdb_ids))
                                sql = f"""
                                    SELECT *, primary_name AS name, tmdb_person_id AS tmdb_id
                                    FROM person_metadata
                                    WHERE tmdb_person_id IN ({placeholders})
                                """
                                cursor.execute(sql, tuple(actor_tmdb_ids))
                                
                                actor_rows = cursor.fetchall()
                                actor_map = {r['tmdb_id']: dict(r) for r in actor_rows}
                                
                                # 组装回有序列表
                                for link in actors_link:
                                    tid = link.get('tmdb_id')
                                    if tid in actor_map:
                                        full_actor = actor_map[tid].copy()
                                        full_actor['character'] = link.get('character') # 使用关系表里的角色名
                                        full_actor['order'] = link.get('order')
                                        db_actors.append(full_actor)
                                        
                                # 按 order 排序
                                db_actors.sort(key=lambda x: x.get('order', 999))
                        except Exception as e:
                            logger.warning(f"  ➜ [实时监控] 从数据库解析演员失败: {e}")

            # 3. 决策逻辑分支
            
            # --- 分支 A: 数据库有，文件没有 -> 生成文件 (纸质存档缺失) ---
            if db_record and not file_exists and db_actors:
                logger.info(f"  ➜ [实时监控] 命中数据库缓存 (ID:{tmdb_id})，但覆盖缓存缺失。正在从数据库生成覆盖缓存文件...")
                try:
                    # 1. 生成主 payload
                    from tasks.helpers import reconstruct_metadata_from_db
                    payload = reconstruct_metadata_from_db(db_record, db_actors)

                    # ★★★ 新增：如果是剧集，需要查询并注入分季/分集数据 ★★★
                    if item_type == "Series":
                        with get_central_db_connection() as conn:
                            cursor = conn.cursor()
                            
                            # A. 查分季
                            cursor.execute("SELECT * FROM media_metadata WHERE parent_series_tmdb_id = %s AND item_type = 'Season'", (str(tmdb_id),))
                            seasons_rows = cursor.fetchall()
                            seasons_data = []
                            for s_row in seasons_rows:
                                s_data = {
                                    "id": int(s_row['tmdb_id']),
                                    "name": s_row['title'],
                                    "overview": s_row['overview'],
                                    "season_number": s_row['season_number'],
                                    "air_date": str(s_row['release_date']) if s_row['release_date'] else None,
                                    "poster_path": s_row['poster_path']
                                }
                                seasons_data.append(s_data)
                            
                            # B. 查分集
                            cursor.execute("SELECT * FROM media_metadata WHERE parent_series_tmdb_id = %s AND item_type = 'Episode'", (str(tmdb_id),))
                            episodes_rows = cursor.fetchall()
                            episodes_data = {} # 字典格式 S1E1: data
                            
                            for e_row in episodes_rows:
                                s_num = e_row['season_number']
                                e_num = e_row['episode_number']
                                key = f"S{s_num}E{e_num}"
                                e_data = {
                                    "id": int(e_row['tmdb_id']),
                                    "name": e_row['title'],
                                    "overview": e_row['overview'],
                                    "season_number": s_num,
                                    "episode_number": e_num,
                                    "air_date": str(e_row['release_date']) if e_row['release_date'] else None,
                                    "vote_average": e_row['rating'],
                                    "still_path": e_row['poster_path']
                                }
                                episodes_data[key] = e_data

                            # C. 注入 payload
                            if seasons_data:
                                payload['seasons_details'] = seasons_data
                            if episodes_data:
                                payload['episodes_details'] = episodes_data
                                
                            logger.info(f"  ➜ [实时监控] 已从数据库恢复 {len(seasons_data)} 个季和 {len(episodes_data)} 个分集的数据。")
                    
                    # 2. 构造上下文对象
                    fake_item_details = {
                        "Id": "pending", 
                        "Name": db_record.get('title'), 
                        "Type": item_type, 
                        "ProviderIds": {"Tmdb": tmdb_id}
                    }
                    
                    # 3. 写入文件
                    self.sync_item_metadata(
                        item_details=fake_item_details,
                        tmdb_id=str(tmdb_id),
                        metadata_override=payload
                    )
                    should_skip_full_processing = True
                    logger.info(f"  ➜ [实时监控] 覆盖文件已恢复。跳过在线刮削。")
                except Exception as e:
                    logger.error(f"  ➜ [实时监控] 从数据库恢复文件失败: {e}，将回退到在线刮削。")

            # --- 分支 B: 文件有，数据库没有 -> 反哺数据库 (数字存档缺失) ---
            elif not db_record and file_exists:
                logger.info(f"  ➜ [实时监控] 命中本地覆盖文件 (ID:{tmdb_id})，但数据库记录缺失。正在反哺数据库...")
                try:
                    override_data = _read_local_json(main_json_path)
                    if override_data:
                        # 提取演员
                        cast_data = (override_data.get('casts', {}) or override_data.get('credits', {})).get('cast', [])
                        
                        # 构造伪造的 Emby 对象用于 upsert
                        fake_item_details = {
                            "Id": "pending", 
                            "Name": override_data.get('title') or override_data.get('name'), 
                            "Type": item_type, 
                            "ProviderIds": {"Tmdb": tmdb_id},
                            "DateCreated": datetime.now(timezone.utc)
                        }
                        
                        # 写入数据库
                        with get_central_db_connection() as conn:
                            cursor = conn.cursor()
                            self._upsert_media_metadata(
                                cursor=cursor,
                                item_type=item_type,
                                final_processed_cast=cast_data, # 直接使用文件里的演员
                                source_data_package=override_data,
                                item_details_from_emby=fake_item_details
                            )
                            conn.commit()
                        
                        should_skip_full_processing = True
                        logger.info(f"  ➜ [实时监控] 数据库记录已补全。跳过在线刮削。")
                except Exception as e:
                    logger.error(f"  ➜ [实时监控] 反哺数据库失败: {e}，将回退到在线刮削。")

            # --- 分支 C: 都有 -> 完美状态 ---
            elif db_record and file_exists:
                # 检查是否需要更新 in_library 状态 (如果是新文件入库)
                if db_record.get('in_library') is False:
                     logger.info(f"  ➜ [实时监控] 数据双全 (ID:{tmdb_id})，但数据库标记为离线。无需处理元数据，仅通知 Emby 刷新。")
                else:
                     logger.info(f"  ➜ [实时监控] 数据双全且在线 (ID:{tmdb_id})。可能是洗版/追更，跳过元数据处理，仅通知 Emby 刷新。")
                
                should_skip_full_processing = True

            # --- 分支 D: 都没有 -> 继续后续的 TMDb 在线流程 ---
            else:
                logger.info(f"  ➜ [实时监控] 本地无缓存 (ID:{tmdb_id})，准备执行 TMDb 在线刮削...")

            # =========================================================
            # 步骤 3: 获取完整详情 & 准备核心处理
            # =========================================================
            details = None
            aggregated_tmdb_data = None
            final_processed_cast = None

            if not should_skip_full_processing:
                time.sleep(random.uniform(0.5, 2.0))
                logger.info(f"  ➜ [实时监控] 正在获取 TMDb 详情并执行核心处理 (ID: {tmdb_id})...")
                
                if item_type == "Movie":
                    details = tmdb.get_movie_details(int(tmdb_id), self.tmdb_api_key)
                else:
                    aggregated_tmdb_data = tmdb.aggregate_full_series_data_from_tmdb(int(tmdb_id), self.tmdb_api_key)
                    details = aggregated_tmdb_data.get('series_details') if aggregated_tmdb_data else None
                    
                if not details:
                    logger.error("  ➜ [实时监控] 无法获取 TMDb 详情，中止处理。")
                    return None
                
                # 提取 TMDb 官方中文别名 & 卖片哥广告拦截
                raw_title = details.get("title") if item_type == "Movie" else details.get("name")
                current_title = utils.clean_invisible_chars(raw_title)

                # 1. 广告拦截：如果是垃圾标题，直接清空，强制进入后续的别名/翻译流程
                if utils.is_spam_title(current_title):
                    logger.warning(f"  ➜ [拦截] 拦截到恶意广告片名: '{current_title}'，准备寻找干净的别名...")
                    current_title = "" 

                # 2. 如果标题为空（被拦截）或不包含中文，则寻找别名
                if not current_title or not utils.contains_chinese(current_title):
                    chinese_alias = None
                    alt_titles_data = details.get("alternative_titles", {})
                    alt_list = alt_titles_data.get("titles") or alt_titles_data.get("results") or []
                    priority_map = {"CN": 1, "SG": 2, "TW": 3, "HK": 4}
                    best_priority = 99
                    
                    for alt in alt_list:
                        alt_title = utils.clean_invisible_chars(alt.get("title", ""))
                        if utils.contains_chinese(alt_title) and not utils.is_spam_title(alt_title):
                            iso_country = alt.get("iso_3166_1", "").upper()
                            current_priority = priority_map.get(iso_country, 5)
                            if current_priority < best_priority:
                                chinese_alias = alt_title
                                best_priority = current_priority
                            if best_priority == 1:
                                break
                    
                    if chinese_alias:
                        logger.info(f"  ➜ 发现干净的 TMDb 官方中文别名: '{chinese_alias}'")
                        if item_type == "Movie": details["title"] = chinese_alias
                        else:
                            details["name"] = chinese_alias
                            if aggregated_tmdb_data and "series_details" in aggregated_tmdb_data:
                                aggregated_tmdb_data["series_details"]["name"] = chinese_alias
                    else:
                        raw_original = details.get("original_title") if item_type == "Movie" else details.get("original_name")
                        original_title = utils.clean_invisible_chars(raw_original)
                        logger.info(f"  ➜ 未找到干净的中文别名，回退到原名: '{original_title}'，等待 AI 翻译。")
                        if item_type == "Movie": details["title"] = original_title
                        else:
                            details["name"] = original_title
                            if aggregated_tmdb_data and "series_details" in aggregated_tmdb_data:
                                aggregated_tmdb_data["series_details"]["name"] = original_title

                # =================================================================
                # ★★★ 提前获取豆瓣数据，充当免费权威翻译字典 ★★★
                # =================================================================
                douban_cast_raw = []
                try:
                    dummy_emby_item = {
                        "Id": "pending",
                        "Name": current_title or original_title,
                        "Type": item_type,
                        "ProductionYear": (details.get('release_date') or details.get('first_air_date') or "")[:4],
                        "ProviderIds": {"Tmdb": tmdb_id}
                    }
                    douban_cast_raw, _ = self._fetch_douban_cast_data(dummy_emby_item, details)
                except Exception as e:
                    logger.warning(f"  ➜ [提前拦截] 获取豆瓣数据失败: {e}")

                # =================================================================
                # ★★★ 核心优化：先把演员表用 IMDb ID 完美处理出来 ★★★
                # =================================================================
                # 准备演员源数据
                authoritative_cast_source = []
                if item_type == "Movie":
                    credits_source = details.get('credits') or details.get('casts') or {}
                    authoritative_cast_source = credits_source.get('cast', [])
                elif item_type == "Series":
                    if aggregated_tmdb_data:
                        all_episodes = list(aggregated_tmdb_data.get("episodes_details", {}).values())
                        authoritative_cast_source = _aggregate_series_cast_from_tmdb_data(details, all_episodes)
                    else:
                        credits_source = details.get('aggregate_credits') or details.get('credits') or {}
                        authoritative_cast_source = credits_source.get('cast', [])

                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    logger.info(f"  ➜ [实时监控] 启动演员表核心处理 (ID精准匹配/映射)...")
                    final_processed_cast = self._process_cast_list(
                        tmdb_cast_people=authoritative_cast_source,
                        emby_cast_people=[],
                        douban_cast_list=douban_cast_raw,
                        item_details_from_emby=dummy_emby_item,
                        cursor=cursor,
                        tmdb_api_key=self.tmdb_api_key,
                        stop_event=None
                    )
                    conn.commit()

                if not final_processed_cast:
                    logger.warning("  ➜ [实时监控] 演员处理未能返回结果，将使用原始数据。")
                    final_processed_cast = authoritative_cast_source

                # =================================================================
                # ★★★ 将完美的中文演员表塞回原数据中，防止 AI 瞎翻译 ★★★
                # =================================================================
                target_tmdb_data = aggregated_tmdb_data if item_type == "Series" else details
                
                cast_payload = []
                for actor in final_processed_cast:
                    cast_payload.append({
                        "id": actor.get("id"), "name": actor.get("name"), "character": actor.get("character"),
                        "order": actor.get("order")
                    })
                    
                if item_type == "Movie":
                    if 'credits' not in target_tmdb_data: target_tmdb_data['credits'] = {}
                    target_tmdb_data['credits']['cast'] = cast_payload
                elif item_type == "Series":
                    if 'series_details' in target_tmdb_data:
                        if 'credits' not in target_tmdb_data['series_details']: target_tmdb_data['series_details']['credits'] = {}
                        target_tmdb_data['series_details']['credits']['cast'] = cast_payload

                # =================================================================
                # ★★★ 大一统 AI 翻译引擎 (此时演员已经是中文，AI 会直接跳过演员翻译) ★★★
                # =================================================================
                if self.ai_translator:
                    from tasks.helpers import translate_tmdb_metadata_recursively
                    translate_tmdb_metadata_recursively(
                        item_type=item_type,
                        tmdb_data=target_tmdb_data,
                        ai_translator=self.ai_translator,
                        item_name=current_title or original_title, 
                        tmdb_api_key=self.tmdb_api_key,
                        config=self.config,
                        douban_cast_data=douban_cast_raw
                    )
            
            # =========================================================
            # 步骤 4 & 5: 生成本地 override 元数据文件 & 写入数据库
            # =========================================================
            if not should_skip_full_processing:
                # 1. 准备伪造的 Emby 对象
                fake_item_details = {
                    "Id": "pending",
                    "Name": details.get('title') or details.get('name'),
                    "Type": item_type,
                    "ProviderIds": {"Tmdb": tmdb_id}
                }

                logger.info(f"  ➜ [实时监控] 正在按照骨架模板格式化元数据...")
                formatted_metadata = construct_metadata_payload(
                    item_type=item_type,
                    tmdb_data=details,
                    aggregated_tmdb_data=aggregated_tmdb_data
                )

                logger.info(f"  ➜ [实时监控] 正在写入本地元数据文件...")
                self.sync_item_metadata(
                    item_details=fake_item_details,
                    tmdb_id=tmdb_id,
                    final_cast_override=final_processed_cast,
                    metadata_override=formatted_metadata 
                )

                logger.info(f"  ➜ [实时监控] 正在将元数据写入数据库 ...")
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    self._upsert_media_metadata(
                        cursor=cursor,
                        item_type=item_type,
                        final_processed_cast=final_processed_cast,
                        source_data_package=formatted_metadata,
                        item_details_from_emby=fake_item_details
                    )
                    conn.commit()

                self.download_images_from_tmdb(
                    tmdb_id=tmdb_id,
                    item_type=item_type,
                    aggregated_tmdb_data=aggregated_tmdb_data
                )

            else:
                logger.info(f"  ➜ [实时监控] 已跳过在线刮削和元数据写入 (数据已通过缓存恢复)。")

            # =========================================================
            # 步骤 6: 通知 Emby 刷新 (可选)
            # =========================================================
            if not skip_refresh:
                logger.info(f"  ➜ [实时监控] 极速通知 Emby 单文件入库: {os.path.basename(file_path)}")
                emby.notify_emby_file_changes([file_path], self.emby_url, self.emby_api_key)
                logger.info(f"  ➜ [实时监控] 预处理完成，Emby 将进行秒级精准入库...")
            else:
                logger.info(f"  ➜ [实时监控] 缓存已生成，等待批量极速通知...")
            
            return file_path

        except Exception as e:
            logger.error(f"  ➜ [实时监控] 处理文件 {file_path} 时发生错误: {e}", exc_info=True)
            return None

    # --- 批量实时监控处理 ---
    def process_file_actively_batch(self, file_paths: List[str]):
        if not file_paths:
            return

        logger.info(f"  ➜ [实时监控] 收到 {len(file_paths)} 个新任务，开始批量预处理...")
        valid_files_to_notify = set()
        
        for i, file_path in enumerate(file_paths):
            try:
                logger.info(f"  ➜ [实时监控] ({i+1}/{len(file_paths)}) 正在处理: {os.path.basename(file_path)}")
                processed_file = self.process_file_actively(file_path, skip_refresh=True)
                if processed_file:
                    valid_files_to_notify.add(processed_file)
            except Exception as e:
                logger.error(f"  ➜ [实时监控] 处理文件 '{file_path}' 失败: {e}")

        if valid_files_to_notify:
            emby.notify_emby_file_changes(list(valid_files_to_notify), self.emby_url, self.emby_api_key)
            logger.info(f"  ➜ [实时监控] 预处理完成，等待视频流数据...")
        else:
            logger.warning(f"  ➜ [实时监控] 未收集到有效的文件路径，任务结束。")

    def _refresh_lib_guid_map(self):
        try:
            libs_data = emby.get_all_libraries_with_paths(self.emby_url, self.emby_api_key)
            new_map = {}
            for lib in libs_data:
                info = lib.get('info', {})
                l_id = str(info.get('Id'))
                l_guid = str(info.get('Guid'))
                if l_id and l_guid:
                    new_map[l_id] = l_guid
            self._global_lib_guid_map = new_map
            self._last_lib_map_update = time.time()
            logger.debug(f"  ➜ 已刷新媒体库 GUID 映射表，共加载 {len(new_map)} 个库。")
        except Exception as e:
            logger.error(f"刷新媒体库 GUID 映射失败: {e}")

    def _get_realtime_ancestor_context(self, item_id: str, source_lib_id: str) -> Tuple[Dict[str, str], Optional[str]]:
        id_to_parent_map = {}
        if not self._global_lib_guid_map or (time.time() - self._last_lib_map_update > 3600):
            self._refresh_lib_guid_map()
        lib_guid = self._global_lib_guid_map.get(str(source_lib_id))

        try:
            curr_id = item_id
            for _ in range(10):
                details = emby.get_emby_item_details(
                    curr_id, self.emby_url, self.emby_api_key, self.emby_user_id,
                    fields="ParentId", silent_404=True
                )
                if not details: break
                
                p_id = details.get('ParentId')
                if p_id == str(source_lib_id) and lib_guid:
                    composite_id = f"{lib_guid}_{p_id}"
                    id_to_parent_map[curr_id] = composite_id
                    id_to_parent_map[composite_id] = "1"
                    break 
                
                if p_id and p_id != '1':
                    id_to_parent_map[str(curr_id)] = p_id
                    curr_id = p_id
                else:
                    break
        except Exception as e:
            logger.error(f"实时构建爬树地图失败: {e}")

        return id_to_parent_map, lib_guid

    def _upsert_media_metadata(
        self,
        cursor: psycopg2.extensions.cursor,
        item_type: str,
        final_processed_cast: List[Dict[str, Any]],
        source_data_package: Optional[Dict[str, Any]],
        item_details_from_emby: Optional[Dict[str, Any]] = None,
        specific_episode_ids: Optional[List[str]] = None
    ):
        if not item_details_from_emby:
            logger.error("  ➜ 写入元数据缓存失败：缺少 Emby 详情数据。")
            return
            
        item_id = str(item_details_from_emby.get('Id'))
        is_pending = (item_id == 'pending')

        source_lib_id = ""
        id_to_parent_map = {}
        lib_guid = None
        
        if not is_pending:
            source_lib_id = str(item_details_from_emby.get('_SourceLibraryId') or "")
            id_to_parent_map, lib_guid = self._get_realtime_ancestor_context(item_id, source_lib_id)

        def get_representative_runtime(emby_items, tmdb_runtime):
            if not emby_items: return tmdb_runtime
            runtimes = [round(item['RunTimeTicks'] / 600000000) for item in emby_items if item.get('RunTimeTicks')]
            return max(runtimes) if runtimes else tmdb_runtime
        
        def _extract_common_json_fields(details: Dict[str, Any], m_type: str):
            genres_raw = details.get('genres', [])
            genres_list = []
            for g in genres_raw:
                if isinstance(g, dict): 
                    name = g.get('name')
                    if name in utils.GENRE_TRANSLATION_PATCH:
                        name = utils.GENRE_TRANSLATION_PATCH[name]
                    genres_list.append({"id": g.get('id', 0), "name": name})
                elif isinstance(g, str): 
                    name = g
                    if name in utils.GENRE_TRANSLATION_PATCH:
                        name = utils.GENRE_TRANSLATION_PATCH[name]
                    genres_list.append({"id": 0, "name": name})
            
            genres_json = json.dumps(genres_list, ensure_ascii=False)

            raw_companies = details.get('production_companies') or []
            companies_list = []
            if isinstance(raw_companies, list):
                for c in raw_companies:
                    if isinstance(c, dict) and c.get('name'):
                        companies_list.append({'id': c.get('id'), 'name': c.get('name')})
            companies_json = json.dumps(companies_list, ensure_ascii=False)

            raw_networks = details.get('networks') or []
            networks_list = []
            if isinstance(raw_networks, list):
                for n in raw_networks:
                    if isinstance(n, dict) and n.get('name'):
                        networks_list.append({'id': n.get('id'), 'name': n.get('name')})
            networks_json = json.dumps(networks_list, ensure_ascii=False)

            keywords_data = details.get('keywords') or details.get('tags') or []
            raw_k_list = []
            if isinstance(keywords_data, dict):
                if m_type == 'Series': raw_k_list = keywords_data.get('results')
                else: raw_k_list = keywords_data.get('keywords')
                if not raw_k_list: raw_k_list = keywords_data.get('results') or keywords_data.get('keywords') or []
            elif isinstance(keywords_data, list):
                raw_k_list = keywords_data
            
            keywords = []
            for k in raw_k_list:
                if isinstance(k, dict) and k.get('name'): keywords.append({'id': k.get('id'), 'name': k.get('name')})
                elif isinstance(k, str) and k: keywords.append({'id': None, 'name': k})
            keywords_json = json.dumps(keywords, ensure_ascii=False)

            countries_raw = details.get('production_countries') or details.get('origin_country') or []
            country_codes = []
            for c in countries_raw:
                if isinstance(c, dict): 
                    code = c.get('iso_3166_1')
                    if code: country_codes.append(code)
                elif isinstance(c, str) and c: country_codes.append(c)
            countries_json = json.dumps(country_codes, ensure_ascii=False)
            return genres_json, companies_json, networks_json, keywords_json, countries_json

        try:
            from psycopg2.extras import execute_batch
            
            if not source_data_package:
                logger.warning("  ➜ 元数据写入跳过：未提供源数据包。")
                return

            records_to_upsert = []
            overview_embedding_json = None
            if item_type in ["Movie", "Series"] and self.ai_translator and self.config.get(constants.CONFIG_OPTION_AI_VECTOR, False):
                overview_text = source_data_package.get('overview') or item_details_from_emby.get('Overview')
                if overview_text:
                    try:
                        embedding = self.ai_translator.generate_embedding(overview_text)
                        if embedding: overview_embedding_json = json.dumps(embedding)
                    except Exception as e_embed:
                        logger.warning(f"  ➜ 生成向量失败: {e_embed}")
            
            if item_type == "Movie":
                movie_record = source_data_package.copy()
                movie_record['item_type'] = 'Movie'
                movie_id = movie_record.get('id')
                movie_record['tmdb_id'] = str(movie_id) if movie_id else ""
                movie_record['runtime_minutes'] = get_representative_runtime([item_details_from_emby], movie_record.get('runtime'))
                movie_record['rating'] = movie_record.get('vote_average')
                
                if is_pending:
                    movie_record['asset_details_json'] = '[]'
                    movie_record['emby_item_ids_json'] = '[]'
                    movie_record['in_library'] = False
                else:
                    all_assets = []
                    all_ids = []  
                    
                    media_sources = item_details_from_emby.get('MediaSources', [])
                    
                    if media_sources and len(media_sources) > 0:
                        for source in media_sources:
                            raw_path = source.get('Path', '')
                            if not raw_path: continue
                            
                            raw_source_id = str(source.get('Id') or item_id)
                            source_id = raw_source_id.replace("mediasource_", "")
                            
                            emby_path = raw_path
                            if emby_path.startswith('http'):
                                emby_path = item_details_from_emby.get('Path', '')
                                
                            mediainfo_path = os.path.splitext(emby_path)[0] + "-mediainfo.json" if emby_path and not emby_path.startswith('http') else None
                            
                            temp_item = item_details_from_emby.copy()
                            temp_item['Id'] = source_id 
                            temp_item['Path'] = emby_path
                            if 'Container' in source: temp_item['Container'] = source['Container']
                            if 'Size' in source: temp_item['Size'] = source['Size']
                            if 'RunTimeTicks' in source: temp_item['RunTimeTicks'] = source['RunTimeTicks']
                            temp_item.pop('Width', None)
                            temp_item.pop('Height', None)
                            if 'MediaStreams' in source:
                                temp_item['MediaStreams'] = source['MediaStreams']
                            temp_item['MediaSources'] = [source]
                            
                            asset_details = parse_full_asset_details(
                                temp_item, 
                                id_to_parent_map=id_to_parent_map, 
                                library_guid=lib_guid,
                                local_mediainfo_path=mediainfo_path 
                            )
                            asset_details['source_library_id'] = source_lib_id

                            all_assets.append(asset_details)
                            all_ids.append(source_id)
                    else:
                        emby_path = item_details_from_emby.get('Path', '')
                        mediainfo_path = os.path.splitext(emby_path)[0] + "-mediainfo.json" if emby_path and not emby_path.startswith('http') else None

                        asset_details = parse_full_asset_details(
                            item_details_from_emby, 
                            id_to_parent_map=id_to_parent_map, 
                            library_guid=lib_guid,
                            local_mediainfo_path=mediainfo_path 
                        )
                        asset_details['source_library_id'] = source_lib_id

                        all_assets.append(asset_details)
                        all_ids.append(item_id)
                    
                    movie_record['asset_details_json'] = json.dumps(all_assets, ensure_ascii=False)
                    movie_record['emby_item_ids_json'] = json.dumps(list(dict.fromkeys(all_ids)))
                    movie_record['in_library'] = True

                movie_record['actors_json'] = json.dumps([{"tmdb_id": int(p.get("id")), "character": p.get("character"), "order": p.get("order")} for p in final_processed_cast if p.get("id")], ensure_ascii=False)
                movie_record['subscription_status'] = 'NONE'
                movie_record['date_added'] = item_details_from_emby.get("DateCreated") or datetime.now(timezone.utc)
                movie_record['overview_embedding'] = overview_embedding_json

                g_json, comp_json, net_json, k_json, c_json = _extract_common_json_fields(source_data_package, 'Movie')
                movie_record['genres_json'] = g_json
                movie_record['production_companies_json'] = comp_json 
                movie_record['networks_json'] = net_json
                movie_record['keywords_json'] = k_json
                movie_record['countries_json'] = c_json

                raw_ratings_map = source_data_package.get('_official_rating_map', {})
                movie_record['official_rating_json'] = json.dumps(raw_ratings_map, ensure_ascii=False)
                
                releases = source_data_package.get('releases', {}).get('countries', [])
                for r in releases:
                    country = r.get('iso_3166_1')
                    cert = r.get('certification')
                    if country and cert: raw_ratings_map[country] = cert
                
                movie_record['official_rating_json'] = json.dumps(raw_ratings_map, ensure_ascii=False)
                
                credits_data = source_data_package.get("credits") or source_data_package.get("casts") or {}
                crew = credits_data.get('crew', [])
                movie_record['directors_json'] = json.dumps([{'id': p.get('id'), 'name': p.get('name')} for p in crew if p.get('job') == 'Director'], ensure_ascii=False)

                records_to_upsert.append(movie_record)

            elif item_type == "Series":
                series_details = source_data_package.get("series_details", source_data_package)
                seasons_details = source_data_package.get("seasons_details", series_details.get("seasons", []))
                
                series_asset_details = []
                if not is_pending:
                    series_path = item_details_from_emby.get('Path')
                    if series_path:
                        series_asset = {
                            "path": series_path,
                            "source_library_id": source_lib_id,
                            "ancestor_ids": calculate_ancestor_ids(item_id, id_to_parent_map, lib_guid)
                        }
                        series_asset_details.append(series_asset)

                series_record = {
                    "item_type": "Series", "tmdb_id": str(series_details.get('id')) if series_details.get('id') else "", "title": series_details.get('name'),
                    "original_title": series_details.get('original_name'), "overview": series_details.get('overview'),
                    "tagline": series_details.get('tagline'),
                    "release_date": series_details.get('first_air_date'), 
                    "last_air_date": series_details.get('last_air_date'),
                    "poster_path": series_details.get('poster_path'),
                    "backdrop_path": series_details.get('backdrop_path'), 
                    "homepage": series_details.get('homepage'),
                    "rating": series_details.get('vote_average'),
                    "total_episodes": series_details.get('number_of_episodes', 0),
                    "watchlist_tmdb_status": series_details.get('status'),
                    "asset_details_json": json.dumps(series_asset_details, ensure_ascii=False),
                    "overview_embedding": overview_embedding_json
                }
                
                if is_pending:
                    series_record['in_library'] = False
                    series_record['emby_item_ids_json'] = '[]'
                else:
                    series_record['in_library'] = True
                    series_record['emby_item_ids_json'] = json.dumps([item_id])

                actors_relation = [{"tmdb_id": int(p.get("id")), "character": p.get("character"), "order": p.get("order")} for p in final_processed_cast if p.get("id")]
                series_record['actors_json'] = json.dumps(actors_relation, ensure_ascii=False)
                
                raw_ratings_map = source_data_package.get('_official_rating_map', {})
                series_record['official_rating_json'] = json.dumps(raw_ratings_map, ensure_ascii=False)

                g_json, comp_json, net_json, k_json, c_json = _extract_common_json_fields(series_details, 'Series')
                series_record['genres_json'] = g_json
                series_record['production_companies_json'] = comp_json
                series_record['networks_json'] = net_json
                series_record['keywords_json'] = k_json
                series_record['countries_json'] = c_json
                
                series_record['directors_json'] = json.dumps([{'id': c.get('id'), 'name': c.get('name')} for c in series_details.get('created_by', [])], ensure_ascii=False)
                
                languages_list = series_details.get('languages', [])
                series_record['original_language'] = series_details.get('original_language') or (languages_list[0] if languages_list else None)
                series_record['subscription_status'] = 'NONE'
                series_record['date_added'] = item_details_from_emby.get("DateCreated") or datetime.now(timezone.utc)
                series_record['ignore_reason'] = None
                records_to_upsert.append(series_record)

                emby_season_versions = []
                if not is_pending:
                    emby_season_versions = emby.get_series_seasons(
                        series_id=item_details_from_emby.get('Id'),
                        base_url=self.emby_url,
                        api_key=self.emby_api_key,
                        user_id=self.emby_user_id,
                        series_name_for_log=series_details.get('name')
                    ) or []
                
                seasons_grouped_by_number = defaultdict(list)
                for s_ver in emby_season_versions:
                    idx = s_ver.get("IndexNumber")
                    if idx is not None:
                        try: seasons_grouped_by_number[int(idx)].append(s_ver)
                        except: pass

                for season in seasons_details:
                    if not isinstance(season, dict): continue
                    
                    s_tmdb_id = season.get('id')
                    if not s_tmdb_id or str(s_tmdb_id) in ['0', 'None', '']:
                        continue

                    s_num = season.get('season_number')
                    if s_num is None: continue 
                    try: s_num_int = int(s_num)
                    except ValueError: continue

                    season_poster = season.get('poster_path') or series_details.get('poster_path')
                    matched_emby_seasons = seasons_grouped_by_number.get(s_num_int, [])

                    season_ids = [s['Id'] for s in matched_emby_seasons] if matched_emby_seasons else []
                    
                    records_to_upsert.append({
                        "tmdb_id": str(s_tmdb_id), "item_type": "Season", 
                        "parent_series_tmdb_id": str(series_details.get('id')), 
                        "title": season.get('name'), "overview": season.get('overview'), 
                        "release_date": season.get('air_date'), "poster_path": season_poster, 
                        "season_number": s_num,
                        "total_episodes": season.get('episode_count', 0),
                        "in_library": bool(matched_emby_seasons) if not is_pending else False,
                        "emby_item_ids_json": json.dumps(season_ids)
                    })
                
                raw_episodes = source_data_package.get("episodes_details", {})
                episodes_details = list(raw_episodes.values()) if isinstance(raw_episodes, dict) else (raw_episodes if isinstance(raw_episodes, list) else [])
                
                emby_episode_versions = []
                if not is_pending:
                    emby_episode_versions = emby.get_all_library_versions(
                        base_url=self.emby_url, api_key=self.emby_api_key, user_id=self.emby_user_id,
                        media_type_filter="Episode", parent_id=item_details_from_emby.get('Id'),
                        fields="Id,Type,ParentIndexNumber,IndexNumber,MediaStreams,Container,Size,Path,ProviderIds,RunTimeTicks,DateCreated,_SourceLibraryId"
                    ) or []
                
                episodes_grouped_by_number = defaultdict(list)
                for ep_version in emby_episode_versions:
                    s_num = ep_version.get("ParentIndexNumber")
                    e_num = ep_version.get("IndexNumber")
                    if s_num is not None and e_num is not None:
                        try: episodes_grouped_by_number[(int(s_num), int(e_num))].append(ep_version)
                        except: pass

                processed_emby_episodes = set()

                for episode in episodes_details:
                    if episode.get('episode_number') is None: continue
                    try:
                        s_num = int(episode.get('season_number'))
                        e_num = int(episode.get('episode_number'))
                    except (ValueError, TypeError): continue

                    e_tmdb_id = episode.get('id')
                    e_tmdb_id_str = str(e_tmdb_id) if e_tmdb_id else ""
                    
                    if e_tmdb_id_str in ['0', 'None', ''] or not e_tmdb_id_str.isdigit():
                        e_tmdb_id_str = f"{series_details.get('id')}-S{s_num}E{e_num}"

                    versions_of_episode = episodes_grouped_by_number.get((s_num, e_num))

                    if versions_of_episode:
                        processed_emby_episodes.add((s_num, e_num))

                    if specific_episode_ids and not is_pending:
                        is_target = False
                        if versions_of_episode:
                            for v in versions_of_episode:
                                if str(v.get('Id')) in specific_episode_ids:
                                    is_target = True
                                    break
                        if not is_target:
                            continue

                    final_runtime = get_representative_runtime(versions_of_episode, episode.get('runtime'))

                    episode_record = {
                        "tmdb_id": e_tmdb_id_str, 
                        "item_type": "Episode", 
                        "parent_series_tmdb_id": str(series_details.get('id')), 
                        "title": episode.get('name'), "overview": episode.get('overview'), 
                        "release_date": episode.get('air_date'), 
                        "season_number": s_num, "episode_number": e_num,
                        "runtime_minutes": final_runtime,
                        "poster_path": episode.get('still_path'),
                        "backdrop_path": episode.get('still_path')
                    }
                    
                    if not is_pending and versions_of_episode:
                        all_assets = []
                        all_ids = []
                        
                        for version in versions_of_episode:
                            raw_path = version.get('Path', '')
                            clean_v_id = str(version.get('Id')).replace("mediasource_", "")
                            
                            emby_path = raw_path
                            if emby_path.startswith('http'):
                                emby_path = item_details_from_emby.get('Path', '')
                                
                            mediainfo_path = os.path.splitext(emby_path)[0] + "-mediainfo.json" if emby_path and not emby_path.startswith('http') else None
                            
                            details = parse_full_asset_details(version, local_mediainfo_path=mediainfo_path)
                            details['source_library_id'] = item_details_from_emby.get('_SourceLibraryId')

                            all_assets.append(details)
                            all_ids.append(clean_v_id)
                            
                        episode_record['asset_details_json'] = json.dumps(all_assets, ensure_ascii=False)
                        episode_record['emby_item_ids_json'] = json.dumps(list(dict.fromkeys(all_ids)))
                        episode_record['in_library'] = True
                    else:
                        episode_record['in_library'] = False
                        episode_record['emby_item_ids_json'] = '[]'
                        episode_record['asset_details_json'] = '[]'
                        
                    records_to_upsert.append(episode_record)

                for (s_num, e_num), versions in episodes_grouped_by_number.items():
                    if (s_num, e_num) in processed_emby_episodes:
                        continue

                    if specific_episode_ids and not is_pending:
                        is_target = False
                        for v in versions:
                            if str(v.get('Id')) in specific_episode_ids:
                                is_target = True
                                break
                        if not is_target:
                            continue

                    fallback_e_tmdb_id = f"{series_details.get('id')}-S{s_num}E{e_num}"
                    logger.debug(f"  ➜ [入库兜底] 发现 Emby 本地分集 S{s_num}E{e_num} 在 TMDb 中不存在，生成内部 ID: {fallback_e_tmdb_id}")

                    emby_ep = versions[0]
                    final_runtime = round(emby_ep['RunTimeTicks'] / 600000000) if emby_ep.get('RunTimeTicks') else None

                    episode_record = {
                        "tmdb_id": fallback_e_tmdb_id, 
                        "item_type": "Episode", 
                        "parent_series_tmdb_id": str(series_details.get('id')), 
                        "title": emby_ep.get('Name') or f"Episode {e_num}", 
                        "overview": emby_ep.get('Overview'), 
                        "release_date": emby_ep.get('PremiereDate'), 
                        "season_number": s_num, "episode_number": e_num,
                        "runtime_minutes": final_runtime,
                        "poster_path": None,
                        "backdrop_path": None,
                    }

                    all_assets = []
                    all_ids = []
                    
                    for version in versions:
                        raw_path = version.get('Path', '')
                        clean_v_id = str(version.get('Id')).replace("mediasource_", "")
                        
                        emby_path = raw_path
                        if emby_path.startswith('http'):
                            emby_path = item_details_from_emby.get('Path', '')
                            
                        mediainfo_path = os.path.splitext(emby_path)[0] + "-mediainfo.json" if emby_path and not emby_path.startswith('http') else None
                        
                        details = parse_full_asset_details(version, local_mediainfo_path=mediainfo_path)
                        details['source_library_id'] = item_details_from_emby.get('_SourceLibraryId')

                        all_assets.append(details)
                        all_ids.append(clean_v_id)
                        
                    episode_record['asset_details_json'] = json.dumps(all_assets, ensure_ascii=False)
                    episode_record['emby_item_ids_json'] = json.dumps(list(dict.fromkeys(all_ids)))
                    episode_record['in_library'] = True

                    records_to_upsert.append(episode_record)

            if not records_to_upsert:
                return
            
            all_possible_columns = [
                "tmdb_id", "item_type", "title", "original_title", "overview", "release_date", "release_year",
                "last_air_date", "backdrop_path", "homepage", "original_language", "poster_path", "rating", 
                "actors_json", "parent_series_tmdb_id", "season_number", "episode_number", "in_library", 
                "subscription_status", "subscription_sources_json", "emby_item_ids_json", 
                "date_added", "official_rating_json", "genres_json", "directors_json", "production_companies_json", 
                "networks_json", "countries_json", "keywords_json", "ignore_reason", "asset_details_json",
                "runtime_minutes", "overview_embedding", "total_episodes", "watchlist_tmdb_status",
                "tagline"
            ]
            data_for_batch = []
            for record in records_to_upsert:
                rec_id = record.get('tmdb_id')
                rec_type = record.get('item_type')
                
                is_valid = False
                if rec_type in ['Movie', 'Series']:
                    is_valid = is_valid_tmdb_id(rec_id)
                elif rec_type in ['Season', 'Episode']:
                    if rec_id and (is_valid_tmdb_id(rec_id) or '-' in str(rec_id)):
                        is_valid = True

                if not is_valid:
                    logger.warning(f"  ➜ [入库拦截] 发现无效的 TMDb ID: '{rec_id}' (类型: {rec_type})，已丢弃该条记录。")
                    continue

                db_row_complete = {col: record.get(col) for col in all_possible_columns}
                
                if db_row_complete['in_library'] is None: db_row_complete['in_library'] = False
                if db_row_complete['subscription_status'] is None: db_row_complete['subscription_status'] = 'NONE'
                if db_row_complete['subscription_sources_json'] is None: db_row_complete['subscription_sources_json'] = '[]'
                if db_row_complete['emby_item_ids_json'] is None: db_row_complete['emby_item_ids_json'] = '[]'

                r_date = db_row_complete.get('release_date')
                if not r_date: db_row_complete['release_date'] = None
                
                l_date = db_row_complete.get('last_air_date')
                if not l_date: db_row_complete['last_air_date'] = None

                final_date_val = db_row_complete.get('release_date')
                if final_date_val and isinstance(final_date_val, str) and len(final_date_val) >= 4:
                    try: db_row_complete['release_year'] = int(final_date_val[:4])
                    except (ValueError, TypeError): pass
                
                data_for_batch.append(db_row_complete)

            if not data_for_batch:
                return

            cols_str = ", ".join(all_possible_columns)
            placeholders_str = ", ".join([f"%({col})s" for col in all_possible_columns])
            cols_to_update = [col for col in all_possible_columns if col not in ['tmdb_id', 'item_type', 'custom_rating']]
            
            cols_to_protect = ['subscription_sources_json']
            timestamp_field = "last_synced_at"
            
            for col in cols_to_protect:
                if col in cols_to_update: cols_to_update.remove(col)

            update_clauses = []
            for col in cols_to_update:
                if col == 'total_episodes':
                    update_clauses.append(
                        "total_episodes = CASE WHEN media_metadata.total_episodes_locked IS TRUE THEN media_metadata.total_episodes ELSE EXCLUDED.total_episodes END"
                    )
                else:
                    update_clauses.append(f"{col} = EXCLUDED.{col}")

            update_clauses.append(f"{timestamp_field} = NOW()")

            sql = f"""
                INSERT INTO media_metadata ({cols_str})
                VALUES ({placeholders_str})
                ON CONFLICT (tmdb_id, item_type) DO UPDATE SET {', '.join(update_clauses)};
            """
            
            execute_batch(cursor, sql, data_for_batch)
            logger.info(f"  ➜ 成功将 {len(data_for_batch)} 条层级元数据记录批量写入数据库。")

        except Exception as e:
            logger.error(f"批量写入层级元数据到数据库时失败: {e}", exc_info=True)
            raise

    def _mark_item_as_processed(self, cursor: psycopg2.extensions.cursor, item_id: str, item_name: str, score: float = 10.0):
        self.log_db_manager.save_to_processed_log(cursor, item_id, item_name, score=score)
        self.processed_items_cache[item_id] = item_name
        logger.debug(f"  ➜ 已将 '{item_name}' 标记为已处理 (数据库 & 内存)。")

    def clear_processed_log(self):
        try:
            with get_central_db_connection() as conn:
                cursor = conn.cursor()
                logger.debug("正在从数据库删除 processed_log 表中的所有记录...")
                cursor.execute("DELETE FROM processed_log")
            
            logger.info("  ➜ 数据库中的已处理记录已清除。")
            self.processed_items_cache.clear()
            logger.info("  ➜ 内存中的已处理记录缓存已清除。")

        except Exception as e:
            logger.error(f"清除数据库或内存已处理记录时失败: {e}", exc_info=True)
            raise
    
    def check_and_add_to_watchlist(self, item_details: Dict[str, Any]):
        item_name_for_log = item_details.get("Name", f"未知项目(ID:{item_details.get('Id')})")
        
        if item_details.get("Type") != "Series":
            return

        logger.info(f"  ➜ 开始为新入库剧集 '{item_name_for_log}' 进行追剧状态判断...")
        try:
            watchlist_proc = WatchlistProcessor(self.config, ai_translator=self.ai_translator)
            watchlist_proc.add_series_to_watchlist(item_details)
        except Exception as e_watchlist:
            logger.error(f"  ➜ 在自动添加 '{item_name_for_log}' 到追剧列表时发生错误: {e_watchlist}", exc_info=True)
    
    def signal_stop(self):
        self._stop_event.set()

    def clear_stop_signal(self):
        self._stop_event.clear()

    def get_stop_event(self) -> threading.Event:
        return self._stop_event

    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def _load_processed_log_from_db(self) -> Dict[str, str]:
        log_dict = {}
        try:
            with get_central_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT item_id, item_name FROM processed_log")
                rows = cursor.fetchall()
                for row in rows:
                    if row['item_id'] and row['item_name']:
                        log_dict[row['item_id']] = row['item_name']
        except Exception as e:
            logger.error(f"从数据库读取已处理记录失败: {e}", exc_info=True)
        return log_dict

    def _find_local_douban_json(self, imdb_id: Optional[str], douban_id: Optional[str], douban_cache_dir: str) -> Optional[str]:
        if not os.path.exists(douban_cache_dir):
            return None
        
        if imdb_id:
            for dirname in os.listdir(douban_cache_dir):
                if dirname.startswith('0_'): continue
                if imdb_id in dirname:
                    dir_path = os.path.join(douban_cache_dir, dirname)
                    for filename in os.listdir(dir_path):
                        if filename.endswith('.json'):
                            return os.path.join(dir_path, filename)
                            
        if douban_id:
            for dirname in os.listdir(douban_cache_dir):
                if dirname.startswith(f"{douban_id}_"):
                    dir_path = os.path.join(douban_cache_dir, dirname)
                    for filename in os.listdir(dir_path):
                        if filename.endswith('.json'):
                            return os.path.join(dir_path, filename)
        return None

    def _fetch_douban_cast_data(self, media_info: Dict[str, Any], tmdb_data: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Optional[float]]:
        provider_ids = media_info.get("ProviderIds", {})
        item_name = media_info.get("Name", "")
        douban_id_from_provider = provider_ids.get("Douban")
        item_type = media_info.get("Type")

        imdb_id = None
        item_year = ""
        if tmdb_data:
            imdb_id = tmdb_data.get("external_ids", {}).get("imdb_id")
            release_date = tmdb_data.get("release_date") or tmdb_data.get("first_air_date") or ""
            if release_date:
                item_year = release_date[:4]
        
        if not imdb_id:
            imdb_id = provider_ids.get("Imdb")
        if not item_year:
            raw_year = media_info.get("ProductionYear")
            item_year = str(raw_year) if raw_year else ""

        douban_cache_dir_name = "douban-movies" if item_type == "Movie" else "douban-tv"
        douban_cache_path = os.path.join(self.local_data_path, "cache", douban_cache_dir_name)
        local_json_path = self._find_local_douban_json(imdb_id, douban_id_from_provider, douban_cache_path)

        if local_json_path:
            logger.debug(f"  ➜ 发现本地豆瓣缓存文件，将直接使用: {local_json_path}")
            douban_data = _read_local_json(local_json_path)
            if douban_data:
                cast = douban_data.get('actors', [])
                rating_str = douban_data.get("rating", {}).get("value")
                rating_float = None
                if rating_str:
                    try: rating_float = float(rating_str)
                    except (ValueError, TypeError): pass
                return cast, rating_float
            else:
                logger.warning(f"本地豆瓣缓存文件 '{local_json_path}' 无效，将回退到在线API。")

        if not self.config.get(constants.CONFIG_OPTION_DOUBAN_ENABLE_ONLINE_API, True):
            logger.info("  ➜ 未找到本地豆瓣缓存，且在线豆瓣API已禁用，跳过豆瓣数据获取。")
            return [], None
        
        logger.info(f"  ➜ 未找到本地豆瓣缓存，准备通过豆瓣在线 API 获取演员信息 (IMDb: {imdb_id or '无'}, 年份: {item_year})...")

        match_info_result = self.douban_api.match_info(
            name=item_name, imdbid=imdb_id, mtype=item_type, year=item_year
        )

        if match_info_result.get("error") or not match_info_result.get("id"):
            logger.warning(f"  ➜ 在线匹配豆瓣ID失败 for '{item_name}': {match_info_result.get('message', '未找到ID')}")
            return [], None

        douban_id = match_info_result["id"]
        douban_type = match_info_result.get("type")

        if not douban_type:
            logger.error(f"  ➜ 从豆瓣匹配结果中未能获取到媒体类型 for ID {douban_id}。处理中止。")
            return [], None

        cast_data = self.douban_api.get_acting(
            name=item_name, 
            douban_id_override=douban_id, 
            mtype=douban_type
        )
        douban_cast_raw = cast_data.get("cast", [])

        return douban_cast_raw, None
    
    def _update_emby_person_names_from_final_cast(self, final_cast: List[Dict[str, Any]], item_name_for_log: str):
        actors_to_update = [
            actor for actor in final_cast 
            if actor.get("emby_person_id") and utils.contains_chinese(actor.get("name"))
        ]

        if not actors_to_update:
            logger.info(f"  ➜ 无需通过 API 更新演员名字 (没有找到需要翻译的 Emby 演员)。")
            return

        logger.info(f"  ➜ 开始为《{item_name_for_log}》的 {len(actors_to_update)} 位演员通过 API 更新名字...")
        
        person_ids = [actor["emby_person_id"] for actor in actors_to_update]
        current_person_details = emby.get_emby_items_by_id(
            base_url=self.emby_url,
            api_key=self.emby_api_key,
            user_id=self.emby_user_id,
            item_ids=person_ids,
            fields="Name"
        )
        
        current_names_map = {p["Id"]: p.get("Name") for p in current_person_details} if current_person_details else {}

        updated_count = 0
        for actor in actors_to_update:
            person_id = actor["emby_person_id"]
            new_name = actor["name"]
            current_name = current_names_map.get(person_id)

            if new_name != current_name:
                emby.update_person_details(
                    person_id=person_id,
                    new_data={"Name": new_name},
                    emby_server_url=self.emby_url,
                    emby_api_key=self.emby_api_key,
                    user_id=self.emby_user_id
                )
                updated_count += 1
                time.sleep(0.2) 

        logger.info(f"  ➜ 成功通过 API 更新了 {updated_count} 位演员的名字。")
    
    def process_full_library(self, update_status_callback: Optional[callable] = None, force_full_update: bool = False):
        self.clear_stop_signal()
        logger.trace(f"进入核心执行层: process_full_library, 接收到的 force_full_update = {force_full_update}")

        if force_full_update:
            logger.info("  ➜ 检测到“深度更新”模式，正在清空已处理日志...")
            try:
                self.clear_processed_log()
            except Exception as e:
                logger.error(f"在 process_full_library 中清空日志失败: {e}", exc_info=True)
                if update_status_callback: update_status_callback(-1, "清空日志失败")
                return

        libs_to_process_ids = self.config.get("libraries_to_process", [])
        if not libs_to_process_ids:
            logger.warning("  ➜ 未在配置中指定要处理的媒体库。")
            return

        logger.info("  ➜ 正在尝试从Emby获取媒体项目...")
        all_emby_libraries = emby.get_emby_libraries(self.emby_url, self.emby_api_key, self.emby_user_id) or []
        library_name_map = {lib.get('Id'): lib.get('Name', '未知库名') for lib in all_emby_libraries}
        
        movies = emby.get_emby_library_items(self.emby_url, self.emby_api_key, "Movie", self.emby_user_id, libs_to_process_ids, library_name_map=library_name_map) or []
        series = emby.get_emby_library_items(self.emby_url, self.emby_api_key, "Series", self.emby_user_id, libs_to_process_ids, library_name_map=library_name_map) or []
        
        if movies:
            source_movie_lib_names = sorted(list({library_name_map.get(item.get('_SourceLibraryId')) for item in movies if item.get('_SourceLibraryId')}))
            logger.info(f"  ➜ 从媒体库【{', '.join(source_movie_lib_names)}】获取到 {len(movies)} 个电影项目。")

        if series:
            source_series_lib_names = sorted(list({library_name_map.get(item.get('_SourceLibraryId')) for item in series if item.get('_SourceLibraryId')}))
            logger.info(f"  ➜ 从媒体库【{', '.join(source_series_lib_names)}】获取到 {len(series)} 个电视剧项目。")

        all_items = movies + series
        total = len(all_items)
        
        if total == 0:
            logger.info("  ➜ 在所有选定的库中未找到任何可处理的项目。")
            if update_status_callback: update_status_callback(100, "未找到可处理的项目。")
            return

        if update_status_callback: update_status_callback(20, "正在检查并清理已删除的媒体项...")
        
        with get_central_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT item_id, item_name FROM processed_log")
            processed_log_entries = cursor.fetchall()
            
            processed_ids_in_db = {entry['item_id'] for entry in processed_log_entries}
            emby_ids_in_library = set()
            for item in all_items:
                if item.get('Id'):
                    emby_ids_in_library.add(str(item['Id']))
                
                if item.get('Type') == 'Movie' and item.get('MediaSources'):
                    for source in item['MediaSources']:
                        source_id = str(source.get('Id', '')).replace('mediasource_', '')
                        if source_id:
                            emby_ids_in_library.add(source_id)
            
            deleted_items_to_clean = processed_ids_in_db - emby_ids_in_library
            
            if deleted_items_to_clean:
                logger.info(f"  ➜ 发现 {len(deleted_items_to_clean)} 个已从 Emby 媒体库删除的项目，正在从 '已处理' 中移除...")
                for deleted_item_id in deleted_items_to_clean:
                    self.log_db_manager.remove_from_processed_log(cursor, deleted_item_id)
                    self.log_db_manager.remove_from_failed_log(cursor, deleted_item_id)
                    if deleted_item_id in self.processed_items_cache:
                        del self.processed_items_cache[deleted_item_id]
                    logger.debug(f"  ➜ 已从 '已处理' 中移除 ItemID: {deleted_item_id}")
                conn.commit()
                logger.info("  ➜ 已删除媒体项的清理工作完成。")
            else:
                logger.info("  ➜ 未发现需要从 '已处理' 中清理的已删除媒体项。")
        
        if update_status_callback: update_status_callback(30, "已删除媒体项清理完成，开始处理现有媒体...")

        for i, item in enumerate(all_items):
            if self.is_stop_requested():
                logger.warning("  ➜ 全库扫描任务已被用户中止。")
                break 
            
            item_id = item.get('Id')
            item_name = item.get('Name', f"ID:{item_id}")

            if not force_full_update and item_id in self.processed_items_cache:
                logger.info(f"  ➜ 正在跳过已处理的项目: {item_name}")
                if update_status_callback:
                    progress_after_cleanup = 30
                    current_progress = progress_after_cleanup + int(((i + 1) / total) * (100 - progress_after_cleanup))
                    update_status_callback(current_progress, f"跳过: {item_name}")
                continue

            if update_status_callback:
                progress_after_cleanup = 30
                current_progress = progress_after_cleanup + int(((i + 1) / total) * (100 - progress_after_cleanup))
                update_status_callback(current_progress, f"处理中 ({i+1}/{total}): {item_name}")
            
            # =================================================================
            # ★★★ 性能二次飞跃：全库扫描时，如果本地有完美缓存，直接跳过 TMDB/豆瓣请求 ★★★
            # =================================================================
            tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
            item_type = item.get("Type")
            
            if not force_full_update and tmdb_id and item_type in ["Movie", "Series"]:
                cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
                override_path = os.path.join(self.local_data_path, "override", cache_folder_name, str(tmdb_id), "all.json" if item_type == "Movie" else "series.json")
                
                if os.path.exists(override_path):
                    logger.info(f"  ➜ [高性能模式] 命中本地缓存，跳过 API 请求: {item_name}")
                    if not item.get('_SourceLibraryId'):
                        lib_info = emby.get_library_root_for_item(
                            item_id=item_id,
                            base_url=self.emby_url,
                            api_key=self.emby_api_key,
                            user_id=self.emby_user_id,
                            item_path=item.get("Path")
                        )
                        if lib_info and lib_info.get('Id'):
                            item['_SourceLibraryId'] = lib_info['Id']
                    
                    self._process_item_core_logic(item, force_full_update=False)
                    time_module.sleep(float(self.config.get("delay_between_items_sec", 0.5)))
                    continue

            self.process_single_item(
                item_id, 
                force_full_update=force_full_update
            )
            
            time_module.sleep(float(self.config.get("delay_between_items_sec", 0.5)))
        
        if not self.is_stop_requested() and update_status_callback:
            update_status_callback(100, "全量处理完成")
    
    def process_single_item(self, emby_item_id: str, force_full_update: bool = False, specific_episode_ids: Optional[List[str]] = None):
        if not force_full_update and not specific_episode_ids and emby_item_id in self.processed_items_cache:
            item_name_from_cache = self.processed_items_cache.get(emby_item_id, f"ID:{emby_item_id}")
            logger.info(f"媒体 '{item_name_from_cache}' 跳过已处理记录。")
            return True

        if self.is_stop_requested():
            return False

        item_details = emby.get_emby_item_details(
            emby_item_id, self.emby_url, self.emby_api_key, self.emby_user_id
        )
        
        if not item_details:
            logger.error(f"process_single_item: 无法获取 Emby 项目 {emby_item_id} 的详情。")
            return False
        
        if not item_details.get('_SourceLibraryId'):
            lib_info = emby.get_library_root_for_item(
                item_id=emby_item_id,
                base_url=self.emby_url,
                api_key=self.emby_api_key,
                user_id=self.emby_user_id,
                item_path=item_details.get("Path")
            )
            if lib_info and lib_info.get('Id'):
                item_details['_SourceLibraryId'] = lib_info['Id']
                logger.debug(f"  ➜ 已为 '{item_details.get('Name')}' 补全媒体库ID: {lib_info['Id']}")
            else:
                logger.warning(f"  ➜ 无法确定 '{item_details.get('Name')}' 所属的媒体库ID。")

        return self._process_item_core_logic(
            item_details_from_emby=item_details,
            force_full_update=force_full_update,
            specific_episode_ids=specific_episode_ids
        )

    def _process_item_core_logic(self, item_details_from_emby: Dict[str, Any], force_full_update: bool = False, specific_episode_ids: Optional[List[str]] = None):
        item_id = item_details_from_emby.get("Id")
        item_name_for_log = item_details_from_emby.get("Name", f"未知项目(ID:{item_id})")
        tmdb_id = item_details_from_emby.get("ProviderIds", {}).get("Tmdb")
        item_type = item_details_from_emby.get("Type")

        logger.trace(f"--- 开始处理 '{item_name_for_log}' (TMDb ID: {tmdb_id}) ---")

        all_emby_people_for_count = item_details_from_emby.get("People", [])
        original_emby_actor_count = len([p for p in all_emby_people_for_count if p.get("Type") == "Actor"])

        if not is_valid_tmdb_id(tmdb_id):
            logger.error(f"  ➜ '{item_name_for_log}' 缺少有效的 TMDb ID (当前值: {tmdb_id})，跳过处理。")
            return False
        if not self.local_data_path:
            logger.error(f"  ➜ '{item_name_for_log}' 处理失败：未在配置中设置“本地数据源路径”。")
            return False
        
        try:
            authoritative_cast_source = []
            tmdb_details_for_extra = None

            logger.info(f"  ➜ 正在构建标准元数据骨架...")
            
            if item_type == "Movie":
                tmdb_details_for_extra = json.loads(json.dumps(utils.MOVIE_SKELETON_TEMPLATE))
            elif item_type == "Series":
                tmdb_details_for_extra = json.loads(json.dumps(utils.SERIES_SKELETON_TEMPLATE))
            
            fresh_data = None
            aggregated_tmdb_data = None
            final_processed_cast = None
            cache_row = None 

            # =================================================================
            # ★★★ 性能二次飞跃：提前检查本地缓存，跳过所有在线请求 ★★★
            # =================================================================
            if not force_full_update:
                cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
                target_override_dir = os.path.join(self.local_data_path, "override", cache_folder_name, tmdb_id)
                main_json_filename = "all.json" if item_type == "Movie" else "series.json"
                override_json_path = os.path.join(target_override_dir, main_json_filename)
                
                if os.path.exists(override_json_path):
                    logger.info(f"  ➜ [快速模式] 发现本地完美覆盖文件，直接加载并跳过 TMDB/豆瓣/AI 请求: {override_json_path}")
                    try:
                        override_data = _read_local_json(override_json_path)
                        if override_data:
                            cast_data = (override_data.get('casts', {}) or override_data.get('credits', {})).get('cast', [])
                            if cast_data:
                                logger.info(f"  ➜ [快速模式] 成功从文件加载 {len(cast_data)} 位演员和元数据...")
                                final_processed_cast = cast_data
                                tmdb_details_for_extra = override_data 
                                
                                if item_type == "Series":
                                    logger.info("  ➜ [快速模式] 检测到剧集，正在聚合本地分集元数据...")
                                    episodes_details_map = {}
                                    seasons_details_list = [] 
                                    
                                    try:
                                        if os.path.exists(target_override_dir):
                                            for fname in os.listdir(target_override_dir):
                                                full_path = os.path.join(target_override_dir, fname)
                                                if fname.startswith("season-") and fname.endswith(".json"):
                                                    try:
                                                        data = _read_local_json(full_path)
                                                        if data:
                                                            if "-episode-" in fname:
                                                                key = f"S{data.get('season_number')}E{data.get('episode_number')}"
                                                                episodes_details_map[key] = data
                                                            else:
                                                                seasons_details_list.append(data)
                                                    except: pass
                                        
                                        if self.tmdb_api_key:
                                            fresh_agg_data = aggregated_tmdb_data
                                            if not fresh_agg_data:
                                                fresh_agg_data = tmdb.aggregate_full_series_data_from_tmdb(int(tmdb_id), self.tmdb_api_key)
                                            
                                            if fresh_agg_data:
                                                fresh_eps = fresh_agg_data.get("episodes_details", {})
                                                added_count = 0
                                                for k, v in fresh_eps.items():
                                                    if k not in episodes_details_map:
                                                        if 'credits' in v:
                                                            del v['credits']
                                                        episodes_details_map[k] = v
                                                        added_count += 1
                                                if added_count > 0:
                                                    logger.info(f"  ➜ [快速模式] 成功补全了 {added_count} 个本地缺失的追更分集数据 (内存补全)。")

                                                fresh_seasons = fresh_agg_data.get("seasons_details", [])
                                                existing_season_nums = {s.get('season_number') for s in seasons_details_list}
                                                for fs in fresh_seasons:
                                                    if fs.get('season_number') not in existing_season_nums:
                                                        seasons_details_list.append(fs)

                                        if episodes_details_map:
                                            tmdb_details_for_extra['episodes_details'] = episodes_details_map
                                        if seasons_details_list:
                                            seasons_details_list.sort(key=lambda x: x.get('season_number', 0))
                                            tmdb_details_for_extra['seasons_details'] = seasons_details_list

                                    except Exception as e_ep:
                                        logger.warning(f"  ➜ [快速模式] 聚合分集/季数据时发生异常: {e_ep}")

                                cache_row = {'source': 'override_file'} 
                                tmdb_to_emby_map = {}
                                for person in item_details_from_emby.get("People", []):
                                    pid = (person.get("ProviderIds") or {}).get("Tmdb")
                                    if pid: tmdb_to_emby_map[str(pid)] = person.get("Id")
                                for actor in final_processed_cast:
                                    aid = str(actor.get('id'))
                                    if aid in tmdb_to_emby_map:
                                        actor['emby_person_id'] = tmdb_to_emby_map[aid]
                    except Exception as e:
                        logger.warning(f"  ➜ 读取覆盖文件失败: {e}，将回退到在线刮削。")
                        final_processed_cast = None

            # =================================================================
            # ★★★ 如果缓存未命中，执行完整的在线刮削、豆瓣匹配和 AI 翻译 ★★★
            # =================================================================
            if final_processed_cast is None:
                logger.info(f"  ➜ 未命中缓存或强制重处理，开始在线获取数据...")
                
                if self.tmdb_api_key:
                    try:
                        if item_type == "Movie":
                            fresh_data = tmdb.get_movie_details(tmdb_id, self.tmdb_api_key)
                            if fresh_data: logger.info(f"  ➜ 成功从 TMDb API 获取到最新电影元数据。")

                        elif item_type == "Series":
                            aggregated_tmdb_data = tmdb.aggregate_full_series_data_from_tmdb(int(tmdb_id), self.tmdb_api_key)
                            if aggregated_tmdb_data:
                                fresh_data = aggregated_tmdb_data.get("series_details")
                                logger.info(f"  ➜ 成功从 TMDb API 获取到最新剧集聚合数据。")

                    except Exception as e:
                        logger.warning(f"  ➜ 从 TMDb API 获取数据失败: {e}")

                if fresh_data:
                    raw_title = fresh_data.get("title") if item_type == "Movie" else fresh_data.get("name")
                    current_title = utils.clean_invisible_chars(raw_title)
                    
                    if utils.is_spam_title(current_title):
                        logger.warning(f"  ➜ [拦截] 检测到恶意广告片名: '{current_title}'，准备寻找替代片名...")
                        current_title = ""
                    
                    if not current_title or not utils.contains_chinese(current_title):
                        chinese_alias = None
                        alt_titles_data = fresh_data.get("alternative_titles", {})
                        alt_list = alt_titles_data.get("titles") or alt_titles_data.get("results") or []
                        priority_map = {"CN": 1, "SG": 2, "TW": 3, "HK": 4}
                        best_priority = 99
                        
                        for alt in alt_list:
                            alt_title = utils.clean_invisible_chars(alt.get("title", ""))
                            if utils.contains_chinese(alt_title) and not utils.is_spam_title(alt_title):
                                iso_country = alt.get("iso_3166_1", "").upper()
                                current_priority = priority_map.get(iso_country, 5)
                                if current_priority < best_priority:
                                    chinese_alias = alt_title
                                    best_priority = current_priority
                                if best_priority == 1:
                                    break
                        
                        if chinese_alias:
                            logger.info(f"  ➜ 发现干净的 TMDb 官方中文别名: '{chinese_alias}'")
                            if item_type == "Movie":
                                fresh_data["title"] = chinese_alias
                            else:
                                fresh_data["name"] = chinese_alias
                                if aggregated_tmdb_data and "series_details" in aggregated_tmdb_data:
                                    aggregated_tmdb_data["series_details"]["name"] = chinese_alias
                        else:
                            original_title = fresh_data.get("original_title") if item_type == "Movie" else fresh_data.get("original_name")
                            logger.info(f"  ➜ 未找到干净的中文别名，回退到原名: '{original_title}'，等待 AI 翻译。")
                            if item_type == "Movie": fresh_data["title"] = original_title
                            else:
                                fresh_data["name"] = original_title
                                if aggregated_tmdb_data and "series_details" in aggregated_tmdb_data:
                                    aggregated_tmdb_data["series_details"]["name"] = original_title

                    # 获取豆瓣数据
                    douban_cast_raw = []
                    dummy_emby_item = item_details_from_emby.copy()
                    dummy_emby_item["Name"] = current_title or original_title or item_details_from_emby.get("Name")
                    try:
                        douban_cast_raw, _ = self._fetch_douban_cast_data(dummy_emby_item, fresh_data)
                    except Exception as e:
                        logger.warning(f"  ➜ [提前拦截] 获取豆瓣数据失败: {e}")

                    # =================================================================
                    # ★★★ 核心优化：先把演员表用 IMDb ID 完美处理出来 ★★★
                    # =================================================================
                    target_tmdb_data = aggregated_tmdb_data if item_type == "Series" else fresh_data
                    
                    # 准备演员源数据
                    if item_type == "Movie":
                        credits_source = fresh_data.get('credits') or fresh_data.get('casts') or {}
                        authoritative_cast_source = credits_source.get('cast', [])
                    elif item_type == "Series":
                        if aggregated_tmdb_data:
                            all_episodes = list(aggregated_tmdb_data.get("episodes_details", {}).values())
                            authoritative_cast_source = _aggregate_series_cast_from_tmdb_data(fresh_data, all_episodes)
                        else:
                            credits_source = fresh_data.get('aggregate_credits') or fresh_data.get('credits') or {}
                            authoritative_cast_source = credits_source.get('cast', [])

                    # 移除无头像演员 (提前过滤，减少处理量)
                    if self.config.get(constants.CONFIG_OPTION_REMOVE_ACTORS_WITHOUT_AVATARS, True) and authoritative_cast_source:
                        original_count = len(authoritative_cast_source)
                        actors_with_avatars = [actor for actor in authoritative_cast_source if actor.get("profile_path")]
                        if len(actors_with_avatars) < original_count:
                            removed_count = original_count - len(actors_with_avatars)
                            logger.info(f"  ➜ 在核心处理前，已从源数据中移除 {removed_count} 位无头像的演员。")
                            authoritative_cast_source = actors_with_avatars

                    with get_central_db_connection() as conn:
                        cursor = conn.cursor()
                        all_emby_people = item_details_from_emby.get("People", [])
                        current_emby_cast_raw = [p for p in all_emby_people if p.get("Type") == "Actor"]
                        emby_config = {"url": self.emby_url, "api_key": self.emby_api_key, "user_id": self.emby_user_id}
                        enriched_emby_cast = self.actor_db_manager.enrich_actors_with_provider_ids(cursor, current_emby_cast_raw, emby_config)

                        logger.info(f"  ➜ 启动演员表核心处理 (ID精准匹配/映射)...")
                        final_processed_cast = self._process_cast_list(
                            tmdb_cast_people=authoritative_cast_source,
                            emby_cast_people=enriched_emby_cast,
                            douban_cast_list=douban_cast_raw,
                            item_details_from_emby=item_details_from_emby,
                            cursor=cursor,
                            tmdb_api_key=self.tmdb_api_key,
                            stop_event=self.get_stop_event()
                        )

                    if not final_processed_cast:
                        raise ValueError("未能生成有效的最终演员列表。")

                    # =================================================================
                    # ★★★ 将完美的中文演员表塞回原数据中，防止 AI 瞎翻译 ★★★
                    # =================================================================
                    cast_payload = []
                    for actor in final_processed_cast:
                        cast_payload.append({
                            "id": actor.get("id"), "name": actor.get("name"), "character": actor.get("character"),
                            "order": actor.get("order")
                        })
                        
                    if item_type == "Movie":
                        if 'credits' not in target_tmdb_data: target_tmdb_data['credits'] = {}
                        target_tmdb_data['credits']['cast'] = cast_payload
                    elif item_type == "Series":
                        if 'series_details' in target_tmdb_data:
                            if 'credits' not in target_tmdb_data['series_details']: target_tmdb_data['series_details']['credits'] = {}
                            target_tmdb_data['series_details']['credits']['cast'] = cast_payload

                    # =================================================================
                    # ★★★ 大一统 AI 翻译引擎 (此时演员已经是中文，AI 会直接跳过演员翻译) ★★★
                    # =================================================================
                    if self.ai_translator:
                        from tasks.helpers import translate_tmdb_metadata_recursively
                        translate_tmdb_metadata_recursively(
                            item_type=item_type,
                            tmdb_data=target_tmdb_data,
                            ai_translator=self.ai_translator,
                            item_name=item_name_for_log,
                            tmdb_api_key=self.tmdb_api_key,
                            config=self.config,
                            douban_cast_data=douban_cast_raw
                        )

                    # 构建最终的 override 骨架
                    tmdb_details_for_extra = construct_metadata_payload(
                        item_type=item_type,
                        tmdb_data=fresh_data,
                        aggregated_tmdb_data=aggregated_tmdb_data,
                        emby_data_fallback=item_details_from_emby
                    )
                    
                    if not item_details_from_emby.get("Genres") and fresh_data.get("genres"):
                        item_details_from_emby["Genres"] = fresh_data.get("genres")
                        logger.debug(f"  ➜ 检测到 Emby 缺少类型数据，已使用 TMDb 数据补全 Genres: {len(fresh_data.get('genres'))} 个")

            # ---------------------------------------------------------
            # 老六笑话兜底 (基于 tmdb_details_for_extra)
            # ---------------------------------------------------------
            if self.config.get("ai_joke_fallback", False) and self.ai_translator and tmdb_details_for_extra:
                jokes_to_generate = {}

                if not tmdb_details_for_extra.get("overview"):
                    jokes_to_generate["main"] = tmdb_details_for_extra.get("title") or tmdb_details_for_extra.get("name")

                ep_list = []
                if item_type == "Series" and tmdb_details_for_extra.get("episodes_details"):
                    episodes = tmdb_details_for_extra["episodes_details"]
                    ep_list = episodes.values() if isinstance(episodes, dict) else (episodes if isinstance(episodes, list) else [])

                    # 尝试从数据库读取旧数据，继承已有笑话，省 Token！
                    old_episodes = {}
                    try:
                        with get_central_db_connection() as conn_joke:
                            cursor_joke = conn_joke.cursor()
                            cursor_joke.execute(
                                "SELECT season_number, episode_number, overview FROM media_metadata WHERE parent_series_tmdb_id = %s AND item_type = 'Episode'",
                                (str(tmdb_id),)
                            )
                            for row in cursor_joke.fetchall():
                                key = f"S{row['season_number']}E{row['episode_number']}"
                                old_episodes[key] = {"overview": row.get('overview', '')}
                    except Exception as e_joke:
                        logger.warning(f"  ➜ 读取旧简介用于AI笑话判断时失败: {e_joke}")

                    for ep in ep_list:
                        if not ep.get("overview"):
                            ep_key = f"S{ep.get('season_number')}E{ep.get('episode_number')}"
                            old_overview = old_episodes.get(ep_key, {}).get("overview") or ""
                            if "【老六占位简介】" in old_overview:
                                ep["overview"] = old_overview
                            else:
                                jokes_to_generate[ep_key] = f"{tmdb_details_for_extra.get('name')} {ep_key}"

                if jokes_to_generate:
                    logger.info(f"  ➜ [老六模式] 发现 {len(jokes_to_generate)} 处缺失简介，正在呼叫 AI 编段子...")
                    generated_jokes = self.ai_translator.batch_generate_jokes(jokes_to_generate)

                    if "main" in generated_jokes:
                        tmdb_details_for_extra["overview"] = generated_jokes["main"]
                        # 如果是新刮削的，同步更新 aggregated_tmdb_data
                        if 'aggregated_tmdb_data' in locals() and aggregated_tmdb_data and "series_details" in aggregated_tmdb_data:
                            aggregated_tmdb_data["series_details"]["overview"] = generated_jokes["main"]

                    for ep in ep_list:
                        ep_key = f"S{ep.get('season_number')}E{ep.get('episode_number')}"
                        if ep_key in generated_jokes:
                            ep["overview"] = generated_jokes[ep_key]

            # ---------------------------------------------------------
            # 写入数据库、Emby 刷新等
            # ---------------------------------------------------------
            with get_central_db_connection() as conn:
                cursor = conn.cursor()

                is_feedback_mode = (
                    cache_row 
                    and isinstance(cache_row, dict) 
                    and cache_row.get('source') == 'override_file'
                    and not specific_episode_ids
                )

                if is_feedback_mode:
                    logger.info(f"  ➜ [快速模式] 检测到完美本地数据，跳过图片下载、文件写入及 Emby 刷新。")
                else:
                    self._update_emby_person_names_from_final_cast(final_processed_cast, item_name_for_log)

                    logger.info(f"  ➜ 处理完成，正在通知 Emby 刷新...")
                    emby.refresh_emby_item_metadata(
                        item_emby_id=item_id,
                        emby_server_url=self.emby_url,
                        emby_api_key=self.emby_api_key,
                        user_id_for_ops=self.emby_user_id,
                        replace_all_metadata_param=True, 
                        item_name_for_log=item_name_for_log
                    )

                self._upsert_media_metadata(
                    cursor=cursor,
                    item_type=item_type,
                    item_details_from_emby=item_details_from_emby,
                    final_processed_cast=final_processed_cast,
                    source_data_package=tmdb_details_for_extra,
                    specific_episode_ids=specific_episode_ids
                )
                
                logger.info(f"  ➜ 正在评估《{item_name_for_log}》的处理质量...")
                
                stream_check_passed = True
                stream_fail_reason = ""
                
                def _check_mediainfo_file(file_path, label_prefix=""):
                    if not file_path:
                        return False, f"{label_prefix} 缺失文件路径"
                    mediainfo_path = os.path.splitext(file_path)[0] + "-mediainfo.json"
                    if os.path.exists(mediainfo_path):
                        return True, ""
                    else:
                        return False, f"{label_prefix}缺失媒体信息: 文件 (-mediainfo.json)"

                if item_type in ['Movie', 'Episode']:
                    emby_path = item_details_from_emby.get("Path")
                    passed, reason = _check_mediainfo_file(emby_path, "")
                    if not passed:
                        stream_check_passed = False
                        stream_fail_reason = reason

                elif item_type == 'Series':
                    try:
                        cursor.execute("""
                            SELECT season_number, episode_number, asset_details_json 
                            FROM media_metadata 
                            WHERE parent_series_tmdb_id = %s AND item_type = 'Episode' AND in_library = TRUE
                            ORDER BY season_number ASC, episode_number ASC
                        """, (tmdb_id,))
                        
                        db_episodes = cursor.fetchall()
                        for db_ep in db_episodes:
                            s_idx = db_ep['season_number']
                            e_idx = db_ep['episode_number']
                            raw_assets = db_ep['asset_details_json']
                            
                            assets = json.loads(raw_assets) if isinstance(raw_assets, str) else (raw_assets if isinstance(raw_assets, list) else [])
                            
                            ep_path = None
                            if assets and len(assets) > 0:
                                ep_path = assets[0].get('path')
                            
                            passed, reason = _check_mediainfo_file(ep_path, f"[S{s_idx}E{e_idx}]")
                            
                            if not passed:
                                stream_check_passed = False
                                stream_fail_reason = reason
                                logger.warning(f"  ➜ [质检] 剧集《{item_name_for_log}》检测到坏分集: {reason}")
                                break 

                    except Exception as e_db_check:
                        logger.warning(f"  ➜ [质检] 数据库验证分集流信息时出错: {e_db_check}")

                raw_genres = item_details_from_emby.get("Genres", [])

                if raw_genres and isinstance(raw_genres[0], dict):
                    genres = [g.get('name') for g in raw_genres if g.get('name')]
                else:
                    genres = raw_genres

                is_animation = "Animation" in genres or "动画" in genres or "Documentary" in genres or "纪录" in genres or "记录" in genres
                
                processing_score = actor_utils.evaluate_cast_processing_quality(
                    final_cast=final_processed_cast, 
                    original_cast_count=original_emby_actor_count,
                    expected_final_count=len(final_processed_cast), 
                    is_animation=is_animation
                )

                if cache_row:
                    logger.info(f"  ➜ [快速模式] 基于缓存数据的实时复核评分: {processing_score:.2f}")
                
                raw_min_score = self.config.get("min_score_for_review")
                if raw_min_score is None:
                    raw_min_score = constants.DEFAULT_MIN_SCORE_FOR_REVIEW
                min_score_for_review = float(raw_min_score)
                
                target_log_id = item_id
                target_log_name = item_name_for_log
                target_log_type = item_type

                if item_type == 'Episode':
                    series_id = item_details_from_emby.get('SeriesId')
                    series_name = item_details_from_emby.get('SeriesName')
                    if series_id:
                        target_log_id = str(series_id)
                        target_log_name = series_name or f"剧集(ID:{series_id})"
                        target_log_type = 'Series'
                        if not stream_check_passed:
                            s_idx = item_details_from_emby.get('ParentIndexNumber')
                            e_idx = item_details_from_emby.get('IndexNumber')
                            stream_fail_reason = f"[S{s_idx}E{e_idx}] {stream_fail_reason}"

                if not stream_check_passed:
                    logger.warning(f"  ➜ [质检]《{item_name_for_log}》因缺失视频流数据，需重新处理。")
                    self.log_db_manager.save_to_failed_log(cursor, target_log_id, target_log_name, stream_fail_reason, target_log_type, score=0.0)
                    self._mark_item_as_processed(cursor, target_log_id, target_log_name, score=0.0)
                    
                elif processing_score < min_score_for_review:
                    reason = f"处理评分 ({processing_score:.2f}) 低于阈值 ({min_score_for_review})。"
                    
                    if cache_row:
                        logger.warning(f"  ➜ [质检]《{item_name_for_log}》本地缓存数据质量不佳 (评分: {processing_score:.2f})，已重新标记为【待复核】。")
                    else:
                        logger.warning(f"  ➜ [质检]《{item_name_for_log}》处理质量不佳，已标记为【待复核】。原因: {reason}")
                        
                    self.log_db_manager.save_to_failed_log(cursor, target_log_id, target_log_name, reason, target_log_type, score=processing_score)
                    self._mark_item_as_processed(cursor, target_log_id, target_log_name, score=processing_score)
                    
                else:
                    logger.info(f"  ➜ 《{item_name_for_log}》质检通过 (评分: {processing_score:.2f})，标记为已处理。")
                    self._mark_item_as_processed(cursor, target_log_id, target_log_name, score=processing_score)
                    self.log_db_manager.remove_from_failed_log(cursor, target_log_id)
                
                conn.commit()

            is_pure_episode_update = (item_type == 'Series' and specific_episode_ids)

            if item_type in ['Movie', 'Series'] and not is_pure_episode_update and \
               self.config.get(constants.CONFIG_OPTION_PROXY_ENABLED) and \
               self.config.get(constants.CONFIG_OPTION_AI_VECTOR):
                try:
                    threading.Thread(target=RecommendationEngine.refresh_cache).start()
                    logger.debug(f"  ➜ [智能推荐] 已触发向量缓存刷新，'{item_name_for_log}' 将即刻加入推荐池。")
                except Exception as e:
                    logger.warning(f"  ➜ [智能推荐] 触发缓存刷新失败: {e}")
            elif is_pure_episode_update:
                logger.debug(f"  ➜ [智能推荐] 检测到为剧集追更模式，跳过向量缓存刷新。")

            logger.trace(f"--- 处理完成 '{item_name_for_log}' ---")

        except (ValueError, InterruptedError) as e:
            logger.warning(f"处理 '{item_name_for_log}' 的过程中断: {e}")
            return False
        except Exception as outer_e:
            logger.error(f"核心处理流程中发生未知严重错误 for '{item_name_for_log}': {outer_e}", exc_info=True)
            try:
                with get_central_db_connection() as conn_fail:
                    self.log_db_manager.save_to_failed_log(conn_fail.cursor(), item_id, item_name_for_log, f"核心处理异常: {str(outer_e)}", item_type)
            except Exception as log_e:
                logger.error(f"写入待复核日志时再次发生错误: {log_e}")
            return False

        logger.trace(f"  ➜ 处理完成 '{item_name_for_log}'")
        return True

    def _process_cast_list(self, tmdb_cast_people: List[Dict[str, Any]],
                                    emby_cast_people: List[Dict[str, Any]],
                                    douban_cast_list: List[Dict[str, Any]],
                                    item_details_from_emby: Dict[str, Any],
                                    cursor: psycopg2.extensions.cursor,
                                    tmdb_api_key: Optional[str],
                                    stop_event: Optional[threading.Event]) -> List[Dict[str, Any]]:
        # ======================================================================
        # 预处理: 清洗同名演员
        # ======================================================================
        logger.debug("  ➜ 预处理：清洗源数据中的同名演员，只保留order最小的一个。")
        cleaned_tmdb_cast = []
        seen_names = {} 
        
        tmdb_cast_people.sort(key=lambda x: x.get('order', 999))

        for actor in tmdb_cast_people:
            name = actor.get("name")
            if not name or not isinstance(name, str):
                continue
            
            cleaned_name = name.strip()
            
            if cleaned_name not in seen_names:
                cleaned_tmdb_cast.append(actor)
                seen_names[cleaned_name] = actor.get('order', 999)
            else:
                role = actor.get("character", "未知角色")
                logger.info(f"  ➜ 为避免张冠李戴，删除同名异人演员: '{cleaned_name}' (角色: {role}, order: {actor.get('order', 999)})")

        tmdb_cast_people = cleaned_tmdb_cast

        original_tmdb_ids = {str(actor.get("id")) for actor in tmdb_cast_people if actor.get("id")}
        
        # ======================================================================
        # 步骤 1: 数据适配与关联
        # ======================================================================
        logger.debug("  ➜ 开始演员数据适配 (反查缓存模式)...")
        
        tmdb_actor_map_by_id = {str(actor.get("id")): actor for actor in tmdb_cast_people}
        tmdb_actor_map_by_en_name = {str(actor.get("name") or "").lower().strip(): actor for actor in tmdb_cast_people}

        final_cast_list = []
        used_tmdb_ids = set()

        for emby_actor in emby_cast_people:
            emby_person_id = emby_actor.get("Id")
            emby_tmdb_id = emby_actor.get("ProviderIds", {}).get("Tmdb")
            emby_name_lower = str(emby_actor.get("Name") or "").lower().strip()

            tmdb_match = None

            if emby_tmdb_id and str(emby_tmdb_id) in tmdb_actor_map_by_id:
                tmdb_match = tmdb_actor_map_by_id[str(emby_tmdb_id)]
            else:
                if emby_name_lower in tmdb_actor_map_by_en_name:
                    tmdb_match = tmdb_actor_map_by_en_name[emby_name_lower]
                else:
                    cache_entry = self.actor_db_manager.get_translation_from_db(cursor, emby_actor.get("Name"), by_translated_text=True)
                    if cache_entry and cache_entry.get('original_text'):
                        original_en_name = str(cache_entry['original_text']).lower().strip()
                        if original_en_name in tmdb_actor_map_by_en_name:
                            tmdb_match = tmdb_actor_map_by_en_name[original_en_name]

            if tmdb_match:
                tmdb_id_str = str(tmdb_match.get("id"))
                merged_actor = tmdb_match.copy()
                merged_actor["emby_person_id"] = emby_person_id
                if utils.contains_chinese(emby_actor.get("Name")):
                    merged_actor["name"] = emby_actor.get("Name")
                else:
                    merged_actor["name"] = tmdb_match.get("name")
                merged_actor["character"] = emby_actor.get("Role")
                final_cast_list.append(merged_actor)
                used_tmdb_ids.add(tmdb_id_str)

        for tmdb_id, tmdb_actor_data in tmdb_actor_map_by_id.items():
            if tmdb_id not in used_tmdb_ids:
                new_actor = tmdb_actor_data.copy()
                new_actor["emby_person_id"] = None
                final_cast_list.append(new_actor)

        logger.debug(f"  ➜ 数据适配完成，生成了 {len(final_cast_list)} 条基准演员数据。")
        
        # ======================================================================
        # 步骤 2: 挂载豆瓣 ID
        # ======================================================================
        douban_candidates = actor_utils.format_douban_cast(douban_cast_list)
        unmatched_local_actors = list(final_cast_list)
        merged_actors = []
        unmatched_douban_actors = []
        logger.info(f"  ➜ 匹配阶段 1: 提取豆瓣ID")
        for d_actor in douban_candidates:
            douban_name_zh = d_actor.get("Name", "").lower().strip()
            douban_name_en = d_actor.get("OriginalName", "").lower().strip()
            match_found_for_this_douban_actor = False
            for i, l_actor in enumerate(unmatched_local_actors):
                local_name = str(l_actor.get("name") or "").lower().strip()
                local_original_name = str(l_actor.get("original_name") or "").lower().strip()
                
                is_match = False
                if douban_name_zh and (douban_name_zh == local_name or douban_name_zh == local_original_name):
                    is_match = True
                elif douban_name_en and (douban_name_en == local_name or douban_name_en == local_original_name):
                    is_match = True
                
                if is_match:
                    douban_id_to_add = d_actor.get("DoubanCelebrityId")
                    if douban_id_to_add:
                        l_actor["douban_id"] = douban_id_to_add
                    
                    # ★★★ 修复：如果豆瓣有明确的中文角色名（非"演员"），强行覆盖AI翻译结果 ★★★
                    d_role = d_actor.get("Role", "").strip()
                    if d_role and utils.contains_chinese(d_role) and d_role != "演员":
                        l_actor["character"] = d_role
                    
                    merged_actors.append(unmatched_local_actors.pop(i))
                    match_found_for_this_douban_actor = True
                    break
            if not match_found_for_this_douban_actor:
                unmatched_douban_actors.append(d_actor)

        current_cast_list = merged_actors + unmatched_local_actors
        final_cast_map = {str(actor['id']): actor for actor in current_cast_list if actor.get('id') and str(actor.get('id')) != 'None'}

        # ======================================================================
        # 步骤 3: 补充缺失的豆瓣演员 (查库补全)
        # ======================================================================
        if not unmatched_douban_actors:
            logger.info("  ➜ 豆瓣API未返回演员或所有演员已匹配，跳过补充演员流程。")
        else:
            logger.info(f"  ➜ 发现 {len(unmatched_douban_actors)} 位潜在的豆瓣补充演员，开始执行匹配与筛选...")
            
            limit = self.config.get(constants.CONFIG_OPTION_MAX_ACTORS_TO_PROCESS, 30)
            try:
                limit = int(limit)
                if limit <= 0: limit = 30
            except (ValueError, TypeError):
                limit = 30

            current_actor_count = len(final_cast_map)
            if current_actor_count >= limit:
                logger.info(f"  ➜ 当前演员数 ({current_actor_count}) 已达上限 ({limit})，将跳过所有豆瓣补充演员的流程。")
                still_unmatched_final = unmatched_douban_actors
            else:
                logger.info(f"  ➜ 当前演员数 ({current_actor_count}) 低于上限 ({limit})，进入补充模式。")
                
                logger.info(f"  ➜ 匹配阶段 2: 用豆瓣ID查'演员映射表' ({len(unmatched_douban_actors)} 位演员)")
                still_unmatched = []
                for d_actor in unmatched_douban_actors:
                    if self.is_stop_requested(): raise InterruptedError("任务中止")
                    d_douban_id = d_actor.get("DoubanCelebrityId")
                    match_found = False
                    if d_douban_id:
                        entry = self.actor_db_manager.find_person_by_any_id(cursor, douban_id=d_douban_id)
                        if entry and entry.get("tmdb_person_id"):
                            tmdb_id_from_map = str(entry.get("tmdb_person_id"))
                            if tmdb_id_from_map not in final_cast_map:
                                logger.info(f"    ├─ 匹配成功 (通过 豆瓣ID映射): 豆瓣演员 '{d_actor.get('Name')}' -> 加入最终演员表")
                                cached_metadata_map = self.actor_db_manager.get_full_actor_details_by_tmdb_ids(cursor, [int(tmdb_id_from_map)])
                                cached_metadata = cached_metadata_map.get(int(tmdb_id_from_map), {})
                                new_actor_entry = {
                                    "id": tmdb_id_from_map, "name": d_actor.get("Name"),
                                    "original_name": cached_metadata.get("original_name") or d_actor.get("OriginalName"),
                                    "character": d_actor.get("Role"), "order": 999,
                                    "imdb_id": entry.get("imdb_id"), "douban_id": d_douban_id,
                                    "emby_person_id": None
                                }
                                final_cast_map[tmdb_id_from_map] = new_actor_entry
                            else:
                                # ★★★ 修复：合并豆瓣角色名 ★★★
                                existing_actor = final_cast_map[tmdb_id_from_map]
                                if utils.contains_chinese(d_actor.get("Name", "")):
                                    existing_actor["name"] = d_actor.get("Name")
                                d_role = d_actor.get("Role", "").strip()
                                if d_role and utils.contains_chinese(d_role) and d_role != "演员":
                                    existing_actor["character"] = d_role
                            match_found = True
                    if not match_found:
                        still_unmatched.append(d_actor)
                unmatched_douban_actors = still_unmatched

                if self.config.get(constants.CONFIG_OPTION_DOUBAN_ENABLE_ONLINE_API, False):
                    logger.info(f"  ➜ 匹配阶段 3: 用IMDb ID进行最终匹配和新增 ({len(unmatched_douban_actors)} 位演员)")
                    still_unmatched_final = []
                    for i, d_actor in enumerate(unmatched_douban_actors):
                        if self.is_stop_requested(): raise InterruptedError("任务中止")
                        
                        if len(final_cast_map) >= limit:
                            logger.info(f"  ➜ 演员数已达上限 ({limit})，跳过剩余 {len(unmatched_douban_actors) - i} 位演员的API查询。")
                            still_unmatched_final.extend(unmatched_douban_actors[i:])
                            break

                        d_douban_id = d_actor.get("DoubanCelebrityId")
                        match_found = False
                        if d_douban_id and self.douban_api and self.tmdb_api_key:
                            if self.is_stop_requested(): raise InterruptedError("任务中止")
                            details = self.douban_api.celebrity_details(d_douban_id)
                            time_module.sleep(0.3)
                            d_imdb_id = None
                            if details and not details.get("error"):
                                try:
                                    info_list = details.get("extra", {}).get("info", [])
                                    if isinstance(info_list, list):
                                        for item in info_list:
                                            if isinstance(item, list) and len(item) == 2 and item[0] == 'IMDb编号':
                                                d_imdb_id = item[1]
                                                break
                                except Exception as e_parse:
                                    logger.warning(f"  ➜ 解析 IMDb ID 时发生意外错误: {e_parse}")
                            
                            if d_imdb_id:
                                logger.debug(f"  ➜ 为 '{d_actor.get('Name')}' 获取到 IMDb ID: {d_imdb_id}，开始匹配...")
                                
                                entry_from_map = self.actor_db_manager.find_person_by_any_id(cursor, imdb_id=d_imdb_id)
                                if entry_from_map and entry_from_map.get("tmdb_person_id"):
                                    tmdb_id_from_map = str(entry_from_map.get("tmdb_person_id"))
                                    if tmdb_id_from_map not in final_cast_map:
                                        logger.debug(f"    ├─ 匹配成功 (通过 IMDb映射): 豆瓣演员 '{d_actor.get('Name')}' -> 加入最终演员表")
                                        new_actor_entry = {
                                            "id": tmdb_id_from_map, "name": d_actor.get("Name"),
                                            "character": d_actor.get("Role"), "order": 999, "imdb_id": d_imdb_id,
                                            "douban_id": d_douban_id, "emby_person_id": None
                                        }
                                        final_cast_map[tmdb_id_from_map] = new_actor_entry
                                    else:
                                        # ★★★ 修复：合并豆瓣角色名 ★★★
                                        existing_actor = final_cast_map[tmdb_id_from_map]
                                        if utils.contains_chinese(d_actor.get("Name", "")):
                                            existing_actor["name"] = d_actor.get("Name")
                                        d_role = d_actor.get("Role", "").strip()
                                        if d_role and utils.contains_chinese(d_role) and d_role != "演员":
                                            existing_actor["character"] = d_role
                                    match_found = True
                                
                                if not match_found:
                                    logger.debug(f"  ➜ 数据库未找到 {d_imdb_id} 的映射，开始通过 TMDb API 反查...")
                                    if self.is_stop_requested(): raise InterruptedError("任务中止")
                                    person_from_tmdb = tmdb.find_person_by_external_id(
                                        external_id=d_imdb_id, api_key=self.tmdb_api_key, source="imdb_id"
                                    )
                                    if person_from_tmdb and person_from_tmdb.get("id"):
                                        tmdb_id_from_find = str(person_from_tmdb.get("id"))
                                        
                                        d_actor['tmdb_id_from_api'] = tmdb_id_from_find
                                        d_actor['imdb_id_from_api'] = d_imdb_id

                                        final_check_row = self.actor_db_manager.find_person_by_any_id(cursor, tmdb_id=tmdb_id_from_find)
                                        if final_check_row:
                                            if tmdb_id_from_find not in final_cast_map:
                                                logger.info(f"    ├─ 匹配成功 (通过 TMDb反查): 豆瓣演员 '{d_actor.get('Name')}' -> 加入最终演员表")
                                                new_actor_entry = {
                                                    "id": tmdb_id_from_find, "name": d_actor.get("Name"),
                                                    "character": d_actor.get("Role"), "order": 999,
                                                    "imdb_id": d_imdb_id, "douban_id": d_douban_id,
                                                    "emby_person_id": None
                                                }
                                                final_cast_map[tmdb_id_from_find] = new_actor_entry
                                            else:
                                                # ★★★ 修复：合并豆瓣角色名 ★★★
                                                existing_actor = final_cast_map[tmdb_id_from_find]
                                                if utils.contains_chinese(d_actor.get("Name", "")):
                                                    existing_actor["name"] = d_actor.get("Name")
                                                d_role = d_actor.get("Role", "").strip()
                                                if d_role and utils.contains_chinese(d_role) and d_role != "演员":
                                                    existing_actor["character"] = d_role
                                            match_found = True
                        
                        if not match_found:
                            still_unmatched_final.append(d_actor)

                    if still_unmatched_final:
                        logger.info(f"  ➜ 检查 {len(still_unmatched_final)} 位未匹配演员，尝试合并或加入最终列表...")
                        added_count = 0
                        merged_count = 0
                        
                        for d_actor in still_unmatched_final:
                            tmdb_id_to_process = d_actor.get('tmdb_id_from_api')
                            if tmdb_id_to_process:
                                if tmdb_id_to_process in final_cast_map:
                                    existing_actor = final_cast_map[tmdb_id_to_process]
                                    original_name = existing_actor.get("name")
                                    new_name = d_actor.get("Name")
                                    
                                    if new_name and new_name != original_name and utils.contains_chinese(new_name):
                                        existing_actor["name"] = new_name
                                        logger.debug(f"    ➜ [合并] 已将演员 (TMDb ID: {tmdb_id_to_process}) 的名字从 '{original_name}' 更新为 '{new_name}'")
                                        merged_count += 1
                                    
                                    # ★★★ 修复：优先使用豆瓣角色名更新 ★★★
                                    d_role = d_actor.get("Role", "").strip()
                                    if d_role and utils.contains_chinese(d_role) and d_role != "演员":
                                        existing_actor["character"] = d_role
                                        logger.debug(f"    ➜ [合并] 优先使用豆瓣角色名更新为: '{d_role}'")
                                else:
                                    new_actor_entry = {
                                        "id": tmdb_id_to_process,
                                        "name": d_actor.get("Name"),
                                        "character": d_actor.get("Role"),
                                        "order": 999,
                                        "imdb_id": d_actor.get("imdb_id_from_api"),
                                        "douban_id": d_actor.get("DoubanCelebrityId"),
                                        "emby_person_id": None
                                    }
                                    final_cast_map[tmdb_id_to_process] = new_actor_entry
                                    added_count += 1
                        
                        if merged_count > 0:
                            logger.info(f"  ➜ 成功合并了 {merged_count} 位现有演员的豆瓣信息。")
                        if added_count > 0:
                            logger.info(f"  ➜ 成功新增了 {added_count} 位演员到最终列表。")
        
        current_cast_list = list(final_cast_map.values())
        
        # ======================================================================
        # 步骤 4: 从 TMDb 补全头像
        # ======================================================================
        actors_to_supplement = [
            actor for actor in current_cast_list 
            if str(actor.get("id")) not in original_tmdb_ids and actor.get("id")
        ]
        
        if actors_to_supplement:
            total_to_supplement = len(actors_to_supplement)
            logger.info(f"  ➜ 开始为 {total_to_supplement} 位新增演员检查并补全头像信息...")

            ids_to_fetch = [actor.get("id") for actor in actors_to_supplement if actor.get("id")]
            all_cached_metadata = self.actor_db_manager.get_full_actor_details_by_tmdb_ids(cursor, ids_to_fetch)
            
            supplemented_count = 0
            for actor in actors_to_supplement:
                if stop_event and stop_event.is_set(): raise InterruptedError("任务中止")
                
                tmdb_id = actor.get("id")
                profile_path = None
                cached_meta = all_cached_metadata.get(tmdb_id)
                if cached_meta and cached_meta.get("profile_path"):
                    profile_path = cached_meta["profile_path"]
                
                elif tmdb_api_key:
                    person_details = tmdb.get_person_details_tmdb(tmdb_id, tmdb_api_key)
                    if person_details:
                        if person_details.get("profile_path"):
                            profile_path = person_details["profile_path"]
                
                if profile_path:
                    actor["profile_path"] = profile_path
                    supplemented_count += 1

            logger.info(f"  ➜ 新增演员头像信息补全完成，成功为 {supplemented_count}/{total_to_supplement} 位演员补充了头像。")
        else:
            logger.info("  ➜ 没有需要补充头像的新增演员。")

        # ======================================================================
        # 步骤 5: 移除无头像演员
        # ======================================================================
        if self.config.get(constants.CONFIG_OPTION_REMOVE_ACTORS_WITHOUT_AVATARS, True):
            actors_with_avatars = [actor for actor in current_cast_list if actor.get("profile_path")]
            actors_without_avatars = [actor for actor in current_cast_list if not actor.get("profile_path")]

            if actors_without_avatars:
                removed_names = [a.get('name', f"TMDbID:{a.get('id')}") for a in actors_without_avatars]
                logger.info(f"  ➜ 将移除 {len(actors_without_avatars)} 位无头像的演员: {removed_names}")
                current_cast_list = actors_with_avatars
        else:
            logger.info("  ➜ 未启用移除无头像演员。")

        # ======================================================================
        # 步骤 6：智能截断与排序
        # ======================================================================
        max_actors = self.config.get(constants.CONFIG_OPTION_MAX_ACTORS_TO_PROCESS, 30)
        try:
            limit = int(max_actors)
            if limit <= 0: limit = 30
        except (ValueError, TypeError):
            limit = 30

        original_count = len(current_cast_list)
        
        if original_count > limit:
            logger.info(f"  ➜ 演员列表总数 ({original_count}) 超过上限 ({limit})，将优先保留有头像的演员后进行截断。")
            sort_key = lambda x: x.get('order') if x.get('order') is not None and x.get('order') >= 0 else 999
            with_profile = [actor for actor in current_cast_list if actor.get("profile_path")]
            without_profile = [actor for actor in current_cast_list if not actor.get("profile_path")]
            with_profile.sort(key=sort_key)
            without_profile.sort(key=sort_key)
            prioritized_list = with_profile + without_profile
            current_cast_list = prioritized_list[:limit]
            logger.debug(f"  ➜ 截断后，保留了 {len(with_profile)} 位有头像演员中的 {len([a for a in current_cast_list if a.get('profile_path')])} 位。")
        else:
            current_cast_list.sort(key=lambda x: x.get('order') if x.get('order') is not None and x.get('order') >= 0 else 999)

        # ======================================================================
        # 步骤 7: 最终格式化
        # ======================================================================
        logger.info(f"  ➜ 将对 {len(current_cast_list)} 位演员进行最终格式化处理...")

        # 保护性保留内存映射供下一步更新 Emby API 使用
        tmdb_to_emby_id_map = {
            str(actor.get('id')): actor.get('emby_person_id')
            for actor in current_cast_list if actor.get('id') and actor.get('emby_person_id')
        }
        
        # 获取原始数据并格式化
        raw_genres = item_details_from_emby.get("Genres", [])
        if raw_genres and isinstance(raw_genres[0], dict):
            genres = [g.get('name') for g in raw_genres if g.get('name')]
        else:
            genres = raw_genres

        is_animation = "Animation" in genres or "动画" in genres or "Documentary" in genres or "纪录" in genres or "记录" in genres
        final_cast_perfect = actor_utils.format_and_complete_cast_list(
            current_cast_list, is_animation, self.config, mode='auto'
        )
        
        # 将刚刚隔离保留的映射物归原主
        for actor in final_cast_perfect:
            tmdb_id_str = str(actor.get("id"))
            if tmdb_id_str in tmdb_to_emby_id_map:
                actor["emby_person_id"] = tmdb_to_emby_id_map[tmdb_id_str]
        for actor in final_cast_perfect:
            actor["provider_ids"] = {
                "Tmdb": str(actor.get("id")),
                "Imdb": actor.get("imdb_id"),
                "Douban": actor.get("douban_id")
            }

        # ======================================================================
        # 步骤 8: 最终数据回写
        # ======================================================================
        logger.info(f"  ➜ 开始将 {len(final_cast_perfect)} 位最终演员的完整信息同步回数据库...")
        processed_count = 0
        
        emby_config_for_upsert = {"url": self.emby_url, "api_key": self.emby_api_key, "user_id": self.emby_user_id}

        for actor in final_cast_perfect:
            map_id, action = self.actor_db_manager.upsert_person(cursor, actor, emby_config_for_upsert)
            
            if action not in ["ERROR", "SKIPPED", "CONFLICT_ERROR", "UNKNOWN_ERROR"]:
                processed_count += 1
            else:
                cursor.connection.rollback()
                cursor.execute("BEGIN")

        logger.info(f"  ➜ 成功处理了 {processed_count} 位演员的数据库回写/更新。")

        return final_cast_perfect
    
    def translate_cast_list_for_editing(self, 
                                    cast_list: List[Dict[str, Any]], 
                                    title: Optional[str] = None, 
                                    year: Optional[int] = None,
                                    tmdb_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not cast_list:
            return []

        if not self.ai_translator or not self.config.get(constants.CONFIG_OPTION_AI_TRANSLATE_ACTOR_ROLE, False):
            logger.info("手动编辑-一键翻译：AI翻译未启用，任务跳过。")
            translated_cast_for_status = [dict(actor) for actor in cast_list]
            for actor in translated_cast_for_status:
                name_needs_translation = actor.get('name') and not utils.contains_chinese(actor.get('name'))
                role_needs_translation = actor.get('role') and not utils.contains_chinese(actor.get('role'))
                if name_needs_translation or role_needs_translation:
                    actor['matchStatus'] = 'AI未启用'
                    break 
            return translated_cast_for_status

        translation_mode = self.config.get(constants.CONFIG_OPTION_AI_TRANSLATION_MODE, "fast")
        
        context_log = f" (上下文: {title} {year})" if title and translation_mode == 'quality' else ""
        logger.info(f"手动编辑-一键翻译：开始批量处理 {len(cast_list)} 位演员 (模式: {translation_mode}){context_log}。")
        
        translated_cast = [dict(actor) for actor in cast_list]
        
        try:
            with get_central_db_connection() as conn:
                cursor = conn.cursor()
                
                translation_cache = {} 
                texts_to_translate = set()

                texts_to_collect = set()
                for actor in translated_cast:
                    if actor.get('name') and not utils.contains_chinese(actor.get('name')):
                        texts_to_collect.add(actor['name'].strip())
                    
                    if actor.get('role'):
                        cleaned_role = utils.clean_character_name_static(actor['role'])
                        actor['role'] = cleaned_role 
                        if not utils.contains_chinese(cleaned_role):
                            texts_to_collect.add(cleaned_role)

                logger.debug(f"[{translation_mode}模式] 正在检查全局翻译缓存...")
                for text in texts_to_collect:
                    cached_entry = self.actor_db_manager.get_translation_from_db(cursor=cursor, text=text)
                    if cached_entry and cached_entry.get("translated_text"):
                        translation_cache[text] = cached_entry.get("translated_text")
                    else:
                        texts_to_translate.add(text)

                if texts_to_translate:
                    logger.info(f"手动编辑-翻译：将 {len(texts_to_translate)} 个词条提交给AI (模式: {translation_mode})。")
                    translation_map_from_api = self.ai_translator.batch_translate(
                        texts=list(texts_to_translate),
                        mode=translation_mode,
                        title=title,
                        year=year
                    )
                    
                    if translation_map_from_api and isinstance(translation_map_from_api, dict):
                        translation_cache.update(translation_map_from_api)
                        
                        for original, translated in translation_map_from_api.items():
                            self.actor_db_manager.save_translation_to_db(
                                cursor=cursor,
                                original_text=original, 
                                translated_text=translated, 
                                engine_used=f"manual_{translation_mode}" 
                            )
                    else:
                        logger.warning("手动编辑-翻译：AI批量翻译未返回有效结果。")
                else:
                    logger.info("手动编辑-翻译：所有词条均在缓存中找到，无需调用API。")

                if translation_cache:
                    for i, actor in enumerate(translated_cast):
                        original_name = actor.get('name', '').strip()
                        if original_name in translation_cache:
                            translated_cast[i]['name'] = translation_cache[original_name]
                        
                        current_role = actor.get('role', '')
                        if current_role in translation_cache:
                            translated_cast[i]['role'] = translation_cache[current_role]
                        
                        if translated_cast[i].get('name') != actor.get('name') or translated_cast[i].get('role') != actor.get('role'):
                            translated_cast[i]['matchStatus'] = '已翻译'
        
        except Exception as e:
            logger.error(f"一键翻译时发生错误: {e}", exc_info=True)
            for actor in translated_cast:
                actor['matchStatus'] = '翻译出错'
                break
            return translated_cast

        logger.info("手动编辑-翻译完成。")
        return translated_cast
    
    def process_item_with_manual_cast(self, item_id: str, manual_cast_list: List[Dict[str, Any]], item_name: str) -> bool:
        logger.info(f"  ➜ 手动处理流程启动：ItemID: {item_id} ('{item_name}')")
        
        try:
            item_details = emby.get_emby_item_details(item_id, self.emby_url, self.emby_api_key, self.emby_user_id)
            if not item_details: raise ValueError(f"无法获取项目 {item_id} 的详情。")
            
            raw_emby_actors = [p for p in item_details.get("People", []) if p.get("Type") == "Actor"]
            emby_config = {"url": self.emby_url, "api_key": self.emby_api_key, "user_id": self.emby_user_id}

            with get_central_db_connection() as conn:
                cursor = conn.cursor()
                enriched_actors = self.actor_db_manager.enrich_actors_with_provider_ids(cursor, raw_emby_actors, emby_config)

            logger.info(f"  ➜ 手动处理：步骤 1/6: 构建TMDb与Emby演员的ID映射...")
            tmdb_to_emby_map = {}
            for person in enriched_actors:
                person_tmdb_id = (person.get("ProviderIds") or {}).get("Tmdb")
                if person_tmdb_id:
                    tmdb_to_emby_map[str(person_tmdb_id)] = person.get("Id")
            logger.info(f"  ➜ 成功构建了 {len(tmdb_to_emby_map)} 条ID映射。")
            
            item_type = item_details.get("Type")
            tmdb_id = item_details.get("ProviderIds", {}).get("Tmdb")
            if not tmdb_id: raise ValueError(f"项目 {item_id} 缺少 TMDb ID。")

            tmdb_details_for_manual_extra = None
            aggregated_tmdb_data_manual = None
            if self.tmdb_api_key:
                if item_type == "Movie":
                    tmdb_details_for_manual_extra = tmdb.get_movie_details(tmdb_id, self.tmdb_api_key)
                    if not tmdb_details_for_manual_extra:
                        logger.warning(f"  ➜ 手动处理：无法从 TMDb 获取电影 '{item_name}' ({tmdb_id}) 的详情。")
                elif item_type == "Series":
                    aggregated_tmdb_data_manual = tmdb.aggregate_full_series_data_from_tmdb(int(tmdb_id), self.tmdb_api_key)
                    if aggregated_tmdb_data_manual:
                        tmdb_details_for_manual_extra = aggregated_tmdb_data_manual.get("series_details")
                    else:
                        logger.warning(f"  ➜ 手动处理：无法从 TMDb 获取剧集 '{item_name}' ({tmdb_id}) 的详情。")
            else:
                logger.warning("  ➜ 手动处理：未配置 TMDb API Key，无法获取 TMDb 详情用于分级数据。")

            cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
            target_override_dir = os.path.join(self.local_data_path, "override", cache_folder_name, tmdb_id)
            main_json_filename = "all.json" if item_type == "Movie" else "series.json"
            main_json_path = os.path.join(target_override_dir, main_json_filename)

            if not os.path.exists(main_json_path):
                raise FileNotFoundError(f"手动处理失败：找不到主元数据文件 '{main_json_path}'。")

            logger.info(f"  ➜ 手动处理：步骤 2/5: 检查并更新AI翻译缓存...")
            try:
                original_roles_map = self.manual_edit_cache.get(item_id)
                if original_roles_map:
                    with get_central_db_connection() as conn:
                        cursor = conn.cursor()
                        updated_count = 0
                        
                        for actor_from_frontend in manual_cast_list:
                            tmdb_id_str = str(actor_from_frontend.get("tmdbId"))
                            if not tmdb_id_str: continue
                            
                            original_role = original_roles_map.get(tmdb_id_str)
                            if original_role is None: 
                                continue

                            new_role = actor_from_frontend.get('role', '')
                            
                            cleaned_new_role = utils.clean_character_name_static(new_role)
                            cleaned_original_role = utils.clean_character_name_static(original_role)

                            if cleaned_new_role and cleaned_new_role != cleaned_original_role:
                                cache_entry = self.actor_db_manager.get_translation_from_db(text=cleaned_original_role, by_translated_text=True, cursor=cursor)
                                if cache_entry and 'original_text' in cache_entry:
                                    original_text_key = cache_entry['original_text']
                                    self.actor_db_manager.save_translation_to_db(
                                        cursor=cursor, original_text=original_text_key,
                                        translated_text=cleaned_new_role, engine_used="manual"
                                    )
                                    logger.debug(f"  ➜ AI翻译缓存已更新: '{original_text_key}' ('{cleaned_original_role}' -> '{cleaned_new_role}')")
                                    updated_count += 1
                        if updated_count > 0:
                            logger.info(f"  ➜ 成功更新了 {updated_count} 条翻译缓存。")
                        else:
                            logger.info(f"  ➜ 无需更新翻译缓存 (角色名未发生有效变更)。")
                        conn.commit()
                else:
                    logger.warning(f"  ➜ 无法更新翻译缓存：内存中找不到 ItemID {item_id} 的原始演员数据会话。")
            except Exception as e:
                logger.error(f"  ➜ 手动处理期间更新翻译缓存时发生顶层错误: {e}", exc_info=True)
            
            logger.info(f"  ➜ 手动处理：步骤 3/6: 通过API更新现有演员的名字...")
            emby_id_to_name_map = {}
            for person in enriched_actors: 
                person_emby_id = person.get("Id")
                if person_emby_id:
                    emby_id_to_name_map[person_emby_id] = person.get("Name")
            
            tmdb_to_emby_map = {}
            emby_id_to_name_map = {}
            for person in enriched_actors:
                person_tmdb_id = (person.get("ProviderIds") or {}).get("Tmdb")
                person_emby_id = person.get("Id")
                if person_tmdb_id and person_emby_id:
                    tmdb_to_emby_map[str(person_tmdb_id)] = person_emby_id
                    emby_id_to_name_map[person_emby_id] = person.get("Name")

            updated_names_count = 0
            for actor_from_frontend in manual_cast_list:
                tmdb_id_str = str(actor_from_frontend.get("tmdbId"))
                
                actor_emby_id = tmdb_to_emby_map.get(tmdb_id_str)
                if not actor_emby_id: continue

                new_name = actor_from_frontend.get("name")
                original_name = emby_id_to_name_map.get(actor_emby_id)
                
                if new_name and original_name and new_name != original_name:
                    emby.update_person_details(
                        person_id=actor_emby_id, new_data={"Name": new_name},
                        emby_server_url=self.emby_url, emby_api_key=self.emby_api_key, user_id=self.emby_user_id
                    )
                    updated_names_count += 1
            
            if updated_names_count > 0:
                logger.info(f"  ➜ 成功通过 API 更新了 {updated_names_count} 位演员的名字。")

            logger.info(f"  ➜ 手动处理：步骤 4/6: 读取原始数据，识别并补全新增演员的元数据...")
            with open(main_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            original_cast_data = (data.get('casts', {}) or data.get('credits', {})).get('cast', [])
            original_cast_map = {str(actor.get('id')): actor for actor in original_cast_data if actor.get('id')}

            new_actor_tmdb_ids = [
                int(actor.get("tmdbId")) for actor in manual_cast_list 
                if str(actor.get("tmdbId")) not in original_cast_map
            ]

            all_new_actors_metadata = {}
            if new_actor_tmdb_ids:
                with get_central_db_connection() as conn_new:
                    cursor_new = conn_new.cursor()
                    all_new_actors_metadata = self.actor_db_manager.get_full_actor_details_by_tmdb_ids(cursor_new, new_actor_tmdb_ids)

            new_cast_built = []
            
            with get_central_db_connection() as conn:
                cursor = conn.cursor()

                for actor_from_frontend in manual_cast_list:
                    tmdb_id_str = str(actor_from_frontend.get("tmdbId"))
                    if not tmdb_id_str: continue
                    
                    if tmdb_id_str in original_cast_map:
                        updated_actor_entry = original_cast_map[tmdb_id_str].copy()
                        updated_actor_entry['name'] = actor_from_frontend.get('name')
                        updated_actor_entry['character'] = actor_from_frontend.get('role')
                        new_cast_built.append(updated_actor_entry)
                    
                    else:
                        logger.info(f"    ├─ 发现新演员: '{actor_from_frontend.get('name')}' (TMDb ID: {tmdb_id_str})，开始补全元数据...")
                        
                        person_details = all_new_actors_metadata.get(int(tmdb_id_str))
                        
                        if not person_details:
                            logger.debug(f"  ➜ 缓存未命中，从 TMDb API 获取详情...")
                            person_details_from_api = tmdb.get_person_details_tmdb(tmdb_id_str, self.tmdb_api_key)
                            if person_details_from_api:
                                self.actor_db_manager.update_actor_metadata_from_tmdb(cursor, tmdb_id_str, person_details_from_api)
                                person_details = person_details_from_api 
                            else:
                                logger.warning(f"  ➜ 无法获取TMDb ID {tmdb_id_str} 的详情，将使用基础信息跳过。")
                                person_details = {} 
                        else:
                            logger.debug(f"  ➜ 成功从数据库缓存命中元数据。")

                        new_actor_entry = {
                            "id": int(tmdb_id_str),
                            "name": actor_from_frontend.get('name'),
                            "character": actor_from_frontend.get('role'),
                            "original_name": person_details.get("original_name"),
                            "profile_path": person_details.get("profile_path"),
                            "adult": person_details.get("adult", False),
                            "gender": person_details.get("gender", 0),
                            "known_for_department": person_details.get("known_for_department", "Acting"),
                            "popularity": person_details.get("popularity", 0.0),
                            "cast_id": None, 
                            "credit_id": None,
                            "order": 999 
                        }
                        new_cast_built.append(new_actor_entry)

            logger.info(f"  ➜ 手动处理：步骤 5/6: 重建演员列表并执行最终格式化...")
            genres = item_details.get("Genres", [])
            is_animation = "Animation" in genres or "动画" in genres or "Documentary" in genres or "纪录" in genres
            final_formatted_cast = actor_utils.format_and_complete_cast_list(
                new_cast_built, is_animation, self.config, mode='manual'
            )
            final_cast_for_json = self._build_cast_from_final_data(final_formatted_cast)

            if 'casts' in data:
                data['casts']['cast'] = final_cast_for_json
            elif 'credits' in data:
                data['credits']['cast'] = final_cast_for_json
            else:
                data.setdefault('credits', {})['cast'] = final_cast_for_json
            
            with open(main_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            if item_type == "Series":
                self._inject_cast_to_series_files(
                    target_dir=target_override_dir, cast_list=final_cast_for_json,
                    series_details=item_details
                )

            logger.info("  ➜ 手动处理：步骤 6/6: 触发 Emby 刷新并更新内部日志...")
            
            emby.refresh_emby_item_metadata(
                item_emby_id=item_id,
                emby_server_url=self.emby_url,
                emby_api_key=self.emby_api_key,
                user_id_for_ops=self.emby_user_id,
                replace_all_metadata_param=True,
                item_name_for_log=item_name
            )

            with get_central_db_connection() as conn:
                cursor = conn.cursor()
                formatted_manual_metadata = None
                if tmdb_details_for_manual_extra:
                    formatted_manual_metadata = construct_metadata_payload(
                        item_type=item_type,
                        tmdb_data=tmdb_details_for_manual_extra,
                        aggregated_tmdb_data=aggregated_tmdb_data_manual,
                        emby_data_fallback=item_details
                    )
                self._upsert_media_metadata(
                    cursor=cursor,
                    item_type=item_type,
                    item_details_from_emby=item_details,
                    final_processed_cast=final_formatted_cast, 
                    source_data_package=formatted_manual_metadata, 
                )
                
                logger.info(f"  ➜ 正在将手动处理完成的《{item_name}》写入已处理日志...")
                self.log_db_manager.save_to_processed_log(cursor, item_id, item_name, score=10.0)
                self.log_db_manager.remove_from_failed_log(cursor, item_id)
                conn.commit()

            logger.info(f"  ➜ 手动处理 '{item_name}' 流程完成。")
            return True

        except Exception as e:
            logger.error(f"  ➜ 手动处理 '{item_name}' 时发生严重错误: {e}", exc_info=True)
            return False
        finally:
            if item_id in self.manual_edit_cache:
                del self.manual_edit_cache[item_id]
                logger.trace(f"已清理 ItemID {item_id} 的手动编辑会话缓存。")
    
    def get_cast_for_editing(self, item_id: str) -> Optional[Dict[str, Any]]:
        logger.info(f"  ➜ 为编辑页面准备数据：ItemID {item_id}")
        
        try:
            emby_details = emby.get_emby_item_details(item_id, self.emby_url, self.emby_api_key, self.emby_user_id)
            if not emby_details:
                raise ValueError(f"在Emby中未找到项目 {item_id}")

            item_name_for_log = emby_details.get("Name", f"未知(ID:{item_id})")
            tmdb_id = emby_details.get("ProviderIds", {}).get("Tmdb")
            item_type = emby_details.get("Type")
            if not tmdb_id:
                raise ValueError(f"项目 '{item_name_for_log}' 缺少 TMDb ID，无法定位元数据文件。")

            cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
            target_override_dir = os.path.join(self.local_data_path, "override", cache_folder_name, tmdb_id)
            main_json_filename = "all.json" if item_type == "Movie" else "series.json"
            main_json_path = os.path.join(target_override_dir, main_json_filename)

            if not os.path.exists(main_json_path):
                raise FileNotFoundError(f"无法为 '{item_name_for_log}' 准备编辑数据：找不到主元数据文件 '{main_json_path}'。请确保该项目已被至少处理过一次。")

            with open(main_json_path, 'r', encoding='utf-8') as f:
                override_data = json.load(f)
            
            cast_from_override = (override_data.get('casts', {}) or override_data.get('credits', {})).get('cast', [])
            logger.debug(f"  ➜ 成功从 override 文件为 '{item_name_for_log}' 加载了 {len(cast_from_override)} 位演员。")

            tmdb_to_emby_map = {}
            for person in emby_details.get("People", []):
                person_tmdb_id = (person.get("ProviderIds") or {}).get("Tmdb")
                if person_tmdb_id:
                    tmdb_to_emby_map[str(person_tmdb_id)] = person.get("Id")
            
            cast_for_frontend = []
            session_cache_map = {}
            
            with get_central_db_connection() as conn:
                cursor = conn.cursor()
                for actor_data in cast_from_override:
                    actor_tmdb_id = actor_data.get('id')
                    if not actor_tmdb_id: continue
                    
                    emby_person_id = tmdb_to_emby_map.get(str(actor_tmdb_id))
                    
                    image_url = None
                    profile_path = actor_data.get("profile_path")
                    if profile_path:
                        if profile_path.startswith('http'):
                            image_url = profile_path
                        else:
                            image_url = f"https://image.tmdb.org/t/p/w185{profile_path}"
                    
                    original_role = actor_data.get('character', '')
                    session_cache_map[str(actor_tmdb_id)] = original_role
                    cleaned_role_for_display = utils.clean_character_name_static(original_role)

                    cast_for_frontend.append({
                        "tmdbId": actor_tmdb_id,
                        "name": actor_data.get('name'),
                        "role": cleaned_role_for_display,
                        "imageUrl": image_url,
                        "emby_person_id": emby_person_id
                    })
                    
            self.manual_edit_cache[item_id] = session_cache_map
            logger.debug(f"已为 ItemID {item_id} 缓存了 {len(session_cache_map)} 条用于手动编辑会话的演员数据。")

            failed_log_info = {}
            with get_central_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT error_message, score FROM failed_log WHERE item_id = %s", (item_id,))
                row = cursor.fetchone()
                if row: failed_log_info = dict(row)

            response_data = {
                "item_id": item_id,
                "item_name": emby_details.get("Name"),
                "item_type": emby_details.get("Type"),
                "image_tag": emby_details.get('ImageTags', {}).get('Primary'),
                "original_score": failed_log_info.get("score"),
                "review_reason": failed_log_info.get("error_message"),
                "current_emby_cast": cast_for_frontend,
                "search_links": {
                    "baidu": utils.generate_search_url('baike', emby_details.get("Name"), emby_details.get("ProductionYear")),
                    "wikipedia": utils.generate_search_url('wikipedia', emby_details.get("Name"), emby_details.get("ProductionYear")),
                    "google": utils.generate_search_url('google', emby_details.get("Name"), emby_details.get("ProductionYear"))
                }
            }
            return response_data

        except Exception as e:
            logger.error(f"  ➜ 获取编辑数据失败 for ItemID {item_id}: {e}", exc_info=True)
            return None
    
    def sync_item_images(self, item_details: Dict[str, Any], update_description: Optional[str] = None, episode_ids_to_sync: Optional[List[str]] = None) -> bool:
        item_id = item_details.get("Id")
        item_type = item_details.get("Type")
        item_name_for_log = item_details.get("Name", f"未知项目(ID:{item_id})")
        
        if not all([item_id, item_type, self.local_data_path]):
            logger.error(f"  ➜ 跳过 '{item_name_for_log}'，因为缺少ID、类型或未配置本地数据路径。")
            return False

        try:
            log_prefix = "覆盖缓存-图片备份："
            tmdb_id = item_details.get("ProviderIds", {}).get("Tmdb")
            if not tmdb_id:
                logger.warning(f"  ➜ {log_prefix} 项目 '{item_name_for_log}' 缺少TMDb ID，无法确定覆盖目录，跳过。")
                return False
            
            cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
            base_override_dir = os.path.join(self.local_data_path, "override", cache_folder_name, tmdb_id)
            image_override_dir = os.path.join(base_override_dir, "images")
            os.makedirs(image_override_dir, exist_ok=True)

            full_image_map = {"Primary": "poster.jpg", "Backdrop": "fanart.jpg", "Logo": "clearlogo.png"}
            if item_type == "Movie":
                full_image_map["Thumb"] = "landscape.jpg"

            images_to_sync = {}
            
            if update_description:
                log_prefix = "[覆盖缓存-图片备份]"
                logger.trace(f"{log_prefix} 正在解析描述: '{update_description}'")
                
                keyword_map = {
                    "primary": "Primary",
                    "backdrop": "Backdrop",
                    "logo": "Logo",
                    "thumb": "Thumb", 
                    "banner": "Banner" 
                }
                
                desc_lower = update_description.lower()
                found_specific_image = False
                for keyword, image_type_api in keyword_map.items():
                    if keyword in desc_lower and image_type_api in full_image_map:
                        images_to_sync[image_type_api] = full_image_map[image_type_api]
                        logger.trace(f"{log_prefix} 匹配到关键词 '{keyword}'，将只同步 {image_type_api} 图片。")
                        found_specific_image = True
                        break 
                
                if not found_specific_image:
                    logger.trace(f"{log_prefix} 未能在描述中找到可识别的图片关键词，将回退到完全同步。")
                    images_to_sync = full_image_map 
            
            else:
                log_prefix = "[覆盖缓存-图片备份]"
                logger.trace(f"  ➜ {log_prefix} 未提供更新描述，将同步所有类型的图片。")
                images_to_sync = full_image_map

            if not episode_ids_to_sync:
                logger.info(f"  ➜ {log_prefix} 开始为 '{item_name_for_log}' 下载 {len(images_to_sync)} 张主图片至覆盖缓存")
                for image_type, filename in images_to_sync.items():
                    if self.is_stop_requested():
                        logger.warning(f"  ➜ {log_prefix} 收到停止信号，中止图片下载。")
                        return False
                    emby.download_emby_image(item_id, image_type, os.path.join(image_override_dir, filename), self.emby_url, self.emby_api_key)
            
            logger.trace(f"  ➜ {log_prefix} 成功完成 '{item_name_for_log}' 的覆盖缓存-图片备份。")
            return True
        except Exception as e:
            logger.error(f"{log_prefix} 为 '{item_name_for_log}' 备份图片时发生未知错误: {e}", exc_info=True)
            return False
    
    def download_images_from_tmdb(self, tmdb_id: str, item_type: str, aggregated_tmdb_data: Optional[Dict[str, Any]] = None) -> bool:
        if not tmdb_id or not self.local_data_path:
            logger.error(f"  ➜ [TMDb图片下载] 缺少 TMDb ID 或本地路径配置，无法下载。")
            return False

        try:
            log_prefix = "[TMDb图片下载]"
            
            cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
            base_override_dir = os.path.join(self.local_data_path, "override", cache_folder_name, str(tmdb_id))
            image_override_dir = os.path.join(base_override_dir, "images")
            os.makedirs(image_override_dir, exist_ok=True)

            orig_lang = "en" 
            try:
                if item_type == "Movie":
                    base_info = tmdb.get_movie_details(int(tmdb_id), self.tmdb_api_key, append_to_response="")
                elif item_type == "Series":
                    base_info = tmdb.get_tv_details(int(tmdb_id), self.tmdb_api_key, append_to_response="")
                
                if base_info:
                    orig_lang = base_info.get("original_language", "en")
            except Exception as e:
                logger.warning(f"  ➜ {log_prefix} 获取原语言失败，将默认使用 en: {e}")

            lang_pref = self.config.get(constants.CONFIG_OPTION_TMDB_IMAGE_LANGUAGE_PREFERENCE, 'zh')

            search_strategies = []
            
            if lang_pref == 'zh':
                search_strategies.append(("zh-CN", "简体中文"))
                search_strategies.append(("zh-TW,zh,zh-HK,zh-SG", "繁体/通用中文"))
                search_strategies.append(("en,null", "英文/无文字"))
                if orig_lang not in ['zh', 'cn', 'tw', 'hk', 'en']:
                    search_strategies.append((f"{orig_lang}", f"原语言({orig_lang})"))
            else:
                if orig_lang in ['zh', 'cn', 'tw', 'hk']:
                    search_strategies.append(("zh-CN,zh-HK,zh-TW,zh,cn", f"原语言(中文系/{orig_lang})"))
                elif orig_lang != 'en':
                    search_strategies.append((orig_lang, f"原语言({orig_lang})"))
                
                search_strategies.append(("en,null", "英文/无文字"))
                
                if orig_lang not in ['zh', 'cn', 'tw', 'hk']:
                    search_strategies.append(("zh-CN,zh-HK,zh-TW,zh", "中文兜底"))

            tmdb_data = None
            used_strategy = ""

            for lang_param, desc in search_strategies:
                logger.debug(f"  ➜ {log_prefix} 尝试获取图片，策略: {desc} ...")
                
                try:
                    if item_type == "Movie":
                        data = tmdb.get_movie_details(
                            int(tmdb_id), 
                            self.tmdb_api_key, 
                            append_to_response="images", 
                            include_image_language=lang_param
                        )
                    elif item_type == "Series":
                        data = tmdb.get_tv_details(
                            int(tmdb_id), 
                            self.tmdb_api_key, 
                            append_to_response="images,seasons", 
                            include_image_language=lang_param
                        )
                    
                    if data and data.get("images", {}).get("posters"):
                        tmdb_data = data
                        used_strategy = desc
                        logger.info(f"  ➜ {log_prefix} 成功通过策略 [{desc}] 获取到 {len(data['images']['posters'])} 张海报。")
                        break 
                    else:
                        logger.debug(f"  ➜ {log_prefix} 策略 [{desc}] 未返回有效海报，尝试下一策略...")
                
                except Exception as e:
                    logger.warning(f"  ➜ {log_prefix} 策略 [{desc}] 请求失败: {e}")

            if not tmdb_data:
                logger.error(f"  ➜ {log_prefix} 所有策略均未获取到图片数据。")
                return False

            downloads = []
            images_node = tmdb_data.get("images", {})

            posters_list = images_node.get("posters", [])
            if posters_list:
                selected_poster = posters_list[0]["file_path"]
                downloads.append((selected_poster, "poster.jpg"))
                logger.info(f"  ➜ {log_prefix} 选中海报: {selected_poster} (评分: {posters_list[0].get('vote_average')})")
            
            backdrops_list = images_node.get("backdrops", [])
            selected_backdrop = None
            if backdrops_list:
                selected_backdrop = backdrops_list[0]["file_path"]
            
            if not selected_backdrop:
                selected_backdrop = tmdb_data.get("backdrop_path")

            if selected_backdrop:
                downloads.append((selected_backdrop, "fanart.jpg"))
                downloads.append((selected_backdrop, "landscape.jpg"))

            logos_list = images_node.get("logos", [])
            if logos_list:
                downloads.append((logos_list[0]["file_path"], "clearlogo.png"))

            if item_type == "Series":
                if aggregated_tmdb_data and "seasons_details" in aggregated_tmdb_data:
                    for season in aggregated_tmdb_data["seasons_details"]:
                        s_num = season.get("season_number")
                        s_poster = season.get("poster_path")
                        if s_num is not None and s_poster:
                            downloads.append((s_poster, f"season-{s_num}.jpg"))
                else:
                    seasons = tmdb_data.get("seasons", [])
                    for season in seasons:
                        s_num = season.get("season_number")
                        s_poster = season.get("poster_path")
                        if s_num is not None and s_poster:
                            downloads.append((s_poster, f"season-{s_num}.jpg"))

                if aggregated_tmdb_data and "episodes_details" in aggregated_tmdb_data:
                    episodes = aggregated_tmdb_data["episodes_details"]
                    ep_list = episodes.values() if isinstance(episodes, dict) else (episodes if isinstance(episodes, list) else [])
                    for ep in ep_list:
                        s_num = ep.get("season_number")
                        e_num = ep.get("episode_number")
                        e_still = ep.get("still_path")
                        if s_num is not None and e_num is not None and e_still:
                            downloads.append((e_still, f"season-{s_num}-episode-{e_num}.jpg"))

            base_image_url = "https://image.tmdb.org/t/p/original"
            import requests
            import concurrent.futures
            
            proxies = config_manager.get_proxies_for_requests()
            
            def _download_single_image(tmdb_path, local_name):
                if not tmdb_path: return 0
                full_url = f"{base_image_url}{tmdb_path}"
                save_path = os.path.join(image_override_dir, local_name)
                
                if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                    return 0

                try:
                    resp = requests.get(full_url, timeout=15, proxies=proxies)
                    if resp.status_code == 200:
                        with open(save_path, 'wb') as f:
                            f.write(resp.content)
                        return 1
                except Exception as e:
                    logger.warning(f"  ➜ 下载图片失败 {local_name}: {e}")
                return 0

            success_count = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(_download_single_image, path, name) for path, name in downloads]
                for future in concurrent.futures.as_completed(futures):
                    success_count += future.result()

            logger.info(f"  ➜ {log_prefix} 共下载 {success_count} 张图片。")
            return True

        except Exception as e:
            logger.error(f"{log_prefix} 发生未知错误: {e}", exc_info=True)
            return False

    def sync_item_metadata(self, item_details: Dict[str, Any], tmdb_id: str,
                       final_cast_override: Optional[List[Dict[str, Any]]] = None,
                       episode_ids_to_sync: Optional[List[str]] = None,
                       metadata_override: Optional[Dict[str, Any]] = None):
        item_type = item_details.get("Type")
        log_prefix = "[覆盖缓存-元数据写入]"

        cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
        target_override_dir = os.path.join(self.local_data_path, "override", cache_folder_name, tmdb_id)
        main_json_filename = "all.json" if item_type == "Movie" else "series.json"
        main_json_path = os.path.join(target_override_dir, main_json_filename)

        os.makedirs(target_override_dir, exist_ok=True)

        perfect_cast_for_injection = []
        
        tmdb_episodes_data = None 
        tmdb_seasons_data = None

        if metadata_override:
            logger.trace(f"  ➜ {log_prefix} 检测到元数据修正，正在写入主文件...")
            
            if 'episodes_details' in metadata_override:
                tmdb_episodes_data = metadata_override['episodes_details']
            
            if 'seasons_details' in metadata_override:
                tmdb_seasons_data = metadata_override['seasons_details']

            data_to_write = copy.deepcopy(metadata_override)

            if self.config.get(constants.CONFIG_OPTION_STUDIO_TO_CHINESE, False):
                try:
                    studio_mapping_data = settings_db.get_setting('studio_mapping')
                    if not studio_mapping_data:
                        studio_mapping_data = utils.DEFAULT_STUDIO_MAPPING
                    
                    company_id_map = {}
                    network_id_map = {}
                    name_map = {} 

                    for entry in studio_mapping_data:
                        label = entry.get('label')
                        if not label: continue
                        for cid in entry.get('company_ids', []): company_id_map[int(cid)] = label
                        for nid in entry.get('network_ids', []): network_id_map[int(nid)] = label
                        for en_name in entry.get('en', []): name_map[en_name.lower().strip()] = label

                    def filter_and_translate_studios(source_list, is_network_field=False):
                        if not source_list: return []
                        filtered = []
                        for item in source_list:
                            s_id = item.get('id')
                            s_name = item.get('name', '').strip()
                            mapped_label = None
                            
                            if s_id is not None:
                                try:
                                    s_id_int = int(s_id)
                                    if is_network_field:
                                        mapped_label = network_id_map.get(s_id_int)
                                    else:
                                        mapped_label = company_id_map.get(s_id_int)
                                except: pass
                            
                            if not mapped_label and s_name:
                                mapped_label = name_map.get(s_name.lower())
                            
                            if mapped_label:
                                item['name'] = mapped_label
                                filtered.append(item)
                        return filtered

                    if item_type == 'Movie' and 'production_companies' in data_to_write:
                        data_to_write['production_companies'] = filter_and_translate_studios(data_to_write['production_companies'], is_network_field=False)
                    
                    elif item_type == 'Series':
                        if 'networks' in data_to_write:
                            data_to_write['networks'] = filter_and_translate_studios(data_to_write['networks'], is_network_field=True)
                        
                        if 'production_companies' in data_to_write:
                            data_to_write['production_companies'] = filter_and_translate_studios(data_to_write['production_companies'], is_network_field=False)

                except Exception as e_studio:
                    logger.warning(f"  ➜ {log_prefix} 处理工作室中文化时发生错误: {e_studio}")

            if item_type == 'Series':
                current_networks = data_to_write.get('networks', [])
                current_companies = data_to_write.get('production_companies', [])
                
                merged_list = current_networks + current_companies
                
                unique_networks = []
                seen_ids = set()
                seen_names = set()
                
                for item in merged_list:
                    if not isinstance(item, dict): continue
                    
                    i_id = item.get('id')
                    i_name = item.get('name')
                    
                    is_duplicate = False
                    
                    if i_id:
                        if i_id in seen_ids: is_duplicate = True
                        else: seen_ids.add(i_id)
                    
                    if i_name:
                        if i_name in seen_names: is_duplicate = True
                        else: seen_names.add(i_name)
                    
                    if not i_id and not i_name: continue
                        
                    if not is_duplicate:
                        unique_networks.append(item)
                
                data_to_write['networks'] = unique_networks
                
                if 'production_companies' in data_to_write:
                    del data_to_write['production_companies']
                
                logger.debug(f"  ➜ {log_prefix} [剧集优化] 已将制作公司合并入电视网并去重，最终数量: {len(unique_networks)}")

            if self.config.get(constants.CONFIG_OPTION_KEYWORD_TO_TAGS, False):
                try:
                    mapping_data = settings_db.get_setting('keyword_mapping')
                    if not mapping_data:
                        mapping_data = utils.DEFAULT_KEYWORD_MAPPING
                    
                    keyword_map = {}
                    for entry in mapping_data:
                        label = entry.get('label')
                        if label:
                            for kid in entry.get('ids', []):
                                keyword_map[str(kid)] = label
                    
                    source_keywords = []
                    kw_data = data_to_write.get('keywords', {})
                    if isinstance(kw_data, dict):
                        source_keywords = kw_data.get('keywords') or kw_data.get('results') or []
                    
                    final_tags = set()
                    for k in source_keywords:
                        if isinstance(k, dict):
                            kid = str(k.get('id', ''))
                            if kid in keyword_map:
                                final_tags.add(keyword_map[kid])
                    
                    tags_json_path = os.path.join(target_override_dir, "tags.json")
                    if final_tags:
                        with open(tags_json_path, 'w', encoding='utf-8') as f:
                            json.dump({"tags": list(final_tags)}, f, ensure_ascii=False, indent=2)
                        logger.info(f"  ➜ {log_prefix} 已根据映射表生成 tags.json，包含 {len(final_tags)} 个中文标签。")
                    else:
                        if os.path.exists(tags_json_path):
                            os.remove(tags_json_path)

                except Exception as e_tags:
                    logger.warning(f"  ➜ {log_prefix} 处理关键词映射写入 tags.json 时发生错误: {e_tags}")
            
            keys_to_remove = ['seasons_details', 'episodes_details', 'release_dates'] 
            for k in keys_to_remove:
                if k in data_to_write:
                    del data_to_write[k]

            with open(main_json_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_write, f, ensure_ascii=False, indent=2)

        if final_cast_override is not None:
            new_cast_for_json = self._build_cast_from_final_data(final_cast_override)
            perfect_cast_for_injection = new_cast_for_json

            if not os.path.exists(main_json_path):
                skeleton = utils.MOVIE_SKELETON_TEMPLATE if item_type == "Movie" else utils.SERIES_SKELETON_TEMPLATE
                data = json.loads(json.dumps(skeleton))
            else:
                with open(main_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            if 'casts' in data: data['casts']['cast'] = perfect_cast_for_injection
            else: data.setdefault('credits', {})['cast'] = perfect_cast_for_injection
            
            with open(main_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            if os.path.exists(main_json_path):
                 with open(main_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    perfect_cast_for_injection = (data.get('casts', {}) or data.get('credits', {})).get('cast', [])

        if item_type == "Series" and perfect_cast_for_injection:
            self._inject_cast_to_series_files(
                target_dir=target_override_dir, 
                cast_list=perfect_cast_for_injection, 
                series_details=item_details, 
                episode_ids_to_sync=episode_ids_to_sync,
                tmdb_episodes_data=tmdb_episodes_data,
                tmdb_seasons_data=tmdb_seasons_data 
            )

    def _build_cast_from_final_data(self, final_cast_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cast_list = []
        for i, actor_info in enumerate(final_cast_data):
            if not actor_info.get("id"): continue
            cast_list.append({
                "id": actor_info.get("id"), "name": actor_info.get("name"), "character": actor_info.get("character"),
                "original_name": actor_info.get("original_name"), "profile_path": actor_info.get("profile_path"),
                "adult": actor_info.get("adult", False), "gender": actor_info.get("gender", 0),
                "known_for_department": actor_info.get("known_for_department", "Acting"),
                "popularity": actor_info.get("popularity", 0.0), "cast_id": actor_info.get("cast_id"),
                "credit_id": actor_info.get("credit_id"), "order": actor_info.get("order", i)
            })
        return cast_list

    def _inject_cast_to_series_files(self, target_dir: str, cast_list: List[Dict[str, Any]], series_details: Dict[str, Any], episode_ids_to_sync: Optional[List[str]] = None, tmdb_episodes_data: Optional[Dict[str, Any]] = None, tmdb_seasons_data: Optional[List[Dict[str, Any]]] = None):
        log_prefix = "[覆盖缓存-元数据写入]"
        if cast_list is not None:
            logger.info(f"  ➜ {log_prefix} 开始将演员表智能同步到所有季/集备份文件...")
        else:
            logger.info(f"  ➜ {log_prefix} 开始将实时元数据（标题/简介）同步到所有季/集备份文件...")
        
        series_id = series_details.get("Id")
        is_pending = (series_id == 'pending') 

        master_actor_map = {}
        if cast_list:
            for actor in cast_list:
                aid = actor.get('id')
                if aid:
                    try: master_actor_map[int(aid)] = actor
                    except ValueError: continue

        def patch_actor_list(target_list):
            if not target_list: return
            for person in target_list:
                pid = person.get('id')
                if not pid: continue
                try:
                    pid_int = int(pid)
                    if pid_int in master_actor_map:
                        master_info = master_actor_map[pid_int]
                        if master_info.get('name'): person['name'] = master_info.get('name')
                        if master_info.get('original_name'): person['original_name'] = master_info.get('original_name')
                        if master_info.get('profile_path'): person['profile_path'] = master_info.get('profile_path')
                        if master_info.get('character'): person['character'] = master_info.get('character')
                except ValueError: continue

        children_from_emby = []
        
        if not is_pending:
            children_from_emby = emby.get_series_children(
                series_id=series_id, base_url=self.emby_url,
                api_key=self.emby_api_key, user_id=self.emby_user_id,
                series_name_for_log=series_details.get("Name")
            ) or []
        else:
            logger.info(f"  ➜ {log_prefix} 处于预处理模式，将基于 TMDb 数据生成分集文件列表...")
            
            seen_seasons = set() 

            if tmdb_episodes_data:
                import re
                for key, ep_data in tmdb_episodes_data.items():
                    match = re.match(r'S(\d+)E(\d+)', key)
                    if match:
                        s_num = int(match.group(1))
                        e_num = int(match.group(2))
                        
                        if s_num == 0 or e_num == 0: continue

                        children_from_emby.append({
                            "Type": "Episode",
                            "ParentIndexNumber": s_num,
                            "IndexNumber": e_num,
                            "Name": ep_data.get('name'),
                            "Overview": ep_data.get('overview')
                        })
                        
                        if s_num not in seen_seasons:
                            children_from_emby.append({
                                "Type": "Season",
                                "IndexNumber": s_num,
                                "Name": f"Season {s_num}"
                            })
                            seen_seasons.add(s_num)

            if tmdb_seasons_data:
                for season in tmdb_seasons_data:
                    if not isinstance(season, dict): continue
                    
                    s_num = season.get('season_number')
                    if s_num is not None:
                        try:
                            s_num_int = int(s_num)
                            children_from_emby.append({
                                "Type": "Season",
                                "IndexNumber": s_num_int,
                                "Name": season.get('name', f"Season {s_num_int}")
                            })
                        except ValueError:
                            pass

        child_data_map = {}
        for child in children_from_emby:
            key = None
            
            if child.get("Type") == "Season": 
                idx = child.get('IndexNumber')
                if idx is not None:
                    try:
                        s_num_int = int(idx)
                        if s_num_int > 0:
                            key = f"season-{s_num_int}"
                    except (ValueError, TypeError):
                        logger.warning(f"  ➜ {log_prefix} 跳过无效的季号 '{idx}'。")
            
            elif child.get("Type") == "Episode": 
                s_num = child.get('ParentIndexNumber')
                e_num = child.get('IndexNumber')
                
                if s_num is not None and e_num is not None:
                    try:
                        s_num_int = int(s_num)
                        e_num_int = int(e_num)
                        if s_num_int > 0 and e_num_int > 0:
                            key = f"season-{s_num_int}-episode-{e_num_int}"
                        else:
                            logger.warning(f"  ➜ {log_prefix} 跳过无效的季/集号 (S{s_num}E{e_num})。")
                    except (ValueError, TypeError):
                        logger.warning(f"  ➜ {log_prefix} 跳过无效的季/集号格式 (S:{s_num}, E:{e_num})。")
            
            if key: 
                child_data_map[key] = child

        updated_children_count = 0
        try:
            files_to_process = set() 
            if episode_ids_to_sync and not is_pending: 
                id_set = set(episode_ids_to_sync)
                for child in children_from_emby:
                    if child.get("Id") in id_set and child.get("Type") == "Episode":
                        s_num = child.get('ParentIndexNumber')
                        e_num = child.get('IndexNumber')
                        if s_num is not None and e_num is not None:
                            try:
                                s_num_int = int(s_num)
                                e_num_int = int(e_num)
                                if s_num_int > 0 and e_num_int > 0:
                                    files_to_process.add(f"season-{s_num_int}-episode-{e_num_int}.json")
                                    files_to_process.add(f"season-{s_num_int}.json") 
                            except (ValueError, TypeError):
                                pass
            else:
                for key in child_data_map.keys():
                    files_to_process.add(f"{key}.json")

            sorted_files_to_process = sorted(list(files_to_process))

            os.makedirs(target_dir, exist_ok=True)

            for filename in sorted_files_to_process:
                child_json_path = os.path.join(target_dir, filename)
                
                is_season_file = filename.startswith("season-") and "-episode-" not in filename
                is_episode_file = "-episode-" in filename
                
                if is_season_file:
                    child_data = json.loads(json.dumps(utils.SEASON_SKELETON_TEMPLATE))
                elif is_episode_file:
                    child_data = json.loads(json.dumps(utils.EPISODE_SKELETON_TEMPLATE))
                else:
                    continue

                data_source = None
                if os.path.exists(child_json_path):
                    data_source = _read_local_json(child_json_path)
                    if data_source:
                        for key in child_data.keys():
                            if key == 'credits' and 'casts' in data_source and 'credits' not in data_source:
                                 child_data['credits'] = data_source['casts']
                            elif key in data_source:
                                child_data[key] = data_source[key]
                
                if data_source:
                    for key in child_data.keys():
                        if key == 'credits' and 'casts' in data_source and 'credits' not in data_source:
                             child_data['credits'] = data_source['casts']
                        elif key in data_source:
                            child_data[key] = data_source[key]

                current_s_num = None
                current_e_num = None
                try:
                    parts = filename.replace(".json", "").split("-")
                    if is_season_file and len(parts) >= 2:
                        current_s_num = int(parts[1])
                    elif is_episode_file and len(parts) >= 4:
                        current_s_num = int(parts[1])
                        current_e_num = int(parts[3])
                except:
                    pass

                specific_tmdb_data = None
                
                if is_episode_file and tmdb_episodes_data and current_s_num is not None and current_e_num is not None:
                    key_s1e1 = f"S{current_s_num}E{current_e_num}"
                    if isinstance(tmdb_episodes_data, dict):
                        specific_tmdb_data = tmdb_episodes_data.get(key_s1e1)
                    elif isinstance(tmdb_episodes_data, list):
                        for ep in tmdb_episodes_data:
                            if ep.get('season_number') == current_s_num and ep.get('episode_number') == current_e_num:
                                specific_tmdb_data = ep
                                break
                    
                    if specific_tmdb_data:
                        child_data['id'] = specific_tmdb_data.get('id')
                        child_data['name'] = specific_tmdb_data.get('name')
                        child_data['overview'] = specific_tmdb_data.get('overview')
                        child_data['season_number'] = current_s_num
                        child_data['episode_number'] = current_e_num
                        if specific_tmdb_data.get('air_date'):
                            child_data['air_date'] = specific_tmdb_data.get('air_date')
                        if specific_tmdb_data.get('vote_average'):
                            child_data['vote_average'] = specific_tmdb_data.get('vote_average')
                        if specific_tmdb_data.get('still_path'):
                            child_data['still_path'] = specific_tmdb_data.get('still_path')

                elif is_season_file and tmdb_seasons_data and current_s_num is not None:
                    for season in tmdb_seasons_data:
                        if not isinstance(season, dict): continue
                        
                        s_num_tmdb = season.get('season_number')
                        if s_num_tmdb is not None and int(s_num_tmdb) == current_s_num:
                            specific_tmdb_data = season
                            break
                    
                    if specific_tmdb_data:
                        child_data['id'] = specific_tmdb_data.get('id')
                        child_data['name'] = specific_tmdb_data.get('name')
                        child_data['overview'] = specific_tmdb_data.get('overview')
                        child_data['season_number'] = current_s_num
                        if specific_tmdb_data.get('air_date'):
                            child_data['air_date'] = specific_tmdb_data.get('air_date')
                        if specific_tmdb_data.get('poster_path'):
                            child_data['poster_path'] = specific_tmdb_data.get('poster_path')
                
                specific_tmdb_data = None
                if is_episode_file and tmdb_episodes_data:
                    try:
                        parts = filename.replace(".json", "").split("-")
                        if len(parts) >= 4:
                            s_num = int(parts[1])
                            e_num = int(parts[3])
                            key = f"S{s_num}E{e_num}" 
                            specific_tmdb_data = tmdb_episodes_data.get(key)
                    except:
                        pass

                credits_node = child_data.get('credits')
                if not isinstance(credits_node, dict):
                    credits_node = {}
                    child_data['credits'] = credits_node

                if specific_tmdb_data:
                    should_remove_no_avatar = self.config.get(constants.CONFIG_OPTION_REMOVE_ACTORS_WITHOUT_AVATARS, True)

                    def process_actor_list(actors):
                        if not actors: return []
                        if should_remove_no_avatar:
                            return [a for a in actors if a.get('profile_path')]
                        return actors

                    raw_cast = specific_tmdb_data.get('credits', {}).get('cast', [])
                    filtered_cast = process_actor_list(raw_cast)
                    if filtered_cast:
                        credits_node['cast'] = filtered_cast
                    
                    if not credits_node.get('cast') and cast_list:
                        credits_node['cast'] = cast_list

                    raw_guests = specific_tmdb_data.get('credits', {}).get('guest_stars', [])
                    filtered_guests = process_actor_list(raw_guests)
                    if filtered_guests:
                        credits_node['guest_stars'] = filtered_guests
                    
                    if specific_tmdb_data.get('credits', {}).get('crew'):
                        credits_node['crew'] = specific_tmdb_data['credits']['crew']
                
                elif is_episode_file:
                    if not credits_node.get('cast'):
                        credits_node['cast'] = cast_list

                elif is_season_file:
                    if not credits_node.get('cast'):
                        credits_node['cast'] = cast_list

                if credits_node.get('cast'):
                    patch_actor_list(credits_node['cast'])
                
                if credits_node.get('guest_stars'):
                    patch_actor_list(credits_node['guest_stars'])

                file_key = os.path.splitext(filename)[0]
                fresh_emby_data = child_data_map.get(file_key)
                if fresh_emby_data:
                    if not specific_tmdb_data:
                        child_data['name'] = fresh_emby_data.get('Name', child_data.get('name'))
                        child_data['overview'] = fresh_emby_data.get('Overview', child_data.get('overview'))
                    if fresh_emby_data.get('CommunityRating'):
                        child_data['vote_average'] = fresh_emby_data.get('CommunityRating')

                try:
                    with open(child_json_path, 'w', encoding='utf-8') as f_child:
                        json.dump(child_data, f_child, ensure_ascii=False, indent=2)
                        updated_children_count += 1
                except Exception as e_child:
                    logger.warning(f"  ➜ 写入子文件 '{filename}' 时失败: {e_child}")
            
            logger.info(f"  ➜ {log_prefix} 成功智能同步了 {updated_children_count} 个季/集文件。")
        except Exception as e_list:
            logger.error(f"  ➜ {log_prefix} 遍历并更新季/集文件时发生错误: {e_list}", exc_info=True)

    def sync_single_item_to_metadata_cache(self, item_id: str, item_name: Optional[str] = None):
        log_prefix = f"实时同步媒体元数据 '{item_name}'"
        
        try:
            fields_to_get = "ProviderIds,Type,Name,OriginalTitle,Overview,Tags,TagItems,OfficialRating,CustomRating,Path,_SourceLibraryId,PremiereDate,ProductionYear"
            item_details = emby.get_emby_item_details(item_id, self.emby_url, self.emby_api_key, self.emby_user_id, fields=fields_to_get)
            
            if not item_details:
                logger.warning(f"  ➜ {log_prefix} 无法获取详情，跳过。")
                return
            
            tmdb_id = item_details.get("ProviderIds", {}).get("Tmdb")
            item_type = item_details.get("Type")
            
            if not tmdb_id or item_type not in ['Movie', 'Series', 'Season', 'Episode']:
                return
            
            if not item_details.get('_SourceLibraryId'):
                lib_info = emby.get_library_root_for_item(item_id, self.emby_url, self.emby_api_key, self.emby_user_id)
                if lib_info: item_details['_SourceLibraryId'] = lib_info.get('Id')

            with get_central_db_connection() as conn:
                with conn.cursor() as cursor:
                    final_tags = extract_tag_names(item_details)
                    
                    updates = {
                        "title": item_details.get('Name'),
                        "original_title": item_details.get('OriginalTitle'),
                        "overview": item_details.get('Overview'),
                        "tags_json": json.dumps(final_tags, ensure_ascii=False),
                        "last_synced_at": datetime.now(timezone.utc)
                    }
                    
                    if item_details.get('PremiereDate'):
                        updates["release_date"] = item_details['PremiereDate']
                    if item_details.get('ProductionYear'):
                        updates["release_year"] = item_details['ProductionYear']

                    new_official_rating = item_details.get('OfficialRating')
                    if new_official_rating is not None: 
                        cursor.execute("SELECT official_rating_json FROM media_metadata WHERE tmdb_id = %s AND item_type = %s", (tmdb_id, item_type))
                        row = cursor.fetchone()
                        current_rating_json = row['official_rating_json'] if row and row['official_rating_json'] else {}
                        
                        current_rating_json['US'] = new_official_rating
                        updates["official_rating_json"] = json.dumps(current_rating_json, ensure_ascii=False)
                    
                    updates["custom_rating"] = item_details.get('CustomRating')
                    
                    set_clauses = [f"{key} = %s" for key in updates.keys()]
                    sql = f"UPDATE media_metadata SET {', '.join(set_clauses)} WHERE tmdb_id = %s AND item_type = %s"
                    
                    cursor.execute(sql, tuple(updates.values()) + (tmdb_id, item_type))
                    
                    conn.commit()
            
            logger.info(f"  ➜ {log_prefix} 数据库同步完成。")

        except Exception as e:
            logger.error(f"{log_prefix} 执行时发生错误: {e}", exc_info=True)

    def sync_emby_updates_to_override_files(self, item_details: Dict[str, Any]):
        item_id = item_details.get("Id")
        item_name_for_log = item_details.get("Name", f"未知项目(ID:{item_id})")
        item_type = item_details.get("Type")
        tmdb_id = item_details.get("ProviderIds", {}).get("Tmdb")
        log_prefix = "[覆盖缓存-元数据持久化]"

        if not all([item_id, item_type, tmdb_id, self.local_data_path]):
            logger.warning(f"  ➜ {log_prefix} 跳过 '{item_name_for_log}'，缺少关键ID或路径配置。")
            return

        logger.info(f"  ➜ {log_prefix} 开始为 '{item_name_for_log}' 更新覆盖缓存文件...")

        cache_folder_name = "tmdb-movies2" if item_type == "Movie" else "tmdb-tv"
        target_override_dir = os.path.join(self.local_data_path, "override", cache_folder_name, tmdb_id)
        main_json_filename = "all.json" if item_type == "Movie" else "series.json"
        main_json_path = os.path.join(target_override_dir, main_json_filename)

        if not os.path.exists(main_json_path):
            logger.warning(f"  ➜ {log_prefix} 无法持久化修改：主覆盖文件 '{main_json_path}' 不存在。请先对该项目进行一次完整处理。")
            return

        try:
            with open(main_json_path, 'r+', encoding='utf-8') as f:
                data = json.load(f)
                updated_count = 0

                fields_to_update = {
                    "Name": "title",
                    "OriginalTitle": "original_title",
                    "Overview": "overview",
                    "Tagline": "tagline",
                    "CommunityRating": "vote_average",
                    "Genres": "genres",
                    "Studios": "production_companies",
                    "Tags": "keywords"
                }
                
                for emby_key, json_key in fields_to_update.items():
                    if emby_key in item_details:
                        new_value = item_details[emby_key]
                        
                        if emby_key in ["Studios", "Genres"]:
                            if isinstance(new_value, list):
                                if emby_key == "Studios":
                                     data[json_key] = [{"name": s.get("Name")} for s in new_value if s.get("Name")]
                                else: 
                                     data[json_key] = [{"id": 0, "name": g} for g in new_value] 
                                updated_count += 1
                        else:
                            data[json_key] = new_value
                            updated_count += 1
                
                if 'OfficialRating' in item_details:
                    new_rating = item_details['OfficialRating']
                    
                    data['mpaa'] = new_rating
                    data['certification'] = new_rating
                    
                    target_country = 'US'
                    
                    if item_type == 'Movie':
                        releases = data.setdefault('releases', {})
                        countries = releases.setdefault('countries', [])
                        
                        found = False
                        for c in countries:
                            if c.get('iso_3166_1') == target_country:
                                c['certification'] = new_rating
                                found = True
                                break
                        if not found:
                            countries.append({
                                "iso_3166_1": target_country,
                                "certification": new_rating,
                                "primary": False,
                                "release_date": ""
                            })
                            
                    elif item_type == 'Series':
                        c_ratings = data.setdefault('content_ratings', {})
                        results = c_ratings.setdefault('results', [])
                        
                        found = False
                        for r in results:
                            if r.get('iso_3166_1') == target_country:
                                r['rating'] = new_rating
                                found = True
                                break
                        if not found:
                            results.append({
                                "iso_3166_1": target_country,
                                "rating": new_rating
                            })
                    
                    updated_count += 1

                if 'PremiereDate' in item_details:
                    date_val = item_details['PremiereDate']
                    if date_val and len(date_val) >= 10:
                        if item_type == 'Movie':
                            data['release_date'] = date_val[:10]
                        elif item_type == 'Series':
                            data['first_air_date'] = date_val[:10]
                        updated_count += 1

                logger.info(f"  ➜ {log_prefix} 准备将 {updated_count} 项更新写入 '{main_json_filename}'。")

                f.seek(0)
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.truncate()

            if item_type == "Series":
                logger.info(f"  ➜ {log_prefix} 检测到为剧集，开始同步更新子项（季/集）的元数据...")
                self._inject_cast_to_series_files(
                    target_dir=target_override_dir,
                    cast_list=None, 
                    series_details=item_details
                )

            logger.info(f"  ➜ {log_prefix} 成功为 '{item_name_for_log}' 持久化了元数据修改。")

        except Exception as e:
            logger.error(f"  ➜ {log_prefix} 为 '{item_name_for_log}' 更新覆盖缓存文件时发生错误: {e}", exc_info=True)

    def close(self):
        if self.douban_api: self.douban_api.close()