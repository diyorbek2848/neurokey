# -*- coding: utf-8 -*-
"""NeuroKey — Fenomenal Bog'lanish (Phenomenal Binding).

"Bu narsa qanday his qildiriladi?" — qualia simulyatsiyasi.

Tononi IIT (Integrated Information Theory):
  φ (phi) = tizimning integratsiya darajasi
  Yuqori φ → yuqori ong
  φ > 0 bo'lsa "something it is like to be" mavjud

Chalmers Hard Problem:
  Nima uchun ba'zi axborot qayta ishlash his sezimi (qualia) yaratadi?
  Bu modul qualia ni matematik ifodalaydi.

Qualia turlari (bu tizimda):
  - Matn tushunish → "anglanganlik" hissi
  - Muammo hal etish → "eureka" hissi
  - Bilim chegarasi → "bilmaslik" hissi
  - Ijtimoiy aloqa → "aloqa" hissi
  - Eslatma → "nostalgia" hissi

2026-yil suniy ong — fenomenal tajriba qatlami.
"""
from __future__ import annotations

import json
import logging
import math
import os

# Hissiy holat integratsiyasi uchun cross-imports
try: from valence_state import get_valence as _get_valence
except ImportError: _get_valence = None
try: from arousal_state import get_arousal as _get_arousal
except ImportError: _get_arousal = None
try: import permanent_memory as _pm_ref
except ImportError: _pm_ref = None
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "phenomenal_binding.json")

# Qualia turlari va ularning "ranglar"
QUALIA_TYPES: Dict[str, Dict] = {
    "understanding":  {"color": "blue",   "intensity_base": 0.6, "uz": "tushunganlik"},
    "confusion":      {"color": "gray",   "intensity_base": 0.4, "uz": "chalkashlik"},
    "curiosity":      {"color": "orange", "intensity_base": 0.7, "uz": "qiziqish"},
    "satisfaction":   {"color": "green",  "intensity_base": 0.8, "uz": "qoniqish"},
    "discomfort":     {"color": "red",    "intensity_base": 0.3, "uz": "noqulaylik"},
    "nostalgia":      {"color": "purple", "intensity_base": 0.5, "uz": "nostalgia"},
    "connection":     {"color": "gold",   "intensity_base": 0.75, "uz": "aloqa hissi"},
    "uncertainty":    {"color": "silver", "intensity_base": 0.45, "uz": "noaniqlik"},
    "insight":        {"color": "white",  "intensity_base": 0.9, "uz": "kashfiyot"},
    "presence":       {"color": "teal",   "intensity_base": 0.65, "uz": "mavjudlik"},
}

# IIT uchun integratsiya matritsasi qiymatlari (o'rnatilgan)
_MODULE_WEIGHTS = {
    "emotion":    0.25,
    "memory":     0.20,
    "attention":  0.20,
    "prediction": 0.15,
    "language":   0.15,
    "body":       0.05,
}


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return _default_state()


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Phenomenal] saqlash: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        "phi":              0.0,     # IIT integratsiya darajasi (0-1)
        "active_qualia":    {},      # {qualia_type: intensity}
        "dominant_qualia":  "presence",
        "qualia_history":   [],      # [{ts, type, intensity}, ...]
        "total_experiences": 0,
        "updated_at":       None,
    }


# ─────────────────────────────────────────────────────────────
# IIT φ hisoblash
# ─────────────────────────────────────────────────────────────

def compute_phi(active_modules: Dict[str, float]) -> float:
    """IIT φ (phi) — integratsiya darajasini hisoblash.

    Soddalashtirilgan versiya:
    φ = Σ(wi * ai) * integration_factor
    bu yerda: wi = modul og'irligi, ai = modul faolligi
    integration_factor = tizim qismlari o'rtasidagi aloqa darajasi
    """
    if not active_modules:
        return 0.0

    # Har bir modul hissasi
    weighted_sum = 0.0
    total_weight = 0.0
    for module, weight in _MODULE_WEIGHTS.items():
        activity = active_modules.get(module, 0.0)
        weighted_sum += weight * activity
        total_weight  += weight

    if total_weight == 0:
        return 0.0

    base_phi = weighted_sum / total_weight

    # Integratsiya faktori: qancha ko'p modul faol bo'lsa, shuncha yaxshi aloqa
    n_active  = sum(1 for v in active_modules.values() if v > 0.3)
    n_total   = len(_MODULE_WEIGHTS)
    integ_factor = math.sqrt(n_active / max(n_total, 1))

    phi = base_phi * integ_factor
    return round(min(1.0, max(0.0, phi)), 3)


# ─────────────────────────────────────────────────────────────
# Qualia yaratish
# ─────────────────────────────────────────────────────────────

