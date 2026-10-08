"""ШАБЛОН ПЛАГИНА MyLauncher.

Как создать свой плагин:
  1. Скопируй этот файл под новым именем (без _ в начале).
  2. Переименуй класс и поменяй метаданные.
  3. Переопредели нужные хуки.
  4. Перезапусти лаунчер или нажми «Перезагрузить» в Настройки → Плагины.
"""

from plugin_base import Plugin


class MyPlugin(Plugin):
    # -------- Метаданные --------
    name = "Мой плагин"
    version = "1.0.0"
    author = "Твоё имя"
    description = "Что делает этот плагин"
    icon = "fa5s.star"

    def on_load(self):
        self.log("загружен")

    def on_unload(self):
        self.log("выгружен")

    def on_startup(self):
        # self.launcher — экземпляр Launcher (QMainWindow)
        # Пример тоста:
        # self.launcher._show_toast("Заголовок", "Текст", "info")
        pass

    def on_app_launch(self, app):
        # app["name"], app["path"], app["category"]
        pass

    def on_app_close(self, app):
        pass

    def on_category_change(self, category_key):
        pass

    def on_theme_change(self, theme_name, accent):
        pass

    def on_settings_tabs(self, colors):
        # Возвращает [(title, widget), ...] — доп. вкладки в настройках
        return []

    def on_context_menu(self, app, menu):
        # menu — QMenu, можно добавлять свои QAction
        pass
