"""Маппинг FontAwesome -> Material Design Icons.

qtawesome умеет и fa5s.*, и mdi.*. Material-иконки визуально мягче
и современнее. Здесь единый словарь + функции получения иконки/паксмапа.

Если поставить USE_MDI = False — вернётся старое поведение (fa5s).
Если mdi-имя не загрузится — автоматом падаем на fa5s.
"""

try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False
    qta = None

from PySide6.QtGui import QIcon, QPixmap


# Главный переключатель: True — mdi, False — всегда fa5s
USE_MDI = True


# Все иконки, которые используются в проекте
FA_TO_MDI = {
    "fa5s.play":                  "mdi.play",
    "fa5s.pen":                   "mdi.pencil",
    "fa5s.folder-open":           "mdi.folder-open",
    "fa5s.folder":                "mdi.folder",
    "fa5s.star":                  "mdi.star",
    "fa5s.star-half-alt":         "mdi.star-off",
    "fa5s.gamepad":               "mdi.gamepad-variant",
    "fa5s.briefcase":             "mdi.briefcase",
    "fa5s.cog":                   "mdi.cog",
    "fa5s.box":                   "mdi.package-variant-closed",
    "fa5s.download":              "mdi.download",
    "fa5s.plus":                  "mdi.plus",
    "fa5s.minus":                 "mdi.minus",
    "fa5s.rocket":                "mdi.rocket-launch",
    "fa5s.thumbtack":             "mdi.pin",
    "fa5s.sun":                   "mdi.white-balance-sunny",
    "fa5s.moon":                  "mdi.moon-waning-crescent",
    "fa5s.compress":              "mdi.arrow-collapse",
    "fa5s.expand":                "mdi.arrow-expand-all",
    "fa5s.times":                 "mdi.close",
    "fa5s.window-minimize":       "mdi.window-minimize",
    "fa5s.window-maximize":       "mdi.window-maximize",
    "fa5s.window-restore":        "mdi.window-restore",
    "fa5s.search":                "mdi.magnify",
    "fa5s.chart-bar":             "mdi.chart-bar",
    "fa5s.sticky-note":           "mdi.note-text",
    "fa5s.link":                  "mdi.link-variant",
    "fa5s.arrow-circle-up":       "mdi.arrow-up-circle",
    "fa5s.stop-circle":           "mdi.stop-circle",
    "fa5s.check":                 "mdi.check",
    "fa5s.angle-up":              "mdi.chevron-up",
    "fa5s.angle-down":            "mdi.chevron-down",
    "fa5s.angle-double-up":       "mdi.chevron-double-up",
    "fa5s.angle-double-down":     "mdi.chevron-double-down",
    "fa5s.trash-alt":             "mdi.delete",
    "fa5s.undo":                  "mdi.undo",
    "fa5s.undo-alt":              "mdi.restore",
    "fa5s.tag":                   "mdi.tag",
    "fa5s.tags":                  "mdi.tag-multiple",
    "fa5s.image":                 "mdi.image",
    "fa5s.panorama":              "mdi.image-multiple",
    "fa5s.keyboard":              "mdi.keyboard",
    "fa5s.save":                  "mdi.content-save",
    "fa5s.palette":               "mdi.palette",
    "fa5s.user-cog":              "mdi.account-cog",
    "fa5s.feather":               "mdi.feather",
    "fa5s.film":                  "mdi.filmstrip",
    "fa5s.history":               "mdi.history",
    "fa5s.th-large":              "mdi.view-grid",
    "fa5s.exclamation-triangle":  "mdi.alert",
    "fa5s.hourglass-half":        "mdi.timer-sand",
    "fa5s.circle":                "mdi.circle",
    "fa5s.sliders-h":             "mdi.tune",
    "fa5s.file-export":           "mdi.file-export",
    "fa5s.file-import":           "mdi.file-import",
    "fa5s.cloud-upload-alt":      "mdi.cloud-upload",
    "fa5s.cloud-download-alt":    "mdi.cloud-download",
    "fa5s.broom":                 "mdi.broom",
    "fa5s.sync-alt":              "mdi.sync",
}


_mdi_failed = set()   # mdi-имена, которые не загрузились (чтобы не пытаться второй раз)
_cache = {}


def _mdi_name(fa_name):
    if not USE_MDI:
        return None
    return FA_TO_MDI.get(fa_name)


def _try_pixmap(name, size, color):
    """Пробует загрузить иконку и вернуть pixmap. None если не получилось."""
    try:
        ico = qta.icon(name, color=color)
        pix = ico.pixmap(size, size)
        if not pix.isNull():
            return pix
    except Exception:
        pass
    return None


def get_pixmap(name, size, color):
    """Возвращает QPixmap для иконки. mdi → fa5s → None."""
    if not HAS_QTAWESOME:
        return None
    key = ("pix", name, size, color)
    if key in _cache:
        return _cache[key]

    # 1) mdi
    mdi = _mdi_name(name)
    if mdi and mdi not in _mdi_failed:
        pix = _try_pixmap(mdi, size, color)
        if pix is not None:
            _cache[key] = pix
            return pix
        _mdi_failed.add(mdi)

    # 2) fa5s
    pix = _try_pixmap(name, size, color)
    _cache[key] = pix
    return pix


def get_icon(name, color):
    """Возвращает QIcon для иконки. mdi → fa5s → пустая."""
    if not HAS_QTAWESOME:
        return QIcon()
    key = ("icon", name, color)
    if key in _cache:
        return _cache[key]

    # 1) mdi
    mdi = _mdi_name(name)
    if mdi and mdi not in _mdi_failed:
        try:
            ico = qta.icon(mdi, color=color)
            # Проверка, что иконка реально есть
            if not ico.pixmap(16, 16).isNull():
                _cache[key] = ico
                return ico
        except Exception:
            pass
        _mdi_failed.add(mdi)

    # 2) fa5s
    try:
        ico = qta.icon(name, color=color)
        _cache[key] = ico
        return ico
    except Exception:
        empty = QIcon()
        _cache[key] = empty
        return empty


def clear_cache():
    _cache.clear()
    _mdi_failed.clear()