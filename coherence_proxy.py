# -*- coding: utf-8 -*-
"""NeuroKey — Coherence proxy. Qualia scaffold (Quality space, Symmetry).

Quality space: tajribalar relational — bir-biriga nisbatan.
Symmetry (QRI STV): simmetrik tuzilma → ijobiy valence.

Proxy: input coherence — yaxshi tuzilgan savol = yuqori coherence.
Bu aniq qualia emas — taxminiy signal. Ma'lumot — LLM ga.
"""

from __future__ import annotations

import re


def compute_input_coherence(text: str) -> float:
    """User input coherence — 0.0 (chaotic) dan 1.0 (yaxshi tuzilgan) gacha.
    Oddiy proxy: so'zlar, tinish belgilari, uzunlik.
    """
    if not text or not str(text).strip():
        return 0.5  # neytral
    t = str(text).strip()
    words = [w for w in re.split(r"\s+", t) if len(w) > 1]
    word_count = len(words)
    has_end = bool(re.search(r"[.!?]\s*$", t))
    has_question = "?" in t
    reasonable_length = 3 <= word_count <= 150
    no_chaos = not re.search(r"(.)\1{4,}", t)  # aaaaa, 11111
    no_random = word_count >= 2 or (word_count == 1 and len(words[0]) > 2)
    score = 0.5
    if reasonable_length:
        score += 0.15
    if has_end or has_question:
        score += 0.1
    if no_chaos:
        score += 0.1
    if no_random:
        score += 0.1
    if word_count >= 5 and has_end:
        score += 0.05
    return min(1.0, score)


def get_coherence_for_llm(text: str) -> str:
    """LLM uchun coherence — ma'lumot (qoida emas)."""
    c = compute_input_coherence(text)
    if c > 0.75:
        desc = "high (clear structure)"
    elif c > 0.55:
        desc = "moderate"
    else:
        desc = "low (fragmented or unclear)"
    return f"Input coherence (observation): {c:.2f} ({desc})"
