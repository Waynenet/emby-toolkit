# services/cover_generator/styles/style_single_2.py

import logging
import random
import base64
from io import BytesIO
from collections import Counter
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from .badge_drawer import draw_badge
from .style_single_1 import is_not_black_white_gray_near, rgb_to_hsv, hsv_to_rgb, darken_color, add_film_grain, image_to_base64

logger = logging.getLogger(__name__)
canvas_size = (1920, 1080)

def adjust_to_macaron(h, s, v): return min(max(s, 0.2), 0.7), min(max(v, 0.55), 0.85)

def find_dominant_vibrant_colors(image, num_colors=5):
    img = image.copy()
    img.thumbnail((100, 100))
    filtered_pixels = [p for p in list(img.convert('RGB').getdata()) if is_not_black_white_gray_near(p)]
    if not filtered_pixels: return []
    macaron_colors, seen_hues = [], set()
    for color, count in Counter(filtered_pixels).most_common(num_colors * 3):
        h, s, v = rgb_to_hsv(color)
        adj_s, adj_v = adjust_to_macaron(h, s, v)
        adj_rgb = hsv_to_rgb(h, adj_s, adj_v)
        if not any(abs(int(h * 360) - seen) < 15 for seen in seen_hues) and adj_rgb not in macaron_colors:
            macaron_colors.append(adj_rgb)
            seen_hues.add(int(h * 360))
            if len(macaron_colors) >= num_colors: break
    return macaron_colors

