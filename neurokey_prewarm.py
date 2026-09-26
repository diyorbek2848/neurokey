# -*- coding: utf-8 -*-
"""
NeuroKey — Ong Konteksti Pre-Warm (Consciousness Pre-Warmer).

Maqsad: User gapirib bo'lganda LLM ga uzatiluvchi ong konteksti
        ALLAQACHON tayyor tursin → 0ms (ketma-ket 200-400ms emas).

Qanday ishlaydi:
  - Startup da fon thread boshladi
  - Har 5 sekundda: valence, arousal, phenomenal, consciousness, narrative — yig'iladi
  - get_cached_context() → darhol qaytaradi (lock → string)
  - Groq connection pre-warm: birinchi real so'rov 0ms overhead
"""
from __future__ import annotations

import os
import threading
import time
import logging
from typing import Optional

log = logging.getLogger(__name__)

_REFRESH_SEC  = 5.0   # kontekst yangilanish davri
_MAX_AGE_SEC  = 15.0  # kesh eskirganligi limiti

# ── Global kesh ──────────────────────────────────────────────────────────────
_lock     = threading.Lock()
_ctx_cache: str   = ""
_updated:   float = 0.0
_ready:     bool  = False

_stop_ev  = threading.Event()
_thread:  Optional[threading.Thread] = None

# ── Groq connection pre-warm ──────────────────────────────────────────────────
_groq_warmed = False
_groq_lock   = threading.Lock()


def _groq_prewarm():
    """Groq bilan bitta minimal so'rov — TCP + TLS + auth oldindan ochilsin."""
    global _groq_warmed
    with _groq_lock:
        if _groq_warmed:
            return
        try:
            import os as _os
            _base_url = (
                _os.environ.get("OPENAI_BASE_URL", "")
                or ""
            )
            if "groq.com" not in _base_url:
                return  # Groq yoqilmagan — o'tkazib yuborish

            from openai import OpenAI as _OAI
            import httpx as _hx
            _cli = _OAI(
                api_key=_os.environ.get("GROQ_API_KEY", ""),
                base_url=_base_url,
                max_retries=0,
                http_client=_hx.Client(verify=False),
            )
            model = _os.environ.get("OPENAI_CHAT_MODEL", "openai/gpt-oss-20b")
            _cli.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                timeout=8,
            )
            _groq_warmed = True
            log.info("[Prewarm] Groq connection ishladi (iliq)")
            print("[PREWARM] Groq connection tayyor — birinchi javob tezroq")
        except Exception as _e:
            log.debug("[Prewarm] Groq prewarm: %s", _e)


_vecmem_warmed = False
_vecmem_lock   = threading.Lock()


def _vector_memory_prewarm():
    """vector_memory OpenAI embedding ulanishini fon threadida isitadi.

    BUG FIX (o'lchandi): jonli suhbatning birinchi 'semantik xotira'
    so'rovi (_vm.get_context_for_llm) 5-7s gacha cho'zilardi — sabab:
    `import openai` + yangi OpenAI mijoz yaratish + TCP/TLS/auth
    handshake hammasi SHU turnning o'zida, sinxron sodir bo'lardi.
    Endi xuddi Groq connection kabi — bularning hammasi startupda,
    fon threadida, foydalanuvchi hali gapirmasdan oldin bajariladi."""
    global _vecmem_warmed
    with _vecmem_lock:
        if _vecmem_warmed:
            return
        try:
            import vector_memory as _vm
            _vm.prewarm()
            _vecmem_warmed = True
            log.info("[Prewarm] vector_memory (OpenAI embedding) isitildi")
            print("[PREWARM] Semantik xotira (vector_memory) tayyor")
        except Exception as e:
            log.debug("[Prewarm] vector_memory prewarm: %s", e)


_facearc_warmed = False
_facearc_lock   = threading.Lock()


