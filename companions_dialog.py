"""Диалог управления правилами «автозапуск спутников»."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QCheckBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from dialogs import dialog_qss, ask_confirm
from icons import get_icon
from storage import log


class CompanionRuleDialog(QDialog):
    """Редактор одного правила."""

    def __init__(self, parent, colors, apps, rule=None):
        super().__init__(parent)
        self.colors = colors
        self.apps = apps
        self.rule = dict(rule) if rule else {
            "trigger": "",
            "launch": [],
            "enabled": True,
            "only_if_not_running": True,
        }
        self.result_rule = None

        self.setWindowTitle("Правило запуска")
        self.setStyleSheet(dialog_qss(colors))
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Правило автозапуска")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(title)

        hint = QLabel(
            "Когда запускается триггер — автоматически запускаются "
            "выбранные спутники."
        )
        hint.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Триггер
        layout.addWidget(QLabel("Когда запускается:"))
        self.trigger_combo = QComboBox()
        for app in self.apps:
            pix = get_icon(app, 20)
            ico = QIcon(pix) if pix else QIcon()
            self.trigger_combo.addItem(ico, app.get("name", ""), app.get("path", ""))
        for i in range(self.trigger_combo.count()):
            if self.trigger_combo.itemData(i) == self.rule.get("trigger"):
                self.trigger_combo.setCurrentIndex(i)
                break
        layout.addWidget(self.trigger_combo)

        # Спутники
        layout.addWidget(QLabel("Запускать вместе с ним:"))
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(20, 20))
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {colors['BG_ALT']};
                color: {colors['TEXT']};
                border: 1px solid {colors['BORDER']};
                border-radius: 10px;
                padding: 6px;
                font-size: 13px;
                outline: none;
            }}
            QListWidget::item {{ padding: 6px; border-radius: 6px; }}
            QListWidget::item:hover {{ background-color: {colors['CARD_HOVER']}; }}
        """)

        trigger_path = self.rule.get("trigger", "")
        current_launch = set(self.rule.get("launch", []))
        for app in self.apps:
            path = app.get("path", "")
            if path == trigger_path:
                continue
            item = QListWidgetItem(app.get("name", ""))
            item.setData(Qt.ItemDataRole.UserRole, path)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            if path in current_launch:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            pix = get_icon(app, 20)
            if pix:
                item.setIcon(QIcon(pix))
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget, 1)

        # Галочки
        self.enabled_check = QCheckBox("Правило включено")
        self.enabled_check.setChecked(self.rule.get("enabled", True))
        layout.addWidget(self.enabled_check)

        self.not_running_check = QCheckBox(
            "Не запускать повторно, если уже запущено"
        )
        self.not_running_check.setChecked(
            self.rule.get("only_if_not_running", True)
        )
        layout.addWidget(self.not_running_check)

        # Кнопки
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        ok = QPushButton("Сохранить")
        ok.setProperty("accent", True)
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def _save(self):
        trigger = self.trigger_combo.currentData()
        if not trigger:
            return
        launch = []
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                launch.append(it.data(Qt.ItemDataRole.UserRole))
        if not launch:
            return

        self.rule["trigger"] = trigger
        self.rule["launch"] = launch
        self.rule["enabled"] = self.enabled_check.isChecked()
        self.rule["only_if_not_running"] = self.not_running_check.isChecked()
        self.result_rule = self.rule
        self.accept()


class CompanionsDialog(QDialog):
    """Список правил."""

    def __init__(self, parent, colors, apps, companions):
        super().__init__(parent)
        self.colors = colors
        self.apps = apps
        self.companions = list(companions)
        self.changed = False

        self.setWindowTitle("Автозапуск спутников")
        self.setStyleSheet(dialog_qss(colors))
        self.setMinimumWidth(560)
        self.resize(600, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("🚀 Автозапуск спутников")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(title)

        hint = QLabel(
            "Правило запускает программы-спутники автоматически, "
            "когда запускается основная программа.\n"
            "Например: запустил Steam → автоматом загрузился Discord."
        )
        hint.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.lw = QListWidget()
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
            QListWidget::item {{ padding: 10px; border-radius: 8px; }}
            QListWidget::item:selected {{
                background-color: {colors['ACCENT_SOFT']};
                color: {colors['ACCENT']};
            }}
        """)
        self._refresh()
        layout.addWidget(self.lw, 1)

        mgmt = QHBoxLayout()
        mgmt.setSpacing(8)
        add_btn = QPushButton("+ Создать")
        edit_btn = QPushButton("✏ Изменить")
        del_btn = QPushButton("🗑 Удалить")
        mgmt.addWidget(add_btn)
        mgmt.addWidget(edit_btn)
        mgmt.addWidget(del_btn)
        mgmt.addStretch()
        layout.addLayout(mgmt)

        bottom = QHBoxLayout()
        bottom.addStretch()
        close = QPushButton("Закрыть")
        close.setProperty("accent", True)
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        add_btn.clicked.connect(self._add)
        edit_btn.clicked.connect(self._edit)
        del_btn.clicked.connect(self._delete)
        self.lw.itemDoubleClicked.connect(lambda _: self._edit())

    def _app_name(self, path):
        for a in self.apps:
            if a.get("path") == path:
                return a.get("name", path)
        return path

    def _refresh(self):
        self.lw.clear()
        if not self.companions:
            it = QListWidgetItem("Правил пока нет")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.lw.addItem(it)
            return
        for rule in self.companions:
            trigger = self._app_name(rule.get("trigger", ""))
            launch = ", ".join(
                self._app_name(p) for p in rule.get("launch", [])
            )
            status = "✓" if rule.get("enabled", True) else "✗"
            text = f"{status}  Когда: {trigger}   →   Запустить: {launch}"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, rule)
            self.lw.addItem(it)

    def _add(self):
        dlg = CompanionRuleDialog(self, self.colors, self.apps)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_rule:
            self.companions.append(dlg.result_rule)
            self.changed = True
            self._refresh()

    def _edit(self):
        it = self.lw.currentItem()
        if not it:
            return
        rule = it.data(Qt.ItemDataRole.UserRole)
        if not isinstance(rule, dict):
            return
        dlg = CompanionRuleDialog(self, self.colors, self.apps, rule)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_rule:
            idx = self.companions.index(rule)
            self.companions[idx] = dlg.result_rule
            self.changed = True
            self._refresh()

    def _delete(self):
        it = self.lw.currentItem()
        if not it:
            return
        rule = it.data(Qt.ItemDataRole.UserRole)
        if not isinstance(rule, dict):
            return
        if not ask_confirm(self, self.colors, "Удалить правило",
                           "Удалить выбранное правило?", ok_text="Удалить"):
            return
        self.companions.remove(rule)
        self.changed = True
        self._refresh()