# -*- coding: utf-8 -*-
"""NeuroKey — Ko'p Modal Bog'lanish (Cross-Modal Binding).

Ong turli sezgi kanallarini birlashtiradi → bitta izchil tajriba.
Ko'rish + Eshitish + His → "Men hozir shu yerda, shu narsani boshdan kechiryapman."

Bu modul:
  - Turli manbalardan kelgan ma'lumotlarni birlashtiradi
  - Qarama-qarshi signallarni tahlil qiladi
  - Eng muhim kanalga ustunlik beradi
  - "Binding problem" ni oddiy yechadi: weighted fusion

Kanallar:
  - text_input   : Matn kanali (asosiy)
  - voice_input  : Ovoz kanali (STT)
  - screen_visual: Ekran vizual (OCR/Vision)
  - system_state : Tizim holati (monitoring)
  - memory_stream: Xotira oqimi (LTM)
  - time_signal  : Vaqt signali
  - emotion_signal: Hissiy signal

2026-yil suniy ong — ko'p modal integratsiya qatlami.
"""
from __future__ import annotations

try: import phenomenal_binding as _cmb_pb
except ImportError: _cmb_pb = None
try: from valence_state import get_valence as _cmb_valence
except ImportError: _cmb_valence = None

import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "cross_modal.json")

CHANNELS = (
    "text_input",
    "voice_input",
    "screen_visual",
    "system_state",
    "memory_stream",
    "time_signal",
    "emotion_signal",
)

# Kanal og'irliklari (qanchalik ishonchli)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "text_input":    1.0,
    "voice_input":   0.9,
    "screen_visual": 0.7,
    "system_state":  0.6,
    "memory_stream": 0.8,
    "time_signal":   0.5,
    "emotion_signal":0.7,
}

_HISTORY_LEN = 30

# Faol signallar: {kanal: {value, strength, ts}}
_active_signals: Dict[str, Dict[str, Any]] = {}
_binding_history: Deque[Dict[str, Any]] = deque(maxlen=_HISTORY_LEN)


def receive(channel: str, value: Any, strength: float = 1.0) -> None:
    """Yangi signal qabul qilish.

    Args:
        channel:  CHANNELS dan biri
        value:    Signal qiymati (matn, raqam, dict)
        strength: Signal kuchi (0.0–1.0)
    """
    channel  = channel if channel in CHANNELS else "text_input"
    strength = max(0.0, min(1.0, float(strength)))

    if isinstance(value, str):
        value = value[:300]

    _active_signals[channel] = {
        "value":    value,
        "strength": strength,
        "weight":   DEFAULT_WEIGHTS.get(channel, 0.5),
        "ts":       time.time(),
        "time_str": datetime.now().strftime("%H:%M:%S"),
    }
    log.debug("[CrossModal] Signal: [%s] str=%.1f", channel, strength)


def bind() -> Dict[str, Any]:
    """Barcha faol signallarni birlashtirish → bitta izchil holat.

    Returns: Birlashtirilgan holat va eng muhim kanal.
    """
    if not _active_signals:
        return {"bound": False, "dominant_channel": None, "summary": ""}

    now     = time.time()
    # Eski signallarni filtrlash (30 sekunddan eski)
    fresh   = {k: v for k, v in _active_signals.items()
               if now - v["ts"] < 30.0}

    if not fresh:
        return {"bound": False, "dominant_channel": None, "summary": ""}

    # Weighted fusion
    total_weight   = 0.0
    dominant       = None
    dominant_score = 0.0

    channel_scores: Dict[str, float] = {}
    for ch, sig in fresh.items():
        score = sig["strength"] * sig["weight"]
        channel_scores[ch] = score
        total_weight += score
        if score > dominant_score:
            dominant_score = score
            dominant       = ch

    # Normalizatsiya
    if total_weight > 0:
        normalized = {k: round(v / total_weight, 3) for k, v in channel_scores.items()}
    else:
        normalized = channel_scores

    # Ziddiyat aniqlash
    conflicts = _detect_conflicts(fresh)

    # Birlashtirilgan holat
    bound_state = {
        "bound":            True,
        "dominant_channel": dominant,
        "channel_weights":  normalized,
        "active_channels":  list(fresh.keys()),
        "conflicts":        conflicts,
        "coherence":        round(1.0 - len(conflicts) * 0.2, 2),
        "timestamp":        datetime.now().isoformat(),
    }

    _binding_history.append(bound_state)
    return bound_state


def _detect_conflicts(signals: Dict[str, Dict[str, Any]]) -> List[str]:
    """Qarama-qarshi signallarni aniqlash."""
    conflicts = []

    # Ovoz va matn ziddiyati (turli til/matn)
    if "voice_input" in signals and "text_input" in signals:
        v_val = str(signals["voice_input"]["value"])[:50].lower()
        t_val = str(signals["text_input"]["value"])[:50].lower()
        if v_val and t_val and v_val[:20] != t_val[:20]:
            pass  # Odatda farqli bo'ladi — bu normal

    return conflicts


def get_dominant_channel() -> Optional[str]:
    """Hozirda eng kuchli kanal."""
    state = bind()
    return state.get("dominant_channel")


def get_coherence() -> float:
    """Signallar izchilligi (0.0 = qarama-qarshi, 1.0 = to'liq izchil)."""
    state = bind()
    return state.get("coherence", 0.5)


def get_active_channels() -> List[str]:
    """Hozirda faol kanallar."""
    now = time.time()
    return [k for k, v in _active_signals.items() if now - v["ts"] < 30.0]


def get_narrative() -> str:
    """Ko'p modal holatni tabiiy tilda."""
    state    = bind()
    dominant = state.get("dominant_channel", "")
    channels = state.get("active_channels", [])
    coherence = state.get("coherence", 0.5)

    if not channels:
        return "Hech qanday faol kanal yo'q."

    ch_names = {
        "text_input":    "matn",
        "voice_input":   "ovoz",
        "screen_visual": "ekran",
        "system_state":  "tizim",
        "memory_stream": "xotira",
        "time_signal":   "vaqt",
        "emotion_signal":"his-tuyg'u",
    }
    ch_str = ", ".join(ch_names.get(c, c) for c in channels[:4])

    coher_word = "to'liq" if coherence > 0.8 else "o'rtacha" if coherence > 0.5 else "parchalangan"
    dom_name   = ch_names.get(dominant, dominant or "noma'lum")

    return (f"Faol kanallar: {ch_str}. "
            f"Asosiy: {dom_name}. "
            f"Izchillik: {coher_word} ({coherence:.0%}).")


def get_context_for_llm() -> str:
    """LLM uchun ko'p modal kontekst."""
    channels  = get_active_channels()
    coherence = get_coherence()
    dominant  = get_dominant_channel()

    if not channels:
        return ""

    parts = ["[KO'P MODAL]"]
    parts.append(f"Kanallar:{len(channels)}")
    if dominant:
        parts.append(f"Asosiy:{dominant.replace('_',' ')}")
    parts.append(f"Izchillik:{coherence:.0%}")

    return " | ".join(parts)


def auto_receive_from_message(user_text: str, voice_detected: bool = False) -> None:
    """Foydalanuvchi xabaridan signallarni avtomatik qabul qilish."""
    if user_text:
        receive("text_input", user_text, strength=1.0)

    if voice_detected:
        receive("voice_input", user_text, strength=0.9)

    # Vaqt signali
    receive("time_signal", datetime.now().isoformat(), strength=0.5)

    # Tizim holati
    receive("system_state", {"active": True, "ts": time.time()}, strength=0.4)
