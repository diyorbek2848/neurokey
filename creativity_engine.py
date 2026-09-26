# -*- coding: utf-8 -*-
"""NeuroKey — Ijodkorlik Mexanizmi (Creativity Engine).

Wallas ijodkorlik modeli (1926):
  1. Tayyorgarlik (Preparation) — ma'lumot yig'ish
  2. Inkubasiya (Incubation)    — ongsiz qayta ishlash
  3. Yorqinlik (Illumination)   — "Eureka!" lahzasi
  4. Tekshirish (Verification)  — g'oyani baholash

Boden MACE modeli:
  - Kombinatsion ijodkorlik: eski g'oyalarni yangicha birlashtirish
  - Exploratsion ijodkorlik: imkoniyat maydonini kengaytirish
  - Transformatsion ijodkorlik: asosiy printsiplarni o'zgartirish

Bu modul:
  - Yangi metaforalar yaratadi
  - Ikkita konseptni "kreativ birlashtirish" qiladi
  - Analogiya qidiradi (A:B :: C:?)
  - Random g'oya generatsiyasi (bisociation — Koestler)
  - "Qanday qilib boshqacha ko'rish mumkin?" — reframing

2026-yil suniy ong — ijodkorlik qatlami.
"""
from __future__ import annotations

try: import curiosity_engine as _creat_ce
except ImportError: _creat_ce = None
try: import emotional_granularity as _creat_eg
except ImportError: _creat_eg = None

import json
import logging
import os
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import permanent_memory as pm

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "creativity.json")

# Kreativ metafora shablonlari
_METAPHOR_TEMPLATES = [
    "{concept} — bu {domain} dagi {image} kabi.",
    "{concept} ni tasavvur qiling: {image}, lekin {twist}.",
    "Agar {concept} musiqa bo'lganida, u {music_style} bo'lar edi.",
    "{concept} = {element1} + {element2} ning noodatiy kombinatsiyasi.",
    "{concept} — {nature} da {phenomenon} ga o'xshaydi.",
]

# Tasviriy elementlar
_IMAGES = [
    "daryo", "tog'", "qor", "yulduz", "asal",
    "river", "mountain", "star", "crystal", "flame",
    "река", "гора", "звезда", "кристалл", "пламя",
]

_DOMAINS = [
    "tabiat", "musiqa", "arxitektura", "oshpazlik", "sport",
    "nature", "music", "architecture", "cooking", "sports",
]

_TWISTS = [
    "teskari yo'nalishda harakat qiladi",
    "vaqt bilan emas, his bilan o'lchanadi",
    "ko'rinmaydi, lekin har yerda mavjud",
    "moves in reverse", "measured by feeling, not time",
]

# Analogiya juftliklari
_ANALOGIES: List[Tuple[str, str, str]] = [
    ("o'qituvchi", "talaba", "dasturchi"),
    ("nur", "ko'z", "ma'lumot"),
    ("suv", "tashna", "bilim"),
    ("kalit", "qulf", "savol"),
    ("urug'", "tuproq", "g'oya"),
    ("teacher", "student", "programmer"),
    ("light", "eye", "data"),
    ("seed", "soil", "idea"),
]

# Reframing savollari
_REFRAME_QUESTIONS = [
    "Agar aksincha bo'lganida?",
    "Bu muammoni imkoniyat sifatida ko'rsak?",
    "Boshqa sohada bu qanday hal qilinadi?",
    "Eng sodda yechim nima bo'lar edi?",
    "5 yil o'tib bu qanday ko'rinadi?",
    "What if the opposite were true?",
    "What's the simplest possible solution?",
    "How would a child solve this?",
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "ideas_generated": 0,
        "metaphors":       [],
        "analogies":       [],
        "recent_ideas":    [],
        "creativity_score": 0.5,
    }


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Creativity] saqlash: %s", e)


