# -*- coding: utf-8 -*-
"""NeuroKey Memory Search — Eski gaplashuvlardan relevant narsalarni topadi.

Xotirasiz suniy ong bo'lolmaydi. Bu modul gaplashuv davomida eski
suhbatlardan tegishli ma'lumotlarni topib, LLM kontekstiga qo'shadi.

Ishlash printsipi:
  1. Joriy savol so'zlari ajratiladi (stop-words o'chiriladi)
  2. memory.json history ichida har bir turn bilan overlap hisoblanadi
  3. Eng yuqori scored top-K turnlar qaytariladi
  4. LLM kontekstiga "ESKI XOTIRA" bloki sifatida qo'shiladi

Muhim: Vector DB ishlatilmaydi — faqat keyword overlap (tez, oflayn, past resurs).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import List, Dict, Optional

_MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "memory.json")
_MEMORY_LOG  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "memory_log.jsonl")

# Stop so'zlar — qidirishda e'tiborga olinmaydi
_STOP_RU = {
    "и","в","на","что","как","это","привет","да","нет","ок","the","a","is","to","for",
    "не","но","так","всё","все","ты","я","мне","он","она","они","им","у","из","с","к",
    "по","при","за","до","от","об","во","со","хорошо","ладно","окей","спасибо","пожалуйста",
    "можешь","можно","нужно","надо","скажи","расскажи","покажи","сделай","открой","закрой",
    "me","my","you","your","the","is","are","was","were","be","been","have","has","had",
    "do","did","does","will","would","could","should","may","might","shall",
}

# Cache — memory.json har yuklanishda cache-ga oliladi (30 soniya TTL)
_cache: Dict = {"turns": [], "loaded_at": 0.0, "mtime": 0.0}
_CACHE_TTL = 30.0  # sekund


def _tokenize(text: str) -> set:
    """Matnni token to'plamiga aylantiradi (stop so'zlarsiz, 3+ harf)."""
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", (text or "").lower())
    return {w for w in words if len(w) >= 3 and w not in _STOP_RU}


def _load_turns() -> List[Dict]:
    """memory.json va memory_log.jsonl dan barcha turnlarni yuklaydi (keshlanadi)."""
    global _cache
    now = time.time()

    # Cache hali yangi bo'lsa — qaytaramiz
    try:
        mtime = os.path.getmtime(_MEMORY_FILE) if os.path.exists(_MEMORY_FILE) else 0.0
    except OSError:
        mtime = 0.0

    if (now - _cache["loaded_at"]) < _CACHE_TTL and _cache["mtime"] == mtime:
        return _cache["turns"]

    turns: List[Dict] = []

    # 1. memory.json → history array
    try:
        with open(_MEMORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for turn in (data.get("history") or []):
            if turn.get("user") or turn.get("assistant"):
                turns.append({
                    "t": turn.get("t", 0),
                    "user": (turn.get("user") or "")[:500],
                    "assistant": (turn.get("assistant") or "")[:300],
                })
    except Exception:
        pass

    # 2. memory_log.jsonl — qo'shimcha history (dublikatlar bo'lishi mumkin, skip qilamiz)
    if os.path.exists(_MEMORY_LOG):
        existing_ts = {t["t"] for t in turns if t["t"]}
        try:
            with open(_MEMORY_LOG, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        ts = rec.get("t", 0)
                        if ts and ts not in existing_ts:
                            turns.append({
                                "t": ts,
                                "user": (rec.get("user") or "")[:500],
                                "assistant": (rec.get("assistant") or "")[:300],
                            })
                            existing_ts.add(ts)
                    except Exception:
                        pass
        except Exception:
            pass

    # Vaqt bo'yicha tartiblash (eng eski → eng yangi)
    turns.sort(key=lambda x: x.get("t", 0))

    _cache["turns"] = turns
    _cache["loaded_at"] = now
    _cache["mtime"] = mtime
    return turns


def search_memory(query: str, top_k: int = 4, min_score: int = 1,
                  skip_last_n: int = 6) -> List[Dict]:
    """Eski gaplashuvlardan joriy savol bilan bog'liq turnlarni topadi.

    Args:
        query:       Joriy foydalanuvchi matni
        top_k:       Nechta eng relevant turn qaytarilsin
        min_score:   Minimal overlap hisobi (kamida shu qadar umumiy so'z)
        skip_last_n: Oxirgi N turnni o'tkazib yuboramiz (ular allaqachon kontekstda)

    Returns:
        List of {"t", "user", "assistant", "score"} — relevance bo'yicha tartiblangan
    """
    if not query or not query.strip():
        return []

    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    turns = _load_turns()
    if not turns:
        return []

    # Oxirgi skip_last_n turnni o'tkazib yuboramiz
    if len(turns) > skip_last_n:
        turns = turns[:-skip_last_n]

    # Prefix uzunligi: qisqa so'zlar uchun kamroq, uzunlar uchun ko'proq
    # "telegram" (8) → prefix 5 → "teleg" = "telegrami"[:5] ✓
    def _prefix_overlap(q_toks: set, a_toks: set) -> int:
        """Exact match + prefix match (stem): 'telegram' ~ 'telegrami'."""
        score = 0
        for q in q_toks:
            plen = max(4, min(len(q), 6))  # 4–6 harf prefix
            q_pref = q[:plen]
            for a in a_toks:
                if q == a or a[:plen] == q_pref:
                    score += 1
                    break
        return score

    scored: List[tuple] = []
    for turn in turns:
        u_tokens = _tokenize(turn.get("user", ""))
        a_tokens = _tokenize(turn.get("assistant", ""))
        all_tokens = u_tokens | a_tokens
        overlap = _prefix_overlap(q_tokens, all_tokens)
        if overlap >= min_score:
            scored.append((overlap, turn))

    # Relevance bo'yicha tartiblash (yuqori → past)
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {**t, "score": s}
        for s, t in scored[:top_k]
    ]


def get_memory_context_for_llm(query: str, top_k: int = 3) -> str:
    """LLM ga beriladigan "eski xotira" bloki.
    Agar hech narsa topilmasa — bo'sh string qaytaradi.

    Qaytariladigan format:
        [ESKI XOTIRA — tegishli suhbatlar]
        Eski suhbat (2025-03-10): Sen: ... Men: ...
        ...
        [/ESKI XOTIRA]
    """
    results = search_memory(query, top_k=top_k, skip_last_n=6)
    if not results:
        return ""

    lines = []
    for r in results:
        ts = r.get("t", 0)
        date_str = ""
        if ts:
            try:
                from datetime import datetime
                date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except Exception:
                pass
        user_text = (r.get("user") or "")[:120].strip()
        asst_text = (r.get("assistant") or "")[:120].strip()
        if user_text or asst_text:
            line = f"  [{date_str}] Foydalanuvchi: {user_text}"
            if asst_text:
                line += f" → Men: {asst_text}"
            lines.append(line)

    if not lines:
        return ""

    return (
        "[ESKI XOTIRA — joriy savolga tegishli eski suhbatlar, eslash uchun ishlatilsin]\n"
        + "\n".join(lines)
        + "\n[/ESKI XOTIRA]"
    )


def invalidate_cache() -> None:
    """Yangi turn qo'shilgandan keyin keshni tozalash uchun."""
    _cache["loaded_at"] = 0.0
