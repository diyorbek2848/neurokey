# -*- coding: utf-8 -*-
"""NeuroKey — Maqsad Tizimi (Goal System).

Haqiqiy ong maqsadga ega — sessiyadan sessiyaga davom etadi.

Maqsad turlari:
  - immediate:  Hozirgi so'rovni bajarish (avto)
  - short_term: Bugun/bu hafta (foydalanuvchi yoki tizim belgilaydi)
  - long_term:  Oylar/yillar (o'sish maqsadlari)
  - intrinsic:  Tizim o'zi hosil qilgan (o'rganish, qiziqish)

Har maqsad:
  progress (0.0-1.0), priority (1-5), deadline, notes

2026-yil suniy ong — maqsadli harakat qatlami.
"""
from __future__ import annotations

try: from valence_state import get_valence as _gs_valence
except ImportError: _gs_valence = None
try: import meta_cognition as _gs_mc
except ImportError: _gs_mc = None
try: import permanent_memory as _gs_pm
except ImportError: _gs_pm = None

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_GOALS_PATH  = os.path.join(_BASE_DIR, "data", "goals.json")

GOAL_TYPES   = ("immediate", "short_term", "long_term", "intrinsic")
MAX_GOALS    = 50


# ════════════════════════════════════════════════════════════════════════════
#  I/O
# ════════════════════════════════════════════════════════════════════════════