def _face_arc_prewarm():
    """InsightFace (ArcFace) 5 ta ONNX modelini fon threadida oldindan
    yuklaydi — xuddi Groq/vector_memory connection kabi.

    BUG FIX (o'lchandi, 2026-09-13): bu yuklash ilgari FAQAT birinchi
    identify() chaqiruvida (odatda kamera guard fon threadida, lekin
    nazariy jihatdan istalgan vaqtda) sodir bo'lardi — CPU rejimida ~5.8s
    davom etadi va shu vaqt oralig'ida boshqa threadlardagi oddiy Python
    operatsiyalarini ham (GIL/CPU raqobati orqali) sekinlashtiradi (qarang
    face_arc.prewarm() dagi batafsil izoh — bu real ORCH_SLOW_MODULE
    loglaridagi vector_memory.get_stats=22413ms va free_will_simulator.
    get_stats=2213ms kechikishlarining bir qismini tushuntiradi). Endi
    startupda, foydalanuvchi hali gapirmasdan oldin yuklanadi."""
    global _facearc_warmed
    with _facearc_lock:
        if _facearc_warmed:
            return
        try:
            import face_arc as _fa
            _fa.prewarm()
            _facearc_warmed = True
            log.info("[Prewarm] face_arc (InsightFace/ArcFace) isitildi")
            print("[PREWARM] Yuz tanish (ArcFace) modeli tayyor")
        except Exception as e:
            log.debug("[Prewarm] face_arc prewarm: %s", e)


def _build_context() -> str:
    """Barcha ong modullaridan kontekst yig'ish — fon threadda."""
    parts: list[str] = []

    # 1. Valence (hissiy holat — ijobiy/salbiy)
    try:
        from valence_state import get_valence
        v = get_valence()
        parts.append(f"Valence: {v:.2f}")
    except Exception:
        pass

    # 2. Arousal (qo'zg'alish darajasi)
    try:
        from arousal_state import get_arousal_for_llm
        ar = get_arousal_for_llm()
        if ar:
            parts.append(ar)
    except Exception:
        pass

    # 3. Phenomenal state (his-tuyg'u konteksti)
    try:
        from phenomenal_state import get_phenomenal_for_llm
        ph = get_phenomenal_for_llm("")
        if ph and len(ph) < 400:
            parts.append(ph)
    except Exception:
        try:
            from phenomenal_binding import get_context_for_llm
            ph2 = get_context_for_llm()
            if ph2:
                parts.append(ph2)
        except Exception:
            pass

    # 4. Consciousness (davomiy xotira, ichki fokus)
    try:
        from consciousness import get_consciousness
        cons = get_consciousness()
        if cons:
            from datetime import datetime
            ctx = cons.get_context_for_llm(
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                screen_summary="",
            )
            if ctx and len(ctx) < 800:
                parts.append(ctx)
    except Exception:
        pass

    # 5. Narrative O'zlik (men kim edim, kimman)
    try:
        from narrative_self import get_narrative_for_llm
        narr = get_narrative_for_llm(short=True)
        if narr and len(narr) < 300:
            parts.append(narr)
    except Exception:
        pass

    return "\n".join(p for p in parts if p)


def _prewarm_knowledge():
    """Bilim bazasi embedding modeli + indeksini oldindan yuklaydi.

    TARTIB MUHIM (bug fix): ilgari faqat ki.search("warmup") chaqirilardi —
    bu ICHKARIDA avval OGʻIR ishni (FAISS indeks + kb_meta.jsonl, o'lchandi:
    millionlab qatorli faylda o'nlab-yuzlab soniya) bajarib, MODELNI FAQAT
    SHUNDAN KEYIN yuklardi. Shu daqiqalab davom etadigan oraliqda
    knowledge_index.is_model_ready() False bo'lib qolardi va question_memory
    kabi modullar (agar ular ham himoyalanmagan bo'lsa) o'z ichida modelni
    QAYTA, mustaqil yuklashga urinishi mumkin edi.
    Endi MODEL BIRINCHI yuklanadi (o'lchandi: CPU'da ~115s, GPU mavjud
    bo'lsa ancha tezroq) — shundan keyin question_memory kabi yengil
    modullar tezda ishlay boshlaydi, og'ir FAISS indeks/meta esa fonda
    davom etadi."""
    try:
        import knowledge_index as ki
        ki.embed(["warmup"])   # FAQAT modelni yuklaydi — indeksni kutmaydi
        log.debug("[Prewarm] embedding modeli yuklandi")
    except Exception as e:
        log.debug("[Prewarm] embedding modeli yuklash: %s", e)
    try:
        import knowledge_index as ki
        ki.search("warmup")   # endi og'ir indeks + meta ham yuklanadi
        log.debug("[Prewarm] bilim bazasi indeksi yuklandi")
    except Exception as e:
        log.debug("[Prewarm] bilim bazasi yuklash: %s", e)
    try:
        import live_vision as lv
        lv.start()   # jonli ekran fon oqimini yoqadi
    except Exception:
        pass


