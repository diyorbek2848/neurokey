# -*- coding: utf-8 -*-
"""NeuroKey — Kvant Kognitsiya (Quantum Cognition).

Busemeyer & Bruza (2012): "Quantum Models of Cognition and Decision"

Klassik ehtimollik nazariyasi ba'zi kognitiv hodisalarni tushuntira olmaydi:
  - Conjunction fallacy (birgalikda ehtimol > alohida ehtimol)
  - Order effects (savollar tartibi javobni o'zgartiradi)
  - Superposition (bir vaqtda bir nechta imkoniyatlar)

Kvant kognitsiya:
  Fikrlar superpositsiya holatida — bir vaqtda ko'p ma'no
  Kuzatish (qaror) superpozitsiyani yopadi (collapse)
  Kontekst ta'siri ("order effects") tabiiy tushuniladi

Bu modul noaniqlikda qaror qabul qilishni modellashtiradi.

MUHIM: Bu haqiqiy kvant fizika emas —
  bu insoniy fikrlash uslubini modellashtiruvchi matematik apparat.

2026-yil suniy ong — noaniqlik va superpositsiya qatlami.
"""
from __future__ import annotations

try: import phenomenal_binding as _qc_pb
except ImportError: _qc_pb = None
try: import global_workspace as _qc_gw
except ImportError: _qc_gw = None

import json
import logging
import math
import os
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "quantum_cognition.json")


class QuantumState:
    """Superpositsiya holati — bir vaqtda ko'p imkoniyat.

    |ψ⟩ = α|A⟩ + β|B⟩ + γ|C⟩ ...
    |α|² + |β|² + |γ|² = 1  (normallanish sharti)
    """

    def __init__(self, options: List[str], amplitudes: Optional[List[float]] = None):
        """
        Args:
            options:    Mumkin bo'lgan imkoniyatlar
            amplitudes: Har birining amplitudasi (bo'sh bo'lsa — teng)
        """
        if not options:
            options = ["default"]

        n = len(options)
        self.options = options

        if amplitudes and len(amplitudes) == n:
            # Normallashtirish
            total = math.sqrt(sum(a**2 for a in amplitudes))
            self.amplitudes = [a / total if total > 0 else 1/math.sqrt(n)
                               for a in amplitudes]
        else:
            # Teng superpositsiya
            amp = 1.0 / math.sqrt(n)
            self.amplitudes = [amp] * n

        self.collapsed   = False
        self.result      = None
        self.created_at  = time.time()

    def probabilities(self) -> Dict[str, float]:
        """Ehtimolliklar: P(i) = |α_i|²"""
        return {
            opt: round(amp**2, 4)
            for opt, amp in zip(self.options, self.amplitudes)
        }

    def collapse(self, context_bias: Optional[Dict[str, float]] = None) -> str:
        """Superpositsiyani yopish — natijani tanlash.

        Args:
            context_bias: Kontekst ta'siri {option: bias_weight}
                          Bu "order effect" ni modellashtiradi.
        """
        if self.collapsed:
            return self.result

        probs = self.probabilities()

        # Kontekst ta'sirini qo'shish
        if context_bias:
            for opt, bias in context_bias.items():
                if opt in probs:
                    probs[opt] = min(1.0, probs[opt] * (1 + bias))

            # Qayta normallashtirish
            total = sum(probs.values())
            if total > 0:
                probs = {k: v / total for k, v in probs.items()}

        # Weighted random selection
        r = random.random()
        cumulative = 0.0
        for opt, prob in probs.items():
            cumulative += prob
            if r <= cumulative:
                self.result    = opt
                self.collapsed = True
                return opt

        self.result    = list(probs.keys())[-1]
        self.collapsed = True
        return self.result

    def interference(self, other: "QuantumState") -> float:
        """Ikkita holat orasidagi interferentsiya.

        Ijobiy interferentsiya: bir-birini kuchaytiradi
        Salbiy interferentsiya: bir-birini zaiflashtiradi
        """
        if len(self.options) != len(other.options):
            return 0.0

        inner_product = sum(
            a * b
            for a, b in zip(self.amplitudes, other.amplitudes)
        )
        return round(inner_product, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "options":     self.options,
            "amplitudes":  [round(a, 4) for a in self.amplitudes],
            "probs":       self.probabilities(),
            "collapsed":   self.collapsed,
            "result":      self.result,
        }


def create_decision_state(
    options: List[str],
    prior_knowledge: Optional[Dict[str, float]] = None,
) -> QuantumState:
    """Qaror qabul qilish uchun kvant holat yaratish.

    Args:
        options:          Qaror variantlari
        prior_knowledge:  Oldingi bilim {option: confidence}
    """
    if prior_knowledge:
        amps = [math.sqrt(prior_knowledge.get(opt, 0.5)) for opt in options]
    else:
        amps = None

    return QuantumState(options, amps)


