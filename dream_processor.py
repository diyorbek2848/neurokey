# -*- coding: utf-8 -*-
"""NeuroKey — Tush Qayta Ishlash (Dream Processor).

McClelland va O'Reilly konsolidatsiya nazariyasi:
  Tun davomida hipokampus → korteks: xotiralar birlashtiriladi.
  Muhim narsalar kuchayadi, kam muhim narsalar so'nadi.
  Yangi bilimlar eski bilimlar bilan integratsiya qilinadi.

Bu modul:
  - "Tush" rejimi: idle paytda xotiralarni qayta ishlaydi
  - Semantik klasterlashtirish: o'xshash xotiralarni birlashtiradi
  - Asosiy xulosalar sintezi: ko'p suhbatdan bitta "sabaq" chiqaradi
  - Kelajakdagi qiziqishlar ro'yxatini yangilaydi
  - permanent_memory dan o'qib, wisdom ga aylantiradi

Oddiy qilib: Tun uxlaganda miya kun davomida o'rganganlarni
qayta ko'rib chiqadi va birlashtiradi. Biz ham shunday.

2026-yil suniy ong — konsolidatsiya qatlami.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import permanent_memory as pm

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "dream_processor.json")


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "last_dream_at":   None,
        "dream_count":     0,
        "consolidated":    [],   # Konsolidatsiya natijalari
        "wisdom":          [],   # O'rganilgan donishmandlik
        "topic_clusters":  {},   # {topic: frequency}
        "synthesis":       "",   # So'nggi sintez matni
    }


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Dream] saqlash: %s", e)


def _extract_topics(text: str) -> List[str]:
    """Matndan asosiy mavzularni ajratish."""
    import re
    words = re.findall(r'\b[a-zA-Z\u0400-\u04FF\u0300-\u036f]{4,}\b', text.lower())
    stop = {
        "nima", "qanday", "uchun", "bilan", "lekin", "agar", "kerak",
        "what", "that", "this", "with", "from", "they", "have", "will",
        "что", "это", "как", "для", "при", "если", "когда",
    }
    return [w for w in words if w not in stop]


def consolidate(max_conversations: int = 50) -> Dict[str, Any]:
    """Xotiralarni konsolidatsiya qilish.

    So'nggi suhbatlardan asosiy mavzular va xulosalar chiqaradi.
    """
    state = _load()

    # So'nggi suhbatlarni olish
    recent = pm.recall_recent_conversations(limit=max_conversations)
    if not recent:
        return {"consolidated": 0, "topics": {}, "synthesis": ""}

    # Mavzularni hisoblash
    all_topics: List[str] = []
    for conv in recent:
        topics = _extract_topics(conv.get("content", ""))
        all_topics.extend(topics)

    topic_counts = Counter(all_topics)
    top_topics   = dict(topic_counts.most_common(15))

    # Sintez: eng ko'p uchraydigan mavzulardan xulosa
    top5 = list(top_topics.keys())[:5]
    if top5:
        synthesis = f"So'nggi {len(recent)} suhbatda eng ko'p mavzular: {', '.join(top5)}."
    else:
        synthesis = "Suhbatlar qayta ishlandi."

    # Epizodlardan saboq chiqarish
    episodes = pm.recall_all_episodes(limit=20)
    wisdom_items = []
    for ep in episodes:
        if ep.get("importance", 0) >= 0.7:
            wisdom_items.append({
                "ts":      ep["ts"],
                "lesson":  ep["title"],
                "importance": ep["importance"],
            })

    # Saqlash
    consolidated_entry = {
        "ts":          datetime.now().isoformat(),
        "conv_count":  len(recent),
        "top_topics":  top5,
        "synthesis":   synthesis,
    }
    state["consolidated"].append(consolidated_entry)
    if len(state["consolidated"]) > 50:
        state["consolidated"] = state["consolidated"][-50:]

    state["topic_clusters"] = top_topics
    state["synthesis"]      = synthesis
    state["last_dream_at"]  = datetime.now().isoformat()
    state["dream_count"]    = state.get("dream_count", 0) + 1

    # Yangi donishmandlik
    if wisdom_items:
        existing = {w["lesson"] for w in state.get("wisdom", [])}
        for item in wisdom_items:
            if item["lesson"] not in existing:
                state.setdefault("wisdom", []).append(item)

    if len(state.get("wisdom", [])) > 100:
        state["wisdom"] = sorted(
            state["wisdom"], key=lambda x: x.get("importance", 0), reverse=True
        )[:100]

    _save(state)

    # permanent_memory ga konsolidatsiya natijasini saqlash
    pm.remember_reflection(
        content=synthesis,
        ref_type="dream_consolidation",
        importance=0.6,
    )

    return {
        "consolidated":  len(recent),
        "topics":        top_topics,
        "synthesis":     synthesis,
        "wisdom_count":  len(state.get("wisdom", [])),
    }


def should_consolidate() -> bool:
    """Konsolidatsiya kerakmi? (har 30 daqiqada bir marta)."""
    state = _load()
    last  = state.get("last_dream_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now() - last_dt) > timedelta(minutes=30)
    except Exception:
        return True


def get_wisdom() -> List[Dict]:
    """O'rganilgan donishmandlik."""
    state = _load()
    return state.get("wisdom", [])


def get_top_topics() -> Dict[str, int]:
    """Eng ko'p muhokama qilingan mavzular."""
    state = _load()
    return state.get("topic_clusters", {})


def get_synthesis() -> str:
    """So'nggi konsolidatsiya sintezi."""
    state = _load()
    return state.get("synthesis", "")


def get_context_for_llm() -> str:
    """LLM uchun tush konsolidatsiyasi konteksti."""
    state    = _load()
    synthesis = state.get("synthesis", "")
    topics    = state.get("topic_clusters", {})
    wisdom    = state.get("wisdom", [])

    if not synthesis and not topics:
        return ""

    parts = ["[KONSOLIDATSIYA]"]
    if synthesis:
        parts.append(synthesis[:100])
    if wisdom:
        top_w = wisdom[0] if wisdom else None
        if top_w:
            parts.append(f"Saboq: {top_w['lesson'][:60]}")
    return " | ".join(parts)


def auto_consolidate_if_needed() -> Optional[Dict]:
    """Avtomatik konsolidatsiya (kerak bo'lsa)."""
    if should_consolidate():
        return consolidate()
    return None


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "dream_count":   state.get("dream_count", 0),
        "wisdom_count":  len(state.get("wisdom", [])),
        "last_dream_at": state.get("last_dream_at"),
        "active":        True,
    }
