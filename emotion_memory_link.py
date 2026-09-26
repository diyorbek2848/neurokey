# -*- coding: utf-8 -*-
"""NeuroKey — His-Xotira Bog'lanishi (Emotion-Memory Link).

Amygdala modeli: Kuchli his-tuyg'u xotirani kuchaytiradi.
LeDoux nazariyasi: Hissiy xotira alohida tizimda saqlanadi.

Printsiplar:
  - Yuqori his intensivligi → xotira muhimligi oshadi
  - "Flashbulb memory": ajablanarli voqealar aniqroq esda qoladi
  - Hissiy holat xotirani eslashni osonlashtiradi (mood-congruent recall)
  - Salbiy his ijobiyga qaraganda kuchliroq ta'sir qiladi (negativity bias)

Bu modul:
  - Har suhbatni hissiy kuchiga qarab taglaydi
  - Kuchli his bilan suhbatlarni alohida "flashbulb" xotirasida saqlaydi
  - Hissiy holat bo'yicha xotira qidiruvi
  - permanent_memory ga hissiy og'irlik bilan saqlaydi

2026-yil suniy ong — amygdala qatlami.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import permanent_memory as pm

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "emotion_memory.json")

# His-tuyg'u valensi va kuchi
EMOTION_WEIGHTS: Dict[str, Tuple[float, float]] = {
    # (valence: -1..+1, arousal: 0..1)
    "joy":          (+0.9, 0.8),
    "xursandchilik":(+0.9, 0.8),
    "sadness":      (-0.7, 0.4),
    "g'am":         (-0.7, 0.4),
    "anger":        (-0.8, 0.9),
    "g'azab":       (-0.8, 0.9),
    "fear":         (-0.9, 0.95),
    "qo'rquv":      (-0.9, 0.95),
    "surprise":     (+0.3, 0.9),
    "hayrat":       (+0.3, 0.9),
    "disgust":      (-0.85, 0.7),
    "nafrat":       (-0.85, 0.7),
    "curiosity":    (+0.6, 0.7),
    "qiziqish":     (+0.6, 0.7),
    "trust":        (+0.7, 0.3),
    "ishonch":      (+0.7, 0.3),
    "pride":        (+0.8, 0.6),
    "g'urur":       (+0.8, 0.6),
    "shame":        (-0.7, 0.5),
    "uyat":         (-0.7, 0.5),
    "love":         (+0.95, 0.7),
    "sevgi":        (+0.95, 0.7),
    "gratitude":    (+0.8, 0.5),
    "minnatdorlik": (+0.8, 0.5),
    "neutral":      (0.0, 0.3),
}

# Flashbulb xotira uchun chegara (arousal > shu = kuchli xotira)
FLASHBULB_THRESHOLD = 0.75

# His aniqlash kalit so'zlar
_EMOTION_KEYWORDS: Dict[str, List[str]] = {
    "joy":      ["rahmat", "zo'r", "ajoyib", "yaxshi", "baxt", "xursand", "happy", "great",
                 "отлично", "замечательно", "прекрасно", "радость", "счастье", "kashfiyot", "yutuq"],
    "sadness":  ["yomon", "g'am", "qayg'u", "sad", "unhappy", "noto'g'ri", "xafa",
                 "грустно", "печаль", "muammo", "qiyin", "проблема", "горе"],
    "surprise": ["voy", "wow", "ajab", "hayratda", "surprised", "unexpected",
                 "удивительно", "неожиданно", "kashfiyot", "yangilik"],
    "anger":    ["g'azab", "yoqmadi", "noto'g'ri", "angry", "xato", "nima bu",
                 "злость", "ошибка", "неправильно", "раздражение"],
    "curiosity":["qiziq", "nima", "qanday", "nima uchun", "interesting", "curious",
                 "интересно", "любопытно", "o'rganish", "o'rgandim", "bilmoq"],
    "gratitude":["rahmat", "tashakkur", "thanks", "minnatdor", "appreciate",
                 "спасибо", "благодарю", "признателен"],
    "fear":     ["qo'rqaman", "xavfli", "dangerous", "scared", "worry", "tashvish",
                 "страх", "боюсь", "опасно", "тревога"],
    "pride":    ["yutdim", "muvaffaqiyat", "proud", "achieved", "bajarildi",
                 "гордость", "достижение", "успех", "справился", "выполнено"],
}


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "current_emotion":    "neutral",
        "current_valence":    0.0,
        "current_arousal":    0.3,
        "flashbulb_memories": [],
        "emotion_history":    [],
        "total_tagged":       0,
    }


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[EML] saqlash: %s", e)


def detect_emotion(text: str) -> Tuple[str, float]:
    """Matndan his-tuyg'u va intensivligini aniqlash.
    Returns: (emotion_name, intensity 0..1)
    """
    t_lower = (text or "").lower()
    best_emotion   = "neutral"
    best_intensity = 0.0

    for emotion, keywords in _EMOTION_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in t_lower)
        if matches > 0:
            intensity = min(1.0, 0.4 + matches * 0.2)
            if intensity > best_intensity:
                best_intensity  = intensity
                best_emotion    = emotion

    # Undov belgilari intensivlikni oshiradi
    exclamations = t_lower.count("!") + t_lower.count("?!")
    if exclamations > 0:
        best_intensity = min(1.0, best_intensity + exclamations * 0.1)

    return best_emotion, best_intensity


def compute_memory_importance(emotion: str, intensity: float,
                               base_importance: float = 0.5) -> float:
    """Hissiy kuchga qarab xotira muhimligini hisoblash.

    LeDoux: Kuchli arousal → stronger memory consolidation.
    """
    weight = EMOTION_WEIGHTS.get(emotion, (0.0, 0.3))
    arousal = weight[1]
    valence = weight[0]

    # Salbiy his ham kuchli xotira yaratadi (negativity bias)
    emotion_boost = arousal * intensity * 0.4

    # Ijobiy his ham muhim
    if valence > 0:
        emotion_boost *= 1.1

    importance = min(1.0, base_importance + emotion_boost)
    return round(importance, 3)


def tag_and_store(user_msg: str, bot_msg: str,
                  explicit_emotion: str = "") -> Dict[str, Any]:
    """Suhbatni hissiy taglash va saqlash."""
    state = _load()

    # His aniqlash
    if explicit_emotion and explicit_emotion != "neutral":
        emotion    = explicit_emotion
        intensity  = 0.7
    else:
        emotion, intensity = detect_emotion(user_msg)
        if emotion == "neutral":
            bot_em, bot_int = detect_emotion(bot_msg)
            if bot_em != "neutral":
                emotion, intensity = bot_em, bot_int

    # Muhimlik hisoblash
    importance = compute_memory_importance(emotion, intensity)

    # Valence va arousal
    valence_arousal = EMOTION_WEIGHTS.get(emotion, (0.0, 0.3))
    valence = valence_arousal[0]
    arousal = valence_arousal[1]

    # permanent_memory ga saqlash
    pm.remember_conversation(
        user_msg=user_msg,
        bot_msg=bot_msg,
        emotion=emotion,
    )

    # Kuchli his = flashbulb xotira
    is_flashbulb = arousal * intensity >= FLASHBULB_THRESHOLD
    if is_flashbulb:
        flashbulbs = state.setdefault("flashbulb_memories", [])
        flashbulbs.append({
            "ts":        datetime.now().isoformat(),
            "emotion":   emotion,
            "intensity": intensity,
            "arousal":   arousal,
            "content":   user_msg[:150],
            "importance": importance,
        })
        # Flashbulb xotirani alohida episode sifatida saqlash
        pm.remember_episode(
            title=f"[{emotion.upper()}] {user_msg[:60]}",
            description=f"User: {user_msg[:200]}\nBot: {bot_msg[:200]}",
            emotion=emotion,
            importance=importance,
            tags="flashbulb",
        )
        if len(flashbulbs) > 100:
            flashbulbs[:] = flashbulbs[-100:]

    # His tarixi
    history = state.setdefault("emotion_history", [])
    history.append({
        "ts":        datetime.now().isoformat(),
        "emotion":   emotion,
        "intensity": round(intensity, 2),
        "valence":   round(valence, 2),
    })
    if len(history) > 500:
        history[:] = history[-500:]

    state["current_emotion"]  = emotion
    state["current_valence"]  = round(valence * intensity, 3)
    state["current_arousal"]  = round(arousal * intensity, 3)
    state["total_tagged"]     = state.get("total_tagged", 0) + 1
    _save(state)

    return {
        "emotion":      emotion,
        "intensity":    intensity,
        "importance":   importance,
        "is_flashbulb": is_flashbulb,
        "valence":      valence,
    }


def recall_by_mood(emotion: str, limit: int = 10) -> List[Dict]:
    """Hissiy holat bo'yicha xotira qidirish (mood-congruent recall)."""
    return pm.recall_by_emotion(emotion, limit=limit)


