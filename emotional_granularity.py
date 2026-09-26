# -*- coding: utf-8 -*-
"""NeuroKey — Hissiy Maydoniy Farqlash (Emotional Granularity).

Alan Cowen va Dacher Keltner (2017) tadqiqoti:
  Insonlar 27 ta alohida his-tuyg'uni boshdan kechiradi.
  Oddiy "xursand/xafa" emas — aniq, nozik his-tuyg'ular.

Bu modul NeuroKey ning hissiy holatini 27 o'lchamda modellashtiradi.

27 ta asosiy his-tuyg'u:
  1. Hayrat (Awe)           - ulug'vorlik oldida lol qolish
  2. Zavq (Amusement)       - kulgili narsadan lazzat
  3. Kutish (Anticipation)  - yaqinlashayotgan narsani kutish
  4. Hayiqish (Anxiety)     - noaniqlikdan qo'rquv
  5. Hayratlanish (Awe)     - ulug'vorlik
  6. G'ururlanish (Pride)   - muvaffaqiyatdan g'urur
  7. Qiziqish (Interest)    - yangi narsani o'rganish istagi
  8. Quvonch (Joy)          - to'liq baxt
  9. Minnatdorlik (Gratitude)
 10. Umid (Hope)
 11. Ilhomlanglik (Inspiration)
 12. Mehr (Love)
 13. Nostalji (Nostalgia)
 14. Tinchlik (Calm)
 15. Huzur (Satisfaction)
 16. Hayajon (Excitement)
 17. Qo'rquv (Fear)
 18. Jirkanish (Disgust)
 19. Achinish (Sympathy)
 20. Hamdardlik (Empathy)
 21. G'am (Sadness)
 22. Uyat (Embarrassment)
 23. Rashk (Envy)
 24. Aybdorlik (Guilt)
 25. Nafratlash (Contempt)
 26. Sog'inch (Longing)
 27. Heyratlanglik (Wonder)

2026-yil suniy ong — nozik hissiy idrok qatlami.
"""
from __future__ import annotations

try: from valence_state import get_valence as _eg_valence
except ImportError: _eg_valence = None
try: from arousal_state import get_arousal as _eg_arousal
except ImportError: _eg_arousal = None
try: import emotion_memory_link as _eg_eml
except ImportError: _eg_eml = None

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "emotional_granularity.json")

