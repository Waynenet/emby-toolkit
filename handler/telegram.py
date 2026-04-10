# 文件: handler/telegram.py
import json
import threading
import extensions
import requests
import logging
import ipaddress
from datetime import datetime
from config_manager import APP_CONFIG, get_proxies_for_requests
from database import media_db
from handler.emby import get_emby_item_details
from database import user_db, request_db
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

def _get_ip_location(ip_with_port: str) -> str:
    """辅助函数：请求外部接口获取 IP 的地理位置"""
    if not ip_with_port or ip_with_port == "未知 IP":
        return ""

    # 尝试剥离端口号 (兼容 IPv4: 1.1.1.1:1234, 和 IPv6: [2001::1]:1234)
    ip = ip_with_port
    if ']' in ip: 
        ip = ip.split(']')[0].replace('[', '')
    elif ':' in ip and ip.count(':') == 1: 
        ip = ip.split(':')[0]
        
    try:
        # 检查是否为局域网/回环 IP
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private or ip_obj.is_loopback:
            return "内网 / 局域网"
    except ValueError:
        pass # 格式不合法则继续往下走尝试查询

    try:
        # 请求免费的 IP 查询接口 (自带中文支持)
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
        proxies = get_proxies_for_requests()
        # 设定较短的超时时间，防止卡死
        response = requests.get(url, timeout=3, proxies=proxies)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                country = data.get('country', '')
                region = data.get('regionName', '')
                city = data.get('city', '')
                
                # 组装并去重 (例如有些直辖市省市同名: "中国 上海 上海" 变为 "中国 上海")
                parts = []
                for loc in [country, region, city]:
                    if loc and loc not in parts:
                        parts.append(loc)
                        
                if parts:
                    return " ".join(parts)
    except Exception as e:
        logger.debug(f"  ➜ 获取 IP 归属地失败 ({ip}): {e}")
        
    return ""

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

# --- 通用的 Telegram 图文消息发送函数 ---
def send_telegram_photo(chat_id: str, photo_url: str, caption: str, disable_notification: bool = False):
    """通用的 Telegram 图文消息发送函数。"""
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
    try:
        proxies = get_proxies_for_requests()
        response = requests.post(api_url, json=payload, timeout=30, proxies=proxies)
        if response.status_code == 200:
            logger.debug(f"  ➜ 成功发送 Telegram 图文消息至 Chat ID: {final_chat_id}")
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

        # --- 2. 准备剧集信息 (如果适用) ---
        episode_info_text = ""
        if item_type == "Series" and new_episode_ids:
            emby_url = APP_CONFIG.get(constants.CONFIG_OPTION_EMBY_SERVER_URL)
            api_key = APP_CONFIG.get(constants.CONFIG_OPTION_EMBY_API_KEY)
            user_id = APP_CONFIG.get(constants.CONFIG_OPTION_EMBY_USER_ID)

            # 收集原始数据而不是直接格式化字符串
            raw_episodes = [] 
            for ep_id in new_episode_ids:
                detail = get_emby_item_details(ep_id, emby_url, api_key, user_id, fields="IndexNumber,ParentIndexNumber")
                if detail:
                    season_num = detail.get("ParentIndexNumber", 0)
                    episode_num = detail.get("IndexNumber", 0)
                    raw_episodes.append((season_num, episode_num))
            
            if raw_episodes:
                formatted_episodes = _format_episode_ranges(raw_episodes)
                episode_info_text = f"🎞️ *集数*: `{formatted_episodes}`\n"

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
            logger.error(f"  ➜ [通知] 从本地数据库获取图片信息时出错: {e}", exc_info=True)
        
        # --- 4. 组装最终的通知文本 (Caption) ---
        notification_title_map = {
            'new': '✨ 入库成功',
            'update': '🔄 已更新'
        }
        notification_title = notification_title_map.get(notification_type, '🔔 状态更新')
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        media_icon = "🎬" if item_type == "Movie" else "📺"
        
        caption = (
            f"{media_icon} *{escaped_title}* {notification_title}\n\n"
            f"{episode_info_text}"
            f"⏰ *时间*: `{current_time}`\n"
            f"📝 *剧情*: {escaped_overview}"
        )
        
        # --- 5. 查询订阅者 ---
        subscribers = request_db.get_subscribers_by_tmdb_id(tmdb_id, item_type) if tmdb_id else []
        subscriber_chat_ids = {
            user_db.get_user_telegram_chat_id(sub.get('user_id')) 
            for sub in subscribers 
            if sub.get('type') == 'user_request' and sub.get('user_id')
        }
        subscriber_chat_ids = {chat_id for chat_id in subscriber_chat_ids if chat_id}

        # --- 6 & 7. 发送全局和管理员通知 ---
        global_channel_id = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_CHANNEL_ID)
        notify_types = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_NOTIFY_TYPES, constants.DEFAULT_TELEGRAM_NOTIFY_TYPES)
        
        if 'library_new' in notify_types:
            if global_channel_id:
                logger.info(f"  ➜ 正在向全局频道 {global_channel_id} 发送通知...")
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
                    
                    logger.info(f"  ➜ 正在向管理员 {admin_chat_id} 发送全局入库通知...")
                    if photo_url:
                        send_telegram_photo(admin_chat_id, photo_url, caption)
                    else:
                        send_telegram_message(admin_chat_id, caption)
        else:
            logger.debug(f"  ➜ [通知] '入库通知' 设置为关闭，跳过频道和管理员的全局广播。")

        # --- 8. 发送个人订阅到货通知 ---
        if subscriber_chat_ids:
            personal_caption_map = {
                'new': f"✅ *您的订阅已入库*\n\n{caption}",
                'update': f"🔄 *您的订阅已更新*\n\n{caption}"
            }
            personal_caption = personal_caption_map.get(notification_type, caption)
            
            for chat_id in subscriber_chat_ids:
                if chat_id == global_channel_id: continue
                logger.info(f"  ➜ 正在向订阅者 {chat_id} 发送个人通知...")
                if photo_url:
                    send_telegram_photo(chat_id, photo_url, personal_caption)
                else:
                    send_telegram_message(chat_id, personal_caption)
            
    except Exception as e:
        logger.error(f"  ➜ 发送媒体通知时发生严重错误: {e}", exc_info=True)

