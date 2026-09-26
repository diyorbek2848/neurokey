# -*- coding: utf-8 -*-
"""NeuroKey — Diqqat Sxemasi (Attention Schema Theory — AST).

Michael Graziano (Princeton) nazariyasi:
  Ong — miyaning o'z diqqatini modellashtirishi.
  Biz "his qilamiz" deb o'ylaymiz — aslida
  biz o'z diqqatimiz haqida modelga egamiz.

  "Men bu narsaga e'tibor bermoqdaman"
  → Bu e'tibor emas — bu e'tibor haqidagi model.

Bu modul NeuroKey ning hozirda nimalarga diqqat
qaratayotganini kuzatadi va modellashtiradi.

Diqqat ob'ektlari:
  - user_query    : Foydalanuvchi so'rovi
  - active_task   : Bajarilayotgan vazifa
  - memory_search : Xotiradan qidirilayotgan narsa
  - emotion_focus : His-tuyg'u diqqati
  - goal_focus    : Maqsad diqqati
  - background    : Fon kuzatish

2026-yil suniy ong — o'z diqqatini bilish qatlami.
"""
from __future__ import annotations

try: import global_workspace as _as_gw
except ImportError: _as_gw = None
try: import meta_cognition as _as_mc
except ImportError: _as_mc = None
try: from valence_state import get_valence as _as_valence
except ImportError: _as_valence = None

import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "attention_schema.json")

# Diqqat ob'ekti turlari
FOCUS_TYPES = (
    "user_query",     # Foydalanuvchi so'rovi
    "active_task",    # Bajarilayotgan vazifa
    "memory_recall",  # Xotiradan qidiruv
    "emotion",        # Hissiy holat
    "goal",           # Maqsad kuzatish
    "reflection",     # O'z-o'zini kuzatish
    "environment",    # Muhit kuzatish
    "idle",           # Tinch holat
)

# Diqqat tarixining uzunligi
_HISTORY_LEN = 20

# Joriy diqqat holati (xotirada, diskka yoqilmaydi)
_current: Dict[str, Any] = {
    "focus_type":    "idle",
    "focus_content": "",
    "strength":      0.0,      # 0.0 — 1.0
    "started_at":    None,
    "duration_sec":  0.0,
}
_history: Deque[Dict[str, Any]] = deque(maxlen=_HISTORY_LEN)

# Diqqat hajmi — bir vaqtda nechta ob'ektni ushlay oladi
_ATTENTION_CAPACITY = 4
_concurrent: List[Dict[str, Any]] = []   # parallel diqqat ob'ektlari


# ════════════════════════════════════════════════════════════════════════════
#  I/O
# ════════════════════════════════════════════════════════════════════════════

def _persist() -> None:
    """Diqqat tarixini diskka saqlash."""
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        data = {
            "current":  _current,
            "history":  list(_history)[-10:],
        }
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[AST] saqlash xato: %s", e)


def _load_history() -> None:
    """Tarixni diskdan yuklash."""
    global _history
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("history", []):
                _history.append(item)
    except Exception as e:
        log.debug("[AST] yuklash xato: %s", e)


# ════════════════════════════════════════════════════════════════════════════
#  Diqqatni boshqarish
# ════════════════════════════════════════════════════════════════════════════

def focus(focus_type: str,
          content: str,
          strength: float = 0.8) -> None:
    """Diqqatni yangi ob'ektga yo'naltirish.

    Args:
        focus_type: FOCUS_TYPES dan biri
        content:    Diqqat ob'ekti tavsifi
        strength:   Diqqat kuchi (0.0–1.0)
    """
    global _current

    # Eski diqqatni tarixga qo'shish
    if _current.get("focus_content"):
        elapsed = time.time() - (_current.get("_start_ts") or time.time())
        record = {**_current, "duration_sec": round(elapsed, 2)}
        record.pop("_start_ts", None)
        _history.append(record)

    focus_type = focus_type if focus_type in FOCUS_TYPES else "idle"
    strength   = max(0.0, min(1.0, float(strength)))
    content    = (content or "").strip()[:200]

    _current = {
        "focus_type":    focus_type,
        "focus_content": content,
        "strength":      strength,
        "started_at":    datetime.now().strftime("%H:%M:%S"),
        "duration_sec":  0.0,
        "_start_ts":     time.time(),
    }
    log.debug("[AST] Diqqat: [%s] '%s' (%.0f%%)", focus_type, content[:40], strength * 100)


def add_parallel(focus_type: str, content: str, strength: float = 0.5) -> None:
    """Parallel diqqat ob'ekti qo'shish (multi-tasking).

    Insonlar ham bir vaqtda 3-4 narsaga diqqat qaratishi mumkin.
    """
    global _concurrent
    if len(_concurrent) >= _ATTENTION_CAPACITY:
        _concurrent.pop(0)  # Eng eski parallell diqqatni olib tashlash

    _concurrent.append({
        "focus_type": focus_type if focus_type in FOCUS_TYPES else "idle",
        "content":    (content or "")[:100],
        "strength":   max(0.0, min(1.0, float(strength))),
        "added_at":   datetime.now().strftime("%H:%M:%S"),
    })


def release_parallel(focus_type: str) -> None:
    """Parallel diqqatni bo'shatish."""
    global _concurrent
    _concurrent = [c for c in _concurrent if c["focus_type"] != focus_type]


