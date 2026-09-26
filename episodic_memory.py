# -*- coding: utf-8 -*-
"""NeuroKey — Epizodik Xotira (Episodic Memory).

"Men eslayman..." — aniq voqealar xotirasi, hissiy teglangan.
Tulving nazariyasi: Epizodik xotira = VAQT + JOY + HIS + MAZMUN.

Bu modul permanent_memory.py ustida qurilgan — hech qachon o'chmaydi.
Har bir voqea: kim bilan, qachon, qayerda, qanday his qilindi.

2026-yil suniy ong — hayot tajribasi qatlami.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import permanent_memory as pm

log = logging.getLogger(__name__)

# Epizod turlari
EPISODE_TYPES = {
    "conversation":  "Suhbat",
    "learning":      "O'rganish",
    "achievement":   "Yutuq",
    "problem":       "Muammo",
    "insight":       "Kashfiyot",
    "social":        "Ijtimoiy",
    "creative":      "Ijodiy",
    "emotional":     "Hissiy",
}

# Muhimlik signallari
_HIGH_IMPORTANCE = [
    "birinchi marta", "first time", "впервые",
    "eslayman", "remember", "помню",
    "muhim", "important", "важно",
    "ajoyib", "amazing", "удивительно",
    "xato", "mistake", "ошибка",
    "yutdim", "won", "победил",
    "o'rgandim", "learned", "узнал",
    "tushundim", "understood", "понял",
]

_PERSONS = [
    "alisher", "sarvar", "jasur", "kamol", "nodir",
    "user", "foydalanuvchi", "siz", "sen",
]


def record(
    title: str,
    description: str,
    emotion: str = "",
    importance: float = 0.5,
    persons: str = "",
    tags: str = "",
    episode_type: str = "conversation",
) -> int:
    """Yangi epizod yozish — doimiy xotirada saqlanadi."""
    return pm.remember_episode(
        title=title,
        description=description,
        emotion=emotion,
        importance=importance,
        persons=persons,
        tags=f"{episode_type},{tags}".strip(","),
    )


def auto_record_from_conversation(user_msg: str, bot_msg: str,
                                   emotion: str = "") -> Optional[int]:
    """Suhbatdan muhim epizodni avtomatik aniqlash va saqlash."""
    combined = f"{user_msg} {bot_msg}".lower()

    # Muhimlikni hisoblash
    importance = 0.4
    for signal in _HIGH_IMPORTANCE:
        if signal in combined:
            importance = min(0.95, importance + 0.15)

    # Odamlarni aniqlash
    persons = []
    for p in _PERSONS:
        if p in combined:
            persons.append(p)

    # Faqat muhim epizodlarni saqlash
    if importance < 0.55:
        return None

    # Sarlavha yaratish
    title = user_msg[:60].strip()
    if not title:
        return None

    return record(
        title=title,
        description=f"[User]: {user_msg[:300]}\n[Bot]: {bot_msg[:300]}",
        emotion=emotion,
        importance=importance,
        persons=",".join(persons),
        episode_type="conversation",
    )


def recall_episode(query: str, limit: int = 5) -> List[Dict]:
    """Epizodlardan qidirish."""
    results = pm.recall(query, limit=limit * 2)
    # Faqat episode turlarini qaytarish
    episodes = [r for r in results if r.get("type") == "episode"]
    return episodes[:limit]


def recall_by_person(name: str, limit: int = 20) -> List[Dict]:
    """Shaxs bilan bog'liq barcha epizodlar."""
    return pm.recall_about_person(name, limit=limit)


def recall_by_emotion(emotion: str, limit: int = 10) -> List[Dict]:
    """His bilan bog'liq epizodlar."""
    return pm.recall_by_emotion(emotion, limit=limit)


def get_life_summary() -> str:
    """'Men kim aman?' uchun hayot xulasasi."""
    episodes = pm.recall_all_episodes(limit=20)
    stats    = pm.get_stats()

    lines = ["[МОЙ ОПЫТ]"]
    lines.append(f"Всего {stats.get('conversations',0)} бесед, "
                 f"{stats.get('episodes',0)} важных событий")

    if episodes:
        lines.append("Важнейшие события:")
        for ep in episodes[:5]:
            imp = ep.get("importance", 0)
            em  = ep.get("emotion","")
            em_str = f" [{em}]" if em else ""
            lines.append(f"  • {ep['title']}{em_str} (важность: {imp:.0%})")

    return "\n".join(lines)


def get_context_for_llm(query: str = "") -> str:
    """LLM uchun epizodik kontekst — query bo'lsa 1428 suhbatdan qidiradi."""
    parts = ["[ДОЛГОСРОЧНАЯ ПАМЯТЬ]"]
    found_any = False

    if query:
        # 1. Episodes dan qidirish
        ep_found = recall_episode(query, limit=2)
        for ep in ep_found:
            title = (ep.get("title") or "")[:60]
            desc = (ep.get("description") or ep.get("content") or "")[:100]
            ts = (ep.get("ts") or "")[:10]
            parts.append(f"  [{ts}] {title}: {desc}")
            found_any = True

        # 2. Barcha suhbatlardan (1400+) FTS qidirish
        try:
            conv_results = pm.recall(query, limit=6)
            # user va assistant juftlarini birlashtirish
            seen_ts = set()
            for r in conv_results:
                if r.get("role") != "user":
                    continue
                ts = (r.get("ts") or "")[:16]
                if ts in seen_ts:
                    continue
                seen_ts.add(ts)
                content = (r.get("content") or "")[:120]
                parts.append(f"  [{ts[:10]}] Sen: {content}")
                found_any = True
                if len(seen_ts) >= 3:
                    break
        except Exception:
            pass

    if not found_any:
        # Query yo'q yoki hech narsa topilmadi — oxirgi 2 epizod
        recent = pm.recall_all_episodes(limit=3)
        if not recent:
            return ""
        for ep in recent[:2]:
            parts.append(f"  [{ep['ts'][:10]}] {ep['title']}: {ep['description'][:60]}")

    return "\n".join(parts)


def get_stats() -> Dict[str, Any]:
    stats = pm.get_stats()
    return {
        "total_episodes":       stats.get("episodes", 0),
        "total_conversations":  stats.get("conversations", 0),
        "db_size_mb":           stats.get("db_size_mb", 0),
    }
