"""Красивый виджет мониторинга системы (CPU / RAM / GPU).

Что внутри:
  • три кольцевых индикатора с плавной анимацией;
  • sparkline — линия с заливкой последних ~40 значений под кольцом;
  • цветовая логика: зелёный (< 50%) → жёлтый (50–80%) → красный (>= 80%);
  • при >= 80% лёгкое свечение вокруг кольца;
  • расширенный tooltip: частоты, объёмы, VRAM, температура GPU;
  • заголовок «SYSTEM» с пульсирующей точкой состояния.

GPU опционален: если нет pynvml или NVIDIA — блок скрыт.
"""

from collections import deque

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QBrush, QPainterPath, QLinearGradient,
)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
except Exception:
    HAS_NVML = False
    pynvml = None

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")

try:
    import custom_tooltip
    HAS_TOOLTIP = True
except Exception:
    HAS_TOOLTIP = False
    custom_tooltip = None


_nvml_shutdown_done = False


def shutdown_nvml():
    global _nvml_shutdown_done
    if _nvml_shutdown_done:
        return
    _nvml_shutdown_done = True
    if not HAS_NVML:
        return
    try:
        pynvml.nvmlShutdown()
    except Exception as e:
        log.error(f"nvmlShutdown: {e}")


# ======================= КОЛЬЦО + SPARKLINE =======================
class RingIndicator(QWidget):
    """Кольцевой индикатор + sparkline-линия + метка, с tooltip."""

    HISTORY_LEN = 40

    # --- Геометрия виджета (вписываем в 48 px контента right_sidebar) ---
    W = 48
    H = 74

    RING_SIZE = 40
    RING_Y = 2
    RING_THICKNESS = 4.0

    SPARK_H = 8.0
    SPARK_PAD_X = 4

    LABEL_H = 12

    def __init__(self, label, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self._label = label
        self._target = 0.0
        self._display = 0.0
        self._history = deque([0.0] * self.HISTORY_LEN,
                              maxlen=self.HISTORY_LEN)
        self._details = {}
        self._tooltip_active = False

        self.setFixedSize(self.W, self.H)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setStyleSheet("background: transparent;")

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(40)     # ~25 fps
        self._anim_timer.timeout.connect(self._animate_step)

    # ---------- API ----------
    def set_value(self, v):
        try:
            v = float(v)
        except Exception:
            v = 0.0
        v = max(0.0, min(100.0, v))
        self._target = v
        self._history.append(v)
        if abs(v - self._display) > 0.05:
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self.update()

    def set_details(self, details: dict):
        self._details = dict(details or {})

    def apply_theme(self, colors):
        self.colors = colors
        self.update()

    def stop(self):
        try:
            self._anim_timer.stop()
        except Exception:
            pass

    # ---------- Анимация ----------
    def _animate_step(self):
        diff = self._target - self._display
        if abs(diff) < 0.4:
            self._display = self._target
            self._anim_timer.stop()
        else:
            self._display += diff * 0.22
        self.update()

    # ---------- Цвет по уровню ----------
    def _value_color(self, v):
        c = self.colors
        if v >= 80:
            return QColor(c["DANGER"])
        if v >= 50:
            return QColor("#F9E2AF")
        return QColor(c["OK"])

    # ---------- Tooltip ----------
    def _build_tooltip_html(self) -> str:
        d = self._details
        lines = []

        title = d.get("title") or self._label
        lines.append(
            f'<div style="font-weight:bold; font-size:13px;">{title}</div>'
        )
        lines.append(
            f'<div style="margin-top:4px; opacity:0.85;">'
            f'Загрузка: {int(round(self._target))}%</div>'
        )

        order = ("freq", "cores", "mem", "swap",
                 "vram", "temp", "clock")
        label_map = {
            "freq":  "Частота",
            "cores": "Ядра",
            "mem":   "Память",
            "swap":  "Swap",
            "vram":  "VRAM",
            "temp":  "Температура",
            "clock": "Частота",
        }
        for key in order:
            val = d.get(key)
            if not val:
                continue
            lines.append(
                f'<div style="margin-top:2px;">'
                f'{label_map.get(key, key)}: {val}</div>'
            )

        return "".join(lines)

    def enterEvent(self, event):
        self._tooltip_active = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._tooltip_active = False
        if HAS_TOOLTIP:
            try:
                custom_tooltip.hide_tooltip()
            except Exception:
                pass
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        if not HAS_TOOLTIP or not self._tooltip_active:
            return super().mouseMoveEvent(event)
        try:
            gp = event.globalPosition().toPoint()
            html = self._build_tooltip_html()
            custom_tooltip.show_tooltip(
                gp, html, self.colors, timeout_ms=3000,
            )
        except Exception:
            pass
        super().mouseMoveEvent(event)

    # ---------- Отрисовка ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        c = self.colors
        w, h = self.width(), self.height()
        v = self._display

        # ---------- 1. КОЛЬЦО ----------
        ring_size = self.RING_SIZE
        ring_x = (w - ring_size) / 2.0
        ring_y = float(self.RING_Y)
        ring_rect = QRectF(ring_x, ring_y, ring_size, ring_size)

        th = self.RING_THICKNESS
        arc_rect = ring_rect.adjusted(
            th / 2, th / 2, -th / 2, -th / 2,
        )

        # 1a) Внутренний полупрозрачный фон
        fill = QColor(c["BG_ALT"])
        fill.setAlpha(140)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawEllipse(
            arc_rect.adjusted(th, th, -th, -th)
        )

        # 1b) Фоновое кольцо
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(c["BORDER"]), th,
                      Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(arc_rect)

        # 1c) Свечение при >= 80%
        span = int(-v / 100.0 * 360 * 16)
        if v >= 80:
            glow = QColor(self._value_color(v))
            glow.setAlpha(70)
            p.setPen(QPen(glow, th + 4,
                          Qt.SolidLine, Qt.RoundCap))
            p.drawArc(arc_rect, 90 * 16, span)

        # 1d) Прогресс-дуга
        if v > 0.05:
            p.setPen(QPen(self._value_color(v), th,
                          Qt.SolidLine, Qt.RoundCap))
            p.drawArc(arc_rect, 90 * 16, span)

        # 1e) Процент в центре кольца
        text_col = (
            QColor(c["SUBTEXT"]) if v < 1.0 else self._value_color(v)
        )
        p.setPen(text_col)
        f = QFont("Segoe UI", 9)
        f.setBold(True)
        p.setFont(f)
        p.drawText(
            QRectF(ring_x, ring_y + 2, ring_size, ring_size - 4),
            Qt.AlignCenter,
            f"{int(round(v))}",
        )

        # ---------- 2. SPARKLINE ----------
        spark_y = ring_y + ring_size + 4
        spark_h = self.SPARK_H
        spark_x = float(self.SPARK_PAD_X)
        spark_w = float(w - self.SPARK_PAD_X * 2)

        # фоновая дорожка
        track = QColor(c["BORDER"])
        track.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(
            QRectF(spark_x, spark_y + spark_h / 2 - 1,
                   spark_w, 2),
            1, 1,
        )

        # линия + заливка под ней
        hist = list(self._history)
        n = len(hist)
        if n >= 2:
            step = spark_w / (n - 1)
            col = self._value_color(v)

            path = QPainterPath()
            path.moveTo(spark_x,
                        spark_y + spark_h -
                        (hist[0] / 100.0) * spark_h)
            for i in range(1, n):
                x = spark_x + i * step
                y = spark_y + spark_h - (hist[i] / 100.0) * spark_h
                path.lineTo(x, y)

            # Заливка под линией
            fill_path = QPainterPath(path)
            fill_path.lineTo(spark_x + (n - 1) * step,
                             spark_y + spark_h)
            fill_path.lineTo(spark_x, spark_y + spark_h)
            fill_path.closeSubpath()

            grad = QLinearGradient(0, spark_y, 0, spark_y + spark_h)
            c1 = QColor(col); c1.setAlpha(120)
            c2 = QColor(col); c2.setAlpha(20)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawPath(fill_path)

            # Сама линия
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(col, 1.4,
                          Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)

        # ---------- 3. ПОДПИСЬ ----------
        label_y = spark_y + spark_h + 3
        p.setPen(QColor(c["SUBTEXT"]))
        f2 = QFont("Segoe UI", 7)
        f2.setBold(True)
        f2.setLetterSpacing(QFont.PercentageSpacing, 120)
        p.setFont(f2)
        p.drawText(
            QRectF(0, label_y, w, self.LABEL_H),
            Qt.AlignHCenter | Qt.AlignVCenter,
            self._label,
        )

        p.end()


# ======================= ЗАГОЛОВОК =======================
class StatusHeader(QWidget):
    """Маленький заголовок «SYSTEM» с пульсирующей точкой статуса."""

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self._status = 0.0
        self._blink = 0.5
        self._blink_dir = 1.0

        self.setFixedHeight(18)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._timer = QTimer(self)
        self._timer.setInterval(50)     # 20 fps — для пульсации
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_status(self, v):
        try:
            self._status = max(0.0, min(100.0, float(v)))
        except Exception:
            self._status = 0.0

    def apply_theme(self, colors):
        self.colors = colors
        self.update()

    def stop(self):
        try:
            self._timer.stop()
        except Exception:
            pass

    def _tick(self):
        self._blink += 0.045 * self._blink_dir
        if self._blink >= 1.0:
            self._blink = 1.0
            self._blink_dir = -1.0
        elif self._blink <= 0.35:
            self._blink = 0.35
            self._blink_dir = 1.0
        self.update()

    def _status_color(self):
        c = self.colors
        v = self._status
        if v >= 80:
            return QColor(c["DANGER"])
        if v >= 50:
            return QColor("#F9E2AF")
        return QColor(c["OK"])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Точка-индикатор
        dot_x = 3.0
        dot_y = h / 2.0
        dot_r = 2.5
        col = self._status_color()
        col.setAlphaF(self._blink)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)

        # Текст
        p.setPen(QColor(self.colors["SUBTEXT"]))
        f = QFont("Segoe UI", 7)
        f.setBold(True)
        f.setLetterSpacing(QFont.PercentageSpacing, 130)
        p.setFont(f)
        p.drawText(
            QRectF(dot_x + 5, 0, w - dot_x - 5, h),
            Qt.AlignLeft | Qt.AlignVCenter,
            "SYSTEM",
        )
        p.end()


