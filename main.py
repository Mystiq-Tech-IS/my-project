"""Точка входа приложения."""

import os
import sys
import traceback
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon


def _resource_path(relative_path):
    """Путь к ресурсу и при разработке, и в .exe."""
    from config import RESOURCE_DIR
    return os.path.join(RESOURCE_DIR, relative_path)


def _create_launcher_safe():
    """Создаёт окно лаунчера со splash screen.

    Если splash падает — пытаемся показать окно без него.
    Если и это падает — показываем диалог ошибки и выходим (без
    рекурсивного пересоздания окна).
    """
    try:
        from storage import load_settings
        from themes import get_theme
        from splash import SplashScreen
    except Exception as e:
        traceback.print_exc()
        print(f"[MyLauncher] Критическая ошибка импорта: {e}", file=sys.stderr)
        raise

    from window import Launcher

    try:
        settings = load_settings()
        theme = get_theme(
            settings.get("theme", "dark"),
            settings.get("accent", "blue"),
        )
        splash_enabled = bool(settings.get("splash_enabled", True))
        duration = int(settings.get("splash_duration", 1500))

        window = Launcher()

        if not splash_enabled:
            window.show()
            return window

        try:
            splash = SplashScreen(theme, duration_ms=duration)

            def _on_started() -> None:
                # Пользователь нажал «ЗАПУСТИТЬ» — играем фразу
                try:
                    import sounds
                    sounds.play_voice("startup")
                except Exception:
                    pass

            def _on_finished(window_ref=window, splash_ref=splash) -> None:
                window_ref.show_materialize()
                splash_ref.deleteLater()

            splash.started.connect(_on_started)
            splash.finished.connect(_on_finished)
            splash.start()
        except Exception as e:
            try:
                from storage import log
                log.error(f"splash init error: {e}")
            except Exception:
                pass
            window.show()

        return window

    except Exception as e:
        try:
            from storage import log
            log.error(f"Launcher init error: {e}\n{traceback.format_exc()}")
        except Exception:
            pass

        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None,
            "Ошибка запуска",
            f"Не удалось запустить лаунчер:\n\n{e}",
        )
        raise


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MyLauncher")
    app.setQuitOnLastWindowClosed(False)

    # Иконка окна в панели задач / Alt+Tab
    icon_path = _resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font = app.font()
    font.setFamily("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)

    _create_launcher_safe()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()