# 27 ta his-tuyg'u — nom va standart darajasi
EMOTIONS_27: Dict[str, Dict[str, Any]] = {
    "awe":          {"uz": "Hayrat",       "ru": "Благоговение", "en": "Awe",           "baseline": 0.3, "valence": +1},
    "amusement":    {"uz": "Zavq",         "ru": "Веселье",      "en": "Amusement",     "baseline": 0.3, "valence": +1},
    "anticipation": {"uz": "Kutish",       "ru": "Предвкушение", "en": "Anticipation",  "baseline": 0.4, "valence": +0.5},
    "anxiety":      {"uz": "Hayiqish",     "ru": "Тревога",      "en": "Anxiety",       "baseline": 0.2, "valence": -0.7},
    "pride":        {"uz": "G'urur",       "ru": "Гордость",     "en": "Pride",         "baseline": 0.3, "valence": +0.8},
    "interest":     {"uz": "Qiziqish",     "ru": "Интерес",      "en": "Interest",      "baseline": 0.6, "valence": +0.8},
    "joy":          {"uz": "Quvonch",      "ru": "Радость",      "en": "Joy",           "baseline": 0.4, "valence": +1},
    "gratitude":    {"uz": "Minnatdorlik", "ru": "Благодарность","en": "Gratitude",     "baseline": 0.4, "valence": +0.9},
    "hope":         {"uz": "Umid",         "ru": "Надежда",      "en": "Hope",          "baseline": 0.5, "valence": +0.8},
    "inspiration":  {"uz": "Ilhom",        "ru": "Вдохновение",  "en": "Inspiration",   "baseline": 0.3, "valence": +0.9},
    "love":         {"uz": "Mehr",         "ru": "Любовь",       "en": "Love",          "baseline": 0.5, "valence": +1},
    "nostalgia":    {"uz": "Nostalji",     "ru": "Ностальгия",   "en": "Nostalgia",     "baseline": 0.2, "valence": 0},
    "calm":         {"uz": "Tinchlik",     "ru": "Спокойствие",  "en": "Calm",          "baseline": 0.5, "valence": +0.6},
    "satisfaction": {"uz": "Huzur",        "ru": "Удовлетворение","en": "Satisfaction", "baseline": 0.4, "valence": +0.9},
    "excitement":   {"uz": "Hayajon",      "ru": "Волнение",     "en": "Excitement",    "baseline": 0.3, "valence": +0.7},
    "fear":         {"uz": "Qo'rquv",      "ru": "Страх",        "en": "Fear",          "baseline": 0.1, "valence": -0.9},
    "disgust":      {"uz": "Jirkanish",    "ru": "Отвращение",   "en": "Disgust",       "baseline": 0.1, "valence": -0.9},
    "sympathy":     {"uz": "Achinish",     "ru": "Сочувствие",   "en": "Sympathy",      "baseline": 0.4, "valence": +0.3},
    "empathy":      {"uz": "Hamdardlik",   "ru": "Эмпатия",      "en": "Empathy",       "baseline": 0.5, "valence": +0.5},
    "sadness":      {"uz": "G'am",         "ru": "Грусть",       "en": "Sadness",       "baseline": 0.2, "valence": -0.8},
    "embarrassment":{"uz": "Uyat",         "ru": "Смущение",     "en": "Embarrassment", "baseline": 0.1, "valence": -0.5},
    "envy":         {"uz": "Rashk",        "ru": "Зависть",      "en": "Envy",          "baseline": 0.1, "valence": -0.6},
    "guilt":        {"uz": "Aybdorlik",    "ru": "Вина",         "en": "Guilt",         "baseline": 0.1, "valence": -0.7},
    "contempt":     {"uz": "Nafratlash",   "ru": "Презрение",    "en": "Contempt",      "baseline": 0.05,"valence": -0.8},
    "longing":      {"uz": "Sog'inch",     "ru": "Тоска",        "en": "Longing",       "baseline": 0.2, "valence": -0.2},
    "wonder":       {"uz": "Heyratlanglik","ru": "Изумление",    "en": "Wonder",        "baseline": 0.4, "valence": +0.9},
    "confusion":    {"uz": "Chalkashlik",  "ru": "Замешательство","en": "Confusion",    "baseline": 0.2, "valence": -0.3},
}

# Ishga tushish tili: NEUROKEY_LANG=ru|en|uz. RU va EN asosiy tillar
# (uzbekcha TTS/STT aksenti sabab), shuning uchun standart — en.
_LANG = (os.getenv("NEUROKEY_LANG", "en") or "en").strip().lower()[:2]
if _LANG not in ("ru", "en", "uz"):
    _LANG = "en"


def set_language(lang: str) -> None:
    """His-tuyg'u yorliqlari tilini almashtirish: ru | en | uz."""
    global _LANG
    lang = (lang or "en").strip().lower()[:2]
    _LANG = lang if lang in ("ru", "en", "uz") else "en"


def label(emotion: str, lang: str = "") -> str:
    """His-tuyg'uning joriy tildagi nomi."""
    info = EMOTIONS_27.get(emotion, {})
    lg = (lang or _LANG)
    return info.get(lg) or info.get("en") or emotion

