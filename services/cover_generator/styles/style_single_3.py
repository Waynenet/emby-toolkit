# services/cover_generator/styles/style_single_3.py

import base64
import io
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import logging
from .style_single_2 import darken_color, find_dominant_vibrant_colors
from .badge_drawer import draw_badge

logger = logging.getLogger(__name__)

canvas_size = (1920, 1080)

def create_style_single_3(image_path, title, font_path, font_size=(1,1), blur_size=50, color_ratio=0.8, item_count=None, config=None):
    try:
        zh_font_path, en_font_path = font_path
        title_zh, title_en = title
        
        src = Image.open(image_path).convert("RGB")
        bg = ImageOps.fit(src, canvas_size, method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=int(blur_size)))
        
        colors = find_dominant_vibrant_colors(src, num_colors=5)
        tint = darken_color(colors[0] if colors else (120, 120, 120), 0.82)
        
        mixed = np.clip(np.array(bg, float) * (1 - float(color_ratio)) + np.array([[tint]], float) * float(color_ratio), 0, 255).astype(np.uint8)
        frame = Image.fromarray(mixed).convert("RGBA")

        cx, cy = canvas_size[0] // 2, canvas_size[1] // 2
        zh_sz = max(1, int(170 * float(font_size[0])))
        en_sz = max(1, int(75 * float(font_size[1])))
        zh_font = ImageFont.truetype(str(zh_font_path), zh_sz)
        en_font = ImageFont.truetype(str(en_font_path), en_sz)
        
        txt_layer = Image.new("RGBA", canvas_size, (0,0,0,0))
        shadow_layer = Image.new("RGBA", canvas_size, (0,0,0,0))
        draw, sdraw = ImageDraw.Draw(txt_layer), ImageDraw.Draw(shadow_layer)
        
        shadow_color = darken_color(tint, 0.65) + (92,)
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
            en_x, en_y = cx - en_w // 2, y0 + zh_h + 40
            for off in range(2, 8, 2): sdraw.text((en_x+off, en_y+off), title_en, font=en_font, fill=shadow_color)
            draw.text((en_x, en_y), title_en, font=en_font, fill=text_color)

        frame = Image.alpha_composite(frame, shadow_layer.filter(ImageFilter.GaussianBlur(8)))
        frame = Image.alpha_composite(frame, txt_layer)
        
        if config and config.get("show_item_count", False) and item_count is not None:
            frame = draw_badge(image=frame, item_count=item_count, font_path=zh_font_path, style=config.get('badge_style', 'badge'), size_ratio=config.get('badge_size_ratio', 0.12), base_color=tint)
            
        buffer = io.BytesIO()
        frame.convert("RGB").save(buffer, format="JPEG", quality=90, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    except Exception as e:
        logger.error(f"创建 style_single_3 失败: {e}", exc_info=True)
        return False