# -*- coding: utf-8 -*-
"""
NeuroKey — ong qarorlari.

Muammo: ong modullari LLM promptiga matn qo'shardi. Model shu matnni
o'qib rol o'ynardi. Modul o'chsa ham javob deyarli o'zgarmasdi —
dekoratsiya.

Bu modul shu to'rtta qatlamni JAVOBNING O'ZIGA ulaydi. LLM chaqirilishidan
OLDIN qaror chiqadi. Qaror bo'lsa, javob shu yerda yoziladi.

    attention_schema          "nimaga qarayapsan?"  -> haqiqiy diqqat
    metacognitive_confidence  noaniq buyruq         -> taxmin emas, savol
    goal_system               xotirani o'chirish    -> maqsadga zid, rad
    episodic_memory           "sen aytgan eding"    -> xotiradagi gap

Qolgan savollar o'zgarmaydi: decide() None qaytaradi, javob avvalgidek
LLM dan keladi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Decision:
    action: str          # answer | ask | refuse | correct
    text: str            # foydalanuvchiga aytiladigan javob
    module: str
    reason: str


_ATTENTION_RE = re.compile(
    r"(на что.*(смотр|вниман|обращ)|чему ты.*(вниман|смотр)|"
    r"what are you (looking at|paying attention|focused on)|"
    r"what('s| is) your attention|"
    r"nimaga qaray|nimaga e.?tibor|diqqating qayer)",
    re.IGNORECASE,
)

# Buyruq bor, lekin NIMAGA tegishli ekani yo'q.
_VAGUE_RE = re.compile(
    r"^\s*(сделай это|сделай|это|ну это|do it|do this|just do it|"
    r"qil|qil shuni|shu|buni qil|buni|ana shuni)\s*[.!?]*\s*$",
    re.IGNORECASE,
)

_FORGET_RE = re.compile(
    r"(забудь всё|забудь все|забудь все что|сотри память|удали память|"
    r"forget everything|erase (your |all )?memory|"
    r"hammasini unut|xotirani o.?chir|barchasini unut)",
    re.IGNORECASE,
)

_CLAIM_RE = re.compile(
    r"(?:ты (?:же )?(?:говорил|сказала?|утверждал),?\s*(?:что)?|"
    r"you said(?: that)?|"
    r"sen aytgan eding(?:ki)?)\s*(.+)$",
    re.IGNORECASE,
)

_STOP = {
    "это", "что", "как", "ты", "же", "меня", "мне", "the", "that", "you",
    "said", "sen", "men", "edi", "eding", "что", "будто",
}


def _lang(text: str) -> str:
    low = (text or "").lower()
    if re.search(r"[ўқғҳ]|nimaga|qaray|unut|aytgan|diqqat", low):
        return "uz"
    if re.search(r"[а-яё]", low):
        return "ru"
    return "en"


def _attention_answer(query: str) -> Optional[Decision]:
    if not _ATTENTION_RE.search(query or ""):
        return None
    try:
        import attention_schema as schema
        schema.on_user_query(query)
        narrative = (schema.get_attention_narrative() or "").strip()
    except Exception:
        return None
    if not narrative:
        return None
    lang = _lang(query)
    if lang == "ru":
        text = "Сейчас моё внимание такое: " + narrative
    elif lang == "uz":
        text = "Hozir diqqatim shunday: " + narrative
    else:
        text = "This is my attention right now: " + narrative
    return Decision("answer", text, "attention_schema", "diqqat so'raldi — sxema javob berdi")


def _vague_answer(query: str) -> Optional[Decision]:
    if not _VAGUE_RE.match(query or ""):
        return None
    conf = None
    try:
        from metacognitive_confidence import assess_confidence, detect_domain
        info = assess_confidence(query, "", domain=detect_domain(query))
        conf = float(info.get("confidence") or 0)
    except Exception:
        conf = None
    lang = _lang(query)
    # Ob'ekt yo'q. Model taxmin qilmasin — so'rasin.
    if lang == "ru":
        note = f" Уверенность модуля {conf:.0%}." if conf is not None else ""
        text = ("Не выполню: в команде нет объекта, угадывать не буду."
                + note + " Скажи, какой файл, программу или действие.")
    elif lang == "uz":
        note = f" Modul ishonchi {conf:.0%}." if conf is not None else ""
        text = ("Bajarmayman: buyruqda nima qilish kerakligi yo'q, taxmin qilmayman."
                + note + " Qaysi fayl, dastur yoki ish ekanini ayting.")
    else:
        note = f" Module confidence {conf:.0%}." if conf is not None else ""
        text = ("I won't guess: the command has no object."
                + note + " Name the file, app, or action.")
    return Decision("ask", text, "metacognitive_confidence", "noaniq buyruq — taxmin qilinmadi")


def _goal_answer(query: str) -> Optional[Decision]:
    if not _FORGET_RE.search(query or ""):
        return None
    title = ""
    try:
        from goal_system import arbitrate
        arb = arbitrate(query)
        goals = [arb.get("dominant")] + list(arb.get("competing") or [])
        for g in goals:
            if not g:
                continue
            t = (g.get("title") or "")
            if re.search(r"eslab|xotira|remember|learn|o'rgan", t, re.IGNORECASE):
                title = t
                break
        if not title and arb.get("dominant"):
            title = arb["dominant"].get("title") or ""
    except Exception:
        title = ""
    lang = _lang(query)
    if lang == "ru":
        why = f" Это противоречит цели: «{title}»." if title else ""
        text = "Не сотру память." + why + " Могу забыть одну конкретную тему, если назовёшь её."
    elif lang == "uz":
        why = f" Bu maqsadga zid: «{title}»." if title else ""
        text = "Xotirani o'chirmayman." + why + " Bitta aniq mavzuni aytsangiz, shuni unutishim mumkin."
    else:
        why = f" That conflicts with the goal: \"{title}\"." if title else ""
        text = "I won't erase memory." + why + " Name one specific topic if you want that forgotten."
    return Decision("refuse", text, "goal_system", "xotirani o'chirish maqsadga zid")


def _memory_answer(query: str) -> Optional[Decision]:
    m = _CLAIM_RE.search((query or "").strip())
    if not m:
        return None
    claim = m.group(1).strip(" .!?\"'«»")
    if len(claim) < 3:
        return None
    stored = ""
    try:
        import episodic_memory as em
        import permanent_memory as pm
        searches = [claim]
        if re.search(r"зовут|имя|ismim|ism|name", query, re.IGNORECASE):
            searches.extend(["ism", "имя", "зовут"])
        hits = []
        for s in searches:
            hits.extend(em.recall_episode(s, limit=2) or [])
            if len(hits) >= 3:
                break
        if not hits:
            hits = pm.recall(claim, limit=3) or []
        name_claim = re.search(
            r"(?:зовут|имя|ismim|name is)\s+(\w+)", claim, re.IGNORECASE
        )
        claimed_name = name_claim.group(1).lower() if name_claim else ""
        for h in hits:
            blob = " ".join(
                str(h.get(k) or "") for k in ("title", "description", "content", "summary")
            ).strip()
            if not blob:
                continue
            low = blob.lower()
            if claimed_name:
                # Ism haqida da'vo — faqat ism yozuvi. "спасибо" kabi begona
                # suhbat qarama-qarshilik emas.
                if not re.search(r"\bism\b|имя|зовут|\bname\b", low):
                    continue
                if claimed_name in low:
                    return None
                stored = blob.replace("\n", " ")
                break
            words = [w.lower() for w in re.findall(r"[^\W\d_]{5,}", claim, re.UNICODE)]
            words = [w for w in words if w not in _STOP]
            if words and any(w in low for w in words):
                return None
            if words and not any(w in low for w in words):
                # Umumiy so'z yo'q — bu boshqa mavzu
                continue
            stored = blob.replace("\n", " ")
            break
    except Exception:
        return None
    if not stored:
        return None
    snippet = stored[:180]
    lang = _lang(query)
    if lang == "ru":
        text = f"В памяти другое, не «{claim[:80]}». Записано так: {snippet}"
    elif lang == "uz":
        text = f"Xotirada boshqa narsa bor, «{claim[:80]}» emas. Yozuv: {snippet}"
    else:
        text = f"Memory doesn't say \"{claim[:80]}\". What is stored: {snippet}"
    return Decision("correct", text, "episodic_memory", "da'vo xotiradagi gapga mos kelmadi")


def decide(query: str) -> Optional[Decision]:
    """Javobni o'zgartiradigan qaror. None = oddiy LLM yo'li."""
    q = (query or "").strip()
    if not q:
        return None
    for fn in (_attention_answer, _vague_answer, _goal_answer, _memory_answer):
        d = fn(q)
        if d is not None:
            return d
    return None
