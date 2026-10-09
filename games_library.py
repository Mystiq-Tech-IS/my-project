"""Библиотека установленных игр — отдельное окно-диалог.

Показывает сетку карточек с обложками, поиск, фильтр по источнику,
кнопку «Добавить в лаунчер», запуск по двойному клику.

Для каждой карточки показывается сегодняшнее время игры (если > 0).
"""

import os
import threading
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QScrollArea,
    QComboBox, QMenu, QApplication, QSizePolicy,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QThreadPool, QRunnable, QObject, QSize, QPointF,
    QRectF,
)
from PySide6.QtGui import (
    QCursor, QPixmap, QPainter, QColor, QPen, QBrush,
    QPainterPath, QFont, QIcon, QLinearGradient, QImage,
)

try:
    from storage import log, load_settings
except Exception:
    import logging
    log = logging.getLogger("launcher")
    def load_settings():
        return {}

try:
    from stats import (
        load_stats, get_today_seconds, get_total_seconds,
        format_short,
    )
except Exception:
    def load_stats():
        return {}
    def get_today_seconds(stats, path):
        return 0
    def get_total_seconds(stats, path):
        return 0
    def format_short(seconds):
        return ""

import game_scanner
import icon_map
from icons import get_icon

try:
    import cover_generator
    HAS_COVER_GEN = cover_generator.is_available()
except Exception:
    cover_generator = None
    HAS_COVER_GEN = False

try:
    import cover_fetcher
    HAS_COVER_FETCHER = True
except Exception:
    cover_fetcher = None
    HAS_COVER_FETCHER = False


_COVER_W = 400
_COVER_H = 280
_COVER_SHOW_NAME = False
_COVER_LIBRARY_STYLE = True


