# -*- coding: utf-8 -*-
"""NeuroKey — Kayfiyat. Davomiylik. spontaneity_rate(mood).

Yaxshi — ko'proq spontan. Yomon — ehtiyotkor. Zerikkan — yangilik qidirish.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class MoodState:
    """Kayfiyat — uzoq davom etadi."""
    mood: str = "neutral"  # good, bad, bored, curious, neutral
    strength: float = 0.5
    since: float = 0.0


_mood: Optional[MoodState] = None


def get_mood() -> MoodState:
    global _mood
    if _mood is None:
        _mood = MoodState()
    return _mood


def update(success: bool, action: str = "") -> None:
    """Natija — mood ga ta'sir."""
    m = get_mood()
    m.since = time.time()
    if success:
        if m.mood == "neutral":
            m.mood = "good"
            m.strength = 0.6
        elif m.mood == "good":
            m.strength = min(1.0, m.strength + 0.1)
    else:
        m.mood = "bad"
        m.strength = 0.7


def set_mood(mood: str, strength: float = 0.5) -> None:
    """Kayfiyatni qo'lda o'rnatish."""
    m = get_mood()
    m.mood = mood
    m.strength = max(0.0, min(1.0, strength))
    m.since = time.time()


def spontaneity_rate(mood: Optional[Dict[str, Any]] = None) -> float:
    """Spontan tanlash ehtimoli 0.0–0.35.
    Yaxshi — ko'proq spontan. Yomon — ehtiyotkor. Zerikkan — o'rtacha."""
    m = get_mood() if mood is None else None
    if m is None and mood:
        mood_val = mood.get("mood", "neutral")
    else:
        mood_val = m.mood if m else "neutral"
    rates = {
        "good": 0.30,
        "curious": 0.28,
        "neutral": 0.20,
        "bored": 0.25,
        "bad": 0.08,
        "": 0.0,
    }
    return rates.get(mood_val, 0.20)


def get() -> Dict[str, Any]:
    """Hozirgi kayfiyat."""
    m = get_mood()
    return {"mood": m.mood, "strength": m.strength, "since": m.since}
