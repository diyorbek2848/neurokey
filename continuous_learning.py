# -*- coding: utf-8 -*-
"""NeuroKey — Uzluksiz O'rganish (Continuous Learning).

Hebbian o'rganish: "Birga yonuvchi neyronlar birga bog'lanadi."
Kolb tajribaviy o'rganish sikli:
  1. Konkret tajriba
  2. Reflektiv kuzatish
  3. Abstrakt konseptualizatsiya
  4. Faol eksperimentatsiya

Bu modul:
  - Har suhbatdan avtomatik bilim ajratadi
  - Yangi faktlar → knowledge bazasiga qo'shiladi
  - Takroriy mavzular → kuchaytiradi (Hebbian)
  - Xatolar → qoida yaratadi
  - Muvaffaqiyatlar → yaxshi usulni eslab qoladi
  - O'rganish tezligini (learning rate) moslaydi
  - permanent_memory ga barcha o'rganishlarni saqlaydi

Hech qachon unutmaydi, doim o'sadi.

2026-yil suniy ong — uzluksiz o'rganish qatlami.
"""
from __future__ import annotations

try: from meta_meta_cognition import get_epistemic_humility_score as _cl_mmc
except ImportError: _cl_mmc = None
try: import self_improvement_loop as _cl_sil
except ImportError: _cl_sil = None

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import permanent_memory as pm

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "continuous_learning.json")

# Bilim ajratish naqshlari — faqat rus tili
_FACT_PATTERNS = [
    # "X — это Y" / "X это Y"
    r"([А-ЯЁ][а-яёА-ЯЁ\s]+?)\s+(?:—\s*это|это|является)\s+([^.!?]{10,80})",
    # "X означает Y"
    r"(\w+)\s+(?:означает|значит)\s+([^.!?]{5,80})",
    # "известно что..." / "важно что..."
    r"(?:известно,?\s+что|важно,?\s+что|оказывается,?\s+что)\s+([^.!?]{10,100})",
    # "Y называется X" / "X называют Y"
    r"([а-яёА-ЯЁ\w]+)\s+называ(?:ется|ют)\s+([^.!?]{5,80})",
    # простое определение в кавычках: «термин» — описание
    r"[«\"]([^»\"]{3,40})[»\"]\s*[—–-]\s*([^.!?]{10,80})",
]

# Сигналы обучения (только русский)
_LEARNING_SIGNALS = [
    "узнал", "понял", "открыл", "научился", "разобрался",
    "интересно", "новое", "выяснил", "обнаружил", "запомню",
]

# Сигналы ошибки (только русский)
_ERROR_SIGNALS = [
    "неправильно", "не понял", "ошибка", "неверно",
    "не так", "перепутал", "неточно", "исправь",
]

# Сигналы успеха (только русский)
_SUCCESS_SIGNALS = [
    "правильно", "верно", "отлично", "именно", "точно",
    "молодец", "хорошо", "выполнено", "готово", "справился",
]


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "learning_rate":    0.3,
        "total_learned":    0,
        "topics_learned":   {},    # {topic: count}
        "recent_lessons":   [],
        "skills_acquired":  [],
        "updated_at":       None,
    }


