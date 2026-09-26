# -*- coding: utf-8 -*-
"""NeuroKey — Diqqat Mexanizmi (Attention Mechanism).

Friston: diqqat = precision weighting.
Yuqori surprise → ko'p diqqat. Past surprise → kam diqqat.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

_MAX_FOCUS_HISTORY = 30
_ATTENTION_THRESHOLD = 0.3


class AttentionMechanism:
    """
    Friston: diqqat = precision weighting.
    NeuroKey uchun: qaysi ma'lumot muhim, qaysi background.
    """

    def __init__(self, active_inference: Any) -> None:
        self.active_inference = active_inference
        self._lock = threading.RLock()
        self.attention_map: Dict[str, float] = {}
        self.focus_history: List[Dict[str, Any]] = []
        self.current_focus: Optional[str] = None
        self._focus_until: float = 0.0

        self.sources: Dict[str, float] = {
            "user_speech": 0.0,
            "screen_content": 0.0,
            "system_state": 0.0,
            "memory": 0.0,
            "prediction_error": 0.0,
        }

    def compute_attention(self, inputs: Dict[str, Any]) -> Dict[str, float]:
        """
        Har input uchun diqqat og'irligini hisoblash.
        """
        try:
            import time
            with self._lock:
                weights: Dict[str, float] = {}
                surprise = getattr(
                    self.active_inference,
                    "prediction_error",
                    inputs.get("surprise_level", 0),
                )
                if hasattr(self.active_inference, "perceive"):
                    obs = {"user_input": inputs.get("user_speech", inputs.get("input", ""))}
                    perc = self.active_inference.perceive(obs)
                    surprise = perc.get("surprise_level", surprise)

                # User speech har doim yuqori
                weights["user_speech"] = 0.5 + min(0.4, surprise * 0.5)
                weights["screen_content"] = 0.2 + (0.2 if inputs.get("screen_content") else 0)
                weights["system_state"] = 0.1 + (0.3 if inputs.get("system_state") == "critical" else 0)
                weights["memory"] = 0.2
                weights["prediction_error"] = min(0.5, surprise)

                # Normalize to sum ~1.0
                total = sum(weights.values())
                if total > 0:
                    for k in weights:
                        weights[k] /= total
                self.attention_map = weights
                return weights
        except Exception:
            return {
                "user_speech": 0.5,
                "screen_content": 0.2,
                "system_state": 0.1,
                "memory": 0.2,
                "prediction_error": 0.0,
            }

    def focus(self, source: str, duration: float = 5.0) -> None:
        """Muayyan manbaga diqqatni yo'naltirish."""
        try:
            import time
            with self._lock:
                self.current_focus = source
                self._focus_until = time.time() + duration
                self.focus_history.append({"source": source, "duration": duration})
                if len(self.focus_history) > _MAX_FOCUS_HISTORY:
                    self.focus_history = self.focus_history[-_MAX_FOCUS_HISTORY:]
        except Exception:
            pass

    def get_weighted_context(self, all_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Diqqat og'irliklari bilan kontekst filtrlash.
        """
        try:
            weights = self.compute_attention(all_inputs)
            filtered = {}
            for k, w in weights.items():
                if w >= _ATTENTION_THRESHOLD and k in all_inputs:
                    filtered[k] = {"value": all_inputs[k], "weight": w}
            return filtered
        except Exception:
            return {}

    def detect_distraction(self) -> bool:
        """Diqqat tarqalganmi?"""
        try:
            with self._lock:
                high_count = sum(1 for w in self.attention_map.values() if w > 0.3)
                return high_count >= 4
        except Exception:
            return False

    def to_llm_context(self) -> str:
        """LLM uchun: hozir nenga diqqat qaratilgan."""
        try:
            with self._lock:
                if self.current_focus:
                    return f"Diqqat: {self.current_focus}."
                top = max(self.attention_map.items(), key=lambda x: x[1], default=(None, 0))
                if top[0]:
                    return f"Diqqat: {top[0]} ({top[1]:.0%})."
                return "Diqqat: foydalanuvchi gapi."
        except Exception:
            return "Diqqat: foydalanuvchi gapi."


_SINGLETON: Optional[AttentionMechanism] = None
_SINGLETON_LOCK = threading.Lock()


def get_attention_mechanism(
    active_inference: Optional[Any] = None,
) -> AttentionMechanism:
    """Singleton AttentionMechanism."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                from active_inference import get_active_inference
                ai = active_inference or get_active_inference()
                _SINGLETON = AttentionMechanism(ai)
    return _SINGLETON