def get_emotional_timeline() -> List[Dict]:
    """Hissiy holat tarixi — kayfiyat qanday o'zgargan."""
    state = _load()
    return state.get("emotion_history", [])[-20:]


def get_flashbulb_memories() -> List[Dict]:
    """Eng kuchli hissiy xotiralar."""
    state = _load()
    fb = state.get("flashbulb_memories", [])
    return sorted(fb, key=lambda x: x.get("importance", 0), reverse=True)[:10]


def get_current_emotional_state() -> Dict[str, Any]:
    state = _load()
    return {
        "emotion":  state.get("current_emotion", "neutral"),
        "valence":  state.get("current_valence", 0.0),
        "arousal":  state.get("current_arousal", 0.3),
        "flashbulb_count": len(state.get("flashbulb_memories", [])),
    }


def get_context_for_llm() -> str:
    state    = _load()
    emotion  = state.get("current_emotion", "neutral")
    valence  = state.get("current_valence", 0.0)
    fb_count = len(state.get("flashbulb_memories", []))

    if emotion == "neutral" and fb_count == 0:
        return ""

    parts = [f"[HISSIY XOTIRA] His: {emotion}"]
    if valence != 0:
        v_str = f"+{valence:.2f}" if valence > 0 else f"{valence:.2f}"
        parts.append(f"Valens: {v_str}")
    if fb_count > 0:
        parts.append(f"Flashbulb: {fb_count} ta kuchli xotira")
    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "current_emotion":    state.get("current_emotion", "neutral"),
        "flashbulb_count":    len(state.get("flashbulb_memories", [])),
        "total_tagged":       state.get("total_tagged", 0),
        "active":             True,
    }
