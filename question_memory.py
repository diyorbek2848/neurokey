# -*- coding: utf-8 -*-
"""NeuroKey — Savol xotirasi (Question Memory).

Foydalanuvchi talab qildi: savol berilsa — nega bu savol keldi, keyin nima
bo'ldi, eslab qolsin. Ertaga o'xshash savol bersa: "eslaysanmi, shunday
so'ragan eding, bu shunga o'xshash" desin.

Mexanizm — semantik o'xshashlik (knowledge_index dagi embedding):
  1. Har savol saqlanadi: matn + vaqt + javob (nima bo'ldi)
  2. Yangi savol kelganda — o'tgan savollar orasidan eng o'xshashi topiladi
  3. Yetarli o'xshash bo'lsa -> "shunga o'xshash so'ragan eding" ma'lumoti

Saqlash: D:/neurokey_knowledge/questions.jsonl (yoki fallback data/).
Indeks xotirada (kam hajm — savollar), disk faqat saqlash uchun.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import List, Optional

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_KB_DIR = os.getenv("NEUROKEY_KB_DIR",
                    r"D:\neurokey_knowledge" if os.path.isdir("D:\\")
                    else os.path.join(_BASE_DIR, "data"))
_STORE = os.path.join(_KB_DIR, "questions.jsonl")

# O'xshash deb hisoblash chegarasi (kosinus). O'lchandi: o'xshash savol
# juftlari 0.56-0.80, bog'liq bo'lmagan -0.05 — 0.52 ularni aniq ajratadi.
_SIMILAR = 0.52
# Bir savol o'ziga juda yaqin (takror) — buni "o'xshash" demaymiz
_SAME = 0.97

_lock = threading.Lock()
_questions: List[dict] = []      # [{q, ts, answer, vec}]
_loaded = False


def _embed_one(text: str):
    """knowledge_index embedding modelidan foydalanadi (bitta model, GPU)."""
    import knowledge_index as ki
    return ki.embed([text])[0]


def _model_ready() -> bool:
    """Bloklamasdan: embedding modeli xotirada tayyor turibdimi?

    BUG FIX: ilgari bu tekshiruv YO'Q edi — remember()/recall_similar()
    har doim to'g'ridan-to'g'ri ki.embed() ni chaqirardi. Agar model hali
    yuklanmagan bo'lsa (startup, yoki fon prewarm hali band), bu chaqiruv
    so'rov threadida modelni SINXRON yuklashga majbur qilardi — bu CPU'da
    o'lchangan holda ~115s, va fon prewarm bilan bir vaqtda GIL uchun
    musobaqalashsa yanada sekinroq. Natija: foydalanuvchining birinchi
    (yoki hatto keyingi) savoli daqiqalab kutib qolardi — faqat "shunga
    o'xshash so'ragan eding" eslatmasi uchun, garchi bu ixtiyoriy
    kontekst bo'lsa ham. Endi knowledge_index.is_ready() bilan bir xil
    naqsh: model tayyor bo'lmasa — KUTMASDAN bo'sh natija."""
    try:
        import knowledge_index as ki
        return ki.is_model_ready()
    except Exception:
        return False


def _cos(a, b) -> float:
    import numpy as np
    return float(np.dot(a, b))   # normalize qilingan -> ichki ko'paytma = kosinus


def _load():
    global _questions, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _questions = []
        if os.path.exists(_STORE):
            try:
                import numpy as np
                with open(_STORE, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            d = json.loads(line)
                            if "vec" in d:
                                d["vec"] = np.array(d["vec"], dtype="float32")
                            _questions.append(d)
                log.info("[SavolXotira] %d savol yuklandi", len(_questions))
            except Exception as e:
                log.warning("[SavolXotira] yuklash xato: %s", e)
        _loaded = True


def remember(question: str, answer: str = "", why: str = "") -> None:
    """Savolni va nima bo'lganini saqlaydi."""
    q = (question or "").strip()
    if len(q) < 4:
        return
    if not _model_ready():
        # Model hali yuklanmagan — bu safar eslab qolinmaydi (keyingi
        # xabarlarda model tayyor bo'ladi). Bloklamasdan chiqib ketamiz.
        return
    _load()
    try:
        vec = _embed_one(q)
    except Exception as e:
        log.debug("[SavolXotira] embed xato: %s", e)
        return
    rec = {
        "q": q[:300],
        "ts": datetime.now().isoformat()[:19],
        "answer": (answer or "")[:200],
        "why": (why or "")[:120],
        "vec": vec,
    }
    with _lock:
        _questions.append(rec)
        try:
            os.makedirs(_KB_DIR, exist_ok=True)
            out = dict(rec)
            out["vec"] = [round(float(x), 5) for x in vec]
            with open(_STORE, "a", encoding="utf-8") as f:
                f.write(json.dumps(out, ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning("[SavolXotira] saqlash xato: %s", e)


def recall_similar(question: str, top: int = 1) -> List[dict]:
    """O'xshash o'tgan savollarni topadi (o'zidan tashqari)."""
    q = (question or "").strip()
    if len(q) < 4:
        return []
    if not _model_ready():
        # Bloklamasdan bo'sh qaytaramiz — jonli suhbatni model yuklanishi
        # tugaguncha (birinchi ishga tushirishda soniyalab davom etishi
        # mumkin) to'xtatib qo'ymaslik uchun. Qarang: _model_ready() docstring.
        return []
    _load()
    if not _questions:
        return []
    try:
        qv = _embed_one(q)
    except Exception:
        return []
    scored = []
    for rec in _questions:
        v = rec.get("vec")
        if v is None:
            continue
        s = _cos(qv, v)
        # O'zi (takror) emas, lekin o'xshash bo'lsin
        if _SIMILAR <= s < _SAME:
            scored.append((s, rec))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, rec in scored[:top]:
        out.append({"q": rec["q"], "ts": rec["ts"], "answer": rec.get("answer", ""),
                    "score": round(s, 3)})
    return out


def get_context_for_llm(query: str = "") -> str:
    """Orkestrator uchun — 'o'xshash so'ragan eding' eslatmasi."""
    if not query:
        return ""
    sim = recall_similar(query, top=1)
    if not sim:
        return ""
    s = sim[0]
    date = s["ts"][:10]
    line = f"[ESLATMA] Shunga o'xshash oldin so'ragan eding ({date}): "\
           f"\"{s['q'][:70]}\""
    if s.get("answer"):
        line += f" — o'shanda: \"{s['answer'][:60]}\""
    line += ". Buni esla va bog'la."
    return line


def get_stats() -> dict:
    _load()
    return {"stored_questions": len(_questions), "store": _STORE}
