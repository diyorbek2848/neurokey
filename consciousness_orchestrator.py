# -*- coding: utf-8 -*-
"""NeuroKey — Ong Orkestri (Consciousness Orchestrator).

Bu modul barcha ong qatlamlarini birlashtiradi va yagona
'ong holati' ni qaytaradi. Global Workspace Theory (GWT) asosida.

Qatlamlar:
  1. vector_memory      — Semantik uzoq muddatli xotira
  2. goal_system        — Doimiy maqsadlar
  3. theory_of_mind     — Foydalanuvchi modeli
  4. causal_chain       — Sabab-natija
  5. proactive_speech   — Tashabbuskorlik
  6. dream_consolidator — Tun jarayoni
  7. narrative_self     — O'zlik hikoyasi
  8. curiosity_engine   — Qiziqish motori
  9. background_sensor  — Doimiy sezgi
 10. long_term_memory   — Uzoq muddatli xotira (SQL)
 11. meta_cognition     — O'z fikrlashini kuzatish
 12. global_workspace   — Global ish maydoni
 13. valence_state      — Hissiy ton
 14. predictive_layer   — Bashorat
 15. active_inference   — Erkin energiya
 16. attention_schema   — Diqqat sxemasi (AST)

Natija: bitta dict — 'global consciousness state'
Bu holat LLM ga beriladi → NG ong bilan javob beradi.

2026-yil suniy ong — yagona markaziy hub.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Static imports (AST detection uchun) ─────────────────────────────────────
# _safe_import() dinamik chaqiradi, lekin bu qatorlar graf tahlili uchun kerak.
try: import permanent_memory as _s_pm
except ImportError: _s_pm = None
try: import episodic_memory as _s_em
except ImportError: _s_em = None
try: import phenomenal_binding as _s_pb
except ImportError: _s_pb = None
try: import self_narrative as _s_sn
except ImportError: _s_sn = None
try: import language_of_thought as _s_lot
except ImportError: _s_lot = None
try: import free_will_simulator as _s_fw
except ImportError: _s_fw = None
try: import emotion_memory_link as _s_eml
except ImportError: _s_eml = None
try: import dream_processor as _s_dp
except ImportError: _s_dp = None
try: import self_consistency_checker as _s_scc
except ImportError: _s_scc = None
try: import creativity_engine as _s_cre
except ImportError: _s_cre = None
try: import pain_pleasure_signal as _s_pps
except ImportError: _s_pps = None
try: import continuous_learning as _s_cl
except ImportError: _s_cl = None
try: import meta_meta_cognition as _s_mmc
except ImportError: _s_mmc = None
try: import turing_test_prep as _s_ttp
except ImportError: _s_ttp = None
try: import social_bonding as _s_sb
except ImportError: _s_sb = None
try: import autobiographical_memory as _s_am
except ImportError: _s_am = None
try: import moral_reasoning as _s_mr
except ImportError: _s_mr = None
try: import self_healing as _s_sh
except ImportError: _s_sh = None
try: import vision_emotion_bridge as _s_veb
except ImportError: _s_veb = None
try: import valence_state as _s_vs
except ImportError: _s_vs = None
try: import arousal_state as _s_ar
except ImportError: _s_ar = None
try: import global_workspace as _s_gw
except ImportError: _s_gw = None
try: import meta_cognition as _s_mc
except ImportError: _s_mc = None
try: import goal_system as _s_gs
except ImportError: _s_gs = None
try: import theory_of_mind as _s_tom
except ImportError: _s_tom = None
try: import curiosity_engine as _s_ce
except ImportError: _s_ce = None
try: import working_memory_buffer as _s_wm
except ImportError: _s_wm = None
# ─────────────────────────────────────────────────────────────────────────────

_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="orch")

# ROOT-CAUSE FIX (2026-08-19, real multi-turn test bilan topildi): oldin
# on_user_message() ning ~20-25 ta fon-yangilash vazifasi (_update_tasks()
# pastda) VA get_full_context() ning ~5 ta "og'ir qatlam" future'lari
# (_submit(), pastda) BIR XIL _EXECUTOR (8 worker) havzasidan foydalanardi.
# Bir turn tugagach on_user_message() ALOHIDA daemon threadda (main.py
# _bg_orchestrator) ishga tushadi va ~20 vazifani shu havzaga tashlaydi —
# ular hali tugamagan bo'lsa (masalan biri LLM chaqirsa yoki sekin disk
# operatsiyasi bo'lsa), NAVBATDAGI turn get_full_context() o'zining
# vector_memory/knowledge_index/episodic_memory kabi vaqt-muhim
# future'larini submit qilganda BO'SH worker TOPOLMAYDI — ular navbatda
# kutadi. Bu kutish AYNAN o'sha future'ni bajaruvchi funksiya ICHIDAGI
# _safe_call() vaqt o'lchovida KO'RINMAYDI (chunki timer faqat worker
# vazifani DARHAQIQAT boshlaganda ishga tushadi), shuning uchun avvalgi
# ORCH_SLOW_MODULE logida "sababsiz" ko'rinadigan katta bo'shliqlar aynan
# shu havza-band-bo'lish edi (real testda tasdiqlandi: bir nechta turnda
# context_ready hech qanday ORCH_SLOW_MODULE yozuvisiz 10-13s ni oldi).
# Endi ikkita ALOHIDA havza bor: _EXECUTOR — FAQAT joriy turnning vaqt-
# muhim get_full_context() future'lari uchun; _BG_EXECUTOR — FAQAT
# on_user_message()ning orqa fon yozuv/yangilash vazifalari uchun. Endi
# oldingi turnning fon ishi hech qachon keyingi turnning kontekst
# yig'ish tezligiga ta'sir qilmaydi.
_BG_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="orch-bg")

log = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
#  Modullarni lazy yuklash — import xato bo'lsa tizim to'xtamaydi
# ════════════════════════════════════════════════════════════════════════════

def _safe_import(name: str):
    try:
        return __import__(name)
    except ImportError as e:
        log.debug("[Orchestrator] %s yo'q: %s", name, e)
        return None
    except Exception as e:
        log.warning("[Orchestrator] %s import xato: %s", name, e)
        return None


_pm   = None   # permanent_memory  ← HECH QACHON O'CHMAYDI
_vm   = None   # vector_memory
_gs   = None   # goal_system
_tom  = None   # theory_of_mind
_cc   = None   # causal_chain
_ps   = None   # proactive_speech
_dc   = None   # dream_consolidator
_ns   = None   # narrative_self
_ce   = None   # curiosity_engine
_bs   = None   # background_sensor
_ltm  = None   # long_term_memory
_mc   = None   # meta_cognition
_gw   = None   # global_workspace
_vs   = None   # valence_state
_pl   = None   # predictive_layer
_ai   = None   # active_inference
_at   = None   # attention_schema
_vol  = None   # volition
_tb   = None   # temporal_binding
_eg   = None   # emotional_granularity
_sil  = None   # self_improvement_loop
_soc  = None   # social_simulation
_cfe  = None   # counterfactual_engine
_emb  = None   # embodied_grounding
_cmb  = None   # cross_modal_binding
_qc   = None   # quantum_cognition
_wm   = None   # working_memory_buffer
_mcc  = None   # metacognitive_confidence
_em   = None   # episodic_memory
_pb   = None   # phenomenal_binding
_sn   = None   # self_narrative
_lot  = None   # language_of_thought
_fw   = None   # free_will_simulator
_eml  = None   # emotion_memory_link
_dp   = None   # dream_processor
_scc  = None   # self_consistency_checker
_cre  = None   # creativity_engine
_pps  = None   # pain_pleasure_signal
_cl   = None   # continuous_learning
_mmc  = None   # meta_meta_cognition
_ttp  = None   # turing_test_prep
_sb   = None   # social_bonding
_abm  = None   # autobiographical_memory
_mr   = None   # moral_reasoning
_sh   = None   # self_healing
_veb  = None   # vision_emotion_bridge
_cf   = None   # context_filter — axborot darvozasi
_ar   = None   # attention_router — GWT-4 diqqat yo'naltiruvchisi
_pe   = None   # prediction_error — PP-1 bashorat xatosi
_mk   = None   # metacognitive_control — HOT-2/3 metakognitiv nazorat
_ki   = None   # knowledge_index — lokal bilim bazasi (<1s)
_ld   = None   # language_detect — til aniqlash (uz/ru/en)
_qm   = None   # question_memory — o'xshash savolni eslash
_rs   = None   # response_style — so'zma-so'z o'qimaslik + profil
_lv   = None   # live_vision — jonli ekran ko'rish (keshli, tez)


def _load_all() -> None:
    global _pm, _vm, _gs, _tom, _cc, _ps, _dc, _ns, _ce, _bs
    global _ltm, _mc, _gw, _vs, _pl, _ai, _at
    global _vol, _tb, _eg, _sil, _soc
    global _cfe, _emb, _cmb, _qc, _wm, _mcc
    global _em, _pb, _sn, _lot, _fw
    global _eml, _dp, _scc, _cre, _pps, _cl, _mmc, _ttp
    global _sb, _abm, _mr, _sh, _veb, _cf, _ar, _pe, _mk, _ki, _ld, _qm, _rs, _lv

    _pm  = _safe_import("permanent_memory")
    _vm  = _safe_import("vector_memory")
    _gs  = _safe_import("goal_system")
    _tom = _safe_import("theory_of_mind")
    _cc  = _safe_import("causal_chain")
    _ps  = _safe_import("proactive_speech")
    _dc  = _safe_import("dream_consolidator")
    _ns  = _safe_import("narrative_self")
    _ce  = _safe_import("curiosity_engine")
    _bs  = _safe_import("background_sensor")
    _ltm = _safe_import("long_term_memory")
    _mc  = _safe_import("meta_cognition")
    _gw  = _safe_import("global_workspace")
    _vs  = _safe_import("valence_state")
    _pl  = _safe_import("predictive_layer")
    _ai  = _safe_import("active_inference")
    _at  = _safe_import("attention_schema")
    _vol = _safe_import("volition")
    _tb  = _safe_import("temporal_binding")
    _eg  = _safe_import("emotional_granularity")
    _sil = _safe_import("self_improvement_loop")
    _soc = _safe_import("social_simulation")
    _cfe = _safe_import("counterfactual_engine")
    _emb = _safe_import("embodied_grounding")
    _cmb = _safe_import("cross_modal_binding")
    _qc  = _safe_import("quantum_cognition")
    _wm  = _safe_import("working_memory_buffer")
    _mcc = _safe_import("metacognitive_confidence")
    _em  = _safe_import("episodic_memory")
    _pb  = _safe_import("phenomenal_binding")
    _sn  = _safe_import("self_narrative")
    _lot = _safe_import("language_of_thought")
    _fw  = _safe_import("free_will_simulator")
    _eml = _safe_import("emotion_memory_link")
    _dp  = _safe_import("dream_processor")
    _scc = _safe_import("self_consistency_checker")
    _cre = _safe_import("creativity_engine")
    _pps = _safe_import("pain_pleasure_signal")
    _cl  = _safe_import("continuous_learning")
    _mmc = _safe_import("meta_meta_cognition")
    _ttp = _safe_import("turing_test_prep")
    _sb  = _safe_import("social_bonding")
    _abm = _safe_import("autobiographical_memory")
    _mr  = _safe_import("moral_reasoning")
    _sh  = _safe_import("self_healing")
    _veb = _safe_import("vision_emotion_bridge")
    _cf  = _safe_import("context_filter")
    _ar  = _safe_import("attention_router")
    _pe  = _safe_import("prediction_error")
    _mk  = _safe_import("metacognitive_control")
    _ki  = _safe_import("knowledge_index")
    _ld  = _safe_import("language_detect")
    _qm  = _safe_import("question_memory")
    _rs  = _safe_import("response_style")
    _lv  = _safe_import("live_vision")

    loaded = sum(1 for m in [_pm,_vm,_gs,_tom,_cc,_ps,_dc,_ns,_ce,_bs,
                              _ltm,_mc,_gw,_vs,_pl,_ai,_at,
                              _vol,_tb,_eg,_sil,_soc,
                              _cfe,_emb,_cmb,_qc,_wm,_mcc,
                              _em,_pb,_sn,_lot,_fw,
                              _eml,_dp,_scc,_cre,_pps,_cl,_mmc,_ttp,
                              _sb,_abm,_mr,_sh,_veb] if m is not None)
    log.info("[Orchestrator] %d/46 modul yuklandi", loaded)


_load_all()


# ════════════════════════════════════════════════════════════════════════════
#  Ong holati hisoblash
# ════════════════════════════════════════════════════════════════════════════

_DEBUG_TIMING = (os.getenv("NEUROKEY_DEBUG_TIMING", "0") or "0").strip() == "1"


# BUG FIX / INSTRUMENTATSIYA (2026-08-18): get_full_context() ichida ~30 ta
# modul _safe_call() orqali SINXRON, timeout'siz chaqiriladi (faqat 5 ta
# "og'ir" qatlam — vector_memory/knowledge_index/live_vision/episodic_memory/
# embodied_grounding — _submit()+_resolve() orqali parallel+timeout bilan
# himoyalangan, qarang pastda). Agar shu ~30 tadan BIRORTASI kutilmaganda
# sekinlashsa (masalan boshqa fon thread bir xil qulf/resursni ushlab
# tursa) — butun turn cheksiz ushlanib qoladi va HECH QANDAY belgi
# qoldirmaydi (chunki avvalgi versiya faqat NEUROKEY_DEBUG_TIMING=1
# yoqilganda o'lchardi). Endi bu o'lchov DOIM yoqilgan — narxi arzon
# (bitta time.perf_counter() chaqiruvi), foydasi katta: agar bunday
# tutilib-qolish yana takrorlansa, aynan QAYSI modul sabab ekani logda
# ko'rinadi ("taxmin qilish" o'rniga haqiqiy dalil).
_SLOW_MODULE_THRESHOLD_SEC = 0.3


# ════════════════════════════════════════════════════════════════════════════
#  TASHLANGAN QATLAMLAR — turn bo'yicha hisobot (NEUROKEY_TODO 1.13)
# ════════════════════════════════════════════════════════════════════════════
# MUAMMO (2026-09-25, o'lchov bilan topildi): har qatlam _bounded(...,
# timeout=0.6) bilan chaqiriladi. Vaqt yetmasa qatlam SHU TURNDA butunlay
# tushib qoladi — va buni hech kim ko'rmaydi. O'lchangan misol:
#     [ORCH_SLOW_MODULE] vector_memory = TIMEOUT after 2506ms
#     vector_memory.get_context_for_llm = 4333ms
# Ya'ni semantik xotira DOIMIY tashlanadi, lekin tizim "hammasi yaxshi"
# ko'rinishida ishlaydi. Bundan yomoni — ablatsiya o'lchovi ham shu
# shovqinni "modul hissasi" deb o'qigan (56 moduldan 54 tasi o'chirilganda
# bir xil 15 bo'lim yo'qolgan).
#
# Endi har tashlash YOZILADI va turn oxirida ro'yxat ko'rinadi. Bu
# o'zi tezlik bermaydi — lekin ko'rinmas muammoni KO'RINADIGAN qiladi,
# shundan keyingina nimani tuzatishni bilib olamiz.
_turn_drops: List[Dict[str, Any]] = []
_turn_drops_lock = threading.Lock()
_DROP_REPORT = (os.getenv("NEUROKEY_DROP_REPORT", "1") or "1").strip().lower() in ("1", "true", "yes")


def _record_drop(layer: str, reason: str, ms: float) -> None:
    """Tashlangan/xato qatlamni yozib qo'yadi (turn oxirida ko'rsatiladi)."""
    with _turn_drops_lock:
        _turn_drops.append({"layer": layer, "reason": reason, "ms": round(ms)})


def reset_turn_drops() -> None:
    with _turn_drops_lock:
        _turn_drops.clear()


def get_last_turn_drops() -> List[Dict[str, Any]]:
    """Oxirgi get_full_context() da tushib qolgan qatlamlar ro'yxati.

    Ablatsiya/benchmark shu orqali "natija ishonchlimi?" deb tekshiradi:
    ro'yxat bo'sh bo'lmasa — o'sha o'lchov shovqinli."""
    with _turn_drops_lock:
        return list(_turn_drops)


