"""Диалоги: ошибки, ввод текста, выбор категории, подтверждение, hotkey."""

from PySide6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, QLineEdit,
    QHBoxLayout, QPushButton, QComboBox, QKeySequenceEdit
)


def dialog_qss(c):
    return f"""
        QDialog, QMessageBox {{ background-color: {c['BG']}; }}
        QLabel {{ color: {c['TEXT']}; font-size: 14px; background: transparent; }}
        QLineEdit, QComboBox, QKeySequenceEdit {{
            background-color: {c['CARD']};
            color: {c['TEXT']};
            border: none;
            border-radius: 10px;
            padding: 10px 14px;
            font-size: 14px;
        }}
        QLineEdit:focus, QComboBox:focus, QKeySequenceEdit:focus {{
            background-color: {c['CARD_HOVER']};
        }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox QAbstractItemView {{
            background-color: {c['CARD']};
            color: {c['TEXT']};
            border: 1px solid {c['CARD_HOVER']};
            border-radius: 8px;
            selection-background-color: {c['CARD_HOVER']};
            outline: none;
        }}
        QPushButton {{
            background-color: {c['CARD']};
            color: {c['TEXT']};
            border: none;
            border-radius: 10px;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: bold;
            min-width: 80px;
        }}
        QPushButton:hover {{ background-color: {c['CARD_HOVER']}; }}
        QPushButton[accent="true"] {{
            background-color: {c['ACCENT']};
            color: {c['BG']};
        }}
        QPushButton[accent="true"]:hover {{ background-color: {c['ACCENT_HOV']}; }}
        QPushButton[danger="true"] {{
            background-color: {c['DANGER']};
            color: {c['BG']};
        }}
    """


def _box(parent, colors, icon, title, message):
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStyleSheet(dialog_qss(colors))
    return box


def show_error(parent, colors, title, message):
    _box(parent, colors, QMessageBox.Critical, title, message).exec()


def show_info(parent, colors, title, message):
    _box(parent, colors, QMessageBox.Information, title, message).exec()


def ask_text(parent, colors, title, label, default=""):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setStyleSheet(dialog_qss(colors))
    dlg.setMinimumWidth(380)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)

    layout.addWidget(QLabel(label))
    edit = QLineEdit(default)
    layout.addWidget(edit)

    buttons = QHBoxLayout()
    buttons.addStretch()

    cancel = QPushButton("Отмена")
    cancel.clicked.connect(dlg.reject)
    buttons.addWidget(cancel)

    ok = QPushButton("ОК")
    ok.setProperty("accent", True)
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    buttons.addWidget(ok)

    layout.addLayout(buttons)

    if dlg.exec() == QDialog.Accepted:
        return edit.text().strip(), True
    return "", False


def ask_category(parent, colors, title, label, options, current="other"):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setStyleSheet(dialog_qss(colors))
    dlg.setMinimumWidth(380)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)

    layout.addWidget(QLabel(label))

    combo = QComboBox()
    for key, name in options:
        combo.addItem(name, key)
    for i in range(combo.count()):
        if combo.itemData(i) == current:
            combo.setCurrentIndex(i)
            break
    layout.addWidget(combo)

    buttons = QHBoxLayout()
    buttons.addStretch()

    cancel = QPushButton("Отмена")
    cancel.clicked.connect(dlg.reject)
    buttons.addWidget(cancel)

    ok = QPushButton("ОК")
    ok.setProperty("accent", True)
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    buttons.addWidget(ok)

    layout.addLayout(buttons)

    if dlg.exec() == QDialog.Accepted:
        return combo.currentData(), True
    return current, False


def ask_already_running(parent, colors, app_name, allow_switch=True):
    """
    Возвращает: 'switch' | 'close' | 'rerun' | 'cancel'.
    allow_switch=False убирает кнопку «Переключиться».
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle("Уже запущено")
    dlg.setStyleSheet(dialog_qss(colors))
    dlg.setMinimumWidth(520)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)

    lbl = QLabel(f"Программа «{app_name}» уже запущена.\nЧто сделать?")
    lbl.setWordWrap(True)
    layout.addWidget(lbl)

    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    buttons.addStretch()

    cancel = QPushButton("Отмена")
    cancel.clicked.connect(
        lambda: (setattr(dlg, "_result", "cancel"), dlg.reject())
    )
    buttons.addWidget(cancel)

    if allow_switch:
        switch = QPushButton("Переключиться")
        switch.clicked.connect(
            lambda: (setattr(dlg, "_result", "switch"), dlg.accept())
        )
        buttons.addWidget(switch)

    rerun = QPushButton("Перезапустить")
    rerun.clicked.connect(
        lambda: (setattr(dlg, "_result", "rerun"), dlg.accept())
    )
    buttons.addWidget(rerun)

    close_btn = QPushButton("Закрыть")
    close_btn.setProperty("danger", True)
    close_btn.setDefault(True)
    close_btn.clicked.connect(
        lambda: (setattr(dlg, "_result", "close"), dlg.accept())
    )
    buttons.addWidget(close_btn)

    layout.addLayout(buttons)

    dlg.exec()
    return getattr(dlg, "_result", "cancel")


def ask_confirm(parent, colors, title, message,
                ok_text="Да", cancel_text="Отмена"):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setStyleSheet(dialog_qss(colors))
    dlg.setMinimumWidth(420)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)

    lbl = QLabel(message)
    lbl.setWordWrap(True)
    layout.addWidget(lbl)

    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    buttons.addStretch()

    cancel = QPushButton(cancel_text)
    cancel.clicked.connect(dlg.reject)
    buttons.addWidget(cancel)

    ok = QPushButton(ok_text)
    ok.setProperty("accent", True)
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    buttons.addWidget(ok)

    layout.addLayout(buttons)

    return dlg.exec() == QDialog.Accepted


def ask_hotkey(parent, colors, app_name, current=""):
    dlg = QDialog(parent)
    dlg.setWindowTitle("Горячая клавиша")
    dlg.setStyleSheet(dialog_qss(colors))
    dlg.setMinimumWidth(420)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)

    lbl = QLabel(
        f"Назначьте горячую клавишу для «{app_name}».\n"
        "Нажмите комбинацию в поле ниже."
    )
    lbl.setWordWrap(True)
    layout.addWidget(lbl)

    edit = QKeySequenceEdit()
    if current:
        edit.setKeySequence(current)
    layout.addWidget(edit)

    hint = QLabel("Пример: Ctrl+Alt+S. Работает глобально из любой программы.")
    hint.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 11px;")
    hint.setWordWrap(True)
    layout.addWidget(hint)

    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    buttons.addStretch()

    cancel = QPushButton("Отмена")
    cancel.clicked.connect(dlg.reject)
    buttons.addWidget(cancel)

    clear = QPushButton("Убрать")
    clear.clicked.connect(lambda: (edit.clear(), dlg.accept()))
    buttons.addWidget(clear)

    ok = QPushButton("ОК")
    ok.setProperty("accent", True)
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    buttons.addWidget(ok)

    layout.addLayout(buttons)

    if dlg.exec() == QDialog.Accepted:
        seq = edit.keySequence().toString()
        seq = seq.replace("Ctrl", "ctrl").replace("Alt", "alt")
        seq = seq.replace("Shift", "shift").replace("Meta", "windows")
        seq = seq.lower()
        return seq, True
    return "", False