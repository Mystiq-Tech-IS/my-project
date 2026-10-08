"""Пути, константы, настройки и профили лаунчера."""

import os

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
APPS_PATH     = os.path.join(BASE_DIR, "apps.json")
PRESETS_PATH  = os.path.join(BASE_DIR, "presets.json")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
PROFILES_PATH = os.path.join(BASE_DIR, "profiles.json")
LOG_PATH      = os.path.join(BASE_DIR, "launcher.log")

APP_NAME    = "Мой лаунчер"
APP_VERSION = "3.1.0"

GITHUB_REPO_URL = ""
LATEST_VERSION  = "3.1.0"

DEFAULT_SETTINGS = {
    "window_width": 1180,
    "window_height": 740,
    "start_view": "normal",
    "always_on_top": True,
    "close_to_tray": True,
    "silent_start": False,
    "autostart": False,

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

    # ---- Авто-обложки через Pillow ----
    "auto_cover_enabled": True,        # использовать, если нет своей обложки

    # ---- Уведомления ----
    "native_notifications": False,     # использовать plyer, если установлен

    "splash_enabled": True,
    "splash_duration": 1500,
    "bg_animation_enabled": True,
    "bg_animation_particles": 28,

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
        "startup":  True,
        "launch":   True,
        "close":    True,
        "error":    True,
        "success":  True,
        "info":     True,
        "shutdown": True,
    },

    "plugins_enabled": True,
    "enabled_plugins": [],

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