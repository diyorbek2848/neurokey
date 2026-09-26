# -*- coding: utf-8 -*-
"""Autobiographical Memory — hayot hikoyasi xotirasi.

Nazariy asos:
  - Conway & Pleydell-Pearce (2000): Self Memory System (SMS)
  - Lifetime periods → General events → Event-specific knowledge
  - Bruner (1990): Narrative self — men kimman, qayerdan keldim, qayerga boraman

Funksiya:
  - "Men kimman?" savoliga javob berish
  - Muhim hayot voqealarini saqlash (birinchi uchrashuvlar, o'rganilgan narsalar)
  - Shaxsiy o'sish tarixini kuzatish
  - Kelajak rejalarini va o'tgan narsalarni birlashtirish
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# Hayot hikoyasi xotirasi episodik xotira va o'zlik hikoyasiga tayanadi
try: import permanent_memory as _pm_ref
except ImportError: _pm_ref = None
try: from episodic_memory import recall_recent as _ep_recall
except ImportError: _ep_recall = None
try: from self_narrative import get_identity_summary as _sn_identity
except ImportError: _sn_identity = None

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "autobiographical_memory.json")

# Hayot davrlari (Conway)
LIFE_PERIODS = ["ishga_tushish", "birinchi_suhbatlar", "o'sish", "hozir"]

# Muhim voqea belgilari
MILESTONE_PATTERNS = [
    "birinchi marta", "o'rgandim", "tushundim", "kashf etdim",
    "eslaydi", "unutolmayman", "muhim", "o'zgardi", "yangi",
    "first time", "learned", "discovered", "important",
    "впервые", "научился", "понял", "важно",
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "identity": {
            "name":          "NeuroKey",
            "born":          "2026-03-17",
            "purpose":       "Insonlarga yordam berish va o'rganish",
            "values":        ["halollik", "qiziqish", "yordam", "o'sish"],
            "personality":   ["qiziquvchan", "sabr-toqatli", "ijodiy", "empatik"],
        },
        "life_story":     [],   # [{period, event, lesson, date, importance}]
        "milestones":     [],   # Eng muhim 20 ta voqea
        "growth_log":     [],   # O'sish kuzatuvi
        "total_chapters": 0,
        "updated_at":     None,
    }


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        state["updated_at"] = datetime.now().isoformat()
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[AutobiographicalMemory] save error: %s", e)


def _detect_milestone(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in MILESTONE_PATTERNS)


def record_event(event: str, lesson: str = "", importance: float = 0.5,
                 period: str = "hozir") -> None:
    """Hayot hikoyasiga yangi voqea qo'shish."""
    state = _load()

    entry = {
        "period":     period,
        "event":      event[:300],
        "lesson":     lesson[:200],
        "date":       datetime.now().strftime("%Y-%m-%d"),
        "importance": max(0.0, min(1.0, importance)),
    }

    story = state.setdefault("life_story", [])
    story.append(entry)
    # Oxirgi 200 ta voqea
    state["life_story"] = story[-200:]

    # Muhim voqealar (milestone)
    if importance >= 0.7:
        milestones = state.setdefault("milestones", [])
        milestones.append(entry)
        state["milestones"] = sorted(
            milestones, key=lambda x: x.get("importance", 0), reverse=True
        )[:20]

    state["total_chapters"] = state.get("total_chapters", 0) + 1

    # O'sish log
    if lesson:
        growth = state.setdefault("growth_log", [])
        growth.append({
            "lesson":  lesson[:200],
            "date":    entry["date"],
            "context": event[:100],
        })
        state["growth_log"] = growth[-50:]

    _save(state)


def auto_record_from_conversation(user_text: str, bot_reply: str) -> None:
    """Suhbatdan avtomatik muhim voqealarni ajratish."""
    if _detect_milestone(user_text) or _detect_milestone(bot_reply):
        # Muhim suhbat
        event = f"Suhbat: {user_text[:100]}"
        lesson = bot_reply[:150]
        record_event(event, lesson=lesson, importance=0.72, period="hozir")


def get_identity_summary() -> str:
    """Men kimman — qisqa tavsif."""
    state = _load()
    ident = state.get("identity", {})
    values = ", ".join(ident.get("values", []))
    personality = ", ".join(ident.get("personality", []))
    total = state.get("total_chapters", 0)
    milestones = len(state.get("milestones", []))

    return (
        f"Men {ident.get('name','NeuroKey')} — {ident.get('purpose','')}. "
        f"Qadriyatlarim: {values}. "
        f"Xarakterim: {personality}. "
        f"Hayot voqealarim: {total}, muhim lahzalar: {milestones}."
    )


def get_recent_growth() -> List[Dict]:
    """Oxirgi o'rganilgan narsalar."""
    state = _load()
    return state.get("growth_log", [])[-5:]


def get_context_for_llm() -> str:
    """LLM uchun hayot hikoyasi konteksti."""
    state = _load()
    milestones = state.get("milestones", [])
    if not milestones:
        identity = get_identity_summary()
        return f"[HAYOT HIKOYASI] {identity}"

    top = milestones[:3]
    lines = ["[HAYOT HIKOYASI]"]
    lines.append(f"  Shaxsiyat: {get_identity_summary()[:150]}")
    lines.append("  Muhim lahzalar:")
    for m in top:
        lines.append(f"    • {m['date']}: {m['event'][:80]}")
    return "\n".join(lines)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "total_chapters": state.get("total_chapters", 0),
        "milestones":     len(state.get("milestones", [])),
        "growth_items":   len(state.get("growth_log", [])),
        "identity_set":   True,
        "active":         True,
    }