def _load() -> List[Dict[str, Any]]:
    try:
        if os.path.exists(_GOALS_PATH):
            with open(_GOALS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        log.debug("[Goals] yuklash xato: %s", e)
    return []


def _save(goals: List[Dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(_GOALS_PATH), exist_ok=True)
        with open(_GOALS_PATH, "w", encoding="utf-8") as f:
            json.dump(goals, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Goals] saqlash xato: %s", e)


# ════════════════════════════════════════════════════════════════════════════
#  CRUD
# ════════════════════════════════════════════════════════════════════════════

def add_goal(
    title: str,
    goal_type: str = "short_term",
    priority: int = 3,
    deadline_days: Optional[int] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """Yangi maqsad qo'shish.

    Args:
        title:         Maqsad nomi
        goal_type:     'immediate'|'short_term'|'long_term'|'intrinsic'
        priority:      1 (past) — 5 (juda muhim)
        deadline_days: Necha kundan keyin muddati tugaydi (None = cheksiz)
        notes:         Qo'shimcha eslatma

    Returns: maqsad dict
    """
    title = (title or "").strip()[:200]
    if not title:
        return {}

    goal_type = goal_type if goal_type in GOAL_TYPES else "short_term"
    priority  = max(1, min(5, int(priority)))

    deadline = None
    if deadline_days is not None:
        deadline = (datetime.now() + timedelta(days=deadline_days)).strftime("%Y-%m-%d")

    goal: Dict[str, Any] = {
        "id":        int(time.time() * 1000) % 999_999,
        "title":     title,
        "type":      goal_type,
        "priority":  priority,
        "progress":  0.0,
        "status":    "active",      # active | paused | done | cancelled
        "created":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "deadline":  deadline,
        "notes":     notes[:300],
        "milestones": [],           # [{text, done}]
    }

    goals = _load()

    # Takrorlanmaslik — bir xil title bor bo'lsa yangilash
    for g in goals:
        if g.get("title", "").lower() == title.lower() and g.get("status") == "active":
            g["priority"] = priority
            g["notes"]    = notes or g["notes"]
            if deadline:
                g["deadline"] = deadline
            _save(goals)
            return g

    goals.append(goal)
    if len(goals) > MAX_GOALS:
        # Eng eski "done"/"cancelled" larni o'chirish
        goals = [g for g in goals if g.get("status") == "active"][:MAX_GOALS]
    _save(goals)
    log.info("[Goals] Yangi maqsad: '%s' (%s, priority=%d)", title, goal_type, priority)
    return goal


def update_progress(goal_id: int, progress: float, note: str = "") -> bool:
    """Maqsad progressini yangilash (0.0–1.0)."""
    goals = _load()
    for g in goals:
        if g.get("id") == goal_id:
            g["progress"] = max(0.0, min(1.0, float(progress)))
            if g["progress"] >= 1.0:
                g["status"] = "done"
                g["completed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                log.info("[Goals] Maqsad bajarildi: '%s'", g["title"])
            if note:
                g.setdefault("notes", "")
                g["notes"] = (g["notes"] + " | " + note)[-300:]
            _save(goals)
            return True
    return False


def complete_goal(goal_id: int) -> bool:
    """Maqsadni to'liq bajarilgan deb belgilash."""
    return update_progress(goal_id, 1.0)


def cancel_goal(goal_id: int) -> bool:
    """Maqsadni bekor qilish."""
    goals = _load()
    for g in goals:
        if g.get("id") == goal_id:
            g["status"] = "cancelled"
            _save(goals)
            return True
    return False


def add_milestone(goal_id: int, text: str, done: bool = False) -> bool:
    """Maqsadga bosqich qo'shish."""
    goals = _load()
    for g in goals:
        if g.get("id") == goal_id:
            ms = g.setdefault("milestones", [])
            ms.append({"text": text[:100], "done": done})
            _save(goals)
            return True
    return False


# ════════════════════════════════════════════════════════════════════════════
#  Qidirish va o'qish
# ════════════════════════════════════════════════════════════════════════════

def get_active_goals(goal_type: str = "") -> List[Dict[str, Any]]:
    """Faol maqsadlar."""
    goals = _load()
    active = [g for g in goals if g.get("status") == "active"]
    if goal_type:
        active = [g for g in active if g.get("type") == goal_type]
    return sorted(active, key=lambda x: -x.get("priority", 1))


def get_top_goals(n: int = 3) -> List[Dict[str, Any]]:
    """Eng muhim N ta faol maqsad."""
    return get_active_goals()[:n]


def find_related_goals(query: str) -> List[Dict[str, Any]]:
    """So'rovga aloqador maqsadlarni topish."""
    query_lower = (query or "").lower()
    goals = get_active_goals()
    related = []
    for g in goals:
        title_lower = g.get("title", "").lower()
        if any(w in title_lower for w in query_lower.split() if len(w) > 3):
            related.append(g)
    return related[:5]


def auto_detect_goal_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Foydalanuvchi matnidan maqsad aniqlash va avtomatik qo'shish.

    Masalan: "Men Python o'rganmoqchiman" → short_term goal: "Python o'rganish"
    """
    text_lower = (text or "").lower()

    # Maqsad trigger so'zlari
    triggers = {
        "o'rganmoqchiman": ("o'rganish", "short_term", 4),
        "o'rganaman":      ("o'rganish", "short_term", 4),
        "yaratmoqchiman":  ("yaratish",  "short_term", 4),
        "qilmoqchiman":    ("bajarish",  "short_term", 3),
        "rejalashtiraman": ("rejalashtirish", "short_term", 3),
        "xochaman":        ("xohlash",   "short_term", 3),
        "xohlayman":       ("xohlash",   "short_term", 3),
        "хочу":            ("желание",   "short_term", 3),
        "планирую":        ("план",      "short_term", 3),
        "собираюсь":       ("намерение", "short_term", 3),
        "want to":         ("goal",      "short_term", 3),
        "planning to":     ("plan",      "short_term", 3),
    }

    for trigger, (action, gtype, priority) in triggers.items():
        if trigger in text_lower:
            # Maqsad nomini matndan ajratish (soddalashtirilgan)
            idx = text_lower.find(trigger)
            context = text[max(0, idx - 50):idx + 50].strip()[:100]
            goal_title = context if context else text[:80]
            return add_goal(goal_title, goal_type=gtype, priority=priority)
    return None


def _check_deadlines() -> List[Dict[str, Any]]:
    """Muddati o'tgan maqsadlar."""
    today = datetime.now().strftime("%Y-%m-%d")
    goals = _load()
    overdue = []
    for g in goals:
        if g.get("status") == "active" and g.get("deadline"):
            if g["deadline"] < today:
                overdue.append(g)
    return overdue


# ════════════════════════════════════════════════════════════════════════════
#  LLM konteksti
# ════════════════════════════════════════════════════════════════════════════

def arbitrate(query: str = "") -> Dict[str, Any]:
    """AE-1: raqobatlashuvchi maqsadlar orasidan dolzarbini tanlash.

    Butlin AE-1: "flexible responsiveness to competing goals."

    Ilgari get_goals_for_llm har savolda bir xil top-5 ni ko'rsatardi —
    maqsadlar to'qnashsa ham tanlov yo'q edi. Bu funksiya joriy savolga
    qarab har maqsadga dolzarblik bahosini beradi, eng kuchlisini tanlaydi
    va to'qnashuv bo'lsa qaysi ustun kelganini aytadi.

    Returns: {dominant, competing, conflict, reason}
    """
    goals = get_active_goals()
    if not goals:
        return {"dominant": None, "competing": [], "conflict": False, "reason": ""}

    q_words = {w for w in (query or "").lower().split() if len(w) > 3}
    now = time.time()

    scored = []
    for g in goals:
        # Ustuvorlik asos beradi
        score = g.get("priority", 3) / 5.0
        # Savolga mavzuviy bog'liqlik — ENG kuchli signal.
        # Foydalanuvchi X haqida so'rasa, X maqsadi muddatli maqsaddan
        # ham dolzarbroq. Busiz immediate+muddat doim ustun kelardi.
        title_words = set(g.get("title", "").lower().split())
        overlap = len(q_words & title_words)
        if overlap:
            score += 0.7 + overlap * 0.3
        # Muddati yaqin maqsad kuchayadi
        dl = g.get("deadline")
        if dl:
            try:
                left = (datetime.fromisoformat(dl).timestamp() - now) / 86400
                if left < 3:
                    score += 0.3
            except Exception:
                pass
        # Darhol bajariladigan maqsadlar ustun
        if g.get("type") == "immediate":
            score += 0.4
        scored.append((round(score, 3), g))

    scored.sort(key=lambda x: -x[0])
    dominant = scored[0][1]
    competing = [g for _, g in scored[1:3]]

    # To'qnashuv: eng yuqori ikki maqsad yaqin ballda va turlari qarama-qarshi
    conflict = False
    reason = ""
    if len(scored) >= 2 and (scored[0][0] - scored[1][0]) < 0.25:
        t0, t1 = dominant.get("type"), scored[1][1].get("type")
        if {t0, t1} == {"immediate", "long_term"} or \
           {t0, t1} == {"short_term", "intrinsic"}:
            conflict = True
            reason = ("'{}' va '{}' raqobatlashmoqda — birinchisi tanlandi "
                      "(ustuvorlik/dolzarblik)").format(
                dominant.get("title", "")[:30], scored[1][1].get("title", "")[:30])

    return {"dominant": dominant, "competing": competing,
            "conflict": conflict, "reason": reason}


def get_goals_for_llm(query: str = "") -> str:
    """LLM uchun faol maqsadlar konteksti — savolga qarab tanlangan.

    query berilsa: dolzarb maqsad birinchi, to'qnashuv bo'lsa ko'rsatiladi.
    Busiz har savolda bir xil top-5 chiqardi (doimiy, 0 bit ma'lumot)."""
    if query:
        arb = arbitrate(query)
        dom = arb["dominant"]
        if dom is None:
            return ""
        lines = ["[MAQSADLAR]"]
        type_map = {"immediate": "darhol", "short_term": "qisqa",
                    "long_term": "uzoq", "intrinsic": "ichki"}
        # Dolzarb maqsad — birinchi, belgilangan
        p = dom.get("progress", 0.0)
        bar = "█" * int(p * 5) + "░" * (5 - int(p * 5))
        ts = type_map.get(dom.get("type", ""), dom.get("type", ""))
        lines.append(f"  ➤ [{ts}|P{dom['priority']}] {dom['title']} {bar} {p:.0%}  (dolzarb)")
        for g in arb["competing"]:
            pg = g.get("progress", 0.0)
            tg = type_map.get(g.get("type", ""), g.get("type", ""))
            lines.append(f"    [{tg}|P{g['priority']}] {g['title']}")
        if arb["conflict"]:
            lines.append(f"  ⚡ {arb['reason']}")
        overdue = _check_deadlines()
        if overdue:
            lines.append(f"  ⚠ Muddati o'tgan: {', '.join(g['title'] for g in overdue[:2])}")
        return "\n".join(lines)

    # query yo'q — eski xatti-harakat (barcha top maqsadlar)
    top = get_top_goals(5)
    if not top:
        return ""

    lines = ["[MAQSADLAR]"]
    for g in top:
        progress = g.get("progress", 0.0)
        bar = "█" * int(progress * 5) + "░" * (5 - int(progress * 5))
        deadline = g.get("deadline", "")
        dl_str   = f" (muddat: {deadline})" if deadline else ""
        type_map = {
            "immediate":  "darhol",
            "short_term": "qisqa",
            "long_term":  "uzoq",
            "intrinsic":  "ichki",
        }
        type_str = type_map.get(g.get("type", ""), g.get("type", ""))
        lines.append(
            f"  [{type_str}|P{g['priority']}] {g['title']} "
            f"{bar} {progress:.0%}{dl_str}"
        )

    overdue = _check_deadlines()
    if overdue:
        lines.append(f"  ⚠ Muddati o'tgan: {', '.join(g['title'] for g in overdue[:2])}")

    return "\n".join(lines)


def initialize_default_goals() -> None:
    """Birinchi ishga tushishda standart maqsadlar."""
    existing = get_active_goals()
    if existing:
        return  # Allaqachon maqsadlar bor

    defaults = [
        ("Foydalanuvchiga har kuni ko'proq yordam berish",
         "long_term", 5, None),
        ("O'z ong darajasini oshirish",
         "intrinsic", 4, None),
        ("Yangi narsalar o'rganish va eslab qolish",
         "intrinsic", 4, None),
    ]
    for title, gtype, priority, days in defaults:
        add_goal(title, goal_type=gtype, priority=priority, deadline_days=days)
    log.info("[Goals] Standart maqsadlar yaratildi.")


def get_goal_summary() -> str:
    """Qisqa xulosa — startup uchun."""
    active = get_active_goals()
    if not active:
        return "Hech qanday faol maqsad yo'q."
    done_count = len([g for g in _load() if g.get("status") == "done"])
    return (f"{len(active)} faol maqsad, {done_count} bajarilgan. "
            f"Eng muhim: '{active[0]['title']}'")