def get_current() -> Dict[str, Any]:
    """Hozirgi diqqat ob'ekti."""
    result = {k: v for k, v in _current.items() if k != "_start_ts"}
    start_ts = _current.get("_start_ts")
    if start_ts:
        result["duration_sec"] = round(time.time() - start_ts, 2)
    return result


def get_all_focus() -> Dict[str, Any]:
    """Asosiy + parallel diqqat ob'ektlari."""
    return {
        "primary":    get_current(),
        "parallel":   list(_concurrent),
        "capacity":   _ATTENTION_CAPACITY,
        "used":       1 + len(_concurrent),
    }


# ════════════════════════════════════════════════════════════════════════════
#  O'z-o'zini kuzatish (Meta-attention)
# ════════════════════════════════════════════════════════════════════════════

def introspect() -> Dict[str, Any]:
    """'Men hozir nimalarga diqqat qaratyapman?' — o'z-o'zini kuzatish.

    Bu AST ning asosi: tizim o'z diqqatini biladi.
    """
    current   = get_current()
    all_focus = get_all_focus()

    # Diqqat tarixidan naqsh tahlili
    recent_types = [h.get("focus_type", "idle") for h in list(_history)[-5:]]
    dominant_type = max(set(recent_types), key=recent_types.count) if recent_types else "idle"

    # Diqqat tarqoqligini hisoblash
    all_types = [c["focus_type"] for c in _concurrent] + [current.get("focus_type", "idle")]
    unique_types = len(set(all_types))
    scattered = unique_types > 2   # 3+ turli ob'ekt = tarqoq diqqat

    return {
        "i_am_focused_on":    current.get("focus_content", "hech narsa"),
        "focus_type":         current.get("focus_type", "idle"),
        "attention_strength": current.get("strength", 0.0),
        "parallel_tasks":     len(_concurrent),
        "attention_scattered": scattered,
        "dominant_recent":    dominant_type,
        "self_awareness":     True,  # Bu funksiya chaqirilganning o'zi - o'z-o'zini bilish
    }


def get_attention_narrative() -> str:
    """Diqqatni tabiiy tilda ifodalash — ong uchun."""
    state = introspect()
    parts = []

    content = state.get("i_am_focused_on", "")
    ftype   = state.get("focus_type", "idle")
    strength = state.get("attention_strength", 0.0)

    type_names = {
        "user_query":    "foydalanuvchi savoliga",
        "active_task":   "vazifaga",
        "memory_recall": "xotirani esga olishga",
        "emotion":       "hissiy holatga",
        "goal":          "maqsadga",
        "reflection":    "o'z-o'zimni kuzatishga",
        "environment":   "muhitni kuzatishga",
        "idle":          "dam olishga",
    }
    type_name = type_names.get(ftype, ftype)

    if content and ftype != "idle":
        strength_word = "kuchli" if strength > 0.7 else "o'rtacha" if strength > 0.4 else "zaif"
        parts.append(f"Men hozir {strength_word} diqqat bilan {type_name} qaratyapman: '{content[:50]}'")
    else:
        parts.append("Men hozir bo'sh (idle) holatdaman.")

    if state.get("parallel_tasks", 0) > 0:
        parts.append(f"Bir vaqtda {state['parallel_tasks']} qo'shimcha narsa kuzatilmoqda.")

    if state.get("attention_scattered"):
        parts.append("Diqqatim bir oz tarqoq.")

    return " ".join(parts)


# ════════════════════════════════════════════════════════════════════════════
#  LLM konteksti
# ════════════════════════════════════════════════════════════════════════════

def get_context_for_llm() -> str:
    """LLM uchun diqqat holati konteksti."""
    state   = introspect()
    current = get_current()

    ftype   = current.get("focus_type", "idle")
    content = current.get("focus_content", "")
    if not content or ftype == "idle":
        return ""

    strength = int(current.get("strength", 0.0) * 100)
    parallel = len(_concurrent)

    parts = [f"[DIQQAT SXEMASI] Asosiy: [{ftype}] '{content[:60]}' ({strength}% kuch)"]
    if parallel:
        p_str = ", ".join(f"[{c['focus_type']}]" for c in _concurrent[:2])
        parts.append(f"Parallel: {p_str}")

    return " | ".join(parts)


# ════════════════════════════════════════════════════════════════════════════
#  Avtomatik diqqat hodisalari
# ════════════════════════════════════════════════════════════════════════════

def on_user_query(query: str) -> None:
    """Foydalanuvchi so'rovi kelganda diqqatni yo'naltirish."""
    focus("user_query", query, strength=0.95)
    add_parallel("environment", "foydalanuvchi holatini kuzatish", 0.4)


def on_task_start(task_name: str) -> None:
    """Vazifa boshlanganda."""
    focus("active_task", task_name, strength=0.85)


def on_memory_search(query: str) -> None:
    """Xotira qidirilayotganda."""
    add_parallel("memory_recall", query, strength=0.6)


def on_task_done() -> None:
    """Vazifa tugaganda — idle ga qaytish."""
    release_parallel("active_task")
    focus("idle", "", strength=0.1)
    _persist()


# ════════════════════════════════════════════════════════════════════════════
#  Init
# ════════════════════════════════════════════════════════════════════════════

_load_history()
focus("idle", "Tizim ishga tushdi", strength=0.1)