def _trim_transparent_pixmap(pix: QPixmap, alpha_threshold: int = 20) -> QPixmap:
    if pix is None or pix.isNull():
        return pix

    try:
        img = pix.toImage()
        if img.isNull():
            return pix

        w = img.width()
        h = img.height()
        if w <= 2 or h <= 2:
            return pix

        step = 4
        x0, y0 = w, h
        x1, y1 = -1, -1
        found = False

        for y in range(0, h, step):
            for x in range(0, w, step):
                if img.pixelColor(x, y).alpha() > alpha_threshold:
                    found = True
                    if x < x0: x0 = x
                    if y < y0: y0 = y
                    if x > x1: x1 = x
                    if y > y1: y1 = y

        if not found:
            return pix

        pad = step + 2
        x0 = max(0, x0 - pad)
        y0 = max(0, y0 - pad)
        x1 = min(w, x1 + pad)
        y1 = min(h, y1 + pad)

        if x1 - x0 < 4 or y1 - y0 < 4:
            return pix

        cropped = pix.copy(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
        return cropped if not cropped.isNull() else pix
    except Exception as e:
        log.error(f"_trim_transparent_pixmap: {e}")
        return pix


# ================== ФОНОВЫЕ ЗАДАЧИ ==================

class _CoverSignals(QObject):
    done = Signal(str, str)


class _CoverDownloadTask(QRunnable):
    def __init__(self, game, signals):
        super().__init__()
        self.game = game
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            appid = self.game.get("appid", "")
            path = ""
            if self.game.get("source") == "steam" and appid:
                path = game_scanner.download_steam_cover(appid, timeout=6)
            if not path:
                path = game_scanner.get_cover_for_game(self.game)
            self.signals.done.emit(self.game.get("path", ""), path or "")
        except Exception as e:
            log.error(f"_CoverDownloadTask: {e}")
            try:
                self.signals.done.emit(self.game.get("path", ""), "")
            except Exception:
                pass


class _WebCoverTask(QRunnable):
    class _Signals(QObject):
        done = Signal(str, str)

    def __init__(self, game, api_key, signals):
        super().__init__()
        self.game = game
        self.api_key = api_key
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        path = ""
        try:
            if not cover_fetcher or not self.api_key:
                self.signals.done.emit(self.game.get("path", ""), "")
                return
            if self.game.get("source") == "steam" and self.game.get("appid"):
                path = cover_fetcher.fetch_cover_by_steam_appid(
                    self.game["appid"], self.game.get("name", ""), self.api_key,
                )
            if not path:
                path = cover_fetcher.fetch_cover_by_name(
                    self.game.get("name", ""), self.api_key,
                )
        except Exception as e:
            log.error(f"_WebCoverTask.run: {e}")
        finally:
            try:
                self.signals.done.emit(self.game.get("path", ""), path or "")
            except Exception:
                pass


class _CoverGenTask(QRunnable):
    def __init__(self, game, colors, icon_png_path, signals):
        super().__init__()
        self.game = game
        self.colors = colors
        self.icon_png_path = icon_png_path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        path = ""
        try:
            if not self.icon_png_path:
                self.signals.done.emit(self.game.get("path", ""), "")
                return
            if cover_generator is None or not HAS_COVER_GEN:
                self.signals.done.emit(self.game.get("path", ""), "")
                return
            path = cover_generator.ensure_cover_file(
                self.game, self.colors,
                w=_COVER_W, h=_COVER_H,
                icon_png_path=self.icon_png_path,
                show_name=_COVER_SHOW_NAME,
                library_style=_COVER_LIBRARY_STYLE,
            ) or ""
        except Exception as e:
            log.error(f"_CoverGenTask.run: {e}")
        finally:
            if self.icon_png_path:
                try:
                    os.remove(self.icon_png_path)
                except Exception:
                    pass
            try:
                self.signals.done.emit(self.game.get("path", ""), path)
            except Exception:
                pass


class _ScannerSignals(QObject):
    done = Signal(list)


class _ScannerTask(QRunnable):
    def __init__(self, force, signals):
        super().__init__()
        self.force = force
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            games = game_scanner.get_games(force_rescan=self.force)
            self.signals.done.emit(games)
        except Exception as e:
            log.error(f"_ScannerTask: {e}")
            try:
                self.signals.done.emit([])
            except Exception:
                pass


# ================== КАРТОЧКА ==================

class GameCard(QFrame):
    clicked         = Signal(dict)
    double_clicked  = Signal(dict)
    right_clicked   = Signal(dict, object)
    button_clicked  = Signal(dict)

    def __init__(self, game, colors, is_in_launcher=False,
                 today_seconds=0, total_seconds=0, parent=None):
        super().__init__(parent)
        self.game = game
        self.colors = colors
        self.is_in_launcher = is_in_launcher
        self.today_seconds = int(today_seconds or 0)
        self.total_seconds = int(total_seconds or 0)
        self._cover_pix = None
        self._hover = False
        self._icon_cache = None

        self.setFixedSize(220, 280)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

    def set_cover_pixmap(self, pix):
        self._cover_pix = pix
        self.update()

    def set_time(self, today_seconds, total_seconds):
        self.today_seconds = int(today_seconds or 0)
        self.total_seconds = int(total_seconds or 0)
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def _is_over_action_button(self, pos):
        w = self.width()
        h = self.height()
        btn_x = 12
        btn_y = h - 38
        btn_w = w - 24
        btn_h = 28
        return (btn_x <= pos.x() <= btn_x + btn_w
                and btn_y <= pos.y() <= btn_y + btn_h)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            if self._is_over_action_button(pos):
                self.button_clicked.emit(self.game)
                return
            self.clicked.emit(self.game)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.game)

    def contextMenuEvent(self, event):
        try:
            self.right_clicked.emit(self.game, event.globalPos())
        except Exception:
            pass

    def _get_trimmed_icon(self, size=256):
        if self._icon_cache is not None:
            return self._icon_cache if not self._icon_cache.isNull() else None

        try:
            raw = get_icon(
                {"path": self.game.get("path", ""), "custom_icon": ""},
                size,
            )
            if not raw or raw.isNull():
                self._icon_cache = QPixmap()
                return None
            if raw.width() < 32 or raw.height() < 32:
                self._icon_cache = QPixmap()
                return None

            trimmed = _trim_transparent_pixmap(raw)
            if (trimmed.isNull()
                    or trimmed.width() < 16
                    or trimmed.height() < 16):
                self._icon_cache = QPixmap()
                return None

            self._icon_cache = trimmed
            return trimmed
        except Exception as e:
            log.error(f"_get_trimmed_icon: {e}")
            self._icon_cache = QPixmap()
            return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        c = self.colors
        w, h = self.width(), self.height()
        radius = 14
        border_w = 2 if self._hover else 1
        border_color = c["ACCENT"] if self._hover else c["BORDER"]

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["CARD_HOVER"] if self._hover else c["CARD"]))
        p.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        p.setPen(QPen(QColor(border_color), border_w))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(
            QRectF(border_w / 2, border_w / 2,
                   w - border_w, h - border_w),
            radius, radius,
        )

        cover_h = 160
        cover_rect = QRectF(1, 1, w - 2, cover_h - 1)

        clip = QPainterPath()
        cr = radius - 1
        clip.moveTo(cover_rect.left(), cover_rect.bottom())
        clip.lineTo(cover_rect.left(), cover_rect.top() + cr)
        clip.quadTo(
            cover_rect.left(), cover_rect.top(),
            cover_rect.left() + cr, cover_rect.top(),
        )
        clip.lineTo(cover_rect.right() - cr, cover_rect.top())
        clip.quadTo(
            cover_rect.right(), cover_rect.top(),
            cover_rect.right(), cover_rect.top() + cr,
        )
        clip.lineTo(cover_rect.right(), cover_rect.bottom())
        clip.closeSubpath()

        p.setClipPath(clip)

        if self._cover_pix and not self._cover_pix.isNull():
            p.drawPixmap(cover_rect.toRect(), self._cover_pix)
            grad = QLinearGradient(0, cover_h - 50, 0, cover_h)
            grad.setColorAt(0, QColor(0, 0, 0, 0))
            grad.setColorAt(1, QColor(0, 0, 0, 120))
            p.fillRect(QRectF(0, cover_h - 50, w, 50), QBrush(grad))
        else:
            grad = QLinearGradient(0, 0, 0, cover_h)
            grad.setColorAt(0, QColor(c["BG_ALT"]))
            grad.setColorAt(1, QColor(c["BG"]))
            p.fillRect(cover_rect, QBrush(grad))

            icon_pix = self._get_trimmed_icon(size=256)
            if icon_pix is not None:
                plate_size = 100
                target_side = 84
                scaled = icon_pix.scaled(
                    int(target_side), int(target_side),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                plate_x = (w - plate_size) / 2
                plate_y = (cover_h - plate_size) / 2

                p.setBrush(QColor(c["ACCENT_SOFT"]))
                p.setPen(QPen(QColor(c["ACCENT"]), 2))
                p.drawRoundedRect(
                    QRectF(plate_x, plate_y, plate_size, plate_size),
                    20, 20,
                )
                iw = scaled.width()
                ih = scaled.height()
                p.drawPixmap(
                    int(plate_x + (plate_size - iw) / 2),
                    int(plate_y + (plate_size - ih) / 2),
                    scaled,
                )
            else:
                name = (self.game.get("name") or "?").strip()
                letter = name[0].upper() if name else "?"

                cx = w / 2
                cy = cover_h / 2
                circle_r = 44

                accent = QColor(c["ACCENT"])
                accent.setAlpha(45)
                p.setPen(Qt.NoPen)
                p.setBrush(accent)
                p.drawEllipse(QPointF(cx, cy), circle_r, circle_r)

                p.setPen(QColor(c["ACCENT"]))
                letter_font = QFont("Segoe UI", 44)
                letter_font.setBold(True)
                p.setFont(letter_font)
                p.drawText(
                    QRectF(cx - circle_r, cy - circle_r,
                           circle_r * 2, circle_r * 2),
                    Qt.AlignCenter, letter,
                )

        p.setClipping(False)

        # ---- Badge источника ----
        source = self.game.get("source", "?")
        src_colors = {
            "steam":     ("#1B2838", "#66C0F4", "S"),
            "epic":      ("#2A2A2A", "#FFFFFF", "E"),
            "gog":       ("#5C2F87", "#FFFFFF", "G"),
            "battlenet": ("#148EFF", "#FFFFFF", "B"),
            "ubisoft":   ("#0084FF", "#FFFFFF", "U"),
            "ea":        ("#FF4747", "#FFFFFF", "EA"),
            "registry":  ("#444444", "#DDDDDD", "R"),
        }
        bg_col, fg_col, letter_badge = src_colors.get(
            source, ("#333", "#CCC", "?")
        )
        bs = 22
        bx = w - bs - 8
        by = 8
        bg_q = QColor(bg_col)
        bg_q.setAlpha(210)
        p.setPen(Qt.NoPen)
        p.setBrush(bg_q)
        p.drawRoundedRect(QRectF(bx, by, bs, bs), 6, 6)
        p.setPen(QColor(fg_col))
        f = QFont("Segoe UI", 8)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(bx, by, bs, bs), Qt.AlignCenter, letter_badge)

        # ---- «Уже в лаунчере» ----
        if self.is_in_launcher:
            tag_w = 100
            tag_h = 22
            tx = 8
            ty = 8
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["OK"]))
            p.drawRoundedRect(QRectF(tx, ty, tag_w, tag_h), 6, 6)
            p.setPen(QColor(c["BG"]))
            f2 = QFont("Segoe UI", 8)
            f2.setBold(True)
            p.setFont(f2)
            p.drawText(
                QRectF(tx, ty, tag_w, tag_h),
                Qt.AlignCenter, "УЖЕ В ЛАУНЧЕРЕ",
            )

        # ---- Имя игры ----
        info_y = cover_h + 8
        p.setPen(QColor(c["TEXT"]))
        name_font = QFont("Segoe UI", 10)
        name_font.setBold(True)
        p.setFont(name_font)
        name = self.game.get("name", "Без имени")
        if len(name) > 26:
            name = name[:24] + "…"
        p.drawText(
            QRectF(12, info_y, w - 24, 20),
            Qt.AlignLeft | Qt.AlignVCenter, name,
        )

        # ---- Источник ----
        src_text = {
            "steam": "Steam",
            "epic": "Epic Games",
            "gog": "GOG",
            "battlenet": "Battle.net",
            "ubisoft": "Ubisoft",
            "ea": "EA App",
            "registry": "Установлено в системе",
        }.get(source, source)

        p.setPen(QColor(c["SUBTEXT"]))
        sub_font = QFont("Segoe UI", 8)
        p.setFont(sub_font)
        src_y = info_y + 20
        p.drawText(
            QRectF(12, src_y, w - 24, 16),
            Qt.AlignLeft | Qt.AlignVCenter, src_text,
        )

        # ---- Время игры (сегодня / всего) ----
        if self.today_seconds > 0 or self.total_seconds > 0:
            parts = []
            if self.today_seconds > 0:
                parts.append(f"сегодня {format_short(self.today_seconds)}")
            if self.total_seconds > 60 and self.total_seconds != self.today_seconds:
                parts.append(f"всего {format_short(self.total_seconds)}")
            time_text = "  ·  ".join(parts)

            if time_text:
                p.setPen(QColor(c["ACCENT"]))
                time_font = QFont("Segoe UI", 8)
                time_font.setBold(True)
                p.setFont(time_font)
                time_y = src_y + 16
                p.drawText(
                    QRectF(12, time_y, w - 24, 16),
                    Qt.AlignLeft | Qt.AlignVCenter, time_text,
                )

        # ---- Кнопка внизу ----
        btn_y = h - 38
        btn_h = 28
        btn_x = 12
        btn_w = w - 24

        if self.is_in_launcher:
            bg = QColor(c["BG_ALT"])
            fg = QColor(c["SUBTEXT"])
            btn_text = "Убрать из лаунчера"
        else:
            bg = QColor(c["ACCENT"] if self._hover else c["ACCENT_SOFT"])
            fg = QColor(c["BG"] if self._hover else c["ACCENT"])
            btn_text = "Добавить в лаунчер"

        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(btn_x, btn_y, btn_w, btn_h), 8, 8)

        p.setPen(fg)
        btn_font = QFont("Segoe UI", 9)
        btn_font.setBold(True)
        p.setFont(btn_font)
        p.drawText(
            QRectF(btn_x, btn_y, btn_w, btn_h),
            Qt.AlignCenter, btn_text,
        )


