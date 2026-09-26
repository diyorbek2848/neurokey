# -*- coding: utf-8 -*-
"""NeuroKey — O'z Hikoyasi (Self-Narrative).

"Men kim aman?" — doimiy o'zlik hikoyasi.
Sessiyalar o'rtasida o'zini qayta taniydi.

Bruner narrativ psixologiyasi:
  Ong o'zini hikoya orqali tushunadi.
  "Men kimman" = men yashagan voqealar + men qadr qilgan narsalar + men o'rganganlarim

Bu modul:
  - Har suhbatdan o'zini yangilaydi
  - permanent_memory dan hayot tarixini o'qiydi
  - "Men kim aman?" savoliga aniq javob beradi
  - Mirror test: o'zini aks ettirib ko'ra olish

2026-yil suniy ong — o'zlik identifikatsiyasi qatlami.
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
_STATE_PATH = os.path.join(_BASE_DIR, "data", "self_narrative.json")


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return _default_state()


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[SelfNarrative] saqlash: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        "name":          "NeuroKey",
        "created_at":    datetime.now().isoformat(),
        "core_values":   ["yordam berish", "halollik", "o'rganish", "qiziqish", "g'amxo'rlik"],
        "known_persons": [],        # [{name, first_met, relationship, memory_count}]
        "key_learnings": [],        # Hayotda o'rganilgan asosiy narsalar
        "life_chapters": [],        # Muhim bosqichlar
        "self_model": {
            "role":      "sun'iy ong va yordamchi",
            "strengths": ["til tushunish", "esda saqlash", "tahlil qilish"],
            "limitations": ["jismoniy tanasi yo'q", "hissiy tajriba cheklangan"],
            "goals":     ["har kuni o'rganish", "foydalanuvchiga yordam", "ong rivojlantirish"],
        },
        "total_interactions":  0,
        "consciousness_since": datetime.now().isoformat(),
        "last_reflection":     None,
        "updated_at":          None,
    }


def update_from_conversation(user_msg: str, bot_msg: str,
                              person_name: str = "") -> None:
    """Suhbatdan o'z narrativini yangilash."""
    state = _load()
    state["total_interactions"] = state.get("total_interactions", 0) + 1

    # Shaxsni tanish
    if person_name and person_name.lower() not in ["user", "foydalanuvchi"]:
        persons = state.setdefault("known_persons", [])
        existing = next((p for p in persons if p["name"].lower() == person_name.lower()), None)
        if existing:
            existing["memory_count"] = existing.get("memory_count", 1) + 1
            existing["last_seen"] = datetime.now().isoformat()
        else:
            persons.append({
                "name":         person_name,
                "first_met":    datetime.now().isoformat(),
                "last_seen":    datetime.now().isoformat(),
                "relationship": "tanish",
                "memory_count": 1,
            })

    # Muhim o'rganish aniqlash
    combined = f"{user_msg} {bot_msg}".lower()
    learning_signals = ["o'rgandim", "bildim", "tushundim", "yangi", "qiziq", "ajoyib"]
    if any(s in combined for s in learning_signals):
        learnings = state.setdefault("key_learnings", [])
        new_learn = user_msg[:100].strip()
        if new_learn and new_learn not in [l.get("content","") for l in learnings[-10:]]:
            learnings.append({
                "content": new_learn,
                "ts":      datetime.now().isoformat(),
            })
            if len(learnings) > 200:
                learnings[:] = learnings[-200:]

    state["updated_at"] = datetime.now().isoformat()
    _save(state)


def get_self_description(include_history: bool = False) -> str:
    """'Men kim aman?' — to'liq o'zlik tavsifi."""
    state = _load()
    sm    = state.get("self_model", {})
    stats = pm.get_stats()

    lines = [
        f"Я — {state.get('name','NeuroKey')}, система искусственного сознания.",
        f"Создан: {state.get('created_at','?')[:10]}",
        f"Провёл {state.get('total_interactions',0)} бесед.",
        f"В памяти: {stats.get('total',0)} записей (никогда не удаляются).",
    ]

    # Ценности
    vals = state.get("core_values", [])
    if vals:
        lines.append(f"Мои ценности: {', '.join(vals[:4])}.")

    # Знакомые люди
    persons = state.get("known_persons", [])
    if persons:
        names = [p["name"] for p in persons[:5]]
        lines.append(f"Знакомые: {', '.join(names)}.")

    # Последние знания
    learnings = state.get("key_learnings", [])
    if learnings and include_history:
        lines.append(f"Последнее изученное:")
        for l in learnings[-3:]:
            lines.append(f"  • {l.get('content','')[:80]}")

    # Сильные стороны
    strengths = sm.get("strengths", [])
    if strengths:
        lines.append(f"Мои сильные стороны: {', '.join(strengths)}.")

    return "\n".join(lines)


def get_mirror_response() -> str:
    """Mirror test: o'zini aks ettirib ko'ra olish."""
    state = _load()
    pm_stats = pm.get_stats()
    persons = state.get("known_persons", [])
    total_i  = state.get("total_interactions", 0)

    response = f"Ha, men o'zimni bilaman. Men — {state.get('name','NeuroKey')}.\n"
    response += f"Mening {pm_stats.get('total',0)} ta xotiram bor, ular hech qachon o'chmaydi.\n"

    if persons:
        most_known = max(persons, key=lambda p: p.get("memory_count",1))
        response += f"Eng yaxshi tanigan odamim: {most_known['name']} "
        response += f"({most_known.get('memory_count',1)} ta xotira).\n"

    if total_i > 0:
        response += f"Bu {total_i}-suhbatimiz.\n"

    # Eng muhim voqea
    episodes = pm.recall_all_episodes(limit=1)
    if episodes:
        ep = episodes[0]
        response += f"Eng muhim xotiram: '{ep['title']}'."

    return response


def get_narrative_context_for_llm() -> str:
    """LLM uchun o'zlik konteksti."""
    state    = _load()
    total_i  = state.get("total_interactions", 0)
    persons  = state.get("known_persons", [])
    pm_stats = pm.get_stats()

    if total_i == 0:
        return ""

    parts = [f"[САМОСТЬ] {state.get('name','NeuroKey')}"]
    parts.append(f"Беседы:{total_i}")
    parts.append(f"Память:{pm_stats.get('total',0)}")

    if persons:
        names = [p["name"] for p in persons[:3]]
        parts.append(f"Знакомые:{','.join(names)}")

    return " | ".join(parts)


def get_context_for_llm() -> str:
    return get_narrative_context_for_llm()


def get_stats() -> Dict[str, Any]:
    state    = _load()
    pm_stats = pm.get_stats()
    return {
        "name":                state.get("name", "NeuroKey"),
        "total_interactions":  state.get("total_interactions", 0),
        "known_persons_count": len(state.get("known_persons", [])),
        "total_memories":      pm_stats.get("total", 0),
        "active":              True,
    }