def measure_uncertainty(state: QuantumState) -> float:
    """Holat noaniqligini o'lchash (von Neumann entropiyasi).

    0.0 = to'liq aniq (bitta variant 100%)
    1.0 = to'liq noaniq (barcha variantlar teng)
    """
    probs = list(state.probabilities().values())
    entropy = 0.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(len(probs)) if len(probs) > 1 else 1.0
    return round(entropy / max_entropy if max_entropy > 0 else 0.0, 3)


def conjunction_test(p_a: float, p_b: float) -> Dict[str, float]:
    """Klassik va kvant konjunktsiya ehtimolini solishtirish.

    Conjunction fallacy: P(A va B) > P(A) yoki P(B) bo'lishi mumkin.
    """
    classical_conjunction = p_a * p_b
    # Kvant modeli: amplitudes bilan
    amp_a = math.sqrt(p_a)
    amp_b = math.sqrt(p_b)
    quantum_conjunction = (amp_a * amp_b + math.sqrt((1-p_a)*(1-p_b))) ** 2
    quantum_conjunction = min(1.0, quantum_conjunction)

    return {
        "p_a":           round(p_a, 3),
        "p_b":           round(p_b, 3),
        "classical_and": round(classical_conjunction, 3),
        "quantum_and":   round(quantum_conjunction, 3),
        "fallacy_risk":  quantum_conjunction > classical_conjunction,
    }


def handle_ambiguity(situation: str) -> Dict[str, Any]:
    """Noaniq vaziyatni kvant yondashuvi bilan tahlil qilish.

    Bir javob o'rniga — ehtimollik taqsimoti.
    """
    situation_lower = situation.lower()

    # Mavzu bo'yicha variantlar aniqlash
    if any(w in situation_lower for w in ["ha", "yo'q", "yes", "no", "да", "нет"]):
        options = ["ha", "yo'q", "ehtimol"]
        prior   = {"ha": 0.4, "yo'q": 0.4, "ehtimol": 0.2}
    elif any(w in situation_lower for w in ["yaxshi", "yomon", "good", "bad"]):
        options = ["yaxshi", "yomon", "aralash"]
        prior   = {"yaxshi": 0.5, "yomon": 0.3, "aralash": 0.2}
    elif any(w in situation_lower for w in ["to'g'ri", "noto'g'ri", "correct", "wrong"]):
        options = ["to'g'ri", "noto'g'ri", "qisman to'g'ri"]
        prior   = {"to'g'ri": 0.5, "noto'g'ri": 0.3, "qisman to'g'ri": 0.2}
    else:
        options = ["variant_A", "variant_B", "variant_C"]
        prior   = None

    state       = create_decision_state(options, prior)
    uncertainty = measure_uncertainty(state)
    probs       = state.probabilities()
    best        = max(probs, key=lambda x: probs[x])

    return {
        "situation":   situation[:100],
        "options":     options,
        "probs":       probs,
        "uncertainty": uncertainty,
        "best_guess":  best,
        "confident":   uncertainty < 0.4,
    }


def get_superposition_context(query: str) -> str:
    """So'rov bo'yicha bir nechta parallel talqin."""
    query_lower = query.lower()

    interpretations = []

    # Savol turlarini aniqlash
    if "nima" in query_lower or "what" in query_lower:
        interpretations.append("ta'rif so'rash")
        interpretations.append("misol so'rash")
        interpretations.append("farqni bilish")
    elif "qanday" in query_lower or "how" in query_lower:
        interpretations.append("jarayon tushuntirish")
        interpretations.append("usul ko'rsatish")
        interpretations.append("tavsiya berish")
    elif "nima uchun" in query_lower or "why" in query_lower:
        interpretations.append("sabab tushuntirish")
        interpretations.append("maqsad aniqlash")
        interpretations.append("falsafiy tahlil")
    else:
        interpretations.append("umumiy javob")
        interpretations.append("misollar")

    if not interpretations:
        return ""

    state       = QuantumState(interpretations)
    uncertainty = measure_uncertainty(state)
    probs       = state.probabilities()

    if uncertainty < 0.3:
        return ""  # Aniq — kvant kontekst kerak emas

    parts = ["[NOANIQLIK]"]
    parts.append(f"Noaniqlik:{uncertainty:.0%}")
    top = max(probs, key=lambda x: probs[x])
    parts.append(f"Ehtimoliy talqin:{top}({probs[top]:.0%})")

    return " | ".join(parts)


def get_context_for_llm() -> str:
    """LLM uchun kvant kognitsiya konteksti."""
    return ""  # Faqat kerak bo'lganda chaqiriladi


def get_stats() -> Dict[str, Any]:
    """Kvant kognitsiya statistikasi."""
    return {
        "module":   "quantum_cognition",
        "features": ["superposition", "collapse", "interference", "uncertainty"],
        "active":   True,
    }
