"""Пример плагина: показывает тост при старте и логирует запуски."""

from plugin_base import Plugin


class HelloPlugin(Plugin):
    name = "Hello World"
    version = "1.0.0"
    author = "MyLauncher"
    description = "Показывает приветствие при старте и логирует запуски программ"
    icon = "fa5s.hand-sparkles"

    def on_load(self):
        self.launched = 0
        self.log("активирован")

    def on_startup(self):
        if self.launcher:
            try:
                self.launcher._show_toast(
                    "👋 Hello, plugin!",
                    "Плагин Hello World загружен",
                    "info",
                )
            except Exception:
                pass

    def on_app_launch(self, app):
        self.launched += 1
        name = app.get("name", "?")
        self.log(f"запущено «{name}» (за сессию: {self.launched})")

    def on_shutdown(self):
        self.log(f"сессия завершена, запущено программ: {self.launched}")