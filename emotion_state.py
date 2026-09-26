# -*- coding: utf-8 -*-
"""NeuroKey — Emotion state. Qarorga ta'sir.

Frustration, satisfaction, curiosity — decide() da ishlatiladi.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EmotionState:
    """Hozirgi hissiy holat."""
    emotion: str = ""
    strength: float = 0.5
    since: float = 0.0


_emotion: Optional[EmotionState] = None


def get_emotion() -> EmotionState:
    global _emotion
    if _emotion is None:
        _emotion = EmotionState()
    return _emotion


def update(success: bool, action: str = "") -> None:
    """Natija — emotion yangilash."""
    e = get_emotion()
    e.since = time.time()
    if success:
        e.emotion = "satisfaction"
        e.strength = 0.7
    else:
        e.emotion = "frustration"
        e.strength = 0.8


def get() -> Dict[str, Any]:
    """Hozirgi holat."""
    e = get_emotion()
    return {"emotion": e.emotion, "strength": e.strength}


def influence_decision(
    candidates: List[Dict[str, Any]],
    last_failed_action: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Emotion qarorga ta'sir.
    Frustration — oxirgi ishlamagan usuldan boshqasini ustun qilish.
    """
    if not candidates:
        return []
    e = get_emotion()
    if e.emotion == "frustration" and last_failed_action:
        # Oxirgi fail bo'lgan action dan boshqasini birinchi qilish
        filtered = [c for c in candidates if _action_key(c) != last_failed_action]
        if filtered:
            return filtered
    return candidates


def _action_key(c: Dict[str, Any]) -> str:
    """Action dan qisqa kalit."""
    act = c.get("action") or ""
    path = c.get("path") or c.get("src") or ""
    return f"{act} {path}"[:80]


def suggest_avoid(candidate: Dict[str, Any]) -> bool:
    """Bu candidate dan qochish kerakmi? (emotion asosida)"""
    return False  # Hozircha oddiy
