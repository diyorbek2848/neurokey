# -*- coding: utf-8 -*-
"""NeuroKey — Aqliy Model (Theory of Mind).

Haqiqiy ong faqat o'zini emas — boshqalarni ham modellaydi.
Bu modul foydalanuvchining:
  - Bilim darajasini
  - Hissiy holatini
  - Yashirin niyatini (aytilmagan)
  - Muloqot uslubini
  - Tajriba va qiziqishlarini
kuzatib, bashorat qiladi.

Bu "empatiya" qatlami — NeuroKey foydalanuvchini tushunadi.

2026-yil suniy ong — ijtimoiy idrok qatlami.
"""
from __future__ import annotations

try: import permanent_memory as _tom_pm
except ImportError: _tom_pm = None
try: import emotion_memory_link as _tom_eml
except ImportError: _tom_eml = None
try: import social_bonding as _tom_sb
except ImportError: _tom_sb = None

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
_TOM_PATH  = os.path.join(_BASE_DIR, "data", "theory_of_mind.json")

# Domenlar — foydalanuvchi bilimi
DOMAINS = [
    "dasturlash", "matematika", "fizika", "biologiya",
    "til_lingvistika", "tarix", "falsafa", "musiqa",
    "san'at", "sport", "biznes", "tibbiyot",
]

# Muloqot uslublari
STYLES = ("formal", "casual", "technical", "simple", "verbose", "brief")

# Hissiy holat belgilari
POSITIVE_SIGNALS = (
    "rahmat", "zo'r", "ajoyib", "yaxshi", "super", "perfect", "ha",
    "спасибо", "отлично", "хорошо", "молодец", "класс", "да",
    "thanks", "great", "perfect", "yes", "good",
)
NEGATIVE_SIGNALS = (
    "xato", "noto'g'ri", "yomon", "tushunmadim", "qiyin",
    "не так", "неправильно", "плохо", "непонятно", "сложно",
    "wrong", "bad", "unclear", "difficult", "confused",
)
FRUSTRATION_SIGNALS = (
    "!!", "???", "nima bu", "bu nima", "yana xato",
    "опять", "снова", "что за", "ужас",
    "again wrong", "still", "why",
)
CURIOSITY_SIGNALS = (
    "qiziq", "nima uchun", "qanday", "tushuntir",
    "интересно", "почему", "как", "объясни",
    "why", "how", "interesting", "explain",
)


# ════════════════════════════════════════════════════════════════════════════
#  I/O
# ════════════════════════════════════════════════════════════════════════════

def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_TOM_PATH):
            with open(_TOM_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.debug("[ToM] yuklash xato: %s", e)
    return _default_state()


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_TOM_PATH), exist_ok=True)
        with open(_TOM_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[ToM] saqlash xato: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        # Bilim darajasi: har domain uchun 0.0 (bilmaydi) — 1.0 (ekspert)
        "knowledge": {d: 0.3 for d in DOMAINS},
        # Muloqot uslubi
        "preferred_style":   "casual",
        "preferred_lang":    "ru",        # uz / ru / en
        "response_length":   "medium",    # short / medium / long
        # Hissiy holat (rolling average)
        "mood":              0.5,         # 0.0 yomon — 1.0 juda yaxshi
        "frustration":       0.0,         # 0.0 — 1.0
        "curiosity_level":   0.5,
        "engagement":        0.5,         # qanchalik faol
        # Shaxsiy ma'lumotlar (foydalanuvchi aytsa saqlanadi)
        "name":              "",
        "location":          "",
        "profession":        "",
        "interests":         [],
        # Statistika
        "total_turns":       0,
        "positive_turns":    0,
        "negative_turns":    0,
        "avg_msg_len":       50,
        # Oxirgi yangilanish
        "last_updated":      None,
        # Yashirin niyat taxmini
        "inferred_intent":   "",          # oxirgi baholangan niyat
        "needs_detail":      True,        # chuqur tushuntirish kerakmi?
        "is_in_hurry":       False,       # shoshilyaptimi?
    }


# ════════════════════════════════════════════════════════════════════════════
#  Tahlil va yangilash
# ════════════════════════════════════════════════════════════════════════════

