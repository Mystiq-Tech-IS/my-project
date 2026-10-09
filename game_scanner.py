"""Сканер установленных игр на компьютере.

Источники:
  • Steam       (steamapps + appmanifest_*.acf)
  • Epic Games  (LauncherInstalled.dat)
  • GOG Galaxy  (реестр + goggame-*.info)
  • Battle.net  (реестр Blizzard Entertainment)
  • Ubisoft     (реестр Ubisoft Launcher)
  • EA App      (реестр Electronic Arts)
  • Реестр Windows (Uninstall — с жёстким фильтром «мусора»)

Результат кэшируется в games_cache.json. Обложки из Steam Store API
кэшируются в .game_covers/ и подгружаются по URL.
"""

import os
import re
import glob
import json
import time
import string
import winreg
import urllib.request

from config import BASE_DIR

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")


CACHE_PATH = os.path.join(BASE_DIR, "games_cache.json")
COVERS_DIR = os.path.join(BASE_DIR, ".game_covers")
CACHE_TTL_SECONDS = 60 * 30  # 30 минут


def _ensure_covers_dir():
    try:
        os.makedirs(COVERS_DIR, exist_ok=True)
    except Exception:
        pass


# ==================== STEAM ====================

# Что попадает в steamapps, но играми не является
_STEAM_SKIP_WORDS = (
    "redistributables", "steamworks common", "steam linux runtime",
    "steamvr", "proton", "steam controller", "steam link",
    "steamworks sdk",
    "wallpaper engine",
)


def _find_steam_path():
    candidates = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
    ]
    for letter in string.ascii_uppercase:
        candidates.append(f"{letter}:\\Steam")
        candidates.append(f"{letter}:\\Games\\Steam")
        candidates.append(f"{letter}:\\SteamLibrary")
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
    except Exception:
        return []
    return [
        m.group(1).replace("\\\\", "\\")
        for m in re.finditer(r'"path"\s+"([^"]+)"', content)
    ]


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


def _is_steam_junk(name):
    n = (name or "").lower()
    return any(w in n for w in _STEAM_SKIP_WORDS)


def _scan_steam():
    steam_path = _find_steam_path()
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

            if _is_steam_junk(info["name"]):
                continue

            install_dir = ""
            if info["installdir"]:
                install_dir = os.path.join(
                    steamapps, "common", info["installdir"]
                )

            results.append({
                "name":        info["name"],
                "path":        f"steam://rungameid/{appid}",
                "install_dir": install_dir,
                "source":      "steam",
                "appid":       appid,
                "icon_path":   "",
                "cover_url":   (
                    f"https://cdn.cloudflare.steamstatic.com/"
                    f"steam/apps/{appid}/header.jpg"
                ),
            })

    results.sort(key=lambda x: x["name"].lower())
    log.info(f"game_scanner: Steam — {len(results)} игр")
    return results


# ==================== EPIC ====================

