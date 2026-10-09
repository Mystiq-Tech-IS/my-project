"""Плитка программы с масштабированием, drag-n-drop, заметками и обновлениями.

Обложки загружаются ЛЕНИВО: при создании карточки ставится placeholder,
реальная обложка готовится в фоновом потоке через QThreadPool и
подменяется по сигналу.
"""

import os
import json
import math
import ctypes
import threading
from ctypes import wintypes
from PySide6.QtWidgets import QFrame, QMenu
from PySide6.QtCore import (
    Qt, Signal, QRect, QRectF, QPointF, QMimeData, QPoint,
    QVariantAnimation, QEasingCurve, QPropertyAnimation,
    QThreadPool, QRunnable, QObject, QTimer,
)
from PySide6.QtGui import (
    QCursor, QColor, QPixmap, QPainter, QPainterPath, QFont, QBrush,
    QLinearGradient, QPen, QIcon, QDrag,
)

from icons import get_icon
from launcher import file_exists
from process_check import is_process_running
import icon_map
import custom_tooltip

try:
    from storage import log
except Exception:
    class _L:
        def info(self, *a, **k): pass
        def error(self, *a, **k): pass
    log = _L()


DRAG_MIME = "application/x-launcher-app"


# ============== БЕЗОПАСНЫЙ SCALED ==============
def _scaled(pix, w, h,
            aspect=Qt.AspectRatioMode.KeepAspectRatio,
            transform=Qt.TransformationMode.SmoothTransformation):
    """Обёртка над QPixmap.scaled с явным int() — фикс PySide6 6.11."""
    try:
        return pix.scaled(int(w), int(h), aspect, transform)
    except Exception:
        try:
            return pix.scaled(int(w), int(h))
        except Exception:
            return pix


# ================= ВЕРСИЯ EXE =================
class _VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature",        wintypes.DWORD),
        ("dwStrucVersion",     wintypes.DWORD),
        ("dwFileVersionMS",    wintypes.DWORD),
        ("dwFileVersionLS",    wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask",    wintypes.DWORD),
        ("dwFileFlags",        wintypes.DWORD),
        ("dwFileOS",           wintypes.DWORD),
        ("dwFileType",         wintypes.DWORD),
        ("dwFileSubtype",      wintypes.DWORD),
        ("dwFileDateMS",       wintypes.DWORD),
        ("dwFileDateLS",       wintypes.DWORD),
    ]


