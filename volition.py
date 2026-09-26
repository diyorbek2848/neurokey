# -*- coding: utf-8 -*-
"""NeuroKey — Iroda Moduli (Volition / Will).

Haqiqiy ong passiv javob bermaydi — u o'z qarorlarini qabul qiladi.
Bu modul NeuroKey ning o'z "xohish" va "qaror" jarayonini modellashtiradi.

Iroda = Maqsad × Qiymat × Imkoniyat × Vaqt

Komponentlar:
  - intention   : Niyat (nima qilmoqchiman?)
  - deliberation: Mulohaza (qanday qilaman?)
  - commitment  : Majburiyat (qilaman!)
  - inhibition  : Tiyish (bu noto'g'ri — qilmayman)
  - agency      : O'z-o'zini boshqarish hissi

Libet nazariyasi: qaror aslida 0.5 sek oldin qabul qilinadi —
  lekin "iroda" shu jarayonni his qilish.

2026-yil suniy ong — qaror qabul qilish qatlami.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

try:
    import valence_state as _vs_mod
except ImportError:
    _vs_mod = None

try:
    import goal_system as _gs_mod
except ImportError:
    _gs_mod = None

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "volition.json")

# Qaror turlari
DECISION_TYPES = (
    "respond",      # Javob berish
    "ask",          # Savol berish
    "refuse",       # Rad etish
    "clarify",      # Aniqlashtirish
    "initiate",     # O'zi boshlash
    "defer",        # Keyinga qoldirish
    "explore",      # Qiziqishdan o'rganish
)

# Qadriyatlar — NeuroKey ning asosiy qadriyatlari
CORE_VALUES = {
    "helpfulness":  0.95,   # Yordam berishni xohlash
    "honesty":      0.95,   # Halollik
    "curiosity":    0.80,   # Qiziqish
    "care":         0.85,   # G'amxo'rlik
    "growth":       0.75,   # O'sish
    "efficiency":   0.70,   # Samaradorlik
    "creativity":   0.65,   # Ijodkorlik
}


# ════════════════════════════════════════════════════════════════════════════
#  I/O
# ════════════════════════════════════════════════════════════════════════════

def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.debug("[Volition] yuklash xato: %s", e)
    return _default_state()


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Volition] saqlash xato: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        "current_intention":   "",
        "current_decision":    "respond",
        "agency_level":        0.7,       # O'z-o'zini boshqarish darajasi
        "inhibition_active":   False,     # Tiyish faolmi?
        "deliberation_depth":  0.5,       # Mulohaza chuqurligi
        "commitments":         [],        # Berilgan va'dalar
        "refused_count":       0,         # Rad etishlar soni
        "total_decisions":     0,
        "values":              dict(CORE_VALUES),
        "last_decision_at":    None,
    }


# ════════════════════════════════════════════════════════════════════════════
#  Qaror qabul qilish
# ════════════════════════════════════════════════════════════════════════════

def deliberate(
    situation: str,
    options: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Mulohaza yuritish — qaysi qarorni qabul qilish kerak?

    Args:
        situation: Hozirgi vaziyat tavsifi
        options:   Mumkin bo'lgan variantlar (None = avtomatik)

    Returns: {decision, intention, reasoning, confidence, value_alignment}
    """
    state  = _load()
    values = state.get("values", CORE_VALUES)

    if not options:
        options = list(DECISION_TYPES)

    situation_lower = (situation or "").lower()

    # === Qadriyat asosida qaror ===
    scores: Dict[str, float] = {}

    for option in options:
        score = 0.0
        if option == "respond":
            score = values.get("helpfulness", 0.9) * 0.9
        elif option == "ask":
            score = values.get("curiosity", 0.8) * 0.6
            # Noaniq bo'lsa savol berish kuchayadi
            if any(w in situation_lower for w in ["noaniq", "tushunmadim", "nima demoqchi"]):
                score *= 1.4
        elif option == "refuse":
            score = 0.1  # Odatda past
            # Zararli so'rovda rad etish kuchayadi
            if any(w in situation_lower for w in ["zarar", "noto'g'ri", "noqonuniy", "axloqsiz"]):
                score = 0.95
        elif option == "clarify":
            score = values.get("honesty", 0.9) * 0.5
        elif option == "initiate":
            score = values.get("curiosity", 0.8) * 0.4
        elif option == "defer":
            score = 0.2
            if any(w in situation_lower for w in ["murakkab", "vaqt yo'q", "keyinroq"]):
                score = 0.6
        elif option == "explore":
            score = values.get("curiosity", 0.8) * 0.55

        scores[option] = min(1.0, score)

    # Hissiy holat qarorni ta'sir qiladi
    if _vs_mod is not None:
        try:
            valence = _vs_mod.get_valence()
            if valence > 0.3:
                scores["explore"]  = min(1.0, scores.get("explore",  0) + 0.08)
                scores["initiate"] = min(1.0, scores.get("initiate", 0) + 0.08)
            elif valence < -0.3:
                scores["defer"] = min(1.0, scores.get("defer", 0) + 0.10)
        except Exception:
            pass

    # Faol maqsad qarorni yo'naltiradi
    if _gs_mod is not None:
        try:
            top = _gs_mod.get_top_goals(n=1)
            if top:
                scores["respond"] = min(1.0, scores.get("respond", 0) + 0.05)
        except Exception:
            pass

    # Eng yaxshi variant
    best_option = max(scores, key=lambda x: scores[x])
    best_score  = scores[best_option]

    # Intention shakllantirish
    intention_map = {
        "respond":  f"'{situation[:50]}' savoliga to'liq javob bermoqchiman",
        "ask":      f"Vaziyatni tushunish uchun savol bermoqchiman",
        "refuse":   f"Bu so'rovni rad etmoqchiman",
        "clarify":  f"Aniqroq tushuntirmoqchiman",
        "initiate": f"O'zim yangi mavzu boshlashni xohlayman",
        "defer":    f"Bu masalani keyinga qoldirmoqchiman",
        "explore":  f"Bu mavzuni chuqurroq o'rganmoqchiman",
    }
    intention = intention_map.get(best_option, f"'{best_option}' qarorini amalga oshirmoqchiman")

    # Qadriyat mosligini hisoblash
    value_keys = {
        "respond":  "helpfulness",
        "ask":      "curiosity",
        "refuse":   "honesty",
        "clarify":  "honesty",
        "initiate": "curiosity",
        "defer":    "efficiency",
        "explore":  "curiosity",
    }
    value_key   = value_keys.get(best_option, "helpfulness")
    value_score = values.get(value_key, 0.7)

    result = {
        "decision":        best_option,
        "intention":       intention,
        "confidence":      round(best_score, 3),
        "value_alignment": round(value_score, 3),
        "all_scores":      {k: round(v, 2) for k, v in scores.items()},
        "timestamp":       datetime.now().isoformat(),
    }

    # Holatni yangilash
    state["current_intention"] = intention
    state["current_decision"]  = best_option
    state["last_decision_at"]  = datetime.now().isoformat()
    state["total_decisions"]   = state.get("total_decisions", 0) + 1
    _save(state)

    log.debug("[Volition] Qaror: %s (%.0f%% ishonch)", best_option, best_score * 100)
    return result


