"""Всплывающий оверлей «Запускается X» в правом нижнем углу."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication


class LaunchOverlay(QWidget):
    def __init__(self, colors):
        super().__init__(None)
        self.colors = colors
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(340, 74)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        outer.addWidget(self.card)

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(14)

        self.icon_label = QLabel("🚀")
        self.icon_label.setFixedSize(42, 42)
        self.icon_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title = QLabel("")
        self.sub = QLabel("")
        text_col.addWidget(self.title)
        text_col.addWidget(self.sub)
        card_layout.addLayout(text_col)
        card_layout.addStretch()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        self.apply_theme()

    def apply_theme(self):
        c = self.colors
        # Без обводки — только фон и закругление
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {c['CARD']};
                border: none;
                border-radius: 14px;
            }}
        """)
        self.icon_label.setStyleSheet(
            "background: transparent; font-size: 30px; border: none;"
        )
        self.title.setStyleSheet(
            f"color: {c['TEXT']}; font-size: 14px; "
            f"font-weight: 700; background: transparent; border: none;"
        )
        self.sub.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 11px; "
            f"background: transparent; border: none;"
        )

    def show_app(self, app_name, pixmap=None, subtitle="Секунду…"):
        self.title.setText(f"Запускается  {app_name}")
        self.sub.setText(subtitle)

        if pixmap and not pixmap.isNull():
            self.icon_label.setText("")
            self.icon_label.setPixmap(
                pixmap.scaled(42, 42, Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)
            )
        else:
            self.icon_label.setPixmap(self.icon_label.pixmap() or None)
            self.icon_label.setText("🚀")

        try:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            x = screen.width() - self.width() - 24
            y = screen.height() - self.height() - 24
            self.move(x, y)
        except Exception:
            pass

        self.show()
        self.raise_()
        self._hide_timer.start(2500)