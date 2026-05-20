# reverse_proxy.py (终极融合版：HTTPStrm缓存流媒体 + 虚拟库完美去重/灰块修复/iOS兼容)

import logging
import requests
import re
import os
import json
from flask import Flask, request, Response, redirect, send_file
from urllib.parse import urlparse, urlunparse
from datetime import datetime, timedelta
import time
import uuid 
from handler.poster_generator import get_missing_poster
from gevent import spawn, joinall
from websocket import create_connection
from database import custom_collection_db, queries_db
from database.connection import get_db_connection
from handler.custom_collection import RecommendationEngine
import config_manager
import constants

import extensions
import handler.emby as emby
logger = logging.getLogger(__name__)

# ==========================================
# 缓存字典，用于防止播放器嗅探导致的重复请求
# ==========================================
_strm_cdn_cache = {}

def get_strm_cache_ttl():
    """动态获取配置中的直链缓存时间，默认 1800 秒"""
    try:
        ttl = int(config_manager.APP_CONFIG.get("proxy_strm_cache_ttl", 1800))
        return ttl if ttl >= 0 else 1800
    except:
        return 1800

def clear_all_strm_cache():
    """供主程序接口调用的清空缓存方法"""
    global _strm_cdn_cache
    count = len(_strm_cdn_cache)
    _strm_cdn_cache.clear()
    logger.info(f"[HTTPStrm] 用户手动清空了 {count} 条直链缓存。")
    return count

# ==========================================
# 虚拟库 ID 处理工具
# ==========================================
MISSING_ID_PREFIX = "-800000_"

def to_missing_item_id(tmdb_id): 
    return f"{MISSING_ID_PREFIX}{tmdb_id}"

def is_missing_item_id(item_id):
    return isinstance(item_id, str) and item_id.startswith(MISSING_ID_PREFIX)

def parse_missing_item_id(item_id):
    return item_id.replace(MISSING_ID_PREFIX, "")

MIMICKED_ID_BASE = 900000
def to_mimicked_id(db_id): return str(-(MIMICKED_ID_BASE + db_id))
def from_mimicked_id(mimicked_id): return -(int(mimicked_id)) - MIMICKED_ID_BASE
def is_mimicked_id(item_id):
    try: return isinstance(item_id, str) and item_id.startswith('-')
    except: return False

def _get_real_emby_url_and_key():
    base_url = config_manager.APP_CONFIG.get("emby_server_url", "").rstrip('/')
    api_key = config_manager.APP_CONFIG.get("emby_api_key", "")
    if not base_url or not api_key: raise ValueError("Emby服务器地址或API Key未配置")
    return base_url, api_key

