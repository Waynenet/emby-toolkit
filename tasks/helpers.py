# tasks/helpers.py
# 跨模块共享的辅助函数

import os
import re
import json
from typing import Optional, Dict, Tuple, List, Set, Any
import logging
from datetime import datetime, timedelta, timezone

from handler.tmdb import get_movie_details, get_tv_details, get_tv_season_details, search_tv_shows, get_tv_season_details
from database import settings_db, connection, request_db, media_db
from ai_translator import AITranslator
import utils
import constants
from database.connection import get_db_connection
from database.actor_db import ActorDBManager

logger = logging.getLogger(__name__)

# =================================================================
# ★★★ 新增：基于 PostgreSQL 的“之”字标题防抖白名单管理器 ★★★
# =================================================================
_TITLE_SPLIT_IGNORE_CACHE = None

def get_title_ignore_cache() -> set:
    """获取白名单（内存缓存，首次调用时从数据库加载）"""
    global _TITLE_SPLIT_IGNORE_CACHE
    if _TITLE_SPLIT_IGNORE_CACHE is None:
        _TITLE_SPLIT_IGNORE_CACHE = set()
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT title FROM title_parse_whitelist")
                    for row in cursor.fetchall():
                        _TITLE_SPLIT_IGNORE_CACHE.add(row['title'])
            logger.debug(f"  ➜ 已从数据库加载 {len(_TITLE_SPLIT_IGNORE_CACHE)} 条剧名防抖白名单。")
        except Exception as e:
            logger.warning(f"  ➜ 读取剧名白名单失败: {e}")
    return _TITLE_SPLIT_IGNORE_CACHE

