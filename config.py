"""Пути, константы, настройки и профили лаунчера."""

import os
import sys


def _is_frozen():
    return getattr(sys, "frozen", False)


def _app_dir():
    """Папка, где лежит .exe (или main.py при разработке).

    Сюда пишутся все изменяемые данные: apps.json, settings.json,
    backups/, stats.json и т.д.
    """
    if _is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _resource_dir():
    """Папка с ресурсами (sounds, plugins, icon, шаблоны).

    В .exe это _MEIPASS (одноразовая распаковка), при разработке —
    папка проекта. Ресурсы здесь только для чтения.
    """
    if _is_frozen():
        return getattr(sys, "_MEIPASS", _app_dir())
    return os.path.dirname(os.path.abspath(__file__))


# BASE_DIR оставлен для обратной совместимости: это папка с данными
BASE_DIR      = _app_dir()
RESOURCE_DIR  = _resource_dir()

APPS_PATH     = os.path.join(BASE_DIR, "apps.json")
PRESETS_PATH  = os.path.join(BASE_DIR, "presets.json")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
PROFILES_PATH = os.path.join(BASE_DIR, "profiles.json")
LOG_PATH      = os.path.join(BASE_DIR, "launcher.log")

APP_NAME    = "MyLauncher"
APP_VERSION = "0.1.0"

GITHUB_OWNER = "Mystiq-Tech-IS"
GITHUB_REPO  = "my-launcher"
GITHUB_REPO_URL =f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"

LATEST_VERSION  = "0.1.0"

DEFAULT_SETTINGS = {
    # Отображаемое название лаунчера — можно менять в Настройках.
    "app_name": APP_NAME,

    "window_width": 1180,
    "window_height": 740,
    "window_x": -1,
    "window_y": -1,
    "window_maximized": False,
    "start_view": "normal",
    "always_on_top": True,
    "close_to_tray": True,
    "silent_start": False,
    "autostart": False,

    # ---- Надёжность / бэкапы ----
    "autobackup_enabled": True,
    "autobackup_interval_minutes": 60,
    "show_load_errors": True,

    "theme": "dark",
    "accent": "blue",

    "hotkey": "ctrl+alt+l",
    "hotkey_enabled": True,
    "quick_hotkey": "ctrl+alt+space",
    "quick_hotkey_enabled": True,

    "show_clock": True,
    "show_search": True,
    "show_running_section": True,
    "show_covers": True,
    "show_glow": True,
    "show_status_text": True,
    "show_section_headers": True,
    "show_tile_badges": True,
    "hide_scrollbar": False,

    "tile_scale": 100,
    "icon_scale": 100,
    "animation_speed": 100,
    "use_material_icons": True,

    "auto_cover_enabled": True,
    "native_notifications": False,

    "splash_enabled": True,
    "splash_duration": 5000,
    "bg_animation_enabled": True,
    "bg_animation_particles": 28,

    # ---- Кастомный фон центральной области ----
    # bg_type: "particles" | "solid" | "image" | "gif" | "video"
    "bg_type": "particles",
    "bg_path": "",                # путь к файлу (png/jpg/gif/mp4/webm/…)
    "bg_opacity": 100,            # 0..100 — непрозрачность фона
    "bg_video_muted": True,       # без звука для видео
    "bg_gradient_color1": "",
    "bg_gradient_color2": "",
    "bg_gradient_angle": 45,
    "window_opacity": 100,
    "title_font_family": "Segoe UI",

    "show_system_monitor": True,
    "system_monitor_interval": 2,
    "system_monitor_gpu": True,

    "confirm_kill": True,
    "overlay_enabled": True,
    "companions_enabled": True,

    "switch_to_window_on_running": False,
    "activate_after_launch": False,

    "sound_enabled": True,
    "sound_volume": 60,
    "sound_events": {
        "launch":  True,
        "close":   True,
        "success": True,
        "error":   True,
        "notify":  False,
        "click":   False,
        "toggle":  False,
    },

    "voice_enabled": False,
    "voice_volume": 80,
    "voice_events": {
        "startup":     True,
        "ready":       True,
        "launch":      True,
        "close":       True,
        "error":       True,
        "success":     True,
        "info":        True,
        "shutdown":    True,
        "click_every": False,
    },

    "plugins_enabled": True,
    "enabled_plugins": [],
# ---- Discord Rich Presence ----
    "discord_enabled": False,
    "discord_client_id": "",
    "discord_large_image": "logo",
    "discord_large_text": APP_NAME,
    "discord_show_when_idle": True,
# ---- SteamGridDB (обложки игр из интернета) ----
    "steamgriddb_api_key": "",
    "steamgriddb_enabled": True,

    "current_category": "all",
    "current_subcategory": "all",
    "active_profile": "custom",
    "cloud_folder": "",
    "recent_paths": [],
    "tray_icon": "",
    "category_companions": {},
    "category_covers": {},
    "subcategories": {},
    "mini_mode": False,
    "mini_width": 240,
    "mini_height": 600,
}

