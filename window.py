"""Главное окно: Epic-стиль + FA + тосты + профили + эффекты JARVIS."""

import os
import sys
import ctypes
import traceback
from ctypes import wintypes
from datetime import datetime
from urllib.parse import quote

from PySide6.QtCore import (
    Qt, Signal, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QSize,
    QPoint, QEvent, QThreadPool, Property,
    QRunnable, QObject,
)

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QFrame, QScrollArea,
    QMenu, QSystemTrayIcon, QApplication, QDialog, QComboBox,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QSize,
    QPoint, QEvent, QThreadPool, Property,
    QRunnable, QObject,
)
from PySide6.QtGui import (
    QAction, QIcon, QPixmap, QPainter, QColor, QFont,
    QDesktopServices, QPen, QBrush, QLinearGradient,
)

try:
    import qtawesome as qta  # type: ignore[import-untyped]
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False
    qta = None

try:
    from pyqttoast import Toast, ToastPreset
    HAS_TOAST = True
except ImportError:
    HAS_TOAST = False
    Toast = None
    ToastPreset = None

from config import APP_NAME, APP_VERSION, CATEGORIES, DEFAULT_SETTINGS
from themes import get_theme
from storage import (
    load_apps, save_apps, load_settings, save_settings, backup_apps,
    backup_all, load_presets, save_presets, log,
    get_last_load_error, clear_last_load_error,
)
from profiles import apply_profile
from stats import load_stats, save_stats, add_time
from launcher import launch, launch_as_admin
from process_check import (
    is_process_running, kill_process, clear_lnk_cache,
)
from icons import clear_cache, get_icon
import icon_map
import sounds
import window_activation
import sysmonitor
import cover_generator
import notifications
import discord_rpc
import game_scanner

try:
    import cover_fetcher
    HAS_COVER_FETCHER = True
except Exception:
    cover_fetcher = None
    HAS_COVER_FETCHER = False

from games_library import GamesLibraryDialog
from sysmonitor import SystemMonitorWidget
from animated_bg import AnimatedBackground
from plugin_manager import PluginManager
import tile_card
from tile_card import (
    TileCard, clear_fa_cache, apply_tile_settings, set_scale as set_tile_scale,
    get_exe_version, pick_cover_from_folder,
)
from presets_dialog import PresetsDialog
from dialogs import (
    show_error, show_info, ask_text, ask_category, ask_already_running,
    ask_confirm, ask_hotkey,
)
from settings_dialog import SettingsDialog
from quick_launcher import QuickLauncher
from overlay import LaunchOverlay
from companion_picker import CompanionPickerDialog


SWP_NOSIZE       = 0x0001
SWP_NOMOVE       = 0x0002
SWP_NOACTIVATE   = 0x0010

HWND_TOPMOST     = -1
HWND_NOTOPMOST   = -2

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

RESIZE_BORDER    = 8


def set_always_on_top_native(window, on: bool):
    try:
        hwnd = int(window.winId())
        ctypes.windll.user32.SetWindowPos(
            hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST,
            0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )
    except Exception as e:
        log.error(f"set_always_on_top_native error: {e}")


def set_rounded_corners(window):
    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception as e:
        log.error(f"set_rounded_corners error: {e}")


def make_tray_icon(colors, custom_path="", app_name=""):
    if custom_path and os.path.exists(custom_path):
        try:
            pix = QPixmap(custom_path)
            if not pix.isNull():
                return QIcon(pix)
        except Exception:
            pass

    letter = "?"
    name = (app_name or APP_NAME or "").strip()
    if name:
        letter = name[0].upper()

    accent = colors["ACCENT"]
    bg_letter = colors["BG"]
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(accent))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, 64, 64, 14, 14)
    p.setPen(QColor(bg_letter))
    p.setFont(QFont("Segoe UI", 34, QFont.Bold))
    p.drawText(pix.rect(), Qt.AlignCenter, letter)
    p.end()
    return QIcon(pix)


CAT_ICONS = {
    "all":     "fa5s.th-large",
    "recent":  "fa5s.history",
    "games":   "fa5s.gamepad",
    "work":    "fa5s.briefcase",
    "system":  "fa5s.cog",
    "other":   "fa5s.box",
}


def get_active_monitor_geometry():
    try:
        from PySide6.QtCore import QRect

        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

        MONITOR_DEFAULTTONEAREST = 2
        hmon = ctypes.windll.user32.MonitorFromPoint(
            pt, MONITOR_DEFAULTTONEAREST
        )

        class _MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("rcMonitor", ctypes.c_long * 4),
                ("rcWork", ctypes.c_long * 4),
                ("dwFlags", ctypes.c_ulong),
            ]

        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            l, t, r, b = mi.rcWork
            return QRect(l, t, r - l, b - t)
    except Exception as e:
        log.error(f"get_active_monitor_geometry: {e}")

    try:
        return QApplication.primaryScreen().availableGeometry()
    except Exception:
        from PySide6.QtCore import QRect
        return QRect(0, 0, 1920, 1080)


class ScanLineOverlay(QWidget):
    def __init__(self, parent, color):
        super().__init__(parent)
        self.color = color
        self._y = -100
        self._anim = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.hide()

    def _get_y(self):
        return self._y

    def _set_y(self, value):
        self._y = int(value)
        self.update()

    scan_y = Property(int, _get_y, _set_y)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = self._y
        w = self.width()
        h = self.height()
        if y < -100 or y > h + 100:
            p.end()
            return
        c = self.color
        for offset, alpha in ((40, 30), (24, 60), (12, 100)):
            grad = QLinearGradient(0, y - offset, 0, y + offset)
            grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 0))
            grad.setColorAt(0.5, QColor(c.red(), c.green(), c.blue(), alpha))
            grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRect(0, y - offset, w, offset * 2)
        p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 220), 1.5))
        p.drawLine(0, y, w, y)
        p.end()

    def run(self, duration_ms=1500):
        parent = self.parent()
        if parent is None:
            return
        try:
            self.setGeometry(0, 0, parent.width(), parent.height())
            self._y = -100
            self.show()
            self.raise_()
            self._anim = QPropertyAnimation(self, b"scan_y", self)
            self._anim.setDuration(int(duration_ms))
            self._anim.setStartValue(-100)
            self._anim.setEndValue(self.height() + 100)
            self._anim.setEasingCurve(QEasingCurve.InOutCubic)
            self._anim.finished.connect(self.hide)
            self._anim.start()
        except Exception as e:
            log.error(f"ScanLineOverlay.run: {e}")

    class _VersionScanSignals(QObject):
        done = Signal(dict)  # {path: "1.2.3.4"}

    class _VersionScanTask(QRunnable):
        """Читает версии exe из WinAPI в фоне."""

        def __init__(self, paths):
            super().__init__()
            self.paths = list(paths)
            self.signals = _VersionScanSignals()
            self.setAutoDelete(True)

        def run(self):
            result = {}
            for p in self.paths:
                try:
                    v = get_exe_version(p)
                    if v:
                        result[p] = v
                except Exception:
                    continue
            try:
                self.signals.done.emit(result)
            except Exception:
                pass

class _VersionScanSignals(QObject):
    done = Signal(dict)   # {path: "1.2.3.4"}


class _VersionScanTask(QRunnable):
    """Читает версии .exe через WinAPI в фоновом потоке."""

    def __init__(self, paths):
        super().__init__()
        self.paths = list(paths)
        self.signals = _VersionScanSignals()
        self.setAutoDelete(True)

    def run(self):
        result = {}
        for p in self.paths:
            try:
                v = get_exe_version(p)
                if v:
                    result[p] = v
            except Exception:
                continue
        try:
            self.signals.done.emit(result)
        except Exception:
            pass

class QuickAppIcon(QFrame):
    clicked     = Signal(dict)
    right_click = Signal(dict, object)

    def __init__(self, app, colors, size=44, tooltip=None, parent=None):
        super().__init__(parent)
        self.app = app
        self.colors = colors
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(tooltip or app.get("name", ""))

        self._pix = None
        try:
            self._pix = get_icon(app, max(16, size - 12))
        except Exception:
            self._pix = None

        self._running = is_process_running(app.get("path", ""))
        self.setStyleSheet("background: transparent;")

    def refresh_running(self):
        try:
            new_running = is_process_running(self.app.get("path", ""))
        except Exception:
            new_running = self._running
        if new_running != self._running:
            self._running = new_running
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.colors
        w, h = self.width(), self.height()
        border_color = c["OK"] if self._running else c["BORDER"]
        bg_color = QColor(c["CARD"])
        if self.underMouse():
            bg_color = QColor(c["CARD_HOVER"])
            if not self._running:
                border_color = c["ACCENT"]
        p.setPen(QPen(QColor(border_color), 1.4))
        p.setBrush(bg_color)
        p.drawEllipse(0.8, 0.8, w - 1.6, h - 1.6)
        if self._pix and not self._pix.isNull():
            iw = self._pix.width()
            ih = self._pix.height()
            p.drawPixmap(int((w - iw) / 2), int((h - ih) / 2), self._pix)
        if self._running:
            dot_r = 3.0
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["OK"]))
            p.drawEllipse(w - 8.0, 4.0, dot_r * 2, dot_r * 2)
        p.end()

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.app)

    def contextMenuEvent(self, event):
        try:
            self.right_click.emit(self.app, event.globalPos())
        except Exception:
            pass


class CustomTitleBar(QFrame):
    def __init__(self, launcher, colors):
        super().__init__()
        self.launcher = launcher
        self.colors = colors
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(42)
        self._drag_offset = None
        self._is_maximized = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 10, 0)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(22, 22)
        self.icon_label.setStyleSheet("background: transparent;")
        try:
            name = (
                self.launcher._app_name()
                if hasattr(self.launcher, "_app_name")
                else APP_NAME
            )
            self.icon_label.setPixmap(
                make_tray_icon(colors, "", name).pixmap(22, 22)
            )
        except Exception:
            pass
        layout.addWidget(self.icon_label)

        name = (
            self.launcher._app_name()
            if hasattr(self.launcher, "_app_name")
            else APP_NAME
        )
        self.title_label = QLabel(name)
        layout.addWidget(self.title_label)
        self.sep1 = QLabel("·")
        layout.addWidget(self.sep1)
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.min_btn = QPushButton()
        self.min_btn.setFixedSize(32, 32)
        self.min_btn.setCursor(Qt.PointingHandCursor)
        self.min_btn.setToolTip("Свернуть")
        self.min_btn.clicked.connect(launcher.showMinimized)

        self.max_btn = QPushButton()
        self.max_btn.setFixedSize(32, 32)
        self.max_btn.setCursor(Qt.PointingHandCursor)
        self.max_btn.setToolTip("Развернуть")
        self.max_btn.clicked.connect(self._toggle_max)

        self.full_btn = QPushButton()
        self.full_btn.setFixedSize(32, 32)
        self.full_btn.setCursor(Qt.PointingHandCursor)
        self.full_btn.setToolTip("Полный экран (F11)")
        self.full_btn.clicked.connect(launcher.toggle_fullscreen)

        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("Закрыть")
        self.close_btn.clicked.connect(launcher.close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.full_btn)
        layout.addWidget(self.close_btn)

        self.apply_theme(colors)
        self.set_status(f"v{APP_VERSION}")
        self._refresh_icons()

    def set_status(self, text):
        self.status_label.setText(text)

    def _toggle_max(self):
        if self.launcher.isMaximized():
            self.launcher.showNormal()
            self._is_maximized = False
        else:
            self.launcher.showMaximized()
            self._is_maximized = True
        self._refresh_icons()

    def _refresh_icons(self):
        c = self.colors
        try:
            custom = getattr(self.launcher, "settings", {}).get("tray_icon", "")
            name = (
                self.launcher._app_name()
                if hasattr(self.launcher, "_app_name")
                else APP_NAME
            )
            self.icon_label.setPixmap(
                make_tray_icon(c, custom, name).pixmap(22, 22)
            )
        except Exception:
            pass

        if not icon_map.HAS_QTAWESOME:
            self.min_btn.setText("−")
            self.max_btn.setText("❐" if self._is_maximized else "□")
            self.full_btn.setText("⛶")
            self.close_btn.setText("✕")
            return

        try:
            self.min_btn.setIcon(icon_map.get_icon("fa5s.window-minimize", c["TEXT"]))
            self.min_btn.setIconSize(QSize(15, 15))
            if self._is_maximized:
                self.max_btn.setIcon(icon_map.get_icon("fa5s.window-restore", c["TEXT"]))
                self.max_btn.setToolTip("Восстановить")
            else:
                self.max_btn.setIcon(icon_map.get_icon("fa5s.window-maximize", c["TEXT"]))
                self.max_btn.setToolTip("Развернуть")
            self.max_btn.setIconSize(QSize(15, 15))
            if self.launcher.isFullScreen():
                self.full_btn.setIcon(icon_map.get_icon("fa5s.compress", c["ACCENT"]))
            else:
                self.full_btn.setIcon(icon_map.get_icon("fa5s.expand", c["TEXT"]))
            self.full_btn.setIconSize(QSize(15, 15))
            self.close_btn.setIcon(icon_map.get_icon("fa5s.times", c["TEXT"]))
            self.close_btn.setIconSize(QSize(16, 16))
        except Exception as e:
            log.error(f"titlebar icon error: {e}")

    def apply_theme(self, colors):
        c = colors
        self.setStyleSheet(f"""
            QFrame#CustomTitleBar {{
                background-color: {c['BG']};
                border: none;
            }}
        """)
        self.title_label.setStyleSheet(
            f"color: {c['TEXT']}; font-size: 12px; "
            f"font-weight: 600; background: transparent;"
        )
        self.sep1.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 12px; background: transparent;"
        )
        self.status_label.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 11px; background: transparent;"
        )
        base_btn = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 16px;
            }}
            QPushButton:hover {{ background-color: {c['CARD_HOVER']}; }}
            QPushButton:pressed {{ background-color: {c['ACCENT_SOFT']}; }}
        """
        close_btn_style = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 16px;
            }}
            QPushButton:hover {{ background-color: {c['DANGER']}; }}
        """
        self.min_btn.setStyleSheet(base_btn)
        self.max_btn.setStyleSheet(base_btn)
        self.full_btn.setStyleSheet(base_btn)
        self.close_btn.setStyleSheet(close_btn_style)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.launcher.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            if self.launcher.isMaximized():
                self.launcher.showNormal()
                self._is_maximized = False
                self._refresh_icons()
                self._drag_offset = (
                    event.globalPosition().toPoint()
                    - self.launcher.frameGeometry().topLeft()
                )
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.launcher.move(new_pos)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_max()


