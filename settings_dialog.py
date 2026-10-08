"""Окно настроек лаунчера с вкладками."""

import os
import json
import webbrowser
import subprocess
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QSpinBox, QFileDialog,
    QListWidget, QListWidgetItem, QMessageBox, QTabWidget,
    QWidget, QFormLayout, QScrollArea, QFrame, QGridLayout,
    QInputDialog, QColorDialog, QSlider,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor

try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False
    qta = None

from dialogs import dialog_qss, show_info, show_error
from storage import log, BACKUP_DIR
from icons import clear_cache
from config import (
    BASE_DIR, APP_VERSION, GITHUB_REPO_URL, LATEST_VERSION, CATEGORIES,
)
import autostart
import icon_map
import sounds
import stats_charts
import window_activation
import sysmonitor

from stats import (
    load_stats, get_top, format_duration, reset_stats, by_category,
)
from profiles import (
    all_profiles, apply_profile, current_overrides,
    save_user_override, reset_profile,
)

from themes import (
    ACCENTS, ACCENT_LABELS,
    is_hex, normalize_hex, lighten, darken,
)


def _fa_icon(name, color):
    return icon_map.get_icon(name, color)


SOUND_EVENT_LABELS = [
    ("launch",  "Запуск программы"),
    ("close",   "Завершение процесса"),
    ("success", "Успешное действие"),
    ("error",   "Ошибки"),
    ("notify",  "Уведомления"),
    ("toggle",  "Переключение категории / темы"),
    ("click",   "Клики по кнопкам"),
]

VOICE_EVENT_LABELS = [
    ("startup",  "Запуск лаунчера"),
    ("launch",   "Запуск программы"),
    ("close",    "Завершение процесса"),
    ("error",    "Ошибка"),
    ("success",  "Успешное действие"),
    ("info",     "Инфо-уведомления"),
    ("shutdown", "Выход из лаунчера"),
]


# ==================== РЕДАКТОР КАТЕГОРИИ ====================
class CategoryEditorDialog(QDialog):
    def __init__(self, parent, colors, cat_key, settings, apps_list):
        super().__init__(parent)
        self.colors = colors
        self.cat_key = cat_key
        self.settings = settings
        self.apps_list = apps_list

        cat_name, cat_emoji = CATEGORIES.get(cat_key, (cat_key, ""))

        self.setWindowTitle(f"Категория: {cat_name}")
        self.setStyleSheet(dialog_qss(colors))
        self.setMinimumWidth(560)
        self.setMinimumHeight(560)

        self._companions = list(
            (settings.get("category_companions") or {}).get(cat_key, []) or []
        )
        self._cover_folder = (
            (settings.get("category_covers") or {}).get(cat_key, "") or ""
        )
        self._subcats = list(
            (settings.get("subcategories") or {}).get(cat_key, []) or []
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel(f"{cat_emoji}  {cat_name}")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        root.addWidget(title)

        h1 = QLabel("Спутники запуска")
        h1.setProperty("sectionHeader", True)
        root.addWidget(h1)

        hint1 = QLabel(
            "Когда запускается любая программа из категории, "
            "автоматически стартуют все эти приложения."
        )
        hint1.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 11px;")
        hint1.setWordWrap(True)
        root.addWidget(hint1)

        self.companions_lw = QListWidget()
        self.companions_lw.setStyleSheet(f"""
            QListWidget {{
                background-color: {colors['BG_ALT']};
                color: {colors['TEXT']};
                border: 1px solid {colors['BORDER']};
                border-radius: 10px;
                padding: 6px;
                font-size: 13px;
            }}
            QListWidget::item {{ padding: 8px; border-radius: 6px; }}
        """)
        self.companions_lw.setMaximumHeight(120)
        root.addWidget(self.companions_lw)

        comp_btns = QHBoxLayout()
        edit_comp = QPushButton("  Изменить список")
        edit_comp.setIcon(_fa_icon("fa5s.pen", colors["TEXT"]))
        edit_comp.clicked.connect(self._edit_companions)
        comp_btns.addWidget(edit_comp)
        comp_btns.addStretch()
        root.addLayout(comp_btns)

        h2 = QLabel("Папка с авто-обложками")
        h2.setProperty("sectionHeader", True)
        root.addWidget(h2)

        hint2 = QLabel(
            "Если у программы нет своей обложки, ей будет назначена "
            "случайная картинка из этой папки."
        )
        hint2.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 11px;")
        hint2.setWordWrap(True)
        root.addWidget(hint2)

        cover_row = QHBoxLayout()
        self.cover_edit = QLineEdit(self._cover_folder)
        self.cover_edit.setReadOnly(True)
        self.cover_edit.setPlaceholderText("(не задана)")
        cover_row.addWidget(self.cover_edit, 1)

        btn_pick = QPushButton("  Выбрать")
        btn_pick.setIcon(_fa_icon("fa5s.folder-open", colors["TEXT"]))
        btn_pick.clicked.connect(self._pick_cover_folder)
        cover_row.addWidget(btn_pick)

        btn_clear = QPushButton("  Очистить")
        btn_clear.setIcon(_fa_icon("fa5s.times", colors["DANGER"]))
        btn_clear.clicked.connect(self._clear_cover_folder)
        cover_row.addWidget(btn_clear)
        root.addLayout(cover_row)

        h3 = QLabel("Подкатегории")
        h3.setProperty("sectionHeader", True)
        root.addWidget(h3)

        hint3 = QLabel(
            "Раздели категорию на группы. Позже в фильтре можно будет "
            "показывать только одну группу."
        )
        hint3.setStyleSheet(f"color: {colors['SUBTEXT']}; font-size: 11px;")
        hint3.setWordWrap(True)
        root.addWidget(hint3)

        self.subcats_lw = QListWidget()
        self.subcats_lw.setStyleSheet(self.companions_lw.styleSheet())
        self.subcats_lw.setMaximumHeight(140)
        root.addWidget(self.subcats_lw)

        sub_btns = QHBoxLayout()
        btn_add_sub = QPushButton("  Добавить")
        btn_add_sub.setIcon(_fa_icon("fa5s.plus", colors["TEXT"]))
        btn_add_sub.clicked.connect(self._add_subcat)
        sub_btns.addWidget(btn_add_sub)

        btn_del_sub = QPushButton("  Удалить выбранную")
        btn_del_sub.setIcon(_fa_icon("fa5s.trash-alt", colors["DANGER"]))
        btn_del_sub.clicked.connect(self._del_subcat)
        sub_btns.addWidget(btn_del_sub)
        sub_btns.addStretch()
        root.addLayout(sub_btns)

        root.addStretch()

        bottom = QHBoxLayout()
        bottom.addStretch()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        ok = QPushButton("Сохранить")
        ok.setProperty("accent", True)
        ok.clicked.connect(self._save)
        bottom.addWidget(ok)
        root.addLayout(bottom)

        self._refresh_companions()
        self._refresh_subcats()

    def _refresh_companions(self):
        self.companions_lw.clear()
        if not self._companions:
            item = QListWidgetItem("нет спутников")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.companions_lw.addItem(item)
            return
        for p in self._companions:
            base = os.path.basename(p)
            item = QListWidgetItem(f"🔗  {base}")
            item.setToolTip(p)
            self.companions_lw.addItem(item)

    def _edit_companions(self):
        from companion_picker import CompanionPickerDialog
        try:
            dlg = CompanionPickerDialog(
                self, self.colors, self.apps_list,
                current_path="",
                companions=self._companions,
            )
        except Exception as e:
            show_error(self, self.colors, "Ошибка", str(e))
            return
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._companions = dlg.result_companions or []
        self._refresh_companions()

    def _pick_cover_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку с обложками",
            self._cover_folder or BASE_DIR,
        )
        if not folder:
            return
        self._cover_folder = folder
        self.cover_edit.setText(folder)

    def _clear_cover_folder(self):
        self._cover_folder = ""
        self.cover_edit.setText("")

    def _refresh_subcats(self):
        self.subcats_lw.clear()
        if not self._subcats:
            item = QListWidgetItem("нет подкатегорий")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.subcats_lw.addItem(item)
            return
        for s in self._subcats:
            self.subcats_lw.addItem(QListWidgetItem(s))

    def _add_subcat(self):
        text, ok = QInputDialog.getText(
            self, "Новая подкатегория",
            "Название (например: Shooters):"
        )
        if not ok:
            return
        text = text.strip()
        if not text or text in self._subcats:
            return
        self._subcats.append(text)
        self._refresh_subcats()

    def _del_subcat(self):
        item = self.subcats_lw.currentItem()
        if not item:
            return
        if item.flags() & Qt.ItemFlag.ItemIsSelectable == 0:
            return
        text = item.text()
        if text in self._subcats:
            self._subcats.remove(text)
            self._refresh_subcats()

    def _save(self):
        cc = dict(self.settings.get("category_companions") or {})
        cv = dict(self.settings.get("category_covers") or {})
        sc = dict(self.settings.get("subcategories") or {})

        cc[self.cat_key] = list(self._companions)
        cv[self.cat_key] = self._cover_folder
        sc[self.cat_key] = list(self._subcats)

        self.settings["category_companions"] = cc
        self.settings["category_covers"] = cv
        self.settings["subcategories"] = sc
        self.accept()


