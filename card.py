"""Карточка программы: modern + gaming style с пульсирующим статусом."""

from PySide6.QtWidgets import (
    QFrame, QLabel, QHBoxLayout, QVBoxLayout, QMenu, QSizePolicy
)
from PySide6.QtCore import (
    Qt, Signal, QVariantAnimation, QEasingCurve, QTimer, QPropertyAnimation
)
from PySide6.QtGui import QCursor, QColor

from icons import get_icon
from launcher import file_exists
from process_check import is_process_running


def _blend(c1_hex, c2_hex, t):
    a = QColor(c1_hex)
    b = QColor(c2_hex)
    r = int(a.red() + (b.red() - a.red()) * t)
    g = int(a.green() + (b.green() - a.green()) * t)
    bl = int(a.blue() + (b.blue() - a.blue()) * t)
    return f"#{r:02X}{g:02X}{bl:02X}"


class PulseDot(QLabel):
    """Маленькая точка, которая пульсирует, когда программа запущена."""
    def __init__(self, color_on, color_off):
        super().__init__()
        self.color_on = color_on
        self.color_off = color_off
        self.setFixedSize(10, 10)
        self._on = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._toggle)
        self._apply()

    def _apply(self):
        c = self.color_on if self._on else self.color_off
        self.setStyleSheet(
            f"background-color: {c}; border-radius: 5px;"
        )

    def _toggle(self):
        self._on = not self._on
        self._apply()

    def start(self):
        self._timer.start(700)

    def stop(self, final_color):
        self._timer.stop()
        self._on = True
        self.color_on = final_color
        self._apply()