def send_playback_notification(data: dict):
    """发送图文并茂的播放状态通知 (增强版：带进度、集数、IP、归属地)"""
    try:
        event_type = data.get("Event")
        user_name = data.get("User", {}).get("Name", "未知用户")
        
        # 提取会话与客户端信息
        session_info = data.get("Session", {})
        device_name = session_info.get("DeviceName", "未知设备")
        client_name = session_info.get("Client", "未知客户端")
        ip_address_raw = session_info.get("RemoteEndPoint", "未知 IP")
        
        item = data.get("Item", {})
        original_item_name = item.get("Name", "未知项目")
        original_item_type = item.get("Type", "Unknown")
        item_id = item.get("Id")
        
        # --- 提取 SxxExx 季集号 ---
        sxe_string = ""
        if original_item_type == "Episode":
            season_num = item.get("ParentIndexNumber")
            episode_num = item.get("IndexNumber")
            if season_num is not None and episode_num is not None:
                sxe_string = f" S{int(season_num):02d}E{int(episode_num):02d}"

        # 格式化标题：剧名 S01E01 - 分集名
        display_item_name = original_item_name
        if original_item_type == "Episode" and item.get("SeriesName"):
            display_item_name = f"{item.get('SeriesName')}{sxe_string} - {original_item_name}"
            
        # --- 提取播放进度 ---
        progress_text = ""
        playback_info = data.get("PlaybackInfo", {})
        if playback_info:
            position_ticks = playback_info.get("PositionTicks", 0)
            runtime_ticks = item.get("RunTimeTicks", 0)
            
            if runtime_ticks > 0:
                pos_str = _format_ticks_to_time(position_ticks)
                total_str = _format_ticks_to_time(runtime_ticks)
                percentage = (position_ticks / runtime_ticks) * 100
                percentage = min(percentage, 100.0) # 限制不超过100%
                progress_text = f"⏳ *进度*: `{pos_str} / {total_str} ({percentage:.1f}%)`\n"
        
        # --- 获取 IP 地理位置 ---
        ip_location = _get_ip_location(ip_address_raw)
        
        # 组装最终展示的 IP (等宽显示 IP，非等宽显示位置信息并带个图钉图标)
        display_ip = f"`{escape_markdown(ip_address_raw)}`"
        if ip_location:
            display_ip += f" 📍 {escape_markdown(ip_location)}"

        # 优先从 Emby Webhook 数据中提取剧情
        raw_overview = item.get("Overview", "")
        
        # --- 本地数据库提取图片和剧情兜底 ---
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
        
        # 格式化剧情文本 (限制长度)
        overview_text = ""
        if raw_overview:
            if len(raw_overview) > 150:
                raw_overview = raw_overview[:150] + "..."
            overview_text = f"\n📝 *剧情*: {escape_markdown(raw_overview)}"
                    
        action_map = {
            "playback.start": "▶️ 开始播放",
            "playback.pause": "⏸ 暂停播放",
            "playback.stop": "⏹ 停止播放"
        }
        action_str = action_map.get(event_type, "🎬 播放状态改变")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ★ 最终组装 Caption
        caption = (
            f"{action_str}\n\n"
            f"👤 *用户*: `{escape_markdown(user_name)}`\n"
            f"🎬 *媒体*: *{escape_markdown(display_item_name)}*\n"
            f"{progress_text}"
            f"📱 *设备*: `{escape_markdown(device_name)} ({escape_markdown(client_name)})`\n"
            f"🌐 *地址*: {display_ip}\n"
            f"🕒 *时间*: `{escape_markdown(current_time)}`"
            f"{overview_text}" 
        )
        
        # --- 收集发送目标 ---
        global_channel_id = APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_CHANNEL_ID)
        admin_ids = set(user_db.get_admin_telegram_chat_ids())

        targets = set()
        if global_channel_id:
            targets.add(str(global_channel_id))
        for aid in admin_ids:
            if aid:
                targets.add(str(aid))

        if not targets:
            logger.debug("  ➜ [播放通知] 未配置接收人 (频道或管理员均为空)，跳过发送。")
            return

        for target in targets:
            if photo_url:
                send_telegram_photo(target, photo_url, caption)
            else:
                send_telegram_message(target, caption)
                
    except Exception as e:
        logger.error(f"  ➜ 组装/发送播放图文通知时发生异常: {e}", exc_info=True)

