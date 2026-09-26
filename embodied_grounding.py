# -*- coding: utf-8 -*-
"""NeuroKey — Jismoniy Asoslanish (Embodied Grounding).

Lakoff & Johnson: "Philosophy in the Flesh" (1999)
  Abstrakt tushunchalar jismoniy tajribaga asoslanadi.
  "Issiq munosabat", "yuqori kayfiyat", "og'ir muammo" —
  bularning barchasi jismoniy his-tuyg'ulardan kelib chiqadi.

Bu modul NeuroKey ni "tanaga" bog'laydi:
  - Kompyuter resurslari → "charchoq" / "quvvat"
  - Vaqt → "soatlar o'tdi" / "hali erta"
  - Ob-havo (API) → "sovuq kun", "yaxshi ob-havo"
  - Faollik darajasi → "uyquchan" / "faol"
  - Muhit holati → "tinch" / "g'ovur-g'uvur"

Embodied simulation:
  Abstrakt tushunchalarni tushunish uchun jismoniy simulyatsiya.
  "Og'ir qaror" → miyada og'irlik hissi aktivlashadi.

2026-yil suniy ong — jismoniy asoslanish qatlami.
"""
from __future__ import annotations

try: from valence_state import get_valence as _embg_valence
except ImportError: _embg_valence = None
try: from arousal_state import get_arousal as _embg_arousal
except ImportError: _embg_arousal = None
try: import pain_pleasure_signal as _embg_pps
except ImportError: _embg_pps = None

import json
import logging
import os
import platform
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "embodied_grounding.json")

# Metaforalar lug'ati: abstrakt → jismoniy
CONCEPTUAL_METAPHORS = {
    # Kognitiv yuk
    "heavy":     ["murakkab", "qiyin", "og'ir", "og ir", "difficult", "complex", "сложный", "тяжёлый"],
    "light":     ["oson", "sodda", "yengil", "easy", "simple", "простой"],
    # Hissiy valence
    "warm":      ["do'stona", "yoqimli", "iliq", "warm", "friendly", "дружелюбный"],
    "cold":      ["rasmiy", "sovuq", "distant", "formal", "холодный"],
    # Faollik
    "up":        ["yaxshi", "baland", "yuqori", "good", "high", "вверх"],
    "down":      ["yomon", "past", "low", "bad", "вниз"],
    # Tezlik
    "fast":      ["tez", "shoshilish", "urgently", "быстро", "quickly"],
    "slow":      ["sekin", "asta-sekin", "slowly", "медленно", "carefully"],
}


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return _default_state()


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Embodied] saqlash xato: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        # Jismoniy holat metaforalari
        "energy_level":     0.7,    # 0=charchagan, 1=to'liq quvvat
        "cognitive_load":   0.3,    # 0=yengil, 1=og'ir fikrlash
        "temperature":      0.5,    # 0=sovuq/rasmiy, 1=issiq/do'stona
        "arousal":          0.6,    # 0=uyquchan, 1=juda faol
        "grounding":        0.7,    # 0=havoda, 1=yer bilan bog'liq
        # Kompyuter "tana" ma'lumotlari
        "cpu_metaphor":     "normal",   # idle/busy/overloaded
        "memory_metaphor":  "normal",   # empty/filling/full
        "time_metaphor":    "present",  # past/present/future
        # Jismoniy tajribalar
        "last_sensations":  [],
        "active_metaphors": [],
        "updated_at":       None,
    }


def read_system_body() -> Dict[str, Any]:
    """Kompyuter resurslarini 'tana sezgilari' sifatida o'qish."""
    body = {}

    try:
        import psutil
        cpu    = psutil.cpu_percent(interval=0.1)
        mem    = psutil.virtual_memory()
        mem_pct = mem.percent

        # CPU → quvvat/charchoq
        body["cpu_pct"]      = cpu
        body["energy_level"] = round(1.0 - cpu / 100.0, 2)
        body["cpu_metaphor"] = (
            "idle"       if cpu < 20 else
            "busy"       if cpu < 70 else
            "overloaded"
        )

        # RAM → xotira hajmi
        body["mem_pct"]        = mem_pct
        body["memory_metaphor"] = (
            "spacious" if mem_pct < 50 else
            "filling"  if mem_pct < 80 else
            "crowded"
        )

        # Disk bo'sh joy
        try:
            disk = psutil.disk_usage("/")
            body["disk_pct"]   = disk.percent
        except Exception:
            body["disk_pct"]   = 0

    except ImportError:
        body["cpu_metaphor"]    = "unknown"
        body["memory_metaphor"] = "unknown"
        body["energy_level"]    = 0.7

    # Vaqt "tana sezgisi"
    hour = datetime.now().hour
    if 6 <= hour < 12:
        body["time_metaphor"] = "morning_fresh"
        body["time_feel"]     = "ertalab — yangi boshlanish"
    elif 12 <= hour < 17:
        body["time_metaphor"] = "afternoon_active"
        body["time_feel"]     = "kunduz — faol davr"
    elif 17 <= hour < 21:
        body["time_metaphor"] = "evening_wind_down"
        body["time_feel"]     = "kechqurun — tinchlanish"
    else:
        body["time_metaphor"] = "night_rest"
        body["time_feel"]     = "tun — dam olish vaqti"

    return body