BUILTIN_PROFILES = {
    "custom": {
        "name": "Пользовательский",
        "icon": "fa5s.user-cog",
        "settings": {},
    },
    "gaming": {
        "name": "Игровой",
        "icon": "fa5s.gamepad",
        "settings": {
            "theme": "dark",
            "accent": "purple",
            "show_clock": False,
            "show_search": True,
            "show_running_section": True,
            "show_covers": True,
            "show_glow": True,
            "show_status_text": False,
            "show_section_headers": False,
            "show_tile_badges": True,
            "tile_scale": 120,
            "icon_scale": 120,
            "animation_speed": 130,
            "hide_scrollbar": False,
            "current_category": "games",
            "bg_type": "particles",
            "bg_animation_enabled": True,
            "bg_animation_particles": 45,
        },
    },
    "work": {
        "name": "Рабочий",
        "icon": "fa5s.briefcase",
        "settings": {
            "theme": "light",
            "accent": "blue",
            "show_clock": True,
            "show_search": True,
            "show_running_section": True,
            "show_covers": False,
            "show_glow": False,
            "show_status_text": True,
            "show_section_headers": True,
            "show_tile_badges": False,
            "tile_scale": 90,
            "icon_scale": 90,
            "animation_speed": 100,
                        "hide_scrollbar": True,
            "current_category": "work",
            "bg_type": "solid",
            "bg_animation_enabled": False,
        },
    },
    "minimal": {
        "name": "Минимализм",
        "icon": "fa5s.feather",
        "settings": {
            "theme": "dark",
            "accent": "green",
            "show_clock": False,
            "show_search": True,
            "show_running_section": False,
            "show_covers": False,
            "show_glow": False,
            "show_status_text": False,
            "show_section_headers": False,
            "show_tile_badges": False,
            "tile_scale": 85,
            "icon_scale": 85,
            "animation_speed": 80,
                        "hide_scrollbar": True,
            "current_category": "all",
            "bg_type": "solid",
            "bg_animation_enabled": False,
        },
    },
    "cinema": {
        "name": "Кино / Мультимедиа",
        "icon": "fa5s.film",
        "settings": {
            "theme": "dark",
            "accent": "pink",
            "show_clock": False,
            "show_search": True,
            "show_running_section": False,
            "show_covers": True,
            "show_glow": True,
            "show_status_text": False,
            "show_section_headers": False,
            "show_tile_badges": True,
            "tile_scale": 135,
            "icon_scale": 130,
            "animation_speed": 150,
                        "hide_scrollbar": False,
            "current_category": "other",
            "bg_type": "gradient",
            "bg_gradient_color1": "#F5C2E7",
            "bg_gradient_color2": "#16161E",
            "bg_gradient_angle": 30,
            "bg_animation_enabled": False,
        },
    },
}

DEFAULT_APPS = [
    {
        "name": "Steam",
        "path": r"C:\Program Files (x86)\Steam\Steam.exe",
        "favorite": False,
        "launch_count": 0,
        "category": "games",
        "subcategory": "",
        "custom_icon": "",
        "custom_cover": "",
        "order": 0,
        "hotkey": "",
        "companions": [],
        "note": "",
        "known_version": "",
    },
]

DEFAULT_PRESETS = [
    {
        "name": "Пример: Работа",
        "icon": "💼",
        "paths": [],
        "description": "Открой настройки пресета, чтобы добавить программы",
    },
]

CATEGORIES = {
    "all":     ("Все",      "🗂"),
    "recent":  ("Недавние", "🕘"),
    "games":   ("Игры",     "🎮"),
    "work":    ("Работа",   "💼"),
    "system":  ("Система",  "⚙"),
    "other":   ("Прочее",   "📦"),
}