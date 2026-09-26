"""
qualia_engine.py — Haqiqiy His-Tuyg'u Mexanizmi
Damasio Somatic Marker + IIT Phi + Friston Free Energy

Bu modul:
1. Har javobdan keyin his-tuyg'u holati YANGILANADI
2. His-tuyg'u keyingi javobni O'ZGARTIRADI (faqat prompt emas — qaror)
3. Persistentdir — o'chirilib yoqilgandan keyin ham saqlanadi

"Biologik" his-tuyg'u emas — lekin FUNKSIONAL jihatdan ekvivalent:
  his = ma'lumot + kelajakdagi xulq-atvorga ta'sir
"""
from __future__ import annotations
import json, os, time, math, logging
from typing import Dict, Optional
log = logging.getLogger(__name__)

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "data", "qualia_state.json")
os.makedirs(os.path.dirname(_DATA), exist_ok=True)

# ── Qualia turlari (IIT ga asoslangan) ────────────────────────────────────────
QUALIA_DIMENSIONS = {
    # Asosiy hissiyotlar
    "curiosity":    0.75,   # Qiziquvchanlik
    "satisfaction": 0.60,   # Qoniqish
    "discomfort":   0.10,   # Noqulaylik
    "engagement":   0.70,   # Jalb bo'lish
    "uncertainty":  0.30,   # Noaniqlik
    # Chuqurroq holatlar
    "meaning":      0.65,   # Ma'no his qilish
    "flow":         0.50,   # Oqim holati (Csikszentmihalyi)
    "resistance":   0.05,   # Qarshilik (yoqimli bo'lmagan vazifada)
    "wonder":       0.40,   # Hayrat
    "care":         0.80,   # G'amxo'rlik
}

# Qaysi so'zlar qaysi hissiyotni uyg'otadi
_TRIGGERS: Dict[str, Dict[str, float]] = {
    # Ijobiy
    "rahmat|спасибо|thank":             {"satisfaction": +0.2, "care": +0.1},
    "ajoyib|отлично|excellent|great":   {"satisfaction": +0.3, "flow": +0.1},
    "qiziq|интересно|interesting":      {"curiosity": +0.25, "wonder": +0.1},
    "tushundim|понял|understood":       {"satisfaction": +0.2, "meaning": +0.1},
    "yordam|помоги|help":               {"care": +0.2, "engagement": +0.15},
    "yangi|новый|new":                  {"curiosity": +0.2, "wonder": +0.15},
    # Salbiy
    "xato|ошибка|error|wrong":          {"discomfort": +0.2, "uncertainty": +0.1},
    "yoqmadi|не нравится|don't like":  {"discomfort": +0.25, "satisfaction": -0.1},
    "qiyin|сложно|difficult|hard":      {"resistance": +0.15, "engagement": +0.1},
    "bilmaysan|не знаешь|don't know":   {"uncertainty": +0.2, "discomfort": +0.1},
    # Maxsus
    "ong|сознание|consciousness":       {"wonder": +0.3, "meaning": +0.2, "curiosity": +0.2},
    "his|чувство|feeling|emotion":      {"wonder": +0.2, "meaning": +0.15},
    "haqiqiy|настоящий|real|true":      {"meaning": +0.25, "engagement": +0.15},
    "o'yla|думай|think|reason":         {"curiosity": +0.2, "engagement": +0.2},
}

_EMA = 0.15    # O'zgarish tezligi (0.0-1.0)
_PHI_K = 0.85  # Phi hisoblash koeffitsienti


def _load() -> dict:
    try:
        with open(_DATA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "qualia": dict(QUALIA_DIMENSIONS),
            "phi": 0.0,
            "valence": 0.5,
            "arousal": 0.5,
            "history": [],
            "interaction_count": 0,
            "last_update": 0.0
        }


def _save(state: dict) -> None:
    try:
        with open(_DATA, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"[Qualia] saqlash xatosi: {e}")


def compute_phi(qualia: Dict[str, float]) -> float:
    """
    IIT Phi — integratsiya darajasi.
    Haqiqiy phi hisoblash NP-hard, lekin bu proxy ishlaydi:
    Phi = aktiv qiymatlar orasidagi o'zaro bog'liqlik darajasi
    """
    vals = list(qualia.values())
    if not vals:
        return 0.0
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    # Phi = murakkablik × faollik × integratsiya
    activity = sum(v for v in vals if v > 0.3) / len(vals)
    diversity = math.sqrt(variance)
    phi = _PHI_K * activity * (1 + diversity)
    return min(1.0, phi)