def _scan_epic():
    manifest = r"C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat"
    if not os.path.exists(manifest):
        return []
    try:
        with open(manifest, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.error(f"game_scanner epic manifest: {e}")
        return []

    install_list = data.get("InstallationList", [])
    results = []
    skip_exe = ("unins", "crash", "report", "launcher", "setup", "redist")

    for item in install_list:
        loc = item.get("InstallLocation")
        name = (item.get("AppName")
                or (os.path.basename(loc) if loc else "Epic Game"))
        if not loc or not os.path.isdir(loc):
            continue

        exe_path = None
        try:
            files = os.listdir(loc)
        except Exception:
            files = []

        name_norm = name.lower().replace(" ", "")
        candidates = [
            f for f in files
            if f.lower().endswith(".exe")
            and not any(w in f.lower() for w in skip_exe)
        ]

        for f in candidates:
            if name_norm and name_norm in f.lower().replace(" ", ""):
                exe_path = os.path.join(loc, f)
                break
        if not exe_path and candidates:
            exe_path = os.path.join(loc, candidates[0])

        results.append({
            "name":        name,
            "path":        exe_path or loc,
            "install_dir": loc,
            "source":      "epic",
            "icon_path":   exe_path or "",
            "cover_url":   "",
        })

    results.sort(key=lambda x: x["name"].lower())
    log.info(f"game_scanner: Epic — {len(results)} игр")
    return results


# ==================== GOG ====================

def _scan_gog():
    results = []
    base_keys = [
        r"SOFTWARE\WOW6432Node\GOG.com\Games",
        r"SOFTWARE\GOG.com\Games",
    ]
    for base in base_keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(k, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(k, sub) as sk:
                            def _get(name, default=""):
                                try:
                                    v, _ = winreg.QueryValueEx(sk, name)
                                    return v
                                except Exception:
                                    return default
                            name = _get("gameName")
                            path = _get("path")
                            exe  = _get("exe")
                            if not name or not path:
                                continue
                            full_exe = exe if exe and os.path.isabs(exe) \
                                else os.path.join(path, exe) if exe else path
                            results.append({
                                "name":        name,
                                "path":        full_exe,
                                "install_dir": path,
                                "source":      "gog",
                                "icon_path":   full_exe,
                                "cover_url":   "",
                            })
                    except Exception:
                        continue
        except FileNotFoundError:
            continue
        except Exception as e:
            log.error(f"game_scanner gog: {e}")
    log.info(f"game_scanner: GOG — {len(results)} игр")
    return results


# ==================== BATTLE.NET ====================

def _scan_battlenet():
    results = []
    base = r"SOFTWARE\WOW6432Node\Blizzard Entertainment"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    i += 1
                except OSError:
                    break
                if sub.lower() in ("launcher", "battle.net"):
                    continue
                try:
                    with winreg.OpenKey(k, sub) as sk:
                        try:
                            install, _ = winreg.QueryValueEx(sk, "InstallPath")
                        except Exception:
                            continue
                        if not install or not os.path.isdir(install):
                            continue
                        exe = None
                        for f in os.listdir(install):
                            if f.lower().endswith(".exe") \
                                    and "launcher" not in f.lower() \
                                    and "updater" not in f.lower():
                                exe = os.path.join(install, f)
                                break
                        results.append({
                            "name":        sub.replace("_", " "),
                            "path":        exe or install,
                            "install_dir": install,
                            "source":      "battlenet",
                            "icon_path":   exe or "",
                            "cover_url":   "",
                        })
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    except Exception as e:
        log.error(f"game_scanner battlenet: {e}")
    log.info(f"game_scanner: Battle.net — {len(results)} игр")
    return results


# ==================== UBISOFT ====================

def _scan_ubisoft():
    results = []
    bases = [
        r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs",
        r"SOFTWARE\Ubisoft\Launcher\Installs",
    ]
    for base in bases:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(k, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(k, sub) as sk:
                            try:
                                install, _ = winreg.QueryValueEx(
                                    sk, "InstallDir"
                                )
                            except Exception:
                                continue
                            install = install.replace("/", "\\")
                            if not install or not os.path.isdir(install):
                                continue
                            exe = None
                            for f in os.listdir(install):
                                if f.lower().endswith(".exe") \
                                        and "launcher" not in f.lower():
                                    exe = os.path.join(install, f)
                                    break
                            results.append({
                                "name":        os.path.basename(install),
                                "path":        exe or install,
                                "install_dir": install,
                                "source":      "ubisoft",
                                "icon_path":   exe or "",
                                "cover_url":   "",
                            })
                    except Exception:
                        continue
        except FileNotFoundError:
            continue
        except Exception as e:
            log.error(f"game_scanner ubisoft: {e}")
    log.info(f"game_scanner: Ubisoft — {len(results)} игр")
    return results


# ==================== EA APP / ORIGIN ====================

def _scan_ea():
    results = []
    bases = [
        r"SOFTWARE\WOW6432Node\Electronic Arts\EA Games",
        r"SOFTWARE\Electronic Arts\EA Games",
    ]
    for base in bases:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(k, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(k, sub) as sk:
                            try:
                                install, _ = winreg.QueryValueEx(
                                    sk, "Install Dir"
                                )
                            except Exception:
                                continue
                            if not install or not os.path.isdir(install):
                                continue
                            results.append({
                                "name":        sub.replace("_", " "),
                                "path":        install,
                                "install_dir": install,
                                "source":      "ea",
                                "icon_path":   "",
                                "cover_url":   "",
                            })
                    except Exception:
                        continue
        except FileNotFoundError:
            continue
        except Exception as e:
            log.error(f"game_scanner ea: {e}")
    log.info(f"game_scanner: EA — {len(results)} игр")
    return results


# ==================== РЕЕСТР WINDOWS (GENERIC) ====================

# --- Шаг 1: жёсткий стоп-лист по имени (софт, лончеры, утилиты) ---
_SKIP_NAME_WORDS = (
    # Лончеры
    "launcher", "game center", "game centre", "игровой центр",
    "gaming center", "hub", "portal", "companion",
    # Установщики/редисты/фреймворки
    "installer", "setup", "update", "updater", "uninstaller",
    "redistributable", "redist", "runtime", "framework",
    "prerequisite", "pre-requisite", "sdk",
    # Драйверы/железо
    "driver", "chipset", "device software", "device driver",
    "control panel", "tray", "helper", "service",
    "intel", "nvidia", "geforce", "realtek", "amd ",
    "razer", "logitech", "corsair", "hyperx", "steelseries",
    "western digital", "wd ", "seagate", "samsung magician",
    "asus", "gigabyte", "gbt_", "gbt ", "msi ", "asrock",
    "moza", "keydominator", "simpro",
    # ОС/офис/браузеры
    "windows", "microsoft visual", "visual c++", "net framework",
    "office ", "edge ", "defender",
    "chrome", "firefox", "opera ", "vivaldi", "brave",
    # Медиа/стриминг
    "vlc", "obs ", "obs studio", "potplayer",
    # Софт-инструменты
    "autohotkey", "yandex", "winrar", "winzip", "7-zip",
    "pycharm", "jetbrains", "intellij", "webstorm", "clion",
    "vscode", "visual studio code", "sublime text",
    "hamachi", "logmein", "teamviewer", "anydesk",
    "rivatuner", "msi afterburner", "overwolf", "curseforge",
    "thunderstore", "mod manager",
    # Явные клиенты (не игры)
    "steam", "ea app", "origin", "uplay", "ubisoft connect",
    "gog galaxy", "battle.net", "epic games launcher",
    "vk play", "my.games", "mail.ru",
    "lesta game", "wargaming game center", "wgc",
    # Мессенджеры
    "telegram", "discord", "slack", "zoom", "skype",
    "whatsapp", "signal",
    # Прочие приложения
    "adobe", "photoshop", "illustrator", "figma", "blender",
    "audacity", "gimp", "inkscape", "krita",
    "python ", "python3", "java ", "node.js", "git ",
    "docker", "putty", "filezilla", "notepad++",
    "spotify", "itunes", "aimp",
    "bitdefender", "kaspersky", "avast", "avg ", "eset",
    "ccleaner", "advanced systemcare", "revo uninstaller",
    "onedrive", "microsoft edge", "microsoft onedrive",
    "jove", "mod pack", "modpack", "mod-pack",
)

# --- Шаг 2: издатели, которые точно НЕ делают игры ---
_SKIP_PUBLISHERS = (
    "intel corporation", "intel(r) corporation",
    "nvidia corporation", "advanced micro devices",
    "realtek semiconductor", "western digital", "seagate technology",
    "logitech", "razer usa", "corsair memory", "asustek computer",
    "micro-star international", "gigabyte technology",
    "google llc", "mozilla corporation", "oracle corporation",
    "samsung electronics", "vmware", "jetbrains", "python software",
    "autohotkey", "yandex", "logmein", "moza racing",
)

# --- Шаг 3: белый список известных игровых издателей ---
_KNOWN_GAME_PUBLISHERS = (
    "battlestate",              # Escape from Tarkov
    "wargaming", "lesta",       # Мир танков, World of Tanks
    "my.games", "my.com", "mail.ru", "vk play",
    "rockstar", "ubisoft", "electronic arts", "ea games",
    "activision", "blizzard", "bethesda", "cd projekt",
    "valve ", "valve corporation",
    "take-two", "2k games", "rockstar games",
    "square enix", "capcom", "konami", "sega", "bandai namco",
    "koei", "paradox interactive", "focus home", "deep silver",
    "thq nordic", "team17", "devolver digital", "annapurna",
    "playstation", "sony interactive", "xbox game studios",
    "nintendo", "tencent", "netease", "perfect world",
    "1c-softclub", "1c-s", "бука", "buka", "софтклаб", "softclub",
    "новый диск", "quest ", "гайдзин", "gaijin",
    "targem", "saber interactive", "bst ", "пиранья",
    "romero games", "asters", "offworld",
    "wf ", "wargaming.net", "лesta",
    "креатив", "crea team",
    "nival", "katauri", "1c ",
    # Издатели и локализации РФ/СНГ
    "леста", "lesta", "lesta studio", "lesta games",
    "wargaming group", "world of tanks",
    "мой мир", "мой.игры", "мой игровой",
    "vk games", "vkgames", "vk group",
    "crytek", "mail.ru group", "my.com b.v.", "mycom",
    "иннова", "innova",
    "бука", "buka entertainment",
    "софтклаб", "softclub",
)

# --- Шаг 4: игровые ключевые слова в имени ---
_GAME_KEYWORDS = (
    " game", "games", "игр", "quest", "shooter",
    "rpg", "adventure", "battle", "fantasy",
    " campaign", " chronicles", " saga",
    " chapter", " episode",
    # Явные названия игр из реестра
    "warface", "warfare", "tanks", "tank ",
    "танк", "войн", "combat", "strike",
    "arena", "frontline", "front line",
)

# --- Игры Microsoft, которые не должны попадать под стоп-фильтр ---
_MS_GAME_MARKERS = (
    "flight simulator", "forza", "halo", "age of empires",
    "minecraft", "sea of thieves", "gears of war", "gears 5",
    "state of decay", "ori and the", "quantum break",
    "sunset overdrive", "killer instinct", "flight sim",
)

_MIN_INSTALL_KB = 500_000   # 500 МБ
_MIN_EXE_BYTES = 5_000_000  # 5 МБ


# Папки внутри install_dir, которые не содержат главный exe игры
_EXE_SKIP_DIRS = (
    "mod", "mods", "jove", "unins", "redist", "vcredist",
    "cache", "logs", "log", "downloaded", "patch", "patches",
    "backup", "backups", "installer", "setup", "dx", "vcredist",
    "directx", "dotnet", "prerequisites", "toolkit",
)

# Фрагменты в имени exe, которые не подходят под «главный запускающий»
_EXE_SKIP_NAMES = (
    "unins", "redist", "vcredist", "setup", "install",
    "update", "updater", "crash", "report", "helper",
    "uninstall", "diagnostic", "dxsetup", "dotnetfx",
)


def _find_game_exe(install_dir, max_depth=2):
    """Ищет главный .exe игры в папке установки.

    Идёт на max_depth уровней вглубь, пропускает папки модов и редистов,
    выбирает самый большой .exe (>5 МБ).
    """
    if not install_dir or not os.path.isdir(install_dir):
        return None

    best = None
    best_size = 0

    def _walk(path, depth):
        nonlocal best, best_size
        if depth > max_depth:
            return
        try:
            entries = os.listdir(path)
        except Exception:
            return
        for f in entries:
            full = os.path.join(path, f)
            try:
                if os.path.isdir(full):
                    fl = f.lower()
                    if any(s in fl for s in _EXE_SKIP_DIRS):
                        continue
                    _walk(full, depth + 1)
                elif f.lower().endswith(".exe"):
                    fl = f.lower()
                    if any(s in fl for s in _EXE_SKIP_NAMES):
                        continue
                    size = os.path.getsize(full)
                    if size >= _MIN_EXE_BYTES and size > best_size:
                        best_size = size
                        best = full
            except Exception:
                continue

    _walk(install_dir, 0)
    return best


def _is_junk_by_name(name):
    n = (name or "").lower()
    if any(w in n for w in _SKIP_NAME_WORDS):
        return True
    # Всё, что от Microsoft, но не похоже на игру — в стоп
    if "microsoft" in n:
        return not any(m in n for m in _MS_GAME_MARKERS)
    return False


def _is_junk_publisher(publisher):
    p = (publisher or "").lower()
    if not p:
        return False
    if "microsoft" in p and ("studio" in p or "game" in p):
        return False  # Microsoft Studios / Microsoft Game Studios
    return any(w in p for w in _SKIP_PUBLISHERS)


def _has_game_keyword(name):
    n = (name or "").lower()
    return any(w in n for w in _GAME_KEYWORDS)


def _has_known_game_publisher(publisher):
    p = (publisher or "").lower()
    if not p:
        return False
    return any(w in p for w in _KNOWN_GAME_PUBLISHERS)


def _scan_registry_games():
    """Строгий сканер Uninstall-ключей — только реальные игры."""
    results = []
    bases = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hive, base in bases:
        try:
            with winreg.OpenKey(hive, base) as k:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(k, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(k, sub) as sk:
                            def _get(n, d=""):
                                try:
                                    v, _ = winreg.QueryValueEx(sk, n)
                                    return v
                                except Exception:
                                    return d

                            name = _get("DisplayName")
                            if not name:
                                continue

                            # --- Жёсткие фильтры реестра ---
                            if _get("SystemComponent", 0) == 1:
                                continue
                            if _get("NoDisplay", 0) == 1:
                                continue
                            if _get("ParentKeyName", ""):
                                continue
                            release = _get("ReleaseType", "").lower()
                            if release in ("update", "hotfix",
                                           "security update", "servicepack"):
                                continue

                            if _is_junk_by_name(name):
                                continue

                            publisher = _get("Publisher", "")
                            if _is_junk_publisher(publisher):
                                continue

                            install = _get("InstallLocation", "") or ""
                            icon = _get("DisplayIcon", "") or ""
                            if icon:
                                icon = icon.split(",")[0].strip('"')

                            if not install and not icon:
                                continue

                            try:
                                size_kb = int(_get("EstimatedSize", 0))
                            except Exception:
                                size_kb = 0

                            # --- Логика «это игра?» ---
                            is_publisher_game = _has_known_game_publisher(
                                publisher
                            )
                            is_keyword_game = _has_game_keyword(name)
                            is_big = size_kb >= _MIN_INSTALL_KB

                            if not (is_publisher_game
                                    or is_keyword_game
                                    or is_big):
                                continue

                            # Ищем исполняемый файл
                            exe = None

                            # 1) DisplayIcon может быть .exe
                            #    (но не uninstaller)
                            if icon and icon.lower().endswith(".exe") \
                                    and os.path.isfile(icon):
                                fl = os.path.basename(icon).lower()
                                if not any(s in fl for s in _EXE_SKIP_NAMES):
                                    exe = icon

                            # 2) Рекурсивный поиск в install_dir
                            if not exe and install and os.path.isdir(install):
                                exe = _find_game_exe(install, max_depth=2)

                            if not exe:
                                continue

                            results.append({
                                "name":        name,
                                "path":        exe,
                                "install_dir": install,
                                "source":      "registry",
                                "icon_path":   icon,
                                "cover_url":   "",
                            })
                    except Exception:
                        continue
        except FileNotFoundError:
            continue
        except Exception as e:
            log.error(f"game_scanner registry: {e}")

    log.info(f"game_scanner: Реестр — {len(results)} игр")
    return results


# ==================== ОБЪЕДИНЕНИЕ ====================

def _dedupe(items):
    """Убирает дубли по имени (без учёта регистра) + пути."""
    seen_names = set()
    seen_paths = set()
    result = []
    for it in items:
        name_key = (it.get("name") or "").strip().lower()
        path_key = (it.get("path") or "").strip().lower()
        if not name_key:
            continue
        if name_key in seen_names:
            continue
        if path_key and path_key in seen_paths:
            continue
        seen_names.add(name_key)
        if path_key:
            seen_paths.add(path_key)
        result.append(it)
    return result


def scan_all_sources():
    """Сканирует все источники. Возвращает список уникальных игр."""
    scanners = [
        ("Steam",       _scan_steam),
        ("Epic",        _scan_epic),
        ("GOG",         _scan_gog),
        ("Battle.net",  _scan_battlenet),
        ("Ubisoft",     _scan_ubisoft),
        ("EA",          _scan_ea),
        ("Registry",    _scan_registry_games),
    ]

    all_games = []
    for label, fn in scanners:
        try:
            all_games.extend(fn())
        except Exception as e:
            log.error(f"game_scanner {label}: {e}")

    priority_order = {
        "steam": 0, "epic": 1, "gog": 2,
        "battlenet": 3, "ubisoft": 4, "ea": 5, "registry": 6,
    }
    all_games.sort(key=lambda g: (
        priority_order.get(g.get("source", ""), 99),
        g.get("name", "").lower(),
    ))

    all_games = _dedupe(all_games)
    log.info(f"game_scanner: всего уникальных игр — {len(all_games)}")
    return all_games


# ==================== КЭШ ====================

def load_cache():
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        ts = data.get("timestamp", 0)
        if time.time() - ts > CACHE_TTL_SECONDS:
            return None
        return data.get("games", [])
    except Exception as e:
        log.error(f"game_scanner load_cache: {e}")
        return None


def save_cache(games):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {"timestamp": time.time(), "games": games},
                f, ensure_ascii=False, indent=2,
            )
    except Exception as e:
        log.error(f"game_scanner save_cache: {e}")


def get_games(force_rescan=False):
    if not force_rescan:
        cached = load_cache()
        if cached is not None:
            log.info(f"game_scanner: из кэша — {len(cached)} игр")
            return cached

    games = scan_all_sources()
    save_cache(games)
    return games


def clear_cache():
    try:
        if os.path.exists(CACHE_PATH):
            os.remove(CACHE_PATH)
        log.info("game_scanner: кэш игр очищен")
        return True
    except Exception as e:
        log.error(f"game_scanner clear_cache: {e}")
        return False


# ==================== ОБЛОЖКИ STEAM STORE API ====================

def _cover_cache_path(appid, suffix="jpg"):
    _ensure_covers_dir()
    return os.path.join(COVERS_DIR, f"{appid}.{suffix}")


def get_steam_cover_local(appid):
    if not appid:
        return ""
    for ext in ("jpg", "png", "webp"):
        p = _cover_cache_path(appid, ext)
        if os.path.exists(p):
            return p
    return ""


def download_steam_cover(appid, timeout=6):
    if not appid:
        return ""
    existing = get_steam_cover_local(appid)
    if existing:
        return existing

    url = (
        f"https://cdn.cloudflare.steamstatic.com/"
        f"steam/apps/{appid}/header.jpg"
    )
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "MyLauncher/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data or len(data) < 500:
            return ""
        path = _cover_cache_path(appid, "jpg")
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        log.error(f"game_scanner download cover {appid}: {e}")
        return ""


def get_cover_for_game(game):
    if not game:
        return ""
    src = game.get("source")
    appid = game.get("appid", "")

    if src == "steam" and appid:
        local = get_steam_cover_local(appid)
        if local:
            return local

    install = game.get("install_dir", "")
    if install and os.path.isdir(install):
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            for name in ("cover", "header", "capsule", "banner", "poster"):
                p = os.path.join(install, name + ext)
                if os.path.exists(p):
                    return p

    return ""


def download_all_steam_covers(games, only_missing=True, timeout=6):
    n = 0
    for g in games:
        if g.get("source") != "steam":
            continue
        appid = g.get("appid")
        if not appid:
            continue
        if only_missing and get_steam_cover_local(appid):
            continue
        if download_steam_cover(appid, timeout=timeout):
            n += 1
    log.info(f"game_scanner: скачано обложек — {n}")
    return n