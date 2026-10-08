"""
Генерация русских голосовых фраз для лаунчера через Piper TTS.
Использует локальную модель ru_RU-ruslan-medium.
"""

import os
import sys
import wave

# --- Настройки ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models", "piper", "russian")
OUTPUT_DIR = os.path.join(BASE_DIR, "sounds", "voice")

# Имя модели (файлы .onnx и .onnx.json должны совпадать)
MODEL_NAME = "ru_RU-ruslan-medium"
MODEL_PATH = os.path.join(MODEL_DIR, f"{MODEL_NAME}.onnx")
CONFIG_PATH = os.path.join(MODEL_DIR, f"{MODEL_NAME}.onnx.json")

# Русские фразы для событий
VOICE_PHRASES = {
    "startup":  "Все системы в сети",
    "launch":   "Сию секунду, сэр",
    "close":    "Как пожелаете",
    "error":    "Боюсь, это невозможно",
    "success":  "Готово, сэр",
    "info":     "Для вас, сэр",
    "shutdown": "До свидания, сэр",
}


def main():
    # 1. Проверяем piper-tts
    try:
        from piper import PiperVoice
    except ImportError:
        print("ОШИБКА: библиотека piper-tts не установлена.")
        print("Установи: pip install piper-tts")
        sys.exit(1)

    # 2. Проверяем файлы модели
    if not os.path.exists(MODEL_PATH) or not os.path.exists(CONFIG_PATH):
        print("ОШИБКА: Файлы модели не найдены.")
        print(f"Проверь, что '{MODEL_NAME}.onnx' и '{MODEL_NAME}.onnx.json' лежат в:")
        print(f"  {MODEL_DIR}")
        print("\nСкачай модель с Hugging Face (ссылки в инструкции).")
        sys.exit(1)

    # 3. Создаём папку вывода
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 4. Загружаем модель
    print(f"Загрузка русской модели: {MODEL_NAME}\n")
    try:
        voice = PiperVoice.load(MODEL_PATH, CONFIG_PATH)
    except Exception as e:
        print(f"ОШИБКА загрузки модели: {e}")
        sys.exit(1)

    # 5. Генерируем фразы
    print(f"Генерация фраз в: {OUTPUT_DIR}\n")
    for key, text in VOICE_PHRASES.items():
        out_path = os.path.join(OUTPUT_DIR, f"{key}.wav")
        print(f"  → {key:10}  «{text}»")
        try:
            with wave.open(out_path, "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
        except Exception as e:
            print(f"     ОШИБКА: {e}")
            sys.exit(1)

    print("\nГотово! Русские голосовые фразы сгенерированы.")
    print("Включи в лаунчере: Настройки → Поведение → Голосовые фразы")


if __name__ == "__main__":
    main()