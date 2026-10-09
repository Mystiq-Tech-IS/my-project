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

    def on_app_launch_pre(self, app):
        """Перед запуском программы. Верните False, чтобы отменить запуск.

        app — dict с 'name', 'path', 'category'. Можно что-то проверить
        (например, лимит времени) и вернуть False для отмены.
        Возврат None или True — запуск продолжится.
        """
        return True

    def on_app_launch(self, app):
        """Программа успешно запущена. app — dict с 'name', 'path', 'category'."""
        pass

    def on_app_close(self, app):
        """Программа завершается (kill или закрытие через лаунчер)."""
        pass

    def on_card_created(self, card):
        """Карточка программы создана. Можно её кастомизировать.

        card — QFrame (TileCard). Можно изменить tooltip, добавить
        собственные сигналы, навесить бейджи через paintEvent (если
        наследуетесь) и т.п.
        """
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

    def provide_theme_overrides(self, theme):
        """Верните dict с переопределениями цветов темы или None.

        Например: {"ACCENT": "#FF00FF", "BG": "#000000"}
        Оверрайды применяются поверх текущей темы. Ключи — как в themes.py:
        BG, BG_ALT, CARD, CARD_HOVER, BORDER, BORDER_HOV,
        TEXT, SUBTEXT, ACCENT, ACCENT_HOV, DANGER, OK, OK_DIM.
        """
        return None