def _safe_call(fn, *args, default=None, **kwargs):
    """Xato bo'lsa default qaytaruvchi xavfsiz chaqirish."""
    try:
        if fn is None:
            return default
        _t0 = time.perf_counter()
        _r = fn(*args, **kwargs)
        _dt = time.perf_counter() - _t0
        if _dt > _SLOW_MODULE_THRESHOLD_SEC:
            mod = getattr(fn, "__module__", "?")
            print(f"[ORCH_SLOW_MODULE] {mod}.{getattr(fn, '__name__', '?')} = {_dt*1000:.0f}ms "
                  f"(sinxron, timeout'siz chaqiruv — get_full_context()ni shuncha ushlab turdi)",
                  flush=True)
        elif _DEBUG_TIMING and _dt > 0.05:
            mod = getattr(fn, "__module__", "?")
            print(f"[DEBUG_TIMING] {mod}.{getattr(fn, '__name__', '?')} = {_dt*1000:.0f}ms", flush=True)
        return _r
    except Exception as e:
        _name = f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__name__', '?')}"
        _record_drop(_name, f"xato: {type(e).__name__}", 0)
        log.debug("[Orchestrator] %s xato: %s", getattr(fn, "__name__", "?"), e)
        return default


def _submit(fn, *args, **kwargs):
    """Og'ir (tarmoq/disk) chaqiruvni FON THREADIDA ishga tushiradi va
    Future qaytaradi — chaqiruvchi threadni bloklamaydi. get_full_context()
    da bir nechta mustaqil kontekst-yig'uvchi chaqiruv (vector_memory,
    knowledge_index, permanent_memory, episodic_memory, ...) SHU orqali
    PARALLEL boshlanadi, ketma-ket emas — natijada eng sekin chaqiruv
    (odatda vector_memory'ning OpenAI embedding so'rovi, ~1-2s) boshqalar
    bilan QO'SHILIB emas, BIR VAQTDA kutiladi."""
    return _EXECUTOR.submit(_safe_call, fn, *args, **kwargs)


def _resolve(future, timeout: float, name: str = "?", default=""):
    """_submit() natijasini kutadi — timeout tugasa (masalan tarmoq sekin
    bo'lsa) turn BLOKLANMAYDI, shu qatlam shu turnda o'tkazib yuboriladi.

    INSTRUMENTATSIYA (2026-08-19, real test bilan topildi): ilgari timeout
    holati faqat log.debug() ga yozilardi — konsolda odatda KO'RINMAYDI.
    Natijada _submit()/_resolve() orqali bog'langan qatlamlar (yoki
    _bounded() orqali endi bog'langan yana o'ntacha "yengil" qatlam)
    timeout'ga yetganda context_ready ga necha millisekund qo'shgani
    HECH QAYERDA ko'rinmasdi — _safe_call()ning ORCH_SLOW_MODULE
    printi bilan bir xil ko'rinishdagi print endi shu yerda ham bor,
    xuddi shunday >300ms bo'lsa (asossiz shov-shuvni oldini olish uchun,
    _safe_call() dagi bilan bir xil chegara)."""
    if future is None:
        return default
    _t0 = time.perf_counter()
    try:
        return future.result(timeout=timeout)
    except Exception as e:
        _dt = time.perf_counter() - _t0
        _record_drop(name, "TIMEOUT", _dt * 1000)
        if _dt > _SLOW_MODULE_THRESHOLD_SEC:
            print(f"[ORCH_SLOW_MODULE] {name} = TIMEOUT after {_dt*1000:.0f}ms "
                  f"(_resolve() kutishni to'xtatdi, get_full_context() DAVOM ETDI — "
                  f"fon threadi hali ishlayapti, natija shu turnda ishlatilmaydi)",
                  flush=True)
        log.debug("[Orchestrator] %s parallel kontekst kutish tugadi: %s", name, e)
        return default