# ======================= ГЛАВНЫЙ ВИДЖЕТ =======================
class SystemMonitorWidget(QWidget):
    """Заголовок + три кольцевых индикатора со sparkline.

    Ширина = 48 px, что в точности совпадает с шириной контента
    правого сайдбара (64 px − 8 px margin слева − 8 px margin справа).
    Благодаря этому виджет встаёт ровно по центру.
    """

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self._gpu_handle = None
        self._interval_ms = 2000

        # Пробуем ещё раз, если кто-то до нас выключил NVML
        global HAS_NVML, pynvml, _nvml_shutdown_done
        if not HAS_NVML:
            try:
                import pynvml as _pynvml
                _pynvml.nvmlInit()
                pynvml = _pynvml
                HAS_NVML = True
                _nvml_shutdown_done = False
            except Exception:
                pass

        if HAS_NVML:
            try:
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e:
                log.error(f"nvml handle: {e}")
                self._gpu_handle = None

        self._gpu_name = ""
        if self._gpu_handle is not None:
            try:
                raw = pynvml.nvmlDeviceGetName(self._gpu_handle)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                self._gpu_name = str(raw)
            except Exception:
                self._gpu_name = "GPU"

        self._cpu_phys_cores = 0
        self._cpu_log_cores = 0
        if HAS_PSUTIL:
            try:
                self._cpu_phys_cores = psutil.cpu_count(logical=False) or 0
                self._cpu_log_cores = psutil.cpu_count(logical=True) or 0
            except Exception:
                pass

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        self.header = StatusHeader(colors, self)
        lay.addWidget(self.header, 0, Qt.AlignHCenter)

        self.ring_cpu = RingIndicator("CPU", colors, self)
        self.ring_ram = RingIndicator("RAM", colors, self)
        self.ring_gpu = RingIndicator("GPU", colors, self)

        lay.addWidget(self.ring_cpu, 0, Qt.AlignHCenter)
        lay.addWidget(self.ring_ram, 0, Qt.AlignHCenter)
        lay.addWidget(self.ring_gpu, 0, Qt.AlignHCenter)

        if self._gpu_handle is None:
            self.ring_gpu.hide()

        # Ключевой момент: ширина = 48 (совпадает с контентом right_sidebar).
        self.setFixedWidth(48)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_stats)
        self._timer.start(self._interval_ms)
        QTimer.singleShot(300, self._update_stats)

        self.apply_theme(colors)

    # ---------- API ----------
    def set_interval(self, seconds):
        try:
            ms = max(1000, int(seconds) * 1000)
        except Exception:
            ms = 2000
        self._interval_ms = ms
        self._timer.start(ms)

    def apply_theme(self, colors):
        self.colors = colors
        self.setStyleSheet("background: transparent;")
        self.header.apply_theme(colors)
        self.ring_cpu.apply_theme(colors)
        self.ring_ram.apply_theme(colors)
        self.ring_gpu.apply_theme(colors)
        self.update()

    def has_gpu(self):
        return self._gpu_handle is not None

    def stop(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        try:
            self.header.stop()
            self.ring_cpu.stop()
            self.ring_ram.stop()
            self.ring_gpu.stop()
        except Exception:
            pass

    # ---------- Обновление значений ----------
    def _update_stats(self):
        if not HAS_PSUTIL:
            return

        cpu_val = 0.0
        ram_val = 0.0
        gpu_val = 0.0

        # ===== CPU =====
        try:
            cpu_val = psutil.cpu_percent(interval=None)
            self.ring_cpu.set_value(cpu_val)
        except Exception:
            pass

        cpu_details = {"title": "CPU"}
        try:
            freq = psutil.cpu_freq()
            if freq and freq.current:
                cpu_details["freq"] = f"{int(freq.current)} МГц"
        except Exception:
            pass
        if self._cpu_log_cores:
            if self._cpu_phys_cores:
                cpu_details["cores"] = (
                    f"{self._cpu_phys_cores} физ. / "
                    f"{self._cpu_log_cores} лог."
                )
            else:
                cpu_details["cores"] = f"{self._cpu_log_cores}"
        self.ring_cpu.set_details(cpu_details)

        # ===== RAM =====
        try:
            mem = psutil.virtual_memory()
            ram_val = mem.percent
            self.ring_ram.set_value(ram_val)

            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            ram_details = {
                "title": "RAM",
                "mem": f"{used_gb:.1f} / {total_gb:.1f} GB",
            }
            try:
                swap = psutil.swap_memory()
                if swap.total > 0:
                    s_used = swap.used / (1024 ** 3)
                    s_total = swap.total / (1024 ** 3)
                    ram_details["swap"] = (
                        f"{s_used:.1f} / {s_total:.1f} GB"
                    )
            except Exception:
                pass
            self.ring_ram.set_details(ram_details)
        except Exception:
            pass

        # ===== GPU =====
        if self._gpu_handle is not None:
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(
                    self._gpu_handle
                )
                gpu_val = float(util.gpu)
                self.ring_gpu.set_value(gpu_val)
            except Exception:
                pass

            gpu_details = {"title": self._gpu_name or "GPU"}
            try:
                mi = pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                used_mb = mi.used / (1024 * 1024)
                total_mb = mi.total / (1024 * 1024)
                gpu_details["vram"] = (
                    f"{used_mb:.0f} / {total_mb:.0f} MB"
                )
            except Exception:
                pass
            try:
                temp = pynvml.nvmlDeviceGetTemperature(
                    self._gpu_handle, 0
                )
                gpu_details["temp"] = f"{temp} °C"
            except Exception:
                pass
            try:
                clk = pynvml.nvmlDeviceGetClockInfo(self._gpu_handle, 0)
                if clk:
                    gpu_details["clock"] = f"{int(clk)} МГц"
            except Exception:
                pass
            self.ring_gpu.set_details(gpu_details)

        # ===== Заголовок =====
        values = [cpu_val, ram_val]
        if self._gpu_handle is not None:
            values.append(gpu_val)
        overall = max(values) if values else 0.0
        self.header.set_status(overall)


def is_supported():
    return {
        "psutil": HAS_PSUTIL,
        "gpu": HAS_NVML,
    }