"""Одноразовый тест сканера игр. Можно удалить после проверки."""
from game_scanner import get_games

games = get_games(force_rescan=True)
print()
print(f"=== Найдено игр: {len(games)} ===")
print()

for g in games[:30]:
    src = g.get("source", "?")
    name = g.get("name", "?")
    print(f"  [{src:10}]  {name}")

if len(games) > 30:
    print(f"  ... и ещё {len(games) - 30}")