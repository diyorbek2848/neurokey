# -*- coding: utf-8 -*-
"""Whisper STT xatolarini tuzatish — salomlashuvlar, TV shovqini, junk."""
from __future__ import annotations

import re

# Butun gap (faqat shu so'z / juda qisqa)
_EXACT = {
    "это": "привет",
    "eto": "привет",
    "ето": "привет",
    "et": "привет",
    "privet": "привет",
    "pryvet": "привет",
    "ptrivet": "привет",
    "prevyet": "привет",
    "privyet": "привет",
    "прив": "привет",
    "привет": "привет",
    "привет! это": "привет",
    "здраствуй": "здравствуй",
    "здраствуйте": "здравствуйте",
}

_PARTIAL = [
    ("privet", "привет"),
    ("pryvet", "привет"),
    ("prevyet", "привет"),
    ("ptrivet", "привет"),
    ("привет! это", "привет"),
    ("привет это", "привет"),
]

# TV / video / fon — LLM ga yuborilmasin (yomon "хватит повторять" javoblari)
_JUNK_PATTERNS = (
    "продолжение следует",
    "to be continued",
    "субтитры",
    "редактор субтитров",
    "корректор",
    "перевод",
    "надписи",
)


def is_stt_junk(text: str) -> bool:
    """Fon/TV yoki bo'sh STT — javob bermaslik."""
    low = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if not low or len(low) < 3:
        return True
    if any(p in low for p in _JUNK_PATTERNS):
        return True
    if low.count("продолжение следует") >= 1 and len(low) < 80:
        return True
    return False


def fix_whisper_text(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    if is_stt_junk(t):
        return ""
    low = re.sub(r"\s+", " ", t.lower()).strip()
    if low in _EXACT:
        fixed = _EXACT[low]
        if fixed != low:
            print(f"[STT] tuzatildi: '{t}' -> '{fixed}'", flush=True)
        return fixed
    if len(low) <= 30:
        out = low
        for bad, good in _PARTIAL:
            if bad in out:
                out = out.replace(bad, good)
        if "здесь здесь" in out or "алло" in out and len(out) < 25:
            print(f"[STT] shovqin e'tiborsiz: '{t}'", flush=True)
            return ""
        if out != low:
            print(f"[STT] tuzatildi: '{t}' -> '{out}'", flush=True)
            return out
    return t
