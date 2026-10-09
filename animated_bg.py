"""Анимированный фон центральной области.

Режимы:
  • particles — медленные частицы с линиями (по умолчанию)
  • solid     — просто фон темы
  • gradient  — плавный градиент двух настраиваемых цветов
  • image     — статичное изображение (PNG / JPG / BMP / WEBP)
  • gif       — анимированный GIF через QMovie
  • video     — видео (MP4 / WEBM / MKV / …) через QMediaPlayer + QVideoSink

Изображение / GIF / видео растягивается на всю область (cover),
поверх можно наложить прозрачность через bg_opacity.
"""

import math
import os
import random

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QUrl
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QMovie, QLinearGradient,
)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
    HAS_MULTIMEDIA = True
except ImportError:
    HAS_MULTIMEDIA = False
    QMediaPlayer = None
    QAudioOutput = None
    QVideoSink = None


class AnimatedBackground(QWidget):
    BG_PARTICLES = "particles"
    BG_IMAGE     = "image"
    BG_GIF       = "gif"
    BG_VIDEO     = "video"
    BG_SOLID     = "solid"
    BG_GRADIENT  = "gradient"

    def __init__(self, colors, parent=None, particle_count=28):
        super().__init__(parent)
        self.colors = colors

        # ---- Частицы ----
        self._particles = []
        self._link_distance = 130
        self._fps = 30
        self._particle_count = max(8, int(particle_count))
        self._init_particles(self._particle_count)

        # ---- Общее ----
        self._bg_type = self.BG_PARTICLES
        self._bg_path = ""
        self._bg_opacity = 100
        self._video_muted = True

        # ---- Image ----
        self._bg_pixmap = None

        # ---- GIF ----
        self._movie = None

        # ---- Video ----
        self._player = None
        self._audio = None
        self._video_sink = None
        self._video_img = None

        # ---- Gradient ----
        self._gradient_color1 = ""
        self._gradient_color2 = ""
        self._gradient_angle = 45

        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(int(1000 / max(10, self._fps)))
        self._timer.start()

    # ======================== ЧАСТИЦЫ ========================
    def _init_particles(self, n):
        self._particles = []
        for _ in range(n):
            self._particles.append({
                "x": random.random(),
                "y": random.random(),
                "vx": (random.random() - 0.5) * 0.0012,
                "vy": (random.random() - 0.5) * 0.0012,
                "r": 1.4 + random.random() * 2.4,
            })

    def _tick(self):
        if self._bg_type != self.BG_PARTICLES:
            return
        for pt in self._particles:
            pt["x"] += pt["vx"]
            pt["y"] += pt["vy"]
            if pt["x"] < -0.02:
                pt["x"] = 1.02
            elif pt["x"] > 1.02:
                pt["x"] = -0.02
            if pt["y"] < -0.02:
                pt["y"] = 1.02
            elif pt["y"] > 1.02:
                pt["y"] = -0.02
        self.update()

    # ======================== API ========================
    def update_colors(self, colors):
        self.colors = colors
        self.update()

    def set_enabled(self, enabled: bool):
        """Совместимость со старым API."""
        if enabled:
            if self._bg_type != self.BG_PARTICLES:
                # Не трогаем кастомный фон
                self._timer.start()
                self.update()
                return
            self._bg_type = self.BG_PARTICLES
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def is_enabled(self):
        return self._bg_type == self.BG_PARTICLES

    def set_particle_count(self, n):
        n = max(8, int(n))
        if n != self._particle_count:
            self._particle_count = n
            self._init_particles(n)

    def apply_settings(self, settings: dict):
        """Применяет настройки фона из settings-словаря."""
        bg_type = settings.get("bg_type", "particles")
        if bg_type not in (self.BG_PARTICLES, self.BG_IMAGE,
                           self.BG_GIF, self.BG_VIDEO,
                           self.BG_SOLID, self.BG_GRADIENT):
            bg_type = self.BG_PARTICLES

        if (bg_type == self.BG_PARTICLES
                and not settings.get("bg_animation_enabled", True)):
            bg_type = self.BG_SOLID

        bg_path = settings.get("bg_path", "") or ""
        try:
            bg_opacity = int(settings.get("bg_opacity", 100))
        except Exception:
            bg_opacity = 100
        bg_opacity = max(0, min(100, bg_opacity))

        bg_muted = bool(settings.get("bg_video_muted", True))

        new_g1 = (settings.get("bg_gradient_color1", "") or "").strip()
        new_g2 = (settings.get("bg_gradient_color2", "") or "").strip()
        try:
            new_angle = int(settings.get("bg_gradient_angle", 45))
        except Exception:
            new_angle = 45
        new_angle = new_angle % 360

        self.set_particle_count(
            int(settings.get("bg_animation_particles", 28))
        )

        need_reload = (
            bg_type != self._bg_type
            or bg_path != self._bg_path
            or new_g1 != self._gradient_color1
            or new_g2 != self._gradient_color2
            or new_angle != self._gradient_angle
        )

        if need_reload:
            self._cleanup_bg()
            self._bg_type = bg_type
            self._bg_path = bg_path
            self._bg_opacity = bg_opacity
            self._video_muted = bg_muted
            self._gradient_color1 = new_g1
            self._gradient_color2 = new_g2
            self._gradient_angle = new_angle

            if bg_type == self.BG_IMAGE:
                self._load_image(bg_path)
            elif bg_type == self.BG_GIF:
                self._load_gif(bg_path)
            elif bg_type == self.BG_VIDEO:
                self._load_video(bg_path)
        else:
            self._bg_opacity = bg_opacity
            self._video_muted = bg_muted
            if self._player is not None:
                try:
                    self._player.setMuted(bg_muted)
                except Exception:
                    pass

        # Таймер нужен только частицам
        if bg_type == self.BG_PARTICLES:
            self._timer.start()
        else:
            self._timer.stop()

        self.update()

    # ======================== ЗАГРУЗКА РЕСУРСОВ ========================
    def _cleanup_bg(self):
        if self._movie is not None:
            try:
                self._movie.stop()
                self._movie.deleteLater()
            except Exception:
                pass
            self._movie = None
        if self._player is not None:
            try:
                self._player.stop()
                self._player.setSource(QUrl())
                self._player.deleteLater()
            except Exception:
                pass
            self._player = None
        if self._audio is not None:
            try:
                self._audio.deleteLater()
            except Exception:
                pass
            self._audio = None
        self._video_sink = None
        self._video_img = None
        self._bg_pixmap = None

    def _load_image(self, path):
        if not path or not os.path.exists(path):
            return
        pix = QPixmap(path)
        if not pix.isNull():
            self._bg_pixmap = pix

    def _load_gif(self, path):
        if not path or not os.path.exists(path):
            return
        try:
            movie = QMovie(path)
            movie.setCacheMode(QMovie.CacheAll)
            movie.frameChanged.connect(lambda _: self.update())
            movie.start()
            self._movie = movie
        except Exception:
            self._movie = None

    def _load_video(self, path):
        if not HAS_MULTIMEDIA:
            return
        if not path or not os.path.exists(path):
            return
        try:
            self._player = QMediaPlayer(self)
            self._video_sink = QVideoSink(self)
            self._player.setVideoSink(self._video_sink)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._audio.setMuted(self._video_muted)
            self._video_sink.videoFrameChanged.connect(self._on_video_frame)
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.setLoops(QMediaPlayer.Infinite)
            self._player.play()
        except Exception:
            self._player = None

    def _on_video_frame(self, frame):
        try:
            img = frame.toImage()
            if img.isNull():
                return
            self._video_img = img
            self.update()
        except Exception:
            pass

    # ======================== РИСОВАНИЕ ========================
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w = max(1, self.width())
        h = max(1, self.height())
        c = self.colors

        # 1) Базовая заливка
        p.fillRect(self.rect(), QColor(c.get("BG", "#16161E")))

        # 2) Кастомный фон
        if self._bg_type == self.BG_IMAGE and self._bg_pixmap is not None:
            self._draw_cover(p, self._bg_pixmap, w, h, self._bg_opacity)
        elif self._bg_type == self.BG_GIF and self._movie is not None:
            pix = self._movie.currentPixmap()
            if not pix.isNull():
                self._draw_cover(p, pix, w, h, self._bg_opacity)
        elif self._bg_type == self.BG_VIDEO and self._video_img is not None:
            pix = QPixmap.fromImage(self._video_img)
            if not pix.isNull():
                self._draw_cover(p, pix, w, h, self._bg_opacity)
        elif self._bg_type == self.BG_GRADIENT:
            self._draw_gradient(p, w, h)

        # 3) Частицы
        if self._bg_type == self.BG_PARTICLES:
            self._draw_particles(p, w, h)

    def _draw_cover(self, p: QPainter, pix: QPixmap,
                    w: int, h: int, opacity: int):
        if opacity <= 0:
            return
        pw, ph = pix.width(), pix.height()
        if pw <= 0 or ph <= 0:
            return
        scale = max(w / pw, h / ph)
        target_w = int(pw * scale)
        target_h = int(ph * scale)
        x = (w - target_w) // 2
        y = (h - target_h) // 2

        if opacity >= 100:
            p.drawPixmap(x, y, target_w, target_h, pix)
        else:
            p.setOpacity(opacity / 100.0)
            p.drawPixmap(x, y, target_w, target_h, pix)
            p.setOpacity(1.0)

    def _draw_gradient(self, p: QPainter, w: int, h: int):
        c = self.colors

        # Цвета: если не заданы вручную — берём ACCENT и BG_ALT
        color1 = self._gradient_color1 or c.get("ACCENT", "#89B4FA")
        color2 = self._gradient_color2 or c.get("BG_ALT", "#1C1C26")

        angle = self._gradient_angle % 360
        rad = math.radians(angle)
        dx = math.cos(rad) * w
        dy = math.sin(rad) * h

        grad = QLinearGradient(0, 0, dx, dy)
        grad.setColorAt(0.0, QColor(color1))
        grad.setColorAt(1.0, QColor(color2))

        op = max(0, min(100, self._bg_opacity))
        if op >= 100:
            p.setOpacity(1.0)
        else:
            p.setOpacity(op / 100.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRect(self.rect())
        p.setOpacity(1.0)

    def _draw_particles(self, p: QPainter, w: int, h: int):
        c = self.colors
        base_dot = QColor(c["ACCENT"])
        base_dot.setAlpha(180)

        pix = []
        for pt in self._particles:
            pix.append((pt["x"] * w, pt["y"] * h, pt["r"]))

        link_threshold = self._link_distance
        n = len(pix)
        p.setBrush(Qt.NoBrush)
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
                col = QColor(c["ACCENT"])
                col.setAlpha(alpha)
                p.setPen(QPen(col, 1.0))
                p.drawLine(QPointF(xi, yi), QPointF(xj, yj))

        p.setPen(Qt.NoPen)
        for x, y, r in pix:
            p.setBrush(base_dot)
            p.drawEllipse(QPointF(x, y), r, r)

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

    # ======================== ЖИЗНЕННЫЙ ЦИКЛ ========================
    def hideEvent(self, event):
        if self._player is not None:
            try:
                self._player.pause()
            except Exception:
                pass
        super().hideEvent(event)

    def showEvent(self, event):
        if self._player is not None:
            try:
                self._player.play()
            except Exception:
                pass
        super().showEvent(event)