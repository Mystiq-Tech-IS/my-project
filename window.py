"""Главное окно: Epic-стиль + FA + тосты + профили + тонкие настройки."""

import os
import sys
import ctypes
import traceback
from datetime import datetime
from urllib.parse import quote
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QFrame, QScrollArea,
    QMenu, QSystemTrayIcon, QApplication, QDialog, QComboBox,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QSize
)
from PySide6.QtGui import (
    QCursor, QAction, QIcon, QPixmap, QPainter, QColor, QFont, QKeyEvent,
    QDesktopServices
)

try:
    import qtawesome as qta
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
    load_presets, save_presets, log,
)
from profiles import apply_profile, all_profiles
from stats import load_stats, save_stats, add_time
from launcher import launch
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


# ================= НАТИВНЫЕ ФУНКЦИИ WINDOWS =================
SWP_NOSIZE       = 0x0001
SWP_NOMOVE       = 0x0002
SWP_NOACTIVATE   = 0x0010

HWND_TOPMOST     = -1
HWND_NOTOPMOST   = -2

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


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


def make_tray_icon(colors, custom_path=""):
    if custom_path and os.path.exists(custom_path):
        try:
            pix = QPixmap(custom_path)
            if not pix.isNull():
                return QIcon(pix)
        except Exception:
            pass

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
    p.drawText(pix.rect(), Qt.AlignCenter, "Л")
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


# ================= АКТИВНЫЙ МОНИТОР =================
def get_active_monitor_geometry():
    """
    Возвращает QRect активного монитора (где курсор).
    Использует WinAPI — без зависимостей.
    Fallback на primaryScreen при ошибке.
    """
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
        if ctypes.windll.user32.GetMonitorInfoW(
            hmon, ctypes.byref(mi)
        ):
            l, t, r, b = mi.rcWork
            return QRect(l, t, r - l, b - t)
    except Exception as e:
        log.error(f"get_active_monitor_geometry: {e}")

    try:
        return QApplication.primaryScreen().availableGeometry()
    except Exception:
        from PySide6.QtCore import QRect
        return QRect(0, 0, 1920, 1080)


try:
    from screeninfo import get_monitors as _si_get_monitors
    HAS_SCREENINFO = True
except ImportError:
    HAS_SCREENINFO = False
    _si_get_monitors = None


