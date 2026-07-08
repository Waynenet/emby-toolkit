# 文件: handler/telegram.py
import json
import threading
import extensions
import requests
import time
import logging
import ipaddress
import urllib.parse
import re
from datetime import datetime
from config_manager import APP_CONFIG, get_proxies_for_requests
from handler.emby import get_emby_item_details
from database import user_db, request_db, media_db
from database.connection import get_db_connection
import constants

logger = logging.getLogger(__name__)

def _format_episode_ranges(episode_list: list) -> str:
    """
    辅助函数：将 [(season, episode), ...] 转换为易读的范围字符串。
    输入: [(1, 1), (1, 2), (1, 3), (1, 5)]
    输出: "S01E01-E03, S01E05"
    """
    if not episode_list:
        return ""
    
    # 1. 按季分组
    season_map = {}
    for s, e in episode_list:
        season_map.setdefault(s, []).append(e)
    
    final_parts = []
    
    # 2. 按季排序处理
    for season in sorted(season_map.keys()):
        episodes = sorted(list(set(season_map[season]))) # 去重并排序
        if not episodes: continue
        
        # 3. 查找连续区间
        ranges = []
        start = episodes[0]
        prev = episodes[0]
        
        for ep in episodes[1:]:
            if ep == prev + 1:
                prev = ep
            else:
                # 结算上一段
                if start == prev:
                    ranges.append(f"E{start:02d}")
                else:
                    ranges.append(f"E{start:02d}-E{prev:02d}")
                start = ep
                prev = ep
        
        # 结算最后一段
        if start == prev:
            ranges.append(f"E{start:02d}")
        else:
            ranges.append(f"E{start:02d}-E{prev:02d}")
        
        # 4. 组装当前季的字符串
        for r in ranges:
            final_parts.append(f"S{season:02d}{r}")
            
    return ", ".join(final_parts)

def escape_markdown(text: str) -> str:
    """
    Helper function to escape characters for Telegram's MarkdownV2.
    只应该用于转义从外部API获取的、内容不可控的文本部分。
    """
    if not isinstance(text, str):
        return ""
    # 根据 Telegram Bot API 文档，这些字符需要转义: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

def _format_ticks_to_time(ticks: int) -> str:
    """辅助函数：将 Emby 的 Ticks (1 tick = 100 ns) 转换为 HH:MM:SS 或 MM:SS 格式"""
    if not ticks or ticks <= 0:
        return "00:00"
    seconds = int(ticks / 10000000)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def _translate_to_chinese(text: str) -> str:
    """利用 Google Translate 免费接口将英文地理位置翻译为中文"""
    if not text:
        return ""
    try:
        encoded_text = urllib.parse.quote(text)
        # 使用 gtx 客户端可免 Key 调用
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q={encoded_text}"
        proxies = get_proxies_for_requests()
        response = requests.get(url, timeout=3, proxies=proxies)
        if response.status_code == 200:
            data = response.json()
            # 拼接翻译结果（应对多段句子）
            translated = "".join([sentence[0] for sentence in data[0]])
            return translated
    except Exception as e:
        logger.debug(f"  ➜ 地理位置翻译失败 '{text}': {e}")
    return text

def _get_ip_location(clean_ip: str) -> str:
    """请求 IP.SB 接口获取 IP 的物理地理位置并翻译为中文"""
    if not clean_ip:
        return ""

    try:
        # 优先判断是否为内网 IP，节省 API 请求
        ip_obj = ipaddress.ip_address(clean_ip)
        if ip_obj.is_private or ip_obj.is_loopback:
            return "本地局域网"
    except ValueError:
        pass 

    try:
        url = f"https://api.ip.sb/geoip/{clean_ip}"
        headers = {"User-Agent": "Mozilla/5.0"}
        proxies = get_proxies_for_requests()
        response = requests.get(url, headers=headers, timeout=5, proxies=proxies)
        
        if response.status_code == 200:
            data = response.json()
            country = data.get('country', '')
            region = data.get('region', '')
            city = data.get('city', '')
            isp = data.get('organization', '')
            
            # 组装地理位置并去重
            loc_parts = []
            for loc in [country, region, city]:
                if loc and loc not in loc_parts:
                    loc_parts.append(loc)
            
            final_str = ""
            if loc_parts:
                english_loc = ", ".join(loc_parts)
                # 将英文的 国家,省份,城市 翻译为中文
                chinese_loc = _translate_to_chinese(english_loc)
                # 清理翻译后可能出现的逗号，让格式更紧凑
                chinese_loc = chinese_loc.replace(", ", " ").replace("，", " ")
                final_str += chinese_loc
            
            if isp:
                # 去掉 ISP 字符串开头可能附带的 ASN 号 (如 "AS13335 Cloudflare, Inc." -> "Cloudflare, Inc.")
                isp_clean = re.sub(r'^AS\d+\s+', '', isp)
                if final_str:
                    final_str += f" ({isp_clean})"
                else:
                    final_str = isp_clean
                    
            return final_str
    except Exception as e:
        logger.debug(f"  ➜ IP.SB 归属地查询失败 ({clean_ip}): {e}")
        
    return ""

def _markdown_code_text(text) -> str:
    """MarkdownV2 code span 内只需要处理反斜杠和反引号。"""
    return str(text or '').replace('\\', '\\\\').replace('`', '\\`')


def _format_size_for_notice(size_bytes) -> str:
    try:
        size = float(size_bytes or 0)
    except Exception:
        return ''
    if size <= 0:
        return ''
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if units[idx] in {'GB', 'TB'}:
        return f"{size:.1f}{units[idx]}" if size < 100 else f"{size:.0f}{units[idx]}"
    if units[idx] == 'MB':
        return f"{size:.0f}MB"
    return f"{int(size)}{units[idx]}"


