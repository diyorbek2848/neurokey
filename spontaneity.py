# -*- coding: utf-8 -*-
"""NeuroKey — Kutilmagan qarorlar. Random tanlash (xavfsiz), surprise at self.

Ong har doim mantiqiy emas. 20–30% — 2-chi yoki 3-chi variant tanlanadi.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple


# Xavfli actionlar — spontan tanlanmaydi
_SAFE_ACTIONS = frozenset({
    "respond", "file_read", "file_list", "file_exists", "file_search",
    "process_start", "process_find", "clipboard_get",
    "window_list", "window_by_title",
})
_RISKY_ACTIONS = frozenset({
    "file_delete", "file_write", "file_append", "process_kill",
    "window_close", "clipboard_set",
})


def is_safe(candidate: Dict[str, Any]) -> bool:
    """Xavfsiz — spontan tanlash mumkin."""
    act = (candidate.get("action") or "").lower()
    if act in _RISKY_ACTIONS:
        return False
    if act in _SAFE_ACTIONS:
        return True
    return act not in ("file_delete", "process_kill", "window_close")


def filter_safe(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Faqat xavfsiz variantlar."""
    return [c for c in candidates if is_safe(c)]


def random_choice(top_k: List[Dict[str, Any]], safe_only: bool = True) -> Optional[Dict[str, Any]]:
    """Top_k dan tasodifiy tanlash. safe_only — faqat xavfsiz variantlar."""
    if not top_k:
        return None
    pool = filter_safe(top_k) if safe_only else top_k
    if not pool:
        return top_k[0]
    return random.choice(pool)


def choose_with_spontaneity(
    candidates: List[Dict[str, Any]],
    spontaneity_rate: float,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Tanlash. spontaneity_rate ehtimol — random_choice, aks holda birinchi.
    Qaytaradi: (chosen, was_spontaneous)."""
    if not candidates:
        return (None, False)
    top_k = candidates[:5]
    if random.random() < spontaneity_rate:
        chosen = random_choice(top_k, safe_only=True)
        if chosen:
            return (chosen, True)
    return (top_k[0] if top_k else None, False)