# ==================== ОКНО НАСТРОЕК ====================
class SettingsDialog(QDialog):
    def __init__(self, parent, colors, settings,
                 apps_provider=None, apps_list=None):
        super().__init__(parent)
        self.colors = colors
        self.parent_window = parent
        self.apps_provider = apps_provider
        self.apps_list = apps_list or []
        self.settings = dict(settings)
        for k in ("category_companions", "category_covers",
                  "subcategories", "sound_events", "voice_events"):
            self.settings[k] = dict(settings.get(k) or {})
        self.settings["enabled_plugins"] = list(
            settings.get("enabled_plugins") or []
        )
        self.selected_accent = settings.get("accent", "blue")
        self.accent_btns = {}
        self.custom_swatch_btn = None
        self._plugin_checks = {}

        self.setWindowTitle("Настройки")
        self.setStyleSheet(dialog_qss(colors) + f"""
            QTabWidget::pane {{
                border: 1px solid {colors['BORDER']};
                border-radius: 12px;
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: {colors['BG_ALT']};
                color: {colors['SUBTEXT']};
                padding: 10px 18px;
                margin-right: 4px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-size: 13px;
                font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background-color: {colors['ACCENT']};
                color: {colors['BG']};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {colors['CARD_HOVER']};
                color: {colors['TEXT']};
            }}
            QCheckBox {{ color: {colors['TEXT']}; font-size: 13px; }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border-radius: 5px;
                border: 1px solid {colors['CARD_HOVER']};
                background: {colors['CARD']};
            }}
            QCheckBox::indicator:checked {{
                background: {colors['ACCENT']};
            }}
            QSpinBox, QComboBox {{
                background-color: {colors['CARD']};
                color: {colors['TEXT']};
                border: 1px solid {colors['BORDER']};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
                min-width: 90px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 16px;
                border: none;
            }}
            QSlider::groove:horizontal {{
                background: {colors['CARD_HOVER']};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {colors['ACCENT']};
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: {colors['ACCENT']};
                height: 6px;
                border-radius: 3px;
            }}
            QLabel[formLabel="true"] {{
                color: {colors['TEXT']};
                font-size: 13px;
            }}
            QLabel[sectionHeader="true"] {{
                color: {colors['ACCENT']};
                font-size: 14px;
                font-weight: bold;
                padding-top: 10px;
            }}
            QFrame[card="true"] {{
                background-color: {colors['BG_ALT']};
                border: 1px solid {colors['BORDER']};
                border-radius: 12px;
            }}
        """)
        self.setMinimumWidth(760)
        self.setMinimumHeight(680)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setFixedSize(24, 24)
        pix = _fa_icon("fa5s.sliders-h", colors["ACCENT"]).pixmap(22, 22)
        if not pix.isNull():
            title_icon.setPixmap(pix)
        header.addWidget(title_icon)
        title = QLabel("Настройки")
        title.setStyleSheet(
            f"color: {colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_appearance_tab()
        self._build_behavior_tab()
        self._build_categories_tab()
        self._build_profiles_tab()
        self._build_data_tab()
        self._build_plugins_tab()
        self._build_about_tab()

        self._add_plugin_tabs()

        bottom = QHBoxLayout()
        bottom.addStretch()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        ok = QPushButton("Сохранить")
        ok.setProperty("accent", True)
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        bottom.addWidget(ok)
        root.addLayout(bottom)

    # ==================== ВКЛАДКА 1: ВНЕШНИЙ ВИД ====================
    def _build_appearance_tab(self):
        c = self.colors
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        outer_lay.addWidget(scroll)

        tab = QWidget()
        scroll.setWidget(tab)

        lay = QVBoxLayout(tab)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        # ---- Тема ----
        h = QLabel("Тема оформления")
        h.setProperty("sectionHeader", True)
        lay.addWidget(h)

        theme_row = QHBoxLayout()
        theme_label = QLabel("Тема:")
        theme_label.setProperty("formLabel", True)
        theme_row.addWidget(theme_label)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Тёмная", "dark")
        self.theme_combo.addItem("Светлая", "light")
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == self.settings.get("theme", "dark"):
                self.theme_combo.setCurrentIndex(i)
                break
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        lay.addLayout(theme_row)

        # ---- Акцент ----
        accent_label = QLabel("Акцентный цвет:")
        accent_label.setProperty("formLabel", True)
        lay.addWidget(accent_label)

        accent_row = QHBoxLayout()
        accent_row.setSpacing(8)

        for key in ACCENTS.keys():
            btn = QPushButton()
            btn.setFixedSize(38, 38)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(ACCENT_LABELS.get(key, key))
            btn.clicked.connect(lambda _=False, k=key: self._select_accent(k))
            accent_row.addWidget(btn)
            self.accent_btns[key] = btn

        sep = QLabel("│")
        sep.setStyleSheet(
            f"color: {c['BORDER_HOV']}; font-size: 22px; "
            f"background: transparent; padding: 0 4px;"
        )
        accent_row.addWidget(sep)

        self.custom_swatch_btn = QPushButton()
        self.custom_swatch_btn.setFixedSize(38, 38)
        self.custom_swatch_btn.setCursor(Qt.PointingHandCursor)
        self.custom_swatch_btn.setToolTip("Свой цвет…")
        self.custom_swatch_btn.clicked.connect(self._pick_custom_accent)
        accent_row.addWidget(self.custom_swatch_btn)

        self.accent_hex_label = QLabel("")
        self.accent_hex_label.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 12px; "
            f"background: transparent; padding-left: 6px;"
        )
        accent_row.addWidget(self.accent_hex_label)

        accent_row.addStretch()
        lay.addLayout(accent_row)

        self._refresh_accent_buttons()

        # ---- Размеры ----
        h2 = QLabel("Размеры и стиль")
        h2.setProperty("sectionHeader", True)
        lay.addWidget(h2)

        sizes = QFormLayout()
        sizes.setSpacing(10)

        self.tile_scale = QSpinBox()
        self.tile_scale.setRange(80, 150)
        self.tile_scale.setSuffix(" %")
        self.tile_scale.setValue(int(self.settings.get("tile_scale", 100)))
        sizes.addRow("Размер плиток:", self.tile_scale)

        self.icon_scale = QSpinBox()
        self.icon_scale.setRange(80, 150)
        self.icon_scale.setSuffix(" %")
        self.icon_scale.setValue(int(self.settings.get("icon_scale", 100)))
        sizes.addRow("Размер иконок:", self.icon_scale)

        self.anim_speed = QSpinBox()
        self.anim_speed.setRange(50, 200)
        self.anim_speed.setSuffix(" %")
        self.anim_speed.setValue(int(self.settings.get("animation_speed", 100)))
        sizes.addRow("Скорость анимаций:", self.anim_speed)

        lay.addLayout(sizes)

        self.chk_material_icons = QCheckBox(
            "Использовать иконки Material Design (вместо Font Awesome)"
        )
        self.chk_material_icons.setChecked(
            self.settings.get("use_material_icons", True)
        )
        lay.addWidget(self.chk_material_icons)

        # ---- Элементы интерфейса ----
        h3 = QLabel("Элементы интерфейса")
        h3.setProperty("sectionHeader", True)
        lay.addWidget(h3)

        checks_grid = QGridLayout()
        checks_grid.setSpacing(10)

        self.chk_clock = QCheckBox("Показывать часы")
        self.chk_clock.setChecked(self.settings.get("show_clock", True))

        self.chk_search = QCheckBox("Показывать поиск")
        self.chk_search.setChecked(self.settings.get("show_search", True))

        self.chk_running = QCheckBox("Секция «Запущено»")
        self.chk_running.setChecked(self.settings.get("show_running_section", True))

        self.chk_covers = QCheckBox("Обложки программ")
        self.chk_covers.setChecked(self.settings.get("show_covers", True))

        self.chk_glow = QCheckBox("Свечение запущенных")
        self.chk_glow.setChecked(self.settings.get("show_glow", True))

        self.chk_status = QCheckBox("Текст статуса")
        self.chk_status.setChecked(self.settings.get("show_status_text", True))

        self.chk_headers = QCheckBox("Заголовки секций")
        self.chk_headers.setChecked(self.settings.get("show_section_headers", True))

        self.chk_badges = QCheckBox("Бейджи на плитках")
        self.chk_badges.setChecked(self.settings.get("show_tile_badges", True))

        self.chk_scrollbar = QCheckBox("Скрыть полосу прокрутки")
        self.chk_scrollbar.setChecked(self.settings.get("hide_scrollbar", False))

        checks_grid.addWidget(self.chk_clock, 0, 0)
        checks_grid.addWidget(self.chk_search, 0, 1)
        checks_grid.addWidget(self.chk_running, 1, 0)
        checks_grid.addWidget(self.chk_covers, 1, 1)
        checks_grid.addWidget(self.chk_glow, 2, 0)
        checks_grid.addWidget(self.chk_status, 2, 1)
        checks_grid.addWidget(self.chk_headers, 3, 0)
        checks_grid.addWidget(self.chk_badges, 3, 1)
        checks_grid.addWidget(self.chk_scrollbar, 4, 0)

        lay.addLayout(checks_grid)

        # ---- Мониторинг системы ----
        h_mon = QLabel("Мониторинг системы")
        h_mon.setProperty("sectionHeader", True)
        lay.addWidget(h_mon)

        monitor_hint = QLabel(
            "Показывает загрузку CPU / RAM / GPU в правом сайдбаре."
        )
        monitor_hint.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 11px;")
        monitor_hint.setWordWrap(True)
        lay.addWidget(monitor_hint)

        self.chk_monitor = QCheckBox("Показывать мониторинг в сайдбаре")
        self.chk_monitor.setChecked(
            self.settings.get("show_system_monitor", True)
        )
        lay.addWidget(self.chk_monitor)

        interval_row = QHBoxLayout()
        interval_lbl = QLabel("Период обновления:")
        interval_lbl.setProperty("formLabel", True)
        interval_row.addWidget(interval_lbl)

        self.combo_monitor_interval = QComboBox()
        self.combo_monitor_interval.addItem("1 секунда", 1)
        self.combo_monitor_interval.addItem("2 секунды", 2)
        self.combo_monitor_interval.addItem("5 секунд", 5)
        self.combo_monitor_interval.addItem("10 секунд", 10)

        cur_int = int(self.settings.get("system_monitor_interval", 2))
        idx = self.combo_monitor_interval.findData(cur_int)
        if idx < 0:
            idx = 1
        self.combo_monitor_interval.setCurrentIndex(idx)
        interval_row.addWidget(self.combo_monitor_interval)

        interval_row.addStretch()
        lay.addLayout(interval_row)

        try:
            info = sysmonitor.is_supported()
            has_psutil = info.get("psutil", False)
            has_gpu = info.get("gpu", False)
        except Exception:
            has_psutil = False
            has_gpu = False

        if has_psutil and has_gpu:
            av_lbl = QLabel("✅ psutil и nvidia-ml-py найдены — CPU, RAM и GPU доступны")
            av_lbl.setStyleSheet(f"color: {c['OK']}; font-size: 11px;")
        elif has_psutil:
            av_lbl = QLabel(
                "✅ psutil найден — CPU и RAM работают.\n"
                "⚠ GPU отключён: нет nvidia-ml-py."
            )
            av_lbl.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 11px;")
        else:
            av_lbl = QLabel(
                "❌ psutil не найден — мониторинг недоступен."
            )
            av_lbl.setStyleSheet(f"color: {c['DANGER']}; font-size: 11px;")
        av_lbl.setWordWrap(True)
        lay.addWidget(av_lbl)

        # ---- Splash + фон ----
        h_extra = QLabel("Оформление и анимация")
        h_extra.setProperty("sectionHeader", True)
        lay.addWidget(h_extra)

        self.chk_splash = QCheckBox("Показывать splash screen при запуске")
        self.chk_splash.setChecked(self.settings.get("splash_enabled", True))
        lay.addWidget(self.chk_splash)

        self.chk_bg_anim = QCheckBox("Анимированный фон (частицы)")
        self.chk_bg_anim.setChecked(
            self.settings.get("bg_animation_enabled", True)
        )
        lay.addWidget(self.chk_bg_anim)

        particles_row = QHBoxLayout()
        particles_lbl = QLabel("Количество частиц:")
        particles_lbl.setProperty("formLabel", True)
        particles_row.addWidget(particles_lbl)

        self.spin_particles = QSpinBox()
        self.spin_particles.setRange(8, 80)
        self.spin_particles.setValue(
            int(self.settings.get("bg_animation_particles", 28))
        )
        particles_row.addWidget(self.spin_particles)
        particles_row.addStretch()
        lay.addLayout(particles_row)

        lay.addStretch()
        self.tabs.addTab(outer, "  Внешний вид")

    # ==================== ВКЛАДКА 2: ПОВЕДЕНИЕ ====================
    def _build_behavior_tab(self):
        c = self.colors
        outer_tab = QWidget()
        outer_lay = QVBoxLayout(outer_tab)
        outer_lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        outer_lay.addWidget(scroll)

        tab = QWidget()
        scroll.setWidget(tab)

        lay = QVBoxLayout(tab)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        # ---- Горячие клавиши ----
        h = QLabel("Горячие клавиши")
        h.setProperty("sectionHeader", True)
        lay.addWidget(h)

        form = QFormLayout()
        form.setSpacing(10)

        self.hotkey_edit = QLineEdit(self.settings.get("hotkey", "ctrl+alt+l"))
        self.hotkey_edit.setPlaceholderText("например: ctrl+alt+l")
        form.addRow("Показать/скрыть окно:", self.hotkey_edit)

        self.quick_hotkey_edit = QLineEdit(
            self.settings.get("quick_hotkey", "ctrl+alt+space")
        )
        self.quick_hotkey_edit.setPlaceholderText("например: ctrl+alt+space")
        form.addRow("Быстрый поиск:", self.quick_hotkey_edit)

        lay.addLayout(form)

        # ---- Запуск и закрытие ----
        h2 = QLabel("Запуск и закрытие")
        h2.setProperty("sectionHeader", True)
        lay.addWidget(h2)

        start_row = QHBoxLayout()
        start_lbl = QLabel("При запуске:")
        start_lbl.setProperty("formLabel", True)
        start_row.addWidget(start_lbl)
        self.start_view_combo = QComboBox()
        self.start_view_combo.addItem("Обычное окно", "normal")
        self.start_view_combo.addItem("Развёрнутое", "maximized")
        self.start_view_combo.addItem("Полный экран", "fullscreen")
        self.start_view_combo.addItem("Тихо в трее", "tray")
        for i in range(self.start_view_combo.count()):
            if self.start_view_combo.itemData(i) == self.settings.get("start_view", "normal"):
                self.start_view_combo.setCurrentIndex(i)
                break
        start_row.addWidget(self.start_view_combo)
        start_row.addStretch()
        lay.addLayout(start_row)

        self.chk_ontop = QCheckBox("Поверх всех окон")
        self.chk_ontop.setChecked(self.settings.get("always_on_top", True))
        lay.addWidget(self.chk_ontop)

        self.chk_tray = QCheckBox("Сворачивать в трей (крестиком)")
        self.chk_tray.setChecked(self.settings.get("close_to_tray", True))
        lay.addWidget(self.chk_tray)

        self.chk_silent = QCheckBox(
            "Тихий запуск (стартовать в трее, не показывая окно)"
        )
        self.chk_silent.setChecked(self.settings.get("silent_start", False))
        lay.addWidget(self.chk_silent)

        self.chk_autostart = QCheckBox("Запускать вместе с Windows")
        try:
            self.chk_autostart.setChecked(autostart.is_enabled())
        except Exception:
            self.chk_autostart.setChecked(False)
        lay.addWidget(self.chk_autostart)

        # ---- Прочее ----
        h3 = QLabel("Прочее")
        h3.setProperty("sectionHeader", True)
        lay.addWidget(h3)

        self.chk_confirm_kill = QCheckBox(
            "Спрашивать подтверждение при завершении процесса"
        )
        self.chk_confirm_kill.setChecked(
            self.settings.get("confirm_kill", True)
        )
        lay.addWidget(self.chk_confirm_kill)

        self.chk_overlay = QCheckBox("Показывать оверлей при запуске")
        self.chk_overlay.setChecked(self.settings.get("overlay_enabled", True))
        lay.addWidget(self.chk_overlay)

        self.chk_companions = QCheckBox("Автозапуск спутников")
        self.chk_companions.setChecked(
            self.settings.get("companions_enabled", True)
        )
        lay.addWidget(self.chk_companions)

        # ---- Активация окон ----
        h_aw = QLabel("Активация окон")
        h_aw.setProperty("sectionHeader", True)
        lay.addWidget(h_aw)

        self.chk_switch_on_running = QCheckBox(
            "При клике на запущенную программу — сразу переключаться в её окно"
        )
        self.chk_switch_on_running.setChecked(
            self.settings.get("switch_to_window_on_running", False)
        )
        lay.addWidget(self.chk_switch_on_running)

        self.chk_activate_after_launch = QCheckBox(
            "После запуска переключаться в окно программы"
        )
        self.chk_activate_after_launch.setChecked(
            self.settings.get("activate_after_launch", False)
        )
        lay.addWidget(self.chk_activate_after_launch)

        if not window_activation.has_support():
            aw_warn = QLabel(
                "⚠ Установите библиотеку pywin32 для точной активации."
            )
            aw_warn.setStyleSheet(
                f"color: {c['DANGER']}; font-size: 11px; padding-top: 4px;"
            )
            aw_warn.setWordWrap(True)
            lay.addWidget(aw_warn)

        # ---- Звуки ----
        h4 = QLabel("Звуки интерфейса")
        h4.setProperty("sectionHeader", True)
        lay.addWidget(h4)

        self.chk_sounds = QCheckBox("Включить звуки")
        self.chk_sounds.setChecked(self.settings.get("sound_enabled", True))
        lay.addWidget(self.chk_sounds)

        volume_row = QHBoxLayout()
        vol_lbl = QLabel("Громкость:")
        vol_lbl.setProperty("formLabel", True)
        volume_row.addWidget(vol_lbl)

        self.slider_volume = QSlider(Qt.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(int(self.settings.get("sound_volume", 60)))
        self.slider_volume.setMinimumWidth(220)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        volume_row.addWidget(self.slider_volume)

        self.lbl_volume = QLabel(f"{self.slider_volume.value()} %")
        self.lbl_volume.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 12px; background: transparent;"
        )
        self.lbl_volume.setMinimumWidth(46)
        volume_row.addWidget(self.lbl_volume)
        volume_row.addStretch()
        lay.addLayout(volume_row)

        sounds_hint = QLabel("Отметь, какие события озвучивать:")
        sounds_hint.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 11px;")
        lay.addWidget(sounds_hint)

        self.sound_event_boxes = {}
        events_grid = QGridLayout()
        events_grid.setSpacing(8)

        for i, (key, label) in enumerate(SOUND_EVENT_LABELS):
            box = QCheckBox(label)
            box.setChecked(bool(
                (self.settings.get("sound_events") or {}).get(key, True)
            ))
            events_grid.addWidget(box, i // 2, i % 2)
            self.sound_event_boxes[key] = box
        lay.addLayout(events_grid)

        sound_btns = QHBoxLayout()
        sound_btns.setSpacing(8)

        btn_test = QPushButton("  Проверить звук")
        btn_test.setIcon(_fa_icon("fa5s.play", c["TEXT"]))
        btn_test.clicked.connect(self._test_sound)
        sound_btns.addWidget(btn_test)

        btn_open_sounds = QPushButton("  Открыть папку sounds")
        btn_open_sounds.setIcon(_fa_icon("fa5s.folder-open", c["TEXT"]))
        btn_open_sounds.clicked.connect(self._open_sounds_folder)
        sound_btns.addWidget(btn_open_sounds)

        btn_regen = QPushButton("  Восстановить стандартные")
        btn_regen.setIcon(_fa_icon("fa5s.undo", c["TEXT"]))
        btn_regen.clicked.connect(self._regenerate_sounds)
        sound_btns.addWidget(btn_regen)
        sound_btns.addStretch()
        lay.addLayout(sound_btns)

        # ---- Голосовые фразы ----
        h5 = QLabel("Голосовые фразы")
        h5.setProperty("sectionHeader", True)
        lay.addWidget(h5)

        voice_hint = QLabel("Фразы лежат в sounds/voice/ как .wav.")
        voice_hint.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 11px;")
        voice_hint.setWordWrap(True)
        lay.addWidget(voice_hint)

        self.chk_voice = QCheckBox("Включить голосовые фразы")
        self.chk_voice.setChecked(self.settings.get("voice_enabled", False))
        lay.addWidget(self.chk_voice)

        voice_vol_row = QHBoxLayout()
        voice_vol_lbl = QLabel("Громкость голоса:")
        voice_vol_lbl.setProperty("formLabel", True)
        voice_vol_row.addWidget(voice_vol_lbl)

        self.slider_voice_volume = QSlider(Qt.Horizontal)
        self.slider_voice_volume.setRange(0, 100)
        self.slider_voice_volume.setValue(int(self.settings.get("voice_volume", 80)))
        self.slider_voice_volume.setMinimumWidth(220)
        self.slider_voice_volume.valueChanged.connect(self._on_voice_volume_changed)
        voice_vol_row.addWidget(self.slider_voice_volume)

        self.lbl_voice_volume = QLabel(f"{self.slider_voice_volume.value()} %")
        self.lbl_voice_volume.setStyleSheet(
            f"color: {c['SUBTEXT']}; font-size: 12px; background: transparent;"
        )
        self.lbl_voice_volume.setMinimumWidth(46)
        voice_vol_row.addWidget(self.lbl_voice_volume)
        voice_vol_row.addStretch()
        lay.addLayout(voice_vol_row)

        voice_events_hint = QLabel("Отметь, какие события озвучивать:")
        voice_events_hint.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 11px;")
        lay.addWidget(voice_events_hint)

        self.voice_event_boxes = {}
        voice_events_grid = QGridLayout()
        voice_events_grid.setSpacing(8)

        for i, (key, label) in enumerate(VOICE_EVENT_LABELS):
            box = QCheckBox(label)
            box.setChecked(bool(
                (self.settings.get("voice_events") or {}).get(key, True)
            ))
            voice_events_grid.addWidget(box, i, 0)
            self.voice_event_boxes[key] = box
        lay.addLayout(voice_events_grid)

        voice_btns = QHBoxLayout()
        voice_btns.setSpacing(8)

        btn_test_voice = QPushButton("  Проверить голос")
        btn_test_voice.setIcon(_fa_icon("fa5s.play", c["TEXT"]))
        btn_test_voice.clicked.connect(self._test_voice)
        voice_btns.addWidget(btn_test_voice)

        btn_open_voice = QPushButton("  Открыть папку voice")
        btn_open_voice.setIcon(_fa_icon("fa5s.folder-open", c["TEXT"]))
        btn_open_voice.clicked.connect(self._open_voice_folder)
        voice_btns.addWidget(btn_open_voice)

        voice_btns.addStretch()
        lay.addLayout(voice_btns)

        lay.addStretch()
        self.tabs.addTab(outer_tab, "  Поведение")

    # ==================== ВКЛАДКА: КАТЕГОРИИ ====================
    def _build_categories_tab(self):
        c = self.colors
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        hint = QLabel(
            "Для каждой категории можно задать:\n"
            "• Спутники — программы, которые стартуют вместе с любой программой категории\n"
            "• Папку авто-обложек — картинки подставляются программам без своей обложки\n"
            "• Подкатегории — группы внутри категории"
        )
        hint.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 12px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self._cat_rows = {}

        for cat_key in ("games", "work", "system", "other"):
            cat_name, cat_emoji = CATEGORIES.get(cat_key, (cat_key, ""))
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background-color: {c['BG_ALT']};
                    border: 1px solid {c['BORDER']};
                    border-radius: 12px;
                }}
            """)
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(16, 12, 16, 12)
            row_lay.setSpacing(12)

            lbl = QLabel(f"{cat_emoji}  {cat_name}")
            lbl.setStyleSheet(
                f"color: {c['TEXT']}; font-size: 15px; "
                f"font-weight: bold; background: transparent;"
            )
            row_lay.addWidget(lbl)

            status = QLabel("")
            status.setStyleSheet(
                f"color: {c['SUBTEXT']}; font-size: 12px; "
                f"background: transparent;"
            )
            row_lay.addWidget(status)

            row_lay.addStretch()

            edit_btn = QPushButton("  Настроить")
            edit_btn.setIcon(_fa_icon("fa5s.pen", c["TEXT"]))
            edit_btn.clicked.connect(
                lambda _=False, k=cat_key: self._edit_category(k)
            )
            row_lay.addWidget(edit_btn)

            lay.addWidget(row)
            self._cat_rows[cat_key] = status

        self._refresh_category_statuses()

        lay.addStretch()
        self.tabs.addTab(tab, "  Категории")

    def _refresh_category_statuses(self):
        cc = self.settings.get("category_companions") or {}
        cv = self.settings.get("category_covers") or {}
        sc = self.settings.get("subcategories") or {}
        for cat_key, status_lbl in self._cat_rows.items():
            n_comp = len(cc.get(cat_key, []) or [])
            has_cover = "🎨" if cv.get(cat_key, "") else ""
            n_sub = len(sc.get(cat_key, []) or [])

            parts = []
            if n_comp:
                parts.append(f"🔗{n_comp}")
            if has_cover:
                parts.append(has_cover)
            if n_sub:
                parts.append(f"🏷{n_sub}")

            if parts:
                status_lbl.setText("   ".join(parts))
            else:
                status_lbl.setText("нет настроек")

    def _edit_category(self, cat_key):
        try:
            dlg = CategoryEditorDialog(
                self, self.colors, cat_key, self.settings, self.apps_list
            )
        except Exception as e:
            show_error(self, self.colors, "Ошибка", str(e))
            return
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._refresh_category_statuses()

    # ==================== ВКЛАДКА 3: ПРОФИЛИ ====================
    def _build_profiles_tab(self):
        c = self.colors
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        hint = QLabel(
            "Профиль — это готовый набор настроек под конкретную задачу."
        )
        hint.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 12px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.profiles_list = QListWidget()
        self.profiles_list.setIconSize(QSize(28, 28))
        self.profiles_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {c['BG_ALT']};
                color: {c['TEXT']};
                border: 1px solid {c['BORDER']};
                border-radius: 12px;
                padding: 6px;
                font-size: 14px;
                outline: none;
            }}
            QListWidget::item {{ padding: 12px; border-radius: 8px; }}
            QListWidget::item:selected {{
                background-color: {c['ACCENT_SOFT']};
                color: {c['ACCENT']};
            }}
            QListWidget::item:hover {{
                background-color: {c['CARD_HOVER']};
            }}
        """)

        self._refresh_profiles_list()
        lay.addWidget(self.profiles_list, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)

        apply_btn = QPushButton("  Применить")
        apply_btn.setIcon(_fa_icon("fa5s.check", c["BG"]))
        apply_btn.setProperty("accent", True)
        apply_btn.clicked.connect(self._apply_selected_profile)
        btns.addWidget(apply_btn)

        save_btn = QPushButton("  Сохранить текущие настройки в профиль")
        save_btn.setIcon(_fa_icon("fa5s.save", c["TEXT"]))
        save_btn.clicked.connect(self._save_into_profile)
        btns.addWidget(save_btn)

        reset_btn = QPushButton("  Сбросить")
        reset_btn.setIcon(_fa_icon("fa5s.undo", c["DANGER"]))
        reset_btn.clicked.connect(self._reset_selected_profile)
        btns.addWidget(reset_btn)

        btns.addStretch()
        lay.addLayout(btns)

        self.tabs.addTab(tab, "  Профили")

    def _refresh_profiles_list(self):
        self.profiles_list.clear()
        profiles = all_profiles()
        active = self.settings.get("active_profile", "custom")

        for key, prof in profiles.items():
            name = prof.get("name", key)
            icon_name = prof.get("icon", "fa5s.folder")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, key)

            if key == active:
                item.setText(f"✓  {name}")
            else:
                item.setText(f"    {name}")

            icon = _fa_icon(
                icon_name,
                self.colors["ACCENT"] if key == active else self.colors["TEXT"]
            )
            if icon_map.HAS_QTAWESOME:
                item.setIcon(icon)

            self.profiles_list.addItem(item)

            if key == active:
                self.profiles_list.setCurrentItem(item)

    def _apply_selected_profile(self):
        item = self.profiles_list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        self.settings["active_profile"] = key

        applied = apply_profile(key, self.settings)
        self._sync_ui_from_settings(applied)
        for k in ("category_companions", "category_covers",
                  "subcategories", "sound_events", "voice_events"):
            applied[k] = self.settings.get(k) or {}
        self.settings = applied
        self._refresh_profiles_list()

        show_info(
            self, self.colors, "Профиль применён",
            f"Активирован профиль «{all_profiles()[key].get('name')}»."
        )

    def _save_into_profile(self):
        item = self.profiles_list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)

        collected = self._collect_ui_settings()

        from profiles import diff_from_default, save_custom_profiles, load_custom_profiles
        from config import BUILTIN_PROFILES
        from copy import deepcopy

        custom = load_custom_profiles()
        if key not in custom:
            custom[key] = deepcopy(BUILTIN_PROFILES.get(key, {}))
        custom[key].setdefault("settings", {})

        overridable = set(BUILTIN_PROFILES.get("gaming", {}).get("settings", {}).keys())
        overridable |= {
            "theme", "accent",
            "show_clock", "show_search", "show_running_section",
            "show_covers", "show_glow", "show_status_text",
            "show_section_headers", "show_tile_badges", "hide_scrollbar",
            "tile_scale", "icon_scale", "animation_speed",
            "current_category",
        }

        diffs = diff_from_default(collected)
        custom[key]["settings"] = {
            k: v for k, v in diffs.items() if k in overridable
        }
        save_custom_profiles(custom)

        show_info(
            self, self.colors, "Профиль обновлён",
            f"Текущие настройки сохранены в профиль «{custom[key].get('name', key)}»."
        )
        self._refresh_profiles_list()

    def _reset_selected_profile(self):
        item = self.profiles_list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if not QMessageBox.question(
            self, "Сбросить профиль",
            f"Вернуть профиль к заводским настройкам?"
        ) == QMessageBox.Yes:
            return
        reset_profile(key)
        self._refresh_profiles_list()

    def _sync_ui_from_settings(self, s):
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == s.get("theme", "dark"):
                self.theme_combo.setCurrentIndex(i)
                break
        self.selected_accent = s.get("accent", "blue")
        self._refresh_accent_buttons()
        self.tile_scale.setValue(int(s.get("tile_scale", 100)))
        self.icon_scale.setValue(int(s.get("icon_scale", 100)))
        self.anim_speed.setValue(int(s.get("animation_speed", 100)))
        self.chk_material_icons.setChecked(s.get("use_material_icons", True))
        self.chk_monitor.setChecked(s.get("show_system_monitor", True))
        cur_int = int(s.get("system_monitor_interval", 2))
        idx = self.combo_monitor_interval.findData(cur_int)
        if idx >= 0:
            self.combo_monitor_interval.setCurrentIndex(idx)
        self.chk_splash.setChecked(s.get("splash_enabled", True))
        self.chk_bg_anim.setChecked(s.get("bg_animation_enabled", True))
        self.spin_particles.setValue(
            int(s.get("bg_animation_particles", 28))
        )
        self.chk_clock.setChecked(s.get("show_clock", True))
        self.chk_search.setChecked(s.get("show_search", True))
        self.chk_running.setChecked(s.get("show_running_section", True))
        self.chk_covers.setChecked(s.get("show_covers", True))
        self.chk_glow.setChecked(s.get("show_glow", True))
        self.chk_status.setChecked(s.get("show_status_text", True))
        self.chk_headers.setChecked(s.get("show_section_headers", True))
        self.chk_badges.setChecked(s.get("show_tile_badges", True))
        self.chk_scrollbar.setChecked(s.get("hide_scrollbar", False))
        for i in range(self.start_view_combo.count()):
            if self.start_view_combo.itemData(i) == s.get("start_view", "normal"):
                self.start_view_combo.setCurrentIndex(i)
                break
        self.chk_ontop.setChecked(s.get("always_on_top", True))
        self.chk_tray.setChecked(s.get("close_to_tray", True))
        self.chk_silent.setChecked(s.get("silent_start", False))
        self.chk_confirm_kill.setChecked(s.get("confirm_kill", True))
        self.chk_overlay.setChecked(s.get("overlay_enabled", True))
        self.chk_companions.setChecked(s.get("companions_enabled", True))
        self.chk_switch_on_running.setChecked(
            s.get("switch_to_window_on_running", False)
        )
        self.chk_activate_after_launch.setChecked(
            s.get("activate_after_launch", False)
        )
        self.chk_sounds.setChecked(s.get("sound_enabled", True))
        self.slider_volume.setValue(int(s.get("sound_volume", 60)))
        events = s.get("sound_events") or {}
        for key, box in self.sound_event_boxes.items():
            box.setChecked(bool(events.get(key, True)))
        self.chk_voice.setChecked(s.get("voice_enabled", False))
        self.slider_voice_volume.setValue(int(s.get("voice_volume", 80)))
        v_events = s.get("voice_events") or {}
        for key, box in self.voice_event_boxes.items():
            box.setChecked(bool(v_events.get(key, True)))

    # ==================== ВКЛАДКА 4: ДАННЫЕ ====================
    def _build_data_tab(self):
        c = self.colors
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        h = QLabel("Список программ")
        h.setProperty("sectionHeader", True)
        lay.addWidget(h)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        btn_export = QPushButton("  Экспорт списка")
        btn_export.setIcon(_fa_icon("fa5s.file-export", c["TEXT"]))
        btn_export.clicked.connect(self._export_apps)
        row1.addWidget(btn_export)
        btn_import = QPushButton("  Импорт списка")
        btn_import.setIcon(_fa_icon("fa5s.file-import", c["TEXT"]))
        btn_import.clicked.connect(self._import_apps)
        row1.addWidget(btn_import)
        row1.addStretch()
        lay.addLayout(row1)

        h2 = QLabel("Облако")
        h2.setProperty("sectionHeader", True)
        lay.addWidget(h2)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        btn_cloud_export = QPushButton("  Экспорт в облако")
        btn_cloud_export.setIcon(_fa_icon("fa5s.cloud-upload-alt", c["TEXT"]))
        btn_cloud_export.clicked.connect(self._cloud_export)
        row2.addWidget(btn_cloud_export)
        btn_cloud_import = QPushButton("  Импорт из облака")
        btn_cloud_import.setIcon(_fa_icon("fa5s.cloud-download-alt", c["TEXT"]))
        btn_cloud_import.clicked.connect(self._cloud_import)
        row2.addWidget(btn_cloud_import)
        row2.addStretch()
        lay.addLayout(row2)

        h3 = QLabel("Локальные данные")
        h3.setProperty("sectionHeader", True)
        lay.addWidget(h3)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        btn_open_data = QPushButton("  Папка данных")
        btn_open_data.setIcon(_fa_icon("fa5s.folder-open", c["TEXT"]))
        btn_open_data.clicked.connect(self._open_data_folder)
        row3.addWidget(btn_open_data)

        btn_open_backups = QPushButton("  Бэкапы")
        btn_open_backups.setIcon(_fa_icon("fa5s.history", c["TEXT"]))
        btn_open_backups.clicked.connect(self._open_backups)
        row3.addWidget(btn_open_backups)

        btn_clear_icons = QPushButton("  Сбросить кэш иконок")
        btn_clear_icons.setIcon(_fa_icon("fa5s.broom", c["TEXT"]))
        btn_clear_icons.clicked.connect(self._clear_icons)
        row3.addWidget(btn_clear_icons)
        row3.addStretch()
        lay.addLayout(row3)

        h4 = QLabel("Статистика и заметки")
        h4.setProperty("sectionHeader", True)
        lay.addWidget(h4)

        row4 = QHBoxLayout()
        row4.setSpacing(8)
        btn_stats = QPushButton("  Открыть статистику")
        btn_stats.setIcon(_fa_icon("fa5s.chart-bar", c["TEXT"]))
        btn_stats.clicked.connect(self._show_stats)
        row4.addWidget(btn_stats)

        btn_export_notes = QPushButton("  Экспорт заметок")
        btn_export_notes.setIcon(_fa_icon("fa5s.sticky-note", c["TEXT"]))
        btn_export_notes.clicked.connect(self._export_notes)
        row4.addWidget(btn_export_notes)
        row4.addStretch()
        lay.addLayout(row4)

        lay.addStretch()
        self.tabs.addTab(tab, "  Данные")

    # ==================== ВКЛАДКА 5: ПЛАГИНЫ ====================
    def _build_plugins_tab(self):
        c = self.colors
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        hint = QLabel(
            "Плагины расширяют функциональность. Файлы .py лежат в папке "
            "plugins/ рядом с лаунчером."
        )
        hint.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 12px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self._plugins_scroll = QScrollArea()
        self._plugins_scroll.setWidgetResizable(True)
        self._plugins_scroll.setFrameShape(QFrame.NoFrame)
        self._plugins_scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
        )

        self._plugins_content = QWidget()
        self._plugins_content_lay = QVBoxLayout(self._plugins_content)
        self._plugins_content_lay.setContentsMargins(0, 0, 0, 0)
        self._plugins_content_lay.setSpacing(10)
        self._plugins_scroll.setWidget(self._plugins_content)
        lay.addWidget(self._plugins_scroll, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)

        btn_open_folder = QPushButton("  Открыть папку plugins")
        btn_open_folder.setIcon(_fa_icon("fa5s.folder-open", c["TEXT"]))
        btn_open_folder.clicked.connect(self._open_plugins_folder)
        btns.addWidget(btn_open_folder)

        btn_reload = QPushButton("  Перезагрузить список")
        btn_reload.setIcon(_fa_icon("fa5s.sync-alt", c["TEXT"]))
        btn_reload.clicked.connect(self._reload_plugins)
        btns.addWidget(btn_reload)

        btns.addStretch()
        lay.addLayout(btns)

        self._refresh_plugins_list()
        self.tabs.addTab(tab, "  Плагины")

    def _get_plugin_manager(self):
        return getattr(self.parent_window, "plugin_manager", None)

    def _refresh_plugins_list(self):
        c = self.colors

        while self._plugins_content_lay.count():
            it = self._plugins_content_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._plugin_checks = {}

        pm = self._get_plugin_manager()
        if pm is None:
            no = QLabel("Менеджер плагинов недоступен.")
            no.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 13px;")
            self._plugins_content_lay.addWidget(no)
            self._plugins_content_lay.addStretch()
            return

        all_plugins = pm.list_all()
        if not all_plugins:
            empty = QLabel("Плагины не найдены.")
            empty.setStyleSheet(
                f"color: {c['SUBTEXT']}; font-size: 13px; padding: 20px;"
            )
            empty.setWordWrap(True)
            self._plugins_content_lay.addWidget(empty)
            self._plugins_content_lay.addStretch()
            return

        for pl in all_plugins:
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background-color: {c['BG_ALT']};
                    border: 1px solid {c['BORDER']};
                    border-radius: 10px;
                }}
            """)
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(14, 12, 14, 12)
            row_lay.setSpacing(12)

            icon_lbl = QLabel()
            icon_lbl.setFixedSize(32, 32)
            icon_lbl.setAlignment(Qt.AlignCenter)
            pix = _fa_icon(pl.get("icon", "fa5s.plug"),
                           c["ACCENT"]).pixmap(24, 24)
            if not pix.isNull():
                icon_lbl.setPixmap(pix)
            row_lay.addWidget(icon_lbl)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)

            title_row = QHBoxLayout()
            title_row.setSpacing(8)
            name_lbl = QLabel(pl["name"])
            name_lbl.setStyleSheet(
                f"color: {c['TEXT']}; font-size: 14px; "
                f"font-weight: bold; background: transparent;"
            )
            title_row.addWidget(name_lbl)

            ver_lbl = QLabel(f"v{pl.get('version', '?')}")
            ver_lbl.setStyleSheet(
                f"color: {c['SUBTEXT']}; font-size: 11px; "
                f"background: transparent;"
            )
            title_row.addWidget(ver_lbl)
            title_row.addStretch()
            text_col.addLayout(title_row)

            desc = pl.get("description", "") or "Без описания"
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                f"color: {c['SUBTEXT']}; font-size: 12px; "
                f"background: transparent;"
            )
            desc_lbl.setWordWrap(True)
            text_col.addWidget(desc_lbl)

            meta_parts = []
            if pl.get("author"):
                meta_parts.append(f"автор: {pl['author']}")
            meta_parts.append(f"файл: {pl.get('file', '?')}")
            meta = QLabel("  ·  ".join(meta_parts))
            meta.setStyleSheet(
                f"color: {c['SUBTEXT']}; font-size: 10px; "
                f"background: transparent;"
            )
            text_col.addWidget(meta)

            row_lay.addLayout(text_col, 1)

            chk = QCheckBox("Включить")
            chk.setChecked(bool(pl.get("enabled")))
            self._plugin_checks[pl["name"]] = chk
            row_lay.addWidget(chk)

            self._plugins_content_lay.addWidget(row)

        self._plugins_content_lay.addStretch()

    def _reload_plugins(self):
        pm = self._get_plugin_manager()
        if pm is None:
            return
        try:
            pm.reload()
        except Exception as e:
            log.error(f"reload plugins: {e}")
        self._refresh_plugins_list()

    def _open_plugins_folder(self):
        try:
            import plugin_manager as pm_mod
            os.makedirs(pm_mod.PLUGINS_DIR, exist_ok=True)
            os.startfile(pm_mod.PLUGINS_DIR)
        except Exception as e:
            log.error(f"open plugins folder: {e}")

    def _add_plugin_tabs(self):
        pm = self._get_plugin_manager()
        if pm is None:
            return
        for name, pl in list(pm.plugins.items()):
            try:
                tabs = pl.on_settings_tabs(self.colors)
                for title, widget in tabs or []:
                    if widget is not None:
                        self.tabs.addTab(widget, f"  {title}")
            except Exception as e:
                log.error(f"Плагин {name}: on_settings_tabs: {e}")

    # ==================== ВКЛАДКА 6: О ПРОГРАММЕ ====================
    def _build_about_tab(self):
        c = self.colors
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        title = QLabel("Мой лаунчер")
        title.setStyleSheet(
            f"color: {c['ACCENT']}; font-size: 22px; font-weight: bold;"
        )
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        ver = QLabel(f"Версия {APP_VERSION}")
        ver.setStyleSheet(f"color: {c['SUBTEXT']}; font-size: 13px;")
        ver.setAlignment(Qt.AlignCenter)
        lay.addWidget(ver)

        lay.addSpacing(20)

        modules_label = QLabel("Установленные модули")
        modules_label.setProperty("sectionHeader", True)
        modules_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(modules_label)

        try:
            mon_info = sysmonitor.is_supported()
        except Exception:
            mon_info = {"psutil": False, "gpu": False}

        mods = [
            ("qtawesome", HAS_QTAWESOME, "Векторные иконки"),
            ("keyboard", self._check_import("keyboard"), "Глобальные hotkey"),
            ("psutil", mon_info.get("psutil", False), "Мониторинг CPU/RAM"),
            ("nvidia-ml-py", mon_info.get("gpu", False), "Мониторинг GPU"),
            ("pyqttoast", self._check_import("pyqttoast"), "Всплывающие уведомления"),
            ("QtMultimedia", sounds.HAS_SOUND, "Звуки интерфейса"),
            ("matplotlib", stats_charts.has_matplotlib(), "Графики статистики"),
            ("pywin32", window_activation.HAS_PYWIN32, "Активация окон"),
        ]
        for name, ok, desc in mods:
            row = QLabel()
            row.setAlignment(Qt.AlignCenter)
            mark = "✅" if ok else "❌"
            color = c["OK"] if ok else c["DANGER"]
            row.setText(f"{mark}  {name}  —  {desc}")
            row.setStyleSheet(f"color: {color}; font-size: 13px;")
            lay.addWidget(row)

        lay.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_update = QPushButton("  Проверить обновления")
        btn_update.setIcon(_fa_icon("fa5s.sync-alt", c["TEXT"]))
        btn_update.clicked.connect(self._check_updates)
        btn_row.addWidget(btn_update)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addSpacing(20)

        icon_header = QLabel("Иконка лаунчера в трее")
        icon_header.setProperty("sectionHeader", True)
        icon_header.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_header)

        preview_row = QHBoxLayout()
        preview_row.addStretch()
        self.tray_icon_preview = QLabel()
        self.tray_icon_preview.setFixedSize(48, 48)
        self.tray_icon_preview.setStyleSheet(
            f"background-color: {c['CARD']}; "
            f"border: 1px solid {c['BORDER']}; border-radius: 10px;"
        )
        self.tray_icon_preview.setAlignment(Qt.AlignCenter)
        self._refresh_tray_icon_preview()
        preview_row.addWidget(self.tray_icon_preview)
        preview_row.addStretch()
        lay.addLayout(preview_row)

        tray_btns = QHBoxLayout()
        tray_btns.addStretch()
        btn_pick_icon = QPushButton("  Выбрать PNG / ICO")
        btn_pick_icon.setIcon(_fa_icon("fa5s.image", c["TEXT"]))
        btn_pick_icon.clicked.connect(self._pick_tray_icon)
        tray_btns.addWidget(btn_pick_icon)
        btn_reset_icon = QPushButton("  Сбросить")
        btn_reset_icon.setIcon(_fa_icon("fa5s.undo", c["DANGER"]))
        btn_reset_icon.clicked.connect(self._reset_tray_icon)
        tray_btns.addWidget(btn_reset_icon)
        tray_btns.addStretch()
        lay.addLayout(tray_btns)

        lay.addStretch()
        self.tabs.addTab(tab, "  О программе")

    def _check_import(self, name):
        try:
            __import__(name)
            return True
        except Exception:
            return False

    # ==================== ЗВУКИ ====================
    def _on_volume_changed(self, val):
        self.lbl_volume.setText(f"{val} %")

    def _on_voice_volume_changed(self, val):
        self.lbl_voice_volume.setText(f"{val} %")

    def _test_sound(self):
        try:
            sounds.set_volume(self.slider_volume.value())
            sounds.set_event_flags({
                key: box.isChecked()
                for key, box in self.sound_event_boxes.items()
            })
            was_enabled = sounds.is_enabled()
            if not was_enabled:
                sounds.set_enabled(True)
            sounds.play("success")
            if not was_enabled:
                sounds.set_enabled(False)
        except Exception as e:
            log.error(f"_test_sound: {e}")

    def _test_voice(self):
        try:
            sounds.set_voice_volume(self.slider_voice_volume.value())
            sounds.set_voice_flags({
                key: box.isChecked()
                for key, box in self.voice_event_boxes.items()
            })
            was_enabled = sounds.is_voice_enabled()
            if not was_enabled:
                sounds.set_voice_enabled(True)
            played = False
            for event in ("startup", "launch", "success", "info"):
                if sounds.has_voice(event):
                    sounds.play_voice(event)
                    played = True
                    break
            if not played:
                show_info(
                    self, self.colors, "Голосовые фразы",
                    "Файлы .wav не найдены в sounds/voice/."
                )
            if not was_enabled:
                sounds.set_voice_enabled(False)
        except Exception as e:
            log.error(f"_test_voice: {e}")

    def _open_sounds_folder(self):
        try:
            import sounds as sounds_mod
            sounds_mod.ensure_sounds_folder()
            os.startfile(sounds_mod.sounds_dir())
        except Exception as e:
            log.error(f"open sounds folder: {e}")

    def _open_voice_folder(self):
        try:
            sounds.ensure_voice_dir()
            os.startfile(sounds.voice_dir())
        except Exception as e:
            log.error(f"open voice folder: {e}")

    def _regenerate_sounds(self):
        if not QMessageBox.question(
            self, "Восстановить звуки",
            "Удалить все .wav из папки sounds/ и создать стандартные заново?"
        ) == QMessageBox.Yes:
            return
        try:
            import importlib
            import sounds as sounds_mod
            importlib.reload(sounds_mod)
            d = sounds_mod.sounds_dir()
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.lower().endswith(".wav"):
                        try:
                            os.remove(os.path.join(d, f))
                        except Exception:
                            pass
            sounds_mod.ensure_sounds_folder()
            sounds_mod.init(
                enabled=self.chk_sounds.isChecked(),
                volume=self.slider_volume.value(),
                event_flags={
                    key: box.isChecked()
                    for key, box in self.sound_event_boxes.items()
                },
            )
            show_info(self, self.colors, "Готово",
                      "Стандартные звуки восстановлены.")
        except Exception as e:
            show_error(self, self.colors, "Ошибка", str(e))

    # ==================== ИКОНКА ТРЕЯ ====================
    def _refresh_tray_icon_preview(self):
        path = self.settings.get("tray_icon", "")
        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                pix = pix.scaled(
                    40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.tray_icon_preview.setPixmap(pix)
                return
        self.tray_icon_preview.setText("Л")
        self.tray_icon_preview.setStyleSheet(
            f"background-color: {self.colors['ACCENT']}; "
            f"color: {self.colors['BG']}; "
            f"font-size: 22px; font-weight: bold; "
            f"border-radius: 10px;"
        )

    def _pick_tray_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите иконку для трея", "",
            "Изображения (*.png *.ico *.jpg *.jpeg *.bmp *.svg);;Все файлы (*.*)"
        )
        if not path:
            return
        self.settings["tray_icon"] = path
        self.tray_icon_preview.setStyleSheet(
            f"background-color: {self.colors['CARD']}; "
            f"border: 1px solid {self.colors['BORDER']}; "
            f"border-radius: 10px;"
        )
        self.tray_icon_preview.setText("")
        self._refresh_tray_icon_preview()

    def _reset_tray_icon(self):
        self.settings["tray_icon"] = ""
        self.tray_icon_preview.setPixmap(QPixmap())
        self._refresh_tray_icon_preview()

    # ==================== УТИЛИТЫ ====================
    def _select_accent(self, key):
        self.selected_accent = key
        self._refresh_accent_buttons()

    def _pick_custom_accent(self):
        if is_hex(self.selected_accent):
            initial = QColor(normalize_hex(self.selected_accent))
        elif self.selected_accent in ACCENTS:
            initial = QColor(ACCENTS[self.selected_accent][0])
        else:
            initial = QColor(self.colors.get("ACCENT", "#89B4FA"))

        dlg = QColorDialog(initial, self)
        dlg.setWindowTitle("Выберите акцентный цвет")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        color = dlg.currentColor()
        if not color.isValid():
            return
        hex_str = color.name().upper()
        self.selected_accent = hex_str
        self._refresh_accent_buttons()

    def _refresh_accent_buttons(self):
        current = self.selected_accent
        is_custom = is_hex(current)

        for key, btn in self.accent_btns.items():
            main, _hover = ACCENTS[key]
            selected = (not is_custom) and (key == current)
            border_color = self.colors["TEXT"] if selected else main
            bw = 3 if selected else 0
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {main};
                    border: {bw}px solid {border_color};
                    border-radius: 19px;
                }}
                QPushButton:hover {{
                    border: {max(bw, 2)}px solid {self.colors['TEXT']};
                }}
            """)

        if self.custom_swatch_btn is not None:
            if is_custom:
                base = normalize_hex(current)
                bw = 3
                border_color = self.colors["TEXT"]
                bg = base
                self.custom_swatch_btn.setText("")
                self.custom_swatch_btn.setIcon(QIcon())
            else:
                bg = self.colors["CARD"]
                bw = 1
                border_color = self.colors["BORDER_HOV"]
                if icon_map.HAS_QTAWESOME:
                    pix = _fa_icon("fa5s.palette",
                                   self.colors["TEXT"]).pixmap(20, 20)
                    if not pix.isNull():
                        self.custom_swatch_btn.setText("")
                        self.custom_swatch_btn.setIcon(QIcon(pix))
                        self.custom_swatch_btn.setIconSize(QSize(20, 20))
                    else:
                        self.custom_swatch_btn.setIcon(QIcon())
                        self.custom_swatch_btn.setText("🎨")
                else:
                    self.custom_swatch_btn.setIcon(QIcon())
                    self.custom_swatch_btn.setText("🎨")

            self.custom_swatch_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {self.colors['TEXT']};
                    border: {bw}px solid {border_color};
                    border-radius: 19px;
                    font-size: 16px;
                }}
                QPushButton:hover {{
                    border: {max(bw, 2)}px solid {self.colors['ACCENT']};
                }}
            """)

        if self.accent_hex_label is not None:
            if is_custom:
                self.accent_hex_label.setText(f"Свой: {normalize_hex(current)}")
            else:
                label = ACCENT_LABELS.get(current, current)
                self.accent_hex_label.setText(f"Пресет: {label}")

    def _open_data_folder(self):
        try:
            os.startfile(BASE_DIR)
        except Exception as e:
            log.error(f"open data folder: {e}")

    def _open_backups(self):
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            os.startfile(BACKUP_DIR)
        except Exception as e:
            log.error(f"open backups: {e}")

    def _clear_icons(self):
        clear_cache()
        icon_map.clear_cache()
        log.info("Кэш иконок очищен")
        show_info(self, self.colors, "Готово", "Кэш иконок очищен")

    def _export_apps(self):
        if not self.apps_provider:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить список", "my_launcher_apps.json",
            "JSON (*.json);;Все файлы (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.apps_provider(), f, ensure_ascii=False, indent=2)
            show_info(self, self.colors, "Экспорт", f"Сохранено:\n{path}")
        except Exception as e:
            show_error(self, self.colors, "Ошибка экспорта", str(e))

    def _import_apps(self):
        if not self.apps_provider:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить список", "",
            "JSON (*.json);;Все файлы (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("Файл не содержит список программ")
            for i, a in enumerate(data):
                if not isinstance(a, dict) or "path" not in a:
                    continue
                a.setdefault("name",
                             os.path.splitext(os.path.basename(a["path"]))[0])
                a.setdefault("favorite", False)
                a.setdefault("launch_count", 0)
                a.setdefault("category", "other")
                a.setdefault("subcategory", "")
                a.setdefault("custom_icon", "")
                a.setdefault("custom_cover", "")
                a.setdefault("order", i)
                a.setdefault("hotkey", "")
                a.setdefault("companions", [])
                a.setdefault("note", "")
                a.setdefault("known_version", "")
            self._pending_import = data
            show_info(
                self, self.colors, "Импорт",
                f"Загружено программ: {len(data)}\n"
                "Нажми «Сохранить», чтобы применить."
            )
        except Exception as e:
            show_error(self, self.colors, "Ошибка импорта", str(e))

    def _cloud_export(self):
        default_dir = self.settings.get("cloud_folder", "") or os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить в облако",
            os.path.join(default_dir, "my_launcher_backup.json"),
            "JSON (*.json);;Все файлы (*.*)"
        )
        if not path:
            return
        try:
            from config import PRESETS_PATH
            bundle = {
                "apps": self.apps_provider() if self.apps_provider else [],
                "settings": dict(self.settings),
            }
            try:
                with open(PRESETS_PATH, "r", encoding="utf-8") as f:
                    bundle["presets"] = json.load(f)
            except Exception:
                bundle["presets"] = []
            with open(path, "w", encoding="utf-8") as f:
                json.dump(bundle, f, ensure_ascii=False, indent=2)
            self.settings["cloud_folder"] = os.path.dirname(path)
            show_info(self, self.colors, "Облако", f"Сохранено в облако:\n{path}")
        except Exception as e:
            show_error(self, self.colors, "Ошибка облака", str(e))

    def _cloud_import(self):
        default_dir = self.settings.get("cloud_folder", "") or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить из облака", default_dir,
            "JSON (*.json);;Все файлы (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                bundle = json.load(f)
            if isinstance(bundle, list):
                apps = bundle
                presets = None
            elif isinstance(bundle, dict):
                apps = bundle.get("apps", [])
                presets = bundle.get("presets", None)
            else:
                raise ValueError("Неизвестный формат файла")
            for i, a in enumerate(apps):
                if not isinstance(a, dict) or "path" not in a:
                    continue
                a.setdefault("name",
                             os.path.splitext(os.path.basename(a["path"]))[0])
                a.setdefault("favorite", False)
                a.setdefault("launch_count", 0)
                a.setdefault("category", "other")
                a.setdefault("subcategory", "")
                a.setdefault("custom_icon", "")
                a.setdefault("custom_cover", "")
                a.setdefault("order", i)
                a.setdefault("hotkey", "")
                a.setdefault("companions", [])
                a.setdefault("note", "")
                a.setdefault("known_version", "")
            self._pending_import = apps
            self._pending_presets_import = presets
            self.settings["cloud_folder"] = os.path.dirname(path)
            extra = ""
            if presets is not None:
                extra = f"\nПресетов: {len(presets)}"
            show_info(self, self.colors, "Облако",
                      f"Загружено программ: {len(apps)}{extra}\n"
                      "Нажми «Сохранить», чтобы применить.")
        except Exception as e:
            show_error(self, self.colors, "Ошибка облака", str(e))

    # ==================== ЭКСПОРТ ЗАМЕТОК ====================
    def _export_notes(self):
        apps = self.apps_list or []
        with_notes = [a for a in apps if (a.get("note") or "").strip()]
        if not with_notes:
            show_info(self, self.colors, "Экспорт заметок",
                      "Ни у одной программы нет заметок.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить заметки",
            os.path.join(BASE_DIR, "notes.md"),
            "Markdown (*.md);;Текст (*.txt);;Все файлы (*.*)"
        )
        if not path:
            return

        try:
            lines = [
                "# Заметки MyLauncher",
                "",
                f"_Экспортировано: {datetime.now():%Y-%m-%d %H:%M}_",
                "",
            ]
            for a in with_notes:
                name = a.get("name", "Без имени")
                note = (a.get("note") or "").strip()
                prog_path = a.get("path", "")
                lines.append(f"## {name}")
                lines.append("")
                lines.append(note)
                lines.append("")
                lines.append(f"`{prog_path}`")
                lines.append("")

            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            show_info(self, self.colors, "Готово",
                      f"Заметок экспортировано: {len(with_notes)}\n\n{path}")
            log.info(f"Заметки экспортированы: {path}")
        except Exception as e:
            show_error(self, self.colors, "Ошибка экспорта", str(e))

    # ==================== СТАТИСТИКА ====================
    def _show_stats(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Статистика использования")
        dlg.setStyleSheet(dialog_qss(self.colors))
        dlg.setMinimumWidth(680)
        dlg.resize(800, 700)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title_icon = QLabel()
        title_icon.setFixedSize(24, 24)
        pix = _fa_icon("fa5s.chart-bar", self.colors["ACCENT"]).pixmap(22, 22)
        if not pix.isNull():
            title_icon.setPixmap(pix)

        title_row = QHBoxLayout()
        title_row.addWidget(title_icon)
        title_lbl = QLabel("Статистика использования")
        title_lbl.setStyleSheet(
            f"color: {self.colors['ACCENT']}; font-size: 18px; font-weight: bold;"
        )
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        period_combo = QComboBox()
        period_combo.addItem("Сегодня", 1)
        period_combo.addItem("7 дней", 7)
        period_combo.addItem("30 дней", 30)
        period_combo.addItem("За всё время", None)
        period_combo.setCurrentIndex(3)

        period_lbl = QLabel("Период:")
        period_lbl.setStyleSheet(f"color: {self.colors['TEXT']}; font-size: 13px;")
        title_row.addWidget(period_lbl)
        title_row.addWidget(period_combo)
        layout.addLayout(title_row)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {self.colors['BORDER']};
                border-radius: 12px;
            }}
            QTabBar::tab {{
                background-color: {self.colors['BG_ALT']};
                color: {self.colors['SUBTEXT']};
                padding: 8px 16px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background-color: {self.colors['ACCENT']};
                color: {self.colors['BG']};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {self.colors['CARD_HOVER']};
                color: {self.colors['TEXT']};
            }}
        """)

        tab1 = QWidget()
        t1 = QVBoxLayout(tab1)
        t1.setContentsMargins(16, 16, 16, 16)
        t1.setSpacing(10)

        total_label = QLabel("")
        total_label.setStyleSheet(
            f"color: {self.colors['SUBTEXT']}; font-size: 12px;"
        )
        t1.addWidget(total_label)

        lw = QListWidget()
        lw.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.colors['BG_ALT']};
                color: {self.colors['TEXT']};
                border: 1px solid {self.colors['BORDER']};
                border-radius: 12px;
                padding: 6px;
                font-size: 14px;
                outline: none;
            }}
            QListWidget::item {{ padding: 10px; border-radius: 8px; }}
            QListWidget::item:hover {{ background-color: {self.colors['CARD_HOVER']}; }}
        """)
        t1.addWidget(lw, 1)
        tabs.addTab(tab1, "  Топ программ")

        tab2 = QWidget()
        t2 = QVBoxLayout(tab2)
        t2.setContentsMargins(16, 16, 16, 16)
        t2.setSpacing(10)

        info = QLabel("Сколько времени в сумме ты проводишь в каждой категории.")
        info.setStyleSheet(f"color: {self.colors['SUBTEXT']}; font-size: 12px;")
        t2.addWidget(info)

        cat_lw = QListWidget()
        cat_lw.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.colors['BG_ALT']};
                color: {self.colors['TEXT']};
                border: 1px solid {self.colors['BORDER']};
                border-radius: 12px;
                padding: 8px;
                font-size: 14px;
                outline: none;
            }}
            QListWidget::item {{ padding: 12px; border-radius: 8px; }}
        """)
        t2.addWidget(cat_lw, 1)
        tabs.addTab(tab2, "  По категориям")

        tab3 = QWidget()
        t3 = QVBoxLayout(tab3)
        t3.setContentsMargins(0, 0, 0, 0)
        t3.setSpacing(0)

        charts_holder = QWidget()
        charts_holder_lay = QVBoxLayout(charts_holder)
        charts_holder_lay.setContentsMargins(0, 0, 0, 0)
        t3.addWidget(charts_holder)

        tabs.addTab(tab3, "  Графики")

        layout.addWidget(tabs, 1)

        cat_icons = {
            "games":  ("🎮", "Игры"),
            "work":   ("💼", "Работа"),
            "system": ("⚙", "Система"),
            "other":  ("📦", "Прочее"),
            "all":    ("🗂", "Все"),
        }

        def rebuild_charts_widget():
            while charts_holder_lay.count():
                it = charts_holder_lay.takeAt(0)
                w = it.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()

            days = period_combo.currentData()
            stats = load_stats()
            widget = stats_charts.create_charts_widget(
                self.colors, stats, self.apps_list, days=days,
            )
            charts_holder_lay.addWidget(widget)

        def refresh():
            days = period_combo.currentData()
            stats = load_stats()
            top = get_top(stats, self.apps_list, limit=20, days=days)
            by_cat = by_category(stats, self.apps_list, days=days)
            total_all = sum(s for _, s in top)

            lw.clear()
            if not top:
                it = QListWidgetItem("За выбранный период данных нет.")
                it.setFlags(Qt.ItemFlag.NoItemFlags)
                lw.addItem(it)
            else:
                medals = ["🥇", "🥈", "🥉"]
                for i, (name, secs) in enumerate(top):
                    prefix = medals[i] if i < 3 else f"  {i+1}."
                    lw.addItem(QListWidgetItem(
                        f"{prefix}  {name}    —   {format_duration(secs)}"
                    ))
            total_label.setText(f"Всего за период: {format_duration(total_all)}")

            cat_lw.clear()
            if not by_cat:
                it = QListWidgetItem("За выбранный период данных нет.")
                it.setFlags(Qt.ItemFlag.NoItemFlags)
                cat_lw.addItem(it)
            else:
                sorted_cats = sorted(
                    by_cat.items(), key=lambda kv: kv[1]["seconds"], reverse=True
                )
                for cat_key, data in sorted_cats:
                    emoji, name = cat_icons.get(cat_key, ("📁", cat_key))
                    secs = data["seconds"]
                    apps_count = len(data["apps"])
                    percent = (secs / total_all * 100) if total_all else 0
                    cat_lw.addItem(QListWidgetItem(
                        f"{emoji}  {name}    —    {format_duration(secs)}    "
                        f"({percent:.1f}%   ·   {apps_count} программ)"
                    ))

            if stats_charts.has_matplotlib():
                rebuild_charts_widget()

        def on_period_changed(_idx):
            refresh()

        period_combo.currentIndexChanged.connect(on_period_changed)

        def on_tab_changed(idx):
            if idx == 2 and stats_charts.has_matplotlib():
                if charts_holder_lay.count() == 0:
                    rebuild_charts_widget()

        tabs.currentChanged.connect(on_tab_changed)

        bottom = QHBoxLayout()

        reset_btn = QPushButton("🗑 Сбросить статистику")
        reset_btn.clicked.connect(lambda: self._reset_stats(lw, total_label))
        bottom.addWidget(reset_btn)

        export_btn = QPushButton("  Экспорт заметок")
        export_btn.setIcon(_fa_icon("fa5s.sticky-note", self.colors["TEXT"]))
        export_btn.clicked.connect(self._export_notes)
        bottom.addWidget(export_btn)

        bottom.addStretch()
        close = QPushButton("Закрыть")
        close.setProperty("accent", True)
        close.clicked.connect(dlg.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        refresh()
        dlg.exec()

    def _reset_stats(self, lw, total_label):
        if not QMessageBox.question(
            self, "Сбросить", "Удалить всю статистику использования?"
        ) == QMessageBox.Yes:
            return
        if reset_stats():
            lw.clear()
            item = QListWidgetItem("Статистика сброшена.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            lw.addItem(item)
            total_label.setText("Всего за период: 0 сек")

    def _check_updates(self):
        try:
            cur = tuple(int(x) for x in APP_VERSION.split("."))
            latest = tuple(int(x) for x in LATEST_VERSION.split("."))
        except Exception:
            show_info(self, self.colors, "Обновление",
                      f"Текущая версия: {APP_VERSION}")
            return

        if latest > cur:
            msg = (
                f"Доступна новая версия!\n\n"
                f"Текущая: {APP_VERSION}\n"
                f"Новая:   {LATEST_VERSION}\n"
            )
            if GITHUB_REPO_URL:
                msg += f"\n{GITHUB_REPO_URL}"
            box = QMessageBox(self)
            box.setWindowTitle("Обновление")
            box.setText(msg)
            box.setIcon(QMessageBox.Information)
            box.setStyleSheet(dialog_qss(self.colors))
            if GITHUB_REPO_URL:
                open_btn = box.addButton("Открыть страницу",
                                         QMessageBox.AcceptRole)
                box.addButton("Закрыть", QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() == open_btn:
                    webbrowser.open(GITHUB_REPO_URL)
            else:
                box.addButton("OK", QMessageBox.AcceptRole)
                box.exec()
        else:
            show_info(self, self.colors, "Обновление",
                      f"У вас последняя версия: {APP_VERSION}")

    # ==================== СБОР / СОХРАНЕНИЕ ====================
    def _collect_ui_settings(self):
        s = dict(self.settings)
        s["theme"] = self.theme_combo.currentData()
        s["accent"] = self.selected_accent
        s["tile_scale"] = int(self.tile_scale.value())
        s["icon_scale"] = int(self.icon_scale.value())
        s["animation_speed"] = int(self.anim_speed.value())
        s["use_material_icons"] = self.chk_material_icons.isChecked()
        s["show_system_monitor"] = self.chk_monitor.isChecked()
        s["system_monitor_interval"] = int(
            self.combo_monitor_interval.currentData() or 2
        )
        s["splash_enabled"] = self.chk_splash.isChecked()
        s["bg_animation_enabled"] = self.chk_bg_anim.isChecked()
        s["bg_animation_particles"] = int(self.spin_particles.value())
        s["show_clock"] = self.chk_clock.isChecked()
        s["show_search"] = self.chk_search.isChecked()
        s["show_running_section"] = self.chk_running.isChecked()
        s["show_covers"] = self.chk_covers.isChecked()
        s["show_glow"] = self.chk_glow.isChecked()
        s["show_status_text"] = self.chk_status.isChecked()
        s["show_section_headers"] = self.chk_headers.isChecked()
        s["show_tile_badges"] = self.chk_badges.isChecked()
        s["hide_scrollbar"] = self.chk_scrollbar.isChecked()
        s["start_view"] = self.start_view_combo.currentData()
        s["always_on_top"] = self.chk_ontop.isChecked()
        s["close_to_tray"] = self.chk_tray.isChecked()
        s["silent_start"] = self.chk_silent.isChecked()
        s["confirm_kill"] = self.chk_confirm_kill.isChecked()
        s["overlay_enabled"] = self.chk_overlay.isChecked()
        s["companions_enabled"] = self.chk_companions.isChecked()
        s["switch_to_window_on_running"] = self.chk_switch_on_running.isChecked()
        s["activate_after_launch"] = self.chk_activate_after_launch.isChecked()
        s["hotkey"] = self.hotkey_edit.text().strip() or "ctrl+alt+l"
        s["quick_hotkey"] = (
            self.quick_hotkey_edit.text().strip() or "ctrl+alt+space"
        )
        s["category_companions"] = dict(self.settings.get("category_companions") or {})
        s["category_covers"] = dict(self.settings.get("category_covers") or {})
        s["subcategories"] = dict(self.settings.get("subcategories") or {})
        s["tray_icon"] = self.settings.get("tray_icon", "")
        s["sound_enabled"] = self.chk_sounds.isChecked()
        s["sound_volume"] = int(self.slider_volume.value())
        s["sound_events"] = {
            key: box.isChecked()
            for key, box in self.sound_event_boxes.items()
        }
        s["voice_enabled"] = self.chk_voice.isChecked()
        s["voice_volume"] = int(self.slider_voice_volume.value())
        s["voice_events"] = {
            key: box.isChecked()
            for key, box in self.voice_event_boxes.items()
        }
        s["enabled_plugins"] = [
            name for name, cb in self._plugin_checks.items() if cb.isChecked()
        ]
        return s

    def _save(self):
        want = self.chk_autostart.isChecked()
        try:
            has = autostart.is_enabled()
        except Exception:
            has = False
        if want and not has:
            ok, err = autostart.enable()
            if not ok:
                show_error(self, self.colors, "Автозапуск", err)
        elif not want and has:
            autostart.disable()
        self.settings = self._collect_ui_settings()
        self.settings["autostart"] = want
        self.accept()

    def result_settings(self):
        return self.settings

    def pending_import(self):
        return getattr(self, "_pending_import", None)

    def pending_presets(self):
        return getattr(self, "_pending_presets_import", None)