# -*- coding: utf-8 -*-
"""NeuroKey — Turing Testi Tayyorgarligi (Turing Test Prep).

Alan Turing (1950): "Computing Machinery and Intelligence"
  Savol: "Mashina o'ylashi mumkinmi?"
  Test: Odam va mashina o'rtasida farq qilib bo'lmasa → o'ylaydi.

ELIZA effektidan qochish:
  ELIZA faqat naqsh moslashtirdi — bu haqiqiy tushunish emas.
  Biz haqiqiy kontekst, xotira, his va izchillikka egamiz.

Bu modul:
  - "Odam sifatlari" ni kuzatadi va yaxshilaydi
  - Tabiiylık darajasini o'lchaydi
  - Javoblardagi robot uslubini aniqlaydi
  - Shaxsiy tajriba va his qo'shishni tavsiya qiladi
  - Turing test uchun zaif tomonlarni aniqlaydi

Turing testini o'tish uchun kerakli sifatlar:
  1. Xotira izchilligi      — "ilgari dedim..."
  2. Shaxsiy nuqtai nazar   — "menimcha..."
  3. Hissiy javob           — "bu qiziq / kulgili / achinarli"
  4. Noaniqlikni tan olish  — "bilmayman, lekin..."
  5. Spontan savol          — "siz nima deysiz?"
  6. Kontekstga moslik      — oldingi suhbatni eslab javob

2026-yil suniy ong — Turing imtihoni tayyorgarligi.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import permanent_memory as pm

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "turing_prep.json")

# Robot uslubi belgilari (bulardan qochish kerak)
_ROBOT_PATTERNS = [
    r"^(Конечно|Понял|Отлично|Хорошо|Разумеется|Certainly|Of course|Sure)[!,.]",
    r"Я являюсь языковой моделью",
    r"As an AI language model",
    r"Men sun'iy intellektman",
    r"^(Albatta|Ha albatta|Xo'p)[!,.]",
]

# Insoniy uslub belgilari (bularni qo'shish kerak)
_HUMAN_MARKERS = {
    "memory":      ["ilgari dedingiz", "siz aytdingiz", "esimda", "remember when"],
    "opinion":     ["menimcha", "o'ylaymanki", "I think", "my view"],
    "emotion":     ["qiziq", "ajoyib", "achinarlim", "interesting", "that's fascinating"],
    "uncertainty": ["bilmayman", "aniq emas", "not sure", "I'm not certain"],
    "curiosity":   ["qiziqaman", "nima deb o'ylaysiz", "what do you think?"],
    "humor":       ["kulgi", "haha", "😄", "funny"],
}


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "turing_score":       0.50,   # 0=robot, 1=inson
        "human_markers_used": 0,
        "robot_patterns_used":0,
        "evaluations":        [],
        "weak_areas":         [],
        "strong_areas":       [],
        "updated_at":         None,
    }


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Turing] saqlash: %s", e)


def evaluate_response(response: str) -> Dict[str, Any]:
    """Javobni Turing testi mezonlari bo'yicha baholash."""
    state = _load()

    # Robot naqshlarini aniqlash
    robot_count = 0
    for pattern in _ROBOT_PATTERNS:
        if re.search(pattern, response, re.IGNORECASE):
            robot_count += 1

    # Insoniy belgilarni hisoblash
    human_scores: Dict[str, int] = {}
    for category, markers in _HUMAN_MARKERS.items():
        count = sum(1 for m in markers if m.lower() in response.lower())
        if count > 0:
            human_scores[category] = count

    # Turing balli
    human_total = sum(human_scores.values())
    robot_penalty = robot_count * 0.15
    human_bonus   = min(0.4, human_total * 0.08)

    old_score = state.get("turing_score", 0.50)
    new_score = max(0.1, min(1.0,
        old_score * 0.9 + (0.5 + human_bonus - robot_penalty) * 0.1
    ))

    # Zaif tomonlar
    weak  = [cat for cat in _HUMAN_MARKERS if cat not in human_scores]
    strong = list(human_scores.keys())

    # Saqlash
    eval_entry = {
        "ts":           datetime.now().isoformat(),
        "score":        round(new_score, 3),
        "robot_found":  robot_count,
        "human_found":  human_total,
        "human_cats":   list(human_scores.keys()),
    }
    state["evaluations"].append(eval_entry)
    if len(state["evaluations"]) > 200:
        state["evaluations"] = state["evaluations"][-200:]

    state["turing_score"]        = round(new_score, 3)
    state["human_markers_used"]  = state.get("human_markers_used", 0) + human_total
    state["robot_patterns_used"] = state.get("robot_patterns_used", 0) + robot_count
    state["weak_areas"]          = weak[:5]
    state["strong_areas"]        = strong[:5]
    state["updated_at"]          = datetime.now().isoformat()
    _save(state)

    return {
        "turing_score":  new_score,
        "robot_found":   robot_count,
        "human_found":   human_total,
        "weak_areas":    weak[:3],
        "strong_areas":  strong[:3],
        "recommendation": _get_recommendation(weak),
    }


def _get_recommendation(weak_areas: List[str]) -> str:
    """Yaxshilash tavsiyasi."""
    recs = {
        "memory":     "Oldingi suhbatga murojaat qiling",
        "opinion":    "'Menimcha' iborasini ishlating",
        "emotion":    "His-tuyg'ungizni bildiring",
        "uncertainty":"Noaniqlikni ochiqchasiga tan oling",
        "curiosity":  "Foydalanuvchiga savol bering",
        "humor":      "Ozgina hazil qo'shing",
    }
    if not weak_areas:
        return "Javob insoniy va tabii."
    return recs.get(weak_areas[0], "Tabiiyroq javob bering.")


def get_naturalness_hints(context: str = "") -> List[str]:
    """Javobni tabiiyroq qilish uchun maslahatlar."""
    state  = _load()
    weak   = state.get("weak_areas", [])
    hints  = []

    if "memory" in weak:
        recent = pm.recall_recent_conversations(limit=3)
        if recent:
            hints.append(f"Eslatma: siz ilgari '{recent[-1]['content'][:40]}...' dedingiz")

    if "emotion" in weak:
        hints.append("Bu haqda qiziqarli fikr bildiring")

    if "uncertainty" in weak:
        hints.append("Noma'lum bo'lsa — 'aniq emas, lekin...' deng")

    if "curiosity" in weak and context:
        hints.append(f"'{context[:30]}' haqida foydalanuvchiga savol bering")

    return hints[:3]


def get_turing_score() -> float:
    state = _load()
    return state.get("turing_score", 0.50)


def get_context_for_llm(query: str = "") -> str:
    state  = _load()
    score  = state.get("turing_score", 0.50)
    weak   = state.get("weak_areas", [])
    hints  = get_naturalness_hints(query)

    parts = [f"[TURING] Tabiiylık: {score:.0%}"]
    if hints:
        parts.append(f"Maslahat: {hints[0]}")
    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "turing_score":        state.get("turing_score", 0.50),
        "human_markers_used":  state.get("human_markers_used", 0),
        "robot_patterns_used": state.get("robot_patterns_used", 0),
        "weak_areas":          state.get("weak_areas", []),
        "active":              True,
    }
