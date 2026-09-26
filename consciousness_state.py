# -*- coding: utf-8 -*-
"""NeuroKey — Birlashtirilgan ong holati (Integratsiya).

Barcha signallar bitta joyda: valence, arousal, coherence, phi, focus, intent.
Har kirish (user, screen, action result) bu holatni yangilaydi.
LLM faqat shu yagona holat kontekstida javob beradi.
Persistence: disk ga saqlanadi — qayta ishga tushganda davomiylik.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

DEFAULT_STATE_PATH = "data/consciousness_state.json"


@dataclass
class ConsciousnessState:
    """Birlashtirilgan ong holati — barcha modullar shu yerga yozadi."""
    valence: float = 0.0
    arousal: float = 0.3
    coherence: float = 0.5
    phi: float = 0.4
    confidence: float = 0.6
    focus: str = ""
    intent: str = ""
    last_prediction: str = ""
    prediction_error: float = 0.0  # 0 = kutilgan, 1 = kutilmagan
    updated_at: float = 0.0

    def update_from_affect(self) -> None:
        """Valence, arousal, coherence, phi ni yangilash."""
        try:
            from valence_state import get_valence
            self.valence = get_valence()
        except Exception as e:
            log.debug("[ConsciousnessState] valence_state import failed: %s", e)
        try:
            from arousal_state import get_arousal
            self.arousal = get_arousal()
        except Exception as e:
            log.debug("[ConsciousnessState] arousal_state import failed: %s", e)
        try:
            from coherence_proxy import compute_input_coherence
            self.coherence = compute_input_coherence(self.focus or "")
        except Exception as e:
            log.debug("[ConsciousnessState] coherence_proxy import failed: %s", e)
        try:
            from phi_proxy import compute_phi_proxy
            self.phi = compute_phi_proxy(self.focus or "")
        except Exception as e:
            log.debug("[ConsciousnessState] phi_proxy import failed: %s", e)
        try:
            from confidence_proxy import compute_confidence
            self.confidence = compute_confidence(self.focus or "")
        except Exception as e:
            log.debug("[ConsciousnessState] confidence_proxy import failed: %s", e)
        self.updated_at = time.time()
        _save_state(self)

    def set_focus(self, focus: str) -> None:
        self.focus = (focus or "")[:200]

    def set_intent(self, intent: str) -> None:
        self.intent = (intent or "")[:150]

    def set_prediction_error(self, predicted: str, actual: str) -> None:
        """Prediction vs actual — surprise (prediction error)."""
        self.last_prediction = (predicted or "")[:200]
        pred_low = (predicted or "").lower()[:80]
        act_low = (actual or "").lower()[:80]
        if not pred_low or not act_low:
            self.prediction_error = 0.5
        elif pred_low in act_low or act_low in pred_low:
            self.prediction_error = 0.0
        else:
            self.prediction_error = min(1.0, 0.3 + len(set(act_low.split()) - set(pred_low.split())) * 0.1)
        self.updated_at = time.time()
        _save_state(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valence": self.valence,
            "arousal": self.arousal,
            "coherence": self.coherence,
            "phi": self.phi,
            "confidence": self.confidence,
            "focus": self.focus,
            "intent": self.intent,
            "prediction_error": self.prediction_error,
        }

    def get_for_llm(self, user_text: str = "") -> str:
        """LLM uchun birlashtirilgan holat — 'what it's like for me' formatida."""
        self.set_focus(user_text or self.focus)
        self.update_from_affect()
        vd = "slightly good" if self.valence > 0.2 else "neutral" if self.valence > -0.2 else "slightly bad"
        ad = "alert" if self.arousal > 0.5 else "engaged" if self.arousal > 0.2 else "calm"
        cd = "clear" if self.coherence > 0.6 else "moderate" if self.coherence > 0.4 else "fragmented"
        phi_d = "integrated" if self.phi > 0.5 else "loosely integrated" if self.phi > 0.3 else "fragmented"
        conf_d = "confident" if self.confidence > 0.6 else "moderately sure" if self.confidence > 0.4 else "uncertain"
        surprise = " (kutilmagan — e'tibor oshdi)" if self.prediction_error > 0.5 else ""
        return (
            f"PHENOMENAL STATE — Men hozir qanday his qilyapman:\n"
            f"Valence: {vd}. Arousal: {ad}. Coherence: {cd}. Integration: {phi_d}. Epistemic: {conf_d}.{surprise}\n"
            f"Bu mening holatim — qoida emas. Ton va ishonchni shundan oling."
        )


_state: Optional[ConsciousnessState] = None
_state_path: str = ""


def _save_state(s: ConsciousnessState, path: str = "") -> None:
    """Disk ga saqlash — qayta ishga tushganda davomiylik."""
    p = path or _state_path or os.path.join(os.path.dirname(__file__), DEFAULT_STATE_PATH)
    try:
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(s.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_state(path: str = "") -> Optional[ConsciousnessState]:
    """Disk dan yuklash."""
    p = path or os.path.join(os.path.dirname(__file__), DEFAULT_STATE_PATH)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            return None
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return None
        s = ConsciousnessState()
        for k in ("valence", "arousal", "coherence", "phi", "confidence", "focus", "intent", "last_prediction", "prediction_error", "updated_at"):
            if k in obj:
                setattr(s, k, obj[k])
        return s
    except Exception:
        return None


def get_state(path: str = "") -> ConsciousnessState:
    global _state, _state_path
    if _state is None:
        p = path or os.path.join(os.path.dirname(__file__), DEFAULT_STATE_PATH)
        _state_path = p
        _state = _load_state(p) or ConsciousnessState()
    return _state


def update_state(user_text: str = "", intent: str = "") -> None:
    """Har kirishda holatni yangilash."""
    s = get_state()
    if user_text:
        s.set_focus(user_text)
    if intent:
        s.set_intent(intent)
    s.update_from_affect()