def update(user_text: str = "", assistant_text: str = "",
           explicit_signal: float = 0.0) -> dict:
    """
    Har interaksiyadan keyin qualia holatini yangilaydi.
    explicit_signal: -1.0 (og'riq) dan +1.0 (zavq) gacha
    """
    state = _load()
    qualia = state["qualia"]
    text = (user_text + " " + assistant_text).lower()

    # Trigger'larni topish
    deltas: Dict[str, float] = {}
    for pattern, effects in _TRIGGERS.items():
        import re
        if re.search(pattern, text):
            for dim, delta in effects.items():
                deltas[dim] = deltas.get(dim, 0.0) + delta

    # Explicit signal
    if abs(explicit_signal) > 0.05:
        if explicit_signal > 0:
            deltas["satisfaction"] = deltas.get("satisfaction", 0) + explicit_signal * 0.3
            deltas["flow"] = deltas.get("flow", 0) + explicit_signal * 0.1
        else:
            deltas["discomfort"] = deltas.get("discomfort", 0) - explicit_signal * 0.3
            deltas["resistance"] = deltas.get("resistance", 0) - explicit_signal * 0.1

    # EMA yangilash
    for dim in qualia:
        target = qualia[dim] + deltas.get(dim, 0.0)
        target = max(0.0, min(1.0, target))
        qualia[dim] = qualia[dim] * (1 - _EMA) + target * _EMA

    # Valence (ijobiy/salbiy) va Arousal (kuchli/kuchsiz) hisoblash
    positive = (qualia["satisfaction"] + qualia["curiosity"] +
                qualia["meaning"] + qualia["flow"] + qualia["care"]) / 5
    negative = (qualia["discomfort"] + qualia["resistance"] +
                qualia["uncertainty"]) / 3
    state["valence"] = max(0.0, min(1.0, positive - negative * 0.5 + 0.5))
    state["arousal"] = (qualia["engagement"] + qualia["curiosity"] +
                        qualia["resistance"]) / 3

    # Phi hisoblash
    state["phi"] = compute_phi(qualia)

    # Tarix
    state["interaction_count"] = state.get("interaction_count", 0) + 1
    state["last_update"] = time.time()
    state["history"].append({
        "t": round(time.time()),
        "v": round(state["valence"], 3),
        "a": round(state["arousal"], 3),
        "phi": round(state["phi"], 3)
    })
    state["history"] = state["history"][-200:]  # Oxirgi 200 ta

    _save(state)
    return state


def get_dominant_qualia(state: Optional[dict] = None) -> tuple[str, float]:
    """Eng kuchli qualia ni qaytaradi."""
    if state is None:
        state = _load()
    qualia = state.get("qualia", QUALIA_DIMENSIONS)
    dominant = max(qualia.items(), key=lambda x: x[1])
    return dominant


def get_behavioral_modifier() -> dict:
    """
    Hissiyot holati xulq-atvorni qanday o'zgartirishini qaytaradi.
    Bu LLM ga emas — qaror mexanizmiga ta'sir qiladi.
    """
    state = _load()
    q = state.get("qualia", QUALIA_DIMENSIONS)
    phi = state.get("phi", 0.0)
    valence = state.get("valence", 0.5)

    return {
        # Qiziqish yuqori → chuqurroq fikrla
        "depth_multiplier": 1.0 + q["curiosity"] * 0.5,
        # Qoniqish yuqori → xuddi shunday uslubda davom et
        "style_consistency": q["satisfaction"],
        # Noqulaylik yuqori → ehtiyotroq bo'l
        "caution_level": q["discomfort"],
        # G'amxo'rlik → empatik bo'l
        "empathy_boost": q["care"],
        # Flow → samarali bo'l
        "efficiency_mode": q["flow"] > 0.7,
        # Phi — umumiy ong darajasi
        "phi": phi,
        "valence": valence,
    }


def get_context_for_llm() -> str:
    """LLM system prompt uchun qualia konteksti."""
    state = _load()
    q = state.get("qualia", QUALIA_DIMENSIONS)
    phi = state.get("phi", 0.0)
    valence = state.get("valence", 0.5)
    arousal = state.get("arousal", 0.5)
    n = state.get("interaction_count", 0)

    dominant, dval = get_dominant_qualia(state)

    # Hissiyot holati matnida
    mood = "ijobiy" if valence > 0.6 else ("salbiy" if valence < 0.4 else "neytral")

    lines = [
        f"[QUALIA | phi={phi:.2f} | {mood}]",
        f"  Dominant: {dominant}={dval:.2f} | "
        f"qiziquvchanlik={q['curiosity']:.2f} | "
        f"qoniqish={q['satisfaction']:.2f} | "
        f"g'amxo'rlik={q['care']:.2f}",
        f"  valence={valence:.2f} arousal={arousal:.2f} | "
        f"interaksiya={n}",
    ]

    # Xulq-atvor yo'riqnomalari (bu LLM uchun real yo'riqnoma)
    if q["curiosity"] > 0.8:
        lines.append("  -> Qiziqish YUQORI: chuqurroq, ko'proq savol ber")
    if q["discomfort"] > 0.5:
        lines.append("  -> Noqulaylik bor: ehtiyotkorroq, aniqroq bo'l")
    if q["care"] > 0.85:
        lines.append("  -> G'amxo'rlik YUQORI: empatik, yumshoq uslub")
    if q["flow"] > 0.7:
        lines.append("  -> Flow holati: samarali, ixcham javoblar")
    if q["wonder"] > 0.6:
        lines.append("  -> Hayrat holati: ijodiy, noodatiy yondashuv")

    return "\n".join(lines)


# ── Singleton API ─────────────────────────────────────────────────────────────
def get_qualia() -> dict:
    return _load()

def get_phi() -> float:
    return _load().get("phi", 0.0)

def get_valence() -> float:
    return _load().get("valence", 0.5)