class AppCard(QFrame):
    clicked               = Signal(dict)
    rename_requested      = Signal(dict)
    change_path_requested = Signal(dict)
    delete_requested      = Signal(dict)
    toggle_favorite       = Signal(dict)
    open_folder           = Signal(dict)
    change_icon_requested = Signal(dict)
    reset_icon_requested  = Signal(dict)
    change_category       = Signal(dict)
    move_requested        = Signal(dict, str)
    kill_process          = Signal(dict)
    set_hotkey_requested  = Signal(dict)

    def __init__(self, app, colors, menu_style="", is_launching=False,
                 parent=None):
        super().__init__(parent)
        self.app = app
        self.colors = colors
        self.menu_style = menu_style
        self.is_launching = is_launching
        self.selected = False
        self._hover_progress = 0.0

        self.setFixedHeight(84)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        self._apply_style(colors["CARD"], colors["BORDER"])

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(160)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_value)

        exists = file_exists(app.get("path", ""))
        running = is_process_running(app.get("path", ""))

        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 12, 20, 12)
        outer.setSpacing(16)

        # ---------- Иконка 56×56 ----------
        icon_holder = QFrame()
        icon_holder.setFixedSize(56, 56)
        icon_holder.setStyleSheet(
            f"background-color: {colors['BG_ALT']}; "
            f"border-radius: 16px; border: 1px solid {colors['BORDER']};"
        )
        icon_layout = QVBoxLayout(icon_holder)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        pix = get_icon(app, 40)
        if pix:
            self.icon_label.setPixmap(pix)
        icon_layout.addWidget(self.icon_label)
        outer.addWidget(icon_holder)

        # ---------- Текст ----------
        text_block = QVBoxLayout()
        text_block.setContentsMargins(0, 0, 0, 0)
        text_block.setSpacing(6)

        prefix = "⭐  " if app.get("favorite") else ""
        name_color = colors["TEXT"] if exists else colors["DANGER"]
        self.name_label = QLabel(prefix + app.get("name", "Без имени"))
        self.name_label.setStyleSheet(
            f"color: {name_color}; font-size: 16px; "
            f"font-weight: 600; background: transparent;"
        )
        text_block.addWidget(self.name_label)

        # ---------- Строка статуса ----------
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)

        if not exists:
            dot_color = colors["DANGER"]
            status_text = "Файл не найден"
            status_color = colors["DANGER"]
            self.pulse = None
        elif is_launching:
            dot_color = colors["ACCENT"]
            status_text = "Запускается..."
            status_color = colors["ACCENT"]
            self.pulse = PulseDot(colors["ACCENT"], colors["ACCENT_SOFT"])
        elif running:
            dot_color = colors["OK"]
            status_text = "Работает"
            status_color = colors["OK"]
            self.pulse = PulseDot(colors["OK"], colors["OK_DIM"])
        else:
            dot_color = colors["SUBTEXT"]
            status_text = "Не запущено"
            status_color = colors["SUBTEXT"]
            self.pulse = None

        if self.pulse:
            status_row.addWidget(self.pulse)
            self.pulse.start()
        else:
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(
                f"background-color: {dot_color}; border-radius: 5px;"
            )
            status_row.addWidget(dot)

        status_label = QLabel(status_text)
        status_label.setStyleSheet(
            f"color: {status_color}; font-size: 12px; background: transparent;"
        )
        status_row.addWidget(status_label)
        status_row.addStretch()

        text_block.addLayout(status_row)
        outer.addLayout(text_block, 1)

        # ---------- Hotkey ----------
        hk = app.get("hotkey", "")
        if hk:
            hk_label = QLabel(f"⌨ {hk}")
            hk_label.setStyleSheet(
                f"color: {colors['ACCENT']}; "
                f"background-color: {colors['ACCENT_SOFT']}; "
                f"border-radius: 8px; padding: 4px 10px; "
                f"font-size: 11px; font-weight: 600;"
            )
            outer.addWidget(hk_label)

        # ---------- Стрелка ----------
        self.arrow = QLabel("›")
        self.arrow.setStyleSheet(
            f"color: {colors['SUBTEXT']}; font-size: 24px; "
            f"font-weight: bold; background: transparent;"
        )
        outer.addWidget(self.arrow)

        if self.selected:
            self.set_selected(True)

    def _apply_style(self, bg, border):
        self.setStyleSheet(f"""
            AppCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 18px;
            }}
        """)

    def _on_hover_value(self, value):
        self._hover_progress = float(value)
        if self.selected:
            return
        bg = _blend(self.colors["CARD"], self.colors["CARD_HOVER"], self._hover_progress)
        border = _blend(self.colors["BORDER"], self.colors["ACCENT"], self._hover_progress * 0.7)
        self._apply_style(bg, border)

        arrow_color = _blend(self.colors["SUBTEXT"], self.colors["ACCENT"], self._hover_progress)
        self.arrow.setStyleSheet(
            f"color: {arrow_color}; font-size: 24px; "
            f"font-weight: bold; background: transparent;"
        )

    def enterEvent(self, event):
        if self.selected:
            return
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()

    def leaveEvent(self, event):
        if self.selected:
            return
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()

    def set_selected(self, value: bool):
        self.selected = value
        if value:
            bg = _blend(self.colors["CARD"], self.colors["ACCENT"], 0.18)
            self._apply_style(bg, self.colors["ACCENT"])
        else:
            self._apply_style(self.colors["CARD"], self.colors["BORDER"])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.app)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_style)

        running = is_process_running(self.app.get("path", ""))

        act_launch = menu.addAction("▶  Запустить")
        menu.addSeparator()

        act_up_first  = menu.addAction("⬆⬆  Наверх")
        act_up        = menu.addAction("⬆  Выше")
        act_down      = menu.addAction("⬇  Ниже")
        act_down_last = menu.addAction("⬇⬇  В конец")
        menu.addSeparator()

        if self.app.get("favorite"):
            act_fav = menu.addAction("☆  Убрать из избранного")
        else:
            act_fav = menu.addAction("⭐  В избранное")

        act_rename   = menu.addAction("✏  Переименовать")
        act_change   = menu.addAction("📁  Изменить путь")
        act_icon     = menu.addAction("🖼  Сменить иконку")
        if self.app.get("custom_icon"):
            act_reset_icon = menu.addAction("↺  Сбросить иконку")
        else:
            act_reset_icon = None
        act_category = menu.addAction("🏷  Изменить категорию")

        if self.app.get("hotkey"):
            act_hotkey = menu.addAction(f"⌨  Изменить hotkey ({self.app['hotkey']})")
            act_hotkey_clear = menu.addAction("✖  Убрать hotkey")
        else:
            act_hotkey = menu.addAction("⌨  Назначить hotkey")
            act_hotkey_clear = None

        act_folder = menu.addAction("📂  Открыть папку")

        if running:
            menu.addSeparator()
            act_kill = menu.addAction("⛔  Завершить процесс")
        else:
            act_kill = None

        menu.addSeparator()
        act_delete = menu.addAction("🗑  Удалить")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen == act_launch:
            self.clicked.emit(self.app)
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
        elif chosen == act_icon:
            self.change_icon_requested.emit(self.app)
        elif act_reset_icon is not None and chosen == act_reset_icon:
            self.reset_icon_requested.emit(self.app)
        elif chosen == act_category:
            self.change_category.emit(self.app)
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