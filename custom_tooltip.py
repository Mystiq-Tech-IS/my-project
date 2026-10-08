"""Кастомный тёмный tooltip в стиле Discord.

Singleton-виджет: один на приложение, переиспользуется.
Показывается по вызову show_tooltip(), автоматически скрывается
через timeout. Рисует закруглённый фон + тонкую рамку.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QPen


_instance = None


class _CustomTooltip(QWidget):
    def __init__(self, colors):
        super().__init__(None)
        self.colors = colors

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        self.setWindowFlags(
            Qt.ToolTip
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(0)

        self.label = QLabel("")
        self.label.setTextFormat(Qt.RichText)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(360)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lay.addWidget(self.label)

        self._apply_text_style()

    def _apply_text_style(self):
        c = self.colors
        self.label.setStyleSheet(
            f"color: {c['TEXT']}; font-size: 12px; "
            f"font-family: 'Segoe UI'; "
            f"background: transparent; border: none;"
        )

    def update_colors(self, colors):
        self.colors = colors
        self._apply_text_style()
        self.update()

    def show_html(self, global_pos, html_text, timeout_ms=2500):
        self.label.setText(html_text)
        self.adjustSize()

        w = self.width()
        h = self.height()

        # Смещение от курсора
        x = global_pos.x() + 14
        y = global_pos.y() + 18

        # Не вылезать за пределы экрана
        try:
            screen = self.screen().availableGeometry()
        except Exception:
            screen = None

        if screen is not None:
            if x + w > screen.right():
                x = global_pos.x() - w - 6
            if y + h > screen.bottom():
                y = global_pos.y() - h - 6
            if x < screen.left():
                x = screen.left() + 4
            if y < screen.top():
                y = screen.top() + 4

        self.move(x, y)
        self.show()
        self.raise_()
        if timeout_ms > 0:
            self._hide_timer.start(timeout_ms)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.colors
        w, h = self.width(), self.height()

        # Фон
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["CARD"]))
        p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)

        # Тонкая рамка
        p.setPen(QPen(QColor(c["BORDER_HOV"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(
            QRectF(0.5, 0.5, w - 1, h - 1), 8, 8
        )


def show_tooltip(global_pos, html_text, colors, timeout_ms=2500):
    """Показать tooltip рядом с курсором. Если уже показан — обновить."""
    global _instance
    if _instance is None:
        _instance = _CustomTooltip(colors)
    else:
        _instance.update_colors(colors)
    _instance.show_html(global_pos, html_text, timeout_ms)


def hide_tooltip():
    """Скрыть tooltip."""
    global _instance
    if _instance is not None:
        try:
            _instance._hide_timer.stop()
            _instance.hide()
        except Exception:
            pass


def cleanup():
    """Закрыть singleton при выходе из приложения."""
    global _instance
    if _instance is not None:
        try:
            _instance.close()
            _instance.deleteLater()
        except Exception:
            pass
        _instance = None