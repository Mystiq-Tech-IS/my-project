"""Управление автозапуском с Windows через папку Startup."""

import os
import sys
import subprocess

from storage import log


def _startup_folder():
    """Возвращает путь к папке автозагрузки текущего пользователя."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    return os.path.join(
        appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )


def _launcher_path():
    """Путь к текущему .exe или .py + способ запуска."""
    if getattr(sys, "frozen", False):
        # Запущено как .exe (собранный PyInstaller)
        return sys.executable, None
    else:
        # Запущено как .py
        return sys.executable, os.path.abspath(sys.argv[0])


def _shortcut_path():
    folder = _startup_folder()
    if not folder:
        return None
    return os.path.join(folder, "MyLauncher.lnk")


def is_enabled():
    """Проверяет, включён ли автозапуск."""
    sp = _shortcut_path()
    return bool(sp and os.path.exists(sp))


def enable():
    """Создаёт ярлык в папке Startup."""
    sp = _shortcut_path()
    if not sp:
        return False, "Не удалось найти папку Startup"

    exe, script = _launcher_path()

    try:
        if getattr(sys, "frozen", False):
            # Создаём ярлык на .exe через PowerShell
            ps = (
                f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{sp}");'
                f'$s.TargetPath = "{exe}";'
                f'$s.WorkingDirectory = "{os.path.dirname(exe)}";'
                f'$s.Save()'
            )
        else:
            # Создаём ярлык на pythonw.exe с аргументом — путь к main.py
            pythonw = exe.replace("python.exe", "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = exe
            ps = (
                f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{sp}");'
                f'$s.TargetPath = "{pythonw}";'
                f'$s.Arguments = \'"{script}"\';'
                f'$s.WorkingDirectory = "{os.path.dirname(script)}";'
                f'$s.Save()'
            )

        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        log.info(f"Автозапуск включён: {sp}")
        return True, ""
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("cp866", errors="ignore") if e.stderr else str(e)
        log.error(f"Не удалось включить автозапуск: {err}")
        return False, err
    except Exception as e:
        log.error(f"Не удалось включить автозапуск: {e}")
        return False, str(e)


def disable():
    """Удаляет ярлык из папки Startup."""
    sp = _shortcut_path()
    if not sp:
        return False, "Не удалось найти папку Startup"
    try:
        if os.path.exists(sp):
            os.remove(sp)
            log.info(f"Автозапуск выключен: {sp}")
        return True, ""
    except Exception as e:
        log.error(f"Не удалось выключить автозапуск: {e}")
        return False, str(e)