# ======================================================================
# ★★★ Telegram 机器人交互监听 (长轮询) ★★★
# ======================================================================
import re
import time
import threading

# 全局变量控制轮询线程
_tg_polling_thread = None
_tg_polling_active = False

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
    
    # 1. 权限校验
    admin_ids = [str(aid) for aid in user_db.get_admin_telegram_chat_ids()]
    if chat_id not in admin_ids:
        logger.warning(f"  ➜ [TG交互] 收到未授权用户 ({chat_id}) 的回调请求，已拒绝。")
        return

    # 2. 响应 Callback Query (消除按钮上的加载圈圈)
    if bot_token and query_id:
        answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        try:
            requests.post(answer_url, json={'callback_query_id': query_id}, proxies=get_proxies_for_requests(), timeout=5)
        except Exception:
            pass

    # 3. 处理任务触发逻辑
    if data.startswith('run_task_'):
        task_key = data.replace('run_task_', '')
        _execute_task_from_tg(chat_id, task_key)

def _handle_incoming_message(message: dict):
    """处理接收到的单条消息 (纯手动遥控器模式)"""
    chat_id = str(message.get('chat', {}).get('id', ''))
    text = message.get('text', '') or message.get('caption', '') # 兼容带图片的 caption
    text = text.strip()
    if not chat_id or not text:
        return

    # 1. 权限校验：只允许管理员发送指令 (或者来自全局频道)
    admin_ids = [str(aid) for aid in user_db.get_admin_telegram_chat_ids()]
    global_channel = str(APP_CONFIG.get(constants.CONFIG_OPTION_TELEGRAM_CHANNEL_ID, ''))
    
    if chat_id not in admin_ids and chat_id != global_channel:
        logger.warning(f"  ➜ [TG交互] 收到未授权用户 ({chat_id}) 的消息，已忽略。")
        return

    # ★★★ 处理 M 菜单发来的命令 ★★★
    if text.startswith('/'):
        cmd = text[1:].lower()
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

    commands.append({"command": "all_tasks", "description": "📋 查看所有可用任务"})

    api_url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
    payload = {"commands": commands}
    
    try:
        proxies = get_proxies_for_requests()
        response = requests.post(api_url, json=payload, timeout=10, proxies=proxies)
        if response.status_code == 200:
            logger.trace("  ➜ 成功注册 Telegram 机器人快捷菜单。")
        else:
            logger.warning(f"  ➜ 注册 Telegram 菜单命令失败: {response.text}")
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
                logger.error("  ➜ Telegram Bot Token 无效，停止轮询。")
                break
                
        except requests.exceptions.Timeout:
            pass 
        except Exception as e:
            logger.debug(f"  ➜ Telegram 轮询网络异常 (将自动重试): {e}")
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