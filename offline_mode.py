"""
offline_mode.py — NeuroKey To'liq Offline Rejim

Internet yo'q joyda ham to'liq ishlash uchun:
- STT: faster-whisper (lokal, GPU)
- TTS: Silero (lokal, GPU)
- LLM: Ollama (lokal, gemma3:4b)
- Vision: faqat lokal OCR
- Web search: keshdan yoki o'chirilgan

python offline_mode.py enable   → offline rejimga o'tish
python offline_mode.py disable  → online rejimga qaytish
python offline_mode.py status   → holat ko'rish
python offline_mode.py test     → internet borligini tekshirish
"""
from __future__ import annotations
import os, json, socket, time, logging
from typing import Optional

log = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_DIR, ".env")
_STATE_FILE = os.path.join(_DIR, "data", "offline_state.json")
os.makedirs(os.path.join(_DIR, "data"), exist_ok=True)


# ─── Internet tekshiruv ──────────────────────────────────────────────────────

def check_internet(timeout: float = 3.0) -> bool:
    """Internet bor-yo'qligini tekshiradi."""
    hosts = [("8.8.8.8", 53), ("1.1.1.1", 53), ("208.67.222.222", 53)]
    for host, port in hosts:
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return True
        except Exception:
            continue
    return False


def check_ollama() -> bool:
    """Ollama lokal serveri ishlayaptimi."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        return True
    except Exception:
        return False


# ─── .env boshqaruv ──────────────────────────────────────────────────────────

def _read_env() -> list[str]:
    try:
        with open(_ENV_FILE, encoding="utf-8") as f:
            return f.readlines()
    except Exception:
        return []


def _write_env(lines: list[str]) -> None:
    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _set_env_var(key: str, value: str) -> None:
    """ENV o'zgaruvchisini o'rnatadi yoki yangilaydi."""
    lines = _read_env()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"# {key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    _write_env(lines)


def _comment_env_var(key: str) -> None:
    """ENV o'zgaruvchisini kommentga aylantiradi."""
    lines = _read_env()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            lines[i] = f"# {stripped}\n"
    _write_env(lines)


# ─── Offline rejim ───────────────────────────────────────────────────────────

def enable() -> dict:
    """To'liq offline rejimga o'tish."""
    results = {}

    # 1. Ollama tekshirish
    ollama_ok = check_ollama()
    if not ollama_ok:
        print("[!] Ollama ishlamayapti! Avval: ollama serve")
        results["ollama"] = False
    else:
        results["ollama"] = True

    # 2. LLM → Ollama ga o'tish
    _set_env_var("OPENAI_BASE_URL", "http://localhost:11434/v1")
    _set_env_var("OPENAI_CHAT_MODEL", "gemma3:4b")
    _set_env_var("OPENAI_API_KEY", "ollama")  # Ollama uchun dummy key
    results["llm"] = "ollama (lokal)"
    print("[OK] LLM: Ollama (gemma3:4b)")

    # 3. STT → faster-whisper lokal
    _set_env_var("STT_BACKEND", "faster_whisper")
    _set_env_var("WHISPER_MODEL", "small")  # small = tez, offline
    results["stt"] = "faster-whisper (lokal)"
    print("[OK] STT: faster-whisper (lokal)")

    # 4. TTS → Silero lokal
    _set_env_var("TTS_BACKEND", "silero")
    _set_env_var("TTS_USE_OPENAI", "0")
    _set_env_var("TTS_USE_EDGE_RUSSIAN", "0")
    results["tts"] = "silero (lokal)"
    print("[OK] TTS: Silero (lokal)")

    # 5. Vision → faqat lokal OCR
    _set_env_var("SCREEN_OCR_FALLBACK_VISION", "0")
    results["vision"] = "lokal OCR (Tesseract/EasyOCR)"
    print("[OK] Vision: faqat lokal OCR")

    # 6. Web search → o'chirish
    _set_env_var("WEB_SEARCH_ENABLED", "0")
    results["web"] = "o'chirilgan"
    print("[OK] Web: o'chirilgan (offline)")

    # Holatni saqlash
    state = {"mode": "offline", "enabled_at": time.time(), "results": results}
    _save_state(state)
    print("\n[HA] NeuroKey OFFLINE rejimda. Qayta ishga tushiring: python main.py")
    return results