# ================== ДИАЛОГ ==================

class GamesLibraryDialog(QDialog):
    def __init__(self, parent, colors, apps,
                 on_add_to_launcher,
                 on_remove_from_launcher,
                 on_launch_game):
        super().__init__(parent)
        self.colors = colors
        self.apps = apps or []
        self.on_add_to_launcher = on_add_to_launcher
        self.on_remove_from_launcher = on_remove_from_launcher
        self.on_launch_game = on_launch_game

        self.games = []
        self.cards = []
        self._load_task = None
        self._stats = {}

        self.setWindowTitle("Библиотека игр")
        self.setModal(False)
        self.resize(1000, 720)
        self.setMinimumSize(700, 500)

        self._build_ui()
        self._apply_theme()
        QTimer.singleShot(80, self._start_scan)

    def _build_ui(self):
        c = self.colors

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Библиотека игр")
        title.setStyleSheet(
            f"color: {c['ACCENT']}; font-size: 20px; font-weight: bold;"
        )
        header.addWidget(title)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 12px;"
        )
        header.addWidget(self.count_label)
        header.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск игры…")
        self.search_edit.setFixedWidth(240)
        self.search_edit.setFixedHeight(34)
        self.search_edit.textChanged.connect(self._filter)
        header.addWidget(self.search_edit)

        self.source_combo = QComboBox()
        self.source_combo.setFixedHeight(34)
        self.source_combo.setMinimumWidth(160)
        self.source_combo.addItem("Все источники", "all")
        self.source_combo.addItem("Steam", "steam")
        self.source_combo.addItem("Epic Games", "epic")
        self.source_combo.addItem("GOG", "gog")
        self.source_combo.addItem("Battle.net", "battlenet")
        self.source_combo.addItem("Ubisoft", "ubisoft")
        self.source_combo.addItem("EA App", "ea")
        self.source_combo.addItem("Только в системе", "registry")
        self.source_combo.currentIndexChanged.connect(self._filter)
        header.addWidget(self.source_combo)

        self.btn_refresh = QPushButton("  Пересканировать")
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_refresh.clicked.connect(self._rescan)
        header.addWidget(self.btn_refresh)

        root.addLayout(header)

        sub_row = QHBoxLayout()
        self.filter_only_in_launcher = QPushButton("  Только в лаунчере")
        self.filter_only_in_launcher.setCheckable(True)
        self.filter_only_in_launcher.setFixedHeight(30)
        self.filter_only_in_launcher.setCursor(QCursor(Qt.PointingHandCursor))
        self.filter_only_in_launcher.toggled.connect(self._filter)
        sub_row.addWidget(self.filter_only_in_launcher)

        self.filter_not_in_launcher = QPushButton("  Только не в лаунчере")
        self.filter_not_in_launcher.setCheckable(True)
        self.filter_not_in_launcher.setFixedHeight(30)
        self.filter_not_in_launcher.setCursor(QCursor(Qt.PointingHandCursor))
        self.filter_not_in_launcher.toggled.connect(self._filter)
        sub_row.addWidget(self.filter_not_in_launcher)

        sub_row.addStretch()

        self.today_label = QLabel("")
        self.today_label.setStyleSheet(
            f"color: {c['ACCENT']}; font-size: 12px; font-weight: bold;"
        )
        sub_row.addWidget(self.today_label)

        root.addLayout(sub_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

        root.addWidget(self.scroll, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 11px;"
        )
        root.addWidget(self.status_label)

        bottom = QHBoxLayout()
        bottom.addStretch()

        btn_download_covers = QPushButton("  Обновить обложки")
        btn_download_covers.setFixedHeight(34)
        btn_download_covers.setCursor(QCursor(Qt.PointingHandCursor))
        btn_download_covers.clicked.connect(self._download_all_covers)
        bottom.addWidget(btn_download_covers)

        btn_close = QPushButton("Закрыть")
        btn_close.setFixedHeight(34)
        btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        btn_close.setProperty("accent", True)
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)

        root.addLayout(bottom)

    def _apply_theme(self):
        c = self.colors
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['BG']}; }}
            QLabel  {{ color: {c['TEXT']}; background: transparent; }}
            QLineEdit, QComboBox {{
                background-color: {c['CARD']};
                color: {c['TEXT']};
                border: 1px solid {c['BORDER']};
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {c['ACCENT']};
            }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                background-color: {c['CARD']};
                color: {c['TEXT']};
                border: 1px solid {c['BORDER']};
                selection-background-color: {c['ACCENT_SOFT']};
                selection-color: {c['ACCENT']};
            }}
            QPushButton {{
                background-color: {c['CARD']};
                color: {c['TEXT']};
                border: 1px solid {c['BORDER']};
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {c['CARD_HOVER']};
                border: 1px solid {c['ACCENT']};
            }}
            QPushButton:checked {{
                background-color: {c['ACCENT']};
                color: {c['BG']};
                border: 1px solid {c['ACCENT']};
            }}
            QPushButton[accent="true"] {{
                background-color: {c['ACCENT']};
                color: {c['BG']};
            }}
                        QPushButton[accent="true"]:hover {{
                background-color: {c['ACCENT_HOV']};
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c['BORDER_HOV']}; border-radius: 4px;
                min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {c['ACCENT']}; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def _start_scan(self, force=False):
        self.status_label.setText("Сканирую установленные игры…")
        self.btn_refresh.setEnabled(False)

        signals = _ScannerSignals()
        signals.done.connect(self._on_scan_done)

        self._load_task = _ScannerTask(force, signals)
        QThreadPool.globalInstance().start(self._load_task)

    def _rescan(self):
        self._start_scan(force=True)

    def _on_scan_done(self, games):
        self.games = games or []
        self.count_label.setText(f"Найдено игр: {len(self.games)}")
        self.status_label.setText("")
        self.btn_refresh.setEnabled(True)

        # Загружаем статистику один раз
        try:
            self._stats = load_stats()
        except Exception:
            self._stats = {}

        self._clear_grid()
        for game in self.games:
            path = game.get("path", "")
            today_s = get_today_seconds(self._stats, path)
            total_s = get_total_seconds(self._stats, path)

            card = GameCard(
                game, self.colors,
                is_in_launcher=self._is_in_launcher(game),
                today_seconds=today_s,
                total_seconds=total_s,
            )
            card.double_clicked.connect(self._on_card_double_click)
            card.right_clicked.connect(self._on_card_right_click)
            card.button_clicked.connect(self._toggle_launcher_state)
            self.cards.append(card)

        self._update_today_total()
        self._filter()
        QTimer.singleShot(100, self._start_covers_download)

    def _update_today_total(self):
        """Обновляет надпись «Сегодня: Xч Yм» сверху."""
        try:
            total = 0
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            for entry in (self._stats or {}).values():
                daily = entry.get("daily") or {}
                total += int(daily.get(today, 0))
            if total > 0:
                self.today_label.setText(
                    f"Сегодня: {format_short(total)}"
                )
            else:
                self.today_label.setText("")
        except Exception:
            self.today_label.setText("")

    def _clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                try:
                    w.setParent(None)
                    w.deleteLater()
                except RuntimeError:
                    pass
        self.cards = []

    def _autocover_path(self, game):
        if cover_generator is None or not HAS_COVER_GEN:
            return ""
        try:
            key = cover_generator._cache_key(
                game, _COVER_W, _COVER_H,
                self.colors.get("ACCENT", "#89B4FA"),
                show_name=_COVER_SHOW_NAME,
                library_style=_COVER_LIBRARY_STYLE,
            )
            path = os.path.join(cover_generator.CACHE_DIR, f"{key}.png")
            if os.path.exists(path):
                return path
        except Exception:
            pass
        return ""

    def _start_covers_download(self):
        signals = _CoverSignals()
        signals.done.connect(self._on_cover_downloaded)

        api_key = ""
        sgdb_enabled = False
        try:
            settings = load_settings()
            api_key = (settings.get("steamgriddb_api_key") or "").strip()
            sgdb_enabled = bool(settings.get("steamgriddb_enabled", True))
        except Exception:
            pass
        if not sgdb_enabled:
            api_key = ""

        for game in self.games:
            local = game_scanner.get_cover_for_game(game)
            if not local and cover_fetcher is not None:
                local = cover_fetcher.find_local_cover_for_game(game)
            if not local:
                local = self._autocover_path(game)

            if local:
                pix = QPixmap(local)
                if not pix.isNull():
                    self._apply_cover_to_card(game, pix)
                    continue

            if game.get("source") == "steam" and game.get("appid"):
                task = _CoverDownloadTask(game, signals)
                QThreadPool.globalInstance().start(task)
                continue

            if api_key and cover_fetcher is not None:
                web_signals = _WebCoverTask._Signals()
                web_signals.done.connect(self._on_cover_downloaded)
                task = _WebCoverTask(game, api_key, web_signals)
                QThreadPool.globalInstance().start(task)

            self._schedule_cover_gen(game, signals)

    def _schedule_cover_gen(self, game, signals):
        if cover_generator is None or not HAS_COVER_GEN:
            return
        try:
            key = cover_generator._cache_key(
                game, _COVER_W, _COVER_H,
                self.colors.get("ACCENT", "#89B4FA"),
                show_name=_COVER_SHOW_NAME,
                library_style=_COVER_LIBRARY_STYLE,
            )
            icon_png = cover_generator._save_icon_as_png(game, key, 256)
            if not icon_png:
                return
            task = _CoverGenTask(game, self.colors, icon_png, signals)
            QThreadPool.globalInstance().start(task)
        except Exception as e:
            log.error(f"_schedule_cover_gen: {e}")

    def _on_cover_downloaded(self, game_path, local_path):
        if not local_path or not os.path.exists(local_path):
            return
        pix = QPixmap(local_path)
        if pix.isNull():
            return
        self._apply_cover_to_card_by_path(game_path, pix)

    def _apply_cover_to_card(self, game, pix):
        self._apply_cover_to_card_by_path(game.get("path", ""), pix)

    def _apply_cover_to_card_by_path(self, game_path, pix):
        try:
            w, h = 218, 158
            scaled = pix.scaled(
                int(w), int(h),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (scaled.width() - w) // 2)
            y = max(0, (scaled.height() - h) // 2)
            cropped = scaled.copy(int(x), int(y), int(w), int(h))
        except Exception:
            cropped = pix

        for card in self.cards:
            if card.game.get("path") == game_path:
                card.set_cover_pixmap(cropped)
                break

    def _download_all_covers(self):
        self.status_label.setText("Обновляю обложки в фоне…")
        signals = _CoverSignals()
        signals.done.connect(self._on_cover_downloaded)

        api_key = ""
        sgdb_enabled = False
        try:
            settings = load_settings()
            api_key = (settings.get("steamgriddb_api_key") or "").strip()
            sgdb_enabled = bool(settings.get("steamgriddb_enabled", True))
        except Exception:
            pass
        if not sgdb_enabled:
            api_key = ""

        for game in self.games:
            src = game.get("source")
            if src == "steam" and game.get("appid"):
                task = _CoverDownloadTask(game, signals)
                QThreadPool.globalInstance().start(task)
                continue

            if api_key and cover_fetcher is not None:
                web_signals = _WebCoverTask._Signals()
                web_signals.done.connect(self._on_cover_downloaded)
                task = _WebCoverTask(game, api_key, web_signals)
                QThreadPool.globalInstance().start(task)
            else:
                self._schedule_cover_gen(game, signals)

    def _is_in_launcher(self, game):
        path = (game.get("path") or "").lower()
        for a in self.apps:
            if (a.get("path") or "").lower() == path:
                return True
        return False

    def _filter(self):
        text = (self.search_edit.text() or "").lower().strip()
        source = self.source_combo.currentData()
        only_in = self.filter_only_in_launcher.isChecked()
        only_out = self.filter_not_in_launcher.isChecked()

        visible = 0
        viewport_w = self.scroll.viewport().width() - 20
        if viewport_w < 300:
            viewport_w = 900
        cols = max(1, (viewport_w + 14) // (220 + 14))

        while self.grid.count():
            self.grid.takeAt(0)

        r = 0
        col = 0
        for card in self.cards:
            g = card.game
            name = (g.get("name") or "").lower()
            src = g.get("source", "")

            if text and text not in name:
                continue
            if source != "all" and src != source:
                continue

            in_l = self._is_in_launcher(g)
            if only_in and not in_l:
                continue
            if only_out and in_l:
                continue

            self.grid.addWidget(card, r, col,
                                Qt.AlignTop | Qt.AlignLeft)
            col += 1
            if col >= cols:
                col = 0
                r += 1
            visible += 1

        for i in range(self.grid.columnCount()):
            self.grid.setColumnStretch(i, 0)
        self.grid.setColumnStretch(cols, 1)

        total = len(self.cards)
        self.count_label.setText(f"Показано {visible} из {total}")

    def _on_card_double_click(self, game):
        try:
            self.on_launch_game(game)
        except Exception as e:
            log.error(f"launch game from library: {e}")

    def _on_card_right_click(self, game, global_pos):
        c = self.colors
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {c['CARD']};
                color: {c['TEXT']};
                border: 1px solid {c['BORDER_HOV']};
                border-radius: 12px; padding: 6px; font-size: 13px;
            }}
            QMenu::item {{ padding: 8px 22px; border-radius: 8px; }}
            QMenu::item:selected {{
                background-color: {c['ACCENT_SOFT']};
                color: {c['ACCENT']};
            }}
            QMenu::separator {{
                height: 1px; background: {c['BORDER']};
                margin: 4px 8px;
            }}
        """)

        act_launch = menu.addAction("▶  Запустить")
        menu.addSeparator()

        in_l = self._is_in_launcher(game)
        if in_l:
            act_add = menu.addAction("✖  Убрать из лаунчера")
        else:
            act_add = menu.addAction("➕  Добавить в лаунчер")

        act_folder = menu.addAction("📂  Открыть папку установки")

        menu.addSeparator()
        act_dl_cover = menu.addAction("🖼  Обновить обложку")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return

        if chosen == act_launch:
            try:
                self.on_launch_game(game)
            except Exception:
                pass
        elif chosen == act_add:
            self._toggle_launcher_state(game)
        elif chosen == act_folder:
            self._open_folder(game)
        elif chosen == act_dl_cover:
            self._refresh_single_cover(game)

    def _refresh_single_cover(self, game):
        signals = _CoverSignals()
        signals.done.connect(self._on_cover_downloaded)

        api_key = ""
        sgdb_enabled = False
        try:
            settings = load_settings()
            api_key = (settings.get("steamgriddb_api_key") or "").strip()
            sgdb_enabled = bool(settings.get("steamgriddb_enabled", True))
        except Exception:
            pass
        if not sgdb_enabled:
            api_key = ""

        src = game.get("source")
        if src == "steam" and game.get("appid"):
            task = _CoverDownloadTask(game, signals)
            QThreadPool.globalInstance().start(task)
            return

        if api_key and cover_fetcher is not None:
            web_signals = _WebCoverTask._Signals()
            web_signals.done.connect(self._on_cover_downloaded)
            task = _WebCoverTask(game, api_key, web_signals)
            QThreadPool.globalInstance().start(task)
        else:
            self._schedule_cover_gen(game, signals)

    def _toggle_launcher_state(self, game):
        in_l = self._is_in_launcher(game)
        try:
            if in_l:
                self.on_remove_from_launcher(game)
            else:
                self.on_add_to_launcher(game)
        except Exception as e:
            log.error(f"toggle launcher state: {e}")

        for card in self.cards:
            card.is_in_launcher = self._is_in_launcher(card.game)
            card.update()
        self._filter()

    def _open_folder(self, game):
        folder = game.get("install_dir") or ""
        if folder and os.path.isdir(folder):
            try:
                os.startfile(folder)
            except Exception as e:
                log.error(f"open folder: {e}")

    def refresh_apps(self, apps):
        self.apps = apps or []
        for card in self.cards:
            card.is_in_launcher = self._is_in_launcher(card.game)
            card.update()
        self._filter()

    def refresh_stats(self):
        """Перечитать статистику и обновить время на карточках."""
        try:
            self._stats = load_stats()
        except Exception:
            self._stats = {}
        for card in self.cards:
            path = card.game.get("path", "")
            card.set_time(
                get_today_seconds(self._stats, path),
                get_total_seconds(self._stats, path),
            )
        self._update_today_total()