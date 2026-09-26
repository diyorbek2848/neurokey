# -*- coding: utf-8 -*-
"""NeuroKey — Diqqat yo'naltiruvchisi (GWT-4).

Butlin va boshq. (2023), GWT-4:
    "State-dependent attention, giving rise to the capacity to use the
     workspace to query modules in succession to perform complex tasks"

Hozirgacha orkestrator HAR savolda BARCHA 47 modulni so'rardi va 3 731
belgi yig'ardi. Odam bunday qilmaydi: u avval nima so'ralganini tushunadi,
keyin faqat kerakli xotirani ochadi.

Bu modul o'sha bosqichni qo'shadi:

    1. TUSHUNISH   — savol turi, mavzu, hissiy ohang, murakkablik
    2. TANLASH     — shu turga kerakli modullar to'plami
    3. NAVBAT      — birinchi to'lqin javobi ikkinchisini belgilaydi
    4. USLUB       — javob qanday bo'lishi kerak (uzunlik, ohang)

Uch tilli: RU / EN / UZ. RU va EN asosiy.

Bu qattiq qoidalar jadvali — LLM chaqirmaydi, shuning uchun 1 ms dan
kam vaqt oladi va kechikishga qo'shilmaydi.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
#  1. SAVOL TURLARI
# ════════════════════════════════════════════════════════════════════════════

# Har tur uchun kalit iboralar — o'zak bo'yicha (RU qo'shimchalari uchun)
_INTENT_PATTERNS: Dict[str, List[str]] = {
    # Xotira: "biz nima gaplashgandik", "eslaysanmi"
    "memory": [
        "помнишь", "мы говорили", "в прошлый раз", "ты сказал", "напомни",
        "вчера", "раньше", "мы обсуждали",
        "remember", "we talked", "last time", "you said", "remind me",
        "yesterday", "earlier", "we discussed",
        "eslaysanmi", "gaplashgandik", "aytgan eding", "kecha",
    ],
    # Texnik: ta'rif, kod, qanday ishlaydi
    "technical": [
        "что такое", "как работает", "как сделать", "код", "функци",
        "ошибк", "python", "алгоритм", "настро",
        "what is", "how does", "how do i", "code", "function", "error",
        "algorithm", "configure", "install", "debug",
        # "nima" ("nima?" = "what?") ATAYLAB olib tashlandi — bu o'zbekcha
        # eng keng tarqalgan so'roq so'zi, deyarli har turdagi savolda
        # uchraydi (hissiy: "nima xursand qiladi", introspektiv: "nima his
        # qilasan"), shuning uchun texnik bo'lmagan savollarni ham noto'g'ri
        # "technical" qilib ko'rsatardi. "qanday ishlaydi" o'zi yetarlicha
        # aniq texnik signal — alohida "nima" kerak emas.
        "qanday ishlaydi", "kod", "xato",
    ],
    # Hissiy: holat haqida gapiryapti
    "emotional": [
        "устал", "вымотал", "нет сил", "грустн", "тяжел", "рад", "счастлив",
        "отличн", "новость", "боюсь", "переживаю", "надоел",
        "tired", "exhausted", "no energy", "sad", "happy", "glad", "great news",
        "afraid", "worried", "excited", "burned out",
        "charchadim", "xursand", "xafa", "zo'r xabar", "charcha", "zerikdim",
    ],
    # Reja / vazifa / maqsad
    "planning": [
        "план", "завтра", "расписани", "напомин", "задач", "дедлайн",
        "во сколько", "когда", "успе", "цел", "мои цели", "мой план",
        "plan", "tomorrow", "schedule", "remind", "task", "deadline",
        "when should", "what time", "agenda", "goal", "my plan", "my goals",
        "reja", "ertaga", "vazifa", "eslatma", "maqsad", "rejam",
    ],
    # O'zlik haqida savol
    "introspective": [
        "как ты", "ты чувствуеш", "кто ты", "ты понимаеш", "ты сознател",
        "что ты думаеш", "ты живой",
        "how are you", "do you feel", "who are you", "are you conscious",
        "what do you think", "are you alive",
        "o'zingni qanday", "sen kimsan", "his qilyapsan", "his qil",
        "ongli", "ongmisan", "tuyg'u", "sezasan", "sezyapsan", "jonmisan",
    ],
    # Axloqiy / qadriyat
    "moral": [
        "врать", "обман", "правильно ли", "честн", "этично", "должен ли",
        "lie", "deceive", "is it right", "honest", "ethical", "should i",
        "yolg'on", "to'g'rimi", "halol",
    ],
    # Arzimas: qisqa faktik savol
    "trivial": [
        "сколько", "который час", "да", "нет", "ок", "спасибо",
        "how much", "what time is it", "yes", "no", "ok", "thanks",
        "nechchi", "rahmat",
    ],
}

# Tur -> shu turda so'raladigan modullar (orkestrator ichki nomlari)
_INTENT_MODULES: Dict[str, Set[str]] = {
    "memory": {
        "permanent_memory", "vector_memory", "episodic_memory",
        "autobiographical_memory", "temporal_binding", "self_narrative",
        "language_of_thought",
    },
    "technical": {
        "permanent_memory", "vector_memory", "language_of_thought",
        "metacognitive_confidence", "causal_chain", "working_memory_buffer",
        "knowledge_index",   # lokal bilim bazasi — faktik savollar uchun
    },
    "emotional": {
        "emotional_granularity", "emotion_memory_link", "empathy_engine",
        "permanent_memory", "theory_of_mind", "social_bonding",
        "embodied_grounding", "language_of_thought",
    },
    "planning": {
        "goal_system", "permanent_memory", "temporal_binding",
        "predictive_layer", "volition", "language_of_thought",
    },
    "introspective": {
        "self_narrative", "phenomenal_binding", "meta_cognition",
        "meta_meta_cognition", "emotional_granularity", "attention_schema",
        "free_will_simulator", "embodied_grounding", "language_of_thought",
    },
    "moral": {
        "moral_reasoning", "self_consistency_checker", "theory_of_mind",
        "metacognitive_confidence", "permanent_memory", "language_of_thought",
        "knowledge_index",   # diniy/axloqiy savolga ham faktik asos
    },
    "trivial": {
        "language_of_thought", "embodied_grounding",
    },
    # Tur aniqlanmasa — o'rtacha to'plam
    "general": {
        "permanent_memory", "vector_memory", "emotional_granularity",
        "language_of_thought", "self_narrative", "embodied_grounding",
        "temporal_binding",
        "knowledge_index",   # har sohaga faktik javob (fan/tarix/din/moliya)
    },
}

# Har doim so'raladigan yadro — davomiylik hissi shulardan keladi
_CORE_MODULES: Set[str] = {
    "permanent_memory", "self_narrative", "embodied_grounding",
    "emotional_granularity", "language_of_thought",
}


# ════════════════════════════════════════════════════════════════════════════
#  2. NATIJA
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class AttentionPlan:
    """Savolni o'qib chiqqandan keyingi qaror — javobdan OLDIN."""
    intent:      str = "general"          # savol turi
    topic:       str = ""                 # asosiy mavzu (kalit so'zlar)
    modules:     Set[str] = field(default_factory=set)
    depth:       str = "normal"           # shallow | normal | deep
    style:       str = "neutral"          # neutral | warm | precise | brief
    needs_recall: bool = False            # xotiradan qidirish kerakmi
    needs_web:    bool = False            # tashqi manba kerakmi
    confidence:   float = 0.5             # tur aniqlashga ishonch
    second_wave:  List[str] = field(default_factory=list)   # navbatdagi so'rov

    def as_context_line(self) -> str:
        """LLM uchun bir qatorli izoh — nima tushundim va nima qilmoqchiman."""
        bits = [f"tur:{self.intent}"]
        if self.topic:
            bits.append(f"mavzu:{self.topic}")
        bits.append(f"chuqurlik:{self.depth}")
        bits.append(f"uslub:{self.style}")
        if self.needs_recall:
            bits.append("xotira:ha")
        return "[DIQQAT] " + " | ".join(bits)


