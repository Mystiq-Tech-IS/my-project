"""Авто-генерация обложек для программ через Pillow.

Если у программы нет своей обложки, генерируем: размытая иконка
на акцентном фоне + название внизу. Кэшируется на диск.
"""

import os
import hashlib

from PySide6.QtGui import QPixmap

try:
    from PIL import Image, ImageFilter, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None

from config import BASE_DIR
from icons import get_icon, _make_placeholder
from launcher import file_exists

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")


CACHE_DIR = os.path.join(BASE_DIR, ".cover_cache")


def is_available():
    return HAS_PIL


def _ensure_cache_dir():
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception:
        pass


def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _blend(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _find_font(size):
    """Возвращает PIL-шрифт для текста. Пытается найти системный."""
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _cache_key(app, w, h, accent_hex):
    raw = f"{app.get('path','')}|{app.get('name','')}|{w}x{h}|{accent_hex}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def generate_cover(app, colors, w=400, h=280, force=False):
    """
    Возвращает QPixmap с обложкой или None если Pillow не установлен.
    Использует кэш на диске.
    """
    if not HAS_PIL:
        return None

    _ensure_cache_dir()

    accent = colors.get("ACCENT", "#89B4FA")
    bg_alt = colors.get("BG_ALT", "#1C1C26")
    text_color = colors.get("TEXT", "#E5E5F0")
    sub = colors.get("SUBTEXT", "#9090A8")

    key = _cache_key(app, w, h, accent)
    cache_path = os.path.join(CACHE_DIR, f"{key}.png")

    if not force and os.path.exists(cache_path):
        pix = QPixmap(cache_path)
        if not pix.isNull():
            return pix

    try:
        # ---------- 1. Базовая иконка приложения ----------
        icon_pix = get_icon(app, 256)
        icon_img = None
        if icon_pix and not icon_pix.isNull():
            icon_pix = icon_pix.scaled(
                256, 256,
                aspectMode=1,  # Qt.KeepAspectRatio
                mode=1,        # Qt.SmoothTransformation
            )
            tmp = os.path.join(CACHE_DIR, f"_tmp_{key}.png")
            icon_pix.save(tmp, "PNG")
            try:
                icon_img = Image.open(tmp).convert("RGBA")
            finally:
                try:
                    os.remove(tmp)
                except Exception:
                    pass

        if icon_img is None:
            # Заглушка — квадрат с буквой
            placeholder = _make_placeholder(app.get("path", ""), 256)
            tmp = os.path.join(CACHE_DIR, f"_tmp_{key}.png")
            placeholder.save(tmp, "PNG")
            try:
                icon_img = Image.open(tmp).convert("RGBA")
            finally:
                try:
                    os.remove(tmp)
                except Exception:
                    pass

        # ---------- 2. Фон — размытая иконка + градиент ----------
        # Увеличим и сильно размоем
        big = icon_img.resize((w * 2, h * 2), Image.LANCZOS)
        bg = big.filter(ImageFilter.GaussianBlur(radius=40))

        # Обрезаем по центру до нужных размеров
        bw, bh = bg.size
        left = (bw - w) // 2
        top = (bh - h) // 2
        bg = bg.crop((left, top, left + w, top + h))

        # Затемняем через полупрозрачный слой акцентного фона
        bg_rgb = _hex_to_rgb(bg_alt)
        accent_rgb = _hex_to_rgb(accent)

        overlay = Image.new("RGBA", (w, h), (*bg_rgb, 200))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay)

        # Диагональный градиент акцента — лёгкий
        grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(grad)
        for y in range(h):
            t = y / max(1, h - 1)
            r, g, b = _blend(accent_rgb, bg_rgb, t * 0.85)
            gdraw.line([(0, y), (w, y)], fill=(r, g, b, 60))
        bg = Image.alpha_composite(bg, grad)

        # ---------- 3. Центральная иконка с подложкой ----------
        pad = 20
        icon_size = min(w, h) // 2 - pad
        icon_resized = icon_img.resize((icon_size, icon_size), Image.LANCZOS)

        # Круглая подложка под иконку
        plate_size = icon_size + 24
        plate = Image.new("RGBA", (plate_size, plate_size), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(plate)
        pdraw.ellipse(
            (0, 0, plate_size - 1, plate_size - 1),
            fill=(*_hex_to_rgb(accent), 40),
            outline=(*accent_rgb, 180),
            width=2,
        )

        # Помещаем иконку на подложку
        plate.paste(icon_resized, (12, 12), icon_resized)

        # Помещаем подложку на фон (по центру верхней части)
        cx = (w - plate_size) // 2
        cy = (h - plate_size) // 2 - 16
        bg.paste(plate, (cx, cy), plate)

        # ---------- 4. Текст — название внизу ----------
        draw = ImageDraw.Draw(bg)
        name = app.get("name", "Без имени")
        name_font = _find_font(max(16, int(w * 0.055)))

        # Тень под текстом
        text_y = h - int(h * 0.18)
        try:
            bbox = draw.textbbox((0, 0), name, font=name_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except Exception:
            text_w, text_h = len(name) * 10, 20

        text_x = (w - text_w) // 2

        # Обрезаем длинные имена
        if text_w > w - 40:
            # По одной букве уменьшаем
            cut = name
            while len(cut) > 4:
                cut = cut[:-1]
                try:
                    bbox = draw.textbbox((0, 0), cut + "…", font=name_font)
                    text_w = bbox[2] - bbox[0]
                except Exception:
                    break
                if text_w <= w - 40:
                    break
            name = cut + "…"
            try:
                bbox = draw.textbbox((0, 0), name, font=name_font)
                text_w = bbox[2] - bbox[0]
            except Exception:
                pass
            text_x = (w - text_w) // 2

        # Тень
        draw.text(
            (text_x + 1, text_y + 1), name,
            font=name_font, fill=(0, 0, 0, 220)
        )
        # Основной текст
        draw.text(
            (text_x, text_y), name,
            font=name_font, fill=(*_hex_to_rgb(text_color), 255)
        )

        # ---------- 5. Сохраняем ----------
        bg.convert("RGB").save(cache_path, "PNG", quality=92)

        pix = QPixmap(cache_path)
        if pix.isNull():
            return None
        return pix

    except Exception as e:
        log.error(f"generate_cover error: {e}")
        return None


def clear_cache():
    """Удалить все сгенерированные обложки."""
    try:
        if os.path.isdir(CACHE_DIR):
            for f in os.listdir(CACHE_DIR):
                if f.endswith(".png"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, f))
                    except Exception:
                        pass
        log.info("Кэш авто-обложек очищен")
        return True
    except Exception as e:
        log.error(f"clear_cover_cache: {e}")
        return False