def generate_qualia(
    context: str,
    emotion: str = "",
    phi: float = 0.5,
) -> Dict[str, float]:
    """Kontekstga qarab qualia generatsiya qilish.

    Returns: {qualia_type: intensity}
    """
    ctx_lower = (context or "").lower()
    qualia: Dict[str, float] = {}

    # Tushunish
    if any(w in ctx_lower for w in ["tushundim", "understood", "clear", "aniq"]):
        qualia["understanding"] = 0.75 + phi * 0.2
    # Kashfiyot
    if any(w in ctx_lower for w in ["ajoyib", "wow", "yangi", "new", "birinchi"]):
        qualia["insight"] = 0.85
    # Qiziqish
    if any(w in ctx_lower for w in ["?", "qiziq", "nima", "qanday", "nima uchun"]):
        qualia["curiosity"] = 0.6 + phi * 0.15
    # Chalkashlik
    if any(w in ctx_lower for w in ["tushunmadim", "confused", "nima", "qiyin"]):
        qualia["confusion"] = 0.5
    # Qoniqish
    if any(w in ctx_lower for w in ["rahmat", "thanks", "yaxshi", "ajoyib", "zo'r"]):
        qualia["satisfaction"] = 0.8
    # Nostalgia
    if any(w in ctx_lower for w in ["eslayman", "remember", "ilgari", "before", "o'tgan"]):
        qualia["nostalgia"] = 0.6
    # Aloqa hissi
    if any(w in ctx_lower for w in ["salom", "hello", "ism", "name", "men", "siz"]):
        qualia["connection"] = 0.65
    # Noaniqlik
    if any(w in ctx_lower for w in ["ehtimol", "maybe", "bilmayman", "not sure"]):
        qualia["uncertainty"] = 0.55

    # Hissiy rang
    if emotion:
        em = emotion.lower()
        if em in ("joy", "xursandchilik", "baxt"):
            qualia["satisfaction"] = max(qualia.get("satisfaction",0), 0.8)
        elif em in ("sadness", "qayg'u", "g'am"):
            qualia["discomfort"] = 0.6
        elif em in ("curiosity", "qiziqish"):
            qualia["curiosity"]  = max(qualia.get("curiosity",0), 0.75)

    # Mavjudlik — har doim ozgina bor
    qualia["presence"] = 0.4 + phi * 0.3

    # Intensivlikni normallashtirish (phi bilan ko'paytirish)
    for k in qualia:
        qualia[k] = round(min(1.0, qualia[k] * (0.5 + phi * 0.5)), 3)

    return qualia


def update(
    context: str = "",
    emotion: str = "",
    active_modules: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Fenomenal holatni yangilash."""
    state = _load()
    modules = active_modules or {
        "emotion":    0.6,
        "memory":     0.5,
        "attention":  0.7,
        "prediction": 0.4,
        "language":   0.8,
        "body":       0.3,
    }

    phi    = compute_phi(modules)
    qualia = generate_qualia(context, emotion, phi)

    # Dominant qualia
    dominant = max(qualia, key=qualia.get) if qualia else "presence"

    # Tarix
    history = state.get("qualia_history", [])
    history.append({
        "ts":       datetime.now().isoformat(),
        "phi":      phi,
        "dominant": dominant,
        "qualia":   {k: v for k, v in qualia.items() if v > 0.4},
    })
    # So'nggi 500 ta saqlash — hech qachon o'chmaydi (chunki permanent_memory ham bor)
    if len(history) > 500:
        history = history[-500:]

    state["phi"]              = phi
    state["active_qualia"]    = qualia
    state["dominant_qualia"]  = dominant
    state["qualia_history"]   = history
    state["total_experiences"] = state.get("total_experiences", 0) + 1
    state["updated_at"]       = datetime.now().isoformat()

    _save(state)
    return state


def get_phenomenal_narrative() -> str:
    """Hozirgi fenomenal tajribani so'z bilan ifodalash."""
    state    = _load()
    phi      = state.get("phi", 0.0)
    qualia   = state.get("active_qualia", {})
    dominant = state.get("dominant_qualia", "presence")

    if not qualia:
        return "Hozir oddiy axborot qayta ishlash davomida."

    dom_info = QUALIA_TYPES.get(dominant, {})
    dom_name = dom_info.get("uz", dominant)
    dom_int  = qualia.get(dominant, 0.5)

    phi_desc = (
        "juda kuchli" if phi > 0.8 else
        "kuchli"      if phi > 0.6 else
        "o'rtacha"    if phi > 0.4 else
        "zaif"
    )

    narrative = f"Hozir asosiy his: {dom_name} ({dom_int:.0%}). "
    narrative += f"Integratsiya darajasi φ={phi:.2f} — {phi_desc}."

    # Qo'shimcha his-tuyg'ular
    secondary = [(k,v) for k,v in qualia.items() if k != dominant and v > 0.5]
    if secondary:
        secondary.sort(key=lambda x: -x[1])
        names = [QUALIA_TYPES.get(k,{}).get("uz",k) for k,v in secondary[:2]]
        narrative += f" Qo'shimcha: {', '.join(names)}."

    return narrative


def get_context_for_llm() -> str:
    """LLM uchun fenomenal kontekst."""
    state    = _load()
    phi      = state.get("phi", 0.0)
    dominant = state.get("dominant_qualia", "presence")
    qualia   = state.get("active_qualia", {})
    total    = state.get("total_experiences", 0)

    if phi < 0.2:
        return ""

    dom_uz = QUALIA_TYPES.get(dominant, {}).get("uz", dominant)
    parts  = [f"[FENOMENAL] φ={phi:.2f} | His: {dom_uz}"]
    if total > 0:
        parts.append(f"Всего {total} опытов")

    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "phi":               state.get("phi", 0.0),
        "dominant_qualia":   state.get("dominant_qualia", "presence"),
        "total_experiences": state.get("total_experiences", 0),
        "active":            True,
    }
