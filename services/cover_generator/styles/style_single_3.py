# services/cover_generator/styles/style_single_3.py

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import logging
from .style_single_2 import darken_color, find_dominant_vibrant_colors
from .style_single_1 import image_to_base64
from .badge_drawer import draw_badge

logger = logging.getLogger(__name__)
canvas_size = (1920, 1080)

def create_style_single_3(image_path, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        zh_font_path, en_font_path = font_path
        title_zh, title_en = title
        zh_font_size_ratio, en_font_size_ratio = font_size
        
        src = Image.open(image_path).convert("RGB")
        bg = ImageOps.fit(src, canvas_size, method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=int(blur_size)))
        
        colors = find_dominant_vibrant_colors(src, num_colors=5)
        tint = darken_color(colors[0] if colors else (120, 120, 120), 0.82)
        
        mixed = np.clip(np.array(bg, float) * (1 - float(color_ratio)) + np.array([[tint]], float) * float(color_ratio), 0, 255).astype(np.uint8)
        frame = Image.fromarray(mixed).convert("RGBA")

        # 字体逻辑与 single 1 看齐
        zh_font_size = int(canvas_size[1] * 0.17 * float(zh_font_size_ratio))
        en_font_size = int(canvas_size[1] * 0.07 * float(en_font_size_ratio))
        zh_font = ImageFont.truetype(str(zh_font_path), zh_font_size)
        en_font = ImageFont.truetype(str(en_font_path), en_font_size)
        
        txt_layer = Image.new("RGBA", canvas_size, (0,0,0,0))
        shadow_layer = Image.new("RGBA", canvas_size, (0,0,0,0))
        draw, sdraw = ImageDraw.Draw(txt_layer), ImageDraw.Draw(shadow_layer)
        
        shadow_color, text_color = darken_color(tint, 0.65) + (92,), (255, 255, 255, 230)
        cx, cy = canvas_size[0] // 2, canvas_size[1] // 2
        
        zh_bbox = draw.textbbox((0, 0), title_zh, font=zh_font)
        zh_w, zh_h = zh_bbox[2] - zh_bbox[0], zh_bbox[3] - zh_bbox[1]
        
        en_lines, en_spacing, total_en_h = [], int(en_font_size * 0.3), 0
        if title_en:
            if draw.textbbox((0, 0), title_en, font=en_font)[2] > zh_w and " " in title_en:
                words = title_en.split(" ")
                curr_line = words[0]
                for w in words[1:]:
                    test_line = curr_line + " " + w
                    if draw.textbbox((0, 0), test_line, font=en_font)[2] > zh_w:
                        en_lines.append(curr_line); curr_line = w
                    else: curr_line = test_line
                if curr_line: en_lines.append(curr_line)
            else: en_lines = [title_en]
            for line in en_lines: total_en_h += draw.textbbox((0, 0), line, font=en_font)[3] + en_spacing
            total_en_h -= en_spacing

        title_spacing = 40 if title_en else 0
        total_text_y = cy - (zh_h + total_en_h + title_spacing) // 2

        zh_x, zh_y = cx - zh_w // 2, total_text_y
        for off in range(3, 11, 2): sdraw.text((zh_x+off, zh_y+off), title_zh, font=zh_font, fill=shadow_color)
        draw.text((zh_x, zh_y), title_zh, font=zh_font, fill=text_color)
        
        if en_lines:
            en_y = zh_y + zh_h + title_spacing
            for i, line in enumerate(en_lines):
                lb = draw.textbbox((0, 0), line, font=en_font)
                ex = cx - (lb[2] - lb[0]) // 2
                cy_pos = en_y + i * (lb[3] - lb[1] + en_spacing)
                for off in range(2, 8, 2): sdraw.text((ex+off, cy_pos+off), line, font=en_font, fill=shadow_color)
                draw.text((ex, cy_pos), line, font=en_font, fill=text_color)

        frame = Image.alpha_composite(frame, shadow_layer.filter(ImageFilter.GaussianBlur(8)))
        frame = Image.alpha_composite(frame, txt_layer)
        
        if config and config.get("show_item_count", False) and item_count is not None:
            frame = draw_badge(image=frame, item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=tint)
            
        return image_to_base64(frame)

    except Exception as e:
        logger.error(f"创建 style_single_3 失败: {e}", exc_info=True)
        return False