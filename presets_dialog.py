"""Диалог создания/редактирования пресета (с FA-иконками и QR)."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QComboBox,
    QMessageBox
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


PRESET_ICONS = [
    "🚀", "💼", "🎮", "🎬", "🎵", "📚", "💻", "🎨",
    "🎯", "⚡", "🔥", "⭐", "🎓", "🌐", "📊", "🎧",
]


class PresetsDialog(QDialog):
    """Редактор одного пресета."""

    def __init__(self, parent, colors, apps, preset=None):
        super().__init__(parent)
        self.colors = colors
        self.apps = apps
        self.preset = dict(preset) if preset else {
            "name": "",
            "icon": "🚀",
            "paths": [],
            "description": "",
        }
        self.result_preset = None

        self.setWindowTitle("Пресет запуска")
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
            QListWidget::item:selected {{
                background-color: {colors['ACCENT_SOFT']};
                color: {colors['ACCENT']};
            }}
            QListWidget::item:hover {{ background-color: {colors['CARD_HOVER']}; }}
        """)
        self.resize(620, 660)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Заголовок
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        title_icon = QLabel()
        title_icon.setFixedSize(24, 24)
        pix = _fa_pixmap("fa5s.rocket", 22, colors["ACCENT"])
        if pix:
            title_icon.setPixmap(pix)
        title_row.addWidget(title_icon)

        title = QLabel("Пресет запуска")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        title_row.addWidget(title)
        title_row.addStretch()

        # Кнопка QR — только если пресет уже существует
        self.qr_btn = QPushButton("  Поделиться QR")
        self.qr_btn.setIcon(_fa_icon("fa5s.qrcode", colors["TEXT"]))
        self.qr_btn.clicked.connect(self._share_qr)
        title_row.addWidget(self.qr_btn)

        layout.addLayout(title_row)

        # Название
        layout.addWidget(QLabel("Название:"))
        self.name_edit = QLineEdit(self.preset.get("name", ""))
        self.name_edit.setPlaceholderText("Например: Работа")
        layout.addWidget(self.name_edit)

        # Иконка
        layout.addWidget(QLabel("Иконка:"))
        icon_row = QHBoxLayout()
        icon_row.setSpacing(6)
        self.icon_btns = {}
        for ico in PRESET_ICONS:
            btn = QPushButton(ico)
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=ico: self._select_icon(i))
            icon_row.addWidget(btn)
            self.icon_btns[ico] = btn
        icon_row.addStretch()
        layout.addLayout(icon_row)
        self._refresh_icon_buttons()

        # Программы
        layout.addWidget(QLabel("Программы в пресете:"))
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(24, 24))
        layout.addWidget(self.list_widget, 1)
        self._populate_list()

        # Кнопки управления
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        add_btn = QPushButton("  Добавить программу")
        add_btn.setIcon(_fa_icon("fa5s.plus", colors["ACCENT"]))
        add_btn.clicked.connect(self._add_app)
        ctrl_row.addWidget(add_btn)

        remove_btn = QPushButton("  Убрать из пресета")
        remove_btn.setIcon(_fa_icon("fa5s.minus", colors["DANGER"]))
        remove_btn.clicked.connect(self._remove_selected)
        ctrl_row.addWidget(remove_btn)

        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Основные кнопки
        layout.addSpacing(6)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()

        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        save = QPushButton("  Сохранить")
        save.setIcon(_fa_icon("fa5s.check", colors["BG"]))
        save.setProperty("accent", True)
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(save)

        layout.addLayout(buttons)

    # ---------------- QR ----------------
    def _share_qr(self):
        # Собираем текущее состояние из полей — чтобы QR содержал актуальные данные
        temp = {
            "name": self.name_edit.text().strip() or "Без имени",
            "icon": self.preset.get("icon", "🚀"),
            "paths": list(self.preset.get("paths", [])),
            "description": self.preset.get("description", ""),
        }
        try:
            from qr_share import QRShareDialog, is_available
        except Exception as e:
            log.error(f"qr_share import: {e}")
            return
        if not is_available():
            # Всё равно покажем диалог — он объяснит, что нужно установить
            pass
        dlg = QRShareDialog(self, self.colors, temp)
        dlg.exec()

    # ---------------- Иконки ----------------
    def _select_icon(self, ico):
        self.preset["icon"] = ico
        self._refresh_icon_buttons()

    def _refresh_icon_buttons(self):
        current = self.preset.get("icon", "🚀")
        for ico, btn in self.icon_btns.items():
            selected = (ico == current)
            border = self.colors["ACCENT"] if selected else self.colors["BORDER"]
            bw = 2 if selected else 1
            bg = self.colors["ACCENT_SOFT"] if selected else self.colors["CARD"]
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {self.colors['TEXT']};
                    border: {bw}px solid {border};
                    border-radius: 10px;
                    font-size: 18px;
                }}
            """)

    # ---------------- Список ----------------
    def _find_app_by_path(self, path):
        for a in self.apps:
            if a.get("path") == path:
                return a
        return None

    def _populate_list(self):
        self.list_widget.clear()
        for path in self.preset.get("paths", []):
            app = self._find_app_by_path(path)
            name = app.get("name") if app else f"(не найдено) {path}"
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            if app:
                pix = get_icon(app, 24)
                if pix:
                    item.setIcon(QIcon(pix))
            self.list_widget.addItem(item)

    def _add_app(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Выберите программы")
        dlg.setStyleSheet(self.styleSheet())
        dlg.setMinimumWidth(480)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Отметьте программы:"))

        lw = QListWidget()
        lw.setIconSize(QSize(24, 24))
        current_paths = set(self.preset.get("paths", []))

        for app in self.apps:
            item = QListWidgetItem(app.get("name", ""))
            item.setData(Qt.ItemDataRole.UserRole, app.get("path", ""))
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            if app.get("path") in current_paths:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            pix = get_icon(app, 24)
            if pix:
                item.setIcon(QIcon(pix))
            lw.addItem(item)

        layout.addWidget(lw, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(dlg.reject)
        btns.addWidget(cancel)
        ok = QPushButton("ОК")
        ok.setProperty("accent", True)
        ok.setDefault(True)
        ok.clicked.connect(dlg.accept)
        btns.addWidget(ok)
        layout.addLayout(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_paths = []
            for i in range(lw.count()):
                it = lw.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    new_paths.append(it.data(Qt.ItemDataRole.UserRole))
            self.preset["paths"] = new_paths
            self._populate_list()

    def _remove_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path in self.preset.get("paths", []):
            self.preset["paths"].remove(path)
        self._populate_list()

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название пресета")
            return
        self.preset["name"] = name
        self.preset["icon"] = self.preset.get("icon", "🚀")
        self.preset["description"] = self.preset.get("description", "")
        self.result_preset = self.preset
        self.accept()