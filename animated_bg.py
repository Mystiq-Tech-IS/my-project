"""Анимированный фон: медленно движущиеся частицы.

Рисуется на QWidget, обновляется 30 fps.
Частицы соединяются тонкими линиями, если близко друг к другу.
"""

import math
import random

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush


class AnimatedBackground(QWidget):
    def __init__(self, colors, parent=None, particle_count=28):
        super().__init__(parent)
        self.colors = colors
        self._enabled = True
        self._fps = 30
        self._link_distance = 130      # px, для соединения линий
        self._particles = []

        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self._init_particles(max(8, int(particle_count)))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(int(1000 / max(10, self._fps)))

    # -------------- Инициализация --------------
    def _init_particles(self, n):
        self._particles = []
        for _ in range(n):
            self._particles.append({
                "x": random.random(),       # 0..1
                "y": random.random(),
                # очень медленное движение
                "vx": (random.random() - 0.5) * 0.0012,
                "vy": (random.random() - 0.5) * 0.0012,
                "r": 1.4 + random.random() * 2.4,
            })

    # -------------- API --------------
    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        if self._enabled:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def is_enabled(self):
        return self._enabled

    def update_colors(self, colors):
        self.colors = colors
        self.update()

    # -------------- Цикл --------------
    def _tick(self):
        if not self._enabled:
            return
        for pt in self._particles:
            pt["x"] += pt["vx"]
            pt["y"] += pt["vy"]

            # Wrap-around (мягко переносим)
            if pt["x"] < -0.02:
                pt["x"] = 1.02
            elif pt["x"] > 1.02:
                pt["x"] = -0.02
            if pt["y"] < -0.02:
                pt["y"] = 1.02
            elif pt["y"] > 1.02:
                pt["y"] = -0.02

        self.update()

    # -------------- Рисование --------------
    def paintEvent(self, event):
        if not self._enabled:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = max(1, self.width())
        h = max(1, self.height())

        c = self.colors
        accent = QColor(c["ACCENT"])
        base_dot = QColor(c["ACCENT"])
        base_dot.setAlpha(180)

        # Считаем пиксельные позиции один раз
        pix = []
        for pt in self._particles:
            pix.append((
                pt["x"] * w,
                pt["y"] * h,
                pt["r"],
            ))

        # ---- Линии между близкими частицами ----
        link_threshold = self._link_distance
        line_color = QColor(c["ACCENT"])
        line_color.setAlpha(0)

        p.setBrush(Qt.NoBrush)
        n = len(pix)
        for i in range(n):
            xi, yi, _ = pix[i]
            for j in range(i + 1, n):
                xj, yj, _ = pix[j]
                dx = xi - xj
                dy = yi - yj
                d2 = dx * dx + dy * dy
                if d2 > link_threshold * link_threshold:
                    continue
                d = math.sqrt(d2)
                if d < 0.001:
                    continue
                alpha = int(60 * (1.0 - d / link_threshold))
                if alpha <= 0:
                    continue
                col = QColor(line_color)
                col.setAlpha(alpha)
                p.setPen(QPen(col, 1.0))
                p.drawLine(QPointF(xi, yi), QPointF(xj, yj))

        # ---- Точки ----
        p.setPen(Qt.NoPen)
        for x, y, r in pix:
            p.setBrush(base_dot)
            p.drawEllipse(QPointF(x, y), r, r)

        # ---- Лёгкий центральный градиент для глубины ----
        try:
            from PySide6.QtGui import QRadialGradient
            cx = w * 0.5
            cy = h * 0.45
            radius = max(w, h) * 0.6
            rg = QRadialGradient(QPointF(cx, cy), radius)
            halo = QColor(c["ACCENT"])
            halo.setAlpha(18)
            rg.setColorAt(0.0, halo)
            halo2 = QColor(c["ACCENT"])
            halo2.setAlpha(0)
            rg.setColorAt(1.0, halo2)
            p.setBrush(QBrush(rg))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(0, 0, w, h))
        except Exception:
            pass