# -*- coding: utf-8 -*-
"""NeuroKey — Sabab-Natija Zanjiri (Causal Chain Reasoning).

GPT shunchaki matndan pattern topadi.
Haqiqiy ong sabab → natija → oqibat zanjirini tushunadi.

Bu modul:
  1. Voqealar zanjirini saqlaydi:  A → B → C
  2. Yangi holat uchun bashorat qiladi: "Agar X bo'lsa, Y bo'ladi"
  3. Counterfactual fikrlaydi: "Agar boshqacha qilsam nima bo'lardi?"
  4. Tizim o'z xatolarini tahlil qiladi va xulosalar chiqaradi
  5. LLM ga kontekst sifatida uzatiladi

Arxitektura:
  - CausalEvent: bir voqea (cause → effect, context, confidence)
  - CausalChain: bir nechta voqealar ketma-ketligi
  - Oddiy SQLite saqlash (og'ir library kerak emas)

2026-yil suniy ong — sabab-natija idrok qatlami.
"""
from __future__ import annotations

try: import predictive_layer as _cc_pl
except ImportError: _cc_pl = None
try: import permanent_memory as _cc_pm
except ImportError: _cc_pm = None

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_CAUSAL_PATH = os.path.join(_BASE_DIR, "data", "causal_chain.json")

MAX_CHAINS   = 200   # maksimal zanjirlar soni
MAX_EVENTS   = 500   # maksimal voqealar


# ════════════════════════════════════════════════════════════════════════════
#  Ma'lumot tuzilmasi
# ════════════════════════════════════════════════════════════════════════════

def _make_event(
    cause:      str,
    effect:     str,
    context:    str  = "",
    confidence: float = 0.7,
    domain:     str  = "general",
    verified:   bool  = False,
) -> Dict[str, Any]:
    """Bir sabab-natija voqeasi."""
    return {
        "id":         int(time.time() * 1000) % 999_999,
        "cause":      cause.strip()[:300],
        "effect":     effect.strip()[:300],
        "context":    context.strip()[:200],
        "confidence": max(0.0, min(1.0, float(confidence))),
        "domain":     domain,
        "verified":   verified,
        "count":      1,          # necha marta tasdiqlandi
        "created":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_seen":  datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _make_chain(
    title:   str,
    events:  List[Dict[str, Any]],
    domain:  str = "general",
) -> Dict[str, Any]:
    """Bir nechta voqealardan iborat zanjir."""
    return {
        "id":      int(time.time() * 1000) % 999_999,
        "title":   title.strip()[:200],
        "events":  events,
        "domain":  domain,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ════════════════════════════════════════════════════════════════════════════
#  I/O
# ════════════════════════════════════════════════════════════════════════════

def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_CAUSAL_PATH):
            with open(_CAUSAL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.debug("[Causal] yuklash xato: %s", e)
    return {"events": [], "chains": []}


def _save(data: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_CAUSAL_PATH), exist_ok=True)
        with open(_CAUSAL_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Causal] saqlash xato: %s", e)


# ════════════════════════════════════════════════════════════════════════════
#  Asosiy API
# ════════════════════════════════════════════════════════════════════════════

def add_event(
    cause:      str,
    effect:     str,
    context:    str   = "",
    confidence: float = 0.7,
    domain:     str   = "general",
) -> Dict[str, Any]:
    """Yangi sabab → natija qo'shish.

    Agar bir xil cause+effect allaqachon bor bo'lsa — count va confidence yangilanadi.
    """
    if not cause or not effect:
        return {}

    data   = _load()
    events = data["events"]

    # Takrorlanmaslik — mavjud bo'lsa yangilash
    cause_l  = cause.lower().strip()
    effect_l = effect.lower().strip()
    for ev in events:
        if (ev["cause"].lower().strip()[:50]  == cause_l[:50] and
                ev["effect"].lower().strip()[:50] == effect_l[:50]):
            ev["count"]      += 1
            ev["confidence"] = min(1.0, ev["confidence"] + 0.05)
            ev["verified"]   = ev["count"] >= 3
            ev["last_seen"]  = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save(data)
            return ev

    ev = _make_event(cause, effect, context, confidence, domain)
    events.append(ev)

    # MAX_EVENTS cheklash — eng past confidence larni o'chirish
    if len(events) > MAX_EVENTS:
        events.sort(key=lambda x: (x.get("confidence", 0), x.get("count", 0)))
        data["events"] = events[int(MAX_EVENTS * 0.1):]

    _save(data)
    log.debug("[Causal] Yangi voqea: '%s' -> '%s'", cause[:40], effect[:40])
    return ev


