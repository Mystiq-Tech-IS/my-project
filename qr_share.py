"""Диалог с QR-кодом для пресета.

Генерирует QR, содержащий JSON пресета (base64), плюс может показать
текстовые инструкции. Позволяет сохранить QR в PNG и скопировать
данные в буфер.
"""

import os
import json
import base64
import tempfile

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False
    qrcode = None

from dialogs import dialog_qss, show_info, show_error
from storage import log


def is_available():
    return HAS_QRCODE


def _make_qr_pixmap(data, size=380):
    """Генерирует QR-код, возвращает QPixmap."""
    if not HAS_QRCODE:
        return None
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size))

        # Сохраняем во временный PNG и читаем как QPixmap
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        img.save(tmp.name, "PNG")
        pix = QPixmap(tmp.name)
        try:
            os.remove(tmp.name)
        except Exception:
            pass
        return pix
    except Exception as e:
        log.error(f"make_qr: {e}")
        return None


def _encode_preset(preset):
    """Упаковывает пресет в компактную base64-строку."""
    try:
        # Мини-версия: имя, иконка, paths
        minimal = {
            "n": preset.get("name", ""),
            "i": preset.get("icon", "🚀"),
            "p": preset.get("paths", []),
        }
        raw = json.dumps(minimal, ensure_ascii=False, separators=(",", ":"))
        b = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
        return f"mylauncher://preset?v=1&d={b}"
    except Exception as e:
        log.error(f"encode preset: {e}")
        return ""


class QRShareDialog(QDialog):
    def __init__(self, parent, colors, preset):
        super().__init__(parent)
        self.colors = colors
        self.preset = preset

        self.setWindowTitle("Поделиться пресетом")
        self.setStyleSheet(dialog_qss(colors))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel(f"QR-код: «{preset.get('name', 'Без имени')}»")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(title)

        if not HAS_QRCODE:
            warn = QLabel(
                "Для работы нужна библиотека qrcode:\n\n"
                "    pip install qrcode[pil]\n\n"
                "После установки перезапусти лаунчер."
            )
            warn.setStyleSheet(
                f"color: {colors['DANGER']}; font-size: 12px;"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)
            close = QPushButton("Закрыть")
            close.setProperty("accent", True)
            close.clicked.connect(self.accept)
            layout.addWidget(close)
            return

        # Данные QR
        data = _encode_preset(preset)
        self._data = data

        hint = QLabel(
            "Наведи камеру телефона — данные пресета попадут в буфер.\n"
            "Либо сохрани PNG и передай другу."
        )
        hint.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # QR-превью
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignCenter)
        qr_label.setMinimumHeight(400)
        qr_label.setStyleSheet(
            f"background-color: white; border-radius: 12px; padding: 10px;"
        )

        pix = _make_qr_pixmap(data, 380)
        if pix:
            qr_label.setPixmap(pix)
        else:
            qr_label.setText("Не удалось сгенерировать QR")
        layout.addWidget(qr_label)

        # Кнопки
        btns = QHBoxLayout()
        btns.setSpacing(8)

        save_btn = QPushButton("  Сохранить PNG")
        save_btn.clicked.connect(self._save_png)
        btns.addWidget(save_btn)

        copy_btn = QPushButton("  Копировать данные")
        copy_btn.clicked.connect(self._copy_data)
        btns.addWidget(copy_btn)

        btns.addStretch()
        close_btn = QPushButton("Закрыть")
        close_btn.setProperty("accent", True)
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _save_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить QR",
            f"preset_{self.preset.get('name', 'qr')}.png",
            "PNG (*.png)"
        )
        if not path:
            return
        pix = _make_qr_pixmap(self._data, 800)
        if pix is None:
            show_error(self, self.colors, "Ошибка",
                       "Не удалось сгенерировать QR")
            return
        try:
            pix.save(path, "PNG")
            show_info(self, self.colors, "Сохранено", f"QR сохранён:\n{path}")
        except Exception as e:
            show_error(self, self.colors, "Ошибка", str(e))

    def _copy_data(self):
        try:
            from PySide6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            cb.setText(self._data)
            show_info(self, self.colors, "Скопировано",
                      "Данные пресета в буфере обмена.")
        except Exception as e:
            show_error(self, self.colors, "Ошибка", str(e))


def decode_preset_data(data_string):
    """Обратная операция — вернуть dict пресета или None."""
    try:
        if not data_string.startswith("mylauncher://preset?"):
            return None
        # Извлекаем параметр d=
        idx = data_string.find("d=")
        if idx < 0:
            return None
        b = data_string[idx + 2:]
        # Убираем возможные & после
        amp = b.find("&")
        if amp >= 0:
            b = b[:amp]
        raw = base64.urlsafe_b64decode(b.encode("ascii")).decode("utf-8")
        minimal = json.loads(raw)
        return {
            "name": minimal.get("n", "Без названия"),
            "icon": minimal.get("i", "🚀"),
            "paths": minimal.get("p", []),
            "description": "",
        }
    except Exception as e:
        log.error(f"decode_preset: {e}")
        return None