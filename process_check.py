"""Проверка процессов + разворачивание .lnk ярлыков."""

import os
import time
import subprocess
import threading

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False
    win32com = None

from storage import log

# Кэш: путь .lnk → путь к цели
_lnk_cache = {}
_lnk_lock = threading.Lock()

# ---------- Снапшот имён процессов с TTL ----------
_PROC_SNAPSHOT_TTL = 1.5
_proc_snapshot = {"time": 0.0, "names": set()}


def _process_name_set():
    """Возвращает set имён активных процессов (lower-case), с TTL-кэшем."""
    if not HAS_PSUTIL:
        return set()
    now = time.time()
    if now - _proc_snapshot["time"] < _PROC_SNAPSHOT_TTL:
        return _proc_snapshot["names"]

    names = set()
    try:
        for p in psutil.process_iter(["name"]):
            try:
                n = (p.info.get("name") or "").lower()
                if n:
                    names.add(n)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        log.error(f"_process_name_set: {e}")

    _proc_snapshot["names"] = names
    _proc_snapshot["time"] = now
    return names


def invalidate_process_cache():
    """Сбросить снапшот — например, сразу после kill()."""
    _proc_snapshot["time"] = 0.0
    _proc_snapshot["names"] = set()


# ================= РАЗВОРАЧИВАНИЕ .LNK =================
# Кэшированный COM-объект WScript.Shell. Создаётся лениво.
# Используем только из главного потока, чтобы не ловить
# COM-apartment ошибки.
_shell_com = None
_shell_lock = threading.Lock()


def _get_shell_com():
    """Возвращает COM-объект WScript.Shell или None."""
    global _shell_com
    if not HAS_WIN32COM:
        return None
    if _shell_com is not None:
        return _shell_com
    with _shell_lock:
        if _shell_com is not None:
            return _shell_com
        try:
            _shell_com = win32com.client.Dispatch("WScript.Shell")
        except Exception as e:
            log.error(f"Dispatch WScript.Shell: {e}")
            _shell_com = None
    return _shell_com


def _resolve_via_win32com(path):
    """Быстрый способ через COM — обычно 1-5 мс."""
    shell = _get_shell_com()
    if shell is None:
        return ""
    try:
        shortcut = shell.CreateShortcut(path)
        target = shortcut.TargetPath or ""
        return target
    except Exception as e:
        log.error(f"_resolve_via_win32com({path}): {e}")
        return ""


def _resolve_via_powershell(path):
    """Резервный способ — если win32com недоступен."""
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
        return out
    except Exception as e:
        log.error(f"_resolve_via_powershell({path}): {e}")
        return ""


def resolve_target(path: str) -> str:
    """Если path — .lnk ярлык, возвращает путь к его цели.

    Сначала пробует быстрый win32com (миллисекунды), при неудаче —
    резервный PowerShell-вызов. Результат кэшируется.
    """
    if not path:
        return path
    if not path.lower().endswith(".lnk"):
        return path

    with _lnk_lock:
        if path in _lnk_cache:
            return _lnk_cache[path]

    if not os.path.exists(path):
        with _lnk_lock:
            _lnk_cache[path] = path
        return path

    # 1) Быстрый путь — win32com
    target = ""
    if HAS_WIN32COM:
        target = _resolve_via_win32com(path)

    # 2) Резерв — PowerShell
    if not target or not os.path.exists(target):
        target = _resolve_via_powershell(path)

    if target and os.path.exists(target):
        log.info(f"resolve_target: {os.path.basename(path)} -> {target}")
        with _lnk_lock:
            _lnk_cache[path] = target
        return target

    with _lnk_lock:
        _lnk_cache[path] = path
    return path


def clear_lnk_cache():
    with _lnk_lock:
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
    return name in _process_name_set()


def count_process(exe_path: str) -> int:
    if not HAS_PSUTIL or not exe_path or "://" in exe_path:
        return 0
    name = _process_name_for(exe_path)
    if not name.endswith(".exe"):
        return 0

    if name not in _process_name_set():
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

    invalidate_process_cache()

    start = time.time()
    while time.time() - start < timeout:
        invalidate_process_cache()
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
    invalidate_process_cache()
    return killed