def disable() -> dict:
    """Online rejimga qaytish."""

    # OpenAI ga qaytish
    _comment_env_var("OPENAI_BASE_URL")
    _comment_env_var("OPENAI_CHAT_MODEL")
    # API key asl qiymatiga qaytsin (eski qiymat kommentda qoldi)

    # STT → OpenAI Whisper
    _set_env_var("STT_BACKEND", "whisper_openai")

    # TTS → OpenAI
    _set_env_var("TTS_USE_OPENAI", "1")
    _set_env_var("TTS_USE_EDGE_RUSSIAN", "1")

    # Vision → fallback yoqish
    _set_env_var("SCREEN_OCR_FALLBACK_VISION", "1")

    # Web → yoqish
    _set_env_var("WEB_SEARCH_ENABLED", "1")

    state = {"mode": "online", "disabled_at": time.time()}
    _save_state(state)
    print("[OK] NeuroKey ONLINE rejimda. Qayta ishga tushiring: python main.py")
    return {"mode": "online"}


# ─── Auto-detect ─────────────────────────────────────────────────────────────

def auto_detect_and_configure() -> str:
    """
    Avtomatik: internet bormi → online, yo'qmi → offline.
    main.py da chaqirish uchun.
    """
    internet = check_internet(timeout=2.0)
    ollama = check_ollama()

    if not internet and ollama:
        log.info("[OFFLINE] Internet yo'q → Ollama ga o'tildi")
        # Faqat LLM ni o'zgartirish (env ga yozmasdan — runtime)
        os.environ["OPENAI_BASE_URL"] = "http://localhost:11434/v1"
        os.environ["OPENAI_CHAT_MODEL"] = "gemma3:4b"
        os.environ["OPENAI_API_KEY"] = "ollama"
        os.environ["WEB_SEARCH_ENABLED"] = "0"
        os.environ["SCREEN_OCR_FALLBACK_VISION"] = "0"
        return "offline"
    elif internet:
        return "online"
    else:
        return "no_connection"


# ─── Holat ───────────────────────────────────────────────────────────────────

def _save_state(state: dict) -> None:
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_status() -> dict:
    internet = check_internet()
    ollama = check_ollama()

    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    except Exception:
        saved = {"mode": "unknown"}

    return {
        "internet": internet,
        "ollama": ollama,
        "configured_mode": saved.get("mode", "unknown"),
        "can_offline": ollama,
        "can_online": internet,
    }


def print_status() -> None:
    s = get_status()
    print("\n=== NEUROKEY ALOQA HOLATI ===")
    print(f"  Internet:      {'[HA]' if s['internet'] else '[YOQ]'}")
    print(f"  Ollama lokal:  {'[HA]' if s['ollama'] else '[YOQ]'}")
    print(f"  Rejim:         {s['configured_mode'].upper()}")
    print(f"  Offline mumkin: {'[HA]' if s['can_offline'] else '[YOQ] — ollama serve kerak'}")
    print("===========================")
    if not s["internet"] and not s["ollama"]:
        print("\n[!] Na internet, na Ollama! NeuroKey ishlay olmaydi.")
        print("    Yechim: WiFi ulang yoki 'ollama serve' buyrug'ini bering.")


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "enable":
        enable()
    elif cmd == "disable":
        disable()
    elif cmd == "status":
        print_status()
    elif cmd == "test":
        print(f"Internet: {'[HA]' if check_internet() else '[YOQ]'}")
        print(f"Ollama:   {'[HA]' if check_ollama() else '[YOQ]'}")
    else:
        print(f"Noma'lum: {cmd}. enable|disable|status|test")
