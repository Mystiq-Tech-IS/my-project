"""Звуки интерфейса через QSoundEffect.

Два уровня:
  1. Бипы (QSoundEffect, wave) — генерируются автоматически в sounds/.
  2. Голосовые фразы — .wav из sounds/voice/, можно положить свои или
     сгенерировать через generate_voice.py.
"""

import os
import math
import struct
import wave

from PySide6.QtCore import QUrl

try:
    from PySide6.QtMultimedia import QSoundEffect
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False
    QSoundEffect = None

from config import BASE_DIR

try:
    from storage import log
except Exception:
    import logging
    log = logging.getLogger("launcher")


SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")
VOICE_DIR = os.path.join(SOUNDS_DIR, "voice")

# ==================== БИПЫ ====================
BUILTIN_SOUNDS = {
    "launch":  ("launch.wav",  880.0, 140),
    "close":   ("close.wav",   392.0, 180),
    "success": ("success.wav", 1046.5, 110),
    "error":   ("error.wav",   220.0, 260),
    "notify":  ("notify.wav",  659.3, 130),
    "click":   ("click.wav",   600.0, 45),
    "toggle":  ("toggle.wav",  740.0, 60),
}

# ==================== ГОЛОСОВЫЕ ФРАЗЫ ====================
# event_name → имя файла в sounds/voice/
VOICE_EVENTS = {
    "startup":  "startup.wav",
    "launch":   "launch.wav",
    "close":    "close.wav",
    "error":    "error.wav",
    "success":  "success.wav",
    "info":     "info.wav",
    "shutdown": "shutdown.wav",
}


_enabled = True
_volume = 0.6
_event_flags = {}
_effects = {}
_initialized = False

_voice_enabled = True
_voice_volume = 0.8
_voice_flags = {}
_voice_effects = {}
_voice_initialized = False


# ==================== ГЕНЕРАЦИЯ БИПОВ ====================
def _generate_wav(path, freq, duration_ms, volume=0.55):
    if os.path.exists(path):
        return
    try:
        framerate = 44100
        n_samples = int(framerate * duration_ms / 1000)
        fade_in = max(1, int(n_samples * 0.10))
        fade_out = max(1, int(n_samples * 0.35))
        amp = int(32767 * volume)
        samples = []
        two_pi_f = 2.0 * math.pi * freq
        for i in range(n_samples):
            t = i / framerate
            v = math.sin(two_pi_f * t)
            if i < fade_in:
                env = i / fade_in
            elif i > n_samples - fade_out:
                env = (n_samples - i) / fade_out
            else:
                env = 1.0
            samples.append(int(amp * v * env))

        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(framerate)
            w.writeframes(struct.pack("<" + "h" * len(samples), *samples))
        log.info(f"Сгенерирован звук: {os.path.basename(path)}")
    except Exception as e:
        log.error(f"generate_wav {path}: {e}")


def ensure_sounds_folder():
    try:
        os.makedirs(SOUNDS_DIR, exist_ok=True)
    except Exception as e:
        log.error(f"ensure_sounds_folder: {e}")
        return
    for name, (filename, freq, dur) in BUILTIN_SOUNDS.items():
        path = os.path.join(SOUNDS_DIR, filename)
        if not os.path.exists(path):
            _generate_wav(path, freq, dur)


def ensure_voice_dir():
    try:
        os.makedirs(VOICE_DIR, exist_ok=True)
    except Exception as e:
        log.error(f"ensure_voice_dir: {e}")