def _notice_asset_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _load_notice_asset_details_by_emby_id(emby_item_id: str) -> list:
    """从 media_metadata.asset_details_json 读取通知参数，不再重新查 Emby MediaSources。"""
    emby_item_id = str(emby_item_id or '').strip()
    if not emby_item_id:
        return []

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT asset_details_json, washing_level
                    FROM media_metadata
                    WHERE asset_details_json IS NOT NULL
                      AND (
                          emby_item_ids_json @> %s::jsonb
                          OR asset_details_json @> %s::jsonb
                      )
                    ORDER BY
                        CASE item_type
                            WHEN 'Episode' THEN 0
                            WHEN 'Movie' THEN 1
                            WHEN 'Season' THEN 2
                            WHEN 'Series' THEN 3
                            ELSE 9
                        END,
                        in_library DESC,
                        date_added DESC NULLS LAST
                    LIMIT 1
                    """,
                    (
                        json.dumps([emby_item_id], ensure_ascii=False),
                        json.dumps([{'emby_item_id': emby_item_id}], ensure_ascii=False),
                    ),
                )
                row = cursor.fetchone()
    except Exception as e:
        logger.warning(f"  ➜ [通知] 查询 asset_details_json 失败: emby_item_id={emby_item_id}, err={e}")
        return []

    if not row:
        return []

    row_data = dict(row)
    assets = _notice_asset_list(row_data.get('asset_details_json'))
    if not assets:
        return []

    # 一条剧集/季记录里可能有多个 asset，优先只取当前 Emby Item 对应的那一个。
    matched = [item for item in assets if str(item.get('emby_item_id') or '').strip() == emby_item_id]
    selected = matched or assets
    for asset in selected:
        asset['_notice_washing_level'] = row_data.get('washing_level')
    return selected


def _notice_asset_value(asset: dict, *keys) -> str:
    for key in keys:
        value = (asset or {}).get(key)
        if value not in (None, ''):
            return str(value).strip()
    return ''


def _notice_asset_size(asset: dict) -> int:
    value = (asset or {}).get('size_bytes')
    if value in (None, ''):
        value = (asset or {}).get('size') or (asset or {}).get('file_size')
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _notice_asset_resolution(asset: dict) -> str:
    resolution = _notice_asset_value(asset, 'resolution_display')
    width = (asset or {}).get('width')
    height = (asset or {}).get('height')
    try:
        width = int(width or 0)
        height = int(height or 0)
    except Exception:
        width, height = 0, 0
    dimension = f"{width}x{height}" if width and height else ''
    if resolution and dimension and dimension not in resolution:
        return f"{resolution} / {dimension}"
    return resolution or dimension


def _notice_join_unique(values, limit: int = 4) -> str:
    out = []
    for value in values or []:
        value = str(value or '').strip()
        if value and value not in out:
            out.append(value)
    if not out:
        return ''
    text = ' / '.join(out[:limit])
    if len(out) > limit:
        text += f" 等{len(out)}种"
    return text


def _notice_asset_washing_level(asset: dict):
    try:
        return int((asset or {}).get('_notice_washing_level'))
    except Exception:
        return None


def _build_notice_washing_text(assets: list) -> str:
    levels = sorted({
        level
        for level in (_notice_asset_washing_level(asset) for asset in assets)
        if level is not None
    })
    if not levels:
        return ''

    def comment_for_level(level: int) -> str:
        if level == 1:
            return "最佳版本"
        if level == 2:
            return "差点意思"
        if level == 3:
            return "凑合看吧"
        return "太烂了"

    level_text = ' / '.join(f"P{level} {comment_for_level(level)}" for level in levels)
    label = f"🏆 *洗版优先级*: `{_markdown_code_text(level_text)}`"
    return label


def _build_notice_asset_params_text(emby_item_ids: list) -> str:
    """生成入库/追更通知参数，数据源固定为 media_metadata.asset_details_json。"""
    assets = []
    seen = set()
    for emby_item_id in emby_item_ids or []:
        for asset in _load_notice_asset_details_by_emby_id(emby_item_id):
            key = str(asset.get('emby_item_id') or '') or str(asset.get('path') or '')
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            assets.append(asset)

    if not assets:
        return ''

    quality = _notice_join_unique(_notice_asset_value(a, 'quality_display') for a in assets)
    resolution = _notice_join_unique(_notice_asset_resolution(a) for a in assets)
    codec = _notice_join_unique(_notice_asset_value(a, 'codec_display', 'video_codec') for a in assets)
    effect = _notice_join_unique(_notice_asset_value(a, 'effect_display') for a in assets)
    audio = _notice_join_unique(_notice_asset_value(a, 'audio_display') for a in assets)
    subtitle = _notice_join_unique(_notice_asset_value(a, 'subtitle_display') for a in assets)

    total_size = sum(_notice_asset_size(a) for a in assets)
    file_count = len(assets)

    lines = []
    washing_text = _build_notice_washing_text(assets)
    if washing_text:
        lines.append(washing_text)

    quality_parts = [part for part in (quality, resolution, codec) if part]
    if quality_parts:
        lines.append(f"🎞️ *画质*: `{_markdown_code_text(' / '.join(quality_parts))}`")
    if effect:
        lines.append(f"🌈 *格式*: `{_markdown_code_text(effect)}`")

    size_text = _format_size_for_notice(total_size)
    if size_text:
        if file_count > 1:
            size_text = f"{size_text}（{file_count}个文件）"
        lines.append(f"💾 *体积*: `{_markdown_code_text(size_text)}`")

    if audio:
        lines.append(f"🎧 *音轨*: `{_markdown_code_text(audio)}`")
    if subtitle:
        lines.append(f"💬 *字幕*: `{_markdown_code_text(subtitle)}`")

    return ('\n'.join(lines) + '\n') if lines else ''

# --- 通用的 Telegram 文本消息发送函数 ---
def send_telegram_message(chat_id: str, text: str, disable_notification: bool = False, reply_markup: dict = None):
    """通用的 Telegram 文本消息发送函数，支持内联键盘。"""
    bot_token = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_BOT_TOKEN)
    if not bot_token or not chat_id:
        return False
    
    final_chat_id = str(chat_id).strip()
    if final_chat_id.startswith('https://t.me/'):
        username = final_chat_id.split('/')[-1]
        if username:
            final_chat_id = f'@{username}'

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': final_chat_id,
        'text': text, 
        'parse_mode': 'MarkdownV2',
        'disable_web_page_preview': True,
        'disable_notification': disable_notification,
    }
    
    # 支持传入键盘标记
    if reply_markup:
        payload['reply_markup'] = reply_markup

    try:
        proxies = get_proxies_for_requests()
        response = requests.post(api_url, json=payload, timeout=15, proxies=proxies)
        if response.status_code == 200:
            logger.info(f"  ➜ 成功发送 Telegram 文本消息至 Chat ID: {final_chat_id}")
            return True
        else:
            logger.error(f"  ➜ 发送 Telegram 文本消息失败, 状态码: {response.status_code}, 响应: {response.text}")
            return False
    except requests.RequestException as e:
        logger.error(f"  ➜ 发送 Telegram 文本消息时发生网络请求错误: {e}")
        return False

def send_telegram_photo(chat_id: str, photo_url: str, caption: str, disable_notification: bool = False, reply_markup: dict = None):
    """支持内联键盘的图文消息发送"""
    bot_token = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_BOT_TOKEN)
    if not bot_token or not chat_id or not photo_url:
        return False
    
    final_chat_id = str(chat_id).strip()
    if final_chat_id.startswith('https://t.me/'):
        username = final_chat_id.split('/')[-1]
        if username:
            final_chat_id = f'@{username}'

    api_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    payload = {
        'chat_id': final_chat_id,
        'photo': photo_url,
        'caption': caption, 
        'parse_mode': 'MarkdownV2',
        'disable_notification': disable_notification,
    }
    
    if reply_markup:
        payload['reply_markup'] = reply_markup

    try:
        proxies = get_proxies_for_requests()
        response = requests.post(api_url, json=payload, timeout=30, proxies=proxies)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"  ➜ 发送 Telegram 图文消息失败, 状态码: {response.status_code}, 响应: {response.text}")
            return False
    except requests.RequestException as e:
        logger.error(f"  ➜ 发送 Telegram 图文消息时发生网络请求错误: {e}")
        return False
    
# --- 全能的通知函数 ---
def send_media_notification(item_details: dict, notification_type: str = 'new', new_episode_ids: list = None):
    """
    【全能媒体通知函数】
    根据传入的媒体详情，自动获取图片、组装消息并发送给频道和订阅者。
    """
    logger.info(f"  ➜ 准备为 '{item_details.get('Name')}' 发送 '{notification_type}' 类型的 Telegram 通知...")
    
    try:
        # --- 1. 准备基础信息 ---
        tmdb_id = item_details.get("ProviderIds", {}).get("Tmdb")
        item_id = item_details.get("Id")
        item_name_for_log = item_details.get("Name", f"ID:{item_id}")
        year = item_details.get("ProductionYear", "")
        title = f"{item_name_for_log} ({year})" if year else item_name_for_log
        overview = item_details.get("Overview", "暂无剧情简介。")
        if len(overview) > 200:
            overview = overview[:200] + "..."
            
        item_type = item_details.get("Type")
        escaped_title = escape_markdown(title)
        escaped_overview = escape_markdown(overview)

        # --- 2. 准备剧集信息 + 媒体参数 ---
        # 媒体参数不再临时查 Emby MediaSources，直接读取 process_single_item 已写入的
        # media_metadata.asset_details_json，避免重复请求和字段口径不一致。
        episode_info_text = ""
        notice_emby_item_ids = []
        if item_type == "Series" and new_episode_ids:
            emby_url = APP_CONFIG.get(constants.CONFIG_OPTION_EMBY_SERVER_URL)
            api_key = APP_CONFIG.get(constants.CONFIG_OPTION_EMBY_API_KEY)
            user_id = APP_CONFIG.get(constants.CONFIG_OPTION_EMBY_USER_ID)

            # 收集原始数据而不是直接格式化字符串，这样我们可以在格式化字符串时使用
            raw_episodes = [] 
            for ep_id in new_episode_ids:
                detail = get_emby_item_details(ep_id, emby_url, api_key, user_id, fields="IndexNumber,ParentIndexNumber")
                if detail:
                    season_num = detail.get("ParentIndexNumber", 0)
                    episode_num = detail.get("IndexNumber", 0)
                    raw_episodes.append((season_num, episode_num))
                notice_emby_item_ids.append(str(ep_id))
            
            if raw_episodes:
                formatted_episodes = _format_episode_ranges(raw_episodes)
                episode_info_text = f"🎞️ *集数*: `{formatted_episodes}`\n"
        elif item_id:
            notice_emby_item_ids.append(str(item_id))

        media_param_text = _build_notice_asset_params_text(notice_emby_item_ids)

        # --- 3. 调用本地数据库获取图片路径 ---
        photo_url = None
        try:
            db_info = media_db.get_notification_media_info_by_emby_id(item_id)
            if db_info:
                path = db_info.get('backdrop_path') or db_info.get('poster_path')
                if not path and db_info.get('item_type') == 'Episode':
                    path = db_info.get('parent_backdrop_path') or db_info.get('parent_poster_path')
                if path:
                    photo_url = f"https://image.tmdb.org/t/p/w780{path}"
        except Exception as e:
            pass

        # =================================================================
        # ★★★ 查询该项目是否被标记为【待复核】 ★★★
        # =================================================================
        needs_review = False
        review_reason = ""
        try:
            # 核心处理器中，分集的报错是挂在父剧集 ID 下的，所以这里要做个转换
            check_id = str(item_id)
            if item_type == 'Episode' and item_details.get('SeriesId'):
                check_id = str(item_details.get('SeriesId'))

            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT reason FROM failed_log WHERE item_id = %s", (check_id,))
                    row = cursor.fetchone()
                    if row:
                        needs_review = True
                        review_reason = row['reason']
        except Exception:
            pass
        
        notification_title_map = {'new': '✨ 入库成功', 'update': '🔄 已更新'}
        notification_title = notification_title_map.get(notification_type, '🔔 状态更新')
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        media_icon = "🎬" if item_type == "Movie" else "📺"

        review_warning = ""
        if needs_review:
            escaped_reason = escape_markdown(review_reason)
            review_warning = (f"\n\n⚠️ *系统提示*: 本次处理被标记为【待复核】\n"
                              f"🔍 *原因*: {escaped_reason}\n💡 _请前往 WebUI 手动介入处理_")

        caption = (f"{media_icon} *{escaped_title}* {notification_title}\n\n"
                   f"{episode_info_text}{media_param_text}⏰ *时间*: `{current_time}`\n📝 *剧情*: {escaped_overview}{review_warning}")
        
        subscribers = request_db.get_subscribers_by_tmdb_id(tmdb_id, item_type) if tmdb_id else []
        subscriber_chat_ids = {
            user_db.get_user_telegram_chat_id(sub.get('user_id')) 
            for sub in subscribers if sub.get('type') == 'user_request' and sub.get('user_id')
        }
        subscriber_chat_ids = {chat_id for chat_id in subscriber_chat_ids if chat_id}

        global_channel_id = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_CHANNEL_ID)
        notify_types = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_NOTIFY_TYPES, constants.DEFAULT_TELEGRAM_NOTIFY_TYPES)
        
        if 'library_new' in notify_types:
            if global_channel_id:
                if photo_url:
                    send_telegram_photo(global_channel_id, photo_url, caption)
                else:
                    send_telegram_message(global_channel_id, caption)

            all_admin_chat_ids = set(user_db.get_admin_telegram_chat_ids())
            if all_admin_chat_ids:
                subscriber_id_set = {str(sid) for sid in subscriber_chat_ids}
                for admin_chat_id in all_admin_chat_ids:
                    if str(admin_chat_id) == str(global_channel_id) or str(admin_chat_id) in subscriber_id_set:
                        continue
                    if photo_url:
                        send_telegram_photo(admin_chat_id, photo_url, caption)
                    else:
                        send_telegram_message(admin_chat_id, caption)

        if subscriber_chat_ids:
            personal_caption_map = {
                'new': f"✅ *您的订阅已入库*\n\n{caption}",
                'update': f"🔄 *您的订阅已更新*\n\n{caption}"
            }
            personal_caption = personal_caption_map.get(notification_type, caption)
            
            for chat_id in subscriber_chat_ids:
                if chat_id == global_channel_id: continue
                if photo_url:
                    send_telegram_photo(chat_id, photo_url, personal_caption)
                else:
                    send_telegram_message(chat_id, personal_caption)
            
    except Exception as e:
        logger.error(f"  ➜ 发送媒体通知时发生严重错误: {e}", exc_info=True)

# --- 用于记录最后一次播放状态，防止 Emby 心跳包刷屏 ---
_last_playback_events = {}

def send_playback_notification(data: dict):
    global _last_playback_events
    try:
        event_type = data.get("Event")
        user_name = data.get("User", {}).get("Name", "未知用户")
        session_info = data.get("Session", {})
        device_name = session_info.get("DeviceName", "未知设备")
        client_name = session_info.get("Client", "未知客户端")
        ip_address_raw = session_info.get("RemoteEndPoint", "未知 IP")
        
        item = data.get("Item", {})
        original_item_name = item.get("Name", "未知项目")
        original_item_type = item.get("Type", "Unknown")
        item_id = item.get("Id")

        # ====================================================
        # ★★★ 新增：播放状态去重拦截逻辑 ★★★
        # ====================================================
        if event_type and item_id:
            current_time = time.time()
            # 依据 用户+设备+媒体ID 生成唯一标识
            stream_key = f"{user_name}_{device_name}_{item_id}"
            last_event, last_time = _last_playback_events.get(stream_key, (None, 0))
            
            # 如果当前状态和上一次完全一样，并且间隔在 5 分钟内，说明是重复的心跳包，直接拦截！
            if event_type == last_event and (current_time - last_time) < 300:
                logger.debug(f"  ➜ 忽略 Emby 重复的播放状态心跳包: {event_type} ({stream_key})")
                # 更新心跳时间，但保持静默
                _last_playback_events[stream_key] = (event_type, current_time)
                return
            
            # 状态发生了改变（比如 播放->暂停，或 暂停->播放），更新记录并放行通知
            _last_playback_events[stream_key] = (event_type, current_time)
            
            # 顺手清理一下过期的记录（超过1小时的），防止内存无限积压
            keys_to_delete = [k for k, v in _last_playback_events.items() if current_time - v[1] > 3600]
            for k in keys_to_delete:
                del _last_playback_events[k]
        # ====================================================
        
        sxe_string = ""
        if original_item_type == "Episode":
            season_num = item.get("ParentIndexNumber")
            episode_num = item.get("IndexNumber")
            if season_num is not None and episode_num is not None:
                sxe_string = f" S{int(season_num):02d}E{int(episode_num):02d}"

        display_item_name = original_item_name
        if original_item_type == "Episode" and item.get("SeriesName"):
            display_item_name = f"{item.get('SeriesName')}{sxe_string} - {original_item_name}"
            
        progress_text = ""
        playback_info = data.get("PlaybackInfo", {})
        if playback_info:
            position_ticks = playback_info.get("PositionTicks", 0)
            runtime_ticks = item.get("RunTimeTicks", 0)
            if runtime_ticks > 0:
                pos_str = _format_ticks_to_time(position_ticks)
                total_str = _format_ticks_to_time(runtime_ticks)
                percentage = min((position_ticks / runtime_ticks) * 100, 100.0)
                progress_text = f"⏳ *进度*: `{pos_str} / {total_str} ({percentage:.1f}%)`\n"
        
        ip_location = _get_ip_location(ip_address_raw)
        display_ip = f"`{escape_markdown(ip_address_raw)}`"
        if ip_location:
            display_ip += f" {escape_markdown(ip_location)}"

        raw_overview = item.get("Overview", "")
        photo_url = None
        if item_id:
            db_info = media_db.get_notification_media_info_by_emby_id(item_id)
            if db_info:
                path = db_info.get('backdrop_path') or db_info.get('poster_path')
                if not path and db_info.get('item_type') == 'Episode':
                    path = db_info.get('parent_backdrop_path') or db_info.get('parent_poster_path')
                if path:
                    photo_url = f"https://image.tmdb.org/t/p/w780{path}"
                if not raw_overview:
                    raw_overview = db_info.get('overview', '')
        
        overview_text = ""
        if raw_overview:
            if len(raw_overview) > 150:
                raw_overview = raw_overview[:150] + "..."
            overview_text = f"\n📝 *剧情*: {escape_markdown(raw_overview)}"
                    
        action_map = {
            "playback.start": "▶️ 开始播放",
            "playback.pause": "⏸ 暂停播放",
            "playback.unpause": "⏯ 恢复播放",
            "playback.stop": "⏹ 停止播放"
        }
        action_str = action_map.get(event_type, "🎬 播放状态改变")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        caption = (f"{action_str}\n\n👤 *用户*: `{escape_markdown(user_name)}`\n"
                   f"🎬 *媒体*: *{escape_markdown(display_item_name)}*\n{progress_text}"
                   f"📱 *设备*: `{escape_markdown(device_name)} ({escape_markdown(client_name)})`\n"
                   f"🌐 *地址*: {display_ip}\n🕒 *时间*: `{escape_markdown(current_time)}`{overview_text}")
        
        admin_ids = set(user_db.get_admin_telegram_chat_ids())
        targets = {str(aid) for aid in admin_ids if aid}

        if not targets:
            return

        for target in targets:
            if photo_url:
                send_telegram_photo(target, photo_url, caption)
            else:
                send_telegram_message(target, caption)
                
    except Exception as e:
        logger.error(f"  ➜ 组装/发送播放图文通知时发生异常: {e}", exc_info=True)

# ======================================================================
# ★★★ Telegram 机器人交互监听与搜索订阅功能 ★★★
# ======================================================================

_tg_polling_thread = None
_tg_polling_active = False

# 搜索会话缓存，用于临时保存用户的搜索结果
_tg_search_sessions = {}
_tg_search_lock = threading.Lock()
_TG_SEARCH_TTL = 15 * 60  # 缓存 15 分钟
_TG_SEARCH_LIMIT = 10

def _tg_get_tmdb_api_key() -> str:
    constant_names = ["CONFIG_OPTION_TMDB_API_KEY", "CONFIG_OPTION_TMDB_APIKEY", "CONFIG_OPTION_TMDB_KEY"]
    for name in constant_names:
        config_key = getattr(constants, name, None)
        if config_key and APP_CONFIG.get(config_key):
            return str(APP_CONFIG.get(config_key)).strip()
    return ""

def _tg_set_session(chat_id: str, results: list):
    with _tg_search_lock:
        _tg_search_sessions[str(chat_id)] = {
            "created_at": time.time(),
            "results": results
        }

def _tg_get_session(chat_id: str):
    with _tg_search_lock:
        session = _tg_search_sessions.get(str(chat_id))
        if session and (time.time() - session["created_at"]) < _TG_SEARCH_TTL:
            return session
        _tg_search_sessions.pop(str(chat_id), None)
        return None

def _tg_clear_session(chat_id: str):
    with _tg_search_lock:
        _tg_search_sessions.pop(str(chat_id), None)

def _tg_start_tmdb_search(chat_id: str, query: str):
    """发起 TMDb 搜索并显示列表"""
    query = str(query or "").strip()
    if not query:
        send_telegram_message(chat_id, escape_markdown("请输入要搜索的影视剧名称。"))
        return

    def run():
        try:
            api_key = _tg_get_tmdb_api_key()
            if not api_key:
                send_telegram_message(chat_id, escape_markdown("❌ 未配置 TMDb API Key，无法进行搜索。"))
                return

            send_telegram_message(chat_id, f"⏳ 正在搜索：*{escape_markdown(query)}*", disable_notification=True)
            from handler.tmdb import search_multi_media, search_media
            
            data = search_multi_media(query=query, api_key=api_key, page=1)
            results = (data or {}).get("results") or []

            if not results:
                movie_results = search_media(query=query, api_key=api_key, item_type="movie") or []
                tv_results = search_media(query=query, api_key=api_key, item_type="tv") or []
                for item in movie_results: item["media_type"] = "movie"
                for item in tv_results: item["media_type"] = "tv"
                results = movie_results + tv_results

            normalized_results = []
            seen = set()
            for item in results:
                media_type = item.get("media_type")
                tmdb_id = item.get("id")
                if media_type not in {"movie", "tv"} or not tmdb_id:
                    continue
                key = (media_type, str(tmdb_id))
                if key in seen:
                    continue
                seen.add(key)
                normalized_results.append(item)
                if len(normalized_results) >= _TG_SEARCH_LIMIT:
                    break

            if not normalized_results:
                _tg_clear_session(chat_id)
                send_telegram_message(chat_id, f"❌ 未搜索到关于 *{escape_markdown(query)}* 的结果。")
                return

            _tg_set_session(chat_id, normalized_results)

            lines = [f"🔎 搜索结果 \\| *{escape_markdown(query)}*\n━━━━━━━━━━━━━━\n请点击下方按钮查看详情：\n"]
            keyboard = []
            row = []
            for idx, item in enumerate(normalized_results, 1):
                m_type = "电影" if item.get("media_type") == "movie" else "剧集"
                title = item.get("title") or item.get("name") or "未知"
                date_text = item.get("release_date") or item.get("first_air_date") or ""
                year = str(date_text)[:4] if date_text else "未知"
                
                lines.append(f"{idx}\\. \\[{m_type}\\] {escape_markdown(title)} \\({escape_markdown(year)}\\)")
                
                row.append({"text": f"{idx:02d}", "callback_data": f"tg_tmdb:{idx}"})
                if len(row) == 5:
                    keyboard.append(row)
                    row = []
                    
            if row: keyboard.append(row)
            keyboard.append([{"text": "❌ 取消搜索", "callback_data": "tg_search_cancel"}])
            
            send_telegram_message(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": keyboard})

        except Exception as e:
            logger.error(f"  ➜ [TG搜索] 搜索失败: {e}", exc_info=True)
            send_telegram_message(chat_id, escape_markdown("❌ 搜索异常，请稍后再试。"))

    threading.Thread(target=run, name="TG_Search_TMDb", daemon=True).start()

def _tg_show_media_details(chat_id: str, selection_number: int):
    """显示选中的影视详情和订阅按钮"""
    session = _tg_get_session(chat_id)
    if not session:
        send_telegram_message(chat_id, escape_markdown("❌ 搜索结果已过期，请重新输入名称搜索。"))
        return

    results = session.get("results", [])
    if selection_number < 1 or selection_number > len(results):
        send_telegram_message(chat_id, escape_markdown("❌ 选择无效。"))
        return

    item = results[selection_number - 1]
    media_type = item.get("media_type", "movie")
    tmdb_id = item.get("id")
    title = item.get("title") or item.get("name") or "未知"
    date_text = item.get("release_date") or item.get("first_air_date") or ""
    year = str(date_text)[:4] if date_text else "未知"
    rating = item.get("vote_average", 0)
    overview = item.get("overview", "暂无简介。")
    poster_path = item.get("poster_path")
    
    if len(overview) > 300:
        overview = overview[:300] + "..."

    type_str = "🎬 电影" if media_type == "movie" else "📺 剧集"
    
    caption = (
        f"*{escape_markdown(title)}* \\({escape_markdown(year)}\\)\n\n"
        f"🆔 *TMDb*: `{tmdb_id}`\n"
        f"🎭 *类型*: {escape_markdown(type_str)}\n"
        f"⭐️ *评分*: {escape_markdown(f'{float(rating):.1f}')}\n\n"
        f"📝 *剧情*: {escape_markdown(overview)}"
    )

    reply_markup = {
        "inline_keyboard": [
            [{"text": "🔔 订阅该项目", "callback_data": f"tg_sub:{media_type}:{tmdb_id}"}],
            [{"text": "🔙 关闭", "callback_data": "tg_search_cancel"}]
        ]
    }

    if poster_path:
        photo_url = f"https://image.tmdb.org/t/p/w780{poster_path}"
        send_telegram_photo(chat_id, photo_url, caption, reply_markup=reply_markup)
    else:
        send_telegram_message(chat_id, caption, reply_markup=reply_markup)

def _tg_handle_subscribe(chat_id: str, media_type: str, tmdb_id: str):
    """处理用户点击订阅按钮"""
    # 这里用 escape_markdown 包装纯文本，防止里面所有的标点符号报错
    send_telegram_message(chat_id, escape_markdown("⏳ 正在提交订阅请求..."), disable_notification=True)
    _tg_clear_session(chat_id)

    def run():
        try:
            from tasks.helpers import process_subscription_items_and_update_db
            from handler.tmdb import get_tv_details
            
            api_key = _tg_get_tmdb_api_key()
            tmdb_items = []
            
            if media_type == "movie":
                tmdb_items.append({
                    'tmdb_id': tmdb_id,
                    'media_type': 'Movie',
                    'season': None
                })
            elif media_type == "tv":
                details = get_tv_details(tmdb_id, api_key)
                if details and 'seasons' in details:
                    for s in details['seasons']:
                        s_num = s.get('season_number')
                        if s_num is not None and s_num > 0:
                            tmdb_items.append({
                                'tmdb_id': tmdb_id,
                                'media_type': 'Series',
                                'season': s_num
                            })
                else:
                    tmdb_items.append({
                        'tmdb_id': tmdb_id,
                        'media_type': 'Series',
                        'season': 1
                    })

            if not tmdb_items:
                send_telegram_message(chat_id, escape_markdown("❌ 无法解析该项目的订阅信息。"))
                return

            # --- 新增：查询 TG ID 绑定的 Emby 用户名 ---
            emby_username = 'TG 搜索'  # 默认兜底名称
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT u.name 
                            FROM emby_users u
                            JOIN emby_users_extended e ON u.id = e.emby_user_id
                            WHERE e.telegram_chat_id = %s
                        """, (str(chat_id),))
                        row = cursor.fetchone()
                        if row and row.get('name'):
                            # 如果查到了绑定的用户，使用该用户名 (可按需加上 TG 后缀以作区分)
                            emby_username = f"{row['name']}" 
            except Exception as e:
                logger.error(f"  ➜ [TG交互] 查询 TG ID {chat_id} 绑定的 Emby 用户名失败: {e}")

            # 标记订阅来源，使用查询到的用户名
            subscription_source = {'type': 'telegram_search', 'user_id': chat_id, 'name': emby_username}
            
            processed_ids = process_subscription_items_and_update_db(
                tmdb_items=tmdb_items,
                tmdb_to_emby_item_map={}, 
                subscription_source=subscription_source,
                tmdb_api_key=api_key
            )
            
            if processed_ids:
                send_telegram_message(chat_id, f"✅ *订阅已提交！*\n系统将在后台自动监控并处理。")
            else:
                send_telegram_message(chat_id, f"⚠️ *请求已处理*\n\\(该项目可能已在库或已处于订阅状态\\)")

        except Exception as e:
            logger.error(f"  ➜ [TG交互] 提交订阅失败: {e}", exc_info=True)
            send_telegram_message(chat_id, escape_markdown("❌ 提交订阅异常：请查看系统日志。"))

    threading.Thread(target=run, name="TG_Resource_Subscribe", daemon=True).start()

