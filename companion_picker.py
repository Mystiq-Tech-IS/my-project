"""Диалог выбора спутников для конкретной программы (с FA-иконками)."""

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False
    qta = None

from dialogs import dialog_qss
from icons import get_icon
from storage import log


def _fa_icon(name, color):
    if not HAS_QTAWESOME:
        return QIcon()
    try:
        return qta.icon(name, color=color)
    except Exception:
        return QIcon()


def _fa_pixmap(name, size, color):
    if not HAS_QTAWESOME:
        return None
    try:
        return qta.icon(name, color=color).pixmap(size, size)
    except Exception:
        return None


class CompanionPickerDialog(QDialog):
    """Отметьте, какие программы запускать вместе с этой."""

    def __init__(self, parent, colors, apps, current_path, companions):
        super().__init__(parent)
        self.colors = colors
        self.apps = apps
        self.current_path = current_path
        self.companions = list(companions)
        self.result_companions = None

        self.setWindowTitle("Спутники запуска")
        self.setStyleSheet(dialog_qss(colors))
        self.setMinimumWidth(560)
        self.resize(600, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # ===== Заголовок с FA-иконкой =====
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        title_icon = QLabel()
        title_icon.setFixedSize(24, 24)
        pix = _fa_pixmap("fa5s.link", 22, colors["ACCENT"])
        if pix:
            title_icon.setPixmap(pix)
        title_row.addWidget(title_icon)

        title = QLabel("Спутники запуска")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        hint = QLabel(
            "Отметьте программы, которые будут автоматически запускаться "
            "вместе с этой.\nМожно добавить и свою программу, которой "
            "нет в списке лаунчера."
        )
        hint.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.lw = QListWidget()
        self.lw.setIconSize(QSize(24, 24))
        self.lw.setStyleSheet(f"""
            QListWidget {{
                background-color: {colors['BG_ALT']};
                color: {colors['TEXT']};
                border: 1px solid {colors['BORDER']};
                border-radius: 12px;
                padding: 6px;
                font-size: 13px;
                outline: none;
            }}
            QListWidget::item {{ padding: 8px; border-radius: 6px; }}
            QListWidget::item:hover {{ background-color: {colors['CARD_HOVER']}; }}
        """)
        layout.addWidget(self.lw, 1)

        self._populate()

        mgmt = QHBoxLayout()
        mgmt.setSpacing(8)
        add_btn = QPushButton("  Добавить свою программу (.exe)")
        add_btn.setIcon(_fa_icon("fa5s.plus", colors["ACCENT"]))
        add_btn.clicked.connect(self._add_external)
        mgmt.addWidget(add_btn)
        mgmt.addStretch()
        layout.addLayout(mgmt)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("  Сохранить")
        ok.setIcon(_fa_icon("fa5s.check", colors["BG"]))
        ok.setProperty("accent", True)
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _populate(self):
        self.lw.clear()
        known_paths = set()
        for app in self.apps:
            p = app.get("path", "")
            if not p or p == self.current_path:
                continue
            known_paths.add(p)
            item = QListWidgetItem(app.get("name", ""))
            item.setData(Qt.ItemDataRole.UserRole, p)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            if p in self.companions:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            pix = get_icon(app, 24)
            if pix:
                item.setIcon(QIcon(pix))
            self.lw.addItem(item)

        for path in self.companions:
            if path in known_paths or path == self.current_path:
                continue
            item = QListWidgetItem(f"[внешняя]  {os.path.basename(path)}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            item.setCheckState(Qt.CheckState.Checked)
            try:
                pix = get_icon({"path": path, "custom_icon": ""}, 24)
                if pix:
                    item.setIcon(QIcon(pix))
            except Exception:
                pass
            self.lw.addItem(item)

    def _add_external(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите программу-спутник", "",
            "Программы (*.exe *.lnk *.bat *.cmd);;Все файлы (*.*)"
        )
        if not path:
            return
        for i in range(self.lw.count()):
            it = self.lw.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == path:
                it.setCheckState(Qt.CheckState.Checked)
                return
        item = QListWidgetItem(f"[внешняя]  {os.path.basename(path)}")
        item.setData(Qt.ItemDataRole.UserRole, path)
        flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
        item.setFlags(flags)
        item.setCheckState(Qt.CheckState.Checked)
        try:
            pix = get_icon({"path": path, "custom_icon": ""}, 24)
            if pix:
                item.setIcon(QIcon(pix))
        except Exception:
            pass
        self.lw.addItem(item)

    def _save(self):
        result = []
        for i in range(self.lw.count()):
            it = self.lw.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                result.append(it.data(Qt.ItemDataRole.UserRole))
        self.result_companions = result
        self.accept()