# services/cover_generator/styles/style_multi_1.py

import logging
import os
import random
import math
from pathlib import Path
from collections import Counter
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from .badge_drawer import draw_badge
from .style_single_1 import add_film_grain, darken_color, image_to_base64
from .style_single_2 import find_dominant_vibrant_colors

logger = logging.getLogger(__name__)

POSTER_GEN_CONFIG = {
    "ROWS": 3, "COLS": 3, "MARGIN": 22, "CORNER_RADIUS": 46.1, "ROTATION_ANGLE": -15.8,
    "START_X": 850, "START_Y": -362, "COLUMN_SPACING": 100, "SAVE_COLUMNS": True,
    "CELL_WIDTH": 410, "CELL_HEIGHT": 610, "CANVAS_WIDTH": 1920, "CANVAS_HEIGHT": 1080,
}

def add_shadow(img, offset=(5, 5), shadow_color=(0, 0, 0, 100), blur_radius=3):
    shadow = Image.new("RGBA", (img.width + offset[0] + blur_radius * 2, img.height + offset[1] + blur_radius * 2), (0, 0, 0, 0))
    shadow.paste(Image.new("RGBA", img.size, shadow_color), (blur_radius + offset[0], blur_radius + offset[1]))
    result = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
    result.paste(img, (blur_radius, blur_radius), img if img.mode == "RGBA" else None)
    return Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(blur_radius)), result)

def draw_text_on_image(image, text, position, font_path, font_size, fill_color=(255, 255, 255, 255), shadow=False, shadow_color=None, shadow_offset=10, shadow_alpha=75):
    img_copy = image.copy()
    text_layer, shadow_layer = Image.new('RGBA', img_copy.size, (255, 255, 255, 0)), Image.new('RGBA', img_copy.size, (0, 0, 0, 0))
    draw, shadow_draw = ImageDraw.Draw(text_layer), ImageDraw.Draw(shadow_layer)
    font = ImageFont.truetype(font_path, font_size)
    if shadow:
        fill_color = fill_color[:3] + (229,)
        shadow_color_with_alpha = shadow_color[:3] + (shadow_alpha,) if shadow_color else tuple(max(0, int(c * 0.7)) for c in fill_color[:3]) + (shadow_alpha,)
        for offset in range(3, shadow_offset + 1, 2):
            shadow_draw.text((position[0] + offset, position[1] + offset), text, font=font, fill=shadow_color_with_alpha)
    draw.text(position, text, font=font, fill=fill_color)
    return Image.alpha_composite(Image.alpha_composite(img_copy, shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_offset))), text_layer)

def draw_multiline_text_on_image(image, text, position, font_path, font_size, max_width=600, line_spacing=10, fill_color=(255, 255, 255, 255), shadow=False, shadow_color=None, shadow_offset=4, shadow_alpha=100):
    img_copy = image.copy()
    text_layer = Image.new('RGBA', img_copy.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(text_layer)
    font = ImageFont.truetype(font_path, font_size)
    
    lines, words = [], text.split(" ")
    curr_line = words[0]
    for w in words[1:]:
        test_line = curr_line + " " + w
        if draw.textbbox((0, 0), test_line, font=font)[2] > max_width:
            lines.append(curr_line); curr_line = w
        else: curr_line = test_line
    if curr_line: lines.append(curr_line)

    if shadow:
        fill_color = fill_color[:3] + (229,)
        shadow_color_with_alpha = shadow_color[:3] + (shadow_alpha,) if shadow_color else tuple(max(0, int(c * 0.7)) for c in fill_color[:3]) + (shadow_alpha,)

    x, y = position
    for i, line in enumerate(lines):
        current_y = y + i * (font_size + line_spacing)
        if shadow:
            for offset in range(3, shadow_offset + 1, 2): draw.text((x + offset, current_y + offset), line, font=font, fill=shadow_color_with_alpha)
        draw.text((x, current_y), line, font=font, fill=fill_color)
    return Image.alpha_composite(img_copy, text_layer), len(lines)

def get_random_color(image_path):
    try:
        img = Image.open(image_path)
        pixel = img.getpixel((random.randint(int(img.width * 0.5), int(img.width * 0.8)), random.randint(int(img.height * 0.5), int(img.height * 0.8))))
        return pixel[:3] + (255,) if isinstance(pixel, tuple) else (pixel, pixel, pixel, 255)
    except: return (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200), 255)

def draw_color_block(image, position, size, color):
    ImageDraw.Draw(image).rectangle([position, (position[0] + size[0], position[1] + size[1])], fill=color)
    return image

def create_gradient_background(width, height, color_list=None):
    selected = color_list[0][:3] if color_list else (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
    r, g, b = [int(c * 0.65) for c in selected]
    c1, c2 = (max(0, r), max(0, g), max(0, b), 255), (min(255, int(r * 1.9)), min(255, int(g * 1.9)), min(255, int(b * 1.9)), 255)
    mask = Image.new("L", (width, height), 0)
    mask.putdata([int(255.0 * (x / width) ** 0.7) for y in range(height) for x in range(width)])
    return Image.composite(Image.new("RGBA", (width, height), c2), Image.new("RGBA", (width, height), c1), mask)

def get_poster_primary_color(image_path):
    try: return Counter([(r, g, b, 255) for r, g, b, a in list(Image.open(image_path).resize((100, 150), Image.LANCZOS).convert('RGBA').getdata()) if a > 200 and not (r < 30 and g < 30 and b < 30)]).most_common(10)
    except: return [(150, 100, 50, 255)]

def create_blur_background(image_path, w, h, bg_color, blur_size, color_ratio):
    bg_img = ImageOps.fit(Image.open(image_path).convert('RGB'), (w, h), method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=int(blur_size)))
    blended = np.clip(np.array(bg_img, float) * (1 - float(color_ratio)) + np.array([[darken_color(bg_color, 0.85)[:3]]], float) * float(color_ratio), 0, 255).astype(np.uint8)
    blended_img = Image.fromarray(blended, 'RGB').convert('RGBA')
    gradient_mask = Image.new("L", (w, h), 0)
    draw_mask = ImageDraw.Draw(gradient_mask)
    for x in range(w): draw_mask.line([(x, 0), (x, h)], fill=int((x / w) * 255 * 0.6))
    lighten_layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    lighten_layer.putalpha(gradient_mask)
    return add_film_grain(Image.alpha_composite(blended_img, lighten_layer), intensity=0.03)

