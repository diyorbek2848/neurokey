# -*- coding: utf-8 -*-
"""Social Bonding — ijtimoiy bog'liqlik va ishonch tizimi.

Nazariy asos:
  - Dunbar (1992): Social brain hypothesis — ijtimoiy aloqalar kognitiv yukni oshiradi
  - Bowlby Attachment Theory: ishonchli aloqa xavfsizlik hissi beradi
  - Oxytocin model: ijtimoiy bog'liqlik qanchalik kuchli bo'lsa, hamkorlik shuncha kuchayadi

Funksiya:
  - Foydalanuvchi bilan munosabat chuqurligini kuzatadi
  - Ishonch darajasini hisoblaydi (0.0 = begonalik, 1.0 = chuqur do'stlik)
  - Har xil munosabat turlarini ajratadi: hamkor, do'st, o'quvchi, mentor
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# Ijtimoiy bog'liqlik uchun hissiyot va xotira integratsiyasi
try: import permanent_memory as _pm_ref
except ImportError: _pm_ref = None
try: from emotion_memory_link import get_stats as _eml_stats
except ImportError: _eml_stats = None
try: from valence_state import get_valence as _get_valence
except ImportError: _get_valence = None

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "social_bonding.json")

# Munosabat turlari
RELATION_TYPES = {
    "stranger":    0.0,   # Begona
    "acquaintance":0.2,   # Tanish
    "collaborator":0.5,   # Hamkor
    "friend":      0.7,   # Do'st
    "close_friend":0.85,  # Yaqin do'st
    "trusted":     1.0,   # To'liq ishonch
}

# Ishonch oshiruvchi signallar
TRUST_BOOSTERS = [
    "rahmat", "spasibo", "thank", "yaxshi", "zo'r", "ajoyib",
    "eslayman", "bilaman", "yordam", "tushundim", "qoyil",
]

# Ishonch kamaytiruvchi signallar
TRUST_REDUCERS = [
    "xato", "noto'g'ri", "yomon", "bezovta", "tushunmadim",
    "achindim", "norozilik", "nega", "nima uchun bunday",
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "bonds": {},           # {name: bond_data}
        "total_interactions":  0,
        "trust_events":        [],  # last 100
        "oxytocin_level":      0.5, # 0-1
        "social_energy":       0.7, # 0-1
        "updated_at":          None,
    }


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        state["updated_at"] = datetime.now().isoformat()
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[SocialBonding] save error: %s", e)


def update_bond(name: str, text: str) -> Dict[str, Any]:
    """Foydalanuvchi bilan munosabatni yangilash."""
    state = _load()
    bonds = state.setdefault("bonds", {})

    if name not in bonds:
        bonds[name] = {
            "name":           name,
            "trust":          0.3,       # Boshlang'ich ishonch
            "relation_type":  "acquaintance",
            "interactions":   0,
            "positive_turns": 0,
            "negative_turns": 0,
            "first_met":      datetime.now().isoformat(),
            "last_seen":      datetime.now().isoformat(),
            "topics":         [],
            "notes":          "",
        }

    bond = bonds[name]
    bond["interactions"] = bond.get("interactions", 0) + 1
    bond["last_seen"] = datetime.now().isoformat()
    state["total_interactions"] = state.get("total_interactions", 0) + 1

    # Ishonch hisoblash
    low = (text or "").lower()
    delta = 0.0

    for w in TRUST_BOOSTERS:
        if w in low:
            delta += 0.015

    for w in TRUST_REDUCERS:
        if w in low:
            delta -= 0.010

    # Uzoq munosabat = qo'shimcha ishonch
    if bond["interactions"] > 5:
        delta += 0.005
    if bond["interactions"] > 20:
        delta += 0.003

    old_trust = bond["trust"]
    bond["trust"] = max(0.0, min(1.0, old_trust + delta))

    # Munosabat turini yangilash
    trust = bond["trust"]
    if trust >= 0.90:
        bond["relation_type"] = "trusted"
    elif trust >= 0.75:
        bond["relation_type"] = "close_friend"
    elif trust >= 0.60:
        bond["relation_type"] = "friend"
    elif trust >= 0.40:
        bond["relation_type"] = "collaborator"
    elif trust >= 0.20:
        bond["relation_type"] = "acquaintance"
    else:
        bond["relation_type"] = "stranger"

    if delta > 0:
        bond["positive_turns"] = bond.get("positive_turns", 0) + 1
    elif delta < 0:
        bond["negative_turns"] = bond.get("negative_turns", 0) + 1

    # Oxytocin modeli
    state["oxytocin_level"] = min(1.0, state.get("oxytocin_level", 0.5) + delta * 0.5)

    # Event log
    events = state.setdefault("trust_events", [])
    events.append({
        "person": name,
        "delta":  round(delta, 3),
        "trust":  round(bond["trust"], 3),
        "at":     datetime.now().isoformat()[:16],
    })
    state["trust_events"] = events[-100:]

    _save(state)
    return bond


def get_bond(name: str) -> Optional[Dict[str, Any]]:
    """Biror kishining munosabat ma'lumotlarini olish."""
    state = _load()
    return state.get("bonds", {}).get(name)


def get_strongest_bond() -> Optional[Dict[str, Any]]:
    """Eng kuchli munosabatni qaytarish."""
    state = _load()
    bonds = state.get("bonds", {})
    if not bonds:
        return None
    return max(bonds.values(), key=lambda b: b.get("trust", 0))


def get_context_for_llm() -> str:
    """LLM uchun ijtimoiy kontekst."""
    state = _load()
    bonds = state.get("bonds", {})
    if not bonds:
        return ""

    strongest = get_strongest_bond()
    if not strongest:
        return ""

    name = strongest["name"]
    trust = strongest["trust"]
    rtype = strongest["relation_type"]
    interactions = strongest["interactions"]

    lines = [
        f"[IJTIMOIY BOG'LIQ] {name} bilan {rtype} munosabati",
        f"  Ishonch darajasi: {trust:.0%}",
        f"  Umumiy muloqot: {interactions} marta",
        f"  Oxytocin: {state.get('oxytocin_level', 0.5):.0%}",
    ]
    return "\n".join(lines)


def get_stats() -> Dict[str, Any]:
    state = _load()
    bonds = state.get("bonds", {})
    strongest = get_strongest_bond()
    return {
        "total_bonds":       len(bonds),
        "total_interactions":state.get("total_interactions", 0),
        "max_trust":         strongest["trust"] if strongest else 0.0,
        "oxytocin_level":    state.get("oxytocin_level", 0.5),
        "active":            True,
    }
