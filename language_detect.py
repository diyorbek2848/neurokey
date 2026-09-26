# -*- coding: utf-8 -*-
"""NeuroKey — Til aniqlash (Language Detection).

Foydalanuvchi talab qildi: o'zbekcha so'rasam — inglizcha yoki arabcha deb
adashmasin. Aniq bilsin qaysi tilda.

Asosiy qiyinchilik: O'ZBEKCHA vs INGLIZCHA — ikkalasi lotin yozuvida.
langdetect qisqa o'zbekchani ko'pincha turk/ingliz deb xato qiladi.

Yechim — ko'p qatlamli:
  1. Yozuv aniqlash (kirill / lotin / arab / boshqa)
  2. Kirill: o'zbek maxsus harflari (қ ғ ў ҳ) -> uz, aks holda -> ru
  3. Lotin: o'zbek morfologiyasi va so'zlari -> uz, aks holda langdetect
  4. Arab/xitoy/koreys -> "other" (uz/ru/en emas)

Natija: 'uz' | 'ru' | 'en' | 'other' + ishonch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Yozuv diapazonlari
_CYRILLIC = re.compile(r"[А-Яа-яЁёЎўҚқҒғҲҳ]")
_LATIN    = re.compile(r"[A-Za-z]")
_ARABIC   = re.compile(r"[؀-ۿ]")
_CJK      = re.compile(r"[一-鿿぀-ヿ가-힯]")

# O'zbek kirill maxsus harflari (rusda yo'q)
_UZ_CYRILLIC = set("ўқғҳЎҚҒҲ")

# O'zbek lotin maxsus belgilari
_UZ_LATIN_MARKERS = ("o'", "g'", "o‘", "g‘", "sh", "ch", "ng")

# O'zbek tez-tez uchraydigan so'zlar / qo'shimchalar
_UZ_WORDS = {
    "men", "sen", "biz", "ular", "bu", "shu", "nima", "qanday", "qanaqa",
    "nega", "qachon", "qayer", "kim", "uchun", "bilan", "ham", "yoki",
    "lekin", "va", "salom", "rahmat", "yaxshi", "yomon", "bor", "yo'q",
    "qil", "qildim", "qilaman", "bo'ldi", "kerak", "mumkin", "hozir",
    "ertaga", "kecha", "bugun", "menga", "senga", "haqida", "deb",
}
# O'zbek morfologik qo'shimchalar (so'z oxiri)
_UZ_SUFFIXES = ("yapti", "moqchi", "gan", "kan", "di", "di", "yman",
                "ysan", "miz", "siz", "lar", "ning", "dan", "ga", "da",
                "man", "san")

# Ingliz tez-tez uchraydigan so'zlar
_EN_WORDS = {
    "the", "is", "are", "was", "were", "and", "or", "but", "what", "how",
    "why", "when", "where", "who", "you", "your", "this", "that", "with",
    "for", "have", "has", "can", "will", "would", "should", "about",
    "please", "hello", "thanks", "yes", "no", "do", "does", "make",
}


@dataclass
class LangResult:
    lang: str = "en"          # uz | ru | en | other
    confidence: float = 0.0
    script: str = ""          # cyrillic | latin | arabic | cjk | mixed


def _uz_score_latin(low: str, words: set) -> int:
    """Lotin matnda o'zbekcha belgilar soni."""
    score = 0
    for m in _UZ_LATIN_MARKERS:
        score += low.count(m)
    score += sum(1 for w in words if w in _UZ_WORDS)
    score += sum(1 for w in words for s in _UZ_SUFFIXES
                 if len(w) > len(s) + 1 and w.endswith(s))
    return score


def detect(text: str) -> LangResult:
    """Matn tilini aniqlaydi: uz | ru | en | other."""
    t = (text or "").strip()
    if not t:
        return LangResult("uz", 0.0, "")

    # 1. Boshqa yozuvlar — arab, xitoy/yapon/koreys
    if _ARABIC.search(t):
        return LangResult("other", 0.95, "arabic")
    if _CJK.search(t):
        return LangResult("other", 0.95, "cjk")

    cyr = len(_CYRILLIC.findall(t))
    lat = len(_LATIN.findall(t))
    total = cyr + lat
    if total == 0:
        return LangResult("uz", 0.2, "")

    # 2. Kirill ustun — rus yoki o'zbek-kirill
    if cyr >= lat:
        if any(ch in t for ch in _UZ_CYRILLIC):
            return LangResult("uz", 0.9, "cyrillic")
        return LangResult("ru", 0.9, "cyrillic")

    # 3. Lotin ustun — o'zbek yoki ingliz (asosiy qiyin holat)
    low = t.lower()
    words = set(re.findall(r"[a-z']+", low))
    uz = _uz_score_latin(low, words)
    en = sum(1 for w in words if w in _EN_WORDS)

    # O'zbek maxsus belgisi (o' g') kuchli signal
    strong_uz = any(m in low for m in ("o'", "g'", "o‘", "g‘"))

    if strong_uz or uz > en:
        conf = min(0.95, 0.55 + uz * 0.1)
        return LangResult("uz", conf, "latin")
    if en > uz:
        conf = min(0.95, 0.55 + en * 0.1)
        return LangResult("en", conf, "latin")

    # 4. Teng — langdetect zaxira
    try:
        from langdetect import detect as ld, DetectorFactory
        DetectorFactory.seed = 0
        code = ld(t)
        if code in ("uz", "tr", "az"):
            return LangResult("uz", 0.5, "latin")
        if code.startswith("ru"):
            return LangResult("ru", 0.5, "latin")
        if code.startswith("en"):
            return LangResult("en", 0.5, "latin")
    except Exception:
        pass

    # 5. Oxirgi zaxira
    return LangResult("en" if en >= uz else "uz", 0.4, "latin")


def detect_lang(text: str) -> str:
    """Qisqa API — faqat til kodi."""
    return detect(text).lang


def get_stats() -> dict:
    return {"supported": ["uz", "ru", "en", "other"]}
