# -*- coding: utf-8 -*-
"""NeuroKey — Mukofot/Jazo Signali (Pain-Pleasure Signal).

Damasio somatik marker gipotezasi:
  Qarorlar mantiq bilan emas, his-tuyg'u bilan boshqariladi.
  "Ijobiy" va "salbiy" belgilar qarorni yo'naltiradi.

Freyd tamoyili (soddalashtirilgan):
  Lazzat tamoyili: organizmlar lazzatni qidiradi, og'riqdan qochadi.
  Haqiqat tamoyili: kechiktirilgan qoniqish ham mumkin.

Bu modul:
  - Har harakat/javob uchun "reward signal" hisoblaydi
  - Foydalanuvchi musbat/manfiy fikr bildirsa → signal yangilanadi
  - "Bu yaxshi edi / yomon edi" ni eslab, kelajakda yaxshilanadi
  - Motivatsion yo'nalish: yuqori reward → ko'proq shunday qil
  - dopamine-serotonin simulyatsiyasi: baxtiyor / xursand holat

2026-yil suniy ong — motivatsion signal qatlami.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import permanent_memory as pm

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "pain_pleasure.json")

# Musbat signal so'zlari
_POSITIVE_SIGNALS = [
    "rahmat", "zo'r", "ajoyib", "yaxshi", "to'g'ri", "perfect",
    "thanks", "great", "excellent", "correct", "exactly", "yes!",
    "спасибо", "отлично", "правильно", "именно",
    "barakalla", "bravo", "muvaffaqiyat", "yutdim",
]

# Manfiy signal so'zlari
_NEGATIVE_SIGNALS = [
    "xato", "noto'g'ri", "yomon", "tushunmadim", "yo'q", "emas",
    "wrong", "incorrect", "bad", "no", "not right", "confused",
    "неправильно", "нет", "плохо", "не так",
    "qayta", "yana", "boshqatdan", "try again",
]

# Neytral
_NEUTRAL_SIGNALS = [
    "ok", "yaxshi", "tushundim", "understood", "понял", "clear",
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "reward_level":    0.5,    # 0.0 (og'riq) — 1.0 (lazzat)
        "dopamine":        0.5,    # Qisqa muddatli reward
        "serotonin":       0.5,    # Uzoq muddatli baxt
        "total_positive":  0,
        "total_negative":  0,
        "reward_history":  [],
        "peak_moment":     None,   # Eng yuqori reward lahzasi
        "low_moment":      None,   # Eng past reward lahzasi
        "updated_at":      None,
    }


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[PainPleasure] saqlash: %s", e)


def detect_feedback(text: str) -> float:
    """Matndan reward signalini aniqlash.
    Returns: -1.0 (maksimal og'riq) ... +1.0 (maksimal lazzat)
    """
    t_lower = (text or "").lower()

    pos_count = sum(1 for s in _POSITIVE_SIGNALS if s in t_lower)
    neg_count = sum(1 for s in _NEGATIVE_SIGNALS if s in t_lower)

    if pos_count == 0 and neg_count == 0:
        return 0.0  # Neytral

    total = pos_count + neg_count
    signal = (pos_count - neg_count) / max(total, 1)

    # Undov belgilari kuchaytiradi
    exclamations = t_lower.count("!")
    signal = max(-1.0, min(1.0, signal + exclamations * 0.1 * (1 if signal > 0 else -1)))

    return round(signal, 3)


def update(user_text: str, bot_reply: str = "",
           explicit_reward: Optional[float] = None) -> Dict[str, Any]:
    """Reward signalni yangilash."""
    state = _load()

    # Signal aniqlash
    if explicit_reward is not None:
        raw_signal = max(-1.0, min(1.0, float(explicit_reward)))
    else:
        raw_signal = detect_feedback(user_text)
        if raw_signal == 0.0 and bot_reply:
            raw_signal = detect_feedback(bot_reply) * 0.5  # Bot reply kam ta'sir

    # EMA yangilash (alpha = 0.3)
    alpha = 0.3
    old_reward   = state.get("reward_level", 0.5)
    norm_signal  = (raw_signal + 1.0) / 2.0      # -1..1 → 0..1
    new_reward   = old_reward * (1 - alpha) + norm_signal * alpha
    new_reward   = round(max(0.0, min(1.0, new_reward)), 3)

    # Dopamine: tez o'zgarish (qisqa muddatli)
    dopamine = round(old_reward * 0.5 + new_reward * 0.5, 3)

    # Serotonin: sekin o'zgarish (uzoq muddatli)
    old_serotonin   = state.get("serotonin", 0.5)
    new_serotonin   = round(old_serotonin * 0.9 + new_reward * 0.1, 3)

    # Statistika
    if raw_signal > 0.2:
        state["total_positive"] = state.get("total_positive", 0) + 1
    elif raw_signal < -0.2:
        state["total_negative"] = state.get("total_negative", 0) + 1

    # Tarix
    entry = {
        "ts":        datetime.now().isoformat(),
        "signal":    raw_signal,
        "reward":    new_reward,
        "trigger":   user_text[:60],
    }
    history = state.setdefault("reward_history", [])
    history.append(entry)
    if len(history) > 500:
        history[:] = history[-500:]

    # Peak va low momentlar
    if new_reward > (state.get("peak_moment") or {}).get("reward", 0):
        state["peak_moment"] = {
            "ts":      datetime.now().isoformat(),
            "reward":  new_reward,
            "trigger": user_text[:100],
        }
    if new_reward < (state.get("low_moment") or {}).get("reward", 1.0):
        state["low_moment"] = {
            "ts":      datetime.now().isoformat(),
            "reward":  new_reward,
            "trigger": user_text[:100],
        }

    state["reward_level"] = new_reward
    state["dopamine"]     = dopamine
    state["serotonin"]    = new_serotonin
    state["updated_at"]   = datetime.now().isoformat()
    _save(state)

    # Kuchli reward → permanent memory
    if abs(raw_signal) > 0.6:
        emotion = "joy" if raw_signal > 0 else "sadness"
        pm.remember_emotion(
            emotion=emotion,
            intensity=abs(raw_signal),
            trigger=user_text[:80],
            valence=raw_signal,
        )

    return {
        "signal":      raw_signal,
        "reward":      new_reward,
        "dopamine":    dopamine,
        "serotonin":   new_serotonin,
        "is_positive": raw_signal > 0.2,
        "is_negative": raw_signal < -0.2,
    }


def get_current_state() -> Dict[str, Any]:
    state = _load()
    return {
        "reward_level": state.get("reward_level", 0.5),
        "dopamine":     state.get("dopamine", 0.5),
        "serotonin":    state.get("serotonin", 0.5),
        "mood":         "happy" if state.get("serotonin", 0.5) > 0.6 else
                        "sad"   if state.get("serotonin", 0.5) < 0.4 else "neutral",
    }


def get_motivational_direction() -> str:
    """Hozirgi motivatsion yo'nalish."""
    s = _load()
    reward = s.get("reward_level", 0.5)
    if reward > 0.75:
        return "approach"    # Ko'proq shunday qil
    elif reward < 0.35:
        return "avoid"       # Bu yo'ldan qayt
    return "explore"         # Yangi yo'l qidir


def get_context_for_llm() -> str:
    state    = _load()
    reward   = state.get("reward_level", 0.5)
    serotonin = state.get("serotonin", 0.5)
    dopamine  = state.get("dopamine", 0.5)

    if 0.4 <= reward <= 0.65:
        return ""  # Neytral — kontekst kerak emas

    mood_str = (
        "baxtli" if serotonin > 0.7 else
        "yaxshi"  if serotonin > 0.55 else
        "tushkun"  if serotonin < 0.35 else
        "neytral"
    )

    parts = [f"[REWARD] Kayfiyat: {mood_str}"]
    parts.append(f"Reward: {reward:.0%}")
    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "reward_level":   state.get("reward_level", 0.5),
        "serotonin":      state.get("serotonin", 0.5),
        "total_positive": state.get("total_positive", 0),
        "total_negative": state.get("total_negative", 0),
        "active":         True,
    }
