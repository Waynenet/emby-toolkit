# tasks/subscriptions.py
# 智能订阅模块
import time
import re
import json
from datetime import datetime, timedelta
import logging
from typing import Any, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入需要的底层模块和共享实例
import config_manager
import constants
import handler.tmdb as tmdb
import handler.moviepilot as moviepilot
import task_manager
from handler import telegram
from database import settings_db, request_db, user_db, media_db, watchlist_db
from .helpers import is_movie_subscribable, check_series_completion, parse_series_title_and_season, should_mark_as_pending

logger = logging.getLogger(__name__)

EFFECT_KEYWORD_MAP = {
    "杜比视界": ["dolby vision", "dovi"],
    "HDR": ["hdr", "hdr10", "hdr10+", "hlg"]
}

AUDIO_SUBTITLE_KEYWORD_MAP = {
    # --- 音轨关键词 ---
    "chi": ["Mandarin", "CHI", "ZHO", "国语", "国配", "国英双语", "公映", "台配", "京译", "上译", "央译"],
    "yue": ["Cantonese", "YUE", "粤语"],
    "eng": ["English", "ENG", "英语"],
    "jpn": ["Japanese", "JPN", "日语"],
    "kor": ["Korean", "KOR", "韩语"],

    # --- 字幕关键词 ---
    # 注意：resubscribe.py 会通过 "sub_" + 语言代码 来查找这里
    "sub_chi": ["CHS", "CHT", "中字", "简中", "繁中", "简", "繁", "Chinese"],
    "sub_eng": ["ENG", "英字", "English"],
    "sub_jpn": ["JPN", "日字", "日文", "Japanese"],
    "sub_kor": ["KOR", "韩字", "韩文", "Korean"],
    "sub_yue": ["CHT", "繁中", "繁体", "Cantonese"],
}

def _normalize_missing_episode_numbers(value) -> List[int]:
    """统一订阅 SUBSCRIBED 补库用：把数据库 JSONB/字符串里的缺集号整理成 int 列表。"""
    if value in (None, ''):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = re.split(r'[，,\s]+', value.strip()) if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        value = [value]

    out = []
    for v in value:
        try:
            n = int(float(v))
            if n > 0 and n not in out:
                out.append(n)
        except Exception:
            pass
    return sorted(out)


def _apply_watchlist_mp_wash_flags(
    mp_payload: Dict[str, Any],
    watchlist_config: Dict[str, Any],
    *,
    force_full: bool = False
) -> str:
    """
    根据追剧配置决定向 MoviePilot 提交的洗版参数。

    订阅助手新策略：
    - no: 关闭，不携带 best_version
    - tv_episode: 分集洗版，未完结携带 best_version，完结携带 best_version + best_version_full
    - completed_full: 完结洗版，未完结不洗版，完结携带 best_version + best_version_full
    - tv: 全集洗版，始终携带 best_version + best_version_full
    """
    mp_config = settings_db.get_setting('mp_config') or {}
    assistant = mp_config.get('subscribe_assistant')
    best_version_type = ''
    if isinstance(assistant, dict):
        best_version_type = str(assistant.get('best_version_type') or '').strip()

    if not best_version_type and isinstance(watchlist_config, dict):
        old_assistant = watchlist_config.get('subscribe_assistant')
        if isinstance(old_assistant, dict):
            best_version_type = str(old_assistant.get('best_version_type') or '').strip()

    if not best_version_type:
        best_version_type = 'no'

    mp_payload.pop('best_version', None)
    mp_payload.pop('best_version_full', None)

    if best_version_type == 'tv':
        mp_payload['best_version'] = 1
        mp_payload['best_version_full'] = 1
        return '全集洗版'

    if force_full and best_version_type in ('tv_episode', 'completed_full'):
        mp_payload['best_version'] = 1
        mp_payload['best_version_full'] = 1
        return '完结洗版'

    if best_version_type == 'tv_episode':
        mp_payload['best_version'] = 1
        return '分集洗版'

    return '补缺模式'