def create_style_multi_1(library_dir, title, font_path, font_size=(1,1), is_blur=False, blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        zh_font_path, en_font_path = font_path
        title_zh, title_en = title
        conf = POSTER_GEN_CONFIG
        first_image_path = Path(library_dir) / "1.jpg"
        
        vibrant_colors = find_dominant_vibrant_colors(Image.open(first_image_path).convert("RGB"))
        blur_color = vibrant_colors[0] if vibrant_colors else random.choice([(237, 159, 77), (186, 225, 255), (202, 231, 200)])
        
        if is_blur: result = create_blur_background(first_image_path, conf["CANVAS_WIDTH"], conf["CANVAS_HEIGHT"], blur_color, blur_size, color_ratio)
        else: result = create_gradient_background(conf["CANVAS_WIDTH"], conf["CANVAS_HEIGHT"], get_poster_primary_color(first_image_path))

        poster_files = sorted([os.path.join(library_dir, f) for f in os.listdir(library_dir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))])
        if not poster_files: return False
        while len(poster_files) < conf["ROWS"] * conf["COLS"]: poster_files.extend(poster_files[:conf["ROWS"] * conf["COLS"] - len(poster_files)])
        
        for col_index, column_posters in enumerate([poster_files[i:i+conf["ROWS"]] for i in range(0, len(poster_files), conf["ROWS"])][:conf["COLS"]]):
            column_image = Image.new("RGBA", (conf["CELL_WIDTH"] + 40, conf["ROWS"] * conf["CELL_HEIGHT"] + (conf["ROWS"] - 1) * conf["MARGIN"] + 40), (0, 0, 0, 0))
            for row_index, poster_path in enumerate(column_posters):
                try:
                    poster = ImageOps.fit(Image.open(poster_path), (conf["CELL_WIDTH"], conf["CELL_HEIGHT"]), method=Image.LANCZOS)
                    mask = Image.new("L", poster.size, 0)
                    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), poster.size], radius=conf["CORNER_RADIUS"], fill=255)
                    poster_with_corners = Image.new("RGBA", poster.size, (0, 0, 0, 0))
                    poster_with_corners.paste(poster, (0, 0), mask)
                    column_image.paste(add_shadow(poster_with_corners, offset=(20, 20), shadow_color=(0, 0, 0, 216), blur_radius=20), (0, row_index * (conf["CELL_HEIGHT"] + conf["MARGIN"])))
                except: continue
            
            rotation_canvas = Image.new("RGBA", (int(math.hypot(column_image.width, column_image.height) * 1.5),) * 2, (0, 0, 0, 0))
            rotation_canvas.paste(column_image, ((rotation_canvas.width - column_image.width) // 2, (rotation_canvas.height - column_image.height) // 2))
            rotated_column = rotation_canvas.rotate(conf["ROTATION_ANGLE"], Image.BICUBIC, expand=True)
            
            column_center_x, column_center_y = conf["START_X"] + col_index * conf["COLUMN_SPACING"], conf["START_Y"] + (conf["ROWS"] * conf["CELL_HEIGHT"] + (conf["ROWS"] - 1) * conf["MARGIN"]) // 2
            if col_index == 1: column_center_x += conf["CELL_WIDTH"] - 50
            elif col_index == 2: column_center_y += -155; column_center_x += conf["CELL_WIDTH"] * 2 - 40
            result.paste(rotated_column, (column_center_x - rotated_column.width // 2, column_center_y - rotated_column.height // 2), rotated_column)

        # 这里使用跟旧版几乎一模一样的字体大小基数和相对排版
        zh_sz = int(163 * float(font_size[0]))
        en_sz = max(30, int(50 * float(font_size[1])))
        text_shadow_color = darken_color(blur_color, 0.8)

        # 完全保留原来的绝对位置(73.32, 427.34)，保持你的多图排版不变
        result = draw_text_on_image(result, title_zh, (73.32, 427.34), zh_font_path, zh_sz, shadow=is_blur, shadow_color=text_shadow_color)
        if title_en:
            result, line_count = draw_multiline_text_on_image(result, title_en, (124.68, 624.55), en_font_path, en_sz, max_width=750, line_spacing=int(en_sz*0.1), shadow=is_blur, shadow_color=text_shadow_color)
            result = draw_color_block(result, (84.38, 620.06), (21.51, en_sz + int(en_sz*0.1) + (line_count - 1) * (en_sz + int(en_sz*0.1))), get_random_color(first_image_path))

        if config and config.get("show_item_count", False) and item_count is not None:
            result = draw_badge(image=result.convert('RGBA'), item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=blur_color)

        return image_to_base64(result)
    except Exception as e:
        logger.error(f"创建多图封面时出错: {e}", exc_info=True)
        return False