def _execute_task_from_tg(chat_id: str, task_key: str):
    """在后台线程中执行选定的任务"""
    from tasks.core import get_task_registry
    registry = get_task_registry(context='all')
    task_info = registry.get(task_key)
    
    if not task_info:
        send_telegram_message(chat_id, escape_markdown("❌ 任务不存在或已失效。"))
        return

    task_function, task_description, processor_type = task_info[:3]
    
    # 获取对应的处理器实例
    target_processor = None
    if processor_type == 'media':
        target_processor = extensions.media_processor_instance
    elif processor_type == 'watchlist':
        target_processor = extensions.watchlist_processor_instance
    elif processor_type == 'actor':
        target_processor = extensions.actor_subscription_processor_instance

    if not target_processor:
        send_telegram_message(chat_id, escape_markdown(f"❌ 无法获取 {processor_type} 处理器实例。"))
        return

    send_telegram_message(chat_id, escape_markdown(f"🚀 任务已启动：*{task_description}*\n请在系统日志或任务中心查看进度。"))
    logger.info(f"  ➜ [TG交互] 管理员 {chat_id} 触发了任务: {task_description}")

    # 包装执行逻辑，处理特殊参数
    def run_wrapper():
        try:
            tasks_requiring_force_flag = ['role-translation', 'enrich-aliases', 'populate-metadata']
            if task_key in tasks_requiring_force_flag:
                task_function(target_processor, force_full_update=False)
            else:
                task_function(target_processor)
            
            send_telegram_message(chat_id, escape_markdown(f"✅ 任务执行完毕：*{task_description}*"))
        except Exception as e:
            logger.error(f"  ➜ TG触发任务 '{task_description}' 失败: {e}", exc_info=True)
            send_telegram_message(chat_id, escape_markdown(f"❌ 任务执行失败：*{task_description}*\n错误信息: {str(e)}"))

    # 启动独立线程执行任务，避免阻塞 TG 轮询
    threading.Thread(target=run_wrapper, name=f"TG_Task_{task_key}", daemon=True).start()