# ==================== ИНИЦИАЛИЗАЦИЯ ====================
def init(enabled=True, volume=60, event_flags=None):
    """Инициализирует бипы."""
    global _initialized, _enabled, _volume, _event_flags
    if not HAS_SOUND:
        log.warning("QSoundEffect недоступен — звуки выключены")
        _initialized = True
        return

    _enabled = bool(enabled)
    try:
        _volume = max(0.0, min(1.0, float(volume) / 100.0))
    except Exception:
        _volume = 0.6
    _event_flags = dict(event_flags or {})

    if _initialized:
        _apply_volume()
        return

    ensure_sounds_folder()
    for name, (filename, _f, _d) in BUILTIN_SOUNDS.items():
        path = os.path.join(SOUNDS_DIR, filename)
        if not os.path.exists(path):
            continue
        try:
            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(path))
            eff.setVolume(_volume)
            _effects[name] = eff
        except Exception as e:
            log.error(f"init sound {name}: {e}")
    _initialized = True
    log.info(f"Звуки инициализированы: {len(_effects)} шт.")


def init_voice(enabled=True, volume=80, event_flags=None):
    """Инициализирует голосовые фразы."""
    global _voice_initialized, _voice_enabled, _voice_volume, _voice_flags
    if not HAS_SOUND:
        _voice_initialized = True
        return

    _voice_enabled = bool(enabled)
    try:
        _voice_volume = max(0.0, min(1.0, float(volume) / 100.0))
    except Exception:
        _voice_volume = 0.8
    _voice_flags = dict(event_flags or {})

    if _voice_initialized:
        _apply_voice_volume()
        return

    ensure_voice_dir()
    for event, filename in VOICE_EVENTS.items():
        path = os.path.join(VOICE_DIR, filename)
        if not os.path.exists(path):
            continue
        try:
            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(path))
            eff.setVolume(_voice_volume)
            _voice_effects[event] = eff
        except Exception as e:
            log.error(f"init_voice {event}: {e}")
    _voice_initialized = True
    log.info(f"Голосовые фразы: {len(_voice_effects)} шт.")


def _apply_volume():
    for eff in _effects.values():
        try:
            eff.setVolume(_volume)
        except Exception:
            pass


def _apply_voice_volume():
    for eff in _voice_effects.values():
        try:
            eff.setVolume(_voice_volume)
        except Exception:
            pass


# ==================== БИПЫ — API ====================
def set_enabled(enabled):
    global _enabled
    _enabled = bool(enabled)


def is_enabled():
    return _enabled


def set_volume(percent):
    global _volume
    try:
        _volume = max(0.0, min(1.0, float(percent) / 100.0))
    except Exception:
        _volume = 0.6
    _apply_volume()


def set_event_flags(flags):
    global _event_flags
    _event_flags = dict(flags or {})


def play(name):
    """Проигрывает бип."""
    if not _enabled or not HAS_SOUND:
        return
    if _event_flags.get(name) is False:
        return
    eff = _effects.get(name)
    if eff is None:
        return
    try:
        eff.play()
    except Exception as e:
        log.error(f"play sound {name}: {e}")


# ==================== ГОЛОС — API ====================
def set_voice_enabled(enabled):
    global _voice_enabled
    _voice_enabled = bool(enabled)


def is_voice_enabled():
    return _voice_enabled


def set_voice_volume(percent):
    global _voice_volume
    try:
        _voice_volume = max(0.0, min(1.0, float(percent) / 100.0))
    except Exception:
        _voice_volume = 0.8
    _apply_voice_volume()


def set_voice_flags(flags):
    global _voice_flags
    _voice_flags = dict(flags or {})


def has_voice(event):
    return event in _voice_effects


def play_voice(event):
    """Проигрывает голосовую фразу. Если файла нет — молчит."""
    if not _voice_enabled or not HAS_SOUND:
        return
    if _voice_flags.get(event) is False:
        return
    eff = _voice_effects.get(event)
    if eff is None:
        return
    try:
        eff.play()
    except Exception as e:
        log.error(f"play_voice {event}: {e}")


def reload_voice():
    """Перечитать файлы из sounds/voice/ (после генерации в UI)."""
    global _voice_effects, _voice_initialized
    _voice_effects = {}
    _voice_initialized = False
    init_voice(_voice_enabled, int(_voice_volume * 100), _voice_flags)


# ==================== ПУТИ ====================
def sounds_dir():
    return SOUNDS_DIR


def voice_dir():
    return VOICE_DIR