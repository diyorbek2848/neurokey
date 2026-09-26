# -*- coding: utf-8 -*-
"""NeuroKey — Fikr Tili (Language of Thought / Mentalese).

Fodor nazariyasi: Ong ichki "Mentalese" tilida fikrlaydi.
Bu til nutq tilidan farqli — predikativ, kompozitsional, amodal.

Bu modul:
  - LLM javobidan oldin ichki "fikr" hosil qiladi (inner_speech.py dan chuqurroq)
  - Mantiqiy formulalar: F(x), ∀x P(x), x → y
  - Konsept grafini quradi
  - Semantic compositionality: kichik fikrlarni kattaga birlashtiradi
  - permanent_memory ga ichki fikrlarni saqlaydi

Misol:
  Input: "Python nima?"
  Mentalese: QUERY(python, DEFINITION) ∧ KNOWS(I, python=lang) ∧ HELPFUL(EXPLAIN)
  Output: kontekst uchun strukturalangan fikr

2026-yil suniy ong — ichki fikr tili qatlami.
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
_STATE_PATH = os.path.join(_BASE_DIR, "data", "language_of_thought.json")

# Konsept turlari
CONCEPT_TYPES = {
    "QUERY":      "savol",
    "ASSERT":     "ta'kidlash",
    "RECALL":     "eslatish",
    "INFER":      "xulosa",
    "PLAN":       "rejalashtirish",
    "EVALUATE":   "baholash",
    "EMPATHIZE":  "empatsiya",
    "EXPLAIN":    "tushuntirish",
    "WARN":       "ogohlantirish",
    "UNCERTAIN":  "noaniqlik",
}

# Savolni aniqlash naqshlari
_QUERY_PATTERNS = {
    "definition":   [r"\bnima\b", r"\bwhat is\b", r"\bwhat's\b", r"\bчто такое\b"],
    "howto":        [r"\bqanday\b", r"\bhow to\b", r"\bкак\b"],
    "why":          [r"\bnima uchun\b", r"\bwhy\b", r"\bпочему\b"],
    "comparison":   [r"\bfarqi\b", r"\bdifference\b", r"\bразница\b", r"\bvs\b"],
    "opinion":      [r"\bnima deysiz\b", r"\bwhat do you think\b", r"\bкак вы думаете\b"],
    "personal":     [r"\bsiz\b", r"\bmen\b", r"\byou\b", r"\bi\b", r"\bвы\b"],
    "action":       [r"\bqiling\b", r"\bdo\b", r"\bсделайте\b", r"\byarating\b"],
    "memory":       [r"\beslayman\b", r"\bremember\b", r"\bпомните\b", r"\bilgari\b"],
}


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"thought_count": 0, "recent_thoughts": []}


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[LoT] saqlash: %s", e)


def parse_query_type(text: str) -> str:
    """So'rov turini aniqlash."""
    t = text.lower()
    for qtype, patterns in _QUERY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, t):
                return qtype
    return "general"


def extract_concepts(text: str) -> List[str]:
    """Matndan asosiy tushunchalarni ajratish."""
    t     = text.strip()
    words = re.findall(r'\b[a-zA-ZА-Яа-яёЁ\u0400-\u04FF\u0300-\u036f'
                       r'\u00C0-\u024F\u1E00-\u1EFF]{3,}\b', t)
    # Stop words
    stop = {
        "nima", "qanday", "uchun", "bilan", "agar", "lekin", "ham",
        "what", "how", "why", "and", "but", "the", "for",
        "что", "как", "почему", "это", "для", "при",
    }
    concepts = [w.lower() for w in words if w.lower() not in stop]
    # Dublikatlarni olib tashlash, tartibni saqlash
    seen = set()
    unique = []
    for c in concepts:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique[:8]


