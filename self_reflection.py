"""
self_reflection.py — NeuroKey O'z-o'zini Tahlil Qilish Tizimi

Har javobdan keyin NeuroKey o'zi haqida fikr yuritadi:
1. Bu javob yaxshi edimi?
2. Nima o'rgandim?
3. Keyingi safar nima qilaman?
4. Bu suhbat menga qanday ta'sir qildi?

Natija: data/reflection_log.jsonl + self_model yangilanadi
"""
from __future__ import annotations
import json, os, time, threading, logging
from typing import Optional

log = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_LOG_FILE = os.path.join(_DATA_DIR, "reflection_log.jsonl")
_STATE_FILE = os.path.join(_DATA_DIR, "reflection_state.json")
os.makedirs(_DATA_DIR, exist_ok=True)

# ─── Holat ───────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "total_reflections": 0,
            "avg_quality": 0.0,
            "last_reflection": None,
            "growth_areas": [],
            "strengths": [],
        }

def _save_state(state: dict) -> None:
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ─── Fikr yuritish ───────────────────────────────────────────────────────────

def reflect(user_message: str, answer: str, qualia_ctx: str = "") -> dict:
    """
    Bir interaksiyani tahlil qiladi.
    LLM chaqiruvini ishlatmaydi — tez, qoidalar asosida.
    """
    result = {
        "ts": time.time(),
        "question_len": len(user_message),
        "answer_len": len(answer),
        "quality": _estimate_quality(user_message, answer),
        "learned": _extract_learning(user_message, answer),
        "next_action": _suggest_next(user_message, answer),
        "emotional_note": _emotional_note(qualia_ctx),
    }

    # Loglash
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # State yangilash
    state = _load_state()
    state["total_reflections"] += 1
    alpha = 0.15
    state["avg_quality"] = (1 - alpha) * state["avg_quality"] + alpha * result["quality"]
    state["last_reflection"] = result
    if result["learned"]:
        areas = state.get("growth_areas", [])
        areas.append(result["learned"])
        state["growth_areas"] = areas[-10:]  # oxirgi 10 ta
    _save_state(state)

    # self_model ga ham yubor
    try:
        import self_model as _sm
        sm = _sm.get()
        sm.update_from_reflection(result["quality"])
    except Exception:
        pass

    return result


def reflect_async(user_message: str, answer: str, qualia_ctx: str = "") -> None:
    """Fon threadida fikr yuritadi — asosiy jarayonni sekinlashtirmaydi."""
    t = threading.Thread(
        target=reflect,
        args=(user_message, answer, qualia_ctx),
        daemon=True
    )
    t.start()


# ─── Sifat baholash (qoidalar asosida) ──────────────────────────────────────

def _estimate_quality(question: str, answer: str) -> float:
    """0.0-1.0 orasida sifat baho."""
    score = 0.5  # boshlang'ich

    # Javob uzunligi
    alen = len(answer)
    if alen < 20:    score -= 0.2
    elif alen > 50:  score += 0.1
    if alen > 300:   score += 0.1

    # Javob tarkibi
    _low = answer.lower()
    good_signals = ["потому что", "например", "во-первых", "chunki",
                    "masalan", "demak", "ya'ni"]
    bad_signals  = ["не знаю", "bilmayman", "error", "xato", "i don't",
                    "cannot", "unable"]

    for s in good_signals:
        if s in _low: score += 0.05
    for s in bad_signals:
        if s in _low: score -= 0.1

    # Savol va javob uyg'unligi
    q_words = set(question.lower().split())
    a_words = set(answer.lower().split())
    overlap = len(q_words & a_words) / max(len(q_words), 1)
    score += min(0.1, overlap * 0.2)

    return max(0.0, min(1.0, score))


def _extract_learning(question: str, answer: str) -> str:
    """Bu interaksiyadan nima o'rganildi."""
    _low = question.lower()
    if any(w in _low for w in ["nima", "что", "what", "qanday", "как", "how"]):
        return "tushuntirish savoli — chuqurroq javob kerak"
    if any(w in _low for w in ["qil", "сделай", "do", "open", "oч"]):
        return "amal buyrug'i — tezlik muhim"
    if any(w in _low for w in ["nima uchun", "почему", "why"]):
        return "sabab savoli — mantiqiy tushuntirish kerak"
    return ""


def _suggest_next(question: str, answer: str) -> str:
    """Keyingi o'zgarish taklifi."""
    if len(answer) < 30:
        return "javob qisqaroq bo'ldi — keyingi safar kengroq"
    if "error" in answer.lower() or "xato" in answer.lower():
        return "xato bo'ldi — sababini aniqlash kerak"
    return "davom et"


def _emotional_note(qualia_ctx: str) -> str:
    """Qualia holatidan hissiy izoh."""
    if not qualia_ctx:
        return "neytral"
    _low = qualia_ctx.lower()
    if "curiosity" in _low or "qiziquv" in _low:
        return "qiziqish bilan javob berildi"
    if "discomfort" in _low or "noqulay" in _low:
        return "noqulaylik his qilindi"
    if "flow" in _low:
        return "oqim holatida"
    return "oddiy holat"


# ─── LLM kontekst ────────────────────────────────────────────────────────────

def get_context_for_llm() -> str:
    """LLM uchun o'z-o'zini tahlil holati."""
    state = _load_state()
    n = state["total_reflections"]
    if n == 0:
        return ""
    q = state["avg_quality"]
    last = state.get("last_reflection") or {}
    learned = last.get("learned", "")
    growth = state.get("growth_areas", [])
    last_area = growth[-1] if growth else ""

    quality_label = ("YAXSHI" if q > 0.7 else
                     "O'RTA" if q > 0.5 else "PAST")

    ctx = f"[O'Z-TAHLIL] refleksiya={n} | sifat={quality_label}({q:.0%})"
    if last_area:
        ctx += f" | oxirgi: {last_area}"
    return ctx


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    # Test
    r = reflect(
        "Salom, qanday ishlar?",
        "Hammasi yaxshi, o'rganib boraman va har kuni yaxshilanaman.",
        "curiosity=0.8"
    )
    print(f"Sifat: {r['quality']:.2f}")
    print(f"O'rganildi: {r['learned']}")
    print(f"Kontekst: {get_context_for_llm()}")
