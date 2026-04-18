# services/cover_generator/styles/style_dynamic_2.py

import math
import numpy as np
import logging
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from gevent import sleep
from .style_single_2 import add_film_grain, align_image_right, darken_color, find_dominant_vibrant_colors, create_diagonal_mask, create_shadow_mask
from .badge_drawer import draw_badge
from .style_dynamic_1 import frames_to_base64

logger = logging.getLogger(__name__)
canvas_size = (640, 360)

def _ease_in_out_sine(t): return 0.5 * (1.0 - math.cos(math.pi * max(0.0, min(1.0, t))))

def create_style_dynamic_2(image_paths, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        scale = canvas_size[1] / 1080.0
        target_w, target_h = canvas_size
        static_mask = create_diagonal_mask(canvas_size, 0.55, 0.40)
        static_s_mask = create_shadow_mask(canvas_size, 0.55, 0.40, max(8, int(target_h * 0.08)))

        assets = []
        for p in image_paths[:5]:
            try:
                src = Image.open(p).convert("RGB")
                fg = align_image_right(src, canvas_size).convert("RGBA")
                bg_c = find_dominant_vibrant_colors(fg)[0] if find_dominant_vibrant_colors(fg) else (120, 120, 120)
                bg = add_film_grain(Image.blend(ImageOps.fit(src, canvas_size, method=Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(max(1, int(blur_size*scale)))), Image.new("RGB", canvas_size, darken_color(bg_c, 0.85)), float(color_ratio)), 0.03).convert("RGBA")
                assets.append({'fg': fg, 'bg': bg, 'shadow': darken_color(bg_c, 0.5), 'badge': bg_c})
            except Exception: pass
            
        if not assets: return False
        
        # 字体计算同 single_1
        zh_font_size = int(1080 * 0.17 * float(font_size[0]) * scale)
        en_font_size = int(1080 * 0.07 * float(font_size[1]) * scale)
        zh_font = ImageFont.truetype(font_path[0], max(1, zh_font_size))
        en_font = ImageFont.truetype(font_path[1], max(1, en_font_size))
        
        text_layer = Image.new('RGBA', canvas_size, (255, 255, 255, 0))
        shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        shadow_draw, draw = ImageDraw.Draw(shadow_layer), ImageDraw.Draw(text_layer)
        
        cx, cy = int(target_w * 0.25), target_h // 2
        text_color, text_shadow_color, shadow_offset = (255, 255, 255, 232), darken_color(assets[0]['badge'], 0.8) + (78,), max(3, int(12*scale))
        
        # 换行算法
        zh_bbox = draw.textbbox((0, 0), title[0], font=zh_font)
        zh_w, zh_h = zh_bbox[2] - zh_bbox[0], zh_bbox[3] - zh_bbox[1]
        en_lines, en_spacing, total_en_h = [], int(en_font_size * 0.3), 0
        
        if title[1]:
            if draw.textbbox((0, 0), title[1], font=en_font)[2] > zh_w and " " in title[1]:
                words = title[1].split(" ")
                curr_line = words[0]
                for w in words[1:]:
                    test_line = curr_line + " " + w
                    if draw.textbbox((0, 0), test_line, font=en_font)[2] > zh_w:
                        en_lines.append(curr_line); curr_line = w
                    else: curr_line = test_line
                if curr_line: en_lines.append(curr_line)
            else: en_lines = [title[1]]
            for line in en_lines: total_en_h += draw.textbbox((0, 0), line, font=en_font)[3] + en_spacing
            total_en_h -= en_spacing

        title_spacing = int(40*scale) if title[1] else 0
        zh_y = cy - (zh_h + total_en_h + title_spacing) // 2
        zh_x = cx - zh_w // 2
        
        for offset in range(3, shadow_offset + 1, 2): shadow_draw.text((zh_x + offset, zh_y + offset), title[0], font=zh_font, fill=text_shadow_color)
        draw.text((zh_x, zh_y), title[0], font=zh_font, fill=text_color)
        
        if en_lines:
            en_y = zh_y + zh_h + title_spacing
            for i, line in enumerate(en_lines):
                lb = draw.textbbox((0, 0), line, font=en_font)
                ex = cx - (lb[2] - lb[0]) // 2
                cy_pos = en_y + i * (lb[3] - lb[1] + en_spacing)
                for offset in range(2, shadow_offset // 2 + 1): shadow_draw.text((ex + offset, cy_pos + offset), line, font=en_font, fill=text_shadow_color)
                draw.text((ex, cy_pos), line, font=en_font, fill=text_color)
                
        static_text = Image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_offset)), text_layer)
        
        if config and config.get("show_item_count", False) and item_count is not None:
            static_text = draw_badge(image=static_text, item_count=item_count, font_path=font_path[0], style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=assets[0]['badge'])

        frames, n = [], len(assets)
        for f in range(90):
            sleep(0.01)
            idx, t = int(f / 90 * n) % n, _ease_in_out_sine((f / 90 * n) % 1)
            nxt = (idx + 1) % n
            
            temp = Image.new('RGBA', canvas_size)
            temp.paste(Image.blend(assets[idx]['fg'], assets[nxt]['fg'], t))
            temp.paste(Image.new('RGBA', canvas_size, tuple(int(assets[idx]['shadow'][k]*(1-t) + assets[nxt]['shadow'][k]*t) for k in range(3)) + (255,)), mask=static_s_mask)
            
            frame = Image.alpha_composite(Image.composite(Image.blend(assets[idx]['bg'], assets[nxt]['bg'], t), temp, static_mask), static_text)
            frames.append(frame.convert("RGB"))
            
        return frames_to_base64(frames)
    except Exception as e:
        logger.error(f"创建 style_dynamic_2 失败: {e}", exc_info=True)
        return False