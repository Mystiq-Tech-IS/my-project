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


# Последняя ошибка загрузки — чтобы UI мог показать диалог.
_last_load_error = ""


def get_last_load_error():
    """Возвращает текст последней ошибки загрузки ('' — если всё ок)."""
    return _last_load_error


def clear_last_load_error():
    global _last_load_error
    _last_load_error = ""


def _normalize_category(value):
    if not value:
        return "other"
    value = str(value)
    if value in CATEGORIES:
        return value
    return "other"


# ==================== БЭКАПЫ ====================

def _cleanup_backups(prefix):
    """Удаляет старые файлы {prefix}_*.json, оставляя BACKUP_KEEP свежих."""
    try:
        files = sorted(
            [f for f in os.listdir(BACKUP_DIR)
             if f.startswith(prefix) and f.endswith(".json")],
            reverse=True,
        )
        for old in files[BACKUP_KEEP:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except Exception:
                pass
    except Exception:
        pass


def backup_apps():
    """Быстрый бэкап только apps.json (вызывается при старте)."""
    if not os.path.exists(APPS_PATH):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dst = os.path.join(BACKUP_DIR, f"apps_{stamp}.json")
        shutil.copy2(APPS_PATH, dst)
        _cleanup_backups("apps_")
        log.info(f"Бэкап создан: {dst}")
    except Exception as e:
        log.error(f"Не удалось создать бэкап: {e}")


def backup_all():
    """Полный бэкап apps + settings + presets. Используется автобэкапом."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        copied = []
        for src, prefix in [
            (APPS_PATH, "apps"),
            (SETTINGS_PATH, "settings"),
            (PRESETS_PATH, "presets"),
        ]:
            if os.path.exists(src):
                dst = os.path.join(BACKUP_DIR, f"{prefix}_{stamp}.json")
                shutil.copy2(src, dst)
                copied.append(prefix)
                _cleanup_backups(f"{prefix}_")

        if copied:
            log.info(f"Автобэкап: {', '.join(copied)} → {stamp}")
        return True
    except Exception as e:
        log.error(f"Автобэкап не удался: {e}")
        return False


def save_broken_file(path):
    """Сохраняет битый файл рядом с бэкапами с суффиксом .broken."""
    if not path or not os.path.exists(path):
        return ""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = os.path.basename(path)
        dst = os.path.join(BACKUP_DIR, f"{name}.broken_{stamp}")
        shutil.copy2(path, dst)
        log.warning(f"Битый файл сохранён: {dst}")
        return dst
    except Exception as e:
        log.error(f"save_broken_file: {e}")
        return ""


# ==================== APPS ====================

def load_apps():
    """Загружает apps.json. При ошибке — сохраняет битый файл и вернёт дефолт."""
    global _last_load_error

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

        if not isinstance(data, list):
            raise ValueError("apps.json должен содержать список")

    except Exception as e:
        err = f"{e}"
        log.error(f"Не удалось загрузить apps.json: {err}")

        # Сохраняем битый файл
        broken_path = save_broken_file(APPS_PATH)
        _last_load_error = (
            f"Файл apps.json повреждён и не может быть прочитан.\n\n"
            f"Ошибка: {err}\n\n"
            f"Резервная копия сохранена:\n"
            f"{broken_path or 'не удалось сохранить'}\n\n"
            f"Загружен пустой список программ. "
            f"Восстановите файл из папки backups."
        )

        return [dict(a) for a in DEFAULT_APPS]

    # Валидация и нормализация
    try:
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
            a.pop("_auto_cover_enabled", None)
        return data
    except Exception as e:
        log.error(f"Ошибка валидации apps.json: {e}")
        _last_load_error = (
            f"apps.json содержит некорректные записи: {e}"
        )
        return []


def save_apps(apps):
    try:
        clean = []
        for a in apps:
            d = dict(a)
            d.pop("_has_update", None)
            d.pop("_clear_hotkey", None)
            d.pop("_category_cover_folder", None)
            d.pop("_auto_cover_enabled", None)
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
        if not isinstance(data, list):
            raise ValueError("presets.json должен быть списком")
        for p in data:
            p.setdefault("name", "Без имени")
            p.setdefault("icon", "🚀")
            p.setdefault("paths", [])
            p.setdefault("description", "")
        return data
    except Exception as e:
        log.error(f"Не удалось загрузить presets.json: {e}")
        save_broken_file(PRESETS_PATH)
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
        if not isinstance(s, dict):
            raise ValueError("settings.json должен быть словарём")
        merged = dict(DEFAULT_SETTINGS)
        merged.update(s)
        for k in ("sound_events", "voice_events",
                  "category_companions", "category_covers",
                  "subcategories"):
            default_val = DEFAULT_SETTINGS.get(k) or {}
            user_val = s.get(k) or {}
            m = dict(default_val)
            m.update(user_val)
            merged[k] = m
        return merged
    except Exception as e:
        log.error(f"Не удалось загрузить settings.json: {e}")
        save_broken_file(SETTINGS_PATH)
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Не удалось сохранить settings.json: {e}")