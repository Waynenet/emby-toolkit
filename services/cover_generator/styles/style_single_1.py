# services/cover_generator/styles/style_single_1.py

import logging
import colorsys
import random
import base64
from io import BytesIO
from collections import Counter
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from .badge_drawer import draw_badge

logger = logging.getLogger(__name__)
canvas_size = (1920, 1080)

def is_not_black_white_gray_near(color, threshold=20):
    r, g, b = color
    if (r < threshold and g < threshold and b < threshold) or \
       (r > 255 - threshold and g > 255 - threshold and b > 255 - threshold): return False
    if abs(r - g) < 10 and abs(g - b) < 10 and abs(r - b) < 10: return False
    return True

def rgb_to_hsv(color): return colorsys.rgb_to_hsv(*[x / 255.0 for x in color])
def hsv_to_rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

def adjust_color_macaron(color):
    h, s, v = rgb_to_hsv(color)
    return hsv_to_rgb(h, max(0.3, min(s, 0.7)), max(0.6, min(v, 0.85)))

def color_distance(color1, color2):
    h1, s1, v1 = rgb_to_hsv(color1)
    h2, s2, v2 = rgb_to_hsv(color2)
    return min(abs(h1 - h2), 1 - abs(h1 - h2)) * 5 + abs(s1 - s2) + abs(v1 - v2)

def find_dominant_macaron_colors(image, num_colors=5):
    img = image.copy()
    img.thumbnail((150, 150))
    filtered_pixels = [p for p in list(img.convert('RGB').getdata()) if is_not_black_white_gray_near(p)]
    if not filtered_pixels: return []
    candidate_colors = Counter(filtered_pixels).most_common(num_colors * 5)
    macaron_colors = []
    for color, _ in candidate_colors:
        adjusted_color = adjust_color_macaron(color)
        if not any(color_distance(adjusted_color, existing) < 0.15 for existing in macaron_colors):
            macaron_colors.append(adjusted_color)
            if len(macaron_colors) >= num_colors: break
    return macaron_colors

def darken_color(color, factor=0.7): return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))

def add_film_grain(image, intensity=0.05):
    img_array = np.array(image)
    noise = np.random.normal(0, intensity * 255, img_array.shape)
    return Image.fromarray(np.clip(img_array + noise, 0, 255).astype(np.uint8))

def crop_to_square(img):
    size = min(img.size)
    left, top = (img.width - size) // 2, (img.height - size) // 2
    return img.crop((left, top, left + size, top + size))
    
def add_rounded_corners(img, radius=30):
    factor = 2
    width, height = img.size
    enlarged_img = img.resize((width * factor, height * factor), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new('L', (width * factor, height * factor), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (width * factor, height * factor)], radius=radius * factor, fill=255)
    background = Image.new("RGBA", (width * factor, height * factor), (255, 255, 255, 0))
    return Image.composite(enlarged_img, background, mask).resize((width, height), Image.Resampling.LANCZOS)

