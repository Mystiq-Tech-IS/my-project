"""Диалог импорта программ из меню Пуск, Steam, Epic и рабочего стола."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QComboBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from dialogs import dialog_qss
from icons import get_icon
from config import CATEGORIES
from storage import log


class ImportDialog(QDialog):
    def __init__(self, parent, colors, candidates, existing_paths):
        super().__init__(parent)
        self.colors = colors
        self.candidates = candidates
        self.existing = existing_paths
        self.selected = []
        self.chosen_category = "other"

        self.setWindowTitle("Импорт программ")
        self.setStyleSheet(dialog_qss(colors) + f"""
            QListWidget {{
                background-color: {colors['BG_ALT']};
                color: {colors['TEXT']};
                border: 1px solid {colors['BORDER']};
                border-radius: 12px;
                padding: 6px;
                outline: none;
            }}
            QListWidget::item {{ padding: 8px 10px; border-radius: 8px; }}
            QListWidget::item:selected {{ background-color: {colors['CARD_HOVER']}; }}
            QListWidget::item:hover {{ background-color: {colors['CARD']}; }}
        """)
        self.resize(720, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Импорт программ")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(title)

        hint = QLabel(
            "Отметьте программы галочками, выберите категорию "
            "и нажмите «Импортировать»."
        )
        hint.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск...")
        self.search.textChanged.connect(self._apply_filter)
        top.addWidget(self.search, 1)

        self.source_combo = QComboBox()
        self.source_combo.addItem("Все источники", "all")
        self.source_combo.addItem("Меню Пуск", "start_menu")
        self.source_combo.addItem("Рабочий стол", "desktop")
        self.source_combo.addItem("Steam", "steam")
        self.source_combo.addItem("Epic Games", "epic")
        self.source_combo.currentIndexChanged.connect(self._apply_filter)
        top.addWidget(self.source_combo)

        layout.addLayout(top)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(32, 32))
        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget, 1)

        self._populate()

        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        cat_label = QLabel("Категория:")
        cat_label.setStyleSheet(f"color: {colors['TEXT']}; font-size: 13px;")
        bottom.addWidget(cat_label)

        self.category_combo = QComboBox()
        for key, (name, _) in CATEGORIES.items():
            if key in ("all", "recent"):
                continue
            self.category_combo.addItem(name, key)
        bottom.addWidget(self.category_combo)

        bottom.addStretch()

        self.counter = QLabel("Выбрано: 0")
        self.counter.setStyleSheet(
            f"color: {colors['SUBTEXT']}; font-size: 13px;"
        )
        bottom.addWidget(self.counter)

        layout.addLayout(bottom)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        btn_all = QPushButton("Все")
        btn_all.clicked.connect(lambda: self._set_all_visible(True))
        buttons.addWidget(btn_all)

        btn_none = QPushButton("Ничего")
        btn_none.clicked.connect(lambda: self._set_all_visible(False))
        buttons.addWidget(btn_none)

        buttons.addStretch()

        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        ok = QPushButton("Импортировать")
        ok.setProperty("accent", True)
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        buttons.addWidget(ok)

        layout.addLayout(buttons)

    def _populate(self):
        for c in self.candidates:
            item = QListWidgetItem()
            name = c["name"]
            if c["path"] in self.existing:
                name += "   (уже добавлено)"
            item.setText(name)
            item.setData(Qt.ItemDataRole.UserRole, c)
            flags = item.flags()
            flags |= Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            item.setCheckState(Qt.CheckState.Unchecked)
            try:
                pix = get_icon({"path": c["path"], "custom_icon": ""}, 32)
                if pix:
                    item.setIcon(QIcon(pix))
            except Exception:
                pass
            self.list_widget.addItem(item)

    def _on_item_changed(self, item):
        n = 0
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                n += 1
        self.counter.setText(f"Выбрано: {n}")

    def _set_all_visible(self, state):
        target = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.isHidden():
                continue
            item.setCheckState(target)

    def _apply_filter(self):
        text = self.search.text().lower().strip()
        source = self.source_combo.currentData()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            c = item.data(Qt.ItemDataRole.UserRole)
            if not c:
                continue
            match_text = text in c["name"].lower()
            match_source = (source == "all") or (c["source"] == source)
            item.setHidden(not (match_text and match_source))

    def _accept(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                c = item.data(Qt.ItemDataRole.UserRole)
                if c:
                    selected.append(c)
        if not selected:
            self.counter.setText("Ничего не выбрано")
            return
        self.selected = selected
        self.chosen_category = self.category_combo.currentData()
        self.accept()