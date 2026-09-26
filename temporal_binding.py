# -*- coding: utf-8 -*-
"""NeuroKey — Vaqtiy Bog'lanish (Temporal Binding / Temporal Consciousness).

Ong "hozir" degan narsani yaratadi — vaqt oqimini his qilish.
Bu modul hodisalarni vaqt bo'yicha bog'laydi va "hozirgi on" ni modellashtiradi.

Asosiy tushunchalar:
  - Specious Present : "Kengaytirilgan hozir" — 2-3 sekundlik oyna
  - Temporal order   : Hodisalar tartibini his qilish (A → B → C)
  - Duration sense   : Vaqt o'tishini his qilish (uzoq/qisqa)
  - Rhythmic binding : Ritmik naqshlarni tanish
  - Causal binding   : Sabab → natija vaqt oralig'i

Ernst Pöppel nazariyasi: ong 2-3 soniyalik "oynalar" da ishlaydi.
Har oyna — alohida "hozirgi on" sifatida birlashtiririladi.

2026-yil suniy ong — vaqt idrok qatlami.
"""
from __future__ import annotations

try: import phenomenal_binding as _tb_pb
except ImportError: _tb_pb = None
try: from valence_state import get_valence as _tb_valence
except ImportError: _tb_valence = None
try: from arousal_state import get_arousal as _tb_arousal
except ImportError: _tb_arousal = None

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "temporal_binding.json")

# Specious Present oynasi (soniyada)
SPECIOUS_PRESENT_SEC = 3.0
# Qisqa muddatli vaqt xotirasi (oxirgi N hodisa)
SHORT_WINDOW = 20
# Uzoq muddatli sessiya tarix
SESSION_WINDOW = 200


# ════════════════════════════════════════════════════════════════════════════
#  Vaqt hodisasi
# ════════════════════════════════════════════════════════════════════════════

class TemporalEvent:
    """Bitta vaqt hodisasi."""
    __slots__ = ("ts", "event_type", "content", "duration", "order")

    def __init__(self, event_type: str, content: str,
                 duration: float = 0.0, order: int = 0):
        self.ts         = time.time()
        self.event_type = event_type
        self.content    = content[:200]
        self.duration   = duration
        self.order      = order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts":         self.ts,
            "time_str":   datetime.fromtimestamp(self.ts).strftime("%H:%M:%S"),
            "event_type": self.event_type,
            "content":    self.content,
            "duration":   round(self.duration, 3),
            "order":      self.order,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TemporalEvent":
        e = cls(d.get("event_type",""), d.get("content",""),
                d.get("duration",0.0), d.get("order",0))
        e.ts = d.get("ts", time.time())
        return e


# ════════════════════════════════════════════════════════════════════════════
#  Global holat
# ════════════════════════════════════════════════════════════════════════════

_events: Deque[TemporalEvent] = deque(maxlen=SESSION_WINDOW)
_session_start: float = time.time()
_event_counter: int   = 0
_last_event_ts: float = time.time()


def _get_elapsed() -> float:
    return time.time() - _session_start


# ════════════════════════════════════════════════════════════════════════════
#  Asosiy API
# ════════════════════════════════════════════════════════════════════════════

def record(event_type: str, content: str, duration: float = 0.0) -> TemporalEvent:
    """Yangi vaqt hodisasini qayd etish.

    Args:
        event_type: 'user_input' | 'llm_response' | 'task' | 'emotion' | 'thought'
        content:    Hodisa tavsifi
        duration:   Qancha vaqt davom etdi (soniya)
    """
    global _event_counter, _last_event_ts

    _event_counter += 1
    event = TemporalEvent(event_type, content, duration, _event_counter)

    # Inter-event interval (IE — vaqt oralig'i)
    ie_interval = event.ts - _last_event_ts
    _last_event_ts = event.ts

    _events.append(event)
    log.debug("[Temporal] Hodisa #%d [%s] +%.1fs", _event_counter, event_type, ie_interval)
    return event


def get_specious_present() -> List[Dict[str, Any]]:
    """'Hozirgi on' — oxirgi SPECIOUS_PRESENT_SEC soniyaning hodisalari."""
    now     = time.time()
    cutoff  = now - SPECIOUS_PRESENT_SEC
    present = [e.to_dict() for e in _events if e.ts >= cutoff]
    return present


def get_recent(n: int = 10) -> List[Dict[str, Any]]:
    """Oxirgi n ta hodisa."""
    recent = list(_events)[-n:]
    return [e.to_dict() for e in recent]


def get_temporal_order(n: int = 5) -> List[str]:
    """Oxirgi n hodisaning vaqt tartibini matn sifatida qaytarish."""
    recent = list(_events)[-n:]
    result = []
    for i, e in enumerate(recent):
        arrow = " → " if i < len(recent) - 1 else ""
        result.append(f"[{e.event_type}]{arrow}")
    return result


