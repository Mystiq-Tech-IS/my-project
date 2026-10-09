"""Генерирует icon.ico для PyInstaller — буква на акцентном фоне.

Запуск:
    python make_icon.py

В корне появится icon.ico с размерами 16…256 px.
"""

from PIL import Image, ImageDraw, ImageFont


# ==================== НАСТРОЙКИ ====================
LETTER = "Л"                       # первая буква названия лаунчера
BG_COLOR = (137, 180, 250, 255)    # ACCENT (голубой, как в теме)
FG_COLOR = (22, 22, 30, 255)       # BG (тёмный, контрастный)
CORNER_RADIUS = 0.22               # скругление квадрата (доля от размера)
# ===================================================


def _find_font(size):
    """Ищет жирный системный шрифт с поддержкой кириллицы."""
    for path in (
        r"C:\Windows\Fonts\segoeuib.ttf",   # Segoe UI Bold
        r"C:\Windows\Fonts\arialbd.ttf",    # Arial Bold
        r"C:\Windows\Fonts\segoeui.ttf",    # Segoe UI
        r"C:\Windows\Fonts\arial.ttf",      # Arial
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_icon(size=512):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Скруглённый фон
    r = int(size * CORNER_RADIUS)
    draw.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=r,
        fill=BG_COLOR,
    )

    # Буква по центру
    font = _find_font(int(size * 0.62))
    bbox = draw.textbbox((0, 0), LETTER, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), LETTER, fill=FG_COLOR, font=font)

    return img


def main():
    base = make_icon(512)
    base.save(
        "icon.ico",
        format="ICO",
        sizes=[
            (16, 16), (24, 24), (32, 32), (48, 48),
            (64, 64), (128, 128), (256, 256),
        ],
    )
    print("icon.ico создан — размеры: 16, 24, 32, 48, 64, 128, 256")


if __name__ == "__main__":
    main()