class CategoryFan(QWidget):
    def __init__(self, launcher, colors, on_select):
        super().__init__()
        self.launcher = launcher
        self.colors = colors
        self.on_select = on_select
        self.opened = False

        self.setMaximumHeight(0)
        self.setVisible(False)
        self.setMinimumHeight(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)

        self.buttons = {}
        for key, (name, _) in CATEGORIES.items():
            btn = QPushButton()
            icon_name = CAT_ICONS.get(key, "fa5s.folder")
            if icon_map.HAS_QTAWESOME:
                btn.setIcon(icon_map.get_icon(icon_name, colors["TEXT"]))
            else:
                btn.setText("●")
            btn.setIconSize(QSize(22, 22))
            btn.setFixedSize(48, 48)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(name)
            btn.clicked.connect(lambda _=False, k=key: self.on_select(k))
            layout.addWidget(btn)
            self.buttons[key] = btn

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._anim_h = QPropertyAnimation(self, b"maximumHeight", self)
        self._anim_h.setDuration(300)
        self._anim_h.setEasingCurve(QEasingCurve.OutCubic)

        self._anim_o = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim_o.setDuration(260)
        self._anim_o.setEasingCurve(QEasingCurve.OutCubic)

        # Один раз и навсегда: _after_close сам проверит флаг opened
        self._anim_h.finished.connect(self._after_close)

    def update_speed(self, percent):
        factor = 100.0 / max(50, min(200, percent))
        dur = int(300 * factor)
        self._anim_h.setDuration(dur)
        self._anim_o.setDuration(int(dur * 0.85))

    def target_height(self):
        n = len(self.buttons)
        if n == 0:
            return 0
        return 6 + n * 48 + (n - 1) * 8

    def toggle(self):
        if self.opened:
            self.close_fan()
        else:
            self.open_fan()

    def open_fan(self):
        if self.opened:
            return
        self.opened = True
        self.setVisible(True)
        self._anim_h.stop()
        self._anim_h.setStartValue(self.maximumHeight())
        self._anim_h.setEndValue(self.target_height())
        self._anim_h.start()
        self._anim_o.stop()
        self._anim_o.setStartValue(self._effect.opacity())
        self._anim_o.setEndValue(1.0)
        self._anim_o.start()

    def close_fan(self):
        if not self.opened:
            return
        self.opened = False
        self._anim_h.stop()
        self._anim_h.setStartValue(self.maximumHeight())
        self._anim_h.setEndValue(0)
        self._anim_h.start()
        self._anim_o.stop()
        self._anim_o.setStartValue(self._effect.opacity())
        self._anim_o.setEndValue(0.0)
        self._anim_o.start()

    def _after_close(self):
        if not self.opened:
            self.setVisible(False)

    def apply_theme(self, colors, active_key="all"):
        self.colors = colors
        c = colors
        for key, btn in self.buttons.items():
            icon_name = CAT_ICONS.get(key, "fa5s.folder")
            if icon_map.HAS_QTAWESOME:
                if key == active_key:
                    btn.setIcon(icon_map.get_icon(icon_name, c["BG"]))
                else:
                    btn.setIcon(icon_map.get_icon(icon_name, c["TEXT"]))
            if key == active_key:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {c['ACCENT']};
                        color: {c['BG']};
                        border: none;
                        border-radius: 12px;
                        font-size: 20px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {c['CARD']};
                        color: {c['TEXT']};
                        border: 1px solid {c['BORDER']};
                        border-radius: 12px;
                        font-size: 20px;
                    }}
                    QPushButton:hover {{
                        background-color: {c['CARD_HOVER']};
                        border: 1px solid {c['ACCENT']};
                    }}
                """)


class PresetTile(QFrame):
    clicked          = Signal(dict)
    edit_requested   = Signal(dict)
    delete_requested = Signal(dict)
    launch_requested = Signal(dict)

    def __init__(self, preset, colors, menu_style="", parent=None):
        super().__init__(parent)
        self.preset = preset
        self.colors = colors
        self.menu_style = menu_style
        self.setFixedSize(tile_card.TILE_WIDTH, tile_card.TILE_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style(colors["CARD"], colors["BORDER"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        cover = QFrame()
        cover.setFixedHeight(tile_card.COVER_HEIGHT)
        cover.setStyleSheet(f"""
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {colors['ACCENT_SOFT']},
                stop:1 {colors['BG_ALT']}
            );
            border-top-left-radius: 14px;
            border-top-right-radius: 14px;
            border-bottom: 1px solid {colors['BORDER']};
        """)
        cover_layout = QVBoxLayout(cover)
        cover_layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel(preset.get("icon", "🚀"))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"background: transparent; border: none; font-size: 60px;"
        )
        cover_layout.addWidget(icon_label)
        layout.addWidget(cover)

        info = QFrame()
        info.setStyleSheet(f"""
            background-color: {colors['CARD']};
            border-bottom-left-radius: 14px;
            border-bottom-right-radius: 14px;
        """)
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(4)
        name = QLabel(preset.get("name", "Без имени"))
        name.setStyleSheet(
            f"color: {colors['TEXT']}; font-size: 13px; "
            f"font-weight: 700; background: transparent;"
        )
        info_layout.addWidget(name)
        sub = QLabel(f"{len(preset.get('paths', []))} программ")
        sub.setStyleSheet(
            f"color: {colors['SUBTEXT']}; font-size: 11px; background: transparent;"
        )
        info_layout.addWidget(sub)
        layout.addWidget(info)

    def _apply_style(self, bg, border):
        self.setStyleSheet(f"""
            PresetTile {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
        """)

    def enterEvent(self, event):
        self._apply_style(self.colors["CARD_HOVER"], self.colors["ACCENT"])

    def leaveEvent(self, event):
        self._apply_style(self.colors["CARD"], self.colors["BORDER"])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.preset)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_style)
        act_launch = menu.addAction("▶  Запустить пресет")
        menu.addSeparator()
        act_edit   = menu.addAction("✏  Редактировать")
        menu.addSeparator()
        act_delete = menu.addAction("🗑  Удалить")
        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen == act_launch:
            self.launch_requested.emit(self.preset)
        elif chosen == act_edit:
            self.edit_requested.emit(self.preset)
        elif chosen == act_delete:
            self.delete_requested.emit(self.preset)


class Launcher(QMainWindow):
    hotkey_pressed       = Signal()
    quick_hotkey_pressed = Signal()

    def __init__(self):
        super().__init__()

        # Дефолты
        self._first_shown = False
        self.plugin_manager = None
        self.apps = []
        self.presets = []
        self.cards = []
        self.preset_tiles = []
        self.category_buttons = {}
        self.launching_paths = set()
        self._program_hotkeys = {}
        self._last_process_states = None
        self._popular_tiles = []
        self._compact_tiles = []
        self._favorites_only = False
        self._scan_overlay = None
        self._materialize_done = False
        self._shutting_down = False
        self._shutdown_overlay = None
        self._shutdown_dim = None
        self._shutdown_fade = None
        self._games_library_dialog = None
        self._tw_timer = None
        self._tw_full = ""
        self._tw_idx = 0
        self._glow_pulse = None
        self.system_monitor = None
        self.animated_bg = None
        self._title_glow = None
        self._normal_geometry = None
        self._was_always_on_top = True
        self._shortcut_btns = {}
        self.settings = dict(DEFAULT_SETTINGS)
        self.colors = get_theme("dark", "blue")

        # Новые поля для №4
        self._started_by_us = set()
        self._settings_badge = None
        self._updates_task_active = False

        self._resize_state = None
        self._resize_border = RESIZE_BORDER
        self._resize_cursor_widget = None
        self._resize_saved_cursor = None

        try:
            QThreadPool.globalInstance().setMaxThreadCount(4)
        except Exception:
            pass

        try:
            backup_apps()
            raw_settings = load_settings()
            active = raw_settings.get("active_profile", "custom")
            self.settings = apply_profile(active, raw_settings)
        except Exception as e:
            log.error(f"init settings error: {e}\n{traceback.format_exc()}")

        try:
            icon_map.USE_MDI = bool(self.settings.get("use_material_icons", True))
        except Exception:
            pass

        try:
            sounds.init(
                enabled=self.settings.get("sound_enabled", True),
                volume=self.settings.get("sound_volume", 60),
                event_flags=self.settings.get("sound_events") or {},
            )
            sounds.init_voice(
                enabled=self.settings.get("voice_enabled", False),
                volume=self.settings.get("voice_volume", 80),
                event_flags=self.settings.get("voice_events") or {},
            )
        except Exception as e:
            log.error(f"init sounds error: {e}")

        try:
            self.apps = load_apps()
            load_err = get_last_load_error()
            if load_err:
                clear_last_load_error()
                QTimer.singleShot(
                    500, lambda e=load_err: self._show_load_error(e)
                )
        except Exception as e:
            log.error(f"init apps error: {e}")
            self.apps = []

        try:
            self.presets = load_presets()
        except Exception as e:
            log.error(f"init presets error: {e}")
            self.presets = []

        self.theme_name = self.settings.get("theme", "dark")
        self.accent = self.settings.get("accent", "blue")
        self.colors = get_theme(self.theme_name, self.accent)

        self.current_category = self.settings.get("current_category", "all")
        if self.current_category not in CATEGORIES:
            self.current_category = "all"
        self.current_subcategory = self.settings.get("current_subcategory", "all")
        self.always_on_top = bool(self.settings.get("always_on_top", True))
        self.mini_mode = False
        self.compact_mode = bool(self.settings.get("compact_mode", False))

        apply_tile_settings(self.settings)
        set_tile_scale(
            int(self.settings.get("tile_scale", 100)),
            int(self.settings.get("icon_scale", 100)),
        )

        self.setWindowTitle(self._app_name())
        self.setMinimumSize(700, 500)
        self.setAcceptDrops(True)
        self.installEventFilter(self)
        self.setMouseTracking(True)

        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self)

        try:
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        except Exception as e:
            log.error(f"frameless init error: {e}")

        self._apply_window_size()
        self._apply_window_opacity()

        self._build_tray()
        self._setup_hotkey()
        self._register_program_hotkeys()
        self._rebuild_ui()

        self.quick = QuickLauncher(
            get_apps_callable=lambda: self.apps,
            colors=self.colors,
        )

        try:
            self.discord_rpc = discord_rpc.DiscordRPC(self.settings)
            if (self.discord_rpc.is_available()
                    and self.settings.get("discord_enabled")):
                QTimer.singleShot(2500, self.discord_rpc.start)
        except Exception as e:
            log.error(f"discord_rpc init: {e}")
            self.discord_rpc = None

        try:
            self.overlay = LaunchOverlay(self.colors)
        except Exception as e:
            log.error(f"overlay init error: {e}")
            self.overlay = None

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_statuses)
        self._status_timer.start(3000)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        self._stats = load_stats()
        self._stats_tick_seconds = 30
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._tick_stats)
        self._stats_timer.start(self._stats_tick_seconds * 1000)

        self._updates_timer = QTimer(self)
        self._updates_timer.timeout.connect(self._check_updates_for_apps)
        self._updates_timer.start(10 * 60 * 1000)
        QTimer.singleShot(1500, self._check_updates_for_apps)

        self._init_plugins()

        self._autobackup_timer = QTimer(self)
        self._autobackup_timer.timeout.connect(self._do_autobackup)
        if self.settings.get("autobackup_enabled", True):
            try:
                interval_min = int(
                    self.settings.get("autobackup_interval_minutes", 60)
                )
            except Exception:
                interval_min = 60
            interval_min = max(5, interval_min)
            self._autobackup_timer.start(interval_min * 60 * 1000)

        if self.settings.get("silent_start", False):
            QTimer.singleShot(0, self.hide)

    # ================= ИМЯ =================
    def _app_name(self) -> str:
        try:
            name = (self.settings.get("app_name") or "").strip()
        except Exception:
            name = ""
        return name or APP_NAME

    def _apply_app_name(self):
        name = self._app_name()
        try:
            self.setWindowTitle(name)
        except Exception:
            pass
        try:
            if hasattr(self, "title") and self.title:
                self.title.setText(name.upper())
        except Exception:
            pass
        try:
            if (hasattr(self, "custom_titlebar")
                    and self.custom_titlebar
                    and hasattr(self.custom_titlebar, "title_label")):
                self.custom_titlebar.title_label.setText(name)
        except Exception:
            pass
        try:
            if hasattr(self, "tray") and self.tray:
                self._update_tray_tooltip()
                self.set_tray_icon()
        except Exception:
            pass

    def _update_tray_tooltip(self):
        try:
            running = sum(
                1 for c in self.cards if getattr(c, "running", False)
            )
            total = len(self.apps)
            name = self._app_name()
            if running > 0:
                self.tray.setToolTip(
                    f"{name} {APP_VERSION}\n"
                    f"Запущено: {running} из {total}\n"
                    f"Всего программ: {total}"
                )
            else:
                self.tray.setToolTip(
                    f"{name} {APP_VERSION}\n"
                    f"Программ: {total}"
                )
        except Exception:
            pass

    def _update_titlebar_status(self):
        try:
            if not (hasattr(self, "custom_titlebar")
                    and self.custom_titlebar):
                return
            running_count = sum(
                1 for c in self.cards if getattr(c, "running", False)
            )
            total = len(self.apps)
            presets_count = len(self.presets)
            self.custom_titlebar.set_status(
                f"v{APP_VERSION}   ·   {total} программ   ·   "
                f"{running_count} запущено   ·   {presets_count} пресетов"
            )
        except Exception:
            pass

    # ================= РЕСАЙЗ =================
    def _screen_pos_from_event(self, event):
        try:
            if hasattr(event, "globalPosition"):
                return event.globalPosition().toPoint()
        except Exception:
            pass
        try:
            return event.globalPos()
        except Exception:
            return None

    def _qt_resize_edges_at(self, global_pos):
        if (self.isMaximized() or self.isFullScreen()
                or not self.isVisible() or global_pos is None):
            return 0
        tl = self.mapToGlobal(QPoint(0, 0))
        w = self.width()
        h = self.height()
        x = global_pos.x() - tl.x()
        y = global_pos.y() - tl.y()
        if x < 0 or y < 0 or x > w or y > h:
            return 0
        b = self._resize_border
        edges = 0
        if y < b:
            edges |= 0x01
        if y > h - b:
            edges |= 0x02
        if x < b:
            edges |= 0x04
        if x > w - b:
            edges |= 0x08
        return edges

    def _cursor_for_edges(self, edges_bits):
        top    = bool(edges_bits & 0x01)
        bottom = bool(edges_bits & 0x02)
        left   = bool(edges_bits & 0x04)
        right  = bool(edges_bits & 0x08)
        if (top and left) or (bottom and right):
            return Qt.SizeFDiagCursor
        if (top and right) or (bottom and left):
            return Qt.SizeBDiagCursor
        if left or right:
            return Qt.SizeHorCursor
        if top or bottom:
            return Qt.SizeVerCursor
        return None

    def _set_resize_cursor(self, widget, cursor_shape):
        if widget is None:
            return
        if self._resize_cursor_widget is widget:
            return
        self._clear_resize_cursor()
        try:
            self._resize_saved_cursor = widget.cursor()
        except Exception:
            self._resize_saved_cursor = None
        try:
            widget.setCursor(cursor_shape)
            self._resize_cursor_widget = widget
        except Exception:
            self._resize_cursor_widget = None

    def _clear_resize_cursor(self):
        w = self._resize_cursor_widget
        if w is None:
            return
        try:
            saved = self._resize_saved_cursor
            if saved is not None and not saved.shape() == Qt.ArrowCursor:
                w.setCursor(saved)
            else:
                w.unsetCursor()
        except Exception:
            pass
        self._resize_cursor_widget = None
        self._resize_saved_cursor = None

    def _handle_qt_resize_hover(self, obj, event):
        if not isinstance(obj, QWidget):
            return
        try:
            if event.buttons() & (Qt.LeftButton | Qt.RightButton | Qt.MiddleButton):
                self._clear_resize_cursor()
                return
        except Exception:
            pass
        try:
            if obj.window() is not self:
                return
        except Exception:
            return
        if (self.isMaximized() or self.isFullScreen()
                or not self.isVisible()):
            if self._resize_cursor_widget is not None:
                self._clear_resize_cursor()
            return
        gp = self._screen_pos_from_event(event)
        if gp is None:
            return
        edges = self._qt_resize_edges_at(gp)
        cur = self._cursor_for_edges(edges) if edges else None
        if cur is not None:
            self._set_resize_cursor(obj, cur)
        else:
            self._clear_resize_cursor()

    def _handle_qt_resize_press(self, obj, event):
        if event.button() != Qt.LeftButton:
            return False
        if self.isMaximized() or self.isFullScreen():
            return False
        if not isinstance(obj, QWidget):
            return False
        try:
            if obj.window() is not self:
                return False
        except Exception:
            return False
        gp = self._screen_pos_from_event(event)
        edges = self._qt_resize_edges_at(gp)
        if not edges:
            return False
        self._clear_resize_cursor()
        self._resize_state = {
            "edges": edges,
            "start_global": gp,
            "start_geometry": self.geometry(),
        }
        try:
            self.grabMouse()
        except Exception as e:
            log.error(f"grabMouse: {e}")
        return True

    def _do_manual_resize(self, event):
        st = self._resize_state
        if st is None:
            return
        gp = self._screen_pos_from_event(event)
        if gp is None:
            return
        edges = st["edges"]
        sg = st["start_geometry"]
        sp = st["start_global"]
        dx = gp.x() - sp.x()
        dy = gp.y() - sp.y()
        x, y, w, h = sg.x(), sg.y(), sg.width(), sg.height()
        min_w = max(400, self.minimumWidth())
        min_h = max(300, self.minimumHeight())
        if edges & 0x04:
            new_w = w - dx
            if new_w < min_w:
                new_w = min_w
                x = sg.x() + sg.width() - min_w
            else:
                x = sg.x() + dx
            w = new_w
        if edges & 0x08:
            w = max(min_w, w + dx)
        if edges & 0x01:
            new_h = h - dy
            if new_h < min_h:
                new_h = min_h
                y = sg.y() + sg.height() - min_h
            else:
                y = sg.y() + dy
            h = new_h
        if edges & 0x02:
            h = max(min_h, h + dy)
        self.setGeometry(x, y, w, h)

    def _end_manual_resize(self):
        if self._resize_state is None:
            return
        self._resize_state = None
        try:
            self.releaseMouse()
        except Exception:
            pass
        self._clear_resize_cursor()

    def _enable_mouse_tracking_recursive(self, root=None):
        if root is None:
            root = self
        try:
            root.setMouseTracking(True)
        except Exception:
            pass
        try:
            for child in root.findChildren(QWidget):
                try:
                    child.setMouseTracking(True)
                except Exception:
                    continue
        except Exception:
            pass

    # ================= ПЛАГИНЫ =================
    def _init_plugins(self):
        try:
            self.plugin_manager = PluginManager(self, self.settings)
        except Exception as e:
            log.error(f"plugin_manager init: {e}")
            self.plugin_manager = None
            return
        QTimer.singleShot(600, self._plugin_startup)

    def _plugin_startup(self):
        if not self.plugin_manager:
            return
        try:
            self.plugin_manager.call_hook("on_startup")
        except Exception as e:
            log.error(f"_plugin_startup: {e}")
        self._apply_plugin_theme_overrides()

    def _apply_plugin_theme_overrides(self):
        try:
            if not self.plugin_manager:
                return
            base = get_theme(self.theme_name, self.accent)
            ovr = self.plugin_manager.collect_theme_overrides(
                self.theme_name, self.accent
            )
            if not ovr:
                return
            base.update(ovr)
            self.colors = base
            self._apply_theme()
            self._refresh_icons()
            if self.animated_bg:
                try:
                    self.animated_bg.update_colors(self.colors)
                except Exception:
                    pass
            if self.system_monitor:
                try:
                    self.system_monitor.apply_theme(self.colors)
                except Exception:
                    pass
        except Exception as e:
            log.error(f"_apply_plugin_theme_overrides: {e}")

    def _reload_plugins_from_tray(self):
        if not self.plugin_manager:
            self._show_toast(
                "Плагины", "Менеджер плагинов недоступен", "warning"
            )
            return
        try:
            self.plugin_manager.reload()
            self._apply_plugin_theme_overrides()
            self.render_cards()
            count = self.plugin_manager.count_active()
            self._show_toast(
                "Плагины перезагружены",
                f"Активных плагинов: {count}",
                "success",
            )
        except Exception as e:
            log.error(f"_reload_plugins_from_tray: {e}")
            self._show_toast("Ошибка", str(e), "error")

    def _inject_plugin_context_menu(self, app, menu):
        if not self.plugin_manager:
            return
        try:
            self.plugin_manager.call_hook("on_context_menu", app, menu)
        except Exception as e:
            log.error(f"_inject_plugin_context_menu: {e}")

    def _show_load_error(self, err_text):
        if not self.settings.get("show_load_errors", True):
            return
        try:
            show_error(self, self.colors, "Ошибка загрузки данных", err_text)
        except Exception as e:
            log.error(f"_show_load_error: {e}")

    def _do_autobackup(self):
        try:
            backup_all()
        except Exception as e:
            log.error(f"_do_autobackup: {e}")

    # ================= ТРЕЙ-МИГАНИЕ =================
    def _flash_tray_icon(self, count=3):
        try:
            if not hasattr(self, "tray") or self.tray is None:
                return
            original = self.tray.icon()
            empty_pix = QPixmap(64, 64)
            empty_pix.fill(Qt.transparent)
            empty_icon = QIcon(empty_pix)

            def _blink(step=0):
                try:
                    if step >= count * 2:
                        self.tray.setIcon(original)
                        return
                    if step % 2 == 0:
                        self.tray.setIcon(empty_icon)
                    else:
                        self.tray.setIcon(original)
                    QTimer.singleShot(140, lambda s=step + 1: _blink(s))
                except Exception:
                    try:
                        self.tray.setIcon(original)
                    except Exception:
                        pass

            _blink(0)
        except Exception as e:
            log.error(f"_flash_tray_icon: {e}")

    # ================= ИКОНКА ТРЕЯ =================
    def set_tray_icon(self):
        try:
            icon = make_tray_icon(
                self.colors,
                self.settings.get("tray_icon", ""),
                self._app_name(),
            )
            self.tray.setIcon(icon)
            if hasattr(self, "custom_titlebar") and self.custom_titlebar:
                self.custom_titlebar._refresh_icons()
        except Exception as e:
            log.error(f"set_tray_icon error: {e}")

    # ================= ИКОНКИ =================
    def _get_fa_icon(self, name, color=None):
        if color is None:
            color = self.colors["TEXT"]
        return icon_map.get_icon(name, color)

    def _refresh_icons(self):
        if not icon_map.HAS_QTAWESOME:
            return
        c = self.colors

        if hasattr(self, "main_category_btn"):
            icon_name = CAT_ICONS.get(self.current_category, "fa5s.folder")
            self.main_category_btn.setIcon(self._get_fa_icon(icon_name, c["BG"]))
            self.main_category_btn.setIconSize(QSize(22, 22))

        if hasattr(self, "fav_btn"):
            color = c["BG"] if self._favorites_only else c["TEXT"]
            self.fav_btn.setIcon(self._get_fa_icon("fa5s.star", color))
            self.fav_btn.setIconSize(QSize(20, 20))

        if hasattr(self, "presets_btn"):
            self.presets_btn.setIcon(self._get_fa_icon("fa5s.rocket", c["ACCENT"]))
            self.presets_btn.setIconSize(QSize(22, 22))
        if hasattr(self, "library_btn"):
            self.library_btn.setIcon(self._get_fa_icon("fa5s.gamepad", c["TEXT"]))
            self.library_btn.setIconSize(QSize(20, 20))
        if hasattr(self, "import_btn"):
            self.import_btn.setIcon(self._get_fa_icon("fa5s.download", c["TEXT"]))
            self.import_btn.setIconSize(QSize(20, 20))
        if hasattr(self, "add_btn"):
            self.add_btn.setIcon(self._get_fa_icon("fa5s.plus", c["BG"]))
            self.add_btn.setIconSize(QSize(24, 24))

        if hasattr(self, "ontop_btn"):
            color = c["BG"] if self.always_on_top else c["TEXT"]
            self.ontop_btn.setIcon(self._get_fa_icon("fa5s.thumbtack", color))
            self.ontop_btn.setIconSize(QSize(20, 20))
        if hasattr(self, "theme_btn"):
            icon_name = "fa5s.sun" if self.theme_name == "dark" else "fa5s.moon"
            self.theme_btn.setIcon(self._get_fa_icon(icon_name, c["TEXT"]))
            self.theme_btn.setIconSize(QSize(20, 20))
        if hasattr(self, "mini_btn"):
            icon_name = "fa5s.expand" if self.mini_mode else "fa5s.compress"
            self.mini_btn.setIcon(self._get_fa_icon(icon_name, c["TEXT"]))
            self.mini_btn.setIconSize(QSize(20, 20))
        if hasattr(self, "compact_btn"):
            color = c["BG"] if self.compact_mode else c["TEXT"]
            self.compact_btn.setIcon(self._get_fa_icon("fa5s.th-large", color))
            self.compact_btn.setIconSize(QSize(20, 20))
        if hasattr(self, "settings_btn"):
            self.settings_btn.setIcon(self._get_fa_icon("fa5s.cog", c["TEXT"]))
            self.settings_btn.setIconSize(QSize(20, 20))
        if hasattr(self, "shutdown_btn"):
            self.shutdown_btn.setIcon(
                self._get_fa_icon("fa5s.power-off", c["DANGER"])
            )
            self.shutdown_btn.setIconSize(QSize(20, 20))

        if hasattr(self, "custom_titlebar") and self.custom_titlebar:
            self.custom_titlebar._refresh_icons()

    # ================= TOASTS =================
    def _play_click_voice(self):
        try:
            if not self.settings.get("voice_enabled", False):
                return
            flags = self.settings.get("voice_events") or {}
            if not flags.get("click_every", False):
                return
            sounds.play_voice("click_every")
        except Exception:
            pass

    def _show_toast(self, title, message, preset="success"):
        if preset == "error":
            sounds.play("error")
            sounds.play_voice("error")
        elif preset == "info":
            sounds.play_voice("info")

        if self.settings.get("native_notifications", False):
            if preset in ("error", "warning", "info"):
                try:
                    notifications.notify(title, message, timeout=4)
                except Exception:
                    pass

        if not HAS_TOAST:
            try:
                icon = (QSystemTrayIcon.Warning if preset == "error"
                        else QSystemTrayIcon.Information)
                if hasattr(self, "tray") and self.tray is not None:
                    self.tray.showMessage(title, message, icon, 3500)
                    return
            except Exception:
                pass
            if preset == "error":
                show_error(self, self.colors, title, message)
            return
        try:
            toast = Toast(self)
            toast.setDuration(3000)
            toast.setTitle(title)
            toast.setText(message)
            bg = QColor(self.colors["CARD"])
            fg = QColor(self.colors["TEXT"])
            accent = QColor(self.colors["ACCENT"])
            err = QColor(self.colors["DANGER"])
            try:
                toast.setBackgroundColor(bg)
                toast.setTitleColor(fg)
                toast.setTextColor(fg)
                toast.setCloseButtonIconColor(fg)
                if preset == "error":
                    toast.setIconColor(err)
                else:
                    toast.setIconColor(accent)
            except Exception:
                pass

            if preset == "error" and ToastPreset is not None:
                try: toast.applyPreset(ToastPreset.ERROR)
                except Exception: pass
            elif preset == "warning" and ToastPreset is not None:
                try: toast.applyPreset(ToastPreset.WARNING)
                except Exception: pass
            elif preset == "info" and ToastPreset is not None:
                try: toast.applyPreset(ToastPreset.INFORMATION)
                except Exception: pass
            elif ToastPreset is not None:
                try: toast.applyPreset(ToastPreset.SUCCESS)
                except Exception: pass

            toast.show()
        except Exception as e:
            log.error(f"toast error: {e}")
            try:
                icon = (QSystemTrayIcon.Warning if preset == "error"
                        else QSystemTrayIcon.Information)
                if hasattr(self, "tray") and self.tray is not None:
                    self.tray.showMessage(title, message, icon, 3500)
            except Exception:
                pass

    # ================= МИНИ-РЕЖИМ =================
    def toggle_mini_mode(self):
        self._play_click_voice()
        if self.mini_mode:
            self.exit_mini_mode()
        else:
            self.enter_mini_mode()

    def enter_mini_mode(self):
        if self.mini_mode:
            return
        self._normal_geometry = self.geometry()
        self._was_always_on_top = self.always_on_top
        self.mini_mode = True
        self.setMinimumSize(200, 300)
        self.resize(
            self.settings.get("mini_width", 240),
            self.settings.get("mini_height", 600),
        )
        screen = get_active_monitor_geometry()
        self.move(screen.right() - self.width() - 10, screen.top() + 50)
        if self.custom_titlebar:
            self.custom_titlebar.hide()
        if self.content_widget:
            self.content_widget.hide()
        if self.mini_panel:
            self.mini_panel.show()
            self._rebuild_mini_panel()
        self.always_on_top = True
        set_always_on_top_native(self, True)
        self._refresh_icons()

    def exit_mini_mode(self):
        if not self.mini_mode:
            return
        self.mini_mode = False
        if self.mini_panel:
            self.mini_panel.hide()
        if self.content_widget:
            self.content_widget.show()
        if self.custom_titlebar:
            self.custom_titlebar.show()
        self.setMinimumSize(700, 500)
        if self._normal_geometry:
            self.setGeometry(self._normal_geometry)
        else:
            self.resize(1180, 740)
        self.always_on_top = self._was_always_on_top
        set_always_on_top_native(self, self.always_on_top)
        self._refresh_icons()
        self._relayout_grid()

    # ================= КОМПАКТНЫЙ =================
    def toggle_compact_mode(self):
        self._play_click_voice()
        self.compact_mode = not self.compact_mode
        self.settings["compact_mode"] = self.compact_mode
        save_settings(self.settings)
        try:
            if self.compact_mode:
                self.popular_header.setVisible(False)
                self.popular_widget.setVisible(False)
                self.running_header.setVisible(False)
                self.running_grid_widget.setVisible(False)
                self.section_label.setVisible(False)
                self.grid_widget.setVisible(False)
                self.compact_widget.setVisible(True)
            else:
                self.compact_widget.setVisible(False)
                self.section_label.setVisible(
                    self.settings.get("show_section_headers", True)
                )
                self.grid_widget.setVisible(True)
        except Exception:
            pass
        self._rebuild_compact_row()
        self._refresh_icons()
        self._apply_theme()
        self._show_toast(
            "Компактный режим",
            "Включён" if self.compact_mode else "Выключен",
            "info",
        )

    def _build_compact_row(self):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(8)
        self.compact_flow = QWidget()
        self.compact_flow.setStyleSheet("background: transparent;")
        self.compact_flow_layout = QGridLayout(self.compact_flow)
        self.compact_flow_layout.setContentsMargins(0, 0, 0, 0)
        self.compact_flow_layout.setSpacing(8)
        self.compact_flow_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        outer.addWidget(self.compact_flow)
        self.compact_empty = QLabel("В этой категории пока нет программ.")
        self.compact_empty.setAlignment(Qt.AlignCenter)
        self.compact_empty.setVisible(False)
        outer.addWidget(self.compact_empty)
        wrap.setVisible(self.compact_mode)
        return wrap

    def _rebuild_compact_row(self):
        if not hasattr(self, "compact_flow_layout"):
            return
        while self.compact_flow_layout.count():
            it = self.compact_flow_layout.takeAt(0)
            w = it.widget() if it else None
            if w:
                try:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                except RuntimeError:
                    pass
        self._compact_tiles = []
        if not self.compact_mode:
            return
        viewport_w = self.scroll.viewport().width()
        if viewport_w < 100:
            viewport_w = 1180
        icon_size = 44
        spacing = 8
        cols = max(1, (viewport_w + spacing) // (icon_size + spacing))
        text = self.search.text().lower().strip()
        sub = self.current_subcategory
        visible = []
        for card in self.cards:
            app = card.app
            name = (app.get("name") or "").lower()
            if text and text not in name:
                continue
            cat = app.get("category") or "other"
            running = getattr(card, "running", False)
            if not running:
                if (self.current_category not in ("all", "recent")
                        and cat != self.current_category):
                    continue
                if (sub and sub != "all"
                        and self.current_category not in ("all", "recent")
                        and (app.get("subcategory") or "") != sub):
                    continue
            if self._favorites_only and not app.get("favorite"):
                continue
            visible.append(app)
        for i, app in enumerate(visible):
            ico = QuickAppIcon(app, self.colors, size=icon_size)
            ico.clicked.connect(self.launch_app)
            ico.right_click.connect(self._show_quick_icon_menu)
            self.compact_flow_layout.addWidget(
                ico, i // cols, i % cols, Qt.AlignTop | Qt.AlignLeft
            )
            self._compact_tiles.append(ico)
        for i in range(self.compact_flow_layout.columnCount()):
            self.compact_flow_layout.setColumnStretch(i, 0)
        self.compact_flow_layout.setColumnStretch(cols, 1)
        self.compact_empty.setVisible(not visible)
        self.compact_empty.setStyleSheet(
            f"color: {self.colors['SUBTEXT']}; font-size: 13px; "
            f"padding: 24px; background: transparent;"
        )

    def _show_quick_icon_menu(self, app, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_style())

        def add(icon_name, text, color=None):
            if color is None:
                color = self.colors["TEXT"]
            ic = self._get_fa_icon(icon_name, color)
            if icon_map.HAS_QTAWESOME:
                return menu.addAction(ic, text)
            return menu.addAction(text)

        act_launch = add("fa5s.play", "Запустить", self.colors["ACCENT"])
        act_admin  = add("fa5s.user-shield", "Запустить от админа")
        menu.addSeparator()
        act_fav = add("fa5s.star",
                      "Убрать из избранного" if app.get("favorite")
                      else "В избранное", "#F9E2AF")
        act_folder = add("fa5s.folder", "Открыть папку")
        menu.addSeparator()
        act_kill = add("fa5s.stop-circle", "Завершить процесс",
                       self.colors["DANGER"])

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen == act_launch:
            self.launch_app(app)
        elif chosen == act_admin:
            self.launch_app_admin(app)
        elif chosen == act_fav:
            self.toggle_favorite(app)
        elif chosen == act_folder:
            self.open_folder(app)
        elif chosen == act_kill:
            self.kill_running_process(app)

    # ================= АДМИН / FULLSCREEN =================
    def launch_app_admin(self, app):
        self._play_click_voice()
        name = app.get("name", "")
        result = launch_as_admin(app)
        if not result.ok:
            self._show_toast(
                "Не удалось запустить от администратора",
                result.error, "error",
            )
            return
        sounds.play("launch")
        sounds.play_voice("launch")
        try:
            for a in self.apps:
                if a == app:
                    a["launch_count"] = a.get("launch_count", 0) + 1
                    break
            save_apps(self.apps)
        except Exception:
            pass
        self._show_toast("Запущено от администратора", name, "success")

    def toggle_fullscreen(self):
        try:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            if self.custom_titlebar:
                QTimer.singleShot(50, self.custom_titlebar._refresh_icons)
        except Exception as e:
            log.error(f"toggle_fullscreen error: {e}")

    def toggle_always_on_top(self):
        self._play_click_voice()
        self.always_on_top = not self.always_on_top
        self.settings["always_on_top"] = self.always_on_top
        save_settings(self.settings)
        set_always_on_top_native(self, self.always_on_top)
        self._apply_theme()

    def _apply_window_size(self):
        self.setMinimumWidth(700)
        self.setMaximumWidth(16777215)
        w = max(700, int(self.settings.get("window_width", 1180)))
        h = max(500, int(self.settings.get("window_height", 740)))
        x = int(self.settings.get("window_x", -1))
        y = int(self.settings.get("window_y", -1))
        self.resize(w, h)
        if x >= 0 and y >= 0:
            try:
                screen = QApplication.primaryScreen().availableGeometry()
                if (x < screen.right() - 100
                        and x + w > screen.left() + 100
                        and y < screen.bottom() - 50
                        and y + h > screen.top() + 50):
                    self.move(x, y)
                    return
            except Exception:
                pass
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            cx = screen.x() + (screen.width() - w) // 2
            cy = screen.y() + (screen.height() - h) // 2
            self.move(cx, cy)
        except Exception:
            pass

    def _apply_window_opacity(self):
        """Применяет window_opacity из настроек."""
        try:
            v = int(self.settings.get("window_opacity", 100))
            v = max(60, min(100, v))
            self.setWindowOpacity(v / 100.0)
        except Exception as e:
            log.error(f"_apply_window_opacity: {e}")

    # ================= UI =================
    def _rebuild_ui(self):
        try:
            old = self.takeCentralWidget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        except Exception as e:
            log.error(f"takeCentralWidget error: {e}")
        self.cards = []
        self.preset_tiles = []
        self.category_buttons = {}
        self._title_glow = None
        self._popular_tiles = []
        self._compact_tiles = []
        apply_tile_settings(self.settings)
        set_tile_scale(
            int(self.settings.get("tile_scale", 100)),
            int(self.settings.get("icon_scale", 100)),
        )
        self._build_full_ui()
        self._apply_theme()
        self._refresh_icons()
        self.render_cards()
        self._apply_monitor_visibility()
        self._apply_bg_animation_visibility()
        QTimer.singleShot(0, self._enable_mouse_tracking_recursive)

    def _build_full_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_vbox = QVBoxLayout(central)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        self.custom_titlebar = CustomTitleBar(self, self.colors)
        main_vbox.addWidget(self.custom_titlebar)

        content = QWidget()
        self.content_widget = content
        root = QHBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # === ЛЕВЫЙ САЙДБАР ===
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(76)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 22, 14, 22)
        side.setSpacing(10)

        cur_name, _ = CATEGORIES.get(self.current_category, ("Все", "🗂"))
        self.main_category_btn = QPushButton()
        icon_name = CAT_ICONS.get(self.current_category, "fa5s.folder")
        if icon_map.HAS_QTAWESOME:
            self.main_category_btn.setIcon(
                self._get_fa_icon(icon_name, self.colors["BG"])
            )
        else:
            self.main_category_btn.setText("🗂")
        self.main_category_btn.setIconSize(QSize(22, 22))
        self.main_category_btn.setFixedSize(48, 48)
        self.main_category_btn.setCursor(Qt.PointingHandCursor)
        self.main_category_btn.setToolTip(f"Категории  ·  сейчас: {cur_name}")
        self.main_category_btn.clicked.connect(self._toggle_fan)
        side.addWidget(self.main_category_btn)

        self.fav_btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            self.fav_btn.setIcon(self._get_fa_icon("fa5s.star", self.colors["TEXT"]))
        else:
            self.fav_btn.setText("⭐")
        self.fav_btn.setIconSize(QSize(20, 20))
        self.fav_btn.setFixedSize(48, 48)
        self.fav_btn.setCursor(Qt.PointingHandCursor)
        self.fav_btn.setToolTip("Только избранные")
        self.fav_btn.clicked.connect(self.toggle_favorites_only)
        side.addWidget(self.fav_btn)

        self.category_fan = CategoryFan(self, self.colors, self._on_fan_select)
        self.category_fan.update_speed(
            self.settings.get("animation_speed", 100)
        )
        side.addWidget(self.category_fan)
        side.addStretch()

        self.presets_btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            self.presets_btn.setIcon(
                self._get_fa_icon("fa5s.rocket", self.colors["ACCENT"])
            )
        else:
            self.presets_btn.setText("🚀")
        self.presets_btn.setIconSize(QSize(22, 22))
        self.presets_btn.setFixedSize(48, 48)
        self.presets_btn.setCursor(Qt.PointingHandCursor)
        self.presets_btn.setToolTip("Пресеты запуска")
        self.presets_btn.clicked.connect(self.open_presets_manager)
        side.addWidget(self.presets_btn)

        self.library_btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            self.library_btn.setIcon(self._get_fa_icon("fa5s.gamepad", self.colors["TEXT"]))
        else:
            self.library_btn.setText("🎮")
        self.library_btn.setIconSize(QSize(20, 20))
        self.library_btn.setFixedSize(48, 48)
        self.library_btn.setCursor(Qt.PointingHandCursor)
        self.library_btn.setToolTip("Библиотека игр")
        self.library_btn.clicked.connect(self.open_games_library)
        side.addWidget(self.library_btn)

        self.import_btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            self.import_btn.setIcon(self._get_fa_icon("fa5s.download", self.colors["TEXT"]))
        else:
            self.import_btn.setText("⬇")
        self.import_btn.setIconSize(QSize(20, 20))
        self.import_btn.setFixedSize(48, 48)
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.setToolTip("Импорт программ")
        self.import_btn.clicked.connect(self.open_import)
        side.addWidget(self.import_btn)

        self.add_btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            self.add_btn.setIcon(self._get_fa_icon("fa5s.plus", self.colors["BG"]))
        else:
            self.add_btn.setText("＋")
        self.add_btn.setIconSize(QSize(24, 24))
        self.add_btn.setFixedSize(48, 48)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setToolTip("Добавить программу")
        self.add_btn.clicked.connect(self.add_app)
        side.addWidget(self.add_btn)

        root.addWidget(self.sidebar)

        # === ЦЕНТР ===
        center = AnimatedBackground(
            self.colors,
            particle_count=int(self.settings.get("bg_animation_particles", 28)),
        )
        self.animated_bg = center
        self.center_widget = center
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(28, 20, 28, 22)
        center_layout.setSpacing(12)

        self.title = QLabel(self._app_name().upper())
        self.title.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.title)

        self._title_glow = QGraphicsDropShadowEffect(self.title)
        self._title_glow.setBlurRadius(24)
        self._title_glow.setOffset(0, 0)
        self._title_glow.setColor(QColor(self.colors["ACCENT"]))
        self.title.setGraphicsEffect(self._title_glow)

        self.clock_label = QLabel()
        self.clock_label.setAlignment(Qt.AlignCenter)
        self.clock_label.setVisible(self.settings.get("show_clock", True))
        center_layout.addWidget(self.clock_label)
        center_layout.addSpacing(4)

        self.search_row_widget = QWidget()
        search_row = QHBoxLayout(self.search_row_widget)
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(10)
        search_row.addStretch()

        self.search_frame = QFrame()
        self.search_frame.setObjectName("SearchFrame")
        self.search_frame.setFixedSize(400, 44)

        search_layout = QHBoxLayout(self.search_frame)
        search_layout.setContentsMargins(16, 0, 16, 0)
        search_layout.setSpacing(10)

        search_icon = QLabel()
        if icon_map.HAS_QTAWESOME:
            search_icon.setPixmap(
                self._get_fa_icon("fa5s.search", self.colors["SUBTEXT"]).pixmap(16, 16)
            )
        else:
            search_icon.setText("🔍")
        search_icon.setObjectName("SearchIcon")
        search_layout.addWidget(search_icon)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск игр и программ...  (Ctrl+F)")
        self.search.setFrame(False)
        self.search.textChanged.connect(self.filter_cards)
        search_layout.addWidget(self.search, 1)
        search_row.addWidget(self.search_frame)

        self.subcat_combo = QComboBox()
        self.subcat_combo.setFixedHeight(44)
        self.subcat_combo.setMinimumWidth(160)
        self.subcat_combo.setVisible(False)
        self.subcat_combo.currentIndexChanged.connect(self._on_subcat_combo)
        search_row.addWidget(self.subcat_combo)
        search_row.addStretch()

        self.search_row_widget.setVisible(self.settings.get("show_search", True))
        center_layout.addWidget(self.search_row_widget)

        # ---- Панель категорий под поиском (текстовое меню) ----
        self.cats_row_widget = QWidget()
        self.cats_row_widget.setStyleSheet("background: transparent;")
        cats_row = QHBoxLayout(self.cats_row_widget)
        cats_row.setContentsMargins(0, 2, 0, 2)
        cats_row.setSpacing(2)
        cats_row.addStretch()

        self.category_buttons = {}
        for key, (name, emoji) in CATEGORIES.items():
            btn = QPushButton(name.upper())
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            btn.setFixedHeight(26)
            btn.clicked.connect(
                lambda _=False, k=key: self._on_category_chip(k)
            )
            cats_row.addWidget(btn)
            self.category_buttons[key] = btn

        cats_row.addStretch()
        center_layout.addWidget(self.cats_row_widget)
        self._refresh_category_chips()

        self._update_clock()
        center_layout.addSpacing(6)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent;")
        self.scroll.viewport().setStyleSheet("background: transparent;")

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_content.setContextMenuPolicy(Qt.CustomContextMenu)
        self.scroll_content.customContextMenuRequested.connect(
            self._on_grid_context_menu
        )
        scroll_vbox = QVBoxLayout(self.scroll_content)
        scroll_vbox.setContentsMargins(0, 4, 0, 4)
        scroll_vbox.setSpacing(14)

        self.popular_header = QLabel("🔥 ПОПУЛЯРНОЕ")
        self.popular_header.setVisible(False)
        scroll_vbox.addWidget(self.popular_header)

        self.popular_widget = QWidget()
        self.popular_widget.setVisible(False)
        self.popular_widget.setStyleSheet("background: transparent;")
        self.popular_layout = QHBoxLayout(self.popular_widget)
        self.popular_layout.setContentsMargins(0, 4, 0, 4)
        self.popular_layout.setSpacing(8)
        self.popular_layout.setAlignment(Qt.AlignLeft)
        scroll_vbox.addWidget(self.popular_widget)

        self.running_header = QLabel("🟢 ЗАПУЩЕНО")
        self.running_header.setVisible(False)
        scroll_vbox.addWidget(self.running_header)

        self.running_grid_widget = QWidget()
        self.running_grid_widget.setVisible(False)
        self.running_grid_widget.setStyleSheet("background: transparent;")
        self.running_grid = QGridLayout(self.running_grid_widget)
        self.running_grid.setContentsMargins(0, 0, 0, 0)
        self.running_grid.setSpacing(tile_card.TILE_SPACING)
        self.running_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll_vbox.addWidget(self.running_grid_widget)

        self.section_label = QLabel("")
        self.section_label.setVisible(False)
        scroll_vbox.addWidget(self.section_label)

        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(tile_card.TILE_SPACING)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll_vbox.addWidget(self.grid_widget)

        self.compact_widget = self._build_compact_row()
        scroll_vbox.addWidget(self.compact_widget)
        scroll_vbox.addStretch()

        self.scroll.setWidget(self.scroll_content)
        center_layout.addWidget(self.scroll, 1)

        # === EMPTY ===
        self.empty_widget = QWidget()
        self.empty_widget.setStyleSheet("background: transparent;")
        empty_outer = QVBoxLayout(self.empty_widget)
        empty_outer.setContentsMargins(0, 20, 0, 20)
        empty_outer.setSpacing(16)
        empty_outer.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignCenter)
        self.empty_icon.setFixedHeight(72)
        if icon_map.HAS_QTAWESOME:
            try:
                pix = self._get_fa_icon("fa5s.box", self.colors["SUBTEXT"]).pixmap(56, 56)
                if not pix.isNull():
                    self.empty_icon.setPixmap(pix)
            except Exception:
                pass
        empty_outer.addWidget(self.empty_icon)

        self.empty_label = QLabel("")
        self.empty_label.setAlignment(Qt.AlignCenter)
        empty_outer.addWidget(self.empty_label)

        self.empty_hint = QLabel("")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setVisible(False)
        empty_outer.addWidget(self.empty_hint)

        self.empty_buttons_widget = QWidget()
        eb_lay = QHBoxLayout(self.empty_buttons_widget)
        eb_lay.setContentsMargins(0, 0, 0, 0)
        eb_lay.setSpacing(10)
        eb_lay.addStretch()

        self.empty_btn_add = QPushButton("  Добавить программу")
        if icon_map.HAS_QTAWESOME:
            self.empty_btn_add.setIcon(self._get_fa_icon("fa5s.plus", self.colors["BG"]))
            self.empty_btn_add.setIconSize(QSize(16, 16))
        self.empty_btn_add.setProperty("accent", True)
        self.empty_btn_add.setCursor(Qt.PointingHandCursor)
        self.empty_btn_add.clicked.connect(self.add_app)
        eb_lay.addWidget(self.empty_btn_add)

        self.empty_btn_import = QPushButton("  Импортировать")
        if icon_map.HAS_QTAWESOME:
            self.empty_btn_import.setIcon(self._get_fa_icon("fa5s.download", self.colors["TEXT"]))
            self.empty_btn_import.setIconSize(QSize(16, 16))
        self.empty_btn_import.setCursor(Qt.PointingHandCursor)
        self.empty_btn_import.clicked.connect(self.open_import)
        eb_lay.addWidget(self.empty_btn_import)

        self.empty_btn_preset = QPushButton("  Создать пресет")
        if icon_map.HAS_QTAWESOME:
            self.empty_btn_preset.setIcon(self._get_fa_icon("fa5s.rocket", self.colors["ACCENT"]))
            self.empty_btn_preset.setIconSize(QSize(16, 16))
        self.empty_btn_preset.setCursor(Qt.PointingHandCursor)
        self.empty_btn_preset.clicked.connect(self.open_presets_manager)
        eb_lay.addWidget(self.empty_btn_preset)
        eb_lay.addStretch()
        empty_outer.addWidget(self.empty_buttons_widget)

        self.search_shortcuts = QWidget()
        shortcut_layout = QHBoxLayout(self.search_shortcuts)
        shortcut_layout.setContentsMargins(0, 0, 0, 0)
        shortcut_layout.setSpacing(10)
        shortcut_layout.addStretch()
        self._make_shortcut_btn(shortcut_layout, "fa5b.google", "Google", "google")
        self._make_shortcut_btn(shortcut_layout, "fa5b.youtube", "YouTube", "youtube")
        self._make_shortcut_btn(shortcut_layout, "fa5b.steam", "Steam", "steam")
        self._make_shortcut_btn(shortcut_layout, "fa5b.twitch", "Twitch", "twitch")
        shortcut_layout.addStretch()
        self.search_shortcuts.setVisible(False)
        empty_outer.addWidget(self.search_shortcuts)

        self.empty_widget.setVisible(False)
        center_layout.addWidget(self.empty_widget)
        root.addWidget(center, 1)

        # === ПРАВЫЙ САЙДБАР ===
        self.right_sidebar = QFrame()
        self.right_sidebar.setObjectName("RightSidebar")
        self.right_sidebar.setFixedWidth(64)
        rside = QVBoxLayout(self.right_sidebar)
        rside.setContentsMargins(8, 22, 8, 22)
        rside.setSpacing(10)

        self.ontop_btn = self._make_icon_btn(
            rside, "fa5s.thumbtack", "Поверх всех окон",
            self.toggle_always_on_top, active_color=True,
        )
        self.theme_btn = self._make_icon_btn(
            rside, "fa5s.sun", "Переключить тему (Ctrl+T)",
            self.toggle_theme
        )
        self.compact_btn = self._make_icon_btn(
            rside, "fa5s.th-large", "Компактный режим (Ctrl+Shift+C)",
            self.toggle_compact_mode
        )
        self.mini_btn = self._make_icon_btn(
            rside, "fa5s.compress", "Мини-режим (Ctrl+M)", self.toggle_mini_mode
        )
        rside.addStretch()

        try:
            self.system_monitor = SystemMonitorWidget(self.colors)
        except Exception as e:
            log.error(f"system_monitor init: {e}")
            self.system_monitor = None
        if self.system_monitor is not None:
            rside.addWidget(self.system_monitor, 0, Qt.AlignHCenter)

        self.settings_btn = self._make_icon_btn(
            rside, "fa5s.cog", "Настройки", self.open_settings
        )

        try:
            badge = QLabel(self.settings_btn)
            badge.setFixedSize(10, 10)
            badge.setStyleSheet(
                f"background-color: {self.colors['DANGER']}; "
                f"border-radius: 5px;"
            )
            badge.setAttribute(Qt.WA_TransparentForMouseEvents)
            badge.move(self.settings_btn.width() - 14, 6)
            badge.setVisible(False)
            self._settings_badge = badge
        except Exception as e:
            log.error(f"settings badge: {e}")
            self._settings_badge = None

        self.shutdown_btn = self._make_icon_btn(
            rside, "fa5s.power-off", "Выключить лаунчер",
            self.confirm_shutdown_launcher
        )

        root.addWidget(self.right_sidebar)
        main_vbox.addWidget(content, 1)

        self.mini_panel = self._build_mini_panel()
        self.mini_panel.setVisible(False)
        main_vbox.addWidget(self.mini_panel, 1)

        try:
            if self.compact_mode:
                self.popular_widget.setVisible(False)
                self.section_label.setVisible(False)
                self.grid_widget.setVisible(False)
                self.compact_widget.setVisible(True)
        except Exception:
            pass

    def _build_mini_panel(self):
        c = self.colors
        panel = QFrame()
        panel.setObjectName("MiniPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("Мини-режим")
        title.setStyleSheet(
            f"color: {c['ACCENT']}; font-size: 14px; font-weight: bold;"
        )
        header.addWidget(title)
        header.addStretch()
        exit_btn = QPushButton()
        exit_btn.setFixedSize(32, 32)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setToolTip("Выйти из мини-режима (Ctrl+M)")
        if icon_map.HAS_QTAWESOME:
            exit_btn.setIcon(self._get_fa_icon("fa5s.compress", c["TEXT"]))
            exit_btn.setIconSize(QSize(16, 16))
        else:
            exit_btn.setText("✕")
        exit_btn.clicked.connect(self.toggle_mini_mode)
        header.addWidget(exit_btn)
        layout.addLayout(header)
        self.mini_scroll = QScrollArea()
        self.mini_scroll.setWidgetResizable(True)
        self.mini_scroll.setFrameShape(QFrame.NoFrame)
        self.mini_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.mini_scroll.setStyleSheet("background: transparent;")
        self.mini_content = QWidget()
        self.mini_grid = QVBoxLayout(self.mini_content)
        self.mini_grid.setContentsMargins(0, 0, 0, 0)
        self.mini_grid.setSpacing(8)
        self.mini_grid.setAlignment(Qt.AlignTop)
        self.mini_scroll.setWidget(self.mini_content)
        layout.addWidget(self.mini_scroll, 1)
        panel.setStyleSheet(f"""
            QFrame#MiniPanel {{
                background-color: {c['BG_ALT']};
                border-left: 1px solid {c['BORDER']};
            }}
        """)
        return panel

    def _rebuild_mini_panel(self):
        if not hasattr(self, "mini_grid"):
            return
        while self.mini_grid.count():
            item = self.mini_grid.takeAt(0)
            w = item.widget() if item else None
            if w:
                w.deleteLater()
        shown = set()
        for app in self.apps:
            path = app.get("path", "")
            if not path or path in shown:
                continue
            if app.get("favorite") or is_process_running(path):
                shown.add(path)
                btn = QPushButton()
                btn.setFixedSize(56, 56)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setToolTip(app.get("name", ""))
                try:
                    pix = get_icon(app, 32)
                    if pix and not pix.isNull():
                        btn.setIcon(QIcon(pix))
                        btn.setIconSize(QSize(32, 32))
                    else:
                        btn.setText(app.get("name", "")[:2])
                except Exception:
                    btn.setText(app.get("name", "")[:2])
                btn.clicked.connect(lambda _=False, a=app: self.launch_app(a))
                self.mini_grid.addWidget(btn, 0, Qt.AlignHCenter)
        if not shown:
            lbl = QLabel("Нет избранных\nи запущенных")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {self.colors['SUBTEXT']}; font-size: 11px;"
            )
            self.mini_grid.addWidget(lbl)
        self.mini_grid.addStretch()

    def _make_shortcut_btn(self, parent_layout, icon_name, label, service):
        btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            btn.setIcon(self._get_fa_icon(icon_name, self.colors["TEXT"]))
            btn.setIconSize(QSize(18, 18))
        btn.setText(f"  {label}")
        btn.setFixedHeight(44)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumWidth(140)
        btn.clicked.connect(lambda _=False, s=service: self._open_web_search(s))
        parent_layout.addWidget(btn)
        self._shortcut_btns[service] = btn

    def _make_icon_btn(self, parent_layout, icon_name, tooltip, callback,
                       active_color=False):
        btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            if active_color and getattr(self, "always_on_top", False):
                btn.setIcon(self._get_fa_icon(icon_name, self.colors["BG"]))
            else:
                btn.setIcon(self._get_fa_icon(icon_name, self.colors["TEXT"]))
            btn.setIconSize(QSize(20, 20))
        btn.setFixedSize(48, 48)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        parent_layout.addWidget(btn)
        return btn

    # ================= ИЗБРАННОЕ / ВЕЕР =================
    def toggle_favorites_only(self):
        self._play_click_voice()
        self._favorites_only = not self._favorites_only
        self._refresh_icons()
        self.filter_cards(self.search.text())
        self._rebuild_popular()
        self._rebuild_compact_row()
        self._show_toast(
            "Фильтр «Избранное»",
            "Включён" if self._favorites_only else "Выключен",
            "info",
        )

    def _toggle_fan(self):
        if not hasattr(self, "category_fan"):
            return
        self.category_fan.toggle()
        self.category_fan.apply_theme(self.colors, self.current_category)

    def _on_category_chip(self, key):
        """Клик по чипу категории под поиском."""
        self._play_click_voice()
        self.set_category(key)

    def _refresh_category_chips(self):
        """Перекрашивает текстовое меню категорий под текущий выбор."""
        if not hasattr(self, "category_buttons"):
            return
        c = self.colors
        for key, btn in self.category_buttons.items():
            active = (key == self.current_category)

            if active:
                # Активная — акцентным цветом, снизу подчёркивание
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        border: none;
                        border-bottom: 2px solid {c['ACCENT']};
                        color: {c['ACCENT']};
                        font-size: 12px;
                        font-weight: 800;
                        letter-spacing: 1.5px;
                        padding: 4px 10px 3px 10px;
                    }}
                """)
            else:
                # Неактивная — приглушённая, при наведении светлеет
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        border: none;
                        border-bottom: 2px solid transparent;
                        color: {c['SUBTEXT']};
                        font-size: 12px;
                        font-weight: 600;
                        letter-spacing: 1.5px;
                        padding: 4px 10px 3px 10px;
                    }}
                    QPushButton:hover {{
                        color: {c['ACCENT']};
                    }}
                """)


    def _on_fan_select(self, key):
        if key not in CATEGORIES:
            return
        self.set_category(key)
        if hasattr(self, "category_fan"):
            self.category_fan.close_fan()

    def _update_main_category_btn(self):
        if not hasattr(self, "main_category_btn"):
            return
        name, _ = CATEGORIES.get(self.current_category, ("Все", "🗂"))
        self.main_category_btn.setToolTip(f"Категории  ·  сейчас: {name}")
        if icon_map.HAS_QTAWESOME:
            icon_name = CAT_ICONS.get(self.current_category, "fa5s.folder")
            self.main_category_btn.setIcon(
                self._get_fa_icon(icon_name, self.colors["BG"])
            )

    def _rebuild_subcat_combo(self):
        if not hasattr(self, "subcat_combo"):
            return
        subs = (self.settings.get("subcategories") or {}).get(
            self.current_category, []
        ) or []
        self.subcat_combo.blockSignals(True)
        self.subcat_combo.clear()
        if not subs:
            self.subcat_combo.setVisible(False)
            self.subcat_combo.blockSignals(False)
            return
        self.subcat_combo.addItem("Все подкатегории", "all")
        for s in subs:
            self.subcat_combo.addItem(s, s)
        cur = self.current_subcategory
        idx = self.subcat_combo.findData(cur)
        if idx < 0:
            idx = 0
            self.current_subcategory = "all"
        self.subcat_combo.setCurrentIndex(idx)
        self.subcat_combo.setVisible(True)
        self.subcat_combo.blockSignals(False)

    def _on_subcat_combo(self, _index):
        data = self.subcat_combo.currentData()
        self.current_subcategory = data or "all"
        self.settings["current_subcategory"] = self.current_subcategory
        save_settings(self.settings)
        self.filter_cards(self.search.text())
        self._rebuild_compact_row()

    def _update_clock(self):
        try:
            if hasattr(self, "clock_label") and self.clock_label:
                self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))
        except Exception:
            pass

    def _open_web_search(self, service):
        query = self.search.text().strip()
        if not query:
            return
        q = quote(query)
        urls = {
            "google": f"https://www.google.com/search?q={q}",
            "youtube": f"https://www.youtube.com/results?search_query={q}",
            "steam": f"https://store.steampowered.com/search/?term={q}",
            "twitch": f"https://www.twitch.tv/search?term={q}",
        }
        url = urls.get(service)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    # ================= ДУБЛИКАТЫ =================
    def _normalize_path_for_compare(self, path):
        if not path:
            return ""
        p = str(path).strip()
        if not p:
            return ""
        if "://" in p:
            return p.lower()
        if p.lower().endswith(".lnk"):
            try:
                from process_check import resolve_target
                real = resolve_target(p)
                if real:
                    return str(real).strip().lower()
            except Exception:
                pass
        return p.lower()

    def _find_app_by_path(self, path):
        target = self._normalize_path_for_compare(path)
        if not target:
            return None
        for a in self.apps:
            if self._normalize_path_for_compare(a.get("path", "")) == target:
                return a
        return None

    # ================= КАРТОЧКИ =================
    def _sorted_apps(self):
        return sorted(
            self.apps,
            key=lambda a: (
                not a.get("favorite", False),
                a.get("order", 0),
                -a.get("launch_count", 0),
            ),
        )

    def _attach_category_cover_folder(self, app):
        cat = app.get("category") or "other"
        covers = self.settings.get("category_covers") or {}
        folder = covers.get(cat, "") or ""
        if folder:
            app["_category_cover_folder"] = folder
        else:
            app.pop("_category_cover_folder", None)

    def render_cards(self):
        for grid in (self.running_grid, self.grid_layout):
            while grid.count():
                item = grid.takeAt(0)
                w = item.widget() if item else None
                if w:
                    try:
                        w.hide()
                        w.setParent(None)
                        w.deleteLater()
                    except RuntimeError:
                        pass
        self.cards = []
        self.preset_tiles = []

        if self.current_category in ("all", "recent"):
            for preset in self.presets:
                tile = PresetTile(
                    preset, self.colors, self.menu_style(),
                    parent=self.grid_widget,
                )
                tile.hide()
                tile.launch_requested.connect(self._launch_preset)
                tile.edit_requested.connect(self._edit_preset)
                tile.delete_requested.connect(self._delete_preset)
                self.preset_tiles.append(tile)

        recent_paths = self.settings.get("recent_paths", [])
        for app in self._sorted_apps():
            app["category"] = app.get("category") or "other"
            if app["category"] not in CATEGORIES:
                app["category"] = "other"
            app.setdefault("companions", [])
            app.setdefault("note", "")
            app.setdefault("subcategory", "")
            if self.current_category == "recent":
                if app.get("path") not in recent_paths:
                    continue
            is_launching = app.get("path") in self.launching_paths
            self._attach_category_cover_folder(app)
            app["_auto_cover_enabled"] = bool(
                self.settings.get("auto_cover_enabled", True)
                and cover_generator.is_available()
            )
            card = TileCard(
                app, self.colors, self.menu_style(),
                is_launching=is_launching,
                parent=self.grid_widget,
            )
            card.context_menu_hook = self._inject_plugin_context_menu
            card.hide()
            card.clicked.connect(self.launch_app)
            card.rename_requested.connect(self.rename_app)
            card.change_path_requested.connect(self.change_path)
            card.delete_requested.connect(self.delete_app)
            card.toggle_favorite.connect(self.toggle_favorite)
            card.open_folder.connect(self.open_folder)
            card.change_icon_requested.connect(self.change_icon)
            card.reset_icon_requested.connect(self.reset_icon)
            card.change_cover_requested.connect(self.change_cover)
            card.reset_cover_requested.connect(self.reset_cover)
            card.change_category.connect(self.change_category_action)
            card.change_subcategory.connect(self.change_subcategory_action)
            card.move_requested.connect(self.move_app)
            card.kill_process.connect(self.kill_running_process)
            card.set_hotkey_requested.connect(self.set_program_hotkey)
            card.companions_requested.connect(self.set_companions)
            card.set_note_requested.connect(self.set_note)
            card.accept_update.connect(self.accept_update)
            card.drop_on_requested.connect(self.reorder_app_drop)
            card.launch_admin_requested.connect(self.launch_app_admin)
            self.cards.append(card)

            if self.plugin_manager:
                try:
                    self.plugin_manager.call_hook("on_card_created", card)
                except Exception as e:
                    log.error(f"on_card_created: {e}")

        name = CATEGORIES.get(self.current_category, ("Все", ""))[0]
        self.section_label.setText(name.upper())
        self._last_process_states = {
            c.app.get("path", ""): is_process_running(c.app.get("path", ""))
            for c in self.cards
        }
        self._update_titlebar_status()
        self._update_tray_tooltip()
        self._rebuild_popular()
        self._rebuild_subcat_combo()
        self.filter_cards(self.search.text())
        self._rebuild_compact_row()
        if hasattr(self, "mini_panel") and self.mini_mode:
            self._rebuild_mini_panel()
        self._animate_card_appearance()
        QTimer.singleShot(0, self._enable_mouse_tracking_recursive)

    def _animate_card_appearance(self):
        if not self.isVisible():
            return
        all_tiles = self.preset_tiles + self.cards
        if not all_tiles or len(all_tiles) > 60:
            return
        for i, w in enumerate(all_tiles):
            try:
                effect = QGraphicsOpacityEffect(w)
                effect.setOpacity(0.0)
                w.setGraphicsEffect(effect)
                anim = QPropertyAnimation(effect, b"opacity", w)
                anim.setDuration(260)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.finished.connect(
                    lambda ww=w: self._cleanup_fade_effect(ww)
                )
                if i < 15:
                    QTimer.singleShot(
                        i * 28, lambda a=anim: self._safe_anim_start(a)
                    )
                else:
                    anim.start()
                w._fade_anim = anim
            except Exception as e:
                log.error(f"animate card appearance: {e}")

    def _cleanup_fade_effect(self, widget):
        try:
            widget.setGraphicsEffect(None)
        except Exception:
            pass

    @staticmethod
    def _safe_anim_start(anim):
        try:
            anim.start()
        except RuntimeError:
            pass

    def filter_cards(self, text):
        text = (text or "").lower().strip()
        visible = 0
        sub = self.current_subcategory
        for card in self.cards:
            app_cat = str(card.app.get("category") or "other")
            running = getattr(card, "running", False)
            is_fav = bool(card.app.get("favorite", False))
            if running:
                in_cat = True
                in_sub = True
            else:
                in_cat = (
                        self.current_category in ("all", "recent")
                        or app_cat == self.current_category
                )
                in_sub = True
                if (sub and sub != "all"
                        and self.current_category not in ("all", "recent")):
                    in_sub = (card.app.get("subcategory") or "") == sub
            in_search = text in card.app.get("name", "").lower()
            in_fav = (not self._favorites_only) or is_fav
            match = in_cat and in_search and in_sub and in_fav
            card.setVisible(bool(match))
            if match:
                visible += 1
        visible_presets = 0
        for tile in self.preset_tiles:
            in_search = (
                    not text or text in tile.preset.get("name", "").lower()
            )
            in_fav = not self._favorites_only
            match = in_search and in_fav
            tile.setVisible(bool(match))
            if match:
                visible_presets += 1
        if self.compact_mode:
            for c in self.cards:
                c.setVisible(False)
            for p in self.preset_tiles:
                p.setVisible(False)
        self._relayout_grid()
        self._rebuild_compact_row()
        total = visible + visible_presets
        if total == 0:
            if not self.apps and not self.presets:
                msg = "Пока здесь пусто"
                hint = ("Добавь первую программу, импортируй её из "
                        "меню Пуск или создай пресет.")
            elif text:
                msg = "Ничего не найдено"
                hint = "Попробуй другой запрос или очисти поиск."
            elif self._favorites_only:
                msg = "Нет избранных"
                hint = "Отметь программы звёздочкой в контекстном меню."
            else:
                msg = "В этой категории пока нет программ"
                hint = "Добавь программу или переключись на другую категорию."
            self.empty_label.setText(msg)
            self.empty_hint.setText(hint)
            self.empty_hint.setVisible(True)
            show_btns = (not text) and (not self._favorites_only)
            self.empty_buttons_widget.setVisible(show_btns)
            show_web = bool(text) and self.settings.get("show_search", True)
            if hasattr(self, "search_shortcuts"):
                self.search_shortcuts.setVisible(show_web)
            if hasattr(self, "empty_widget"):
                self.empty_widget.setVisible(True)
            else:
                self.empty_label.setVisible(True)
        else:
            if hasattr(self, "empty_widget"):
                self.empty_widget.setVisible(False)
            else:
                self.empty_label.setVisible(False)

    def set_category(self, key):
        if key not in CATEGORIES:
            return
        self._play_click_voice()
        self.current_category = key
        self.settings["current_category"] = key
        self.current_subcategory = "all"
        self.settings["current_subcategory"] = "all"
        save_settings(self.settings)
        self._update_main_category_btn()
        if hasattr(self, "category_fan"):
            self.category_fan.apply_theme(self.colors, self.current_category)
        # self.section_label скрыт — заголовок показывается только в меню
        self._rebuild_subcat_combo()
        self._refresh_category_chips()
        self.filter_cards(self.search.text())
        self._rebuild_compact_row()
        try:
            self.scroll.verticalScrollBar().setValue(0)
        except Exception:
            pass
        sounds.play("toggle")
        if self.plugin_manager:
            try:
                self.plugin_manager.call_hook("on_category_change", key)
            except Exception:
                pass

    # ================= СОРТИРОВКА =================
    def _renumber_orders(self):
        sorted_apps = self._sorted_apps()
        for i, app in enumerate(sorted_apps):
            for a in self.apps:
                if a is app:
                    a["order"] = i
                    break

    def move_app(self, app, direction):
        target = None
        for a in self.apps:
            if a == app:
                target = a
                break
        if target is None:
            return
        self._renumber_orders()
        sorted_apps = self._sorted_apps()
        if direction == "top":
            same = [a for a in sorted_apps
                    if a.get("favorite", False) == target.get("favorite", False)]
            if same and same[0] is target:
                return
            target["order"] = min(a.get("order", 0) for a in same) - 1
        elif direction == "bottom":
            same = [a for a in sorted_apps
                    if a.get("favorite", False) == target.get("favorite", False)]
            if same and same[-1] is target:
                return
            target["order"] = max(a.get("order", 0) for a in same) + 1
        elif direction == "up":
            same = [a for a in sorted_apps
                    if a.get("favorite", False) == target.get("favorite", False)]
            try:
                pos = next(i for i, a in enumerate(same) if a is target)
            except StopIteration:
                return
            if pos == 0:
                return
            prev = same[pos - 1]
            target["order"], prev["order"] = prev["order"], target["order"]
        elif direction == "down":
            same = [a for a in sorted_apps
                    if a.get("favorite", False) == target.get("favorite", False)]
            try:
                pos = next(i for i, a in enumerate(same) if a is target)
            except StopIteration:
                return
            if pos >= len(same) - 1:
                return
            nxt = same[pos + 1]
            target["order"], nxt["order"] = nxt["order"], target["order"]
        save_apps(self.apps)
        self.render_cards()

    def reorder_app_drop(self, src_app, dst_app):
        if src_app is dst_app:
            return
        src = next((a for a in self.apps
                    if a.get("path") == src_app.get("path")), None)
        dst = next((a for a in self.apps
                    if a.get("path") == dst_app.get("path")), None)
        if src is None or dst is None:
            return
        self._renumber_orders()
        ordered = self._sorted_apps()
        try:
            src_pos = next(i for i, a in enumerate(ordered) if a is src)
            dst_pos = next(i for i, a in enumerate(ordered) if a is dst)
        except StopIteration:
            return
        if src_pos == dst_pos:
            return
        ordered.pop(src_pos)
        ordered.insert(dst_pos, src)
        for i, a in enumerate(ordered):
            a["order"] = i
        save_apps(self.apps)
        self.render_cards()

    # ================= ДЕЙСТВИЯ =================
    def _add_app_by_path(self, path):
        existing = self._find_app_by_path(path)
        if existing is not None:
            self._show_toast(
                "Уже добавлено",
                f"«{existing.get('name')}» уже в лаунчере",
                "info",
            )
            return
        name = os.path.splitext(os.path.basename(path))[0]
        max_order = max((a.get("order", 0) for a in self.apps), default=-1)
        new_app = {
            "name": name, "path": path, "favorite": False,
            "launch_count": 0, "category": "other",
            "subcategory": "",
            "custom_icon": "", "custom_cover": "",
            "order": max_order + 1, "hotkey": "",
            "companions": [], "note": "",
            "known_version": "",
        }
        options = [(k, v[0]) for k, v in CATEGORIES.items()
                   if k not in ("all", "recent")]
        cat, ok = ask_category(
            self, self.colors, "Выберите категорию",
            f"Куда добавить «{name}»?", options,
            current=self.current_category
            if self.current_category not in ("all", "recent") else "other",
        )
        if ok:
            new_app["category"] = cat
        self.apps.append(new_app)
        save_apps(self.apps)
        self.render_cards()
        QTimer.singleShot(500, self._check_updates_for_apps)
        sounds.play("success")
        sounds.play_voice("success")

    def add_app(self):
        self._play_click_voice()
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите программу", "",
            "Программы (*.exe *.lnk *.bat *.cmd);;Все файлы (*.*)"
        )
        if not path:
            return
        self._add_app_by_path(path)

    def open_import(self):
        self._play_click_voice()
        from importers import (
            scan_start_menu, scan_desktop, scan_steam, scan_epic
        )
        from import_dialog import ImportDialog
        candidates = (
            scan_start_menu() + scan_desktop()
            + scan_steam() + scan_epic()
        )
        if not candidates:
            self._show_toast("Импорт", "Не найдено ни одной программы", "warning")
            return
        existing = {a["path"] for a in self.apps}
        dlg = ImportDialog(self, self.colors, candidates, existing)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dlg.chosen_category
        added = 0
        skipped = 0
        max_order = max((a.get("order", 0) for a in self.apps), default=-1)
        for c in dlg.selected:
            if c["path"] in existing or self._find_app_by_path(c["path"]):
                skipped += 1
                continue
            max_order += 1
            category = chosen if chosen in CATEGORIES else "other"
            self.apps.append({
                "name": c["name"], "path": c["path"],
                "favorite": False, "launch_count": 0,
                "category": category, "subcategory": "",
                "custom_icon": "", "custom_cover": "",
                "order": max_order, "hotkey": "",
                "companions": [], "note": "",
                "known_version": "",
            })
            existing.add(c["path"])
            added += 1
        if added:
            save_apps(self.apps)
            self.render_cards()
            msg = f"Добавлено программ: {added}"
            if skipped:
                msg += f"\nПропущено: {skipped}"
            self._show_toast("Импорт завершён", msg, "success")
            QTimer.singleShot(500, self._check_updates_for_apps)
            sounds.play("success")
            sounds.play_voice("success")
        else:
            self._show_toast("Импорт завершён",
                             "Ничего нового не добавлено", "info")

    def rename_app(self, app):
        self._play_click_voice()
        new_name, ok = ask_text(self, self.colors, "Переименовать",
                                "Новое название:", app.get("name", ""))
        if ok and new_name:
            for a in self.apps:
                if a == app:
                    a["name"] = new_name
                    break
            save_apps(self.apps)
            self.render_cards()

    def change_path(self, app):
        self._play_click_voice()
        new_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите новую программу", "",
            "Программы (*.exe *.lnk *.bat *.cmd);;Все файлы (*.*)"
        )
        if new_path:
            for a in self.apps:
                if a == app:
                    a["path"] = new_path
                    a["known_version"] = ""
                    break
            clear_cache()
            clear_lnk_cache()
            save_apps(self.apps)
            self.render_cards()
            QTimer.singleShot(500, self._check_updates_for_apps)

    def change_icon(self, app):
        self._play_click_voice()
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите иконку", "",
            "Иконки (*.png *.ico *.jpg *.jpeg *.bmp *.svg);;Все файлы (*.*)"
        )
        if not path:
            return
        for a in self.apps:
            if a == app:
                a["custom_icon"] = path
                break
        clear_cache()
        save_apps(self.apps)
        self.render_cards()

    def reset_icon(self, app):
        for a in self.apps:
            if a == app:
                a["custom_icon"] = ""
                break
        clear_cache()
        save_apps(self.apps)
        self.render_cards()

    def change_cover(self, app):
        self._play_click_voice()
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите обложку (рекомендуется 200×140 или шире)", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp);;Все файлы (*.*)"
        )
        if not path:
            return
        for a in self.apps:
            if a == app:
                a["custom_cover"] = path
                break
        save_apps(self.apps)
        self.render_cards()

    def reset_cover(self, app):
        for a in self.apps:
            if a == app:
                a["custom_cover"] = ""
                break
        save_apps(self.apps)
        self.render_cards()

    def change_category_action(self, app):
        options = [(k, v[0]) for k, v in CATEGORIES.items()
                   if k not in ("all", "recent")]
        cat, ok = ask_category(self, self.colors, "Изменить категорию",
                               "Выберите новую категорию:", options,
                               current=app.get("category", "other"))
        if ok:
            for a in self.apps:
                if a == app:
                    a["category"] = cat if cat in CATEGORIES else "other"
                    a["subcategory"] = ""
                    break
            save_apps(self.apps)
            self.render_cards()

    def change_subcategory_action(self, app):
        cat = app.get("category") or "other"
        subs = (self.settings.get("subcategories") or {}).get(cat, []) or []
        options = [("", "— Без подкатегории —")]
        for s in subs:
            options.append((s, s))
        if len(options) == 1:
            self._show_toast(
                "Нет подкатегорий",
                f"Сначала добавь подкатегории для категории "
                f"«{CATEGORIES.get(cat, (cat,))[0]}»:\n"
                "Настройки → Категории → Настроить",
                "info",
            )
            return
        current = app.get("subcategory") or ""
        chosen, ok = ask_category(
            self, self.colors, "Подкатегория",
            f"Выбери подкатегорию для «{app.get('name')}»:",
            options, current=current if current else "",
        )
        if not ok:
            return
        for a in self.apps:
            if a == app:
                a["subcategory"] = chosen or ""
                break
        save_apps(self.apps)
        self.render_cards()

    def set_program_hotkey(self, app):
        if app.get("_clear_hotkey"):
            app.pop("_clear_hotkey", None)
            for a in self.apps:
                if a == app:
                    a["hotkey"] = ""
                    break
            save_apps(self.apps)
            self._register_program_hotkeys()
            self.render_cards()
            return
        current = app.get("hotkey", "")
        seq, ok = ask_hotkey(self, self.colors, app.get("name", ""),
                             current=current)
        if not ok:
            return
        if not seq:
            for a in self.apps:
                if a == app:
                    a["hotkey"] = ""
                    break
        else:
            for a in self.apps:
                if a is not app and a.get("hotkey") == seq:
                    self._show_toast(
                        "Горячая клавиша занята",
                        f"«{seq}» уже назначена для «{a.get('name')}»",
                        "warning",
                    )
                    return
            for a in self.apps:
                if a == app:
                    a["hotkey"] = seq
                    break
        save_apps(self.apps)
        self._register_program_hotkeys()
        self.render_cards()

    def set_note(self, app):
        from PySide6.QtWidgets import QInputDialog
        current = (app.get("note") or "").strip()
        text, ok = QInputDialog.getMultiLineText(
            self, "Заметка",
            f"Заметка для «{app.get('name')}»:",
            current,
        )
        if not ok:
            return
        new_note = text.strip()
        for a in self.apps:
            if a == app:
                a["note"] = new_note
                break
        save_apps(self.apps)
        self.render_cards()

    def set_companions(self, app):
        try:
            dlg = CompanionPickerDialog(
                self, self.colors, self.apps,
                current_path=app.get("path", ""),
                companions=app.get("companions", []) or [],
            )
        except Exception as e:
            log.error(f"CompanionPickerDialog error: {e}")
            show_error(self, self.colors, "Ошибка",
                       f"Не удалось открыть диалог: {e}")
            return
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        for a in self.apps:
            if a == app:
                a["companions"] = dlg.result_companions or []
                break
        save_apps(self.apps)
        self.render_cards()

    def delete_app(self, app):
        self._play_click_voice()
        name = app.get("name", "")
        ok = ask_confirm(self, self.colors, "Удалить программу",
                         f"Удалить «{name}» из лаунчера?\n"
                         "Сама программа на диске останется на месте.",
                         ok_text="Удалить")
        if not ok:
            return
        for i, a in enumerate(self.apps):
            if a == app:
                del self.apps[i]
                break
        save_apps(self.apps)
        self._register_program_hotkeys()
        clear_lnk_cache()
        self.render_cards()
        sounds.play("close")
        sounds.play_voice("close")

    def toggle_favorite(self, app):
        self._play_click_voice()
        for a in self.apps:
            if a == app:
                a["favorite"] = not a.get("favorite", False)
                break
        save_apps(self.apps)
        self.render_cards()

    def open_folder(self, app):
        self._play_click_voice()
        path = app.get("path", "")
        if "://" in path:
            return
        folder = os.path.dirname(path)
        if os.path.exists(folder):
            os.startfile(folder)

    def kill_running_process(self, app):
        self._play_click_voice()
        name = app.get("name", "")
        if self.settings.get("confirm_kill", True):
            ok = ask_confirm(
                self, self.colors,
                "Завершить процесс",
                f"Завершить «{name}»?\n\n"
                "Все несохранённые данные в программе могут быть потеряны.",
                ok_text="Завершить",
            )
            if not ok:
                return
        n = kill_process(app.get("path", ""))
        if n:
            log.info(f"Завершено процессов: {n} ({name})")
            sounds.play("close")
            sounds.play_voice("close")
            try:
                self._started_by_us.discard(app.get("path", ""))
            except Exception:
                pass
            if self.plugin_manager:
                try:
                    self.plugin_manager.call_hook("on_app_close", app)
                except Exception:
                    pass
            if getattr(self, "discord_rpc", None) is not None:
                try:
                    self.discord_rpc.on_app_close(app)
                except Exception:
                    pass
            QTimer.singleShot(300, self.render_cards)
        else:
            self._show_toast("Завершение процесса",
                             "Процесс не найден или уже закрыт", "warning")

    # ================= КОНТЕКСТНОЕ МЕНЮ =================
    def _on_grid_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_style())

        def add(icon_name, text, color=None):
            if color is None:
                color = self.colors["TEXT"]
            icon = self._get_fa_icon(icon_name, color)
            if icon_map.HAS_QTAWESOME:
                return menu.addAction(icon, text)
            return menu.addAction(text)

        act_add = add("fa5s.plus", "Добавить программу…", self.colors["ACCENT"])
        act_paste = add("fa5s.file-import", "Вставить путь из буфера",
                        self.colors["ACCENT"])
        act_import = add("fa5s.download", "Импорт из меню Пуск / Steam / Epic…")
        act_library = add("fa5s.gamepad", "Библиотека игр…")
        menu.addSeparator()
        act_compact = add("fa5s.th-large",
                          "Обычный режим" if self.compact_mode
                          else "Компактный режим")
        act_fav = add("fa5s.star",
                      "Показать все" if self._favorites_only
                      else "Показать только избранные")
        menu.addSeparator()
        act_reload = add("fa5s.sync-alt", "Перечитать apps.json (Ctrl+R)")
        act_refresh = add("fa5s.undo", "Обновить статусы (F5)")
        menu.addSeparator()
        act_folder_data = add("fa5s.folder-open", "Открыть папку данных")
        act_settings = add("fa5s.cog", "Настройки…")

        chosen = menu.exec(self.scroll_content.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_add:
            self.add_app()
        elif chosen == act_paste:
            self._paste_from_clipboard()
        elif chosen == act_import:
            self.open_import()
        elif chosen == act_library:
            self.open_games_library()
        elif chosen == act_compact:
            self.toggle_compact_mode()
        elif chosen == act_fav:
            self.toggle_favorites_only()
        elif chosen == act_reload:
            self._reload_apps_from_disk()
        elif chosen == act_refresh:
            self._refresh_statuses()
        elif chosen == act_folder_data:
            try:
                from config import BASE_DIR
                os.startfile(BASE_DIR)
            except Exception as e:
                log.error(f"open data folder: {e}")
        elif chosen == act_settings:
            self.open_settings()

    # ================= ПОПУЛЯРНОЕ =================
    def _rebuild_popular(self):
        if not hasattr(self, "popular_layout"):
            return
        while self.popular_layout.count():
            item = self.popular_layout.takeAt(0)
            w = item.widget() if item else None
            if w:
                try:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                except RuntimeError:
                    pass
        self._popular_tiles = []
        candidates = []
        for app in self.apps:
            try:
                count = int(app.get("launch_count", 0) or 0)
            except Exception:
                count = 0
            if count <= 0:
                continue
            if self._favorites_only and not app.get("favorite"):
                continue
            try:
                if is_process_running(app.get("path", "")):
                    continue
            except Exception:
                pass
            candidates.append((count, app))
        if not candidates:
            self.popular_header.setVisible(False)
            self.popular_widget.setVisible(False)
            return
        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[:5]
        for count, app in top:
            ico = QuickAppIcon(
                app, self.colors, size=48,
                tooltip=f"{app.get('name', '')}  ·  запусков: {count}",
            )
            ico.clicked.connect(self.launch_app)
            ico.right_click.connect(self._show_quick_icon_menu)
            self.popular_layout.addWidget(ico, 0, Qt.AlignLeft)
            self._popular_tiles.append(ico)
        self.popular_layout.addStretch()
        show_popular = (not self.compact_mode) and len(top) > 0
        self.popular_header.setVisible(
            show_popular
            and self.settings.get("show_section_headers", True)
        )
        self.popular_widget.setVisible(show_popular)

    # ================= СЕТКА =================
    def _relayout_grid(self):
        if not hasattr(self, "grid_layout"):
            return
        scroll_pos = self.scroll.verticalScrollBar().value()
        for grid in (self.running_grid, self.grid_layout):
            while grid.count():
                grid.takeAt(0)
        if self.compact_mode:
            try:
                self.scroll.verticalScrollBar().setValue(scroll_pos)
            except Exception:
                pass
            return
        visible_cards = [c for c in self.cards if c.isVisible()]
        visible_presets = [p for p in self.preset_tiles if p.isVisible()]
        running_cards = [c for c in visible_cards if getattr(c, "running", False)]
        other_cards = [c for c in visible_cards if not getattr(c, "running", False)]
        show_running_setting = self.settings.get("show_running_section", True)
        show_running_section = show_running_setting and len(running_cards) > 0
        viewport_w = self.scroll.viewport().width()
        if viewport_w < 100:
            viewport_w = 1180
        tw = tile_card.TILE_WIDTH
        ts = tile_card.TILE_SPACING
        cols = max(1, (viewport_w + ts) // (tw + ts))
        self.running_header.setVisible(
            show_running_section
            and self.settings.get("show_section_headers", True)
        )
        self.running_grid_widget.setVisible(show_running_section)
        if show_running_section:
            for i, tile in enumerate(running_cards):
                self.running_grid.addWidget(
                    tile, i // cols, i % cols, Qt.AlignTop | Qt.AlignLeft
                )
            for i in range(self.running_grid.columnCount()):
                self.running_grid.setColumnStretch(i, 0)
            self.running_grid.setColumnStretch(cols, 1)
            main_tiles = visible_presets + other_cards
        else:
            main_tiles = visible_presets + running_cards + other_cards
        if main_tiles:
            for i, tile in enumerate(main_tiles):
                self.grid_layout.addWidget(
                    tile, i // cols, i % cols, Qt.AlignTop | Qt.AlignLeft
                )
            for i in range(self.grid_layout.columnCount()):
                self.grid_layout.setColumnStretch(i, 0)
            self.grid_layout.setColumnStretch(cols, 1)
        try:
            self.scroll.verticalScrollBar().setValue(scroll_pos)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._relayout_grid)
        QTimer.singleShot(20, self._rebuild_compact_row)
        if self._scan_overlay is not None:
            try:
                self._scan_overlay.setGeometry(0, 0, self.width(), self.height())
            except Exception:
                pass

    # ================= СТАТУСЫ =================
    def _refresh_statuses(self):
        if getattr(self, "discord_rpc", None) is not None:
            try:
                self.discord_rpc.tick()
                cur = self.discord_rpc._current_session
                if cur:
                    path = cur.get("path")
                    if path and not is_process_running(path):
                        dummy = {"path": path, "name": cur.get("name", "")}
                        self.discord_rpc.on_app_close(dummy)
            except Exception:
                pass

        if not self.cards:
            self._update_titlebar_status()
            self._update_tray_tooltip()
            return
        unique_paths = {
            c.app.get("path", "") for c in self.cards
            if c.app.get("path", "")
        }
        states = {p: is_process_running(p) for p in unique_paths}
        self._update_titlebar_status()
        self._update_tray_tooltip()
        if states == self._last_process_states:
            return
        self._last_process_states = states
        changed = False
        for card in self.cards:
            p = card.app.get("path", "")
            new_running = states.get(p, False)
            if getattr(card, "running", False) != new_running:
                card.running = new_running
                changed = True
                try:
                    card.update()
                except Exception:
                    pass

        # Уведомление о завершении программ, запущенных через лаунчер
        try:
            for p in list(self._started_by_us):
                if not states.get(p, False):
                    name = None
                    for a in self.apps:
                        if a.get("path") == p:
                            name = a.get("name", "")
                            break
                    if not name:
                        name = os.path.basename(p)
                    self._show_toast(
                        "Программа завершилась",
                        name,
                        "info",
                    )
                    self._started_by_us.discard(p)
        except Exception:
            pass

        for ico in getattr(self, "_popular_tiles", []) or []:
            try:
                ico.refresh_running()
            except Exception:
                pass
        for ico in getattr(self, "_compact_tiles", []) or []:
            try:
                ico.refresh_running()
            except Exception:
                pass
        if changed:
            self.render_cards()

    # ================= СТАТИСТИКА / ОБНОВЛЕНИЯ =================
    def _tick_stats(self):
        if not self.apps:
            return
        for app in self.apps:
            path = app.get("path", "")
            if not path or "://" in path:
                continue
            try:
                if is_process_running(path):
                    add_time(self._stats, path, self._stats_tick_seconds)
            except Exception:
                pass
        try:
            save_stats(self._stats)
        except Exception as e:
            log.error(f"save_stats: {e}")

    def _check_updates_for_apps(self):
        """Собирает версии .exe в фоне, чтобы не фризить UI."""
        # Отменяем предыдущую задачу, если ещё летит
        if getattr(self, "_updates_task_active", False):
            return
        self._updates_task_active = True

        paths = []
        for app in self.apps:
            p = app.get("path", "")
            if p and "://" not in p:
                paths.append(p)

        task = _VersionScanTask(paths)
        task.signals.done.connect(self._on_versions_scanned)
        QThreadPool.globalInstance().start(task)

    def _on_versions_scanned(self, versions):
        self._updates_task_active = False
        changed = False
        for app in self.apps:
            path = app.get("path", "")
            if not path or "://" in path:
                app.pop("_has_update", None)
                continue
            current = versions.get(path, "")
            if not current:
                app.pop("_has_update", None)
                continue
            known = (app.get("known_version") or "").strip()
            if not known:
                app["known_version"] = current
                changed = True
                app.pop("_has_update", None)
            elif known != current:
                app["_has_update"] = True
            else:
                app.pop("_has_update", None)

        if changed:
            save_apps(self.apps)
        has_updates = any(a.get("_has_update") for a in self.apps)
        if has_updates:
            self.render_cards()
        self._update_settings_badge(has_updates)
    def _update_settings_badge(self, has_updates):
        try:
            if self._settings_badge is None:
                return
            self._settings_badge.setVisible(bool(has_updates))
            if has_updates:
                self._settings_badge.move(
                    self.settings_btn.width() - 14, 6
                )
        except Exception:
            pass

    def accept_update(self, app):
        path = app.get("path", "")
        cur = get_exe_version(path) if path else ""
        for a in self.apps:
            if a == app:
                a["known_version"] = cur
                a.pop("_has_update", None)
                break
        save_apps(self.apps)
        sounds.play("success")
        sounds.play_voice("success")
        self.render_cards()

    # ================= БИБЛИОТЕКА =================
    def _find_cover_for_library_game(self, game):
        try:
            p = game_scanner.get_cover_for_game(game)
            if p and os.path.exists(p):
                return p
        except Exception:
            pass
        if cover_fetcher is not None:
            try:
                p = cover_fetcher.find_local_cover_for_game(game)
                if p and os.path.exists(p):
                    return p
            except Exception:
                pass
        try:
            key = cover_generator._cache_key(
                game, 400, 280,
                self.colors.get("ACCENT", "#89B4FA"),
                show_name=False, library_style=True,
            )
            p = os.path.join(cover_generator.CACHE_DIR, f"{key}.png")
            if os.path.exists(p):
                return p
        except Exception:
            pass
        try:
            key = cover_generator._cache_key(
                game, 400, 280,
                self.colors.get("ACCENT", "#89B4FA"),
            )
            p = os.path.join(cover_generator.CACHE_DIR, f"{key}.png")
            if os.path.exists(p):
                return p
        except Exception:
            pass
        try:
            if cover_generator.is_available():
                icon_png = cover_generator._save_icon_as_png(
                    game, "tmp_lib_add", 256
                )
                if icon_png:
                    try:
                        result = cover_generator.ensure_cover_file(
                            game, self.colors,
                            w=400, h=280,
                            icon_png_path=icon_png,
                            show_name=False, library_style=True,
                        )
                    finally:
                        try:
                            os.remove(icon_png)
                        except Exception:
                            pass
                    if result and os.path.exists(result):
                        return result
        except Exception as e:
            log.error(f"_find_cover_for_library_game gen: {e}")
        return ""

    def open_games_library(self):
        self._play_click_voice()
        if (self._games_library_dialog is not None
                and self._games_library_dialog.isVisible()):
            self._games_library_dialog.raise_()
            self._games_library_dialog.activateWindow()
            self._games_library_dialog.refresh_apps(self.apps)
            try:
                self._games_library_dialog.refresh_stats()
            except Exception:
                pass
            return
        try:
            dlg = GamesLibraryDialog(
                self, self.colors, self.apps,
                on_add_to_launcher=self._library_add_to_launcher,
                on_remove_from_launcher=self._library_remove_from_launcher,
                on_launch_game=self._library_launch_game,
            )
            dlg.finished.connect(self._on_library_closed)
            self._games_library_dialog = dlg
            dlg.show()
        except Exception as e:
            log.error(f"open_games_library: {e}")
            show_error(self, self.colors, "Ошибка",
                       f"Не удалось открыть библиотеку: {e}")

    def _on_library_closed(self, _result):
        self._games_library_dialog = None

    def _library_add_to_launcher(self, game):
        self._play_click_voice()
        path = (game.get("path") or "").strip()
        if not path:
            self._show_toast("Ошибка", "У игры нет пути запуска", "error")
            return
        existing = self._find_app_by_path(path)
        if existing is not None:
            self._show_toast(
                "Уже добавлено",
                f"«{existing.get('name')}» уже в лаунчере",
                "info",
            )
            return
        max_order = max((a.get("order", 0) for a in self.apps), default=-1)
        custom_cover = self._find_cover_for_library_game(game)
        new_app = {
            "name":         game.get("name", "Без имени"),
            "path":         path,
            "favorite":     False,
            "launch_count": 0,
            "category":     "games",
            "subcategory":  "",
            "custom_icon":  "",
            "custom_cover": custom_cover,
            "order":        max_order + 1,
            "hotkey":       "",
            "companions":   [],
            "note":         "",
            "known_version": "",
        }
        self.apps.append(new_app)
        save_apps(self.apps)
        self.render_cards()
        QTimer.singleShot(500, self._check_updates_for_apps)
        sounds.play("success")
        self._show_toast("Добавлено в лаунчер", new_app["name"], "success")

    def _library_remove_from_launcher(self, game):
        path = (game.get("path") or "").strip().lower()
        removed = None
        for i, a in enumerate(self.apps):
            if (a.get("path") or "").lower() == path:
                removed = self.apps.pop(i)
                break
        if removed is None:
            return
        save_apps(self.apps)
        self._register_program_hotkeys()
        self.render_cards()
        sounds.play("close")
        self._show_toast("Удалено из лаунчера",
                         removed.get("name", ""), "info")

    def _library_launch_game(self, game):
        self._play_click_voice()
        path = (game.get("path") or "").strip()
        if not path:
            self._show_toast("Ошибка", "У игры нет пути запуска", "error")
            return
        app = next(
            (a for a in self.apps
             if (a.get("path") or "").lower() == path.lower()),
            None,
        )
        if app is not None:
            self.launch_app(app)
            return
        temp = {
            "name": game.get("name", ""),
            "path": path,
            "custom_icon": "",
            "category": "games",
        }
        result = launch(temp)
        if not result.ok:
            self._show_toast("Не удалось запустить", result.error, "error")
            return
        sounds.play("launch")
        sounds.play_voice("launch")
        self._show_toast("Запущено", game.get("name", ""), "success")
        if getattr(self, "discord_rpc", None) is not None:
            try:
                self.discord_rpc.on_app_launch(temp)
            except Exception:
                pass

    # ================= ПРЕСЕТЫ =================
    def open_presets_manager(self):
        self._play_click_voice()
        dlg = QDialog(self)
        dlg.setWindowTitle("Пресеты запуска")
        dlg.setMinimumWidth(560)
        dlg.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title = QLabel("Пресеты запуска")
        title.setStyleSheet(
            f"color: {self.colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(title)
        hint = QLabel(
            "Пресет запускает сразу несколько программ одной кнопкой.\n"
            "Например: «Работа» = Word + Chrome + Telegram."
        )
        hint.setStyleSheet(f"color: {self.colors['SUBTEXT']}; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        lw = QListWidget()
        lw.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.colors['BG_ALT']};
                color: {self.colors['TEXT']};
                border: 1px solid {self.colors['BORDER']};
                border-radius: 12px;
                padding: 6px;
                font-size: 14px;
                outline: none;
            }}
            QListWidget::item {{ padding: 10px; border-radius: 8px; }}
            QListWidget::item:selected {{
                background-color: {self.colors['ACCENT_SOFT']};
                color: {self.colors['ACCENT']};
            }}
        """)

        def refresh():
            lw.clear()
            for p in self.presets:
                item = QListWidgetItem(
                    f"{p.get('icon', '🚀')}  {p.get('name', 'Без имени')}   "
                    f"({len(p.get('paths', []))} программ)"
                )
                item.setData(Qt.ItemDataRole.UserRole, p)
                lw.addItem(item)

        refresh()
        layout.addWidget(lw, 1)
        mgmt_row = QHBoxLayout()
        mgmt_row.setSpacing(8)
        add_btn = QPushButton("+ Создать пресет")
        mgmt_row.addWidget(add_btn)
        edit_btn = QPushButton("✏ Редактировать")
        mgmt_row.addWidget(edit_btn)
        del_btn = QPushButton("🗑 Удалить")
        mgmt_row.addWidget(del_btn)
        mgmt_row.addStretch()
        layout.addLayout(mgmt_row)
        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = QPushButton("Закрыть")
        close_btn.setProperty("accent", True)
        close_btn.clicked.connect(dlg.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        def add_preset():
            edit_dlg = PresetsDialog(self, self.colors, self.apps)
            if edit_dlg.exec() == QDialog.DialogCode.Accepted:
                if edit_dlg.result_preset:
                    self.presets.append(edit_dlg.result_preset)
                    save_presets(self.presets)
                    refresh()
                    self.render_cards()

        def edit_preset():
            item = lw.currentItem()
            if not item:
                return
            preset = item.data(Qt.ItemDataRole.UserRole)
            edit_dlg = PresetsDialog(self, self.colors, self.apps, preset)
            if edit_dlg.exec() == QDialog.DialogCode.Accepted:
                if edit_dlg.result_preset:
                    idx = self.presets.index(preset)
                    self.presets[idx] = edit_dlg.result_preset
                    save_presets(self.presets)
                    refresh()
                    self.render_cards()

        def delete_preset():
            item = lw.currentItem()
            if not item:
                return
            preset = item.data(Qt.ItemDataRole.UserRole)
            if not ask_confirm(self, self.colors, "Удалить пресет",
                               f"Удалить пресет «{preset.get('name')}»?",
                               ok_text="Удалить"):
                return
            self.presets.remove(preset)
            save_presets(self.presets)
            refresh()
            self.render_cards()

        add_btn.clicked.connect(add_preset)
        edit_btn.clicked.connect(edit_preset)
        del_btn.clicked.connect(delete_preset)
        lw.itemDoubleClicked.connect(lambda _: edit_preset())
        dlg.exec()

    def _launch_preset(self, preset):
        paths = preset.get("paths", [])
        if not paths:
            self._show_toast("Пресет пуст",
                             "В пресете нет программ", "warning")
            return
        launched = 0
        for path in paths:
            app = next((a for a in self.apps if a.get("path") == path), None)
            if app is None:
                continue
            if is_process_running(path):
                continue
            self._do_launch(app)
            launched += 1

    def _edit_preset(self, preset):
        dlg = PresetsDialog(self, self.colors, self.apps, preset)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.result_preset:
                idx = self.presets.index(preset)
                self.presets[idx] = dlg.result_preset
                save_presets(self.presets)
                self.render_cards()

    def _delete_preset(self, preset):
        if not ask_confirm(self, self.colors, "Удалить пресет",
                           f"Удалить пресет «{preset.get('name')}»?",
                           ok_text="Удалить"):
            return
        self.presets.remove(preset)
        save_presets(self.presets)
        self.render_cards()

    # ================= ТРЕЙ / HOTKEY =================
    def _build_tray(self):
        self.tray = QSystemTrayIcon(
            make_tray_icon(
                self.colors,
                self.settings.get("tray_icon", ""),
                self._app_name(),
            ),
            self,
        )
        self.tray.setToolTip(f"{self._app_name()} {APP_VERSION}")
        self.tray.setContextMenu(self._build_tray_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _populate_recent_menu(self, menu):
        try:
            recents = self.settings.get("recent_paths", [])[:8]
        except Exception:
            recents = []
        if not recents:
            empty = menu.addAction("(пока пусто)")
            empty.setEnabled(False)
            return
        for path in recents:
            app = next((a for a in self.apps if a.get("path") == path), None)
            name = app.get("name") if app else os.path.basename(path)
            act = menu.addAction(f"  {name}")
            act.triggered.connect(
                lambda _=False, p=path: self._launch_recent(p)
            )
        menu.addSeparator()
        act_clear = menu.addAction("Очистить список")
        act_clear.triggered.connect(self._clear_recent)

    def _launch_recent(self, path):
        app = next((a for a in self.apps if a.get("path") == path), None)
        if app is None:
            self._show_toast("Не найдено",
                             "Программа больше не в списке лаунчера",
                             "warning")
            return
        self.show_window()
        self.launch_app(app)

    def _clear_recent(self):
        self.settings["recent_paths"] = []
        save_settings(self.settings)
        try:
            self.tray.setContextMenu(self._build_tray_menu())
        except Exception as e:
            log.error(f"_clear_recent: {e}")

    def _build_tray_menu(self):
        menu = QMenu()
        self._style_menu(menu)
        act_show = menu.addAction("Показать окно")
        act_show.triggered.connect(self.show_window)
        act_hide = menu.addAction("Скрыть окно")
        act_hide.triggered.connect(self.hide)
        menu.addSeparator()
        act_add = menu.addAction("➕  Добавить программу…")
        act_add.triggered.connect(self._tray_add_program)
        act_paste = menu.addAction("📋  Вставить путь из буфера")
        act_paste.triggered.connect(self._paste_from_clipboard)
        act_library = menu.addAction("🎮  Библиотека игр…")
        act_library.triggered.connect(self.open_games_library)
        menu.addSeparator()
        act_quick = menu.addAction("Быстрый поиск…  (Ctrl+Alt+Space)")
        act_quick.triggered.connect(self.show_quick)
        recent_menu = QMenu("Недавние", menu)
        self._style_menu(recent_menu)
        self._populate_recent_menu(recent_menu)
        menu.addMenu(recent_menu)
        act_ontop = menu.addAction("Поверх всех окон")
        act_ontop.setCheckable(True)
        act_ontop.setChecked(self.always_on_top)
        act_ontop.triggered.connect(self.toggle_always_on_top)
        act_settings = menu.addAction("Настройки…")
        act_settings.triggered.connect(self.open_settings)
        menu.addSeparator()
        act_reload_plugins = menu.addAction("🔄  Перезагрузить плагины")
        act_reload_plugins.triggered.connect(self._reload_plugins_from_tray)
        menu.addSeparator()
        act_quit = menu.addAction("Выход")
        act_quit.triggered.connect(self.quit_app)
        return menu

    def _tray_add_program(self):
        self.show_window()
        QTimer.singleShot(80, self.add_app)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_window()

    def _setup_hotkey(self):
        try:
            import keyboard
        except ImportError:
            log.warning("Библиотека keyboard не установлена")
            return
        if self.settings.get("hotkey_enabled", True):
            hotkey = self.settings.get("hotkey", "ctrl+alt+l")
            try:
                keyboard.add_hotkey(hotkey, lambda: self.hotkey_pressed.emit())
                self.hotkey_pressed.connect(self.toggle_window)
            except Exception as e:
                log.error(f"Hotkey error: {e}")
        if self.settings.get("quick_hotkey_enabled", True):
            qhotkey = self.settings.get("quick_hotkey", "ctrl+alt+space")
            try:
                keyboard.add_hotkey(
                    qhotkey, lambda: self.quick_hotkey_pressed.emit()
                )
                self.quick_hotkey_pressed.connect(self.show_quick)
            except Exception as e:
                log.error(f"Quick hotkey error: {e}")

    def _reload_hotkey(self):
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self._setup_hotkey()
        self._register_program_hotkeys()

    def _register_program_hotkeys(self):
        try:
            import keyboard
        except ImportError:
            return
        for path, handle in list(self._program_hotkeys.items()):
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._program_hotkeys = {}
        for app in self.apps:
            hk = (app.get("hotkey") or "").strip()
            if not hk:
                continue
            try:
                path = app.get("path", "")
                handle = keyboard.add_hotkey(
                    hk, lambda p=path: self._launch_by_path_from_hotkey(p)
                )
                self._program_hotkeys[path] = handle
            except Exception as e:
                log.error(f"hotkey '{hk}': {e}")

    def _launch_by_path_from_hotkey(self, path):
        for app in self.apps:
            if app.get("path") == path:
                self.show_window()
                self.launch_app(app)
                return

    def show_quick(self):
        if self.quick:
            self.quick.update_colors(self.colors)
            self.quick.popup()

    # ================= ТЕМА =================
    def toggle_theme(self):
        self._play_click_voice()
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.settings["theme"] = self.theme_name
        save_settings(self.settings)
        self.colors = get_theme(self.theme_name, self.accent)
        try:
            clear_fa_cache()
            icon_map.clear_cache()
        except Exception:
            pass
        try:
            if self.plugin_manager:
                ovr = self.plugin_manager.collect_theme_overrides(
                    self.theme_name, self.accent
                )
                if ovr:
                    self.colors.update(ovr)
        except Exception:
            pass
        self.set_tray_icon()
        self._apply_theme()
        self._refresh_icons()
        try:
            self.tray.setContextMenu(self._build_tray_menu())
        except Exception:
            pass
        if self.quick:
            self.quick.update_colors(self.colors)
        if getattr(self, "overlay", None):
            try:
                self.overlay.colors = self.colors
                self.overlay.apply_theme()
            except Exception:
                pass
        sounds.play("toggle")
        if self.system_monitor:
            self.system_monitor.apply_theme(self.colors)
        if self.animated_bg:
            self.animated_bg.update_colors(self.colors)
        if self.plugin_manager:
            try:
                self.plugin_manager.call_hook(
                    "on_theme_change", self.theme_name, self.accent
                )
            except Exception:
                pass
        self.render_cards()

    def _apply_theme(self):
        c = self.colors
        hide_scroll = self.settings.get("hide_scrollbar", False)
        sb_width = 0 if hide_scroll else 8

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {c['BG']}; }}
            QFrame#Sidebar {{
                background-color: {c['BG_ALT']};
                border-right: 1px solid {c['BORDER']};
            }}
            QFrame#RightSidebar {{
                background-color: {c['BG_ALT']};
                border-left: 1px solid {c['BORDER']};
            }}
            QFrame#SearchFrame {{
                background-color: {c['CARD']};
                border: 1px solid {c['BORDER']};
                border-radius: 12px;
            }}
            QFrame#SearchFrame:hover {{ border: 1px solid {c['BORDER_HOV']}; }}
            QLabel#SearchIcon {{
                color: {c['SUBTEXT']}; background: transparent;
            }}
        """)

        if getattr(self, "custom_titlebar", None):
            self.custom_titlebar.apply_theme(c)
            try:
                custom = self.settings.get("tray_icon", "")
                self.custom_titlebar.icon_label.setPixmap(
                    make_tray_icon(c, custom, self._app_name()).pixmap(22, 22)
                )
            except Exception:
                pass

        font_family = (
                              self.settings.get("title_font_family") or "Segoe UI"
                      ).strip() or "Segoe UI"
        self.title.setStyleSheet(
            f"color: {c['ACCENT']}; font-size: 26px; "
            f"font-family: '{font_family}'; "
            f"font-weight: 800; letter-spacing: 3px; "
            f"background: transparent;"
        )
        if self._title_glow is not None:
            self._title_glow.setColor(QColor(c["ACCENT"]))
        if hasattr(self, "clock_label"):
            self.clock_label.setStyleSheet(
                f"color: {c['TEXT']}; font-size: 22px; "
                f"font-weight: 600; background: transparent; "
                f"letter-spacing: 2px;"
            )
        self.popular_header.setStyleSheet(
            f"color: {c['ACCENT']}; font-size: 14px; "
            f"font-weight: 700; letter-spacing: 0.5px; "
            f"background: transparent;"
        )
        self.section_label.setStyleSheet(
            f"color: {c['TEXT']}; font-size: 15px; "
            f"font-weight: 700; letter-spacing: 0.5px; "
            f"background: transparent;"
        )
        self.running_header.setStyleSheet(
            f"color: {c['OK']}; font-size: 14px; "
            f"font-weight: 700; letter-spacing: 0.5px; "
            f"background: transparent;"
        )
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; color: {c['TEXT']};
                border: none; font-size: 13px; padding: 0;
            }}
        """)
        if hasattr(self, "subcat_combo"):
            self.subcat_combo.setStyleSheet(f"""
                QComboBox {{
                    background-color: {c['CARD']};
                    color: {c['TEXT']};
                    border: 1px solid {c['BORDER']};
                    border-radius: 12px;
                    padding: 6px 12px;
                    font-size: 13px;
                }}
                QComboBox:hover {{ border: 1px solid {c['ACCENT']}; }}
                QComboBox::drop-down {{ border: none; width: 24px; }}
                QComboBox QAbstractItemView {{
                    background-color: {c['CARD']};
                    color: {c['TEXT']};
                    border: 1px solid {c['BORDER']};
                    selection-background-color: {c['ACCENT_SOFT']};
                    selection-color: {c['ACCENT']};
                }}
            """)
        icon_btn_style = f"""
            QPushButton {{
                background-color: {c['CARD']}; color: {c['TEXT']};
                border: 1px solid {c['BORDER']};
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {c['CARD_HOVER']};
                border: 1px solid {c['ACCENT']};
            }}
            QPushButton:pressed {{ background-color: {c['ACCENT_SOFT']}; }}
        """
        icon_btn_active = f"""
            QPushButton {{
                background-color: {c['ACCENT']}; color: {c['BG']};
                border: 1px solid {c['ACCENT']};
                border-radius: 12px;
            }}
            QPushButton:hover {{ background-color: {c['ACCENT_HOV']}; }}
        """
        self.import_btn.setStyleSheet(icon_btn_style)
        self.settings_btn.setStyleSheet(icon_btn_style)
        if self.always_on_top:
            self.ontop_btn.setStyleSheet(icon_btn_active)
        else:
            self.ontop_btn.setStyleSheet(icon_btn_style)
        self.theme_btn.setStyleSheet(icon_btn_style)
        if hasattr(self, "mini_btn"):
            self.mini_btn.setStyleSheet(icon_btn_style)
        if hasattr(self, "compact_btn"):
            if self.compact_mode:
                self.compact_btn.setStyleSheet(icon_btn_active)
            else:
                self.compact_btn.setStyleSheet(icon_btn_style)

        if self._settings_badge is not None:
            try:
                self._settings_badge.setStyleSheet(
                    f"background-color: {c['DANGER']}; "
                    f"border-radius: 5px;"
                )
            except Exception:
                pass

        if hasattr(self, "shutdown_btn"):
            self.shutdown_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c['CARD']};
                    color: {c['DANGER']};
                    border: 1px solid {c['BORDER']};
                    border-radius: 12px;
                }}
                QPushButton:hover {{
                    background-color: {c['DANGER']};
                    color: {c['BG']};
                    border: 1px solid {c['DANGER']};
                }}
            """)

        self._style_sidebar_buttons()
        if hasattr(self, "category_fan"):
            self.category_fan.apply_theme(c, self.current_category)

        self.empty_label.setStyleSheet(
            f"color: {c['TEXT']}; font-size: 15px; font-weight: 600; "
            f"background: transparent; padding: 4px;"
        )
        self.empty_hint.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 12px; "
            f"background: transparent; padding: 2px;"
        )
        self.empty_btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['ACCENT']};
                color: {c['BG']};
                border: none;
                border-radius: 10px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background-color: {c['ACCENT_HOV']}; }}
        """)
        self.empty_btn_import.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['CARD']};
                color: {c['TEXT']};
                border: 1px solid {c['BORDER']};
                border-radius: 10px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {c['CARD_HOVER']};
                border: 1px solid {c['ACCENT']};
            }}
        """)
        self.empty_btn_preset.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['CARD']};
                color: {c['TEXT']};
                border: 1px solid {c['BORDER']};
                border-radius: 10px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {c['CARD_HOVER']};
                border: 1px solid {c['ACCENT']};
            }}
        """)
        if hasattr(self, "compact_empty"):
            self.compact_empty.setStyleSheet(
                f"color: {c['SUBTEXT']}; font-size: 13px; "
                f"padding: 24px; background: transparent;"
            )
        for service, btn in self._shortcut_btns.items():
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c['CARD']};
                    color: {c['TEXT']};
                    border: 1px solid {c['BORDER']};
                    border-radius: 12px;
                    padding: 0 20px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {c['CARD_HOVER']};
                    border: 1px solid {c['ACCENT']};
                    color: {c['ACCENT']};
                }}
                QPushButton:pressed {{
                    background-color: {c['ACCENT_SOFT']};
                }}
            """)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: {sb_width}px; margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c['BORDER_HOV']}; border-radius: 4px;
                min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {c['ACCENT']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self.scroll_content.setStyleSheet("background: transparent;")
        self.grid_widget.setStyleSheet("background: transparent;")
        self.running_grid_widget.setStyleSheet("background: transparent;")
        self.popular_widget.setStyleSheet("background: transparent;")
        self.empty_widget.setStyleSheet("background: transparent;")
        if hasattr(self, "compact_flow"):
            self.compact_flow.setStyleSheet("background: transparent;")
        if hasattr(self, "compact_widget"):
            self.compact_widget.setStyleSheet("background: transparent;")
        if self.mini_panel:
            self.mini_panel.setStyleSheet(f"""
                QFrame#MiniPanel {{
                    background-color: {c['BG_ALT']};
                    border-left: 1px solid {c['BORDER']};
                }}
            """)

        # Чипы категорий под поиском
        self._refresh_category_chips()

    def _style_sidebar_buttons(self):
        c = self.colors
        if hasattr(self, "main_category_btn"):
            self.main_category_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c['ACCENT']};
                    color: {c['BG']};
                    border: none;
                    border-radius: 12px;
                }}
                QPushButton:hover {{ background-color: {c['ACCENT_HOV']}; }}
            """)
            self._update_main_category_btn()
        if hasattr(self, "fav_btn"):
            if self._favorites_only:
                self.fav_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {c['ACCENT']};
                        color: {c['BG']};
                        border: none;
                        border-radius: 12px;
                    }}
                    QPushButton:hover {{ background-color: {c['ACCENT_HOV']}; }}
                """)
            else:
                self.fav_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {c['CARD']};
                        color: {c['TEXT']};
                        border: 1px solid {c['BORDER']};
                        border-radius: 12px;
                    }}
                    QPushButton:hover {{
                        background-color: {c['CARD_HOVER']};
                        border: 1px solid {c['ACCENT']};
                    }}
                """)
        if hasattr(self, "presets_btn"):
            self.presets_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c['ACCENT_SOFT']};
                    color: {c['TEXT']};
                    border: 1px solid {c['ACCENT']};
                    border-radius: 12px;
                }}
                QPushButton:hover {{ background-color: {c['ACCENT']}; }}
            """)
        if hasattr(self, "library_btn"):
            self.library_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c['ACCENT_SOFT']};
                    color: {c['TEXT']};
                    border: 1px solid {c['ACCENT']};
                    border-radius: 12px;
                }}
                QPushButton:hover {{
                    background-color: {c['ACCENT']};
                    color: {c['BG']};
                }}
            """)
        if hasattr(self, "add_btn"):
            self.add_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:0, y2:1,
                        stop:0 {c['ACCENT']},
                        stop:1 {c['ACCENT_HOV']}
                    );
                    color: {c['BG']};
                    border: none;
                    border-radius: 14px;
                }}
                QPushButton:hover {{ background-color: {c['ACCENT_HOV']}; }}
            """)
        if hasattr(self, "import_btn"):
            self.import_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c['CARD']};
                    color: {c['TEXT']};
                    border: 1px solid {c['BORDER']};
                    border-radius: 12px;
                }}
                QPushButton:hover {{
                    background-color: {c['CARD_HOVER']};
                    border: 1px solid {c['ACCENT']};
                }}
            """)

    def _style_menu(self, menu):
        c = self.colors
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {c['CARD']}; color: {c['TEXT']};
                border: 1px solid {c['BORDER_HOV']};
                border-radius: 12px; padding: 8px; font-size: 13px;
            }}
            QMenu::item {{ padding: 8px 22px; border-radius: 8px; }}
            QMenu::item:selected {{
                background-color: {c['ACCENT_SOFT']}; color: {c['ACCENT']};
            }}
            QMenu::separator {{
                height: 1px; background: {c['BORDER']}; margin: 4px 8px;
            }}
        """)

    def menu_style(self):
        c = self.colors
        return f"""
            QMenu {{
                background-color: {c['CARD']}; color: {c['TEXT']};
                border: 1px solid {c['BORDER_HOV']};
                border-radius: 12px; padding: 8px; font-size: 13px;
            }}
            QMenu::item {{ padding: 8px 22px; border-radius: 8px; }}
            QMenu::item:selected {{
                background-color: {c['ACCENT_SOFT']}; color: {c['ACCENT']};
            }}
            QMenu::separator {{
                height: 1px; background: {c['BORDER']}; margin: 4px 8px;
            }}
        """

    # ================= НАСТРОЙКИ =================
    def open_settings(self):
        self._play_click_voice()
        try:
            dlg = SettingsDialog(
                self, self.colors, self.settings,
                apps_provider=lambda: self.apps,
                apps_list=self.apps,
            )
        except Exception as e:
            log.error(f"Ошибка окна настроек: {e}\n{traceback.format_exc()}")
            show_error(self, self.colors, "Ошибка настроек", str(e))
            return
        try:
            result = dlg.exec()
        except Exception as e:
            log.error(f"Ошибка диалога настроек: {e}")
            show_error(self, self.colors, "Ошибка настроек", str(e))
            return
        if result != QDialog.DialogCode.Accepted:
            return
        new = dlg.result_settings()

        old_hotkey = self.settings.get("hotkey")
        old_quick = self.settings.get("quick_hotkey")
        old_theme = self.settings.get("theme")
        old_accent = self.settings.get("accent", "blue")
        old_ontop = self.settings.get("always_on_top", True)
        old_tray_icon = self.settings.get("tray_icon", "")
        old_app_name = self.settings.get("app_name", APP_NAME)
        old_material = self.settings.get("use_material_icons", True)
        old_bg_anim = self.settings.get("bg_animation_enabled", True)
        old_bg_type = self.settings.get("bg_type", "particles")
        old_bg_path = self.settings.get("bg_path", "")
        old_bg_opacity = self.settings.get("bg_opacity", 100)
        old_bg_muted = self.settings.get("bg_video_muted", True)
        old_auto_cover = self.settings.get("auto_cover_enabled", True)
        old_tile_scale = self.settings.get("tile_scale", 100)
        old_icon_scale = self.settings.get("icon_scale", 100)
        old_autobackup = self.settings.get("autobackup_enabled", True)
        old_autobackup_int = self.settings.get(
            "autobackup_interval_minutes", 60
        )

        self.settings.update(new)
        save_settings(self.settings)
        active = self.settings.get("active_profile", "custom")
        self.settings = apply_profile(active, self.settings)
        self.settings.update({
            k: v for k, v in new.items()
            if k in ("app_name",
                     "bg_type", "bg_path", "bg_opacity", "bg_video_muted",
                     "hotkey", "quick_hotkey", "autostart", "silent_start",
                     "close_to_tray", "always_on_top", "start_view",
                     "cloud_folder", "active_profile",
                     "hotkey_enabled", "quick_hotkey_enabled",
                     "window_width", "window_height", "tray_icon",
                     "category_companions", "category_covers",
                     "subcategories", "use_material_icons",
                     "sound_enabled", "sound_volume", "sound_events",
                     "voice_enabled", "voice_volume", "voice_events",
                     "switch_to_window_on_running", "activate_after_launch",
                     "enabled_plugins",
                     "show_system_monitor", "system_monitor_interval",
                     "system_monitor_gpu",
                     "splash_enabled", "splash_duration",
                     "bg_animation_enabled", "bg_animation_particles",
                     "auto_cover_enabled", "native_notifications",
                     "compact_mode",
                     "discord_enabled", "discord_client_id",
                     "discord_large_image", "discord_large_text",
                     "discord_show_when_idle",
                     "steamgriddb_api_key", "steamgriddb_enabled",
                     "autobackup_enabled", "autobackup_interval_minutes",
                     "show_load_errors")
        })
        save_settings(self.settings)

        if self.settings.get("use_material_icons", True) != old_material:
            icon_map.USE_MDI = bool(
                self.settings.get("use_material_icons", True)
            )
            icon_map.clear_cache()

        if self.settings.get("auto_cover_enabled", True) != old_auto_cover:
            try:
                cover_generator.clear_cache()
            except Exception:
                pass

        sounds.init(
            enabled=self.settings.get("sound_enabled", True),
            volume=self.settings.get("sound_volume", 60),
            event_flags=self.settings.get("sound_events") or {},
        )
        sounds.set_voice_enabled(self.settings.get("voice_enabled", False))
        sounds.set_voice_volume(self.settings.get("voice_volume", 80))
        sounds.set_voice_flags(self.settings.get("voice_events") or {})
        try:
            sounds.reload_voice()
        except Exception:
            pass

        apply_tile_settings(self.settings)
        set_tile_scale(
            int(self.settings.get("tile_scale", 100)),
            int(self.settings.get("icon_scale", 100)),
        )
        try:
            clear_fa_cache()
        except Exception:
            pass
        if (new.get("tile_scale") != old_tile_scale
                or new.get("icon_scale") != old_icon_scale):
            try:
                cover_generator.clear_cache()
            except Exception:
                pass

        if (self.settings.get("autobackup_enabled", True) != old_autobackup
                or self.settings.get(
                    "autobackup_interval_minutes", 60
                ) != old_autobackup_int):
            try:
                self._autobackup_timer.stop()
            except Exception:
                pass
            if self.settings.get("autobackup_enabled", True):
                try:
                    iv = int(self.settings.get(
                        "autobackup_interval_minutes", 60
                    ))
                except Exception:
                    iv = 60
                iv = max(5, iv)
                self._autobackup_timer.start(iv * 60 * 1000)

        pending = dlg.pending_import()
        if pending is not None:
            self.apps = pending
            save_apps(self.apps)
            self._register_program_hotkeys()
            QTimer.singleShot(500, self._check_updates_for_apps)

        try:
            pending_presets = dlg.pending_presets()
        except Exception:
            pending_presets = None
        if pending_presets is not None:
            self.presets = pending_presets
            save_presets(self.presets)

        theme_changed = (
                new.get("theme") != old_theme
                or new.get("accent", "blue") != old_accent
        )
        if theme_changed:
            self.theme_name = new.get("theme", self.theme_name)
            self.accent = new.get("accent", self.accent)
            self.colors = get_theme(self.theme_name, self.accent)
            try:
                if self.plugin_manager:
                    ovr = self.plugin_manager.collect_theme_overrides(
                        self.theme_name, self.accent
                    )
                    if ovr:
                        self.colors.update(ovr)
            except Exception:
                pass
            try:
                clear_fa_cache()
                icon_map.clear_cache()
            except Exception:
                pass
            if self.quick:
                self.quick.update_colors(self.colors)
            if getattr(self, "overlay", None):
                try:
                    self.overlay.colors = self.colors
                    self.overlay.apply_theme()
                except Exception:
                    pass

        if (new.get("hotkey") != old_hotkey
                or new.get("quick_hotkey") != old_quick):
            self._reload_hotkey()

        if new.get("always_on_top", True) != old_ontop:
            self.always_on_top = bool(new.get("always_on_top", True))
            set_always_on_top_native(self, self.always_on_top)

        if new.get("tray_icon", "") != old_tray_icon:
            self.set_tray_icon()

        if new.get("app_name", old_app_name) != old_app_name:
            self._apply_app_name()

        if hasattr(self, "category_fan"):
            self.category_fan.update_speed(
                self.settings.get("animation_speed", 100)
            )

        new_bg_anim = self.settings.get("bg_animation_enabled", True)
        new_bg_type = self.settings.get("bg_type", "particles")
        new_bg_path = self.settings.get("bg_path", "")
        new_bg_opacity = self.settings.get("bg_opacity", 100)
        new_bg_muted = self.settings.get("bg_video_muted", True)
        self._apply_bg_animation_visibility()
        self._apply_window_opacity()
        if self.animated_bg:
            try:
                self.animated_bg.update_colors(self.colors)
            except Exception:
                pass

        self._apply_ui_visibility()
        self._apply_monitor_visibility()
        self._apply_theme()
        self._refresh_icons()
        try:
            self.tray.setContextMenu(self._build_tray_menu())
        except Exception:
            pass
        self._rebuild_subcat_combo()
        self.render_cards()

        sounds.play("success")
        sounds.play_voice("success")

        if getattr(self, "discord_rpc", None) is not None:
            try:
                self.discord_rpc.apply_settings(self.settings)
            except Exception as e:
                log.error(f"discord_rpc apply_settings: {e}")

        if self.plugin_manager:
            try:
                self.plugin_manager.settings = self.settings
                self.plugin_manager.sync_with_settings()
                self.plugin_manager.call_hook(
                    "on_settings_saved", self.settings
                )
            except Exception as e:
                log.error(f"plugin sync after settings: {e}")

    def _apply_ui_visibility(self):
        if hasattr(self, "clock_label"):
            self.clock_label.setVisible(self.settings.get("show_clock", True))
        if hasattr(self, "search_row_widget"):
            self.search_row_widget.setVisible(
                self.settings.get("show_search", True)
            )
        if hasattr(self, "cats_row_widget"):
            self.cats_row_widget.setVisible(
                self.settings.get("show_search", True)
            )
        # section_label скрыт — не показываем (дублирует чипы категорий)
        if hasattr(self, "popular_header"):
            self.popular_header.setVisible(
                self.settings.get("show_section_headers", True)
                and not self.compact_mode
                and bool(self._popular_tiles)
            )
        if hasattr(self, "scroll"):
            if self.settings.get("hide_scrollbar", False):
                self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            else:
                self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def _apply_monitor_visibility(self):
        if self.system_monitor is None:
            return
        show = bool(self.settings.get("show_system_monitor", True))
        self.system_monitor.setVisible(show)
        try:
            interval = int(self.settings.get("system_monitor_interval", 2))
            self.system_monitor.set_interval(interval)
        except Exception:
            pass

    def _apply_bg_animation_visibility(self):
        if self.animated_bg is None:
            return
        try:
            self.animated_bg.apply_settings(self.settings)
        except Exception as e:
            log.error(f"_apply_bg_animation_visibility: {e}")

    # ================= DRAG & DROP =================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.isfile(path):
                self._add_app_by_path(path)

    # ================= КЛАВИАТУРА =================
    def eventFilter(self, obj, event):
        et = event.type()

        if self._resize_state is not None:
            if et == QEvent.MouseMove:
                self._do_manual_resize(event)
                return True
            if et == QEvent.MouseButtonRelease:
                self._end_manual_resize()
                return True
            if et == QEvent.MouseButtonPress:
                return True

        if et == QEvent.MouseMove and self.isVisible():
            self._handle_qt_resize_hover(obj, event)
        elif et == QEvent.HoverMove and self.isVisible():
            self._handle_qt_resize_hover(obj, event)
        elif et == QEvent.MouseButtonPress:
            if self._handle_qt_resize_press(obj, event):
                return True

        if et == QEvent.KeyPress:
            if event.key() == Qt.Key_F11:
                self.toggle_fullscreen()
                return True
            if (event.key() == Qt.Key_M
                    and event.modifiers() & Qt.ControlModifier):
                self.toggle_mini_mode()
                return True
            if event.key() == Qt.Key_Escape and self.isFullScreen():
                self.showNormal()
                if self.custom_titlebar:
                    self.custom_titlebar._refresh_icons()
                return True

            mods = event.modifiers()

            if (event.key() == Qt.Key_C
                    and mods & Qt.ControlModifier
                    and mods & Qt.ShiftModifier):
                self.toggle_compact_mode()
                return True

            if (event.key() == Qt.Key_Z
                    and mods & Qt.ControlModifier
                    and mods & Qt.ShiftModifier):
                try:
                    import plugin_manager as pm_mod
                    os.makedirs(pm_mod.PLUGINS_DIR, exist_ok=True)
                    os.startfile(pm_mod.PLUGINS_DIR)
                    self._show_toast("Плагины", pm_mod.PLUGINS_DIR, "info")
                except Exception as e:
                    log.error(f"open plugins folder: {e}")
                return True

            if (event.key() == Qt.Key_Y
                    and mods & Qt.ControlModifier
                    and mods & Qt.ShiftModifier):
                try:
                    from storage import BACKUP_DIR
                    os.makedirs(BACKUP_DIR, exist_ok=True)
                    os.startfile(BACKUP_DIR)
                    self._show_toast("Бэкапы", BACKUP_DIR, "info")
                except Exception as e:
                    log.error(f"open backups folder: {e}")
                return True

            if event.key() == Qt.Key_F5:
                self._play_click_voice()
                self._refresh_statuses()
                self._show_toast(
                    "Обновлено", "Статусы программ проверены", "info"
                )
                return True

            if (event.key() == Qt.Key_R and mods & Qt.ControlModifier):
                self._play_click_voice()
                self._reload_apps_from_disk()
                return True

            if ((event.key() == Qt.Key_F or event.key() == Qt.Key_K)
                    and mods & Qt.ControlModifier):
                try:
                    self.search.setFocus()
                    self.search.selectAll()
                except Exception:
                    pass
                return True

            if (event.key() == Qt.Key_T and mods & Qt.ControlModifier):
                self.toggle_theme()
                return True

            if (event.key() == Qt.Key_V and mods & Qt.ControlModifier):
                focused = QApplication.focusWidget()
                if not isinstance(focused, QLineEdit):
                    self._paste_from_clipboard()
                    return True

            key = event.key()
            if (Qt.Key_1 <= key <= Qt.Key_9
                    and not (mods & (Qt.ControlModifier
                                     | Qt.AltModifier
                                     | Qt.ShiftModifier))):
                self._quick_launch_by_index(key - Qt.Key_1)
                return True

            focused = QApplication.focusWidget()
            if isinstance(focused, QLineEdit):
                if event.key() == Qt.Key_Escape:
                    focused.clear()
                    return True
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    if self.search.text().strip():
                        self._open_web_search("google")
                        return True
                return super().eventFilter(obj, event)
            if event.key() == Qt.Key_Slash:
                self.search.setFocus()
                return True

        return super().eventFilter(obj, event)

    def _quick_launch_by_index(self, idx):
        """Порядок совпадает с визуальным: running → preset → другие."""
        try:
            if hasattr(self, "grid_layout") and hasattr(self, "running_grid"):
                ordered = []
                # Сначала секция «Запущено» — row-major
                if self.running_grid_widget.isVisible():
                    for i in range(self.running_grid.count()):
                        it = self.running_grid.itemAt(i)
                        w = it.widget() if it else None
                        if w is not None and w.isVisible():
                            ordered.append(w)
                # Потом основная сетка
                for i in range(self.grid_layout.count()):
                    it = self.grid_layout.itemAt(i)
                    w = it.widget() if it else None
                    if w is not None and w.isVisible():
                        ordered.append(w)
            else:
                ordered = [c for c in self.cards if c.isVisible()]
        except Exception:
            return

        if idx < 0 or idx >= len(ordered):
            return

        tile = ordered[idx]
        app = getattr(tile, "app", None)
        if app is None:
            # Это может быть PresetTile — у него .preset, не .app
            preset = getattr(tile, "preset", None)
            if preset:
                self._launch_preset(preset)
            return

        try:
            from PySide6.QtCore import QPointF
            tile._start_ripple(
                QPointF(tile.width() / 2, tile.height() / 2)
            )
        except Exception:
            pass
        self.launch_app(app)

    # ================= БУФЕР =================
    def _reload_apps_from_disk(self):
        try:
            self.apps = load_apps()
            self._register_program_hotkeys()
            self.render_cards()
            self._show_toast(
                "Перечитано",
                f"Загружено программ: {len(self.apps)}",
                "info",
            )
        except Exception as e:
            log.error(f"reload_apps_from_disk: {e}")
            self._show_toast("Ошибка", str(e), "error")

    def _paste_from_clipboard(self):
        try:
            cb = QApplication.clipboard()
            text = (cb.text() or "").strip()
        except Exception:
            text = ""
        if not text:
            self._show_toast(
                "Буфер пуст",
                "Скопируй путь к .exe или .lnk и повтори",
                "warning",
            )
            return
        paths = [
            line.strip().strip('"')
            for line in text.splitlines()
            if line.strip()
        ]
        added = 0
        skipped = 0
        existing = {a.get("path", "") for a in self.apps}
        for path in paths:
            if not path or path in existing:
                skipped += 1
                continue
            if self._find_app_by_path(path):
                skipped += 1
                continue
            if not os.path.exists(path):
                skipped += 1
                continue
            try:
                self._add_app_by_path_silent(path)
                existing.add(path)
                added += 1
            except Exception as e:
                log.error(f"paste: {e}")
                skipped += 1
        if added:
            save_apps(self.apps)
            self.render_cards()
            QTimer.singleShot(500, self._check_updates_for_apps)
            msg = f"Добавлено: {added}"
            if skipped:
                msg += f"\nПропущено: {skipped}"
            self._show_toast("Вставлено из буфера", msg, "success")
            sounds.play("success")
            sounds.play_voice("success")
        else:
            self._show_toast(
                "Ничего не добавлено",
                "В буфере нет валидных путей к файлам",
                "warning",
            )

    def _add_app_by_path_silent(self, path):
        name = os.path.splitext(os.path.basename(path))[0]
        max_order = max((a.get("order", 0) for a in self.apps), default=-1)
        cat = self.current_category
        if cat in ("all", "recent"):
            cat = "other"
        self.apps.append({
            "name": name, "path": path, "favorite": False,
            "launch_count": 0, "category": cat,
            "subcategory": "",
            "custom_icon": "", "custom_cover": "",
            "order": max_order + 1, "hotkey": "",
            "companions": [], "note": "",
            "known_version": "",
        })

    # ================= ЗАПУСК =================
    def launch_app(self, app):
        self._play_click_voice()
        path = app.get("path", "")
        name = app.get("name", "")
        if is_process_running(path):
            if self.settings.get("switch_to_window_on_running", False):
                if window_activation.activate_app_window(path):
                    return
            choice = ask_already_running(
                self, self.colors, name,
                allow_switch=window_activation.has_support(),
            )
            if choice == "cancel":
                return
            if choice == "switch":
                window_activation.activate_app_window(path)
                return
            if choice == "close":
                self._close_running(app)
                return
            if choice == "rerun":
                self._close_running(app, then_launch=True)
                return
            return
        self._do_launch(app)

    def _close_running(self, app, then_launch=False):
        kill_process(app.get("path", ""))
        sounds.play("close")
        sounds.play_voice("close")
        try:
            self._started_by_us.discard(app.get("path", ""))
        except Exception:
            pass
        if self.plugin_manager:
            try:
                self.plugin_manager.call_hook("on_app_close", app)
            except Exception:
                pass
        if getattr(self, "discord_rpc", None) is not None:
            try:
                self.discord_rpc.on_app_close(app)
            except Exception:
                pass
        if then_launch:
            QTimer.singleShot(700, lambda: self._do_launch(app))
        else:
            QTimer.singleShot(300, self.render_cards)

    def _do_launch(self, app):
        path = app.get("path", "")
        name = app.get("name", "")

        if self.plugin_manager:
            try:
                results = self.plugin_manager.call_hook(
                    "on_app_launch_pre", app
                )
                if any(r is False for r in results):
                    self._show_toast(
                        "Запуск отменён",
                        f"Плагин запретил запуск «{name}»",
                        "info",
                    )
                    return
            except Exception as e:
                log.error(f"on_app_launch_pre: {e}")

        result = launch(app)
        if not result.ok:
            self._show_toast("Не удалось запустить", result.error, "error")
            return

        sounds.play("launch")
        sounds.play_voice("launch")

        for a in self.apps:
            if a == app:
                a["launch_count"] = a.get("launch_count", 0) + 1
                break
        save_apps(self.apps)

        try:
            self._started_by_us.add(path)
        except Exception:
            pass

        self._flash_tray_icon()

        recents = self.settings.get("recent_paths", [])
        if path in recents:
            recents.remove(path)
        recents.insert(0, path)
        self.settings["recent_paths"] = recents[:15]
        save_settings(self.settings)

        try:
            self.tray.setContextMenu(self._build_tray_menu())
        except Exception:
            pass

        if self.settings.get("overlay_enabled", True) and self.overlay:
            try:
                pix = get_icon(app, 42)
                self.overlay.colors = self.colors
                self.overlay.apply_theme()
                self.overlay.show_app(name, pix)
            except Exception as e:
                log.error(f"overlay show error: {e}")

        if self.settings.get("companions_enabled", True):
            self._launch_companions(app)
            self._launch_category_companions(app)

        self.launching_paths.add(path)
        self.render_cards()
        QTimer.singleShot(2000, lambda p=path: self._clear_launching(p))

        if self.plugin_manager:
            try:
                self.plugin_manager.call_hook("on_app_launch", app)
            except Exception:
                pass

        discord_cover_url = ""
        if getattr(self, "discord_rpc", None) is not None:
            try:
                discord_cover_url = self._get_discord_cover_url(app)
                self.discord_rpc.on_app_launch(
                    app, cover_url=discord_cover_url
                )
            except Exception as e:
                log.error(f"discord_rpc on_app_launch: {e}")

        if (not discord_cover_url
                and getattr(self, "discord_rpc", None) is not None
                and self.discord_rpc.is_connected()):
            QTimer.singleShot(
                1500, lambda a=app: self._async_discord_cover(a)
            )

        if self.settings.get("activate_after_launch", False):
            QTimer.singleShot(
                2500,
                lambda p=path: window_activation.activate_app_window(p),
            )

    def _launch_companions(self, app):
        companions = app.get("companions", []) or []
        if not companions:
            return
        any_launched = False
        for cpath in companions:
            if not cpath or cpath == app.get("path"):
                continue
            if is_process_running(cpath):
                continue
            target = next(
                (a for a in self.apps if a.get("path") == cpath), None
            )
            launch_app_dict = target if target else {
                "name": os.path.splitext(os.path.basename(cpath))[0],
                "path": cpath, "custom_icon": "",
            }
            r = launch(launch_app_dict)
            if r.ok:
                if target:
                    target["launch_count"] = (
                        target.get("launch_count", 0) + 1
                    )
                any_launched = True
        save_apps(self.apps)
        if any_launched:
            QTimer.singleShot(400, self.render_cards)

    def _launch_category_companions(self, app):
        cat = app.get("category") or "other"
        cc = self.settings.get("category_companions", {}) or {}
        companions = cc.get(cat, []) or []
        if not companions:
            return
        any_launched = False
        for cpath in companions:
            if not cpath or cpath == app.get("path"):
                continue
            if is_process_running(cpath):
                continue
            target = next(
                (a for a in self.apps if a.get("path") == cpath), None
            )
            launch_app_dict = target if target else {
                "name": os.path.splitext(os.path.basename(cpath))[0],
                "path": cpath, "custom_icon": "",
            }
            r = launch(launch_app_dict)
            if r.ok:
                if target:
                    target["launch_count"] = (
                        target.get("launch_count", 0) + 1
                    )
                any_launched = True
        save_apps(self.apps)
        if any_launched:
            QTimer.singleShot(400, self.render_cards)

    def _clear_launching(self, path):
        self.launching_paths.discard(path)
        self.render_cards()

    # ================= DISCORD URL =================
    def _get_discord_cover_url(self, app):
        try:
            if app.get("source") == "steam" and app.get("appid"):
                return (
                    f"https://cdn.cloudflare.steamstatic.com/"
                    f"steam/apps/{app['appid']}/header.jpg"
                )
            if cover_fetcher is not None:
                url = cover_fetcher.get_url_cache_for_game(app)
                if url:
                    return url
            custom = (app.get("custom_cover") or "").strip()
            if custom.startswith("http://") or custom.startswith("https://"):
                return custom
        except Exception as e:
            log.error(f"_get_discord_cover_url: {e}")
        return ""

    def _async_discord_cover(self, app):
        rpc = getattr(self, "discord_rpc", None)
        if rpc is None or not rpc.is_connected():
            return
        if cover_fetcher is None:
            return
        api_key = ""
        try:
            settings = load_settings()
            api_key = (settings.get("steamgriddb_api_key") or "").strip()
            sgdb_enabled = bool(settings.get("steamgriddb_enabled", True))
        except Exception:
            return
        if not api_key or not sgdb_enabled:
            return
        cur = rpc._current_session
        if not cur or cur.get("path") != app.get("path"):
            return
        try:
            url = ""
            if app.get("source") == "steam" and app.get("appid"):
                url = cover_fetcher.fetch_cover_url_by_steam_appid(
                    app["appid"], api_key
                )
            if not url:
                url = cover_fetcher.fetch_cover_url_by_name(
                    app.get("name", ""), api_key
                )
            if url:
                cover_fetcher.cache_url_for_game(app, url)
                rpc.update_cover(url)
        except Exception as e:
            log.error(f"_async_discord_cover: {e}")

    # ================= JARVIS =================
    def show_materialize(self):
        if getattr(self, "_materialize_done", False):
            self.show_window()
            return
        self._materialize_done = True
        # Целевая прозрачность — пользовательская настройка
        try:
            user_opacity = max(
                60, min(100, int(self.settings.get("window_opacity", 100)))
            ) / 100.0
        except Exception:
            user_opacity = 1.0

        # Целевая прозрачность — пользовательская настройка
        try:
            user_opacity = max(
                60, min(100, int(self.settings.get("window_opacity", 100)))
            ) / 100.0
        except Exception:
            user_opacity = 1.0

        try:
            self.setWindowOpacity(0.0)
        except Exception:
            pass

        self.show()

        try:
            self._window_fade = QPropertyAnimation(
                self, b"windowOpacity", self
            )
            self._window_fade.setDuration(600)
            self._window_fade.setStartValue(0.0)
            self._window_fade.setEndValue(user_opacity)
            self._window_fade.setEasingCurve(QEasingCurve.OutCubic)
            self._window_fade.start()
        except Exception:
            pass
        try:
            if self._scan_overlay is None:
                self._scan_overlay = ScanLineOverlay(
                    self, QColor(self.colors["ACCENT"])
                )
            self._scan_overlay.color = QColor(self.colors["ACCENT"])
            QTimer.singleShot(80, lambda: self._scan_overlay.run(1400))
        except Exception as e:
            log.error(f"show_materialize scan: {e}")
        self._schedule_section_fades()
        self._play_startup_effects()
        QTimer.singleShot(200, self._enable_mouse_tracking_recursive)
        QTimer.singleShot(3000, self._play_systems_ready_voice)

    def _schedule_section_fades(self):
        plan = [
            (getattr(self, "sidebar", None),          200, 500),
            (getattr(self, "search_row_widget", None), 450, 350),
            (getattr(self, "right_sidebar", None),    700, 450),
            (getattr(self, "scroll", None),           950, 600),
        ]
        for w, delay, dur in plan:
            if w is None:
                continue
            QTimer.singleShot(
                delay, lambda ww=w, dd=dur: self._fade_in(ww, dd)
            )
        QTimer.singleShot(1300, self._animate_card_appearance)

    def _fade_in(self, widget, duration=350):
        if widget is None:
            return
        try:
            eff = QGraphicsOpacityEffect(widget)
            eff.setOpacity(0.0)
            widget.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", widget)
            anim.setDuration(int(duration))
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)

            def _cleanup(w=widget):
                try:
                    w.setGraphicsEffect(None)
                except Exception:
                    pass

            anim.finished.connect(_cleanup)
            anim.start()
            widget._fade_anim = anim
        except Exception as e:
            log.error(f"_fade_in: {e}")

    def _play_startup_effects(self):
        QTimer.singleShot(700, self._start_title_typewriter)
        QTimer.singleShot(2100, self._start_title_glow_pulse)
        QTimer.singleShot(400, self._cascade_sidebar_buttons)

    def _start_title_typewriter(self):
        try:
            if not hasattr(self, "title") or self.title is None:
                return
            full = self._app_name().upper()
            self.title.setText("")
            self._tw_full = full
            self._tw_idx = 0
            if self._tw_timer is not None:
                try:
                    self._tw_timer.stop()
                except Exception:
                    pass
            self._tw_timer = QTimer(self)
            self._tw_timer.timeout.connect(self._tw_step)
            self._tw_timer.start(45)
        except Exception as e:
            log.error(f"typewriter: {e}")

    def _tw_step(self):
        try:
            if self._tw_idx >= len(self._tw_full):
                if self._tw_timer is not None:
                    self._tw_timer.stop()
                return
            self._tw_idx += 1
            self.title.setText(self._tw_full[:self._tw_idx])
        except Exception:
            try:
                if self._tw_timer is not None:
                    self._tw_timer.stop()
            except Exception:
                pass

    def _start_title_glow_pulse(self):
        try:
            if self._title_glow is None:
                return
            self._glow_pulse = QPropertyAnimation(
                self._title_glow, b"blurRadius", self
            )
            self._glow_pulse.setDuration(2400)
            self._glow_pulse.setStartValue(24)
            self._glow_pulse.setKeyValueAt(0.5, 48)
            self._glow_pulse.setEndValue(24)
            self._glow_pulse.setLoopCount(-1)
            self._glow_pulse.setEasingCurve(QEasingCurve.InOutSine)
            self._glow_pulse.start()
        except Exception as e:
            log.error(f"glow pulse: {e}")

    def _cascade_sidebar_buttons(self):
        try:
            btns = [
                getattr(self, "main_category_btn", None),
                getattr(self, "fav_btn", None),
                getattr(self, "presets_btn", None),
                getattr(self, "library_btn", None),
                getattr(self, "import_btn", None),
                getattr(self, "add_btn", None),
            ]
            for i, b in enumerate(btns):
                if b is None:
                    continue
                QTimer.singleShot(i * 90, lambda bb=b: self._flash_button(bb))
        except Exception as e:
            log.error(f"cascade sidebar: {e}")

    def _flash_button(self, btn):
        try:
            w0 = btn.width()
            h0 = btn.height()
            btn.setFixedSize(int(w0 * 1.22), int(h0 * 1.22))
            QTimer.singleShot(130, lambda: btn.setFixedSize(w0, h0))
        except Exception:
            pass

    def _play_systems_ready_voice(self):
        try:
            if not self.settings.get("voice_enabled", False):
                return
            flags = self.settings.get("voice_events") or {}
            if not flags.get("ready", True):
                return
            sounds.play_voice("ready")
        except Exception as e:
            log.error(f"_play_systems_ready_voice: {e}")

    # ================= ОКНО / ТРЕЙ =================
    def toggle_window(self):
        self._play_click_voice()
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def confirm_shutdown_launcher(self):
        self._play_click_voice()
        try:
            ok = ask_confirm(
                self, self.colors,
                "Выключить лаунчер",
                "Закрыть лаунчер?\n\n"
                "Все запущенные программы останутся работать.",
                ok_text="Выключить",
            )
        except Exception as e:
            log.error(f"confirm_shutdown_launcher: {e}")
            return
        if not ok:
            return
        self.settings["close_to_tray"] = False
        self.close()

    def quit_app(self):
        log.info("quit_app")
        if self._shutting_down:
            return
        try:
            import custom_tooltip
            custom_tooltip.cleanup()
        except Exception:
            pass
        try:
            _app = QApplication.instance()
            if _app is not None:
                _app.removeEventFilter(self)
        except Exception:
            pass
        try:
            if self.system_monitor:
                self.system_monitor.stop()
        except Exception:
            pass
        try:
            import sysmonitor as _sysmon
            _sysmon.shutdown_nvml()
        except Exception:
            pass
        try:
            if self.animated_bg:
                self.animated_bg.set_enabled(False)
        except Exception:
            pass
        if getattr(self, "discord_rpc", None) is not None:
            try:
                self.discord_rpc.stop()
            except Exception:
                pass
        if self.plugin_manager:
            try:
                self.plugin_manager.call_hook("on_shutdown")
            except Exception:
                pass
            for name in list(self.plugin_manager.plugins.keys()):
                self.plugin_manager.unload(name)
        try:
            if hasattr(self, "_updates_timer"):
                self._updates_timer.stop()
        except Exception:
            pass
        try:
            if self.isMaximized():
                self.settings["window_maximized"] = True
            else:
                self.settings["window_maximized"] = False
                self.settings["window_height"] = self.height()
                self.settings["window_width"] = self.width()
                self.settings["window_x"] = self.x()
                self.settings["window_y"] = self.y()
            save_settings(self.settings)
        except Exception:
            pass
        try:
            self._tick_stats()
        except Exception:
            pass
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            if self.tray:
                self.tray.hide()
        except Exception:
            pass
        self._fade_out_and_close()

    def _fade_out_and_close(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self.setEnabled(False)
        except Exception:
            pass
        try:
            overlay = QWidget(self)
            overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
            overlay.setStyleSheet("background-color: #000000;")
            overlay.setGeometry(0, 0, self.width(), self.height())
            overlay.show()
            overlay.raise_()
            eff = QGraphicsOpacityEffect(overlay)
            eff.setOpacity(0.0)
            overlay.setGraphicsEffect(eff)
            self._shutdown_overlay = overlay
            dim = QPropertyAnimation(eff, b"opacity", self)
            dim.setDuration(900)
            dim.setStartValue(0.0)
            dim.setEndValue(0.85)
            dim.setEasingCurve(QEasingCurve.OutCubic)
            dim.start()
            self._shutdown_dim = dim
        except Exception as e:
            log.error(f"shutdown overlay: {e}")
        try:
            sounds.play_voice("shutdown")
        except Exception:
            pass
        QTimer.singleShot(1000, self._fade_window_out)
        QTimer.singleShot(3200, self._final_quit)

    def _fade_window_out(self):
        try:
            fade = QPropertyAnimation(self, b"windowOpacity", self)
            fade.setDuration(1200)
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)
            fade.setEasingCurve(QEasingCurve.InCubic)
            fade.start()
            self._shutdown_fade = fade
        except Exception as e:
            log.error(f"_fade_window_out: {e}")

    def _final_quit(self):
        try:
            QApplication.quit()
        except Exception:
            pass
        os._exit(0)

    def hide_to_tray(self):
        try:
            self.hide()
        except Exception as e:
            log.error(f"hide_to_tray error: {e}")

    def closeEvent(self, event):
        if self._shutting_down:
            event.accept()
            return
        close_to_tray = self.settings.get("close_to_tray", True)
        tray_available = False
        try:
            tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        except Exception:
            pass
        if close_to_tray and tray_available:
            event.ignore()
            self.hide_to_tray()
        else:
            event.ignore()
            self.quit_app()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._first_shown:
            self._first_shown = True
            QTimer.singleShot(50, lambda: set_always_on_top_native(
                self, self.always_on_top
            ))
            QTimer.singleShot(80, lambda: set_rounded_corners(self))
            QTimer.singleShot(120, self._refresh_icons)
            QTimer.singleShot(30, self._apply_start_view)
        QTimer.singleShot(50, self._relayout_grid)
        QTimer.singleShot(100, self._enable_mouse_tracking_recursive)

    def _apply_start_view(self):
        view = self.settings.get("start_view", "normal")
        try:
            if view == "maximized":
                self.showMaximized()
            elif (self.settings.get("window_maximized", False)
                    and view == "normal"):
                self.showMaximized()
            elif view == "fullscreen":
                self.showFullScreen()
                if self.custom_titlebar:
                    QTimer.singleShot(50, self.custom_titlebar._refresh_icons)
            elif view == "tray":
                self.hide()
        except Exception as e:
            log.error(f"_apply_start_view: {e}")