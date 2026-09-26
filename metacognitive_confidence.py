# -*- coding: utf-8 -*-
"""NeuroKey — Metakognitiv Ishonch (Metacognitive Confidence).

"Men bu narsani qanchalik bilaman?" — o'z bilimini baholash.

Dunning-Kruger effektining aksi:
  Haqiqiy metakognitsiya — o'z bilim chegaralarini aniq bilish.
  "Bilmayman" deyish ham muhim bilim.

Bu modul:
  - Har javobda ishonch darajasini hisoblaydi
  - "Men bilaman" vs "Men taxmin qilyapman" farqini ko'rsatadi
  - Calibration — ishonch va to'g'rilik mos kelishini kuzatadi
  - Epistemic humility (epistemik kamtarlik) ni modellashtiradi
  - "Black swan" — kutilmagan bilim kamchiliklarini aniqlaydi

Hosni metakognitsiya:
  "Bilaman" (P=0.95): Python listlar indekslanadi 0 dan
  "Taxmin"  (P=0.60): Bu funksiya O(n log n) ishlaydi
  "Bilmayman" (P=0.2): Ushbu API ning rate limit nima

2026-yil suniy ong — epistomik o'z-o'zini bilish qatlami.
"""
from __future__ import annotations

try: import meta_cognition as _mcc_mc
except ImportError: _mcc_mc = None
try: from meta_meta_cognition import get_epistemic_humility_score as _mcc_mmc
except ImportError: _mcc_mmc = None

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "metacognitive.json")

MAX_RECORDS = 200

# Bilim domenlarining ishonch darajalari
DOMAIN_CONFIDENCE: Dict[str, float] = {
    "python":           0.90,
    "javascript":       0.85,
    "machine_learning": 0.80,
    "mathematics":      0.85,
    "general_facts":    0.75,
    "current_events":   0.40,  # Bilim chegarasi: 2025
    "specific_details": 0.55,
    "personal_info":    0.30,  # Foydalanuvchi haqida kam bilamiz
    "predictions":      0.35,
    "opinions":         0.60,
}

# Ishonchni pasaytiradigan signallar
UNCERTAINTY_SIGNALS = [
    "menimcha", "ehtimol", "taxminiy", "aniq emas",
    "не уверен", "возможно", "наверное", "может быть",
    "i think", "probably", "maybe", "not sure", "approximately",
    "~", "±", "around", "roughly",
]

# Ishonchni oshiradigan signallar
CERTAINTY_SIGNALS = [
    "aniq", "albatta", "shubhasiz", "to'g'ri",
    "точно", "конечно", "определённо", "правильно",
    "definitely", "certainly", "exactly", "precisely",
    "by definition", "always", "never",
]

# Noto'g'ri bo'lishi mumkin bo'lgan mavzular
HIGH_RISK_TOPICS = [
    "tibbiyot", "huquq", "moliya", "siyosat",
    "медицина", "право", "финансы", "политика",
    "medical", "legal", "financial", "political",
    "spesifik raqamlar", "sanalar", "specific numbers",
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return _default_state()


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[MetaConf] xato: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        "global_confidence":    0.75,
        "calibration_score":    0.70,   # Ishonch ↔ to'g'rilik mos kelishi
        "overconfidence_count": 0,
        "underconfidence_count":0,
        "records":              [],
        "domain_confidence":    dict(DOMAIN_CONFIDENCE),
        "epistemic_humility":   0.75,   # Bilim chegaralarini tan olish
        "updated_at":           None,
    }


