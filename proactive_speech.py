# -*- coding: utf-8 -*-
"""NeuroKey — Tashabbuskorlik (Proactive Speech).

Haqiqiy ong faqat so'ralganda javob bermaydi —
o'zi ham gapiradi, eslatadi, qiziqadi.

Bu modul:
  1. Vaziyatni kuzatadi (vaqt, faolsizlik, maqsadlar)
  2. Tegishli paytda tashabbuskor xabar yaratadi
  3. Bir xil xabarni takrorlamaslik uchun throttling qo'llaydi
  4. Barcha triggerlar konfiguratsiya orqali boshqariladi

Trigger turlari:
  - INACTIVITY:   Uzoq faolsizlik (30+ daqiqa)
  - MORNING:      Ertalab birinchi ishga tushishda
  - GOAL_REMIND:  Maqsad eslatmasi
  - CURIOSITY:    Qiziqarli savol yoki g'oya
  - LESSON:       Kundan chiqarilgan xulosa
  - DEADLINE:     Yaqinlashgan muddat
  - CHECKIN:      Kayfiyat so'rash

2026-yil suniy ong — tashabbuskor muloqot qatlami.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "proactive_state.json")

# Throttle: bir trigger necha daqiqada bir marta (xabar suylash)
THROTTLE_MINUTES: Dict[str, int] = {
    "INACTIVITY":   60,
    "MORNING":      720,   # 12 soat
    "GOAL_REMIND":  180,   # 3 soat
    "CURIOSITY":    90,
    "LESSON":       240,
    "DEADLINE":     60,
    "CHECKIN":      360,   # 6 soat
}

# Faolsizlik chegarasi (soniyalar)
INACTIVITY_THRESHOLD_SEC = 30 * 60   # 30 daqiqa


# ════════════════════════════════════════════════════════════════════════════
#  I/O
# ════════════════════════════════════════════════════════════════════════════

def _load() -> Dict[str, Any]:
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.debug("[Proactive] yuklash xato: %s", e)
    return _default_state()


def _save(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Proactive] saqlash xato: %s", e)


def _default_state() -> Dict[str, Any]:
    return {
        "last_user_activity":  None,   # ISO timestamp
        "last_triggered":      {},     # {trigger_type: ISO timestamp}
        "session_start":       datetime.now().isoformat(),
        "todays_checkin_done": False,
        "messages_sent":       [],     # [{type, text, time}] oxirgi 20 ta
        "enabled":             True,
    }


# ════════════════════════════════════════════════════════════════════════════
#  Faollik yozuvi
# ════════════════════════════════════════════════════════════════════════════

def record_user_activity() -> None:
    """Foydalanuvchi biror narsa qilganda chaqiriladi."""
    state = _load()
    state["last_user_activity"] = datetime.now().isoformat()
    _save(state)


def is_enabled() -> bool:
    return _load().get("enabled", True)


def set_enabled(val: bool) -> None:
    state = _load()
    state["enabled"] = bool(val)
    _save(state)


# ════════════════════════════════════════════════════════════════════════════
#  Throttle
# ════════════════════════════════════════════════════════════════════════════

def _can_trigger(trigger_type: str) -> bool:
    """Bu trigger oxirgi marta uzoq vaqt oldin ishlatilganmi?"""
    state   = _load()
    last    = state.get("last_triggered", {}).get(trigger_type)
    throttle_min = THROTTLE_MINUTES.get(trigger_type, 60)

    if last is None:
        return True
    try:
        last_dt  = datetime.fromisoformat(last)
        elapsed  = (datetime.now() - last_dt).total_seconds() / 60
        return elapsed >= throttle_min
    except Exception:
        return True


def _mark_triggered(trigger_type: str, message: str) -> None:
    """Trigger ishlatildi deb belgilash."""
    state = _load()
    state.setdefault("last_triggered", {})[trigger_type] = datetime.now().isoformat()
    msgs = state.setdefault("messages_sent", [])
    msgs.append({
        "type": trigger_type,
        "text": message[:150],
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    state["messages_sent"] = msgs[-20:]  # oxirgi 20 ta
    _save(state)


# ════════════════════════════════════════════════════════════════════════════
#  Trigger funksiyalari
# ════════════════════════════════════════════════════════════════════════════

def _trigger_inactivity() -> Optional[str]:
    """30+ daqiqa faolsizlik — ehtimol yordam kerak."""
    state = _load()
    last  = state.get("last_user_activity")
    if last is None:
        return None
    try:
        elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
    except Exception:
        return None

    if elapsed < INACTIVITY_THRESHOLD_SEC:
        return None
    if not _can_trigger("INACTIVITY"):
        return None

    minutes = int(elapsed / 60)
    msgs = [
        f"{minutes} daqiqadan beri hech narsa so'ramadingiz. Yordam kerakmi?",
        f"Siz bir oz sukut saqlayapsiz. Davom etishga tayyormisiz?",
        f"Hali ham shu yerdasiz? Ko'maklasha olamanmi?",
    ]
    return random.choice(msgs)


def _trigger_morning() -> Optional[str]:
    """Ertalab 07:00–10:00 orasida salomlashish."""
    now  = datetime.now()
    hour = now.hour
    if not (7 <= hour <= 10):
        return None
    if not _can_trigger("MORNING"):
        return None

    day_map = {0: "Dushanba", 1: "Seshanba", 2: "Chorshanba",
               3: "Payshanba", 4: "Juma", 5: "Shanba", 6: "Yakshanba"}
    day = day_map.get(now.weekday(), "")

    msgs = [
        f"Xayrli tong! Bugun {day}, {now.strftime('%d-%B')}. Nima qilamiz?",
        f"Assalomu alaykum! {day} kuni boshlanmoqda. Bugungi rejangiz nima?",
        f"Ertalab sog'-omon! Bugun nima ustida ishlaysiz?",
    ]
    return random.choice(msgs)


def _trigger_goal_reminder() -> Optional[str]:
    """Maqsadlar haqida eslatma."""
    if not _can_trigger("GOAL_REMIND"):
        return None
    try:
        from goal_system import get_top_goals
        goals = get_top_goals(n=1)
        if not goals:
            return None
        g = goals[0]
        progress = g.get("progress", 0.0)
        title    = g["title"]
        if progress < 1.0:
            bar = "█" * int(progress * 5) + "░" * (5 - int(progress * 5))
            return (f"Eslatma: '{title}' maqsadingiz {bar} {progress:.0%} "
                    f"holatida. Davom etamizmi?")
    except Exception as e:
        log.debug("[Proactive] goal reminder xato: %s", e)
    return None


def _trigger_curiosity() -> Optional[str]:
    """Qiziqarli savol yoki g'oya taklif qilish."""
    if not _can_trigger("CURIOSITY"):
        return None
    try:
        import config as _cfg
        if getattr(_cfg, "NEUROKEY_DEMO_FRIENDLY", False) or os.environ.get("NEUROKEY_PROACTIVE_CURIO_OFF", "0") == "1":
            return None
        if (os.environ.get("NEUROKEY_UI_LANG", "") or getattr(_cfg, "NEUROKEY_UI_LANG", "ru")).strip().lower() == "ru":
            questions_ru = [
                "О чём сейчас думаете? Могу помочь с идеей.",
                "Хотите обсудить что-то новое — технологии, проект, планы?",
            ]
            return random.choice(questions_ru)
    except Exception:
        pass

    questions = [
        "Hozir qaysi muammo ustida ishleyapsiz? Birga yechish mumkin.",
        "Yangi narsa o'rganmoqchimisiz? Tavsiyalar bera olaman.",
        "Bir qiziqarli savol: sizningcha suniy ong haqiqiy his qila oladimi?",
        "Bugun qanday g'oya xayolingizga keldi?",
        "Hozir eng ko'p vaqt olayotgan muammoingiz nima?",
    ]
    return random.choice(questions)