def mentalese_formula(text: str, context: str = "") -> str:
    """Matnni Mentalese formulasiga o'girish.

    Misol: "Python funksiya nima?" →
    "QUERY(python.funksiya, DEFINITION) ∧ RECALL(python.knowledge) → EXPLAIN"
    """
    q_type   = parse_query_type(text)
    concepts = extract_concepts(text)

    # Asosiy predikativ
    pred_map = {
        "definition": "QUERY({concepts}, DEFINITION)",
        "howto":      "QUERY({concepts}, PROCEDURE)",
        "why":        "QUERY({concepts}, CAUSE)",
        "comparison": "QUERY({concepts}, COMPARE)",
        "opinion":    "QUERY({concepts}, OPINION)",
        "personal":   "QUERY(SELF, STATE)",
        "action":     "PLAN({concepts}, EXECUTE)",
        "memory":     "RECALL({concepts})",
        "general":    "PROCESS({concepts})",
    }

    pred_tmpl = pred_map.get(q_type, pred_map["general"])
    concept_str = ".".join(concepts[:3]) if concepts else "x"
    pred        = pred_tmpl.replace("{concepts}", concept_str)

    # Xotira chaqiruvi
    memory_part = ""
    if concepts:
        memory_part = f" ∧ RECALL({concepts[0]})"

    # Natija
    action_map = {
        "definition": "EXPLAIN",
        "howto":      "INSTRUCT",
        "why":        "REASON",
        "comparison": "COMPARE",
        "opinion":    "EVALUATE",
        "personal":   "INTROSPECT",
        "action":     "EXECUTE",
        "memory":     "RETRIEVE",
        "general":    "RESPOND",
    }
    action = action_map.get(q_type, "RESPOND")

    formula = f"{pred}{memory_part} → {action}"
    return formula


def think(text: str, context: str = "") -> Dict[str, Any]:
    """Matn uchun ichki fikr hosil qilish.

    Returns: {formula, query_type, concepts, thought_str}
    """
    formula  = mentalese_formula(text, context)
    q_type   = parse_query_type(text)
    concepts = extract_concepts(text)

    # Inson tiliga yaqin fikr
    concept_str = ", ".join(concepts[:3]) if concepts else "bu mavzu"
    thought_templates = {
        "definition":  f"'{concept_str}' haqida ta'rif kerak. Xotiramdan qidiraman.",
        "howto":       f"'{concept_str}' qanday qilinishini ko'rsatish kerak.",
        "why":         f"'{concept_str}' sababi nima? Tahlil qilaman.",
        "comparison":  f"'{concept_str}' ni taqqoslash kerak.",
        "opinion":     f"'{concept_str}' bo'yicha o'z fikrimni bayon qilaman.",
        "personal":    f"O'zimga qarasam... hozirgi holatim nima?",
        "action":      f"'{concept_str}' bajaring. Imkoniyatlarimni baholayman.",
        "memory":      f"'{concept_str}' ni esga olaman. Xotiramni ko'raman.",
        "general":     f"'{concept_str}' haqida fikr yuritaman.",
    }
    thought_str = thought_templates.get(q_type, thought_templates["general"])

    # Xotirada saqlash
    state = _load()
    state["thought_count"] = state.get("thought_count", 0) + 1
    recent = state.setdefault("recent_thoughts", [])
    recent.append({
        "ts":       datetime.now().isoformat(),
        "formula":  formula,
        "q_type":   q_type,
        "concepts": concepts[:5],
    })
    if len(recent) > 100:
        recent[:] = recent[-100:]
    _save(state)

    # permanent_memory ga saqlash
    pm.remember_thought(thought_str, query=text[:100], confidence=0.7)

    return {
        "formula":    formula,
        "query_type": q_type,
        "concepts":   concepts,
        "thought":    thought_str,
    }


def get_context_for_llm(query: str = "") -> str:
    """LLM uchun ichki fikr konteksti."""
    if not query:
        return ""

    result = think(query)
    formula = result.get("formula", "")
    thought = result.get("thought", "")
    q_type  = result.get("query_type", "general")
    concepts = result.get("concepts", [])

    if not formula:
        return ""

    parts = [f"[ICHKI FIKr] Savol turi: {q_type}"]
    if concepts:
        parts.append(f"Asosiy tushunchalar: {', '.join(concepts[:4])}")
    parts.append(f"Mentalese: {formula}")
    parts.append(f"Fikr: {thought}")

    return "\n".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "thought_count": state.get("thought_count", 0),
        "active":        True,
    }
