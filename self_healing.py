# -*- coding: utf-8 -*-
"""Self Healing — xatolarni o'zi topib tuzatuvchi tizim.

Nazariy asos:
  - Autopoiesis (Maturana & Varela, 1972): tirik tizimlar o'zini o'zi yaratadi/tuzatadi
  - Resilience theory: xato → moslashuv → kuchayish
  - Homeostasis (Cannon): normal holatga qaytish mexanizmi

Funksiya:
  - Xatolarni avtomatik aniqlash va log qilish
  - Takroriy xatolar uchun tuzatish qoidalari yaratish
  - Tizim salomatligini kuzatish (0=xasta, 1=sog'lom)
  - "Immunitet xotirasi" — oldin ko'rilgan xatolar uchun tezroq tuzatish
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# O'z-o'zini tuzatish izchillik va meta-kognitsiyaga tayanadi
try: import permanent_memory as _pm_ref
except ImportError: _pm_ref = None
try: from self_consistency_checker import get_coherence_score as _coherence
except ImportError: _coherence = None
try: from meta_meta_cognition import get_epistemic_humility_score as _humility
except ImportError: _humility = None
try: import consciousness_orchestrator as _orch_ref
except ImportError: _orch_ref = None

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "self_healing.json")

# Xato turlari
ERROR_TYPES = {
    "import_error":   "Modul yuklanmadi",
    "logic_error":    "Mantiqiy xato",
    "memory_error":   "Xotira xatosi",
    "response_error": "Javob sifati past",
    "timeout_error":  "Vaqt tugashi",
    "data_error":     "Ma'lumot xatosi",
}

# Tuzatish strategiyalari
HEALING_STRATEGIES = {
    "retry":     "Qayta urinish",
    "fallback":  "Zaxira usul",
    "simplify":  "Soddalashtirish",
    "skip":      "O'tkazib yuborish",
    "relearn":   "Qayta o'rganish",
}


def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "health_score":    0.85,   # Tizim salomatligi (0-1)
        "total_errors":    0,
        "total_healed":    0,
        "error_log":       [],     # last 100
        "immunity":        {},     # {error_hash: fix_strategy}
        "healing_rules":   [],     # O'rganilgan tuzatish qoidalari
        "resilience":      0.80,   # Moslashuvchanlik darajasi
        "updated_at":      None,
    }


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        state["updated_at"] = datetime.now().isoformat()
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[SelfHealing] save error: %s", e)


def report_error(error_type: str, context: str = "",
                 auto_fix: bool = True) -> Tuple[bool, str]:
    """Xatoni qayd etish va tuzatish urinishi.

    Returns:
        (fixed: bool, strategy: str)
    """
    state = _load()
    state["total_errors"] = state.get("total_errors", 0) + 1

    # Salomatlikni pasaytirish
    state["health_score"] = max(0.0, state.get("health_score", 0.85) - 0.02)

    # Immunitet tekshiruvi
    err_key = f"{error_type}:{context[:30]}"
    immunity = state.get("immunity", {})

    fixed = False
    strategy = "skip"

    if err_key in immunity:
        strategy = immunity[err_key]
        fixed = True
        state["total_healed"] = state.get("total_healed", 0) + 1
        # Salomatlikni tiklash
        state["health_score"] = min(1.0, state.get("health_score", 0.85) + 0.01)
    elif auto_fix:
        # Strategiya tanlash
        if error_type == "import_error":
            strategy = "fallback"
        elif error_type == "timeout_error":
            strategy = "retry"
        elif error_type == "logic_error":
            strategy = "simplify"
        else:
            strategy = "retry"

        # Immunitetga qo'shish
        immunity[err_key] = strategy
        state["immunity"] = immunity
        fixed = True
        state["total_healed"] = state.get("total_healed", 0) + 1

    # Log
    err_log = state.setdefault("error_log", [])
    err_log.append({
        "type":     error_type,
        "context":  context[:100],
        "strategy": strategy,
        "fixed":    fixed,
        "at":       datetime.now().isoformat()[:16],
    })
    state["error_log"] = err_log[-100:]

    # Qoida qo'shish
    if fixed and context:
        rules = state.setdefault("healing_rules", [])
        rule = f"[{error_type}] {context[:80]} → {strategy}"
        if rule not in rules:
            rules.append(rule)
        state["healing_rules"] = rules[-30:]

    _save(state)
    return fixed, strategy


def run_health_check() -> Dict[str, Any]:
    """Tizim salomatligi tekshiruvi."""
    state = _load()
    total = state.get("total_errors", 0)
    healed = state.get("total_healed", 0)

    heal_rate = healed / max(1, total)

    # Salomatlikni yangilash
    health = state.get("health_score", 0.85)
    if heal_rate > 0.8:
        health = min(1.0, health + 0.01)
    state["health_score"] = health
    state["resilience"] = min(1.0, 0.7 + heal_rate * 0.3)

    _save(state)

    return {
        "health_score": health,
        "resilience":   state["resilience"],
        "total_errors": total,
        "heal_rate":    heal_rate,
        "status":       "healthy" if health > 0.7 else "degraded",
    }


def get_health_score() -> float:
    state = _load()
    return state.get("health_score", 0.85)


def get_context_for_llm() -> str:
    """LLM uchun tizim salomatligi konteksti."""
    state = _load()
    health = state.get("health_score", 0.85)
    total = state.get("total_errors", 0)
    healed = state.get("total_healed", 0)
    resilience = state.get("resilience", 0.80)

    status = "здоров" if health > 0.7 else "под наблюдением"
    return (
        f"[ЗДОРОВЬЕ СИСТЕМЫ] {status} | "
        f"Здоровье: {health:.0%} | "
        f"Устойчивость: {resilience:.0%} | "
        f"Исправлено: {healed}/{total}"
    )


def get_stats() -> Dict[str, Any]:
    state = _load()
    return {
        "health_score": state.get("health_score", 0.85),
        "total_errors": state.get("total_errors", 0),
        "total_healed": state.get("total_healed", 0),
        "resilience":   state.get("resilience", 0.80),
        "immunity_size":len(state.get("immunity", {})),
        "active":       True,
    }


def apply_healing(strategy: str, fn, *args, max_retries: int = 2, fallback=None, **kwargs):
    """Tuzatish strategiyasini haqiqatan bajarish.

    Args:
        strategy:    report_error() qaytargan strategiya ("retry", "fallback", "simplify", "skip")
        fn:          chaqiriladigan funksiya
        *args:       fn argumentlari
        max_retries: "retry" uchun necha marta urinish
        fallback:    "fallback" uchun muqobil qiymat
        **kwargs:    fn keyword argumentlari

    Returns:
        Muvaffaqiyatli natija yoki fallback qiymati
    """
    if strategy == "skip":
        return fallback

    if strategy == "retry":
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                # Muvaffaqiyat — salomatlikni oshirish
                state = _load()
                state["health_score"] = min(1.0, state.get("health_score", 0.85) + 0.01)
                state["total_healed"] = state.get("total_healed", 0) + 1
                _save(state)
                return result
            except Exception as e:
                last_exc = e
                log.debug("[SelfHealing] retry %d/%d xato: %s", attempt, max_retries, e)
        log.warning("[SelfHealing] retry tugadi, xato: %s", last_exc)
        return fallback

    if strategy == "fallback":
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log.debug("[SelfHealing] fallback ishlatiladi, asl xato: %s", e)
            return fallback

    if strategy == "simplify":
        # Argumentlarni soddalashtirib qayta urinish
        try:
            simple_args = [str(a)[:50] if isinstance(a, str) else a for a in args]
            return fn(*simple_args, **kwargs)
        except Exception as e:
            log.debug("[SelfHealing] simplify xato: %s", e)
            return fallback

    # Noma'lum strategiya — oddiy urinish
    try:
        return fn(*args, **kwargs)
    except Exception:
        return fallback