def add_chain(title: str, steps: List[Tuple[str, str]], domain: str = "general") -> Dict[str, Any]:
    """Ko'p bosqichli zanjir qo'shish.

    steps = [(cause1, effect1), (cause2, effect2), ...]
    Har step avvalgi effectning cause'i bo'ladi.
    """
    if not title or not steps:
        return {}

    data   = _load()
    events = []
    for i, (c, e) in enumerate(steps):
        ev = _make_event(c, e, domain=domain, confidence=0.6)
        events.append(ev)

    chain = _make_chain(title, events, domain)
    data.setdefault("chains", []).append(chain)

    # Voqealarni ham alohida saqlaymiz
    for ev in events:
        add_event(ev["cause"], ev["effect"], domain=domain)

    # MAX_CHAINS cheklash
    if len(data["chains"]) > MAX_CHAINS:
        data["chains"] = data["chains"][-MAX_CHAINS:]

    _save(data)
    return chain


def record_outcome(cause: str, actual_effect: str, was_correct: bool) -> None:
    """Bashorat natijasini qayd etish — o'rganish uchun."""
    data   = _load()
    events = data["events"]
    cause_l = cause.lower().strip()

    for ev in events:
        if ev["cause"].lower().strip()[:60] == cause_l[:60]:
            if was_correct:
                ev["confidence"] = min(1.0, ev["confidence"] + 0.1)
                ev["count"]     += 1
                ev["verified"]  = ev["count"] >= 3
            else:
                ev["confidence"] = max(0.0, ev["confidence"] - 0.15)
            ev["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            break
    else:
        # Yangi voqea sifatida qo'shish
        ev = _make_event(cause, actual_effect, confidence=0.5 if was_correct else 0.2)
        events.append(ev)

    _save(data)


# ════════════════════════════════════════════════════════════════════════════
#  Qidirish va bashorat
# ════════════════════════════════════════════════════════════════════════════

def predict_effect(cause: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Berilgan sababga oid natijalarni topish."""
    if not cause:
        return []
    cause_l = cause.lower()
    data    = _load()
    results = []

    words = [w for w in cause_l.split() if len(w) > 3]
    if not words:
        words = cause_l.split()

    for ev in data["events"]:
        ev_cause_l = ev["cause"].lower()
        if any(w in ev_cause_l for w in words):
            results.append(ev)

    results.sort(key=lambda x: -(x.get("confidence", 0) * x.get("count", 1)))
    return results[:top_k]


def find_related_causes(effect: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Berilgan natijaga oid sabablarni topish."""
    if not effect:
        return []
    effect_l = effect.lower()
    data     = _load()
    results  = []

    words = [w for w in effect_l.split() if len(w) > 3]
    if not words:
        words = effect_l.split()

    for ev in data["events"]:
        ev_effect_l = ev["effect"].lower()
        if any(w in ev_effect_l for w in words):
            results.append(ev)

    results.sort(key=lambda x: -(x.get("confidence", 0)))
    return results[:top_k]


def counterfactual(original_cause: str, alternative_cause: str) -> str:
    """Counterfactual fikrlash: 'Agar X emas, Y bo'lsam nima bo'lardi?'"""
    orig_effects = predict_effect(original_cause, top_k=2)
    alt_effects  = predict_effect(alternative_cause, top_k=2)

    if not orig_effects and not alt_effects:
        return (f"'{original_cause}' va '{alternative_cause}' haqida "
                f"yetarli ma'lumot yo'q.")

    orig_str = orig_effects[0]["effect"] if orig_effects else "noma'lum"
    alt_str  = alt_effects[0]["effect"]  if alt_effects  else "noma'lum"

    return (f"Agar '{original_cause}' bo'lsa: '{orig_str}'.\n"
            f"Agar '{alternative_cause}' bo'lsa: '{alt_str}'.")


# ════════════════════════════════════════════════════════════════════════════
#  Avtomatik o'rganish suhbatdan
# ════════════════════════════════════════════════════════════════════════════

# Sabab-natija bog'lovchi so'zlar
_CAUSAL_CONNECTORS = [
    ("chunki", "reverse"),    # "B chunki A" => A->B
    ("sababli", "reverse"),
    ("natijasida", "forward"),# "A natijasida B" => A->B
    ("shuning uchun", "forward"),
    ("oqibatida", "forward"),
    ("потому что", "reverse"),
    ("потому", "reverse"),
    ("поэтому", "forward"),
    ("из-за", "reverse"),
    ("в результате", "forward"),
    ("because", "reverse"),
    ("therefore", "forward"),
    ("so ", "forward"),
    ("leads to", "forward"),
    ("causes", "forward"),
    ("results in", "forward"),
]


def extract_causal_from_text(text: str, domain: str = "general") -> List[Dict[str, Any]]:
    """Matndan sabab-natija munosabatlarini avtomatik chiqarish."""
    if not text or len(text) < 10:
        return []

    found = []
    text_lower = text.lower()

    for connector, direction in _CAUSAL_CONNECTORS:
        idx = text_lower.find(connector)
        if idx < 0:
            continue

        before = text[:idx].strip()
        after  = text[idx + len(connector):].strip()

        # Jumlani cheklash
        before = before.split(".")[-1].strip()[:200]
        after  = after.split(".")[0].strip()[:200]

        if len(before) < 5 or len(after) < 5:
            continue

        if direction == "forward":
            cause, effect = before, after
        else:
            cause, effect = after, before

        ev = add_event(cause, effect, context=text[:100], domain=domain, confidence=0.55)
        if ev:
            found.append(ev)

    return found


# ════════════════════════════════════════════════════════════════════════════
#  LLM konteksti
# ════════════════════════════════════════════════════════════════════════════

def get_causal_context_for_llm(query: str) -> str:
    """LLM uchun tegishli sabab-natija konteksti."""
    predictions = predict_effect(query, top_k=3)
    causes      = find_related_causes(query, top_k=2)
    combined    = predictions + causes

    if not combined:
        return ""

    seen = set()
    lines = ["[SABAB-NATIJA MA'LUMOTNOMA]"]
    for ev in combined:
        key = (ev["cause"][:30], ev["effect"][:30])
        if key in seen:
            continue
        seen.add(key)
        conf = ev.get("confidence", 0.5)
        cnt  = ev.get("count", 1)
        lines.append(
            f"  {ev['cause'][:60]} → {ev['effect'][:60]}  "
            f"(ishonch: {conf:.0%}, tasdiqlangan: {cnt}x)"
        )

    return "\n".join(lines)


def add_system_lesson(situation: str, what_happened: str, lesson: str) -> None:
    """Tizim o'z xatosidan dars chiqarganda saqlash."""
    add_event(
        cause=situation,
        effect=what_happened,
        context=f"Dars: {lesson}",
        domain="system_lesson",
        confidence=0.8,
    )
    log.info("[Causal] Tizim darsi: '%s' -> '%s'", situation[:40], lesson[:40])


def get_stats() -> Dict[str, Any]:
    data = _load()
    verified = [e for e in data["events"] if e.get("verified")]
    return {
        "total_events":    len(data["events"]),
        "total_chains":    len(data.get("chains", [])),
        "verified_events": len(verified),
    }


# ════════════════════════════════════════════════════════════════════════════
#  Standart bilimlar (birinchi ishga tushishda)
# ════════════════════════════════════════════════════════════════════════════

def initialize_default_knowledge() -> None:
    """Asosiy sabab-natija bilimlarini yuklash."""
    data = _load()
    if data["events"]:
        return  # allaqachon bilimlar bor

    defaults = [
        # Tizim
        ("foydalanuvchi uzoq vaqt kutsa",
         "frustratsiya ortadi",
         "ux", 0.9),
        ("tizim xato bersa va tushuntirilmasa",
         "foydalanuvchi ishonchini yo'qotadi",
         "ux", 0.85),
        ("qisqa va aniq javob berilsa",
         "foydalanuvchi mamnun bo'ladi",
         "ux", 0.8),
        # O'rganish
        ("yangi ma'lumot eski bilan bog'lansa",
         "yaxshi eslab qolinadi",
         "learning", 0.85),
        ("bir narsa ko'p marta takrorlansa",
         "yodga singib qoladi",
         "learning", 0.9),
        # Muloqot
        ("foydalanuvchi qisqa savol bersa",
         "qisqa javob kutadi",
         "communication", 0.8),
        ("foydalanuvchi '!!!' yoki '???' ishlatsa",
         "asabiy yoki hayron ekanligini bildiradi",
         "communication", 0.85),
    ]

    for cause, effect, domain, conf in defaults:
        add_event(cause, effect, domain=domain, confidence=conf)

    log.info("[Causal] Standart bilimlar yuklandi.")