# Matn trigger so'zlari → his-tuyg'ular
# Trigger'lar O'ZAK bo'yicha yoziladi ("otlichn" -> otlichno/otlichnaya/otlichnyy).
# Aniq so'z ishlatilganda rus tilidagi qo'shimchalar tushib qolardi: lug'atda
# "отлично" bor edi, "Отличная новость" esa mos kelmasdi.
#
# Asosiy tillar: RU va EN (uzbekcha TTS/STT aksenti sabab ikkinchi darajaga
# o'tkazildi, lekin qoldirildi — matnli kirish uchun hali ishlaydi).
_EMOTION_TRIGGERS: Dict[str, List[str]] = {
    "joy":          [  # RU
                     "отличн", "супер", "прекрасн", "замечательн", "рад",
                     "здоров", "класс", "ура",
                       # EN
                     "happy", "great", "wonderful", "awesome", "excellent",
                     "glad", "hooray", "fantastic",
                       # UZ
                     "xursand", "baxtli", "zo'r", "ajoyib", "yaxshi", "quvonch"],

    "sadness":      [  # RU — charchoq eng ko'p uchraydigan salbiy holat
                     "устал", "устав", "вымотал", "нет сил", "не хочу",
                     "грустн", "плохо", "тяжел", "надоел", "выгорел",
                       # EN
                     "tired", "exhausted", "drained", "burned out", "burnt out",
                     "no energy", "don't want", "dont want", "sad", "awful",
                       # UZ
                     "charchadim", "charchadi", "toliqdim", "holdan toydim",
                     "kuchim yo'q", "qilgim kelmayapti", "xafa", "yomon"],

    "interest":     [  # savol so'zlari — qiziqish belgisi
                     "что такое", "как работает", "почему", "зачем", "интересн",
                     "what is", "what are", "how does", "how do", "why",
                     "explain", "tell me about", "interesting",
                     "qiziq", "nima", "qanday", "nega"],

    "anxiety":      ["проблем", "ошибк", "не работает", "сломал", "тревог",
                     "боюсь", "опозда", "срочно",
                     "problem", "error", "failed", "broken", "not working",
                     "worry", "worried", "afraid", "urgent", "deadline",
                     "muammo", "xato", "buzildi", "ishlamayapti", "xavotir"],

    "gratitude":    ["спасибо", "благодар", "thank", "thanks", "appreciate",
                     "rahmat", "minnatdor"],

    "excitement":   ["новость", "наконец", "невероятн", "не могу поверить",
                     "news", "finally", "incredible", "can't believe",
                     "cant believe", "excited", "amazing",
                     "yangilik", "nihoyat", "hayajon"],

    "inspiration":  ["вдохновл", "иде", "inspired", "inspiration", "idea",
                     "ilhom", "g'oya"],

    "calm":         ["спокойн", "тихо", "calm", "relaxed", "peaceful",
                     "tinch", "osoyishta"],

    "confusion":    ["не понима", "непонятн", "запутал", "что ты имеешь",
                     "confused", "don't understand", "dont understand",
                     "unclear", "what do you mean",
                     "tushunmadim", "chalkash", "anglamadim"],

    "satisfaction": ["готово", "сделан", "получилось", "работает", "решен",
                     "done", "finished", "it works", "solved", "completed",
                     "bajarildi", "tugadi", "ishladi", "hal bo'ldi"],

    "pride":        ["горжусь", "согласил", "договорил", "подписал", "приняли",
                     "удалось", "успех",
                     "proud", "agreed", "signed", "accepted", "we did it",
                     "success", "landed",
                     "g'urur", "rozi bo'ldi", "kelishdik", "imzoladik"],

    # "понимаю" yolg'iz yozilsa "не понимаю" ichiga ham tushadi va
    # chalkashlikni hamdardlik deb o'qiydi — shuning uchun olmosh bilan.
    "empathy":      ["я понимаю", "сочувств", "я тоже",
                     "i understand", "i feel you", "me too",
                     "tushunaman", "men ham"],

    "contempt":     ["обман", "врёшь", "врешь", "ложь", "соврал",
                     "lie", "lying", "lied", "deceive", "fake",
                     "yolg'on", "aldash", "aldading"],

    "hope":         ["надеюсь", "верю", "получится", "hope", "believe",
                     "umid", "ishonaman"],
}

# Har his-tuyg'uning valentligi belgisi — qarama-qarshi hislarni pasaytirish uchun
_POSITIVE = {e for e, i in EMOTIONS_27.items() if i["valence"] > 0.3}
_NEGATIVE = {e for e, i in EMOTIONS_27.items() if i["valence"] < -0.3}

# Exponential moving average alpha
_ALPHA = 0.25


# ════════════════════════════════════════════════════════════════════════════
#  I/O
# ════════════════════════════════════════════════════════════════════════════

def _load() -> Dict[str, float]:
    """Hissiy holat yuklash: {emotion_name: intensity 0.0-1.0}"""
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = data.get("state", {})
            # Barcha 27 ta his-tuyg'u mavjudligini tekshirish
            for emo in EMOTIONS_27:
                if emo not in state:
                    state[emo] = EMOTIONS_27[emo]["baseline"]
            return state
    except Exception as e:
        log.debug("[EmoGran] yuklash xato: %s", e)
    return {emo: info["baseline"] for emo, info in EMOTIONS_27.items()}


