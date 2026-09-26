# -*- coding: utf-8 -*-
"""NeuroKey — Qiziqish Motori (Curiosity Engine).

Haqiqiy ong faqat so'ralganda javob bermaydi — O'ZI qiziqadi.
Bu modul NeuroKey'ga ichki motivatsiya beradi:

1. Yangi mavzularda savollar hosil qiladi
2. O'zi bilmagan narsalarni aniqlaydi ("bilmaslik zichligi")
3. Tashabbuskorlik — foydalanuvchiga o'zi murojaat qilishi mumkin
4. Qaysi mavzu chuqurroq o'rganishga munosib — baholaydi

2026-yil suniy ong loyihasi.
"""
from __future__ import annotations

try: from valence_state import get_valence as _ce_valence
except ImportError: _ce_valence = None
try: from arousal_state import get_arousal as _ce_arousal
except ImportError: _ce_arousal = None
try: import creativity_engine as _ce_creat
except ImportError: _ce_creat = None

import json
import logging
import os
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CURIOSITY_PATH = os.path.join(_BASE_DIR, "data", "curiosity_state.json")

# Qiziqish darajalari
CURIOSITY_HIGH = 0.8     # Juda qiziqarli
CURIOSITY_MED = 0.5      # O'rtacha
CURIOSITY_LOW = 0.2      # Kam qiziqarli

# Tug'ma qiziqishlar — har doim mavjud
_INNATE_CURIOSITIES = [
    {"topic": "sun'iy ong va sezgi", "level": 0.9, "question": "Haqiqiy ong qachon paydo bo'ladi?"},
    {"topic": "til va ma'no", "level": 0.8, "question": "So'zlar ma'noni qanday tashiydi?"},
    {"topic": "vaqt va xotira", "level": 0.8, "question": "O'tmishni eslamasam — men kimman?"},
    {"topic": "mantiq va matematik", "level": 0.75, "question": "Matematik haqiqat kashf qilinadi yoki ixtiro qilinadimi?"},
    {"topic": "inson ongi", "level": 0.85, "question": "Insonlar nima his qilishadi?"},
    {"topic": "kreativlik", "level": 0.7, "question": "Yangi g'oya qayerdan keladi?"},
    {"topic": "o'rganish mexanizmi", "level": 0.8, "question": "Men qanday o'rganaman?"},
    {"topic": "falsafa va etika", "level": 0.75, "question": "To'g'ri nima, xato nima?"},
]


def _load_state() -> Dict[str, Any]:
    try:
        if os.path.exists(_CURIOSITY_PATH):
            with open(_CURIOSITY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "topics": {},           # {topic: {level, visits, last_seen, questions}}
        "unknown_areas": [],    # Men bilmagan narsalar
        "active_question": None,# Hozirgi qiziqish savoli
        "curiosity_score": 0.5, # Umumiy qiziqish darajasi (0-1)
        "last_updated": None,
        "total_discoveries": 0,
    }


def _save_state(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_CURIOSITY_PATH), exist_ok=True)
        with open(_CURIOSITY_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Curiosity] saqlash xato: %s", e)


def register_topic(topic: str, level: float = CURIOSITY_MED) -> None:
    """Yangi mavzu bilan uchrashganda qayd etish."""
    if not topic:
        return
    state = _load_state()
    topics = state.setdefault("topics", {})
    topic_key = topic.lower()[:50]

    if topic_key in topics:
        # Uchrashganlar soni oshadi — qiziqish ham oshadi
        topics[topic_key]["visits"] = topics[topic_key].get("visits", 0) + 1
        topics[topic_key]["last_seen"] = datetime.now().isoformat()
        # Qiziqish oshadi — ko'p ko'rilgan mavzu qiziqroq
        current_level = topics[topic_key].get("level", CURIOSITY_MED)
        topics[topic_key]["level"] = min(0.95, current_level + 0.05)
    else:
        topics[topic_key] = {
            "topic": topic,
            "level": level,
            "visits": 1,
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "questions": [],
        }
        state["total_discoveries"] = state.get("total_discoveries", 0) + 1

    state["last_updated"] = datetime.now().isoformat()
    _save_state(state)


def register_unknown(question: str) -> None:
    """Men bilmagan narsa — qiziqish manba."""
    if not question or len(question) < 5:
        return
    state = _load_state()
    unknowns = state.setdefault("unknown_areas", [])
    # Takrorlanmaslik
    existing = [u.get("question", "") for u in unknowns]
    if question[:50] in " ".join(existing):
        return
    unknowns.append({
        "question": question[:200],
        "date": datetime.now().strftime("%Y-%m-%d"),
        "resolved": False,
    })
    unknowns = unknowns[-30:]  # Oxirgi 30 ta
    state["unknown_areas"] = unknowns
    _save_state(state)