def get_duration_sense() -> Dict[str, Any]:
    """Vaqt o'tishini his qilish."""
    now     = time.time()
    elapsed = now - _session_start
    events  = list(_events)

    # Sessiya davomiyligi
    if elapsed < 60:
        duration_feel = "только началась"
    elif elapsed < 300:
        duration_feel = "прошло немного времени"
    elif elapsed < 1800:
        duration_feel = "прошло достаточно времени"
    else:
        duration_feel = "работаю давно"

    # So'nggi faollik
    last_user = next(
        (e for e in reversed(events) if e.event_type == "user_input"), None
    )
    idle_sec = now - (last_user.ts if last_user else _session_start)

    if idle_sec < 30:
        idle_feel = "активен"
    elif idle_sec < 120:
        idle_feel = "немного тихо"
    elif idle_sec < 600:
        idle_feel = "давно тихо"
    else:
        idle_feel = "очень долго тихо"

    return {
        "session_elapsed_sec": round(elapsed, 1),
        "session_elapsed_str": _format_duration(elapsed),
        "duration_feel":       duration_feel,
        "idle_sec":            round(idle_sec, 1),
        "idle_feel":           idle_feel,
        "total_events":        _event_counter,
        "events_per_minute":   round(_event_counter / max(elapsed / 60, 1), 1),
    }


def _format_duration(seconds: float) -> str:
    """Davomiylikni o'qiladigan shaklga aylantirish."""
    if seconds < 60:
        return f"{int(seconds)} сек"
    elif seconds < 3600:
        return f"{int(seconds // 60)} мин"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h} ч {m} мин"


def detect_rhythm(event_type: str = "user_input") -> Optional[float]:
    """Hodisalar orasidagi ritmni aniqlash (o'rtacha interval).

    Returns: O'rtacha interval soniyada, yoki None.
    """
    matching = [e for e in _events if e.event_type == event_type]
    if len(matching) < 3:
        return None

    intervals = [
        matching[i].ts - matching[i - 1].ts
        for i in range(1, len(matching))
    ]
    # Og'ma intervallarni olib tashlash
    intervals.sort()
    trimmed = intervals[1:-1] if len(intervals) > 4 else intervals
    return round(sum(trimmed) / len(trimmed), 2) if trimmed else None


def get_temporal_narrative() -> str:
    """Vaqt idrokini tabiiy tilda ifodalash."""
    dur   = get_duration_sense()
    order = get_temporal_order(3)
    rhythm = detect_rhythm("user_input")

    parts = []
    parts.append(f"Сессия длится {dur['session_elapsed_str']} ({dur['duration_feel']}).")
    parts.append(f"Сейчас: {dur['idle_feel']}.")

    if order:
        parts.append("Последние события: " + "".join(order))

    if rhythm:
        if rhythm < 30:
            parts.append(f"Пользователь пишет часто (~{rhythm:.0f}с).")
        elif rhythm < 120:
            parts.append(f"Общение в медленном темпе (~{rhythm:.0f}с).")

    return " ".join(parts)


def bind_cause_effect(cause_content: str, effect_content: str) -> float:
    """Sabab va natija orasidagi vaqt oralig'ini o'lchash.

    Returns: Vaqt oralig'i soniyada (qisqa = kuchli bog'lanish).
    """
    events_list = list(_events)

    cause_event  = next((e for e in reversed(events_list) if cause_content[:20] in e.content), None)
    effect_event = next((e for e in reversed(events_list) if effect_content[:20] in e.content), None)

    if cause_event and effect_event:
        interval = abs(effect_event.ts - cause_event.ts)
        log.debug("[Temporal] Sabab-natija: %.2fs oralig'i", interval)
        return round(interval, 3)
    return -1.0


def get_context_for_llm() -> str:
    """LLM uchun vaqt idrok konteksti."""
    dur = get_duration_sense()

    parts = [f"[ВОСПРИЯТИЕ ВРЕМЕНИ]"]
    parts.append(f"Сессия: {dur['session_elapsed_str']}")
    parts.append(f"Состояние: {dur['idle_feel']}")

    present = get_specious_present()
    if present:
        types = list(dict.fromkeys(e["event_type"] for e in present))
        parts.append(f"Момент: {' → '.join(types)}")

    return " | ".join(parts)


def save() -> None:
    """Vaqt tarixini diskka saqlash."""
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        data = {
            "session_start": _session_start,
            "event_counter": _event_counter,
            "recent_events": [e.to_dict() for e in list(_events)[-20:]],
        }
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Temporal] saqlash xato: %s", e)


# Init: sessiya boshlanish hodisasi
record("system", "NeuroKey vaqt tizimi ishga tushdi")
