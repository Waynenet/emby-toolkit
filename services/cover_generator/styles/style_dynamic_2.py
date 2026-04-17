# services/cover_generator/styles/style_dynamic_2.py

import base64
import math
import io
import numpy as np
import logging
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from gevent import sleep
from .style_single_2 import (
    add_film_grain, align_image_right, darken_color, find_dominant_vibrant_colors
)
from .badge_drawer import draw_badge

logger = logging.getLogger(__name__)

canvas_size = (640, 360)

def _clamp(v, lo, hi): return max(lo, min(hi, v))
def _ease_in_out_sine(t): return 0.5 * (1.0 - math.cos(math.pi * _clamp(t, 0.0, 1.0)))

def _create_dynamic_diagonal_mask(size, top_x, bottom_x):
    mask = Image.new("L", size, 255)
    ImageDraw.Draw(mask).polygon([(top_x, 0), (size[0], 0), (size[0], size[1]), (bottom_x, size[1])], fill=0)
    return mask

def _create_dynamic_shadow_mask(size, top_x, bottom_x, feather_size=12):
    mask = Image.new("L", size, 0)
    edge_w = max(2, feather_size // 2)
    ImageDraw.Draw(mask).polygon([(top_x - 2, 0), (top_x - 2 + edge_w, 0), (bottom_x - 2 + edge_w, size[1]), (bottom_x - 2, size[1])], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(radius=max(2, feather_size // 2)))

def create_style_dynamic_2(image_paths, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        scale = canvas_size[1] / 1080.0
        zh_font_path, en_font_path = font_path
        title_zh, title_en = title
        
        target_w, target_h = canvas_size
        split_top_start = int(target_w * 0.55)
        split_bottom_start = int(target_w * 0.40)
        static_mask = _create_dynamic_diagonal_mask((target_w, target_h), split_top_start, split_bottom_start)
        static_shadow_mask = _create_dynamic_shadow_mask((target_w, target_h), split_top_start, split_bottom_start, feather_size=max(8, int(target_h * 0.08)))

        assets = []
        for p in image_paths[:5]:
            try:
                src = Image.open(p).convert("RGB")
                fg = align_image_right(src, canvas_size).convert("RGBA")
                colors = find_dominant_vibrant_colors(fg)
                bg_color = colors[0] if colors else (120, 120, 120)

                bg_img = ImageOps.fit(src, canvas_size, method=Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(radius=max(1, int(blur_size * scale))))
                bg_mix = Image.blend(bg_img, Image.new("RGB", canvas_size, darken_color(bg_color, 0.85)), float(color_ratio))
                bg = add_film_grain(bg_mix, intensity=0.03).convert("RGBA")
                
                assets.append({'fg': fg, 'bg': bg, 'shadow': darken_color(bg_color, 0.5), 'badge': bg_color})
            except Exception: pass
            
        if not assets: return False

        text_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        draw, sdraw = ImageDraw.Draw(text_layer), ImageDraw.Draw(shadow_layer)
        
        zh_sz = max(1, int(170 * float(font_size[0]) * scale))
        en_sz = max(1, int(75 * float(font_size[1]) * scale))
        zh_font = ImageFont.truetype(zh_font_path, zh_sz)
        en_font = ImageFont.truetype(en_font_path, en_sz)
        
        cx, cy = int(target_w * 0.25), int(target_h * 0.5)
        text_color = (255, 255, 255, 232)
        shadow_color = darken_color(assets[0]['badge'], 0.8) + (78,)
        
        zh_bbox = draw.textbbox((0, 0), title_zh, font=zh_font)
        zh_x, zh_y = cx - (zh_bbox[2]-zh_bbox[0])//2, cy - (zh_bbox[3]-zh_bbox[1])
        for off in range(3, 11, 2): sdraw.text((zh_x+off, zh_y+off), title_zh, font=zh_font, fill=shadow_color)
        draw.text((zh_x, zh_y), title_zh, font=zh_font, fill=text_color)
        
        if title_en:
            en_bbox = draw.textbbox((0, 0), title_en, font=en_font)
            ex, ey = cx - (en_bbox[2]-en_bbox[0])//2, zh_y + (zh_bbox[3]-zh_bbox[1]) + int(40*scale)
            for off in range(2, 6, 2): sdraw.text((ex+off, ey+off), title_en, font=en_font, fill=shadow_color)
            draw.text((ex, ey), title_en, font=en_font, fill=text_color)

        static_text = Image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(8)), text_layer)
        if config and config.get("show_item_count", False) and item_count is not None:
            static_text = draw_badge(image=static_text, item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=assets[0]['badge'])

        frames = []
        n_imgs = len(assets)
        total_frames = 15 * 6 

        for f in range(total_frames):
            sleep(0.01) # ★ 防卡死
            phase = f / total_frames
            cycle = phase * n_imgs
            idx, nxt = int(cycle) % n_imgs, (int(cycle) + 1) % n_imgs
            local = cycle - int(cycle)
            
            t = _ease_in_out_sine(local)
            c_fg = Image.blend(assets[idx]['fg'], assets[nxt]['fg'], t)
            c_bg = Image.blend(assets[idx]['bg'], assets[nxt]['bg'], t)
            
            c_s = tuple(int(assets[idx]['shadow'][k]*(1-t) + assets[nxt]['shadow'][k]*t) for k in range(3))
            
            temp = Image.new('RGBA', canvas_size)
            temp.paste(c_fg)
            temp.paste(Image.new('RGBA', canvas_size, c_s + (255,)), mask=static_shadow_mask)
            
            frame = Image.composite(c_bg, temp, static_mask)
            frame = Image.alpha_composite(frame, static_text)
            frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=255))

        buffer = io.BytesIO()
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=66, loop=0, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    except Exception as e:
        logger.error(f"创建 style_dynamic_2 失败: {e}", exc_info=True)
        return False