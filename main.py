"""Точка входа приложения."""

import sys
from PySide6.QtWidgets import QApplication

from window import Launcher


def _create_launcher_safe() -> Launcher:
    """Создаёт окно лаунчера со splash screen.

    В случае любой ошибки при инициализации splash — возвращает окно
    без splash, чтобы лаунчер всё равно запустился.
    """
    try:
        from storage import load_settings
        from themes import get_theme
        from splash import SplashScreen

        settings = load_settings()
        theme = get_theme(
            settings.get("theme", "dark"),
            settings.get("accent", "blue"),
        )
        splash_enabled = bool(settings.get("splash_enabled", True))
        duration = int(settings.get("splash_duration", 1500))

        window = Launcher()

        if splash_enabled:
            splash = SplashScreen(theme, duration_ms=duration)

            # Объекты передаются аргументами по умолчанию —
            # так PyCharm видит их конкретные типы, а не Optional.
            def _on_finished(window_ref=window, splash_ref=splash) -> None:
                window_ref.show()
                splash_ref.deleteLater()

            splash.finished.connect(_on_finished)
            splash.start()
        else:
            window.show()

        return window

    except Exception as e:  # noinspection PyBroadException
        try:
            from storage import log
            log.error(f"splash init error: {e}")
        except Exception:
            pass
        window = Launcher()
        window.show()
        return window


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MyLauncher")
    app.setQuitOnLastWindowClosed(False)

    font = app.font()
    font.setFamily("Segoe UI")  # noinspection SpellCheckingInspection
    font.setPointSize(10)
    app.setFont(font)

    _create_launcher_safe()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()