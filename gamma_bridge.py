# -*- coding: utf-8 -*-
"""NeuroKey — Gamma.app taqdimot yaratish moduli.

Gamma.app API orqali ovoz buyrug'i bilan AI taqdimot (presentation/document) yaratadi.
Kalit: GAMMA_API_KEY (.env da)
Base URL: https://public-api.gamma.app
Auth: X-API-KEY header

Qo'llanilish:
    "NeuroKey, taqdimot yarat: sun'iy intellekt haqida 10 ta slayd"
    "NeuroKey, презентацию сделай про маркетинг"
    "создай документ о нашем стартапе"
"""
import os
import time
import webbrowser
import subprocess
import tempfile
from typing import Optional, Dict, Any

try:
    import requests as _req
    import urllib3 as _urllib3
    _urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)
    _HAVE_REQUESTS = True
except ImportError:
    _HAVE_REQUESTS = False

try:
    import config as C
    _GAMMA_KEY = (os.getenv("GAMMA_API_KEY") or getattr(C, "GAMMA_API_KEY", "")).strip()
except Exception:
    _GAMMA_KEY = (os.getenv("GAMMA_API_KEY", "")).strip()

_BASE_URL = "https://public-api.gamma.app"
_HEADERS_BASE = {"Content-Type": "application/json"}


def _get_key() -> str:
    return (os.getenv("GAMMA_API_KEY") or _GAMMA_KEY or "").strip()


def is_available() -> bool:
    """Gamma API kalit mavjudmi?"""
    return bool(_get_key()) and _HAVE_REQUESTS


# ── So'rovni aniqlash ────────────────────────────────────────────────────────

_TRIGGER_WORDS = [
    # O'zbek
    "taqdimot yarat", "taqdimot qil", "slayd yarat", "slayd qil",
    "prezentatsiya yarat", "prezentatsiya qil",
    # Rus
    "создай презентацию", "сделай презентацию", "создай слайды",
    "сделай слайды", "создай доклад", "сделай доклад",
    "создай документ", "сделай документ",
    # English
    "create presentation", "make presentation", "create slides",
    "make slides", "create a deck", "make a deck",
    "generate presentation", "create document",
]

_FORMAT_WORDS = {
    "document":     ["документ", "doc", "doküman", "hujjat"],
    "webpage":      ["webpage", "web sahifa", "сайт", "вебстраница"],
    "social":       ["social", "instagram", "post", "пост"],
    "presentation": [],  # default
}

_EXPORT_WORDS = {
    "pdf":  ["pdf", "пдф"],
    "pptx": ["pptx", "powerpoint", "powerpoynt"],
}


def is_gamma_request(text: str) -> bool:
    """Foydalanuvchi taqdimot yaratmoqchi ekanini aniqlash."""
    if not text:
        return False
    low = text.lower().strip()
    return any(kw in low for kw in _TRIGGER_WORDS)


def extract_gamma_params(text: str) -> Dict[str, Any]:
    """Matndan parametrlarni ajratib olish.

    Qaytaradi: {topic, format, num_cards, export_as, language, instructions}
    """
    low = text.lower().strip()
    params: Dict[str, Any] = {
        "topic": "",
        "format": "presentation",
        "num_cards": 10,
        "export_as": None,
        "language": "ru",
        "instructions": "",
    }

    # Format aniqlash
    for fmt, words in _FORMAT_WORDS.items():
        if any(w in low for w in words):
            params["format"] = fmt
            break

    # Export aniqlash
    for ext, words in _EXPORT_WORDS.items():
        if any(w in low for w in words):
            params["export_as"] = ext
            break

    # Slayd soni aniqlash: "15 ta slayd", "20 slides"
    import re
    m = re.search(r"(\d+)\s*(?:та\s*)?(?:slayd|слайд|slide|card|карт)", low)
    if m:
        n = int(m.group(1))
        params["num_cards"] = max(3, min(n, 60))

    # Til aniqlash
    if any(w in low for w in ["o'zbek", "uzbek", "uzbekcha", "o'zbekcha"]):
        params["language"] = "uz"
    elif any(w in low for w in ["english", "ingliz", "inglizcha"]):
        params["language"] = "en"
    else:
        params["language"] = "ru"

    # Mavzu ajratish — trigger so'zdan keyin kela'digan matn
    topic = text
    for kw in sorted(_TRIGGER_WORDS, key=len, reverse=True):
        idx = low.find(kw)
        if idx != -1:
            topic = text[idx + len(kw):].strip(" :,-\n")
            break
    # Tozalash
    topic = re.sub(r"\b\d+\s*(?:та\s*)?(?:slayd|слайд|slide|card|карт)\b", "", topic, flags=re.I).strip(" :,-")
    topic = re.sub(r"\b(?:pdf|pptx|powerpoint)\b", "", topic, flags=re.I).strip()
    params["topic"] = topic or "Yangi taqdimot"

    return params


# ── API chaqiruvlari ─────────────────────────────────────────────────────────

def _headers() -> Dict[str, str]:
    return {**_HEADERS_BASE, "X-API-KEY": _get_key()}