# ★★★ 内部辅助函数：处理整部剧集的精细化订阅 ★★★
# ==============================================================================
def _subscribe_full_series_with_logic(
    tmdb_id: int,
    series_name: str,
    config: Dict,
    tmdb_api_key: str,
    source: Dict = None,
    consume_quota: bool = False,
) -> bool:
    """
    处理整部剧集的订阅：
    1. 查询 TMDb 获取所有季。
    2. 遍历所有季。
    3. 检查是否未上映 -> 设为 PENDING_RELEASE。
    5. 检查是否完结/配置开启 -> 决定 best_version。
    6. 逐季提交订阅并更新本地数据库。
    """
    watchlist_config = settings_db.get_setting('watchlist_config') or {}

    try:
        # 1. 获取剧集详情
        series_details = tmdb.get_tv_details(tmdb_id, tmdb_api_key)
        if not series_details:
            logger.error(f"  ➜ 无法获取剧集 ID {tmdb_id} 的详情，跳过订阅。")
            return False

        # 规范化名称
        final_series_name = series_details.get('name', series_name)
        series_poster = series_details.get('poster_path')
        series_backdrop = series_details.get('backdrop_path')

        # 2. 获取所有有效季 (Season > 0)
        seasons = series_details.get('seasons', [])
        valid_seasons = sorted([s for s in seasons if s.get('season_number', 0) > 0], key=lambda x: x['season_number'])

        if not valid_seasons:
            logger.warning(f"  ➜ 剧集《{final_series_name}》没有有效的季信息，尝试直接订阅整剧。")
            # 兜底：直接订阅 ID
            mp_payload = {"name": final_series_name, "tmdbid": tmdb_id, "type": "电视剧"}
            wash_mode = _apply_watchlist_mp_wash_flags(mp_payload, watchlist_config)
            logger.info(f"  ➜ 《{final_series_name}》整剧兜底订阅使用 {wash_mode}。")
            return moviepilot.subscribe_with_custom_payload(mp_payload, config, consume_quota=consume_quota)

        # 3. 确定最后一季的季号
        last_season_num = valid_seasons[-1]['season_number']
        any_success = False

        # ★★★ 关键步骤 1：先激活父剧集 ★★★
        watchlist_db.add_item_to_watchlist(str(tmdb_id), final_series_name)

        logger.info(f"  ➜ 正在处理《{final_series_name}》的 {len(valid_seasons)} 个季 (S{valid_seasons[0]['season_number']} - S{last_season_num})...")

        # 4. 遍历逐个订阅
        for season in valid_seasons:
            s_num = season['season_number']
            s_id = season.get('id') # 季的 TMDb ID
            air_date_str = season.get('air_date')

            # 优先使用季海报，没有则使用剧集海报
            season_poster = season.get('poster_path')
            # 如果概要中缺失日期，强制获取季详情
            if not air_date_str:
                logger.debug(f"  ➜ S{s_num} 概要信息缺失发行日期，正在获取详细信息...")
                season_details_deep = tmdb.get_tv_season_details(tmdb_id, s_num, tmdb_api_key)

                if season_details_deep:
                    # 1. 尝试直接获取季日期
                    air_date_str = season_details_deep.get('air_date')

                    # 2. ★★★ 新增：如果季日期仍为空，遍历分集找最早的日期 ★★★
                    if not air_date_str and 'episodes' in season_details_deep:
                        episodes = season_details_deep['episodes']
                        # 提取所有有效的 air_date
                        valid_dates = [e.get('air_date') for e in episodes if e.get('air_date')]
                        if valid_dates:
                            # 取最早的一个日期
                            air_date_str = min(valid_dates)
                            logger.debug(f"  ➜ 从分集数据中推断出 S{s_num} 发行日期: {air_date_str}")

                    # 补全海报和简介
                    if not season_poster: season_poster = season_details_deep.get('poster_path')
                    if not season.get('overview'): season['overview'] = season_details_deep.get('overview')
            final_poster = season_poster if season_poster else series_poster

            # ==============================================================
            # 逻辑 A: 检查是否未上映 (Pending Release)
            # ==============================================================
            is_future_season = False
            # 如果有日期且大于今天，或者干脆没有日期(视为待定/未上映)，都标记为未上映
            if air_date_str:
                try:
                    air_date = datetime.strptime(air_date_str, "%Y-%m-%d").date()
                    if air_date > datetime.now().date():
                        is_future_season = True
                except ValueError:
                    pass
            else:
                # 如果深挖了详情还是没有日期，通常意味着 TBD (To Be Determined)，也应视为未上映，防止错误订阅
                is_future_season = True
                logger.info(f"  ➜ 季《{final_series_name}》S{s_num} 无发行日期，视为 '待上映'。")

            if is_future_season:
                logger.info(f"  ➜ 《{final_series_name}》第 {s_num} 季 尚未播出 ({air_date_str})，已加入待上映列表。")

                media_info = {
                    'tmdb_id': str(s_id) if s_id else f"{tmdb_id}_S{s_num}",
                    'title': season.get('name', f"第 {s_num} 季"),
                    'season_number': s_num,
                    'parent_series_tmdb_id': str(tmdb_id),
                    'release_date': air_date_str,
                    'poster_path': final_poster,
                    'backdrop_path': series_backdrop,
                    'overview': season.get('overview')
                }

                request_db.set_media_status_pending_release(
                    tmdb_ids=media_info['tmdb_id'],
                    item_type='Season',
                    source=source,
                    media_info_list=[media_info]

                )
                any_success = True
                continue

            # ==============================================================
            # 逻辑 B: 自动待定检查 (Auto Pending)
            # ==============================================================
            # 针对刚上映但集数信息不全的剧集，我们需要将其在 MP 中标记为 'P' (待定)
            # 并设置一个虚假的总集数，防止 MP 下载完现有集数后直接完结订阅。
            is_pending_logic, fake_total_episodes = should_mark_as_pending(tmdb_id, s_num, tmdb_api_key)

            if is_pending_logic:
                logger.info(f"  ➜ 季《{final_series_name}》S{s_num} 满足自动待定条件，将执行 [订阅 -> 转待定] 流程。")

            # ==============================================================
            # 逻辑 C: 准备订阅 Payload
            # ==============================================================
            mp_payload = {
                "name": final_series_name,
                "tmdbid": tmdb_id,
                "type": "电视剧",
                "season": s_num
            }

            # ==============================================================
            # 逻辑 D: 决定 Best Version (洗版/完结检测)
            # ==============================================================
            # 只有在【不满足】待定条件时，才去检查完结状态。
            # 如果已经是待定状态，说明肯定没完结，不需要检查，也不应该开启洗版。
            is_completed = False
            if not is_pending_logic:
                is_completed = check_series_completion(
                    tmdb_id,
                    tmdb_api_key,
                    season_number=s_num,
                    series_name=final_series_name
                )
                wash_mode = _apply_watchlist_mp_wash_flags(
                    mp_payload,
                    watchlist_config,
                    force_full=is_completed
                )
                if is_completed:
                    logger.info(f"  ➜ S{s_num} 已完结，强制使用 {wash_mode} 订阅。")
                else:
                    logger.info(f"  ➜ S{s_num} 未完结，向 MoviePilot 提交 {wash_mode} 订阅。")
            else:
                logger.info(f"  ➜ S{s_num} 处于待定模式，向 MoviePilot 提交补缺订阅。")

            # ==============================================================
            # 逻辑 E: 提交订阅 & 后置状态修正
            # ==============================================================
            mp_submit_success = moviepilot.subscribe_with_custom_payload(mp_payload, config, consume_quota=consume_quota)

            if mp_submit_success:
                any_success = True

                # ★★★ 核心修复：如果是待定逻辑，订阅成功后立即修改 MP 状态 ★★★
                if is_pending_logic:
                    logger.info(f"  ➜ [后置操作] 正在将 S{s_num} 的状态修改为 'P' (待定)，并将总集数修正为 {fake_total_episodes}...")
                    # 调用 moviepilot.py 中的 update_subscription_status
                    # 注意：这里传入 fake_total_episodes 以防止 MP 自动完结
                    mp_update_success = moviepilot.update_subscription_status(
                        tmdb_id=tmdb_id,
                        season=s_num,
                        status='P', # P = Pending
                        config=config,
                        total_episodes=fake_total_episodes
                    )
                    if mp_update_success:
                        logger.info(f"  ➜ S{s_num} 已成功转为待定状态。")
                    else:
                        logger.warning(f"  ➜ S{s_num} 订阅成功，但转待定状态失败。")

                # 订阅成功后，更新本地数据库状态为 SUBSCRIBED
                # (即使 MP 是 Pending，对于本地请求队列来说，它也算是“已处理/已订阅”)
                target_s_id = str(s_id) if s_id else f"{tmdb_id}_S{s_num}"
                media_info = {
                    'tmdb_id': target_s_id,
                    'parent_series_tmdb_id': str(tmdb_id),
                    'season_number': s_num,
                    'title': season.get('name'),
                    'poster_path': final_poster,
                    'backdrop_path': series_backdrop,
                    'release_date': air_date_str
                }
                request_db.set_media_status_subscribed(
                    tmdb_ids=[target_s_id],
                    item_type='Season',
                    source=source,
                    media_info_list=[media_info]
                )

        return any_success

    except Exception as e:
        logger.error(f"处理整剧订阅逻辑时出错: {e}", exc_info=True)
        return False

