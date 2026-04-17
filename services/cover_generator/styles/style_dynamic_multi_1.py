# services/cover_generator/styles/style_dynamic_multi_1.py

import base64
import io
import math
import os
import random
import logging
from pathlib import Path
from gevent import sleep

from PIL import Image, ImageDraw, ImageOps
from .style_multi_1 import (
    POSTER_GEN_CONFIG, add_shadow, create_blur_background, 
    create_gradient_background, draw_color_block, draw_multiline_text_on_image, 
    draw_text_on_image, find_dominant_vibrant_colors, get_poster_primary_color, darken_color, get_random_color
)
from .badge_drawer import draw_badge

def create_style_dynamic_multi_1(library_dir, title, font_path, font_size=(1,1), is_blur=False, blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        target_w, target_h = 640, 360
        scale = target_h / 1080.0
        def s(val): return val * scale

        zh_font_path, en_font_path = font_path
        title_zh, title_en = title
        zh_sz = int(163 * float(font_size[0]) * scale)
        en_sz = max(15, int(50 * float(font_size[1]) * scale))

        poster_folder = Path(library_dir)
        first_image_path = poster_folder / "1.jpg"

        rows, cols = POSTER_GEN_CONFIG["ROWS"], POSTER_GEN_CONFIG["COLS"]
        margin, corner_radius = s(POSTER_GEN_CONFIG["MARGIN"]), s(POSTER_GEN_CONFIG["CORNER_RADIUS"])
        rotation_angle = POSTER_GEN_CONFIG["ROTATION_ANGLE"]
        start_x, start_y = s(POSTER_GEN_CONFIG["START_X"]), s(POSTER_GEN_CONFIG["START_Y"])
        column_spacing = s(POSTER_GEN_CONFIG["COLUMN_SPACING"])
        cell_width, cell_height = s(POSTER_GEN_CONFIG["CELL_WIDTH"]), s(POSTER_GEN_CONFIG["CELL_HEIGHT"])

        color_img = Image.open(first_image_path).convert("RGB")        
        vibrant_colors = find_dominant_vibrant_colors(color_img)
        blur_color = vibrant_colors[0] if vibrant_colors else (237, 159, 77)

        if is_blur: bg_img = create_blur_background(first_image_path, target_w, target_h, blur_color, blur_size * scale, color_ratio)
        else: bg_img = create_gradient_background(target_w, target_h, get_poster_primary_color(first_image_path))

        text_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        text_shadow_color = darken_color(blur_color, 0.8)
        text_layer = draw_text_on_image(text_layer, title_zh, (s(73.32), s(427.34)), zh_font_path, "ch.ttf", zh_sz, shadow=is_blur, shadow_color=text_shadow_color)
        if title_en:
            text_layer, lc = draw_multiline_text_on_image(text_layer, title_en, (s(124.68), s(624.55)), en_font_path, "en.otf", en_sz, int(en_sz*0.1), shadow=is_blur, shadow_color=text_shadow_color, is_multiline=True)
            text_layer = draw_color_block(text_layer, (s(84.38), s(620.06)), (s(21.51), int(en_sz * 1.5 * lc)), get_random_color(first_image_path))

        if config and config.get("show_item_count", False) and item_count is not None:
            text_layer = draw_badge(image=text_layer, item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=blur_color)

        base_frame = Image.alpha_composite(bg_img.convert("RGBA"), text_layer)

        formats = (".jpg", ".jpeg", ".png", ".webp")
        all_posters = sorted([os.path.join(poster_folder, f) for f in os.listdir(poster_folder) if f.lower().endswith(formats)])
        if not all_posters: return False

        # 计算铺满画面一共需要多少张图
        needed_count = rows * cols
        
        # 预先将现有的图片无限循环，确保丢给处理流程的路径数量足够
        extended_posters = (all_posters * needed_count)[:needed_count]
        
        processed_images = []
        for p_path in extended_posters:
            try:
                img = ImageOps.fit(Image.open(p_path).convert("RGBA"), (int(cell_width), int(cell_height)), method=Image.Resampling.BILINEAR)
                if corner_radius > 0:
                    mask = Image.new("L", (int(cell_width), int(cell_height)), 0)
                    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (int(cell_width), int(cell_height))], radius=corner_radius, fill=255)
                    img.putalpha(mask)
                processed_images.append(add_shadow(img, offset=(int(s(15)), int(s(15))), shadow_color=(0, 0, 0, 200), blur_radius=int(s(10))))
            except: pass

        # ★ 修改点：只要有 1 张成功处理的图就可以继续，不需要必须 3 张
        if not processed_images: 
            return False

        # ★ 修改点：如果成功处理的图片数量不够铺满墙，就用已有的图片反复循环来填补
        while len(processed_images) < needed_count:
            processed_images.extend(processed_images[:needed_count - len(processed_images)])

        col_images = [[], [], []]
        for i in range(len(processed_images)): col_images[i % 3].append(processed_images[i])

        scroll_dist = rows * (cell_height + margin) 
        cos_val = max(1e-6, math.cos(math.radians(abs(rotation_angle))))
        view_h = int(target_h / cos_val * 1.6)
        view_w = int(cell_width + s(60))
        
        rendered_strips = []
        for col_imgs in col_images:
            loop_posters = col_imgs * 2 + [col_imgs[0]]
            strip_h = len(loop_posters) * cell_height + (len(loop_posters) - 1) * margin
            strip = Image.new("RGBA", (int(cell_width) + int(s(60)), int(strip_h) + int(s(60))), (0, 0, 0, 0))
            for row_index, p_img in enumerate(loop_posters):
                strip.paste(p_img, (0, int(row_index * (cell_height + margin))), p_img)
            rendered_strips.append(strip)

        base_centers = []
        col_x_step = cell_width - s(50)
        for col_idx in range(cols):
            bcx, bcy = start_x + col_idx * column_spacing, start_y + (rows * cell_height + (rows - 1) * margin) // 2
            if col_idx == 1: bcx += col_x_step
            elif col_idx == 2: bcy += -s(155); bcx += col_x_step * 2 + s(30)
            base_centers.append((bcx, bcy))

        total_frames = 15 * 6
        col_phases = [0, scroll_dist // 4, scroll_dist // 2]
        frames = []

        for i in range(total_frames):
            sleep(0.01) # ★ 防卡死
            frame = base_frame.copy()
            progress = i / total_frames

            for col_idx, strip in enumerate(rendered_strips):
                total_scroll = progress * scroll_dist
                phase_offset = col_phases[col_idx % len(col_phases)]

                if col_idx == 1: dy_float = (total_scroll + phase_offset) % scroll_dist
                else: dy_float = (scroll_dist - total_scroll + phase_offset) % scroll_dist

                dy_int = int(dy_float)
                sub_strip = strip.crop((0, dy_int, view_w, dy_int + view_h))
                rotated = sub_strip.rotate(rotation_angle, resample=Image.Resampling.BILINEAR, expand=True)
                
                bcx, bcy = base_centers[col_idx]
                pos_x = int(bcx - rotated.width // 2 + cell_width // 2)
                pos_y = int(bcy - rotated.height // 2)
                frame.paste(rotated, (pos_x, pos_y), rotated)

            frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=128)) # 128色降体积

        buffer = io.BytesIO()
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=66, loop=0, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    except Exception as e:
        logger.error(f"创建 style_dynamic_multi_1 失败: {e}", exc_info=True)
        return False