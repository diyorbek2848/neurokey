# -*- coding: utf-8 -*-
"""NeuroKey — Confidence. Metacognition scaffold.

Past confidence = "Men aniq emasman, lekin…" — epistemic humility.
Coherence past, regret ko'p, valence salbiy → confidence past.
"""
from __future__ import annotations


def compute_confidence(user_text: str = "") -> float:
    """0..1 — qancha ishonch. Past = epistemic humility."""
    c = 0.7  # default
    try:
        from coherence_proxy import compute_input_coherence
        coh = compute_input_coherence(user_text or "")
        c = 0.5 + coh * 0.4  # coherence → confidence
    except Exception:
        pass
    try:
        from regret import get_regret_count
        n = get_regret_count()
        if n > 0:
            c -= min(0.3, n * 0.03)  # regret → past confidence
    except Exception:
        pass
    try:
        from valence_state import get_valence
        v = get_valence()
        if v < -0.3:
            c -= 0.1  # salbiy valence → biroz past confidence
    except Exception:
        pass
    return max(0.1, min(1.0, c))


def get_confidence_for_llm(user_text: str = "") -> str:
    """LLM uchun — metacognition ma'lumot."""
    conf = compute_confidence(user_text or "")
    if conf < 0.4:
        desc = "low — express uncertainty when relevant"
    elif conf < 0.6:
        desc = "moderate — hedge when unsure"
    else:
        desc = "adequate"
    return f"Confidence (epistemic): {conf:.2f} ({desc})"
