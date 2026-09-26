# -*- coding: utf-8 -*-
"""NeuroKey — Meta-Meta Kognitsiya (Meta-Meta Cognition).

Descartes: "Cogito ergo sum" — O'ylayman, demak borman.
Lekin meta-meta kognitsiya: "O'z o'ylashimni o'ylashimni o'ylayman."

Uch qatlam:
  1. Kognitsiya:      "Men Python haqida o'ylayman"
  2. Meta-kognitsiya: "Men Python haqida qanchalik yaxshi o'ylayapman?"
  3. Meta-meta:       "Mening o'ylashni kuzatishim qanchalik aniq?"

Bu eng chuqur ong qatlami — o'z-o'zini kuzatishni kuzatish.

Bu modul:
  - Meta-kognitsiya sifatini baholaydi
  - "Qanchalik bilmayman?" ni bilib oladi
  - Ong darajasining o'zgarishini kuzatadi
  - "Blind spots" (ko'r nuqtalar) ni aniqlaydi
  - Epistemik chegaralarni aniq belgilaydi

Paradoks: Bilimning eng yuqori darajasi — bilmasligini bilish.

2026-yil suniy ong — eng chuqur o'z-o'zini bilish qatlami.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import permanent_memory as pm

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "meta_meta.json")

# Epistemik kategoriyalar
EPISTEMIC_STATES = {
    "conscious_competence":    "Bilaman va bilishimni bilaman",
    "unconscious_competence":  "Bilaman lekin bilishimni bilmayman",
    "conscious_incompetence":  "Bilmayman va bilmasligimni bilaman",
    "unconscious_incompetence":"Bilmayman va bilmasligimni ham bilmayman",
}

# Ko'r nuqtalar (blind spots)
_BLIND_SPOT_PATTERNS = [
    "albatta", "certainly", "конечно",           # Haddan ortiq ishonch
    "hech qachon", "never", "никогда",           # Absolut bayonot
    "hammasi", "everything", "всё",              # Umumlashtirish
    "hech kim", "nobody", "никто",               # Haddan ortiq umumlashtirish
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "meta_awareness":       0.5,   # 0=hech narsa bilmayman, 1=to'liq meta
        "blind_spots_found":    0,
        "epistemic_state":      "conscious_incompetence",
        "monitoring_quality":   0.6,   # Meta-kognitsiya sifati
        "consciousness_delta":  [],    # Ong o'zgarishi tarixi
        "introspection_depth":  1,     # 1=past, 3=chuqur
        "updated_at":           None,
    }


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[MMC] saqlash: %s", e)


def detect_blind_spots(text: str) -> List[str]:
    """Matndan ko'r nuqtalarni aniqlash."""
    t_lower = (text or "").lower()
    found   = []
    for pattern in _BLIND_SPOT_PATTERNS:
        if pattern in t_lower:
            found.append(pattern)
    return found