def add_to_title_ignore_cache(title: str):
    """加入白名单（同步更新内存与数据库）"""
    cache = get_title_ignore_cache()
    if title not in cache:
        cache.add(title)
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO title_parse_whitelist (title) 
                        VALUES (%s) ON CONFLICT (title) DO NOTHING
                    """, (title,))
                conn.commit()
        except Exception as e:
            logger.warning(f"  ➜ 写入剧名白名单到数据库失败: {e}")

AUDIO_SUBTITLE_KEYWORD_MAP = {
    "chi": ["Mandarin", "CHI", "ZHO", "国语", "国配", "国英双语", "公映", "台配", "京译", "上译", "央译"],
    "yue": ["Cantonese", "YUE", "粤语"],
    "eng": ["English", "ENG", "英语"],
    "jpn": ["Japanese", "JPN", "日语"],
    "kor": ["Korean", "KOR", "韩语"],
    "sub_chi": ["CHS", "SC", "GB", "简体", "简中", "简", "中字", "Simplified"],  
    "sub_yue": ["CHT", "TC", "BIG5", "繁體", "繁体", "繁", "Traditional"],    
    "sub_eng": ["ENG", "英字"],
    "sub_jpn": ["JPN", "日字", "日文"],
    "sub_kor": ["KOR", "韩字", "韩文"],
}

AUDIO_DISPLAY_MAP = {'chi': '国语', 'yue': '粤语', 'eng': '英语', 'jpn': '日语', 'kor': '韩语'}
SUB_DISPLAY_MAP = {'chi': '简体', 'yue': '繁体', 'eng': '英文', 'jpn': '日文', 'kor': '韩文'}

RELEASE_GROUPS: Dict[str, List[str]] = {
    "0ff": ['FF(?:(?:A|WE)B|CD|E(?:DU|B)|TV)'],
    "1pt": [],
    "52pt": [],
    "观众": ['Audies', r'\bAD(?:Audio|E(?:book|)|Music|Web)\b'],
    "azusa": [],
    "备胎": ['BeiTai'],
    "学校": ['Bts(?:CHOOL|HD|PAD|TV)', 'Zone'],
    "carpt": ['CarPT'],
    "彩虹岛": ['CHD(?:Bits|PAD|(?:|HK)TV|WEB|)', 'StBOX', 'OneHD', 'Lee', 'xiaopie'],
    "碟粉": ['discfan'],
    "dragonhd": [],
    "eastgame": ['(?:(?:iNT|(?:HALFC|Mini(?:S|H|FH)D))-|)TLF'],
    "filelist": [],
    "gainbound": ['(?:DG|GBWE)B'],
    "hares": ['Hares(?:(?:M|T)V|Web|)'],
    "hd4fans": [],
    "高清视界": ['HDA(?:pad|rea|TV)', 'EPiC'],
    "阿童木": ['hdatmos'],
    "hdbd": [],
    "hdchina": ['HDC(?:hina|TV|)', 'k9611', 'tudou', 'iHD'],
    "杜比": ['D(?:ream|BTV)', '(?:HD|QHstudI)o'],
    "红豆饭": ['beAst(?:TV|)', 'HDFans'],
    "家园": ['HDH(?:ome|Pad|TV|WEB|)'],
    "hdpt": ['HDPT(?:Web|)'],
    "天空": ['HDS(?:ky|TV|Pad|WEB|)', 'AQLJ'],
    "高清时间": ['hdtime'],
    "HDU": [],
    "hdvideo": [],
    "hdzone": ['HDZ(?:one|)'],
    "憨憨": ['HHWEB'],
    "末日": ['AGSV(PT|WEB|MUS)'],
    "hitpt": [],
    "htpt": ['HTPT'],
    "iptorrents": [],
    "joyhd": [],
    "朋友": ['FRDS', 'Yumi', 'cXcY'],
    "柠檬": ['L(?:eague(?:(?:C|H)D|(?:M|T)V|NF|WEB)|HD)', 'i18n', 'CiNT'],
    "馒头": ['MTeam(?:TV|)', 'MPAD', 'MWeb'],
    "nanyangpt": [],
    "老师": ['nicept'],
    "oshen": [],
    "我堡": ['Our(?:Bits|TV)', 'FLTTH', 'Ao', 'PbK', 'MGs', 'iLove(?:HD|TV)'],
    "猪猪": ['PiGo(?:NF|(?:H|WE)B)'],
    "铂金学院": ['ptchina'],
    "猫站": ['PTer(?:DIY|Game|(?:M|T)V|WEB|)'],
    "pthome": ['PTH(?:Audio|eBook|music|ome|tv|WEB|)'],
    "ptmsg": [],
    "烧包": ['PTsbao', 'OPS', 'F(?:Fans(?:AIeNcE|BD|D(?:VD|IY)|TV|WEB)|HDMv)', 'SGXT'],
    "pttime": [],
    "葡萄": ['PuTao'],
    "聆音": ['lingyin'],
    "春天": [r"CMCT(?:A|V)?", "Oldboys", "GTR", "CLV", "CatEDU", "Telesto", "iFree"],
    "鲨鱼": ['Shark(?:WEB|DIY|TV|MV|)'],
    "他吹吹风": ['tccf'],
    "北洋园": ['TJUPT'],
    "听听歌": ['TTG', 'WiKi', 'NGB', 'DoA', '(?:ARi|ExRE)N'],
    "U2": [],
    "ultrahd": [],
    "others": ['B(?:MDru|eyondHD|TN)', 'C(?:fandora|trlhd|MRG)', 'DON', 'EVO', 'FLUX', 'HONE(?:yG|)',
               'N(?:oGroup|T(?:b|G))', 'PandaMoon', 'SMURF', 'T(?:EPES|aengoo|rollHD )'],
    "anime": [r'\bANi\b', r'\bHYSUB\b', r'\bKTXP\b', 'LoliHouse', r'\bMCE\b', 'Nekomoe kissaten', 'SweetSub', 'MingY',
              '(?:Lilith|NC)-Raws', '织梦字幕组', '枫叶字幕组', '猎户手抄部', '喵萌奶茶屋', '漫猫字幕社',
              '霜庭云花Sub', '北宇治字幕组', '氢气烤肉架', '云歌字幕组', '萌樱字幕组', '极影字幕社',
              '悠哈璃羽字幕社',
              '❀拨雪寻春❀', '沸羊羊(?:制作|字幕组)', '(?:桜|樱)都字幕组'],
    "青蛙": ['FROG(?:E|Web|)'],
    "ubits": ['UB(?:its|WEB|TV)'],
    "影巢": ['HiveWeb'],
}

def normalize_full_width_chars(text: str) -> str:
    """将字符串中的全角字符（数字、字母、冒号）转换为半角。"""
    if not text:
        return ""
    # 全角空格
    text = text.replace('\u3000', ' ')
    # 全角数字、字母、冒号的转换表
    full_width = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ： "
    half_width = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz: "
    translation_table = str.maketrans(full_width, half_width)
    return text.translate(translation_table)

def _extract_exclusion_keywords_from_filename(filename: str) -> List[str]:
    """
    【V2 - 正则修复版】
    基于 RELEASE_GROUPS 字典中的别名匹配文件名，找到发布组名（中文）。
    此版本能正确处理正则表达式别名。
    """
    if not filename:
        return []
    tail_token = extract_release_group_token_from_filename(filename)
    tail_group = normalize_release_group_name(tail_token)
    if tail_token and tail_group and tail_group != tail_token:
        return [tail_group]
    return []

def extract_release_groups_from_filename(filename: str) -> List[str]:
    """Return standardized release group names matched by RELEASE_GROUPS."""
    return _extract_exclusion_keywords_from_filename(filename)

def extract_release_group_token_from_filename(filename: str) -> str:
    """从常见命名尾部提取原始发布组别名，例如 HDSWEB、ADWeb。"""
    text = str(filename or '').strip()
    if not text:
        return ''
    name_part = os.path.splitext(text)[0].strip(' ._-')
    if '@' in name_part:
        token = name_part.rsplit('@', 1)[-1]
    else:
        token = re.split(r'\s*[·-]\s*', name_part)[-1]
    token = str(token or '').strip(' ._-')
    if re.search(r'[A-Za-z]', token):
        return token
    return ''

def normalize_release_group_name(value: str) -> str:
    """将发布组别名归一为 RELEASE_GROUPS 的标准组名；未命中时返回清洗后的原值。"""
    text = str(value or '').strip(' ._-')
    if not text:
        return ''
    text = re.sub(r'\.(?:mkv|mp4|ts|avi|mov|wmv|strm|nfo|json)$', '', text, flags=re.IGNORECASE).strip(' ._-')
    if not text:
        return ''

    for group_name, alias_list in get_release_group_mapping().items():
        if text.lower() == str(group_name).lower():
            return group_name
        for alias in alias_list:
            try:
                if re.fullmatch(alias, text, re.IGNORECASE):
                    return group_name
            except re.error as e:
                logger.warning(f"RELEASE_GROUPS 中存在无效的正则表达式: '{alias}' for group '{group_name}'. Error: {e}")
                continue
    return text

def describe_release_group_match(filename: str) -> Dict[str, str]:
    """返回发布组标准名和命中的尾部别名，用于锁版判断和日志展示。"""
    token = extract_release_group_token_from_filename(filename)
    groups = extract_release_groups_from_filename(filename)
    standard = groups[0] if groups else ''
    return {
        'group': standard,
        'alias': token if standard else '',
    }

def format_release_group_label(group_name: str, alias: str = '') -> str:
    group = str(group_name or '').strip(' ._-')
    return group or str(alias or '').strip(' ._-')

def get_keywords_by_group_name(group_name: str) -> List[str]:
    """
    根据发布组的中文名（或其他键名），反查其在 RELEASE_GROUPS 中对应的所有关键词/别名。
    
    :param group_name: 发布组的键名，例如 "朋友"
    :return: 对应的关键词列表，例如 ['FRDS', 'Yumi', 'cXcY']。如果找不到则返回空列表。
    """
    if not group_name:
        return []
    # 使用 .get() 方法安全地获取值，如果找不到键，则返回一个空列表
    return RELEASE_GROUPS.get(group_name, [])

def build_exclusion_regex_from_groups(group_names: List[str]) -> str:
    """
    接收一个发布组名称的列表，查询它们所有的关键词，并构建一个单一的、
    用于排除的 OR 正则表达式。
    
    :param group_names: 发布组名称列表，例如 ["朋友", "春天"]
    :return: 一个正则表达式字符串，例如 "(?:FRDS|Yumi|cXcY|CMCT(?:A|V)?|Oldboys|...)"
             如果列表为空或未找到任何关键词，则返回空字符串。
    """
    if not group_names:
        return ""

    all_keywords = []
    # 遍历传入的每一个组名
    for group_name in group_names:
        # 调用我们之前的反查函数，获取该组的所有关键词
        keywords = get_keywords_by_group_name(group_name)
        if keywords:
            all_keywords.extend(keywords)

    if not all_keywords:
        return ""

    # 使用 | (OR) 将所有关键词连接起来，并用一个非捕获组 (?:...) 包裹
    # 这意味着“只要标题中包含任意一个关键词，就匹配成功”
    return f"(?:{'|'.join(all_keywords)})"

def _get_standardized_effect(path_lower: str, video_stream: Optional[Dict]) -> str:
    """
    【V10 - 优先 JSON 数据版】
    优先从视频流(JSON)中提取精确的 HDR/DV 信息，如果流中没有，再从文件名兜底。
    """
    # 1. 优先对视频流进行精确分析 (JSON数据为准)
    if video_stream and isinstance(video_stream, dict):
        all_stream_info = []
        for key, value in video_stream.items():
            all_stream_info.append(str(key).lower())
            if isinstance(value, str):
                all_stream_info.append(value.lower())
        combined_info = " ".join(all_stream_info)

        if "doviprofile81" in combined_info: return "dovi_p8"
        if "doviprofile76" in combined_info: return "dovi_p7"
        if "doviprofile5" in combined_info: return "dovi_p5"
        if any(s in combined_info for s in ["dvhe.08", "dvh1.08"]): return "dovi_p8"
        if any(s in combined_info for s in ["dvhe.07", "dvh1.07"]): return "dovi_p7"
        if any(s in combined_info for s in ["dvhe.05", "dvh1.05"]): return "dovi_p5"
        
        has_dv = "dovi" in combined_info or "dolby" in combined_info or "dolbyvision" in combined_info
        has_hdr = "hdr10+" in combined_info or "hdr10plus" in combined_info or "hdr" in combined_info
        
        if has_dv and has_hdr: return "dovi_p8"
        if has_dv: return "dovi_other"
        if "hdr10+" in combined_info or "hdr10plus" in combined_info: return "hdr10+"
        if "hdr" in combined_info: return "hdr"

    # 2. 如果视频流没有提取到特效信息，再从文件名判断 (补充兜底)
    if ("dovi" in path_lower or "dolbyvision" in path_lower or "dv" in path_lower) and "hdr" in path_lower:
        return "dovi_p8"
    if any(s in path_lower for s in ["dovi p7", "dovi.p7", "dv.p7", "profile 7", "profile7"]):
        return "dovi_p7"
    if any(s in path_lower for s in ["dovi p5", "dovi.p5", "dv.p5", "profile 5", "profile5"]):
        return "dovi_p5"
    if "dovi" in path_lower or "dolbyvision" in path_lower:
        return "dovi_other"
    if "hdr10+" in path_lower or "hdr10plus" in path_lower:
        return "hdr10+"
    if "hdr" in path_lower:
        return "hdr"

    # 3. 默认是SDR
    return "sdr"

def _extract_quality_tag_from_filename(filename_lower: str) -> str:
    """
    从文件名中提取质量标签，如果找不到，则返回 '未知'。
    """
    QUALITY_HIERARCHY = [
        ('remux', 'Remux'),
        ('bluray', 'BluRay'),
        ('blu-ray', 'BluRay'),
        ('web-dl', 'WEB-DL'),
        ('webdl', 'WEB-DL'),
        ('webrip', 'WEBrip'),
        ('hdtv', 'HDTV'),
        ('dvdrip', 'DVDrip')
    ]
    
    for tag, display in QUALITY_HIERARCHY:
        # 使用更宽松的匹配，避免因为点、空格等问题匹配失败
        if tag in filename_lower:
            return display
            
    return "未知"

def _get_resolution_tier(width: int, height: int) -> tuple[int, str]:
    """
    根据视频流的宽高判断分辨率。
    考虑到电影经常切除上下黑边（如 1920x800）或左右黑边（如 1804x1080），必须综合判断 width 和 height。
    """
    # 4K: 标准 3840x2160。切黑边可能 3840x1600 等。只要宽>=3800 或 高>=2100 就算
    if width >= 3800 or height >= 2100: return 4, "4k"
    
    # 1080p: 标准 1920x1080。切黑边可能 1920x800，或者左右切边 1804x1080
    if width >= 1800 or height >= 1000: return 3, "1080p"
    
    # 720p: 标准 1280x720。切黑边可能 1280x536
    if width >= 1200 or height >= 700: return 2, "720p"
    
    # 480p: 标准 720x480, 854x480
    if width >= 700 or height >= 480: return 1, "480p"
    
    return 0, "未知"

def _get_detected_languages_from_streams(
    media_streams: List[dict], 
    stream_type: str
) -> set:
    detected_langs = set()
    standard_codes = {
        'chi': {'chi', 'zho', 'chs', 'zh-cn', 'zh-hans', 'zh-sg', 'cmn'}, 
        'yue': {'yue', 'cht'}, 
        'eng': {'eng'},
        'jpn': {'jpn'},
        'kor': {'kor'},
    }
    
    for stream in media_streams:
        if stream.get('Type') == stream_type:
            # 检查 Language 字段
            if lang_code := str(stream.get('Language', '')).lower():
                for key, codes in standard_codes.items():
                    if lang_code in codes:
                        detected_langs.add(key)
            
            # 检查标题字段 (修复 None 值拼接报错，并加空格防止粘连)
            raw_title = stream.get('Title') or ''
            raw_display = stream.get('DisplayTitle') or ''
            title_string = f"{raw_title} {raw_display}".lower()
            
            if not title_string.strip(): continue
            for lang_key, keywords in AUDIO_SUBTITLE_KEYWORD_MAP.items():
                normalized_lang_key = lang_key.replace('sub_', '')
                if any(keyword.lower() in title_string for keyword in keywords):
                    detected_langs.add(normalized_lang_key)
    return detected_langs

def analyze_media_asset(item_details: dict) -> dict:
    """视频流分析引擎"""
    if not item_details:
        return {}

    media_streams = item_details.get('MediaStreams', [])
    file_path = item_details.get('Path', '')
    file_name = os.path.basename(file_path) if file_path else ""
    file_name_lower = file_name.lower()

    video_stream = next((s for s in media_streams if s.get('Type') == 'Video'), None)
    resolution_str = "未知"
    if video_stream and video_stream.get("Width"):
        _, resolution_str = _get_resolution_tier(video_stream["Width"], video_stream.get("Height", 0))
    if resolution_str == "未知":
        if "2160p" in file_name_lower or "4K" in file_name_lower:
            resolution_str = "4k"
        elif "1080p" in file_name_lower:
            resolution_str = "1080p"
        elif "720p" in file_name_lower:
            resolution_str = "720p"
        elif "480p" in file_name_lower: 
            resolution_str = "480p"

    quality_str = _extract_quality_tag_from_filename(file_name_lower)
    
    # 1. 获取权威的、细分的特效标签 (例如 'dovi_p8')
    effect_tag = _get_standardized_effect(file_name_lower, video_stream)
    
    # 2. 将其转换为您期望的、标准化的显示格式
    EFFECT_DISPLAY_MAP = {
        "dovi_p8": "DoVi_P8", "dovi_p7": "DoVi_P7", "dovi_p5": "DoVi_P5",
        "dovi_other": "DoVi", "hdr10+": "HDR10+", "hdr": "HDR", "sdr": "SDR"
    }
    effect_display_str = EFFECT_DISPLAY_MAP.get(effect_tag, effect_tag) # 如果没匹配到，显示原始tag

    # 3. 获取原始编码，并将其转换为标准显示格式
    codec_str = '未知'
    CODEC_DISPLAY_MAP = {
        'hevc': 'HEVC', 'h265': 'HEVC', 'x265': 'HEVC',
        'h264': 'H.264', 'avc': 'H.264', 'x264': 'H.264',
        'vp9': 'VP9', 'av1': 'AV1'
    }
    
    # 1. 优先从流获取
    if video_stream and video_stream.get('Codec'):
        raw_codec = video_stream.get('Codec').lower()
        codec_str = CODEC_DISPLAY_MAP.get(raw_codec, raw_codec.upper())
    # 2. 流获取失败，从文件名猜测
    else:
        for key, val in CODEC_DISPLAY_MAP.items():
            # 简单的包含判断，比如 "x265"
            if key in file_name_lower:
                codec_str = val
                break

    # 恢复语言标签提取 (保证洗版和筛选规则正常工作)
    detected_audio_langs = _get_detected_languages_from_streams(media_streams, 'Audio')
    audio_str = ', '.join(sorted([AUDIO_DISPLAY_MAP.get(lang, lang) for lang in detected_audio_langs]))
    
    # ★★★ 增强音频 (Audio) 的文件名兜底 ★★★
    # 如果 Emby 没分析出音轨语言，尝试从文件名提取常见音频格式作为展示
    if not audio_str:
        audio_keywords = {
            'truehd': 'TrueHD', 'atmos': 'Atmos', 
            'dts-hd': 'DTS-HD', 'dts': 'DTS', 
            'ac3': 'AC3', 'eac3': 'EAC3', 'dd+': 'Dolby Digital+',
            'aac': 'AAC', 'flac': 'FLAC'
        }
        found_audios = []
        for k, v in audio_keywords.items():
            if k in file_name_lower:
                found_audios.append(v)
        if found_audios:
            audio_str = " | ".join(found_audios) 
        else:
            audio_str = '无' 

    # 提取字幕语言
    detected_sub_langs = _get_detected_languages_from_streams(media_streams, 'Subtitle')
    if 'chi' not in detected_sub_langs and 'yue' not in detected_sub_langs and any(
        s.get('IsExternal') for s in media_streams if s.get('Type') == 'Subtitle'):
        detected_sub_langs.add('chi')
    subtitle_str = ', '.join(sorted([SUB_DISPLAY_MAP.get(lang, lang) for lang in detected_sub_langs])) or '无'

    release_group_list = _extract_exclusion_keywords_from_filename(file_name)

    return {
        "resolution_display": resolution_str,
        "quality_display": quality_str,
        "effect_display": effect_display_str, 
        "codec_display": codec_str,          
        "audio_display": audio_str,
        "subtitle_display": subtitle_str,
        "audio_languages_raw": list(detected_audio_langs),
        "subtitle_languages_raw": list(detected_sub_langs),
        "release_group_raw": release_group_list,
    }

def parse_full_asset_details(item_details: dict, id_to_parent_map: dict = None, library_guid: str = None, local_mediainfo_path: str = None) -> dict:
    """
    视频流分析主函数 (神医融合版)
    优先读取神医插件生成的 -mediainfo.json，原文照搬并提取展示标签。
    """
    # 提取并计算时长 (分钟)
    runtime_ticks = item_details.get('RunTimeTicks')
    runtime_min = round(runtime_ticks / 600000000) if runtime_ticks else None

    item_id = str(item_details.get("Id"))
    ancestors = []
    if id_to_parent_map and item_id:
        ancestors = calculate_ancestor_ids(item_id, id_to_parent_map, library_guid)

    # ★★★ 核心修复 1：如果没有传入路径，主动去同级目录寻找 JSON ★★★
    if not local_mediainfo_path:
        file_path = item_details.get('Path', '')
        if file_path and not file_path.startswith('http'):
            guessed_path = os.path.splitext(file_path)[0] + "-mediainfo.json"
            if os.path.exists(guessed_path):
                local_mediainfo_path = guessed_path

    raw_shenyi_data = None
    if local_mediainfo_path and os.path.exists(local_mediainfo_path):
        try:
            with open(local_mediainfo_path, 'r', encoding='utf-8') as f:
                raw_shenyi_data = json.load(f)
        except Exception as e:
            logger.error(f"读取神医媒体信息文件失败 {local_mediainfo_path}: {e}")

    primary_source = None
    media_streams = []
    
    # ★★★ 提取 Emby 原生的流信息 (用于提取外挂字幕) ★★★
    emby_media_sources = item_details.get("MediaSources", [])
    emby_primary_source = emby_media_sources[0] if emby_media_sources and len(emby_media_sources) > 0 else None
    emby_streams = (emby_primary_source.get("MediaStreams") if emby_primary_source else None) or item_details.get("MediaStreams", [])

    # ★★★ 核心修复 2：兼容两种不同的 JSON 嵌套格式，并融合外挂字幕 ★★★
    if raw_shenyi_data and isinstance(raw_shenyi_data, list) and len(raw_shenyi_data) > 0:
        first_item = raw_shenyi_data[0]
        if "MediaSourceInfo" in first_item:
            primary_source = first_item.get("MediaSourceInfo", {})
        else:
            primary_source = first_item
            
        # 1. 先拿视频文件内嵌的流 (视频、音频、内嵌字幕)
        media_streams = primary_source.get("MediaStreams", [])
        
        # 2. ★★★ 核心修补：从 Emby 数据中把“外挂字幕”揪出来，塞进我们的流列表里 ★★★
        if emby_streams:
            for stream in emby_streams:
                # 只要是字幕，且被 Emby 标记为外挂 (IsExternal)，就加进来
                if stream.get("Type") == "Subtitle" and stream.get("IsExternal"):
                    media_streams.append(stream)
                    
    else:
        # 兜底：如果没有神医 JSON，完全使用 Emby 原始数据
        primary_source = emby_primary_source
        media_streams = emby_streams

    container = (primary_source.get("Container") if primary_source else None) or item_details.get("Container")
    size_bytes = (primary_source.get("Size") if primary_source else None) or item_details.get("Size")

    date_added_to_library = item_details.get("DateCreated")

    asset = {
        "emby_item_id": item_details.get("Id"), 
        "path": item_details.get("Path", ""),
        "size_bytes": size_bytes,   
        "container": container,     
        "video_codec": None, 
        "video_bitrate_mbps": None, 
        "bit_depth": None,          
        "frame_rate": None,         
        "audio_tracks": [], 
        "subtitles": [],
        "date_added_to_library": date_added_to_library,
        "ancestor_ids": ancestors,
        "runtime_minutes": runtime_min
    }
    
    # 遍历流信息提取基础数据
    for stream in media_streams:
        stream_type = stream.get("Type")
        if stream_type == "Video":
            asset["video_codec"] = stream.get("Codec")
            asset["width"] = stream.get("Width")
            asset["height"] = stream.get("Height")
            if stream.get("BitRate"):
                asset["video_bitrate_mbps"] = round(stream.get("BitRate") / 1000000, 1)
            asset["bit_depth"] = stream.get("BitDepth")
            asset["frame_rate"] = stream.get("AverageFrameRate") or stream.get("RealFrameRate")
        elif stream_type == "Audio":
            asset["audio_tracks"].append({
                "language": stream.get("Language"), 
                "codec": stream.get("Codec"), 
                "channels": stream.get("Channels"), 
                "display_title": stream.get("DisplayTitle"),
                "is_default": stream.get("IsDefault")
            })
        elif stream_type == "Subtitle":
            asset["subtitles"].append({
                "language": stream.get("Language"), 
                "display_title": stream.get("DisplayTitle"),
                "is_forced": stream.get("IsForced"),  
                "format": stream.get("Codec") 
            })
            
    # 生成前端展示用的 display 标签
    fake_details_for_analysis = item_details.copy()
    fake_details_for_analysis['MediaStreams'] = media_streams 
    
    display_tags = analyze_media_asset(fake_details_for_analysis)
    asset.update(display_tags)
    
    return asset

# --- 判断电影是否满足订阅条件 ---
def is_movie_subscribable(movie_id: int, api_key: str, config: dict) -> bool:
    """
    检查一部电影是否适合订阅。
    """
    if not api_key:
        logger.error("TMDb API Key 未提供，无法检查电影是否可订阅。")
        return False

    strategy = settings_db.get_setting('subscription_strategy_config') or {}
    # 优先使用数据库配置，没有则使用默认值
    delay_days = int(strategy.get('delay_subscription_days', 0))

    # 初始日志仍然使用ID，因为此时我们还没有片名
    logger.debug(f"  ➜ 检查电影 (ID: {movie_id}) 是否适合订阅 (延迟天数: {delay_days})...")

    details = get_movie_details(
        movie_id=movie_id,
        api_key=api_key,
        append_to_response="release_dates"
    )

    # ★★★ 获取片名用于后续日志，如果获取失败则回退到使用ID ★★★
    log_identifier = f"《{details.get('title')}》" if details and details.get('title') else f"(ID: {movie_id})"

    if not details:
        logger.warning(f"  ➜ 无法获取电影 {log_identifier} 的详情，默认其不适合订阅。")
        return False

    release_info = details.get("release_dates", {}).get("results", [])
    if not release_info:
        logger.warning(f"  ➜ 电影 {log_identifier} 未找到任何地区的发行日期信息，默认其不适合订阅。")
        return False

    earliest_theatrical_date = None
    today = datetime.now().date()

    for country_releases in release_info:
        for release in country_releases.get("release_dates", []):
            release_type = release.get("type")
            if release_type in [4, 5]:
                logger.info(f"  ➜ 成功: 电影 {log_identifier} 已有数字版/光盘发行记录 (Type {release_type})，适合订阅。")
                return True
            if release_type in [1, 2, 3]:
                try:
                    release_date_str = release.get("release_date", "").split("T")[0]
                    if release_date_str:
                        current_release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
                        if earliest_theatrical_date is None or current_release_date < earliest_theatrical_date:
                            earliest_theatrical_date = current_release_date
                except (ValueError, TypeError):
                    logger.warning(f"  ➜ 解析电影 {log_identifier} 的上映日期 '{release.get('release_date')}' 时出错。")
                    continue

    if earliest_theatrical_date:
        days_since_release = (today - earliest_theatrical_date).days
        if days_since_release >= delay_days:
            logger.info(f"  ➜ 成功: 电影 {log_identifier} 最早于 {days_since_release} 天前在影院上映，已超过配置的 {delay_days} 天，适合订阅。")
            return True
        else:
            logger.info(f"  ➜ 失败: 电影 {log_identifier} 最早于 {days_since_release} 天前在影院上映，未满配置的 {delay_days} 天，不适合订阅。")
            return False

    logger.warning(f"  ➜ 电影 {log_identifier} 未找到数字版或任何有效的影院上映日期，默认其不适合订阅。")
    return False

# --- 剧集/季状态检查（统一逻辑） ---
def check_series_completion(
    tmdb_id: int,
    api_key: str,
    season_number: Optional[int] = None,
    series_name: str = "未知剧集",
    mode: str = "completed"
) -> bool:
    """
    统一检查剧集或指定季的播出状态。

    mode:
      - "completed": TMDb 状态为 Ended/Canceled 才返回 True。
      - "airing": TMDb 状态不是 Ended/Canceled 才返回 True。

    注意：
      - 获取不到数据时，两个 mode 都返回 False。
        也就是：未知状态既不强行判完结，也不强行判连载。
    """
    if mode not in ("completed", "airing"):
        raise ValueError("check_series_completion mode 只能是 'completed' 或 'airing'")

    def _match(status: str) -> bool:
        if mode == "airing":
            return status == "airing"
        return status == "completed"

    if not api_key or not tmdb_id:
        return False

    try:
        show_details = get_tv_details(tmdb_id, api_key)
        if not show_details:
            logger.warning(f"  ➜ 剧集《{series_name}》缺少 TMDb 详情，状态未知。")
            return False

        show_status = str(show_details.get("status") or "").strip()
        completed = show_status in ["Ended", "Canceled"]
        target_label = f"第 {season_number} 季" if season_number else "全剧"
        logger.info(
            f"  ➜ 剧集《{series_name}》{target_label} 按 TMDb 状态判定："
            f"{show_status or '未知'} -> {'已完结' if completed else '连载中'}。"
        )
        return _match("completed" if completed else "airing")
                        
    except Exception as e:
        logger.warning(
            f"  ➜ 检查《{series_name}》第 {season_number if season_number else 'All'} 季状态失败: {e}，状态未知。",
            exc_info=True
        )
        return False

def parse_series_title_and_season(title: str, api_key: str = None) -> Tuple[Optional[str], Optional[int]]:
    """
    从一个可能包含季号的剧集标题中，解析出基础剧名和季号。
    
    【V2 - 严格校验版】
    针对 "唐朝诡事录之长安" 这种 "主标题之副标题" 格式：
    1. 尝试拆分。
    2. 必须通过 TMDb API 验证：主标题能搜到剧，且副标题能匹配到该剧的某一季。
    3. 验证失败则视为普通剧名，不进行截断。
    """
    if not title:
        return None, None
        
    normalized_title = normalize_full_width_chars(title)

    # --- 1. 优先处理 "主标题之副标题" 格式 (严格校验逻辑) ---
    # 仅当提供了 API Key 且该剧名不在数据库白名单中时才尝试这种高风险解析
    if '之' in normalized_title and api_key and normalized_title not in get_title_ignore_cache():
        parts = normalized_title.split('之', 1)
        if len(parts) == 2:
            parent_candidate = parts[0].strip()
            subtitle_candidate = parts[1].strip()
            
            # 只有当主标题长度大于1时才处理（避免误伤《云之羽》等）
            if len(parent_candidate) > 1 and subtitle_candidate:
                try:
                    # A. 搜索主标题 (例如 "唐朝诡事录")
                    search_results = search_tv_shows(parent_candidate, api_key)
                    
                    # 只有搜到了结果，才继续验证
                    if search_results:
                        # 假设第一个结果就是我们要找的剧
                        tv_id = search_results[0]['id']
                        # B. 获取该剧的所有季信息
                        tv_details = get_tv_details(tv_id, api_key, append_to_response="seasons")
                        
                        if tv_details and 'seasons' in tv_details:
                            for season in tv_details['seasons']:
                                season_name = season.get('name', '')
                                season_num = season.get('season_number')
                                
                                # C. 严格比对：副标题必须包含在季名中
                                # 例如：季名 "唐朝诡事录之西行"，副标题 "西行" -> 匹配成功
                                if season_num and season_num > 0:
                                    if subtitle_candidate in season_name:
                                        logger.info(f"  ➜ [智能解析] 成功将 '{title}' 解析为《{parent_candidate}》第 {season_num} 季 (匹配季名: {season_name})")
                                        return parent_candidate, season_num
                                        
                    # 如果代码走到这里，说明虽然有'之'，但没匹配到任何季信息
                    # 加入数据库白名单，下次看到直接放行，永远省去 TMDb 的网络请求！
                    add_to_title_ignore_cache(normalized_title)
                    logger.debug(f"  ➜ [智能解析] '{title}' 包含'之'字但未匹配到季信息，已加入数据库白名单，后续永久免检。")
                    
                except Exception as e:
                    logger.warning(f"  ➜ 解析 '之' 字标题时 TMDb 查询出错: {e}，将回退到普通模式。")

    # --- 2. 标准正则匹配 (原有逻辑) ---
    # 如果上面的逻辑没返回，说明它不是 "主标题之副标题" 格式，或者校验失败。
    # 此时 normalized_title 依然是完整的 "亦舞之城"，我们继续检查它是否包含 "S2", "第2季" 等标准标记。
    
    roman_map = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10}
    chinese_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

    patterns = [
        # 模式1: 最优先匹配 "第X季" 或 "Season X"
        re.compile(r'^(.*?)\s*(?:第([一二三四五六七八九十\d]+)季|Season\s*(\d+))', re.IGNORECASE),
        
        # 模式2: 匹配年份 (如 "2024")
        re.compile(r'^(.*?)\s+((?:19|20)\d{2})$'),
        
        # 模式3: 中文数字(带前缀) 或 罗马/阿拉伯数字
        re.compile(r'^(.*?)\s*(?:[第部]\s*([一二三四五六七八九十])|([IVX\d]+))(?:[:\s-]|$)')
    ]

    for pattern in patterns:
        match = pattern.match(normalized_title)
        if not match: continue
        
        groups = [g for g in match.groups() if g is not None]
        if len(groups) < 2: continue
        
        base_name, season_str = groups[0].strip(), groups[1].strip()

        # 健壮性检查
        if (not base_name and len(normalized_title) < 8) or (len(base_name) <= 1 and season_str.isdigit()):
            continue

        season_num = 0
        if season_str.isdigit(): season_num = int(season_str)
        elif season_str.upper() in roman_map: season_num = roman_map[season_str.upper()]
        elif season_str in chinese_map: season_num = chinese_map[season_str]

        if season_num > 0:
            for suffix in ["系列", "合集"]:
                if base_name.endswith(suffix): base_name = base_name[:-len(suffix)]
            return base_name, season_num

    # --- 3. 最终返回 ---
    # 如果所有尝试都失败（既不是"之"字季播剧，也没有"S2"标记）
    # 返回 None, None。调用方会因此使用原始的完整标题进行搜索。
    # 对于 "亦舞之城"，这里返回 (None, None)，于是系统会搜索 "亦舞之城"，这是正确的。
    return None, None

def should_mark_as_pending(tmdb_id: int, season_number: int, api_key: str) -> tuple[bool, int]:
    """
    检查指定季是否满足“自动待定”条件。
    修复版：改用 get_tv_details 获取整剧信息中的 episode_count 字段，而非计算单季详情的列表长度。
    返回: (是否待定, 虚标总集数)
    """
    try:
        # 1. 读取配置
        watchlist_cfg = settings_db.get_setting('watchlist_config') or {}
        auto_pending_cfg = watchlist_cfg.get('auto_pending', {})
        
        if not auto_pending_cfg.get('enabled', False):
            return False, 0

        threshold_days = int(auto_pending_cfg.get('days', 30))
        threshold_episodes = int(auto_pending_cfg.get('episodes', 1))
        fake_total = int(auto_pending_cfg.get('default_total_episodes', 99))
        
        # 2. 获取 TMDb 整剧详情 (比获取单季详情更稳，因为包含明确的 episode_count 字段)
        show_details = get_tv_details(tmdb_id, api_key)
        if not show_details:
            return False, 0

        # 3. 在整剧详情的 seasons 列表中找到目标季
        target_season = None
        seasons = show_details.get('seasons', [])
        for season in seasons:
            if season.get('season_number') == season_number:
                target_season = season
                break
        
        if not target_season:
            # 如果没找到该季信息，无法判断，默认不待定
            return False, 0

        # 4. 获取核心数据
        air_date_str = target_season.get('air_date')
        # 直接读取官方提供的该季总集数，而不是计算列表长度
        episode_count = target_season.get('episode_count', 0)
        
        if air_date_str:
            try:
                air_date = datetime.strptime(air_date_str, '%Y-%m-%d').date()
                # 使用 UTC 时间避免时区导致的日期差异
                today = datetime.now(timezone.utc).date()
                days_diff = (today - air_date).days
                
                # 逻辑：上线时间在阈值内 (例如30天内) AND 集数很少 (例如只有1集)
                # 这种情况通常意味着是刚出的剧，或者数据还没更新全，或者是试播集
                if (0 <= days_diff <= threshold_days) and (episode_count <= threshold_episodes):
                    logger.info(f"  ➜ 触发自动待定: 第{season_number}季 上线{days_diff}天, TMDb记录集数{episode_count} (阈值: {threshold_episodes})")
                    return True, fake_total
            except ValueError:
                pass
                
        return False, 0

    except Exception as e:
        logger.warning(f"检查待定条件失败: {e}")
        return False, 0
    
# --- 计算祖先 ID 集合 ---
def calculate_ancestor_ids(item_id: str, id_to_parent_map: dict, library_guid: str) -> List[str]:
    """
    计算一个条目的祖先 ID 集合，包含其直接父级、祖父级等所有上层 ID，直到根节点
    """
    if not item_id or not id_to_parent_map:
        return []

    ancestors = set()
    curr_id = id_to_parent_map.get(item_id)
    
    while curr_id and curr_id != "1":
        ancestors.add(curr_id)
        # ★★★ 核心修改：增加严格的 None 字符串过滤 ★★★
        if library_guid and str(library_guid).lower() != "none":
            ancestors.add(f"{library_guid}_{curr_id}")
        
        curr_id = id_to_parent_map.get(curr_id)
    
    if library_guid and str(library_guid).lower() != "none":
        ancestors.add(library_guid)
        
    return [str(fid) for fid in ancestors if fid and str(fid).lower() != "none"]

# --- 通用订阅处理函数 ---
def process_subscription_items_and_update_db(
    tmdb_items: List[Dict[str, Any]], 
    tmdb_to_emby_item_map: Dict[str, Any], 
    subscription_source: Dict[str, Any], 
    tmdb_api_key: str
) -> Set[str]:
    """
    通用订阅处理器：接收一组 TMDb 条目，自动处理元数据、父剧集占位、在库检查，并更新 request_db。
    
    :param tmdb_items: 待处理列表，格式 [{'tmdb_id': '...', 'media_type': 'Movie'/'Series', 'season': 1, ...}]
    :param tmdb_to_emby_item_map: 全量本地媒体映射表 (用于判断是否在库)
    :param subscription_source: 订阅源对象 (用于写入数据库 source 字段)
    :param tmdb_api_key: TMDb API Key
    :return: processed_active_ids (Set[str]) - 本次处理中确认活跃的 ID 集合 (用于调用方做清理/Diff)
    """
    if not tmdb_items:
        return set()

    logger.info(f"  ➜ [通用订阅] 开始处理 {len(tmdb_items)} 个媒体条目...")

    # 1. 提前加载所有在库的“季”的信息 (用于精准判断季是否存在)
    in_library_seasons_set = set()
    try:
        with connection.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT parent_series_tmdb_id, season_number FROM media_metadata WHERE item_type = 'Season' AND in_library = TRUE")
            for row in cursor.fetchall():
                in_library_seasons_set.add((str(row['parent_series_tmdb_id']), row['season_number']))
    except Exception as e_db:
        logger.error(f"  -> [通用订阅] 获取在库季列表失败: {e_db}")

    # 2. 获取所有在库的 Key 集合 (Movie/Series)
    in_library_keys = set(tmdb_to_emby_item_map.keys())

    # 3. 获取已订阅/暂停的 Key 集合 (防止重复请求 API)
    subscribed_or_paused_keys = set()
    try:
        with connection.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tmdb_id, item_type FROM media_metadata WHERE subscription_status IN ('SUBSCRIBED', 'PAUSED', 'WANTED', 'IGNORED', 'PENDING_RELEASE')")
            for row in cursor.fetchall():
                subscribed_or_paused_keys.add(f"{row['tmdb_id']}_{row['item_type']}")
    except Exception as e_sub:
        logger.error(f"  -> [通用订阅] 获取订阅状态失败: {e_sub}")
    
    missing_released_items = []
    missing_unreleased_items = []
    parent_series_to_ensure_exist = {} 
    today_str = datetime.now().strftime('%Y-%m-%d')
    parent_series_cache = {} 

    # 用于记录本次真正处理过的 ID (返回给调用方用于清理)
    processed_active_ids = set()

    for item_def in tmdb_items:
        # 这里的 tmdb_id 必须保持为 剧集 ID (Series ID) 或 电影 ID
        tmdb_id = str(item_def.get('tmdb_id')) 
        if not tmdb_id or tmdb_id.lower() == 'none': continue

        media_type = item_def.get('media_type')
        season_num = item_def.get('season')

        # 将原始 ID (剧ID/影ID) 加入活跃列表
        processed_active_ids.add(tmdb_id)

        # --- A. 在库检查 ---
        is_in_library = False
        
        # 1. 显式 Emby ID
        if item_def.get('emby_id'):
            is_in_library = True
        # 2. 季的在库检查
        elif media_type == 'Series' and season_num is not None:
            if (tmdb_id, season_num) in in_library_seasons_set:
                is_in_library = True
        
        # 3. 通用 Key 检查
        if not is_in_library:
            current_key = f"{tmdb_id}_{media_type}"
            if current_key in in_library_keys:
                is_in_library = True
        
        if is_in_library: continue

        # --- B. 获取详情并构建请求 ---
        try:
            details = None
            item_type_for_db = media_type
            
            # 用于写入 media_metadata 的 ID (如果是季，这里会变成季ID)
            target_db_id = tmdb_id 
            
            # ★★★ 分支 1: 带季号的剧集 (视为季) ★★★
            if media_type == 'Series' and season_num is not None:
                parent_id = tmdb_id 
                item_type_for_db = 'Season'

                # 1. 获取/缓存父剧集信息
                if parent_id not in parent_series_cache:
                    p_details = get_tv_details(parent_id, tmdb_api_key)
                    if p_details:
                        parent_series_cache[parent_id] = p_details
                
                parent_details = parent_series_cache.get(parent_id)
                if not parent_details: continue

                # 2. 加入父剧集占位 (确保父剧集存在于 media_metadata，状态为 NONE)
                parent_series_to_ensure_exist[parent_id] = {
                    'tmdb_id': str(parent_id),
                    'item_type': 'Series',
                    'title': parent_details.get('name'),
                    'original_title': parent_details.get('original_name'),
                    'release_date': parent_details.get('first_air_date'),
                    'poster_path': parent_details.get('poster_path'),
                    'backdrop_path': parent_details.get('backdrop_path'),
                    'overview': parent_details.get('overview')
                }

                # 3. 获取季详情
                details = get_tv_season_details(parent_id, season_num, tmdb_api_key)
                if details:
                    details['parent_series_tmdb_id'] = str(parent_id)
                    details['parent_title'] = parent_details.get('name')
                    details['parent_poster_path'] = parent_details.get('poster_path')
                    details['parent_backdrop_path'] = parent_details.get('backdrop_path')
                    
                    # 获取真实的季 ID
                    real_season_id = str(details.get('id'))
                    target_db_id = real_season_id
                    
                    # ★★★ 关键：将季 ID 也加入活跃列表，防止被误清理 ★★★
                    processed_active_ids.add(real_season_id)
                    
                    # 二次检查订阅状态 (检查季ID是否已订阅)
                    s_key = f"{real_season_id}_Season"
                    if s_key in subscribed_or_paused_keys: continue
            
            # 分支 2: 电影
            elif media_type == 'Movie':
                if f"{tmdb_id}_Movie" in subscribed_or_paused_keys: continue
                details = get_movie_details(tmdb_id, tmdb_api_key)
                if details:
                    target_db_id = str(details.get('id'))
                    processed_active_ids.add(target_db_id)

            if not details: continue
            
            # --- C. 构建数据库记录 (用于订阅) ---
            release_date = details.get("air_date") or details.get("release_date") or details.get("first_air_date", '')
            release_year = int(release_date.split('-')[0]) if (release_date and '-' in release_date) else None

            item_details_for_db = {
                'tmdb_id': target_db_id, # 这里存入的是 季ID 或 电影ID
                'item_type': item_type_for_db, # 这里是 'Season' 或 'Movie'
                'title': details.get('name') or details.get('title'),
                'release_date': release_date,
                'release_year': release_year, 
                'overview': details.get('overview'),
                'poster_path': details.get('poster_path') or details.get('parent_poster_path'),
                'backdrop_path': details.get('backdrop_path') or details.get('parent_backdrop_path'),
                'parent_series_tmdb_id': details.get('parent_series_tmdb_id'),
                'season_number': details.get('season_number'),
                'source': subscription_source # 直接使用传入的 source
            }
            
            if item_type_for_db == 'Season':
                item_details_for_db['title'] = details.get('name') or f"第 {season_num} 季"

            # --- D. 分流 ---
            if release_date and release_date > today_str:
                missing_unreleased_items.append(item_details_for_db)
            else:
                missing_released_items.append(item_details_for_db)

        except Exception as e:
            logger.error(f"  -> [通用订阅] 处理条目 {tmdb_id} ({media_type}) 时出错: {e}")

    # 4. 执行数据库操作 (批量写入)
    if parent_series_to_ensure_exist:
        logger.info(f"  -> [通用订阅] 正在确保 {len(parent_series_to_ensure_exist)} 个父剧集元数据存在...")
        request_db.set_media_status_none(
            tmdb_ids=list(parent_series_to_ensure_exist.keys()),
            item_type='Series',
            media_info_list=list(parent_series_to_ensure_exist.values())
        )

    def group_and_update(items_list, status):
        if not items_list: return
        logger.info(f"  -> [通用订阅] 将 {len(items_list)} 个缺失媒体设为 '{status}'...")
        requests_by_type = {}
        for item in items_list:
            itype = item['item_type']
            if itype not in requests_by_type: requests_by_type[itype] = []
            requests_by_type[itype].append(item)
            
        for itype, requests in requests_by_type.items():
            ids = [req['tmdb_id'] for req in requests]
            if status == 'WANTED':
                request_db.set_media_status_wanted(ids, itype, media_info_list=requests, source=subscription_source)
            elif status == 'PENDING_RELEASE':
                request_db.set_media_status_pending_release(ids, itype, media_info_list=requests, source=subscription_source)

    group_and_update(missing_released_items, 'WANTED')
    group_and_update(missing_unreleased_items, 'PENDING_RELEASE')
    
    return processed_active_ids

# --- 分级映射逻辑 ---
def apply_rating_logic(metadata_skeleton: Dict[str, Any], tmdb_data: Dict[str, Any], item_type: str):
    """
    将 TMDb 的原始分级数据，经过配置的映射规则处理后，注入到元数据骨架中。
    """
    from database import settings_db
    
    final_rating_str = ""
    
    # 加载配置
    rating_mapping = settings_db.get_setting('rating_mapping') or utils.DEFAULT_RATING_MAPPING
    priority_list = settings_db.get_setting('rating_priority') or utils.DEFAULT_RATING_PRIORITY
    
    # 获取原产国
    origin_country = None
    if item_type == "Movie":
        _countries = tmdb_data.get('production_countries')
        origin_country = _countries[0].get('iso_3166_1') if _countries else None
    else:
        _countries = tmdb_data.get('origin_country', [])
        origin_country = _countries[0] if _countries else None

    # 准备数据源
    available_ratings = {}
    target_list_node = [] # 指向骨架中的列表节点
    
    if item_type == "Movie":
        # 电影数据源解析
        if 'release_dates' in tmdb_data:
            metadata_skeleton['release_dates'] = tmdb_data['release_dates']
            # 构建列表和字典
            countries_list = []
            for r in tmdb_data['release_dates'].get('results', []):
                country_code = r.get('iso_3166_1')
                cert = ""
                release_date = ""
                for rel in r.get('release_dates', []):
                    if rel.get('certification'):
                        cert = rel.get('certification')
                        release_date = rel.get('release_date')
                        break
                if cert:
                    available_ratings[country_code] = cert
                    countries_list.append({
                        "iso_3166_1": country_code,
                        "certification": cert,
                        "release_date": release_date,
                        "primary": (country_code == origin_country)
                    })
            metadata_skeleton['releases']['countries'] = countries_list
            target_list_node = metadata_skeleton['releases']['countries']
            
    elif item_type == "Series":
        # 剧集数据源解析
        if 'content_ratings' in tmdb_data:
            metadata_skeleton['content_ratings'] = tmdb_data['content_ratings']
            for r in tmdb_data['content_ratings'].get('results', []):
                available_ratings[r.get('iso_3166_1')] = r.get('rating')
            target_list_node = metadata_skeleton['content_ratings']['results']

    # --- 核心映射逻辑 ---
    target_us_code = None
    
    # 1. 成人强制修正
    if tmdb_data.get('adult') is True:
        logger.warning(f"  ➜ 发现成人内容，忽略任何国家分级强制设为 'XXX'.")
        target_us_code = 'XXX'
    # 2. 只有当不是成人内容时，才走常规映射逻辑
    elif 'US' in available_ratings:
        final_rating_str = available_ratings['US']
    else:
        # 3. 按优先级查找
        for p_country in priority_list:
            search_country = origin_country if p_country == 'ORIGIN' else p_country
            if not search_country: continue
            
            if search_country in available_ratings:
                source_rating = available_ratings[search_country]
                
                # 尝试映射
                if isinstance(rating_mapping, dict) and search_country in rating_mapping and 'US' in rating_mapping:
                    current_val = None
                    for rule in rating_mapping[search_country]:
                        if str(rule['code']).strip().upper() == str(source_rating).strip().upper():
                            current_val = rule.get('emby_value')
                            break
                    
                    if current_val is not None:
                        valid_us_rules = []
                        for rule in rating_mapping['US']:
                            r_code = rule.get('code', '')
                            if item_type == "Movie" and r_code.startswith('TV-'): continue
                            if item_type == "Series" and r_code in ['G', 'PG', 'PG-13', 'R', 'NC-17']: continue
                            valid_us_rules.append(rule)
                        
                        # 精确匹配
                        for rule in valid_us_rules:
                            try:
                                if int(rule.get('emby_value')) == int(current_val):
                                    target_us_code = rule['code']
                                    break
                            except: pass
                        
                        # 向上兼容
                        if not target_us_code:
                            for rule in valid_us_rules:
                                try:
                                    if int(rule.get('emby_value')) == int(current_val) + 1:
                                        target_us_code = rule['code']
                                        break
                                except: pass
                
                if target_us_code:
                    logger.info(f"  ➜ [分级映射] 将 {search_country}:{source_rating} 映射为 US:{target_us_code}")
                    final_rating_str = target_us_code
                    break
                elif not final_rating_str:
                    final_rating_str = source_rating

    # 4. 补全 US 分级到列表
    if target_us_code:
        # 移除旧 US
        if item_type == "Movie":
            target_list_node[:] = [c for c in target_list_node if c.get('iso_3166_1') != 'US']
            target_list_node.append({
                "iso_3166_1": "US",
                "certification": target_us_code,
                "release_date": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                "primary": False
            })
        else:
            target_list_node[:] = [r for r in target_list_node if r.get('iso_3166_1') != 'US']
            target_list_node.append({
                "iso_3166_1": "US",
                "rating": target_us_code
            })

    # 5. 写入根节点兜底
    if final_rating_str:
        metadata_skeleton['mpaa'] = final_rating_str
        metadata_skeleton['certification'] = final_rating_str

def construct_metadata_payload(item_type: str, tmdb_data: Dict[str, Any], 
                                  aggregated_tmdb_data: Optional[Dict[str, Any]] = None,
                                  emby_data_fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        统一封装：将 TMDb 原始数据转换为符合本地 override 格式的标准元数据骨架。
        包含：基础字段映射、复杂字段处理(Genres/Keywords/Videos)、分级逻辑、剧集子项结构化等。
        """
        # 1. 初始化骨架
        if item_type == "Movie":
            payload = json.loads(json.dumps(utils.MOVIE_SKELETON_TEMPLATE))
        else:
            payload = json.loads(json.dumps(utils.SERIES_SKELETON_TEMPLATE))

        if not tmdb_data:
            return payload

        # 2. 基础字段直接覆盖 (排除特殊字段)
        exclude_keys = [
            'casts', 'releases', 'release_dates', 'keywords', 'trailers', 
            'content_ratings', 'videos', 'credits', 'genres', 
            'episodes_details', 'seasons_details', 'created_by', 'networks',
            'production_companies'
        ]
        for key in payload.keys():
            if key in tmdb_data and key not in exclude_keys:
                payload[key] = tmdb_data[key]

        # 3. 通用复杂字段处理
        # Genres: 优先 TMDb，Emby 兜底
        if 'genres' in tmdb_data and tmdb_data['genres']:
            payload['genres'] = tmdb_data['genres']
        elif emby_data_fallback and emby_data_fallback.get('Genres'):
            payload['genres'] = [{'id': 0, 'name': g} for g in emby_data_fallback['Genres']]

        # Keywords
        if 'keywords' in tmdb_data:
            kw_data = tmdb_data['keywords']
            if item_type == "Movie":
                if isinstance(kw_data, dict): payload['keywords']['keywords'] = kw_data.get('keywords', [])
                elif isinstance(kw_data, list): payload['keywords']['keywords'] = kw_data
            else:
                if isinstance(kw_data, dict): payload['keywords']['results'] = kw_data.get('results', [])
                elif isinstance(kw_data, list): payload['keywords']['results'] = kw_data

        # Videos / Trailers
        if 'videos' in tmdb_data:
            if item_type == "Movie":
                youtube_list = []
                for v in tmdb_data['videos'].get('results', []):
                    if v.get('site') == 'YouTube' and v.get('type') == 'Trailer':
                        youtube_list.append({
                            "name": v.get('name'), "size": str(v.get('size', 'HD')), 
                            "source": v.get('key'), "type": "Trailer"
                        })
                payload['trailers']['youtube'] = youtube_list
            else:
                payload['videos'] = tmdb_data['videos']

        # 手动处理 Studios 字段
        if 'production_companies' in tmdb_data:
            payload['production_companies'] = tmdb_data['production_companies']
        
        if 'networks' in tmdb_data:
            payload['networks'] = tmdb_data['networks']

        # 4. 类型特定处理
        if item_type == "Movie":
            # 演员表
            credits_source = tmdb_data.get('credits') or tmdb_data.get('casts') or {}
            if credits_source:
                payload['casts']['cast'] = credits_source.get('cast', [])
                payload['casts']['crew'] = credits_source.get('crew', [])
            
            # 分级
            apply_rating_logic(payload, tmdb_data, "Movie")

        elif item_type == "Series":
            # 演员表
            credits_source = tmdb_data.get('aggregate_credits') or tmdb_data.get('credits') or {}
            if credits_source:
                payload['credits']['cast'] = credits_source.get('cast', [])
                payload['credits']['crew'] = credits_source.get('crew', [])
            
            if 'created_by' in tmdb_data: payload['created_by'] = tmdb_data['created_by']
            if 'networks' in tmdb_data: payload['networks'] = tmdb_data['networks']
            
            # 外部ID
            if 'external_ids' in tmdb_data:
                ext_ids = tmdb_data['external_ids']
                if 'imdb_id' in ext_ids: payload['external_ids']['imdb_id'] = ext_ids['imdb_id']
                if 'tvdb_id' in ext_ids: payload['external_ids']['tvdb_id'] = ext_ids['tvdb_id']
                if 'tvrage_id' in ext_ids: payload['external_ids']['tvrage_id'] = ext_ids['tvrage_id']

            # 分级
            apply_rating_logic(payload, tmdb_data, "Series")

            # 挂载子项数据 (Seasons / Episodes)
            if aggregated_tmdb_data:
                payload['seasons_details'] = aggregated_tmdb_data.get('seasons_details', [])
                
                raw_episodes = aggregated_tmdb_data.get('episodes_details', {})
                formatted_episodes = {}
                
                # 统一处理分集骨架
                for key, ep_data in raw_episodes.items():
                    ep_skeleton = json.loads(json.dumps(utils.EPISODE_SKELETON_TEMPLATE))
                    
                    # 关键字段
                    ep_skeleton['id'] = ep_data.get('id') 
                    ep_skeleton['season_number'] = ep_data.get('season_number')
                    ep_skeleton['episode_number'] = ep_data.get('episode_number')
                    ep_skeleton['name'] = ep_data.get('name')
                    ep_skeleton['overview'] = ep_data.get('overview')
                    ep_skeleton['air_date'] = ep_data.get('air_date')
                    ep_skeleton['vote_average'] = ep_data.get('vote_average')
                    ep_skeleton['still_path'] = ep_data.get('still_path')
                    
                    # 演员
                    ep_credits = ep_data.get('credits', {})
                    ep_skeleton['credits']['cast'] = ep_credits.get('cast', []) 
                    ep_skeleton['credits']['guest_stars'] = ep_credits.get('guest_stars', [])
                    ep_skeleton['credits']['crew'] = ep_credits.get('crew', [])
                    
                    formatted_episodes[key] = ep_skeleton
                
                payload['episodes_details'] = formatted_episodes

        return payload

