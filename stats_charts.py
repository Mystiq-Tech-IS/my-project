"""Графики статистики через matplotlib. Импорт matplotlib — опциональный."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt

# ---- Опциональный импорт matplotlib ----
try:
    import matplotlib
    matplotlib.use("QtAgg", force=False)
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    HAS_MPL = True
    MPL_ERROR = ""
except Exception as _e:
    HAS_MPL = False
    MPL_ERROR = str(_e)
    FigureCanvasQTAgg = None
    Figure = None


CATEGORY_LABELS = {
    "games":  "Игры",
    "work":   "Работа",
    "system": "Система",
    "other":  "Прочее",
}


def has_matplotlib():
    return HAS_MPL


def create_charts_widget(colors, stats, apps, days=None):
    """Возвращает QWidget с графиками или с сообщением об отсутствии matplotlib."""
    if not HAS_MPL:
        return _no_mpl_widget(colors)
    return _ChartsWidget(colors, stats, apps, days=days)


def _no_mpl_widget(colors):
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(40, 40, 40, 40)
    lay.setAlignment(Qt.AlignCenter)
    lay.setSpacing(16)

    title = QLabel("📊 Требуется matplotlib")
    title.setAlignment(Qt.AlignCenter)
    title.setStyleSheet(
        f"color: {colors['TEXT']}; font-size: 18px; font-weight: bold;"
    )
    lay.addWidget(title)

    hint = QLabel(
        "Для отображения графиков установите библиотеку:\n\n"
        "    pip install matplotlib\n\n"
        "После установки перезапустите лаунчер."
    )
    hint.setAlignment(Qt.AlignCenter)
    hint.setStyleSheet(
        f"color: {colors['SUBTEXT']}; font-size: 13px;"
    )
    lay.addWidget(hint)

    if MPL_ERROR:
        err = QLabel(f"Ошибка импорта: {MPL_ERROR}")
        err.setAlignment(Qt.AlignCenter)
        err.setWordWrap(True)
        err.setStyleSheet(
            f"color: {colors['DANGER']}; font-size: 11px; padding-top: 12px;"
        )
        lay.addWidget(err)
    return w


# ==================== ГЛАВНЫЙ ВИДЖЕТ ГРАФИКОВ ====================
class _ChartsWidget(QWidget):
    def __init__(self, colors, stats, apps, days=None):
        super().__init__()
        self.colors = colors
        self.stats = stats
        self.apps = apps
        self.days = days

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        self.lay = QVBoxLayout(content)
        self.lay.setContentsMargins(14, 14, 14, 14)
        self.lay.setSpacing(16)

        self._build_pie()
        self._build_bar()
        self._build_line()

    # ---------- Общие настройки ----------
    def _new_figure(self, w_inches=6.0, h_inches=3.2):
        fig = Figure(figsize=(w_inches, h_inches), dpi=100)
        fig.patch.set_facecolor(self.colors["BG_ALT"])
        canvas = FigureCanvasQTAgg(fig)
        canvas.setStyleSheet("background: transparent;")
        canvas.setMinimumHeight(int(h_inches * 100))
        return fig, canvas

    def _setup_axes(self, ax):
        c = self.colors
        ax.set_facecolor(c["BG_ALT"])
        for spine in ax.spines.values():
            spine.set_color(c["BORDER"])
        ax.tick_params(colors=c["TEXT"], labelsize=9)
        if ax.title:
            ax.title.set_color(c["TEXT"])
        ax.grid(True, color=c["BORDER"], alpha=0.25, linewidth=0.5)

    def _section_title(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {self.colors['ACCENT']}; font-size: 13px; "
            f"font-weight: bold; background: transparent; padding-top: 6px;"
        )
        return lbl

    # ---------- 1) Круговая по категориям ----------
    def _build_pie(self):
        from stats import by_category
        by_cat = by_category(self.stats, self.apps, days=self.days)

        self.lay.addWidget(self._section_title("Распределение по категориям"))

        if not by_cat:
            empty = QLabel("Нет данных за выбранный период.")
            empty.setStyleSheet(
                f"color: {self.colors['SUBTEXT']}; font-size: 12px;"
            )
            self.lay.addWidget(empty)
            return

        fig, canvas = self._new_figure(h_inches=3.0)
        ax = fig.add_subplot(111)

        cats = list(by_cat.keys())
        sizes = [by_cat[k]["seconds"] for k in cats]
        labels = [CATEGORY_LABELS.get(k, k) for k in cats]

        # Палитра — акцент + вариации
        base = self.colors["ACCENT"]
        palette = self._category_palette(len(cats))

        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=None,
            autopct=lambda p: f"{p:.1f}%",
            colors=palette,
            startangle=90,
            wedgeprops={"edgecolor": self.colors["BG_ALT"], "linewidth": 2},
            textprops={"color": self.colors["TEXT"], "fontsize": 10},
        )
        for t in autotexts:
            t.set_color(self.colors["BG"])
            t.set_fontweight("bold")
            t.set_fontsize(9)

        ax.axis("equal")
        ax.legend(
            wedges,
            labels,
            loc="center left",
            bbox_to_anchor=(1.0, 0.5),
            frameon=False,
            labelcolor=self.colors["TEXT"],
            fontsize=10,
        )
        ax.set_title("")
        fig.tight_layout()
        self.lay.addWidget(canvas)

    def _category_palette(self, n):
        """Простая палитра от акцента."""
        from matplotlib.colors import to_rgba
        accent = self.colors["ACCENT"]
        rgba = to_rgba(accent)
        # Сгенерируем n оттенков, меняя яркость
        shades = []
        for i in range(max(1, n)):
            factor = 1.0 - (i * 0.18)
            factor = max(0.35, factor)
            r = rgba[0] * factor
            g = rgba[1] * factor
            b = rgba[2] * factor
            shades.append((r, g, b))
        return shades

    # ---------- 2) Столбчатая топ-10 ----------
    def _build_bar(self):
        from stats import get_top
        top = get_top(self.stats, self.apps, limit=10, days=self.days)

        self.lay.addWidget(self._section_title("Топ-10 программ"))

        if not top:
            empty = QLabel("Нет данных за выбранный период.")
            empty.setStyleSheet(
                f"color: {self.colors['SUBTEXT']}; font-size: 12px;"
            )
            self.lay.addWidget(empty)
            return

        names = [n for n, _ in top]
        # В секундах → в минутах для читаемости
        mins = [max(1, s // 60) for _, s in top]
        # Разворачиваем, чтобы первая программа была сверху
        names_r = list(reversed(names))
        mins_r = list(reversed(mins))

        fig, canvas = self._new_figure(h_inches=0.4 + 0.32 * len(names_r))
        ax = fig.add_subplot(111)

        accent = self.colors["ACCENT"]
        bars = ax.barh(names_r, mins_r, color=accent, edgecolor="none",
                       height=0.65)

        ax.set_xlabel("Минуты", color=self.colors["TEXT"], fontsize=9)
        ax.tick_params(colors=self.colors["TEXT"], labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(self.colors["BORDER"])
        ax.set_facecolor(self.colors["BG_ALT"])
        ax.grid(True, axis="x", color=self.colors["BORDER"],
                alpha=0.25, linewidth=0.5)

        # Подписи значений справа от столбиков
        for bar, val in zip(bars, mins_r):
            width = bar.get_width()
            if width > 0:
                ax.text(
                    width, bar.get_y() + bar.get_height() / 2,
                    f" {val}м",
                    va="center", ha="left",
                    color=self.colors["TEXT"], fontsize=8,
                )

        # Убираем обрезку длинных имён
        fig.tight_layout()
        self.lay.addWidget(canvas)

    # ---------- 3) Линейный тренд за 30 дней ----------
    def _build_line(self):
        from stats import daily_trend
        data = daily_trend(self.stats, self.apps, days=30)

        self.lay.addWidget(self._section_title("Тренд за 30 дней"))

        total = sum(s for _, s in data)
        if total <= 0:
            empty = QLabel("Нет данных за последние 30 дней.")
            empty.setStyleSheet(
                f"color: {self.colors['SUBTEXT']}; font-size: 12px;"
            )
            self.lay.addWidget(empty)
            return

        # Ось X — индексы (0..29), ось Y — минуты
        xs = list(range(len(data)))
        ys = [s // 60 for _, s in data]   # в минутах
        # Подписи: показываем каждую пятую дату в формате MM-DD
        labels = []
        for i, (d, _) in enumerate(data):
            if i % 5 == 0:
                labels.append(d[5:])  # MM-DD
            else:
                labels.append("")

        fig, canvas = self._new_figure(h_inches=3.0)
        ax = fig.add_subplot(111)

        accent = self.colors["ACCENT"]
        ax.plot(xs, ys, color=accent, linewidth=2,
                marker="o", markersize=3, markerfacecolor=accent)
        ax.fill_between(xs, ys, color=accent, alpha=0.15)

        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=0,
                           color=self.colors["TEXT"], fontsize=8)
        ax.set_ylabel("Минуты/день", color=self.colors["TEXT"], fontsize=9)
        ax.tick_params(colors=self.colors["TEXT"], labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(self.colors["BORDER"])
        ax.set_facecolor(self.colors["BG_ALT"])
        ax.grid(True, color=self.colors["BORDER"], alpha=0.25, linewidth=0.5)

        fig.tight_layout()
        self.lay.addWidget(canvas)

        # Итоговая подпись под графиком
        from stats import format_duration
        total_lbl = QLabel(
            f"Всего за 30 дней: {format_duration(total)}"
        )
        total_lbl.setStyleSheet(
            f"color: {self.colors['SUBTEXT']}; font-size: 11px; padding-top: 4px;"
        )
        self.lay.addWidget(total_lbl)