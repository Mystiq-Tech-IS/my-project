"""Быстрый лаунчер в стиле Spotlight: всплывающее окно с поиском."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent
from PySide6.QtGui import QIcon, QKeyEvent

from icons import get_icon
from launcher import launch
from storage import log


class QuickLauncher(QWidget):
    """Всплывающее окно поиска. По умолчанию скрыто."""

    def __init__(self, get_apps_callable, colors):
        super().__init__(None)
        self.get_apps = get_apps_callable
        self.colors = colors

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setFixedSize(600, 420)

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти и запустить...")
        self.search.setFixedHeight(46)
        self.search.textChanged.connect(self._update_results)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(28, 28))
        self.list_widget.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.list_widget, 1)

        self.hint = QLabel("↑↓ — навигация, Enter — запустить, Esc — закрыть")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.hint)

    def _apply_theme(self):
        c = self.colors
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {c['BG']};
                border-radius: 14px;
            }}
            QLineEdit {{
                background-color: {c['CARD']};
                color: {c['TEXT']};
                border: 2px solid {c['ACCENT']};
                border-radius: 12px;
                padding: 0 16px;
                font-size: 16px;
            }}
            QListWidget {{
                background-color: {c['BG']};
                color: {c['TEXT']};
                border: none;
                outline: none;
                font-size: 14px;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-radius: 8px;
            }}
            QListWidget::item:selected {{
                background-color: {c['ACCENT']};
                color: {c['BG']};
            }}
            QLabel {{
                color: {c['SUBTEXT']};
                background: transparent;
            }}
        """)

    def update_colors(self, colors):
        self.colors = colors
        self._apply_theme()

    def _populate(self):
        self.list_widget.clear()
        query = self.search.text().lower().strip()

        apps = self.get_apps()
        sorted_apps = sorted(
            apps,
            key=lambda a: (
                not a.get("favorite", False),
                a.get("order", 0),
                -a.get("launch_count", 0),
            ),
        )

        shown = 0
        for app in sorted_apps:
            name = app.get("name", "")
            if query and query not in name.lower():
                continue
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, app)
            try:
                pix = get_icon(app, 28)
                if pix:
                    item.setIcon(QIcon(pix))
            except Exception:
                pass
            self.list_widget.addItem(item)
            shown += 1
            if shown >= 50:
                break

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _update_results(self):
        self._populate()

    def _on_item_activated(self, item):
        app = item.data(Qt.ItemDataRole.UserRole)
        if not app:
            return
        self.hide()
        result = launch(app)
        if not result.ok:
            log.error(f"QuickLauncher: не удалось запустить {app.get('name')}: {result.error}")
        else:
            log.info(f"QuickLauncher: запущено {app.get('name')}")

    def popup(self):
        """Открывает окно по центру сверху и ставит фокус."""
        self.search.clear()
        self._populate()

        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.top() + 120
        self.move(x, y)

        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Down:
                row = self.list_widget.currentRow()
                if row < self.list_widget.count() - 1:
                    self.list_widget.setCurrentRow(row + 1)
                return True
            if key == Qt.Key_Up:
                row = self.list_widget.currentRow()
                if row > 0:
                    self.list_widget.setCurrentRow(row - 1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                item = self.list_widget.currentItem()
                if item:
                    self._on_item_activated(item)
                return True
            if key == Qt.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        # Скрываем при потере фокуса
        self.hide()
        super().focusOutEvent(event)