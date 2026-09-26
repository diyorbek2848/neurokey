# -*- coding: utf-8 -*-
"""
NeuroKey — real-vaqt debug log.
Barcha muhim hodisalar timestamps bilan yoziladi.
Fayl: neurokey_logs/neurokey_debug.log
Max hajm: 5MB, keyin tozalanadi.
"""
import os
import time
import threading

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neurokey_logs")
_LOG_FILE = os.path.join(_LOG_DIR, "neurokey_debug.log")
_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
_lock = threading.Lock()

os.makedirs(_LOG_DIR, exist_ok=True)

# Har ishga tushganda yangi seans boshlanadi
with _lock:
    try:
        if os.path.isfile(_LOG_FILE) and os.path.getsize(_LOG_FILE) > _MAX_SIZE:
            os.remove(_LOG_FILE)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"  NeuroKey seans boshlandi: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n")
    except Exception:
        pass


def log(tag: str, msg: str):
    """Hodisani faqat log fayliga yozadi (konsol emas)."""
    ts = time.strftime("%H:%M:%S") + f".{int(time.monotonic() * 1000) % 1000:03d}"
    line = f"[{ts}] [{tag}] {msg}"
    with _lock:
        try:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def log_tts(msg: str):
    log("TTS", msg)


def log_stt(msg: str):
    log("STT", msg)


def log_main(msg: str):
    log("MAIN", msg)