# ================= ТАЙТЛБАР =================
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
            self.icon_label.setPixmap(
                make_tray_icon(colors).pixmap(22, 22)
            )
        except Exception:
            pass
        layout.addWidget(self.icon_label)

        self.title_label = QLabel(APP_NAME)
        layout.addWidget(self.title_label)

        self.sep1 = QLabel("·")
        layout.addWidget(self.sep1)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.min_btn = QPushButton()
        self.min_btn.setFixedSize(32, 32)
        self.min_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.min_btn.setToolTip("Свернуть")
        self.min_btn.clicked.connect(launcher.showMinimized)

        self.max_btn = QPushButton()
        self.max_btn.setFixedSize(32, 32)
        self.max_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.max_btn.setToolTip("Развернуть")
        self.max_btn.clicked.connect(self._toggle_max)

        self.full_btn = QPushButton()
        self.full_btn.setFixedSize(32, 32)
        self.full_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.full_btn.setToolTip("Полный экран (F11)")
        self.full_btn.clicked.connect(launcher.toggle_fullscreen)

        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setCursor(QCursor(Qt.PointingHandCursor))
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
            self.icon_label.setPixmap(
                make_tray_icon(c, custom).pixmap(22, 22)
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

            is_full = self.launcher.isFullScreen()
            if is_full:
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


# ================= ВЕЕР КАТЕГОРИЙ =================
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
            btn.setCursor(QCursor(Qt.PointingHandCursor))
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

    def update_speed(self, percent):
        base = 300
        factor = 100.0 / max(50, min(200, percent))
        dur = int(base * factor)
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
        try:
            self._anim_h.finished.disconnect()
        except Exception:
            pass
        self._anim_h.finished.connect(self._after_close)
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


# ================= ПРЕСЕТ-ПЛИТКА =================
class PresetTile(QFrame):
    clicked          = Signal(dict)
    edit_requested   = Signal(dict)
    delete_requested = Signal(dict)
    launch_requested = Signal(dict)

    def __init__(self, preset, colors, menu_style=""):
        super().__init__()
        self.preset = preset
        self.colors = colors
        self.menu_style = menu_style
        self.setFixedSize(tile_card.TILE_WIDTH, tile_card.TILE_HEIGHT)
        self.setCursor(QCursor(Qt.PointingHandCursor))
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

        backup_apps()

        raw_settings = load_settings()
        active = raw_settings.get("active_profile", "custom")
        self.settings = apply_profile(active, raw_settings)

        icon_map.USE_MDI = bool(self.settings.get("use_material_icons", True))

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

        self.apps = load_apps()
        self.presets = load_presets()
        self.cards = []
        self.preset_tiles = []
        self.category_buttons = {}
        self.launching_paths = set()
        self._program_hotkeys = {}
        self._last_process_states = None

        self.theme_name = self.settings.get("theme", "dark")
        self.accent = self.settings.get("accent", "blue")
        self.colors = get_theme(self.theme_name, self.accent)
        self.current_category = self.settings.get("current_category", "all")
        if self.current_category not in CATEGORIES:
            self.current_category = "all"
        self.current_subcategory = self.settings.get("current_subcategory", "all")
        self.always_on_top = bool(self.settings.get("always_on_top", True))
        self._first_shown = False
        self.mini_mode = False
        self._normal_geometry = None
        self._was_always_on_top = True
        self.system_monitor = None
        self.animated_bg = None

        apply_tile_settings(self.settings)
        set_tile_scale(
            int(self.settings.get("tile_scale", 100)),
            int(self.settings.get("icon_scale", 100)),
        )

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(700, 500)
        self.setAcceptDrops(True)
        self.installEventFilter(self)

        try:
            self.setWindowFlags(
                self.windowFlags() | Qt.FramelessWindowHint
            )
        except Exception as e:
            log.error(f"frameless init error: {e}")

        self._apply_window_size()

        self._build_tray()
        self._setup_hotkey()
        self._register_program_hotkeys()
        self._rebuild_ui()

        self.quick = QuickLauncher(
            get_apps_callable=lambda: self.apps,
            colors=self.colors,
        )

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

        QTimer.singleShot(1500, self._check_updates_for_apps)

        self._updates_timer = QTimer(self)
        self._updates_timer.timeout.connect(self._check_updates_for_apps)
        self._updates_timer.start(10 * 60 * 1000)

        self._init_plugins()

        if self.settings.get("silent_start", False):
            QTimer.singleShot(0, self.hide)

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
        self.plugin_manager.call_hook("on_startup")
        QTimer.singleShot(200, lambda: sounds.play_voice("startup"))

    # ================= ИКОНКА ТРЕЯ =================
    def set_tray_icon(self):
        try:
            icon = make_tray_icon(
                self.colors, self.settings.get("tray_icon", "")
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

        if hasattr(self, "presets_btn"):
            self.presets_btn.setIcon(self._get_fa_icon("fa5s.rocket", c["ACCENT"]))
            self.presets_btn.setIconSize(QSize(22, 22))
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
        if hasattr(self, "settings_btn"):
            self.settings_btn.setIcon(self._get_fa_icon("fa5s.cog", c["TEXT"]))
            self.settings_btn.setIconSize(QSize(20, 20))

        if hasattr(self, "custom_titlebar") and self.custom_titlebar:
            self.custom_titlebar._refresh_icons()

    # ================= TOASTS =================
    def _show_toast(self, title, message, preset="success"):
        if preset == "error":
            sounds.play("error")
            sounds.play_voice("error")
        elif preset == "info":
            sounds.play_voice("info")

        # Нативные уведомления (plyer)
        if self.settings.get("native_notifications", False):
            if preset in ("error", "warning", "info"):
                try:
                    notifications.notify(title, message, timeout=4)
                except Exception:
                    pass

        if not HAS_TOAST:
            if preset == "error":
                show_error(self, self.colors, title, message)
            else:
                show_info(self, self.colors, title, message)
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
            if preset == "error":
                show_error(self, self.colors, title, message)
            else:
                show_info(self, self.colors, title, message)

    # ================= МИНИ-РЕЖИМ =================
    def toggle_mini_mode(self):
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

        # Используем активный монитор вместо primary
        screen = get_active_monitor_geometry()
        x = screen.right() - self.width() - 10
        y = screen.top() + 50
        self.move(x, y)

        if hasattr(self, "custom_titlebar") and self.custom_titlebar:
            self.custom_titlebar.hide()
        if hasattr(self, "content_widget") and self.content_widget:
            self.content_widget.hide()
        if hasattr(self, "mini_panel") and self.mini_panel:
            self.mini_panel.show()
            self._rebuild_mini_panel()

        self.always_on_top = True
        set_always_on_top_native(self, True)
        self._refresh_icons()

    def exit_mini_mode(self):
        if not self.mini_mode:
            return
        self.mini_mode = False

        if hasattr(self, "mini_panel") and self.mini_panel:
            self.mini_panel.hide()
        if hasattr(self, "content_widget") and self.content_widget:
            self.content_widget.show()
        if hasattr(self, "custom_titlebar") and self.custom_titlebar:
            self.custom_titlebar.show()

        self.setMinimumSize(700, 500)
        if hasattr(self, "_normal_geometry") and self._normal_geometry:
            self.setGeometry(self._normal_geometry)
        else:
            self.resize(1180, 740)

        self.always_on_top = getattr(self, "_was_always_on_top", True)
        set_always_on_top_native(self, self.always_on_top)
        self._refresh_icons()
        self._relayout_grid()

    # ================= ПОЛНОЭКРАННЫЙ РЕЖИМ =================
    def toggle_fullscreen(self):
        try:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            if hasattr(self, "custom_titlebar") and self.custom_titlebar:
                QTimer.singleShot(50, self.custom_titlebar._refresh_icons)
        except Exception as e:
            log.error(f"toggle_fullscreen error: {e}")

    # ================= ВСЕГДА НАВЕРХУ =================
    def toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        self.settings["always_on_top"] = self.always_on_top
        save_settings(self.settings)
        set_always_on_top_native(self, self.always_on_top)
        self._apply_theme()

    # ================= РАЗМЕР =================
    def _apply_window_size(self):
        self.setMinimumWidth(700)
        self.setMaximumWidth(16777215)
        self.resize(
            max(700, self.settings.get("window_width", 1180)),
            max(500, self.settings.get("window_height", 740)),
        )

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

    # ================= UI =================
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

        # ============ ЛЕВЫЙ САЙДБАР ============
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
        self.main_category_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.main_category_btn.setToolTip(f"Категории  ·  сейчас: {cur_name}")
        self.main_category_btn.clicked.connect(self._toggle_fan)
        side.addWidget(self.main_category_btn)

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
        self.presets_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.presets_btn.setToolTip("Пресеты запуска")
        self.presets_btn.clicked.connect(self.open_presets_manager)
        side.addWidget(self.presets_btn)

        self.import_btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            self.import_btn.setIcon(
                self._get_fa_icon("fa5s.download", self.colors["TEXT"])
            )
        else:
            self.import_btn.setText("⬇")
        self.import_btn.setIconSize(QSize(20, 20))
        self.import_btn.setFixedSize(48, 48)
        self.import_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.import_btn.setToolTip(
            "Импорт из меню Пуск, Steam, Epic или Рабочего стола"
        )
        self.import_btn.clicked.connect(self.open_import)
        side.addWidget(self.import_btn)

        self.add_btn = QPushButton()
        if icon_map.HAS_QTAWESOME:
            self.add_btn.setIcon(
                self._get_fa_icon("fa5s.plus", self.colors["BG"])
            )
        else:
            self.add_btn.setText("＋")
        self.add_btn.setIconSize(QSize(24, 24))
        self.add_btn.setFixedSize(48, 48)
        self.add_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.add_btn.setToolTip("Добавить программу")
        self.add_btn.clicked.connect(self.add_app)
        side.addWidget(self.add_btn)

        root.addWidget(self.sidebar)

        # ============ ЦЕНТР ============
        center = AnimatedBackground(
            self.colors,
            particle_count=int(self.settings.get("bg_animation_particles", 28)),
        )
        self.animated_bg = center
        self.center_widget = center

        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(28, 20, 28, 22)
        center_layout.setSpacing(12)

        self.title = QLabel("МОЙ ЛАУНЧЕР")
        self.title.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.title)

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
        self.search.setPlaceholderText("Поиск игр и программ...")
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

        self._update_clock()

        center_layout.addSpacing(6)

        # ============ СКРОЛЛ ============
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_content = QWidget()
        scroll_vbox = QVBoxLayout(self.scroll_content)
        scroll_vbox.setContentsMargins(0, 4, 0, 4)
        scroll_vbox.setSpacing(14)

        self.running_header = QLabel("🟢 ЗАПУЩЕНО")
        self.running_header.setVisible(False)
        scroll_vbox.addWidget(self.running_header)

        self.running_grid_widget = QWidget()
        self.running_grid_widget.setVisible(False)
        self.running_grid = QGridLayout(self.running_grid_widget)
        self.running_grid.setContentsMargins(0, 0, 0, 0)
        self.running_grid.setSpacing(tile_card.TILE_SPACING)
        self.running_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll_vbox.addWidget(self.running_grid_widget)

        self.section_label = QLabel("ВСЕ ПРОГРАММЫ")
        self.section_label.setVisible(
            self.settings.get("show_section_headers", True)
        )
        scroll_vbox.addWidget(self.section_label)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(tile_card.TILE_SPACING)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll_vbox.addWidget(self.grid_widget)

        scroll_vbox.addStretch()

        self.scroll.setWidget(self.scroll_content)
        center_layout.addWidget(self.scroll, 1)

        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setContentsMargins(0, 20, 0, 20)
        empty_layout.setSpacing(16)

        self.empty_label = QLabel("")
        self.empty_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_label)

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
        empty_layout.addWidget(self.search_shortcuts)

        self.empty_widget.setVisible(False)
        center_layout.addWidget(self.empty_widget)

        root.addWidget(center, 1)

        # ============ ПРАВЫЙ САЙДБАР ============
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
            rside, "fa5s.sun", "Переключить тему", self.toggle_theme
        )
        self.mini_btn = self._make_icon_btn(
            rside, "fa5s.compress", "Мини-режим (Ctrl+M)", self.toggle_mini_mode
        )
        rside.addStretch()

        # ---- Мониторинг системы ----
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
        root.addWidget(self.right_sidebar)

        main_vbox.addWidget(content, 1)

        self.mini_panel = self._build_mini_panel()
        self.mini_panel.setVisible(False)
        main_vbox.addWidget(self.mini_panel, 1)

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
        exit_btn.setCursor(QCursor(Qt.PointingHandCursor))
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
            w = item.widget()
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
                btn.setCursor(QCursor(Qt.PointingHandCursor))
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
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setMinimumWidth(140)
        btn.clicked.connect(lambda _=False, s=service: self._open_web_search(s))
        parent_layout.addWidget(btn)
        if not hasattr(self, "_shortcut_btns"):
            self._shortcut_btns = {}
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
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        parent_layout.addWidget(btn)
        return btn

    # ================= ВЕЕР =================
    def _toggle_fan(self):
        if not hasattr(self, "category_fan"):
            return
        self.category_fan.toggle()
        self.category_fan.apply_theme(self.colors, self.current_category)

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

    # ================= ПОДКАТЕГОРИИ =================
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

    # ================= ЧАСЫ =================
    def _update_clock(self):
        try:
            if hasattr(self, "clock_label") and self.clock_label:
                self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))
        except Exception:
            pass

    # ================= ПОИСК В ИНТЕРНЕТЕ =================
    def _open_web_search(self, service):
        query = self.search.text().strip()
        if not query:
            return
        q = quote(query)
        urls = {
            "google":  f"https://www.google.com/search?q={q}",
            "youtube": f"https://www.youtube.com/results?search_query={q}",
            "steam":   f"https://store.steampowered.com/search/?term={q}",
            "twitch":  f"https://www.twitch.tv/search?term={q}",
        }
        url = urls.get(service)
        if url:
            QDesktopServices.openUrl(QUrl(url))
            log.info(f"Открываю поиск {service}: {query}")

    # ================= СЕТКА =================
    def _relayout_grid(self):
        if not hasattr(self, "grid_layout"):
            return

        for grid in (self.running_grid, self.grid_layout):
            while grid.count():
                grid.takeAt(0)

        visible_cards = [c for c in self.cards if c.isVisible()]
        visible_presets = [p for p in self.preset_tiles if p.isVisible()]

        running_cards = [c for c in visible_cards if getattr(c, "running", False)]
        other_cards   = [c for c in visible_cards if not getattr(c, "running", False)]

        show_running_setting = self.settings.get("show_running_section", True)
        # Секция «Запущено» показывается всегда, если есть запущенные —
        # вне зависимости от текущей категории.
        show_running_section = (
            show_running_setting
            and len(running_cards) > 0
        )

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
                r = i // cols
                c = i % cols
                self.running_grid.addWidget(
                    tile, r, c, Qt.AlignTop | Qt.AlignLeft
                )
            for i in range(self.running_grid.columnCount()):
                self.running_grid.setColumnStretch(i, 0)
            self.running_grid.setColumnStretch(cols, 1)

            main_tiles = visible_presets + other_cards
        else:
            # Секция запущенных выключена или их нет —
            # все карточки (в т.ч. запущенные) идут в основную сетку
            main_tiles = visible_presets + running_cards + other_cards

        if main_tiles:
            for i, tile in enumerate(main_tiles):
                r = i // cols
                c = i % cols
                self.grid_layout.addWidget(
                    tile, r, c, Qt.AlignTop | Qt.AlignLeft
                )
            for i in range(self.grid_layout.columnCount()):
                self.grid_layout.setColumnStretch(i, 0)
            self.grid_layout.setColumnStretch(cols, 1)

        main_tiles = visible_presets + other_cards
        if main_tiles:
            for i, tile in enumerate(main_tiles):
                r = i // cols
                c = i % cols
                self.grid_layout.addWidget(
                    tile, r, c, Qt.AlignTop | Qt.AlignLeft
                )
            for i in range(self.grid_layout.columnCount()):
                self.grid_layout.setColumnStretch(i, 0)
            self.grid_layout.setColumnStretch(cols, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._relayout_grid)

    def _refresh_statuses(self):
        if not self.cards:
            return
        states = {}
        for card in self.cards:
            p = card.app.get("path", "")
            states[p] = is_process_running(p)
        if states == self._last_process_states:
            return
        self._last_process_states = states
        self.render_cards()

    # ================= СТАТИСТИКА =================
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

    # ================= ОБНОВЛЕНИЯ EXE =================
    def _check_updates_for_apps(self):
        changed = False
        for app in self.apps:
            path = app.get("path", "")
            if not path or "://" in path or not path.lower().endswith(".exe"):
                app.pop("_has_update", None)
                continue
            try:
                current = get_exe_version(path)
            except Exception:
                current = ""
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
        if any(a.get("_has_update") for a in self.apps):
            self.render_cards()

    def accept_update(self, app):
        path = app.get("path", "")
        cur = get_exe_version(path) if path else ""
        for a in self.apps:
            if a == app:
                a["known_version"] = cur
                a.pop("_has_update", None)
                break
        save_apps(self.apps)
        log.info(f"Обновление принято: {app.get('name')} → {cur}")
        sounds.play("success")
        sounds.play_voice("success")
        self.render_cards()

    # ================= ПРЕСЕТЫ =================
    def open_presets_manager(self):
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
                    sounds.play("success")
                    sounds.play_voice("success")

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
                    sounds.play("success")
                    sounds.play_voice("success")

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
            sounds.play("close")
            sounds.play_voice("close")

        add_btn.clicked.connect(add_preset)
        edit_btn.clicked.connect(edit_preset)
        del_btn.clicked.connect(delete_preset)
        lw.itemDoubleClicked.connect(lambda _: edit_preset())

        dlg.exec()

    def _launch_preset(self, preset):
        paths = preset.get("paths", [])
        if not paths:
            self._show_toast("Пресет пуст", "В пресете нет программ", "warning")
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
        log.info(f"Пресет «{preset.get('name')}»: запущено {launched} из {len(paths)}")

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
            make_tray_icon(self.colors, self.settings.get("tray_icon", "")),
            self
        )
        self.tray.setToolTip(f"{APP_NAME} {APP_VERSION}")

        menu = QMenu()
        self._style_menu(menu)

        act_show = QAction("Показать окно", self)
        act_show.triggered.connect(self.show_window)
        menu.addAction(act_show)

        act_hide = QAction("Скрыть окно", self)
        act_hide.triggered.connect(self.hide)
        menu.addAction(act_hide)

        menu.addSeparator()
        act_quick = QAction("Быстрый поиск...", self)
        act_quick.triggered.connect(self.show_quick)
        menu.addAction(act_quick)

        act_ontop = QAction("Поверх всех окон", self)
        act_ontop.setCheckable(True)
        act_ontop.setChecked(self.always_on_top)
        act_ontop.triggered.connect(self.toggle_always_on_top)
        menu.addAction(act_ontop)

        act_settings = QAction("Настройки...", self)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()
        act_quit = QAction("Выход", self)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

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
        for path, hk in list(self._program_hotkeys.items()):
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self._program_hotkeys = {}
        for app in self.apps:
            hk = (app.get("hotkey") or "").strip()
            if not hk:
                continue
            try:
                path = app.get("path", "")
                keyboard.add_hotkey(
                    hk, lambda p=path: self._launch_by_path_from_hotkey(p)
                )
                self._program_hotkeys[path] = hk
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
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.settings["theme"] = self.theme_name
        save_settings(self.settings)
        self.colors = get_theme(self.theme_name, self.accent)
        try:
            clear_fa_cache()
            icon_map.clear_cache()
        except Exception:
            pass
        self.set_tray_icon()
        self._apply_theme()
        self._refresh_icons()
        self._style_menu(self.tray.contextMenu())
        if hasattr(self, "quick") and self.quick:
            self.quick.update_colors(self.colors)
        if hasattr(self, "overlay") and self.overlay:
            try:
                self.overlay.colors = self.colors
                self.overlay.apply_theme()
            except Exception:
                pass
        sounds.play("toggle")

        if hasattr(self, "system_monitor") and self.system_monitor:
            self.system_monitor.apply_theme(self.colors)

        if hasattr(self, "animated_bg") and self.animated_bg:
            self.animated_bg.update_colors(self.colors)

        if self.plugin_manager:
            self.plugin_manager.call_hook(
                "on_theme_change", self.theme_name, self.accent
            )

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

        if hasattr(self, "custom_titlebar") and self.custom_titlebar:
            self.custom_titlebar.apply_theme(c)
            try:
                custom = self.settings.get("tray_icon", "")
                self.custom_titlebar.icon_label.setPixmap(
                    make_tray_icon(c, custom).pixmap(22, 22)
                )
            except Exception:
                pass

        self.title.setStyleSheet(
            f"color: {c['ACCENT']}; font-size: 26px; "
            f"font-weight: 800; letter-spacing: 3px; "
            f"background: transparent;"
        )
        glow = QGraphicsDropShadowEffect(self.title)
        glow.setBlurRadius(24)
        glow.setColor(QColor(c["ACCENT"]))
        glow.setOffset(0, 0)
        self.title.setGraphicsEffect(glow)

        if hasattr(self, "clock_label"):
            self.clock_label.setStyleSheet(
                f"color: {c['TEXT']}; font-size: 22px; "
                f"font-weight: 600; background: transparent; "
                f"letter-spacing: 2px;"
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

        self._style_sidebar_buttons()

        if hasattr(self, "category_fan"):
            self.category_fan.apply_theme(c, self.current_category)

        self.empty_label.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 14px; padding: 10px;"
        )

        if hasattr(self, "_shortcut_btns"):
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
        self.empty_widget.setStyleSheet("background: transparent;")

        if hasattr(self, "mini_panel") and self.mini_panel:
            self.mini_panel.setStyleSheet(f"""
                QFrame#MiniPanel {{
                    background-color: {c['BG_ALT']};
                    border-left: 1px solid {c['BORDER']};
                }}
            """)

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

        if hasattr(self, "add_btn") and self.add_btn:
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
                QPushButton:pressed {{ background-color: {c['ACCENT']}; }}
            """)

        if hasattr(self, "import_btn") and self.import_btn:
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
                QPushButton:pressed {{ background-color: {c['ACCENT_SOFT']}; }}
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
        old_material = self.settings.get("use_material_icons", True)
        old_bg_anim = self.settings.get("bg_animation_enabled", True)
        old_auto_cover = self.settings.get("auto_cover_enabled", True)

        self.settings.update(new)
        save_settings(self.settings)

        active = self.settings.get("active_profile", "custom")
        self.settings = apply_profile(active, self.settings)
        self.settings.update({
            k: v for k, v in new.items()
            if k in ("hotkey", "quick_hotkey", "autostart", "silent_start",
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
                     "auto_cover_enabled", "native_notifications")
        })
        save_settings(self.settings)

        new_material = self.settings.get("use_material_icons", True)
        if new_material != old_material:
            icon_map.USE_MDI = bool(new_material)
            icon_map.clear_cache()

        new_auto_cover = self.settings.get("auto_cover_enabled", True)
        if new_auto_cover != old_auto_cover:
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

        pending = dlg.pending_import()
        if pending is not None:
            self.apps = pending
            save_apps(self.apps)
            self._register_program_hotkeys()
            QTimer.singleShot(500, self._check_updates_for_apps)

        pending_presets = None
        try:
            pending_presets = dlg.pending_presets()
        except Exception:
            pass
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
                clear_fa_cache()
                icon_map.clear_cache()
            except Exception:
                pass
            if hasattr(self, "quick") and self.quick:
                self.quick.update_colors(self.colors)
            if hasattr(self, "overlay") and self.overlay:
                try:
                    self.overlay.colors = self.colors
                    self.overlay.apply_theme()
                except Exception:
                    pass
            if hasattr(self, "animated_bg") and self.animated_bg:
                self.animated_bg.update_colors(self.colors)

        if new.get("hotkey") != old_hotkey or new.get("quick_hotkey") != old_quick:
            self._reload_hotkey()

        if new.get("always_on_top", True) != old_ontop:
            self.always_on_top = bool(new.get("always_on_top", True))
            set_always_on_top_native(self, self.always_on_top)

        if new.get("tray_icon", "") != old_tray_icon:
            self.set_tray_icon()

        if hasattr(self, "category_fan"):
            self.category_fan.update_speed(
                self.settings.get("animation_speed", 100)
            )

        new_bg_anim = self.settings.get("bg_animation_enabled", True)
        if new_bg_anim != old_bg_anim:
            self._apply_bg_animation_visibility()

        self._apply_ui_visibility()
        self._apply_monitor_visibility()
        self._apply_theme()
        self._refresh_icons()
        self._style_menu(self.tray.contextMenu())
        self._rebuild_subcat_combo()
        self.render_cards()

        sounds.play("success")
        sounds.play_voice("success")

        if self.plugin_manager:
            try:
                self.plugin_manager.settings = self.settings
                self.plugin_manager.sync_with_settings()
                self.plugin_manager.call_hook("on_settings_saved", self.settings)
            except Exception as e:
                log.error(f"plugin sync after settings: {e}")

    def _apply_ui_visibility(self):
        if hasattr(self, "clock_label"):
            self.clock_label.setVisible(self.settings.get("show_clock", True))
        if hasattr(self, "search_row_widget"):
            self.search_row_widget.setVisible(
                self.settings.get("show_search", True)
            )
        if hasattr(self, "section_label"):
            self.section_label.setVisible(
                self.settings.get("show_section_headers", True)
            )
        if hasattr(self, "scroll"):
            if self.settings.get("hide_scrollbar", False):
                self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            else:
                self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def _apply_monitor_visibility(self):
        if not hasattr(self, "system_monitor") or self.system_monitor is None:
            return
        show = bool(self.settings.get("show_system_monitor", True))
        self.system_monitor.setVisible(show)
        try:
            interval = int(self.settings.get("system_monitor_interval", 2))
            self.system_monitor.set_interval(interval)
        except Exception:
            pass

    def _apply_bg_animation_visibility(self):
        if not hasattr(self, "animated_bg") or self.animated_bg is None:
            return
        enabled = bool(self.settings.get("bg_animation_enabled", True))
        try:
            self.animated_bg.set_enabled(enabled)
        except Exception:
            pass

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
        if event.type() == QKeyEvent.KeyPress:
            if event.key() == Qt.Key_F11:
                self.toggle_fullscreen()
                return True
            if event.key() == Qt.Key_M and event.modifiers() & Qt.ControlModifier:
                self.toggle_mini_mode()
                return True
            if event.key() == Qt.Key_Escape and self.isFullScreen():
                self.showNormal()
                if hasattr(self, "custom_titlebar") and self.custom_titlebar:
                    self.custom_titlebar._refresh_icons()
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
                w = item.widget()
                if w:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()

        self.cards = []
        self.preset_tiles = []

        if self.current_category in ("all", "recent"):
            for preset in self.presets:
                tile = PresetTile(preset, self.colors, self.menu_style())
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
            # Разрешение на авто-генерацию обложки
            app["_auto_cover_enabled"] = bool(
                self.settings.get("auto_cover_enabled", True)
                and cover_generator.is_available()
            )

            card = TileCard(
                app, self.colors, self.menu_style(),
                is_launching=is_launching,
            )
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

            self.cards.append(card)

        name = CATEGORIES.get(self.current_category, ("Все", ""))[0]
        self.section_label.setText(name.upper())

        self._last_process_states = {
            c.app.get("path", ""): is_process_running(c.app.get("path", ""))
            for c in self.cards
        }

        running_count = sum(1 for c in self.cards if getattr(c, "running", False))
        total = len(self.apps)
        presets_count = len(self.presets)
        if hasattr(self, "custom_titlebar") and self.custom_titlebar:
            self.custom_titlebar.set_status(
                f"v{APP_VERSION}   ·   {total} программ   ·   "
                f"{running_count} запущено   ·   {presets_count} пресетов"
            )

        self._rebuild_subcat_combo()
        self.filter_cards(self.search.text())

        if hasattr(self, "mini_panel") and self.mini_mode:
            self._rebuild_mini_panel()

        self._animate_card_appearance()

    # ================= ПЛАВНОЕ ПОЯВЛЕНИЕ =================
    def _animate_card_appearance(self):
        all_tiles = self.preset_tiles + self.cards
        if not all_tiles:
            return
        if len(all_tiles) > 60:
            return

        cascade_limit = 15
        step_ms = 28
        duration = 260

        for i, w in enumerate(all_tiles):
            try:
                effect = QGraphicsOpacityEffect(w)
                effect.setOpacity(0.0)
                w.setGraphicsEffect(effect)

                anim = QPropertyAnimation(effect, b"opacity", w)
                anim.setDuration(duration)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.OutCubic)

                anim.finished.connect(
                    lambda ww=w: self._cleanup_fade_effect(ww)
                )

                if i < cascade_limit:
                    QTimer.singleShot(
                        i * step_ms,
                        lambda a=anim: self._safe_anim_start(a),
                    )
                else:
                    anim.start()

                w._fade_anim = anim
                w._fade_effect = effect
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

            # Запущенные программы видны всегда (кроме фильтра по поиску):
            # так пользователь видит, что у него работает, из любой категории.
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
            match = in_cat and in_search and in_sub
            card.setVisible(bool(match))
            if match:
                visible += 1

        visible_presets = 0
        for tile in self.preset_tiles:
            in_search = (
                not text or text in tile.preset.get("name", "").lower()
            )
            tile.setVisible(bool(in_search))
            if in_search:
                visible_presets += 1

        self._relayout_grid()

        total = visible + visible_presets
        if total == 0:
            if not self.apps and not self.presets:
                msg = "Пусто.\nНажми ＋"
            elif text:
                msg = "Ничего не найдено"
            else:
                msg = "В этой категории пока нет программ."
            self.empty_label.setText(msg)

            show_web = bool(text) and self.settings.get("show_search", True)
            if hasattr(self, "search_shortcuts"):
                self.search_shortcuts.setVisible(show_web)
            if hasattr(self, "empty_widget"):
                self.empty_widget.setVisible(bool(msg) or show_web)
            else:
                self.empty_label.setVisible(bool(msg))
        else:
            if hasattr(self, "empty_widget"):
                self.empty_widget.setVisible(False)
            else:
                self.empty_label.setVisible(False)

    # ================= КАТЕГОРИИ =================
    def set_category(self, key):
        if key not in CATEGORIES:
            return
        self.current_category = key
        self.settings["current_category"] = key
        self.current_subcategory = "all"
        self.settings["current_subcategory"] = "all"
        save_settings(self.settings)

        self._update_main_category_btn()
        if hasattr(self, "category_fan"):
            self.category_fan.apply_theme(self.colors, self.current_category)

        self.section_label.setText(CATEGORIES[key][0].upper())
        self._rebuild_subcat_combo()
        self.filter_cards(self.search.text())
        sounds.play("toggle")

        if self.plugin_manager:
            self.plugin_manager.call_hook("on_category_change", key)

    # ================= СОРТИРОВКА =================
    def _renumber_orders(self):
        sorted_apps = self._sorted_apps()
        for i, app in enumerate(sorted_apps):
            for a in self.apps:
                if a is app:
                    a["order"] = i
                    break

    def move_app(self, app, direction):
        sorted_apps = self._sorted_apps()
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

    # ================= DRAG-N-DROP ПЕРЕСТАНОВКА =================
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
        log.info(f"Перестановка: {src.get('name')} → позиция {dst_pos}")
        self.render_cards()

    # ================= ДЕЙСТВИЯ =================
    def _add_app_by_path(self, path):
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
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите программу", "",
            "Программы (*.exe *.lnk *.bat *.cmd);;Все файлы (*.*)"
        )
        if not path:
            return
        self._add_app_by_path(path)

    def open_import(self):
        from importers import (
            scan_start_menu, scan_desktop, scan_steam, scan_epic
        )
        from import_dialog import ImportDialog

        candidates = (
            scan_start_menu() + scan_desktop() +
            scan_steam() + scan_epic()
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
            if c["path"] in existing:
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
            self._show_toast("Импорт завершён", "Ничего нового не добавлено", "info")

    def rename_app(self, app):
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
                f"Сначала добавь подкатегории для категории «{CATEGORIES.get(cat, (cat,))[0]}»:\n"
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
            self,
            "Заметка",
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
        log.info(f"Заметка для {app.get('name')}: '{new_note[:50]}'")
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
                log.info(
                    f"Спутники для {a.get('name')}: "
                    f"{len(a['companions'])} шт."
                )
                break
        save_apps(self.apps)
        self.render_cards()

    def delete_app(self, app):
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
        for a in self.apps:
            if a == app:
                a["favorite"] = not a.get("favorite", False)
                break
        save_apps(self.apps)
        self.render_cards()

    def open_folder(self, app):
        path = app.get("path", "")
        if "://" in path:
            return
        folder = os.path.dirname(path)
        if os.path.exists(folder):
            os.startfile(folder)

    def kill_running_process(self, app):
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
            if self.plugin_manager:
                self.plugin_manager.call_hook("on_app_close", app)
            QTimer.singleShot(300, self.render_cards)
        else:
            self._show_toast("Завершение процесса",
                            "Процесс не найден или уже закрыт", "warning")

    # ================= ЗАПУСК =================
    def launch_app(self, app):
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
        if self.plugin_manager:
            self.plugin_manager.call_hook("on_app_close", app)
        if then_launch:
            QTimer.singleShot(700, lambda: self._do_launch(app))
        else:
            QTimer.singleShot(300, self.render_cards)

    def _do_launch(self, app):
        path = app.get("path", "")
        name = app.get("name", "")
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

        recents = self.settings.get("recent_paths", [])
        if path in recents:
            recents.remove(path)
        recents.insert(0, path)
        self.settings["recent_paths"] = recents[:15]
        save_settings(self.settings)

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
            self.plugin_manager.call_hook("on_app_launch", app)

        if self.settings.get("activate_after_launch", False):
            QTimer.singleShot(
                2500,
                lambda p=path: window_activation.activate_app_window(p),
            )

    def _launch_companions(self, app):
        companions = app.get("companions", []) or []
        if not companions:
            return
        for cpath in companions:
            if not cpath or cpath == app.get("path"):
                continue
            if is_process_running(cpath):
                log.info(f"Спутник уже запущен: {cpath}")
                continue

            target = next(
                (a for a in self.apps if a.get("path") == cpath), None
            )
            launch_app_dict = target if target else {
                "name": os.path.splitext(os.path.basename(cpath))[0],
                "path": cpath,
                "custom_icon": "",
            }

            r = launch(launch_app_dict)
            if r.ok:
                log.info(f"Спутник запущен: {launch_app_dict.get('name')}")
                if target:
                    target["launch_count"] = target.get("launch_count", 0) + 1
                if self.settings.get("overlay_enabled", True) and self.overlay:
                    try:
                        pix = get_icon(launch_app_dict, 42)
                        self.overlay.colors = self.colors
                        self.overlay.apply_theme()
                        self.overlay.show_app(
                            launch_app_dict.get("name", ""),
                            pix,
                            subtitle="Запущен автоматически",
                        )
                    except Exception:
                        pass
        save_apps(self.apps)

    def _launch_category_companions(self, app):
        cat = app.get("category") or "other"
        cc = self.settings.get("category_companions", {}) or {}
        companions = cc.get(cat, []) or []
        if not companions:
            return
        log.info(
            f"Категорийные спутники для категории '{cat}': "
            f"{len(companions)} шт."
        )
        for cpath in companions:
            if not cpath or cpath == app.get("path"):
                continue
            if is_process_running(cpath):
                log.info(f"Спутник категории уже запущен: {cpath}")
                continue

            target = next(
                (a for a in self.apps if a.get("path") == cpath), None
            )
            launch_app_dict = target if target else {
                "name": os.path.splitext(os.path.basename(cpath))[0],
                "path": cpath,
                "custom_icon": "",
            }

            r = launch(launch_app_dict)
            if r.ok:
                log.info(f"Спутник категории запущен: {launch_app_dict.get('name')}")
                if target:
                    target["launch_count"] = target.get("launch_count", 0) + 1
                if self.settings.get("overlay_enabled", True) and self.overlay:
                    try:
                        pix = get_icon(launch_app_dict, 42)
                        self.overlay.colors = self.colors
                        self.overlay.apply_theme()
                        self.overlay.show_app(
                            launch_app_dict.get("name", ""),
                            pix,
                            subtitle="Спутник категории",
                        )
                    except Exception:
                        pass
        save_apps(self.apps)

    def _clear_launching(self, path):
        self.launching_paths.discard(path)
        self.render_cards()

    # ================= ОКНО / ТРЕЙ =================
    def toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        log.info("quit_app")
        try:
            import custom_tooltip
            custom_tooltip.cleanup()
        except Exception:
            pass

        try:
            if hasattr(self, "system_monitor") and self.system_monitor:
                self.system_monitor.stop()
        except Exception:
            pass

        try:
            if hasattr(self, "animated_bg") and self.animated_bg:
                self.animated_bg.set_enabled(False)
        except Exception:
            pass

        try:
            sounds.play_voice("shutdown")
            import time
            time.sleep(0.8)
        except Exception:
            pass

        if self.plugin_manager:
            try:
                self.plugin_manager.call_hook("on_shutdown")
            except Exception as e:
                log.error(f"plugin on_shutdown: {e}")
            for name in list(self.plugin_manager.plugins.keys()):
                self.plugin_manager.unload(name)

        try:
            if hasattr(self, "_updates_timer"):
                self._updates_timer.stop()
        except Exception:
            pass

        try:
            self.settings["window_height"] = self.height()
            self.settings["window_width"] = self.width()
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
            if hasattr(self, "tray") and self.tray:
                self.tray.hide()
        except Exception:
            pass
        try:
            QApplication.quit()
        except Exception:
            pass
        QTimer.singleShot(300, lambda: os._exit(0))

    def hide_to_tray(self):
        try:
            self.hide()
            self._show_toast(
                APP_NAME,
                "Свёрнут в трей. Ctrl+Alt+L — показать.",
                "info",
            )
        except Exception as e:
            log.error(f"hide_to_tray error: {e}")

    def closeEvent(self, event):
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
            event.accept()
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

    def _apply_start_view(self):
        view = self.settings.get("start_view", "normal")
        try:
            if view == "maximized":
                self.showMaximized()
            elif view == "fullscreen":
                self.showFullScreen()
                if hasattr(self, "custom_titlebar") and self.custom_titlebar:
                    QTimer.singleShot(50, self.custom_titlebar._refresh_icons)
            elif view == "tray":
                self.hide()
                self._show_toast(APP_NAME,
                                 "Свёрнут в трей. Ctrl+Alt+L — показать.",
                                 "info")
        except Exception as e:
            log.error(f"_apply_start_view: {e}")