def _handle_callback_query(callback_query: dict):
    """处理内联键盘的按钮点击事件"""
    query_id = callback_query.get('id')
    from_user = callback_query.get('from', {})
    chat_id = str(from_user.get('id', ''))
    data = callback_query.get('data', '')
    bot_token = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_BOT_TOKEN)
    
    admin_ids = [str(aid) for aid in user_db.get_admin_telegram_chat_ids()]
    if chat_id not in admin_ids:
        logger.warning(f"  ➜ [TG交互] 收到未授权用户 ({chat_id}) 的回调请求，已拒绝。")
        return

    if bot_token and query_id:
        answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        try:
            requests.post(answer_url, json={'callback_query_id': query_id}, proxies=get_proxies_for_requests(), timeout=5)
        except Exception:
            pass

    # 1. 搜索取消
    if data == 'tg_search_cancel':
        _tg_clear_session(chat_id)
        send_telegram_message(chat_id, "✅ 已关闭窗口。")
        return

    # 2. 点击搜索结果选项展示详情
    if data.startswith('tg_tmdb:'):
        try:
            selection = int(data.split(':', 1)[1])
            _tg_show_media_details(chat_id, selection)
        except Exception as e:
            logger.error(f"  ➜ [TG交互] 处理详情查看失败: {e}")
        return

    # 3. 点击订阅按钮
    if data.startswith('tg_sub:'):
        try:
            parts = data.split(':')
            media_type = parts[1]
            tmdb_id = parts[2]
            _tg_handle_subscribe(chat_id, media_type, tmdb_id)
        except Exception as e:
            logger.error(f"  ➜ [TG交互] 处理订阅失败: {e}")
        return

    # 4. 执行系统任务
    if data.startswith('run_task_'):
        task_key = data.replace('run_task_', '')
        _execute_task_from_tg(chat_id, task_key)

