# services/cover_generator/styles/style_dynamic_1.py

import logging
import random
import io
import base64
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from gevent import sleep

from .style_single_1 import (
    find_dominant_macaron_colors, color_distance, darken_color, 
    add_film_grain, crop_to_square, add_rounded_corners
)
from .badge_drawer import draw_badge

logger = logging.getLogger(__name__)

# 使用 640x360 保证内存和CPU不爆炸
canvas_size = (640, 360) 

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _ease_in_out_sine(t):
    t = _clamp(t, 0.0, 1.0)
    return 0.5 * (1.0 - math.cos(math.pi * t))

def rotate_on_stable_canvas(img, angle, size):
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x, y = (size - img.width) // 2, (size - img.height) // 2
    canvas.paste(img, (x, y), img)
    c = size // 2
    return canvas.rotate(angle, resample=Image.Resampling.BICUBIC, center=(c, c))

def pre_bake_shadow(card_img, radius=10, opacity=0.5):
    w, h = card_img.size
    pad = int(radius * 3)
    out_w, out_h = w + pad*2, h + pad*2
    if out_w % 2 == 0: out_w += 1
    if out_h % 2 == 0: out_h += 1
    pad_x, pad_y = (out_w - w) // 2, (out_h - h) // 2
    
    shadow_layer = Image.new("RGBA", (w, h), (0, 0, 0, int(255 * opacity)))
    canvas = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    canvas.paste(shadow_layer, (pad_x + 10, pad_y + 10), card_img.split()[3])
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius))
    canvas.paste(card_img, (pad_x, pad_y), card_img)
    return canvas

