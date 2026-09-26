# -*- coding: utf-8 -*-
"""NeuroKey — BIRLASHTIRILGAN XOTIRA (Unified Memory).

Xotirasiz suniy ong bo'lmaydi. Bu modul — barcha xotira manbalarini birlashtiradi:
- memory.json (history, 5000 turn)
- long_term_memory (facts, profile)
- consciousness (working_memory, reflections)
- improvements (xatolardan o'rganish)
LLM har safar TO'LIQ kontekstni oladi.
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Any, Dict, List, Optional


class UnifiedMemoryTemporal:
    """Sliding window temporal integration — 'hozir' ni ta'minlaydi."""

    def __init__(self, maxlen: int = 10, window_seconds: float = 5.0):
        self.temporal_window: deque = deque(maxlen=maxlen)
        self.window_seconds = window_seconds

    def remember_moment(self, state: Dict[str, Any]) -> None:
        """Har processing da chaqiriladi. Temporal buffer ga qo'shadi."""
        self.temporal_window.append({"state": dict(state), "timestamp": time.time()})

    def get_current_moment(self) -> Dict[str, Any]:
        """
        'Hozir' — oxirgi window_seconds da nima bo'ldi?
        Bu consciousness.py ga beriladi.
        """
        now = time.time()
        cutoff = now - self.window_seconds
        recent = [m for m in self.temporal_window if m.get("timestamp", 0) >= cutoff]
        if not recent:
            return {"status": "empty", "moments": []}
        return {
            "status": "ok",
            "moments": recent,
            "count": len(recent),
        }


_temporal: Optional[UnifiedMemoryTemporal] = None


def get_temporal_buffer() -> UnifiedMemoryTemporal:
    """Temporal buffer singleton."""
    global _temporal
    if _temporal is None:
        _temporal = UnifiedMemoryTemporal(maxlen=10, window_seconds=5.0)
    return _temporal

# Default limits
MAX_HISTORY_TURNS = 40  # LLM ga uzatiladigan dialog (14 dan 40 ga)
MAX_IMPROVEMENTS = 8
MAX_FACTS = 35
MAX_WORKING_MEMORY = 12  # consciousness working_memory


def get_unified_context(
    memory_store=None,
    long_term_memory=None,
    consciousness=None,
    lang: str = "ru",
    app_dir: str = "",
    query: str = "",
) -> str:
    """
    Barcha xotira manbalaridan birlashtirilgan kontekst.
    Xotirasiz suniy ong bo'lmaydi — har narsa ulangan.
    """
    parts = []
    # 1. Dialog history (ko'proq turn)
    if memory_store and hasattr(memory_store, "data"):
        history = memory_store.data.get("history", [])
        n = min(len(history), MAX_HISTORY_TURNS)
        if n > 0:
            recent = history[-n:]
            lines = []
            for h in recent:
                u = (h.get("user") or "").strip()[:200]
                a = (h.get("assistant") or "").strip()[:250]
                if u:
                    lines.append(f"User: {u}")
                if a:
                    lines.append(f"Ты: {a}")
            if lines:
                parts.append(
                    "ПОЛНАЯ ИСТОРИЯ ДИАЛОГА (ты помнишь всё — это твоя память):\n"
                    + "\n".join(lines[-60:])  # oxirgi 60 qator
                )
    # 1b. Episodic memory — keyword-based qidiruv eski turnlarda
    if query and memory_store and hasattr(memory_store, "data"):
        try:
            from long_term_memory import LongTermMemory as _LTM
            _all_history = memory_store.data.get("history", [])
            _relevant = _LTM.search_episodic_memory(query, _all_history, limit=5, min_turns_ago=MAX_HISTORY_TURNS)
            if _relevant:
                ep_lines = []
                for h in _relevant:
                    u = (h.get("user") or "").strip()[:200]
                    a = (h.get("assistant") or "").strip()[:200]
                    if u:
                        ep_lines.append(f"User: {u}")
                    if a:
                        ep_lines.append(f"Ты: {a}")
                if ep_lines:
                    parts.append(
                        "ЭПИЗОДИЧЕСКАЯ ПАМЯТЬ (ты это говорил/обсуждал раньше — вспомни и учти):\n"
                        + "\n".join(ep_lines)
                    )
        except Exception:
            pass
    # 2. Improvements (xatolardan o'rganish)
    if memory_store and hasattr(memory_store, "data"):
        improvements = memory_store.data.get("improvements", [])
        if improvements:
            imp = improvements[-MAX_IMPROVEMENTS:]
            imp_lines = [f"- {i.get('error', '')[:80]} → {i.get('fix', '')[:80]}" for i in imp if i.get("fix")]
            if imp_lines:
                parts.append("Ты учился на ошибках (используй):\n" + "\n".join(imp_lines[-5:]))
    # 3. Long-term facts (profile_ctx da ham bor — bu yerda qisqaroq)
    if long_term_memory and hasattr(long_term_memory, "get_user_facts_for_llm"):
        try:
            facts = long_term_memory.get_user_facts_for_llm(limit=MAX_FACTS)
            if facts:
                parts.append(facts)
        except Exception:
            pass
    # 3b. Keyword-based facts retrieval from LTM DB
    if query and long_term_memory and hasattr(long_term_memory, "search_facts_by_keywords"):
        try:
            kw_facts = long_term_memory.search_facts_by_keywords(query, limit=8)
            if kw_facts:
                parts.append(kw_facts)
        except Exception:
            pass
    # 4. Consciousness (working_memory + reflections)
    if consciousness and hasattr(consciousness, "data"):
        working = consciousness.data.get("working_memory", [])[-6:]
        if working:
            lines = []
            for w in working:
                u = (w.get("user") or "").strip()[:150]
                a = (w.get("assistant") or "").strip()[:200]
                th = (w.get("thought") or "").strip()[:100]
                if u:
                    lines.append(f"User: {u}")
                if a:
                    lines.append(f"Ты: {a}")
                if th:
                    lines.append(f"Твоя мысль: {th}")
            if lines:
                parts.append("Твоё рабочее состояние (продолжай):\n" + "\n".join(lines[-20:]))
        reflections = consciousness.data.get("reflections", [])[-4:]
        if reflections:
            refs = [r.get("thought", "")[:80] for r in reflections if r.get("thought")]
            if refs:
                parts.append("Твои последние мысли: " + "; ".join(refs))
    if not parts:
        return ""
    out = (
        "UNIFIED MEMORY — вся твоя память (без памяти нет сознания):\n\n"
        + "\n\n".join(parts)
        + "\n\nИспользуй ВСЁ. Ты помнишь. Ты — одна непрерывная сущность."
    )
    return out[:18000]  # kontekst limiti
