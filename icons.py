"""Извлечение иконок: своя картинка → иконка .exe → заглушка с буквой."""

import os
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtCore import QFileInfo, Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont

_provider = QFileIconProvider()
_cache = {}


def get_icon(app, size=48):
    path = app.get("path", "")
    custom = app.get("custom_icon", "")
    key = (path, custom, size)
    if key in _cache:
        return _cache[key]

    pix = None

    if custom and os.path.exists(custom):
        try:
            p = QPixmap(custom)
            if not p.isNull():
                pix = p.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception:
            pix = None

    if pix is None and path and os.path.exists(path):
        try:
            icon = _provider.icon(QFileInfo(path))
            if not icon.isNull():
                pix = icon.pixmap(size, size)
        except Exception:
            pix = None

    if pix is None or pix.isNull():
        pix = _make_placeholder(path, size)

    _cache[key] = pix
    return pix


def _make_placeholder(path, size):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#45475A"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, 12, 12)
    p.setPen(QColor("#CDD6F4"))
    p.setFont(QFont("Segoe UI", int(size * 0.45), QFont.Bold))

    letter = "?"
    if path:
        name = os.path.splitext(os.path.basename(path))[0]
        if name:
            letter = name[0].upper()
    p.drawText(pix.rect(), Qt.AlignCenter, letter)
    p.end()
    return pix


def clear_cache():
    _cache.clear()