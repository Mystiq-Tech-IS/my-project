"""ШАБЛОН ПЛАГИНА MyLauncher.

Как создать свой плагин:
  1. Скопируй этот файл под новым именем (без _ в начале).
  2. Переименуй класс и поменяй метаданные.
  3. Переопредели нужные хуки.
  4. Перезапусти лаунчер или нажми «Перезагрузить» в Настройки → Плагины.

Имя файла — любое, кроме начинающегося с _. Класс должен быть один и
наследоваться от Plugin.
"""

from plugin_base import Plugin


class MyPlugin(Plugin):
    # -------- Метаданные --------
    name = "Мой плагин"
    version = "1.0.0"
    author = "Твоё имя"
    description = "Что делает этот плагин"
    icon = "fa5s.star"

    # -------- Жизненный цикл --------
    def on_load(self):
        """Плагин активирован."""
        self.log("загружен")
        # Например: self.counter = 0

    def on_unload(self):
        """Плагин выключается."""
        self.log("выгружен")

    # -------- События --------
    def on_startup(self):
        """Лаунчер полностью загружен."""
        # self.launcher — экземпляр Launcher (QMainWindow)
        # можно вызывать self.launcher._show_toast("Заголовок", "Текст", "info")
        pass

    def on_shutdown(self):
        pass

    def on_app_launch(self, app):
        """Программа запущена."""
        # app["name"], app["path"], app["category"]
        pass

    def on_app_close(self, app):
        pass

    def on_category_change(self, category_key):
        pass

    def on_theme_change(self, theme_name, accent):
        pass

    # -------- UI --------
    def on_settings_tabs(self, colors):
        """
        Возвращает список [(title, widget), ...] — доп. вкладки настроек.
        Пример: см. plugins/session_stats.py
        """
        return []