"""Менеджер плагинов: обнаружение, загрузка, вызов хуков."""

import os
import sys
import importlib.util
import inspect

from config import BASE_DIR
from plugin_base import Plugin

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")


PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")


# ============== ШАБЛОНЫ СТАРТОВЫХ ФАЙЛОВ ==============
_TEMPLATE_PY = '''"""ШАБЛОН ПЛАГИНА MyLauncher.

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
'''

_HELLO_PY = '''"""Пример плагина: показывает тост при старте и логирует запуски."""

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
                    "\\u{1F44B} Hello, plugin!",
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
'''

_DAY_GREETING_PY = '''"""Пример плагина: приветствие по времени суток."""

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
            text = "Доброе утро! \\u2600"
        elif 12 <= h < 18:
            text = "Добрый день! \\u{1F324}"
        elif 18 <= h < 23:
            text = "Добрый вечер! \\u{1F319}"
        else:
            text = "Доброй ночи! \\u{1F4A4}"

        if self.launcher:
            try:
                self.launcher._show_toast("MyLauncher", text, "info")
            except Exception:
                pass
'''

_SESSION_STATS_PY = '''"""Пример плагина с собственной вкладкой в настройках."""

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

        title = QLabel("\\u{1F4CA} Статистика сессии")
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
        ) or "\\u2014"

        info = QLabel(
            f"\\u23F1   Время работы: {uptime_str}\\n"
            f"\\u{1F680}  Запущено программ: {self.launched}\\n"
            f"\\u{1F5C2}   Категорий просмотрено: "
            f"{len(self.categories_visited)}  ({cats_str})"
        )
        info.setStyleSheet(
            f"color: {colors['TEXT']}; font-size: 14px; padding-top: 8px;"
        )
        info.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lay.addWidget(info)
        lay.addStretch()

        return [("Сессия", w)]
'''


_STARTER_FILES = {
    "_template.py":     _TEMPLATE_PY,
    "hello_plugin.py":  _HELLO_PY,
    "day_greeting.py":  _DAY_GREETING_PY,
    "session_stats.py": _SESSION_STATS_PY,
}


class PluginManager:
    def __init__(self, launcher, settings):
        self.launcher = launcher
        self.settings = settings
        self.plugins = {}       # name -> instance
        self.discovered = {}    # name -> {class, path, file, meta}
        self._ensure_dir()
        self._ensure_examples()
        self.discover()
        self.sync_with_settings()

    # ====================== Обнаружение ======================
    def _ensure_dir(self):
        try:
            os.makedirs(PLUGINS_DIR, exist_ok=True)
        except Exception as e:
            log.error(f"PluginManager: не могу создать plugins/: {e}")

    def _ensure_examples(self):
        """Создаёт стартовые файлы в plugins/, если их там нет."""
        if not os.path.isdir(PLUGINS_DIR):
            return
        for fname, content in _STARTER_FILES.items():
            path = os.path.join(PLUGINS_DIR, fname)
            if os.path.exists(path):
                continue
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                log.info(f"Создан пример плагина: {fname}")
            except Exception as e:
                log.error(f"Не могу создать {fname}: {e}")

    def discover(self):
        """Сканирует папку plugins/ и заполняет self.discovered."""
        self.discovered = {}
        if not os.path.isdir(PLUGINS_DIR):
            return

        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)

        for fname in sorted(os.listdir(PLUGINS_DIR)):
            if not fname.endswith(".py"):
                continue
            if fname.startswith("_"):
                continue
            path = os.path.join(PLUGINS_DIR, fname)
            self._discover_file(path)

    def _discover_file(self, path):
        fname = os.path.basename(path)
        try:
            mod_name = f"launcher_plugin_{fname[:-3]}"
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            log.error(f"Плагин {fname}: ошибка импорта: {e}")
            return

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is Plugin:
                continue
            if not issubclass(obj, Plugin):
                continue
            name = getattr(obj, "name", fname[:-3])
            self.discovered[name] = {
                "class": obj,
                "path": path,
                "file": fname,
                "meta": {
                    "name": name,
                    "version": getattr(obj, "version", "1.0.0"),
                    "author": getattr(obj, "author", ""),
                    "description": getattr(obj, "description", ""),
                    "icon": getattr(obj, "icon", "fa5s.plug"),
                },
            }
            break

    # ====================== Загрузка / выгрузка ======================
    def _load(self, name):
        if name in self.plugins:
            return True
        info = self.discovered.get(name)
        if not info:
            log.warning(f"Плагин «{name}» не найден среди обнаруженных")
            return False
        try:
            inst = info["class"](self.launcher)
            inst.on_load()
            self.plugins[name] = inst
            log.info(f"Плагин загружен: {name}")
            return True
        except Exception as e:
            log.error(f"Плагин {name}: ошибка активации: {e}")
            return False

    def unload(self, name):
        if name not in self.plugins:
            return
        try:
            self.plugins[name].on_unload()
        except Exception as e:
            log.error(f"Плагин {name}: ошибка выгрузки: {e}")
        del self.plugins[name]
        log.info(f"Плагин выгружен: {name}")

    def sync_with_settings(self):
        enabled = set(self.settings.get("enabled_plugins") or [])

        for name in list(self.plugins.keys()):
            if name not in enabled:
                self.unload(name)

        for name in enabled:
            if name not in self.plugins:
                self._load(name)

    def reload(self):
        for name in list(self.plugins.keys()):
            self.unload(name)
        self._ensure_examples()
        self.discover()
        self.sync_with_settings()

    # ====================== Вызов хуков ======================
    def call_hook(self, hook_name, *args, **kwargs):
        results = []
        for name, pl in list(self.plugins.items()):
            method = getattr(pl, hook_name, None)
            if not method:
                continue
            try:
                r = method(*args, **kwargs)
                if r is not None:
                    results.append(r)
            except Exception as e:
                log.error(f"Плагин {name}, хук {hook_name}: {e}")
        return results

    # ====================== Метаданные для UI ======================
    def list_all(self):
        enabled = set(self.settings.get("enabled_plugins") or [])
        result = []
        for name, info in sorted(self.discovered.items()):
            meta = dict(info["meta"])
            meta["file"] = info["file"]
            meta["enabled"] = name in enabled
            meta["loaded"] = name in self.plugins
            result.append(meta)
        return result

    def count_active(self):
        return len(self.plugins)