def add_shadow_and_rotate(canvas, img, angle, offset=(10, 10), radius=10, opacity=0.5, center_pos=None):
    width, height = img.size
    if center_pos is None: center_pos = (canvas.width // 2, canvas.height // 2)
    padding = max(radius * 4, 100)
    shadow = Image.new("RGBA", (width + padding * 2, height + padding * 2), (0, 0, 0, 0))
    shadow_mask = img.split()[3] if img.mode == "RGBA" else Image.new("L", (width, height), 255)
    shadow.paste((0, 0, 0, int(255 * opacity)), (padding, padding, padding + width, padding + height), shadow_mask)
    rotated_shadow = shadow.filter(ImageFilter.GaussianBlur(radius)).rotate(angle, Image.BICUBIC, expand=True)
    canvas.paste(rotated_shadow, (center_pos[0] - rotated_shadow.width // 2 + offset[0], center_pos[1] - rotated_shadow.height // 2 + offset[1]), rotated_shadow)
    rotated_img = img.rotate(angle, Image.BICUBIC, expand=True)
    canvas.paste(rotated_img, (center_pos[0] - rotated_img.width // 2, center_pos[1] - rotated_img.height // 2), rotated_img)
    return canvas

def image_to_base64(image):
    buffer = BytesIO()
    try: image.save(buffer, format="WEBP", quality=85, method=4)
    except:
        if image.mode == "RGBA" or image.info.get('transparency'): image.save(buffer, format="PNG", optimize=True)
        else: image.convert("RGB").save(buffer, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def create_style_single_1(image_path, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        zh_font_path, en_font_path = font_path
        title_zh, title_en = title
        zh_font_size_ratio, en_font_size_ratio = font_size

        if int(blur_size) < 0: blur_size = 50
        if not (0 <= float(color_ratio) <= 1): color_ratio = 0.8
        if not float(zh_font_size_ratio) > 0: zh_font_size_ratio = 1
        if not float(en_font_size_ratio) > 0: en_font_size_ratio = 1
        
        original_img = Image.open(image_path).convert("RGB")
        candidate_colors = find_dominant_macaron_colors(original_img, num_colors=6)
        random.shuffle(candidate_colors)
        extracted_colors = candidate_colors[:6]
        
        soft_macaron_colors = [(237, 159, 77), (186, 225, 255), (255, 223, 186), (202, 231, 200)]
        while len(extracted_colors) < 6:
            extracted_colors.append(random.choice(soft_macaron_colors) if not extracted_colors else max(soft_macaron_colors, key=lambda c: min(color_distance(c, e) for e in extracted_colors)))
        
        bg_color = darken_color(extracted_colors[0], 0.85)
        base_color_for_badge = extracted_colors[0]
        card_colors = [extracted_colors[1], extracted_colors[2]]
        
        bg_img = ImageOps.fit(original_img.copy(), canvas_size, method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=int(blur_size)))
        blended_bg = np.clip(np.array(bg_img, float) * (1 - float(color_ratio)) + np.array([[bg_color]], float) * float(color_ratio), 0, 255).astype(np.uint8)
        
        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        canvas.paste(add_film_grain(Image.fromarray(blended_bg), intensity=0.03))
        
        square_img = crop_to_square(original_img).resize((int(canvas_size[1] * 0.7), int(canvas_size[1] * 0.7)), Image.LANCZOS)
        main_card = add_rounded_corners(square_img, radius=square_img.height//8).convert("RGBA")
        
        aux1 = Image.fromarray(np.clip(np.array(square_img.copy().filter(ImageFilter.GaussianBlur(8)), float)*0.5 + np.array([[card_colors[0]]], float)*0.5, 0, 255).astype(np.uint8))
        aux_card1 = add_rounded_corners(aux1, radius=square_img.height//8).convert("RGBA")
        
        aux2 = Image.fromarray(np.clip(np.array(square_img.copy().filter(ImageFilter.GaussianBlur(16)), float)*0.4 + np.array([[card_colors[1]]], float)*0.6, 0, 255).astype(np.uint8))
        aux_card2 = add_rounded_corners(aux2, radius=square_img.height//8).convert("RGBA")
        
        center_pos = (int(canvas_size[0] - canvas_size[1] * 0.5), int(canvas_size[1] * 0.5))
        cards_canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        for card, angle, shadow_cfg in zip([aux_card2, aux_card1, main_card], [36, 18, 0], [{'offset': (10, 16), 'radius': 12, 'opacity': 0.4}, {'offset': (15, 22), 'radius': 15, 'opacity': 0.5}, {'offset': (20, 26), 'radius': 18, 'opacity': 0.6}]):
            cards_canvas = add_shadow_and_rotate(cards_canvas, card, angle, **shadow_cfg, center_pos=center_pos)
        
        canvas = Image.alpha_composite(canvas.convert("RGBA"), cards_canvas)
        
        # 5. 文字处理 (保留原视觉左侧排版，加入自动换行)
        text_layer = Image.new('RGBA', canvas_size, (255, 255, 255, 0))
        shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        shadow_draw, draw = ImageDraw.Draw(shadow_layer), ImageDraw.Draw(text_layer)
        
        left_area_center_x = int(canvas_size[0] * 0.25)
        left_area_center_y = canvas_size[1] // 2
        
        zh_font_size = int(canvas_size[1] * 0.17 * float(zh_font_size_ratio))
        en_font_size = int(canvas_size[1] * 0.07 * float(en_font_size_ratio))
        zh_font = ImageFont.truetype(zh_font_path, zh_font_size)
        en_font = ImageFont.truetype(en_font_path, en_font_size)
        
        text_color = (255, 255, 255, 229)
        text_shadow_color = darken_color(bg_color, 0.8) + (75,)
        shadow_offset = 12
        
        # 换行算法
        zh_bbox = draw.textbbox((0, 0), title_zh, font=zh_font)
        zh_w = zh_bbox[2] - zh_bbox[0]
        zh_h = zh_bbox[3] - zh_bbox[1]
        
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
        total_text_y = left_area_center_y - (zh_h + total_en_h + title_spacing) // 2

        zh_x = left_area_center_x - zh_w // 2
        zh_y = total_text_y
        for offset in range(3, shadow_offset + 1, 2):
            shadow_draw.text((zh_x + offset, zh_y + offset), title_zh, font=zh_font, fill=text_shadow_color)
        draw.text((zh_x, zh_y), title_zh, font=zh_font, fill=text_color)
        
        if en_lines:
            en_y = zh_y + zh_h + title_spacing
            for i, line in enumerate(en_lines):
                lb = draw.textbbox((0, 0), line, font=en_font)
                ex = left_area_center_x - (lb[2] - lb[0]) // 2
                cy = en_y + i * (lb[3] - lb[1] + en_spacing)
                for offset in range(2, shadow_offset // 2 + 1):
                    shadow_draw.text((ex + offset, cy + offset), line, font=en_font, fill=text_shadow_color)
                draw.text((ex, cy), line, font=en_font, fill=text_color)
        
        combined = Image.alpha_composite(canvas, shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_offset)))
        combined = Image.alpha_composite(combined, text_layer)
        
        if config and config.get("show_item_count", False) and item_count is not None:
            combined = draw_badge(image=combined.convert('RGBA'), item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=base_color_for_badge)

        return image_to_base64(combined)
    except Exception as e:
        logger.error(f"创建单图封面(style 1)时出错: {e}", exc_info=True)
        return False