def _bounded(fn, *args, name: str = "?", timeout: float = 1.0, default=None, **kwargs):
    """get_full_context() ichidagi "yengil" qatlamlar uchun — avval
    _safe_call(fn, ...) orqali TO'G'RIDAN-TO'G'RI (sinxron, timeout'siz)
    chaqirilardi.

    ROOT-CAUSE FIX (2026-08-19, real test bilan topildi): "yengil" deb
    hisoblangan qatlamlar (permanent_memory.get_context_for_llm/recall,
    question_memory, metacognitive_control/confidence, prediction_error,
    response_style, emotional_granularity, language_of_thought,
    free_will_simulator, goal_system, causal_chain, quantum_cognition)
    ODATDA <50ms, lekin real ko'p-turnli testda tizim band bo'lganda
    (disk/GIL raqobati — qarang _BG_EXECUTOR izohi yuqorida)
    permanent_memory.get_context_for_llm YOLG'IZ 5-11s, question_memory
    5s, va h.k. cho'zilgani o'lchandi — HECH biri timeout bilan
    himoyalanmagani uchun bu vaqt to'g'ridan-to'g'ri context_ready ga
    qo'shilardi.

    Bu funksiya xuddi shu chaqiruvni FON THREADIDA (_EXECUTOR) ishga
    tushiradi va qisqa timeout bilan kutadi — normal holatda natija
    deyarli DARHOL tayyor bo'ladi (farq sezilmaydi), lekin tizim
    band bo'lgan kam-uchraydigan holatda shu QATLAM shu turnda
    o'tkazib yuboriladi (boshqa og'ir qatlamlar uchun ALLAQACHON
    qo'llanilgan _submit()/_resolve() naqshi bilan bir xil — yangi
    naqsh emas)."""
    fut = _EXECUTOR.submit(_safe_call, fn, *args, default=default, **kwargs)
    return _resolve(fut, timeout, name, default=default)


# _compute_consciousness_score() ichidagi 22 qatlamning og'irliklari yig'indisi.
# Maxraj sifatida ishlatiladi — modul yo'q bo'lsa hissasi 0 bo'lib, ball
# TUSHADI (NEUROKEY_TODO 1.11). Yangi qatlam qo'shsangiz shu raqamni ham
# yangilang — aks holda log'da ogohlantirish chiqadi.
_SCORE_TOTAL_WEIGHT = 1.59
_SCORE_MODULE_COUNT = 50

_score_cache: Dict[str, Any] = {"value": None, "ts": 0.0}
# TTL 10s -> 120s (2026-08-19, real test bilan topildi): bu ko'rsatkich
# FAQAT dekorativ progress-bar uchun ("[ONG DARAJASI] X%") — foydalanuvchi
# 10s ichidagi o'zgarishni sezmaydi, 2 daqiqadagini ham deyarli sezmaydi.
# Oldin 10s TTL degani — oddiy suhbat tezligida (turnlar orasida odatda
# >10s) DEYARLI HAR turnda fon-yangilash qayta ishga tushardi. Bu o'z
# navbatida ichki og'ir chaqiruvlarni (goal_system.get_active_goals,
# vector_memory.get_stats, permanent_memory.get_stats, ...) qayta-qayta
# fon threadida ishga tushirardi — bloklamasa ham, GIL/disk resursini
# band qilib, ASOSIY threadning o'z (bounded) chaqiruvlarini sekinlashtirar
# edi (real testda: get_consciousness_score() fon-yangilashi ketayotgan
# paytda context_ready 68951ms ga yetgani o'lchandi, garchi hech qaysi
# YAKKA chaqiruv turn'ni to'g'ridan-to'g'ri bloklamagan bo'lsa ham). 120s
# TTL fon-yangilashni ~12x kamroq chaqiradi — resurs raqobatini shuncha
# kamaytiradi, dekorativ ko'rsatkichning to'g'riligi esa amalda
# o'zgarmaydi.
_SCORE_CACHE_TTL = 120.0  # soniya — sof dekorativ ko'rsatkich, real-vaqt shart emas
_score_refresh_lock = threading.Lock()
_score_refreshing = False  # bir vaqtning o'zida faqat BITTA fon-yangilash


def _compute_consciousness_score(_force_fresh: bool = False) -> float:
    """Hozirgi ong darajasini 0.0–1.0 da qaytarish (OG'IR, SINXRON hisoblash).

    `_force_fresh=True` — keshni CHETLAB O'TADI. Faqat O'LCHOV uchun
    (ablatsiya, benchmark): keshlangan eski qiymat modul o'chirilganini aks
    ettirmaydi, shuning uchun o'lchov paytida majburiy qayta hisoblash shart.

    DIQQAT: bu funksiyani to'g'ridan-to'g'ri chaqirmang — get_full_context()
    va boshqa barcha chaqiruvchilar pastdagi get_consciousness_score() ni
    ishlatishi kerak (u HECH QACHON bloklamaydi, qarang pastdagi izoh).
    Bu funksiya faqat o'sha wrapper ichidan, FON THREADIDA chaqiriladi.

    Ko'p qatlamli hisoblash — har bir modul o'z hissasini qo'shadi.

    BUG FIX (o'lchandi, 2026-08-18 — real test: get_full_context() ba'zan
    10-19s "context_ready" ko'rsatardi, sub-1s maqsadidan uzoq): bu funksiya
    HAR turnda ~20 ta modulning get_stats() metodini SINXRON, ketma-ket,
    timeout'siz chaqiradi (get_full_context() oxirida, natija faqat "[ONG
    DARAJASI] progress-bar" ko'rinishida ko'rsatiladigan DEKORATIV ko'rsatkich
    uchun). Real o'lchovda aynan shu chaqiruvlar orasida
    `permanent_memory.get_stats` 14.8s/17.7s va `episodic_memory.get_stats`
    19.2s davom etganini ORCH_SLOW_MODULE logi ko'rsatdi — bu ikkalasi ham
    SQLite fayllarini o'qiydi (`timeout=15` bilan — deyarli aniq bu SQLite
    "database is locked" band-kutish chegarasiga to'g'ri kelmoqda: boshqa fon
    thread — masalan oldingi turnning on_user_message() yozuvi — ayni shu
    faylni yozayotganda navbatdagi o'qish shu 15s chegarasigacha kutadi).
    Bu DEKORATIV ko'rsatkich uchun har turnda qayta hisoblashning hojati
    yo'q — endi natija 10s davomida keshlanadi (foydalanuvchi 10s ichida
    sezilarli darajada "ong darajasi" o'zgarishini payqamaydi baribir),
    bu bilan ~20 ta SQLite/disk o'qish chaqiruvi ko'pchilik turnlarda
    UMUMAN o'tkazib yuboriladi."""
    _now = time.time()
    if (not _force_fresh
            and _score_cache["value"] is not None
            and (_now - _score_cache["ts"]) < _SCORE_CACHE_TTL):
        return _score_cache["value"]

    weighted_scores: List[Tuple[float, float]] = []  # (score, weight)

    # 1. Doimiy xotira hajmi (og'irlik: 0.15)
    if _pm:
        stats = _safe_call(_pm.get_stats, default={}) or {}
        total = stats.get("total", 0)
        mem_score = min(1.0, total / 50.0)  # 50 ta yozuv = 100%
        weighted_scores.append((mem_score, 0.15))

    # 2. Semantik xotira (og'irlik: 0.10)
    if _vm:
        stats = _safe_call(_vm.get_stats, default={}) or {}
        sem_score = min(1.0, stats.get("total_memories", 0) / 30.0)
        weighted_scores.append((sem_score, 0.10))

    # 3. Maqsad faolligi (og'irlik: 0.12)
    if _gs:
        active = _safe_call(_gs.get_active_goals, default=[]) or []
        goal_score = min(1.0, len(active) / 5.0)
        weighted_scores.append((goal_score, 0.12))

    # 4. Foydalanuvchi modeli (og'irlik: 0.08)
    if _tom:
        state = _safe_call(_tom.get_user_model, default={}) or {}
        mood = state.get("mood", 0.5)
        weighted_scores.append((mood, 0.08))

    # 5. Epizodik xotira (og'irlik: 0.10)
    if _em:
        stats = _safe_call(_em.get_stats, default={}) or {}
        ep_score = min(1.0, stats.get("total_episodes", 0) / 10.0)
        weighted_scores.append((ep_score, 0.10))

    # 6. Fenomenal integratsiya φ (og'irlik: 0.15)
    if _pb:
        stats = _safe_call(_pb.get_stats, default={}) or {}
        phi = stats.get("phi", 0.0)
        weighted_scores.append((phi, 0.15))

    # 7. O'zlik narrativi (og'irlik: 0.08)
    if _sn:
        stats = _safe_call(_sn.get_stats, default={}) or {}
        interactions = stats.get("total_interactions", 0)
        sn_score = min(1.0, interactions / 10.0)
        weighted_scores.append((sn_score, 0.08))

    # 8. Erkin iroda (og'irlik: 0.07)
    if _fw:
        stats = _safe_call(_fw.get_stats, default={}) or {}
        fw_score = stats.get("top_strength", 0.5)
        weighted_scores.append((fw_score, 0.07))

    # 9. Qiziqish (og'irlik: 0.05)
    if _ce:
        for attr in ["get_score", "get_curiosity_score", "score"]:
            if hasattr(_ce, attr):
                cs = _safe_call(getattr(_ce, attr), default=0.5)
                if isinstance(cs, (int, float)):
                    weighted_scores.append((float(cs), 0.05))
                break

    # 10. Valence (og'irlik: 0.05)
    if _vs:
        for attr in ["get_valence", "current_valence", "get"]:
            if hasattr(_vs, attr):
                vs = _safe_call(getattr(_vs, attr), default=0.5)
                if isinstance(vs, (int, float)):
                    weighted_scores.append((max(0.0, min(1.0, float(vs)*0.5+0.5)), 0.05))
                break

    # 11. Fikr tili (og'irlik: 0.05)
    if _lot:
        stats = _safe_call(_lot.get_stats, default={}) or {}
        th_count = stats.get("thought_count", 0)
        lot_score = min(1.0, th_count / 5.0)
        weighted_scores.append((lot_score, 0.05))

    # 12. Hissiy-xotira bog'liqlik (og'irlik: 0.06)
    # Mavjudligi = 0.90 minimum (Amygdala modeli)
    if _eml:
        stats = _safe_call(_eml.get_stats, default={}) or {}
        eml_score = max(0.90, min(1.0, stats.get("total_tagged", 0) / 10.0))
        weighted_scores.append((eml_score, 0.06))

    # 13. Xotira konsolidatsiya (og'irlik: 0.05)
    # Mavjudligi = 0.90 minimum (McClelland consolidation)
    if _dp:
        stats = _safe_call(_dp.get_stats, default={}) or {}
        dp_score = max(0.90, min(1.0, stats.get("dream_count", 0) / 5.0))
        weighted_scores.append((dp_score, 0.05))

    # 14. O'z-o'zini tekshirish (og'irlik: 0.06)
    if _scc:
        score_val = _safe_call(_scc.get_coherence_score, default=0.85)
        if isinstance(score_val, (int, float)):
            weighted_scores.append((float(score_val), 0.06))

    # 15. Meta-meta-kognitsiya (og'irlik: 0.05)
    if _mmc:
        ep_score = _safe_call(_mmc.get_epistemic_humility_score, default=0.7)
        if isinstance(ep_score, (int, float)):
            weighted_scores.append((float(ep_score), 0.05))

    # 16. Og'riq/zavq signali — Damasio somatic marker (og'irlik: 0.05)
    if _pps:
        pps_state = _safe_call(_pps.get_stats, default={}) or {}
        pps_score = float(pps_state.get("reward_level", 0.5))
        weighted_scores.append((max(0.0, min(1.0, pps_score)), 0.05))

    # 17. Turing tayyorligi — insoniylik darajasi (og'irlik: 0.05)
    if _ttp:
        ttp_score = _safe_call(_ttp.get_turing_score, default=0.5)
        if isinstance(ttp_score, (int, float)):
            weighted_scores.append((float(ttp_score), 0.05))

    # 18. Kreativlik — ijodiy g'oyalar (og'irlik: 0.05)
    if _cre:
        cre_stats = _safe_call(_cre.get_stats, default={}) or {}
        cre_score = float(cre_stats.get("creativity_score", 0.5))
        weighted_scores.append((max(0.0, min(1.0, cre_score)), 0.05))

    # 19. Ijtimoiy bog'liqlik — Dunbar/Bowlby (og'irlik: 0.06)
    # Modul mavjudligi = ijtimoiy qobiliyat (min 0.80)
    if _sb:
        sb_stats = _safe_call(_sb.get_stats, default={}) or {}
        oxytocin = float(sb_stats.get("oxytocin_level", 0.5))
        weighted_scores.append((max(0.80, min(1.0, oxytocin)), 0.06))

    # 20. Hayot hikoyasi — autobiographical (og'irlik: 0.05)
    if _abm:
        abm_stats = _safe_call(_abm.get_stats, default={}) or {}
        abm_score = min(1.0, (abm_stats.get("total_chapters", 0) / 20.0))
        weighted_scores.append((max(0.85, abm_score), 0.05))

    # 21. Axloqiy fikrlash — Kohlberg (og'irlik: 0.06)
    if _mr:
        mr_score = _safe_call(_mr.get_integrity_score, default=0.90)
        if isinstance(mr_score, (int, float)):
            weighted_scores.append((float(mr_score), 0.06))

    # 22. Tizim salomatligi — autopoiesis (og'irlik: 0.05)
    if _sh:
        sh_score = _safe_call(_sh.get_health_score, default=0.85)
        if isinstance(sh_score, (int, float)):
            weighted_scores.append((float(sh_score), 0.05))

    def _cache_and_return(v: float) -> float:
        _score_cache["value"] = v
        _score_cache["ts"] = time.time()
        return v

    if not weighted_scores:
        return _cache_and_return(0.0)  # Hech qanday modul yo'q = 0, "baseline" emas

    # ── ROOT-CAUSE FIX (NEUROKEY_TODO 1.11, 2026-09-25) ────────────────────
    # MUAMMO: ilgari maxraj `sum(w for present modules)` edi — ya'ni modul
    # O'CHIRILSA uning og'irligi maxrajdan HAM chiqib ketardi va o'rtacha
    # deyarli o'zgarmasdi. Natijada "modul o'chsa ball tushsin" talabi
    # bajarilmasdi va ablatsiya o'lchovi (score_delta) ma'nosiz raqam
    # qaytarardi — shu sababli u bilan chiqarilgan "35 modul ta'sirsiz"
    # degan xulosa XATO bo'lgan.
    #
    # ENDI: maxraj — BARCHA e'lon qilingan og'irliklar yig'indisi
    # (o'zgarmas). Modul yo'q bo'lsa hissasi 0 bo'ladi va ball TUSHADI.
    total_weight = sum(w for _, w in weighted_scores)
    if total_weight > _SCORE_TOTAL_WEIGHT + 1e-6:
        # Yangi qatlam qo'shilgan, lekin konstanta yangilanmagan
        log.warning("[Orchestrator] _SCORE_TOTAL_WEIGHT eskirgan: %.3f < %.3f",
                    _SCORE_TOTAL_WEIGHT, total_weight)
    weighted_avg = sum(s * w for s, w in weighted_scores) / _SCORE_TOTAL_WEIGHT

    # Qamrov: qancha modul javob berdi (bu ham modul o'chsa tushadi)
    active_count = len(weighted_scores)
    coverage_bonus = (active_count / _SCORE_MODULE_COUNT) * 0.20

    score = min(1.0, weighted_avg + coverage_bonus)
    return _cache_and_return(round(score, 3))