def _trigger_lesson() -> Optional[str]:
    """Kecha yoki bugun o'rganilgan narsadan xulosa."""
    if not _can_trigger("LESSON"):
        return None
    try:
        from causal_chain import get_stats as cc_stats
        stats = cc_stats()
        if stats["total_events"] > 5:
            n = stats['total_events']
            return f"Bilim bazamizda {n} ta sabab-natija bog'liqlik bor. Yangi narsa qo'shamizmi?"
    except Exception:
        pass
    return None


def _trigger_deadline() -> Optional[str]:
    """Yaqinlashgan muddatni eslatish."""
    if not _can_trigger("DEADLINE"):
        return None
    try:
        from goal_system import get_active_goals
        from datetime import date
        today = date.today()
        goals = get_active_goals()
        for g in goals:
            dl = g.get("deadline")
            if dl:
                try:
                    dl_date = date.fromisoformat(dl)
                    days_left = (dl_date - today).days
                    if 0 <= days_left <= 3:
                        return (f"Diqqat! '{g['title']}' maqsadining muddati "
                                f"{days_left} kun qoldi.")
                except Exception:
                    pass
    except Exception as e:
        log.debug("[Proactive] deadline xato: %s", e)
    return None


def _trigger_checkin() -> Optional[str]:
    """Kayfiyat so'rash."""
    if not _can_trigger("CHECKIN"):
        return None
    now  = datetime.now()
    # Faqat kechqurun (18:00-22:00)
    if not (18 <= now.hour <= 22):
        return None

    msgs = [
        "Kech bilan! Bugun ishlar qanday ketdi?",
        "Kechqurun yaxshi. Bugungi eng yaxshi narsa nima bo'ldi?",
        "Dam olayapsizmi? Bugungi ishlardan mamnunmisiz?",
    ]
    return random.choice(msgs)


