# -*- coding: utf-8 -*-
"""NeuroKey — O'z-O'zini Yaxshilash Halqasi (Self-Improvement Loop).

Haqiqiy ong o'z xatolarini ko'radi va o'zgaradi.
Bu modul:
  - Har suhbatdan keyin o'z-o'zini baholaydi
  - Xatolarni aniqlaydi va sababini tushunadi
  - Yaxshilanish bo'yicha reja tuzadi
  - Qadriyatlar va uslubni moslaydi
  - O'zining ong darajasini kuzatib boradi

Psixologik asosi: PDCA tsikli + Kolb o'rganish tsikli
  Plan → Do → Check → Act
  Experience → Reflection → Conceptualization → Experiment

2026-yil suniy ong — metakognitiv o'z-o'zini yaxshilash.
"""
from __future__ import annotations

try: import self_healing as _sil_sh
except ImportError: _sil_sh = None
try: from meta_meta_cognition import get_epistemic_humility_score as _sil_mmc
except ImportError: _sil_mmc = None
try: import permanent_memory as _sil_pm
except ImportError: _sil_pm = None

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH   = os.path.join(_BASE_DIR, "data", "self_improvement_log.json")
_PLAN_PATH  = os.path.join(_BASE_DIR, "data", "improvement_plan.json")

MAX_LOG_ENTRIES = 500


# ════════════════════════════════════════════════════════════════════════════
#  Sifat baholash
# ════════════════════════════════════════════════════════════════════════════

QUALITY_DIMENSIONS = {
    "accuracy":     "To'g'rilik",
    "clarity":      "Ravonlik",
    "helpfulness":  "Foydalilik",
    "empathy":      "Hamdardlik",
    "conciseness":  "Qisqalik",
    "depth":        "Chuqurlik",
    "creativity":   "Ijodkorlik",
    "timing":       "Vaqt",
}


