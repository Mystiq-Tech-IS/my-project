"""Управление профилями настроек: загрузка, сохранение, применение."""

import os
import json
from copy import deepcopy

from config import (
    PROFILES_PATH, DEFAULT_SETTINGS, BUILTIN_PROFILES,
)
from storage import log


def load_custom_profiles():
    """Возвращает пользовательские профили (созданные или изменённые)."""
    if not os.path.exists(PROFILES_PATH):
        return {}
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"load_custom_profiles: {e}")
        return {}


def save_custom_profiles(profiles):
    try:
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"save_custom_profiles: {e}")


def all_profiles():
    """Возвращает объединённый словарь: встроенные + перезаписанные пользователем."""
    result = deepcopy(BUILTIN_PROFILES)
    custom = load_custom_profiles()
    for key, prof in custom.items():
        result[key] = prof
    return result


def apply_profile(profile_key, base_settings=None):
    """
    Возвращает новый словарь настроек:
    копия base_settings (или DEFAULT_SETTINGS) + переопределения профиля.
    """
    base = dict(base_settings) if base_settings else dict(DEFAULT_SETTINGS)
    profiles = all_profiles()
    prof = profiles.get(profile_key)
    if not prof:
        return base
    overrides = prof.get("settings", {})
    for k, v in overrides.items():
        base[k] = v
    base["active_profile"] = profile_key
    return base


def current_overrides(profile_key):
    """Возвращает только те настройки, которые профиль переопределяет."""
    profiles = all_profiles()
    prof = profiles.get(profile_key, {})
    return dict(prof.get("settings", {}))


def save_user_override(profile_key, key, value):
    """Сохраняет пользовательскую настройку в профиль (создаёт, если нужно)."""
    custom = load_custom_profiles()

    if profile_key not in custom:
        # Копируем встроенный профиль и дополняем
        builtin = BUILTIN_PROFILES.get(profile_key, {})
        custom[profile_key] = deepcopy(builtin)

    custom[profile_key].setdefault("settings", {})
    custom[profile_key]["settings"][key] = value
    save_custom_profiles(custom)


def reset_profile(profile_key):
    """Сбрасывает профиль к встроенному состоянию."""
    custom = load_custom_profiles()
    if profile_key in custom:
        del custom[profile_key]
        save_custom_profiles(custom)
        log.info(f"Профиль сброшен: {profile_key}")


def diff_from_default(settings):
    """Возвращает только те настройки, которые отличаются от дефолтных."""
    out = {}
    for k, v in settings.items():
        if k == "active_profile":
            continue
        if DEFAULT_SETTINGS.get(k) != v:
            out[k] = v
    return out