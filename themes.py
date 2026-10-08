"""Тёмная и светлая темы + пресеты акцентных цветов + кастомный HEX-акцент."""

DARK = {
    "BG":         "#16161E",
    "BG_ALT":     "#1C1C26",
    "CARD":       "#22222E",
    "CARD_HOVER": "#2E2E3E",
    "BORDER":     "#2A2A38",
    "BORDER_HOV": "#3A3A50",
    "TEXT":       "#E5E5F0",
    "SUBTEXT":    "#9090A8",
    "ACCENT":     "#89B4FA",
    "ACCENT_HOV": "#A6C8FF",
    "DANGER":     "#F38BA8",
    "OK":         "#A6E3A1",
    "OK_DIM":     "#4F8F4A",
}

LIGHT = {
    "BG":         "#F5F5FA",
    "BG_ALT":     "#EDEDF4",
    "CARD":       "#FFFFFF",
    "CARD_HOVER": "#F0F0F8",
    "BORDER":     "#E0E0EC",
    "BORDER_HOV": "#C8C8DC",
    "TEXT":       "#1E1E2E",
    "SUBTEXT":    "#6C6F85",
    "ACCENT":     "#1E66F5",
    "ACCENT_HOV": "#4A7FFF",
    "DANGER":     "#D20F39",
    "OK":         "#40A02B",
    "OK_DIM":     "#A0D096",
}

THEMES = {"dark": DARK, "light": LIGHT}

ACCENTS = {
    "blue":   ("#89B4FA", "#A6C8FF"),
    "pink":   ("#F5C2E7", "#F8D5F0"),
    "green":  ("#A6E3A1", "#C1EDBD"),
    "orange": ("#FAB387", "#FCD0A8"),
    "purple": ("#CBA6F7", "#DCC2FA"),
    "red":    ("#F38BA8", "#F8A5BC"),
}

ACCENT_LABELS = {
    "blue":   "Голубой",
    "pink":   "Розовый",
    "green":  "Зелёный",
    "orange": "Оранжевый",
    "purple": "Фиолетовый",
    "red":    "Красный",
}


def hex_to_rgba(hex_color: str, alpha: int = 60) -> str:
    """Преобразует #RRGGBB в rgba(r,g,b,a) для QSS."""
    h = normalize_hex(hex_color).lstrip("#")
    if len(h) != 6:
        return f"rgba(0, 0, 0, {alpha})"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def normalize_hex(color_str: str) -> str:
    """Приводит #abc, #AABBCC, AABBCC к #AABBCC (или '' если не HEX)."""
    if not color_str or not isinstance(color_str, str):
        return ""
    s = color_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return ""
    if not all(c in "0123456789abcdefABCDEF" for c in s):
        return ""
    return "#" + s.upper()


def is_hex(color_str: str) -> bool:
    return bool(normalize_hex(color_str))


def lighten(hex_color: str, amount: float = 0.18) -> str:
    """Осветляет HEX на указанную долю."""
    h = normalize_hex(hex_color).lstrip("#")
    if len(h) != 6:
        return hex_color
    r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02X}{g:02X}{b:02X}"


def darken(hex_color: str, amount: float = 0.18) -> str:
    """Затемняет HEX на указанную долю."""
    h = normalize_hex(hex_color).lstrip("#")
    if len(h) != 6:
        return hex_color
    r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return f"#{r:02X}{g:02X}{b:02X}"


def get_theme(name, accent="blue"):
    """Возвращает цвета темы.

    accent — либо ключ из ACCENTS (blue/pink/...), либо HEX (#RRGGBB).
    Для кастомного HEX автоматически строится HOV (светлее для тёмной темы,
    темнее для светлой) и производные с прозрачностью.
    """
    theme = dict(THEMES.get(name, DARK))
    is_dark_theme = (name != "light")

    # --- Пресет ---
    if accent in ACCENTS:
        a, ah = ACCENTS[accent]
        theme["ACCENT"] = a
        theme["ACCENT_HOV"] = ah

    # --- Кастомный HEX ---
    elif is_hex(accent):
        base = normalize_hex(accent)
        theme["ACCENT"] = base
        # В тёмной теме ховер — светлее, в светлой — темнее
        theme["ACCENT_HOV"] = (
            lighten(base, 0.20) if is_dark_theme else darken(base, 0.15)
        )

    # --- Иначе — дефолт из темы (уже установлен) ---

    # Производные с прозрачностью
    theme["ACCENT_GLOW"]  = hex_to_rgba(theme["ACCENT"], 100)
    theme["ACCENT_SOFT"]  = hex_to_rgba(theme["ACCENT"], 35)
    theme["OK_GLOW"]      = hex_to_rgba(theme["OK"], 100)
    theme["OK_SOFT"]      = hex_to_rgba(theme["OK"], 40)
    theme["DANGER_SOFT"]  = hex_to_rgba(theme["DANGER"], 40)

    return theme