# services/cover_generator/styles/style_dynamic_multi_1.py

import math
import os
import logging
from pathlib import Path
from gevent import sleep

from PIL import Image, ImageDraw, ImageOps, ImageFont
from .style_multi_1 import POSTER_GEN_CONFIG, add_shadow, create_blur_background, create_gradient_background, get_poster_primary_color, draw_text_on_image, draw_multiline_text_on_image, draw_color_block, get_random_color
from .style_single_2 import find_dominant_vibrant_colors
from .style_single_1 import darken_color
from .badge_drawer import draw_badge
from .style_dynamic_1 import frames_to_base64

logger = logging.getLogger(__name__)

def create_style_dynamic_multi_1(library_dir, title, font_path, font_size=(1,1), is_blur=False, blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        scale = 360 / 1080.0
        conf = POSTER_GEN_CONFIG
        first_img = Path(library_dir) / "1.jpg"

        colors = find_dominant_vibrant_colors(Image.open(first_img).convert("RGB"))
        blur_c = colors[0] if colors else (237, 159, 77)

        if is_blur: bg_img = create_blur_background(first_img, 640, 360, blur_c, blur_size * scale, color_ratio)
        else: bg_img = create_gradient_background(640, 360, get_poster_primary_color(first_img))

        # 字体逻辑保持与 static 的 multi 同步
        zh_sz = int(1080 * 0.17 * float(font_size[0]) * scale)
        en_sz = int(1080 * 0.07 * float(font_size[1]) * scale)
        text_shadow_color = darken_color(blur_c, 0.8)

        text_layer = Image.new("RGBA", (640, 360), (0, 0, 0, 0))
        # 根据 scale 缩小左侧文字排版位置
        text_layer = draw_text_on_image(text_layer, title[0], (73.32 * scale, 427.34 * scale), font_path[0], zh_sz, shadow=is_blur, shadow_color=text_shadow_color)
        if title[1]:
            text_layer, lc = draw_multiline_text_on_image(text_layer, title[1], (124.68 * scale, 624.55 * scale), font_path[1], en_sz, max_width=750 * scale, line_spacing=int(en_sz*0.1), shadow=is_blur, shadow_color=text_shadow_color)
            text_layer = draw_color_block(text_layer, (84.38 * scale, 620.06 * scale), (21.51 * scale, en_sz + int(en_sz*0.1) + (lc - 1) * (en_sz + int(en_sz*0.1))), get_random_color(first_img))

        if config and config.get("show_item_count", False) and item_count is not None:
            text_layer = draw_badge(image=text_layer, item_count=item_count, font_path=font_path[0], style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=blur_c)

        base_frame = Image.alpha_composite(bg_img.convert("RGBA"), text_layer)

        all_posters = sorted([os.path.join(library_dir, f) for f in os.listdir(library_dir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))])
        if not all_posters: return False

        needed = conf["ROWS"] * conf["COLS"]
        extended = (all_posters * needed)[:needed]
        
        cw, ch = conf["CELL_WIDTH"] * scale, conf["CELL_HEIGHT"] * scale
        proc_imgs = []
        for p in extended:
            try:
                img = ImageOps.fit(Image.open(p).convert("RGBA"), (int(cw), int(ch)), method=Image.Resampling.BILINEAR)
                mask = Image.new("L", img.size, 0)
                ImageDraw.Draw(mask).rounded_rectangle([(0, 0), img.size], radius=conf["CORNER_RADIUS"]*scale, fill=255)
                img.putalpha(mask)
                proc_imgs.append(add_shadow(img, (int(15*scale), int(15*scale)), (0, 0, 0, 200), int(10*scale)))
            except: pass

        if not proc_imgs: return False
        while len(proc_imgs) < needed: proc_imgs.extend(proc_imgs[:needed - len(proc_imgs)])

        col_imgs = [[], [], []]
        for i, img in enumerate(proc_imgs): col_imgs[i % 3].append(img)

        s_dist = conf["ROWS"] * (ch + conf["MARGIN"]*scale)
        view_h, view_w = int(360 / math.cos(math.radians(abs(conf["ROTATION_ANGLE"]))) * 1.6), int(cw + 60*scale)
        
        strips = []
        for imgs in col_imgs:
            loop = imgs * 2 + [imgs[0]]
            strip = Image.new("RGBA", (view_w, int(len(loop) * ch + (len(loop) - 1) * conf["MARGIN"]*scale + 60*scale)), (0, 0, 0, 0))
            for r, img in enumerate(loop): strip.paste(img, (0, int(r * (ch + conf["MARGIN"]*scale))), img)
            strips.append(strip)

        centers = []
        for c in range(conf["COLS"]):
            bx, by = conf["START_X"]*scale + c * conf["COLUMN_SPACING"]*scale, conf["START_Y"]*scale + s_dist / 2
            if c == 1: bx += cw - 50*scale
            elif c == 2: by -= 155*scale; bx += (cw - 50*scale) * 2 + 30*scale
            centers.append((bx, by))

        frames, phases = [], [0, s_dist // 4, s_dist // 2]
        for i in range(90):
            sleep(0.01)
            frame = base_frame.copy()
            for c, strip in enumerate(strips):
                dy = (i / 90 * s_dist + phases[c % 3]) % s_dist if c == 1 else (s_dist - i / 90 * s_dist + phases[c % 3]) % s_dist
                rot = strip.crop((0, int(dy), view_w, int(dy) + view_h)).rotate(conf["ROTATION_ANGLE"], resample=Image.Resampling.BILINEAR, expand=True)
                frame.paste(rot, (int(centers[c][0] - rot.width // 2 + cw // 2), int(centers[c][1] - rot.height // 2)), rot)
            frames.append(frame.convert("RGB"))

        return frames_to_base64(frames)
    except Exception as e:
        logger.error(f"创建 style_dynamic_multi_1 失败: {e}", exc_info=True)
        return False