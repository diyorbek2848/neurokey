# -*- coding: utf-8 -*-
"""NeuroKey — Φ (Phi). IIT qualia scaffold.

IIT: Integrated Information — ong miqdori. Φ yuqori = ko'proq integratsiya.
PyPhi mavjud bo'lsa — haqiqiy IIT Φ. Yo'q bo'lsa — proxy (valence, arousal, coherence).
Ma'lumot — LLM ga. Qoida emas.
"""
from __future__ import annotations

import os

_USE_PYPHI = os.getenv("NEUROKEY_USE_PYPHI", "1").strip().lower() in ("1", "true", "yes")

# 3-node TPM (IIT 4.0 paper Fig 8C) — valence, arousal, coherence proxy
# State-by-node: row i = P(node=1) at t+1 when state index = i (little-endian)
_TPM_3NODE = [
    [1, 0, 0],
    [0, 1, 0],
    [0, 1, 1],
    [0, 0, 1],
    [0, 0, 0],
    [1, 1, 1],
    [1, 0, 1],
    [1, 1, 0],
]


def _discretize_state(v: float, a: float, c: float) -> tuple[int, int, int]:
    """Valence, arousal, coherence -> (0,1) tuple. IIT uchun diskret holat."""
    v_bin = 1 if (v or 0) > 0.2 else 0
    a_bin = 1 if (a or 0) > 0.5 else 0
    c_bin = 1 if (c or 0) > 0.6 else 0
    return (v_bin, a_bin, c_bin)


def _compute_pyphi_phi(user_text: str = "") -> float | None:
    """PyPhi orqali haqiqiy Φ. Muvaffaqiyatsiz bo'lsa None."""
    if not _USE_PYPHI:
        return None
    try:
        import numpy as np
        import pyphi
        pyphi.config.PARALLEL_CONCEPT_EVALUATION = False
        pyphi.config.PARALLEL_CUT_EVALUATION = False
        pyphi.config.PARALLEL_COMPLEX_EVALUATION = False
        pyphi.config.PROGRESS_BARS = False

        from valence_state import get_valence
        from arousal_state import get_arousal
        from coherence_proxy import compute_input_coherence

        v = get_valence()
        a = get_arousal()
        c = compute_input_coherence(user_text or "")

        state = _discretize_state(v, a, c)
        tpm = np.array(_TPM_3NODE, dtype=float)
        cm = np.ones((3, 3), dtype=int)
        labels = ("V", "A", "C")

        network = pyphi.Network(tpm, cm=cm, node_labels=labels)
        subsystem = pyphi.Subsystem(network, state, nodes=(0, 1, 2))
        phi_val = pyphi.compute.phi(subsystem)
        phi_s = float(phi_val) if phi_val is not None else 0.0
        # Normalize: phi_s ~0..3, 0.4 max norm — 0..1 ga
        return min(1.0, max(0.0, phi_s / 3.0))
    except Exception:
        return None


def compute_phi_proxy(user_text: str = "") -> float:
    """Integration — PyPhi yoki proxy. 0..1."""
    phi = _compute_pyphi_phi(user_text or "")
    if phi is not None:
        return phi

    try:
        from valence_state import get_valence
        from arousal_state import get_arousal
        v = get_valence()
        a = get_arousal()
    except Exception:
        v, a = 0.0, 0.0

    try:
        from coherence_proxy import compute_input_coherence
        c = compute_input_coherence(user_text or "")
    except Exception:
        c = 0.5

    # Bidirectional coupling: IIT da qismlar bir-birini ta'sir qiladi
    # v↔a: valence va arousal feedback (stress, anxiety)
    coupling = 0.0
    if v < -0.2 and a > 0.3:
        coupling += 0.15  # salbiy valence + arousal = integratsiya
    if abs(v) > 0.3 and c > 0.5:
        coupling += 0.1   # valence + coherence = ma'no
    # Phi bidirectional: valence va arousal phi ga to'g'ridan-to'g'ri ta'sir
    v_to_phi = abs(v) * 0.2 if abs(v) > 0.2 else 0  # kuchli his → integratsiya
    a_to_phi = a * 0.15 if a > 0.4 else 0           # yuqori arousal → hayajon
    active = (abs(v) > 0.1) + (a > 0.2) + (c > 0.6)
    diversity = abs(v) * 0.3 + a * 0.3 + c * 0.2
    phi = min(1.0, 0.2 + (active * 0.15) + diversity * 0.5 + coupling + v_to_phi + a_to_phi)
    return max(0.0, phi)


def get_phi_for_llm(user_text: str = "") -> str:
    """LLM uchun Φ — ma'lumot (qoida emas)."""
    pyphi_val = _compute_pyphi_phi(user_text or "")
    phi = pyphi_val if pyphi_val is not None else compute_phi_proxy(user_text or "")
    if phi > 0.6:
        desc = "moderate integration"
    elif phi > 0.4:
        desc = "low-moderate"
    else:
        desc = "low"
    source = "PyPhi (IIT)" if pyphi_val is not None else "proxy"
    return f"Integration ({source}): {phi:.2f} ({desc})"