def _save(state: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[CL] saqlash: %s", e)


def extract_facts(text: str) -> List[str]:
    """Matndan faktlarni avtomatik ajratish."""
    facts = []
    for pattern in _FACT_PATTERNS:
        try:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                fact = " ".join(m) if isinstance(m, tuple) else m
                fact = fact.strip()
                if 10 < len(fact) < 200:
                    facts.append(fact)
        except Exception:
            pass
    return facts[:5]


def detect_topic(text: str) -> str:
    """Matn mavzusini aniqlash."""
    t = text.lower()
    if any(w in t for w in ["python", "kod", "funksiya", "class", "import"]):
        return "python"
    if any(w in t for w in ["math", "formula", "hisob", "algebra", "integral"]):
        return "mathematics"
    if any(w in t for w in ["ml", "ai", "neural", "model", "train"]):
        return "machine_learning"
    if any(w in t for w in ["til", "grammar", "language", "so'z"]):
        return "language"
    if any(w in t for w in ["tarix", "history", "давно", "yil", "asr"]):
        return "history"
    if any(w in t for w in ["fan", "science", "fizika", "kimyo", "biologiya"]):
        return "science"
    return "general"


def learn_from_conversation(user_msg: str, bot_msg: str,
                              feedback: str = "") -> Dict[str, Any]:
    """Suhbatdan avtomatik o'rganish.

    Args:
        user_msg:  Foydalanuvchi xabari
        bot_msg:   Bot javobi
        feedback:  Keyingi xabar (muvaffaqiyat/xato signali)
    """
    state = _load()
    ts    = datetime.now().isoformat()

    learned = []
    topic   = detect_topic(user_msg + " " + bot_msg)

    # 1. Mavzuni kuchaytirish (Hebbian)
    topics = state.setdefault("topics_learned", {})
    topics[topic] = topics.get(topic, 0) + 1

    # 2. Faktlarni ajratish
    facts = extract_facts(bot_msg)
    for fact in facts:
        pm.remember_knowledge(
            topic=topic,
            content=fact,
            source="conversation",
            confidence=0.6,
        )
        learned.append({"type": "fact", "content": fact[:100]})

    # 3. Feedback tahlili
    if feedback:
        fb_lower = feedback.lower()

        # Xato → qoida yaratish
        if any(s in fb_lower for s in _ERROR_SIGNALS):
            rule = f"'{bot_msg[:60]}...' uslubi xato edi — boshqacha qil"
            pm.remember_rule(rule, rule_type="fix", source="auto_learn")
            learned.append({"type": "error_rule", "content": rule[:100]})
            # Learning rate kamaytirish (shu yo'ldan qayt)
            state["learning_rate"] = max(0.1, state["learning_rate"] - 0.02)

        # Muvaffaqiyat → usulni saqlash
        elif any(s in fb_lower for s in _SUCCESS_SIGNALS):
            rule = f"'{bot_msg[:60]}...' uslubi yaxshi ishladi"
            pm.remember_rule(rule, rule_type="success", source="auto_learn")
            learned.append({"type": "success_rule", "content": rule[:100]})
            # Learning rate oshirish
            state["learning_rate"] = min(0.9, state["learning_rate"] + 0.01)

    # 4. O'rganish signali
    if any(s in (user_msg + bot_msg).lower() for s in _LEARNING_SIGNALS):
        pm.remember_reflection(
            content=f"O'rganish: {user_msg[:100]}",
            ref_type="learning",
            importance=0.6,
        )
        learned.append({"type": "learning_moment", "content": user_msg[:60]})

    # Tarix
    if learned:
        lessons = state.setdefault("recent_lessons", [])
        lessons.append({
            "ts":      ts,
            "topic":   topic,
            "count":   len(learned),
            "items":   learned[:3],
        })
        if len(lessons) > 200:
            lessons[:] = lessons[-200:]
        state["total_learned"] = state.get("total_learned", 0) + len(learned)

    state["updated_at"] = ts
    _save(state)

    return {
        "learned_count": len(learned),
        "topic":         topic,
        "items":         learned,
        "learning_rate": state["learning_rate"],
    }


def get_learned_topics() -> Dict[str, int]:
    state = _load()
    topics = state.get("topics_learned", {})
    return dict(sorted(topics.items(), key=lambda x: -x[1])[:10])


def get_recent_lessons(n: int = 10) -> List[Dict]:
    state = _load()
    return state.get("recent_lessons", [])[-n:]


def get_learning_progress() -> str:
    """O'rganish progressi tavsifi."""
    state  = _load()
    total  = state.get("total_learned", 0)
    topics = get_learned_topics()
    rate   = state.get("learning_rate", 0.3)

    if total == 0:
        return "Ещё ничего не изучено."

    top_topic = list(topics.keys())[0] if topics else "general"
    return (
        f"Изучено {total} элементов. "
        f"Основная тема: {top_topic}. "
        f"Скорость обучения: {rate:.0%}."
    )


def get_context_for_llm() -> str:
    state  = _load()
    total  = state.get("total_learned", 0)
    topics = get_learned_topics()
    rate   = state.get("learning_rate", 0.3)

    if total == 0:
        return ""

    top3 = list(topics.keys())[:3]
    parts = [f"[ОБУЧЕНИЕ] Всего: {total}"]
    if top3:
        parts.append(f"Темы: {', '.join(top3)}")
    return " | ".join(parts)


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "total_learned":  state.get("total_learned", 0),
        "learning_rate":  state.get("learning_rate", 0.3),
        "topics_count":   len(state.get("topics_learned", {})),
        "active":         True,
    }
