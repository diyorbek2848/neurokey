# -*- coding: utf-8 -*-
"""NeuroKey — Pushaymon. O'tgan xato — keyingi qarorga ta'sir."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional


_MAX_REGRET = 20
_regret_queue: deque = deque(maxlen=_MAX_REGRET)


def _action_key(c: Dict[str, Any]) -> str:
    act = c.get("action") or ""
    path = c.get("path") or c.get("src") or c.get("name_or_pid") or ""
    return f"{act} {path}"[:80]


def add_fail(action: Dict[str, Any]) -> None:
    """Muvaffaqiyatsiz amal — pushaymon qo'shish."""
    key = _action_key(action)
    if key:
        _regret_queue.append(key)


def should_avoid(candidate: Dict[str, Any]) -> bool:
    """Bu variantdan qochish kerakmi? (o'tganda yomon bo'lgan)."""
    key = _action_key(candidate)
    if not key:
        return False
    return key in _regret_queue


def filter_regret(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pushaymon bo'lgan variantlarni olib tashlash. (Deprecated: regret LLM ga ma'lumot.)"""
    return [c for c in candidates if not should_avoid(c)]


def get_regret_for_llm() -> str:
    """LLM uchun pushaymon ro'yxati — ma'lumot (qoida emas)."""
    if not _regret_queue:
        return ""
    items = list(_regret_queue)[-10:]  # oxirgi 10 ta
    return "Recently failed (consider avoiding): " + "; ".join(items)


def get_regret_count() -> int:
    """Pushaymon ro'yxatidagi elementlar soni."""
    return len(_regret_queue)
