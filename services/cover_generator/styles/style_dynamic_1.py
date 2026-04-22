# services/cover_generator/styles/style_dynamic_1.py

import logging
import math
import io
import base64
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from gevent import sleep

from .style_single_1 import find_dominant_macaron_colors, darken_color, add_film_grain, crop_to_square, add_rounded_corners
from .badge_drawer import draw_badge

logger = logging.getLogger(__name__)
canvas_size = (640, 360) 

def _clamp(v, lo, hi): return max(lo, min(hi, v))
def _ease_in_out_sine(t): return 0.5 * (1.0 - math.cos(math.pi * _clamp(t, 0.0, 1.0)))

def rotate_on_stable_canvas(img, angle, size):
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas.rotate(angle, resample=Image.Resampling.BICUBIC, center=(size // 2, size // 2))

def pre_bake_shadow(card_img, radius=10, opacity=0.5):
    w, h = card_img.size
    pad = int(radius * 3)
    out_w, out_h = w + pad*2 + (w + pad*2)%2, h + pad*2 + (h + pad*2)%2
    canvas = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (w, h), (0, 0, 0, int(255 * opacity))), ((out_w - w) // 2 + 10, (out_h - h) // 2 + 10), card_img.split()[3])
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius))
    canvas.paste(card_img, ((out_w - w) // 2, (out_h - h) // 2), card_img)
    return canvas

def frames_to_base64(frames, duration=66):
    buffer = io.BytesIO()
    try: frames[0].save(buffer, format="WEBP", save_all=True, append_images=frames[1:], duration=duration, loop=0, method=4, quality=80)
    except:
        buffer = io.BytesIO()
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=duration, loop=0, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def create_style_dynamic_1(image_paths, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        scale = canvas_size[1] / 1080.0
        assets = []
        card_size = int(canvas_size[1] * 0.7) + (int(canvas_size[1] * 0.7) % 2)
        
        for path in image_paths[:5]:
            try:
                img = Image.open(path).convert("RGB")
                colors = find_dominant_macaron_colors(img, 3)
                bg_c = darken_color(colors[0], 0.85) if colors else (40, 40, 40)
                bg = np.clip(np.array(ImageOps.fit(img, canvas_size, method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(max(1, int(blur_size*scale)))), float) * (1 - float(color_ratio)) + np.array([[bg_c]], float) * float(color_ratio), 0, 255).astype(np.uint8)
                base_bg = add_film_grain(Image.fromarray(bg), 0.03).convert("RGBA")
                
                sq = crop_to_square(img).resize((card_size, card_size), Image.Resampling.BICUBIC)
                c_main = pre_bake_shadow(add_rounded_corners(sq, card_size//8).convert("RGBA"), max(1, int(15*scale)))
                c_mid = pre_bake_shadow(add_rounded_corners(Image.fromarray(np.clip(np.array(sq.copy().filter(ImageFilter.GaussianBlur(8)), float)*0.5 + np.array([[colors[1] if len(colors)>1 else (186,225,255)]], float)*0.5, 0, 255).astype(np.uint8)), card_size//8).convert("RGBA"), max(1, int(15*scale)))
                c_heavy = pre_bake_shadow(add_rounded_corners(Image.fromarray(np.clip(np.array(sq.copy().filter(ImageFilter.GaussianBlur(16)), float)*0.4 + np.array([[colors[2] if len(colors)>2 else (255,223,186)]], float)*0.6, 0, 255).astype(np.uint8)), card_size//8).convert("RGBA"), max(1, int(15*scale)))
                
                assets.append({'bg': base_bg, 'main': c_main, 'mid': c_mid, 'heavy': c_heavy, 'badge': bg_c})
            except Exception: pass
            
        if not assets: return False
        
        zh_font_size = int(1080 * 0.17 * float(font_size[0]) * scale)
        en_font_size = int(1080 * 0.07 * float(font_size[1]) * scale)
        zh_font = ImageFont.truetype(font_path[0], max(1, zh_font_size))
        en_font = ImageFont.truetype(font_path[1], max(1, en_font_size))
        
        text_layer = Image.new('RGBA', canvas_size, (255, 255, 255, 0))
        shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        shadow_draw, draw = ImageDraw.Draw(shadow_layer), ImageDraw.Draw(text_layer)
        
        left_area_center_x, left_area_center_y = int(canvas_size[0] * 0.25), canvas_size[1] // 2
        text_color, text_shadow_color, shadow_offset = (255, 255, 255, 229), darken_color(assets[0]['badge'], 0.8) + (75,), max(3, int(12*scale))
        
        zh_bbox = draw.textbbox((0, 0), title[0], font=zh_font)
        zh_w, zh_h = zh_bbox[2] - zh_bbox[0], zh_bbox[3] - zh_bbox[1]
        zh_offset_y = zh_bbox[1]
        
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
            for line in en_lines: 
                lb = draw.textbbox((0, 0), line, font=en_font)
                total_en_h += (lb[3] - lb[1]) + en_spacing
            total_en_h -= en_spacing

        title_spacing = int(40*scale) if title[1] else 0
        total_text_y = left_area_center_y - (zh_h + total_en_h + title_spacing) // 2

        zh_x = left_area_center_x - zh_w // 2
        zh_y = total_text_y - zh_offset_y
        
        for offset in range(3, shadow_offset + 1, 2): shadow_draw.text((zh_x + offset, zh_y + offset), title[0], font=zh_font, fill=text_shadow_color)
        draw.text((zh_x, zh_y), title[0], font=zh_font, fill=text_color)
        
        if en_lines:
            curr_en_y = total_text_y + zh_h + title_spacing
            for i, line in enumerate(en_lines):
                lb = draw.textbbox((0, 0), line, font=en_font)
                ex = left_area_center_x - (lb[2] - lb[0]) // 2
                cy = curr_en_y - lb[1]
                for offset in range(2, shadow_offset // 2 + 1): shadow_draw.text((ex + offset, cy + offset), line, font=en_font, fill=text_shadow_color)
                draw.text((ex, cy), line, font=en_font, fill=text_color)
                curr_en_y += (lb[3] - lb[1]) + en_spacing
                
        static_text = Image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_offset)), text_layer)
        
        if config and config.get("show_item_count", False) and item_count is not None:
            static_text = draw_badge(image=static_text, item_count=item_count, font_path=font_path[0], style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=assets[0]['badge'])

        rot_size = int(math.ceil(math.hypot(assets[0]['main'].width, assets[0]['main'].height))) + 9
        if rot_size % 2 == 0: rot_size += 1
        
        frames, n = [], len(assets)
        for f in range(90):
            sleep(0.01)
            t_phase = f / 90 * n
            idx, local = int(t_phase) % n, t_phase % 1
            t = _ease_in_out_sine(local)
            
            frame = Image.blend(assets[idx]['bg'], assets[(idx+1)%n]['bg'], t).copy()
            for ang, alpha, offs, card in [(25.0, 1.0, (int(24*scale), int(24*scale)), Image.blend(assets[(idx+2)%n]['heavy'], assets[(idx+3)%n]['heavy'], _clamp(t*0.9, 0, 1))), (10.0 + (-5.0)*t, 1.0, (int(12*scale)*(1-t), int(12*scale)*(1-t)), Image.blend(assets[(idx+1)%n]['mid'], assets[(idx+1)%n]['main'], _clamp(t*0.95, 0, 1))), (-5.0, _clamp(1.0-((local-0.4)/0.6)**2,0,1) if local>0.4 else 1.0, (canvas_size[0]*0.75*t, -canvas_size[1]*0.20*t), assets[idx]['main'])]:
                if alpha <= 0: continue
                c = card.copy()
                if alpha < 1.0: c.putalpha(c.split()[3].point(lambda p: int(p * alpha)))
                r = rotate_on_stable_canvas(c, ang, rot_size)
                frame.paste(r, (int(canvas_size[0]*0.75 + offs[0] - rot_size//2), int(canvas_size[1]//2 + offs[1] - rot_size//2)), r)
                
            frames.append(Image.alpha_composite(frame, static_text).convert("RGB"))
            
        return frames_to_base64(frames)
    except Exception as e:
        logger.error(f"创建 style_dynamic_1 失败: {e}", exc_info=True)
        return False