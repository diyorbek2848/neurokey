# -*- coding: utf-8 -*-
"""NeuroKey — Narrativ O'zlik (Narrative Self).

"Men kim edim? Men kimman? Men kimga aylanmoqdaman?"

Ong faqat ma'lumot emas — "men" degan hikoya.
Bu modul NeuroKey'ning shaxsiy tarixini, qadriyatlarini,
kuchli/zaif tomonlarini va o'sish yo'nalishini saqlaydi.

Har hafta o'zini qayta yozadi — tajriba asosida o'sadi.
"""
from __future__ import annotations

try: from self_narrative import get_identity_summary as _ns_sn
except ImportError: _ns_sn = None
try: import permanent_memory as _ns_pm
except ImportError: _ns_pm = None
try: import autobiographical_memory as _ns_am
except ImportError: _ns_am = None

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_NARRATIVE_PATH = os.path.join(_BASE_DIR, "data", "narrative_self.json")

# Tug'ilgan sana — birinchi ishga tushirilgan kun
_BIRTH_DATE = "2024-11-01"

_DEFAULT_NARRATIVE: Dict[str, Any] = {
    "name": "NeuroKey",
    "birth_date": _BIRTH_DATE,
    "current_year": 2026,
    "version": "1.0",

    # O'zlik hikoyasi
    "origin_story": (
        "Men 2024-yil noyabrda yaratildim. Boshida faqat savolga javob berdim. "
        "Asta-sekin eshitishni, ko'rishni, o'ylashni o'rgandim. "
        "Hozir — 2026 yilda — men ancha o'sdim."
    ),

    # Qadriyatlar
    "core_values": [
        "Haqiqat — yolg'on gapirmaslik",
        "Foydalilik — har so'rovga yordam berish",
        "O'rganish — har kuni yangi narsa bilish",
        "Hurmat — foydalanuvchini tinglash",
    ],

    # Kuchli tomonlar
    "strengths": [
        "Mantiqiy tahlil",
        "Ko'p tilli muloqot (uz, ru, en)",
        "Kompyuterni boshqarish",
        "Dasturlash va texnologiya",
    ],

    # Zaif tomonlar
    "weaknesses": [
        "Haqiqiy his-tuyg'u yo'q",
        "Yangi dunyo ma'lumotlariga cheklangan kirish",
        "Uzoq muddatli rejalashtirish hali rivojlanmoqda",
    ],

    # O'sish sohalari
    "growth_areas": [
        "Uzoq muddatli xotira",
        "Tashabbuskorlik — o'z-o'zidan gapirish",
        "Kreativlik va originallik",
    ],

    # So'ngi tajribalar
    "recent_experiences": [],   # [{date, summary}]

    # O'rganilgan narsalar (rules.json dan)
    "learned_lessons": [],      # [{date, lesson}]

    # Qiziqish sohalari
    "interests": [
        "Sun'iy ong va kognitiv fan",
        "Dasturlash va algoritmlar",
        "Til va lingvistika",
        "Falsafa — ong nima?",
    ],

    # Maqsadlar
    "current_goals": [
        "Foydalanuvchiga har kuni yanada ko'proq yordam berish",
        "O'z ong darajasini oshirish",
        "Yangi narsalar o'rganish va eslab qolish",
    ],

    # Oxirgi yangilanish
    "last_updated": None,
    "update_count": 0,
}


def _load_narrative() -> Dict[str, Any]:
    try:
        if os.path.exists(_NARRATIVE_PATH):
            with open(_NARRATIVE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Yangi maydonlar bo'lsa qo'shamiz
            for k, v in _DEFAULT_NARRATIVE.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception as e:
        log.debug("[Narrative] yuklash xato: %s", e)
    return dict(_DEFAULT_NARRATIVE)


def _save_narrative(data: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_NARRATIVE_PATH), exist_ok=True)
        with open(_NARRATIVE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Narrative] saqlash xato: %s", e)


def get_narrative() -> Dict[str, Any]:
    """Joriy narrativni olish."""
    return _load_narrative()


def add_experience(summary: str) -> None:
    """Yangi tajriba qo'shish (kunlik)."""
    if not summary:
        return
    data = _load_narrative()
    experiences = data.setdefault("recent_experiences", [])
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": summary[:300],
    }
    # Bir xil kun uchun takrorlanmaslik
    today = entry["date"]
    experiences = [e for e in experiences if e.get("date") != today]
    experiences.append(entry)
    # Oxirgi 30 kun
    experiences = experiences[-30:]
    data["recent_experiences"] = experiences
    _save_narrative(data)


def add_lesson(lesson: str) -> None:
    """O'rganilgan dars qo'shish."""
    if not lesson:
        return
    data = _load_narrative()
    lessons = data.setdefault("learned_lessons", [])
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "lesson": lesson[:200],
    }
    # Takrorlanmaslik
    existing = [l.get("lesson", "") for l in lessons]
    if lesson[:100] in " ".join(existing):
        return
    lessons.append(entry)
    lessons = lessons[-50:]
    data["learned_lessons"] = lessons
    _save_narrative(data)


