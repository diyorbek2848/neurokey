# -*- coding: utf-8 -*-
"""NeuroKey — Bashoratli oldindan javob (Speculative Pre-Response).

MUAMMO (asoschi so'roviga ko'ra, 2026-09-11): odam suhbatda gapni oxirigacha
kutib o'tirmaydi — suhbatdosh hali gapirayotganda, eshitilgan qism asosida
javobni miyada shakllantira boshlaydi. Gap tugashi bilan, agar oxiri
kutganidek chiqqan bo'lsa, DEYARLI 0 kechikish bilan javob beradi. Agar
oxirida kutilmagan burilish chiqsa — boshlagan fikrini TASHLAB, qaytadan
o'ylaydi.

Bundan oldin NeuroKey'da bu YO'Q edi: STT (Vosk) yakuniy transkriptni
berguncha HECH QANDAY javob tayyorlash boshlanmasdi — ketma-ket
(tinglash -> tugagach o'ylash -> javob) edi, parallel emas.
(Tekshirilgan: prediction_error.py/predictive_layer.py faqat "keyingi
NAVBATDA foydalanuvchi nima so'raydi" (butun savol darajasida, navbat
tugagach) bashorat qiladi — bu boshqa narsa. inner_speech.py'dagi
"parallel" ham STT bilan emas, YAKUNIY transkript tayyor bo'lgandan
keyingi kontekst-yig'ish bosqichi bilan parallel edi.)

Bu modul aynan yetishmagan qismni qo'shadi:
  - STT hali GAPNI TUGATMAGAN paytda (o'sish davomidagi PARTIAL
    transkript asosida) — fon oqimda TO'LIQ javob (haqiqiy LLM
    chaqiruvi bilan) tayyorlanadi.
  - STT gapni tugatib, YAKUNIY transkript kelgach — solishtiriladi:
    yakuniy matn bashorat uchun ishlatilgan (qisman) matnni yetarlicha
    "qamrab olsa" (foydalanuvchi oxirida mavzuni burmagan bo'lsa) ->
    tayyor javob DARHOL qaytariladi.
    Aks holda (mos kelmasa) -> None qaytadi, chaqiruvchi ODATDAGI
    to'liq (butun kontekst bilan) yo'lni ishlatishi kerak — HECH QACHON
    noto'g'ri/eskirgan javob majburan ishlatilmaydi.

MUHIM CHEKLOV (ochiq aytilishi kerak): bu yerdagi bashorat javobi
main.py'dagi asosiy pipeline'ning to'liq ~40 qatlamli ong kontekstidan
FOYDALANMAYDI (llm_router.answer() faqat matnning o'zi bilan chaqiriladi
— shaxsiyat/emotsiya/yuz-tanish kabi identity_core darajasidagi kontekst
hamon ishlaydi, lekin orchestrator/consciousness_orchestrator'ning og'ir
xotira-qatlamlari YO'Q). Sabab: to'liq kontekstni STT hali tugamagan
paytda oldindan yig'ish uchun main.py'ning butun handle_text() funksiyasini
qayta yozish kerak bo'lardi (7000+ qatorli, chuqur holat bilan bog'liq) —
bu xavfli. Shuning uchun bu yerda ONGLI RAVISHDA yengilroq, lekin darhol
gapira oladigan javob variantini tanladik: agar mos kelmasa baribir
tashlab yuboriladi, mos kelsa esa "kontekst biroz kambag'alroq, lekin
DARHOL aytilgan" javob — "sekin, lekin to'liq" dan ko'ra insonga
yaqinroq tajriba beradi.

XAVFSIZLIK: butunlay IXTIYORIY — NEUROKEY_SPECULATIVE_RESPONSE=1
qilinmaguncha hech narsa qilmaydi (mavjud demo xatti-harakati
o'zgarmaydi). Har qanday ichki xato jim yutiladi — bu modul HECH QACHON
asosiy pipeline'ni bloklamaydi yoki uni to'xtatmaydi, faqat "bor-yo'g'i
tezlashtirish" sifatida ishlaydi (o'chirilgan hollarda yoki xato bo'lsa —
oddiy sekin-lekin-ishonchli yo'l ishlayveradi).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

# ── Sozlamalar ────────────────────────────────────────────────────────────────
_MIN_WORDS        = 4     # partial kamida shuncha so'zdan iborat bo'lsin
_MIN_NEW_WORDS    = 3     # oldingi urinishdan beri kamida shuncha YANGI so'z qo'shilgan bo'lsin
_MIN_INTERVAL_SEC = 0.6   # ketma-ket urinishlar orasidagi eng kam vaqt (LLM'ni bosib ketmaslik uchun)
_MIN_COVERAGE     = 0.92  # yakuniy matn bashorat qilingan qismni shuncha % qamrab olishi kerak

_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)


def _enabled() -> bool:
    return (os.getenv("NEUROKEY_SPECULATIVE_RESPONSE", "0") or "0").strip().lower() in ("1", "true", "yes")


def _content_words(text: str) -> set:
    return {w.lower() for w in _WORD.findall(text or "")}


def _coverage(expected_partial: str, actual_final: str) -> float:
    """actual_final matni expected_partial (oldinroq eshitilgan, qisqaroq)
    qismini qanchalik qamrab olganini qaytaradi (0..1).

    QAMROV — simmetrik o'xshashlik EMAS (prediction_error._error() bilan
    bir xil mantiq, ataylab): foydalanuvchi mavzuni davom ettirib
    qo'shimcha so'z qo'shsa, bu "kutilmagan" hisoblanmasligi kerak —
    faqat bashorat qilingan qism yakuniy matnda ALLAQACHON bormi, shuni
    tekshiramiz."""
    exp_w = _content_words(expected_partial)
    if not exp_w:
        return 0.0
    act_w = _content_words(actual_final)
    if not act_w:
        return 0.0
    return len(exp_w & act_w) / len(exp_w)


_lock = threading.Lock()
_state: Dict[str, Any] = {
    "generation": 0,          # har yangi urinishda +1 — eskisi (agar hali tugallanmagan bo'lsa) e'tiborsiz qoldiriladi
    "partial_used": "",       # oxirgi TUGALLANGAN urinishda ishlatilgan partial matn
    "reply": None,            # tayyor javob matni (yoki hali/hech yo'q bo'lsa None)
    "started_ts": 0.0,
    "done_ts": 0.0,
    "in_flight_partial": "",  # hozir fon oqimda ishlanayotgan partial
}


def reset() -> None:
    """Yangi navbat/aylanish boshlanganda (masalan foydalanuvchi to'xtab,
    keyin qaytadan gapira boshlaganda) eski holatni tozalash uchun."""
    with _lock:
        _state["generation"] += 1
        _state["partial_used"] = ""
        _state["reply"] = None
        _state["in_flight_partial"] = ""
        _state["started_ts"] = 0.0
        _state["done_ts"] = 0.0


def on_partial(partial_text: str, lang_hint: Optional[str] = None) -> None:
    """STT hali gapni TUGATMAGAN paytda, o'sib borayotgan partial transkript
    bilan chaqiriladi (masalan stt_vosk.py'ning partial-natija shoxobchasidan).

    Chaqiruvchini HECH QACHON bloklamaydi — darhol qaytadi, ish fon
    thread'da davom etadi."""
    if not _enabled():
        return
    try:
        partial_text = (partial_text or "").strip()
        if not partial_text:
            return
        words = partial_text.split()
        if len(words) < _MIN_WORDS:
            return

        with _lock:
            prev = _state["in_flight_partial"]
            now = time.monotonic()
            if prev:
                prev_words = len(prev.split())
                if (len(words) - prev_words) < _MIN_NEW_WORDS:
                    return
                if (now - _state.get("started_ts", 0.0)) < _MIN_INTERVAL_SEC:
                    return
            _state["generation"] += 1
            gen = _state["generation"]
            _state["in_flight_partial"] = partial_text
            _state["started_ts"] = now

        def _run():
            reply = None
            try:
                from llm_router import answer as _ans
                reply = _ans(partial_text, lang_hint=lang_hint, brief=False) or None
            except Exception as e:
                log.debug("[Speculative] generatsiya xato: %s", e)
                reply = None
            try:
                with _lock:
                    if _state["generation"] != gen:
                        return  # bu urinish eskirgan — yangi partial kelib ulgurgan, natija tashlanadi
                    _state["partial_used"] = partial_text
                    _state["reply"] = reply
                    _state["done_ts"] = time.monotonic()
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True, name="NK-Speculative").start()
    except Exception as e:
        log.debug("[Speculative] on_partial xato: %s", e)


