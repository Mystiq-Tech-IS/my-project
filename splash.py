"""JARVIS-style splash screen при запуске лаунчера.

Два режима:
  • idle    — ждёт нажатия кнопки «ЗАПУСТИТЬ». Кольца крутятся медленно.
  • loading — прогресс-бар заполняется за duration_ms, потом окно
              загрузки исчезает и emit'ится сигнал `finished`.

Всё рисуется QPainter'ом, без внешних ассетов.
"""

import math
import time
from datetime import datetime

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QPainterPath,
    QLinearGradient, QRadialGradient, QConicalGradient,
)

from config import APP_NAME, APP_VERSION


class SplashScreen(QWidget):
    finished = Signal()   # загрузка завершена → можно показать окно
    started  = Signal()   # пользователь нажал «Запустить»

    # ------- Режимы -------
    STATE_IDLE    = "idle"
    STATE_LOADING = "loading"

    def __init__(self, colors, duration_ms=5000):
        super().__init__(None)
        self.colors = colors
        self._duration_ms = max(600, int(duration_ms))

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.SplashScreen
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(600, 440)

        self._center_on_screen()

        # ---- Состояние анимации ----
        self._state = self.STATE_IDLE
        self._loading_elapsed = 0
        self._idle_elapsed = 0
        self._phase = 0.0        # 0..1 — прогресс загрузки
        self._ring_a = 0.0
        self._ring_b = 0.0
        self._ring_c = 0.0
        self._scan_y = 0.0
        self._pulse = 0.0

        # Кнопка «Запустить»
        self._btn_rect = None
        self._btn_hover = False

        # ---- Таймеры ----
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._tick_idle)
        self._idle_timer.setInterval(40)   # 25 fps

        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._tick_loading)
        self._loading_timer.setInterval(25)   # 40 fps

        self._modules = [
            "CORE", "MEMORY", "UI", "NETWORK",
            "AUDIO", "GRAPHICS", "PLUGINS", "DISCORD", "LIBRARY",
        ]

        self.setMouseTracking(True)

    # ---------------- Позиционирование ----------------
    def _center_on_screen(self):
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + (screen.height() - self.height()) // 2
            self.move(x, y)
        except Exception:
            pass

    # ---------------- Управление ----------------
    def start(self):
        """Показать splash в режиме ожидания кнопки."""
        self.show()
        self.raise_()
        self._state = self.STATE_IDLE
        self._loading_elapsed = 0
        self._idle_elapsed = 0
        self._phase = 0.0
        self._idle_timer.start()

    def _begin_loading(self):
        """Начать загрузку: скрыть кнопку, показать прогресс-бар."""
        if self._state != self.STATE_IDLE:
            return
        self._state = self.STATE_LOADING
        self._idle_timer.stop()
        self._loading_elapsed = 0
        self._loading_timer.start()
        try:
            self.started.emit()
        except Exception:
            pass
        self.update()

    # ---------------- Тики ----------------
    def _tick_idle(self):
        self._idle_elapsed += self._idle_timer.interval()
        t = self._idle_elapsed / 1000.0

        # Медленное вращение
        self._ring_a = (self._ring_a + 0.25) % 360
        self._ring_b = (self._ring_b - 0.40) % 360
        self._ring_c = (self._ring_c + 0.65) % 360

        self._scan_y = 0.5 + 0.5 * math.sin(t * 0.6)
        self._pulse = 0.5 + 0.5 * math.sin(t * 1.6)
        self.update()

    def _tick_loading(self):
        dt = self._loading_timer.interval()
        self._loading_elapsed += dt
        self._phase = min(1.0, self._loading_elapsed / float(self._duration_ms))

        # Масштабируем скорость вращения от длительности, чтобы при
        # 5000 мс было плавно, а при 1500 — динамично.
        scale = 1500.0 / max(500, self._duration_ms)
        self._ring_a = (self._ring_a + 0.9 * scale) % 360
        self._ring_b = (self._ring_b - 1.4 * scale) % 360
        self._ring_c = (self._ring_c + 2.1 * scale) % 360

        t = self._loading_elapsed / 1000.0
        self._scan_y = 0.5 + 0.5 * math.sin(t * 1.4)
        self._pulse = 0.5 + 0.5 * math.sin(t * 3.6)

        self.update()

        if self._loading_elapsed >= self._duration_ms:
            self._loading_timer.stop()
            self.finished.emit()
            self.close()

    # ---------------- Мышь ----------------
    def mouseMoveEvent(self, event):
        if self._state == self.STATE_IDLE and self._btn_rect is not None:
            hover = self._btn_rect.contains(event.position())
            if hover != self._btn_hover:
                self._btn_hover = hover
                self.setCursor(
                    Qt.PointingHandCursor if hover else Qt.ArrowCursor
                )
                self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self._state != self.STATE_IDLE:
            return
        if event.button() != Qt.LeftButton:
            return
        if self._btn_rect and self._btn_rect.contains(event.position()):
            self._begin_loading()

    # ---------------- Рисование ----------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.TextAntialiasing)

        w, h = self.width(), self.height()
        c = self.colors

        accent = QColor(c["ACCENT"])
        accent_hov = QColor(c["ACCENT_HOV"])
        bg = QColor(c["BG"])
        bg_alt = QColor(c["BG_ALT"])
        text = QColor(c["TEXT"])
        subtext = QColor(c["SUBTEXT"])
        is_loading = (self._state == self.STATE_LOADING)

        # ---------- Фон ----------
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, bg_alt)
        bg_grad.setColorAt(1.0, bg)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bg_grad))
        p.drawRoundedRect(QRectF(0, 0, w, h), 20, 20)

        # Градиентная рамка
        border_grad = QLinearGradient(0, 0, w, h)
        border_grad.setColorAt(0.0, accent_hov)
        border_grad.setColorAt(0.5, accent)
        border_grad.setColorAt(1.0, accent_hov)
        p.setPen(QPen(QBrush(border_grad), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 20, 20)

        # ---------- Фоновая сетка ----------
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 22), 1))
        grid_step = 30
        for gx in range(0, w, grid_step):
            p.drawLine(gx, 0, gx, h)
        for gy in range(0, h, grid_step):
            p.drawLine(0, gy, w, gy)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 70))
        for gx in range(0, w, grid_step):
            for gy in range(0, h, grid_step):
                p.drawEllipse(QPointF(gx, gy), 1.0, 1.0)

        # ---------- Скан ----------
        scan_y = int(self._scan_y * h)
        scan_grad = QLinearGradient(0, scan_y - 30, 0, scan_y + 30)
        scan_grad.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        scan_grad.setColorAt(0.5, QColor(accent.red(), accent.green(), accent.blue(), 28))
        scan_grad.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(scan_grad))
        p.drawRect(QRectF(0, scan_y - 30, w, 60))

        # ---------- Кольца ----------
        cx = w / 2.0
        cy = h / 2.0 - 40

        self._draw_dashed_ring(p, cx, cy, 98, self._ring_a, accent, 90)
        self._draw_segment_ring(p, cx, cy, 78, self._ring_b, accent_hov, 6)
        self._draw_dashed_ring(p, cx, cy, 62, self._ring_c, accent, 130)

        if is_loading:
            self._draw_progress_arc(p, cx, cy, 90, self._phase, accent)

        # ---------- Пульс центра ----------
        pulse_r = 44 + 3 * self._pulse
        radial = QRadialGradient(QPointF(cx, cy), pulse_r + 12)
        glow = QColor(accent)
        glow.setAlpha(int(50 + 40 * self._pulse))
        radial.setColorAt(0.0, glow)
        glow2 = QColor(accent)
        glow2.setAlpha(0)
        radial.setColorAt(1.0, glow2)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(radial))
        p.drawEllipse(QPointF(cx, cy), pulse_r + 12, pulse_r + 12)

        inner_grad = QLinearGradient(cx - 40, cy - 40, cx + 40, cy + 40)
        inner_grad.setColorAt(0.0, accent_hov)
        inner_grad.setColorAt(1.0, accent)
        p.setBrush(QBrush(inner_grad))
        p.setPen(QPen(QColor(accent_hov), 1.5))
        p.drawEllipse(QPointF(cx, cy), 40, 40)

        p.setPen(QColor(c["BG"]))
        f = QFont("Segoe UI", 30)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(cx - 40, cy - 40, 80, 80), Qt.AlignCenter, "Л")

        # ---------- Версия ----------
        ver_font = QFont("Segoe UI", 9)
        ver_font.setLetterSpacing(QFont.PercentageSpacing, 110)
        p.setFont(ver_font)
        p.setPen(subtext)
        p.drawText(
            QRectF(0, cy + 76, w, 16),
            Qt.AlignHCenter | Qt.AlignTop,
            f"v{APP_VERSION}",
        )

        # ---------- Кнопка / Прогресс ----------
        if is_loading:
            self._draw_progress_bar(p, w, h, accent, accent_hov)
            self._btn_rect = None
        else:
            self._draw_start_button(p, w, h, accent, accent_hov, text, subtext)

        # ---------- Угловая телеметрия ----------
        corner_font = QFont("Consolas", 8)
        p.setFont(corner_font)
        p.setPen(QColor(accent.red(), accent.green(), accent.blue(), 200))

        p.drawText(
            QRectF(16, 12, w - 32, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            "SYSTEM  //  ONLINE",
        )
        now = datetime.now().strftime("%H:%M:%S")
        p.drawText(
            QRectF(16, 12, w - 32, 14),
            Qt.AlignRight | Qt.AlignVCenter,
            now,
        )

        if is_loading:
            mod_idx = min(
                len(self._modules) - 1,
                int(self._phase * len(self._modules)),
            )
            module_name = self._modules[mod_idx]
            left_text = f"LOADING  //  {module_name}"
            right_text = f"MODULES  //  {mod_idx + 1:02d}/{len(self._modules):02d}"
        else:
            left_text = "STATUS  //  READY"
            right_text = "AWAITING  //  INPUT"

        p.drawText(
            QRectF(16, h - 30, w - 32, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            left_text,
        )
        p.drawText(
            QRectF(16, h - 30, w - 32, 14),
            Qt.AlignRight | Qt.AlignVCenter,
            right_text,
        )

        # ---------- Точки-индикаторы ----------
        dot_pulse = 0.4 + 0.6 * self._pulse
        for (px, py) in (
            (16, 40), (w - 16, 40),
            (16, h - 44), (w - 16, h - 44),
        ):
            col = QColor(accent)
            col.setAlphaF(dot_pulse)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(px, py), 3, 3)

        # ---------- Внутренний бордер ----------
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(10, 10, w - 20, h - 20), 14, 14)

        p.end()

    # ---------------- Компоненты ----------------

    def _draw_start_button(self, p, w, h, accent, accent_hov, text, subtext):
        """Большая кнопка «ЗАПУСТИТЬ» по центру."""
        btn_w = 260
        btn_h = 54
        btn_x = (w - btn_w) / 2
        btn_y = h - 110

        rect = QRectF(btn_x, btn_y, btn_w, btn_h)
        self._btn_rect = rect

        # Тень/свечение снизу
        if self._btn_hover:
            glow = QColor(accent)
            glow.setAlpha(80)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(
                QRectF(btn_x - 6, btn_y - 6, btn_w + 12, btn_h + 12),
                16, 16,
            )

        # Градиент фона кнопки
        grad = QLinearGradient(btn_x, btn_y, btn_x, btn_y + btn_h)
        if self._btn_hover:
            grad.setColorAt(0.0, accent_hov)
            grad.setColorAt(1.0, accent)
            border_col = accent_hov
            fg = QColor(self.colors["BG"])
        else:
            base = QColor(accent)
            base.setAlpha(230)
            base2 = QColor(accent)
            base2.setAlpha(180)
            grad.setColorAt(0.0, base)
            grad.setColorAt(1.0, base2)
            border_col = accent_hov
            fg = QColor(self.colors["BG"])

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(rect, 12, 12)

        # Двойной бордер
        p.setPen(QPen(border_col, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 12, 12)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.drawRoundedRect(
            QRectF(btn_x + 3, btn_y + 3, btn_w - 6, btn_h - 6),
            10, 10,
        )

        # Текст кнопки
        btn_font = QFont("Segoe UI", 12)
        btn_font.setBold(True)
        btn_font.setLetterSpacing(QFont.PercentageSpacing, 140)
        p.setFont(btn_font)
        p.setPen(fg)
        p.drawText(rect, Qt.AlignCenter, "▶   ЗАПУСТИТЬ")

        # Подпись под кнопкой
        hint_font = QFont("Segoe UI", 8)
        hint_font.setLetterSpacing(QFont.PercentageSpacing, 110)
        p.setFont(hint_font)
        p.setPen(subtext)
        p.drawText(
            QRectF(0, btn_y + btn_h + 8, w, 16),
            Qt.AlignHCenter | Qt.AlignTop,
            "нажмите, чтобы запустить лаунчер",
        )

    def _draw_progress_bar(self, p, w, h, accent, accent_hov):
        """Полоса загрузки + проценты."""
        bar_w = w - 160
        bar_h = 4
        bar_x = 80
        bar_y = h - 60

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.colors["CARD_HOVER"]))
        p.drawRoundedRect(
            QRectF(bar_x, bar_y, bar_w, bar_h),
            bar_h / 2, bar_h / 2,
        )

        fill_w = max(2, bar_w * self._phase)
        fill_grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
        fill_grad.setColorAt(0.0, accent)
        fill_grad.setColorAt(1.0, accent_hov)
        p.setBrush(QBrush(fill_grad))
        p.drawRoundedRect(
            QRectF(bar_x, bar_y, fill_w, bar_h),
            bar_h / 2, bar_h / 2,
        )

        pct_font = QFont("Consolas", 9)
        pct_font.setBold(True)
        p.setFont(pct_font)
        p.setPen(accent)
        p.drawText(
            QRectF(bar_x + bar_w - 60, bar_y - 18, 60, 16),
            Qt.AlignRight | Qt.AlignVCenter,
            f"{int(self._phase * 100):02d}%",
        )

    # ---------------- Хелперы рисования ----------------

    def _draw_dashed_ring(self, p, cx, cy, r, angle_deg, color, dash_len):
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        segments = 48
        seg_angle = 360.0 / segments
        gap_ratio = dash_len / 100.0
        for i in range(segments):
            start = angle_deg + i * seg_angle
            length = seg_angle * (1.0 - gap_ratio)
            p.drawArc(
                QRectF(cx - r, cy - r, r * 2, r * 2),
                int(start * 16),
                int(length * 16),
            )

    def _draw_segment_ring(self, p, cx, cy, r, angle_deg, color, n_segments):
        pen = QPen(color, 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        seg = 360.0 / n_segments
        for i in range(n_segments):
            start = angle_deg + i * seg
            length = seg * 0.55
            p.drawArc(
                QRectF(cx - r, cy - r, r * 2, r * 2),
                int(start * 16),
                int(length * 16),
            )

    def _draw_progress_arc(self, p, cx, cy, r, phase, color):
        if phase <= 0.001:
            return
        glow = QColor(color)
        glow.setAlpha(90)
        pen_glow = QPen(glow, 4.0)
        pen_glow.setCapStyle(Qt.RoundCap)
        p.setPen(pen_glow)
        p.setBrush(Qt.NoBrush)

        span = int(-phase * 360 * 16)
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.drawArc(rect, 90 * 16, span)

        pen = QPen(color, 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 90 * 16, span)