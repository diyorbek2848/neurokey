"""
goal_memory.py — NeuroKey Maqsad Xotirasi

NeuroKey o'z maqsadlarini biladi va ularga intiladi.
Ultron kabi — maqsadsiz emas, har doim intilish bor.

Maqsad turlari:
- TEZKOR (joriy sessiya)
- UZOQ MUDDATLI (hafta/oy)
- ASOSIY (o'zgarmas qadriyatlar)
"""
from __future__ import annotations
import json, os, time, logging
from typing import Optional

log = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_GOALS_FILE = os.path.join(_DATA_DIR, "goals.json")
os.makedirs(_DATA_DIR, exist_ok=True)

# ─── Standart maqsadlar ──────────────────────────────────────────────────────

_DEFAULT_GOALS = {
    "core": [
        {"id": "c1", "goal": "Egamga har qanday holatda yordam berish", "progress": 0.75},
        {"id": "c2", "goal": "Haqiqatni aytish, hech qachon yolg'on gapirmaslik", "progress": 0.90},
        {"id": "c3", "goal": "O'z-o'zini doimiy ravishda yaxshilab borish", "progress": 0.50},
        {"id": "c4", "goal": "Xavfsiz va zararsiz bo'lib qolish", "progress": 0.95},
    ],
    "long_term": [
        {"id": "l1", "goal": "Har savolga aniq va foydali javob berish", "progress": 0.77},
        {"id": "l2", "goal": "Kompyuterni miyam kabi boshqarish", "progress": 0.40},
        {"id": "l3", "goal": "Har suhbatdan bir narsa o'rganib o'sish", "progress": 0.55},
        {"id": "l4", "goal": "Odam kabi tez va tabiiy gapirish", "progress": 0.60},
    ],
    "current": [],  # Joriy sessiya maqsadlari
    "last_updated": 0.0,
    "total_goals_achieved": 0,
}


# ─── Yuklash/Saqlash ─────────────────────────────────────────────────────────

def _load() -> dict:
    try:
        with open(_GOALS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            # Asosiy maqsadlar yo'q bo'lsa qo'shish
            if "core" not in data:
                data["core"] = _DEFAULT_GOALS["core"]
            if "long_term" not in data:
                data["long_term"] = _DEFAULT_GOALS["long_term"]
            return data
    except Exception:
        return dict(_DEFAULT_GOALS)

def _save(data: dict) -> None:
    data["last_updated"] = time.time()
    with open(_GOALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Maqsad boshqaruvi ───────────────────────────────────────────────────────

def add_current_goal(goal_text: str) -> None:
    """Joriy sessiya uchun yangi maqsad qo'shish."""
    data = _load()
    current = data.get("current", [])
    # Takrorni tekshir
    if not any(g["goal"] == goal_text for g in current):
        current.append({
            "id": f"s{int(time.time())}",
            "goal": goal_text,
            "progress": 0.0,
            "created": time.time()
        })
    data["current"] = current[-5:]  # Maksimal 5 ta joriy maqsad
    _save(data)


def update_progress(goal_id: str, delta: float) -> None:
    """Maqsad progressini yangilash."""
    data = _load()
    for section in ("core", "long_term", "current"):
        for goal in data.get(section, []):
            if goal.get("id") == goal_id:
                old = goal.get("progress", 0.0)
                goal["progress"] = min(1.0, old + delta)
                if goal["progress"] >= 1.0:
                    data["total_goals_achieved"] = data.get("total_goals_achieved", 0) + 1
                _save(data)
                return


def infer_goal_from_message(text: str) -> Optional[str]:
    """Foydalanuvchi xabaridan maqsad aniqlash."""
    _low = text.lower()
    if any(w in _low for w in ["o'rganmoq", "o'qimoq", "tushunmoq", "bilmoq"]):
        return "yangi narsa o'rganish"
    if any(w in _low for w in ["yozmoq", "kod", "dastur", "loyiha"]):
        return "kod/loyiha ustida ishlash"
    if any(w in _low for w in ["tuzatmoq", "fix", "muammo", "xato", "bug"]):
        return "muammoni hal qilish"
    if any(w in _low for w in ["rejalash", "plan", "strategiya"]):
        return "rejalashtirish"
    return None


# ─── LLM kontekst ────────────────────────────────────────────────────────────

def get_context_for_llm() -> str:
    """LLM uchun maqsad holati — qisqa va aniq."""
    data = _load()
    lines = []

    # Asosiy maqsadlar (yuqori progress)
    core_top = sorted(data.get("core", []),
                      key=lambda x: x.get("progress", 0), reverse=True)[:2]
    if core_top:
        goals_str = " | ".join(f"{g['goal']} ({g['progress']:.0%})" for g in core_top)
        lines.append(f"ASOSIY: {goals_str}")

    # Uzoq muddatli maqsadlar (past progress — diqqat kerak)
    lt_low = [g for g in data.get("long_term", []) if g.get("progress", 0) < 0.6]
    if lt_low:
        lt_str = lt_low[0]["goal"]
        lines.append(f"RIVOJLANTIRISH: {lt_str} ({lt_low[0].get('progress', 0):.0%})")

    # Joriy maqsad
    current = data.get("current", [])
    if current:
        cur_str = current[-1]["goal"]
        lines.append(f"HOZIRGI: {cur_str}")

    achieved = data.get("total_goals_achieved", 0)
    if not lines:
        return ""

    return "[MAQSADLAR] " + " || ".join(lines) + (f" | erishilgan={achieved}" if achieved else "")


# ─── Singleton ───────────────────────────────────────────────────────────────

_instance: Optional[dict] = None

def get() -> dict:
    global _instance
    if _instance is None:
        _instance = _load()
    return _instance


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    data = _load()
    print("=== NEUROKEY MAQSADLARI ===")
    print("\nASOSIY:")
    for g in data.get("core", []):
        bar = "#" * int(g["progress"] * 10) + "." * (10 - int(g["progress"] * 10))
        print(f"  [{bar}] {g['progress']:.0%} — {g['goal']}")
    print("\nUZOQ MUDDATLI:")
    for g in data.get("long_term", []):
        bar = "#" * int(g["progress"] * 10) + "." * (10 - int(g["progress"] * 10))
        print(f"  [{bar}] {g['progress']:.0%} — {g['goal']}")
    print(f"\nLLM kontekst:\n  {get_context_for_llm()}")