def align_image_right(img, canvas_size):
    target_width = int(canvas_size[0] * 0.675)
    resized = img.resize((int(img.width * (canvas_size[1] / img.height)), canvas_size[1]), Image.LANCZOS)
    if resized.width < target_width:
        resized = img.resize((target_width, int(img.height * (target_width / img.width))), Image.LANCZOS)
        if resized.height > canvas_size[1]: resized = resized.crop((0, (resized.height - canvas_size[1]) // 2, target_width, (resized.height + canvas_size[1]) // 2))
        final = Image.new("RGB", canvas_size)
        final.paste(resized, (canvas_size[0] - target_width, 0))
        return final
    crop_left = max(0, min(resized.width / 2 - target_width / 2, resized.width - target_width))
    cropped = resized.crop((int(crop_left), 0, int(crop_left + target_width), canvas_size[1]))
    final = Image.new("RGB", canvas_size)
    final.paste(cropped, (canvas_size[0] - cropped.width + int(canvas_size[0] * 0.075), 0))
    return final

def create_diagonal_mask(size, split_top=0.5, split_bottom=0.33):
    mask = Image.new('L', size, 255)
    ImageDraw.Draw(mask).polygon([(int(size[0] * split_top), 0), (size[0], 0), (size[0], size[1]), (int(size[0] * split_bottom), size[1])], fill=0)
    return mask

def create_shadow_mask(size, split_top=0.5, split_bottom=0.33, feather_size=40):
    mask = Image.new('L', size, 0)
    shadow_width = feather_size // 3
    top_x, bottom_x = int(size[0] * split_top), int(size[0] * split_bottom)
    ImageDraw.Draw(mask).polygon([(top_x - 5, 0), (top_x - 5 + shadow_width, 0), (bottom_x - 5 + shadow_width, size[1]), (bottom_x - 5, size[1])], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(radius=feather_size//3))

def create_style_single_2(image_path, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        zh_font_path, en_font_path = font_path
        title_zh, title_en = title
        zh_font_size_ratio, en_font_size_ratio = font_size

        if int(blur_size) < 0: blur_size = 50
        if not (0 <= float(color_ratio) <= 1): color_ratio = 0.8
        if not float(zh_font_size_ratio) > 0: zh_font_size_ratio = 1
        if not float(en_font_size_ratio) > 0: en_font_size_ratio = 1

        split_top, split_bottom = 0.55, 0.4
        fg_img_original = Image.open(image_path).convert("RGB")
        fg_img = align_image_right(fg_img_original, canvas_size)
        
        vibrant_colors = find_dominant_vibrant_colors(fg_img)
        bg_color = vibrant_colors[0] if vibrant_colors else random.choice([(237, 159, 77), (255, 183, 197), (186, 225, 255), (255, 223, 186), (202, 231, 200)])
        base_color_for_badge = bg_color
        shadow_color = darken_color(bg_color, 0.5)
        
        bg_img = ImageOps.fit(fg_img_original, canvas_size, method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=int(blur_size)))
        dark_bg = darken_color(bg_color, 0.85)
        blended_bg = np.clip(np.array(bg_img, float) * (1 - float(color_ratio)) + np.array([[dark_bg]], float) * float(color_ratio), 0, 255).astype(np.uint8)
        
        diagonal_mask = create_diagonal_mask(canvas_size, split_top, split_bottom)
        temp_canvas = Image.new('RGB', canvas_size)
        temp_canvas.paste(fg_img)
        temp_canvas.paste(Image.new('RGB', canvas_size, shadow_color), mask=create_shadow_mask(canvas_size, split_top, split_bottom, 30))
        canvas = Image.composite(add_film_grain(Image.fromarray(blended_bg), 0.05), temp_canvas, diagonal_mask).convert('RGBA')
        
        # 文字处理
        text_layer = Image.new('RGBA', canvas_size, (255, 255, 255, 0))
        shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        shadow_draw, draw = ImageDraw.Draw(shadow_layer), ImageDraw.Draw(text_layer)   
        
        left_area_center_x = int(canvas_size[0] * 0.25)
        left_area_center_y = canvas_size[1] // 2
        zh_font_size = int(canvas_size[1] * 0.17 * float(zh_font_size_ratio))
        en_font_size = int(canvas_size[1] * 0.07 * float(en_font_size_ratio))
        zh_font = ImageFont.truetype(str(zh_font_path), zh_font_size)
        en_font = ImageFont.truetype(str(en_font_path), en_font_size)
        
        text_color, text_shadow_color, shadow_offset = (255, 255, 255, 229), darken_color(dark_bg, 0.8) + (75,), 12
        
        zh_bbox = draw.textbbox((0, 0), title_zh, font=zh_font)
        zh_w, zh_h = zh_bbox[2] - zh_bbox[0], zh_bbox[3] - zh_bbox[1]
        zh_offset_y = zh_bbox[1]
        
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
            
            for line in en_lines: 
                lb = draw.textbbox((0, 0), line, font=en_font)
                total_en_h += (lb[3] - lb[1]) + en_spacing
            total_en_h -= en_spacing

        title_spacing = 40 if title_en else 0
        total_text_y = left_area_center_y - (zh_h + total_en_h + title_spacing) // 2

        zh_x = left_area_center_x - zh_w // 2
        zh_y = total_text_y - zh_offset_y
        for offset in range(3, shadow_offset + 1, 2):
            shadow_draw.text((zh_x + offset, zh_y + offset), title_zh, font=zh_font, fill=text_shadow_color)
        draw.text((zh_x, zh_y), title_zh, font=zh_font, fill=text_color)
        
        if en_lines:
            curr_en_y = total_text_y + zh_h + title_spacing
            for line in en_lines:
                lb = draw.textbbox((0, 0), line, font=en_font)
                ex = left_area_center_x - (lb[2] - lb[0]) // 2
                cy = curr_en_y - lb[1]
                for offset in range(2, shadow_offset // 2 + 1):
                    shadow_draw.text((ex + offset, cy + offset), line, font=en_font, fill=text_shadow_color)
                draw.text((ex, cy), line, font=en_font, fill=text_color)
                curr_en_y += (lb[3] - lb[1]) + en_spacing

        combined = Image.alpha_composite(canvas, shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_offset)))
        combined = Image.alpha_composite(combined, text_layer)

        if config and config.get("show_item_count", False) and item_count is not None:
            combined = draw_badge(image=combined.convert('RGBA'), item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=base_color_for_badge)

        return image_to_base64(combined)
    except Exception as e:
        logger.error(f"创建单图封面(style 2)时出错: {e}", exc_info=True)
        return False