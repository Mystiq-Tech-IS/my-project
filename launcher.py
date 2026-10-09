"""Логика запуска программ: обычные файлы, URI, запуск от админа."""

import os
import ctypes
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

    # Ярлыки и скрипты — через os.startfile
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


def launch_as_admin(app: dict) -> LaunchResult:
    """Запускает программу с повышением прав (UAC) через ShellExecuteW.

    Для .lnk-ярлыка сначала разворачиваем цель — ShellExecuteW с runas
    плохо работает с ярлыками напрямую.
    """
    path = (app.get("path") or "").strip()
    if not path:
        return LaunchResult(False, "Пустой путь к программе")

    if "://" in path or path.startswith("mailto:"):
        return LaunchResult(
            False,
            "Нельзя запустить ссылку/URI с правами администратора",
        )

    if not os.path.exists(path):
        return LaunchResult(False, f"Файл не найден:\n{path}")

    # Для .lnk — разворачиваем в .exe
    target = path
    ext = os.path.splitext(path)[1].lower()
    if ext == ".lnk":
        try:
            from process_check import resolve_target
            real = resolve_target(path)
            if real and os.path.exists(real):
                target = real
        except Exception as e:
            log.error(f"launch_as_admin resolve_target: {e}")

    try:
        workdir = os.path.dirname(target) or None
        SW_SHOWNORMAL = 1
        # ShellExecuteW возвращает HINSTANCE-подобное число:
        #   > 32 — успех
        #   <= 32 — код ошибки (5 = пользователь отменил UAC)
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            target,
            None,
            workdir,
            SW_SHOWNORMAL,
        )
        code = int(result)
        if code > 32:
            return LaunchResult(True)
        if code == 5:
            return LaunchResult(False, "Запуск отменён пользователем (UAC)")
        return LaunchResult(False, f"ShellExecuteW вернул код {code}")
    except Exception as e:
        log.error(f"launch_as_admin error: {e}")
        return LaunchResult(False, str(e))


def file_exists(path: str) -> bool:
    if not path:
        return False
    if "://" in path or path.startswith("mailto:"):
        return True
    return os.path.exists(path)