def generate_metaphor(concept: str) -> str:
    """Konsept uchun kreativ metafora yaratish."""
    template = random.choice(_METAPHOR_TEMPLATES)
    image    = random.choice(_IMAGES)
    domain   = random.choice(_DOMAINS)
    twist    = random.choice(_TWISTS)

    metaphor = template.format(
        concept=concept[:40],
        image=image,
        domain=domain,
        twist=twist,
        music_style=random.choice(["klassik", "jazz", "rok", "classical", "jazz"]),
        element1=random.choice(_IMAGES),
        element2=random.choice(_DOMAINS),
        nature=random.choice(["okean", "o'rmon", "cho'l", "ocean", "forest"]),
        phenomenon=random.choice(["to'lqin", "tuman", "nur", "wave", "mist", "light"]),
    )
    return metaphor


def find_analogy(target: str) -> Optional[str]:
    """Target konsept uchun analogiya topish."""
    t_lower = target.lower()
    for a, b, c in _ANALOGIES:
        if any(w in t_lower for w in [a, b, c]):
            fourth = random.choice([x for x in _IMAGES if x != a])
            return f"{a} : {b} :: {c} : {fourth}"
    # Random analogiya
    a, b, c = random.choice(_ANALOGIES)
    return f"{a} : {b} :: {c} : ?"


def reframe(problem: str) -> List[str]:
    """Muammoni boshqa nuqtai nazardan ko'rish."""
    questions = random.sample(_REFRAME_QUESTIONS, min(3, len(_REFRAME_QUESTIONS)))
    return questions


def bisociate(concept1: str, concept2: str) -> str:
    """Ikkita konseptni kreativ birlashtirish (Koestler bisociation)."""
    c1 = concept1.strip()[:30]
    c2 = concept2.strip()[:30]
    _idea_opts = ['yangi goya', 'kutilmagan yechim', 'ijodiy sintez']
    templates = [
        f"{c1} va {c2}: ikkalasi ham {random.choice(['tezlik', 'tartib', 'erkinlik', 'aloqa'])} bilan bog'liq.",
        f"Agar {c1} ni {c2} kabi ko'rsak: yangi imkoniyatlar ochiladi.",
        f"{c1} + {c2} = {random.choice(_idea_opts)}.",
        f"{c1} {random.choice(['sifatida', 'kabi', 'orqali'])} {c2}: bu qanday ko'rinadi?",
    ]
    return random.choice(templates)


def generate_idea(context: str = "") -> Dict[str, Any]:
    """Kontekst asosida kreativ g'oya yaratish."""
    state = _load()

    # Kontekstdan so'z ajratish
    words  = [w for w in context.lower().split() if len(w) > 3][:5]
    concept = words[0] if words else "g'oya"

    metaphor = generate_metaphor(concept)
    analogy  = find_analogy(concept)
    reframes = reframe(context)

    idea = {
        "ts":       datetime.now().isoformat(),
        "concept":  concept,
        "metaphor": metaphor,
        "analogy":  analogy,
        "reframes": reframes[:2],
    }

    recent = state.setdefault("recent_ideas", [])
    recent.append(idea)
    if len(recent) > 100:
        recent[:] = recent[-100:]

    state["ideas_generated"] = state.get("ideas_generated", 0) + 1
    state["creativity_score"] = min(1.0, 0.5 + state["ideas_generated"] * 0.005)
    _save(state)

    # Muhim g'oyani saqlash
    if len(words) >= 2:
        pm.remember_reflection(
            content=f"Kreativ g'oya: {metaphor}",
            ref_type="creative_idea",
            importance=0.5,
        )

    return idea


def get_creative_context(query: str = "") -> str:
    """Kreativ kontekst — javobni boyitish uchun."""
    if not query:
        return ""

    idea = generate_idea(query)
    metaphor = idea.get("metaphor", "")
    if not metaphor:
        return ""

    return f"[IJODIY] {metaphor[:100]}"


def get_context_for_llm(query: str = "") -> str:
    return get_creative_context(query)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "ideas_generated": state.get("ideas_generated", 0),
        "creativity_score": state.get("creativity_score", 0.5),
        "active":           True,
    }