def get_speculative_if_matching(final_text: str, min_coverage: float = _MIN_COVERAGE) -> Optional[str]:
    """Yakuniy transkript tayyor bo'lganda chaqiriladi.

    Agar so'nggi TUGALLANGAN bashorat yakuniy matnni yetarlicha qamrab
    olgan bo'lsa (foydalanuvchi oxirida mavzuni burmagan) — tayyor javobni
    qaytaradi (chaqiruvchi buni DARHOL ishlatishi mumkin — deyarli 0
    kechikish). Aks holda None — chaqiruvchi ODATDAGI to'liq yo'lni
    davom ettirishi kerak.

    Hech qachon False-positive bermaydi deb KAFOLAT bermaydi (buni
    hech narsa bera olmaydi — inson ham xato taxmin qiladi), lekin
    min_coverage yuqori (0.92) qilib qo'yilgan — noaniq holatda ODATDAGI
    yo'l afzal ko'riladi."""
    if not _enabled():
        return None
    try:
        final_text = (final_text or "").strip()
        if not final_text:
            return None
        with _lock:
            reply = _state.get("reply")
            used = _state.get("partial_used", "")
            started = _state.get("started_ts", 0.0)
            done = _state.get("done_ts", 0.0)
        if not reply or not used:
            return None
        if done <= 0 or done < started:
            return None  # hali tugallanmagan (juda tez tugadi gap)
        cov = _coverage(used, final_text)
        log.info("[Speculative] qamrov=%.2f kutilgan='%s' yakuniy='%s'",
                 cov, used[:50], final_text[:50])
        if cov >= min_coverage:
            # Ishlatildi — holatni tozalaymiz, keyingi (mutlaqo boshqa)
            # navbatga tasodifan qayta ishlatilib qolmasin.
            reset()
            return reply
        return None
    except Exception as e:
        log.debug("[Speculative] get_speculative_if_matching xato: %s", e)
        return None


def get_stats() -> Dict[str, Any]:
    with _lock:
        return {
            "enabled":       _enabled(),
            "has_reply":     _state.get("reply") is not None,
            "partial_used":  (_state.get("partial_used") or "")[:80],
            "generation":    _state.get("generation"),
        }
