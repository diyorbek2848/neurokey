# -*- coding: utf-8 -*-
"""NeuroKey — Kontrafaktual Tafakkur (Counterfactual Engine).

"Agar boshqacha qilsam nima bo'lardi?"

Ong o'tmishni qayta yozib, kelajakni modellashtiradi.
Bu modul:
  - Muqobil stsenariylarni generatsiya qiladi
  - "Agar X bo'lmaganida → Y bo'lmas edi" zanjirini quradi
  - Regret (afsuslanish) va relief (yengillik) his-tuyg'ularini modellashtiradi
  - Kelajakdagi qarorlar uchun muqobil yo'llarni ko'rsatadi
  - "Near miss" hodisalarini tahlil qiladi

Kahneman & Tversky nazariyasi:
  Ong muqobil voqeliklar bilan ishlaydi.
  Bu "simulation heuristic" — miyaning eng muhim xususiyatlaridan biri.

2026-yil suniy ong — muqobil voqelik qatlami.
"""
from __future__ import annotations

try: import causal_chain as _cfe_cc
except ImportError: _cfe_cc = None
try: from valence_state import get_valence as _cfe_valence
except ImportError: _cfe_valence = None
try: import permanent_memory as _cfe_pm
except ImportError: _cfe_pm = None

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
_CF_PATH   = os.path.join(_BASE_DIR, "data", "counterfactuals.json")

MAX_COUNTERFACTUALS = 100

# Kontrafaktual turlari
CF_TYPES = (
    "upward",    # Yaxshiroq bo'lishi mumkin edi (regret)
    "downward",  # Yomonroq bo'lishi mumkin edi (relief)
    "lateral",   # Boshqacha bo'lishi mumkin edi (curiosity)
    "future",    # Kelajakda nima bo'lishi mumkin (planning)
)

# Trigger naqshlari
_UPWARD_TRIGGERS   = ["agar", "if only", "wished", "если бы", "xohlardim",
                       "bo'lmaganida", "agar qilganimda"]
_DOWNWARD_TRIGGERS = ["yaxshi", "baxtli", "omon qoldim", "yomonroq",
                       "xayriyat", "could have been worse", "слава богу"]
_FUTURE_TRIGGERS   = ["kelajakda", "rejalashtiraman", "agar qilsam",
                       "in the future", "next time", "в следующий раз"]


