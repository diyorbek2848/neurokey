# -*- coding: utf-8 -*-
"""NeuroKey — Jonli ekran ko'rish (Live Vision).

Foydalanuvchi talab qildi: skrinshot olib tahlil qilguncha vaqt ketadi.
Real vaqtda ko'rish kerak — savol berilsa, DARROV javob berish.

O'lchandi (asosiy muammo):
  grab_screen:  93 ms   (tez)
  oyna holati:  1 ms    (tez)
  OCR:          4000 ms (SEKIN — bo'yin shu yerda)

Yechim — FON KESHLASH:
  - Fon oqimi doimiy grab + oyna holatini yangilaydi (tez, 93ms)
  - OCR faqat ekran O'ZGARGANDA qilinadi (kadr xeshi solishtiriladi)
  - Natija keshda saqlanadi
  - Savol kelganda: keshdan javob — <1 ms, kutish yo'q

Shunda tizim "real vaqtda ko'rayotgandek" his qilinadi: javob har doim
tayyor keshdan keladi, yangi 4s OCR dan emas.

ONG ULANISHI: joriy ko'rinish orkestrator kontekstiga qo'shiladi —
NeuroKey ekranda nima borligini "biladi", so'ralmasa ham.

CHEKLOV: OCR matnni o'qiydi (UI, sayt, kod). Kino/rasmdagi qahramonni
tanish uchun vision-LLM kerak (describe_on_demand). OCR emas.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

# Fon yangilanish oralig'i
_POLL_FAST = 0.5    # oyna holati + grab (tez)
_OCR_MIN_INTERVAL = 2.0   # OCR eng ko'pi bilan har 2s (o'zgarsa)

_lock = threading.Lock()
_state = {
    "windows": None,       # ScreenState
    "screen_text": "",     # oxirgi OCR natijasi
    "frame_hash": "",      # oxirgi kadr xeshi (o'zgarishni aniqlash)
    "ts_window": 0.0,
    "ts_ocr": 0.0,
}
_thread = None
_running = False
_last_img = None


def _frame_hash(img) -> str:
    """Kadrning tez xeshi — o'zgarishni aniqlash uchun (to'liq emas, kichraytirilgan)."""
    try:
        small = img.resize((32, 18)).convert("L")
        return hashlib.md5(small.tobytes()).hexdigest()[:16]
    except Exception:
        return ""


def _loop():
    global _last_img
    import screen_vision as sv
    try:
        import screen_awareness as sa
    except Exception:
        sa = None

    while _running:
        try:
            # 1. Oyna holati — tez (1ms)
            if sa is not None:
                st = sa.get_screen_state()
                with _lock:
                    _state["windows"] = st
                    _state["ts_window"] = time.time()

            # 2. Grab — tez (93ms)
            img = sv.grab_screen()
            if img is not None:
                h = _frame_hash(img)
                changed = h != _state.get("frame_hash")
                now = time.time()
                # 3. OCR — faqat o'zgargan bo'lsa va interval o'tgan bo'lsa
                if changed and (now - _state["ts_ocr"]) >= _OCR_MIN_INTERVAL:
                    txt = sv.extract_text_fast(img) or ""
                    with _lock:
                        _state["screen_text"] = txt
                        _state["frame_hash"] = h
                        _state["ts_ocr"] = now
                    _last_img = img
        except Exception as e:
            log.debug("[JonliKo'rish] loop xato: %s", e)
        time.sleep(_POLL_FAST)


def start():
    """Fon ko'rish oqimini ishga tushiradi."""
    global _thread, _running
    if _running:
        return
    _running = True
    _thread = threading.Thread(target=_loop, daemon=True, name="live_vision")
    _thread.start()
    log.info("[JonliKo'rish] fon oqimi boshlandi")


def stop():
    global _running
    _running = False


def get_current_view() -> dict:
    """Joriy ko'rinish — KESHDAN, bir zumda (<1ms). Kutish yo'q."""
    if not _running:
        start()   # birinchi so'rovda fon oqimini avtomatik yoqadi
    with _lock:
        st = _state["windows"]
        return {
            "active_window": getattr(st, "active_title", "") if st else "",
            "open_count": getattr(st, "open_count", 0) if st else 0,
            "minimized": getattr(st, "minimized", []) if st else [],
            "maximized": getattr(st, "maximized", []) if st else [],
            "screen_text": _state["screen_text"][:400],
            "text_age_sec": round(time.time() - _state["ts_ocr"], 1)
                            if _state["ts_ocr"] else None,
        }


def describe_on_demand() -> str:
    """Kino/rasm uchun vision-LLM bilan tavsif (OCR emas). Sekinroq.

    Foydalanuvchi 'bu qahramon yovuzmi?' desa — bu chaqiriladi."""
    try:
        import screen_vision as sv
        img = _last_img or sv.grab_screen()
        if img is None:
            return ""
        if hasattr(sv, "describe_screen_with_vision"):
            return sv.describe_screen_with_vision(img) or ""
        return sv.extract_text_fast(img) or ""
    except Exception as e:
        log.debug("[JonliKo'rish] describe xato: %s", e)
        return ""


def get_context_for_llm(query: str = "") -> str:
    """Orkestrator uchun — ekranda nima borligi (keshdan, tez)."""
    v = get_current_view()
    if not v["active_window"] and not v["screen_text"]:
        return ""
    parts = [f"[EKRAN] Faol oyna: {v['active_window'][:50]}"]
    if v["open_count"]:
        parts.append(f"{v['open_count']} oyna ochiq")
    if v["minimized"]:
        parts.append(f"yig'ilgan: {', '.join(v['minimized'][:2])}")
    line = "[EKRAN] " + " | ".join(
        [f"Faol: {v['active_window'][:40]}"] +
        ([f"{v['open_count']} oyna"] if v["open_count"] else []) +
        ([f"yig'ilgan: {v['minimized'][0]}"] if v["minimized"] else [])
    )
    if v["screen_text"]:
        age = v["text_age_sec"]
        line += f"\n[EKRAN MATN] ({age}s oldin ko'rildi) {v['screen_text'][:200]}"
    return line


def get_stats() -> dict:
    with _lock:
        return {
            "running": _running,
            "has_text": bool(_state["screen_text"]),
            "text_age_sec": round(time.time() - _state["ts_ocr"], 1)
                            if _state["ts_ocr"] else None,
        }
