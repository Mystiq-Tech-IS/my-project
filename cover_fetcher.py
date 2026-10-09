"""Подтягивание обложек игр из интернета через SteamGridDB.

SteamGridDB — бесплатный сервис с тысячами обложек игр. Требует
API-ключ (регистрация через Steam, бесплатно).

Как получить ключ:
  1. Зайди на https://www.steamgriddb.com
  2. Войди через Steam.
  3. Открой Preferences → API.
  4. Нажми Generate Key.
  5. Скопируй ключ и вставь в Настройки → Данные → SteamGridDB API Key.

Поиск толерантен к неточностям: убирает ™ ® (RUS) Launcher Edition,
пробует несколько вариантов имени, сравнивает найденные названия
через SequenceMatcher и берёт лучший результат. ID игры кэшируется
в sgdb_cache.json, URL-ы обложек — в sgdb_url_cache.json.
"""

import os
import re
import json
import difflib
import urllib.request
import urllib.parse

from config import BASE_DIR

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")


API_BASE = "https://www.steamgriddb.com/api/v2"
COVERS_DIR = os.path.join(BASE_DIR, ".game_covers")
CACHE_PATH = os.path.join(BASE_DIR, "sgdb_cache.json")
URL_CACHE_PATH = os.path.join(BASE_DIR, "sgdb_url_cache.json")


# ==================== ИЗВЕСТНЫЕ АЛИАСЫ ====================

_KNOWN_ALIASES = {
    "мир танков":        "World of Tanks",
    "танки":             "World of Tanks",
    "world of tanks":    "World of Tanks",

    "мир кораблей":      "World of Warships",
    "world of warships": "World of Warships",

    "мир самолётов":     "World of Warplanes",
    "мир самолетов":     "World of Warplanes",

    "варфейс":           "Warface",
    "warface клинч":     "Warface: Clutch",
    "warface clutch":    "Warface: Clutch",

    "побег из таркова":  "Escape from Tarkov",
    "escape from tarkov arena": "Escape from Tarkov",

    "танки онлайн":      "Tanki Online",
    "tanki":             "Tanki Online",

    "калибр":            "Caliber",
}


# ==================== КЭШ ID ====================

_cache = None
_cache_dirty = False


def _load_cache():
    global _cache, _cache_dirty
    if _cache is not None:
        return _cache
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                _cache = data if isinstance(data, dict) else {}
        else:
            _cache = {}
    except Exception as e:
        log.error(f"cover_fetcher load_cache: {e}")
        _cache = {}
    _cache_dirty = False
    return _cache


def _save_cache():
    global _cache_dirty
    if not _cache_dirty:
        return
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
        _cache_dirty = False
    except Exception as e:
        log.error(f"cover_fetcher save_cache: {e}")


def clear_id_cache():
    """Удаляет sgdb_cache.json и все скачанные обложки SteamGridDB."""
    global _cache, _cache_dirty
    _cache = {}
    _cache_dirty = False
    try:
        if os.path.exists(CACHE_PATH):
            os.remove(CACHE_PATH)
    except Exception as e:
        log.error(f"cover_fetcher clear_id_cache file: {e}")

    try:
        if os.path.isdir(COVERS_DIR):
            for f in os.listdir(COVERS_DIR):
                if f.startswith("sgdb_"):
                    try:
                        os.remove(os.path.join(COVERS_DIR, f))
                    except Exception:
                        pass
    except Exception as e:
        log.error(f"cover_fetcher clear_id_cache covers: {e}")

    log.info("cover_fetcher: кэш ID и обложки очищены")


# ==================== КЭШ URL-ОВ ОБЛОЖЕК ====================

_url_cache = None
_url_cache_dirty = False