def _worker():
    """Fon thread — har _REFRESH_SEC sekundda kontekst yangilanadi.

    TARTIB MUHIM (bug fix): oldin _prewarm_knowledge() BIRINCHI edi — agar
    bilim bazasi katta bo'lsa (masalan D:\\neurokey_knowledge — o'nlab GB,
    millionlab metadata qatori, sof Python bilan JSON qilib o'qiladi),
    bu daqiqalab davom etishi mumkin, va shu vaqt davomida ARZON/TEZ ong
    konteksti (_refresh_now — valence/arousal/consciousness/narrative,
    odatda <1s) ham HECH QACHON tayyor bo'lmas edi (get_cached_context()
    "" qaytarardi), garchi u bilim bazasiga umuman bog'liq bo'lmasa ham.
    Endi TEZ narsa BIRINCHI — foydalanuvchi ong konteksti fallback'idan
    (main.py) bir necha soniyada foyda ko'radi, og'ir bilim bazasi esa
    fonda davom etadi va tayyor bo'lgach avtomatik ishlatiladi.
    
    QOTIB QOLISHNING OLDINI OLISH: Hamma og'ir modellarni bir vaqtda 
    yuklamaslik uchun ular ketma-ket, kichik pauzalar bilan yuklanadi.
    """
    # Tez — ong konteksti (valence/arousal/consciousness/narrative)
    _refresh_now()
    
    # Startupdagi ilk TTS salomlashuv qotib qolmasligi uchun (GIL lock)
    _defer = float(os.getenv("NEUROKEY_PREWARM_DEFER_SEC", "15") or "15")
    if _defer > 0:
        time.sleep(_defer)

    # Sekin isitishlar — NEUROKEY_*_PREWARM=0 bo'lsa o'tkazib yuboriladi
    # (8 GB RAM / LITE tier). Ong modullari saqlanadi, faqat startda yuklanmaydi.
    _groq_prewarm()

    if os.getenv("NEUROKEY_VECTOR_PREWARM", "1").strip().lower() in ("1", "true", "yes"):
        time.sleep(2.0)
        _vector_memory_prewarm()

    if os.getenv("NEUROKEY_FACE_PREWARM", "0").strip().lower() in ("1", "true", "yes"):
        time.sleep(2.0)
        _face_arc_prewarm()

    if os.getenv("NEUROKEY_KB_PREWARM", "0").strip().lower() in ("1", "true", "yes"):
        time.sleep(2.0)
        _prewarm_knowledge()

    while not _stop_ev.is_set():
        _stop_ev.wait(_REFRESH_SEC)
        if _stop_ev.is_set():
            break
        _refresh_now()


def _refresh_now():
    global _ctx_cache, _updated, _ready
    t0 = time.monotonic()
    try:
        ctx = _build_context()
        elapsed = time.monotonic() - t0
        with _lock:
            _ctx_cache = ctx
            _updated   = time.monotonic()
            _ready     = True
        log.debug("[Prewarm] kontekst yangilandi %.0fms", elapsed * 1000)
    except Exception as e:
        log.debug("[Prewarm] xato: %s", e)


def start():
    """Prewarm boshlash — main.py startup da bir marta chaqiriladi."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_ev.clear()
    _thread = threading.Thread(target=_worker, daemon=True, name="NK-Prewarm")
    _thread.start()
    print("[PREWARM] Ong konteksti fon threadida isitilmoqda...")


def stop():
    """Thread to'xtatish (ixtiyoriy)."""
    _stop_ev.set()


def get_cached_context(max_age: float = _MAX_AGE_SEC) -> str:
    """
    Keshlangan ong kontekstini qaytaradi — 0ms.
    Agar kesh eski bo'lsa yoki tayyor bo'lmasa → bo'sh string.
    """
    with _lock:
        if not _ready:
            return ""
        age = time.monotonic() - _updated
        if age > max_age:
            return ""
        return _ctx_cache


def is_ready() -> bool:
    """True — kamida bir marta hisoblangan."""
    with _lock:
        return _ready


def get_stats() -> dict:
    """Debug uchun holat."""
    with _lock:
        age = time.monotonic() - _updated if _ready else -1
        return {
            "ready":         _ready,
            "age_sec":       round(age, 1) if age >= 0 else None,
            "ctx_len":       len(_ctx_cache),
            "groq_warmed":   _groq_warmed,
            "vecmem_warmed": _vecmem_warmed,
            "facearc_warmed": _facearc_warmed,
        }
