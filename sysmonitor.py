"""Виджет мониторинга системы для правого сайдбара.

Показывает CPU / RAM / GPU в компактном виде.
GPU работает только для NVIDIA и если установлен nvidia-ml-py.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

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


class SystemMonitorWidget(QWidget):
    """Компактный виджет: три строки CPU/RAM/GPU с процентами."""

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self._gpu_handle = None
        self._interval_ms = 2000

        # --- Проверка GPU ---
        if HAS_NVML:
            try:
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e:
                log.error(f"nvml handle: {e}")
                self._gpu_handle = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignCenter)

        self.lbl_cpu = self._make_label("CPU --")
        self.lbl_ram = self._make_label("RAM --")
        self.lbl_gpu = self._make_label("GPU --")

        lay.addWidget(self.lbl_cpu)
        lay.addWidget(self.lbl_ram)
        if self._gpu_handle is not None:
            lay.addWidget(self.lbl_gpu)
        else:
            self.lbl_gpu.hide()

        self.setFixedWidth(56)

        # --- Таймер ---
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_stats)
        self._timer.start(self._interval_ms)
        # Первое обновление сразу
        QTimer.singleShot(300, self._update_stats)

        self.apply_theme(colors)

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        f = QFont("Segoe UI", 8)
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    def set_interval(self, seconds):
        """Переустановить период обновления."""
        try:
            ms = max(1000, int(seconds) * 1000)
        except Exception:
            ms = 2000
        self._interval_ms = ms
        self._timer.start(ms)

    def apply_theme(self, colors):
        self.colors = colors
        c = colors
        # Фон — прозрачный, цвет текста по уровню
        self.setStyleSheet("background: transparent;")
        self._refresh_colors()

    def _refresh_colors(self):
        c = self.colors
        for lbl, val in (
            (self.lbl_cpu, getattr(self, "_cpu", 0.0)),
            (self.lbl_ram, getattr(self, "_ram", 0.0)),
            (self.lbl_gpu, getattr(self, "_gpu", 0.0)),
        ):
            if not lbl.isVisible():
                continue
            if val >= 80:
                col = c["DANGER"]
            elif val >= 50:
                col = "#F9E2AF"
            else:
                col = c["OK"]
            lbl.setStyleSheet(
                f"color: {col}; background: transparent;"
            )

    # ================== ОБНОВЛЕНИЕ ==================
    def _update_stats(self):
        if not HAS_PSUTIL:
            self.lbl_cpu.setText("CPU —")
            self.lbl_ram.setText("RAM —")
            return

        # CPU
        try:
            cpu = psutil.cpu_percent(interval=None)
            self._cpu = cpu
            self.lbl_cpu.setText(f"CPU {int(cpu)}%")
        except Exception:
            self.lbl_cpu.setText("CPU —")

        # RAM
        try:
            mem = psutil.virtual_memory()
            ram = mem.percent
            self._ram = ram
            self.lbl_ram.setText(f"RAM {int(ram)}%")
        except Exception:
            self.lbl_ram.setText("RAM —")

        # GPU (NVIDIA)
        if self._gpu_handle is not None:
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                gpu = util.gpu
                self._gpu = gpu
                self.lbl_gpu.setText(f"GPU {int(gpu)}%")
            except Exception:
                self.lbl_gpu.setText("GPU —")

        self._refresh_colors()

    def has_gpu(self):
        return self._gpu_handle is not None

    def stop(self):
        try:
            self._timer.stop()
        except Exception:
            pass


# ---------- Вызывается один раз при старте лаунчера ----------
def is_supported():
    """Есть ли psutil (обязателен) и, опционально, GPU."""
    return {
        "psutil": HAS_PSUTIL,
        "gpu": HAS_NVML,
    }