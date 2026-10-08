"""Активация окна программы: pywin32 → pygetwindow → fail.

pywin32 — точный метод: находим PID по имени exe, ищем его top-level
окно, восстанавливаем из minimize, ставим на передний план.

pygetwindow — fallback по заголовку окна, менее точный, но без него
нечего делать. Обе библиотеки опциональны.
"""

import os
import time

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import win32gui
    import win32process
    import win32con
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False
    win32gui = None
    win32process = None
    win32con = None

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False
    gw = None

from process_check import resolve_target


def has_support():
    return HAS_PYWIN32 or HAS_PYGETWINDOW


# ==================== PYWIN32 ====================
def _windows_for_pid(pid):
    """Список (hwnd, title) для процесса."""
    result = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid != pid:
                return True
            title = win32gui.GetWindowText(hwnd)
            if title:
                result.append((hwnd, title))
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception as e:
        log.error(f"_windows_for_pid: {e}")
    return result


def _activate_hwnd(hwnd):
    """Восстанавливает + SetForegroundWindow. Пробует ALT-трюк."""
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        show_cmd = placement[1]
        if show_cmd == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    except Exception:
        pass

    try:
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        # Иногда Windows не даёт фокус — эмулируем нажатие ALT
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # ALT down
            try:
                win32gui.SetForegroundWindow(hwnd)
                return True
            finally:
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # ALT up
        except Exception as e:
            log.error(f"SetForegroundWindow: {e}")
            return False


def _activate_via_pywin32(exe_path):
    if not (HAS_PYWIN32 and HAS_PSUTIL):
        return False
    try:
        real = resolve_target(exe_path)
        name = os.path.basename(real).lower()
        if not name.endswith(".exe"):
            return False

        pids = []
        for p in psutil.process_iter(["name", "pid"]):
            try:
                if (p.info.get("name") or "").lower() == name:
                    pids.append(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if not pids:
            return False

        for pid in pids:
            wins = _windows_for_pid(pid)
            for hwnd, title in wins:
                if _activate_hwnd(hwnd):
                    log.info(
                        f"Окно активировано (pid={pid}, '{title[:60]}')"
                    )
                    return True
        return False
    except Exception as e:
        log.error(f"_activate_via_pywin32: {e}")
        return False


# ==================== PYGETWINDOW ====================
def _activate_via_pygetwindow(exe_path):
    if not HAS_PYGETWINDOW:
        return False
    try:
        real = resolve_target(exe_path)
        base = os.path.splitext(os.path.basename(real))[0]
        if not base:
            return False
        base_lower = base.lower()

        candidates = []

        # Точный поиск по заголовку
        try:
            candidates.extend(gw.getWindowsWithTitle(base) or [])
        except Exception:
            pass

        # Нечёткий: имя процесса как подстрока в заголовке
        if not candidates:
            try:
                for w in gw.getAllWindows():
                    title = (getattr(w, "title", "") or "").lower()
                    if not title:
                        continue
                    if base_lower in title:
                        candidates.append(w)
            except Exception:
                pass

        for w in candidates:
            try:
                if getattr(w, "isMinimized", False):
                    w.restore()
                w.activate()
                log.info(f"Окно активировано (pygetwindow): {base}")
                return True
            except Exception:
                continue
        return False
    except Exception as e:
        log.error(f"_activate_via_pygetwindow: {e}")
        return False


# ==================== ГЛАВНАЯ ====================
def activate_app_window(exe_path):
    """Пытается активировать главное окно программы. True если получилось."""
    if not exe_path:
        return False
    if HAS_PYWIN32 and _activate_via_pywin32(exe_path):
        return True
    if _activate_via_pygetwindow(exe_path):
        return True
    return False


def activate_with_retry(exe_path, attempts=3, delay=0.35):
    """Пробует активировать с ретраями — на случай медленного старта окна."""
    for i in range(max(1, attempts)):
        if activate_app_window(exe_path):
            return True
        time.sleep(delay)
    return False