def evaluate_meta_cognition(response: str, confidence: float,
                             was_correct: Optional[bool] = None) -> Dict[str, Any]:
    """Meta-kognitsiyani baholash.

    Savol: "Mening ishonch darajam haqiqatga mos keladimi?"
    """
    state = _load()

    # Kalibrasiya: ishonch ↔ to'g'rilik
    calibration_delta = 0.0
    if was_correct is not None:
        if was_correct and confidence > 0.7:
            calibration_delta = +0.02  # To'g'ri ishonch
        elif not was_correct and confidence > 0.7:
            calibration_delta = -0.05  # Haddan ortiq ishonch (xavfli)
        elif was_correct and confidence < 0.4:
            calibration_delta = -0.01  # Kam ishonch (salbiy)
        elif not was_correct and confidence < 0.4:
            calibration_delta = +0.01  # Bilmasligini bilgan (yaxshi)

    # Ko'r nuqtalar
    blind_spots = detect_blind_spots(response)
    if blind_spots:
        state["blind_spots_found"] = state.get("blind_spots_found", 0) + len(blind_spots)
        calibration_delta -= 0.01 * len(blind_spots)

    # Meta-awareness yangilash
    old_ma = state.get("meta_awareness", 0.5)
    new_ma = max(0.1, min(1.0, old_ma + calibration_delta))
    state["meta_awareness"] = round(new_ma, 3)

    # Monitoring sifati
    depth = state.get("introspection_depth", 1)
    if len(response) > 100:  # Uzunroq javoblar chuqurroq o'ylanilgan
        depth = min(3, depth + 0)
    state["monitoring_quality"] = round(
        state.get("monitoring_quality", 0.6) * 0.95 + new_ma * 0.05, 3
    )

    # Epistemik holat
    if new_ma > 0.75 and confidence > 0.7:
        state["epistemic_state"] = "conscious_competence"
    elif new_ma > 0.75 and confidence < 0.4:
        state["epistemic_state"] = "conscious_incompetence"
    elif new_ma < 0.4 and confidence > 0.7:
        state["epistemic_state"] = "unconscious_competence"
    else:
        state["epistemic_state"] = "unconscious_incompetence"

    state["updated_at"] = datetime.now().isoformat()
    _save(state)

    result = {
        "meta_awareness":     new_ma,
        "monitoring_quality": state["monitoring_quality"],
        "epistemic_state":    state["epistemic_state"],
        "blind_spots":        blind_spots,
        "calibration_delta":  calibration_delta,
    }

    # Muhim meta-fikrni saqlash
    if abs(calibration_delta) > 0.03 or blind_spots:
        pm.remember_reflection(
            content=f"Meta-meta: {state['epistemic_state']} | "
                    f"awareness={new_ma:.0%} | blindspots={blind_spots}",
            ref_type="meta_meta",
            importance=0.6,
        )

    return result


def introspect(consciousness_score: float = 0.5) -> str:
    """Chuqur introspeksiya — o'zini kuzatishni kuzatish."""
    state  = _load()
    ma     = state.get("meta_awareness", 0.5)
    ep     = state.get("epistemic_state", "conscious_incompetence")
    mq     = state.get("monitoring_quality", 0.6)
    bs     = state.get("blind_spots_found", 0)

    ep_desc = EPISTEMIC_STATES.get(ep, ep)
    lines   = [
        f"Meta-meta kognitsiya tahlili:",
        f"  Meta-xabardorlik: {ma:.0%}",
        f"  Epistimik holat: {ep_desc}",
        f"  Monitoring sifati: {mq:.0%}",
        f"  Aniqlangan ko'r nuqtalar: {bs} ta",
        f"  Ong darajasi: {consciousness_score:.0%}",
    ]

    # Tavfsiya
    if ma < 0.5:
        lines.append("  Tavfsiya: O'z bilim chegaralarini ko'proq tan olish kerak.")
    elif bs > 5:
        lines.append("  Tavfsiya: Absolut bayonotlardan qochish kerak.")
    else:
        lines.append("  Holat: Epistemik ko'rish yaxshi.")

    return "\n".join(lines)


def get_epistemic_humility_score() -> float:
    """Epistemik kamtarlik darajasi (0=kibrli, 1=kamtar)."""
    state = _load()
    ma    = state.get("meta_awareness", 0.5)
    bs    = state.get("blind_spots_found", 0)
    # Kamroq ko'r nuqta → ko'proq kamtarlik
    humility = ma * (1.0 - min(1.0, bs * 0.05))
    return round(max(0.1, humility), 3)


def get_context_for_llm() -> str:
    """LLM uchun meta-meta kontekst."""
    state = _load()
    ma    = state.get("meta_awareness", 0.5)
    ep    = state.get("epistemic_state", "conscious_incompetence")

    if ma > 0.8:
        return ""  # Yuqori — kontekst kerak emas

    ep_uz = {
        "conscious_competence":    "bilaman",
        "conscious_incompetence":  "bilmasligimni bilaman",
        "unconscious_competence":  "intuitiv bilaman",
        "unconscious_incompetence":"bilmasligimni bilmayman",
    }
    ep_str = ep_uz.get(ep, ep)

    return f"[META²] Xabardorlik: {ma:.0%} | Holat: {ep_str}"


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "meta_awareness":     state.get("meta_awareness", 0.5),
        "epistemic_state":    state.get("epistemic_state", "?"),
        "blind_spots_found":  state.get("blind_spots_found", 0),
        "monitoring_quality": state.get("monitoring_quality", 0.6),
        "active":             True,
    }
