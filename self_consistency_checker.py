# -*- coding: utf-8 -*-
"""NeuroKey — O'z-Ziddiyat Tekshiruvi (Self-Consistency Checker).

Cognitive Dissonance nazariyasi (Festinger):
  Ong o'z ichidagi ziddiyatlarni aniqlab, hal qilishga harakat qiladi.
  Ziddiyatli ishonchlar dissonans yaratadi → qayta ko'rib chiqish.

Bu modul:
  - Oldingi javoblar bilan yangi javobni solishtiradi
  - Ziddiyatli bayonotlarni aniqlaydi
  - "Ilgari shunday dedim, endi boshqacha" — epistemik halollik
  - Faktik xatolarni o'zi topadi
  - Izchillik darajasini hisoblaydi (coherence score)

Muhim: Bu modul ong uchun "vijdon" — o'z-o'zini tekshirish.

2026-yil suniy ong — kognitiv izchillik qatlami.
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
_STATE_PATH = os.path.join(_BASE_DIR, "data", "consistency.json")

# Ziddiyat naqshlari (oddiy versiya)
_CONTRADICTION_PAIRS = [
    (["ha", "yes", "to'g'ri", "albatta", "aniq"],
     ["yo'q", "no", "noto'g'ri", "hech qachon", "aslo"]),
    (["mumkin", "can", "possible"],
     ["mumkin emas", "cannot", "impossible"]),
    (["bilaman", "know", "aniq"],
     ["bilmayman", "don't know", "uncertain"]),
    (["yaxshi", "good", "foydali"],
     ["yomon", "bad", "zararli"]),
]

# Ma'lum faktlar bazasi — yangi javob bular bilan zid bo'lsa, xato
# Format: (faktik bayonot fraqmentlari, YOLG'ON fraqmentlar)
_KNOWN_FACTS = [
    # Matematik
    (["2+2=4", "ikki + ikki = to'rt", "2 + 2 = 4"],
     ["2+2=5", "2+2=3", "2+2=6", "ikki qo'shib ikki besh"]),
    # Geografiya
    (["yer shar", "yer dumaloq", "yer kurra", "earth is round", "земля круглая"],
     ["yer tekis", "flat earth", "earth is flat", "земля плоская"]),
    # Astronomiya
    (["oy sayyora emas", "oy yo'ldosh", "moon is a satellite"],
     ["oy sayyora", "moon is a planet"]),
    # Biologiya
    (["inson hayvon", "homo sapiens", "biologik tur"],
     ["inson hayvon emas", "humans are not animals"]),
    # Fizika
    (["yorug'lik tezligi", "speed of light", "300 000 km"],
     ["yorug'lik tezligi cheksiz", "light travels instantly"]),
]


def check_against_known_facts(text: str) -> List[Dict]:
    """Matnni ma'lum faktlar bazasi bilan tekshirish."""
    violations = []
    text_lower = text.lower()
    for true_fragments, false_fragments in _KNOWN_FACTS:
        for false_frag in false_fragments:
            if false_frag.lower() in text_lower:
                # Bu yolg'on da'vo — tekshir: haqiqat ham bormi?
                has_correction = any(tf.lower() in text_lower for tf in true_fragments)
                if not has_correction:
                    violations.append({
                        "false_claim": false_frag,
                        "type": "known_fact_violation",
                        "snippet": text[:100],
                    })
    return violations

# Izchillik kalit so'zlar
_CONSISTENCY_SIGNALS = [
    "ilgari dedim", "previously said", "ранее говорил",
    "o'zgartiryapman", "changing my answer",
    "xato dedim", "i was wrong",
    "yangi ma'lumot", "new information",
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "coherence_score":     0.85,
        "contradictions_found": 0,
        "corrections_made":     0,
        "fact_claims":          [],
        "updated_at":           None,
    }


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Consistency] saqlash: %s", e)