def get_exe_version(path):
    """Возвращает строку вида '1.2.3.4' из метаданных exe (или '').

    Умеет разворачивать .lnk-ярлыки через process_check.resolve_target.
    """
    if not path:
        return ""

    real = path
    if path.lower().endswith(".lnk"):
        try:
            from process_check import resolve_target
            real = resolve_target(path) or path
        except Exception:
            real = path

    if not real or not os.path.isfile(real):
        return ""
    if not real.lower().endswith(".exe"):
        return ""

    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(real, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(real, 0, size, buf):
            return ""
        r = ctypes.c_void_p()
        length = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(
            buf, "\\", ctypes.byref(r), ctypes.byref(length)
        ):
            return ""
        info = ctypes.cast(
            r, ctypes.POINTER(_VS_FIXEDFILEINFO)
        ).contents
        ms = info.dwFileVersionMS
        ls = info.dwFileVersionLS
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return ""


# ================= ГЛОБАЛЬНЫЕ НАСТРОЙКИ ПЛИТОК =================
SETTINGS = {
    "show_covers":       True,
    "show_glow":         True,
    "show_status_text":  True,
    "show_tile_badges":  True,
}

BASE_TILE_WIDTH   = 200
BASE_TILE_HEIGHT  = 235
BASE_COVER_HEIGHT = 140
BASE_RADIUS       = 14
BASE_TILE_SPACING = 16

BASE_KILL_BTN_X = 14
BASE_KILL_BTN_Y = 200
BASE_KILL_BTN_W = 110
BASE_KILL_BTN_H = 22

SCALE_TILE = 1.0
SCALE_ICON = 1.0

TILE_WIDTH   = BASE_TILE_WIDTH
TILE_HEIGHT  = BASE_TILE_HEIGHT
COVER_HEIGHT = BASE_COVER_HEIGHT
TILE_SPACING = BASE_TILE_SPACING
RADIUS       = BASE_RADIUS

KILL_BTN_X = BASE_KILL_BTN_X
KILL_BTN_Y = BASE_KILL_BTN_Y
KILL_BTN_W = BASE_KILL_BTN_W
KILL_BTN_H = BASE_KILL_BTN_H


def set_scale(tile_percent, icon_percent):
    """Пересчитывает глобальные размеры плиток."""
    global SCALE_TILE, SCALE_ICON
    global TILE_WIDTH, TILE_HEIGHT, COVER_HEIGHT, TILE_SPACING, RADIUS
    global KILL_BTN_X, KILL_BTN_Y, KILL_BTN_W, KILL_BTN_H

    SCALE_TILE = max(0.5, min(2.0, float(tile_percent) / 100.0))
    SCALE_ICON = max(0.5, min(2.0, float(icon_percent) / 100.0))

    TILE_WIDTH   = int(round(BASE_TILE_WIDTH  * SCALE_TILE))
    TILE_HEIGHT  = int(round(BASE_TILE_HEIGHT * SCALE_TILE))
    COVER_HEIGHT = int(round(BASE_COVER_HEIGHT * SCALE_TILE))
    TILE_SPACING = int(round(BASE_TILE_SPACING * SCALE_TILE))
    RADIUS       = int(round(BASE_RADIUS * SCALE_TILE))

    KILL_BTN_X = int(round(BASE_KILL_BTN_X * SCALE_TILE))
    KILL_BTN_Y = int(round(BASE_KILL_BTN_Y * SCALE_TILE))
    KILL_BTN_W = int(round(BASE_KILL_BTN_W * SCALE_TILE))
    KILL_BTN_H = int(round(BASE_KILL_BTN_H * SCALE_TILE))

    log.info(
        f"tile scale: tile={tile_percent}% icon={icon_percent}% "
        f"→ {TILE_WIDTH}×{TILE_HEIGHT}"
    )


def _s(v):  return int(round(v * SCALE_TILE))
def _si(v): return int(round(v * SCALE_ICON))
def _fs(base_size): return max(6, int(round(base_size * SCALE_TILE)))


def apply_tile_settings(settings_dict):
    for k in SETTINGS.keys():
        if k in settings_dict:
            SETTINGS[k] = bool(settings_dict[k])


# ============== ОБЁРТКИ НАД icon_map ==============
def _get_fa_pixmap(name, size, color_hex):
    return icon_map.get_pixmap(name, size, color_hex)


def _get_fa_icon(name, color_hex):
    return icon_map.get_icon(name, color_hex)


def clear_fa_cache():
    icon_map.clear_cache()


def _cover_pixmap(path, w, h):
    try:
        w, h = int(w), int(h)
        pix = QPixmap(path)
        if pix.isNull():
            return None
        pix = _scaled(
            pix, w, h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (pix.width() - w) // 2)
        y = max(0, (pix.height() - h) // 2)
        return pix.copy(int(x), int(y), w, h)
    except Exception:
        return None


# ============== АВТО-ОБЛОЖКИ ИЗ ПАПКИ КАТЕГОРИИ ==============
_cover_file_cache = {}
_cover_cache_lock = threading.Lock()


def pick_cover_from_folder(folder, seed=""):
    if not folder or not os.path.isdir(folder):
        return ""
    key = (folder, str(seed))
    with _cover_cache_lock:
        if key in _cover_file_cache:
            return _cover_file_cache[key]
    try:
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
        files = sorted(
            f for f in os.listdir(folder)
            if f.lower().endswith(exts)
        )
        if not files:
            with _cover_cache_lock:
                _cover_file_cache[key] = ""
            return ""
        idx = hash(str(seed)) % len(files)
        result = os.path.join(folder, files[idx])
        with _cover_cache_lock:
            _cover_file_cache[key] = result
        return result
    except Exception:
        return ""


def clear_cover_file_cache():
    with _cover_cache_lock:
        _cover_file_cache.clear()


# ============== ГРАДИЕНТ ДЛЯ РАМКИ ==============
def _make_border_brush(color_a, color_b, w, h, diagonal=True):
    if diagonal:
        grad = QLinearGradient(0, 0, w, h)
    else:
        grad = QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0.0, color_a)
    grad.setColorAt(0.5, color_b)
    grad.setColorAt(1.0, color_a)
    return QBrush(grad)


def _blend_color(c1, c2, t):
    t = max(0.0, min(1.0, float(t)))
    r = int(c1.red()   + (c2.red()   - c1.red())   * t)
    g = int(c1.green() + (c2.green() - c1.green()) * t)
    b = int(c1.blue()  + (c2.blue()  - c1.blue())  * t)
    a = int(c1.alpha() + (c2.alpha() - c1.alpha()) * t)
    return QColor(r, g, b, a)


# ============== ФОНОВАЯ ЗАГРУЗКА ОБЛОЖЕК ==============

class _CoverLoaderSignals(QObject):
    done = Signal(object)


class _CoverLoaderTask(QRunnable):
    def __init__(self, app, colors, icon_png_path, target_w, target_h,
                 signals):
        super().__init__()
        self.app = app
        self.colors = colors
        self.icon_png_path = icon_png_path
        self.target_w = target_w
        self.target_h = target_h
        self.signals = signals
        self.setAutoDelete(True)

    def _cleanup_icon(self):
        if self.icon_png_path:
            try:
                os.remove(self.icon_png_path)
            except Exception:
                pass
            self.icon_png_path = None

    def run(self):
        path = None
        try:
            path = self._prepare_path()
        except Exception as e:
            log.error(f"_CoverLoaderTask.run: {e}")
            path = None
        finally:
            self._cleanup_icon()
        try:
            self.signals.done.emit(path)
        except Exception:
            pass

    def _prepare_path(self):
        app = self.app
        colors = self.colors

        custom = app.get("custom_cover", "")
        if custom and os.path.exists(custom):
            return custom

        folder = app.get("_category_cover_folder", "")
        if folder:
            picked = pick_cover_from_folder(
                folder, seed=app.get("path", "")
            )
            if picked:
                return picked

        auto = app.get("_auto_cover_enabled", False)
        if auto and self.icon_png_path:
            try:
                import cover_generator
                result = cover_generator.ensure_cover_file(
                    app, colors,
                    w=max(200, self.target_w * 2),
                    h=max(140, self.target_h * 2),
                    icon_png_path=self.icon_png_path,
                )
                return result
            except Exception as e:
                log.error(f"auto cover: {e}")

        return None


# ================= КАРТОЧКА =================

class TileCard(QFrame):
    clicked                = Signal(dict)
    rename_requested       = Signal(dict)
    change_path_requested  = Signal(dict)
    delete_requested       = Signal(dict)
    toggle_favorite        = Signal(dict)
    open_folder            = Signal(dict)
    change_icon_requested  = Signal(dict)
    reset_icon_requested   = Signal(dict)
    change_cover_requested = Signal(dict)
    reset_cover_requested  = Signal(dict)
    change_category        = Signal(dict)
    change_subcategory     = Signal(dict)
    move_requested         = Signal(dict, str)
    kill_process           = Signal(dict)
    set_hotkey_requested   = Signal(dict)
    companions_requested   = Signal(dict)
    set_note_requested     = Signal(dict)
    accept_update          = Signal(dict)
    drop_on_requested      = Signal(dict, dict)
    launch_admin_requested = Signal(dict)

    def __init__(self, app, colors, menu_style="", is_launching=False,
                 parent=None):
        super().__init__(parent)
        self.app = app
        self.colors = colors
        self.menu_style = menu_style
        self.is_launching = is_launching
        self.selected = False
        self._hover = False
        self._kill_hover = False
        self._drag_start = None
        self._note_badge_rect = None
        self._over_note_badge = False
        self.context_menu_hook = None

        self._hover_progress = 0.0
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(220)
        self._hover_anim.setEasingCurve(QEasingCurve.OutBack)
        self._hover_anim.valueChanged.connect(self._on_hover_anim)

        self._ripple_progress = 0.0
        self._ripple_pos = QPointF(0, 0)
        self._ripple_anim = QVariantAnimation(self)
        self._ripple_anim.setDuration(550)
        self._ripple_anim.setStartValue(0.0)
        self._ripple_anim.setEndValue(1.0)
        self._ripple_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._ripple_anim.valueChanged.connect(self._on_ripple_anim)
        self._ripple_anim.finished.connect(self._on_ripple_finished)

        self.exists = file_exists(app.get("path", ""))
        self.running = (
            is_process_running(app.get("path", "")) if self.exists else False
        )

        self.setFixedSize(TILE_WIDTH, TILE_HEIGHT)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.setToolTip("")

        self._glow = 1.0
        self._glow_anim = None
        if self.running and SETTINGS["show_glow"]:
            self._glow_anim = QVariantAnimation(self)
            self._glow_anim.setDuration(1800)
            self._glow_anim.setStartValue(0.35)
            self._glow_anim.setEndValue(1.0)
            self._glow_anim.setLoopCount(-1)
            self._glow_anim.setEasingCurve(QEasingCurve.InOutSine)
            self._glow_anim.valueChanged.connect(self._on_glow)
            self._glow_anim.start()

        self._cover_pix = None
        self._cover_signals = None
        self._cover_loading = False
        self._needs_cover = bool(SETTINGS.get("show_covers", True))

        icon_size = _si(32) if self._needs_cover else _si(72)
        self._icon_size = icon_size
        self._icon = self._make_fast_placeholder_icon(icon_size)

        if self._needs_cover:
            self._schedule_cover_load()
        QTimer.singleShot(50, self._load_real_icon)

    # ============ БЫСТРЫЙ PLACEHOLDER ============
    def _make_fast_placeholder_icon(self, size):
        try:
            from icons import _make_placeholder
            return _make_placeholder(self.app.get("path", ""), size)
        except Exception:
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            return pix

    # ============ ФОНОВАЯ ЗАГРУЗКА ОБЛОЖКИ ============
    def _schedule_cover_load(self):
        if self._cover_loading:
            return
        self._cover_loading = True

        icon_png_path = None
        try:
            import cover_generator
            key = cover_generator._cache_key(
                self.app,
                max(200, TILE_WIDTH * 2),
                max(140, COVER_HEIGHT * 2),
                self.colors.get("ACCENT", "#89B4FA"),
            )
            icon_png_path = cover_generator._save_icon_as_png(
                self.app, key, 256
            )
        except Exception as e:
            log.error(f"_schedule_cover_load icon: {e}")
            icon_png_path = None

        signals = _CoverLoaderSignals()
        signals.done.connect(self._on_cover_ready)

        task = _CoverLoaderTask(
            self.app, self.colors, icon_png_path,
            TILE_WIDTH, COVER_HEIGHT, signals,
        )
        QThreadPool.globalInstance().start(task)

        self._cover_signals = signals

    def _on_cover_ready(self, path):
        try:
            self._cover_loading = False
            if not path or not os.path.exists(path):
                return
            pix = _cover_pixmap(path, TILE_WIDTH, COVER_HEIGHT)
            if pix is None or pix.isNull():
                return
            self._cover_pix = pix
            self.update()
        except Exception as e:
            log.error(f"_on_cover_ready: {e}")

    def _load_real_icon(self):
        try:
            pix = get_icon(self.app, self._icon_size)
            if pix and not pix.isNull():
                self._icon = pix
                self.update()
        except Exception as e:
            log.error(f"_load_real_icon: {e}")

    # ============ АНИМАЦИИ ============
    def _on_glow(self, value):
        self._glow = float(value)
        self.update()

    def _on_hover_anim(self, value):
        self._hover_progress = float(value)
        self.update()

    def _on_ripple_anim(self, value):
        self._ripple_progress = float(value)
        self.update()

    def _on_ripple_finished(self):
        self._ripple_progress = 0.0
        self.update()

    def _start_ripple(self, pos):
        try:
            self._ripple_pos = QPointF(pos)
            self._ripple_anim.stop()
            self._ripple_progress = 0.0
            self._ripple_anim.start()
        except Exception:
            pass

    def _kill_rect(self):
        return QRectF(KILL_BTN_X, KILL_BTN_Y, KILL_BTN_W, KILL_BTN_H)

    def _is_over_kill_btn(self, pos):
        if not (self.running and self.exists):
            return False
        return self._kill_rect().contains(QPointF(pos))

    # ============ РИСОВАНИЕ ============
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        c = self.colors
        w, h = self.width(), self.height()
        radius = RADIUS

        hover_t = max(0.0, min(1.5, self._hover_progress))

        state = "normal"
        if self.selected or self._hover:
            state = "accent"
            border_w = _s(2)
        elif self.running and self.exists:
            state = "running"
            border_w = _s(2)
        elif self.is_launching:
            state = "launching"
            border_w = _s(2)
        else:
            border_w = _s(1)

        if (self.running and self.exists and not self.selected
                and SETTINGS["show_glow"]):
            glow_rgb = QColor(c["OK"])
            layers = 18
            for i in range(layers, 0, -1):
                t = i / layers
                alpha = int(80 * (t ** 2.2) * self._glow)
                if alpha <= 0:
                    continue
                glow_rgb.setAlpha(alpha)
                p.setPen(Qt.NoPen)
                p.setBrush(glow_rgb)
                inset = i * 0.8 * SCALE_TILE
                r = max(2, radius - inset * 0.4)
                p.drawRoundedRect(
                    QRectF(inset, inset, w - inset * 2, h - inset * 2),
                    r, r
                )
        elif self.is_launching:
            glow_rgb = QColor(c["ACCENT"])
            layers = 14
            for i in range(layers, 0, -1):
                t = i / layers
                alpha = int(65 * (t ** 2.2))
                if alpha <= 0:
                    continue
                glow_rgb.setAlpha(alpha)
                p.setPen(Qt.NoPen)
                p.setBrush(glow_rgb)
                inset = i * 0.8 * SCALE_TILE
                r = max(2, radius - inset * 0.4)
                p.drawRoundedRect(
                    QRectF(inset, inset, w - inset * 2, h - inset * 2),
                    r, r
                )

        card_base = QColor(c["CARD"])
        card_hover = QColor(c["CARD_HOVER"])
        bg_color = _blend_color(card_base, card_hover, hover_t)
        p.setPen(Qt.NoPen)
        p.setBrush(bg_color)
        p.drawRoundedRect(
            QRectF(border_w, border_w,
                   w - border_w * 2, h - border_w * 2),
            radius - border_w, radius - border_w,
        )

        if state == "normal":
            p.setPen(QPen(QColor(c["BORDER"]), border_w))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(
                QRectF(border_w / 2, border_w / 2,
                       w - border_w, h - border_w),
                radius, radius,
            )
        else:
            if state == "running":
                base = QColor(c["OK"])
                light = QColor(c["OK"]).lighter(135)
            elif state == "launching":
                base = QColor(c["ACCENT"])
                light = QColor(c["ACCENT"]).lighter(140)
            else:
                base = QColor(c["ACCENT"])
                light = QColor(c["ACCENT_HOV"])

            brush = _make_border_brush(base, light, w, h, diagonal=True)
            p.setPen(QPen(brush, border_w))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(
                QRectF(border_w / 2, border_w / 2,
                       w - border_w, h - border_w),
                radius, radius,
            )

        cover_rect = QRectF(
            border_w, border_w,
            w - border_w * 2, COVER_HEIGHT - border_w,
        )
        cover_path = QPainterPath()
        cr = radius - border_w
        cover_path.moveTo(cover_rect.left(), cover_rect.bottom())
        cover_path.lineTo(cover_rect.left(), cover_rect.top() + cr)
        cover_path.quadTo(
            cover_rect.left(), cover_rect.top(),
            cover_rect.left() + cr, cover_rect.top(),
        )
        cover_path.lineTo(cover_rect.right() - cr, cover_rect.top())
        cover_path.quadTo(
            cover_rect.right(), cover_rect.top(),
            cover_rect.right(), cover_rect.top() + cr,
        )
        cover_path.lineTo(cover_rect.right(), cover_rect.bottom())
        cover_path.closeSubpath()

        p.setClipPath(cover_path)

        if self._cover_pix and not self._cover_pix.isNull():
            p.drawPixmap(cover_rect.toRect(), self._cover_pix)
            grad_h = _s(70)
            grad = QLinearGradient(0, COVER_HEIGHT - grad_h, 0, COVER_HEIGHT)
            grad.setColorAt(0, QColor(0, 0, 0, 0))
            grad.setColorAt(1, QColor(0, 0, 0, 160))
            p.fillRect(
                QRectF(0, COVER_HEIGHT - grad_h, w, grad_h), QBrush(grad)
            )
            if self._icon and not self._icon.isNull():
                badge_size = _s(44)
                bx = _s(10)
                by = COVER_HEIGHT - badge_size - _s(10)
                p.setBrush(QColor(c["BG_ALT"]))
                p.setPen(QPen(QColor(c["ACCENT"]), max(1, _s(2))))
                p.drawRoundedRect(
                    QRectF(bx, by, badge_size, badge_size),
                    _s(10), _s(10),
                )
                iw = self._icon.width()
                ih = self._icon.height()
                p.drawPixmap(
                    int(bx + (badge_size - iw) / 2),
                    int(by + (badge_size - ih) / 2),
                    self._icon,
                )
        else:
            grad = QLinearGradient(0, border_w, 0, COVER_HEIGHT)
            grad.setColorAt(0, QColor(c["BG_ALT"]))
            grad.setColorAt(1, QColor(c["BG"]))
            p.fillRect(cover_rect, QBrush(grad))
            if self._icon and not self._icon.isNull():
                iw = self._icon.width()
                ih = self._icon.height()
                pad = _s(10)
                p.setBrush(QColor(c["ACCENT_SOFT"]))
                p.setPen(QPen(QColor(c["ACCENT"]), max(1, _s(1))))
                p.drawRoundedRect(
                    QRectF(
                        (w - iw) / 2 - pad,
                        (COVER_HEIGHT - ih) / 2 - pad,
                        iw + pad * 2,
                        ih + pad * 2,
                    ),
                    _s(20), _s(20),
                )
                p.drawPixmap(
                    int((w - iw) / 2),
                    int((COVER_HEIGHT - ih) / 2),
                    self._icon,
                )

        p.setClipping(False)

        p.setPen(QPen(QColor(c["BORDER"]), 1))
        p.drawLine(
            int(border_w), COVER_HEIGHT,
            int(w - border_w), COVER_HEIGHT,
        )

        # ====== БЕЙДЖИ ======
        self._note_badge_rect = None
        if SETTINGS["show_tile_badges"]:
            badges = []

            if self.app.get("favorite"):
                badges.append(("fa5s.star", "#F9E2AF", "★", "fav"))

            note = (self.app.get("note") or "").strip()
            if note:
                badges.append(("fa5s.sticky-note", c["ACCENT"], "📝", "note"))

            if self.app.get("_has_update"):
                badges.append(("fa5s.arrow-circle-up", c["OK"], "⬆", "update"))

            companions = self.app.get("companions", []) or []
            if companions:
                badges.append(("fa5s.link", c["ACCENT"], None, "comp"))

            bx = _s(10)
            by = _s(10)
            for i, (icon_name, icon_color, fallback, key) in enumerate(badges):
                bw_ = _s(30)
                if key == "comp":
                    bw_ = _s(44)
                bh_ = _s(26)

                p.setPen(Qt.NoPen)
                p.setBrush(QColor(30, 30, 46, 210))
                p.drawRoundedRect(bx, by, bw_, bh_, _s(10), _s(10))

                if key == "note":
                    self._note_badge_rect = QRectF(bx, by, bw_, bh_)

                if key == "comp":
                    link_pix = _get_fa_pixmap("fa5s.link", _s(12), icon_color)
                    if link_pix:
                        p.drawPixmap(
                            bx + _s(6),
                            int(by + (bh_ - link_pix.height()) / 2),
                            link_pix,
                        )
                    p.setPen(QColor(icon_color))
                    p.setFont(QFont("Segoe UI", _fs(10), QFont.Bold))
                    p.drawText(
                        QRect(bx + _s(20), by, bw_ - _s(20), bh_),
                        Qt.AlignCenter,
                        str(len(companions)),
                    )
                else:
                    pix = _get_fa_pixmap(icon_name, _s(14), icon_color)
                    if pix:
                        p.drawPixmap(
                            int(bx + (bw_ - pix.width()) / 2),
                            int(by + (bh_ - pix.height()) / 2),
                            pix,
                        )
                    elif fallback:
                        p.setPen(QColor(icon_color))
                        p.setFont(QFont("Segoe UI", _fs(13)))
                        p.drawText(
                            QRect(bx, by, bw_, bh_), Qt.AlignCenter, fallback
                        )

                bx += bw_ + _s(6)

        # ====== ИМЯ ======
        info_y = COVER_HEIGHT + _s(6)
        name_color = QColor(c["TEXT"] if self.exists else c["DANGER"])
        p.setPen(name_color)
        name_font = QFont("Segoe UI", _fs(10))
        name_font.setBold(True)
        p.setFont(name_font)

        name = self.app.get("name", "Без имени")
        max_chars = max(10, int(22 * SCALE_TILE))
        if len(name) > max_chars:
            name = name[:max_chars - 2] + "…"
        p.drawText(
            QRect(_s(14), info_y, w - _s(28), _s(20)),
            Qt.AlignLeft | Qt.AlignVCenter, name,
        )

        # ====== СТАТУС ======
        status_y = info_y + _s(22)
        if not self.exists:
            status_text = "Не найден"
            status_color = QColor(c["DANGER"])
            status_icon = "fa5s.exclamation-triangle"
            status_icon_color = c["DANGER"]
        elif self.is_launching:
            status_text = "Запускается"
            status_color = QColor(c["ACCENT"])
            status_icon = "fa5s.hourglass-half"
            status_icon_color = c["ACCENT"]
        elif self.running:
            status_text = "Работает"
            status_color = QColor(c["OK"])
            status_icon = "fa5s.circle"
            status_icon_color = c["OK"]
        else:
            status_text = "Не запущено"
            status_color = QColor(c["SUBTEXT"])
            status_icon = "fa5s.circle"
            status_icon_color = c["SUBTEXT"]

        dot_x = _s(18)
        dot_y = status_y + _s(9)

        if self.running and self.exists and SETTINGS["show_glow"]:
            sz = 4.0 + 1.5 * (self._glow - 0.35) / 0.65
            glow_dot = QColor(c["OK"])
            glow_dot.setAlpha(int(100 * self._glow))
            p.setBrush(glow_dot)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(dot_x, dot_y),
                          (sz + 3) * SCALE_TILE,
                          (sz + 3) * SCALE_TILE)

        status_pix = _get_fa_pixmap(status_icon, _s(12), status_icon_color)
        if status_pix:
            p.drawPixmap(
                _s(12),
                int(status_y + (_s(18) - status_pix.height()) / 2),
                status_pix,
            )
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(status_color))
            p.drawEllipse(QPointF(dot_x, dot_y), _s(4), _s(4))

        if SETTINGS["show_status_text"]:
            p.setPen(status_color)
            p.setFont(QFont("Segoe UI", _fs(8)))
            p.drawText(
                QRect(_s(30), status_y, w - _s(76), _s(18)),
                Qt.AlignLeft | Qt.AlignVCenter, status_text,
            )

        if self.running and self.exists:
            check_pix = _get_fa_pixmap("fa5s.check", _s(12), c["OK"])
            if check_pix:
                p.drawPixmap(
                    int(w - _s(26)),
                    int(status_y + (_s(18) - check_pix.height()) / 2),
                    check_pix,
                )
            else:
                p.setPen(QColor(c["OK"]))
                check_font = QFont("Segoe UI", _fs(11))
                check_font.setBold(True)
                p.setFont(check_font)
                p.drawText(
                    QRect(w - _s(32), status_y, _s(22), _s(18)),
                    Qt.AlignCenter, "✓",
                )

        # ====== КНОПКА ЗАВЕРШЕНИЯ ======
        if self.running and self.exists:
            rect = self._kill_rect()
            if self._kill_hover:
                bg = QColor(c["DANGER"]); fg = QColor("#FFFFFF")
                pen = QColor(c["DANGER"])
            else:
                bg = QColor(c["BG_ALT"]); fg = QColor(c["DANGER"])
                pen = QColor(c["DANGER"])

            p.setBrush(bg)
            p.setPen(QPen(pen, 1))
            p.drawRoundedRect(rect, _s(6), _s(6))

            stop_pix = _get_fa_pixmap(
                "fa5s.stop-circle", _s(11),
                "#FFFFFF" if self._kill_hover else c["DANGER"]
            )
            if stop_pix:
                p.drawPixmap(
                    int(rect.left() + _s(10)),
                    int(rect.top() + (rect.height() - stop_pix.height()) / 2),
                    stop_pix,
                )
                p.setPen(fg)
                p.setFont(QFont("Segoe UI", _fs(9), QFont.Bold))
                p.drawText(
                    QRect(int(rect.left()) + _s(24), int(rect.top()),
                          int(rect.width()) - _s(24), int(rect.height())),
                    Qt.AlignLeft | Qt.AlignVCenter, "Завершить",
                )
            else:
                p.setPen(fg)
                p.setFont(QFont("Segoe UI", _fs(9), QFont.Bold))
                p.drawText(rect, Qt.AlignCenter, "Завершить")

        # ====== RIPPLE ======
        if self._ripple_progress > 0.001:
            try:
                clip_path = QPainterPath()
                clip_path.addRoundedRect(
                    QRectF(0, 0, w, h), radius, radius
                )
                p.setClipPath(clip_path)

                max_r = max(w, h) * 1.35
                r = max_r * self._ripple_progress
                alpha = int(90 * (1.0 - self._ripple_progress) ** 1.6)
                if alpha > 0:
                    col = QColor(c["ACCENT"])
                    col.setAlpha(alpha)
                    p.setPen(Qt.NoPen)
                    p.setBrush(col)
                    p.drawEllipse(self._ripple_pos, r, r)
                p.setClipping(False)
            except Exception:
                pass

    # ============ СОБЫТИЯ ============
    def set_selected(self, value: bool):
        self.selected = value
        self.update()

    def enterEvent(self, event):
        self._hover = True
        try:
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_progress)
            self._hover_anim.setEndValue(1.0)
            self._hover_anim.setEasingCurve(QEasingCurve.OutBack)
            self._hover_anim.start()
        except Exception:
            self._hover_progress = 1.0
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self._kill_hover = False
        self._over_note_badge = False
        try:
            custom_tooltip.hide_tooltip()
        except Exception:
            pass
        try:
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_progress)
            self._hover_anim.setEndValue(0.0)
            self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._hover_anim.start()
        except Exception:
            pass
        self.update()

    def _build_note_tooltip(self):
        name = self.app.get("name", "")
        note = (self.app.get("note") or "").strip()
        safe_name = (name
                     .replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;"))
        safe_note = (note
                     .replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;"))
        html = (
            f'<div style="font-weight:bold; font-size:13px;">'
            f'📝 {safe_name}</div>'
            f'<div style="margin-top:6px; opacity:0.85;">{safe_note}</div>'
        )
        return html

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        in_kill = self._is_over_kill_btn(pos)
        if in_kill != self._kill_hover:
            self._kill_hover = in_kill
            self.update()

        if self._drag_start and (event.buttons() & Qt.LeftButton):
            delta = (event.position().toPoint() - self._drag_start)
            if delta.manhattanLength() > 15:
                self._start_drag()
                self._drag_start = None

        note_rect = self._note_badge_rect
        if note_rect is not None and note_rect.contains(QPointF(pos)):
            if not self._over_note_badge:
                self._over_note_badge = True
                try:
                    custom_tooltip.show_tooltip(
                        event.globalPosition().toPoint(),
                        self._build_note_tooltip(),
                        self.colors,
                        timeout_ms=4000,
                    )
                except Exception as e:
                    log.error(f"show_tooltip: {e}")
        else:
            if self._over_note_badge:
                self._over_note_badge = False
                try:
                    custom_tooltip.hide_tooltip()
                except Exception:
                    pass

        super().mouseMoveEvent(event)

    def _start_drag(self):
        try:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(DRAG_MIME, json.dumps(self.app).encode("utf-8"))
            drag.setMimeData(mime)
            pix = self.grab()
            if not pix.isNull():
                drag.setPixmap(pix)
                drag.setHotSpot(QPoint(pix.width() // 2, pix.height() // 2))
            drag.exec(Qt.MoveAction)
        except Exception as e:
            log.error(f"start drag: {e}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(DRAG_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(DRAG_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(DRAG_MIME):
            return
        try:
            data = bytes(event.mimeData().data(DRAG_MIME)).decode("utf-8")
            src = json.loads(data)
        except Exception:
            return
        if src.get("path") == self.app.get("path"):
            return
        self.drop_on_requested.emit(src, self.app)
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            if self._is_over_kill_btn(pos):
                self.kill_process.emit(self.app)
                return
            self._start_ripple(pos)
            self._drag_start = pos

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._drag_start is not None:
                self.clicked.emit(self.app)
            self._drag_start = None
        super().mouseReleaseEvent(event)

    # ============ МЕНЮ ============
    def contextMenuEvent(self, event):
        c = self.colors
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_style)

        running = is_process_running(self.app.get("path", ""))
        companions = self.app.get("companions", []) or []

        def add_action(icon_name, text, color=None):
            if color is None:
                color = c["TEXT"]
            icon = _get_fa_icon(icon_name, color)
            if icon_map.HAS_QTAWESOME:
                return menu.addAction(icon, text)
            return menu.addAction(text)

        act_launch = add_action("fa5s.play", "Запустить", c["ACCENT"])
        act_launch_admin = add_action(
            "fa5s.user-shield",
            "Запустить от имени администратора",
            c["TEXT"],
        )

        menu.addSeparator()
        act_up_first  = add_action("fa5s.angle-double-up", "Наверх")
        act_up        = add_action("fa5s.angle-up", "Выше")
        act_down      = add_action("fa5s.angle-down", "Ниже")
        act_down_last = add_action("fa5s.angle-double-down", "В конец")
        menu.addSeparator()

        if self.app.get("favorite"):
            act_fav = add_action("fa5s.star-half-alt",
                                 "Убрать из избранного", "#F9E2AF")
        else:
            act_fav = add_action("fa5s.star", "В избранное", "#F9E2AF")

        act_rename = add_action("fa5s.pen", "Переименовать")
        act_change = add_action("fa5s.folder-open", "Изменить путь")

        note_text = "Изменить заметку"
        if (self.app.get("note") or "").strip():
            note_text = "Изменить заметку  📝"
        act_note = add_action("fa5s.sticky-note", note_text)

        act_icon = add_action("fa5s.image", "Сменить иконку")
        if self.app.get("custom_icon"):
            act_reset_icon = add_action("fa5s.undo-alt",
                                        "Сбросить иконку", c["SUBTEXT"])
        else:
            act_reset_icon = None

        act_cover = add_action("fa5s.panorama", "Сменить обложку")
        if self.app.get("custom_cover"):
            act_reset_cover = add_action("fa5s.undo-alt",
                                         "Сбросить обложку", c["SUBTEXT"])
        else:
            act_reset_cover = None

        act_category = add_action("fa5s.tag", "Изменить категорию")
        act_subcategory = add_action("fa5s.tags", "Подкатегория")

        act_accept_update = None
        if self.app.get("_has_update"):
            act_accept_update = add_action(
                "fa5s.arrow-circle-up",
                "Принять обновление",
                c["OK"],
            )

        if companions:
            comp_text = f"Спутники запуска ({len(companions)})"
        else:
            comp_text = "Настроить спутники"
        act_companions = add_action("fa5s.link", comp_text, c["ACCENT"])

        if self.app.get("hotkey"):
            act_hotkey = add_action(
                "fa5s.keyboard",
                f"Изменить hotkey ({self.app['hotkey']})"
            )
            act_hotkey_clear = add_action("fa5s.times", "Убрать hotkey")
        else:
            act_hotkey = add_action("fa5s.keyboard", "Назначить hotkey")
            act_hotkey_clear = None

        act_folder = add_action("fa5s.folder", "Открыть папку")

        if running:
            menu.addSeparator()
            act_kill = add_action("fa5s.stop-circle",
                                  "Завершить процесс", c["DANGER"])
        else:
            act_kill = None

        menu.addSeparator()
        act_delete = add_action("fa5s.trash-alt", "Удалить", c["DANGER"])

        # Хук плагинов — могут добавить свои пункты в меню
        if self.context_menu_hook is not None:
            try:
                self.context_menu_hook(self.app, menu)
            except Exception as e:
                log.error(f"context_menu_hook: {e}")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen == act_launch:
            self.clicked.emit(self.app)
        elif chosen == act_launch_admin:
            self.launch_admin_requested.emit(self.app)
        elif chosen == act_up_first:
            self.move_requested.emit(self.app, "top")
        elif chosen == act_up:
            self.move_requested.emit(self.app, "up")
        elif chosen == act_down:
            self.move_requested.emit(self.app, "down")
        elif chosen == act_down_last:
            self.move_requested.emit(self.app, "bottom")
        elif chosen == act_fav:
            self.toggle_favorite.emit(self.app)
        elif chosen == act_rename:
            self.rename_requested.emit(self.app)
        elif chosen == act_change:
            self.change_path_requested.emit(self.app)
        elif chosen == act_note:
            self.set_note_requested.emit(self.app)
        elif chosen == act_icon:
            self.change_icon_requested.emit(self.app)
        elif act_reset_icon is not None and chosen == act_reset_icon:
            self.reset_icon_requested.emit(self.app)
        elif chosen == act_cover:
            self.change_cover_requested.emit(self.app)
        elif act_reset_cover is not None and chosen == act_reset_cover:
            self.reset_cover_requested.emit(self.app)
        elif chosen == act_category:
            self.change_category.emit(self.app)
        elif chosen == act_subcategory:
            self.change_subcategory.emit(self.app)
        elif act_accept_update is not None and chosen == act_accept_update:
            self.accept_update.emit(self.app)
        elif chosen == act_companions:
            self.companions_requested.emit(self.app)
        elif chosen == act_hotkey:
            self.set_hotkey_requested.emit(self.app)
        elif act_hotkey_clear is not None and chosen == act_hotkey_clear:
            self.app["_clear_hotkey"] = True
            self.set_hotkey_requested.emit(self.app)
        elif chosen == act_folder:
            self.open_folder.emit(self.app)
        elif act_kill is not None and chosen == act_kill:
            self.kill_process.emit(self.app)
        elif chosen == act_delete:
            self.delete_requested.emit(self.app)