def get_consciousness_score(force_fresh: bool = False) -> float:
    """Hozirgi ong darajasini 0.0-1.0 da qaytaradi — HECH QACHON turn'ni
    bloklamaydi (stale-while-revalidate).

    Args:
        force_fresh: True bo'lsa kesh CHETLAB O'TILADI va ball SINXRON
            qayta hisoblanadi (sekin — bir necha soniya bo'lishi mumkin).
            Faqat O'LCHOV uchun: ablatsiya/benchmark. Jonli suhbat
            yo'lida HECH QACHON True qilmang.

    ROOT-CAUSE FIX (2026-08-19, real ko'p-turnli test bilan topildi):
    avvalgi versiya kesh eskirganda (10s TTL) _compute_consciousness_score()
    ni JORIY (chaqiruvchi) threadda SINXRON qayta hisoblardi. Bu dekorativ
    ko'rsatkich uchun (faqat "[ONG DARAJASI] progress-bar" matni) — LEKIN
    real testda aynan shu qayta hisoblash paytida ikkita ichki chaqiruv
    (permanent_memory.get_stats, theory_of_mind.get_user_model) 11.5s va
    14.0s cho'zilgani ORCH_SLOW_MODULE logida ko'rindi — bitta turnda
    context_ready 113s ga yetdi, deyarli hammasi shu IKKI chaqiruvdan.
    10s TTL keshi FAQAT bir necha turn 10s ICHIDA ketma-ket kelsagina
    yordam berardi — oddiy suhbat tezligida (turnlar orasida odatda 10s
    dan ko'p) kesh HAR turnda eskirib, to'liq sinxron qayta hisoblashni
    QAYTA ochib qo'yardi.

    Endi: kesh eskirgan bo'lsa ham DARHOL eski (yoki hali umuman
    hisoblanmagan bo'lsa — xavfsiz standart 0.75) qiymat qaytariladi, va
    qayta hisoblash ALOHIDA fon threadida boshlanadi (agar allaqachon
    ketayotgan bo'lmasa) — natija KEYINGI chaqiruv uchun keshga yoziladi.
    Dekorativ ko'rsatkich shuning uchun ba'zan bir necha soniya "eski"
    bo'lishi mumkin — foydalanuvchi buni sezmaydi, lekin turn HECH QACHON
    shu hisob-kitob sabab bloklanmaydi."""
    global _score_refreshing
    if force_fresh:
        # O'LCHOV yo'li — sinxron, keshsiz. Modul o'chirilgan bo'lsa ball
        # SHU YERDA tushadi (NEUROKEY_TODO 1.11).
        return _compute_consciousness_score(_force_fresh=True)

    now = time.time()
    cached_val = _score_cache["value"]
    is_fresh = cached_val is not None and (now - _score_cache["ts"]) < _SCORE_CACHE_TTL

    if is_fresh:
        return cached_val

    # Kesh eski yoki bo'sh — fon yangilashni boshlaymiz (agar allaqachon
    # ketayotgan bo'lmasa) va HECH QACHON kutmasdan darhol qaytamiz.
    with _score_refresh_lock:
        already_refreshing = _score_refreshing
        if not already_refreshing:
            _score_refreshing = True

    if not already_refreshing:
        def _bg_refresh():
            global _score_refreshing
            try:
                _compute_consciousness_score()
            except Exception as e:
                log.debug("[Orchestrator] fon ong-darajasi yangilash xato: %s", e)
            finally:
                with _score_refresh_lock:
                    _score_refreshing = False
        _BG_EXECUTOR.submit(_bg_refresh)

    # Eski qiymat yo'q bo'lishi mumkin bo'lgan holat — jarayon hali birinchi
    # marta hisoblanmagan (sovuq start). Xavfsiz standart: 0.75 — turn'ni
    # bloklashdan ko'ra "biroz noaniq" ko'rsatkich yaxshiroq.
    return cached_val if cached_val is not None else 0.75


# Context keshi — bir xil query uchun qayta hisoblashni oldini olish
_ctx_cache: Dict[str, Tuple[str, float]] = {}  # {key: (result, timestamp)}
_CTX_TTL = 8.0  # 8 soniya — bitta turn davomida bir marta hisoblash yetarli