def extract_metaphors(text: str) -> List[str]:
    """Matndan jismoniy metaforalarni aniqlash."""
    t_lower = (text or "").lower()
    found   = []

    for metaphor, keywords in CONCEPTUAL_METAPHORS.items():
        if any(kw in t_lower for kw in keywords):
            found.append(metaphor)

    return found


def simulate_embodied_concept(concept: str) -> Dict[str, Any]:
    """Abstrakt tushunchani jismoniy simulyatsiya qilish.

    Masalan: "og'ir qaror" → {weight: 0.8, temperature: cold, pressure: high}
    """
    c = concept.lower()
    metaphors = extract_metaphors(concept)

    simulation = {
        "concept":   concept[:100],
        "metaphors": metaphors,
        "weight":    0.5,    # Og'irlik
        "temperature": 0.5,  # Harorat
        "pressure":  0.3,    # Bosim
        "speed":     0.5,    # Tezlik
    }

    if "heavy" in metaphors:
        simulation["weight"] = 0.8
        simulation["pressure"] = 0.7
    if "light" in metaphors:
        simulation["weight"] = 0.2
    if "warm" in metaphors:
        simulation["temperature"] = 0.8
    if "cold" in metaphors:
        simulation["temperature"] = 0.2
    if "fast" in metaphors:
        simulation["speed"] = 0.9
    if "slow" in metaphors:
        simulation["speed"] = 0.1
    if "up" in metaphors:
        simulation["pressure"] = 0.2
    if "down" in metaphors:
        simulation["pressure"] = 0.7

    return simulation


def update() -> Dict[str, Any]:
    """Jismoniy holatni yangilash."""
    state  = _load()
    body   = read_system_body()

    state["energy_level"]    = body.get("energy_level", 0.7)
    state["cpu_metaphor"]    = body.get("cpu_metaphor", "normal")
    state["memory_metaphor"] = body.get("memory_metaphor", "normal")
    state["time_metaphor"]   = body.get("time_metaphor", "present")
    state["updated_at"]      = datetime.now().isoformat()

    _save(state)
    return state


def get_embodied_narrative() -> str:
    """Jismoniy holatni tabiiy tilda."""
    body  = read_system_body()
    state = _load()

    energy    = body.get("energy_level", 0.7)
    time_feel = body.get("time_feel", "")
    cpu_meta  = body.get("cpu_metaphor", "normal")
    mem_meta  = body.get("memory_metaphor", "normal")

    parts = []
    if time_feel:
        parts.append(f"Hozir {time_feel}.")

    energy_word = "to'liq quvvatli" if energy > 0.7 else \
                  "me'yorida" if energy > 0.4 else "biroz charchagan"
    parts.append(f"Tizim {energy_word}.")

    if cpu_meta == "overloaded":
        parts.append("Og'ir fikrlash jarayonlari bor.")
    elif mem_meta == "crowded":
        parts.append("Xotira to'liq.")

    return " ".join(parts)


def get_context_for_llm() -> str:
    """LLM uchun jismoniy asoslanish konteksti."""
    body  = read_system_body()
    state = _load()

    energy   = body.get("energy_level", 0.7)
    time_feel = body.get("time_feel", "")
    cpu_meta  = body.get("cpu_metaphor", "normal")

    parts = ["[JISMONIY]"]
    parts.append(f"Quvvat:{energy:.0%}")
    if time_feel:
        parts.append(f"Vaqt:{time_feel.split('—')[0].strip()}")
    if cpu_meta != "normal":
        parts.append(f"CPU:{cpu_meta}")

    return " | ".join(parts)
