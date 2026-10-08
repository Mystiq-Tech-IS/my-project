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
            text = "Доброе утро! \u2600"
        elif 12 <= h < 18:
            text = "Добрый день! \u{1F324}"
        elif 18 <= h < 23:
            text = "Добрый вечер! \u{1F319}"
        else:
            text = "Доброй ночи! \u{1F4A4}"

        if self.launcher:
            try:
                self.launcher._show_toast("MyLauncher", text, "info")
            except Exception:
                pass
