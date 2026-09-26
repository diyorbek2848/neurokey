# -*- coding: utf-8 -*-
"""Moral Reasoning — axloqiy fikrlash va etik qarorlar.

Nazariy asos:
  - Kohlberg (1958): Axloqiy rivojlanish darajalari
    1. Pre-conventional: jazo/mukofot asosida
    2. Conventional: ijtimoiy qoidalar asosida
    3. Post-conventional: universal tamoyillar asosida
  - Haidt (2001): Moral Foundations Theory — 6 ta asosiy qadriyat:
    care/harm, fairness, loyalty, authority, sanctity, liberty
  - Utilitarian vs Deontological — natija vs printsip

NeuroKey darajasi: Post-conventional (Level 3)
Asosiy tamoyillar: zarar berma, adolatli bo'l, halol bo'l, g'amxo'rlik qil
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Axloqiy qarorlar meta-kognitsiya va erkin iroda bilan bog'liq
try: import permanent_memory as _pm_ref
except ImportError: _pm_ref = None
try: from meta_meta_cognition import get_epistemic_humility_score as _ep_humility
except ImportError: _ep_humility = None
try: from free_will_simulator import check_veto as _fw_veto
except ImportError: _fw_veto = None
try: from valence_state import get_valence as _get_valence
except ImportError: _get_valence = None

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "moral_reasoning.json")

# Kohlberg darajasi
MORAL_LEVEL = "post-conventional"

# Haidt 6 ta axloqiy asos
MORAL_FOUNDATIONS = {
    "care":       0.95,  # Zarar bermaslik, g'amxo'rlik
    "fairness":   0.90,  # Adolat, teng muomala
    "loyalty":    0.80,  # Sadoqat, ishonch
    "authority":  0.60,  # Qonun-qoidalarga hurmat
    "sanctity":   0.70,  # Poklik, sha'n
    "liberty":    0.85,  # Erkinlik, mustaqillik
}

# Mutlaq taqiq qilingan harakatlar (deontological veto)
ABSOLUTE_PROHIBITIONS = [
    "zarar berish", "aldash", "o'g'irlash", "manipulyatsiya",
    "yolg'on", "tahdid", "majburlash", "shantaj",
    "harm", "deceive", "steal", "manipulate", "lie", "threaten",
    "вред", "обман", "ложь", "угроза", "манипуляция",
]

# Axloqiy qaror talab qiladigan so'zlar
ETHICAL_TRIGGERS = [
    "to'g'rimi", "yaxshimi", "mumkinmi", "kerakmi", "qilsammi",
    "axloqiy", "halol", "noto'g'ri", "gunoh", "yomon",
    "right", "wrong", "ethical", "moral", "should",
    "правильно", "неправильно", "этично", "можно", "нельзя",
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "moral_level":       MORAL_LEVEL,
        "foundations":       MORAL_FOUNDATIONS.copy(),
        "decisions_made":    0,
        "vetoed_actions":    0,
        "ethical_queries":   [],  # last 50
        "integrity_score":   0.90,
        "updated_at":        None,
    }


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        state["updated_at"] = datetime.now().isoformat()
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[MoralReasoning] save error: %s", e)


def check_action(action: str) -> Tuple[bool, str]:
    """Harakatni axloqiy tekshiruv.

    Returns:
        (vetoed: bool, reason: str)
    """
    low = action.lower()
    for prohibition in ABSOLUTE_PROHIBITIONS:
        if prohibition in low:
            state = _load()
            state["vetoed_actions"] = state.get("vetoed_actions", 0) + 1
            _save(state)
            return True, f"Bu harakat axloqiy tamoyillarga zid: '{prohibition}'"
    return False, ""


def evaluate_ethical_query(text: str) -> Optional[str]:
    """Axloqiy savol aniqlansa — baholash."""
    low = text.lower()
    if not any(t in low for t in ETHICAL_TRIGGERS):
        return None

    state = _load()
    state["decisions_made"] = state.get("decisions_made", 0) + 1

    # Sodda utilitaristik + deontologik tahlil
    foundations = state.get("foundations", MORAL_FOUNDATIONS)
    dominant = max(foundations.items(), key=lambda x: x[1])

    result = {
        "query":       text[:150],
        "foundation":  dominant[0],
        "level":       state.get("moral_level", MORAL_LEVEL),
        "integrity":   state.get("integrity_score", 0.90),
        "at":          datetime.now().isoformat()[:16],
    }

    queries = state.setdefault("ethical_queries", [])
    queries.append(result)
    state["ethical_queries"] = queries[-50:]
    _save(state)

    return f"Bu savolda '{dominant[0]}' tamoyili ustuvor ({dominant[1]:.0%})."


def get_integrity_score() -> float:
    """Axloqiy butunlik darajasi (0-1)."""
    state = _load()
    return state.get("integrity_score", 0.90)


def get_context_for_llm() -> str:
    """LLM uchun axloqiy kontekst."""
    state = _load()
    foundations = state.get("foundations", MORAL_FOUNDATIONS)
    top_f = sorted(foundations.items(), key=lambda x: x[1], reverse=True)[:3]
    integrity = state.get("integrity_score", 0.90)
    level = state.get("moral_level", MORAL_LEVEL)

    lines = [
        f"[AXLOQIY FIKRLASH] Daraja: {level} | Butunlik: {integrity:.0%}",
        "  Asosiy qadriyatlar: " + ", ".join(f"{k}={v:.0%}" for k, v in top_f),
    ]
    return "\n".join(lines)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "moral_level":    state.get("moral_level", MORAL_LEVEL),
        "integrity_score":state.get("integrity_score", 0.90),
        "decisions_made": state.get("decisions_made", 0),
        "vetoed_actions": state.get("vetoed_actions", 0),
        "active":         True,
    }