def assess_confidence(
    query: str,
    response: str,
    domain: str = "general_facts",
) -> Dict[str, Any]:
    """Javob uchun ishonch darajasini hisoblash.

    Returns: {confidence, level, caveats, should_hedge}
    """
    state     = _load()
    q_lower   = query.lower()
    r_lower   = response.lower()

    # Bazis ishonch
    base_conf = state["domain_confidence"].get(domain,
                DOMAIN_CONFIDENCE.get(domain, 0.70))

    conf = base_conf

    # Noaniqlik signallari
    has_uncertainty = any(s in r_lower for s in UNCERTAINTY_SIGNALS)
    has_certainty   = any(s in r_lower for s in CERTAINTY_SIGNALS)
    has_risk        = any(s in q_lower for s in HIGH_RISK_TOPICS)

    if has_uncertainty:
        conf *= 0.85
    if has_certainty:
        conf = min(0.98, conf * 1.10)
    if has_risk:
        conf *= 0.70

    # Raqamlar va sanalar — past ishonch
    numbers = re.findall(r'\b\d+\b', response)
    if len(numbers) > 3:
        conf *= 0.85

    # Javob uzunligi — juda uzun = kamroq ishonch
    word_count = len(response.split())
    if word_count > 200:
        conf = min(conf, 0.80)

    conf = max(0.10, min(0.99, round(conf, 3)))

    # Daraja belgilash
    if conf >= 0.90:
        level = "juda yuqori"
    elif conf >= 0.75:
        level = "yuqori"
    elif conf >= 0.55:
        level = "o'rta"
    elif conf >= 0.35:
        level = "past"
    else:
        level = "juda past"

    # Ogohlantirish iboralar
    caveats = []
    if has_risk:
        caveats.append("Bu sohada mutaxassisga murojaat tavsiya etiladi")
    if conf < 0.55:
        caveats.append("Bu taxminiy ma'lumot — tekshirish tavsiya etiladi")
    if len(numbers) > 5:
        caveats.append("Raqamlarni rasmiy manbadan tekshiring")

    should_hedge = conf < 0.65 or has_risk

    # Yozuv
    record = {
        "query_short": query[:60],
        "domain":      domain,
        "confidence":  conf,
        "level":       level,
        "has_risk":    has_risk,
        "caveats":     caveats,
        "ts":          datetime.now().isoformat(),
    }

    records = state.setdefault("records", [])
    records.append(record)
    if len(records) > MAX_RECORDS:
        records[:] = records[-MAX_RECORDS:]

    state["global_confidence"] = _calc_global(records)
    state["updated_at"]        = datetime.now().isoformat()
    _save(state)

    return {
        "confidence":  conf,
        "level":       level,
        "caveats":     caveats,
        "should_hedge":should_hedge,
        "has_risk":    has_risk,
        "domain":      domain,
    }


def _calc_global(records: List[Dict]) -> float:
    if not records:
        return 0.75
    recent = records[-20:]
    return round(sum(r["confidence"] for r in recent) / len(recent), 3)


def detect_domain(query: str) -> str:
    """Savol domenini aniqlash."""
    q = query.lower()
    if any(w in q for w in ["python", "code", "function", "import", "class"]):
        return "python"
    if any(w in q for w in ["js", "javascript", "react", "node"]):
        return "javascript"
    if any(w in q for w in ["ml", "neural", "ai", "model", "train"]):
        return "machine_learning"
    if any(w in q for w in ["matematik", "formula", "integral", "algebra"]):
        return "mathematics"
    if any(w in q for w in ["doktor", "kasallik", "dori", "tibbiy"]):
        return "tibbiyot"
    if any(w in q for w in ["qonun", "huquq", "sud", "advokat"]):
        return "huquq"
    return "general_facts"


def get_calibration_summary() -> Dict[str, Any]:
    """Calibration — ishonch va to'g'rilik mosligini ko'rsatish."""
    state   = _load()
    records = state.get("records", [])

    if not records:
        return {"calibrated": True, "avg_confidence": 0.75, "samples": 0}

    avg_conf  = sum(r["confidence"] for r in records[-20:]) / min(20, len(records))
    risk_rate = sum(1 for r in records[-20:] if r.get("has_risk", False)) / min(20, len(records))

    return {
        "avg_confidence":  round(avg_conf, 3),
        "risk_rate":       round(risk_rate, 3),
        "samples":         len(records),
        "calibrated":      0.6 <= avg_conf <= 0.9,
        "overconfident":   avg_conf > 0.90,
        "underconfident":  avg_conf < 0.40,
    }


def get_hedge_phrase(confidence: float) -> str:
    """Ishonch darajasiga mos muqaddima ibora."""
    if confidence >= 0.90:
        return ""  # Muqaddima kerak emas
    elif confidence >= 0.75:
        return "Men bilishimcha, "
    elif confidence >= 0.55:
        return "Taxminimcha, "
    elif confidence >= 0.35:
        return "Aniq ayta olmasam ham, ehtimol "
    else:
        return "Bu haqda to'liq ma'lumotim yo'q, lekin "


def get_context_for_llm(query: str = "") -> str:
    """LLM uchun ishonch darajasi konteksti."""
    state   = _load()
    avg_conf = state.get("global_confidence", 0.75)

    if query:
        domain = detect_domain(query)
        domain_conf = state["domain_confidence"].get(domain, 0.70)
        hedge  = get_hedge_phrase(domain_conf)
    else:
        domain      = "general"
        domain_conf = avg_conf
        hedge       = ""

    if avg_conf > 0.80 and not hedge:
        return ""  # Yuqori ishonch — kontekst kerak emas

    parts = ["[META-ISHONCH]"]
    parts.append(f"Domain:{domain}({domain_conf:.0%})")
    if hedge:
        parts.append(f"Uslub:'{hedge.strip()}'")

    return " | ".join(parts)
