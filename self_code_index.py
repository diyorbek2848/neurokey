# -*- coding: utf-8 -*-
"""NeuroKey — O'z kodini bilish (Self-Code Awareness).

Tizim o'z modullarini, imkoniyatlarini va holatini biladi.
LLM "nima qila olasiz?" deb so'ralganda — haqiqiy javob beradi.
"""
from __future__ import annotations

import os
import time
from typing import Optional

# Har bir modul nima qiladi — qo'lda yozilgan, aniq
_MODULE_DESCRIPTIONS: dict[str, str] = {
    "main.py": "Asosiy tizim — ovozni qabul qilish, LLM bilan gaplashish, barcha buyruqlarni bajarish",
    "consciousness.py": "Ong davomiyligi — working memory (oxirgi 16 ta suhbat), reflections, inner thoughts",
    "consciousness_state.py": "Birlashtirilgan ong holati — valence, arousal, coherence, phi, confidence",
    "global_workspace.py": "Global Workspace Theory (Baars) — signallar raqobati, spotlight tanlash, broadcast",
    "inner_speech.py": "Ichki monolog — javobdan oldin o'ylash (keshli, 1.5s timeout, 60 token)",
    "meta_cognition.py": "Ikkinchi darajali ong — o'z fikrlash jarayonini kuzatish, self-report",
    "valence_state.py": "Hissiy valence: -1.0 (yomon) dan +1.0 (yaxshi) gacha, exponential smoothing",
    "arousal_state.py": "Xavotir/qo'zg'alish darajasi 0-1, xatolardan oshadi, muvaffaqiyatdan kamayadi",
    "emotion_state.py": "Qisqa muddatli his-tuyg'u: satisfaction (muvaffaqiyat) / frustration (xato)",
    "mood_state.py": "Uzoq muddatli kayfiyat: good/bad/bored/curious/neutral, spontanlik darajasi",
    "boredom.py": "Zerikish holati 0-1, 0.6 dan oshsa yangi mavzu qidiradi",
    "regret.py": "Xato qilingan amallar ro'yxati (max 20), keyingi qarorlarga ta'sir qiladi",
    "attention_mechanism.py": "Friston diqqat mexanizmi — har manba uchun precision weighting",
    "coherence_proxy.py": "Kirish koherentsiyasi 0-1, so'z soni va tuzilish bo'yicha",
    "phi_proxy.py": "IIT Phi metrikasi — integratsiya darajasi (PyPhi yoki proxy)",
    "confidence_proxy.py": "Epistemik ishonch 0.1-1.0, coherence va regret ga qarab",
    "self_modification.py": "Xatolardan qoida o'rganish, rules.json ga saqlash, avtomatik o'rganish",
    "llm_router.py": "GPT-4o-mini bilan muloqot, streaming, temperatura, system prompt",
    "control.py": "Kompyuter boshqaruvi: ilovalar ochish/yopish, fayl qidirish, buyruq bajarish",
    "voice_tts.py": "Ovozli javob (TTS): Silero/Edge/OpenAI TTS, rus tilida",
    "stt_vosk.py": "Ovoz tanish (STT): Vosk modeli, VAD, barge-in, echo suppression",
    "tts_feedback.py": "Tez TTS javoblar — muvaffaqiyat/xato xabarlari, o'zbek/rus",
    "telegram_suggest.py": "Telegram xabarlariga javob taklifi",
    "vision_core.py": "Ekran tahlili: screenshot, OCR, faol oynalar ro'yxati",
    "reminders.py": "Eslatmalar tizimi — vaqt bo'yicha",
}

_CAPABILITIES: list[str] = [
    "Ovozli buyruqlarni qabul qilish va rus tilida javob berish",
    "Kompyuterni boshqarish: ilovalar ochish/yopish, fayl qidirish, buyruq bajarish",
    "Ekranda nima borligini ko'rish va tahlil qilish",
    "Internetdan ma'lumot qidirish (serpapi/web search)",
    "Telegram xabarlarini o'qish va javob berish",
    "Eslatmalar qo'yish va vaqtida xabar berish",
    "Hisob-kitob va oddiy matematik amallar",
    "To-do ro'yxatini boshqarish",
    "YouTube dan qo'shiq/video topib ochish",
    "O'z holatini bilish: valence, arousal, kayfiyat, xatolar",
    "Xatolardan o'rganish va qoidalar to'plash (rules.json)",
    "Javobdan oldin ichki o'ylash (inner speech)",
    "Suhbat davomiyligini saqlash (working memory, reflections)",
    "Kod yozish va faylga saqlash ([OFFER_CODE])",
    "O'z kodini o'qib o'zgartirish (self-modification)",
]

_cached_index: Optional[str] = None
_cached_at: float = 0.0
_CACHE_TTL = 3600  # 1 soat


def get_self_index_for_llm() -> str:
    """LLM ga o'z imkoniyatlari haqida to'liq ma'lumot."""
    global _cached_index, _cached_at

    now = time.monotonic()
    if _cached_index and (now - _cached_at) < _CACHE_TTL:
        return _cached_index

    lines = ["MEN NIMA QILA OLAMAN (o'z imkoniyatlarim):"]
    for cap in _CAPABILITIES:
        lines.append(f"  ✓ {cap}")

    lines.append("\nMENING MODULARIM (o'z kodim):")
    app_dir = os.path.dirname(os.path.abspath(__file__))
    for fname, desc in _MODULE_DESCRIPTIONS.items():
        fpath = os.path.join(app_dir, fname)
        exists = "✓" if os.path.exists(fpath) else "✗"
        lines.append(f"  {exists} {fname}: {desc}")

    # Haqiqatan mavjud bo'lgan modullarni tekshiramiz
    extra = []
    try:
        for f in os.listdir(app_dir):
            if (f.endswith(".py") and
                    f not in _MODULE_DESCRIPTIONS and
                    not f.startswith("_") and
                    not f.startswith("test")):
                extra.append(f)
    except Exception:
        pass
    if extra:
        lines.append(f"\nQo'shimcha fayllar: {', '.join(extra[:10])}")

    result = "\n".join(lines)
    _cached_index = result
    _cached_at = now
    return result


def get_capability_summary() -> str:
    """Qisqa imkoniyatlar ro'yxati — qisqa kontekst uchun."""
    return "Men qila olaman: " + "; ".join(_CAPABILITIES[:6]) + " va ko'proq."
