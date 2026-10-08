"""Логика запуска программ: обычные файлы и URI (steam://, http:// и т.п.)."""

import os
from PySide6.QtCore import QProcess, QUrl
from PySide6.QtGui import QDesktopServices

from storage import log


class LaunchResult:
    def __init__(self, ok: bool, error: str = ""):
        self.ok = ok
        self.error = error


def launch(app: dict) -> LaunchResult:
    path = (app.get("path") or "").strip()
    if not path:
        return LaunchResult(False, "Пустой путь к программе")

    # URI (steam://, epic://, http://, https://, mailto:)
    if "://" in path or path.startswith("mailto:"):
        try:
            QDesktopServices.openUrl(QUrl(path))
            return LaunchResult(True)
        except Exception as e:
            log.error(f"Ошибка открытия URI {path}: {e}")
            return LaunchResult(False, f"Не удалось открыть ссылку:\n{e}")

    if not os.path.exists(path):
        return LaunchResult(False, f"Файл не найден:\n{path}")

    ext = os.path.splitext(path)[1].lower()

    # Ярлыки и скрипты лучше запускать через os.startfile —
    # так Windows сама разбирается с ними правильно.
    if ext in (".lnk", ".bat", ".cmd"):
        try:
            os.startfile(path)
            return LaunchResult(True)
        except Exception as e:
            log.error(f"Ошибка запуска {path}: {e}")
            return LaunchResult(False, str(e))

    # Обычный .exe — через QProcess, не блокирует
    try:
        ok, _pid = QProcess.startDetached(path, [])
        if ok:
            return LaunchResult(True)
        return LaunchResult(False, "Не удалось запустить процесс")
    except Exception as e:
        log.error(f"Ошибка запуска {path}: {e}")
        return LaunchResult(False, str(e))


def file_exists(path: str) -> bool:
    if not path:
        return False
    if "://" in path or path.startswith("mailto:"):
        return True
    return os.path.exists(path)