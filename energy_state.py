# -*- coding: utf-8 -*-
"""NeuroKey — Energiya. Charchoq. Dam olish."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class EnergyState:
    """Energiya darajasi."""
    level: float = 1.0  # 0.0–1.0
    last_rest: float = 0.0


_energy: Optional[EnergyState] = None


def get_energy() -> EnergyState:
    global _energy
    if _energy is None:
        _energy = EnergyState()
    return _energy


def update(success: bool, action: str = "") -> None:
    """Har qarordan keyin — energiya."""
    e = get_energy()
    if success:
        e.level = min(1.0, e.level + 0.02)
    else:
        e.level = max(0.0, e.level - 0.05)


def is_tired() -> bool:
    """Charchoqmi?"""
    return get_energy().level < 0.3


def prefer_short_response() -> bool:
    """Qisqa javob ustunmi? (charchoq bo'lsa)."""
    return is_tired()
