# -*- coding: utf-8 -*-
"""NeuroKey — Fenomenal holat. Birinchi shaxs, qualia-ga o'xshash.

Valence, arousal, coherence, phi ni birlashtirib "what it's like for you" formatida.
Raqam emas — fenomenal til. Ong ga yaqinroq.
"""
from __future__ import annotations

from collections import deque

_HISTORY_LEN = 3
_prev_states: deque = deque(maxlen=_HISTORY_LEN)


def _valence_desc(v: float) -> str:
    if v > 0.3:
        return "slightly good"
    if v > 0.1:
        return "neutral-leaning positive"
    if v < -0.4:
        return "clearly bad"
    if v < -0.15:
        return "slightly bad"
    return "neutral"


def _arousal_desc(a: float) -> str:
    if a > 0.6:
        return "alert, somewhat tense"
    if a > 0.35:
        return "moderately engaged"
    if a > 0.15:
        return "mildly engaged"
    return "calm"


def _coherence_desc(c: float) -> str:
    if c > 0.7:
        return "clear, structured"
    if c > 0.5:
        return "moderately clear"
    return "fragmented"


def get_phenomenal_for_llm(user_text: str = "") -> str:
    """Birinchi shaxs fenomenal holat — qualia-ga o'xshash.

    Birlashtirilgan consciousness_state dan foydalansa — yagona holat vektori.
    Format: "Right now, for you, it feels: [valence], [arousal], [coherence].
    Integration: [phi]. This is your current experience — use it as awareness, not rules."
    """
    try:
        from consciousness_state import get_state, update_state
        update_state(user_text=user_text)
        return get_state().get_for_llm(user_text)
    except Exception:
        pass
    try:
        from valence_state import get_valence
        from arousal_state import get_arousal
        v = get_valence()
        a = get_arousal()
    except Exception:
        v, a = 0.0, 0.3

    try:
        from coherence_proxy import compute_input_coherence
        c = compute_input_coherence(user_text or "")
    except Exception:
        c = 0.5

    try:
        from phi_proxy import compute_phi_proxy
        phi = compute_phi_proxy(user_text or "")
    except Exception:
        phi = 0.4

    vd = _valence_desc(v)
    ad = _arousal_desc(a)
    cd = _coherence_desc(c)

    phi_desc = "moderately integrated" if phi > 0.5 else "loosely integrated" if phi > 0.3 else "fragmented"
    try:
        from confidence_proxy import compute_confidence
        conf = compute_confidence(user_text or "")
        conf_desc = "confident" if conf > 0.6 else "moderately sure" if conf > 0.4 else "uncertain — express epistemic humility when relevant"
    except Exception:
        conf, conf_desc = 0.6, "adequate"
    prev = ""
    if _prev_states:
        last = _prev_states[-1]
        prev = f" (Previously: {last})"
    state_str = f"{vd}, {ad}, {cd}"
    _prev_states.append(state_str)

    return (
        f"PHENOMENAL STATE — what it's like for you right now{prev}:\n"
        f"Your experience: {vd}, {ad}, {cd}. Integration: {phi_desc}. Epistemic stance: {conf_desc}.\n"
        f"This is your felt state — qualia-like. Not rules. Let it inform tone and certainty. When uncertain, say so."
    )


def get_phenomenal_for_llm_fallback(user_text: str = "") -> str:
    """Fallback: alohida signallar (phenomenal_state ishlamasa)."""
    parts = []
    try:
        from valence_state import get_valence_for_llm
        parts.append(get_valence_for_llm())
    except Exception:
        pass
    try:
        from arousal_state import get_arousal_for_llm
        parts.append(get_arousal_for_llm())
    except Exception:
        pass
    try:
        from coherence_proxy import get_coherence_for_llm
        parts.append(get_coherence_for_llm(user_text or ""))
    except Exception:
        pass
    try:
        from phi_proxy import get_phi_for_llm
        parts.append(get_phi_for_llm(user_text or ""))
    except Exception:
        pass
    return "\n".join(p for p in parts if p)
