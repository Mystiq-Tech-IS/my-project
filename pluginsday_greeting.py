"""Пример плагина: приветствие по времени суток."""

from datetime import datetime
from plugin_base import Plugin


class DayGreeting(Plugin):
    name = "Приветствие дня"
    version = "1.0.0"
    author = "MyLauncher"
    description = "Показывает приветствие в зависимости от времени суток"
    icon = "fa5s.sun"

    def on_startup(self):
        h = datetime.now().hour
        if 5 <= h < 12:
            text = "Доброе утро! ☀"
        elif 12 <= h < 18:
            text = "Добрый день! 🌤"
        elif 18 <= h < 23:
            text = "Добрый вечер! 🌙"
        else:
            text = "Доброй ночи! 💤"

        if self.launcher:
            try:
                self.launcher._show_toast("MyLauncher", text, "info")
            except Exception:
                pass