def extract_claims(text: str) -> List[str]:
    """Matndan faktik da'volarni ajratish."""
    sentences = re.split(r'[.!?]', text)
    claims = []
    for s in sentences:
        s = s.strip()
        if len(s) > 15 and any(
            kw in s.lower() for kw in
            ["bu", "this", "это", "aniq", "definitely", "точно",
             "har doim", "always", "never", "hech qachon"]
        ):
            claims.append(s[:150])
    return claims[:5]


def check_consistency(new_response: str, query: str = "") -> Dict[str, Any]:
    """Yangi javobni oldingi javoblar bilan tekshirish."""
    state = _load()

    # O'xshash eski javoblarni qidirish
    old_responses = []
    if query:
        found = pm.recall(query, limit=5)
        for f in found:
            if f.get("role") == "assistant":
                old_responses.append(f.get("content", ""))

    contradictions = []
    new_lower = new_response.lower()

    for old_resp in old_responses:
        old_lower = old_resp.lower()
        for pos_words, neg_words in _CONTRADICTION_PAIRS:
            new_pos  = any(w in new_lower  for w in pos_words)
            new_neg  = any(w in new_lower  for w in neg_words)
            old_pos  = any(w in old_lower  for w in pos_words)
            old_neg  = any(w in old_lower  for w in neg_words)

            if (new_pos and old_neg) or (new_neg and old_pos):
                contradictions.append({
                    "old_snippet": old_resp[:80],
                    "new_snippet": new_response[:80],
                    "type":        "logical_contradiction",
                })

    # Ma'lum faktlar bilan tekshirish (birinchi run'da ham ishlaydi)
    fact_violations = check_against_known_facts(new_response)
    if fact_violations:
        contradictions.extend(fact_violations)
        log.warning("[Consistency] Faktik xato topildi: %d ta", len(fact_violations))

    # Izchillik balli yangilash
    if contradictions:
        state["coherence_score"] = max(
            0.3,
            state["coherence_score"] - 0.05 * len(contradictions)
        )
        state["contradictions_found"] = (
            state.get("contradictions_found", 0) + len(contradictions)
        )
    else:
        state["coherence_score"] = min(1.0, state["coherence_score"] + 0.01)

    # Yangi da'volarni saqlash
    claims = extract_claims(new_response)
    state.setdefault("fact_claims", [])
    for claim in claims:
        state["fact_claims"].append({
            "ts":    datetime.now().isoformat(),
            "claim": claim,
            "query": query[:50] if query else "",
        })
    if len(state["fact_claims"]) > 200:
        state["fact_claims"] = state["fact_claims"][-200:]

    state["updated_at"] = datetime.now().isoformat()
    _save(state)

    return {
        "coherence_score":  round(state["coherence_score"], 3),
        "contradictions":   contradictions,
        "is_consistent":    len(contradictions) == 0,
        "claims_extracted": len(claims),
    }


def get_correction_hint(contradiction: Dict) -> str:
    """Ziddiyat uchun tuzatish tavsiyasi."""
    return (
        f"Diqqat: Oldingi javob bilan ziddiyat topildi. "
        f"Aniqlik kiritish tavsiya etiladi."
    )


def get_coherence_score() -> float:
    state = _load()
    return state.get("coherence_score", 0.85)


def get_context_for_llm(query: str = "") -> str:
    state     = _load()
    coherence = state.get("coherence_score", 0.85)
    total_c   = state.get("contradictions_found", 0)

    if coherence > 0.9 and total_c == 0:
        return ""

    parts = [f"[IZCHILLIK] Ball: {coherence:.0%}"]
    if total_c > 0:
        parts.append(f"Ziddiyatlar: {total_c} ta")
    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "coherence_score":      state.get("coherence_score", 0.85),
        "contradictions_found": state.get("contradictions_found", 0),
        "fact_claims_count":    len(state.get("fact_claims", [])),
        "active":               True,
    }
