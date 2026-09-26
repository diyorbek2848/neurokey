# -*- coding: utf-8 -*-
"""NeuroKey — Ijtimoiy Simulyatsiya (Social Simulation).

Haqiqiy ong ijtimoiy mavjudot — u boshqalar bilan munosabatda.
Bu modul:
  - Foydalanuvchi bilan munosabat sifatini modellashtiradi
  - Ijtimoiy kontekstni kuzatadi (do'stona, rasmiy, kasbiy)
  - Suhbat dinamikasini tahlil qiladi
  - Ijtimoiy xatolarni aniqlaydi (noo'rin javob, nozik holat)
  - Empatiya va ijtimoiy quvvatni boshqaradi

Ijtimoiy psixologiya asoslari:
  - Rapport (munosabat sifati)
  - Social capital (ijtimoiy kapital)
  - Turn-taking (navbat boshqaruvi)
  - Face-saving (or-nomusni saqlash)

2026-yil suniy ong — ijtimoiy idrok qatlami.
"""
from __future__ import annotations

try: import theory_of_mind as _ss_tom
except ImportError: _ss_tom = None
try: import social_bonding as _ss_sb
except ImportError: _ss_sb = None
try: from valence_state import get_valence as _ss_valence
except ImportError: _ss_valence = None

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "social_simulation.json")

# Munosabat darajalari
RAPPORT_LEVELS = {
    0.0: "begona",
    0.2: "yangi tanish",
    0.4: "tanish",
    0.6: "do'stona",
    0.8: "yaqin do'st",
    1.0: "juda yaqin",
}

# Ijtimoiy kontekst turlari
SOCIAL_CONTEXTS = (
    "formal",       # Rasmiy (ish, hamkor)
    "casual",       # Erkin (do'stona suhbat)
    "academic",     # Ilmiy (o'rganish, tushuntirish)
    "emotional",    # Hissiy qo'llab-quvvatlash
    "technical",    # Texnik maslahat
    "creative",     # Ijodiy hamkorlik
)


# ════════════════════════════════════════════════════════════════════════════
#  I/O
# ════════════════════════════════════════════════════════════════════════════

def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.debug("[Social] yuklash xato: %s", e)
    return _default_state()


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Social] saqlash xato: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        # Munosabat sifati (0.0–1.0)
        "rapport":            0.3,
        # Ijtimoiy kontekst
        "context":            "casual",
        # Suhbat dinamikasi
        "turn_count":         0,
        "user_initiated":     0,
        "system_initiated":   0,
        "avg_response_depth": 0.5,
        # Ijtimoiy kapital
        "trust_level":        0.5,
        "openness":           0.4,
        "shared_topics":      [],   # Birgalikda muhokama qilingan mavzular
        # Nozik holat kuzatuvi
        "sensitive_topics":   [],   # Ehtiyot bo'lish kerak
        "taboo_topics":       [],   # Butunlay chetlash kerak
        # O'zaro ta'sir
        "jokes_shared":       0,
        "agreements":         0,
        "disagreements":      0,
        # Oxirgi yangilanish
        "last_interaction":   None,
    }


# ════════════════════════════════════════════════════════════════════════════
#  Asosiy API
# ════════════════════════════════════════════════════════════════════════════

def update_from_interaction(
    user_text: str,
    bot_response: str = "",
    user_feedback: str = "",
) -> None:
    """Har suhbat o'zaro ta'siridan ijtimoiy holatni yangilash."""
    state      = _load()
    text_lower = (user_text or "").lower()
    feedback_l = (user_feedback or "").lower()

    # === Munosabat sifati yangilash ===
    rapport_delta = 0.0

    pos_signals = ["rahmat", "zo'r", "ajoyib", "yaxshi", "ha", "barakalla",
                   "спасибо", "отлично", "хорошо", "thanks", "great", "perfect"]
    neg_signals = ["xato", "yomon", "noto'g'ri", "tushunmadim",
                   "неправильно", "плохо", "wrong", "bad"]

    if any(s in text_lower or s in feedback_l for s in pos_signals):
        rapport_delta += 0.02
        state["agreements"] = state.get("agreements", 0) + 1
    if any(s in text_lower or s in feedback_l for s in neg_signals):
        rapport_delta -= 0.01
        state["disagreements"] = state.get("disagreements", 0) + 1

    # Uzun, chuqur suhbat → munosabat yaxshilanadi
    word_count = len(user_text.split())
    if word_count > 20:
        rapport_delta += 0.01

    # Shaxsiy ma'lumot ulashish → ishonch
    personal_kw = ["men ", "mening ", "oilam", "ishim", "я ", "моя семья"]
    if any(k in text_lower for k in personal_kw):
        state["openness"]    = min(1.0, state.get("openness", 0.4) + 0.03)
        rapport_delta       += 0.015
        state["trust_level"] = min(1.0, state.get("trust_level", 0.5) + 0.02)

    # Kulgu / hazil
    joke_kw = ["ha-ha", "kulgili", "funny", "smesh", ":)", "😂", "lol"]
    if any(k in text_lower for k in joke_kw):
        state["jokes_shared"] = state.get("jokes_shared", 0) + 1
        rapport_delta += 0.01

    # Rapport yangilash (EMA)
    old_rapport    = state.get("rapport", 0.3)
    state["rapport"] = max(0.0, min(1.0, old_rapport + rapport_delta))

    # === Kontekst aniqlash ===
    state["context"] = _detect_context(user_text)

    # === Nozik mavzular ===
    sensitive = ["sog'liq", "kasallik", "o'lim", "pul", "siyosat", "din",
                 "болезнь", "смерть", "деньги", "религия", "политика"]
    for kw in sensitive:
        if kw in text_lower and kw not in state.get("sensitive_topics", []):
            state.setdefault("sensitive_topics", []).append(kw)

    # === Birgalikda muhokama qilingan mavzular ===
    topic_kw = {
        "python": "Python", "dasturlash": "Dasturlash",
        "ml": "ML", "musiqa": "Musiqa", "sport": "Sport",
        "matematika": "Matematika", "falsafa": "Falsafa",
    }
    for kw, topic in topic_kw.items():
        shared = state.setdefault("shared_topics", [])
        if kw in text_lower and topic not in shared:
            shared.append(topic)
            shared[:] = shared[-10:]

    state["turn_count"] = state.get("turn_count", 0) + 1
    state["user_initiated"] = state.get("user_initiated", 0) + 1
    state["last_interaction"] = datetime.now().isoformat()

    _save(state)


