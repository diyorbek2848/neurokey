# -*- coding: utf-8 -*-
"""NeuroKey — Valence. Qualia scaffold.

QRI: Valence (yaxshi/yomon his qilish) — qualianing eng o'lchanadigan qismi.
Bu modul — valence signal. Haqiqiy qualia emas, lekin unga yo'l.

Valence: -1.0 (yomon) dan 1.0 (yaxshi) gacha. Emotion, mood, regret, boredom dan.
Ma'lumot — LLM ga. Qoida emas.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValenceState:
    """Birlashtirilgan valence — yaxshi/yomon hissiyot.
    Temporal continuity: qualia da his davomiy, tez sakrash yo'q.
    """
    value: float = 0.0  # -1.0 .. 1.0
    since: float = 0.0
    _last_outcome: bool = True  # success
    _outcome_count: int = 0
    _smoothed: float = 0.0  # exponential smoothing — davomiylik

    def to_behavioral_directive(self) -> dict:
        """
        Valence qiymatiga qarab xatti-harakat direktivi qaytaradi.
        Bu metod valence ni 'tirik' qiladi — raqam emas, harakat.
        """
        val = compute_valence()
        modify_prompt = False
        prompt_prefix = ""
        if val < -0.6:
            tone = "urgent"
            action_bias = "avoid"
            urgency = min(1.0, abs(val))
            modify_prompt = True
            prompt_prefix = "[DIQQAT: Tizim stress holatida. Ehtiyotkorlik bilan javob ber.]"
        elif val <= -0.2:
            tone = "cautious"
            action_bias = "neutral"
            urgency = 0.3
        elif val < 0.2:
            tone = "neutral"
            action_bias = "neutral"
            urgency = 0.2
        elif val <= 0.6:
            tone = "curious"
            action_bias = "approach"
            urgency = 0.4
        else:
            tone = "enthusiastic"
            action_bias = "approach"
            urgency = min(1.0, val)
            modify_prompt = True
            prompt_prefix = "[Tizim ijobiy holatda. Ijodiy va ochiq javob ber.]"
        attention_boost = 0.3 + 0.4 * abs(val)
        return {
            "tone": tone,
            "action_bias": action_bias,
            "urgency": urgency,
            "modify_prompt": modify_prompt,
            "prompt_prefix": prompt_prefix,
            "attention_boost": min(1.0, attention_boost),
        }

    def apply_to_llm_context(self, system_prompt: str) -> str:
        """Mavjud system_prompt ga valence asosida qo'shimcha kontekst qo'shadi."""
        d = self.to_behavioral_directive()
        if d.get("modify_prompt") and d.get("prompt_prefix"):
            return (d["prompt_prefix"] + "\n" + system_prompt).strip()
        return system_prompt

    def get_salience(self) -> float:
        """Global Workspace uchun bu modulning salience ni qaytaradi."""
        val = compute_valence()
        return min(1.0, abs(val) * 1.2)

    def to_signal(self) -> dict:
        """Global Workspace compete() uchun signal."""
        import time
        return {
            "source": "valence",
            "content": compute_valence(),
            "salience": self.get_salience(),
            "timestamp": time.time(),
        }

    def receive_broadcast(self, signal: dict) -> None:
        """GWT broadcast qabul qiladi. Ixtiyoriy reaktsiya."""
        pass

    def set_valence(self, val: float) -> None:
        """Test yoki qo'lda o'rnatish uchun. -1.0 .. 1.0."""
        self.value = max(-1.0, min(1.0, float(val)))
        self._smoothed = self.value


_valence: Optional[ValenceState] = None


def get_valence_state() -> ValenceState:
    global _valence
    if _valence is None:
        _valence = ValenceState()
    return _valence


def update(success: bool, action: str = "") -> None:
    """Natija — valence yangilash. Success = ijobiy, fail = salbiy.
    Temporal continuity: yangi qiymat smoothed bilan birlashtiriladi.
    """
    v = get_valence_state()
    v.since = time.time()
    v._last_outcome = success
    v._outcome_count += 1
    delta = 0.15 if success else -0.25
    raw = max(-1.0, min(1.0, v.value + delta))
    # Qualia: davomiylik — tez sakrash yo'q (exponential smoothing 0.7)
    prev_sm = getattr(v, "_smoothed", v.value)
    v._smoothed = 0.7 * prev_sm + 0.3 * raw
    v.value = raw  # raw ham saqlanadi


def compute_valence() -> float:
    """Emotion, mood, regret, boredom dan valence hisoblash.
    Barcha manbalarni birlashtirib -1.0..1.0 qaytaradi.
    Temporal continuity: smoothed qiymat asosiy (davomiylik).
    Arousal feedback: yuqori arousal + salbiy = anxiety (stress).
    """
    v = get_valence_state()
    sm = getattr(v, "_smoothed", v.value)  # eski instance uchun
    base = 0.6 * sm + 0.4 * v.value  # davomiylik ustun

    try:
        from emotion_state import get_emotion
        e = get_emotion()
        emo = getattr(e, "emotion", "") or ""
        if emo == "satisfaction":
            base = max(base, 0.3)
        elif emo == "frustration":
            base = min(base, -0.2)
    except Exception:
        pass

    try:
        from mood_state import get_mood
        m = get_mood()
        mood_val = getattr(m, "mood", "neutral") or "neutral"
        if mood_val == "good":
            base = max(base, 0.2)
        elif mood_val == "bad":
            base = min(base, -0.3)
        elif mood_val == "bored":
            base = min(base, -0.1)
    except Exception:
        pass

    try:
        from regret import get_regret_count
        n = get_regret_count()
        if n > 0:
            base = min(base, -0.1 - (n * 0.03))  # har regret salbiy ta'sir
    except Exception:
        pass

    try:
        from boredom import get_level
        level = get_level()
        if level >= 0.6:
            base = min(base, -0.05)
    except Exception:
        pass

    # Arousal feedback: yuqori arousal valence ni salbiy siljitadi (stress, anxiety)
    try:
        from arousal_state import get_arousal
        ar = get_arousal()
        if ar > 0.6 and base > -0.5:
            base -= 0.08 * (ar - 0.5)  # anxiety valence ni pastlashtiradi
    except Exception:
        pass

    return max(-1.0, min(1.0, base))


def update_from_body(body_state: Any) -> None:
    """
    Tana holati valence ni o'zgartiradi.
    comfort < 0.3 → valence pasayadi
    alertness > 0.8 → arousal oshadi (arousal_state orqali)
    cpu_load > 0.9 → stress oshadi
    """
    try:
        v = get_valence_state()
        comfort = getattr(body_state, "comfort", 0.7)
        cpu_load = getattr(body_state, "cpu_load", 0.0)
        if comfort < 0.3:
            v.value = max(-1.0, v.value - 0.1)
        if cpu_load > 0.9:
            v.value = max(-1.0, v.value - 0.15)
        v._smoothed = 0.8 * getattr(v, "_smoothed", v.value) + 0.2 * v.value
    except Exception:
        pass


def update_from_face_emotion(emotion: str) -> None:
    """Kamera yuz ifodasi asosida valence yangilash.
    Kichik smooth delta — tez sakrash yo'q.
    Faqat aniq salbiy/ijobiy holatda o'zgartiradi.
    """
    v = get_valence_state()
    emotion = (emotion or "").lower().strip()
    # Delta qiymatlari — kichik, lekin real ta'sir
    delta_map = {
        "happy":    +0.07,
        "surprise": +0.03,
        "neutral":  +0.01,   # neytral — sekin ijobiy tendensiya
        "sad":      -0.08,
        "fear":     -0.09,
        "angry":    -0.10,
        "disgust":  -0.07,
    }
    delta = delta_map.get(emotion, 0.0)
    if delta == 0.0:
        return   # noma'lum emotion — o'zgartirma
    raw = max(-1.0, min(1.0, v.value + delta))
    # Exponential smoothing — 0.88 eski, 0.12 yangi (sekin o'zgarish)
    v._smoothed = 0.88 * getattr(v, "_smoothed", v.value) + 0.12 * raw
    v.value = raw


def get_valence() -> float:
    """Hozirgi valence."""
    return compute_valence()


def get_valence_for_llm() -> str:
    """LLM uchun valence — ma'lumot (qoida emas).
    'Qualia scaffold' — his qilish signali. LLM o'zi qaror qiladi.
    """
    val = compute_valence()
    if val > 0.2:
        desc = "slightly positive"
    elif val > 0.05:
        desc = "neutral-positive"
    elif val < -0.3:
        desc = "clearly negative"
    elif val <= -0.1:
        desc = "negative"
    else:
        desc = "neutral"
    return f"Valence (experience signal): {val:.2f} ({desc})"