def create_style_dynamic_1(image_paths, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        zh_font_path, en_font_path = font_path
        title_zh, title_en = title
        scale = canvas_size[1] / 1080.0
        
        assets = []
        card_size = int(canvas_size[1] * 0.7)
        if card_size % 2 == 0: card_size += 1
        
        for path in image_paths[:5]:
            try:
                img = Image.open(path).convert("RGB")
                colors = find_dominant_macaron_colors(img, num_colors=1)
                bg_color = darken_color(colors[0], 0.85) if colors else (40, 40, 40)
                
                bg_img = ImageOps.fit(img, canvas_size, method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=max(1, int(blur_size*scale))))
                blended_bg = np.clip(np.array(bg_img, dtype=float) * (1 - float(color_ratio)) + np.array([[bg_color]], dtype=float) * float(color_ratio), 0, 255).astype(np.uint8)
                base_bg = add_film_grain(Image.fromarray(blended_bg), intensity=0.03).convert("RGBA")
                
                sq = crop_to_square(img).resize((card_size, card_size), Image.Resampling.BICUBIC)
                
                # Main
                card_main = add_rounded_corners(sq, radius=card_size//8).convert("RGBA")
                b_main = pre_bake_shadow(card_main, radius=max(1, int(15*scale)), opacity=0.5)
                
                # Mid
                c1 = find_dominant_macaron_colors(img, num_colors=3)
                c_mid = c1[1] if len(c1)>1 else (186,225,255)
                mix_mid = np.clip(np.array(sq.copy().filter(ImageFilter.GaussianBlur(8)), float)*0.5 + np.array([[c_mid]], float)*0.5, 0, 255).astype(np.uint8)
                card_mid = add_rounded_corners(Image.fromarray(mix_mid), radius=card_size//8).convert("RGBA")
                b_mid = pre_bake_shadow(card_mid, radius=max(1, int(15*scale)), opacity=0.5)
                
                # Heavy
                c_heavy = c1[2] if len(c1)>2 else (255,223,186)
                mix_heavy = np.clip(np.array(sq.copy().filter(ImageFilter.GaussianBlur(16)), float)*0.4 + np.array([[c_heavy]], float)*0.6, 0, 255).astype(np.uint8)
                card_heavy = add_rounded_corners(Image.fromarray(mix_heavy), radius=card_size//8).convert("RGBA")
                b_heavy = pre_bake_shadow(card_heavy, radius=max(1, int(15*scale)), opacity=0.5)
                
                assets.append({'bg': base_bg, 'main': b_main, 'mid': b_mid, 'heavy': b_heavy, 'badge_color': bg_color})
            except Exception: pass
            
        if not assets: return False
        n_cards = len(assets)

        text_layer = Image.new('RGBA', canvas_size, (255, 255, 255, 0))
        shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        draw = ImageDraw.Draw(text_layer)
        
        zh_sz = max(1, int(170 * float(font_size[0]) * scale))
        en_sz = max(1, int(75 * float(font_size[1]) * scale))
        zh_font = ImageFont.truetype(zh_font_path, zh_sz)
        en_font = ImageFont.truetype(en_font_path, en_sz)
        text_shadow_color = darken_color(assets[0]['badge_color'], 0.8) + (75,)
        
        zh_bbox = draw.textbbox((0, 0), title_zh, font=zh_font)
        cx, cy = int(canvas_size[0] * 0.25), int(canvas_size[1] * 0.5)
        zh_x, zh_y = cx - (zh_bbox[2]-zh_bbox[0])//2, cy - (zh_bbox[3]-zh_bbox[1])
        for off in range(3, 11, 2): shadow_draw.text((zh_x + off, zh_y + off), title_zh, font=zh_font, fill=text_shadow_color)
        draw.text((zh_x, zh_y), title_zh, font=zh_font, fill=(255, 255, 255, 229))
        
        if title_en:
            en_bbox = draw.textbbox((0, 0), title_en, font=en_font)
            en_x, en_y = cx - (en_bbox[2]-en_bbox[0])//2, zh_y + (zh_bbox[3]-zh_bbox[1]) + int(40*scale)
            for off in range(2, 8, 2): shadow_draw.text((en_x + off, en_y + off), title_en, font=en_font, fill=text_shadow_color)
            draw.text((en_x, en_y), title_en, font=en_font, fill=(255, 255, 255, 229))

        static_text = Image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(8)), text_layer)
        if config and config.get("show_item_count", False) and item_count is not None:
            static_text = draw_badge(image=static_text, item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=assets[0]['badge_color'])

        rot_size = int(math.ceil(math.hypot(assets[0]['main'].width, assets[0]['main'].height))) + 9
        if rot_size % 2 == 0: rot_size += 1
        center_offset = rot_size // 2
        c_pos = (int(canvas_size[0]*0.75), cy)

        total_frames = 15 * 6 # 15 fps * 6s
        frames = []
        
        for f in range(total_frames):
            sleep(0.01) # ★ 防卡死
            phase = f / total_frames
            cycle = phase * n_cards
            idx = int(cycle)
            local = cycle - idx

            idx_a = idx % n_cards
            idx_b = (idx + 1) % n_cards
            idx_c = (idx + 2) % n_cards
            idx_d = (idx + 3) % n_cards

            s1, s2, s3 = -5.0, 10.0, 25.0
            dx, dy = int(12 * scale), int(12 * scale)
            p1, p2, p3 = (0,0), (dx, dy), (dx*2, dy*2)

            t = _ease_in_out_sine(local)
            
            ang_b = s2 + (s1 - s2) * t
            pos_b = (p2[0] + (p1[0]-p2[0])*t, p2[1] + (p1[1]-p2[1])*t)
            ang_c = s3 + (s2 - s3) * t
            pos_c = (p3[0] + (p2[0]-p3[0])*t, p3[1] + (p2[1]-p3[1])*t)
            
            ang_a = s1
            fly_x, fly_y = canvas_size[0]*0.75, -canvas_size[1]*0.20
            dx_a, dy_a = fly_x * t, fly_y * t
            alpha_a = _clamp(1.0 - ((local-0.4)/0.6)**2, 0.0, 1.0) if local > 0.4 else 1.0

            b_blend = Image.blend(assets[idx_b]['mid'], assets[idx_b]['main'], _clamp(t*0.95, 0, 1))
            c_blend = Image.blend(assets[idx_c]['heavy'], assets[idx_c]['mid'], _clamp(t*0.90, 0, 1))

            z_order = [
                (s3, t, p3, assets[idx_d]['heavy']),
                (ang_c, 1.0, pos_c, c_blend),
                (ang_b, 1.0, pos_b, b_blend),
                (ang_a, alpha_a, (dx_a, dy_a), assets[idx_a]['main']),
            ]

            bg = Image.blend(assets[idx_a]['bg'], assets[idx_b]['bg'], t)
            frame = bg.copy()
            
            for ang, alpha, offs, card in z_order:
                if alpha <= 0: continue
                if alpha < 1.0:
                    a_mask = card.split()[3].point(lambda p: int(p * alpha))
                    card = card.copy()
                    card.putalpha(a_mask)
                
                rotated = rotate_on_stable_canvas(card, ang, rot_size)
                draw_x = int(round(c_pos[0] + offs[0])) - center_offset
                draw_y = int(round(c_pos[1] + offs[1])) - center_offset
                frame.paste(rotated, (draw_x, draw_y), rotated)

            frame = Image.alpha_composite(frame, static_text)
            frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=255))

        buffer = io.BytesIO()
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=66, loop=0, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    except Exception as e:
        logger.error(f"创建 style_dynamic_1 失败: {e}", exc_info=True)
        return False