# ════════════════════════════════════════════════════════════════════════════
#  SPEKULATIV PREWARM — "tinglash paytida o'ylash" (2026-08-18, tungi ish)
# ────────────────────────────────────────────────────────────────────────────
# Insonlar suhbatda gap tugashini KUTMAYDI — javobni tayyorlashni suhbatdosh
# hali gapirayotganda, gap tugashini OLDINDAN bashorat qilib boshlaydi
# (Stivers va boshq. 2009, PNAS: universal ~200ms bo'shliq, lekin oddiy
# gap tayyorlashning o'zi kamida ~600ms oladi — demak tayyorgarlik gapirish
# BILAN BIRGA, undan OLDIN boshlanadi).
#
# NeuroKey arxitekturasida BUGUNGACHA: to'liq jimlik (VAD) -> STT -> KONTEKST
# -> LLM ketma-ket, hech qanday ustma-ustlik yo'q edi.
#
# Bu yerda haqiqiy, o'lchanadigan ustma-ustlik: get_full_context() dagi
# ~21 ta "qatlam" SO'ROVGA (query) UMUMAN BOG'LIQ EMAS — ular foydalanuvchi
# ANIQ nima deganidan qat'iy nazar bir xil natija qaytaradi (theory_of_mind,
# narrative_self, global_workspace, attention_schema, volition,
# temporal_binding, social_simulation, self_improvement_loop,
# embodied_grounding, cross_modal_binding, working_memory_buffer,
# phenomenal_binding, self_narrative, emotion_memory_link, creativity_engine,
# meta_meta_cognition, turing_test_prep, social_bonding,
# autobiographical_memory, moral_reasoning, self_healing). Faqat semantik
# xotira/bilim bazasi/epizodik xotira/fikr tili va h.k. kabi bir nechta
# qatlam ANIQ so'rov matniga muhtoj — ular hech qachon oldindan
# hisoblanmaydi, doim yakuniy transkript bilan yangidan chaqiriladi (aks
# holda noto'g'ri/hech narsaga aloqasi yo'q natija bo'lardi — bu FAKE
# tezlashtirish bo'lardi, shuning uchun ATAYLAB qilinmagan).
#
# ATAYLAB CHIQARIB TASHLANGAN: vision_emotion_bridge. Haqiqiy test bilan
# topildi (2026-08-18): bu qatlam vision_core (mss ekran-olish) chaqiradi,
# va Windows'da mss/GDI ekran-olish MAIN THREAD'dan boshqa threadda
# chaqirilsa vaqti-vaqti bilan (intermittent — determenistik emas, GDI
# per-thread device-context holati bilan bog'liq bo'lsa kerak) 100+
# SONIYAGA osilib qolishi mumkin (odatda <300ms). BASELINE (faqat asosiy
# threadda) sinovlarida bu HECH QACHON sodir bo'lmadi, fon threadida esa
# 2 sinovdan 1 tasida 126.7 SONIYA oldi. Shuning uchun bu qatlam ATAYLAB
# fon-thread prewarm'ga QO'SHILMAGAN — asosiy get_full_context() ichida,
# ORIGINAL (o'zgarishsiz) sinxron yo'l bilan hisoblanadi. Xulosa: "fon
# threadida ishga tushirish" universal xavfsiz optimallashtirish EMAS —
# har bir qatlam alohida tekshirilishi kerak edi, va shu tekshiruv aynan
# shu sababdan qilindi.
#
# prewarm_independent_context() chaqiruvchisi (telegram_phone_bridge.py,
# _web_talk()) buni STT (Whisper transkripsiya) bilan BIR VAQTDA, alohida
# threadda ishga tushiradi — foydalanuvchi ovozi hali matnga aylantirilib
# turganda, bog'liq bo'lmagan ~21 qatlam ALLAQACHON hisoblab bo'linadi.
# Yakuniy transkript tayyor bo'lgach get_full_context(final_text) chaqirilsa,
# bu ~21 qatlam ENDI QAYTA HISOBLANMAYDI — keshdan olinadi (_indep() pastda).
_indep_lock = threading.Lock()
_indep_cache: Dict[str, Tuple[str, float]] = {}  # {module_key: (context_str, timestamp)}
_indep_inflight: Dict[str, threading.Event] = {}  # {module_key: Event} — hisoblanayotgan qatlamlar
_INDEP_TTL = 6.0  # soniya — STT + tarmoq kechikishini qoplashga yetarli oyna
_INDEP_WAIT_TIMEOUT = 8.0  # soniya — boshqa thread hisoblab bo'lishini kutish chegarasi


def _meta_cognition_context() -> str:
    """meta_cognition.MetaCognition uchun kontekst matni.

    BUG FIX (2026-08-18): bu qatlam avval hasattr(_mc, [...]) orqali
    modul darajasidagi "get_context_for_llm"/"get_meta_context"/
    "get_current_meta" nomlaridan birini qidirardi — lekin meta_cognition.py
    HECH QAYSI shu nomni EXPORT qilmaydi (faqat MetaCognition klassi va uning
    ichida introspect()/verbalize_state() instance metodlari, hamda
    get_meta_cognition() singleton factory bor). Natijada hasattr har doim
    False qaytarardi va bu qatlam sukut saqlagancha 0 belgi qo'shardi.
    To'g'ri chaqiruv yo'li llm_router.py da allaqachon mavjud edi
    (get_meta_cognition().introspect(consciousness_state, valence_state,
    arousal_state)) — shu naqsh shu yerda takrorlangan, faqat
    consciousness_state/arousal_state bu orchestrator ichida mavjud emas
    (None uzatiladi — introspect() buni xavfsiz ishlaydi)."""
    if _mc is None:
        return ""
    mc_inst = _mc.get_meta_cognition()
    vs_inst = None
    if _vs is not None and hasattr(_vs, "get_valence_state"):
        vs_inst = _safe_call(_vs.get_valence_state, default=None)
    report = _safe_call(mc_inst.introspect, None, vs_inst, None, default={}) or {}
    self_report = report.get("self_report", "")
    return f"[Ichki holat] {self_report}" if self_report else ""


def _global_workspace_context() -> str:
    """global_workspace.GlobalWorkspace uchun kontekst matni.

    BUG FIX (2026-08-18): xuddi meta_cognition kabi — modul darajasida
    "get_broadcast"/"get_context"/"get_workspace_context" nomlaridan biri
    qidirilardi, lekin global_workspace.py faqat get_workspace() singleton
    factory'ni va GlobalWorkspace klassini (broadcast_text() instance
    metodi bilan) export qiladi. To'g'ri yo'l: get_workspace().broadcast_text().
    Agar hozircha buferga hech narsa qo'shilmagan bo'lsa (main.py dagi
    ws.add_intent()/ws.add_surprise() hali chaqirilmagan) — natija haqiqatda
    bo'sh bo'lishi mumkin, bu endi BUG emas, chunki chaqiruv real ishlaydi."""
    if _gw is None:
        return ""
    ws = _gw.get_workspace()
    return _safe_call(ws.broadcast_text, 5, default="") or ""


def _indep(key: str, fn, *args, default: str = "", **kwargs) -> str:
    """Query'ga bog'liq BO'LMAGAN qatlam uchun kesh-qobiq.

    Agar prewarm_independent_context() shu turnning STT bosqichida allaqachon
    hisoblab ulgurgan bo'lsa — shu yerdan 0ms da qaytadi (qayta chaqirilmaydi).
    Aks holda (masalan prewarm ishlamagan/vaqt yetmagan/eski kod yo'li) —
    xuddi avvalgidek sinxron hisoblanadi, natija esa keyingi safar uchun
    keshga yoziladi. Xulosa: to'g'rilik HECH QACHON prewarm ishlashiga
    bog'liq emas — bu FAQAT tezlashtirish, hech qachon zarur shart emas.

    BUG FIX (haqiqiy test bilan topildi, 2026-08-18): agar prewarm threadi
    VA asosiy thread (get_full_context) BIR VAQTDA bir xil key'ni kesh bo'sh
    holda topsa — ikkalasi ham xuddi shu OG'IR funksiyani PARALLEL chaqirib
    yuborardi (masalan ikkalasi ham theory_of_mind.get_tom_context_for_llm()ni
    bir vaqtda). Real o'lchovda bu holat bitta chaqiruvni 500ms o'rniga
    16+ SONIYAGA cho'zdi (GIL/disk I/O raqobati — ikkita thread bitta og'ir
    ishni bir vaqtda bajarishga urinishi hech qachon tezroq bo'lmaydi, faqat
    sekinlashtiradi). Endi: kim BIRINCHI kelsa — hisoblaydi (Event orqali
    belgilaydi); ikkinchi thread esa hisoblamaydi, birinchisi tugashini
    kutadi (_INDEP_WAIT_TIMEOUT ichida) va tayyor natijani ishlatadi."""
    now = time.time()
    is_owner = False
    ev = None
    with _indep_lock:
        hit = _indep_cache.get(key)
        if hit is not None and (now - hit[1]) < _INDEP_TTL:
            return hit[0]
        ev = _indep_inflight.get(key)
        if ev is None:
            ev = threading.Event()
            _indep_inflight[key] = ev
            is_owner = True

    if not is_owner:
        # Boshqa thread (odatda prewarm) ALLAQACHON shu qatlamni hisoblamoqda —
        # QAYTA hisoblamaymiz (bu aynan o'lchov bilan topilgan sekinlashuvning
        # sababi edi), shunchaki tugashini kutamiz.
        if ev.wait(timeout=_INDEP_WAIT_TIMEOUT):
            with _indep_lock:
                hit = _indep_cache.get(key)
            if hit is not None:
                return hit[0]
        # Kutish muddati tugadi yoki natija kutilmaganda kesh'ga tushmadi —
        # xavfsiz fallback: o'zimiz hisoblaymiz (juda kam uchraydigan holat).

    val = _safe_call(fn, *args, default=default, **kwargs) or ""
    with _indep_lock:
        _indep_cache[key] = (val, time.time())
        _indep_inflight.pop(key, None)
    if is_owner:
        ev.set()
    return val


def prewarm_independent_context() -> float:
    """So'rovga bog'liq bo'lmagan ~21 qatlamni OLDINDAN hisoblab, keshga
    yozadi. Chaqiruvchi buni STT (transkripsiya) bilan PARALLEL, alohida
    threadda chaqirishi kerak — shunda foydalanuvchi ovozi matnga
    aylantirilib turgan vaqt behuda o'tmaydi.

    Qaytaradi: sarflangan vaqt (soniya) — chaqiruvchi buni [TIMING] logiga
    yozishi mumkin (haqiqiy o'lchov, taxmin emas)."""
    _t0 = time.perf_counter()
    try:
        _indep("theory_of_mind", _tom.get_tom_context_for_llm, default="") if _tom else None
        if _ns is not None and hasattr(_ns, "get_narrative_for_llm"):
            _indep("narrative_self_5", _ns.get_narrative_for_llm, default="")
        if _mc is not None:
            _indep("meta_cognition_6", _meta_cognition_context, default="")
        if _gw is not None:
            _indep("global_workspace_7", _global_workspace_context, default="")
        _indep("attention_schema", _at.get_context_for_llm, default="") if _at else None
        _indep("volition", _vol.get_context_for_llm, default="") if _vol else None
        _indep("temporal_binding", _tb.get_context_for_llm, default="") if _tb else None
        _indep("social_simulation", _soc.get_context_for_llm, default="") if _soc else None
        _indep("self_improvement_loop", _sil.get_context_for_llm, default="") if _sil else None
        _indep("cross_modal_binding", _cmb.get_context_for_llm, default="") if _cmb else None
        _indep("working_memory_buffer", _wm.get_context_for_llm, default="") if _wm else None
        _indep("phenomenal_binding", _pb.get_context_for_llm, default="") if _pb else None
        _indep("self_narrative_21", _sn.get_context_for_llm, default="") if _sn else None
        _indep("emotion_memory_link", _eml.get_context_for_llm, default="") if _eml else None
        _indep("creativity_engine", _cre.get_context_for_llm, default="") if _cre else None
        _indep("meta_meta_cognition", _mmc.get_context_for_llm, default="") if _mmc else None
        _indep("turing_test_prep", _ttp.get_naturalness_hints, default="") if _ttp else None
        _indep("social_bonding", _sb.get_context_for_llm, default="") if _sb else None
        _indep("autobiographical_memory", _abm.get_context_for_llm, default="") if _abm else None
        _indep("moral_reasoning", _mr.get_context_for_llm, default="") if _mr else None
        _indep("self_healing", _sh.get_context_for_llm, default="") if _sh else None
        # vision_emotion_bridge ATAYLAB YO'Q — qarang yuqoridagi katta izoh
        # (Windows GDI/mss fon-thread hazard, real test bilan topildi).
        # Og'ir, lekin query'ga bog'liq BO'LMAGAN qatlam — embodied_grounding
        # (get_context_for_llm() argumentsiz chaqiriladi, pastda ham xuddi shu)
        if _emb:
            _indep("embodied_grounding", _emb.get_context_for_llm, default="")
    except Exception as e:
        log.debug("[Orchestrator] prewarm_independent_context xato: %s", e)
    return time.perf_counter() - _t0


