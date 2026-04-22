# services/cover_generator/styles/style_dynamic_3.py

import math
import numpy as np
import logging
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from gevent import sleep
from .style_single_2 import darken_color, find_dominant_vibrant_colors
from .badge_drawer import draw_badge
from .style_dynamic_1 import frames_to_base64

logger = logging.getLogger(__name__)
canvas_size = (640, 360)

def create_style_dynamic_3(image_paths, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        scale = canvas_size[1] / 1080.0
        assets = []
        for p in image_paths[:5]:
            try:
                src = Image.open(p).convert("RGB")
                bg = ImageOps.fit(src, canvas_size, method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(max(8, int(blur_size * scale))))
                colors = find_dominant_vibrant_colors(src, 5)
                tint = darken_color(colors[0] if colors else (120, 120, 120), 0.82)
                assets.append({'bg': Image.fromarray(np.clip(np.array(bg, float) * (1 - float(color_ratio)) + np.array([[tint]], float) * float(color_ratio), 0, 255).astype(np.uint8)).convert("RGBA"), 'tint': tint})
            except Exception: pass
            
        if not assets: return False

        zh_font_size = int(1080 * 0.17 * float(font_size[0]) * scale)
        en_font_size = int(1080 * 0.07 * float(font_size[1]) * scale)
        zh_f = ImageFont.truetype(str(font_path[0]), max(1, zh_font_size))
        en_f = ImageFont.truetype(str(font_path[1]), max(1, en_font_size))
        
        texts = []
        for item in assets:
            txt_layer = Image.new('RGBA', canvas_size, (255, 255, 255, 0))
            shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
            shadow_draw, draw = ImageDraw.Draw(shadow_layer), ImageDraw.Draw(txt_layer)
            
            cx, cy = canvas_size[0] // 2, canvas_size[1] // 2
            text_color, shadow_color, shadow_offset = (255, 255, 255, 230), darken_color(item['tint'], 0.65) + (92,), max(3, int(10*scale))
            
            zh_bbox = draw.textbbox((0, 0), title[0], font=zh_f)
            zh_w, zh_h = zh_bbox[2] - zh_bbox[0], zh_bbox[3] - zh_bbox[1]
            zh_offset_y = zh_bbox[1]
            
            en_lines, en_spacing, total_en_h = [], int(en_font_size * 0.3), 0
            if title[1]:
                if draw.textbbox((0, 0), title[1], font=en_f)[2] > zh_w and " " in title[1]:
                    words = title[1].split(" ")
                    curr_line = words[0]
                    for w in words[1:]:
                        test_line = curr_line + " " + w
                        if draw.textbbox((0, 0), test_line, font=en_f)[2] > zh_w:
                            en_lines.append(curr_line); curr_line = w
                        else: curr_line = test_line
                    if curr_line: en_lines.append(curr_line)
                else: en_lines = [title[1]]
                for line in en_lines: 
                    lb = draw.textbbox((0, 0), line, font=en_f)
                    total_en_h += (lb[3] - lb[1]) + en_spacing
                total_en_h -= en_spacing

            title_spacing = int(40*scale) if title[1] else 0
            total_text_y = cy - (zh_h + total_en_h + title_spacing) // 2

            zh_x = cx - zh_w // 2
            zh_y = total_text_y - zh_offset_y
            
            for offset in range(3, shadow_offset + 1, 2): shadow_draw.text((zh_x + offset, zh_y + offset), title[0], font=zh_f, fill=shadow_color)
            draw.text((zh_x, zh_y), title[0], font=zh_f, fill=text_color)
            
            if en_lines:
                curr_en_y = total_text_y + zh_h + title_spacing
                for i, line in enumerate(en_lines):
                    lb = draw.textbbox((0, 0), line, font=en_f)
                    ex = cx - (lb[2] - lb[0]) // 2
                    cy_pos = curr_en_y - lb[1]
                    for offset in range(2, shadow_offset // 2 + 1): shadow_draw.text((ex + offset, cy_pos + offset), line, font=en_f, fill=shadow_color)
                    draw.text((ex, cy_pos), line, font=en_f, fill=text_color)
                    curr_en_y += (lb[3] - lb[1]) + en_spacing
                    
            txt = Image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_offset)), txt_layer)
            if config and config.get("show_item_count", False) and item_count is not None:
                txt = draw_badge(image=txt, item_count=item_count, font_path=font_path[0], style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=item['tint'])
            texts.append(txt)

        frames, n = [], len(assets)
        for f in range(90):
            sleep(0.01)
            idx, t = int(f / 90 * n) % n, 0.5 * (1.0 - math.cos(math.pi * max(0.0, min(1.0, (f / 90 * n) % 1))))
            nxt = (idx + 1) % n
            frame = Image.alpha_composite(Image.blend(assets[idx]['bg'], assets[nxt]['bg'], t), Image.blend(texts[idx], texts[nxt], t))
            frames.append(frame.convert("RGB"))

        return frames_to_base64(frames)
    except Exception as e:
        logger.error(f"创建 style_dynamic_3 失败: {e}", exc_info=True)
        return False