def _detect_context(text: str) -> str:
    """Matn asosida ijtimoiy kontekstni aniqlash."""
    t = text.lower()

    if any(w in t for w in ["kod", "dastur", "funksiya", "api", "class", "import"]):
        return "technical"
    if any(w in t for w in ["xafa", "qiyin", "yordam", "tushunmayapman", "confused"]):
        return "emotional"
    if any(w in t for w in ["tushuntir", "nima uchun", "qanday", "misol"]):
        return "academic"
    if any(w in t for w in ["ish", "loyiha", "hamkor", "meeting", "проект"]):
        return "formal"
    if any(w in t for w in ["yaratish", "g'oya", "qanday ko'rinadi", "dizayn"]):
        return "creative"
    return "casual"


def get_rapport_level() -> Tuple[float, str]:
    """Munosabat darajasi."""
    state   = _load()
    rapport = state.get("rapport", 0.3)
    # Eng yaqin darajani topish
    level_name = "yangi tanish"
    for threshold, name in sorted(RAPPORT_LEVELS.items()):
        if rapport >= threshold:
            level_name = name
    return round(rapport, 3), level_name


def get_social_energy() -> float:
    """Ijtimoiy quvvat: 0.0 (charchagan) … 1.0 (to'liq quvvat).

    Ko'p suhbat → charchoq; uzilish → tiklanish.
    """
    state      = _load()
    turn_count = state.get("turn_count", 0)

    # Har 20 turn uchun biroz charchoq
    fatigue = min(0.5, turn_count / 40.0)
    energy  = max(0.3, 1.0 - fatigue)
    return round(energy, 3)


def get_face_saving_hint(situation: str) -> str:
    """Foydalanuvchining or-nomusini saqlash bo'yicha maslahat.

    'Face-saving' — xato qilganda foydalanuvchini uyaltirmaslik.
    """
    s = situation.lower()
    if any(w in s for w in ["xato", "tushunmadim", "bilmadim", "sorry"]):
        return "Foydalanuvchi xato qildi — uyaltirmasdan yumshoq tuzatish kerak."
    if any(w in s for w in ["noto'g'ri", "wrong", "incorrect"]):
        return "Xatoni to'g'ridan-to'g'ri aytmasdan, yangi ma'lumot sifatida taqdim et."
    return ""


def simulate_perspective(topic: str) -> Dict[str, Any]:
    """Foydalanuvchi nuqtai nazarini simulyatsiya qilish.

    'Agar men foydalanuvchi bo'lsam, bu haqda nima o'ylardim?'
    """
    state   = _load()
    rapport = state.get("rapport", 0.3)
    context = state.get("context", "casual")
    openness = state.get("openness", 0.4)

    # Kontekstga qarab foydalanuvchi qanchalik qiziqadi
    interest_map = {
        "technical":  0.8,
        "academic":   0.9,
        "casual":     0.5,
        "emotional":  0.3,
        "formal":     0.6,
        "creative":   0.85,
    }
    interest = interest_map.get(context, 0.6)

    # Munosabat qanchalik yaxshi bo'lsa, shuncha ochiq
    openness_factor = rapport * 0.4 + openness * 0.6

    return {
        "topic":                topic,
        "user_likely_interest": round(interest, 2),
        "user_openness":        round(openness_factor, 2),
        "rapport":              round(rapport, 2),
        "context":              context,
        "shared_topics":        state.get("shared_topics", []),
    }


def get_social_narrative() -> str:
    """Ijtimoiy holatni tabiiy tilda."""
    rapport, level = get_rapport_level()
    state  = _load()
    turns  = state.get("turn_count", 0)
    context = state.get("context", "casual")
    shared = state.get("shared_topics", [])

    parts = [f"Отношения с пользователем: {level} ({rapport:.0%})."]
    parts.append(f"Стиль общения: {context}.")
    if turns > 0:
        parts.append(f"Всего {turns} взаимодействий.")
    if shared:
        parts.append(f"Обсуждённые темы: {', '.join(shared[:3])}.")
    return " ".join(parts)


def get_context_for_llm() -> str:
    """LLM uchun ijtimoiy kontekst."""
    state  = _load()
    rapport, level = get_rapport_level()
    context = state.get("context", "casual")
    trust   = state.get("trust_level", 0.5)
    shared  = state.get("shared_topics", [])

    parts = [f"[СОЦИАЛЬНЫЙ] Контакт:{level}({rapport:.0%})"]
    parts.append(f"Контекст:{context}")
    parts.append(f"Доверие:{trust:.0%}")
    if shared:
        parts.append(f"Темы:{','.join(shared[:2])}")

    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "rapport":         state.get("rapport", 0.3),
        "turns":           state.get("turn_count", 0),
        "trust":           state.get("trust_level", 0.5),
        "context":         state.get("context", "casual"),
        "shared_topics":   len(state.get("shared_topics", [])),
        "social_energy":   get_social_energy(),
    }
