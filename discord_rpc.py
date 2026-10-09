"""Discord Rich Presence для MyLauncher.

Показывает в профиле Discord: какую программу/игру ты запустил, сколько
времени сессия идёт, и обложку игры (если доступна).

Как включить:
  1. Зайди на https://discord.com/developers/applications
  2. Создай New Application → назови как угодно (например, MyLauncher).
  3. Скопируй Application ID — это и есть client_id.
  4. (Опционально) Вкладка Rich Presence → Art Assets: загрузи
     изображение и назови ассет "logo".
  5. Вставь client_id в Настройки → Поведение → Discord Rich Presence.
  6. Включи галочку.

Обложки игр:
  • Steam → передаём URL с CDN Steam (работает без настройки).
  • Другие игры → URL из SteamGridDB, если API-ключ задан.
  • Если URL нет → показывается общий large_image из настроек.
"""

import time
import threading
from datetime import datetime

try:
    from pypresence import Presence
    from pypresence.exceptions import DiscordNotFound, InvalidID, PipeClosed
    HAS_PYPRESENCE = True
except ImportError:
    HAS_PYPRESENCE = False
    Presence = None
    class DiscordNotFound(Exception): pass
    class InvalidID(Exception): pass
    class PipeClosed(Exception): pass

from config import APP_NAME, GITHUB_REPO_URL

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")


