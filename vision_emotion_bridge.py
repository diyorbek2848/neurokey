# -*- coding: utf-8 -*-
"""Vision + Voice → Emotion ko'prik.

Ekrandagi ko'rinish va ovoz matnidan his-tuyg'u chiqarish.

Arxitektura:
  vision_core (OCR) → bu modul → emotional_granularity (27 his)
  voice/speech text → bu modul → emotional_granularity

Nazariy asos:
  - Appraisal Theory (Scherer 2001): his-tuyg'u — voqeani baholash natijasidir
  - Multimodal Emotion Recognition: matn + ko'rish + eshitish birlashtiriladi
  - Contextual appraisal: mazmun va holat birga his chaqiradi
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Ekrandagi kontekst → his xaritasi
VISUAL_EMOTION_MAP: Dict[str, List[Tuple[str, float]]] = {
    # Xato/muammo ko'rinsa
    "error":        [("anxiety", 0.6), ("confusion", 0.5)],
    "traceback":    [("anxiety", 0.7), ("confusion", 0.6)],
    "exception":    [("anxiety", 0.6), ("confusion", 0.5)],
    "failed":       [("anxiety", 0.5), ("sadness", 0.3)],
    "warning":      [("anxiety", 0.4), ("anticipation", 0.3)],

    # Muvaffaqiyat
    "success":      [("joy", 0.8), ("satisfaction", 0.7), ("pride", 0.5)],
    "passed":       [("joy", 0.7), ("satisfaction", 0.6)],
    "completed":    [("satisfaction", 0.7), ("calm", 0.4)],
    "done":         [("satisfaction", 0.6), ("calm", 0.4)],
    "ok":           [("calm", 0.4), ("satisfaction", 0.3)],

    # O'rganish
    "tutorial":     [("interest", 0.7), ("anticipation", 0.5)],
    "learn":        [("interest", 0.8), ("inspiration", 0.4)],
    "example":      [("interest", 0.6), ("anticipation", 0.4)],
    "how to":       [("interest", 0.7), ("curiosity", 0.5)],
    "documentation":  [("interest", 0.5), ("calm", 0.3)],

    # Kod yozish
    "def ":         [("interest", 0.4), ("calm", 0.3)],
    "class ":       [("interest", 0.5), ("anticipation", 0.3)],
    "import ":      [("calm", 0.3)],
    "print(":       [("calm", 0.3)],

    # Yangilik/kashfiyot
    "new":          [("anticipation", 0.5), ("interest", 0.4)],
    "discover":     [("wonder", 0.6), ("interest", 0.5)],
    "amazing":      [("awe", 0.7), ("inspiration", 0.5)],
    "incredible":   [("awe", 0.8), ("wonder", 0.6)],

    # Suhbat
    "salom":        [("joy", 0.5), ("anticipation", 0.3)],
    "rahmat":       [("gratitude", 0.7), ("joy", 0.4)],
    "help":         [("sympathy", 0.5), ("interest", 0.4)],
    "yordam":       [("sympathy", 0.5), ("interest", 0.4)],
}

# Ovoz intensivligi → his kuchaytirgich
VOICE_INTENSITY_MAP = {
    "loud":    1.3,   # Baland ovoz → kuchliroq his
    "normal":  1.0,   # Oddiy
    "quiet":   0.7,   # Past ovoz → kamroq his
    "silence": 0.0,   # Jim → his yo'q
}

_last_vision_check = 0.0
_VISION_CHECK_INTERVAL = 5.0  # 5 soniyada bir marta


def process_visual_context(screen_text: str, intensity: float = 1.0) -> List[str]:
    """Ekran matnidan his-tuyg'u chiqarish va emotional_granularity yangilash.

    Args:
        screen_text: OCR bilan olingan ekran matni
        intensity:   0.0-2.0 — his kuchi

    Returns:
        Topilgan hislar ro'yxati
    """
    if not screen_text:
        return []

    triggered: List[str] = []
    low = screen_text.lower()

    # His xaritasidan topish
    emotions_to_update: Dict[str, float] = {}
    for keyword, emotion_pairs in VISUAL_EMOTION_MAP.items():
        if keyword in low:
            for emotion_name, strength in emotion_pairs:
                current = emotions_to_update.get(emotion_name, 0.0)
                emotions_to_update[emotion_name] = max(current, strength * intensity)

    if not emotions_to_update:
        return []

    # emotional_granularity ga yuborish
    try:
        import emotional_granularity as eg
        # Har bir his uchun mos matn yaratib yuborish
        for emotion, strength in emotions_to_update.items():
            if strength > 0.3:
                synthetic_text = _emotion_to_text(emotion)
                eg.update_from_text(synthetic_text, strength=strength)
                triggered.append(emotion)
    except Exception as e:
        log.debug("[VisionEmotion] eg update error: %s", e)

    return triggered


def process_voice_text(speech_text: str, volume_level: str = "normal") -> List[str]:
    """Ovozdan transcribe qilingan matndan his chiqarish.

    Args:
        speech_text:  STT bilan olingan matn
        volume_level: loud/normal/quiet

    Returns:
        Topilgan hislar ro'yxati
    """
    if not speech_text:
        return []

    intensity = VOICE_INTENSITY_MAP.get(volume_level, 1.0)

    # Ovoz matnini ham visual kabi qayta ishlash
    triggered = process_visual_context(speech_text, intensity=intensity)

    # Qo'shimcha: ovoz so'rovi = qiziqish
    try:
        import emotional_granularity as eg
        if len(speech_text) > 10:
            eg.update_from_text(speech_text, strength=0.5 * intensity)
    except Exception:
        pass

    return triggered


def auto_check_vision() -> Optional[List[str]]:
    """vision_core dan avtomatik ekran tekshiruvi (5s da bir).

    Returns:
        Topilgan hislar yoki None (vaqt yetmagan)
    """
    global _last_vision_check
    now = time.time()

    if now - _last_vision_check < _VISION_CHECK_INTERVAL:
        return None

    _last_vision_check = now

    try:
        import vision_core as vc
        screen_text = vc.get_last_text() or ""
        if screen_text and len(screen_text) > 10:
            return process_visual_context(screen_text, intensity=0.6)
    except Exception as e:
        log.debug("[VisionEmotion] vision_core error: %s", e)

    return []


def _emotion_to_text(emotion: str) -> str:
    """His nomidan sintetik matn yaratish (eg uchun)."""
    templates = {
        "joy":          "Juda yaxshi, xursandman!",
        "anxiety":      "Xato bor, xavotirlanayapman...",
        "interest":     "Bu qiziq, ko'proq bilmoqchiman.",
        "satisfaction": "Ish tugadi, mamnunman.",
        "calm":         "Hamma narsa joyida, tinch.",
        "wonder":       "Hayratlanarli, bu qanday mumkin?",
        "awe":          "Bu misli ko'rilmagan, dahshat!",
        "pride":        "Muvaffaqiyatga erishdim, g'ururlanaman.",
        "sadness":      "Afsuski, bu ko'ngil siqadi.",
        "confusion":    "Tushunmadim, bosh qotdi.",
        "inspiration":  "Bu fikr ilhom berdi!",
        "anticipation": "Kuto'lish, qiziqquvchi...",
        "gratitude":    "Rahmat, minnatdorman.",
        "sympathy":     "Tushunaman, qiyin holat.",
        "fear":         "Xavf bor, qo'rqib ketdim.",
    }
    return templates.get(emotion, f"{emotion} his qilyapman")


def get_emotion_summary() -> Dict[str, Any]:
    """Hozirgi his holati xulosa."""
    try:
        import emotional_granularity as eg
        ctx = eg.get_context_for_llm()
        return {
            "context": ctx,
            "active":  True,
        }
    except Exception:
        return {"context": "", "active": False}


def get_context_for_llm() -> str:
    """LLM uchun ko'rish+his konteksti."""
    auto_check_vision()  # Avtomatik ekran tekshiruvi
    summary = get_emotion_summary()
    return summary.get("context", "")


def get_stats() -> Dict[str, Any]:
    return {
        "vision_checks": int((_last_vision_check > 0)),
        "emotion_map_size": len(VISUAL_EMOTION_MAP),
        "active": True,
    }