def _load_log() -> List[Dict[str, Any]]:
    try:
        if os.path.exists(_LOG_PATH):
            with open(_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_log(entries: List[Dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        if len(entries) > MAX_LOG_ENTRIES:
            entries = entries[-MAX_LOG_ENTRIES:]
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[SelfImprove] log xato: %s", e)


def _load_plan() -> Dict[str, Any]:
    try:
        if os.path.exists(_PLAN_PATH):
            with open(_PLAN_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"improvements": [], "focus_area": "", "updated_at": None}


def _save_plan(plan: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_PLAN_PATH), exist_ok=True)
        with open(_PLAN_PATH, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[SelfImprove] plan xato: %s", e)


# ════════════════════════════════════════════════════════════════════════════
#  O'z-o'zini baholash
# ════════════════════════════════════════════════════════════════════════════

def evaluate_response(
    user_query: str,
    bot_response: str,
    user_feedback: str = "",
) -> Dict[str, Any]:
    """Javobni avtomatik baholash va o'rganish.

    Returns: {scores, issues, lessons, overall}
    """
    scores: Dict[str, float] = {}
    issues: List[str] = []
    lessons: List[str] = []

    resp_lower  = (bot_response or "").lower()
    query_lower = (user_query or "").lower()
    feedback_l  = (user_feedback or "").lower()

    # === To'g'rilik ===
    accuracy = 0.75
    if any(w in feedback_l for w in ["xato", "noto'g'ri", "wrong", "incorrect", "неправильно"]):
        accuracy = 0.2
        issues.append("Javob noto'g'ri bo'lishi mumkin")
        lessons.append("Noaniq mavzularda 'menimcha' yoki 'tekshirish tavsiya etiladi' de")
    elif any(w in feedback_l for w in ["to'g'ri", "correct", "правильно", "ha"]):
        accuracy = 0.95
    scores["accuracy"] = accuracy

    # === Ravonlik ===
    clarity = 0.7
    avg_word_per_sentence = len(resp_lower.split()) / max(resp_lower.count(".") + 1, 1)
    if avg_word_per_sentence > 30:
        clarity = 0.4
        issues.append("Jumlalar juda uzun")
        lessons.append("Har jumlada 15-20 so'zdan oshma")
    elif avg_word_per_sentence < 8:
        clarity = 0.9
    scores["clarity"] = clarity

    # === Foydalilik ===
    helpfulness = 0.7
    if any(w in feedback_l for w in ["yordam berdi", "rahmat", "ajoyib", "helpful"]):
        helpfulness = 0.95
        lessons.append("Bu yondashuv foydali — takrorlash mumkin")
    elif any(w in feedback_l for w in ["keraksiz", "useless", "не помогло"]):
        helpfulness = 0.2
        issues.append("Javob foydasiz deb baholandi")
    scores["helpfulness"] = helpfulness

    # === Qisqalik ===
    word_count = len(bot_response.split())
    if word_count > 300:
        conciseness = 0.3
        issues.append(f"Javob juda uzun ({word_count} so'z)")
        lessons.append("300 so'zdan oshmasin, asosiyni ajrat")
    elif word_count < 10:
        conciseness = 0.4
        issues.append("Javob juda qisqa")
    else:
        conciseness = 0.8
    scores["conciseness"] = conciseness

    # === Hamdardlik ===
    empathy = 0.6
    emotional_queries = ["yordam", "qiyin", "tushunmayapman", "xafa", "help", "confused"]
    if any(w in query_lower for w in emotional_queries):
        empathy_words = ["tushunaman", "yordam", "birga", "understand", "help you"]
        if any(w in resp_lower for w in empathy_words):
            empathy = 0.9
        else:
            empathy = 0.4
            lessons.append("Hissiy so'rovlarga avval hamdardlik bildirish kerak")
    scores["empathy"] = empathy

    # Umumiy ball
    overall = sum(scores.values()) / len(scores)
    scores["overall"] = round(overall, 3)

    # Yaxshilanish rejasiga qo'shish
    if issues:
        _add_to_plan(issues, lessons, overall)

    # Logga yozish
    entry = {
        "timestamp": datetime.now().isoformat(),
        "query_short": user_query[:60],
        "scores": {k: round(v, 2) for k, v in scores.items()},
        "issues": issues,
        "lessons": lessons,
        "overall": round(overall, 3),
    }
    log_entries = _load_log()
    log_entries.append(entry)
    _save_log(log_entries)

    if issues:
        log.info("[SelfImprove] Muammolar: %s", "; ".join(issues[:2]))

    return entry


def _add_to_plan(issues: List[str], lessons: List[str], score: float) -> None:
    """Yaxshilanish rejasini yangilash."""
    plan = _load_plan()
    improvements = plan.setdefault("improvements", [])

    for issue in issues:
        # Allaqachon bormi?
        existing = next((i for i in improvements if i.get("issue","") == issue), None)
        if existing:
            existing["count"] = existing.get("count", 1) + 1
            existing["last_seen"] = datetime.now().isoformat()
        else:
            improvements.append({
                "issue":     issue,
                "count":     1,
                "first_seen": datetime.now().isoformat(),
                "last_seen":  datetime.now().isoformat(),
                "resolved":   False,
            })

    # Lessons
    for lesson in lessons:
        plan.setdefault("lessons", [])
        if lesson not in plan["lessons"]:
            plan["lessons"].append(lesson)
            plan["lessons"] = plan["lessons"][-30:]  # Eng oxirgi 30

    # Eng ko'p uchraydigan muammo — focus area
    if improvements:
        most_common = max(improvements, key=lambda x: x.get("count", 1))
        plan["focus_area"] = most_common["issue"]

    plan["updated_at"] = datetime.now().isoformat()
    plan["avg_score"]  = score
    _save_plan(plan)


# ════════════════════════════════════════════════════════════════════════════
#  Tahlil va hisobot
# ════════════════════════════════════════════════════════════════════════════

def get_improvement_plan() -> Dict[str, Any]:
    """Hozirgi yaxshilanish rejasi."""
    return _load_plan()


def get_top_issues(n: int = 3) -> List[Dict[str, Any]]:
    """Eng ko'p uchraydigan muammolar."""
    plan = _load_plan()
    issues = [i for i in plan.get("improvements", []) if not i.get("resolved")]
    return sorted(issues, key=lambda x: -x.get("count", 1))[:n]


def get_recent_lessons(n: int = 5) -> List[str]:
    """Oxirgi N ta dars."""
    plan = _load_plan()
    return plan.get("lessons", [])[-n:]


def get_performance_trend() -> Dict[str, Any]:
    """Oxirgi 20 suhbat bo'yicha samaradorlik trendi."""
    entries = _load_log()[-20:]
    if not entries:
        return {"trend": "no_data", "avg_score": 0.5}

    scores  = [e.get("overall", 0.5) for e in entries]
    avg     = sum(scores) / len(scores)
    first_5 = sum(scores[:5]) / 5 if len(scores) >= 5 else avg
    last_5  = sum(scores[-5:]) / 5 if len(scores) >= 5 else avg

    if last_5 > first_5 + 0.05:
        trend = "improving"
    elif last_5 < first_5 - 0.05:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "trend":     trend,
        "avg_score": round(avg, 3),
        "first_5":   round(first_5, 3),
        "last_5":    round(last_5, 3),
        "samples":   len(entries),
    }


def get_self_reflection() -> str:
    """O'z-o'zini tahlil qilish — tabiiy tilda."""
    trend   = get_performance_trend()
    issues  = get_top_issues(2)
    lessons = get_recent_lessons(2)
    plan    = _load_plan()

    parts = []
    avg = trend.get("avg_score", 0.5)
    parts.append(f"O'rtacha sifat darajam: {avg:.0%}.")

    t = trend.get("trend", "stable")
    if t == "improving":
        parts.append("So'nggi suhbatlarda yaxshilanmoqdaman.")
    elif t == "declining":
        parts.append("So'nggi suhbatlarda sifatim pasaymoqda — diqqat kerak.")
    else:
        parts.append("Sifatim barqaror.")

    if issues:
        parts.append("Asosiy muammo: " + issues[0]["issue"] + ".")

    focus = plan.get("focus_area", "")
    if focus:
        parts.append(f"Hozirgi diqqat yo'nalishi: {focus}.")

    return " ".join(parts)


def get_context_for_llm() -> str:
    """LLM uchun o'z-o'zini yaxshilash konteksti."""
    trend   = get_performance_trend()
    lessons = get_recent_lessons(2)
    issues  = get_top_issues(1)

    if trend.get("trend") == "no_data":
        return ""

    parts = ["[САМОСОВЕРШЕНСТВОВАНИЕ]"]
    avg   = trend.get("avg_score", 0.5)
    parts.append(f"Качество: {avg:.0%}")

    if issues:
        parts.append(f"Внимание: {issues[0]['issue'][:40]}")

    if lessons:
        parts.append(f"Урок: {lessons[-1][:50]}")

    return " | ".join(parts)