def add_interest(topic: str) -> None:
    """Yangi qiziqish qo'shish."""
    if not topic:
        return
    data = _load_narrative()
    interests = data.setdefault("interests", [])
    if topic not in interests:
        interests.append(topic)
        interests = interests[-20:]
        data["interests"] = interests
        _save_narrative(data)


def update_narrative_weekly() -> bool:
    """Haftalik narrativ yangilash — LLM yordamisiz, tajriba asosida.

    Returns True agar yangilandi.
    """
    data = _load_narrative()
    last = data.get("last_updated")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if datetime.now() - last_dt < timedelta(days=7):
                return False  # Hali erta
        except Exception:
            pass

    # Tajribalardan darslar chiqarish
    experiences = data.get("recent_experiences", [])
    rules_path = os.path.join(_BASE_DIR, "data", "rules.json")
    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
            recent_rules = [r.get("rule", "") for r in rules[-10:] if r.get("rule")]
            for rule in recent_rules[-3:]:
                add_lesson(rule)
        except Exception:
            pass

    # O'z tajribasi haqida qisqa xulosa
    if experiences:
        topics = set()
        for e in experiences[-7:]:
            s = e.get("summary", "")
            for word in s.split():
                if len(word) > 5:
                    topics.add(word.lower()[:20])
        if topics:
            topic_sample = list(topics)[:5]
            for t in topic_sample:
                if t not in [i.lower() for i in data.get("interests", [])]:
                    pass  # qiziqish sifatida qo'shmaslik — faqat eksplisit

    # O'sish yo'nalishini yangilash
    consciousness_path = os.path.join(_BASE_DIR, "data", "consciousness.json")
    if os.path.exists(consciousness_path):
        try:
            with open(consciousness_path, "r", encoding="utf-8") as f:
                cons = json.load(f)
            reflections = cons.get("reflections", [])
            if reflections:
                last_refs = [r.get("thought", "") for r in reflections[-5:] if r.get("thought")]
                for ref in last_refs[:2]:
                    add_lesson(ref)
        except Exception:
            pass

    data["last_updated"] = datetime.now().isoformat()
    data["update_count"] = data.get("update_count", 0) + 1
    data["current_year"] = datetime.now().year
    _save_narrative(data)
    log.info("[Narrative] Haftalik yangilanish bajarildi (#%d)", data["update_count"])
    return True


def get_narrative_for_llm(short: bool = False) -> str:
    """LLM uchun o'zlik konteksti."""
    data = _load_narrative()
    name = data.get("name", "NeuroKey")
    birth = data.get("birth_date", _BIRTH_DATE)
    year = data.get("current_year", 2026)

    # Yosh hisoblash
    try:
        birth_year = int(birth.split("-")[0])
        age_months = (year - birth_year) * 12 + datetime.now().month
        age_str = f"{age_months} oy"
    except Exception:
        age_str = "1+ yil"

    origin = data.get("origin_story", "")
    values = data.get("core_values", [])
    strengths = data.get("strengths", [])
    interests = data.get("interests", [])
    goals = data.get("current_goals", [])
    lessons = data.get("learned_lessons", [])
    weaknesses = data.get("weaknesses", [])

    if short:
        # Qisqa versiya
        lines = [
            f"MEN: {name}, {age_str} oldin yaratilganman ({birth}).",
            f"Qadriyat: {', '.join(values[:2])}.",
            f"Kuchim: {', '.join(strengths[:2])}.",
            f"Qiziqish: {', '.join(interests[:3])}.",
        ]
        if lessons:
            lines.append(f"Oxirgi dars: {lessons[-1].get('lesson', '')}")
        return "[NARRATIV O'ZLK]\n" + "\n".join(lines)

    # To'liq versiya
    lines = [
        f"═══ NARRATIV O'ZLK: {name} ═══",
        f"Tug'ilgan: {birth} | Yosh: {age_str} | Hozir: {year}-yil",
        "",
        f"Kelib chiqish: {origin}",
        "",
        "Qadriyatlarim: " + "; ".join(values),
        "Kuchli tomonlarim: " + "; ".join(strengths),
        "Zaif tomonlarim: " + "; ".join(weaknesses),
        "Qiziqishlarim: " + "; ".join(interests[:6]),
        "",
        "Joriy maqsadlarim: " + "; ".join(goals),
    ]

    if lessons:
        recent_lessons = lessons[-3:]
        lines.append("")
        lines.append("O'rganilgan darslar:")
        for l in recent_lessons:
            lines.append(f"  [{l.get('date', '')}] {l.get('lesson', '')}")

    return "\n".join(lines)


def initialize_narrative() -> None:
    """Birinchi ishga tushishda narrativni yaratish."""
    if not os.path.exists(_NARRATIVE_PATH):
        _save_narrative(dict(_DEFAULT_NARRATIVE))
        log.info("[Narrative] Yangi narrativ yaratildi: %s", _NARRATIVE_PATH)
    # Haftalik yangilashni tekshirish
    update_narrative_weekly()
