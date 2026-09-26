# -*- coding: utf-8 -*-
"""NeuroKey — Arousal. Qualia scaffold (ACM).

ACM: Arousal (anxiety) — dunyo kutilmagan bo'lsa oshadi (prediction error).
Valence + Arousal = Emotional homeostasis. R = Rext + λ(V - A).

Arousal: 0.0 (tinch) dan 1.0 (hayajon, qo'rquv) gacha.
Ma'lumot — LLM ga. Qoida emas.
"""

from __future__ import annotations

try: import pain_pleasure_signal as _as2_pps
except ImportError: _as2_pps = None
try: import emotional_granularity as _as2_eg
except ImportError: _as2_eg = None

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


_MAX_OUTCOMES = 20
_outcomes: deque = deque(maxlen=_MAX_OUTCOMES)


@dataclass
class ArousalState:
    """Arousal — kutilmaganlik, prediction error."""
    value: float = 0.0  # 0.0 (calm) .. 1.0 (anxious)
    since: float = 0.0

    def get_salience(self) -> float:
        """Global Workspace uchun salience — yuqori arousal = yuqori salience."""
        ar = compute_arousal()
        return min(1.0, ar * 1.1)

    def to_signal(self) -> dict:
        """Global Workspace compete() uchun signal."""
        return {
            "source": "arousal",
            "content": compute_arousal(),
            "salience": self.get_salience(),
            "timestamp": time.time(),
        }

    def receive_broadcast(self, signal: dict) -> None:
        """GWT broadcast qabul qiladi. Ixtiyoriy reaktsiya."""
        pass


_arousal: Optional[ArousalState] = None


def get_arousal_state() -> ArousalState:
    global _arousal
    if _arousal is None:
        _arousal = ArousalState()
    return _arousal


def update(success: bool, action: str = "") -> None:
    """Natija — arousal yangilash.
    Success = kutilgan, prediction error past → arousal kamayadi.
    Fail = kutilmagan, prediction error yuqori → arousal oshadi.
    """
    _outcomes.append(0 if success else 1)  # 0=ok, 1=fail
    a = get_arousal_state()
    a.since = time.time()
    delta = 0.2 if not success else -0.08
    a.value = max(0.0, min(1.0, a.value + delta))


def compute_arousal() -> float:
    """Arousal hisoblash — prediction error, regret, emotion dan."""
    a = get_arousal_state()
    base = a.value

    # Recent fail rate (sliding window)
    if _outcomes:
        fail_rate = sum(_outcomes) / len(_outcomes)
        base = max(base, fail_rate * 0.5)

    try:
        from emotion_state import get_emotion
        e = get_emotion()
        if getattr(e, "emotion", "") == "frustration":
            base = max(base, 0.4)  # frustration → anxiety
    except Exception:
        pass

    try:
        from regret import get_regret_count
        n = get_regret_count()
        if n > 0:
            base = max(base, 0.2 + (n * 0.02))  # regret → anxiety
    except Exception:
        pass

    # Valence feedback: salbiy valence arousal ni oshiradi (stress, negativity bias)
    try:
        from valence_state import get_valence
        val = get_valence()
        if val < -0.2:
            base = max(base, 0.25 - (val * 0.2))  # salbiy valence → anxiety
    except Exception:
        pass

    return max(0.0, min(1.0, base))


def get_arousal() -> float:
    """Hozirgi arousal."""
    return compute_arousal()


def get_arousal_for_llm() -> str:
    """LLM uchun arousal — ma'lumot (qoida emas).
    ACM: Arousal = anxiety when unpredictable.
    """
    ar = compute_arousal()
    if ar > 0.6:
        desc = "high (anxious, unpredictable)"
    elif ar > 0.35:
        desc = "moderate"
    elif ar > 0.15:
        desc = "low-moderate"
    else:
        desc = "low (calm)"
    return f"Arousal (predictability signal): {ar:.2f} ({desc})"
