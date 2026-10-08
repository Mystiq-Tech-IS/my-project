"""Базовый класс для плагинов MyLauncher.

Плагин — это класс-наследник `Plugin`, размещённый в папке plugins/.
Достаточно одного .py файла. Лаунчер найдёт его автоматически,
если в настройках плагин включён.

Все хуки опциональны — переопределяй только нужные.
"""


class Plugin:
    """Базовый класс плагина."""

    # ---- Метаданные (переопределяются в наследниках) ----
    name = "Unnamed Plugin"
    version = "1.0.0"
    author = ""
    description = ""
    icon = "fa5s.plug"       # Fa5s-имя для отображения в UI

    def __init__(self, launcher=None):
        self.launcher = launcher
        self.enabled = True
        self._log = None

    # ---- Логирование ----
    def log(self, message):
        """Пишет сообщение в общий launcher.log с префиксом [plugin:Name]."""
        try:
            if self._log is None:
                from storage import log as _log
                self._log = _log
            self._log.info(f"[plugin:{self.name}] {message}")
        except Exception:
            pass

    # ================== ЖИЗНЕННЫЙ ЦИКЛ ==================
    def on_load(self):
        """Плагин активирован. Инициализация ресурсов, переменных."""
        pass

    def on_unload(self):
        """Плагин выключается. Освободи ресурсы (таймеры, потоки, окна)."""
        pass

    # ================== СОБЫТИЯ ЛАУНЧЕРА ==================
    def on_startup(self):
        """Лаунчер полностью загружен и окно показано. Можно трогать UI."""
        pass

    def on_shutdown(self):
        """Лаунчер собирается завершиться."""
        pass

    def on_app_launch(self, app):
        """Программа успешно запущена. app — dict с 'name', 'path', 'category'."""
        pass

    def on_app_close(self, app):
        """Программа завершается (kill или закрытие через лаунчер)."""
        pass

    def on_category_change(self, category_key):
        """Смена категории: 'all', 'games', 'work', 'system', 'other'."""
        pass

    def on_theme_change(self, theme_name, accent):
        """Сменилась тема или акцент. theme_name — 'dark'|'light',
        accent — ключ пресета или HEX."""
        pass

    def on_settings_saved(self, settings):
        """Настройки сохранены. settings — итоговый словарь."""
        pass

    # ================== UI-ХУКИ ==================
    def on_settings_tabs(self, colors):
        """
        Возвращает список кортежей [(title, widget), ...] — дополнительные
        вкладки в окне настроек. widget — QWidget, colors — dict темы.
        """
        return []

    def on_context_menu(self, app, menu):
        """
        Пользователь открыл контекстное меню плитки. app — программа (dict),
        menu — QMenu (можно добавлять свои QAction). Ничего не возвращай.
        """
        pass