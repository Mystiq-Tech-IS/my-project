"""Компактная карточка-иконка для режима «док»."""

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QMenu
from PySide6.QtCore import Qt, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QCursor

from icons import get_icon
from card import _blend
from process_check import is_process_running


class CompactCard(QFrame):
    clicked          = Signal(dict)
    toggle_favorite  = Signal(dict)
    delete_requested = Signal(dict)
    open_folder      = Signal(dict)
    launch_only      = Signal(dict)

    def __init__(self, app, colors, menu_style="", parent=None):
        super().__init__(parent)
        self.app = app
        self.colors = colors
        self.menu_style = menu_style
        self.running = is_process_running(app.get("path", ""))

        # Маленькая иконка
        self.setFixedSize(44, 44)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        self._hover_progress = 0.0
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(140)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_value)

        if self.running:
            self._apply_style(colors["CARD"], colors["OK"])
        else:
            self._apply_style(colors["CARD"], colors["BORDER"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        pix = get_icon(app, 32)
        if pix:
            icon_label.setPixmap(pix)
        layout.addWidget(icon_label)

        self.setToolTip(app.get("name", ""))

    def _apply_style(self, bg, border):
        self.setStyleSheet(f"""
            CompactCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
        """)

    def _on_hover_value(self, value):
        self._hover_progress = float(value)
        bg = _blend(self.colors["CARD"], self.colors["CARD_HOVER"], self._hover_progress)

        if self.running:
            border = self.colors["OK"]
        else:
            border = _blend(
                self.colors["BORDER"],
                self.colors["ACCENT"],
                self._hover_progress * 0.7,
            )
        self._apply_style(bg, border)

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.app)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_style)

        act_launch = menu.addAction("▶  Запустить")
        menu.addSeparator()
        if self.app.get("favorite"):
            act_fav = menu.addAction("☆  Убрать из избранного")
        else:
            act_fav = menu.addAction("⭐  В избранное")
        act_folder = menu.addAction("📂  Открыть папку")
        menu.addSeparator()
        act_delete = menu.addAction("🗑  Удалить")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen == act_launch:
            self.clicked.emit(self.app)
        elif chosen == act_fav:
            self.toggle_favorite.emit(self.app)
        elif chosen == act_folder:
            self.open_folder.emit(self.app)
        elif chosen == act_delete:
            self.delete_requested.emit(self.app)