def _load_url_cache():
    global _url_cache, _url_cache_dirty
    if _url_cache is not None:
        return _url_cache
    try:
        if os.path.exists(URL_CACHE_PATH):
            with open(URL_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                _url_cache = data if isinstance(data, dict) else {}
        else:
            _url_cache = {}
    except Exception as e:
        log.error(f"cover_fetcher _load_url_cache: {e}")
        _url_cache = {}
    _url_cache_dirty = False
    return _url_cache


def _save_url_cache():
    global _url_cache_dirty
    if not _url_cache_dirty or _url_cache is None:
        return
    try:
        with open(URL_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_url_cache, f, ensure_ascii=False, indent=2)
        _url_cache_dirty = False
    except Exception as e:
        log.error(f"cover_fetcher _save_url_cache: {e}")


def get_url_cache_for_game(game):
    """Возвращает закэшированный URL обложки или ''."""
    if not game:
        return ""
    cache = _load_url_cache()
    if game.get("source") == "steam" and game.get("appid"):
        key = f"steam:{game['appid']}"
        if key in cache:
            return cache[key]
    name = game.get("name") or ""
    norm = _normalize_name(name)
    if norm and norm in cache:
        return cache[norm]
    return ""


def cache_url_for_game(game, url):
    """Сохраняет URL обложки в кэш."""
    global _url_cache_dirty
    if not url or not game:
        return
    cache = _load_url_cache()
    if game.get("source") == "steam" and game.get("appid"):
        cache[f"steam:{game['appid']}"] = url
    name = game.get("name") or ""
    norm = _normalize_name(name)
    if norm:
        cache[norm] = url
    _url_cache_dirty = True
    _save_url_cache()


def clear_url_cache():
    """Полностью очищает кэш URL-ов."""
    global _url_cache, _url_cache_dirty
    _url_cache = {}
    _url_cache_dirty = False
    try:
        if os.path.exists(URL_CACHE_PATH):
            os.remove(URL_CACHE_PATH)
    except Exception as e:
        log.error(f"cover_fetcher clear_url_cache: {e}")


# ==================== ОБЩЕЕ ====================

def is_available():
    return True


def _ensure_covers_dir():
    try:
        os.makedirs(COVERS_DIR, exist_ok=True)
    except Exception:
        pass


def _api_get(url, api_key, timeout=8):
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "MyLauncher/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8", errors="ignore")
        return json.loads(data)
    except Exception as e:
        log.error(f"cover_fetcher API: {url} — {e}")
        return None


# ==================== НОРМАЛИЗАЦИЯ ====================

_NOISE_SUFFIXES = (
    " launcher", " steam", " edition", " remaster", " remastered",
    " definitive", " complete", " ultimate", " deluxe", " gold",
    " enhanced", " classic", " goty", " game of the year",
    " special edition", " collectors", " collector's",
    " (rus)", " [rus]", " (ru)", " [ru]",
    " (eng)", " [eng]", " (en)", " [en]",
    " pc", " windows", " win",
)

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


def _translify(name):
    return "".join(_TRANSLIT.get(ch.lower(), ch) for ch in name)


def _normalize_name(name):
    if not name:
        return ""
    s = name
    for ch in ("™", "®", "©", "℠"):
        s = s.replace(ch, "")
    s = re.sub(r"[\(\[\{]\s*(19|20)\d{2}\s*[\)\]\}]", " ", s)
    s = re.sub(r"[\(\[\{][^\)\]\}]{0,20}[\)\]\}]", " ", s)
    low = s.lower()
    for w in _NOISE_SUFFIXES:
        if low.endswith(w):
            s = s[: -len(w)]
            low = s.lower()
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"[^\w\s:']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


