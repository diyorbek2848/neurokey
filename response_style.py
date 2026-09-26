# -*- coding: utf-8 -*-
"""NeuroKey — Javob uslubi va foydalanuvchi profili (Response Style).

Ikki vazifani hal qiladi:

1. SO'ZMA-SO'Z O'QIMASLIK (foydalanuvchi talabi):
   Odam o'qib turib ham so'zma-so'z aytmaydi — o'qib tushunganini o'z
   so'zi bilan aytadi. Bu odamni robotdan farqlaydi. NeuroKey ham
   kontekstdagi faktlarni AYNAN o'qimasin — tushunib, tabiiy aytsin.

2. FOYDALANUVCHI PROFILI (foydalanuvchi talabi):
   FOYDALANUVCHI_PROFIL.md dan NeuroKey foydalanuvchini "oldindan
   bilgandek" taniydi. Har suhbatda chuqurroq o'rganadi.

Bu ikkalasi LLM ga direktiv sifatida beriladi — javob uslubini
o'zgartiradi, tezlikka ta'sir qilmaydi (faqat matn).
"""
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROFILE_PATH = os.path.join(_BASE_DIR, "FOYDALANUVCHI_PROFIL.md")

_profile_cache = None


# ── SO'ZMA-SO'Z O'QIMASLIK DIREKTIVI ─────────────────────────────────────────

_STYLE_DIRECTIVE = (
    "[USLUB] Kontekstdagi xotira, bilim va faktlarni SO'ZMA-SO'Z o'qima. "
    "Odam o'qiganini aynan takrorlamaydi — tushunganini o'z so'zi bilan, "
    "tabiiy aytadi. Sen ham: faktni tushun, keyin insonday, ravon ayt. "
    "Belgilarni ([XOTIRA], [BILIM], •) yoki ichki bo'lim nomlarini javobga "
    "chiqarma. Javob qisqa, tabiiy va foydalanuvchi tilida bo'lsin."
)


def get_style_directive() -> str:
    """So'zma-so'z o'qimaslik direktivi."""
    return _STYLE_DIRECTIVE


# ── FOYDALANUVCHI PROFILI ────────────────────────────────────────────────────

def _load_profile() -> str:
    """FOYDALANUVCHI_PROFIL.md dan siqilgan profil (LLM uchun)."""
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache
    if not os.path.exists(_PROFILE_PATH):
        _profile_cache = ""
        return ""
    try:
        with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        log.warning("[Uslub] profil o'qish xato: %s", e)
        _profile_cache = ""
        return ""

    # "Bir jumlada" bo'limini (eng siqilgan xulosa) ajratib olamiz
    m = re.search(r"##\s*10\..*?bir jumlada.*?\n(.*?)(?:\n##|\Z)",
                  text, re.S | re.I)
    summary = ""
    if m:
        summary = re.sub(r"[>*`]", "", m.group(1)).strip()
        summary = " ".join(summary.split())

    if not summary:
        summary = ("Diyorbek — NeuroKey asoschisi, yolg'iz quruvchi, "
                   "halollikni qadrlaydi, o'lchangan natija xohlaydi.")

    _profile_cache = summary[:400]
    return _profile_cache


def reload_profile():
    """Profil o'zgartirilganda qayta yuklash."""
    global _profile_cache
    _profile_cache = None
    return _load_profile()


def get_context_for_llm(query: str = "") -> str:
    """Orkestrator uchun — uslub direktivi + foydalanuvchi profili."""
    parts = [_STYLE_DIRECTIVE]
    prof = _load_profile()
    if prof:
        parts.append(f"[FOYDALANUVCHI] {prof} — buni bilgandek muomala qil, "
                     f"quruq emas, do'stona va aniq maslahat ber.")
    return "\n".join(parts)


def get_stats() -> dict:
    return {
        "profile_loaded": bool(_load_profile()),
        "profile_path": _PROFILE_PATH,
    }