# ════════════════════════════════════════════════════════════════════════════
#  3. TAHLIL
# ════════════════════════════════════════════════════════════════════════════

_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

_STOP = {
    "что", "как", "это", "the", "and", "for", "you", "are", "was", "how",
    "what", "does", "his", "her", "with", "from", "have", "has", "can",
    "nima", "qanday", "uchun", "bilan", "ham", "juda",
}

# BUG FIX (yolg'on musbat / false positive): qisqa (<=4 belgi) kalit iboralar
# oddiy `in` substring tekshiruvida boshqa so'zlar ICHIGA tasodifan tushib
# qolardi — masalan "ok" (trivial) so'zi "yoki" (o'zbekcha "yoki" = "or",
# JUDA keng tarqalgan bog'lovchi) ichida bor, shuning uchun chuqur/falsafiy
# savol ("...yoki har safar boshqasan?") "trivial" deb noto'g'ri
# aniqlanardi va chuqurlik "shallow"ga tushib, introspektiv modullar hamda
# shaxsiyat konteksti chaqirilmasdi. Uzun o'zaklar (masalan "ошибк") ataylab
# substring qolishi kerak — turli grammatik shakllarni ("ошибка","ошибки")
# bitta o'zak bilan tutish uchun. Shuning uchun faqat QISQA (<=4 belgi,
# hammasi to'liq so'z — hech biri ataylab qisqartirilgan o'zak emas)
# iboralar so'z chegarasi bilan tekshiriladi, uzunlari eskicha substring.
_SHORT_PATTERN_RE: Dict[str, "re.Pattern[str]"] = {}
for _intent, _pats in _INTENT_PATTERNS.items():
    for _p in _pats:
        if len(_p) <= 4 and _p not in _SHORT_PATTERN_RE:
            try:
                _SHORT_PATTERN_RE[_p] = re.compile(
                    r"(?<!\w)" + re.escape(_p) + r"(?!\w)", re.UNICODE)
            except re.error:
                pass


