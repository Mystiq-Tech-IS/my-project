"""Авто-генерация обложек для программ через Pillow.

Два стиля:
  • Обычный (library_style=False) — иконка на круглой подложке.
    Используется на главном экране.
  • Библиотечный (library_style=True) — крупная иконка без подложки
    на размытом акцентном фоне. Используется в библиотеке игр —
    выглядит как полноценная обложка.
"""

import os
import hashlib

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

try:
    from PIL import Image, ImageFilter, ImageDraw, ImageFont
    try:
        from PIL import ImageOps
    except ImportError:
        ImageOps = None
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None
    ImageOps = None

from config import BASE_DIR
from icons import get_icon, _make_placeholder

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")


# Кэш обложек — рядом с .exe (в temp не сохранится)
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


def _cache_key(app, w, h, accent_hex, show_name=True, library_style=False):
    raw = (f"{app.get('path','')}|{app.get('name','')}|{w}x{h}"
           f"|{accent_hex}"
           f"|{int(bool(show_name))}"
           f"|{int(bool(library_style))}")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _pixmap_scaled(pix, w, h):
    """Безопасный scaled с явным int() — фикс PySide6 6.11.

    В PySide6 6.11.2 сигнатура QPixmap.scaled требует keyword-аргументов
    по позиции — при явной передаче enum падает даже fallback. Поэтому
    второй try использует именованные аргументы.
    """
    if pix is None or pix.isNull():
        return pix

    w_i = int(w)
    h_i = int(h)

    try:
        return pix.scaled(
            w_i, h_i,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception as e:
        log.error(f"_pixmap_scaled primary: {e}")

    try:
        return pix.scaled(
            w_i, h_i,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        )
    except Exception as e:
        log.error(f"_pixmap_scaled kwargs: {e}")

    # Возвращаем как есть — иконка отрисуется в исходном размере
    return pix


def _fit_square(icon_img, target):
    """Вписывает иконку в квадрат target×target, сохраняя пропорции."""
    icon_img = icon_img.copy()
    try:
        if ImageOps is not None:
            return ImageOps.contain(
                icon_img, (int(target), int(target)), Image.LANCZOS
            )
    except Exception:
        pass
    # Fallback: resize по короткой стороне
    iw, ih = icon_img.size
    if iw > ih:
        new_w = int(target)
        new_h = max(1, int(ih * target / iw))
    else:
        new_h = int(target)
        new_w = max(1, int(iw * target / ih))
    return icon_img.resize((new_w, new_h), Image.LANCZOS)


# =================== ЯДРО ГЕНЕРАЦИИ ===================

def _build_cover_image(app, colors, w, h, icon_img,
                       show_name=True, library_style=False):
    """Общая логика отрисовки обложки. Возвращает PIL.Image (RGB).

    library_style=False → иконка на круглой подложке (главный экран).
    library_style=True  → крупная иконка без подложки, размытие сильнее
                          (для библиотеки игр — эффект «обложки»).
    """
    accent = colors.get("ACCENT", "#89B4FA")
    bg_alt = colors.get("BG_ALT", "#1C1C26")
    text_color = colors.get("TEXT", "#E5E5F0")

    # Размытие фона: в библиотеке делаем мягче и шире
    blur_radius = 70 if library_style else 40

    big = icon_img.resize((w * 2, h * 2), Image.LANCZOS)
    bg = big.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    bw, bh = bg.size
    left = (bw - w) // 2
    top = (bh - h) // 2
    bg = bg.crop((left, top, left + w, top + h))

    bg_rgb = _hex_to_rgb(bg_alt)
    accent_rgb = _hex_to_rgb(accent)

    # Приглушение: в библиотеке overlay слабее, чтобы размытая иконка
    # была заметна, а не выглядела как однотонный серый.
    overlay_alpha = 120 if library_style else 200
    overlay = Image.new("RGBA", (w, h), (*bg_rgb, overlay_alpha))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay)

    # Акцентный градиент сверху вниз — оба стиля
    grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    for y in range(h):
        t = y / max(1, h - 1)
        r, g, b = _blend(accent_rgb, bg_rgb, t * 0.85)
        gdraw.line([(0, y), (w, y)], fill=(r, g, b, 60))
    bg = Image.alpha_composite(bg, grad)

    # ---- Размещение иконки ----
    if library_style:
        # Крупная иконка БЕЗ плашки, по центру, чуть выше середины
        icon_target = int(min(w, h) * 0.68)
        icon_resized = _fit_square(icon_img, icon_target)

        icx = (w - icon_resized.width) // 2
        icy = (h - icon_resized.height) // 2 - int(h * 0.02)
        if icy < 0:
            icy = 0

        # Мягкая подложка-подсветка, чтобы иконка не терялась на фоне
        try:
            soft_glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            sg_draw = ImageDraw.Draw(soft_glow)
            pad = 30
            cx = w // 2
            cy = h // 2 - int(h * 0.02)
            r_hint = max(icon_resized.width, icon_resized.height) // 2 + pad
            glow_col = accent_rgb + (55,)
            sg_draw.ellipse(
                (cx - r_hint, cy - r_hint, cx + r_hint, cy + r_hint),
                fill=glow_col,
            )
            soft_glow = soft_glow.filter(ImageFilter.GaussianBlur(radius=24))
            bg = Image.alpha_composite(bg, soft_glow)
        except Exception:
            pass

        bg.paste(icon_resized, (icx, icy), icon_resized)
    else:
        # Старое поведение: иконка на круглой подложке
        pad = 20
        icon_size = min(w, h) // 2 - pad
        icon_resized = icon_img.resize((icon_size, icon_size), Image.LANCZOS)

        plate_size = icon_size + 24
        plate = Image.new("RGBA", (plate_size, plate_size), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(plate)
        pdraw.ellipse(
            (0, 0, plate_size - 1, plate_size - 1),
            fill=(*accent_rgb, 40),
            outline=(*accent_rgb, 180),
            width=2,
        )
        plate.paste(icon_resized, (12, 12), icon_resized)

        cx = (w - plate_size) // 2
        cy = (h - plate_size) // 2 - 16
        bg.paste(plate, (cx, cy), plate)

    # ---- Имя на обложке (опционально) ----
    if show_name:
        draw = ImageDraw.Draw(bg)
        name = app.get("name", "Без имени")
        name_font = _find_font(max(16, int(w * 0.055)))

        text_y = h - int(h * 0.18)
        try:
            bbox = draw.textbbox((0, 0), name, font=name_font)
            text_w = bbox[2] - bbox[0]
        except Exception:
            text_w = len(name) * 10

        text_x = (w - text_w) // 2

        if text_w > w - 40:
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

        draw.text(
            (text_x + 1, text_y + 1), name,
            font=name_font, fill=(0, 0, 0, 220),
        )
        draw.text(
            (text_x, text_y), name,
            font=name_font, fill=(*_hex_to_rgb(text_color), 255),
        )

    return bg.convert("RGB")


# =================== ПУБЛИЧНЫЕ ФУНКЦИИ ===================

def generate_cover(app, colors, w=400, h=280, force=False,
                   show_name=True, library_style=False):
    """Генерирует QPixmap-обложку (для GUI-потока)."""
    if not HAS_PIL:
        return None

    _ensure_cache_dir()

    accent = colors.get("ACCENT", "#89B4FA")
    key = _cache_key(app, w, h, accent,
                     show_name=show_name,
                     library_style=library_style)
    cache_path = os.path.join(CACHE_DIR, f"{key}.png")

    if not force and os.path.exists(cache_path):
        pix = QPixmap(cache_path)
        if not pix.isNull():
            return pix

    try:
        icon_pix = get_icon(app, 256)
        icon_img = None
        if icon_pix and not icon_pix.isNull():
            icon_pix = _pixmap_scaled(icon_pix, 256, 256)
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

        bg = _build_cover_image(
            app, colors, w, h, icon_img,
            show_name=show_name,
            library_style=library_style,
        )
        bg.save(cache_path, "PNG", quality=92)

        pix = QPixmap(cache_path)
        return pix if not pix.isNull() else None

    except Exception as e:
        log.error(f"generate_cover error: {e}")
        return None


def _save_icon_as_png(app, cache_key, size=256):
    """Сохраняет иконку приложения как PNG во временный файл.

    Безопасна для фонового потока, если сама сохраняемая иконка
    была получена в GUI-потоке.
    """
    if not HAS_PIL:
        return None
    _ensure_cache_dir()
    try:
        icon_pix = get_icon(app, size)
        if icon_pix is None or icon_pix.isNull():
            icon_pix = _make_placeholder(app.get("path", ""), size)
        icon_pix = _pixmap_scaled(icon_pix, size, size)
        tmp = os.path.join(CACHE_DIR, f"_icon_{cache_key}.png")
        if not icon_pix.save(tmp, "PNG"):
            return None
        return tmp
    except Exception as e:
        log.error(f"_save_icon_as_png: {e}")
        return None


def ensure_cover_file(app, colors, w=400, h=280, icon_png_path=None,
                      show_name=True, library_style=False):
    """Возвращает путь к PNG-обложке, генерируя её при необходимости.

    Безопасна для фонового потока, если icon_png_path подготовлен
    в GUI-потоке.
    """
    if not HAS_PIL:
        return None

    _ensure_cache_dir()

    accent = colors.get("ACCENT", "#89B4FA")
    key = _cache_key(app, w, h, accent,
                     show_name=show_name,
                     library_style=library_style)
    cache_path = os.path.join(CACHE_DIR, f"{key}.png")

    if os.path.exists(cache_path):
        return cache_path

    try:
        icon_img = None

        if icon_png_path and os.path.exists(icon_png_path):
            try:
                icon_img = Image.open(icon_png_path).convert("RGBA")
            except Exception:
                icon_img = None

        if icon_img is None:
            try:
                icon_pix = get_icon(app, 256)
                if icon_pix and not icon_pix.isNull():
                    icon_pix = _pixmap_scaled(icon_pix, 256, 256)
                    tmp = os.path.join(CACHE_DIR, f"_tmp_{key}.png")
                    icon_pix.save(tmp, "PNG")
                    try:
                        icon_img = Image.open(tmp).convert("RGBA")
                    finally:
                        try:
                            os.remove(tmp)
                        except Exception:
                            pass
            except Exception:
                icon_img = None

        if icon_img is None:
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

        bg = _build_cover_image(
            app, colors, w, h, icon_img,
            show_name=show_name,
            library_style=library_style,
        )
        bg.save(cache_path, "PNG", quality=92)
        return cache_path

    except Exception as e:
        log.error(f"ensure_cover_file error: {e}")
        return None


def clear_cache():
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