def create_presentation(
    topic: str,
    format: str = "presentation",
    num_cards: int = 10,
    language: str = "ru",
    export_as: Optional[str] = None,
    instructions: str = "",
    text_mode: str = "generate",
    progress_cb=None,
) -> Dict[str, Any]:
    """Gamma.app da taqdimot yaratadi.

    progress_cb(message) — har bosqichda qayta chaqiriladi.
    Qaytaradi: {ok, url, export_url, credits_used, error}
    """
    if not is_available():
        return {"ok": False, "error": "GAMMA_API_KEY yo'q yoki requests o'rnatilmagan"}

    def _cb(msg):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    _cb("Gamma.app ga ulanilmoqda...")

    payload: Dict[str, Any] = {
        "inputText": topic,
        "textMode": text_mode,
        "format": format,
        "numCards": num_cards,
        "textOptions": {
            "language": language,
            "amount": "medium",
        },
        "imageOptions": {
            "source": "aiGenerated",
            "stylePreset": "photorealistic",
        },
    }
    if export_as:
        payload["exportAs"] = export_as
    if instructions:
        payload["additionalInstructions"] = instructions[:5000]

    try:
        resp = _req.post(
            f"{_BASE_URL}/v1.0/generations",
            headers=_headers(),
            json=payload,
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        gen_id = resp.json().get("generationId")
        if not gen_id:
            return {"ok": False, "error": f"generationId kelmadi: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"So'rov xatosi: {e}"}

    _cb("Taqdimot yaratilmoqda, kuting...")

    # Polling — har 5 sekundda tekshirish, max 3 daqiqa
    deadline = time.time() + 180
    poll_interval = 5
    dots = 0
    while time.time() < deadline:
        time.sleep(poll_interval)
        dots += 1
        try:
            r = _req.get(
                f"{_BASE_URL}/v1.0/generations/{gen_id}",
                headers=_headers(),
                timeout=15,
                verify=False,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "")
            if status == "completed":
                gamma_url = data.get("gammaUrl", "")
                export_url = data.get("exportUrl", "")
                credits = data.get("credits", {})
                _cb(f"Taqdimot tayyor! ({credits.get('deducted',0)} kredit sarflandi)")
                return {
                    "ok": True,
                    "url": gamma_url,
                    "export_url": export_url,
                    "credits_deducted": credits.get("deducted", 0),
                    "credits_remaining": credits.get("remaining", 0),
                    "gen_id": gen_id,
                    "error": None,
                }
            elif status == "failed":
                return {"ok": False, "error": f"Gamma xatosi: {data.get('error', 'unknown')}"}
            else:
                if dots % 3 == 0:
                    _cb(f"Hali tayyorlanmoqda... ({int(time.time() - (deadline - 180))}s)")
        except Exception as e:
            _cb(f"Polling xatosi: {e}")
            time.sleep(5)

    return {"ok": False, "error": "Vaqt tugadi (3 daqiqa) — gamma.app da ko'ring"}


def open_in_browser(url: str) -> bool:
    """Taqdimotni brauzarda ochish."""
    if not url:
        return False
    try:
        webbrowser.open(url)
        return True
    except Exception:
        try:
            os.startfile(url)
            return True
        except Exception:
            return False


def download_export(export_url: str, filename: str = "presentation") -> Optional[str]:
    """Export URL dan faylni yuklab olish (PDF/PPTX). Fayl yo'lini qaytaradi."""
    if not export_url or not _HAVE_REQUESTS:
        return None
    try:
        ext = "pdf" if "pdf" in export_url.lower() else "pptx"
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads, exist_ok=True)
        path = os.path.join(downloads, f"{filename}.{ext}")
        r = _req.get(export_url, headers={"X-API-KEY": _get_key()}, timeout=60, stream=True)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return path
    except Exception:
        return None


def list_themes() -> list:
    """Mavjud themelarni ro'yxat qilish."""
    if not is_available():
        return []
    try:
        r = _req.get(f"{_BASE_URL}/v1.0/themes", headers=_headers(), timeout=10, verify=False)
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception:
        return []


def get_handle_reply(text: str, tts_say=None) -> Optional[str]:
    """main.py dan to'g'ridan-to'g'ri chaqirish uchun.

    Parametrlarni ajratadi, taqdimot yaratadi, URL ni aytadi va brauzarda ochadi.
    Qaytaradi: javob matni (TTS uchun) yoki None (agar gamma so'rovi emas).
    """
    if not is_gamma_request(text):
        return None

    if not is_available():
        return "Gamma API kaliti topilmadi. .env faylida GAMMA_API_KEY ni tekshiring."

    params = extract_gamma_params(text)
    topic = params["topic"]

    def _say(msg):
        if tts_say:
            try:
                tts_say(msg)
            except Exception:
                pass

    # Boshlash xabari
    fmt_names = {
        "presentation": "taqdimot",
        "document": "hujjat",
        "webpage": "veb sahifa",
        "social": "post",
    }
    fmt_name = fmt_names.get(params["format"], "taqdimot")
    _say(f"{topic} mavzusida {params['num_cards']} sahifali {fmt_name} yaratilmoqda. Biroz kuting.")

    result = create_presentation(
        topic=topic,
        format=params["format"],
        num_cards=params["num_cards"],
        language=params["language"],
        export_as=params["export_as"],
        progress_cb=None,
    )

    if not result["ok"]:
        _err_msg = result.get('error', 'noma`lum xato')
        msg = f"Gamma xatosi: {_err_msg}"
        _say(msg)
        return msg

    url = result.get("url", "")
    credits = result.get("credits_deducted", 0)
    remaining = result.get("credits_remaining", 0)

    # Brauzarda oching
    if url:
        open_in_browser(url)

    # Export fayl (agar so'ralgan bo'lsa)
    export_url = result.get("export_url", "")
    export_path = None
    if export_url and params.get("export_as"):
        safe_topic = "".join(c for c in topic[:30] if c.isalnum() or c in " _-").strip()
        export_path = download_export(export_url, filename=safe_topic or "presentation")

    # Javob
    if export_path:
        reply = f"{fmt_name.capitalize()} tayyor! Brauzerda ochildi va {export_path} ga saqlandi. {credits} kredit sarflandi, qoldi {remaining}."
    else:
        reply = f"{fmt_name.capitalize()} tayyor! Brauzerda ochildi. {credits} kredit sarflandi, qoldi {remaining}."

    _say(reply)
    return reply
