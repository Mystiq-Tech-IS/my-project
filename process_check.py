"""Проверка процессов + разворачивание .lnk ярлыков."""

import os
import time
import subprocess

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from storage import log

# Кэш: путь .lnk → путь .exe (или пустая строка, если не удалось)
_lnk_cache = {}


def resolve_target(path: str) -> str:
    """Если path — .lnk ярлык, возвращает путь к его цели. Иначе возвращает path."""
    if not path:
        return path
    if not path.lower().endswith(".lnk"):
        return path
    if path in _lnk_cache:
        return _lnk_cache[path]

    if not os.path.exists(path):
        _lnk_cache[path] = path
        return path

    try:
        ps = (
            f'$ws = New-Object -ComObject WScript.Shell;'
            f'$sc = $ws.CreateShortcut("{path}");'
            f'Write-Output $sc.TargetPath'
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = res.stdout.decode("cp866", errors="ignore").strip()
        # PowerShell иногда пишет BOM или пустую строку
        if out and os.path.exists(out):
            log.info(f"resolve_target: {os.path.basename(path)} -> {out}")
            _lnk_cache[path] = out
            return out
        # Не удалось развернуть — вернём оригинал
        _lnk_cache[path] = path
        return path
    except Exception as e:
        log.error(f"resolve_target error для {path}: {e}")
        _lnk_cache[path] = path
        return path


def clear_lnk_cache():
    _lnk_cache.clear()


def _process_name_for(path: str) -> str:
    """Возвращает имя .exe для процесса, с учётом .lnk."""
    real = resolve_target(path)
    return os.path.basename(real).lower()


def is_process_running(exe_path: str) -> bool:
    if not HAS_PSUTIL or not exe_path or "://" in exe_path:
        return False
    name = _process_name_for(exe_path)
    if not name.endswith(".exe"):
        return False
    try:
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() == name:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        log.error(f"is_process_running error: {e}")
    return False


def count_process(exe_path: str) -> int:
    if not HAS_PSUTIL or not exe_path or "://" in exe_path:
        return 0
    name = _process_name_for(exe_path)
    if not name.endswith(".exe"):
        return 0
    n = 0
    try:
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() == name:
                    n += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return n


def kill_process(exe_path: str, timeout: float = 4.0) -> int:
    if not HAS_PSUTIL or not exe_path or "://" in exe_path:
        return 0

    name = _process_name_for(exe_path)
    if not name.endswith(".exe"):
        return 0

    killed = 0
    try:
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() == name:
                    p.terminate()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        log.error(f"kill_process (terminate) error: {e}")

    start = time.time()
    while time.time() - start < timeout:
        if not is_process_running(exe_path):
            log.info(f"Процесс {name} завершён (terminate)")
            return killed
        time.sleep(0.2)

    log.warning(f"Процесс {name} не завершился за {timeout} сек — kill()")
    try:
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() == name:
                    p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        log.error(f"kill_process (kill) error: {e}")

    time.sleep(0.3)
    return killed


def try_activate_window(exe_path: str) -> bool:
    """Оставлено для совместимости, но не используется."""
    return False