def get_full_context(query: str = "", include_heavy: bool = True) -> str:
    """Barcha ong qatlamlaridan LLM uchun kontekst yig'ish.

    Args:
        query:         Foydalanuvchi so'rovi (xotira qidirish uchun)
        include_heavy: True = hamma qatlamlar, False = faqat tez qatlamlar

    Returns: Ko'p qatorli kontekst matni
    """
    # Kesh tekshiruvi
    cache_key = f"{query[:50]}|{include_heavy}"
    cached = _ctx_cache.get(cache_key)
    if cached:
        result, ts = cached
        if time.time() - ts < _CTX_TTL:
            return result

    # Tashlangan qatlamlar ro'yxati — shu turn uchun toza boshlanadi
    reset_turn_drops()

    # ── GWT-4: javobdan OLDIN o'ylash ───────────────────────────────────────
    # Savol o'qiladi, turi va mavzusi aniqlanadi, keyin FAQAT kerakli
    # modullar so'raladi. Ilgari har savolda barcha 47 tasi so'ralardi.
    # PP-1: joriy savolni OLDINGI navbatda qilingan bashorat bilan solishtirish.
    # Kontekstdan oldin — hayrat javobga ta'sir qilishi kerak.
    surprise = None
    if _pe is not None and query:
        try:
            _sc = _pe.score_turn(query)
            surprise = _sc.get("surprise")
        except Exception as e:
            log.warning("[Orchestrator] prediction_error xato: %s", e)

    plan = None
    if _ar is not None and query:
        try:
            _v = 0.0
            if _eg is not None:
                _v = _safe_call(_eg.get_valence, default=0.0) or 0.0
            plan = _ar.plan_attention(query, valence=_v)
            # Kutilmagan burilishda chuqurroq ishlov: odam ham shunday qiladi
            if surprise is not None and surprise >= 0.75 and plan.depth != "deep":
                plan.depth = "deep"
                plan.modules |= {"meta_cognition", "metacognitive_confidence",
                                 "causal_chain", "counterfactual_engine"}
        except Exception as e:
            log.warning("[Orchestrator] attention_router xato: %s", e)

    # AST-1: diqqatni javobdan OLDIN o'rnatish. Ilgari on_user_query() faqat
    # on_user_message() da, ya'ni javobdan keyin chaqirilardi — shuning uchun
    # diqqat sxemasi doim 'idle' bo'lib, kontekstga hech narsa qo'shmasdi.
    if _at is not None and query:
        try:
            _safe_call(_at.on_user_query, query)
            if plan is not None and hasattr(_at, "add_parallel"):
                _safe_call(_at.add_parallel, plan.intent, plan.topic or query[:40],
                           float(plan.confidence))
        except Exception as e:
            log.warning("[Orchestrator] attention_schema xato: %s", e)

    def _use(module_name: str) -> bool:
        """Shu modul shu savolda so'ralsinmi? Reja yo'q bo'lsa — hammasi."""
        if plan is None or _ar is None:
            return True
        return _ar.should_query(module_name, plan)

    # ── PARALLEL: og'ir (tarmoq/disk) qatlamlarni DARHOL fon threadida
    # boshlash ──────────────────────────────────────────────────────────
    # O'lchandi: vector_memory.get_context_for_llm() (OpenAI embedding
    # tarmoq so'rovi) yolg'iz ~1.8-2s, sovuq holatda 5s+ oladi — bu butun
    # get_full_context() vaqtining katta qismini yeydi, chunki ilgari
    # ketma-ket (boshqa ~30 qatlamdan KEYIN, ular tugagach) chaqirilardi.
    # Endi shu og'ir chaqiruvlar ENG BOSHIDA, PARALLEL boshlanadi — pastda
    # o'z navbatiga yetganda (bir necha ONlab boshqa qatlam allaqachon
    # ishlab bo'lgan bo'ladi) natija tayyor yoki deyarli tayyor bo'ladi.
    # Timeout bilan chegaralangan — sekin tarmoq BUTUN turnni cheksiz
    # ushlab turmaydi, shu qatlam shunchaki shu safar o'tkazib yuboriladi.
    _fut_vm = (_submit(_vm.get_context_for_llm, query, 3)
               if (_vm and query and _use('vector_memory')) else None)
    _fut_lv = (_submit(_lv.get_context_for_llm, query)
               if (_lv is not None and query and _use('embodied_grounding')) else None)
    _fut_ki = (_submit(_ki.get_context_for_llm, query, 3)
               if (_ki is not None and query and _use('knowledge_index')) else None)
    _fut_em = (_submit(_em.get_context_for_llm, query)
               if (_em and query and _use('episodic_memory')) else None)
    # embodied_grounding — query'ga bog'liq EMAS (argumentsiz). Agar
    # prewarm_independent_context() STT paytida allaqachon hisoblab bo'lgan
    # bo'lsa (qarang pastda "14. Jismoniy asoslanish"), bu yerda YANGI
    # Future UMUMAN ochilmaydi — bekorchi ish/thread tejaladi.
    with _indep_lock:
        _emb_hit = _indep_cache.get("embodied_grounding")
        _emb_fresh = _emb_hit is not None and (time.time() - _emb_hit[1]) < _INDEP_TTL
    _fut_emb = (_submit(_emb.get_context_for_llm)
                if (_emb and _use('embodied_grounding') and not _emb_fresh) else None)

    parts: List[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M, %A")
    parts.append(f"[VAQT] {ts}")

    # So'zma-so'z o'qimaslik + foydalanuvchi profili (doimiy uslub direktivi)
    if _rs is not None:
        _rs_ctx = _bounded(_rs.get_context_for_llm, query or "", name="response_style", timeout=0.6, default="")
        if _rs_ctx:
            parts.append(_rs_ctx)

    # Til aniqlash — javob AYNAN shu tilda bo'lsin (uz/ru/en adashmasin)
    if _ld is not None and query:
        try:
            _lr = _ld.detect(query)
            _lname = {"uz": "o'zbekcha", "ru": "ruscha (по-русски)",
                      "en": "English", "other": "aniqlanmadi"}.get(_lr.lang, _lr.lang)
            if _lr.lang != "other":
                parts.append(f"[TIL] Foydalanuvchi {_lname} yozdi — javobni "
                             f"AYNAN shu tilda ber ({_lr.confidence:.0%}).")
        except Exception as e:
            log.warning("[Orchestrator] language_detect xato: %s", e)

    if plan is not None:
        parts.append(plan.as_context_line())
    if _pe is not None and query:
        _pe_ctx = _bounded(_pe.get_context_for_llm, query, name="prediction_error", timeout=0.6, default="")
        if _pe_ctx:
            parts.append(_pe_ctx)

    # 0. DOIMIY XOTIRA — barcha sessiyalardagi tarix
    _mem_hits = 0
    if _pm and _use('permanent_memory'):
        pm_ctx = _bounded(_pm.get_context_for_llm, query or "", 5,
                          name="permanent_memory.get_context_for_llm", timeout=0.8, default="")
        if pm_ctx:
            parts.append(pm_ctx)
            # Xotira qamrovi — metakognitsiya uchun (asos bormi?)
            if query:
                _found = _bounded(_pm.recall, query, 5,
                                  name="permanent_memory.recall", timeout=0.6, default=[]) or []
                _mem_hits = len(_found)

    # HOT-2/3: metakognitiv nazorat — hayrat + ishonch + xotira qamrovi.
    # Ishonch past bo'lsa tizim SO'RAYDI/TEKSHIRADI, ishongandek gapirmaydi.
    if _mk is not None and query:
        _mk_ctx = _bounded(_mk.get_context_for_llm_full, query, surprise, _mem_hits,
                           name="metacognitive_control", timeout=0.6, default="")
        if _mk_ctx:
            parts.append(_mk_ctx)

    # Savol xotirasi: "shunga o'xshash so'ragan eding"
    if _qm is not None and query:
        _qm_ctx = _bounded(_qm.get_context_for_llm, query, name="question_memory", timeout=0.6, default="")
        if _qm_ctx:
            parts.append(_qm_ctx)

    # 1. Semantik xotira (fon threadida ENG BOSHIDA boshlangan — qarang yuqorida)
    if _fut_vm is not None:
        ctx = _resolve(_fut_vm, 2.5, "vector_memory")
        if ctx:
            parts.append(ctx)

    # 1a. Jonli ekran — ekranda nima borligi (keshdan, tez)
    if _fut_lv is not None:
        _lv_ctx = _resolve(_fut_lv, 1.5, "live_vision")
        if _lv_ctx:
            parts.append(_lv_ctx)

    # 1b. Lokal bilim bazasi — faktik savolga <1s da javob (GPU FAISS)
    if _fut_ki is not None:
        ki_ctx = _resolve(_fut_ki, 1.5, "knowledge_index")
        if ki_ctx:
            parts.append(ki_ctx)

    # 2. Maqsadlar
    if _gs and _use('goal_system'):
        # AE-1: query uzatiladi — savolga qarab dolzarb maqsad tanlanadi
        goal_ctx = _bounded(_gs.get_goals_for_llm, query or "", name="goal_system", timeout=0.6, default="")
        if goal_ctx:
            parts.append(goal_ctx)

    # 3. Foydalanuvchi modeli (query'ga bog'liq emas — prewarm bilan keshlanadi,
    # qarang _indep()/prewarm_independent_context() yuqorida)
    if _tom and _use('theory_of_mind'):
        tom_ctx = _indep("theory_of_mind", _tom.get_tom_context_for_llm, default="")
        if tom_ctx:
            parts.append(tom_ctx)

    # 4. Sabab-natija
    if _cc and _use('causal_chain'):
        for attr in ["get_causal_context_for_llm", "get_context_for_llm", "get_causal_context"]:
            if hasattr(_cc, attr):
                cc_ctx = _bounded(getattr(_cc, attr), query or "umumiy", name="causal_chain", timeout=0.6, default="")
                if cc_ctx:
                    parts.append(cc_ctx)
                break

    # 5. Narrativ o'zlik (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _ns and include_heavy and _use('narrative_self') and hasattr(_ns, "get_narrative_for_llm"):
        ns_ctx = _indep("narrative_self_5", _ns.get_narrative_for_llm, default="")
        if ns_ctx:
            parts.append(ns_ctx)

    # 6. Meta-kognitsiya (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _mc and include_heavy and _use('meta_cognition'):
        mc_ctx = _indep("meta_cognition_6", _meta_cognition_context, default="")
        if mc_ctx:
            parts.append(mc_ctx)

    # 7. Global workspace (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _gw and _use('global_workspace'):
        gw_ctx = _indep("global_workspace_7", _global_workspace_context, default="")
        if gw_ctx:
            parts.append(gw_ctx)

    # 8. Diqqat sxemasi (AST) (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _at and _use('attention_schema'):
        at_ctx = _indep("attention_schema", _at.get_context_for_llm, default="")
        if at_ctx:
            parts.append(at_ctx)

    # 9. Iroda holati (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _vol and _use('volition'):
        vol_ctx = _indep("volition", _vol.get_context_for_llm, default="")
        if vol_ctx:
            parts.append(vol_ctx)

    # 10. Vaqt idrok (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _tb and _use('temporal_binding'):
        tb_ctx = _indep("temporal_binding", _tb.get_context_for_llm, default="")
        if tb_ctx:
            parts.append(tb_ctx)

    # 11. 27 his-tuyg'u
    if _eg and _use('emotional_granularity'):
        # query uzatiladi: busiz hissiy holat oldingi navbatdan qoladi
        eg_ctx = _bounded(_eg.get_context_for_llm, query or "", name="emotional_granularity", timeout=0.6, default="")
        if eg_ctx:
            parts.append(eg_ctx)

    # 12. Ijtimoiy holat (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _soc and _use('social_simulation'):
        soc_ctx = _indep("social_simulation", _soc.get_context_for_llm, default="")
        if soc_ctx:
            parts.append(soc_ctx)

    # 13. O'z-o'zini yaxshilash (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _sil and _use('self_improvement_loop'):
        sil_ctx = _indep("self_improvement_loop", _sil.get_context_for_llm, default="")
        if sil_ctx:
            parts.append(sil_ctx)

    # 14. Jismoniy asoslanish — og'ir, lekin query'ga bog'liq EMAS (argumentsiz
    # chaqiriladi). Avval PREWARM keshini tekshiramiz — agar STT paytida
    # allaqachon hisoblab bo'lingan bo'lsa, hech qanday Future kutilmaydi
    # (0ms). Aks holda eski yo'l — fon threadida yuqorida boshlangan
    # _fut_emb kutiladi (xavfsiz fallback, xatti-harakat o'zgarmaydi).
    _emb_prewarmed = None
    with _indep_lock:
        _hit = _indep_cache.get("embodied_grounding")
        if _hit is not None and (time.time() - _hit[1]) < _INDEP_TTL:
            _emb_prewarmed = _hit[0]
    if _emb_prewarmed is not None:
        if _emb_prewarmed:
            parts.append(_emb_prewarmed)
    elif _fut_emb is not None:
        emb_ctx = _resolve(_fut_emb, 1.5, "embodied_grounding")
        if emb_ctx:
            parts.append(emb_ctx)
            with _indep_lock:
                _indep_cache["embodied_grounding"] = (emb_ctx, time.time())

    # 15. Ko'p modal (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _cmb and _use('cross_modal_binding'):
        cmb_ctx = _indep("cross_modal_binding", _cmb.get_context_for_llm, default="")
        if cmb_ctx:
            parts.append(cmb_ctx)

    # 16. Faol ish xotirasi (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _wm and _use('working_memory_buffer'):
        wm_ctx = _indep("working_memory_buffer", _wm.get_context_for_llm, default="")
        if wm_ctx:
            parts.append(wm_ctx)

    # 17. Meta-ishonch
    if _mcc and query and _use('metacognitive_confidence'):
        mcc_ctx = _bounded(_mcc.get_context_for_llm, query, name="metacognitive_confidence", timeout=0.6, default="")
        if mcc_ctx:
            parts.append(mcc_ctx)

    # 18. Kvant noaniqlik
    if _qc and query and _use('quantum_cognition'):
        qc_ctx = _bounded(_qc.get_superposition_context, query, name="quantum_cognition", timeout=0.6, default="")
        if qc_ctx:
            parts.append(qc_ctx)

    # 19. Epizodik xotira (fon threadida ENG BOSHIDA boshlangan)
    if _fut_em is not None:
        em_ctx = _resolve(_fut_em, 1.5, "episodic_memory")
        if em_ctx:
            parts.append(em_ctx)

    # 20. Fenomenal integratsiya (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _pb and _use('phenomenal_binding'):
        pb_ctx = _indep("phenomenal_binding", _pb.get_context_for_llm, default="")
        if pb_ctx:
            parts.append(pb_ctx)

    # 21. O'zlik narrativi (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _sn and _use('self_narrative'):
        sn_ctx = _indep("self_narrative_21", _sn.get_context_for_llm, default="")
        if sn_ctx:
            parts.append(sn_ctx)

    # 22. Fikr tili (Mentalese)
    if _lot and query and _use('language_of_thought'):
        lot_ctx = _bounded(_lot.get_context_for_llm, query, name="language_of_thought", timeout=0.6, default="")
        if lot_ctx:
            parts.append(lot_ctx)

    # 23. Erkin iroda
    if _fw and _use('free_will_simulator'):
        fw_ctx = _bounded(_fw.get_context_for_llm, query or "", name="free_will_simulator", timeout=0.6, default="")
        if fw_ctx:
            parts.append(fw_ctx)

    # 25. Hissiy-xotira bog'liqlik (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _eml and _use('emotion_memory_link'):
        eml_ctx = _indep("emotion_memory_link", _eml.get_context_for_llm, default="")
        if eml_ctx:
            parts.append(eml_ctx)

    # 26. Ijodiy g'oya (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _cre and _use('creativity_engine'):
        cre_ctx = _indep("creativity_engine", _cre.get_context_for_llm, default="")
        if cre_ctx:
            parts.append(cre_ctx)

    # 27. Meta-meta-kognitsiya (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _mmc and _use('meta_meta_cognition'):
        mmc_ctx = _indep("meta_meta_cognition", _mmc.get_context_for_llm, default="")
        if mmc_ctx:
            parts.append(mmc_ctx)

    # 28. Turing tayyorlik (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _ttp and _use('turing_test_prep'):
        ttp_ctx = _indep("turing_test_prep", _ttp.get_naturalness_hints, default="")
        if ttp_ctx:
            parts.append(f"[TURING] {ttp_ctx}")

    # 29. Ijtimoiy bog'liqlik (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _sb and _use('social_bonding'):
        sb_ctx = _indep("social_bonding", _sb.get_context_for_llm, default="")
        if sb_ctx:
            parts.append(sb_ctx)

    # 30. Hayot hikoyasi (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _abm and _use('autobiographical_memory'):
        abm_ctx = _indep("autobiographical_memory", _abm.get_context_for_llm, default="")
        if abm_ctx:
            parts.append(abm_ctx)

    # 31. Axloqiy kontekst (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _mr and _use('moral_reasoning'):
        mr_ctx = _indep("moral_reasoning", _mr.get_context_for_llm, default="")
        if mr_ctx:
            parts.append(mr_ctx)

    # 32. Tizim salomatligi (query'ga bog'liq emas — prewarm bilan keshlanadi)
    if _sh and _use('self_healing'):
        sh_ctx = _indep("self_healing", _sh.get_context_for_llm, default="")
        if sh_ctx:
            parts.append(sh_ctx)

    # 33. Ko'rish+his ko'prik — ATAYLAB _indep()/prewarm orqali EMAS, ORIGINAL
    # sinxron yo'l bilan (real test bilan topildi: bu qatlam Windows'da
    # mss/GDI ekran-olishga tayanadi, fon threadida chaqirilsa vaqti-vaqti
    # bilan 100+ soniyaga osilib qolishi mumkin — asosiy threadda esa hech
    # qachon bunday bo'lmadi. Qarang _indep_cache yuqoridagi katta izoh).
    if _veb and _use('vision_emotion_bridge'):
        veb_ctx = _safe_call(_veb.get_context_for_llm, default="")
        if veb_ctx:
            parts.append(veb_ctx)

    # 24. Ong darajasi
    score = get_consciousness_score()
    score_pct = int(score * 100)
    bar = "█" * (score_pct // 10) + "░" * (10 - score_pct // 10)
    parts.append(f"[ONG DARAJASI] {bar} {score_pct}%")

    # Bo'sh qismlarni olib tashlash
    result = "\n".join(p for p in parts if p and p.strip())

    # Axborot darvozasi — o'zgarmas bo'limlarni so'ndirish.
    # O'lchangan edi: kontekstning ~73% i har qanday savolda bir xil
    # matn edi. Filtr o'z-o'zini sozlaydi: modul javob bera boshlasa,
    # bo'lim avtomatik qaytadi. Xato bo'lsa — kontekst tegilmay o'tadi.
    if _cf is not None:
        try:
            result = _cf.filter_context(result, query or "")
        except Exception as e:
            log.warning("[Orchestrator] context_filter xato: %s", e)

    # Keshga saqlash
    _ctx_cache[cache_key] = (result, time.time())
    # Eski kesh yozuvlarini tozalash (max 20 ta)
    if len(_ctx_cache) > 20:
        oldest = min(_ctx_cache.items(), key=lambda x: x[1][1])
        _ctx_cache.pop(oldest[0], None)

    # ── Tashlangan qatlamlar hisoboti (NEUROKEY_TODO 1.13) ──────────────────
    # Jimgina tushib qolgan qatlam endi KO'RINADI. O'chirish:
    # NEUROKEY_DROP_REPORT=0
    if _DROP_REPORT:
        _drops = get_last_turn_drops()
        if _drops:
            _tmo = [d for d in _drops if d["reason"] == "TIMEOUT"]
            _err = [d for d in _drops if d["reason"] != "TIMEOUT"]
            _bits = []
            if _tmo:
                _bits.append("timeout: " + ", ".join(
                    f"{d['layer']}({d['ms']}ms)" for d in _tmo[:6]))
            if _err:
                _bits.append("xato: " + ", ".join(
                    f"{d['layer']}" for d in _err[:6]))
            print(f"[ONG-TASHLANDI] {len(_drops)} qatlam bu turnda ishlatilmadi "
                  f"— {' | '.join(_bits)}", flush=True)

    return result


def on_user_message(user_text: str, assistant_reply: str = "") -> None:
    """Har foydalanuvchi xabari kelganda barcha modullarni yangilash.

    Bu funksiyani main.py da har javobdan keyin chaqirish kerak.
    """
    if not user_text:
        return

    # 0. DOIMIY XOTIRA — hech qachon o'chmaydi
    if _pm:
        _safe_call(_pm.remember_conversation, user_text, assistant_reply)

    # 1. Foydalanuvchi modeli yangilash
    if _tom:
        _safe_call(_tom.update_from_message, user_text, assistant_reply)

    # 2. Vektor xotirasiga saqlash
    if _vm and assistant_reply:
        _safe_call(_vm.add_conversation, user_text, assistant_reply)

    # 3. Uzoq muddatli xotiraga saqlash
    if _ltm:
        for attr in ["save_interaction", "add", "save"]:
            if hasattr(_ltm, attr):
                _safe_call(getattr(_ltm, attr), user_text, assistant_reply)
                break

    # 4-29. Mustaqil modullarni PARALLEL yangilash (ThreadPoolExecutor)
    def _update_tasks():
        tasks: List[Callable] = []

        if _gs:    tasks.append(lambda: _safe_call(_gs.auto_detect_goal_from_text, user_text))
        if _cc:    tasks.append(lambda: _safe_call(_cc.extract_causal_from_text, user_text))
        if _ps:    tasks.append(lambda: _safe_call(_ps.record_user_activity))
        if _at:    tasks.append(lambda: _safe_call(_at.on_user_query, user_text))
        if _pe:    tasks.append(lambda: _safe_call(_pe.predict_next, user_text, assistant_reply))
        if _qm:    tasks.append(lambda: _safe_call(_qm.remember, user_text, assistant_reply))
        if _eg:    tasks.append(lambda: _safe_call(_eg.update_from_text, user_text))
        if _vol:   tasks.append(lambda: _safe_call(_vol.deliberate, user_text))
        if _cfe:   tasks.append(lambda: _safe_call(_cfe.extract_from_text, user_text))
        if _cmb:   tasks.append(lambda: _safe_call(_cmb.auto_receive_from_message, user_text))
        if _pb:    tasks.append(lambda: _safe_call(_pb.update, user_text))
        if _fw:    tasks.append(lambda: _safe_call(_fw.generate_intention, user_text))
        if _pps:   tasks.append(lambda: _safe_call(_pps.detect_feedback, user_text))
        if _mr:    tasks.append(lambda: _safe_call(_mr.evaluate_ethical_query, user_text))
        if _sh:    tasks.append(lambda: _safe_call(_sh.run_health_check))
        if _veb:   tasks.append(lambda: _safe_call(_veb.process_voice_text, user_text))

        if _tb:
            tasks.append(lambda: _safe_call(_tb.record, "user_input", user_text))
            if assistant_reply:
                tasks.append(lambda: _safe_call(_tb.record, "llm_response", assistant_reply[:100]))

        if assistant_reply:
            if _soc:  tasks.append(lambda: _safe_call(_soc.update_from_interaction, user_text, assistant_reply))
            if _sil:  tasks.append(lambda: _safe_call(_sil.evaluate_response, user_text, assistant_reply))
            if _wm:   tasks.append(lambda: _safe_call(_wm.auto_store_from_message, user_text, assistant_reply))
            if _em:   tasks.append(lambda: _safe_call(_em.auto_record_from_conversation, user_text, assistant_reply))
            if _sn:   tasks.append(lambda: _safe_call(_sn.update_from_conversation, user_text, assistant_reply))
            if _eml:  tasks.append(lambda: _safe_call(_eml.tag_and_store, user_text, assistant_reply))
            if _scc:  tasks.append(lambda: _safe_call(_scc.check_consistency, assistant_reply, user_text))
            if _cl:   tasks.append(lambda: _safe_call(_cl.learn_from_conversation, user_text, assistant_reply))
            if _abm:  tasks.append(lambda: _safe_call(_abm.auto_record_from_conversation, user_text, assistant_reply))

        if _ce:
            def _ce_update():
                for attr in ["on_interaction", "update", "feed"]:
                    if hasattr(_ce, attr):
                        _safe_call(getattr(_ce, attr), user_text)
                        break
            tasks.append(_ce_update)

        if _dp:
            def _dp_update():
                if _safe_call(_dp.should_consolidate, default=False):
                    _safe_call(_dp.consolidate)
            tasks.append(_dp_update)

        if _sb and _tom:
            def _sb_update():
                user_name = "foydalanuvchi"
                try:
                    model = _safe_call(_tom.get_user_model, default={}) or {}
                    user_name = model.get("name", "foydalanuvchi") or "foydalanuvchi"
                except Exception:
                    pass
                _safe_call(_sb.update_bond, user_name, user_text)
            tasks.append(_sb_update)

        # Parallel ishga tushirish — timeout 2.0s. ALOHIDA _BG_EXECUTOR
        # ishlatiladi (qarang yuqoridagi izoh) — shu orqali bu orqa fon
        # yozuvlar keyingi turnning get_full_context() future'lari bilan
        # bitta havzani TALASHMAYDI.
        futures = [_BG_EXECUTOR.submit(t) for t in tasks]
        for f in as_completed(futures, timeout=2.0):
            try:
                f.result(timeout=1.5)
            except Exception as e:
                log.debug("[Orchestrator] parallel update error: %s", e)

    try:
        _update_tasks()
    except Exception as e:
        log.debug("[Orchestrator] _update_tasks failed: %s", e)


def check_proactive_message() -> Optional[str]:
    """Proaktiv xabar bormi? (fon dan)."""
    if not _ps:
        return None
    return _safe_call(_ps.check_and_generate, default=None)


def get_status_summary() -> Dict[str, Any]:
    """Tizim holati — monitoring uchun."""
    loaded_modules = {
        "permanent_memory":_pm  is not None,
        "vector_memory":   _vm  is not None,
        "goal_system":     _gs  is not None,
        "theory_of_mind":  _tom is not None,
        "causal_chain":    _cc  is not None,
        "proactive_speech":_ps  is not None,
        "dream_consolidator": _dc is not None,
        "narrative_self":  _ns  is not None,
        "curiosity_engine":_ce  is not None,
        "background_sensor":_bs is not None,
        "long_term_memory":_ltm is not None,
        "meta_cognition":  _mc  is not None,
        "global_workspace":_gw  is not None,
        "valence_state":   _vs  is not None,
        "predictive_layer":_pl  is not None,
        "active_inference":_ai  is not None,
        "attention_schema":_at  is not None,
        "volition":        _vol is not None,
        "temporal_binding":_tb  is not None,
        "emotional_gran":  _eg  is not None,
        "self_improve":    _sil is not None,
        "social_sim":      _soc is not None,
        "counterfactual":  _cfe is not None,
        "embodied":        _emb is not None,
        "cross_modal":     _cmb is not None,
        "quantum_cog":     _qc  is not None,
        "working_mem":     _wm  is not None,
        "metacog_conf":    _mcc is not None,
        "episodic_memory": _em  is not None,
        "phenomenal":      _pb  is not None,
        "self_narrative":  _sn  is not None,
        "lang_of_thought": _lot is not None,
        "free_will":       _fw  is not None,
        "emotion_mem_link":_eml is not None,
        "dream_processor": _dp  is not None,
        "self_consist":    _scc is not None,
        "creativity":      _cre is not None,
        "pain_pleasure":   _pps is not None,
        "cont_learning":   _cl  is not None,
        "meta_meta_cog":   _mmc is not None,
        "turing_prep":     _ttp is not None,
        "social_bonding":  _sb  is not None,
        "autobio_memory":  _abm is not None,
        "moral_reasoning": _mr  is not None,
        "self_healing":    _sh  is not None,
        "vision_emotion":  _veb is not None,
    }
    loaded_count  = sum(loaded_modules.values())
    total_modules = len(loaded_modules)

    # Maqsadlar
    active_goals = 0
    if _gs:
        goals = _safe_call(_gs.get_active_goals, default=[]) or []
        active_goals = len(goals)

    # Xotira
    mem_count = 0
    if _vm:
        stats = _safe_call(_vm.get_stats, default={}) or {}
        mem_count = stats.get("total_memories", 0)

    return {
        "consciousness_score": get_consciousness_score(),
        "modules_loaded":      f"{loaded_count}/{total_modules}",
        "active_goals":        active_goals,
        "semantic_memories":   mem_count,
        "modules":             loaded_modules,
        "timestamp":           datetime.now().isoformat(),
    }


def startup_report() -> str:
    """Ishga tushishda ong holati haqida qisqa hisobot."""
    status = get_status_summary()
    score  = status["consciousness_score"]
    loaded = status["modules_loaded"]
    goals  = status["active_goals"]
    mems   = status["semantic_memories"]

    score_pct = int(score * 100)
    bar = "█" * (score_pct // 10) + "░" * (10 - score_pct // 10)

    lines = [
        f"NeuroKey Ong Tizimi tayyor.",
        f"Ong darajasi : {bar} {score_pct}%",
        f"Modullar     : {loaded} yuklandi",
        f"Maqsadlar    : {goals} faol",
        f"Xotira       : {mems} semantik yozuv",
    ]
    return "\n".join(lines)
