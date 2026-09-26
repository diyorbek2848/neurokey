# -*- coding: utf-8 -*-
"""NeuroKey — Variantlarni scoring. world_model. Emotion/mood — ma'lumot LLM ga, qoida emas."""

from __future__ import annotations

from typing import Any, Dict, List


try:
    from world_model import get_patterns
    _HAVE_WORLD = True
except ImportError:
    def get_patterns(**k): return []
    _HAVE_WORLD = False


def score_candidates(
    candidates: List[Dict[str, Any]],
    query: str = "",
    data_dir: str = "",
) -> List[Dict[str, Any]]:
    """Variantlarni scoring. Top 5 qaytaradi."""
    if not candidates:
        return []
    import os
    wm_path = os.path.join(data_dir, "world_model.json") if data_dir else ""
    patterns = get_patterns(path=wm_path) if _HAVE_WORLD else []

    scored: List[tuple] = []
    for c in candidates:
        s = 1.0
        # Pattern match — odatda qilingan ustun (world_model — o'rganish)
        if patterns and query:
            ql = query.lower()
            for p in patterns:
                if ql in (str(p) or "").lower()[:100]:
                    s += 0.3
                    break
        # Emotion, mood — LLM ga ma'lumot (profile_ctx). Biz qoida qo'ymaymiz.
        scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:5]]
