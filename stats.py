"""Учёт времени использования программ (с разбивкой по дням)."""

import os
import json
from datetime import datetime, timedelta

from config import BASE_DIR
from storage import log

STATS_PATH = os.path.join(BASE_DIR, "stats.json")


def load_stats():
    if not os.path.exists(STATS_PATH):
        return {}
    try:
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"load_stats: {e}")
        return {}


def save_stats(stats):
    try:
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"save_stats: {e}")


def add_time(stats, path, seconds):
    """Добавляет время. Помимо общей суммы копит разбивку по дням в daily."""
    if not path:
        return
    entry = stats.get(path) or {"seconds": 0, "last_seen": "", "daily": {}}
    entry["seconds"] = int(entry.get("seconds", 0)) + int(seconds)
    entry["last_seen"] = datetime.now().isoformat(timespec="seconds")
    today = datetime.now().strftime("%Y-%m-%d")
    daily = entry.setdefault("daily", {})
    daily[today] = int(daily.get(today, 0)) + int(seconds)
    stats[path] = entry


def _seconds_in_period(entry, days):
    """Сколько секунд у записи за последние N дней. days=None — всё время."""
    if days is None:
        return int(entry.get("seconds", 0))
    daily = entry.get("daily") or {}
    if not daily:
        return int(entry.get("seconds", 0))
    cutoff = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    total = 0
    for d, s in daily.items():
        if d >= cutoff:
            total += int(s)
    return total


# ==================== КОРОТКИЙ ФОРМАТ ====================

def format_short(seconds):
    """Короткий формат: 12с, 35м, 1ч 20м, 2д 5ч.

    Используется на карточках, где мало места.
    """
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}с"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}м"
    hours = minutes // 60
    minutes = minutes % 60
    if hours < 24:
        if minutes:
            return f"{hours}ч {minutes}м"
        return f"{hours}ч"
    days = hours // 24
    hours = hours % 24
    return f"{days}д {hours}ч"


def format_duration(seconds):
    """Полный формат для отчётов: '1 ч 20 мин', '2 д 5 ч'."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} сек"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes // 60
    minutes = minutes % 60
    if hours < 24:
        return f"{hours}ч {minutes}м" if minutes else f"{hours} ч"
    days = hours // 24
    hours = hours % 24
    return f"{days}д {hours}ч"


# ==================== ВРЕМЯ КОНКРЕТНОЙ ИГРЫ ====================

def get_today_seconds(stats, path):
    """Сколько секунд у программы за сегодня."""
    if not path:
        return 0
    entry = stats.get(path)
    if not entry:
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    daily = entry.get("daily") or {}
    return int(daily.get(today, 0))


def get_week_seconds(stats, path):
    """Время за последние 7 дней."""
    if not path:
        return 0
    entry = stats.get(path)
    if not entry:
        return 0
    return _seconds_in_period(entry, 7)


def get_total_seconds(stats, path):
    """Всё время по программе."""
    if not path:
        return 0
    entry = stats.get(path) or {}
    return int(entry.get("seconds", 0))


def get_month_seconds(stats, path):
    """Время за последние 30 дней."""
    if not path:
        return 0
    entry = stats.get(path)
    if not entry:
        return 0
    return _seconds_in_period(entry, 30)


# ==================== ОБЩЕЕ ВРЕМЯ ====================

def get_today_total(stats, apps):
    """Общее время за сегодня по всем программам."""
    today = datetime.now().strftime("%Y-%m-%d")
    total = 0
    for app in apps:
        path = app.get("path", "")
        entry = stats.get(path)
        if not entry:
            continue
        daily = entry.get("daily") or {}
        total += int(daily.get(today, 0))
    return total


def get_week_total(stats, apps):
    """Общее время за последние 7 дней."""
    total = 0
    for app in apps:
        path = app.get("path", "")
        entry = stats.get(path)
        if not entry:
            continue
        total += _seconds_in_period(entry, 7)
    return total


# ==================== АКТИВНЫЕ СЕГОДНЯ ====================

def get_active_since_today(stats, apps, threshold_min=5):
    """Программы, в которые играли сегодня (>= threshold_min минут).

    Возвращает список [(app, today_seconds)], отсортированный по убыванию.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    result = []
    for app in apps:
        path = app.get("path", "")
        entry = stats.get(path)
        if not entry:
            continue
        daily = entry.get("daily") or {}
        secs = int(daily.get(today, 0))
        if secs >= threshold_min * 60:
            result.append((app, secs))
    result.sort(key=lambda x: x[1], reverse=True)
    return result


# ==================== СУЩЕСТВУЮЩИЕ ФУНКЦИИ ====================

def get_top(stats, apps, limit=10, days=None):
    entries = []
    for app in apps:
        path = app.get("path", "")
        entry = stats.get(path)
        if not entry:
            continue
        secs = _seconds_in_period(entry, days)
        if secs <= 0:
            continue
        entries.append((app.get("name", path), secs))
    entries.sort(key=lambda x: x[1], reverse=True)
    return entries[:limit]


def by_category(stats, apps, days=None):
    result = {}
    for app in apps:
        path = app.get("path", "")
        cat = app.get("category") or "other"
        entry = stats.get(path)
        if not entry:
            continue
        secs = _seconds_in_period(entry, days)
        if secs <= 0:
            continue

        if cat not in result:
            result[cat] = {"seconds": 0, "apps": []}
        result[cat]["seconds"] += secs
        result[cat]["apps"].append((app.get("name", path), secs))

    for cat in result:
        result[cat]["apps"].sort(key=lambda x: x[1], reverse=True)

    return result


def total_by_category(stats, apps):
    b = by_category(stats, apps)
    return {k: v["seconds"] for k, v in b.items()}


def daily_trend(stats, apps, days=30):
    daily_total = {}
    for app in apps:
        path = app.get("path", "")
        entry = stats.get(path)
        if not entry:
            continue
        daily = entry.get("daily") or {}
        for d, s in daily.items():
            daily_total[d] = daily_total.get(d, 0) + int(s)

    result = []
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    for i in range(days):
        d = start + timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        result.append((key, daily_total.get(key, 0)))
    return result


def reset_stats():
    try:
        if os.path.exists(STATS_PATH):
            os.remove(STATS_PATH)
        return True
    except Exception as e:
        log.error(f"reset_stats: {e}")
        return False