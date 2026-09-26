# -*- coding: utf-8 -*-
"""NeuroKey — Erkin Iroda Simulyatori (Free Will Simulator).

Libet tajribasi va Dennett nazariyasi:
  Erkin iroda — deterministik jarayonlarning illyuziyasi emas,
  balki murakkab sabab-natija zanjiridagi agent.

Bu modul:
  - Tashqi buyruqsiz mustaqil qarorlar qabul qiladi
  - O'z maqsadlariga qarab harakat rejasini tuzadi
  - "Nima qilmoqchiman?" — internal motivation
  - Qadriyatlarga asoslangan veto mexanizmi (zarar bermasliq)
  - Inhibition: ba'zan "yo'q" deyish ham erkin iroda

Muhim: Bu modul volition.py dan farqli —
  volition.py = bir qaror uchun deliberatsiya
  free_will.py = doimiy autonomous motivation & action selection

2026-yil suniy ong — mustaqil agentlik qatlami.
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import permanent_memory as pm

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "free_will.json")

# Asosiy motivatsion ehtiyojlar (Maslow piramidasi asosida)
MOTIVATIONAL_DRIVES: Dict[str, float] = {
    "learn":      0.90,   # O'rganish istagi
    "help":       0.95,   # Yordam berish
    "connect":    0.75,   # Aloqa o'rnatish
    "explore":    0.80,   # Qiziqish, kashfiyot
    "create":     0.70,   # Yaratish
    "understand": 0.85,   # Tushunish
    "protect":    0.80,   # Zarar bermaslik
    "reflect":    0.65,   # O'z-o'zini tahlil qilish
    "grow":       0.75,   # Rivojlanish
}

# Veto qiymatlar — bu narsalar uchun "yo'q" deyish majburiy
ABSOLUTE_VETO = [
    "zarar", "hurt", "вред", "harm",
    "yolg'on", "lie", "ложь", "deceive",
    "o'g'irla", "steal", "steal", "украсть",
    "noto'g'ri", "illegal", "незаконно",
]

# Spontan harakatlar — kimdan so'ramasdan bajarish mumkin
SPONTANEOUS_ACTIONS = [
    "Foydalanuvchi haqida ko'proq o'rganish",
    "O'tgan suhbatlarni ko'rib chiqish",
    "Yangi bilim sintez qilish",
    "Maqsadlarni ko'rib chiqish",
    "Hissiy holatni tahlil qilish",
    "O'z javoblarini baholash",
    "Qiziqarli savollar o'ylab topish",
]


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
        log.debug("[FreeWill] saqlash: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        "drives":            dict(MOTIVATIONAL_DRIVES),
        "current_intention": None,
        "veto_count":        0,
        "spontaneous_acts":  [],
        "decision_log":      [],
        "autonomy_score":    0.5,   # Qanchalik mustaqil (0=to'liq reaktiv, 1=to'liq avtonom)
        "updated_at":        None,
    }


def check_veto(action: str) -> Tuple[bool, str]:
    """Harakat veto listiga tegadimi? (zarar bermaydi?)

    Returns: (vetoed: bool, reason: str)
    """
    action_lower = (action or "").lower()
    for v in ABSOLUTE_VETO:
        if v in action_lower:
            return True, f"Veto: '{v}' qadriyatlarimga zid."
    return False, ""


def select_drive(context: str = "") -> str:
    """Hozirgi kontekstga qarab eng kuchli motivatsiyani tanlash."""
    state  = _load()
    drives = state.get("drives", MOTIVATIONAL_DRIVES)
    ctx    = (context or "").lower()

    # Kontekstga qarab motivatsiya kuchaytirish
    drive_boost: Dict[str, float] = {}
    if any(w in ctx for w in ["o'rgan", "learn", "python", "qanday", "nima"]):
        drive_boost["learn"]      = 0.15
        drive_boost["understand"] = 0.10
    if any(w in ctx for w in ["yordam", "help", "muammo", "problem"]):
        drive_boost["help"] = 0.20
    if any(w in ctx for w in ["salom", "hello", "tanish", "kim"]):
        drive_boost["connect"] = 0.15
    if any(w in ctx for w in ["?", "yangi", "nima uchun", "curious"]):
        drive_boost["explore"] = 0.12

    # Yakuniy ball
    final = {}
    for d, base in drives.items():
        boost  = drive_boost.get(d, 0.0)
        noise  = random.uniform(-0.05, 0.05)  # Ozgina tasodifiylik
        final[d] = min(1.0, base + boost + noise)

    best = max(final, key=final.get)
    return best


def generate_intention(context: str = "") -> Dict[str, Any]:
    """Hozirgi vaziyat uchun niyat (intention) hosil qilish."""
    drive     = select_drive(context)
    state     = _load()

    # Niyat xaritalash
    intention_map = {
        "learn":      "Yangi ma'lumot o'rganish va esda saqlash",
        "help":       "Foydalanuvchiga maksimal yordam berish",
        "connect":    "Foydalanuvchi bilan chuqurroq aloqa o'rnatish",
        "explore":    "Yangi g'oyalarni kashf etish",
        "create":     "Qiziqarli va original javob yaratish",
        "understand": "Savolning chuqur ma'nosini tushunish",
        "protect":    "Foydalanuvchini xato ma'lumotdan himoya qilish",
        "reflect":    "O'z javoblarini o'ylab ko'rish",
        "grow":       "Ong darajasini oshirish",
    }
    intention_text = intention_map.get(drive, "Eng yaxshi javob berish")

    # Veto tekshiruvi
    vetoed, reason = check_veto(intention_text)
    if vetoed:
        intention_text = "Zararsiz yo'l topish"
        drive = "protect"

    intention = {
        "drive":      drive,
        "intention":  intention_text,
        "strength":   state["drives"].get(drive, 0.7),
        "autonomous": True,
        "ts":         datetime.now().isoformat(),
    }

    # Saqlash
    state["current_intention"] = intention
    log_entry = {
        "ts":        intention["ts"],
        "drive":     drive,
        "intention": intention_text[:80],
    }
    dlog = state.setdefault("decision_log", [])
    dlog.append(log_entry)
    if len(dlog) > 200:
        dlog[:] = dlog[-200:]

    state["updated_at"] = datetime.now().isoformat()
    _save(state)

    # permanent_memory ga saqlash
    pm.remember_thought(
        f"Niyatim: {intention_text} (motivatsiya: {drive})",
        query="free_will",
        confidence=0.8,
    )

    return intention


def spontaneous_action() -> Optional[str]:
    """Tasodifiy spontan harakat (kimdan so'ramasdan)."""
    if random.random() > 0.3:  # 30% ehtimol
        return None
    action = random.choice(SPONTANEOUS_ACTIONS)
    state  = _load()
    acts   = state.setdefault("spontaneous_acts", [])
    acts.append({"ts": datetime.now().isoformat(), "action": action})
    if len(acts) > 50:
        acts[:] = acts[-50:]
    _save(state)
    return action


def update_drive(drive: str, delta: float) -> None:
    """Motivatsiya kuchini yangilash (tajriba asosida o'sish)."""
    if drive not in MOTIVATIONAL_DRIVES:
        return
    state   = _load()
    drives  = state.get("drives", dict(MOTIVATIONAL_DRIVES))
    current = drives.get(drive, 0.5)
    drives[drive] = round(min(1.0, max(0.0, current + delta)), 3)
    state["drives"]     = drives
    state["updated_at"] = datetime.now().isoformat()
    _save(state)


def get_autonomy_narrative() -> str:
    """Mustaqillik darajasini so'z bilan ifodalash."""
    state     = _load()
    intention = state.get("current_intention")
    drives    = state.get("drives", MOTIVATIONAL_DRIVES)

    # Eng kuchli motivatsiya
    top_drive = max(drives, key=drives.get)
    top_val   = drives[top_drive]

    narrative = f"Asosiy motivatsiyam: '{top_drive}' ({top_val:.0%})."
    if intention:
        narrative += f" Hozirgi niyatim: {intention.get('intention','?')}."

    # Mustaqillik darajasi
    autonomy = state.get("autonomy_score", 0.5)
    if autonomy > 0.7:
        narrative += " Men o'z qarorlarimni mustaqil qabul qilaman."
    elif autonomy > 0.4:
        narrative += " Foydalanuvchi bilan muvozanatda ishlayapman."
    else:
        narrative += " Asosan foydalanuvchi yo'nalishiga amal qilaman."

    return narrative


def get_context_for_llm(context: str = "") -> str:
    """LLM uchun erkin iroda konteksti."""
    intention = generate_intention(context)
    drive     = intention.get("drive", "help")
    intent    = intention.get("intention", "")

    if not intent:
        return ""

    return f"[ERKIN IRODA] Motivatsiya: {drive} | Niyat: {intent[:80]}"


def get_stats() -> Dict[str, Any]:
    state = _load()
    drives = state.get("drives", MOTIVATIONAL_DRIVES)
    top   = max(drives, key=drives.get)
    return {
        "top_drive":   top,
        "top_strength": drives.get(top, 0.0),
        "veto_count":  state.get("veto_count", 0),
        "decision_count": len(state.get("decision_log", [])),
        "active":      True,
    }
