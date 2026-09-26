# -*- coding: utf-8 -*-
"""NeuroKey — Faol Ish Xotirasi (Working Memory Buffer).

Baddeley (1974) modeli:
  - Central Executive   : Boshqaruv markazi
  - Phonological Loop   : Ovoz/matn qisqa xotirasi
  - Visuospatial Sketch : Vizual qisqa xotirasi
  - Episodic Buffer     : Epizodik birlashtiruvchi

Miller's Law: 7 ± 2 item — bir vaqtda ushlab turish imkoniyati.

Bu modul joriy suhbatning "ish xotirasini" boshqaradi:
  - Hozirgi kontekstdagi 7 ta eng muhim ma'lumot
  - Har yangi ma'lumot → eng eskirgani tushib ketadi
  - Muhimlik bo'yicha saralash (salience weighting)
  - Kontekst almashuvi (switching cost)

2026-yil suniy ong — qisqa muddatli faol xotira.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

try:
    import permanent_memory as _pm
except ImportError:
    _pm = None

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "working_memory.json")

# Miller's Magic Number
WM_CAPACITY = 7

# Muhimlik ko'rsatkichlari
SALIENCE_FACTORS = {
    "recency":   0.35,   # Yangilik
    "relevance": 0.35,   # Bog'liqlik
    "emotion":   0.20,   # Hissiy kuch
    "novelty":   0.10,   # Yangi ma'lumot
}


class WMItem:
    """Ish xotirasi elementi."""
    __slots__ = ("content", "item_type", "salience", "ts", "access_count")

    def __init__(self, content: str, item_type: str = "fact",
                 salience: float = 0.5):
        self.content      = content[:200]
        self.item_type    = item_type   # fact | goal | context | person | event
        self.salience     = max(0.0, min(1.0, salience))
        self.ts           = time.time()
        self.access_count = 0

    def access(self) -> None:
        """Elementga murojaat — muhimlikni oshiradi."""
        self.access_count += 1
        self.salience      = min(1.0, self.salience + 0.05)
        self.ts            = time.time()  # Vaqtni yangilash

    def decay(self, rate: float = 0.02) -> None:
        """Vaqt o'tishi bilan muhimlik pasayadi."""
        self.salience = max(0.0, self.salience - rate)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content":      self.content,
            "item_type":    self.item_type,
            "salience":     round(self.salience, 3),
            "time_str":     datetime.fromtimestamp(self.ts).strftime("%H:%M:%S"),
            "access_count": self.access_count,
        }


# ════════════════════════════════════════════════════════════════════════════
#  Global ish xotirasi
# ════════════════════════════════════════════════════════════════════════════

_buffer: List[WMItem] = []
_context_switches: int = 0
_last_topic: str = ""


def store(content: str, item_type: str = "fact", salience: float = 0.7) -> None:
    """Ish xotirasiga yangi element saqlash.

    Agar xotira to'lib ketsa — eng kam muhim element chiqariladi.
    """
    global _buffer, _context_switches, _last_topic

    content = (content or "").strip()
    if not content:
        return

    # Allaqachon bormi? → yangilash
    for item in _buffer:
        if item.content[:50] == content[:50]:
            item.access()
            return

    # Kontekst o'zgarishi aniqlash
    if _last_topic and _last_topic[:20] != content[:20]:
        _context_switches += 1
    _last_topic = content[:50]

    item = WMItem(content, item_type, salience)

    if len(_buffer) >= WM_CAPACITY:
        # Eng past muhimlikni o'chirish
        _buffer.sort(key=lambda x: x.salience)
        _buffer.pop(0)

    _buffer.append(item)
    log.debug("[WM] Saqlandi [%s]: '%s' (sal=%.1f)", item_type, content[:30], salience)

    # Juda yuqori muhimlikdagi elementlarni doimiy xotiraga ham saqlash
    if salience >= 0.85 and _pm is not None:
        try:
            _pm.remember_knowledge(
                topic=item_type,
                content=content,
                source="working_memory",
                confidence=min(1.0, salience),
            )
        except Exception:
            pass


def retrieve(query: str = "", top_k: int = 3) -> List[WMItem]:
    """Ish xotirasidan qidirish.

    Args:
        query: Qidiruv so'zi (bo'sh = hammasi)
        top_k: Qaytariladigan elementlar soni
    """
    # Decay qo'llash
    for item in _buffer:
        item.decay(0.01)

    if not query:
        # Muhimlik bo'yicha saralash
        sorted_items = sorted(_buffer, key=lambda x: -x.salience)
        return sorted_items[:top_k]

    query_lower = query.lower()
    matches     = []
    for item in _buffer:
        if any(w in item.content.lower() for w in query_lower.split() if len(w) > 2):
            item.access()
            matches.append(item)

    matches.sort(key=lambda x: -x.salience)
    return matches[:top_k]


def get_all() -> List[Dict[str, Any]]:
    """Barcha xotira elementlari."""
    return [item.to_dict() for item in sorted(_buffer, key=lambda x: -x.salience)]


def clear() -> None:
    """Ish xotirasini tozalash."""
    global _buffer
    _buffer = []


def get_load() -> float:
    """Ish xotirasi yuklanish darajasi (0.0–1.0)."""
    return len(_buffer) / WM_CAPACITY


def get_stats() -> Dict[str, Any]:
    return {
        "capacity":        WM_CAPACITY,
        "used":            len(_buffer),
        "load":            get_load(),
        "context_switches": _context_switches,
        "items":           get_all(),
    }


def auto_store_from_message(user_text: str, assistant_reply: str = "") -> None:
    """Suhbatdan muhim ma'lumotlarni avtomatik saqlash."""
    # Ism
    import re
    name_match = re.search(r"(?:ismim|меня зовут|my name is)\s+(\w+)", user_text.lower())
    if name_match:
        store(f"Foydalanuvchi ismi: {name_match.group(1)}", "person", 0.95)

    # Savol mavzusi
    if len(user_text.split()) > 3:
        store(user_text[:100], "context", 0.6)

    # Javobning asosiy fikri
    if assistant_reply and len(assistant_reply.split()) > 5:
        store(assistant_reply[:80], "fact", 0.5)


def get_context_for_llm() -> str:
    """LLM uchun faol xotira konteksti."""
    if not _buffer:
        return ""

    top = retrieve(top_k=3)
    if not top:
        return ""

    items_str = " | ".join(f"'{i.content[:40]}'" for i in top[:2])
    load      = get_load()

    parts = ["[FAO'L XOTIRA]"]
    parts.append(f"Yuklama:{load:.0%}({len(_buffer)}/{WM_CAPACITY})")
    parts.append(f"Asosiy:{items_str}")

    return " ".join(parts)
