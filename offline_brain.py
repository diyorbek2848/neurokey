# -*- coding: utf-8 -*-
"""
Fast local "brain" for offline demo.
Rule-based semantic matching with response variation (<1s, no server).
"""
import json
import os
import random
import re
from collections import deque

_BRAIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_knowledge_ru.json")
_BRAIN = []
_LOADED = False
_RECENT_BY_ID = {}


def _tokenize(text: str):
    return [t for t in re.split(r"[^a-zA-Zа-яА-ЯёЁ0-9]+", (text or "").lower()) if t]


def _load_brain():
    global _LOADED, _BRAIN
    if _LOADED:
        return
    _LOADED = True
    try:
        with open(_BRAIN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            _BRAIN = data
    except Exception:
        _BRAIN = []


def _extract_candidates(text: str):
    t = (text or "").strip()
    if not t:
        return []
    parts = [t]
    # Agar user bitta gap ichida bir nechta savol bersa, har bir bo'lakni ham tekshiramiz.
    for sep in ("?", " и ", " ham ", ";"):
        new_parts = []
        for p in parts:
            if sep in p:
                new_parts.extend([x.strip() for x in p.split(sep) if x.strip()])
            else:
                new_parts.append(p)
        parts = new_parts
    # Qo'shtirnoq ichidagi savol ham alohida candidate bo'lsin
    for m in re.findall(r"[\"“](.*?)[\"”]", t):
        if m.strip():
            parts.append(m.strip())
    # Uzunroq/muhim bo'laklar oldinda
    parts = sorted(set(parts), key=len, reverse=True)
    return parts


def _pick_non_repeating(intent_id: str, responses):
    if not responses:
        return None
    if len(responses) == 1:
        return responses[0]
    recent = _RECENT_BY_ID.setdefault(intent_id, deque(maxlen=min(5, max(2, len(responses) // 2))))
    candidates = [r for r in responses if r not in recent]
    if not candidates:
        recent.clear()
        candidates = list(responses)
    chosen = random.choice(candidates)
    recent.append(chosen)
    return chosen


def answer_from_brain(text: str):
    _load_brain()
    if not _BRAIN:
        return None
    best = None
    best_score = 0
    for candidate in _extract_candidates(text):
        tokens = set(_tokenize(candidate))
        if not tokens:
            continue
        for item in _BRAIN:
            kws = set((item.get("keywords") or []))
            if not kws:
                continue
            hit = len(tokens.intersection(kws))
            # optional regex boost
            pat = item.get("pattern") or ""
            if pat:
                try:
                    if re.search(pat, candidate, re.IGNORECASE):
                        hit += 2
                except Exception:
                    pass
            if hit > best_score:
                best_score = hit
                best = item

    if not best or best_score < 2:
        return None

    responses = best.get("responses") or []
    if not responses:
        return None
    return _pick_non_repeating(best.get("id") or "generic", responses)