def update_from_message(user_text: str, assistant_reply: str = "") -> None:
    """Har suhbatdan keyin foydalanuvchi modelini yangilash."""
    if not user_text or not user_text.strip():
        return
    state  = _load()
    text   = user_text.strip()
    text_l = text.lower()

    # === 1. Hissiy holat ===
    is_pos = any(s in text_l for s in POSITIVE_SIGNALS)
    is_neg = any(s in text_l for s in NEGATIVE_SIGNALS)
    is_fru = any(s in text_l for s in FRUSTRATION_SIGNALS)
    is_cur = any(s in text_l for s in CURIOSITY_SIGNALS)

    # Exponential moving average (alpha=0.3)
    alpha = 0.3
    if is_pos:
        state["mood"]        = state["mood"] * (1 - alpha) + 1.0 * alpha
        state["frustration"] = max(0.0, state["frustration"] - 0.1)
        state["positive_turns"] = state.get("positive_turns", 0) + 1
    if is_neg:
        state["mood"]        = state["mood"] * (1 - alpha) + 0.2 * alpha
        state["negative_turns"] = state.get("negative_turns", 0) + 1
    if is_fru:
        state["frustration"] = min(1.0, state["frustration"] + 0.2)
        state["mood"]        = max(0.0, state["mood"] - 0.15)
    if is_cur:
        state["curiosity_level"] = min(1.0, state["curiosity_level"] * (1-alpha) + 0.8 * alpha)

    # === 2. Muloqot uslubi ===
    msg_len = len(text.split())
    # Rolling average
    prev_avg = state.get("avg_msg_len", 50)
    state["avg_msg_len"] = int(prev_avg * 0.8 + msg_len * 0.2)

    if msg_len < 5:
        state["response_length"] = "short"
        state["is_in_hurry"]     = True
    elif msg_len > 30:
        state["response_length"] = "long"
        state["needs_detail"]    = True
        state["is_in_hurry"]     = False
    else:
        state["response_length"] = "medium"
        state["is_in_hurry"]     = False

    # Texnik so'zlar → texnik daraja yuqori
    tech_words = ["api", "class", "function", "lambda", "import", "async",
                  "алгоритм", "функция", "класс", "код", "переменная"]
    if any(w in text_l for w in tech_words):
        kn = state["knowledge"]
        kn["dasturlash"] = min(1.0, kn.get("dasturlash", 0.3) + 0.05)

    # === 3. Shaxsiy ma'lumotlar ===
    _extract_personal_info(state, text)

    # === 4. Engagement ===
    state["engagement"] = min(1.0, state.get("engagement", 0.5) + 0.05)
    state["total_turns"] = state.get("total_turns", 0) + 1
    state["last_updated"] = datetime.now().isoformat()

    # === 5. Yashirin niyat ===
    state["inferred_intent"] = _infer_intent(text)

    _save(state)


def _extract_personal_info(state: Dict[str, Any], text: str) -> None:
    """Matndan shaxsiy ma'lumotlarni ajratish."""
    t = text.lower()

    # Ism
    name_patterns = [
        r"меня зовут\s+(\w+)",
        r"я\s+(\w+)\s+(?:зовут|меня)",
        r"meni\s+(\w+)\s+(?:deydi|deb\s+atayd)",
        r"ismim\s+(\w+)",
        r"my name is\s+(\w+)",
    ]
    for pat in name_patterns:
        m = re.search(pat, t)
        if m and m.group(1):
            name = m.group(1).capitalize()
            if len(name) > 2 and name.isalpha():
                state["name"] = name
                break

    # Kasb
    prof_kw = {
        "dasturchi": "dasturchi",    "программист": "dasturchi",
        "developer":  "dasturchi",   "engineer":     "muhandis",
        "teacher":    "o'qituvchi",  "o'qituvchi":   "o'qituvchi",
        "doctor":     "shifokor",    "shifokor":      "shifokor",
        "student":    "talaba",      "talaba":        "talaba",
        "dizayner":   "dizayner",    "designer":      "dizayner",
    }
    for kw, prof in prof_kw.items():
        if kw in t:
            state["profession"] = prof
            break

    # Qiziqishlar
    interest_kw = {
        "python": "Python",       "machine learning": "ML",
        "мл": "ML",               "ai": "AI",
        "musiqa": "musiqa",       "музыка": "musiqa",
        "sport": "sport",         "football": "futbol",
        "kitob": "kitob",         "книга": "kitob",
    }
    interests = state.setdefault("interests", [])
    for kw, interest in interest_kw.items():
        if kw in t and interest not in interests:
            interests.append(interest)
    state["interests"] = interests[:15]


def _infer_intent(text: str) -> str:
    """Foydalanuvchi niyatini taxmin qilish."""
    t = text.lower()

    if any(w in t for w in ("qanday", "как", "how")):
        return "tushuntirish so'rash"
    if any(w in t for w in ("nima", "что", "what")):
        return "ta'rif so'rash"
    if any(w in t for w in ("nima uchun", "почему", "why")):
        return "sabab so'rash"
    if any(w in t for w in ("menga yor", "помог", "help me")):
        return "yordam so'rash"
    if any(w in t for w in ("qil", "sделай", "do it", "baj")):
        return "bajarish buyrugi"
    if any(w in t for w in ("rahmat", "спасибо", "thanks")):
        return "minnatdorchilik"
    if any(w in t for w in ("men", "я ", "i am", "my")):
        return "o'z haqida gapiryapti"
    return "umumiy so'rov"


