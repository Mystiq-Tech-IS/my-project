"""Загрузка/сохранение apps.json, presets.json, settings.json, бэкапы."""

import json
import os
import shutil
import logging
from datetime import datetime

from config import (
    APPS_PATH, PRESETS_PATH, SETTINGS_PATH, LOG_PATH,
    DEFAULT_APPS, DEFAULT_PRESETS, DEFAULT_SETTINGS, CATEGORIES,
    BASE_DIR,
)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("launcher")

BACKUP_DIR = os.path.join(BASE_DIR, "backups")
BACKUP_KEEP = 7


def _normalize_category(value):
    if not value:
        return "other"
    value = str(value)
    if value in CATEGORIES:
        return value
    return "other"


def backup_apps():
    if not os.path.exists(APPS_PATH):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dst = os.path.join(BACKUP_DIR, f"apps_{stamp}.json")
        shutil.copy2(APPS_PATH, dst)
        files = sorted(
            [f for f in os.listdir(BACKUP_DIR)
             if f.startswith("apps_") and f.endswith(".json")],
            reverse=True,
        )
        for old in files[BACKUP_KEEP:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except Exception:
                pass
        log.info(f"Бэкап создан: {dst}")
    except Exception as e:
        log.error(f"Не удалось создать бэкап: {e}")


def load_apps():
    if not os.path.exists(APPS_PATH):
        result = []
        for i, a in enumerate(DEFAULT_APPS):
            item = dict(a)
            item.setdefault("order", i)
            item.setdefault("companions", [])
            item.setdefault("note", "")
            item.setdefault("subcategory", "")
            item.setdefault("known_version", "")
            item["category"] = _normalize_category(item.get("category"))
            result.append(item)
        return result
    try:
        with open(APPS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for i, a in enumerate(data):
            a.setdefault("favorite", False)
            a.setdefault("launch_count", 0)
            a.setdefault("custom_icon", "")
            a.setdefault("custom_cover", "")
            a.setdefault("order", i)
            a.setdefault("hotkey", "")
            a.setdefault("companions", [])
            a.setdefault("note", "")
            a.setdefault("subcategory", "")
            a.setdefault("known_version", "")
            a["category"] = _normalize_category(a.get("category"))
            a.pop("_has_update", None)
            a.pop("_category_cover_folder", None)
        return data
    except Exception as e:
        log.error(f"Не удалось загрузить apps.json: {e}")
        return [dict(a) for a in DEFAULT_APPS]


def save_apps(apps):
    try:
        clean = []
        for a in apps:
            d = dict(a)
            d.pop("_has_update", None)
            d.pop("_clear_hotkey", None)
            d.pop("_category_cover_folder", None)
            clean.append(d)
        with open(APPS_PATH, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Не удалось сохранить apps.json: {e}")


# ==================== PRESETS ====================
def load_presets():
    if not os.path.exists(PRESETS_PATH):
        return [dict(p) for p in DEFAULT_PRESETS]
    try:
        with open(PRESETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for p in data:
            p.setdefault("name", "Без имени")
            p.setdefault("icon", "🚀")
            p.setdefault("paths", [])
            p.setdefault("description", "")
        return data
    except Exception as e:
        log.error(f"Не удалось загрузить presets.json: {e}")
        return [dict(p) for p in DEFAULT_PRESETS]


def save_presets(presets):
    try:
        with open(PRESETS_PATH, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Не удалось сохранить presets.json: {e}")


# ==================== SETTINGS ====================
def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(s)
        for k in ("sound_events", "category_companions",
                  "category_covers", "subcategories"):
            default_val = DEFAULT_SETTINGS.get(k) or {}
            user_val = s.get(k) or {}
            m = dict(default_val)
            m.update(user_val)
            merged[k] = m
        # enabled_plugins — список, оставим как есть
        return merged
    except Exception as e:
        log.error(f"Не удалось загрузить settings.json: {e}")
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Не удалось сохранить settings.json: {e}")