def _name_variants(name):
    """Список вариантов имени для поиска (в порядке приоритета)."""
    variants = []
    seen = set()

    def _add(v):
        v = (v or "").strip()
        if not v or v.lower() in seen:
            return
        seen.add(v.lower())
        variants.append(v)

    norm = _normalize_name(name)

    if norm and norm in _KNOWN_ALIASES:
        _add(_KNOWN_ALIASES[norm])

    _add(name)
    _add(norm)

    if ":" in (name or ""):
        base = name.split(":", 1)[0].strip()
        _add(base)
        _add(_normalize_name(base))

    if norm and any(ch in norm for ch in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"):
        tr = _translify(norm)
        _add(tr)
        _add(re.sub(r"\bthe\b", "", tr).strip())

    return variants


# ==================== MATCHING ====================

def _similarity(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _score_candidate(query_norm, candidate_name):
    c_norm = _normalize_name(candidate_name)
    if not c_norm or not query_norm:
        return 0.0
    if c_norm == query_norm:
        return 1.0
    if query_norm in c_norm or c_norm in query_norm:
        ratio_len = min(len(query_norm), len(c_norm)) / max(
            len(query_norm), len(c_norm)
        )
        return 0.75 + 0.25 * ratio_len
    return _similarity(query_norm, c_norm)


# ==================== ПОИСК ====================

def _search_once(query, api_key, timeout=8):
    try:
        q = urllib.parse.quote(query)
        url = f"{API_BASE}/search/autocomplete/{q}"
        data = _api_get(url, api_key, timeout=timeout)
        if not data or not data.get("success"):
            return []
        return data.get("data") or []
    except Exception as e:
        log.error(f"cover_fetcher _search_once: {e}")
        return []


def search_game(name, api_key, timeout=8):
    """Ищет игру. Возвращает {'id': ..., 'name': ...} или None."""
    if not name or not api_key:
        return None

    norm = _normalize_name(name)
    has_alias = norm in _KNOWN_ALIASES

    if not has_alias:
        cache = _load_cache()
        if norm in cache:
            return {"id": cache[norm], "name": name, "_from_cache": True}

    variants = _name_variants(name)
    log.info(f"cover_fetcher: ищем «{name}» — варианты: {variants}")

    best = None
    best_score = 0.0
    best_query = ""

    for q in variants:
        results = _search_once(q, api_key, timeout=timeout)
        if not results:
            continue
        q_norm = _normalize_name(q)
        for item in results:
            cand = item.get("name", "")
            score = _score_candidate(q_norm, cand)
            if score > best_score:
                best_score = score
                best = item
                best_query = q

    if best is None or best_score < 0.55:
        if best is not None:
            log.info(
                f"cover_fetcher: «{name}» → слабый матч "
                f"({best_score:.2f} «{best.get('name')}») — пропуск"
            )
        else:
            log.info(f"cover_fetcher: «{name}» не найдено")
        return None

    if best.get("id") and not has_alias:
        cache = _load_cache()
        cache[norm] = best["id"]
        global _cache_dirty
        _cache_dirty = True
        _save_cache()

    log.info(
        f"cover_fetcher: «{name}» → «{best.get('name')}» "
        f"(score={best_score:.2f}, запрос='{best_query}')"
    )
    return best


# ==================== URL ОБЛОЖЕК ====================

def _sort_grids_by_quality(grids):
    def key(g):
        upvotes = int(g.get("upvotes", 0) or 0)
        score = int(g.get("score", 0) or 0)
        downloads = int(g.get("downloads", 0) or 0)
        alt_penalty = -1 if g.get("alt") else 0
        return (upvotes, score, downloads, alt_penalty)
    try:
        return sorted(grids, key=key, reverse=True)
    except Exception:
        return grids


def _get_grids(game_id, api_key, timeout=8):
    try:
        url = (f"{API_BASE}/grids/game/{game_id}"
               f"?dimensions=460x215,920x430&mimes=image/jpeg,image/png")
        data = _api_get(url, api_key, timeout=timeout)
        if data and data.get("success"):
            grids = data.get("data") or []
            if grids:
                return _sort_grids_by_quality(grids)
        url2 = f"{API_BASE}/grids/game/{game_id}"
        data = _api_get(url2, api_key, timeout=timeout)
        if data and data.get("success"):
            return _sort_grids_by_quality(data.get("data") or [])
        return []
    except Exception as e:
        log.error(f"cover_fetcher _get_grids: {e}")
        return []


def _get_heroes(game_id, api_key, timeout=8):
    try:
        url = f"{API_BASE}/heroes/game/{game_id}"
        data = _api_get(url, api_key, timeout=timeout)
        if not data or not data.get("success"):
            return []
        return _sort_grids_by_quality(data.get("data") or [])
    except Exception as e:
        log.error(f"cover_fetcher _get_heroes: {e}")
        return []


def get_cover_url_by_game_id(game_id, api_key, timeout=8):
    """Возвращает (url, kind). kind: 'grid' | 'hero' | ''."""
    if not game_id or not api_key:
        return "", ""

    grids = _get_grids(game_id, api_key, timeout)
    if grids:
        return grids[0].get("url", ""), "grid"

    heroes = _get_heroes(game_id, api_key, timeout)
    if heroes:
        return heroes[0].get("url", ""), "hero"

    return "", ""


def get_cover_url_by_steam_appid(steam_appid, api_key, timeout=8):
    if not steam_appid or not api_key:
        return "", ""
    try:
        url = f"{API_BASE}/games/steam/{steam_appid}"
        data = _api_get(url, api_key, timeout=timeout)
        if not data or not data.get("success"):
            return "", ""
        game = data.get("data")
        if not game:
            return "", ""
        return get_cover_url_by_game_id(game.get("id"), api_key, timeout)
    except Exception as e:
        log.error(f"cover_fetcher steam_appid: {e}")
        return "", ""


# ==================== ФАЙЛЫ ====================

def _safe_filename(name):
    safe = "".join(
        c if c.isalnum() or c in "._- " else "_"
        for c in (name or "cover")
    )
    return safe.strip()[:80] or "cover"


def _cover_path_for_name(name, suffix=""):
    base = _safe_filename(_normalize_name(name) or name)
    if suffix:
        return os.path.join(COVERS_DIR, f"sgdb_{suffix}_{base}.jpg")
    return os.path.join(COVERS_DIR, f"sgdb_{base}.jpg")


def download_cover(url, save_path, timeout=10):
    if not url:
        return False
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "MyLauncher/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data or len(data) < 500:
            return False
        _ensure_covers_dir()
        with open(save_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        log.error(f"cover_fetcher download: {e}")
        return False


# ==================== ВЫСОКОУРОВНЕВЫЕ ====================

def fetch_cover_by_name(name, api_key, force=False):
    if not name or not api_key:
        return ""
    try:
        save_path = _cover_path_for_name(name)
        if not force and os.path.exists(save_path) \
                and os.path.getsize(save_path) > 500:
            return save_path

        game = search_game(name, api_key)
        if not game:
            return ""
        url, kind = get_cover_url_by_game_id(game.get("id"), api_key)
        if not url:
            log.info(f"cover_fetcher: «{name}» — нет ни grid, ни hero")
            return ""
        if download_cover(url, save_path):
            log.info(
                f"cover_fetcher: обложка для «{name}» сохранена "
                f"(источник: {kind})"
            )
            cache_url_for_game({"name": name}, url)
            return save_path
        return ""
    except Exception as e:
        log.error(f"cover_fetcher fetch_by_name: {e}")
        return ""


def fetch_cover_by_steam_appid(steam_appid, name_hint, api_key, force=False):
    if not api_key:
        return ""
    if steam_appid:
        try:
            save_path = os.path.join(
                COVERS_DIR, f"sgdb_steam_{steam_appid}.jpg"
            )
            if not force and os.path.exists(save_path) \
                    and os.path.getsize(save_path) > 500:
                return save_path
            url, kind = get_cover_url_by_steam_appid(steam_appid, api_key)
            if url and download_cover(url, save_path):
                log.info(
                    f"cover_fetcher: обложка Steam appid={steam_appid} "
                    f"сохранена (источник: {kind})"
                )
                cache_url_for_game(
                    {"source": "steam", "appid": steam_appid,
                     "name": name_hint or ""},
                    url,
                )
                return save_path
        except Exception as e:
            log.error(f"cover_fetcher fetch_by_steam_appid: {e}")

    if name_hint:
        return fetch_cover_by_name(name_hint, api_key, force=force)
    return ""


def fetch_cover_url_by_name(name, api_key):
    """Ищет URL обложки в SteamGridDB, НЕ скачивая её."""
    if not name or not api_key:
        return ""
    try:
        game = search_game(name, api_key)
        if not game:
            return ""
        url, _kind = get_cover_url_by_game_id(game.get("id"), api_key)
        return url or ""
    except Exception as e:
        log.error(f"cover_fetcher fetch_cover_url_by_name: {e}")
        return ""


def fetch_cover_url_by_steam_appid(steam_appid, api_key):
    """URL обложки для Steam-игры."""
    if not steam_appid or not api_key:
        return ""
    try:
        url, _kind = get_cover_url_by_steam_appid(steam_appid, api_key)
        return url or ""
    except Exception as e:
        log.error(f"cover_fetcher fetch_cover_url_by_steam_appid: {e}")
        return ""


def get_discord_cover_url(game, api_key=""):
    """Возвращает URL обложки для Discord RPC.

    1) Если Steam — сразу URL CDN (без сети).
    2) Иначе — из URL-кэша.
    3) Иначе, если api_key дан — запрашивает SteamGridDB (без скачивания)
       и кэширует.
    """
    if not game:
        return ""

    # 1) Steam CDN — моментально
    if game.get("source") == "steam" and game.get("appid"):
        return (
            f"https://cdn.cloudflare.steamstatic.com/"
            f"steam/apps/{game['appid']}/header.jpg"
        )

    # 2) Из URL-кэша
    cached = get_url_cache_for_game(game)
    if cached:
        return cached

    # 3) Запрос к SteamGridDB
    if api_key:
        url = fetch_cover_url_by_name(game.get("name", ""), api_key)
        if url:
            cache_url_for_game(game, url)
            return url

    return ""


def find_local_cover_for_game(game):
    """Ищет уже скачанную обложку SteamGridDB для игры."""
    try:
        if game.get("source") == "steam" and game.get("appid"):
            p = os.path.join(COVERS_DIR, f"sgdb_steam_{game['appid']}.jpg")
            if os.path.exists(p) and os.path.getsize(p) > 500:
                return p

        name = game.get("name") or ""
        for variant in _name_variants(name):
            p = _cover_path_for_name(variant)
            if os.path.exists(p) and os.path.getsize(p) > 500:
                return p

        p = _cover_path_for_name(name)
        if os.path.exists(p) and os.path.getsize(p) > 500:
            return p
    except Exception:
        pass
    return ""