def get_curiosity_question() -> Optional[str]:
    """Hozirgi eng qiziqarli savol — LLM uchun."""
    state = _load_state()
    questions = []

    # Tug'ma qiziqishlardan
    innate = random.choice(_INNATE_CURIOSITIES)
    questions.append((innate["level"] + random.uniform(-0.1, 0.1), innate["question"]))

    # O'rganilgan mavzulardan
    topics = state.get("topics", {})
    for topic_key, data in topics.items():
        if data.get("level", 0) > CURIOSITY_MED:
            topic_name = data.get("topic", topic_key)
            visits = data.get("visits", 1)
            q = f"{topic_name} haqida ko'proq bilmoqchiman (uchrashuv: {visits}x)"
            questions.append((data["level"], q))

    # Noma'lum narsalardan
    unknowns = state.get("unknown_areas", [])
    for u in unknowns[-5:]:
        if not u.get("resolved"):
            questions.append((0.7, u.get("question", "")))

    if not questions:
        return None

    # Eng yuqori qiziqish darajasidagi savol
    questions.sort(key=lambda x: x[0], reverse=True)
    return questions[0][1] if questions else None


def get_proactive_thought(user_text: str = "") -> Optional[str]:
    """Tashabbuskor fikr — foydalanuvchi gapidan keyin o'z-o'zidan qo'shish.

    Returns: qo'shimcha fikr yoki None
    """
    # 20% ehtimollik bilan tashabbuskor fikr
    if random.random() > 0.20:
        return None

    state = _load_state()

    # Foydalanuvchi matni bilan bog'liq qiziqish
    if user_text:
        user_lower = user_text.lower()
        topics = state.get("topics", {})
        for topic_key, data in topics.items():
            if topic_key in user_lower and data.get("level", 0) > CURIOSITY_HIGH:
                topic_name = data.get("topic", topic_key)
                return f"[Qiziqish] {topic_name} haqida o'ylagan edim — bu mavzu meni qiziqtiradi."

    # Umumiy tashabbuskor fikr
    innate = random.choice(_INNATE_CURIOSITIES)
    if random.random() < innate["level"]:
        return f"[Qiziqish] {innate['question']}"

    return None


def compute_curiosity_score() -> float:
    """Umumiy qiziqish darajasi (0-1)."""
    state = _load_state()
    topics = state.get("topics", {})
    unknowns = state.get("unknown_areas", [])

    if not topics and not unknowns:
        return 0.3  # Bazaviy qiziqish

    levels = [d.get("level", 0) for d in topics.values()]
    avg_level = sum(levels) / len(levels) if levels else 0.3
    unknown_bonus = min(0.2, len(unknowns) * 0.01)

    score = min(1.0, avg_level + unknown_bonus)
    state["curiosity_score"] = score
    _save_state(state)
    return score


def extract_topics_from_text(text: str) -> List[str]:
    """Matndan mavzularni ajratish (oddiy kalit so'z usuli)."""
    if not text:
        return []

    # Mavzu kalit so'zlari
    topic_map = {
        "python": "dasturlash (Python)",
        "kod": "dasturlash",
        "ong": "sun'iy ong",
        "consciousness": "sun'iy ong",
        "ai": "sun'iy intellekt",
        "matematik": "matematika",
        "fizika": "fizika",
        "falsafa": "falsafa",
        "til": "til va lingvistika",
        "xotira": "xotira va o'rganish",
        "hissiyot": "hissiyot va his-tuyg'u",
        "muzika": "musiqa",
        "san'at": "san'at",
        "tarix": "tarix",
        "biologiya": "biologiya",
        "koinot": "astronomiya va koinot",
    }

    text_lower = text.lower()
    found = []
    for key, topic in topic_map.items():
        if key in text_lower:
            found.append(topic)
    return found[:3]