def _handle_incoming_message(message: dict):
    """处理接收到的单条消息 (纯手动遥控器模式)"""
    chat_id = str(message.get('chat', {}).get('id', ''))
    text = message.get('text', '') or message.get('caption', '')
    text = text.strip()
    if not chat_id or not text:
        return

    admin_ids = [str(aid) for aid in user_db.get_admin_telegram_chat_ids()]
    global_channel = str(APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_CHANNEL_ID, ''))
    
    if chat_id not in admin_ids and chat_id != global_channel:
        logger.warning(f"  ➜ [TG交互] 收到未授权用户 ({chat_id}) 的消息，已忽略。")
        return

    if text.startswith('/'):
        cmd_body = text[1:].strip()
        cmd_token = cmd_body.split()[0].lower() if cmd_body else ''
        cmd = cmd_token.split('@', 1)[0]
        cmd_args = cmd_body[len(cmd_token):].strip() if cmd_token else ''
        
        # 搜索命令
        if cmd in ['search', 'find']:
            if not cmd_args:
                send_telegram_message(chat_id, "请输入要搜索的片名，例如：/search 阿凡达")
                return
            _tg_start_tmdb_search(chat_id, cmd_args)
            return

        from tasks.core import get_task_registry
        registry = get_task_registry(context='all')

        if cmd in ['all_tasks', 'tasks', 'menu']:
            keyboard = []
            row = []
            for key, info in registry.items():
                desc = info[1]
                row.append({"text": desc, "callback_data": f"run_task_{key}"})
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row: keyboard.append(row)
            reply_markup = {"inline_keyboard": keyboard}
            send_telegram_message(chat_id, escape_markdown("📋 *所有可用任务列表*\n请点击下方按钮执行对应任务："), reply_markup=reply_markup)
            return

        for key in registry.keys():
            expected_cmd = key.replace('-', '_').lower()
            if cmd == expected_cmd:
                _execute_task_from_tg(chat_id, key)
                return
        return

    # 若输入普通纯文本（不是命令，不是链接），直接视为搜索请求
    is_url = text.lower().startswith('http')
    is_magnet = text.lower().startswith('magnet:?')
    is_ed2k = text.lower().startswith('ed2k://')
    
    if not (is_url or is_magnet or is_ed2k):
        _tg_start_tmdb_search(chat_id, text)

