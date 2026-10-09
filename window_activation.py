"""Активация окна программы: pywin32 → pygetwindow → fail.

pywin32 — точный метод. Работает и без psutil: имя процесса получаем
через win32process.GetModuleFileNameEx.

pygetwindow — fallback по заголовку окна.

Обе библиотеки опциональны.
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
    import win32api
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False
    win32gui = None
    win32process = None
    win32con = None
    win32api = None

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False
    gw = None

from process_check import resolve_target


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def has_support():
    return HAS_PYWIN32 or HAS_PYGETWINDOW


def _pid_of_hwnd(hwnd):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return pid
    except Exception:
        return 0


def _exe_name_of_pid(pid):
    """Возвращает имя .exe процесса через WinAPI. Работает без psutil."""
    if pid <= 0:
        return ""
    handle = None
    try:
        handle = win32api.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return ""
        try:
            path = win32process.GetModuleFileNameEx(handle, 0)
        except Exception:
            try:
                path = win32process.GetProcessImageFileName(handle)
            except Exception:
                path = ""
        return os.path.basename(path).lower() if path else ""
    except Exception:
        return ""
    finally:
        if handle:
            try:
                win32api.CloseHandle(handle)
            except Exception:
                pass


def _windows_for_pid(pid):
    """Список (hwnd, title) для процесса."""
    result = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if _pid_of_hwnd(hwnd) != pid:
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
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            try:
                win32gui.SetForegroundWindow(hwnd)
                return True
            finally:
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
        except Exception as e:
            log.error(f"SetForegroundWindow: {e}")
            return False


def _collect_pids_by_exe_name(name):
    """Возвращает PID'ы процессов с указанным .exe. Работает без psutil."""
    pids = []
    target = (name or "").lower()
    if not target:
        return pids

    def _cb(hwnd, _):
        try:
            pid = _pid_of_hwnd(hwnd)
            if not pid or pid in pids:
                return True
            if _exe_name_of_pid(pid) == target:
                pids.append(pid)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception as e:
        log.error(f"_collect_pids_by_exe_name: {e}")
    return pids


def _activate_via_pywin32(exe_path):
    if not HAS_PYWIN32:
        return False
    try:
        real = resolve_target(exe_path)
        name = os.path.basename(real).lower()
        if not name.endswith(".exe"):
            return False

        pids = []

        if HAS_PSUTIL:
            try:
                for p in psutil.process_iter(["name", "pid"]):
                    try:
                        if (p.info.get("name") or "").lower() == name:
                            pids.append(p.info["pid"])
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception:
                pids = []

        if not pids:
            pids = _collect_pids_by_exe_name(name)

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


def _target_pids_for(exe_name):
    pids = set()
    if not exe_name:
        return pids

    if HAS_PSUTIL:
        try:
            for p in psutil.process_iter(["name", "pid"]):
                try:
                    if (p.info.get("name") or "").lower() == exe_name:
                        pids.add(p.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return pids
        except Exception:
            pass

    if HAS_PYWIN32:
        for pid in _collect_pids_by_exe_name(exe_name):
            pids.add(pid)
    return pids


def _filter_windows_by_pid(windows, target_pids):
    if not target_pids or not HAS_PYWIN32:
        return windows
    result = []
    for w in windows:
        try:
            hwnd = getattr(w, "_hWnd", None)
            if hwnd is None:
                continue
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid in target_pids:
                result.append(w)
        except Exception:
            continue
    return result


def _activate_via_pygetwindow(exe_path):
    if not HAS_PYGETWINDOW:
        return False
    try:
        real = resolve_target(exe_path)
        name = os.path.basename(real).lower()
        if not name.endswith(".exe"):
            return False
        base = os.path.splitext(name)[0]
        if not base:
            return False
        base_lower = base.lower()

        target_pids = _target_pids_for(name)

        candidates = []

        try:
            candidates.extend(gw.getWindowsWithTitle(base) or [])
        except Exception:
            pass

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

        candidates = _filter_windows_by_pid(candidates, target_pids)

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


def activate_app_window(exe_path):
    if not exe_path:
        return False
    if HAS_PYWIN32 and _activate_via_pywin32(exe_path):
        return True
    if _activate_via_pygetwindow(exe_path):
        return True
    return False


def activate_with_retry(exe_path, attempts=3, delay=0.35):
    for _ in range(max(1, attempts)):
        if activate_app_window(exe_path):
            return True
        time.sleep(delay)
    return False