def reconstruct_metadata_from_db(db_row: Dict[str, Any], actors_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    【增强版】将数据库记录还原为符合本地 override 格式的标准元数据骨架。
    修复：填充 original_language 以解决 ID 冲突；填充导演、国家、总集数等缺失字段。
    """
    item_type = db_row.get('item_type')
    
    # 1. 初始化骨架
    if item_type == "Movie":
        payload = json.loads(json.dumps(utils.MOVIE_SKELETON_TEMPLATE))
    else:
        payload = json.loads(json.dumps(utils.SERIES_SKELETON_TEMPLATE))

    # 2. 基础字段映射
    payload['id'] = int(db_row.get('tmdb_id') or 0)
    payload['overview'] = db_row.get('overview')
    payload['original_language'] = db_row.get('original_language')
    payload['status'] = db_row.get('watchlist_tmdb_status')
    payload['backdrop_path'] = db_row.get('backdrop_path')
    payload['homepage'] = db_row.get('homepage')
    payload['vote_average'] = db_row.get('rating')
    payload['poster_path'] = db_row.get('poster_path')
    payload['tagline'] = db_row.get('tagline')

    # 标题与日期
    if item_type == "Movie":
        payload['title'] = db_row.get('title')
        payload['original_title'] = db_row.get('original_title')
        r_date = db_row.get('release_date')
        payload['release_date'] = str(r_date) if r_date else ''
        payload['runtime'] = db_row.get('runtime_minutes')
    else:
        payload['name'] = db_row.get('title')
        payload['original_name'] = db_row.get('original_title')
        r_date = db_row.get('release_date')
        payload['first_air_date'] = str(r_date) if r_date else ''
        l_date = db_row.get('last_air_date')
        payload['last_air_date'] = str(l_date) if l_date else ''
        payload['number_of_episodes'] = db_row.get('total_episodes', 0)
        # 数据库不存总季数，给个默认值 1，避免为 0
        payload['number_of_seasons'] = 1 
    
    # 3. 复杂 JSON 字段还原
    # Genres (类型)
    if db_row.get('genres_json'):
        try:
            raw_genres = db_row['genres_json']
            genres_data = json.loads(raw_genres) if isinstance(raw_genres, str) else raw_genres
            if genres_data:
                if isinstance(genres_data[0], str):
                    payload['genres'] = [{"id": 0, "name": g} for g in genres_data]
                else:
                    payload['genres'] = genres_data
        except Exception as e:
            logger.warning(f"还原 Genres 失败: {e}")

    # 1. 电影：只恢复制作公司
    if item_type == 'Movie':
        if db_row.get('production_companies_json'):
            try:
                raw = db_row['production_companies_json']
                data = json.loads(raw) if isinstance(raw, str) else raw
                if data: payload['production_companies'] = data
            except Exception: pass

    # 2. 剧集：合并 Networks + Companies -> 写入 networks
    elif item_type == 'Series':
        merged_list = []
        seen_ids = set()

        # A. 优先读取 Networks (权重高，如 CCTV-8)
        if db_row.get('networks_json'):
            try:
                raw = db_row['networks_json']
                nets = json.loads(raw) if isinstance(raw, str) else raw
                if nets:
                    for n in nets:
                        nid = n.get('id')
                        if nid and nid not in seen_ids:
                            merged_list.append(n)
                            seen_ids.add(nid)
            except Exception: pass

        # B. 补充读取 Companies (权重低，如 正午阳光)
        # 只有当 ID 不冲突时才加入。
        # 例子：如果 Networks 里有 521(CCTV-8)，Companies 里有 521(梦工厂)，这里会跳过梦工厂，保留 CCTV-8。
        # 例子：正午阳光 ID 是独立的，会成功加入。
        if db_row.get('production_companies_json'):
            try:
                raw = db_row['production_companies_json']
                comps = json.loads(raw) if isinstance(raw, str) else raw
                if comps:
                    for c in comps:
                        cid = c.get('id')
                        if cid and cid not in seen_ids:
                            merged_list.append(c)
                            seen_ids.add(cid)
            except Exception: pass

        # C. 写入 JSON
        if merged_list:
            # Emby 剧集只看 networks
            payload['networks'] = merged_list

    # Directors (导演/主创) -> 映射到 created_by 或 crew
    if db_row.get('directors_json'):
        try:
            raw_directors = db_row['directors_json']
            directors_list = json.loads(raw_directors) if isinstance(raw_directors, str) else raw_directors
            if directors_list:
                if item_type == 'Series':
                    # 剧集：数据库存的 directors 其实是 created_by
                    payload['created_by'] = directors_list
                else:
                    # 电影：放入 crew 并标记为 Director
                    crew_list = []
                    for d in directors_list:
                        crew_list.append({
                            "id": d.get('id'),
                            "name": d.get('name'),
                            "job": "Director",
                            "department": "Directing"
                        })
                    payload['casts']['crew'] = crew_list
        except Exception as e:
            logger.warning(f"还原 Directors 失败: {e}")

    # Countries (国家)
    if db_row.get('countries_json'):
        try:
            raw_countries = db_row['countries_json']
            countries_list = json.loads(raw_countries) if isinstance(raw_countries, str) else raw_countries
            if countries_list:
                # 数据库存的是代码列表 ["CN", "US"]
                if item_type == 'Series':
                    payload['origin_country'] = countries_list
                else:
                    # 电影需要对象列表
                    payload['production_countries'] = [{"iso_3166_1": c, "name": ""} for c in countries_list]
        except Exception as e:
            logger.warning(f"还原 Countries 失败: {e}")
        
    # Keywords (Tags)
    if db_row.get('keywords_json'):
        try:
            raw_kw = db_row['keywords_json']
            kw_list = json.loads(raw_kw) if isinstance(raw_kw, str) else raw_kw
            if kw_list:
                if item_type == "Movie":
                    payload['keywords']['keywords'] = kw_list
                else:
                    payload['keywords']['results'] = kw_list
        except Exception as e:
            logger.warning(f"还原 Keywords 失败: {e}")

    # 4. 演员表 (Cast)
    if actors_list:
        formatted_cast = []
        for i, actor in enumerate(actors_list):
            final_name = actor.get('name') or actor.get('original_name')
            formatted_cast.append({
                "id": actor.get('tmdb_id'),
                "name": final_name,
                "original_name": actor.get('original_name'),
                "character": actor.get('character') or actor.get('role'),
                "profile_path": actor.get('profile_path'),
                "order": actor.get('order', i),
                "known_for_department": "Acting"
            })
        
        if item_type == "Movie":
            payload['casts']['cast'] = formatted_cast
        else:
            payload['credits']['cast'] = formatted_cast

    # 5. 分级 (Official Rating)
    if db_row.get('official_rating_json'):
        try:
            raw_rating = db_row['official_rating_json']
            ratings_map = json.loads(raw_rating) if isinstance(raw_rating, str) else raw_rating
            
            rating_val = ratings_map.get('US')
            if not rating_val and ratings_map:
                rating_val = list(ratings_map.values())[0]
            
            if rating_val:
                payload['mpaa'] = rating_val
                payload['certification'] = rating_val
                
                if item_type == "Movie":
                    payload['releases']['countries'] = [{
                        "iso_3166_1": "US", "certification": rating_val, "release_date": "", "primary": True
                    }]
                else:
                    payload['content_ratings']['results'] = [{
                        "iso_3166_1": "US", "rating": rating_val
                    }]
        except Exception as e:
            logger.warning(f"还原 Rating 失败: {e}")

    return payload

# 1. 在参数中新增 text_only
def translate_tmdb_metadata_recursively(
    item_type: str, 
    tmdb_data: Dict[str, Any], 
    ai_translator: Any, 
    item_name: str = "",
    tmdb_api_key: str = None,
    config: dict = None,
    douban_cast_data: list = None,
    text_only: bool = False  # <--- 【新增参数】默认 False 保持兼容，True 时跳过演员
):
    """
    【大一统翻译引擎】递归翻译 TMDb 数据的标题、简介、标语、演员名和角色名。
    加入豆瓣字典拦截：优先使用豆瓣的官方中文数据，剥夺 AI 乱翻译的机会。
    加入智能兜底：如果豆瓣角色为"演员"，则交给 AI 翻译；若 AI 翻译失败(仍为全英文)，则使用"演员"兜底。
    """
    if not ai_translator or not tmdb_data or not config:
        return

    # --- 0. 初始化统计与配置 ---
    stats = {
        'original_cast_count': 0, 'truncated_cast_count': 0,
        'title_pending_count': 0, 'overview_pending_count': 0, 'tagline_pending_count': 0,
        'person_pending_count': 0, 'role_pending_count': 0,
        'title_cache_hits': 0, 'overview_cache_hits': 0, 'tagline_cache_hits': 0,
        'person_cache_hits': 0, 'role_cache_hits': 0,
        'title_needs_translation': 0, 'overview_needs_translation': 0, 'tagline_needs_translation': 0,
        'person_ai_calls': 0, 'role_ai_calls': 0
    }

    translate_title_enabled = config.get(constants.CONFIG_OPTION_AI_TRANSLATE_TITLE, False)
    translate_overview_enabled = config.get(constants.CONFIG_OPTION_AI_TRANSLATE_OVERVIEW, False)
    translate_ep_overview_enabled = config.get(constants.CONFIG_OPTION_AI_TRANSLATE_EPISODE_OVERVIEW, False)
    translate_role_enabled = config.get(constants.CONFIG_OPTION_AI_TRANSLATE_ACTOR_ROLE, False)
    remove_no_avatar = config.get(constants.CONFIG_OPTION_REMOVE_ACTORS_WITHOUT_AVATARS, True)
    
    try:
        max_actors = int(config.get(constants.CONFIG_OPTION_MAX_ACTORS_TO_PROCESS, 30))
    except (ValueError, TypeError):
        max_actors = 30
        
    translation_mode = config.get(constants.CONFIG_OPTION_AI_TRANSLATION_MODE, "fast")

    # 收集器
    pending_media = {} 
    actor_terms = {'person': set(), 'role': set()}
    actor_refs = []

    # =================================================================
    # ★★★ 构建豆瓣权威字典 ★★★
    # =================================================================
    douban_actor_map = {}
    if douban_cast_data:
        for d in douban_cast_data:
            en_name = (d.get('OriginalName') or '').lower().strip()
            zh_name = (d.get('Name') or '').strip()
            role = (d.get('Role') or '').strip()
            
            if en_name:
                douban_actor_map[en_name] = {'name': zh_name, 'role': role}
            if zh_name:
                douban_actor_map[zh_name.lower()] = {'name': zh_name, 'role': role}

    # --- 1. 媒体与演员遍历收集阶段 ---
    def _collect_single_item(data_dict: Dict, specific_item_type: str):
        current_tmdb_id = data_dict.get('id')
        if not current_tmdb_id: return
        tmdb_id_str = str(current_tmdb_id)
        
        # ========== A. 媒体信息收集 ==========
        title_key = 'title' if specific_item_type == 'Movie' else 'name'
        local_info = media_db.get_local_translation_info(tmdb_id_str, specific_item_type)
        
        needs_title, needs_overview, needs_tagline = False, False, False
        
        # A1. 简介 (Overview)
        is_ep = (specific_item_type == 'Episode')
        if (not is_ep and translate_overview_enabled) or (is_ep and translate_ep_overview_enabled):
            raw_tmdb_overview = data_dict.get('overview') or ''
            local_overview = local_info.get('overview') if local_info else ''
            
            # --- 第 1 步：清洗并检验 TMDb 官方数据的纯洁性 ---
            tmdb_overview = utils.clean_invisible_chars(raw_tmdb_overview)
            if utils.is_spam_title(tmdb_overview):
                tmdb_overview = "" # 发现广告，直接击杀，当它不存在
            
            # --- 第 2 步：仲裁逻辑 ---
            if tmdb_overview and utils.contains_chinese(tmdb_overview):
                # 只要 TMDb 有干净的官方中文，无论是电影、剧集还是分集，无条件以官方为准！
                # 直接覆盖（代码中不用特意写覆盖，因为 tmdb_data 里本身就是 tmdb_overview）
                # 注意：这里我们故意不加 cache_hits，因为用的是官方数据
                data_dict['overview'] = tmdb_overview 
            else:
                # TMDb 没中文（或者是广告被击杀了），那就看本地有没有货
                if local_overview and utils.contains_chinese(local_overview):
                    # 本地有货（不管是笑话还是机翻），顶上去
                    data_dict['overview'] = local_overview
                    stats['overview_cache_hits'] += 1
                else:
                    # 连本地都没货，准备摇人（呼叫 AI）
                    # 尝试拉取英文兜底，给 AI 翻译用
                    if not tmdb_overview and tmdb_api_key:
                        try:
                            if specific_item_type == 'Movie':
                                data_dict['overview'] = get_movie_details(int(tmdb_id_str), tmdb_api_key, language="en-US").get('overview', '')
                            elif specific_item_type == 'Series':
                                data_dict['overview'] = get_tv_details(int(tmdb_id_str), tmdb_api_key, language="en-US").get('overview', '')
                        except Exception: pass
                    
                    if data_dict.get('overview'):
                        needs_overview = True
                        stats['overview_pending_count'] += 1

        # A2. 标题 (Title)
        if translate_title_enabled:
            raw_title = data_dict.get(title_key) or ''
            current_title = utils.clean_invisible_chars(raw_title)
            if utils.is_spam_title(current_title):
                current_title = ""
            
            if current_title and utils.contains_chinese(current_title):
                # TMDb 官方有干净中文，无条件使用
                data_dict[title_key] = current_title
            else:
                local_title = local_info.get('title') if local_info else ''
                if local_title and utils.contains_chinese(local_title):
                    # 官方没有，用本地缓存
                    data_dict[title_key] = local_title
                    stats['title_cache_hits'] += 1
                else:
                    # 都没有，呼叫 AI
                    needs_title = True
                    stats['title_pending_count'] += 1

        # A3. 标语 (Tagline)
        if translate_title_enabled and specific_item_type in ['Movie', 'Series']:
            tagline = data_dict.get('tagline')
            if not tagline or not utils.contains_chinese(tagline):
                # 先用本地缓存回填，避免重复翻译
                if local_info and local_info.get('tagline') and utils.contains_chinese(local_info['tagline']):
                    data_dict['tagline'] = local_info['tagline']
                    stats['tagline_cache_hits'] += 1
                else:
                    # 本地没有中文标语，再去补英文原文，准备送翻译
                    if not tagline and tmdb_api_key:
                        try:
                            if specific_item_type == 'Movie':
                                en_data = get_movie_details(int(tmdb_id_str), tmdb_api_key, language="en-US")
                                data_dict['tagline'] = en_data.get('tagline', '')
                            elif specific_item_type == 'Series':
                                en_data = get_tv_details(int(tmdb_id_str), tmdb_api_key, language="en-US")
                                data_dict['tagline'] = en_data.get('tagline', '')
                        except Exception:
                            pass

                    if data_dict.get('tagline'):
                        needs_tagline = True
                        stats['tagline_pending_count'] += 1

        if needs_title or needs_overview or needs_tagline:
            pending_media[tmdb_id_str] = {
                "type": specific_item_type, "title_key": title_key,
                "title": data_dict.get(title_key) if needs_title else None,
                "overview": data_dict.get('overview') if needs_overview else None,
                "tagline": data_dict.get('tagline') if needs_tagline else None,
                "ref": data_dict 
            }

        # ========== B. 演员信息收集与截断 ==========
        # ★★★ 关键修改：如果启用了 text_only，直接退出，不处理演员 ★★★
        if text_only:
            return

        credits_dict = data_dict.get('credits') or data_dict.get('aggregate_credits') or data_dict.get('casts')
        if not credits_dict or 'cast' not in credits_dict: return

        cast_list = credits_dict['cast']
        stats['original_cast_count'] += len(cast_list)

        if remove_no_avatar:
            with_pic = [a for a in cast_list if a.get('profile_path')]
            no_pic = [a for a in cast_list if not a.get('profile_path')]
            with_pic.sort(key=lambda x: x.get('order', 999))
            no_pic.sort(key=lambda x: x.get('order', 999))
            cast_list[:] = (with_pic + no_pic)[:max_actors]
        else:
            cast_list.sort(key=lambda x: x.get('order', 999))
            cast_list[:] = cast_list[:max_actors]

        stats['truncated_cast_count'] += len(cast_list)

        # 收集翻译词条
        if translate_role_enabled:
            for actor in cast_list:
                orig_name = actor.get('original_name', '').lower().strip()
                curr_name = actor.get('name', '').lower().strip()
                
                # =========================================================
                # ★★★ 豆瓣防线 & 智能兜底 ★★★
                # =========================================================
                d_match = None
                if douban_actor_map:
                    # 双重匹配：原名或现名匹配上豆瓣都可以
                    d_match = douban_actor_map.get(orig_name) or douban_actor_map.get(curr_name)
                    
                if d_match:
                    if d_match['name'] and utils.contains_chinese(d_match['name']):
                        actor['name'] = d_match['name']
                    
                    d_role = d_match.get('role', '').strip()
                    if d_role and utils.contains_chinese(d_role):
                        if d_role == "演员":
                            # 记下豆瓣给的保底词汇，先不覆盖，给 AI 一个翻译原英文的机会
                            actor['_douban_fallback_role'] = "演员"
                        else:
                            actor['character'] = d_role

                # --- 豆瓣处理完后，如果还不是中文，才丢给 AI ---
                name = actor.get('name', '')
                if name and not utils.contains_chinese(name):
                    actor_terms['person'].add(name)
                    actor_refs.append((actor, 'name', name, 'person'))

                role = actor.get('character', '')
                if role:
                    cleaned_role = utils.clean_character_name_static(role)
                    actor['character'] = cleaned_role 
                    if not utils.contains_chinese(cleaned_role):
                        actor_terms['role'].add(cleaned_role)
                        actor_refs.append((actor, 'character', cleaned_role, 'role'))

    # 遍历入口
    if item_type == 'Movie':
        _collect_single_item(tmdb_data, 'Movie')
    elif item_type == 'Series':
        series_details = tmdb_data.get('series_details', tmdb_data)
        _collect_single_item(series_details, 'Series')
        for season in tmdb_data.get("seasons_details", []):
            _collect_single_item(season, 'Season')
        episodes_container = tmdb_data.get("episodes_details", {})
        episodes_list = episodes_container.values() if isinstance(episodes_container, dict) else episodes_container
        for ep in episodes_list:
            _collect_single_item(ep, 'Episode')

    stats['person_pending_count'] = len(actor_terms['person'])
    stats['role_pending_count'] = len(actor_terms['role'])

    # --- 2. AI 批量翻译与回填阶段 ---
    BATCH_SIZE = 20
    
    # [A] 处理媒体信息
    if pending_media:
        # 1. 简介
        overviews_to_translate = {k: v["overview"] for k, v in pending_media.items() if v["overview"]}
        if overviews_to_translate:
            # 修复：在这里一次性加上实际准备提交给 API 的总数
            stats['overview_needs_translation'] += len(overviews_to_translate)
            items_list = list(overviews_to_translate.items())
            for i in range(0, len(items_list), BATCH_SIZE):
                batch_dict = dict(items_list[i:i+BATCH_SIZE])
                trans_results = ai_translator.batch_translate_overviews(batch_dict, context_title=item_name)
                for tid, trans_text in trans_results.items():
                    if trans_text and utils.contains_chinese(trans_text) and tid in pending_media:
                        pending_media[tid]["ref"]['overview'] = trans_text

        # 2. 标语
        taglines_to_translate = {k: v["tagline"] for k, v in pending_media.items() if v["tagline"]}
        if taglines_to_translate:
            # 修复：在这里一次性加上实际准备提交给 API 的总数
            stats['tagline_needs_translation'] += len(taglines_to_translate)
            items_list = list(taglines_to_translate.items())
            for i in range(0, len(items_list), BATCH_SIZE):
                batch_dict = dict(items_list[i:i+BATCH_SIZE])
                trans_results = ai_translator.batch_translate_overviews(batch_dict, context_title=item_name)
                for tid, trans_text in trans_results.items():
                    if trans_text and utils.contains_chinese(trans_text) and tid in pending_media:
                        pending_media[tid]["ref"]['tagline'] = trans_text

        # 3. 标题
        titles_to_translate = {k: v["title"] for k, v in pending_media.items() if v["title"]}
        if titles_to_translate:
            # 修复：在这里一次性加上实际准备提交给 API 的总数
            stats['title_needs_translation'] += len(titles_to_translate)
            items_list = list(titles_to_translate.items())
            for i in range(0, len(items_list), BATCH_SIZE):
                batch_dict = dict(items_list[i:i+BATCH_SIZE])
                trans_results = ai_translator.batch_translate_titles(batch_dict, media_type="Episode")
                for tid, trans_text in trans_results.items():
                    if trans_text and utils.contains_chinese(trans_text) and tid in pending_media:
                        title_key = pending_media[tid]["title_key"]
                        pending_media[tid]["ref"][title_key] = trans_text

    # [B] 处理演员信息
    if translate_role_enabled and (actor_terms['person'] or actor_terms['role']):
        from database.connection import get_db_connection
        from database.actor_db import ActorDBManager
        
        final_actor_translation_map = {}
        api_submit_list = []
        all_actor_terms = list(actor_terms['person'].union(actor_terms['role']))
        actor_db = ActorDBManager()

        # 将人名和角色名拆分处理
        person_submit_list = []
        role_submit_list = []

        # Phase 1: 查库 (开启数据库连接)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 查人名缓存
            for term in actor_terms['person']:
                cached = actor_db.get_translation_from_db(cursor, term)
                if cached and cached.get('translated_text'):
                    final_actor_translation_map[term] = cached['translated_text']
                    stats['person_cache_hits'] += 1
                else:
                    person_submit_list.append(term)
                    stats['person_ai_calls'] += 1
                    
            # 查角色名缓存
            for term in actor_terms['role']:
                cached = actor_db.get_translation_from_db(cursor, term)
                if cached and cached.get('translated_text'):
                    final_actor_translation_map[term] = cached['translated_text']
                    stats['role_cache_hits'] += 1
                else:
                    role_submit_list.append(term)
                    stats['role_ai_calls'] += 1

        # Phase 2: 调用 AI API (数据库连接已释放)
        api_results_to_save = {}
        
        # 1. 人名：强制使用音译模式 (transliterate)
        if person_submit_list:
            logger.info(f"  ➜ 启动【音译模式】处理 {len(person_submit_list)} 个人名...")
            person_results = ai_translator.batch_translate(person_submit_list, mode="transliterate", title=item_name)
            if person_results:
                final_actor_translation_map.update(person_results)
                for k, v in person_results.items():
                    api_results_to_save[k] = (v, f"{ai_translator.provider}_transliterate")
                    
        # 2. 角色名：使用用户配置的模式 (fast 或 quality)
        if role_submit_list:
            logger.info(f"  ➜ 启动【{translation_mode}模式】处理 {len(role_submit_list)} 个角色名...")
            role_results = ai_translator.batch_translate(role_submit_list, mode=translation_mode, title=item_name)
            if role_results:
                final_actor_translation_map.update(role_results)
                for k, v in role_results.items():
                    api_results_to_save[k] = (v, f"{ai_translator.provider}_{translation_mode}")

        # Phase 3: 写库 (重新开启数据库连接)
        if api_results_to_save:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for term, (translated, engine_used) in api_results_to_save.items():
                    actor_db.save_translation_to_db(cursor, term, translated, engine_used)

        # =========================================================
        # ★★★ 智能回填与终极兜底判断 ★★★
        # =========================================================
        # 1. 回填 AI 结果
        for actor_dict, field_key, orig_text, t_type in actor_refs:
            if orig_text in final_actor_translation_map:
                actor_dict[field_key] = final_actor_translation_map[orig_text]
        
        # 2. 全局统一兜底
        for actor_dict, field_key, orig_text, t_type in actor_refs:
            if t_type == 'role':
                current_val = actor_dict.get(field_key, '')
                # 规则：只要是角色名，且最终(无论是原版还是AI翻译后)没有中文，一律强行设为"演员"
                if not utils.contains_chinese(current_val):
                    actor_dict[field_key] = "演员"
            
            # 清理临时字段
            actor_dict.pop('_douban_fallback_role', None)

    # --- 3. 统计汇总日志输出 ---
    total_pending = (
        stats['title_pending_count'] + stats['overview_pending_count'] +
        stats['tagline_pending_count'] + stats['person_pending_count'] + stats['role_pending_count']
    )
    if total_pending > 0 or stats['original_cast_count'] > 0:
        logger.info("  ➜ [AI翻译引擎] 翻译统计汇总")
        logger.info(
            f"  ➜ 演员节点: 原始 {stats['original_cast_count']} 人 → "
            f"最终保留 {stats['truncated_cast_count']} 人（含剧/季/集）"
        )
        logger.info(
            f"  ➜ 待翻词条: 标题 {stats['title_pending_count']} | "
            f"简介 {stats['overview_pending_count']} | "
            f"标语 {stats['tagline_pending_count']} | "
            f"人名 {stats['person_pending_count']} | "
            f"角色 {stats['role_pending_count']}"
        )
        logger.info(
            f"  ➜ 缓存命中: 标题 {stats['title_cache_hits']} | "
            f"简介 {stats['overview_cache_hits']} | "
            f"标语 {stats['tagline_cache_hits']} | "
            f"人名 {stats['person_cache_hits']} | "
            f"角色 {stats['role_cache_hits']}"
        )
        logger.info(
            f"  ➜ 实际提交: 标题 {stats['title_needs_translation']} | "
            f"简介 {stats['overview_needs_translation']} | "
            f"标语 {stats['tagline_needs_translation']} | "
            f"人名 {stats['person_ai_calls']} | "
            f"角色 {stats['role_ai_calls']}"
        )