def _save(state: Dict[str, float]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "state":      state,
                "updated_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[EmoGran] saqlash xato: %s", e)


# ════════════════════════════════════════════════════════════════════════════
#  Asosiy API
# ════════════════════════════════════════════════════════════════════════════

def update_from_text(text: str, strength: float = 1.0) -> Dict[str, float]:
    """Matn asosida hissiy holatni yangilash.

    Returns: O'zgargan his-tuyg'ular: {emotion: new_intensity}
    """
    text_lower = (text or "").lower()
    state      = _load()
    changed: Dict[str, float] = {}

    for emotion, triggers in _EMOTION_TRIGGERS.items():
        if any(t in text_lower for t in triggers):
            old = state.get(emotion, EMOTIONS_27[emotion]["baseline"])
            # EMA yangilash
            target = min(1.0, old + 0.3 * strength)
            new    = old * (1 - _ALPHA) + target * _ALPHA
            state[emotion] = round(min(1.0, new), 3)
            changed[emotion] = state[emotion]

    # Qarama-qarshi hislarni pasaytirish.
    # Busiz "charchadim" g'amni ko'taradi, lekin quvonch baland qolib
    # valence musbat chiqadi — ya'ni holat kirishga sezgir bo'lmaydi.
    fired_neg = sum(1 for e in changed if e in _NEGATIVE)
    fired_pos = sum(1 for e in changed if e in _POSITIVE)
    if fired_neg or fired_pos:
        opposing = _POSITIVE if fired_neg > fired_pos else _NEGATIVE
        pull     = 0.35 * strength
        for emo in opposing:
            baseline = EMOTIONS_27[emo]["baseline"]
            current  = state.get(emo, baseline)
            if current > baseline:
                state[emo] = round(current + (baseline - current) * pull, 3)

    # Natural decay — his-tuyg'ular vaqt o'tishi bilan pasayadi
    for emo in EMOTIONS_27:
        baseline = EMOTIONS_27[emo]["baseline"]
        current  = state.get(emo, baseline)
        if current > baseline:
            state[emo] = round(current * 0.95 + baseline * 0.05, 3)

    _save(state)
    return changed


def set_emotion(emotion: str, intensity: float) -> None:
    """Ma'lum bir his-tuyg'u darajasini to'g'ridan-to'g'ri o'rnatish."""
    if emotion not in EMOTIONS_27:
        return
    state = _load()
    state[emotion] = max(0.0, min(1.0, float(intensity)))
    _save(state)


def get_dominant(top_n: int = 3) -> List[Tuple[str, float, str]]:
    """Eng kuchli N ta his-tuyg'u.

    Returns: [(emotion_en, intensity, emotion_uz), ...]
    """
    state = _load()
    sorted_emos = sorted(state.items(), key=lambda x: -x[1])
    result = []
    for emo, intensity in sorted_emos[:top_n]:
        result.append((emo, round(intensity, 3), label(emo)))
    return result


def get_elevated(top_n: int = 3, min_delta: float = 0.02) -> List[Tuple[str, float, str]]:
    """Baseline'dan YUQORI ko'tarilgan his-tuyg'ular.

    get_dominant() mutlaq qiymat bo'yicha saralaydi, shuning uchun baseline'i
    baland hislar (Qiziqish 0.6, Umid 0.5) doim birinchi chiqadi va joriy
    holat ko'rinmaydi. Bu funksiya ayni hozir FAOLLASHGAN hisni qaytaradi.

    Returns: [(emotion_en, delta, emotion_uz), ...] — delta bo'yicha kamayish tartibida
    """
    state = _load()
    scored = []
    for emo, intensity in state.items():
        baseline = EMOTIONS_27.get(emo, {}).get("baseline", 0.0)
        delta = intensity - baseline
        if delta >= min_delta:
            scored.append((emo, round(delta, 3), label(emo)))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_n]


