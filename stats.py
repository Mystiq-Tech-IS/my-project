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


def format_duration(seconds):
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


def get_top(stats, apps, limit=10, days=None):
    """Топ программ. days=None — за всё время, иначе за N дней."""
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
    """
    Возвращает dict: {category_key: {'seconds': int, 'apps': [(name, secs)]}}
    days=None — за всё время.
    """
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
    """
    Возвращает список (дата 'YYYY-MM-DD', суммарные_секунды) за последние N дней.
    Сумма — по всем переданным apps.
    """
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