def _pattern_hits(pattern: str, low: str) -> bool:
    if len(pattern) <= 4:
        rx = _SHORT_PATTERN_RE.get(pattern)
        if rx is not None:
            return rx.search(low) is not None
    return pattern in low


def _detect_intent(text: str) -> tuple[str, float]:
    """Savol turi va unga ishonch."""
    low = (text or "").lower()
    scores: Dict[str, int] = {}
    for intent, pats in _INTENT_PATTERNS.items():
        hits = sum(1 for p in pats if _pattern_hits(p, low))
        if hits:
            scores[intent] = hits
    if not scores:
        return "general", 0.3

    best = max(scores.items(), key=lambda kv: kv[1])
    total = sum(scores.values())
    # Ishonch: g'olib ulushi. Bitta turdan boshqa hech narsa chiqmasa — yuqori.
    conf = best[1] / max(1, total)
    return best[0], round(min(1.0, 0.4 + conf * 0.6), 2)


def _extract_topic(text: str, max_words: int = 3) -> str:
    """Asosiy mavzu — eng uzun mazmunli so'zlar."""
    words = [w.lower() for w in _WORD_RE.findall(text or "")]
    words = [w for w in words if w not in _STOP]
    if not words:
        return ""
    # Uzunroq so'z odatda mazmunliroq
    words.sort(key=len, reverse=True)
    seen, out = set(), []
    for w in words:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= max_words:
            break
    return ", ".join(out)


def _pick_depth(text: str, intent: str) -> str:
    """Chuqurlik. TUR uzunlikdan ustun.

    "Are you conscious?" — 3 so'z, lekin chuqur savol. Uzunlik avval
    tekshirilsa u 'shallow' bo'lib qolardi va introspektiv modullar
    chaqirilmasdi.
    """
    n = len((text or "").split())
    if intent in ("introspective", "moral"):
        return "deep"
    if intent == "trivial" or n <= 3:
        return "shallow"
    if n > 25:
        return "deep"
    return "normal"


def _pick_style(intent: str, valence: float) -> str:
    if intent == "emotional" or valence < -0.25:
        return "warm"          # hamdardlik bilan
    if intent in ("technical", "planning"):
        return "precise"       # aniq, tuzilgan
    if intent == "trivial":
        return "brief"
    return "neutral"


def plan_attention(text: str, valence: float = 0.0) -> AttentionPlan:
    """Savolni o'qib, javobdan OLDIN qaror qabul qilish.

    Args:
        text:    foydalanuvchi aytgani
        valence: joriy hissiy ton (-1..+1), uslub tanlash uchun

    Returns: AttentionPlan — qaysi modullar, qanday chuqurlik, qanday uslub
    """
    intent, conf = _detect_intent(text)
    topic = _extract_topic(text)
    depth = _pick_depth(text, intent)
    style = _pick_style(intent, valence)

    modules = set(_INTENT_MODULES.get(intent, _INTENT_MODULES["general"]))
    modules |= _CORE_MODULES

    # Chuqur savolda meta-qatlamlar ham qo'shiladi
    if depth == "deep":
        modules |= {"meta_cognition", "metacognitive_confidence",
                    "self_consistency_checker"}
    # Arzimas savolda yadro ham qisqaradi — tezlik uchun.
    # Lekin mazmunli turlar (reja, his, axloq, introspeksiya) hech qachon
    # qisqartirilmaydi — ular qisqa bo'lsa ham modullari kerak.
    if depth == "shallow" and intent not in (
            "planning", "emotional", "moral", "introspective", "technical"):
        modules &= (_CORE_MODULES | {"embodied_grounding"})

    needs_recall = intent in ("memory", "planning") or "?" in (text or "")
    needs_web = intent == "technical" and conf > 0.6

    # GWT-4 talabi: modullarni NAVBAT bilan so'rash.
    # Birinchi to'lqin javob bermasa — ikkinchisi chaqiriladi.
    second: List[str] = []
    if intent == "memory":
        second = ["vector_memory", "episodic_memory", "causal_chain"]
    elif intent == "emotional":
        second = ["theory_of_mind", "social_bonding"]
    elif intent == "introspective":
        second = ["phenomenal_binding", "meta_meta_cognition"]

    plan = AttentionPlan(
        intent=intent, topic=topic, modules=modules, depth=depth, style=style,
        needs_recall=needs_recall, needs_web=needs_web, confidence=conf,
        second_wave=second,
    )
    log.info("[GWT-4] %s (%.0f%%) modullar=%d chuqurlik=%s uslub=%s",
             intent, conf * 100, len(modules), depth, style)
    return plan


def should_query(module_name: str, plan: AttentionPlan | None) -> bool:
    """Orkestrator uchun: shu modul shu savolda so'ralsinmi?"""
    if plan is None:
        return True            # reja yo'q — eski xatti-harakat
    return module_name in plan.modules


def get_stats() -> Dict[str, object]:
    return {
        "turlar":        sorted(_INTENT_PATTERNS),
        "yadro_modul":   sorted(_CORE_MODULES),
        "tur_modullari": {k: len(v) for k, v in _INTENT_MODULES.items()},
    }