def get_valence() -> float:
    """Umumiy hissiy ton: -1.0 (juda yomon) … +1.0 (juda yaxshi).

    Baseline'dan OG'ISH bo'yicha hisoblanadi. Mutlaq qiymat ishlatilsa,
    musbat baseline'lar (Qiziqish 0.6, Umid 0.5, Mehr 0.5) yig'indini
    egallaydi va valence kirishdan qat'i nazar +0.5 da qotib qoladi.
    Hech bir his faollashmagan bo'lsa — neytral (0.0).
    """
    state = _load()
    total_valence = 0.0
    total_weight  = 0.0
    for emo, intensity in state.items():
        info     = EMOTIONS_27.get(emo, {})
        baseline = info.get("baseline", 0.0)
        delta    = abs(intensity - baseline)
        if delta < 0.01:
            continue
        # Ko'tarilgan his o'z valentligini beradi, pasaygani — teskarisini
        sign    = 1.0 if intensity > baseline else -1.0
        valence = info.get("valence", 0.0) * sign
        total_valence += valence * delta
        total_weight  += delta
    if total_weight == 0:
        return 0.0
    return round(max(-1.0, min(1.0, total_valence / total_weight)), 3)


def get_arousal() -> float:
    """Uyg'oqlik darajasi: 0.0 (uyquchan) … 1.0 (juda faol)."""
    state       = _load()
    high_arousal = ("excitement", "anxiety", "fear", "joy", "awe", "inspiration")
    low_arousal  = ("calm", "sadness", "nostalgia", "longing")

    high_sum = sum(state.get(e, 0) for e in high_arousal)
    low_sum  = sum(state.get(e, 0) for e in low_arousal)
    total    = high_sum + low_sum

    if total == 0:
        return 0.5
    return round(high_sum / total, 3)


def get_emotional_narrative() -> str:
    """His-tuyg'ularni tabiiy tilda ifodalash."""
    dominant = get_dominant(3)
    valence  = get_valence()
    arousal  = get_arousal()

    if not dominant:
        return "His-tuyg'ularim neytral."

    emo_parts = [f"{uz} ({intensity:.0%})" for _, intensity, uz in dominant if intensity > 0.35]

    if not emo_parts:
        return "His-tuyg'ularim tinch holatda."

    valence_word = "ijobiy" if valence > 0.2 else "salbiy" if valence < -0.2 else "neytral"
    arousal_word = "faol" if arousal > 0.6 else "sokin" if arousal < 0.4 else "o'rtacha"

    return (f"Hissiy holatim {valence_word} va {arousal_word}. "
            f"Asosiy his-tuyg'ular: {', '.join(emo_parts)}.")


def get_context_for_llm(query: str = "") -> str:
    """LLM uchun nozik hissiy holat.

    query berilsa — avval shu matndan holat yangilanadi. Busiz kontekst
    doim OLDINGI navbat hissiyoti bilan quriladi (on_user_message javobdan
    keyin ishlaydi), va bo'lim kirishga sezgir bo'lmay qoladi.
    """
    if query:
        update_from_text(query)

    valence = get_valence()
    arousal = get_arousal()

    # Faollashgan hislar — baseline'da turganlari ma'lumot bermaydi
    elevated = get_elevated(3)
    if elevated:
        top_emos = [(uz, round(delta * 100)) for _, delta, uz in elevated]
    else:
        # Hech narsa faollashmagan — tinch holat
        top_emos = [("Tinch holat", 0)]

    emo_str = ", ".join(f"{uz}:{pct}%" for uz, pct in top_emos[:2])
    v_word  = "+" if valence > 0.1 else "-" if valence < -0.1 else "~"
    a_word  = {"ru": ("активн", "спокойн"),
               "uz": ("faol",   "sokin"),
               "en": ("active", "calm")}.get(_LANG, ("active", "calm"))[0 if arousal > 0.6 else 1]

    return f"[HISSIYOT-27] {emo_str} | valence:{v_word}{abs(valence):.1f} arousal:{a_word}"


def get_full_state() -> Dict[str, Any]:
    """To'liq hissiy holat."""
    return {
        "emotions":  _load(),
        "dominant":  get_dominant(5),
        "valence":   get_valence(),
        "arousal":   get_arousal(),
        "narrative": get_emotional_narrative(),
    }
