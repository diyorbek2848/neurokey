# -*- coding: utf-8 -*-
"""NeuroKey — Metakognitiv nazorat (HOT-2 + HOT-3).

Butlin va boshq. (2023):
  HOT-2: "Metacognitive monitoring distinguishing reliable perceptual
          representations from noise"
  HOT-3: "Agency guided by a general belief-formation and action selection
          system, and a strong disposition to update beliefs in accordance
          with the outputs of metacognitive monitoring"

Ilgari ishonch (metacognitive_confidence) va hayrat (prediction_error)
alohida hisoblanardi, lekin ular HECH QANDAY HARAKATGA ta'sir qilmasdi.
`behavioral_engine` da ishonch = jadval + random.uniform() edi — soxta.

Bu modul halqani yopadi:

  KUZATISH (HOT-2):  hayrat + domen ishonchi + xotira qamrovi
                     -> bu javob ishonchlimi yoki shubhalimi?
  HARAKAT  (HOT-3):  ishonch past -> SO'RA / TEKSHIR / EHTIYOT BO'L
                     ishonch yuqori -> to'g'ridan javob ber

Natija LLM ga direktiv sifatida beriladi — u shunchaki ma'lumot emas,
xatti-harakatni o'zgartiradi.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# Harakat chegaralari
_ASK_THRESHOLD    = 0.40   # bundan past -> aniqlik so'rash
_VERIFY_THRESHOLD = 0.55   # bundan past -> tashqi tekshirish
_CONFIDENT_ABOVE  = 0.80   # bundan yuqori -> to'g'ridan javob


@dataclass
class MetaDecision:
    """Metakognitiv kuzatuvdan kelib chiqqan HARAKAT qarori."""
    reliability: float = 0.7          # 0..1 — bu javobga qanchalik ishonsa bo'ladi
    action: str = "answer"            # answer | hedge | clarify | verify
    hedge: str = ""                   # muqaddima ibora
    reason: str = ""                  # nega shu qaror

    def as_context_line(self) -> str:
        """LLM uchun direktiv — nima QILISH kerak."""
        if self.action == "clarify":
            return ("[METAKOGNITSIYA] Ishonch past ({:.0%}). "
                    "Darrov javob berma — avval aniqlashtiruvchi savol ber. "
                    "{}").format(self.reliability, self.reason)
        if self.action == "verify":
            return ("[METAKOGNITSIYA] Ishonch o'rtacha ({:.0%}). "
                    "Javob ber, lekin tekshirish kerakligini ayt yoki "
                    "manba so'ra. {}").format(self.reliability, self.reason)
        if self.action == "hedge":
            return ("[METAKOGNITSIYA] Ishonch cheklangan ({:.0%}). "
                    "'{}' bilan boshla, aniq bilmagan joyni tan ol."
                    ).format(self.reliability, self.hedge.strip())
        # answer
        return ("[METAKOGNITSIYA] Ishonch yuqori ({:.0%}). "
                "To'g'ridan, aniq javob ber.").format(self.reliability)


def decide(
    query: str = "",
    surprise: Optional[float] = None,
    domain_conf: Optional[float] = None,
    memory_hits: int = 0,
) -> MetaDecision:
    """Metakognitiv qaror: shu savolga qanday munosabatda bo'lish.

    Args:
        query:       foydalanuvchi savoli
        surprise:    PP-1 dan hayrat (0..1), None bo'lsa e'tiborsiz
        domain_conf: metacognitive_confidence dan domen ishonchi (0..1)
        memory_hits: xotiradan topilgan tegishli natijalar soni

    Returns: MetaDecision — harakat + sabab
    """
    # 1. Domen ishonchini olish (berilmagan bo'lsa hisoblaymiz)
    if domain_conf is None:
        try:
            import metacognitive_confidence as mc
            st = mc._load()
            dom = mc.detect_domain(query) if query else "general"
            domain_conf = st["domain_confidence"].get(dom, 0.70)
        except Exception:
            domain_conf = 0.70

    # 2. Hayratni olish (berilmagan bo'lsa PP-1 tarixidan)
    if surprise is None:
        try:
            import prediction_error as pe
            stats = pe.get_stats()
            surprise = stats.get("last_error")
        except Exception:
            surprise = None

    # 3. Ishonchlilikni hisoblash — HOT-2 kuzatuvi.
    #    Domen ishonchidan boshlanadi, hayrat va xotira qamrovi o'zgartiradi.
    reliability = float(domain_conf)

    if surprise is not None:
        # Yuqori hayrat -> kutilmagan -> ishonch tushadi
        reliability -= surprise * 0.35

    # Tegishli xotira topilgan bo'lsa -> ishonch oshadi (asos bor)
    if memory_hits >= 2:
        reliability += 0.15
    elif memory_hits == 0 and query:
        reliability -= 0.10   # hech narsa eslamadik -> ehtiyot

    reliability = max(0.05, min(0.99, round(reliability, 3)))

    # 4. Harakatni tanlash — HOT-3.
    if reliability < _ASK_THRESHOLD:
        action, reason = "clarify", "(kutilmagan yoki notanish so'rov)"
    elif reliability < _VERIFY_THRESHOLD:
        action, reason = "verify", "(qisman ma'lumot)"
    elif reliability < _CONFIDENT_ABOVE:
        action, reason = "hedge", ""
    else:
        action, reason = "answer", ""

    hedge = ""
    if action in ("hedge", "verify"):
        try:
            import metacognitive_confidence as mc
            hedge = mc.get_hedge_phrase(reliability)
        except Exception:
            hedge = "Taxminimcha, "

    dec = MetaDecision(reliability=reliability, action=action,
                       hedge=hedge, reason=reason)
    log.info("[HOT-3] reliability=%.2f action=%s (surprise=%s conf=%.2f hits=%d)",
             reliability, action, surprise, domain_conf, memory_hits)
    return dec


def get_context_for_llm(query: str = "") -> str:
    """Orkestrator uchun — metakognitiv direktiv qatori.

    Faqat MA'NOLI bo'lsa chiqadi: ishonch yuqori va hayrat past bo'lsa
    jim turadi (bu bo'lim doimiy matnga aylanmasligi uchun)."""
    dec = decide(query)
    # Ishonch juda yuqori bo'lsa direktiv shart emas — tabiiy javob
    if dec.action == "answer" and dec.reliability >= 0.88:
        return ""
    return dec.as_context_line()


def get_context_for_llm_full(query: str = "", surprise=None, memory_hits: int = 0) -> str:
    """Orkestrator uchun — hayrat va xotira qamrovi bilan to'liq qaror.

    Orkestrator allaqachon surprise (PP-1) va memory_hits ni hisoblagan,
    shuning uchun ularni qayta hisoblamasdan uzatadi."""
    dec = decide(query, surprise=surprise, memory_hits=memory_hits)
    if dec.action == "answer" and dec.reliability >= 0.88:
        return ""
    return dec.as_context_line()


def get_stats() -> dict:
    dec = decide("")
    return {"reliability": dec.reliability, "action": dec.action}
