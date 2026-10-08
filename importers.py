"""Сканирование меню Пуск, Steam, Epic и рабочего стола."""

import os
import re
import glob
import json
import string

from storage import log


# ==================== МЕНЮ ПУСК ====================
def scan_start_menu():
    folders = [
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                     "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("APPDATA", ""),
                     "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    results = []
    seen = set()
    skip_words = ("uninstall", "удалить", "деинстал", "readme", "справка")

    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for root, _, files in os.walk(folder):
            for f in files:
                if not f.lower().endswith(".lnk"):
                    continue
                name = os.path.splitext(f)[0]
                if any(w in name.lower() for w in skip_words):
                    continue
                full = os.path.join(root, f)
                if full in seen:
                    continue
                seen.add(full)
                results.append({
                    "name": name,
                    "path": full,
                    "source": "start_menu",
                    "category": guess_category(name, "start_menu"),
                })
    results.sort(key=lambda x: x["name"].lower())
    log.info(f"Меню Пуск: найдено {len(results)} ярлыков")
    return results


# ==================== РАБОЧИЙ СТОЛ ====================
def scan_desktop():
    """Сканирует ярлыки с рабочего стола текущего пользователя + общего."""
    folders = [
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
    ]
    results = []
    seen = set()
    skip_words = ("uninstall", "удалить", "деинстал", "readme", "справка")

    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for f in os.listdir(folder):
            if not f.lower().endswith(".lnk"):
                continue
            name = os.path.splitext(f)[0]
            if any(w in name.lower() for w in skip_words):
                continue
            full = os.path.join(folder, f)
            if full in seen:
                continue
            seen.add(full)
            results.append({
                "name": name,
                "path": full,
                "source": "desktop",
                "category": guess_category(name, "desktop"),
            })
    results.sort(key=lambda x: x["name"].lower())
    log.info(f"Рабочий стол: найдено {len(results)} ярлыков")
    return results


# ==================== АВТО-КАТЕГОРИЯ ====================
def guess_category(name: str, source: str = "") -> str:
    if source in ("steam", "epic"):
        return "games"
    n = (name or "").lower()

    game_words = ("steam", "epic", "gog", "origin", "uplay", "battle.net",
                  "rockstar", "riot", "игр", "game", "unity", "unreal",
                  "minecraft", "roblox")
    if any(w in n for w in game_words):
        return "games"

    work_words = ("office", "word", "excel", "powerpoint", "outlook",
                  "onenote", "teams", "slack", "zoom", "discord", "skype",
                  "telegram", "whatsapp", "visual studio", "vs code",
                  "vscode", "pycharm", "intellij", "webstorm", "sublime",
                  "notepad++", "jetbrains", "eclipse", "photoshop",
                  "illustrator", "figma", "blender", "gimp", "obsidian",
                  "notion", "evernote", "trello", "jira", "git", "postman",
                  "insomnia", "dbeaver")
    if any(w in n for w in work_words):
        return "work"

    sys_words = ("панель управления", "control panel",
                 "диспетчер задач", "task manager",
                 "командная строка", "command prompt",
                 "powershell", "cmd", "terminal", "term",
                 "проводник", "explorer", "настройки", "settings",
                 "regedit", "реестр", "управление дисками",
                 "диспетчер устройств", "службы", "services",
                 "просмотр событий", "восстановление",
                 "дефрагментация", "калькулятор", "calculator")
    if any(w in n for w in sys_words):
        return "system"

    return "other"


# ==================== STEAM ====================
def find_steam_path():
    candidates = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
    ]
    for letter in string.ascii_uppercase:
        candidates.append(f"{letter}:\\Steam")
        candidates.append(f"{letter}:\\Games\\Steam")
    for c in candidates:
        if os.path.exists(os.path.join(c, "steam.exe")):
            return c
    return None


def _parse_vdf_paths(vdf_path):
    if not os.path.exists(vdf_path):
        return []
    try:
        with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        log.error(f"Не удалось прочитать {vdf_path}: {e}")
        return []
    paths = []
    for match in re.finditer(r'"path"\s+"([^"]+)"', content):
        p = match.group(1).replace("\\\\", "\\")
        paths.append(p)
    return paths


def _parse_appmanifest(acf_path):
    try:
        with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return None
    appid_m   = re.search(r'"appid"\s+"(\d+)"', content)
    name_m    = re.search(r'"name"\s+"([^"]+)"', content)
    install_m = re.search(r'"installdir"\s+"([^"]+)"', content)
    if not (appid_m and name_m):
        return None
    return {
        "appid":      appid_m.group(1),
        "name":       name_m.group(1),
        "installdir": install_m.group(1) if install_m else "",
    }


def scan_steam(steam_path=None):
    if not steam_path:
        steam_path = find_steam_path()
    if not steam_path:
        return []

    library_folders = [steam_path]
    vdf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    library_folders.extend(_parse_vdf_paths(vdf))

    results = []
    seen_ids = set()
    for lib in library_folders:
        steamapps = os.path.join(lib, "steamapps")
        if not os.path.isdir(steamapps):
            continue
        for acf in glob.glob(os.path.join(steamapps, "appmanifest_*.acf")):
            info = _parse_appmanifest(acf)
            if not info:
                continue
            appid = info["appid"]
            if appid in seen_ids:
                continue
            seen_ids.add(appid)
            results.append({
                "name":     info["name"],
                "path":     f"steam://rungameid/{appid}",
                "appid":    appid,
                "source":   "steam",
                "category": "games",
            })
    results.sort(key=lambda x: x["name"].lower())
    log.info(f"Steam: найдено {len(results)} игр")
    return results


# ==================== EPIC ====================
def scan_epic():
    manifest = r"C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat"
    if not os.path.exists(manifest):
        return []
    try:
        with open(manifest, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.error(f"Epic manifest: {e}")
        return []

    install_list = data.get("InstallationList", [])
    results = []
    skip_exe = ("unins", "crash", "report", "launcher", "setup", "redist")

    for item in install_list:
        loc = item.get("InstallLocation")
        name = item.get("AppName") or (os.path.basename(loc) if loc else "Epic Game")
        if not loc or not os.path.isdir(loc):
            continue
        exe_path = None
        try:
            files = os.listdir(loc)
        except Exception:
            files = []
        name_norm = name.lower().replace(" ", "")
        candidates = []
        for f in files:
            if not f.lower().endswith(".exe"):
                continue
            fl = f.lower()
            if any(w in fl for w in skip_exe):
                continue
            candidates.append(f)
        for f in candidates:
            if name_norm and name_norm in f.lower().replace(" ", ""):
                exe_path = os.path.join(loc, f)
                break
        if not exe_path and candidates:
            exe_path = os.path.join(loc, candidates[0])
        target = exe_path or loc
        results.append({
            "name": name, "path": target,
            "source": "epic", "category": "games",
        })
    results.sort(key=lambda x: x["name"].lower())
    log.info(f"Epic: найдено {len(results)} игр")
    return results