class DiscordRPC:
    def __init__(self, settings):
        self.settings = settings or {}
        self._rpc = None
        self._enabled = bool(self.settings.get("discord_enabled", False))
        self._client_id = (self.settings.get("discord_client_id") or "").strip()
        self._large_image = (
            self.settings.get("discord_large_image") or "logo"
        ).strip()
        self._large_text = (
            self.settings.get("discord_large_text") or APP_NAME
        ).strip()
        self._show_when_idle = bool(
            self.settings.get("discord_show_when_idle", True)
        )

        self._lock = threading.Lock()
        self._connected = False
        self._current_session = None
        self._idle_since = time.time()

    # ================== СТАТУС ==================

    def is_available(self):
        return HAS_PYPRESENCE

    def is_connected(self):
        return self._connected

    def is_enabled(self):
        return self._enabled

    # ================== ЖИЗНЕННЫЙ ЦИКЛ ==================

    def start(self):
        if not HAS_PYPRESENCE:
            log.info("discord_rpc: pypresence не установлен")
            return False
        if not self._enabled:
            return False
        if not self._client_id:
            log.warning("discord_rpc: не указан client_id")
            return False
        if self._connected:
            return True

        # Подключаемся в фоне, чтобы не вешать UI
        try:
            import threading
            t = threading.Thread(
                target=self._connect_thread, daemon=True, name="DiscordRPC-Connect"
            )
            t.start()
            return True
        except Exception as e:
            log.error(f"discord_rpc start thread: {e}")
            return False

    def _connect_thread(self):
        try:
            with self._lock:
                self._rpc = Presence(self._client_id)
                self._rpc.connect()
                self._connected = True
            log.info(f"discord_rpc: подключён (client_id={self._client_id})")
            if self._show_when_idle:
                self._update_idle()
        except InvalidID:
            log.error("discord_rpc: неверный client_id")
            self._connected = False
        except DiscordNotFound:
            log.warning("discord_rpc: Discord не запущен")
            self._connected = False
        except Exception as e:
            log.error(f"discord_rpc start: {e}")
            self._connected = False
    def stop(self):
        if not self._connected or self._rpc is None:
            self._connected = False
            return
        try:
            with self._lock:
                try:
                    self._rpc.clear()
                except Exception:
                    pass
                try:
                    self._rpc.close()
                except Exception:
                    pass
                self._rpc = None
                self._connected = False
            log.info("discord_rpc: отключён")
        except Exception as e:
            log.error(f"discord_rpc stop: {e}")

    def restart(self):
        self.stop()
        self.start()

    def apply_settings(self, settings):
        self.settings = settings or {}

        new_enabled = bool(self.settings.get("discord_enabled", False))
        new_client_id = (self.settings.get("discord_client_id") or "").strip()
        new_large_image = (
            self.settings.get("discord_large_image") or "logo"
        ).strip()
        new_large_text = (
            self.settings.get("discord_large_text") or APP_NAME
        ).strip()
        new_show_idle = bool(
            self.settings.get("discord_show_when_idle", True)
        )

        changed = (
            new_enabled != self._enabled
            or new_client_id != self._client_id
            or new_large_image != self._large_image
            or new_large_text != self._large_text
            or new_show_idle != self._show_when_idle
        )

        self._enabled = new_enabled
        self._client_id = new_client_id
        self._large_image = new_large_image
        self._large_text = new_large_text
        self._show_when_idle = new_show_idle

        if not changed:
            return

        if self._enabled:
            self.restart()
            if self._current_session:
                self._update_current()
            elif self._show_when_idle:
                self._update_idle()
        else:
            self.stop()

    # ================== СОБЫТИЯ ==================

    def on_app_launch(self, app, cover_url=""):
        """Программа запущена.

        cover_url — необязательный URL обложки (внешний). Если пусто —
        используется стандартный large_image из настроек.
        """
        if not self._connected:
            return
        try:
            name = app.get("name", "Программа")
            category = app.get("category") or "other"
            is_game = (category == "games")

            cur = self._current_session
            if cur is not None and cur.get("is_game") and not is_game:
                return

            self._current_session = {
                "name":         name,
                "category":     category,
                "is_game":      is_game,
                "start_ts":     time.time(),
                "path":         app.get("path", ""),
                "cover_url":    cover_url or "",
            }
            self._update_current()
        except Exception as e:
            log.error(f"discord_rpc on_app_launch: {e}")

    def update_cover(self, cover_url):
        """Обновляет обложку для активной сессии (внешний URL)."""
        if not self._connected:
            return
        if not cover_url:
            return
        cur = self._current_session
        if cur is None:
            return
        if cur.get("cover_url") == cover_url:
            return
        cur["cover_url"] = cover_url
        self._update_current()

    def on_app_close(self, app):
        if not self._connected:
            return
        try:
            cur = self._current_session
            if cur is None:
                return
            if cur.get("path") != app.get("path"):
                return

            self._current_session = None
            if self._show_when_idle:
                self._update_idle()
            else:
                self._clear()
        except Exception as e:
            log.error(f"discord_rpc on_app_close: {e}")

    def tick(self):
        if not self._connected:
            return
        try:
            if self._rpc is None:
                self._connected = False
        except Exception:
            self._connected = False

    # ================== ВНУТРЕННЕЕ ==================

    def _build_activity(self, details, state, start=None, buttons=None,
                        large_image=None, large_text=None):
        activity = {
            "details": details,
            "state": state,
            "large_image": large_image or self._large_image,
            "large_text": large_text or self._large_text,
            "instance": False,
        }
        if start is not None:
            activity["start"] = int(start)
        if buttons:
            activity["buttons"] = buttons
        return activity

    def _update_current(self):
        cur = self._current_session
        if not cur:
            return
        try:
            is_game = cur.get("is_game", False)
            name = cur["name"]
            cover_url = cur.get("cover_url", "") or ""

            if is_game:
                details = f"Играет в {name}"
            else:
                details = f"Запущено: {name}"

            started = cur["start_ts"]
            state = f"Сессия с {datetime.fromtimestamp(started):%H:%M}"

            buttons = None
            if GITHUB_REPO_URL:
                buttons = [{"label": "MyLauncher", "url": GITHUB_REPO_URL}]

            # Если есть URL обложки — используем её вместо стандартного ассета
            large_image = cover_url if cover_url else self._large_image
            large_text = self._large_text

            activity = self._build_activity(
                details=details,
                state=state,
                start=started,
                buttons=buttons,
                large_image=large_image,
                large_text=large_text,
            )
            self._set(activity)
        except Exception as e:
            log.error(f"discord_rpc _update_current: {e}")

    def _update_idle(self):
        try:
            activity = self._build_activity(
                details=f"В {APP_NAME}",
                state="Ничего не запущено",
                start=self._idle_since,
            )
            self._set(activity)
        except Exception as e:
            log.error(f"discord_rpc _update_idle: {e}")

    def _set(self, activity):
        if not self._connected or self._rpc is None:
            return
        try:
            with self._lock:
                self._rpc.update(**activity)
        except PipeClosed:
            self._connected = False
            log.warning("discord_rpc: pipe closed (Discord закрылся?)")
        except Exception as e:
            log.error(f"discord_rpc update: {e}")

    def _clear(self):
        if not self._connected or self._rpc is None:
            return
        try:
            with self._lock:
                self._rpc.clear()
        except Exception as e:
            log.error(f"discord_rpc clear: {e}")