def _fetch_items_in_chunks(base_url, api_key, user_id, item_ids, fields):
    """并发分块获取 Emby 项目详情"""
    if not item_ids: return []
    unique_ids = list(dict.fromkeys(item_ids))
    
    def chunk_list(lst, n):
        for i in range(0, len(lst), n): yield lst[i:i + n]
    
    id_chunks = list(chunk_list(unique_ids, 200))
    target_url = f"{base_url}/emby/Users/{user_id}/Items"
    
    def fetch_chunk(chunk):
        params = {'api_key': api_key, 'Ids': ",".join(chunk), 'Fields': fields}
        try:
            resp = requests.get(target_url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json().get("Items", [])
        except Exception as e:
            logger.error(f"并发获取某分块数据时失败: {e}")
            return None
            
    greenlets = [spawn(fetch_chunk, chunk) for chunk in id_chunks]
    joinall(greenlets)
    
    all_items = []
    for g in greenlets:
        if g.value: all_items.extend(g.value)
    return all_items

def _fetch_sorted_items_via_emby_proxy(user_id, item_ids, sort_by, sort_order, limit, offset, fields, total_record_count):
    """通过 Emby 代理或内存回退排序"""
    base_url, api_key = _get_real_emby_url_and_key()
    estimated_ids_length = len(item_ids) * 33 
    URL_LENGTH_THRESHOLD = 1800 

    try:
        if estimated_ids_length < URL_LENGTH_THRESHOLD:
            logger.trace(f"  ➜ [Emby 代理排序] ID列表较短 ({len(item_ids)}个)，使用 GET 方法。")
            target_url = f"{base_url}/emby/Users/{user_id}/Items"
            emby_params = {
                'api_key': api_key, 'Ids': ",".join(item_ids), 'Fields': fields,
                'SortBy': sort_by, 'SortOrder': sort_order,
                'StartIndex': offset, 'Limit': limit,
            }
            resp = requests.get(target_url, params=emby_params, timeout=25)
            resp.raise_for_status()
            return resp.json()
        else:
            logger.trace(f"  ➜ [内存排序回退] ID列表超长 ({len(item_ids)}个)，启动内存排序。")
            primary_sort_by = sort_by.split(',')[0]
            fields_for_sorting = f"{fields},{primary_sort_by}"
            
            all_items_details = _fetch_items_in_chunks(base_url, api_key, user_id, item_ids, fields_for_sorting)
            real_total_count = len(all_items_details)

            try:
                is_desc = sort_order == 'Descending'
                def get_sort_val(item):
                    val = item.get(primary_sort_by)
                    if 'Date' in primary_sort_by or 'Year' in primary_sort_by:
                        return val or "1900-01-01T00:00:00.000Z"
                    if 'Rating' in primary_sort_by or 'Count' in primary_sort_by:
                        return float(val) if val is not None else 0
                    return str(val or "").lower()

                all_items_details.sort(key=get_sort_val, reverse=is_desc)
            except Exception as sort_e:
                logger.error(f"  ➜ 内存排序时发生错误: {sort_e}", exc_info=True)
            
            paginated_items = all_items_details[offset : offset + limit]
            return {"Items": paginated_items, "TotalRecordCount": real_total_count}

    except Exception as e:
        logger.error(f"  ➜ Emby代理排序或内存回退时失败: {e}", exc_info=True)
        return {"Items": [], "TotalRecordCount": 0}

# ==========================================
# 虚拟库业务逻辑
# ==========================================

def handle_get_views(user_id):
    """获取用户主页视图"""
    real_server_id = extensions.EMBY_SERVER_ID
    if not real_server_id: return "Proxy is not ready", 503

    try:
        user_visible_native_libs = emby.get_emby_libraries(
            config_manager.APP_CONFIG.get("emby_server_url", ""),
            config_manager.APP_CONFIG.get("emby_api_key", ""), user_id
        )
        if user_visible_native_libs is None: user_visible_native_libs = []

        collections = custom_collection_db.get_all_active_custom_collections()
        fake_views_items = []
        
        for coll in collections:
            real_emby_collection_id = coll.get('emby_collection_id')
            if not real_emby_collection_id: continue

            allowed_users = coll.get('allowed_user_ids')
            if allowed_users and isinstance(allowed_users, list):
                if user_id not in allowed_users: continue
            
            db_id = coll['id']
            mimicked_id = to_mimicked_id(db_id)
            image_tags = {"Primary": f"{real_emby_collection_id}?timestamp={int(time.time())}"}
            definition = coll.get('definition_json') or {}
            
            if isinstance(definition, str):
                try: definition = json.loads(definition)
                except Exception: definition = {}

            # 强制伪装 mixed 防止 Emby Web UI 渲染错误
            collection_type = "mixed"

            fake_view = {
                "Name": coll['name'], "ServerId": real_server_id, "Id": mimicked_id,
                "Guid": str(uuid.uuid4()), "Etag": f"{db_id}{int(time.time())}",
                "DateCreated": "2025-01-01T00:00:00.0000000Z", "CanDelete": False, "CanDownload": False,
                "SortName": coll['name'], "ExternalUrls": [], "ProviderIds": {}, "IsFolder": True,
                "ParentId": "2", "Type": "CollectionFolder", "PresentationUniqueKey": str(uuid.uuid4()),
                "DisplayPreferencesId": real_emby_collection_id if real_emby_collection_id else f"custom-{db_id}", 
                "ForcedSortName": coll['name'],
                "Taglines": [], "RemoteTrailers": [],
                "UserData": {"PlaybackPositionTicks": 0, "IsFavorite": False, "Played": False},
                "ChildCount": coll.get('in_library_count', 1),
                "PrimaryImageAspectRatio": 1.7777777777777777, 
                "CollectionType": collection_type, "ImageTags": image_tags, "BackdropImageTags": [], 
                "LockedFields": [], "LockData": False, "Tags": []
            }
            fake_views_items.append(fake_view)
        
        native_views_items = []
        should_merge_native = config_manager.APP_CONFIG.get('proxy_merge_native_libraries', True)
        if should_merge_native:
            all_native_views = user_visible_native_libs
            raw_selection = config_manager.APP_CONFIG.get('proxy_native_view_selection', '')
            selected_native_view_ids = [x.strip() for x in raw_selection.split(',') if x.strip()] if isinstance(raw_selection, str) else raw_selection
            
            if selected_native_view_ids:
                native_views_items = [view for view in all_native_views if view.get("Id") in selected_native_view_ids]
            else:
                native_views_items = []
        
        final_items = []
        native_order = config_manager.APP_CONFIG.get('proxy_native_view_order', 'before')
        if native_order == 'after':
            final_items.extend(fake_views_items)
            final_items.extend(native_views_items)
        else:
            final_items.extend(native_views_items)
            final_items.extend(fake_views_items)

        final_response = {"Items": final_items, "TotalRecordCount": len(final_items)}
        return Response(json.dumps(final_response), mimetype='application/json')
        
    except Exception as e:
        logger.error(f"[PROXY] 获取视图数据时出错: {e}", exc_info=True)
        return "Internal Proxy Error", 500

def handle_get_mimicked_library_details(user_id, mimicked_id):
    """获取虚拟库详情"""
    try:
        real_db_id = from_mimicked_id(mimicked_id)
        coll = custom_collection_db.get_custom_collection_by_id(real_db_id)
        if not coll: return "Not Found", 404

        real_server_id = extensions.EMBY_SERVER_ID
        real_emby_collection_id = coll.get('emby_collection_id')
        image_tags = {"Primary": real_emby_collection_id} if real_emby_collection_id else {}
        
        definition = coll.get('definition_json') or {}
        if isinstance(definition, str):
            try: definition = json.loads(definition)
            except Exception: definition = {}

        collection_type = "mixed"

        fake_library_details = {
            "Name": coll['name'], "ServerId": real_server_id, "Id": mimicked_id,
            "Guid": str(uuid.uuid4()), "Etag": f"{real_db_id}{int(time.time())}",
            "DateCreated": "2025-01-01T00:00:00.0000000Z", "CanDelete": False, "CanDownload": False,
            "SortName": coll['name'], "ExternalUrls": [], "ProviderIds": {}, "IsFolder": True,
            "ParentId": "2", "Type": "CollectionFolder", "PresentationUniqueKey": str(uuid.uuid4()),
            "DisplayPreferencesId": real_emby_collection_id if real_emby_collection_id else f"custom-{real_db_id}", 
            "ForcedSortName": coll['name'],
            "Taglines": [], "RemoteTrailers": [],
            "UserData": {"PlaybackPositionTicks": 0, "IsFavorite": False, "Played": False},
            "ChildCount": coll.get('in_library_count', 1),
            "PrimaryImageAspectRatio": 1.7777777777777777, 
            "CollectionType": collection_type, "ImageTags": image_tags, "BackdropImageTags": [], 
            "LockedFields": [], "LockData": False, "Tags": []
        }
        return Response(json.dumps(fake_library_details), mimetype='application/json')
    except Exception as e:
        logger.error(f"获取伪造库详情时出错: {e}", exc_info=True)
        return "Internal Server Error", 500

def handle_get_mimicked_library_image(path):
    """获取虚拟库封面图"""
    try:
        tag_with_timestamp = request.args.get('tag') or request.args.get('Tag')
        if not tag_with_timestamp: return "Bad Request", 400
        real_emby_collection_id = tag_with_timestamp.split('?')[0]
        base_url, _ = _get_real_emby_url_and_key()
        image_url = f"{base_url}/Items/{real_emby_collection_id}/Images/Primary"
        headers = {key: value for key, value in request.headers if key.lower() != 'host'}
        headers['Host'] = urlparse(base_url).netloc
        resp = requests.get(image_url, headers=headers, stream=True, params=request.args)
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        response_headers = [(name, value) for name, value in resp.raw.headers.items() if name.lower() not in excluded_headers]
        return Response(resp.iter_content(chunk_size=8192), resp.status_code, response_headers)
    except Exception as e:
        return "Internal Proxy Error", 500

UNSUPPORTED_METADATA_ENDPOINTS = [
    '/Genres', '/Studios', '/Tags', '/OfficialRatings', '/Years'
]

def handle_mimicked_library_metadata_endpoint(path, mimicked_id, params):
    """处理虚拟库的元数据请求 (白屏拦截修复)"""
    empty_response = json.dumps({"Items": [], "TotalRecordCount": 0})
    
    if any(path.endswith(endpoint) for endpoint in UNSUPPORTED_METADATA_ENDPOINTS):
        return Response(empty_response, mimetype='application/json')

    try:
        real_db_id = from_mimicked_id(mimicked_id)
        collection_info = custom_collection_db.get_custom_collection_by_id(real_db_id)
        if not collection_info or not collection_info.get('emby_collection_id'):
            return Response(empty_response, mimetype='application/json')

        real_emby_collection_id = collection_info.get('emby_collection_id')
        base_url, api_key = _get_real_emby_url_and_key()
        target_url = f"{base_url}/{path}"
        
        headers = {k: v for k, v in request.headers if k.lower() not in ['host']}
        headers['Host'] = urlparse(base_url).netloc
        
        new_params = params.copy()
        new_params['ParentId'] = real_emby_collection_id
        new_params['api_key'] = api_key
        
        resp = requests.get(target_url, headers=headers, params=new_params, timeout=15)
        resp.raise_for_status()
        
        return Response(resp.content, resp.status_code, content_type=resp.headers.get('Content-Type'))

    except Exception as e:
        logger.error(f"处理虚拟库元数据请求 '{path}' 时出错: {e}", exc_info=True)
        return Response(empty_response, mimetype='application/json')
    
def handle_get_mimicked_library_items(user_id, mimicked_id, params):
    """虚拟库核心逻辑：实时权限过滤、原生排序、多季聚合排重、灰块完美修复"""
    try:
        real_db_id = from_mimicked_id(mimicked_id)
        collection_info = custom_collection_db.get_custom_collection_by_id(real_db_id)
        if not collection_info:
            return Response(json.dumps({"Items": [], "TotalRecordCount": 0}), mimetype='application/json')

        definition = collection_info.get('definition_json') or {}
        if isinstance(definition, str):
            try: definition = json.loads(definition)
            except: definition = {}

        collection_type = collection_info.get('type')
        emby_limit = int(params.get('Limit', 50))
        offset = int(params.get('StartIndex', 0))
        
        defined_limit = definition.get('limit')
        if defined_limit: defined_limit = int(defined_limit)
        
        req_sort_by = params.get('SortBy')
        req_sort_order = params.get('SortOrder')
        defined_sort_by = definition.get('default_sort_by')
        defined_sort_order = definition.get('default_sort_order')

        if defined_sort_by and defined_sort_by != 'none':
            sort_by = defined_sort_by
            sort_order = defined_sort_order or 'Descending'
            is_native_mode = False
        else:
            sort_by = req_sort_by or 'DateCreated'
            sort_order = req_sort_order or 'Descending'
            is_native_mode = True

        is_emby_proxy_sort_required = (
            collection_type in ['ai_recommendation', 'ai_recommendation_global'] or 
            'DateLastContentAdded' in sort_by or
            (is_native_mode and sort_by not in ['DateCreated', 'Random'])
        )

        tmdb_ids_filter = None
        rules = definition.get('rules', [])
        logic = definition.get('logic', 'AND')
        item_types = definition.get('item_type', ['Movie'])
        target_library_ids = definition.get('target_library_ids', [])

        # --- 场景 A: 榜单类 (占位符 + 严格去重聚合) ---
        if collection_type == 'list':
            show_placeholders = config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_PROXY_SHOW_MISSING_PLACEHOLDERS, False)
            raw_list_json = collection_info.get('generated_media_info_json')
            raw_list = json.loads(raw_list_json) if isinstance(raw_list_json, str) else (raw_list_json or [])
            
            if raw_list:
                tmdb_ids_in_list = [str(i.get('tmdb_id')) for i in raw_list if i.get('tmdb_id')]
                
                # 获取父剧集映射
                tmdb_to_parent_map = {}
                try:
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                SELECT tmdb_id, COALESCE(parent_series_tmdb_id, tmdb_id) as series_id 
                                FROM media_metadata 
                                WHERE tmdb_id = ANY(%s)
                            """, (tmdb_ids_in_list,))
                            for row in cursor.fetchall():
                                tmdb_to_parent_map[str(row['tmdb_id'])] = str(row['series_id'])
                except Exception as e:
                    logger.error(f"获取父剧集映射失败: {e}")

                items_in_db, _ = queries_db.query_virtual_library_items(
                    rules=rules, logic=logic, user_id=user_id,
                    limit=2000, offset=0, 
                    sort_by='DateCreated', sort_order='Descending',
                    item_types=item_types, target_library_ids=target_library_ids,
                    tmdb_ids=tmdb_ids_in_list
                )
                
                global_existing_items, _ = queries_db.query_virtual_library_items(
                    rules=rules, logic=logic, user_id=None, 
                    limit=2000, offset=0,
                    item_types=item_types, target_library_ids=target_library_ids,
                    tmdb_ids=tmdb_ids_in_list
                )

                local_tmdb_map = {str(i['tmdb_id']): i['Id'] for i in items_in_db if i.get('tmdb_id')}
                local_emby_id_set = {str(i['Id']) for i in items_in_db}
                global_tmdb_set = {str(i['tmdb_id']) for i in global_existing_items if i.get('tmdb_id')}
                global_emby_id_set = {str(i['Id']) for i in global_existing_items}
                
                series_with_existing_items = set()
                for tid in local_tmdb_map.keys():
                    series_with_existing_items.add(tmdb_to_parent_map.get(tid, tid))
                for tid in global_tmdb_set:
                    series_with_existing_items.add(tmdb_to_parent_map.get(tid, tid))

                full_view_list = []
                seen_emby_ids = set()
                seen_series_tids = set()

                for raw_item in raw_list:
                    tid = str(raw_item.get('tmdb_id')) if raw_item.get('tmdb_id') else "None"
                    eid = str(raw_item.get('emby_id')) if raw_item.get('emby_id') else "None"

                    if (not tid or tid.lower() == "none") and (not eid or eid.lower() == "none"):
                        continue

                    series_tid = tmdb_to_parent_map.get(tid, tid) if tid != "None" else "None"

                    if series_tid != "None" and series_tid in seen_series_tids:
                        continue

                    added = False

                    if tid != "None" and tid in local_tmdb_map:
                        real_eid = local_tmdb_map[tid]
                        if real_eid not in seen_emby_ids:
                            full_view_list.append({"is_missing": False, "id": real_eid, "tmdb_id": tid})
                            seen_emby_ids.add(real_eid)
                            added = True
                    elif eid != "None" and eid in local_emby_id_set:
                        if eid not in seen_emby_ids:
                            full_view_list.append({"is_missing": False, "id": eid, "tmdb_id": tid})
                            seen_emby_ids.add(eid)
                            added = True
                    elif (tid != "None" and tid in global_tmdb_set) or (eid != "None" and eid in global_emby_id_set):
                        added = True 
                    elif tid != "None":
                        if series_tid in series_with_existing_items:
                            continue
                        if show_placeholders:
                            full_view_list.append({"is_missing": True, "tmdb_id": tid})
                            added = True

                    if added and series_tid != "None":
                        seen_series_tids.add(series_tid)

                    if defined_limit and len(full_view_list) >= defined_limit:
                        break

                paged_part = full_view_list[offset : offset + emby_limit]
                reported_total_count = len(full_view_list)

                real_eids = [x['id'] for x in paged_part if not x['is_missing']]
                missing_tids = [x['tmdb_id'] for x in paged_part if x['is_missing']]
                
                status_map = queries_db.get_missing_items_metadata(missing_tids)
                
                base_url, api_key = _get_real_emby_url_and_key()
                full_fields = "PrimaryImageAspectRatio,ImageTags,HasPrimaryImage,ProviderIds,UserData,Name,ProductionYear,CommunityRating,Type"
                emby_details = _fetch_items_in_chunks(base_url, api_key, user_id, real_eids, full_fields)
                emby_map = {item['Id']: item for item in emby_details}

                final_items = []
                for entry in paged_part:
                    if not entry['is_missing']:
                        eid = entry['id']
                        if eid in emby_map:
                            final_items.append(emby_map[eid])
                    else:
                        tid = entry['tmdb_id']
                        meta = status_map.get(tid, {})
                        status = meta.get('subscription_status', 'WANTED')
                        db_item_type = meta.get('item_type', 'Movie')
                        
                        placeholder = {
                            "Name": meta.get('title', '未知内容'),
                            "ServerId": extensions.EMBY_SERVER_ID,
                            "Id": to_missing_item_id(tid),
                            "Type": db_item_type,
                            "ProductionYear": int(meta.get('release_year')) if meta.get('release_year') else None,
                            "ImageTags": {"Primary": f"missing_{status}_{tid}"},
                            "HasPrimaryImage": True,
                            "PrimaryImageAspectRatio": 0.6666666666666666,
                            "UserData": {"PlaybackPositionTicks": 0, "PlayCount": 0, "IsFavorite": False, "Played": False},
                            "ProviderIds": {"Tmdb": tid},
                            "LocationType": "Virtual"
                        }
                        r_date = meta.get('release_date')
                        r_year = meta.get('release_year')
                        if r_date:
                            try:
                                if hasattr(r_date, 'strftime'): placeholder["PremiereDate"] = r_date.strftime('%Y-%m-%dT00:00:00.0000000Z')
                                else: placeholder["PremiereDate"] = str(r_date)
                            except: pass
                        if "PremiereDate" not in placeholder and r_year: placeholder["PremiereDate"] = f"{r_year}-01-01T00:00:00.0000000Z"
                        if db_item_type == 'Series': placeholder["Status"] = "Released"
                        final_items.append(placeholder)
                
                return Response(json.dumps({"Items": final_items, "TotalRecordCount": reported_total_count}), mimetype='application/json')

        # --- 场景 B: 筛选/推荐类 (自动灰块修复) ---
        else:
            if collection_type in ['ai_recommendation', 'ai_recommendation_global']:
                api_key = config_manager.APP_CONFIG.get("tmdb_api_key")
                if api_key:
                    engine = RecommendationEngine(api_key)
                    if collection_type == 'ai_recommendation': candidate_pool = engine.generate_user_vector(user_id, limit=300, allowed_types=item_types)
                    else: candidate_pool = engine.generate_global_vector(limit=300, allowed_types=item_types)
                    tmdb_ids_filter = [str(i['id']) for i in candidate_pool]

            sql_limit = defined_limit if is_emby_proxy_sort_required and defined_limit else 5000 if is_emby_proxy_sort_required else min(emby_limit, defined_limit - offset) if (defined_limit and defined_limit > offset) else emby_limit
            sql_offset = 0 if is_emby_proxy_sort_required else offset
            sql_sort = 'Random' if 'ai_recommendation' in collection_type else sort_by

            items, total_count = queries_db.query_virtual_library_items(
                rules=rules, logic=logic, user_id=user_id,
                limit=sql_limit, offset=sql_offset,
                sort_by=sql_sort, sort_order=sort_order,
                item_types=item_types, target_library_ids=target_library_ids,
                tmdb_ids=tmdb_ids_filter
            )

            reported_total_count = min(total_count, defined_limit) if defined_limit else total_count

            if not items:
                return Response(json.dumps({"Items": [], "TotalRecordCount": reported_total_count}), mimetype='application/json')

            final_emby_ids = [i['Id'] for i in items]
            full_fields = "PrimaryImageAspectRatio,ImageTags,HasPrimaryImage,ProviderIds,UserData,Name,ProductionYear,CommunityRating,DateCreated,PremiereDate,Type,RecursiveItemCount,SortName,ChildCount,BasicSyncInfo"

            if is_emby_proxy_sort_required:
                sorted_data = _fetch_sorted_items_via_emby_proxy(
                    user_id, final_emby_ids, sort_by, sort_order, emby_limit, offset, full_fields, reported_total_count
                )
                return Response(json.dumps(sorted_data), mimetype='application/json')
            else:
                base_url, api_key = _get_real_emby_url_and_key()
                items_from_emby = _fetch_items_in_chunks(base_url, api_key, user_id, final_emby_ids, full_fields)
                items_map = {item['Id']: item for item in items_from_emby}
                
                final_items = [items_map[eid] for eid in final_emby_ids if eid in items_map]
                
                # --- 核心：灰块消除补丁 ---
                expected_count = len(final_emby_ids)
                actual_count = len(final_items)
                
                if actual_count < expected_count:
                    diff = expected_count - actual_count
                    reported_total_count = max(0, reported_total_count - diff)
                    if reported_total_count <= emby_limit:
                        reported_total_count = actual_count

                return Response(json.dumps({"Items": final_items, "TotalRecordCount": reported_total_count}), mimetype='application/json')

    except Exception as e:
        logger.error(f"处理虚拟库 '{mimicked_id}' 失败: {e}", exc_info=True)
        return Response(json.dumps({"Items": [], "TotalRecordCount": 0}), mimetype='application/json')

def handle_get_latest_items(user_id, params):
    """处理首页最新媒体 (附加防泄露逻辑)"""
    try:
        base_url, api_key = _get_real_emby_url_and_key()
        virtual_library_id = params.get('ParentId') or params.get('customViewId')
        limit = int(params.get('Limit', 20))
        fields = params.get('Fields', "PrimaryImageAspectRatio,BasicSyncInfo,DateCreated,UserData")

        def get_collection_filter_ids(coll_data):
            c_type = coll_data.get('type')
            if c_type == 'list':
                raw_json = coll_data.get('generated_media_info_json')
                raw_list = json.loads(raw_json) if isinstance(raw_json, str) else (raw_json or [])
                return [str(i.get('tmdb_id')) for i in raw_list if i.get('tmdb_id')]
            elif c_type in ['ai_recommendation', 'ai_recommendation_global']:
                return ["-1"] 
            return None

        if virtual_library_id and is_mimicked_id(virtual_library_id):
            real_db_id = from_mimicked_id(virtual_library_id)
            collection_info = custom_collection_db.get_custom_collection_by_id(real_db_id)
            if not collection_info: return Response(json.dumps([]), mimetype='application/json')

            definition = collection_info.get('definition_json') or {}
            if isinstance(definition, str): definition = json.loads(definition)
            
            if not definition.get('show_in_latest', True):
                return Response(json.dumps([]), mimetype='application/json')

            tmdb_ids_filter = get_collection_filter_ids(collection_info)
            if tmdb_ids_filter is not None and (len(tmdb_ids_filter) == 0 or tmdb_ids_filter == ["-1"]):
                 return Response(json.dumps([]), mimetype='application/json')

            item_types = definition.get('item_type', ['Movie'])
            is_series_only = isinstance(item_types, list) and len(item_types) == 1 and item_types[0] == 'Series'
            sort_by = 'DateLastContentAdded,DateCreated' if is_series_only else 'DateCreated'

            items, total_count = queries_db.query_virtual_library_items(
                rules=definition.get('rules', []), logic=definition.get('logic', 'AND'),
                user_id=user_id, limit=500, offset=0,
                sort_by='DateCreated', sort_order='Descending',
                item_types=item_types, target_library_ids=definition.get('target_library_ids', []),
                tmdb_ids=tmdb_ids_filter  
            )
            
            if not items: return Response(json.dumps([]), mimetype='application/json')
            final_emby_ids = [i['Id'] for i in items]

            sorted_data = _fetch_sorted_items_via_emby_proxy(
                user_id, final_emby_ids, sort_by, 'Descending', limit, 0, fields, len(final_emby_ids)
            )
            return Response(json.dumps(sorted_data.get("Items", [])), mimetype='application/json')

        elif not virtual_library_id:
            included_collection_ids = custom_collection_db.get_active_collection_ids_for_latest_view()
            if not included_collection_ids:
                return Response(json.dumps([]), mimetype='application/json')
            
            all_latest = []
            for coll_id in included_collection_ids:
                coll = custom_collection_db.get_custom_collection_by_id(coll_id)
                if not coll: continue
                
                allowed_users = coll.get('allowed_user_ids')
                if allowed_users and user_id not in allowed_users: continue

                tmdb_ids_filter = get_collection_filter_ids(coll)
                if tmdb_ids_filter is not None and (len(tmdb_ids_filter) == 0 or tmdb_ids_filter == ["-1"]):
                    continue

                definition = coll.get('definition_json')
                items, _ = queries_db.query_virtual_library_items(
                    rules=definition.get('rules', []),
                    logic=definition.get('logic', 'AND'),
                    user_id=user_id,
                    limit=limit, 
                    offset=0,
                    sort_by='DateCreated',
                    sort_order='Descending',
                    item_types=definition.get('item_type', ['Movie']),
                    target_library_ids=definition.get('target_library_ids', []),
                    tmdb_ids=tmdb_ids_filter 
                )
                all_latest.extend(items)
            
            unique_ids = list({i['Id'] for i in all_latest})
            if not unique_ids: return Response(json.dumps([]), mimetype='application/json')
            
            items_details = _fetch_items_in_chunks(base_url, api_key, user_id, unique_ids, "DateCreated")
            items_details.sort(key=lambda x: x.get('DateCreated', ''), reverse=True)
            latest_ids = [i['Id'] for i in items_details[:limit]]

        else:
            target_url = f"{base_url}/{path.lstrip('/')}"
            forward_headers = {k: v for k, v in request.headers if k.lower() not in ['host', 'accept-encoding']}
            forward_headers['Host'] = urlparse(base_url).netloc
            forward_params = request.args.copy()
            forward_params['api_key'] = api_key
            resp = requests.request(method=request.method, url=target_url, headers=forward_headers, params=forward_params, data=request.get_data(), stream=True, timeout=30.0)
            excluded_resp_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            response_headers = [(name, value) for name, value in resp.raw.headers.items() if name.lower() not in excluded_resp_headers]
            return Response(resp.iter_content(chunk_size=8192), resp.status_code, response_headers)

        if not latest_ids:
            return Response(json.dumps([]), mimetype='application/json')

        items_from_emby = _fetch_items_in_chunks(base_url, api_key, user_id, latest_ids, fields)
        items_map = {item['Id']: item for item in items_from_emby}
        final_items = [items_map[id] for id in latest_ids if id in items_map]
        
        return Response(json.dumps(final_items), mimetype='application/json')

    except Exception as e:
        logger.error(f"  ➜ 处理最新媒体时发生未知错误: {e}", exc_info=True)
        return Response(json.dumps([]), mimetype='application/json')

# ==========================================
# 核心反代入口 (HTTPStrm + 虚拟库拦截整合)
# ==========================================

proxy_app = Flask(__name__)

@proxy_app.route('/', defaults={'path': ''})
@proxy_app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'])
def proxy_all(path):
    # --- 1. WebSocket 代理逻辑 ---
    if 'Upgrade' in request.headers and request.headers.get('Upgrade', '').lower() == 'websocket':
        ws_client = request.environ.get('wsgi.websocket')
        if not ws_client: return "WebSocket upgrade failed", 400

        try:
            base_url, _ = _get_real_emby_url_and_key()
            parsed_url = urlparse(base_url)
            ws_scheme = 'wss' if parsed_url.scheme == 'https' else 'ws'
            target_ws_url = urlunparse((ws_scheme, parsed_url.netloc, f'/{path}', '', request.query_string.decode(), ''))
            
            headers_to_server = {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'upgrade', 'connection', 'sec-websocket-key', 'sec-websocket-version']}
            ws_server = create_connection(target_ws_url, header=headers_to_server, timeout=10)

            def forward_to_server():
                try:
                    while not ws_client.closed and ws_server.connected:
                        message = ws_client.receive()
                        if message is not None: ws_server.send(message)
                        else: break
                except: pass
                finally: ws_server.close()

            def forward_to_client():
                try:
                    while ws_server.connected and not ws_client.closed:
                        message = ws_server.recv()
                        if message is not None: ws_client.send(message)
                        else: break
                except: pass
                finally: ws_client.close()
            
            greenlets = [spawn(forward_to_server), spawn(forward_to_client)]
            joinall(greenlets)
            return Response()

        except Exception as e:
            logger.error(f"WebSocket 代理错误: {e}")
            return Response(status=500)

    # --- 2. HTTP 代理逻辑 ---
    try:
        full_path = f'/{path}'
        full_path_lower = full_path.lower()
        
        # ====================================================================
        # ★★★ 拦截 H: 视频流请求 (302 优化版) ★★★
        # ====================================================================
        is_video_stream = '/videos/' in full_path_lower and ('/stream' in full_path_lower or '/original' in full_path_lower) and '/subtitles/' not in full_path_lower
        is_download = '/items/' in full_path_lower and '/download' in full_path_lower and '/remoteimages/' not in full_path_lower

        if is_video_stream or is_download:
            if 'master.m3u8' not in full_path_lower and 'hls' not in full_path_lower:
                try:
                    item_id_match = re.search(r'/(?:videos|items)/([a-zA-Z0-9_-]+)/', full_path_lower)
                    if item_id_match:
                        item_id = item_id_match.group(1)
                        base_url, api_key = _get_real_emby_url_and_key()
                        media_source_id = request.args.get('MediaSourceId')
                        play_session_id = request.args.get('PlaySessionId', '')

                        pb_url = f"{base_url}/Items/{item_id}/PlaybackInfo"
                        # 【优化点1】请求 PlaybackInfo 时锁定最高码率，确保拿到直链源码
                        pb_params = {
                            'api_key': api_key, 
                            'UserId': request.args.get('UserId') or request.args.get('userId', ''),
                            'MaxStreamingBitrate': 140000000,
                            'PlaySessionId': play_session_id
                        }
                        
                        pb_resp = requests.get(pb_url, params=pb_params, timeout=10)
                        if pb_resp.status_code == 200:
                            media_sources = pb_resp.json().get('MediaSources', [])
                            target_source = None
                            
                            if media_source_id:
                                target_source = next((s for s in media_sources if s.get('Id') == media_source_id), None)
                            if not target_source and media_sources:
                                target_source = media_sources[0]

                            if target_source:
                                file_path = target_source.get('Path', '')

                                if file_path.startswith('http://') or file_path.startswith('https://'):
                                    global _strm_cdn_cache
                                    current_time = time.time()
                                    
                                    # 清理过期缓存
                                    keys_to_delete = [k for k, v in _strm_cdn_cache.items() if current_time > v[1]]
                                    for k in keys_to_delete: del _strm_cdn_cache[k]
                                    
                                    # 命中缓存
                                    if file_path in _strm_cdn_cache and current_time <= _strm_cdn_cache[file_path][1]:
                                        cached_cdn_url = _strm_cdn_cache[file_path][0]
                                        logger.info(f"[HTTPStrm 缓存命中] 拦截到重复请求，直接返回已知 CDN 直链: {cached_cdn_url}")
                                        return redirect(cached_cdn_url, code=302)
                                        
                                    logger.info(f"[HTTPStrm] 捕获 STRM 链接，首次执行后台链路穿透: {file_path}")
                                    req_headers = {
                                        "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
                                        "Accept": "*/*"
                                    }
                                    
                                    try:
                                        strm_resp = requests.get(
                                            file_path, 
                                            headers=req_headers, 
                                            allow_redirects=True, 
                                            stream=True, 
                                            timeout=8
                                        )
                                        final_cdn_url = strm_resp.url
                                        strm_resp.close() 
                                        
                                        ttl_seconds = get_strm_cache_ttl()
                                        if final_cdn_url and final_cdn_url != file_path:
                                            logger.info(f"[HTTPStrm 网络优化] 成功穿透中间跳转链，单次直达底层 CDN: {final_cdn_url}")
                                            if ttl_seconds > 0:
                                                _strm_cdn_cache[file_path] = (final_cdn_url, current_time + ttl_seconds)
                                            return redirect(final_cdn_url, code=302)
                                        else:
                                            logger.info(f"[HTTPStrm] 链接已是直链，无中间跳转: {file_path}")
                                            if ttl_seconds > 0:
                                                _strm_cdn_cache[file_path] = (file_path, current_time + ttl_seconds)
                                            return redirect(file_path, code=302)
                                            
                                    except Exception as fetch_e:
                                        logger.warning(f"[HTTPStrm] 链路穿透失败，将直接 302 原始链接交给客户端处理。原因: {fetch_e}")
                                        return redirect(file_path, code=302)
                                else:
                                    logger.debug(f"[HTTPStrm] 媒体源不是 http(s) 链接 ({file_path})，跳过拦截，进入普通代理。")
                except Exception as e:
                    logger.error(f"[HTTPStrm] 拦截流过程出错: {e}，将无缝回退到透明代理。", exc_info=True)

            # --- 流回退/本地文件代理透传逻辑 ---
            base_url, api_key = _get_real_emby_url_and_key()
            target_url = f"{base_url}/{path.lstrip('/')}"
            forward_headers = {k: v for k, v in request.headers if k.lower() not in ['host', 'accept-encoding']}
            forward_headers['Host'] = urlparse(base_url).netloc
            forward_params = request.args.copy()
            forward_params['api_key'] = api_key

            resp = requests.request(
                method=request.method, 
                url=target_url, 
                headers=forward_headers,
                params=forward_params, 
                data=request.get_data(), 
                stream=True, 
                timeout=(10.0, 1800.0),
                allow_redirects=False # 【优化点2】禁止自动追跳转，防止代理服务器偷偷去下载网盘文件
            )

            # 【优化点2配套】如果 Emby 自己给了 302(比如使用了 Alist 等网盘挂载件)，直接透传 302
            if resp.status_code in [301, 302, 303, 307, 308]:
                redirect_url = resp.headers.get('Location', '')
                logger.debug(f"[原生重定向透传] Emby 服务器返回了重定向: {redirect_url}")
                response = redirect(redirect_url, code=resp.status_code)
                for name, value in resp.headers.items():
                    if name.lower() not in ['content-length', 'connection']:
                        response.headers[name] = value
                return response

            excluded_resp_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            response_headers = [(name, value) for name, value in resp.raw.headers.items() if name.lower() not in excluded_resp_headers]
            # 【优化点3】chunk_size 缩小为 8192，大幅降低代理转发时的内存开销
            return Response(resp.iter_content(chunk_size=8192), resp.status_code, response_headers)
        
        # ====================================================================
        # ★★★ 拦截：虚拟库业务及各接口路由 ★★★
        # ====================================================================

        # 1. 缺失占位符海报
        if path.startswith('emby/Items/') and '/Images/Primary' in path:
            item_id = path.split('/')[2]
            if is_missing_item_id(item_id):
                combined_id = parse_missing_item_id(item_id)
                real_tmdb_id = combined_id.split('_S_')[0] if '_S_' in combined_id else combined_id
                meta = queries_db.get_best_metadata_by_tmdb_id(real_tmdb_id)
                db_status = meta.get('subscription_status', 'WANTED')
                current_status = db_status if db_status in ['WANTED', 'SUBSCRIBED', 'PENDING_RELEASE', 'PAUSED', 'IGNORED'] else 'WANTED'
                
                img_file_path = get_missing_poster(
                    tmdb_id=real_tmdb_id, 
                    status=current_status,
                    poster_path=meta.get('poster_path')
                )
                
                if img_file_path and os.path.exists(img_file_path):
                    resp = send_file(img_file_path, mimetype='image/jpeg')
                    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    return resp

        # 2. Views 拦截
        if path.endswith('/Views') and path.startswith('emby/Users/'):
            # 使用更安全的 path 变量进行提取
            user_id_match = re.search(r'emby/Users/([^/]+)/', path)
            if user_id_match:
                return handle_get_views(user_id_match.group(1))
            else:
                return "Could not determine user from path", 400

        # 3. Latest 拦截
        if path.endswith('/Items/Latest'):
            user_id_match = re.search(r'/emby/Users/([^/]+)/', full_path)
            if user_id_match:
                return handle_get_latest_items(user_id_match.group(1), request.args)

        # 4. Details 拦截 (iOS兼容)
        details_match = re.search(r'/Items/(-(\d+))(?:$|\?)', full_path)
        if details_match and '/Images/' not in full_path and '/PlaybackInfo' not in full_path:
            mimicked_id = details_match.group(1)
            user_id_match = re.search(r'/Users/([^/]+)/', full_path)
            user_id = user_id_match.group(1) if user_id_match else request.args.get('UserId')
            return handle_get_mimicked_library_details(user_id, mimicked_id)

        # 5. 虚拟库图片 拦截
        if path.startswith('emby/Items/') and '/Images/' in path:
            item_id = path.split('/')[2]
            if is_mimicked_id(item_id):
                return handle_get_mimicked_library_image(path)
        
        # 6. Items / Metadata 拦截 (ParentId兼容)
        parent_id = request.args.get("ParentId") or request.args.get("parentId")
        if parent_id and is_mimicked_id(parent_id):
            user_id_match = re.search(r'emby/Users/([^/]+)/Items$', path)
            if user_id_match:
                user_id = user_id_match.group(1)
                return handle_get_mimicked_library_items(user_id, parent_id, request.args)
            return handle_mimicked_library_metadata_endpoint(path, parent_id, request.args)

        # ====================================================================
        # ★★★ 兜底透传 (普通图片/接口等非拦截请求走这里) ★★★
        # ====================================================================
        base_url, api_key = _get_real_emby_url_and_key()
        target_url = f"{base_url}/{path.lstrip('/')}"
        forward_headers = {k: v for k, v in request.headers if k.lower() not in ['host', 'accept-encoding']}
        forward_headers['Host'] = urlparse(base_url).netloc
        forward_params = request.args.copy()
        forward_params['api_key'] = api_key
        
        resp = requests.request(
            method=request.method, url=target_url, headers=forward_headers,
            params=forward_params, data=request.get_data(), stream=True, timeout=(10.0, 1800.0)
        )
        
        excluded_resp_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        response_headers = [(name, value) for name, value in resp.raw.headers.items() if name.lower() not in excluded_resp_headers]
        return Response(resp.iter_content(chunk_size=8192), resp.status_code, response_headers)
        
    except Exception as e:
        logger.error(f"[PROXY] HTTP 代理时发生未知错误: {e}", exc_info=True)
        return "Internal Server Error", 500