def _setup_bot_commands(bot_token: str):
    """
    向 Telegram 注册机器人的命令菜单 (生成输入框左侧的 Menu 按钮)
    将常用任务直接注册为快捷命令。
    """
    from tasks.core import get_task_registry
    registry = get_task_registry(context='all')

    allowed_tasks = APP_CONFIG.get(
        constants.CONFIG_OPTION_TELEGRAM_MENU_TASKS, 
        constants.DEFAULT_TELEGRAM_MENU_TASKS
    )
    if not allowed_tasks:
        allowed_tasks = constants.DEFAULT_TELEGRAM_MENU_TASKS

    commands = []
    for key in allowed_tasks:
        if key in registry:
            desc = registry[key][1]
            cmd_name = key.replace('-', '_').lower()
            commands.append({"command": cmd_name, "description": f"🚀 {desc}"})

    commands.append({"command": "search", "description": "🔎 搜索并订阅影视剧"})
    commands.append({"command": "all_tasks", "description": "📋 查看所有可用任务"})

    api_url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
    payload = {"commands": commands}
    
    try:
        proxies = get_proxies_for_requests()
        response = requests.post(api_url, json=payload, timeout=10, proxies=proxies)
        if response.status_code == 200:
            logger.trace("  ➜ 成功注册 Telegram 机器人快捷菜单。")
    except Exception as e:
        logger.error(f"  ➜ 注册 Telegram 菜单命令时发生网络异常: {e}")

