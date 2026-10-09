"""Диагностика: что возвращает SteamGridDB по именам игр.

Показывает все совпадения для каждой игры и итоговый выбор.
Запуск: python test_sgdb.py
"""
import sys
from storage import load_settings
import cover_fetcher

settings = load_settings()
api_key = (settings.get("steamgriddb_api_key") or "").strip()

if not api_key:
    print("STEAMGRIDDB_API_KEY не задан в настройках лаунчера.")
    print("Настройки → Данные → SteamGridDB API Key")
    sys.exit(1)

print(f"API key: {api_key[:8]}...{api_key[-4:]}")
print()

# Список твоих игр из последнего скриншота
games = [
    "Broken Arrow",
    "Supreme Commander 2",
    "Valheim",
    "Escape from Tarkov",
    "Escape from Tarkov: Arena",
    "Warface",
    "Мир танков",
    "World of Tanks",
]

for name in games:
    print("=" * 70)
    print(f"Игра: {name}")
    variants = cover_fetcher._name_variants(name)
    print(f"  Варианты поиска: {variants}")

    # Сырые результаты по первому варианту
    results = cover_fetcher._search_once(name, api_key)
    print(f"  Сырых результатов: {len(results)}")
    for r in results[:5]:
        print(f"    id={r.get('id')}  name='{r.get('name')}'")

    # Итоговый выбор
    best = cover_fetcher.search_game(name, api_key)
    if best:
        print(f"  ✓ ВЫБРАНО: id={best.get('id')} name='{best.get('name')}'")
        url = cover_fetcher.get_cover_url_by_game_id(best.get("id"), api_key)
        print(f"  URL обложки: {url[:80] if url else '(нет)'}")
    else:
        print(f"  ✗ НЕ НАЙДЕНО (score < 0.55)")
    print()