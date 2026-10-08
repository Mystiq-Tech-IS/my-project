"""Кастомный splash screen при запуске лаунчера.

Показывается 1.5 секунды, рисуется QPainter'ом:
- акцентный круг с буквой «Л»
- название и версия
- прогресс-полоса внизу
"""

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QLinearGradient,
)

from config import APP_NAME, APP_VERSION


class SplashScreen(QWidget):
    finished = Signal()

    def __init__(self, colors, duration_ms=1500):
        super().__init__(None)
        self.colors = colors
        self.duration_ms = max(300, int(duration_ms))

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.SplashScreen
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(420, 260)

        self._center_on_screen()

        # Анимация
        self._elapsed = 0
        self._phase = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.setInterval(30)   # ~33 fps

    # ---------------- Позиционирование ----------------
    def _center_on_screen(self):
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + (screen.height() - self.height()) // 2
            self.move(x, y)
        except Exception:
            pass

    # ---------------- Анимация ----------------
    def start(self):
        self.show()
        self.raise_()
        self._elapsed = 0
        self._phase = 0.0
        self._anim_timer.start()

    def _tick(self):
        self._elapsed += self._anim_timer.interval()
        self._phase = min(1.0, self._elapsed / float(self.duration_ms))
        self.update()
        if self._elapsed >= self.duration_ms:
            self._anim_timer.stop()
            self.finished.emit()
            self.close()

    # ---------------- Рисование ----------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.TextAntialiasing)

        c = self.colors
        w, h = self.width(), self.height()
        pad = 1
        radius = 22

        # Тень — лёгкий градиент под окном
        try:
            shadow = QLinearGradient(0, 0, 0, h)
            shadow.setColorAt(0.0, QColor(0, 0, 0, 0))
            shadow.setColorAt(1.0, QColor(0, 0, 0, 80))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(shadow))
            p.drawRoundedRect(
                QRectF(pad + 4, pad + 6, w - pad * 2 - 4, h - pad * 2),
                radius, radius,
            )
        except Exception:
            pass

        # Фон окна
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["BG_ALT"]))
        p.drawRoundedRect(
            QRectF(pad, pad, w - pad * 2, h - pad * 2),
            radius, radius,
        )

        # Градиентная рамка
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(c["ACCENT"]))
        grad.setColorAt(0.5, QColor(c["ACCENT_HOV"]))
        grad.setColorAt(1.0, QColor(c["ACCENT"]))
        p.setPen(QPen(QBrush(grad), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(
            QRectF(pad + 1, pad + 1, w - pad * 2 - 2, h - pad * 2 - 2),
            radius - 1, radius - 1,
        )

        # ---- Логотип (круг с буквой Л) ----
        # Пульсирующий масштаб
        pulse = 1.0 + 0.06 * self._bounce(self._phase)

        base_size = 84
        circle_size = base_size * pulse
        cx = w / 2
        cy = 92

        circle_rect = QRectF(
            cx - circle_size / 2,
            cy - circle_size / 2,
            circle_size,
            circle_size,
        )

        # Градиент на круге
        circle_grad = QLinearGradient(
            circle_rect.topLeft(), circle_rect.bottomRight()
        )
        circle_grad.setColorAt(0.0, QColor(c["ACCENT_HOV"]))
        circle_grad.setColorAt(1.0, QColor(c["ACCENT"]))

        # Внешнее свечение
        glow = QColor(c["ACCENT"])
        glow.setAlpha(int(70 * self._bounce(self._phase)))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(circle_rect.adjusted(-8, -8, 8, 8))

        # Круг
        p.setBrush(QBrush(circle_grad))
        p.setPen(Qt.NoPen)
        p.drawEllipse(circle_rect)

        # Буква «Л»
        letter_font = QFont("Segoe UI", int(circle_size * 0.5))
        letter_font.setBold(True)
        p.setFont(letter_font)
        p.setPen(QColor(c["BG"]))
        p.drawText(circle_rect, Qt.AlignCenter, "Л")

        # ---- Название ----
        title_font = QFont("Segoe UI", 16)
        title_font.setBold(True)
        p.setFont(title_font)
        p.setPen(QColor(c["TEXT"]))
        p.drawText(
            QRectF(0, cy + circle_size / 2 + 14, w, 28),
            Qt.AlignHCenter | Qt.AlignTop,
            APP_NAME,
        )

        # ---- Версия ----
        ver_font = QFont("Segoe UI", 9)
        p.setFont(ver_font)
        p.setPen(QColor(c["SUBTEXT"]))
        p.drawText(
            QRectF(0, cy + circle_size / 2 + 40, w, 18),
            Qt.AlignHCenter | Qt.AlignTop,
            f"v{APP_VERSION}",
        )

        # ---- Прогресс-полоса ----
        bar_w = w - 120
        bar_h = 4
        bar_x = 60
        bar_y = h - 42

        # Дорожка
        p.setBrush(QColor(c["CARD_HOVER"]))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(
            QRectF(bar_x, bar_y, bar_w, bar_h),
            bar_h / 2, bar_h / 2,
        )

        # Заполнение — плавный градиент
        fill_w = bar_w * self._phase
        if fill_w > 0:
            fill_grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            fill_grad.setColorAt(0.0, QColor(c["ACCENT"]))
            fill_grad.setColorAt(1.0, QColor(c["ACCENT_HOV"]))
            p.setBrush(QBrush(fill_grad))
            p.drawRoundedRect(
                QRectF(bar_x, bar_y, fill_w, bar_h),
                bar_h / 2, bar_h / 2,
            )

        # ---- Подпись под прогресс-баром ----
        status_font = QFont("Segoe UI", 8)
        p.setFont(status_font)
        p.setPen(QColor(c["SUBTEXT"]))
        p.drawText(
            QRectF(0, bar_y + bar_h + 6, w, 16),
            Qt.AlignHCenter | Qt.AlignTop,
            "Загрузка…",
        )

    @staticmethod
    def _bounce(t):
        """Плавный sin-импульс 0..1..0 для пульсации."""
        import math
        return 0.5 + 0.5 * math.sin(t * math.pi * 2)