import logging
import re
import threading
import time

import requests

import config_manager
import constants
from handler.emby import emby_client


logger = logging.getLogger(__name__)

PLUGIN_NAME = 'ETK MediaInfo Bridge'
PLUGIN_TASK_KEY = 'ETKMediaInfoBridgeUpdate'
LATEST_RELEASE_API = 'https://api.github.com/repos/hbq0405/etk-mediainfo-bridge/releases/latest'
_START_LOCK = threading.Lock()
_STARTED = False


def _version_tuple(value):
    numbers = [int(part) for part in re.findall(r'\d+', str(value or ''))[:4]]
    return tuple((numbers + [0, 0, 0, 0])[:4]) if numbers else None


def _emby_headers(api_key):
    return {'X-Emby-Token': api_key, 'Accept': 'application/json'}


def _emby_get_json(base_url, api_key, path):
    response = emby_client.get(
        f"{base_url.rstrip('/')}{path}",
        headers=_emby_headers(api_key),
        params={'api_key': api_key},
    )
    response.raise_for_status()
    return response.json()


def _latest_plugin_version():
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'EmbyToolKit-PluginUpdater',
    }
    token = str(config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_GITHUB_TOKEN) or '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    response = requests.get(
        LATEST_RELEASE_API,
        headers=headers,
        timeout=20,
        proxies=config_manager.get_proxies_for_requests(),
    )
    response.raise_for_status()
    tag = str((response.json() or {}).get('tag_name') or '').strip()
    return tag, _version_tuple(tag)


def _find_plugin(plugins):
    for plugin in plugins or []:
        if str(plugin.get('Name') or '').strip() == PLUGIN_NAME:
            return plugin
    return None


def _find_update_task(tasks):
    for task in tasks or []:
        if str(task.get('Key') or '').strip() == PLUGIN_TASK_KEY:
            return task
    return None


def _task_end_time(task):
    return str(((task or {}).get('LastExecutionResult') or {}).get('EndTimeUtc') or '').strip()


def _wait_for_task(base_url, api_key, task_id, previous_end_time, timeout_seconds=420):
    deadline = time.monotonic() + timeout_seconds
    saw_running = False
    while time.monotonic() < deadline:
        tasks = _emby_get_json(base_url, api_key, '/ScheduledTasks')
        task = next((item for item in tasks if str(item.get('Id')) == str(task_id)), None)
        if task is None:
            raise RuntimeError('Emby 插件更新任务已消失')
        if str(task.get('State') or '').lower() == 'running':
            saw_running = True
            time.sleep(2)
            continue

        result = task.get('LastExecutionResult') or {}
        end_time = str(result.get('EndTimeUtc') or '').strip()
        if saw_running or (end_time and end_time != previous_end_time):
            status = str(result.get('Status') or '').strip()
            if status.lower() == 'completed':
                return True
            logger.error(
                "  ➜ [插件联动更新] Emby 更新任务失败: status=%s, error=%s",
                status or 'unknown',
                result.get('ErrorMessage') or result.get('LongErrorMessage') or '',
            )
            return False
        time.sleep(2)
    logger.error("  ➜ [插件联动更新] 等待 Emby 插件更新任务超时。")
    return False


def check_and_update_etk_plugin():
    base_url = str(config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_EMBY_SERVER_URL) or '').strip()
    api_key = str(config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_EMBY_API_KEY) or '').strip()
    if not base_url or not api_key:
        logger.debug("  ➜ [插件联动更新] 未配置 Emby 地址或 API Key，跳过检查。")
        return False

    try:
        plugin = _find_plugin(_emby_get_json(base_url, api_key, '/Plugins'))
        if plugin is None:
            logger.warning("  ➜ [插件联动更新] Emby 未安装 ETK MediaInfo Bridge，跳过自动更新。")
            return False
        current_text = str(plugin.get('Version') or '').strip()
        current_version = _version_tuple(current_text)
        latest_text, latest_version = _latest_plugin_version()
        if current_version is None or latest_version is None:
            logger.warning(
                "  ➜ [插件联动更新] 无法解析插件版本: current=%s, latest=%s",
                current_text or 'unknown',
                latest_text or 'unknown',
            )
            return False
        if current_version >= latest_version:
            logger.debug(
                "  ➜ [插件联动更新] 插件已是最新版: %s",
                current_text,
            )
            return False

        tasks = _emby_get_json(base_url, api_key, '/ScheduledTasks')
        task = _find_update_task(tasks)
        if task is None:
            logger.error("  ➜ [插件联动更新] Emby 中未找到插件更新计划任务。")
            return False

        task_id = str(task.get('Id') or '').strip()
        if not task_id:
            logger.error("  ➜ [插件联动更新] Emby 插件更新任务缺少 ID。")
            return False
        previous_end_time = _task_end_time(task)
        logger.info(
            "  ➜ [插件联动更新] 检测到新版本: %s -> %s，正在触发 Emby 更新任务。",
            current_text,
            latest_text,
        )
        if str(task.get('State') or '').lower() != 'running':
            response = emby_client.post(
                f"{base_url.rstrip('/')}/ScheduledTasks/Running/{task_id}",
                headers=_emby_headers(api_key),
                params={'api_key': api_key},
            )
            response.raise_for_status()

        if not _wait_for_task(base_url, api_key, task_id, previous_end_time):
            return False

        system_info = _emby_get_json(base_url, api_key, '/System/Info')
        if not bool(system_info.get('HasPendingRestart')):
            logger.error("  ➜ [插件联动更新] 更新任务已完成，但 Emby 未报告待重启，拒绝自动重启。")
            return False

        logger.info("  ➜ [插件联动更新] 插件已更新，正在自动重启 Emby 使其生效。")
        response = emby_client.post(
            f"{base_url.rstrip('/')}/System/Restart",
            headers=_emby_headers(api_key),
            params={'api_key': api_key},
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error("  ➜ [插件联动更新] 自动检查或更新失败: %s", e)
        return False


def schedule_etk_plugin_update_check(delay_seconds=30):
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return False
        _STARTED = True

    def delayed_check():
        time.sleep(max(0, delay_seconds))
        check_and_update_etk_plugin()

    threading.Thread(
        target=delayed_check,
        name='ETKPluginUpdateCheck',
        daemon=True,
    ).start()
    return True