# ★★★ 手动动订阅任务 ★★★
def task_manual_subscribe_batch(processor, subscribe_requests: List[Dict]):
    """
    手动订阅任务
    """
    total_items = len(subscribe_requests)
    task_name = f"手动订阅 {total_items} 个项目"
    logger.trace(f"--- 开始执行 '{task_name}' 任务 ---")

    task_manager.update_status_from_thread(0, "正在准备手动订阅任务...")

    if not subscribe_requests:
        task_manager.update_status_from_thread(100, "任务完成：没有需要处理的项目。")
        return

    try:
        config = config_manager.APP_CONFIG
        tmdb_api_key = config.get(constants.CONFIG_OPTION_TMDB_API_KEY)
        watchlist_config = settings_db.get_setting('watchlist_config') or {}

        processed_count = 0

        for i, req in enumerate(subscribe_requests):
            tmdb_id = req.get('tmdb_id')
            item_type = req.get('item_type')
            item_title_for_log = req.get('title', f"ID: {tmdb_id}")
            season_number = req.get('season_number')
            user_id = req.get('user_id')

            # 构建来源信息 (用于后续通知)
            source = None
            if user_id:
                source = {'type': 'user_request', 'user_id': user_id}

            if not tmdb_id or not item_type:
                logger.warning(f"跳过一个无效的订阅请求: {req}")
                continue

            task_manager.update_status_from_thread(
                int((i / total_items) * 100),
                f"({i+1}/{total_items}) 正在处理: {item_title_for_log}"
            )

            # 检查配额
            if settings_db.get_subscription_quota() <= 0:
                logger.warning("  ➜ 每日订阅配额已用尽，任务提前结束。")
                break

            success = False

            # ==================================================================
            # 逻辑分支 1: 剧集 / 季
            # ==================================================================
            if item_type == 'Series' or item_type == 'Season':
                # 1. ★★★ 核心修复：ID 和 季号 修正 ★★★
                if item_type == 'Season':
                    # 尝试从请求中获取父剧集 ID (统一订阅页面传过来的是 series_tmdb_id 或 parent_series_tmdb_id)
                    parent_id = req.get('series_tmdb_id') or req.get('parent_series_tmdb_id')

                    # 如果请求里没有，去数据库查 (说明传入的 tmdb_id 可能是季 ID)
                    if not parent_id:
                        season_info = media_db.get_media_details(str(tmdb_id), 'Season')
                        if season_info:
                            parent_id = season_info.get('parent_series_tmdb_id')
                            if season_number is None:
                                season_number = season_info.get('season_number')

                    # 如果找到了父剧集 ID，且与当前 tmdb_id 不同，说明传入的是季 ID
                    # 必须将其替换为父剧集 ID，因为后续的 check_series_completion 和 MP 订阅都需要剧集 ID
                    if parent_id and str(parent_id) != str(tmdb_id):
                        logger.debug(f"  ➜ [ID修正] 将季 ID {tmdb_id} 替换为父剧集 ID {parent_id}")
                        tmdb_id = parent_id

                # 2. 处理单季订阅 (最常见情况)
                if season_number is not None:
                    series_name = media_db.get_series_title_by_tmdb_id(str(tmdb_id))
                    if not series_name: series_name = item_title_for_log

                    mp_payload = {
                        "name": series_name,
                        "tmdbid": int(tmdb_id),
                        "type": "电视剧",
                        "season": int(season_number)
                    }

                    # B. ★★★ 核心：完结状态检查 ★★★
                    is_completed = check_series_completion(
                        int(tmdb_id),
                        tmdb_api_key,
                        season_number=season_number,
                        series_name=series_name
                    )
                    wash_mode = _apply_watchlist_mp_wash_flags(
                        mp_payload,
                        watchlist_config,
                        force_full=is_completed
                    )

                    if is_completed:
                        logger.info(f"  ➜ [手动订阅] 第{season_number}季 已完结，强制使用 {wash_mode}。")
                    else:
                        logger.info(f"  ➜ [手动订阅] 第{season_number}季 尚未完结，使用 {wash_mode}。")

                    success = moviepilot.subscribe_with_custom_payload(mp_payload, config, consume_quota=True)

                # 3. 处理整剧订阅 (Series)
                elif item_type == 'Series':
                    # 调用整剧处理逻辑 (内部会遍历所有季)
                    success = _subscribe_full_series_with_logic(
                        tmdb_id=int(tmdb_id),
                        series_name=item_title_for_log,
                        config=config,
                        tmdb_api_key=tmdb_api_key,
                        source=source,
                        consume_quota=True,
                    )
                    if success:
                        # 整剧订阅成功只代表订阅任务已提交，不代表整剧已完成。
                        # Series/Season/Episode 的订阅状态由统一订阅与智能追剧接管；
                        # 只有本地完美完结后才清 NONE。
                        logger.info(f"  ➜ [订阅状态] 整剧订阅已提交，保留《{item_title_for_log}》的订阅状态，等待智能追剧完美完结后清理。")

                else:
                    logger.error(f"  ➜ 订阅失败：季《{item_title_for_log}》缺少季号信息。")
                    continue

            # ==================================================================
            # 逻辑分支 2: 电影
            # ==================================================================
            elif item_type == 'Movie':
                if not is_movie_subscribable(int(tmdb_id), tmdb_api_key, config):
                    logger.warning(f"  ➜ 电影《{item_title_for_log}》不满足发行日期条件，跳过订阅。")
                    continue

                mp_payload = {"name": item_title_for_log, "tmdbid": int(tmdb_id), "type": "电影"}
                # 电影手动订阅，通常意味着用户现在就想看，且电影一般没有“连载”概念
                # 可以默认开启 best_version=1 以获取更好质量，或者保持默认 0
                # 这里保持默认 0 比较稳妥，除非用户明确是洗版操作，但为了简化，这里不设 best_version
                success = moviepilot.subscribe_with_custom_payload(mp_payload, config, consume_quota=True)

            # ==================================================================
            # 结果处理
            # ==================================================================
            if success:
                logger.info(f"  ➜ 《{item_title_for_log}》订阅成功！")

                # 更新数据库状态 (Series 类型在 _subscribe_full_series_with_logic 里处理了)
                if item_type != 'Series':
                    # 如果是季，需要构建正确的 ID (例如 tmdbid_S1)
                    # 这里的 tmdb_id 已经被修正为 Series ID，所以需要重新构建 Season ID
                    target_id_for_update = str(tmdb_id)
                    if item_type == 'Season' and season_number is not None:
                         # 尝试查询真实的季 ID，查不到则用拼接 ID
                         real_season_id = request_db.get_season_tmdb_id(str(tmdb_id), season_number)
                         target_id_for_update = real_season_id if real_season_id else f"{tmdb_id}_S{season_number}"

                    request_db.set_media_status_subscribed(
                        tmdb_ids=[target_id_for_update],
                        item_type=item_type,
                    )

                processed_count += 1
            else:
                logger.error(f"  ➜ 订阅《{item_title_for_log}》失败，请检查 MoviePilot 日志。")

        final_message = f"  ➜ 手动订阅任务完成，成功处理 {processed_count}/{total_items} 个项目。"
        task_manager.update_status_from_thread(100, final_message)
        logger.info(f"--- '{task_name}' 任务执行完毕 ---")

    except Exception as e:
        logger.error(f"  ➜ {task_name} 任务失败: {e}", exc_info=True)
        task_manager.update_status_from_thread(-1, f"错误: {e}")

