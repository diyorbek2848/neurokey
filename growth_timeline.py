# -*- coding: utf-8 -*-
"""
growth_timeline.py — NeuroKey O'sish Tarixi
============================================
NeuroKey o'zini har yangilaganida bu yerga yozadi.
Investor ko'radi: "47 marta o'zini yangilagan." — isbotlangan tarix.
"""
from __future__ import annotations
import json, os
from datetime import datetime
from typing import List, Dict, Any

_BASE = os.path.dirname(os.path.abspath(__file__))
_TIMELINE_PATH = os.path.join(_BASE, "data", "growth_timeline.json")


def _load() -> List[Dict[str, Any]]:
    try:
        if os.path.exists(_TIMELINE_PATH):
            with open(_TIMELINE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save(entries: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(_TIMELINE_PATH), exist_ok=True)
    with open(_TIMELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def record_improvement(
    organ_name: str,
    reason: str,
    description: str,
    trigger_keywords: List[str] = None,
    confirmed_by_owner: bool = True,
) -> Dict[str, Any]:
    """Yangi organ qo'shilganda timeline ga yozish."""
    entry = {
        "id": len(_load()) + 1,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "organ_file": organ_name,
        "reason": reason,
        "description": description,
        "keywords": trigger_keywords or [],
        "confirmed_by_owner": confirmed_by_owner,
        "timestamp": datetime.now().isoformat(),
    }
    entries = _load()
    entries.append(entry)
    _save(entries)
    return entry


def get_all() -> List[Dict[str, Any]]:
    return _load()


def get_total_count() -> int:
    return len(_load())


def get_summary() -> str:
    """Investor uchun bir jumlada: 'NeuroKey 47 marta o'zini yangilagan'"""
    entries = _load()
    if not entries:
        return "NeuroKey hali o'zini yangilamagan."
    total = len(entries)
    last = entries[-1]
    last_date = last.get("date", "?")
    last_desc = last.get("description", "")[:60]
    return (
        f"NeuroKey {total} marta o'zini yangilagan. "
        f"Oxirgi: {last_date} — {last_desc}."
    )


def print_timeline() -> None:
    """Terminalda chiroyli ko'rsatish."""
    entries = _load()
    if not entries:
        print("\n  [GROWTH] Hali birorta yangilanish yo'q.\n")
        return

    print(f"\n{'='*60}")
    print(f"  NEUROKEY O'SIB BORMOQDA — {len(entries)} ta o'zgarish")
    print(f"{'='*60}")
    for e in entries[-10:]:  # oxirgi 10 ta
        idx    = e.get("id", "?")
        date   = e.get("date", "?")
        desc   = e.get("description", "")[:50]
        reason = e.get("reason", "")[:40]
        print(f"  #{idx:03d} | {date} | {desc}")
        print(f"       Sabab: {reason}")
    if len(entries) > 10:
        print(f"  ... va yana {len(entries)-10} ta o'zgarish")
    print(f"{'='*60}\n")


def get_for_llm_context() -> str:
    """LLM ga berish uchun qisqa kontekst."""
    total = get_total_count()
    if total == 0:
        return ""
    last = get_all()[-1]
    return (
        f"[GROWTH] {total} ta yangilanish. "
        f"Oxirgi: {last.get('description','')[:40]}"
    )
