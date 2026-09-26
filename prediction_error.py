# -*- coding: utf-8 -*-
"""NeuroKey — Bashorat xatosi (PP-1).

Butlin va boshq. (2023), PP-1:
    "Input modules using predictive coding"

Ilgari "bashorat xatosi" soxta edi — `behavioral_engine.py` da:

    if self.state.total_queries % 3 == 0:
        self.state.prediction_errors += 1     # har 3-savolda +1

Bu hech qanday bashoratni o'lchamaydi. `predictive_layer.py` da esa
haqiqiy qismlar bor edi (predict_next_request, calculate_prediction_error,
update_patterns) — lekin halqa hech qachon yopilmagan: bashorat qilinardi,
keyin hech qachon haqiqat bilan solishtirilmasdi.

Bu modul halqani yopadi:

    1-navbat oxiri : keyingi savol nima bo'lishini BASHORAT qiladi
    2-navbat boshi : haqiqiy savol bilan SOLISHTIRADI -> xato 0..1
    xato katta     : hayrat -> chuqurroq ishlov, diqqat oshadi
    har navbat     : model YANGILANADI

Natija ikki xil: tezlik (javob oldindan tayyorlanadi) va "fikrlash"
hissi (kutmagan narsaga duch kelganda tizim o'zgaradi).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "prediction_error.json")

_HISTORY_LEN = 30
_lock = threading.Lock()
_state: Optional[Dict[str, Any]] = None

# Hayrat darajalari
_SURPRISE_HIGH = 0.75    # kutilmagan — chuqurroq ishlov kerak
_SURPRISE_LOW  = 0.35    # kutilgan — odatiy oqim


def _blank() -> Dict[str, Any]:
    return {
        "pending": [],        # [{prediction, probability, ts}] — keyingi navbat uchun
        "history": [],        # [{expected, actual, error, ts}]
        "turns": 0,
        "avg_error": 0.5,
    }


def _load() -> Dict[str, Any]:
    global _state
    if _state is not None:
        return _state
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("pending", [])
            data.setdefault("history", [])
            data.setdefault("turns", 0)
            data.setdefault("avg_error", 0.5)
            _state = data
            return _state
    except Exception as e:
        log.warning("[PP-1] yuklash xato: %s", e)
    _state = _blank()
    return _state


def _save() -> None:
    if _state is None:
        return
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        tmp = _STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False)
        os.replace(tmp, _STATE_PATH)   # atomik
    except Exception as e:
        log.warning("[PP-1] saqlash xato: %s", e)


def reset() -> None:
    global _state
    with _lock:
        _state = _blank()
        _save()


# ── Xato hisoblash ───────────────────────────────────────────────────────────

import re as _re

# Mazmunsiz so'zlar — RU / EN / UZ. Bularni qoldirsak birlashma shishadi
# va bir xil mavzu davomi ham "kutilmagan" bo'lib chiqadi.
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of",
    "in", "on", "at", "for", "and", "or", "but", "it", "its", "this", "that",
    "i", "you", "he", "she", "we", "they", "my", "your", "me", "has", "have",
    "had", "do", "does", "did", "so", "if", "then", "than", "about", "with",
    "right", "ok", "okay", "tell", "say", "just", "not", "no", "yes",
    "и", "в", "на", "с", "по", "что", "это", "как", "не", "я", "ты", "мы",
    "он", "она", "они", "мой", "твой", "есть", "был", "была", "было", "да",
    "нет", "же", "ли", "бы", "или", "но", "к", "у", "за", "о", "от",
    "va", "bilan", "uchun", "bu", "shu", "men", "sen", "biz", "ular", "ham",
    "yoki", "lekin", "ha", "yo'q", "juda", "nima", "qanday",
}

_WORD = _re.compile(r"[^\W\d_]{2,}", _re.UNICODE)


def _content_words(text: str) -> set:
    """Mazmunli so'zlar to'plami — to'xtash so'zlarisiz."""
    return {w for w in (m.lower() for m in _WORD.findall(text or ""))
            if w not in _STOP}


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _error(expected: str, actual: str) -> float:
    """Bashorat vs haqiqat farqi: 0.0 (kutilgan) .. 1.0 (butunlay boshqa).

    O'lchov — QAMROV, simmetrik o'xshashlik emas. To'g'ri savol:
    "men kutgan narsa sodir bo'ldimi?" Foydalanuvchi mavzuni davom
    ettirib qo'shimcha so'z ishlatsa, bu hayrat emas.

    Simmetrik Jaccard buni noto'g'ri o'lchardi:
      kutgan  'tell about recursion python'
      haqiqat 'recursion in python has a depth limit right'
      Jaccard -> 0.80 (kutilmagan)   QAMROV -> 0.00 (kutilgan) ✓
    """
    exp_w = _content_words(expected)
    act_w = _content_words(actual)
    if not exp_w:
        return 1.0            # bashorat yo'q — hamma narsa kutilmagan
    if not act_w:
        return 1.0
    covered = len(exp_w & act_w) / len(exp_w)
    return round(max(0.0, min(1.0, 1.0 - covered)), 3)


# ── Asosiy API ───────────────────────────────────────────────────────────────

def score_turn(query: str) -> Dict[str, Any]:
    """Joriy savolni OLDINGI navbatda qilingan bashorat bilan solishtiradi.

    Kontekst yig'ilishidan OLDIN chaqiriladi — javob shu natijadan
    ta'sirlanishi kerak.

    Returns: {surprise, expected, was_predicted, level, turns}
    """
    with _lock:
        st = _load()
        pending: List[Dict[str, Any]] = st.get("pending") or []

        if not pending:
            # Birinchi navbat — solishtirish uchun bashorat yo'q
            out = {"surprise": None, "expected": "", "was_predicted": False,
                   "level": "unknown", "turns": st["turns"]}
            return out

        # Eng yaxshi mos keluvchi bashoratni topamiz
        errors = [(_error(p.get("prediction", ""), query), p) for p in pending]
        errors.sort(key=lambda x: x[0])
        best_err, best = errors[0]

        st["turns"] += 1
        st["history"].append({
            "expected": best.get("prediction", "")[:80],
            "actual":   (query or "")[:80],
            "error":    best_err,
            "ts":       time.time(),
        })
        del st["history"][:-_HISTORY_LEN]

        # Yugurib boruvchi o'rtacha — model qanchalik yaxshi bashorat qilyapti
        st["avg_error"] = round(st["avg_error"] * 0.8 + best_err * 0.2, 3)
        st["pending"] = []          # bashorat ishlatildi
        _save()

        level = ("high" if best_err >= _SURPRISE_HIGH else
                 "low"  if best_err <= _SURPRISE_LOW  else "medium")

        log.info("[PP-1] hayrat=%.2f (%s) kutgan='%s'",
                 best_err, level, best.get("prediction", "")[:40])

        return {
            "surprise":      best_err,
            "expected":      best.get("prediction", ""),
            "was_predicted": best_err <= _SURPRISE_LOW,
            "level":         level,
            "turns":         st["turns"],
            "avg_error":     st["avg_error"],
        }


def predict_next(query: str, reply: str = "", context: Optional[List[str]] = None) -> List[str]:
    """Keyingi navbat uchun bashorat qiladi va saqlaydi.

    Javob berilgandan KEYIN chaqiriladi (on_user_message).
    """
    preds: List[Dict[str, Any]] = []

    # 1) predictive_layer mavjud bo'lsa — uning naqsh bazasidan
    try:
        import predictive_layer as pl
        layer = pl.get_predictive_layer()
        ctx = list(context or [])
        if query:
            ctx.append(query)
        raw = layer.predict_next_request(ctx) or []
        for r in raw[:3]:
            p = r.get("prediction") if isinstance(r, dict) else str(r)
            if p:
                preds.append({"prediction": p,
                              "probability": float(r.get("probability", 0.3))
                              if isinstance(r, dict) else 0.3})
        # Model yangilanadi — haqiqat kelgani bilan
        if query:
            layer.update_patterns(query, was_predicted=False)
    except Exception as e:
        log.debug("[PP-1] predictive_layer yo'q yoki xato: %s", e)

    # 2) Zaxira: mavzu davomiyligi gipotezasi.
    #    Odam odatda mavzuni davom ettiradi — bu tekshiriladigan bashorat.
    if not preds and query:
        words = [w for w in _normalize(query).split() if len(w) > 3][:4]
        if words:
            preds.append({"prediction": " ".join(words), "probability": 0.25})

    with _lock:
        st = _load()
        st["pending"] = [{**p, "ts": time.time()} for p in preds[:3]]
        _save()

    return [p["prediction"] for p in preds]


def get_context_for_llm(query: str = "") -> str:
    """LLM uchun bashorat holati.

    Faqat MA'NOLI bo'lsa chiqadi: hayrat yuqori yoki juda past bo'lganda.
    O'rtacha holatda jim turadi — bu bo'lim doimiy matnga aylanmasligi uchun.
    """
    with _lock:
        st = _load()
        hist = st.get("history") or []
        if not hist:
            return ""
        last = hist[-1]

    err = last.get("error")
    if err is None:
        return ""

    if err >= _SURPRISE_HIGH:
        return (f"[BASHORAT] Kutmagan burilish ({err:.0%}) — "
                f"kutgan edim: '{last.get('expected', '')[:40]}'. "
                f"Mavzu o'zgardi, diqqat qayta yo'naltirildi.")
    if err <= _SURPRISE_LOW:
        return f"[BASHORAT] Kutilgan davom ({err:.0%}) — mavzu bir xil."
    return ""


def get_stats() -> Dict[str, Any]:
    with _lock:
        st = _load()
        hist = list(st.get("history") or [])
    if not hist:
        return {"turns": 0, "avg_error": None, "history": 0}
    errs = [h["error"] for h in hist if h.get("error") is not None]
    return {
        "turns":      st.get("turns", 0),
        "avg_error":  st.get("avg_error"),
        "last_error": errs[-1] if errs else None,
        "min_error":  min(errs) if errs else None,
        "max_error":  max(errs) if errs else None,
        "history":    len(hist),
        "pending":    len(st.get("pending") or []),
    }