# ★★★ 自动订阅任务 ★★★
def task_auto_subscribe(processor):
    """
    【V2 - 统一订阅处理器】
    """
    task_name = "统一订阅处理"
    logger.trace(f"--- 开始执行 '{task_name}' 任务 ---")

    task_manager.update_status_from_thread(0, "正在加载订阅策略...")
    config = config_manager.APP_CONFIG

    # 1. 加载策略配置 (优先从数据库读取，如果没有则使用默认值)
    strategy_config = settings_db.get_setting('subscription_strategy_config') or {}
    mp_config = settings_db.get_setting('mp_config') or {}

    # 默认策略参数
    movie_search_window = int(mp_config.get('movie_search_window_days', 1))     # 默认搜索1天
    movie_pause_days = int(mp_config.get('movie_pause_days', 7))                # 默认暂停7天

    # 2. 读取请求延迟配置
    try:
        mp_config = settings_db.get_setting('mp_config') or {}
        request_delay = int(mp_config.get('resubscribe_delay_seconds', 0))
    except:
        request_delay = 0

    try:
        # ======================================================================
        # 阶段 1 - 电影间歇性订阅搜索
        # ======================================================================
        # 仅当配置有效时执行
        if movie_search_window > 0 and movie_pause_days > 0:
            logger.info(f"  ➜ [策略] 执行电影间歇性订阅搜索维护...")

            # 2.1 复活 (Revive: PAUSED -> SUBSCRIBED)
            # 对应 MP 状态: 'S' -> 'R'
            movies_to_revive = request_db.get_movies_to_revive()
            if movies_to_revive:
                revived_ids = []
                for movie in movies_to_revive:
                    tmdb_id = movie['tmdb_id']
                    title = movie['title']

                    # ★★★ 修改：直接更新状态为 'R' (Run) ★★★
                    # season=None 表示电影
                    if moviepilot.update_subscription_status(int(tmdb_id), None, 'R', config):
                        revived_ids.append(tmdb_id)
                    else:
                        # 如果更新失败（比如MP里订阅丢了），尝试重新订阅兜底
                        logger.warning(f"    - 《{title}》状态切换失败，尝试重新提交订阅...")
                        if moviepilot.subscribe_with_custom_payload({"tmdbid": int(tmdb_id), "type": "电影"}, config):
                            revived_ids.append(tmdb_id)

                if revived_ids:
                    request_db.update_movie_status_revived(revived_ids)
                    logger.info(f"  ➜ 成功复活 {len(revived_ids)} 部电影 (MP状态->R)。")

            # 2.2 暂停 (Pause: SUBSCRIBED -> PAUSED)
            # 对应 MP 状态: 'R' -> 'S'
            movies_to_pause = request_db.get_movies_to_pause(search_window_days=movie_search_window)
            if movies_to_pause:
                paused_ids = []
                for movie in movies_to_pause:
                    tmdb_id = movie['tmdb_id']
                    title = movie['title']

                    # ★★★ 修改开始：尝试暂停，失败则补订后再次暂停 ★★★
                    if moviepilot.update_subscription_status(int(tmdb_id), None, 'S', config):
                        paused_ids.append(tmdb_id)
                    else:
                        logger.warning(f"    - 《{title}》暂停失败 (MP中可能不存在)，尝试重新订阅并同步状态...")

                        # 1. 尝试补订 (默认状态通常为 R)
                        mp_payload = {"name": title, "tmdbid": int(tmdb_id), "type": "电影"}
                        if moviepilot.subscribe_with_custom_payload(mp_payload, config):
                            # 2. 补订成功后，再次尝试将其状态更新为 'S'
                            if moviepilot.update_subscription_status(int(tmdb_id), None, 'S', config):
                                paused_ids.append(tmdb_id)
                                logger.info(f"    - ➜ 《{title}》补订并暂停成功。")
                            else:
                                logger.warning(f"    - ➜ 《{title}》补订成功，但暂停状态同步失败。")
                        else:
                            logger.error(f"    - ➜ 《{title}》补订失败，无法执行暂停操作。")

                if paused_ids:
                    request_db.update_movie_status_paused(paused_ids, pause_days=movie_pause_days)
                    logger.info(f"  ➜ 成功暂停 {len(paused_ids)} 部暂无资源的电影 (MP状态->S)。")

        # 阶段 2 - 执行订阅
        # ======================================================================
        logger.info("  ➜ 正在检查未上映...")
        promoted_count = media_db.promote_pending_to_wanted()
        if promoted_count > 0:
            logger.info(f"  ➜ 成功将 {promoted_count} 个项目从“未上映”更新为“待订阅”。")
        else:
            logger.trace("  ➜ 没有需要晋升状态的媒体项。")

        wanted_items = media_db.get_all_wanted_media()
        if not wanted_items:
            logger.info("  ➜ 待订阅列表为空，无需处理。")
            task_manager.update_status_from_thread(100, "待订阅列表为空。")
            return

        logger.info(f"  ➜ 发现 {len(wanted_items)} 个待处理的订阅请求。")
        task_manager.update_status_from_thread(10, f"发现 {len(wanted_items)} 个待处理请求...")

        tmdb_api_key = config.get(constants.CONFIG_OPTION_TMDB_API_KEY)
        subscription_details = []
        rejected_details = []
        notifications_to_send = {}
        failed_notifications_to_send = {}
        quota_exhausted = False

        # 2. 遍历待办列表，逐一处理
        for i, item in enumerate(wanted_items):
            if processor.is_stop_requested(): break

            task_manager.update_status_from_thread(
                int(10 + (i / len(wanted_items)) * 85),
                f"({i+1}/{len(wanted_items)}) 正在处理: {item['title']}"
            )

            # ★★★ 1. 准备基础信息 (提前获取剧集标题，用于日志和搜索) ★★★
            subscription_status = str(item.get('subscription_status') or 'NONE').strip().upper()
            is_wanted_subscription = subscription_status == 'WANTED'
            is_subscribed_recheck = subscription_status == 'SUBSCRIBED'
            missing_episode_numbers = _normalize_missing_episode_numbers(item.get('missing_episode_numbers'))

            tmdb_id = item['tmdb_id']
            item_type = item['item_type']
            title = item['title'] # 默认为 item 标题
            season_number = item.get('season_number')

            # 2.1 发行日期保护只属于 WANTED 新订阅。
            # 非 WANTED 的电影/追更补库项不再做发行日期检查，避免统一订阅日志被补库项刷屏。
            if is_wanted_subscription and item_type == 'Movie' and not is_movie_subscribable(int(tmdb_id), tmdb_api_key, config):
                logger.info(f"  ➜ 电影《{title}》未到发行日期，本次跳过。")
                rejected_details.append({'item': f"电影《{title}》", 'reason': '未发行'})
                # ★★★ 新增：解析来源并记录失败通知 ★★★
                sources = item.get('subscription_sources_json', [])
                for source in sources:
                    if source.get('type') == 'user_request' and (user_id := source.get('user_id')):
                        if user_id not in failed_notifications_to_send:
                            failed_notifications_to_send[user_id] = []
                        failed_notifications_to_send[user_id].append(f"《{title}》(原因: 不满足发行日期延迟订阅)")
                continue

            # 统一订阅任务不再处理 Episode 队列项。
            # 单集只作为 Season.missing_episode_numbers 参与本地精确过滤；
            # 共享中心已经改为入池广播，不再登记客户端缺口；统一订阅只按 Season 粒度查询/消费已有资源。
            if item_type == 'Episode':
                logger.warning(
                    f"  ➜ [队列保护] 《{title}》仍以 Episode 进入统一订阅队列，已跳过；"
                    f"请检查 database.media_db.get_all_wanted_media 是否已应用季粒度补丁。"
                )
                continue

            item_year = ''
            for _year_key in ('release_date', 'first_air_date', 'air_date', 'year'):
                _year_value = item.get(_year_key)
                if _year_value:
                    _match = re.search(r'((?:19|20)\d{2})', str(_year_value))
                    if _match:
                        item_year = _match.group(1)
                        break
            if not item_year:
                _match = re.search(r'\(((?:19|20)\d{2})\)', str(item.get('title') or ''))
                if _match:
                    item_year = _match.group(1)
            parent_tmdb_id = None

            # 如果是剧/季/集，统一修正父剧 ID 与标题。
            # Episode 也必须走这里：共享中心的单集消费以“父剧 TMDb + SxxEyy”为主键。
            if item_type in ['Series', 'Season', 'Episode']:
                if item_type == 'Season':
                    parent_tmdb_id = item.get('parent_series_tmdb_id') or item.get('series_tmdb_id')
                    # 尝试解析 ID
                    if not parent_tmdb_id and '_' in str(tmdb_id):
                        parent_tmdb_id = str(tmdb_id).split('_')[0]
                    if not parent_tmdb_id:
                        parent_tmdb_id = tmdb_id
                elif item_type == 'Episode':
                    parent_tmdb_id = item.get('parent_series_tmdb_id') or item.get('series_tmdb_id')
                    # 极少数历史占位 ID 可能是 124364_S4E6 / 124364_E6 这类，兜底拆出父剧 ID。
                    if not parent_tmdb_id and '_' in str(tmdb_id):
                        parent_tmdb_id = str(tmdb_id).split('_')[0]
                    # Episode 的 tmdb_id 可能是“集自身 ID”，不能盲目当父剧 ID。
                else:
                    parent_tmdb_id = tmdb_id

                # 获取剧集名称
                series_name = media_db.get_series_title_by_tmdb_id(parent_tmdb_id) if parent_tmdb_id else None
                if not series_name:
                     # 尝试从 item title 解析 (例如 "Breaking Bad - S1")
                     raw_title = item.get('title', '')
                     parsed_name, _ = parse_series_title_and_season(raw_title, tmdb_api_key)
                     series_name = parsed_name if parsed_name else raw_title

                # 更新 title 变量为剧集标题；Episode 日志补上 SxxEyy，避免只显示剧名看不出目标集。
                if series_name:
                    if item_type == 'Episode' and item.get('episode_number') is not None:
                        try:
                            title = f"{series_name} S{int(season_number or item.get('season_number') or 0):02d}E{int(item.get('episode_number')):02d}"
                        except Exception:
                            title = series_name
                    else:
                        title = series_name

            if (not is_wanted_subscription) and item_type == 'Season':
                logger.info(
                    f"  ➜ [追更模式] 《{title}》 第 {int(season_number or 0):02d} 季 "
                    f"缺失集: {missing_episode_numbers or '未知/按季处理'}"
                )

            # --- MoviePilot 订阅保护 ---
            # 只有 subscription_status=WANTED 的新请求才允许进入 MP 订阅链路。
            # SUBSCRIBED / NONE / PAUSED 等由追更或补库带进队列的项目，只能走共享池/云资源补库，
            # 不能因为不等于 SUBSCRIBED 就被误判为新订阅。
            if is_wanted_subscription and settings_db.get_subscription_quota() <= 0:
                quota_exhausted = True
                logger.warning(f"  ➜ 每日订阅配额已用尽，跳过待订阅项目《{title}》，继续处理非 MP 补库项。")
                continue

            # 提交 MP 订阅
            success = False
            action_type = "MP"
            watchlist_config = settings_db.get_setting('watchlist_config') or {}

            # ==========================================
            # 动态订阅源处理 (MP) - 已针对单 MP 订阅源优化
            # ==========================================
            raw_sources = strategy_config.get('subscription_sources') or []
            # 判断配置中是否启用了 mp 订阅
            use_mp = 'mp' in raw_sources if isinstance(raw_sources, list) else False

            if use_mp:
                if not is_wanted_subscription:
                    # 避免追更季/已订阅项重复投递 MP
                    logger.debug(f"  ➜ [MP保护] 跳过《{title}》的 MoviePilot 订阅（非 WANTED 状态）。")
                else:
                    # 仅在 WANTED 状态下执行 MP 订阅逻辑
                    if item_type == 'Movie':
                        logger.info(f"  ➜ 正在向 MoviePilot 提交电影《{title}》的订阅...")
                        mp_payload = {"name": title, "tmdbid": int(tmdb_id), "type": "电影"}
                        success = moviepilot.subscribe_with_custom_payload(mp_payload, config, consume_quota=True)
                        
                    elif item_type == 'Series':
                        success = _subscribe_full_series_with_logic(int(tmdb_id), title, config, tmdb_api_key, consume_quota=True)
                        
                    elif item_type == 'Episode':
                        logger.info(f"  ➜ 已跳过 MP 兜底。")
                        
                    elif item_type == 'Season' and parent_tmdb_id and season_number is not None:
                        mp_payload = {"name": title, "tmdbid": int(parent_tmdb_id), "type": "电视剧", "season": int(season_number)}

                        is_pending, fake_eps = should_mark_as_pending(int(parent_tmdb_id), int(season_number), tmdb_api_key)
                        is_completed = False

                        if not is_pending:
                            is_completed = check_series_completion(
                                int(parent_tmdb_id),
                                tmdb_api_key,
                                season_number=int(season_number),
                                series_name=title
                            )
                            wash_mode = _apply_watchlist_mp_wash_flags(
                                mp_payload,
                                watchlist_config,
                                force_full=is_completed
                            )
                            if is_completed:
                                logger.info(f"  ➜ 《{title}》S{season_number} 已完结，强制使用 {wash_mode} 订阅。")
                            else:
                                logger.info(f"  ➜ 《{title}》S{season_number} 未完结，向 MoviePilot 提交 {wash_mode} 订阅。")
                        else:
                            logger.info(f"  ➜ 《{title}》S{season_number} 处于待定模式，向 MoviePilot 提交补缺订阅。")

                        success = moviepilot.subscribe_with_custom_payload(mp_payload, config, consume_quota=True)
                        if success and is_pending:
                            moviepilot.update_subscription_status(int(parent_tmdb_id), int(season_number), 'P', config, total_episodes=fake_eps)

            # 处理订阅结果
            if success:
                if is_wanted_subscription:
                    logger.info(f"  ➜ 《{title}》订阅成功！")

                # WANTED 成功后更新为 SUBSCRIBED；SUBSCRIBED 补库成功只保持原状态，不能重复消耗订阅配额。
                # Series 走 MP 整剧逻辑时仍由 _subscribe_full_series_with_logic 内部逐季处理；
                if is_wanted_subscription and item_type != 'Series':
                    request_db.set_media_status_subscribed(
                        tmdb_ids=item['tmdb_id'],
                        item_type=item_type,
                    )

                # 准备通知 (智能拼接通知标题)
                item_display_name = ""
                if item_type == 'Season':
                    season_num = item.get('season_number')
                    if season_num is not None:
                        item_display_name = f"剧集《{series_name} 第 {season_num} 季》"
                    else:
                        item_display_name = f"剧集《{series_name}》"
                elif item_type == 'Episode':
                    try:
                        item_display_name = f"剧集《{series_name or title} S{int(item.get('season_number') or 0):02d}E{int(item.get('episode_number') or 0):02d}》"
                    except Exception:
                        item_display_name = f"单集《{item['title']}》"
                else:
                    item_display_name = f"{item_type}《{item['title']}》"

                # 解析订阅来源，找出需要通知的用户
                sources = item.get('subscription_sources_json', [])
                source_display_parts = []
                for source in sources:
                    source_type = source.get('type')
                    if source_type == 'resubscribe':
                        rule_name = telegram.escape_markdown(source.get('rule_name', '未知规则'))
                        source_display_parts.append(f"`[自动洗版]` \\({rule_name}\\)")
                    elif source_type == 'user_request' and (user_id := source.get('user_id')):
                        if user_id not in notifications_to_send:
                            notifications_to_send[user_id] = []

                        # 为用户通知构建完整的标题
                        user_notify_title = item['title']
                        if item_type == 'Season':
                            season_num = item.get('season_number')
                            if season_num is not None:
                                user_notify_title = f"{series_name} 第 {season_num} 季"

                        notifications_to_send[user_id].append(user_notify_title)
                        user_name = telegram.escape_markdown(user_db.get_username_by_id(user_id) or user_id)
                        source_display_parts.append(f"`[用户请求]` \\({user_name}\\)")
                    elif source_type == 'actor_subscription':
                        actor_name = telegram.escape_markdown(source.get('name', '未知'))
                        source_display_parts.append(f"`[演员订阅]` \\({actor_name}\\)")
                    elif source_type in ['custom_collection', 'native_collection']:
                        coll_name = telegram.escape_markdown(source.get('name', '未知'))
                        source_display_parts.append(f"`[合集]` \\({coll_name}\\)")
                    elif source_type == 'telegram_search':
                        tg_name = telegram.escape_markdown(source.get('name', '未知'))
                        source_display_parts.append(f"`[TG搜索]` \\({tg_name}\\)")
                    elif source_type == 'watchlist':
                        source_display_parts.append("`[追剧补全]`")

                source_display = " ".join(set(source_display_parts)) or "`[未知来源]`"
                subscription_details.append({'source': source_display, 'item': item_display_name, 'action': action_type})

            else:
                if is_wanted_subscription:
                    logger.error(f"  ➜ 订阅《{title}》失败，请检查 MoviePilot 连接或日志。")
            # 如果配置了延时，且不是列表中的最后一个项目，则进行休眠
            if request_delay > 0 and i < len(wanted_items) - 1:
                logger.debug(f"  ➜ 根据配置暂停 {request_delay} 秒...")
                time.sleep(request_delay)

        # 发送用户通知
        logger.info(f"  ➜ 准备为 {len(notifications_to_send)} 位用户发送合并的成功通知...")
        for user_id, subscribed_items in notifications_to_send.items():
            try:
                user_chat_id = user_db.get_user_telegram_chat_id(user_id)
                if user_chat_id:
                    items_list_str = "\n".join([f"· `{telegram._markdown_code_text(item)}`" for item in subscribed_items])
                    message_text = (f"🎉 *您的 {len(subscribed_items)} 个订阅已成功处理*\n\n您之前想看的下列内容现已加入下载队列：\n{items_list_str}")
                    telegram.send_telegram_message(user_chat_id, message_text)
            except Exception as e:
                logger.error(f"  ➜ 为用户 {user_id} 发送自动订阅的合并通知时出错: {e}")

        # 失败的通知
        logger.info(f"  ➜ 准备为 {len(failed_notifications_to_send)} 位用户发送合并的失败通知...")
        for user_id, failed_items in failed_notifications_to_send.items():
            try:
                user_chat_id = user_db.get_user_telegram_chat_id(user_id)
                if user_chat_id:
                    items_list_str = "\n".join([f"· `{telegram._markdown_code_text(item)}`" for item in failed_items])
                    message_text = (f"➜ *您的部分订阅请求未被处理*\n\n下列内容因不满足条件而被跳过：\n{items_list_str}")
                    telegram.send_telegram_message(user_chat_id, message_text)
            except Exception as e:
                logger.error(f"为用户 {user_id} 发送自动订阅的合并失败通知时出错: {e}")

        if subscription_details:
            header = f"  ✅ *统一订阅任务完成，成功处理 {len(subscription_details)} 项:*"

            item_lines = []
            for detail in subscription_details:
                source = detail.get('source', '`[未知来源]`')
                item = telegram.escape_markdown(detail['item'])
                
                action_tag = "TG搜索" if detail.get('action') == 'TG搜索' else "MP订阅"
                
                # 直接拼接 source，因为上面已经提前做好了 Markdown 格式化和转义
                item_lines.append(f"├─ `[{action_tag}]` {source} {item}")

            summary_message = header + "\n" + "\n".join(item_lines)
        else:
            summary_message = "ℹ️ *统一订阅任务完成，无成功处理的订阅项。*"

        if rejected_details:
            rejected_header = f"\n\n➜ *下列 {len(rejected_details)} 项因不满足订阅条件而被跳过:*"

            rejected_lines = []
            for detail in rejected_details:
                reason = telegram.escape_markdown(detail.get('reason', '未知原因'))
                item = telegram.escape_markdown(detail['item'])
                rejected_lines.append(f"├─ `{reason}` {item}")

            summary_message += rejected_header + "\n" + "\n".join(rejected_lines)

        if quota_exhausted:
            content = "(每日订阅配额已用尽，部分项目可能未处理)"
            escaped_content = telegram.escape_markdown(content)
            summary_message += f"\n\n*{escaped_content}*"

        # 打印日志和发送通知的逻辑保持不变
        logger.info(summary_message.replace('*', '').replace('`', ''))
        admin_chat_ids = user_db.get_admin_telegram_chat_ids()
        if admin_chat_ids:
            logger.info(f"  ➜ 准备向 {len(admin_chat_ids)} 位管理员发送任务总结...")
            for chat_id in admin_chat_ids:
                # 发送通知，静默模式，避免打扰
                telegram.send_telegram_message(chat_id, summary_message, disable_notification=True)

        task_manager.update_status_from_thread(100, "统一订阅任务处理完成。")
        logger.info(f"--- '{task_name}' 任务执行完毕 ---")

    except Exception as e:
        logger.error(f"  ➜ {task_name} 任务失败: {e}", exc_info=True)
        task_manager.update_status_from_thread(-1, f"错误: {e}")
