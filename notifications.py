"""Кросс-платформенные нотификации через plyer с fallback на Qt.

Если plyer установлен — используем его (нативные тосты Windows).
Иначе — QSystemTrayIcon.showMessage (встроенный).
"""

try:
    from plyer import notification as plyer_notif
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False
    plyer_notif = None

from config import APP_NAME

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")


def is_available():
    return HAS_PLYER


def notify(title, message, timeout=5, app_icon=None):
    """
    Показывает нативное уведомление.
    Если plyer доступен — использует его, иначе — Qt-трей.
    """
    if HAS_PLYER:
        try:
            plyer_notif.notify(
                title=title,
                message=message,
                app_name=APP_NAME,
                timeout=timeout,
                app_icon=app_icon or "",
            )
            return True
        except Exception as e:
            log.error(f"plyer notify: {e}")
            # Падаем на Qt
    return _notify_qt_fallback(title, message, timeout)


def _notify_qt_fallback(title, message, timeout):
    """Fallback на QSystemTrayIcon."""
    try:
        from PySide6.QtWidgets import QSystemTrayIcon, QApplication
        # Ищем любой трей-икон в приложении
        for widget in QApplication.topLevelWidgets():
            tray = getattr(widget, "tray", None)
            if tray is not None and isinstance(tray, QSystemTrayIcon):
                tray.showMessage(
                    title, message, QSystemTrayIcon.Information,
                    timeout * 1000,
                )
                return True
    except Exception as e:
        log.error(f"qt notify fallback: {e}")
    return False