"""Пример плагина с собственной вкладкой в настройках."""

from datetime import datetime
from plugin_base import Plugin


class SessionStats(Plugin):
    name = "Статистика сессии"
    version = "1.0.0"
    author = "MyLauncher"
    description = "Считает запуски, категории и время работы за сессию"
    icon = "fa5s.chart-line"

    def on_load(self):
        self.started_at = datetime.now()
        self.launched = 0
        self.categories_visited = set()

    def on_app_launch(self, app):
        self.launched += 1

    def on_category_change(self, category_key):
        if category_key not in ("all", "recent"):
            self.categories_visited.add(category_key)

    def on_settings_tabs(self, colors):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
        from PySide6.QtCore import Qt

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        title = QLabel("📊 Статистика сессии")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        lay.addWidget(title)

        uptime = datetime.now() - self.started_at
        seconds = int(uptime.total_seconds())
        minutes = seconds // 60
        hours = minutes // 60
        minutes = minutes % 60
        if hours > 0:
            uptime_str = f"{hours}ч {minutes}м"
        elif minutes > 0:
            uptime_str = f"{minutes}м {seconds % 60}с"
        else:
            uptime_str = f"{seconds}с"

        cat_names = {
            "games": "Игры", "work": "Работа",
            "system": "Система", "other": "Прочее",
        }
        cats_str = ", ".join(
            cat_names.get(k, k) for k in sorted(self.categories_visited)
        ) or "—"

        info = QLabel(
            f"⏱   Время работы: {uptime_str}\n"
            f"🚀  Запущено программ: {self.launched}\n"
            f"🗂   Категорий просмотрено: "
            f"{len(self.categories_visited)}  ({cats_str})"
        )
        info.setStyleSheet(
            f"color: {colors['TEXT']}; font-size: 14px; padding-top: 8px;"
        )
        info.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lay.addWidget(info)
        lay.addStretch()

        return [("Сессия", w)]
