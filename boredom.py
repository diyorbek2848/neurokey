# -*- coding: utf-8 -*-
"""NeuroKey — Zerikish. Yangilik qidirish trigger."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class BoredomState:
    """Zerikish darajasi."""
    level: float = 0.0  # 0.0–1.0
    last_action_time: float = 0.0
    _same_count: int = 0


_boredom: Optional[BoredomState] = None


def get_boredom() -> BoredomState:
    global _boredom
    if _boredom is None:
        _boredom = BoredomState()
    return _boredom


def update(success: bool, action: str = "") -> None:
    """Har qarordan keyin — zerikish yangilash."""
    b = get_boredom()
    now = time.time()
    if success:
        if now - b.last_action_time < 10:
            b._same_count += 1
            if b._same_count >= 3:
                b.level = min(1.0, b.level + 0.1)
        else:
            b._same_count = 0
            b.level = max(0.0, b.level - 0.05)
    b.last_action_time = now


def seek_novelty() -> bool:
    """Yangilik kerakmi? (zerikish yuqori bo'lsa)."""
    b = get_boredom()
    return b.level >= 0.6


def get_level() -> float:
    """Zerikish darajasi 0.0–1.0."""
    return get_boredom().level