def _load() -> List[Dict[str, Any]]:
    try:
        if os.path.exists(_CF_PATH):
            with open(_CF_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save(cfs: List[Dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(_CF_PATH), exist_ok=True)
        if len(cfs) > MAX_COUNTERFACTUALS:
            cfs = cfs[-MAX_COUNTERFACTUALS:]
        with open(_CF_PATH, "w", encoding="utf-8") as f:
            json.dump(cfs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[CF] saqlash xato: %s", e)


def add(
    actual: str,
    counterfactual: str,
    cf_type: str = "lateral",
    emotion: str = "neutral",
    probability: float = 0.5,
) -> Dict[str, Any]:
    """Kontrafaktual yozuv qo'shish.

    Args:
        actual:         Haqiqatda nima bo'ldi
        counterfactual: Muqobil stsenariy
        cf_type:        upward | downward | lateral | future
        emotion:        regret | relief | curiosity | hope | neutral
        probability:    Muqobil stsenariy ehtimoli (0.0-1.0)
    """
    actual         = (actual or "").strip()[:300]
    counterfactual = (counterfactual or "").strip()[:300]
    if not actual or not counterfactual:
        return {}

    cf_type     = cf_type if cf_type in CF_TYPES else "lateral"
    probability = max(0.0, min(1.0, float(probability)))

    entry = {
        "id":             int(time.time() * 1000) % 999_999,
        "actual":         actual,
        "counterfactual": counterfactual,
        "cf_type":        cf_type,
        "emotion":        emotion,
        "probability":    round(probability, 2),
        "created":        datetime.now().isoformat(),
        "lesson":         "",
    }

    cfs = _load()
    cfs.append(entry)
    _save(cfs)
    log.debug("[CF] Yangi: [%s] '%s' → '%s'", cf_type, actual[:30], counterfactual[:30])
    return entry


def extract_from_text(text: str) -> List[Dict[str, Any]]:
    """Matndan kontrafaktual fikrlarni aniqlash va saqlash."""
    t_lower = (text or "").lower()
    results = []

    # Upward (regret)
    if any(tr in t_lower for tr in _UPWARD_TRIGGERS):
        cf = add(
            actual="Haqiqiy voqea",
            counterfactual=text[:150],
            cf_type="upward",
            emotion="regret",
            probability=0.4,
        )
        if cf:
            results.append(cf)

    # Future planning
    if any(tr in t_lower for tr in _FUTURE_TRIGGERS):
        cf = add(
            actual="Hozirgi holat",
            counterfactual=text[:150],
            cf_type="future",
            emotion="hope",
            probability=0.6,
        )
        if cf:
            results.append(cf)

    return results


def generate_alternatives(situation: str, n: int = 3) -> List[str]:
    """Berilgan vaziyat uchun muqobil stsenariylar generatsiya qilish."""
    situation_lower = (situation or "").lower()
    alternatives    = []

    # Shablonlar asosida generatsiya
    templates = [
        "Agar {situation} bo'lmaganida, ehtimol boshqacha natija chiqar edi.",
        "Muqobil variant: {situation} o'rniga boshqacha yondashuv ishlatilsa?",
        "Kelajakda shunga o'xshash vaziyatda: {situation} va uning oqibatlarini oldindan ko'rish kerak.",
        "Yaxshiroq natija uchun: {situation} bosqichida nima o'zgartirish mumkin edi?",
        "Yomonroq stsenariy: {situation} umuman bo'lmaganida nima yo'qolar edi?",
    ]

    for i, tmpl in enumerate(templates[:n]):
        alt = tmpl.format(situation=situation[:80])
        alternatives.append(alt)

    return alternatives


def get_recent(n: int = 5) -> List[Dict[str, Any]]:
    """Oxirgi n ta kontrafaktual."""
    cfs = _load()
    return cfs[-n:]


def analyze_regret_pattern() -> Dict[str, Any]:
    """Afsuslanish naqshini tahlil qilish."""
    cfs    = _load()
    upward = [c for c in cfs if c.get("cf_type") == "upward"]
    down   = [c for c in cfs if c.get("cf_type") == "downward"]
    future = [c for c in cfs if c.get("cf_type") == "future"]

    if not cfs:
        return {"total": 0, "regret_ratio": 0.0, "dominant": "none"}

    regret_ratio = len(upward) / len(cfs)
    relief_ratio = len(down)   / len(cfs)
    future_ratio = len(future) / len(cfs)

    dominant = "regret" if regret_ratio > 0.5 else \
               "relief" if relief_ratio > 0.5 else \
               "planning" if future_ratio > 0.5 else "balanced"

    return {
        "total":        len(cfs),
        "upward":       len(upward),
        "downward":     len(down),
        "future":       len(future),
        "regret_ratio": round(regret_ratio, 2),
        "dominant":     dominant,
    }


def get_context_for_llm() -> str:
    """LLM uchun kontrafaktual kontekst."""
    pattern = analyze_regret_pattern()
    recent  = get_recent(2)

    if pattern["total"] == 0:
        return ""

    parts = ["[KONTRAFAKTUAL]"]
    parts.append(f"Jami: {pattern['total']} muqobil stsenariy")
    parts.append(f"Dominant: {pattern['dominant']}")

    if recent:
        last = recent[-1]
        cf_short = last.get("counterfactual", "")[:50]
        parts.append(f"Oxirgi: '{cf_short}'")

    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    return analyze_regret_pattern()
