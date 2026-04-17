# services/cover_generator/styles/style_dynamic_3.py

import base64
import io
import math
import numpy as np
import logging
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from gevent import sleep
from .style_single_2 import darken_color, find_dominant_vibrant_colors
from .badge_drawer import draw_badge

logger = logging.getLogger(__name__)

canvas_size = (640, 360)

def _clamp(v, lo, hi): return max(lo, min(hi, v))
def _ease_in_out_sine(t): return 0.5 * (1.0 - math.cos(math.pi * _clamp(t, 0.0, 1.0)))

def create_style_dynamic_3(image_paths, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        scale = canvas_size[1] / 1080.0
        zh_font_path, en_font_path = font_path
        title_zh, title_en = title

        assets = []
        for p in image_paths[:5]:
            try:
                src = Image.open(p).convert("RGB")
                bg = ImageOps.fit(src, canvas_size, method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=max(8, int(blur_size * scale))))
                
                colors = find_dominant_vibrant_colors(src, num_colors=5)
                tint = darken_color(colors[0] if colors else (120, 120, 120), 0.82)
                
                mixed = np.clip(np.array(bg, float) * (1 - float(color_ratio)) + np.array([[tint]], float) * float(color_ratio), 0, 255).astype(np.uint8)
                assets.append({'bg': Image.fromarray(mixed).convert("RGBA"), 'tint': tint})
            except Exception: pass
            
        if not assets: return False

        texts = []
        cx, cy = canvas_size[0] // 2, canvas_size[1] // 2
        zh_sz = max(1, int(170 * float(font_size[0]) * scale))
        en_sz = max(1, int(75 * float(font_size[1]) * scale))
        zh_font = ImageFont.truetype(str(zh_font_path), zh_sz)
        en_font = ImageFont.truetype(str(en_font_path), en_sz)
        
        for item in assets:
            txt_layer = Image.new("RGBA", canvas_size, (0,0,0,0))
            shadow_layer = Image.new("RGBA", canvas_size, (0,0,0,0))
            draw, sdraw = ImageDraw.Draw(txt_layer), ImageDraw.Draw(shadow_layer)
            
            shadow_color = darken_color(item['tint'], 0.65) + (92,)
            text_color = (255, 255, 255, 230)
            
            zh_bbox = draw.textbbox((0, 0), title_zh, font=zh_font)
            zh_w, zh_h = zh_bbox[2] - zh_bbox[0], zh_bbox[3] - zh_bbox[1]
            
            y0 = cy - zh_h // 2
            zh_x = cx - zh_w // 2
            
            for off in range(3, 11, 2): sdraw.text((zh_x+off, y0+off), title_zh, font=zh_font, fill=shadow_color)
            draw.text((zh_x, y0), title_zh, font=zh_font, fill=text_color)
            
            if title_en:
                en_bbox = draw.textbbox((0, 0), title_en, font=en_font)
                en_w = en_bbox[2] - en_bbox[0]
                en_x, en_y = cx - en_w // 2, y0 + zh_h + int(40*scale)
                for off in range(2, 8, 2): sdraw.text((en_x+off, en_y+off), title_en, font=en_font, fill=shadow_color)
                draw.text((en_x, en_y), title_en, font=en_font, fill=text_color)

            combined = Image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(8)), txt_layer)
            if config and config.get("show_item_count", False) and item_count is not None:
                combined = draw_badge(image=combined, item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=item['tint'])
            
            texts.append(combined)

        frames = []
        n_imgs = len(assets)
        total_frames = 15 * 6

        for f in range(total_frames):
            sleep(0.01) # ★ 防卡死
            phase = f / total_frames
            cycle = phase * n_imgs
            idx, nxt = int(cycle) % n_imgs, (int(cycle) + 1) % n_imgs
            local = cycle - int(cycle)
            
            t = _ease_in_out_sine(local)
            frame = Image.blend(assets[idx]['bg'], assets[nxt]['bg'], t)
            t_mix = Image.blend(texts[idx], texts[nxt], t)
            frame = Image.alpha_composite(frame, t_mix)
            
            frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=255))

        buffer = io.BytesIO()
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=66, loop=0, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    except Exception as e:
        logger.error(f"创建 style_dynamic_3 失败: {e}", exc_info=True)
        return False