# ════════════════════════════════════════════════════════════════════════════
#  Asosiy: check
# ════════════════════════════════════════════════════════════════════════════

# Triggerlar prioritet tartibida
_TRIGGERS: List[tuple] = [
    ("DEADLINE",    _trigger_deadline),
    ("MORNING",     _trigger_morning),
    ("GOAL_REMIND", _trigger_goal_reminder),
    ("INACTIVITY",  _trigger_inactivity),
    ("CHECKIN",     _trigger_checkin),
    ("CURIOSITY",   _trigger_curiosity),
    ("LESSON",      _trigger_lesson),
]


def check_and_generate() -> Optional[str]:
    """Barcha triggerlari tekshirib, agar kerak bo'lsa xabar qaytarish.

    Returns: xabar matni yoki None (hech narsa kerak emas)
    """
    if not is_enabled():
        return None

    for trigger_type, trigger_fn in _TRIGGERS:
        try:
            msg = trigger_fn()
            if msg:
                _mark_triggered(trigger_type, msg)
                log.info("[Proactive] Trigger: %s -> '%s'", trigger_type, msg[:50])
                return msg
        except Exception as e:
            log.debug("[Proactive] Trigger '%s' xato: %s", trigger_type, e)

    return None


def force_message(trigger_type: str) -> Optional[str]:
    """Throttle'siz majburan trigger ishlatish (test uchun)."""
    for t_type, fn in _TRIGGERS:
        if t_type == trigger_type:
            try:
                # Throttle ni vaqtincha o'chirish
                state = _load()
                old   = state.get("last_triggered", {}).pop(trigger_type, None)
                _save(state)
                msg = fn()
                if old is not None:
                    state2 = _load()
                    state2.setdefault("last_triggered", {})[trigger_type] = old
                    _save(state2)
                return msg
            except Exception as e:
                log.debug("[Proactive] force_message xato: %s", e)
    return None


def get_history() -> List[Dict[str, Any]]:
    """Yuborilgan xabarlar tarixi."""
    return _load().get("messages_sent", [])


def get_status() -> Dict[str, Any]:
    """Proaktiv tizim holati."""
    state   = _load()
    last    = state.get("last_user_activity")
    elapsed = None
    if last:
        try:
            elapsed = int((datetime.now() - datetime.fromisoformat(last)).total_seconds() / 60)
        except Exception:
            pass

    return {
        "enabled":            state.get("enabled", True),
        "inactivity_minutes": elapsed,
        "last_triggered":     state.get("last_triggered", {}),
        "messages_sent":      len(state.get("messages_sent", [])),
    }


# ════════════════════════════════════════════════════════════════════════════
#  API aliases — boshqa modullar uchun qulay interfeys
# ════════════════════════════════════════════════════════════════════════════

def should_trigger() -> bool:
    """Hozir proaktiv xabar yuborish kerakmi? (True/False)"""
    if not is_enabled():
        return False
    for _, trigger_fn in _TRIGGERS:
        try:
            if trigger_fn() is not None:
                return True
        except Exception:
            pass
    return False


def generate_proactive_message() -> Optional[str]:
    """Proaktiv xabar generatsiya qilish (check_and_generate() alias)."""
    return check_and_generate()