def _telegram_polling_worker():
    """后台轮询线程"""
    global _tg_polling_active
    bot_token = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_BOT_TOKEN)
    if not bot_token:
        logger.info("  ➜ 未配置 Telegram Bot Token，交互功能未启动。")
        return

    _setup_bot_commands(bot_token)
    api_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    offset = None
    logger.trace("  ➜ Telegram 机器人交互监听已启动！")
    
    while _tg_polling_active:
        try:
            params = {'timeout': 30, 'allowed_updates': ['message', 'callback_query']}
            if offset:
                params['offset'] = offset
                
            proxies = get_proxies_for_requests()
            response = requests.get(api_url, params=params, timeout=40, proxies=proxies)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    for update in data.get('result', []):
                        offset = update['update_id'] + 1
                        if 'message' in update:
                            _handle_incoming_message(update['message'])
                        elif 'callback_query' in update:
                            _handle_callback_query(update['callback_query'])
                            
            elif response.status_code == 401 or response.status_code == 404:
                break
                
        except requests.exceptions.Timeout:
            pass 
        except Exception:
            time.sleep(5) 
            
        time.sleep(1)

def start_telegram_bot():
    """启动 Telegram 机器人监听"""
    global _tg_polling_thread, _tg_polling_active
    if _tg_polling_active:
        return
    bot_token = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_BOT_TOKEN)
    if not bot_token:
        return
    _tg_polling_active = True
    _tg_polling_thread = threading.Thread(target=_telegram_polling_worker, daemon=True, name="TG_Polling_Thread")
    _tg_polling_thread.start()

def stop_telegram_bot():
    """停止 Telegram 机器人监听"""
    global _tg_polling_active
    _tg_polling_active = False
    logger.info("  ➜ Telegram 机器人交互监听已停止。")