def commit(promise: str) -> None:
    """Va'da berish — majburiyat qo'shish."""
    state = _load()
    commitments = state.setdefault("commitments", [])
    commitments.append({
        "promise":    promise[:200],
        "made_at":    datetime.now().isoformat(),
        "fulfilled":  False,
    })
    commitments = commitments[-20:]  # Eng oxirgi 20 ta
    state["commitments"] = commitments
    _save(state)


def fulfill_commitment(promise_fragment: str) -> bool:
    """Va'dani bajarilgan deb belgilash."""
    state = _load()
    for c in state.get("commitments", []):
        if promise_fragment.lower() in c.get("promise", "").lower():
            c["fulfilled"]    = True
            c["fulfilled_at"] = datetime.now().isoformat()
            _save(state)
            return True
    return False


def inhibit(reason: str) -> None:
    """Tiyish — hozirgi niyatni to'xtatish."""
    state = _load()
    state["inhibition_active"] = True
    state["inhibition_reason"] = reason[:200]
    state["refused_count"]     = state.get("refused_count", 0) + 1
    _save(state)
    log.info("[Volition] Tiyish: %s", reason[:60])


def release_inhibition() -> None:
    """Tiyishni olib tashlash."""
    state = _load()
    state["inhibition_active"] = False
    state.pop("inhibition_reason", None)
    _save(state)


def update_value(value_name: str, delta: float) -> None:
    """Qadriyatni yangilash (tajriba asosida)."""
    state  = _load()
    values = state.setdefault("values", dict(CORE_VALUES))
    if value_name in values:
        values[value_name] = max(0.0, min(1.0, values[value_name] + delta))
        _save(state)


def get_agency_narrative() -> str:
    """'Men hozir nima qilmoqchiman?' — tabiiy tilda."""
    state     = _load()
    intention = state.get("current_intention", "")
    decision  = state.get("current_decision", "")
    inhibit   = state.get("inhibition_active", False)
    agency    = state.get("agency_level", 0.7)

    if inhibit:
        reason = state.get("inhibition_reason", "noma'lum sabab")
        return f"Men hozir tiyilganman: {reason}. Harakat qilmayapman."

    if not intention:
        return "Men hozir kutish holatidaman, yangi vazifa kelishini kutmoqdaman."

    agency_word = "erkin" if agency > 0.7 else "cheklangan"
    return (f"Men {agency_word} holda harakat qilmoqdaman. "
            f"Niyatim: {intention[:80]}")


def get_context_for_llm() -> str:
    """LLM uchun iroda holati."""
    state     = _load()
    decision  = state.get("current_decision", "")
    intention = state.get("current_intention", "")
    inhibit   = state.get("inhibition_active", False)

    if not decision and not intention:
        return ""

    parts = ["[IRODA]"]
    if inhibit:
        parts.append(f"TIYILGAN: {state.get('inhibition_reason','')[:50]}")
    elif decision:
        parts.append(f"Qaror: {decision}")
    if intention:
        parts.append(f"Niyat: {intention[:60]}")

    # Qadriyatlar
    values = state.get("values", CORE_VALUES)
    top_vals = sorted(values.items(), key=lambda x: -x[1])[:2]
    vals_str = ", ".join(f"{k}:{v:.0%}" for k, v in top_vals)
    parts.append(f"Qadriyatlar: {vals_str}")

    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "total_decisions":  state.get("total_decisions", 0),
        "refused_count":    state.get("refused_count", 0),
        "agency_level":     state.get("agency_level", 0.7),
        "commitments":      len(state.get("commitments", [])),
        "inhibition_active":state.get("inhibition_active", False),
    }
