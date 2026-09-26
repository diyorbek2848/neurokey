# -*- coding: utf-8 -*-
"""NeuroKey — User yo'q bo'lganda: curiosity, boredom → variantlar."""

from __future__ import annotations

import os
from typing import Any, Dict, List


def autonomous_candidates(
    context: Dict[str, Any],
    seek_novelty: bool = False,
) -> List[Dict[str, Any]]:
    """User yo'q — curiosity, zerikish. Exploration amallar.
    seek_novelty=True — yangilik qidirish (boredom yuqori)."""
    docs = os.path.expanduser("~\\Documents") if os.name == "nt" else os.path.expanduser("~/Documents")
    base = [
        {"action": "file_list", "path": docs},
        {"action": "window_list"},
        {"action": "clipboard_get"},
    ]
    if seek_novelty:
        base.append({"action": "file_search", "root": docs, "pattern": "*.txt"})
    return base
