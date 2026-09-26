# -*- coding: utf-8 -*-
"""NeuroKey — Ichki monolog (Inner Speech).

Javobdan oldin LLM haqiqiy o'ylaydi: qisqa, keshli, timeoutli.
Bu ChatGPT dan farq: biz o'ylaymiz, keyin gapiramiz.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Optional


_CACHE_TTL = 60       # 1 daqiqa: yangi savolda yangi fikr
_MAX_TOKENS = 100     # kengaytirilgan fikrlash uchun
_TIMEOUT_SEC = 2.0    # parallel ishlaydi — kuta olamiz

_cache: dict = {}  # {question_hash: (thought, timestamp)}
_lock = threading.Lock()


def _hash(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode("utf-8", errors="ignore")).hexdigest()


def think(question: str, ctx: str = "") -> str:
    """
    Savol haqida ichki fikr generatsiya qiladi.
    Keshli: bir xil savol 5 daqiqa ichida qayta o'ylanmaydi.
    Timeoutli: 1.5s ichida javob kelmasa — bo'sh qaytaradi.
    """
    if not question or not question.strip():
        return ""

    h = _hash(question)
    now = time.monotonic()

    # Kesh tekshiruvi
    with _lock:
        cached = _cache.get(h)
        if cached:
            thought, ts = cached
            if (now - ts) < _CACHE_TTL:
                return thought

    result: list = [""]
    done = threading.Event()

    def _call():
        try:
            from llm_router import answer as _ans
            short_ctx = (ctx[:200] + "…") if len(ctx) > 200 else ctx
            # Kengaytirilgan fikrlash: nima so'rayapti, nima qilish kerak, xato qilmaslik uchun nima eslab qolish kerak
            prompt = (
                f"Foydalanuvchi dedi: «{question[:200]}»\n"
                + (f"Kontekst: {short_ctx}\n" if short_ctx else "")
                + "Ichki tahlil (rus tilida, FAQAT o'zing uchun — 2-3 qisqa jumla):\n"
                + "1. U aslida nima so'rayapti yoki nima xohlayapti?\n"
                + "2. Men nima qilishim kerak — to'g'ri javob yoki amal?\n"
                + "3. Bu yerda xato qilmaslik uchun nima eslab qolishim kerak?\n"
                + "Javob:"
            )
            thought = (_ans(
                prompt,
                brief=True,
                max_tokens=_MAX_TOKENS,
                lang_hint="ru",
            ) or "").strip()
            result[0] = thought[:300]
        except Exception:
            result[0] = ""
        finally:
            done.set()

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    done.wait(timeout=_TIMEOUT_SEC)

    thought = result[0]

    # Keshga saqlash (bo'sh bo'lmasa)
    if thought:
        with _lock:
            _cache[h] = (thought, time.monotonic())
            # Kesh hajmini cheklash
            if len(_cache) > 200:
                oldest = sorted(_cache.items(), key=lambda x: x[1][1])[:50]
                for k, _ in oldest:
                    _cache.pop(k, None)

    return thought


def start_parallel(question: str, ctx: str = "") -> "threading.Event | None":
    """
    Parallel rejimda inner speech ni boshlaydi.
    Darhol threading.Event qaytaradi — keyinroq collect_parallel() bilan natijani olish.
    Kontekst qurilayotganda parallel ravishda ishlaydi.
    """
    if not question or not question.strip():
        return None

    h = _hash(question)
    now = time.monotonic()

    # Allaqachon keshda bo'lsa — parallel kerak emas
    with _lock:
        cached = _cache.get(h)
        if cached and (now - cached[1]) < _CACHE_TTL:
            return None  # collect_parallel() keshdan oladi

    done = threading.Event()
    result_box: list = [""]

    def _run():
        try:
            result_box[0] = think(question, ctx)
        except Exception:
            result_box[0] = ""
        finally:
            done.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # Event va result_box ni birga saqlash uchun done._result_box = result_box
    done._result_box = result_box  # type: ignore[attr-defined]
    return done


def collect_parallel(event: "threading.Event | None", question: str, wait_extra: float = 0.3) -> str:
    """
    start_parallel() dan qaytgan event dan natijani olish.
    Agar hali tayyor bo'lmasa — wait_extra sekundalik qo'shimcha kutish.
    """
    if event is None:
        # Keshdan to'g'ridan-to'g'ri
        return think(question)

    # Qolgan vaqtni kutamiz (parallel ishlagan, faqat qolganini kutamiz)
    if not event.is_set():
        event.wait(timeout=wait_extra)

    result_box = getattr(event, "_result_box", [""])
    return result_box[0] if result_box else ""


def get_inner_speech() -> "InnerSpeech":
    """Singleton wrapper."""
    return _InnerSpeechSingleton()


class _InnerSpeechSingleton:
    """Ob'ekt interfeysi — global_workspace bilan moslik uchun."""

    def think(self, question: str, ctx: str = "") -> str:
        return think(question, ctx)

    def clear_cache(self) -> None:
        with _lock:
            _cache.clear()