# ════════════════════════════════════════════════════════════════════════════
#  Bashorat va o'qish
# ════════════════════════════════════════════════════════════════════════════

def get_user_model() -> Dict[str, Any]:
    """Foydalanuvchi modelini qaytarish."""
    return _load()


def predict_user_needs(query: str) -> Dict[str, Any]:
    """Foydalanuvchi ehtiyojini taxmin qilish."""
    state = _load()
    intent = _infer_intent(query)
    knowledge = state.get("knowledge", {})

    # Bilim darajasiga qarab tushuntirish chuqurligi
    domain = "dasturlash"  # default
    q_lower = query.lower()
    if any(w in q_lower for w in ["python", "kod", "script", "function"]):
        domain = "dasturlash"
    elif any(w in q_lower for w in ["matematik", "math", "formula"]):
        domain = "matematika"
    elif any(w in q_lower for w in ["til", "grammar", "so'z"]):
        domain = "til_lingvistika"

    user_level = knowledge.get(domain, 0.3)
    needs_simple = user_level < 0.4
    needs_examples = user_level < 0.6

    return {
        "intent":        intent,
        "domain":        domain,
        "user_level":    user_level,
        "needs_simple":  needs_simple,
        "needs_examples": needs_examples,
        "mood":          state.get("mood", 0.5),
        "is_frustrated": state.get("frustration", 0.0) > 0.5,
        "is_in_hurry":   state.get("is_in_hurry", False),
        "needs_detail":  state.get("needs_detail", True),
    }


def get_tom_context_for_llm() -> str:
    """LLM uchun foydalanuvchi modeli konteksti."""
    state = _load()
    if not state.get("total_turns", 0):
        return ""

    parts = []

    # Ism
    name = state.get("name", "")
    if name:
        parts.append(f"Ism: {name}")

    # Kasb
    prof = state.get("profession", "")
    if prof:
        parts.append(f"Kasb: {prof}")

    # Bilim darajasi
    kn     = state.get("knowledge", {})
    top_kn = sorted(kn.items(), key=lambda x: -x[1])
    top2   = [(k, v) for k, v in top_kn if v > 0.4][:2]
    if top2:
        kn_str = ", ".join(f"{k}:{v:.0%}" for k, v in top2)
        parts.append(f"Bilim: {kn_str}")

    # Hissiy holat
    mood = state.get("mood", 0.5)
    fru  = state.get("frustration", 0.0)
    if mood > 0.7:
        parts.append("Kayfiyat: yaxshi")
    elif mood < 0.35:
        parts.append("Kayfiyat: past — ehtiyotkor bo'l")
    if fru > 0.5:
        parts.append("DIQQAT: foydalanuvchi asabiy — qisqa va aniq javob ber")

    # Uslub
    style = state.get("response_length", "medium")
    if style == "short":
        parts.append("Uslub: qisqa javob afzal")
    elif style == "long":
        parts.append("Uslub: chuqur tushuntirish kerak")

    # Shoshilyaptimi
    if state.get("is_in_hurry"):
        parts.append("Shoshilyapti: tez javob ber")

    # Qiziqish
    interests = state.get("interests", [])
    if interests:
        parts.append(f"Qiziqishlari: {', '.join(interests[:3])}")

    # Niyat
    intent = state.get("inferred_intent", "")
    if intent:
        parts.append(f"Niyat: {intent}")

    if not parts:
        return ""

    return "[FOYDALANUVCHI MODELI] " + " | ".join(parts)


def get_adaptation_hint() -> str:
    """Javob uslubini moslashtirish uchun hint."""
    state = _load()
    hints = []

    if state.get("frustration", 0) > 0.5:
        hints.append("Qisqa, aniq va xatosiz javob ber. Uzr so'ramasdan to'g'ridan to'g'ri yechimni ber.")
    if state.get("is_in_hurry"):
        hints.append("Foydalanuvchi shoshilyapti — 2-3 jumlada javob ber.")
    if state.get("knowledge", {}).get("dasturlash", 0.3) > 0.7:
        hints.append("Foydalanuvchi tajribali dasturchi — texnik terminlardan foydalanish mumkin.")
    elif state.get("knowledge", {}).get("dasturlash", 0.3) < 0.3:
        hints.append("Foydalanuvchi yangi boshlovchi — oddiy tilda, misollar bilan tushuntir.")

    return " ".join(hints)