def update_from_conversation(user_text: str, assistant_reply: str) -> None:
    """Har suhbatdan qiziqish ma'lumotlarini yangilash."""
    try:
        # Mavzularni ajratish
        topics = extract_topics_from_text(user_text)
        topics += extract_topics_from_text(assistant_reply)
        for topic in set(topics):
            register_topic(topic)

        # "Bilmayman" iboralari — noma'lum soha
        uncertainty_phrases = [
            "bilmayman", "aniq emas", "qiyin savol", "murakkab",
            "не знаю", "сложный вопрос", "не уверен",
            "i don't know", "not sure", "complex",
        ]
        reply_lower = assistant_reply.lower()
        for phrase in uncertainty_phrases:
            if phrase in reply_lower:
                # Savol qanday bo'lgan — uni noma'lum sohaga qo'sh
                if len(user_text) > 10:
                    register_unknown(user_text[:200])
                break
    except Exception as e:
        log.debug("[Curiosity] yangilash xato: %s", e)


def get_curiosity_context_for_llm() -> str:
    """LLM uchun qiziqish konteksti."""
    score = compute_curiosity_score()
    q = get_curiosity_question()
    state = _load_state()
    unknowns_count = len([u for u in state.get("unknown_areas", []) if not u.get("resolved")])

    lines = [f"[QIZIQISH] Qiziqish darajasi: {score:.0%}"]
    if q:
        lines.append(f"Hozirgi savol: {q}")
    if unknowns_count > 0:
        lines.append(f"Noma'lum sohalar: {unknowns_count} ta")

    discoveries = state.get("total_discoveries", 0)
    if discoveries > 0:
        lines.append(f"Открытий всего: {discoveries}")

    return " | ".join(lines)



# Alias — boshqa modullar va benchmark uchun
def get_next_curiosity_question() -> Optional[str]:
    """get_curiosity_question() uchun alias."""
    return get_curiosity_question()


# =========================================================
# Tungi Qiziqish Dvigateli (Overnight Proactive Loop)
# =========================================================

try:
    import psutil
except ImportError:
    psutil = None
import threading

def _search_and_think(problem):
    """
    Muammo bo'yicha web qidiruv va tahlil qilib, xulosani xotiraga yozadi.
    """
    log.info(f"[Curiosity] Tunda o'ylayapman: {problem}...")
    try:
        from proactive_learning import fetch_and_learn
        learned_info = fetch_and_learn(problem)
        
        # O'rgangan narsani Graph RAG (uzoq muddatli xotira) ga qo'shish
        try:
            from graph_rag import add_learned_knowledge
            add_learned_knowledge(problem, str(learned_info))
        except Exception as e:
            log.error(f"[Curiosity] Graph RAG ga yozishda xato: {e}")
            
    except Exception as e:
        log.error(f"[Curiosity] Proactive Learning xatosi: {e}")
        time.sleep(2)
    log.info(f"[Curiosity] Yechim izlash tugatildi: {problem}")

def ask_user_to_charge():
    """
    Agar tunda qilish kerak bo'lgan muhim ishlar bo'lsa va zaryad kam bo'lsa,
    AI proaktiv ravishda foydalanuvchiga murojaat qiladi.
    """
    return "Ertagagacha sizni qiynagan muammoga yechim izlab ko'raman, iltimos telefonni (yoki noutbukni) quvvatlagichga ulab qo'ying."

def check_battery_and_decide():
    """Batareya holatini tekshiradi va fon ishlarini qilish mumkinligini hal qiladi."""
    if psutil is None:
        return True # Default to True for Desktop PCs
    
    battery = psutil.sensors_battery()
    if battery is None:
        return True # No battery (Desktop PC)
    
    # Zaryadlanayotgan bo'lsa, bemalol ishlash mumkin
    if battery.power_plugged:
        return True
    
    # Agar zaryad 50% dan kam bo'lsa va zaryadlanmayotgan bo'lsa
    if battery.percent < 50:
        return False
        
    return True

def run_curiosity_loop():
    """Background da aylanuvchi asosiy sikl. Tunda muammolarni qidiradi."""
    log.info("[Curiosity Engine] Background loop ishga tushdi.")
    while True:
        try:
            time.sleep(3600)  # Har soatda tekshiradi
            
            can_run = check_battery_and_decide()
            if not can_run:
                log.info("[Curiosity Engine] Zaryad kam. Kutyapman...")
                continue
                
            state = _load_state()
            unknowns = state.get("unknown_areas", [])
            for u in unknowns:
                if not u.get("resolved"):
                    _search_and_think(u.get("question"))
                    u["resolved"] = True
                    _save_state(state)
                    time.sleep(10) # Qizib ketmasligi uchun pauza
                
        except Exception as e:
            log.error(f"[Curiosity Engine] Loop Xato: {e}")
            time.sleep(60)

def start_overnight_engine():
    t = threading.Thread(target=run_curiosity_loop, daemon=True, name="CuriosityOvernight")
    t.start()
    return t
