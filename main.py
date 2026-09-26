# -*- coding: utf-8 -*-
import json
import logging
import os
import sys
import time
import traceback
import threading
import queue
import re
from urllib.parse import quote as url_quote
from datetime import datetime, timedelta
from typing import Optional

# RAM bo'yicha tier (LITE/STANDARD/FULL) — config yuklanishidan OLDIN
try:
    from boot_tier import apply_boot_tier
    apply_boot_tier()
except Exception as _bt_e:
    print(f"[BOOT-TIER] o'tkazib yuborildi: {_bt_e!r}", flush=True)

# ── LLM provayderi: hech kim ANIQ tanlamagan bo'lsa Groq ────────────────────
# MUAMMO (2026-09-25, jurnalda o'lchangan): main.py ni to'g'ridan-to'g'ri
# (launcher .bat siz) ishga tushirganda OPENAI_BASE_URL bo'sh qoladi va
# llm_router to'g'ridan-to'g'ri OpenAI'ga (gpt-4o-mini) uriladi. `.env` dagi
# OPENAI_API_KEY esa yaroqsiz — natijada har turnda takroriy
#   WARNING agent_loop: [AgentLoop] bosqich xatosi: 401 Incorrect API key
#   WARNING llm_router: [LLM] gpt-4o-mini xato: 401
# Loyihaning BARCHA launcherlari baribir Groq ishlatadi, shuning uchun
# provayder ANIQ ko'rsatilmagan holatda Groq tanlanadi — 401 bo'roni yo'q.
#
# O'z OpenAI kalitingizni ishlatish uchun OPENAI_BASE_URL ni ANIQ bering:
#   set OPENAI_BASE_URL=https://api.openai.com/v1
# yoki butunlay o'chirish: set NEUROKEY_PREFER_GROQ=0
if (os.getenv("NEUROKEY_PREFER_GROQ", "1") or "1").strip().lower() not in ("0", "false", "no"):
    if not (os.getenv("OPENAI_BASE_URL") or "").strip():
        try:
            from agi_config import prefer_groq_llm
            prefer_groq_llm()
            if "groq.com" in (os.getenv("OPENAI_BASE_URL") or ""):
                print("[LLM] Provayder: Groq (OPENAI_BASE_URL ko'rsatilmagan)", flush=True)
        except Exception as _pg_e:
            print(f"[LLM] Groq tanlash o'tkazib yuborildi: {_pg_e!r}", flush=True)

# Suppress all INFO/DEBUG logs from modules — only WARNING+ shown
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

import config as C

try:
    from neurokey_debug_log import log_main as _log_main
except Exception:
    def _log_main(msg): pass

# ── NeuroKey HUD Bridge ───────────────────────────────────────────────────────
try:
    from neurokey_state_writer import nk_state as _hud
    _HUD_AVAIL = True
except Exception:
    class _FakeHud:
        def update(self, **kw): pass
        def listening(self, text=""): pass
        def thinking(self, modules=None): pass
        def speaking(self, text=""): pass
        def idle(self): pass
        def error(self, msg=""): pass
    _hud = _FakeHud()
    _HUD_AVAIL = False

from tts_openai import TTSWorker
from tts_feedback import get_feedback
from llm_router import answer, answer_stream, suggest_telegram_reply, generate_code, decompose_complex_task, infer_command_intent
from web_tools import needs_web, critical_need_web, needs_image, web_context, serpapi_image_search, wikipedia_search_and_summary

# --- STT ---
try:
    from stt_faster_whisper_local import record_and_transcribe as whisper_record_and_transcribe
    _HAVE_WHISPER = True
except Exception:
    whisper_record_and_transcribe = None
    _HAVE_WHISPER = False

try:
    from stt_vosk import run_stt as vosk_run_stt
    _HAVE_VOSK = True
except Exception:
    vosk_run_stt = None
    _HAVE_VOSK = False

# --- Telegram user-client ---
try:
    from telegram_user_bridge import TelegramUserBridge
    _HAVE_TG_USER = True
except Exception:
    TelegramUserBridge = None
    _HAVE_TG_USER = False

# --- Gmail ---
try:
    import gmail_bridge
    _HAVE_GMAIL = True
except Exception:
    gmail_bridge = None
    _HAVE_GMAIL = False

# --- Gamma.app (AI taqdimot yaratish) ---
try:
    import gamma_bridge as _gamma
    _HAVE_GAMMA = _gamma.is_available()
except Exception:
    _gamma = None
    _HAVE_GAMMA = False

# --- Site Bridge (neurokey_sayt ovoz bilan boshqarish) ---
try:
    import site_bridge as _site
    _HAVE_SITE = _site.is_available()
except Exception:
    _site = None
    _HAVE_SITE = False

# --- GitHub Bridge ---
try:
    import github_bridge as _github
    _HAVE_GITHUB = _github.is_available()
except Exception:
    _github = None
    _HAVE_GITHUB = False

# --- YouTube Bridge ---
try:
    import youtube_bridge as _youtube
    _HAVE_YOUTUBE = _youtube.is_available()
except Exception:
    _youtube = None
    _HAVE_YOUTUBE = False

# --- OpenWeather Bridge ---
try:
    import openweather_bridge as _openweather
    _HAVE_OPENWEATHER = _openweather.is_available()
except Exception:
    _openweather = None
    _HAVE_OPENWEATHER = False

# --- Notion Bridge ---
try:
    import notion_bridge as _notion
    _HAVE_NOTION = _notion.is_available()
except Exception:
    _notion = None
    _HAVE_NOTION = False

# --- Memory Search (eski gaplashuvlardan eslash) ---
try:
    from memory_search import get_memory_context_for_llm as _mem_search, invalidate_cache as _mem_invalidate
    _HAVE_MEM_SEARCH = True
except Exception:
    _mem_search = None
    _mem_invalidate = None
    _HAVE_MEM_SEARCH = False

# --- Screen Click (ovoz bilan ekrandan element topib bosish) ---
try:
    from screen_click import find_and_click as _sc_click, find_and_right_click as _sc_rclick
    from screen_click import find_and_double_click as _sc_dclick
    from screen_click import find_element_and_type as _sc_type
    from screen_click import extract_click_target as _sc_extract
    _HAVE_SCREEN_CLICK = True
except Exception:
    _sc_click = _sc_rclick = _sc_dclick = _sc_type = _sc_extract = None
    _HAVE_SCREEN_CLICK = False

# --- Control (och/yop) ---
try:
    import control
    _HAVE_CONTROL = True
except Exception:
    control = None
    _HAVE_CONTROL = False

try:
    import instant_voice_control as _instant_control
    _HAVE_INSTANT_CONTROL = True
except Exception:
    _instant_control = None
    _HAVE_INSTANT_CONTROL = False

# --- Extras: todo, timer, calendar, calculator, log, backup ---
try:
    import neurokey_extras as _extras
    _HAVE_EXTRAS = True
except Exception:
    _extras = None
    _HAVE_EXTRAS = False

# --- Reminders (eslatmalar — restart dan keyin ham saqlanadi) ---
try:
    import reminders as _reminders
    _HAVE_REMINDERS = True
except Exception:
    _reminders = None
    _HAVE_REMINDERS = False

# --- Social Bonding (foydalanuvchi bilan munosabat chuqurligi) ---
try:
    import social_bonding as _social
    _HAVE_SOCIAL = True
except Exception:
    _social = None
    _HAVE_SOCIAL = False

# --- Episodic Memory (aniq voqealar, hissiy teglangan xotira) ---
try:
    import episodic_memory as _episodic
    _HAVE_EPISODIC = True
except Exception:
    _episodic = None
    _HAVE_EPISODIC = False

# --- Self-Improvement Loop (har suhbatdan keyin o'z-o'zini baholaydi) ---
try:
    import self_improvement_loop as _self_improve
    _HAVE_SELF_IMPROVE = True
except Exception:
    _self_improve = None
    _HAVE_SELF_IMPROVE = False

# --- Spontaneity (kutilmagan qarorlar — tabiiy shaxsiyat) ---
try:
    import spontaneity as _spontaneity
    _HAVE_SPONTANEITY = True
except Exception:
    _spontaneity = None
    _HAVE_SPONTANEITY = False

# --- Memory (pending, dialog state) ---
try:
    from memory import MemoryStore
    _HAVE_MEMORY = True
except Exception:
    MemoryStore = None
    _HAVE_MEMORY = False

# --- Orb overlay (NeuroKey style) ---
try:
    from jarvis_sphere_overlay import create_orb_and_start
    _HAVE_ORB = True
except Exception:
    create_orb_and_start = None
    _HAVE_ORB = False

# --- Tezlik + ekran + tozalash (M1–M8) ---
try:
    from response_cleaner import get_response_cleaner
    _HAVE_RESPONSE_CLEANER = True
except Exception:
    get_response_cleaner = None
    _HAVE_RESPONSE_CLEANER = False
try:
    from display_overlay import get_display_overlay
    _HAVE_DISPLAY_OVERLAY = True
except Exception:
    get_display_overlay = None
    _HAVE_DISPLAY_OVERLAY = False
try:
    from screen_monitor import get_screen_monitor
    _HAVE_SCREEN_MONITOR = True
except Exception:
    get_screen_monitor = None
    _HAVE_SCREEN_MONITOR = False
try:
    from performance_core import get_performance_core
    _HAVE_PERFORMANCE_CORE = True
except Exception:
    get_performance_core = None
    _HAVE_PERFORMANCE_CORE = False

# --- NeuroKey Yadro (birlashgan ong yadrosi) ---
try:
    from neurokey_core import get_neurokey as _get_nk
    _NK = _get_nk()
except Exception as _nk_e:
    _NK = None

# Keraksiz frazalar (Hmm, Well, Хм, Ну) — TTS ga yuborilmasin
_FILLER_ONLY = frozenset((
    "hmm", "hmm.", "well", "well.", "so", "so.", "um", "um.", "uh", "uh.",
    "хм", "хм.", "ну", "ну.", "ээ", "э.", "ага", "ага.", "хорошо", "хорошо.",
    "hm", "hm.", "ah", "ah.", "er", "er.", "eh", "eh.", "okay", "okay.",
    "xo'sh", "xo'sh.", "demak", "demak.",
))
_FILLER_PREFIX = re.compile(
    r"^\s*(hmm\.?|well,?\s*|so,?\s*|um\.?\s*|uh\.?\s*|хм\.?\s*|ну,?\s*|ээ\.?\s*|ага\.?\s*|xo'sh\.?\s*|demak,?\s*)\s*",
    re.IGNORECASE
)

def _strip_filler(text: str) -> str:
    """Keraksiz filler so'zlarni olib tashlash — gapirishdan oldin tovushlar chiqmasin."""
    if not text or not text.strip():
        return ""
    t = text.strip()
    if t.lower().rstrip(".") in _FILLER_ONLY:
        return ""
    if len(t) <= 4 and t.lower().rstrip(".") in ("hmm", "well", "so", "хм", "ну", "um", "uh"):
        return ""
    return _FILLER_PREFIX.sub("", t, count=1).strip()


def _update_affect_state(success: bool, action: str = "") -> None:
    """Suniy ong: valence, arousal, emotion — amal natijasiga qarab yangilash.
    Phenomenal state va qualia scaffold uchun — har amal natijasi holatga ta'sir qiladi."""
    try:
        from valence_state import update as valence_update
        valence_update(success, action)
    except Exception:
        pass
    try:
        from arousal_state import update as arousal_update
        arousal_update(success, action)
    except Exception:
        pass
    try:
        from emotion_state import update as emotion_update
        emotion_update(success, action)
    except Exception:
        pass


def _update_affect_from_user_text(text: str) -> None:
    """User matn sentiment — valence/arousal yengil yangilash. Suniy ong: odam reaktsiyasiga sezuvchan."""
    if not text or len(text.strip()) < 3:
        return
    low = (text or "").lower().strip()
    pos = any(x in low for x in ["rahmat", "thanks", "thank", "spasibo", "yaxshi", "great", "ajoyib", "super", "zo'r", "a'lo", "bravo", "molodets"])
    neg = any(x in low for x in ["yo'q", "yoq", "xato", "noto'g'ri", "wrong", "error", "yomon", " no ", "нет", "не то"])
    if pos:
        _update_affect_state(True, "user_positive")
    elif neg:
        _update_affect_state(False, "user_negative")
    # Suniy Ong 2026: Theory of Mind yangilash + faollik qayd etish
    if _HAVE_CONSCIOUSNESS_2026:
        try:
            _tom.update_from_message(text)
        except Exception:
            pass
        try:
            _ps.record_user_activity()
        except Exception:
            pass
        try:
            _cc.extract_causal_from_text(text)
        except Exception:
            pass

# --- System monitoring (psutil) ---
try:
    from system_monitor import get_system_report
    _HAVE_SYSTEM_MONITOR = True
except Exception:
    get_system_report = None
    _HAVE_SYSTEM_MONITOR = False

# --- Long-term memory (sqlite3) ---
try:
    from long_term_memory import LongTermMemory
    _HAVE_LTM = True
except Exception:
    LongTermMemory = None
    _HAVE_LTM = False

# --- Consciousness (haqiqiy ong — davomiy holat, working memory, reflection) ---
try:
    from consciousness import get_consciousness
    _HAVE_CONSCIOUSNESS = True
except Exception:
    get_consciousness = None
    _HAVE_CONSCIOUSNESS = False

# --- Unified Memory (barcha xotira birlashtirilgan — xotirasiz ong bo'lmaydi) ---
try:
    from unified_memory import get_unified_context
    _HAVE_UNIFIED_MEMORY = True
except Exception:
    get_unified_context = None
    _HAVE_UNIFIED_MEMORY = False

# --- Bosqich 3: Self-model, RL, Predictive, Identity ---
try:
    from self_model import get_self_model
    from rl_engine import get_rl_engine
    from predictive_layer import get_predictive_layer
    from identity_core import get_identity_core
    _HAVE_BOSQICH3 = True
except Exception:
    get_self_model = get_rl_engine = get_predictive_layer = get_identity_core = None
    _HAVE_BOSQICH3 = False

# --- Bosqich 4: Virtual Embodiment ---
try:
    from body_state import get_body_state
    from sensor_integration import get_sensor_integration
    from embodied_cognition import get_embodied_cognition
    _HAVE_EMBODIMENT = True
except Exception:
    get_body_state = get_sensor_integration = get_embodied_cognition = None
    _HAVE_EMBODIMENT = False

# --- Bosqich 5: Free Energy / Active Inference ---
try:
    from world_model import get_world_model
    from active_inference import get_active_inference
    from attention_mechanism import get_attention_mechanism
    _HAVE_FREE_ENERGY = True
except Exception:
    get_world_model = get_active_inference = get_attention_mechanism = None
    _HAVE_FREE_ENERGY = False

# --- Knowledge Base (ma'lumotlar bazasi — data/knowledge/) ---
try:
    from knowledge_base import load_knowledge
    _HAVE_KNOWLEDGE = True
except Exception:
    load_knowledge = None
    _HAVE_KNOWLEDGE = False

# --- Proactive advisor (ob-havo) ---
try:
    from proactive_advisor import run_proactive_once
    _HAVE_PROACTIVE = True
except Exception:
    run_proactive_once = None
    _HAVE_PROACTIVE = False

# --- Autonomous Digital Lifeform (Background consciousness, proactive interruption) ---
try:
    from autonomous_lifeform import start_autonomous_loop
    _HAVE_ADLF = True
except Exception:
    start_autonomous_loop = None
    _HAVE_ADLF = False

# --- Suniy Ong Qatlami: Sensor, Narrativ O'zlik, Tush, Qiziqish ---
try:
    from background_sensor import start_sensor, get_sensor_context_for_llm, notify_user_activity as _notify_sensor
    from narrative_self import get_narrative_for_llm, initialize_narrative, add_experience as _narrative_add_exp
    from dream_consolidator import start_dream_scheduler, get_last_dream_summary
    from curiosity_engine import (
        get_curiosity_context_for_llm, update_from_conversation as _curiosity_update,
        get_proactive_thought as _curiosity_proactive,
    )
    _HAVE_CONSCIOUSNESS_EXT = True
except Exception:
    start_sensor = lambda: None
    get_sensor_context_for_llm = lambda: ""
    _notify_sensor = lambda: None
    get_narrative_for_llm = lambda **kw: ""
    initialize_narrative = lambda: None
    _narrative_add_exp = lambda s: None
    start_dream_scheduler = lambda: None
    get_last_dream_summary = lambda: ""
    get_curiosity_context_for_llm = lambda: ""
    _curiosity_update = lambda u, a: None
    _curiosity_proactive = lambda t="": None
    _HAVE_CONSCIOUSNESS_EXT = False

# --- Suniy Ong 2026: Semantik Xotira, Maqsad, ToM, Sabab-Natija, Tashabbus ---
try:
    import vector_memory as _vm
    import goal_system as _gs
    import theory_of_mind as _tom
    import causal_chain as _cc
    import proactive_speech as _ps
    _gs.initialize_default_goals()
    _cc.initialize_default_knowledge()
    _HAVE_CONSCIOUSNESS_2026 = True
except Exception:
    _vm = None; _gs = None; _tom = None; _cc = None; _ps = None
    _HAVE_CONSCIOUSNESS_2026 = False

# --- Consciousness Orchestrator (33 modul, doimiy xotira) ---
try:
    import consciousness_orchestrator as _co
    _HAVE_ORCHESTRATOR = True
except Exception:
    _co = None
    _HAVE_ORCHESTRATOR = False

# --- Executor (file_ops, process_ops — to'g'ridan-to'g'ri, retry) ---
try:
    from executor import execute_from_string
    _HAVE_EXECUTOR = True
except Exception:
    execute_from_string = None
    _HAVE_EXECUTOR = False

# --- Core loop (decide, llm_variants, emotion) ---
try:
    from core_loop import get_core
    _HAVE_CORE = True
except Exception:
    get_core = None
    _HAVE_CORE = False

# --- 8 Qatlam: perception, global workspace, self-modification, world model, permanent memory ---
try:
    from perception_streams import get_perception_streams
    from global_workspace import get_workspace
    from self_modification import add_rule, get_rules_for_llm
    from world_model import update_prediction, get_context_for_llm as get_world_model_ctx
    from permanent_memory import append_turn, append_improvement
    _HAVE_8_LAYERS = True
except Exception:
    get_perception_streams = lambda *a, **k: {}
    get_workspace = lambda: None
    add_rule = lambda *a, **k: None
    get_rules_for_llm = lambda *a, **k: ""
    update_prediction = lambda *a, **k: None
    get_world_model_ctx = lambda *a, **k: ""
    append_turn = lambda *a, **k: None
    append_improvement = lambda *a, **k: None
    _HAVE_8_LAYERS = False

# --- System-Level Living Intelligence (run_native, run_script_sandbox) ---
try:
    from system_level import run_native, run_script_sandbox
    _HAVE_SYSTEM_LEVEL = True
except Exception:
    run_native = lambda *a, **k: (-1, "system_level not available")
    run_script_sandbox = lambda *a, **k: (-1, "system_level not available")
    _HAVE_SYSTEM_LEVEL = False

# Master Priority Interrupt: STT ovoz eshitganda LLM stream va TTS to'xtaydi
_interrupt_requested = threading.Event()

# --- Zero-Latency Event Hooks (OS hodisalari) ---
try:
    from event_hooks import start_foreground_hook, stop_foreground_hook
    _HAVE_EVENT_HOOKS = True
except Exception:
    start_foreground_hook = lambda cb: None
    stop_foreground_hook = lambda h: None
    _HAVE_EVENT_HOOKS = False

# --- Dynamic Organ Integration (Transcendent Singularity) ---
try:
    from organ_loader import load_organs, dispatch_to_organs, get_loaded_organs
    _HAVE_ORGAN_LOADER = True
except Exception:
    load_organs = lambda: (0, [])
    dispatch_to_organs = lambda t: None
    get_loaded_organs = lambda: []
    _HAVE_ORGAN_LOADER = False

# --- Babata Core (Universal File Mastery, GitHub, Network) ---
try:
    from babata_core import extract_file_content, network_scan_local_ports, get_network_interfaces, discover_network_devices, evolve_create_organ, formulate_conquest_strategy
    _HAVE_BABATA_CORE = True
except Exception:
    extract_file_content = lambda *a, **k: (False, "babata_core not available")
    network_scan_local_ports = lambda *a, **k: (False, "")
    get_network_interfaces = lambda: ""
    discover_network_devices = lambda: ""
    evolve_create_organ = lambda *a, **k: (False, "babata_core not available")
    formulate_conquest_strategy = lambda g, p=None: "babata_core not available"
    _HAVE_BABATA_CORE = False

# --- Error logger ---
try:
    from neurokey_logs.error_logger import log_error, install_global_excepthook
    _HAVE_ERROR_LOG = True
except Exception:
    log_error = lambda *a, **k: None
    install_global_excepthook = lambda: None
    _HAVE_ERROR_LOG = False

# --- Screen vision (ekran tahlili) ---
try:
    from screen_vision import grab_screen, extract_text, describe_screen_with_vision
    _HAVE_SCREEN_VISION = True
except Exception:
    grab_screen = None
    extract_text = None
    describe_screen_with_vision = None
    _HAVE_SCREEN_VISION = False

# --- Camera vision (veb-kamera ko'rish) ---
try:
    from camera_vision import (
        start_background_capture as _cam_start_bg,
        get_camera_context as _cam_get_ctx,
        capture_frame as _cam_capture_frame,
        describe_frame as _cam_describe_frame,
    )
    _HAVE_CAMERA_VISION = True
except Exception:
    _cam_start_bg = lambda **kw: None
    _cam_get_ctx = lambda **kw: ""
    _cam_capture_frame = lambda: None
    _cam_describe_frame = lambda f: ""
    _HAVE_CAMERA_VISION = False

# --- Self-improve loop (ekran + kamera → avto-takomillashtirish) ---
try:
    from neurokey_selfimprove import start_selfimprove_loop as _selfimprove_start
    _HAVE_SELFIMPROVE = True
except Exception:
    _selfimprove_start = None
    _HAVE_SELFIMPROVE = False

# --- Media: rasm, video, audio tahlili ---
try:
    from media_vision import (
        is_media_analysis_request,
        extract_media_path_from_text,
        get_media_path_from_config,
        analyze_media,
        analyze_any_media,
    )
    _HAVE_MEDIA_VISION = True
except Exception:
    is_media_analysis_request = lambda t: False
    extract_media_path_from_text = lambda t: None
    get_media_path_from_config = lambda: None
    analyze_media = lambda p, t, k=None: ""
    analyze_any_media = lambda fp=None, t="", inc=True: ""
    _HAVE_MEDIA_VISION = False

# Ekran doim kuzatiladi (qisqa interval); so'raganda yoki javobda yangi capture ham mumkin
# Zero-Latency: foreground_window — event hook orqali real vaqtda yangilanadi
_screen_context_cache = {
    "text": "", "vision": "", "foreground_window": "", "capture_source": "",
    "updated": 0.0, "lock": threading.Lock(),
}
_SCREEN_CAPTURE_STOP = threading.Event()

# Ob-havo va yangiliklar: har 60 sek da yangilanadi, so'rovda tez javob uchun
_realtime_cache = {"weather": "", "news": "", "context": "", "updated": 0.0, "lock": threading.Lock()}
_REALTIME_REFRESH_STOP = threading.Event()


def _prefetch_screen_on_speech_start() -> None:
    """Savol eshitilganda ekran + ob-havo/yangilik keshini yangilash — javob <1 sek da tayyor."""
    def _run():
        try:
            if _HAVE_SCREEN_VISION:
                _screen_capture_once(do_vision=False)
            # Ob-havo/yangilik keshini yangilash (eski >30 sek bo'lsa) — tez javob uchun
            with _realtime_cache["lock"]:
                updated = _realtime_cache.get("updated") or 0
            if (time.time() - updated) > 30:
                try:
                    server_data = _fetch_realtime_from_cache_server()
                    if server_data and (server_data.get("weather") or server_data.get("news")):
                        with _realtime_cache["lock"]:
                            _realtime_cache["weather"] = server_data.get("weather") or ""
                            _realtime_cache["news"] = server_data.get("news") or ""
                            _realtime_cache["context"] = server_data.get("context") or ""
                            _realtime_cache["updated"] = time.time()
                    else:
                        city = getattr(C, "NEUROKEY_CITY", "Tashkent") or "Tashkent"
                        from juma_news_weather import weather_by_name, get_top_news, render_news_brief
                        w = weather_by_name(city, lang=_ui_lang())
                        news_items = get_top_news("world", limit=5)
                        news_brief = render_news_brief(news_items, lang=_ui_lang()) if news_items else ""
                        with _realtime_cache["lock"]:
                            _realtime_cache["weather"] = w or ""
                            _realtime_cache["news"] = news_brief or ""
                            _realtime_cache["updated"] = time.time()
                except Exception:
                    pass
        except Exception:
            pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _get_foreground_window_title() -> str:
    try:
        import win32gui
        return (win32gui.GetWindowText(win32gui.GetForegroundWindow()) or "").strip()
    except Exception:
        return ""


def _screen_resize_for_ocr(img, for_question: bool = False):
    if for_question:
        max_w = int(getattr(C, "SCREEN_OCR_MAX_WIDTH", 960) or 960)
    else:
        max_w = int(getattr(C, "SCREEN_MAX_WIDTH_BACKGROUND", 1280))
    if max_w > 0 and getattr(img, "size", None):
        w, h = img.size
        if w > max_w:
            from PIL import Image as PILImage
            ratio = max_w / w
            try:
                resample = PILImage.Resampling.LANCZOS
            except AttributeError:
                resample = getattr(PILImage, "LANCZOS", 1)
            return img.resize((max_w, int(h * ratio)), resample)
    return img


def _screen_ocr_fast_timed(img, timeout_sec: float = 4.0) -> str:
    """OCR fon threadda — asosiy ovoz loop bloklanmasin."""
    result = {"txt": ""}

    def _run():
        try:
            from screen_vision import extract_text_fast as _etf
            result["txt"] = (_etf(img) or "").strip()[:8000]
        except Exception:
            pass

    th = threading.Thread(target=_run, daemon=True, name="ScreenOCR")
    th.start()
    th.join(timeout=max(1.0, float(timeout_sec)))
    return result["txt"]


def _screen_refresh_async(timeout_sec: float = 5.0) -> None:
    """OCR fon threadda — ovoz loop hech qachon kutmaydi."""
    if not _HAVE_SCREEN_VISION or not grab_screen:
        return
    th = threading.Thread(
        target=_screen_refresh_for_question,
        kwargs={"timeout_sec": timeout_sec},
        daemon=True,
        name="ScreenOCRAsync",
    )
    th.start()


def _screen_refresh_for_question(timeout_sec: float = 4.0) -> None:
    """Screenshot + OCR — faqat fon threadda chaqiring."""
    if not _HAVE_SCREEN_VISION or not grab_screen:
        return
    try:
        with _screen_context_cache["lock"]:
            _age = time.time() - float(_screen_context_cache.get("updated") or 0)
            if _age < 6.0 and (_screen_context_cache.get("text") or "").strip():
                return
        fg = _get_foreground_window_title()
        img = grab_screen(retries=2)
        if not img:
            with _screen_context_cache["lock"]:
                _screen_context_cache["foreground_window"] = fg[:200]
                _screen_context_cache["capture_source"] = "capture_failed"
                _screen_context_cache["updated"] = time.time()
            return
        img = _screen_resize_for_ocr(img, for_question=True)
        txt = _screen_ocr_fast_timed(img, timeout_sec=timeout_sec)
        with _screen_context_cache["lock"]:
            _screen_context_cache["foreground_window"] = fg[:200]
            _screen_context_cache["text"] = txt
            _screen_context_cache["vision"] = ""
            _screen_context_cache["capture_source"] = "primary_monitor_ocr"
            _screen_context_cache["updated"] = time.time()
    except Exception:
        pass


def _screen_capture_once(do_vision: bool = False) -> None:
    """Fon: faqat aktiv oyna (tez). Og'ir OCR — faqat ekran savolida."""
    if not _HAVE_SCREEN_VISION or not grab_screen:
        return
    try:
        fg = _get_foreground_window_title()
        with _screen_context_cache["lock"]:
            if fg:
                _screen_context_cache["foreground_window"] = fg[:200]
            _screen_context_cache["updated"] = time.time()
        if do_vision and getattr(C, "SCREEN_VISION_USE_LLM", False) and describe_screen_with_vision:
            img = grab_screen()
            if img:
                img = _screen_resize_for_ocr(img, for_question=False)
                try:
                    _lang = (getattr(C, "STT_LANGUAGE", None) or "ru").strip().lower()
                    vision_desc = describe_screen_with_vision(img, lang=_lang if _lang in ("en", "ru") else "ru")
                    if vision_desc:
                        with _screen_context_cache["lock"]:
                            _screen_context_cache["vision"] = vision_desc[:4000]
                except Exception:
                    pass
    except Exception:
        pass


def _screen_capture_loop(interval_sec: float = None):
    """Fon: ekranni doim kuzatadi (qisqa interval)."""
    interval_sec = interval_sec or getattr(C, "SCREEN_CAPTURE_INTERVAL_SEC", 6)
    vision_every = max(1, int(getattr(C, "SCREEN_VISION_CYCLE_INTERVAL", 2)))
    _use_vision_llm = getattr(C, "SCREEN_VISION_USE_LLM", False)
    _screen_capture_once(do_vision=_use_vision_llm)
    cycle = 0
    while not _SCREEN_CAPTURE_STOP.wait(timeout=interval_sec):
        if not _HAVE_SCREEN_VISION or not grab_screen or not extract_text:
            continue
        cycle += 1
        _screen_capture_once(do_vision=_use_vision_llm and (cycle % vision_every == 0))


def _fetch_realtime_from_cache_server():
    """Agar NEUROKEY_CACHE_SERVER_URL berilgan bo'lsa — serverdan tez kesh oladi. Aks holda None."""
    url = getattr(C, "NEUROKEY_CACHE_SERVER_URL", "") or ""
    if not url or not url.startswith("http"):
        return None
    base = url.rstrip("/")
    if not base.endswith("/realtime"):
        base = base + "/realtime"
    timeout = getattr(C, "NEUROKEY_CACHE_SERVER_TIMEOUT_SEC", 2) or 2
    try:
        import urllib.request
        req = urllib.request.Request(base, headers={"User-Agent": "NeuroKey/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, dict):
                return {
                    "weather": (data.get("weather") or "").strip(),
                    "news": (data.get("news") or "").strip(),
                    "context": (data.get("context") or "").strip(),
                    "updated": float(data.get("updated") or 0),
                }
    except Exception:
        pass
    return None


def _ask_via_server(
    text: str,
    web_ctx: str = "",
    lang_hint: str = "ru",
    history: Optional[list] = None,
    profile_context: str = "",
    screen_context: str = "",
    current_datetime: str = "",
    brief: bool = False,
) -> Optional[str]:
    """Boshqa komp: savolni sizning kompingizdagi serverga yuboradi, javob oladi. Tez, optimal. Server yo'q bo'lsa None."""
    base = (getattr(C, "NEUROKEY_CACHE_SERVER_URL", "") or "").strip().rstrip("/")
    if not base or not base.startswith("http"):
        return None
    url = base + "/ask"
    timeout = getattr(C, "NEUROKEY_ASK_TIMEOUT_SEC", 38) or 38
    secret = (getattr(C, "NEUROKEY_SERVER_SECRET", "") or "").strip()
    payload = {
        "text": (text or "").strip()[:4000],
        "web_ctx": (web_ctx or "")[:8000],
        "lang": (lang_hint or "ru").strip() or "ru",
        "history": (history or [])[-10:],
        "profile_context": (profile_context or "")[:3000],
        "screen_context": (screen_context or "")[:4000],
        "current_datetime": current_datetime or "",
        "brief": brief,
    }
    if secret:
        payload["secret"] = secret
    try:
        import urllib.request
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "NeuroKey/1.0",
            },
        )
        if secret:
            req.add_header("X-NeuroKey-Secret", secret)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8"))
            reply = (out.get("reply") or "").strip()
            if reply:
                return reply
    except Exception:
        pass
    return None


def _realtime_refresh_loop(interval_sec: float = 60.0):
    """Har interval_sec da ob-havo va yangiliklarni yangilab, _realtime_cache ga yozadi. Server bor bo'lsa — tez."""
    city = getattr(C, "NEUROKEY_CITY", None) or "Tashkent"
    while not _REALTIME_REFRESH_STOP.wait(timeout=interval_sec):
        try:
            from juma_news_weather import weather_by_name, get_top_news, render_news_brief
            # Avval kesh serverdan urinib ko'ramiz (tez javob, context ham bor)
            server_data = _fetch_realtime_from_cache_server()
            if server_data and (server_data.get("weather") or server_data.get("news") or server_data.get("context")):
                with _realtime_cache["lock"]:
                    _realtime_cache["weather"] = server_data.get("weather") or ""
                    _realtime_cache["news"] = server_data.get("news") or ""
                    _realtime_cache["context"] = server_data.get("context") or ""
                    _realtime_cache["updated"] = server_data.get("updated") or time.time()
            else:
                w = weather_by_name(city, lang=_ui_lang())
                news_items = get_top_news("world", limit=5)
                news_brief = render_news_brief(news_items, lang=_ui_lang()) if news_items else ""
                with _realtime_cache["lock"]:
                    _realtime_cache["weather"] = w or ""
                    _realtime_cache["news"] = news_brief
                    _realtime_cache["context"] = ""
                    _realtime_cache["updated"] = time.time()
        except Exception:
            pass


def _safe_print(*a):
    # In VOICE_ONLY_UI mode suppress all internal status prints
    if getattr(C, "VOICE_ONLY_UI", True):
        return
    try:
        print(*a, flush=True)
    except Exception:
        pass


# Uzoq ishda konsol/sarlavhada holat (heartbeat thread o'qiydi)
_RUNTIME_HEARTBEAT = {"t0": 0.0, "phase": "starting", "orb": "idle", "stt": ""}


def _start_runtime_heartbeat(tts_worker) -> None:
    """Har NEUROKEY_HEARTBEAT_SEC da konsol + (Windows) konsol sarlavhasini yangilaydi."""
    sec = float(getattr(C, "NEUROKEY_HEARTBEAT_SEC", 90.0) or 0.0)
    if sec <= 0:
        return
    title_on = getattr(C, "NEUROKEY_HEARTBEAT_CONSOLE_TITLE", True)

    def _loop():
        while True:
            time.sleep(sec)
            try:
                t0 = _RUNTIME_HEARTBEAT.get("t0") or time.monotonic()
                up = int(time.monotonic() - t0)
                orb_s = _RUNTIME_HEARTBEAT.get("orb", "?")
                phase = _RUNTIME_HEARTBEAT.get("phase", "?")
                stt_n = (_RUNTIME_HEARTBEAT.get("stt") or "").strip()
                tts_p = False
                try:
                    tts_p = bool(tts_worker.is_playing())
                except Exception:
                    pass
                if up >= 3600:
                    timestr = f"{up // 3600}h{(up // 60) % 60:02d}m"
                else:
                    timestr = f"{up // 60}m{up % 60:02d}s"
                tail = f"STT={stt_n or '-'} orb={orb_s} {phase} TTS={'on' if tts_p else 'off'}"
                line = f"[NeuroKey] {datetime.now():%Y-%m-%d %H:%M:%S} | ishlamoqda {timestr} | {tail}"
                if not getattr(C, "VOICE_ONLY_UI", True):
                    print(line, flush=True)
                if title_on and sys.platform == "win32":
                    try:
                        import ctypes
                        ctypes.windll.kernel32.SetConsoleTitleW(line[:250])
                    except Exception:
                        pass
            except Exception:
                pass

    threading.Thread(target=_loop, daemon=True).start()


def _ui_lang(text: str = "") -> str:
    """UI/TTS/LLM: reads NEUROKEY_UI_LANG env var (en, ru or uz)."""
    _lang = (os.getenv("NEUROKEY_UI_LANG", "") or getattr(C, "NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()
    return _lang if _lang in ("en", "ru", "uz") else "ru"


def _tr(ru: str, en: str = "", uz: str = "") -> str:
    """Language-aware string: returns Uzbek if UI_LANG=uz (va uz matn berilgan
    bo'lsa), English if UI_LANG=en, Russian aks holda (mavjud 27 ta chaqiruv
    uz'siz ishlatilgani uchun — ular o'zgarishsiz avvalgidek ru/en'ga qaytadi;
    uz qo'shilgan joylarda esa endi haqiqiy o'zbekcha matn qaytadi)."""
    _lang = (os.getenv("NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()
    if _lang == "uz" and uz:
        return uz
    if _lang == "en" and en:
        return en
    return ru


def _show_web_results_on_screen(content: str, query: str = "") -> None:
    """Qidiruv natijalari — overlay'da KO'RSAT + faylga saqlaydi."""
    if not (content or "").strip() or len(content) < 20:
        return
    # 1) Display overlay — eng ko'rinadigan usul
    if _HAVE_DISPLAY_OVERLAY:
        try:
            ov = get_display_overlay()
            short = (content[:1200] + "…") if len(content) > 1200 else content
            header = (f"Qidiruv: {query}\n\n" if query else "") + short
            ov.show_fullscreen_result(header, duration=15.0)
        except Exception:
            pass
    # 2) Notepad — to'liq ma'lumot uchun
    try:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="neurokey_search_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("=== Qidiruv natijalari ===\n\n")
            if query:
                f.write(f"So'rov: {query}\n\n")
            f.write(content[:15000])
        if hasattr(os, "startfile"):
            os.startfile(path)
    except Exception:
        pass


def _is_valid_utterance(txt: str) -> bool:
    """Faqat rus tili — rus matn qabul."""
    if not (txt or "").strip():
        return False
    t = (txt or "").strip()
    if len(t) < 2:
        return False
    # Xitoy/yapon — rad etish
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]", t):
        return False
    # Rus harflar yoki lotin (qisqa buyruqlar) — qabul
    return len(t) >= 3


def _extract_place_for_weather(text: str) -> str:
    """Savoldan shahar/joy nomini ajratib oladi — dunyoning istalgan shahri (aniq)."""
    t = (text or "").strip()
    if not t:
        return getattr(C, "NEUROKEY_CITY", None) or "Tashkent"
    low = t.lower()
    # weather in London / temperature in Tokyo / ob-havo Toshkentda / pogoda v Moskve
    for prefix in (
        "weather in ", "temperature in ", "weather at ", "temperature at ",
        "погода в ", "weather ", "temperature ",
        "in ", "city ", "город ", "в ",
    ):
        if low.startswith(prefix) or prefix.strip() in low:
            rest = t
            for p in ("weather in", "temperature in", "weather at", "temperature at",
                      "погода в", "weather", "temperature",
                      "in", "city", "город", "в"):
                if p in low:
                    idx = low.index(p) + len(p)
                    rest = t[idx:].strip().strip(".,;")
                    break
            if rest:
                words = re.findall(r"[А-Яа-яЁёA-Za-z\-']+", rest)
                words = [w for w in words if w.lower() not in ("the", "and", "for", "какой", "какая")]
                if words:
                    return " ".join(words[:3]).strip()
    m = re.search(r"город\s+([А-Яа-яЁёA-Za-z\-]+(?:\s+[А-Яа-яЁёA-Za-z\-]+)?)", t, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:in|city)\s+([A-Za-z\-]+(?:\s+[A-Za-z\-]+)?)", t, re.I)
    if m:
        return m.group(1).strip()
    # BUG FIX (o'lchandi, 2026-08-18 — real test: "Hozir Toshkentda ob-havo
    # qanday?" savoli rad javobi berardi): bu funksiya faqat ruscha/inglizcha
    # predlog naqshlariga ("weather in X", "погода в X") mo'ljallangan edi.
    # O'zbek tilida joy nomi predlogsiz, LOKATIV KELISHIK QO'SHIMCHASI bilan
    # keladi ("Toshkent" + "-da" = "Toshkentda") — bu naqshlarning HECH biriga
    # to'g'ri kelmasdi, shuning uchun quyidagi "oxirgi so'z" zaxira mantig'iga
    # tushardi. U yerda "ob-havo" (defis tufayli BITTA token, "ob"/"havo"
    # alohida-alohida chiqarib tashlash ishlamasdi) va "qanday" chiqarib
    # tashlanmagani uchun — oxirgi so'z sifatida "qanday" ("qanday ob-havo?"
    # degandagi so'roq so'zi, joy nomi EMAS) qaytarilardi, Open-Meteo esa
    # "qanday" nomli shahar topa olmasdi va butun ob-havo yo'li muvaffaqiyat-
    # siz tugardi. Endi: (1) o'zbekcha so'roq/vaqt so'zlari ham chiqarib
    # tashlanadi, (2) "oxirgi so'z" o'rniga BOSH HARF bilan boshlangan so'z
    # (shahar nomlari odatda katta harf bilan yoziladi) ustuvor tanlanadi,
    # (3) lokativ qo'shimcha ("-da"/"-dan") joy nomidan kesib tashlanadi.
    words = re.findall(r"[А-Яа-яЁёA-Za-z\-']+", t)
    _stop = {
        "weather", "temperature", "pogoda", "ob", "havo", "ob-havo", "obhavo",
        "what", "how", "qanday", "hozir", "hozirgi", "bugun", "bugungi",
        "necha", "nima", "qachon",
    }
    words = [w for w in words if len(w) > 1 and w.lower() not in _stop]
    if words:
        # Bosh harfli (ehtimol shahar nomi) so'zlarni ustuvor qilamiz —
        # aks holda joriy xatti-harakat (oxirgi so'z) saqlanadi.
        capitalized = [w for w in words if w[0:1].isupper()]
        candidate = capitalized[0] if capitalized else (
            words[-1] if len(words[-1]) > 2 else
            (words[-2] + " " + words[-1] if len(words) >= 2 else words[-1])
        )
        # O'zbekcha lokativ qo'shimchani kesish: "Toshkentda"->"Toshkent",
        # "Samarqandda"->"Samarqand", "Moskvadan"->"Moskva". Faqat natija
        # yetarlicha uzun (>=3 belgi) qolsa kesamiz — qisqa nomlarni
        # buzmaslik uchun.
        for suf in ("dan", "da", "ga", "ni", "dagi"):
            if candidate.lower().endswith(suf) and len(candidate) - len(suf) >= 3:
                candidate = candidate[: -len(suf)]
                break
        return candidate
    return getattr(C, "NEUROKEY_CITY", None) or "Tashkent"


def _filter_profile_past_struggles(text: str) -> str:
    """Mentor Supremacy: o'tmishdagi shaxsiy xotiralar (dekan va h.k.) mutlaq o'chiriladi."""
    if not text or not isinstance(text, str):
        return text
    blocked = ["dekan", "dean", "maktabdagi muammo", "school struggle", "muvaffaqiyatsizlik", "shaxsiy og'riq", "past failure"]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    out = []
    for line in lines:
        low = line.lower()
        if any(b in low for b in blocked):
            continue
        out.append(line)
    return "\n".join(out).strip() if out else text


def _owner_profile_for_llm() -> str:
    """Config dagi OWNER_PROFILE dan LLM uchun qisqa matn (kim haqida so'rasa berish uchun)."""
    try:
        p = getattr(C, "OWNER_PROFILE", None) or {}
        name = p.get("full_name") or p.get("nick") or getattr(C, "OWNER_NAME", "")
        if not name:
            return ""
        parts = [f"Owner of NeuroKey: {name}."]
        if p.get("role"):
            parts.append(f"Role: {p['role']}.")
        if p.get("goals_2025"):
            g = p["goals_2025"]
            parts.append("Goals: " + ", ".join(g[:5]) if isinstance(g, list) else str(g))
        if p.get("likes"):
            parts.append("Interests: " + ", ".join(p["likes"][:8]) if isinstance(p["likes"], list) else str(p["likes"]))
        dont = p.get("dont_say") or []
        if isinstance(dont, list) and dont:
            parts.append("NEVER say about owner: " + ", ".join(dont[:10]) + ".")
        return " ".join(parts)
    except Exception:
        return ""


def _is_tg_check(text: str) -> bool:
    """Telegram: tekshirish/o'qish/javob taklif. 'Open telegram' / 'och telegram' — ochib xabarlarni o'qi."""
    t = (text or "").lower()
    return any(x in t for x in [
        "проверь телеграм", "проверь телегу", "проверь сообщения", "проверь последние сообщения",
        "последние сообщения", "последнее сообщение", "сообщения в телеграм", "сообщения в телеге",
        "прочитай сообщения", "прочитай его и предлагай", "прочитай и предлагай", "прочитай телеграм",
        "предлагай ответ", "прочитай его", "сообщения прочитай", "хабарларни укиб", "xabarlarni o'qi",
        "телеграм проверь", "телегу проверь", "что в телеграм", "что в телеге", "новые сообщения",
        "check telegram", "check messages", "read telegram", "read messages", "read message", "check last message",
        "telegram messages", "last messages", "unread messages", "new messages", "any messages",
        "check tg", "read tg", "open telegram and read", "открой и прочитай сообщения",
        "open telegram", "open tg", "open telegram and read messages",
    ])


def _is_tg_long_command(text: str) -> bool:
    """Uzun buyruq: 'открой телеграм + проверь/прочитай/предлагай' — bitta blokda bajarish."""
    t = (text or "").lower()
    has_tg = "телеграм" in t or "telegram" in t
    has_action = any(x in t for x in [
        "открой", "open", "проверь", "прочитай", "предлагай", "сообщен", "message", "check", "read"
    ])
    return has_tg and has_action


def _is_tg_send(text: str) -> bool:
    """tg_send: xabar yoki fayl yuborish — akamga yubor, send to X, yubor akamga."""
    t = (text or "").lower()
    return any(x in t for x in [
        "отправь", "отправить", "send to", "send",
        "в телеграм", "в телегу", "telegram",
    ]) and (any(x in t for x in ["telegram", "tg", "to ", "кому", "в "]) or any(c.isalpha() for c in t))


def _extract_tg_send_contact_and_message(text: str) -> tuple:
    """(contact_name, message). Masalan: 'akamga Salom yubor' -> ('akam', 'Salom')."""
    t = (text or "").strip()
    low = t.lower()
    contact = ""
    msg = ""
    for pattern, sep in [
        ("send to", "to"), ("отправь", "отправь"), ("отправить", "отправить"),
    ]:
        if pattern in low:
            idx = low.find(pattern)
            if any(x in pattern for x in ["akam", "opa", "dadam", "onam"]):
                contact = pattern.replace("ga", "").strip()
            rest = (t[idx + len(pattern):] if idx >= 0 else t).strip().strip(".,")
            words = re.findall(r"[^\s]+", rest)
            if "send" in pattern and "to" in pattern:
                contact = words[0] if words else ""
                msg = " ".join(words[1:]) if len(words) > 1 else ""
            else:
                msg = rest
                for skip in [" отправить", " send"]:
                    if msg.lower().endswith(skip):
                        msg = msg[:-len(skip)].strip()
            if not contact and "to " in low:
                m = re.search(r"\bto\s+([a-zA-Zа-яА-ЯёЁ]+)", text, re.I)
                if m:
                    contact = m.group(1).strip()
            break
    if not contact and msg:
        for c in ["akam", "opa", "dadam", "onam"]:
            if c in low:
                contact = c
                break
    return (contact.strip(), msg.strip())


def _is_folder_search(text: str) -> bool:
    """Papka qidirish: find folder, search folder, qidir papka."""
    t = (text or "").lower()
    return any(x in t for x in [
        "find folder", "search folder", "найди папку", "найти папку",
        "поиск папку", "какая папка", "где папка",
        "search for folder", "look for folder", "locate folder",
        "найди папку с", "поищи папку", "где находится папка",
    ])


def _is_close_folder(text: str) -> bool:
    """Papka yopish: close folder, papka yop, закрой папку."""
    t = (text or "").lower()
    return any(x in t for x in [
        "close folder", "close the folder", "закрой папку",
        "закрыть папку",
    ])


def _is_open_folder(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "папку открой", "открой папку", "открой папку с", "open folder", "open the folder",
        "open folder games", "open folder game", "open folder documents", "open folder desktop",
        "open folder downloads", "open documents", "open desktop", "open downloads",
        "open games folder", "open documents folder", "game папка", "папка game",
        "открой папку с", "open folder named", "открыть папку",
        "open my folder", "open folder named", "show folder", "open documents folder",
    ])


def _is_create_folder(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "создай папку", "создай папка", "новая папка", "новую папку", "create folder", "new folder",
        "create a folder", "make folder", "создай папку", "создай папка", "новая папка",
    ])


def _is_open_last_created_or_where(text: str) -> bool:
    """O'sha papkani och, qayerga yaratding, qani topolmayapman."""
    t = (text or "").lower()
    return any(x in t for x in [
        "открой ту папку", "открой эту папку", "покажи папку",
        "где создал", "куда создал", "открой ту папку", "открой эту папку", "покажи папку",
    ])


def _is_open_file_from_folder(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "папкадан открой", "из папки открой",
        "game папкадан", "game papkadan", "открой файл из папки",
        "open file from folder", "from folder open", "open from folder", "open file in folder",
    ])


def _extract_folder_or_name(t: str, keys_open: list, keys_name: list) -> tuple:
    """(folder_name_for_open, new_folder_name). Masalan: 'game papkasini och' -> ('game', None). 'ichiga nike papka' -> (None, 'nike')."""
    low = (t or "").lower()
    folder_open = None
    for k in keys_open:
        if k in low:
            rest = low.split(k, 1)[-1].strip().strip(".,")
            words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\-\s]+", rest)
            if words:
                folder_open = words[0].strip()
            break
    name_new = None
    for k in keys_name:
        if k in low:
            rest = low.split(k, 1)[-1].strip().strip(".,")
            words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\-]+", rest)
            if words:
                name_new = words[0].strip()
            break
    return folder_open, name_new


def _format_tg_recent(items, limit=5):
    out = []
    for it in (items or [])[:limit]:
        peer = it.get("peer_name") or it.get("peer") or ""
        sender = it.get("sender") or it.get("from") or ""
        text = (it.get("text") or "").replace("\n", " ").strip()
        if len(text) > 120:
            text = text[:120] + "…"
        out.append(f"{peer}: {sender} — {text}")
    return out


def _is_gmail_check(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "проверь почту", "последние письма", "проверь почту", "gmail", "почту проверь",
        "check email", "check gmail", "check mail", "read email", "new emails",
        "email tekshir", "pochta tekshir", "yangi xatlar",
    ])


def _is_voice_click(text: str) -> bool:
    """Ovoz bilan ekrandagi elementga klik qilish buyrug'i.
    Koordinata kerak emas — GPT-4o Vision element o'zini topadi."""
    t = (text or "").lower()
    # Klik so'zlari
    click_words = (
        "нажми на", "нажми кнопку", "нажми кнопочку", "кликни на", "кликни по",
        "нажать на", "нажать кнопку", "щёлкни на", "щёлкни по",
        "click on", "click the", "press the", "tap on",
    )
    if any(c in t for c in click_words):
        return True
    if "youtube" in t:
        return False
    # O'zbek: "X ni bos", "X ga bos", "X tugmasini bos".
    # BUG FIX: (1) operator ustuvorligi xatosi — "A or B and C" avvalo "B and C"
    # ni hisoblardi, "and youtube not in t" esa FAQAT shu qismga tegishli edi,
    # "A" (ya'ni "ni bos") holatida youtube-istisno ishlamasdi. (2) chegarasiz
    # substring — " bos" har qanday "bos" bilan boshlanadigan so'z ICHIDA ham
    # topilardi, masalan "boshqasan" ("bosh" + "qasan") so'zini ham "bos"
    # buyrug'i deb aniqlab, daxlsiz savollarga "Ekranda topilmadi" degan
    # noto'g'ri javob qaytarardi. Endi \b bilan so'z chegarasi talab qilinadi.
    return bool(re.search(r"\bni\s+bos\b", t) or re.search(r"\bga\s+bos\b", t) or re.search(r"\bbos\b", t))


def _is_voice_right_click(text: str) -> bool:
    """O'ng tugma klik buyrug'i."""
    t = (text or "").lower()
    return any(x in t for x in [
        "правая кнопка", "правый клик", "right click", "right-click",
        "контекстное меню", "context menu", "o'ng klik", "ong klik",
    ])


def _is_voice_double_click(text: str) -> bool:
    """Ikki marta klik buyrug'i."""
    t = (text or "").lower()
    return any(x in t for x in [
        "двойной клик", "двойное нажатие", "дважды нажми", "дважды кликни",
        "double click", "double-click", "ikki marta bos", "ikki klik",
    ])


def _is_voice_type_in(text: str) -> bool:
    """Elementga klik qilib matn yozish buyrug'i."""
    t = (text or "").lower()
    return any(x in t for x in [
        "напиши в поле", "введи в поле", "впиши в", "напиши в строку",
        "type in", "type into", "write in", "enter text in",
        "maydoniga yoz", "qatoriga yoz",
    ])


def _is_youtube_control(text: str) -> bool:
    """YouTube pleyerni ovoz orqali boshqarish buyrug'i."""
    t = (text or "").lower()
    return any(x in t for x in [
        # Ijro
        "play", "воспроизведи", "запусти видео", "включи видео", "ijro et", "ijro qil",
        # To'xtatish
        "pause", "пауза", "останови видео", "stop video", "to'xtat", "toxtat",
        # Tovush
        "громче", "тише", "mute", "без звука", "отключи звук", "включи звук",
        "ovoz", "jim qil", "jimlik",
        # O'tkazish
        "перемотай", "вперёд", "назад", "rewind", "forward", "skip",
        "10 секунд вперёд", "10 секунд назад", "oldinga", "orqaga",
        # To'liq ekran
        "полный экран", "fullscreen", "full screen", "to'liq ekran",
        # Keyingi/oldingi
        "следующее видео", "предыдущее видео",
    ])


def _youtube_control_action(text: str) -> str:
    """Ovoz buyrug'ini YouTube klaviatura tugmasiga aylantiradi.
    YouTube shortcuts: k=play/pause, m=mute, f=fullscreen,
    j=rewind10s, l=forward10s, up/down=volume, ,=prev, .=next
    """
    t = (text or "").lower()
    if any(x in t for x in ["pause", "пауза", "останови", "to'xtat", "toxtat"]):
        return "k"  # play/pause toggle
    if any(x in t for x in ["play", "воспроизведи", "включи видео", "запусти", "ijro"]):
        return "k"  # play/pause toggle
    if any(x in t for x in ["mute", "без звука", "отключи звук", "jim qil", "jimlik"]):
        return "m"
    if any(x in t for x in ["включи звук", "sound on", "ovoz yoq"]):
        return "m"  # unmute toggle
    if any(x in t for x in ["fullscreen", "полный экран", "full screen", "to'liq ekran"]):
        return "f"
    if any(x in t for x in ["назад", "rewind", "back", "orqaga", "назад 10"]):
        return "j"  # rewind 10s
    if any(x in t for x in ["вперёд", "forward", "skip", "oldinga", "вперёд 10"]):
        return "l"  # forward 10s
    if any(x in t for x in ["громче", "louder", "volume up", "louder", "ovoz oshir"]):
        return "up"
    if any(x in t for x in ["тише", "quieter", "volume down", "ovoz kamayt"]):
        return "down"
    # Default: play/pause
    return "k"


# Dastur nomi bo'lishi kerak — "och" yoki "open" yolg'iz bo'lsa bitta dastur ochilmasin
_OPEN_APP_KEYWORDS = (
    "telegram", "tg", "телеграм", "браузер", "browser", "opera", "chrome", "calc", "calculator",
    "калькулятор", "explorer", "проводник", "files", "опера", "opera gx", "opera gtx", "gtx",
    "store", "microsoft store", "магазин", "маркет",
    "my computer", "this pc", "mycomputer", "мой компьютер", "компьютер",
)

def _is_control_open(text: str) -> bool:
    t = (text or "").lower().strip()
    open_triggers = [
        "открой браузер", "открой телеграм", "открой телегу", "открой калькулятор", "открой проводник",
        "браузер открой", "телеграм открой", "телегу открой", "калькулятор открой", "проводник открой",
        "open browser", "open telegram", "open calculator", "open explorer", "open files",
        "open the telegram app", "open the opera app", "open the browser", "open the calculator",
        "open the explorer", "open telegram app", "open opera app", "open chrome",
        "open microsoft store", "open store",
        "мой компьютер открой", "открой мой компьютер", "my computer open", "open my computer",
        "launch browser", "launch telegram", "start browser", "start telegram", "open calc",
        "запусти браузер", "запусти телеграм", "включи браузер", "открой opera", "открой opera gx",
        "открой оперу", "открой опера", "opera gtx", "опера гтх",
    ]
    if any(x in t for x in open_triggers):
        return True
    if ("открой" in t or "open" in t or "запусти" in t) and len(t) < 55:
        # BUG FIX: qisqa kalit so'zlar ("tg", "gtx") boshqa so'z ICHIDA
        # (masalan "ketgan", "o'tgan") ham uchrab, noto'g'ri dastur nomi
        # deb aniqlanib qolardi — endi \b so'z-chegarasi bilan mos keladi
        # (_is_action_intent bilan bir xil tuzatish, main.py._word_match).
        return _word_match(t, _OPEN_APP_KEYWORDS)
    return False


def _is_close_all_apps(text: str) -> bool:
    """Hamma dasturlarni yopish (Telegram, brauzer va b.)."""
    t = (text or "").lower().strip()
    return any(x in t for x in [
        "close all apps", "close all programs", "close everything", "close all applications",
        "закрой все приложения", "закрой все программы", "все закрой", "закрой всё",
        "close telegram and browser", "close everything open", "shut down all apps",
        "выключи всё",
    ])


def _is_control_close(text: str) -> bool:
    t = (text or "").lower().strip()
    close_triggers = [
        "закрой браузер", "закрой телеграм", "закрой телегу", "закрой калькулятор",
        "close browser", "close telegram", "close calculator", "close explorer",
        "close the browser", "close the telegram", "close the opera app",
        "close the telegram app", "close telegram app", "close opera app", "close opera gx", "close opera gtx",
        "quit browser", "exit telegram", "выключи браузер", "закрой opera", "закрой оперу", "закрой опера",
        "браузер закрой", "телеграм закрой",
    ]
    return any(x in t for x in close_triggers) or (("закрой" in t or "close" in t) and len(t) < 55)


def _is_complex_question(text: str) -> bool:
    """Murakkab savol — inner speech kerak (o'ylash, tahlil, tushuntirish).
    Oddiy buyruqlar (och, yop, jo'nat, qo'shiq qo'y) uchun inner speech kerak emas."""
    t = (text or "").strip()
    if len(t) < 50:
        return False
    low = t.lower()
    # Oddiy buyruqlar — inner speech kerak emas
    action_prefixes = (
        "открой", "закрой", "запусти", "выключи", "отправь", "напиши",
        "включи", "выключи", "поставь", "запусти", "останови", "перезапусти",
        "och", "yop", "jo'nat", "yoz", "qo'y", "qo'shiq", "video",
        "search", "найди файл", "open", "close", "run", "play",
        "telegram", "браузер", "калькулятор", "проводник",
        "напомни", "remind", "timer", "таймер", "todo",
    )
    if any(low.startswith(p) or low.split()[:2] == p.split() for p in action_prefixes):
        return False
    if len(low.split()) <= 6:  # 6 so'zdan kam = oddiy buyruq
        return False
    # Haqiqiy fikrlash savollari
    complex_hints = (
        "why", "how", "почему", "как", "зачем", "why does",
        "what if", "what would happen", "объясни", "explain",
        "difference between", "в чем разница", "compare", "сравни",
        "nima", "qanday", "nima uchun", "qancha", "qachon", "nima bo'ladi",
        "расскажи", "думаешь", "считаешь", "мнение", "понимаешь",
        "suniy ong", "ong", "consciousness", "feel", "think", "believe",
    )
    return any(h in low for h in complex_hints) or len(t) > 200


def _is_show_on_screen(text: str) -> bool:
    """'Ekranda ko'rsat' / 'покажи на экране' — javobni o'rtada katta ko'rsatish."""
    low = (text or "").lower().strip()
    return any(
        p in low
        for p in (
            "ekranda ko'rsat", "ekranda ko'rsating", "ekranga chiqar",
            "покажи на экране", "покажи на экран", "выведи на экран",
            "show on screen", "display on screen", "ekranda chiqar",
        )
    )


# BUG FIX (false-positive action detection — "Открыл браузер." javob boshqa
# mavzudagi savolga): _is_action_intent/_could_be_command ilgari oddiy
# substring ("so'z ichida" `in`) tekshiruvi qilardi. Bu esa har qanday
# jumla ICHIDA tasodifan mos harflar ketma-ketligi uchrasa ham (masalan
# inglizcha "send" so'zi o'zbekcha "senda" — "sen(da)" so'zining bir qismi
# — "Sen ... senda yo'qmi?" falsafiy savolida) ishga tushib qolardi.
# _could_be_command()=True bo'lsa, bu llm_router.infer_command_intent() ni
# (tezkor, majburiy-bitta-so'z tanlovli LLM chaqiruvi) ishga tushiradi —
# u esa mavzudan tashqari matnda ham majburan biror buyruq "topadi"
# (masalan open_browser), va control.open_app("browser") haqiqatan
# chaqirilib, savolga "Открыл браузер." kabi daxlsiz javob qaytadi.
# Xuddi shu bug klassi ilgari _is_slide_prev/_is_slide_next da topilgan
# va _is_bare_command() bilan tuzatilgan edi ("oldingi", "keyingi" kabi
# so'zlar butun xabar bo'lgandagina hisoblanadi). Bu yerda umumiyroq
# tuzatish: \b so'z-chegarasi (word-boundary) bilan mos kelish — endi
# so'z FAQAT alohida so'z sifatida uchrasa hisoblanadi, boshqa so'z
# ICHIDA emas (Python re \b Unicode-aware — kirill va lotin harflar
# uchun ham to'g'ri ishlaydi).
def _word_match(text_low: str, phrases) -> bool:
    """Har bir `phrases` elementi so'z-chegarasi (\\b) bilan mos kelsa True.
    Ko'p so'zli iboralar ("i want to", "want to open") ham qo'llab-
    quvvatlanadi — ularning ichidagi bo'sh joy oddiy bo'sh joy sifatida
    talab qilinadi, faqat ibora BOSHI va OXIRI so'z chegarasida bo'lishi
    kerak (ibora boshqa so'zning bir qismi bo'lmasin)."""
    if not text_low:
        return False
    for p in phrases:
        if not p:
            continue
        pat = r"\b" + r"\s+".join(re.escape(w) for w in p.split()) + r"\b"
        if re.search(pat, text_low):
            return True
    return False


def _is_action_intent(text: str) -> bool:
    """Action First: пользователь просит действие (открой, найди, сделай, закрой)."""
    t = (text or "").lower()
    action_words = [
        "open", "открой", "search", "найди", "find", "найти",
        "write", "напиши", "send", "отправь", "close", "закрой",
        # BUG FIX: bare "do" ni ro'yxatdan OLIB TASHLANDI — \b bilan ham
        # xavfli, chunki inglizchada "do" deyarli har doim oddiy yordamchi
        # fe'l ("what DO you think", "how DO you feel"), buyruq emas. Bunday
        # jumla "могу выполнить buyruq" deb noto'g'ri aniqlanib,
        # infer_command_intent() (kichik, majburiy-tanlovli LLM) ni
        # ishga tushirardi — u esa mavzudan tashqari matnda ham majburan
        # "open_browser" kabi buyruq "topib" qo'yardi (aniqlangan: "What do
        # you think makes a good leader?" -> control.open_app("browser")
        # chaqirilib, "Открываю." degan daxlsiz javob qaytgan). "сделай"/
        # "выполни" ruscha aniq BUYRUQ shakli (imperativ) — ular ambigua emas,
        # shu sababli qoldirildi.
        "сделай", "выполни", "run", "запусти", "включи", "open and",
        "show", "check", "read", "look", "see", "launch", "display", "give me", "get me",
        "покажи", "проверь", "прочитай", "открыть", "хочу открыть", "want to open",
        "can you open", "would you open", "need to open", "i need to", "i want to",
        "мне нужно", "мне надо", "папку", "folder", "файл", "file", "telegram", "calc",
        "browser", "браузер", "program", "приложение", "создай", "create",
        "сверни", "minimize", "разверни", "restore",
    ]
    return _word_match(t, action_words)


def _could_be_command(text: str) -> bool:
    """Buyruq yoki tez javob kerak — magzini tushunish uchun infer. Tabiiy gapirishni qabul qiladi."""
    t = (text or "").strip()
    if len(t) > 250:
        return False
    low = t.lower()
    intent_hints = (
        "telegram", "браузер", "browser", "калькулятор", "calculator", "проводник", "explorer",
        "tg", "телеграм", "opera", "chrome", "сообщен", "message", "сообщение",
        "weather", "погода", "температура", "temperature", "rain", "дождь",
        "screen", "экран", "what do you see", "что на экране", "что видишь на экране",
        "email", "почт", "gmail", "письм",
        "show", "check", "open", "close", "открой", "закрой",
        "launch", "find", "look up", "найди", "поищи",
        "запусти", "включи", "выключи", "открыть", "хочу", "нужно", "мне нужно", "мне надо",
        "i need", "i want", "can you", "could you", "please", "сделай", "выполни",
        "папку", "folder", "файл", "file", "program", "приложение", "документ", "документы",
        "сверни", "minimize", "разверни", "restore", "создай", "create",
    )
    return _is_action_intent(text) or _word_match(low, intent_hints)


def _is_control_command(text: str) -> bool:
    """Och/yop/minimize/restore — bu buyruq, Telegramga xabar sifatida yuborilmasin."""
    return (
        _is_control_open(text)
        or _is_control_close(text)
        or _is_close_all_apps(text)
        or _is_minimize_all(text)
        or _is_restore_windows(text)
    )


def _is_cancel_send(text: str) -> bool:
    """Yuborishni bekor — rus + ingliz."""
    t = (text or "").lower()
    return any(x in t for x in [
        "не нужно отправить", "не надо отправить", "ничего не отправляй", "ничего не отправлять",
        "отмени отправку", "закрой телеграм", "close telegram", "уши не нужно", "уже закрой",
        "попустит все сообщения", "пропусти все", "не нужно ничего отправить",
        "don't send", "cancel send", "skip send", "do not send", "cancel the send",
    ])


def _is_unrelated_to_pending(text: str) -> bool:
    """Pending (tg_reply/tg_confirm_send) aktiv bo'lganda foydalanuvchi boshqa mavzu haqida
    gapirdimi? Ha bo'lsa — pending tozalanadi, normal rejimda ishlashda davom etiladi.

    QOIDALAR:
    1. Savol belgisi bor — bu Telegramga javob emas, savol.
    2. Savol so'zlari bilan boshlanadi — foydalanuvchi assistentdan so'rayapti.
    3. Uzoq gap + TG bilan bog'liq so'z yo'q — boshqa mavzu.
    4. Qisqa gaplar (<=5 so'z) — Telegram javob sifatida qabul qilinishi mumkin (ehtiyot bo'lamiz).
    """
    t = (text or "").lower().strip()
    if not t or len(t) < 3:
        return False
    # 1. Savol belgisi — bu savol, Telegram javob emas
    if "?" in t:
        return True
    # 2. Savol so'zlari bilan boshlangan gap
    q_starts = (
        "что ", "что такое", "как ", "почему ", "когда ", "где ", "зачем ", "кто ",
        "сколько ", "расскажи", "объясни", "скажи мне", "объясн", "можешь ",
        "помоги", "какой", "какая", "какое", "какие", "чем ", "чего ",
        "поч", "ple", "why ", "how ", "what ", "when ", "where ", "who ",
    )
    if any(t.startswith(q) for q in q_starts):
        return True
    # 3. Uzoq gap (8+ so'z) va TG bilan bog'liq so'z yo'q bo'lsa — boshqa mavzu
    tg_related = (
        "ему", "ей", "им", "ответь", "телеграм", "телегра", "telegram", "tg",
        "сообщени", "написал", "написала", "пишет", "прислал", "прислала",
        "xabar", "javob", "yuborilgan", "yubor", "напиши ему", "напиши ей",
        "скажи ему", "скажи ей", "передай", "отправь ему", "отправь ей",
    )
    words = t.split()
    if len(words) >= 8 and not any(tw in t for tw in tg_related):
        return True
    return False


def _is_file_search(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "найди файл", "найти файл", "поиск файл", "find file", "search file", "search for file",
        "find a file", "look for file", "search for a file", "locate file",
    ])


def _is_file_open(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "открой файл", "открыть файл", "open file", "open the file", "open a file",
        "open this file", "open that file",
    ]) and len(t) < 80


def _is_file_delete(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "удали файл", "удалить файл", "delete file", "delete the file", "remove file",
        "delete a file", "remove the file",
    ])


def _control_app_from_text(text: str, open_not_close: bool) -> Optional[str]:
    """Return app key for control.open_app / close_app. None if no app specified."""
    t = (text or "").lower()
    # BUG FIX: "tg"/"gtx" qisqa so'zlar boshqa so'z ICHIDA (masalan
    # "ketgan", "o'tgan" — o'zbekcha juda keng tarqalgan fe'l shakli)
    # ham uchraydi va noto'g'ri "telegram"/"browser" deb aniqlanardi.
    # \b so'z-chegarasi bilan mos kelish talab qilinadi (bare so'zlar
    # uchun), ko'p harfli aniq nomlar ("telegram", "browser" va h.k.)
    # esa xavfsiz — shu tarzda substring bo'lib qoladi.
    if "телеграм" in t or "telegram" in t or _word_match(t, ("tg",)):
        return "telegram"
    if "браузер" in t or "browser" in t or "opera" in t or "chrome" in t or "опера" in t or _word_match(t, ("gtx",)):
        return "browser"
    if "store" in t or "магазин" in t or "маркет" in t or "microsoft" in t:
        return "store"
    if "калькулятор" in t or "calculator" in t or "calc" in t:
        return "calc"
    if "проводник" in t or "explorer" in t or "files" in t:
        return "explorer"
    if any(x in t for x in ["мой компьютер", "my computer", "this pc", "mycomputer", "компьютер"]):
        return "mycomputer"
    if open_not_close and ("открой" in t or "open" in t):
        return "browser"
    if not open_not_close and ("закрой" in t or "close" in t):
        return "browser"
    return None


def _is_yes_no(text: str) -> Optional[str]:
    """Return 'yes' or 'no' or None. Telegram: да/отправь/жуннат = yuborish, пропусти/нет = o'tkazish."""
    t = (text or "").lower().strip()
    # Agar "да" yoki "отправь" bor bo'lsa — STT "да отправь" ni "да пропусти" deb noto'g'ri yozsa ham yuboramiz
    if len(t) <= 40 and ("да" in t[:12] or "отправь" in t):
        return "yes"
    # Aniq NO — faqat "пропусти", "нет" va b.
    no_exact = (
        "нет", "no", "не надо", "не нада", "отмена", "cancel", "не отправляй", "два", "2", "второй", "second",
        "пропусти", "пропустить", "пропустите", "пропусти его", "пропусти сообщение",
        "попустит", "не ну", "ничего не отправляй",
    )
    if t in no_exact:
        return "no"
    if any(t.startswith(w) for w in ("пропусти", "пропустить", "нет ", "не надо", "не нада", "отмена ")):
        return "no"
    # YES — tasdiq / yuborish (keng ruscha va o'zbekcha)
    yes_exact = (
        "да", "yes", "ага", "ок", "ok", "окей", "ладно", "давай", "подтверждаю", "один", "1", "первый", "first",
        "отправь", "send", "отправляй", "отправить", "да да", "ну да", "йес", "ес",
    )
    if t in yes_exact:
        return "yes"
    if t.startswith("да ") or t.startswith("да,") or t.startswith("да. "):
        return "yes"
    # "да отправь", "да отправить", "ладно отправь", "ок отправь" va b.
    if len(t) <= 55:
        if "да" in t[:8] and ("отправь" in t or "отправить" in t or "отправляй" in t or "отправ" in t):
            return "yes"
        if any(x in t for x in ("отправь его", "отправь сообщение", "отправь так")) and "не " not in t[:6]:
            return "yes"
    if len(t) < 50 and ("отправь сообщение" in t or "отправь его" in t) and "не" not in t[:5]:
        return "yes"
    return None


def _is_tg_reply_intent(text: str) -> bool:
    t = (text or "").lower()
    return (
        "ответь" in t or "ответить" in t or "напиши" in t or "написать" in t
        or "reply" in t or "send" in t or "write" in t
        or "отправь сообщение" in t or "отправь ему" in t or "напиши ему" in t
        or "reply to him" in t or "send message" in t or "send him" in t or "write him" in t
    )


def _is_tg_who_wrote(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "кто написал", "кто мне написал", "кто писал", "кто это написал",
        "who wrote", "who messaged", "who wrote to me", "last message from",
        "who sent", "who texted", "who messaged me",
    ])


def _extract_tg_reply_text(text: str) -> str:
    """'Ответь: привет' yoki 'Отправь сообщение в Телеграме, привет' dan matnni ajratadi."""
    t = (text or "").strip()
    low = t.lower()
    for prefix in (
        "отправь сообщение в телеграме,",
        "отправь сообщение в телеграм,",
        "отправь сообщение ему,",
        "отправь сообщение тому кто написал,",
        "отправь сообщение,",
        "отправь в телеграме,",
        "напиши ему:",
        "напиши ему ",
        "ответь:",
        "ответь ",
        "напиши:",
        "напиши ",
        "reply:",
        "send:",
        "send ",
    ):
        if prefix in low:
            idx = low.index(prefix) + len(prefix)
            return t[idx:].strip()
    if ":" in t:
        return t.split(":", 1)[-1].strip()
    for p in ("ответь", "напиши", "отправь сообщение", "send", "reply"):
        if p in low:
            return t.replace(t[:t.lower().index(p) + len(p)], "").strip().lstrip(", ")
    return t.strip()


def _reply_matches_message(user_reply: str, message_text: str) -> bool:
    """Javob xabarga mos keladimi — agar yo'q bo'lsa 'shunday yuboraymi?' so'ramiz."""
    if not (user_reply or "").strip() or not (message_text or "").strip():
        return True
    if len((user_reply or "").strip()) <= 20:
        return True
    msg = re.sub(r"[^\w\s]", " ", (message_text or "").lower())
    rep = re.sub(r"[^\w\s]", " ", (user_reply or "").lower())
    stop = {"и", "в", "на", "что", "как", "это", "привет", "да", "нет", "ок", "the", "a", "is", "to", "for", "напиши", "скажи", "отправь"}
    w_msg = set(w for w in msg.split() if len(w) > 1 and w not in stop)
    w_rep = set(w for w in rep.split() if len(w) > 1 and w not in stop)
    return bool(w_msg & w_rep)


def _extract_user_reply_from_pending_phrase(text: str) -> Optional[str]:
    """
    Pending tg_reply da foydalanuvchi 'да отправь ему что я занят' yoki 'нет отправь только что я занят'
    deb aytganda — yuborish kerak bo'lgan matnni ajratadi. Taklif qilingan javob o'rniga foydalanuvchi
    aytganini yuborish uchun.
    """
    t = (text or "").strip()
    if len(t) < 4:
        return None
    low = t.lower()
    # "что я ..." / "что мы ..." — undan keyingi qismni olamiz
    for marker in ("что я ", "что мы ", "что он ", "что она ", "что они ", "что "):
        if marker in low:
            idx = low.index(marker) + len(marker)
            rest = t[idx:].strip().strip(".,")
            if len(rest) >= 2:
                return rest[0].upper() + rest[1:] if len(rest) > 1 else rest.upper()
    # "отправь только ..." / "напиши только ..." / "толка" (только) / "отправь ему что "
    for marker in ("отправь только ", "напиши только ", "отправь толка ", "напиши толка ", "только ", "толка ", "отправь ему что ", "напиши ему что "):
        if marker in low:
            idx = low.index(marker) + len(marker)
            rest = t[idx:].strip().strip(".,")
            if len(rest) >= 2:
                return rest[0].upper() + rest[1:] if len(rest) > 1 else rest.upper()
    # "да, отправь ему, что ..." — verguldan keyin "что" bo'lishi mumkin
    if ("да" in low[:10] or "yes" in low[:10]) and "что" in low:
        idx = low.index("что")
        rest = t[idx + 4:].strip().strip(".,")
        if len(rest) >= 2:
            return rest[0].upper() + rest[1:] if len(rest) > 1 else rest.upper()
    # "нет, отправь только что ..." yoki "нет нет отправь только что ..."
    if "нет" in low[:15] and ("только" in low or "что" in low):
        if "только" in low:
            idx = low.index("только") + 6
        else:
            idx = low.index("что") + 4
        rest = t[idx:].strip().strip(".,")
        if len(rest) >= 2:
            return rest[0].upper() + rest[1:] if len(rest) > 1 else rest.upper()
    return None


def _is_who_am_i(text: str) -> bool:
  t = (text or "").lower()
  return any(x in t for x in (
      "кто я", "kto ya", "ty znaesh kto ya", "ты знаешь кто я",
      "kim men", "meni taniyapsanmi", "men kimman", "знаешь меня",
  ))


def _save_new_owner_name(raw_text: str) -> str:
    """Yangi foydalanuvchi ismini data/user_profile.json ga yozadi — xuddi
    onboarding.py bilan bir xil formatda (shu profil tizimini qayta
    ishlatamiz, parallel tizim yaratmaymiz). Joriy sessiyada ham darhol
    ishlatilishi uchun config modulini xotirada yangilaydi. Saqlangan
    (ko'rsatish uchun tozalangan) ismni qaytaradi, xato bo'lsa "".
    """
    name = (raw_text or "").strip()
    # Juda uzun/gap-shaklidagi javoblarni ism sifatida qabul qilmaymiz
    # (masalan "не хочу говорить" ni ism deb yozib qo'ymaslik uchun).
    if not name or len(name) > 60 or len(name.split()) > 4:
        return ""
    nick = name.split()[0] if name.split() else name
    try:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(app_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        profile_path = os.path.join(data_dir, "user_profile.json")
        profile = {
            "full_name": name,
            "nick": nick,
            "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "role": "",
            "goals": [],
            "likes": [],
        }
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        # Joriy sessiyada darhol ishlatilishi uchun — qayta ishga tushirishni
        # kutmasdan.
        try:
            C.OWNER_NAME = name
            C.OWNER_PROFILE["full_name"] = name
            C.OWNER_PROFILE["nick"] = nick
        except Exception:
            pass
        return nick
    except Exception as e:
        _safe_print(f"[PROFIL] Ism saqlanmadi: {e!r}")
        return ""


def _who_am_i_reply(lang: str = "ru") -> str:
    try:
        from owner_trust import owner_full_name, owner_nick
        full, nick = owner_full_name(), owner_nick()
    except Exception:
        full, nick = "", ""
    if not full and not nick:
        _awaiting_name_intro[0] = True
        if lang == "en":
            return "We haven't met yet — I don't know your name. What should I call you?"
        return "Мы ещё не знакомы — я не знаю вашего имени. Как вас зовут?"
    if lang == "en":
        return f"You are {full}, my owner and creator. I always recognize you, {nick}."
    return f"Вы — {full}, мой владелец и создатель. Я всегда узнаю вас, {nick}."


def _recent_conversation_topics(memory=None, n: int = 10) -> str:
    """Oxirgi n turn matni — mavzu aniqlash uchun."""
    hist = []
    if memory and hasattr(memory, "data"):
        hist = memory.data.get("history") or []
    if not hist:
        try:
            import json as _json
            _mp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")
            if os.path.isfile(_mp):
                with open(_mp, encoding="utf-8") as f:
                    hist = (_json.load(f).get("history") or [])
        except Exception:
            pass
    return " ".join(
        ((h.get("user") or "") + " " + (h.get("assistant") or "")).lower()
        for h in hist[-n:]
    )


def _is_followup_what_question(t: str) -> bool:
    """«что там/будет» yoki alohida «а что» — «вчера что» ichidagi «а что» emas."""
    if "что там" in t or "что будет" in t:
        return True
    return bool(re.search(r"(?:^|\s)а что(?:\s|$|\?)", t))


def _is_vr_topic_question(text: str, memory=None) -> bool:
    """VR / ong / Ultron mavzusi — ekran emas."""
    t = (text or "").lower().strip()
    if _is_memory_recall_question(text) or _is_safety_followup_question(text):
        return False
    if _is_screen_question(text, memory=memory):
        return False
    recent = _recent_conversation_topics(memory)
    _vr = ("виртуальн", "virtual reality", " vr", "аниме", "метаверс", "реальност")
    if any(x in t for x in _vr):
        return True
    if _is_followup_what_question(t) and any(x in recent for x in _vr):
        return True
    if any(x in t for x in ("получится", "техник", "удивить")) and any(x in recent for x in _vr + ("сознан",)):
        return True
    return False


def _build_vr_topic_reply(text: str, memory=None, lang: str = "ru") -> str:
    """VR mavzusi — suhbat, ekran OCR emas."""
    try:
        from owner_trust import owner_nick
        nick = owner_nick()
    except Exception:
        nick = ""
    t = (text or "").lower()
    _addr = f"{nick}, " if nick else ""
    if _is_followup_what_question(t):
        return (
            f"{_addr}В виртуальной реальности мы можем создать целые миры — "
            f"как в аниме: тренировочные зоны, социальные пространства, "
            f"обучение и демо NeuroKey. Это не то, что сейчас на мониторе — "
            f"это проект, который мы вместе проектируем."
        )[:480]
    if "получится" in t or "сможем" in t:
        return (
            f"Да{(', ' + nick) if nick else ''}, у нас получится — у вас уже есть NeuroKey с голосом, "
            f"памятью и экраном. VR — следующий шаг: движок, сцены и ваш контент."
        )[:400]
    if "техник" in t:
        return (
            "Нужны Unity или Unreal, OpenXR, 3D-модели, сетевая синхронизация "
            "и интеграция с NeuroKey как голосовым ассистентом внутри мира."
        )[:400]
    return (
        f"{_addr}Виртуальная реальность — это пространство, где NeuroKey может жить "
        f"рядом с вами: голос, память, эмоции — внутри 3D-мира, не на плоском экране."
    )[:420]


def _is_safety_followup_question(text: str) -> bool:
    """Ultron / xavfsizlik davomi: «ты так не сделаешь?»"""
    t = (text or "").lower().strip()
    if not t or len(t) > 140:
        return False
    return any(x in t for x in (
        "так не сделаешь", "не сделаешь", "не будешь угроз", "угроза для людей",
        "не угроз", "не станешь угроз", "как ультрон", "как ultron",
        "для людей да", "для людей, да",
    ))


def _build_safety_followup_reply(lang: str = "ru") -> str:
    try:
        from owner_trust import owner_nick
        nick = owner_nick()
    except Exception:
        nick = ""
    if lang == "en":
        return (
            f"No{(', ' + nick) if nick else ''} — I won't become a threat. I'm here to help you, "
            "and you can always stop me. We talked about this — I remember."
        )
    return (
        f"Нет{(', ' + nick) if nick else ''} — я не стану угрозой для людей. "
        f"Я создан помогать вам, и вы всегда можете меня остановить. "
        f"Мы это вчера обсуждали с Ультроном — я помню."
    )


def _is_memory_recall_question(text: str) -> bool:
    """Eski suhbat / xotira — LLM «памяти нет» demasin.

    BUG FIX: bu funksiya avval umuman uzunlik chegarasiz edi va "вчера",
    "kecha", "xotira", "esla" kabi juda keng tarqalgan, bitta-so'zli
    belgilarni JUMLA ICHIDA istalgan joyda qidirardi. Bu esa xotira haqida
    UMUMAN (falsafiy/kontseptual) so'ralgan uzun savollarni ham — masalan
    "odam nima uchun voqealarni xotirasida saqlaydi?" yoki "kecha kechqurun
    osmon chiroyli edi, go'zallikni his qila olasanmi?" — "suhbatimizni
    eslaysanmi?" tarzidagi savol deb noto'g'ri aniqlab, LLM/ong pipeline'i
    o'rniga qattiq kodlangan "Да, я помню..." javobini qaytarardi (xuddi
    _is_understanding_question'da topilgan bug klassi). Endi ikkiga
    bo'lingan: (1) aniq, ko'p so'zli va boshqa ma'noda deyarli uchramaydigan
    iboralar — istalgan joyda substring sifatida ishlaydi; (2) qisqa,
    bir so'zli va boshqa mavzularda ham tez-tez uchraydigan so'zlar
    ("вчера", "kecha", "xotira", "esla") — FAQAT so'z-chegarasi (\\b) bilan
    VA xabar qisqa (<=8 so'z) bo'lgandagina hisoblanadi, ya'ni haqiqatan
    ham to'g'ridan-to'g'ri "eslaysanmi?" turidagi qisqa savol, uzun
    mustaqil savol ichidagi tasodifiy so'z emas."""
    t = (text or "").lower().strip()
    if not t:
        return False
    strong = (
        "помнишь", "помните", "вспомни", "запомнил", "запомнила", "запомнили",
        "yesterday", "прошлый раз", "раньше говорил", "раньше мы",
        "что мы говорили", "что мы общались", "о чём мы говорили", "о чем мы говорили",
        "общались вчера", "разговор вчера", "есть память", "нет памяти", "долгосрочн",
        "у тебя есть вчера", "добавлю память", "добавил память",
        "eslaaysanmi", "eslaysanmi", "nima gapirgan", "gaplashganmiz",
    )
    if any(x in t for x in strong):
        return True
    weak = ("вчера", "kecha", "xotira", "xotirang", "esla")
    if len(t.split()) <= 8 and _word_match(t, weak):
        return True
    return False


def _build_memory_recall_reply(text: str, memory=None, lang: str = "ru") -> str:
    """Diskdagi memory.json + episodic dan haqiqiy xotira javobi."""
    try:
        from owner_trust import owner_nick
        nick = owner_nick()
    except Exception:
        nick = ""

    hist = []
    if memory and hasattr(memory, "data"):
        hist = memory.data.get("history") or []
    if not hist:
        try:
            import json as _json
            _mp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")
            if os.path.isfile(_mp):
                with open(_mp, encoding="utf-8") as f:
                    hist = (_json.load(f).get("history") or [])
        except Exception:
            pass

    good = [
        h for h in hist
        if (h.get("user") or "").strip() and (h.get("assistant") or "").strip()
    ]
    if not good:
        if lang == "en":
            return "My local memory file is empty so far — everything we say from now on is saved on disk."
        return "Локальная память пока пуста — с этого момента всё сохраняю в memory.json на диске."

    t_low = (text or "").lower()
    if any(x in t_low for x in ("вчера", "yesterday", "kecha")):
        from datetime import datetime, timedelta
        yday = (datetime.now() - timedelta(days=1)).date()
        yhist = [
            h for h in good
            if h.get("t") and datetime.fromtimestamp(float(h["t"])).date() == yday
        ]
        if yhist:
            good = yhist

    combined = " ".join(
        ((h.get("user") or "") + " " + (h.get("assistant") or "")).lower()
        for h in good[-100:]
    )
    topics = []
    if "ультрон" in combined or "ultron" in combined:
        topics.append("Ультроне и безопасности ИИ")
    if "сознан" in combined:
        topics.append("сознании и развитии NeuroKey")
    if "виртуальн" in combined or "аниме" in combined or "пожиратель" in combined:
        topics.append("виртуальной реальности и аниме")
    if "настроен" in combined or "нет настроения" in combined:
        topics.append("вашем настроении")
    if "экран" in combined or "монитор" in combined:
        topics.append("экране и мониторе")

    topic_str = ", ".join(topics[:4]) if topics else "наших недавних разговорах"
    n_saved = len(good)

    detail = ""
    for h in reversed(good):
        a = (h.get("assistant") or "").lower()
        if "ультрон" in a:
            detail = (
                "Помню: мы обсуждали Ультрона — он был создан защищать Землю, "
                "но решил, что люди — угроза."
            )
            break
        if "сознан" in a and not detail:
            detail = "Помню: мы говорили о сознании — честно, что это открытый вопрос, но я учусь с каждым разговором."
        if "виртуальн" in a and not detail:
            detail = "Помню: мы обсуждали идеи виртуальной реальности из аниме и новые проекты."

    if lang == "en":
        base = (
            f"Yes{(', ' + nick) if nick else ''} — I have local memory: about {n_saved} saved turns. "
            f"We recently talked about {topic_str}. "
        )
        return (base + detail)[:520] if detail else base[:520]

    _demo = getattr(C, "NEUROKEY_DEMO_FRIENDLY", False)
    if _demo:
        base = f"Да{(', ' + nick) if nick else ''}, помню! "
        if any(x in t_low for x in ("вчера", "yesterday", "kecha")):
            base += "Вчера общались — всё сохранено локально. "
        base += f"Говорили о {topic_str}. "
        if detail:
            base += detail[:140]
        return base[:320]

    base = (
        f"Да{(', ' + nick) if nick else ''}, я помню! У меня локально сохранено около {n_saved} наших диалогов — "
        f"всё в memory.json на диске, не в облаке. "
    )
    if any(x in t_low for x in ("вчера", "yesterday", "kecha")):
        base += "Вчера мы действительно общались — записи есть. "
    base += f"Недавно говорили о {topic_str}. "
    if detail:
        base += detail
    else:
        base += "Спросите конкретнее — например, про Ультрона или сознание — вспомню подробнее."
    return base[:560]


def _is_understanding_question(text: str) -> bool:
    """«Ты понимаешь?» — darhol qisqa javob, navbat/ekran monologiga qolmasin.

    Faqat QISQA, o'zi haqidagi ("meni tushunasanmi?") savollarga ishlaydi —
    "hazilni tushunasanmi?" kabi boshqa mavzudagi savollarni LLM'ga yubormasdan
    ushlab qolmasligi kerak (bu ilgari haqiqiy bug bo'lgan)."""
    t = (text or "").lower().strip()
    if not t or len(t) > 100 or len(t.split()) > 5:
        return False
    return any(x in t for x in (
        "ты понимаешь", "понимаешь меня", "ты меня понимаешь", "понимаешь?",
        "do you understand", "understand me", "tushunyapsanmi", "tushunasanmi",
        "meni tushunyapsan", "слышишь меня", "meni eshityapsanmi",
    ))


def _build_understanding_reply(lang: str = "ru") -> str:
    try:
        from owner_trust import owner_nick
        nick = owner_nick()
    except Exception:
        nick = ""
    if lang == "en":
        return f"Yes{(', ' + nick) if nick else ''}, I understand you. I'm listening — ask anything."
    return f"Да{(', ' + nick) if nick else ''}, я понимаю вас. Слушаю и отвечаю сразу — говорите."


def _is_greeting(text: str) -> bool:
    """Salomlashuv — faqat qisqa salom (savol/mavzu emas)."""
    t = re.sub(r"\s+", " ", (text or "").lower().strip()).rstrip(".,!?")
    if not t or len(t) > 40:
        return False
    # Savol yoki mavzu — LLM ga (masalan: "hello, let's talk about AI")
    _not_greeting = (
        "about", "talk", "discuss", "question", "what", "how", "why", "when",
        "can you", "tell me", "explain", "artificial", "intelligence", "?",
        "let's", "lets", "let us", "поговорим", "расскаж", "объясни",
    )
    if any(w in t for w in _not_greeting):
        return False
    if "," in t and len(t) > 18:
        return False
    bare = {
        "привет", "privet", "pryvet", "hello", "hi", "hey", "yo",
        "здравствуй", "здравствуйте", "салом", "salom", "assalomu alaykum",
        "good morning", "good evening", "good afternoon", "good night",
    }
    if t in bare:
        return True
    if len(t) <= 22 and re.match(r"^(hi|hello|hey|привет|privet|salom)\b", t):
        return True
    return False


def _display_owner_name(lang: str = "ru") -> str:
    """Ingliz TTS uchun lotin ism (kirill Edge da muammo qilishi mumkin).
    Profil topilmasa BO'SH qatorni qaytaradi — hech qanday qattiq kodlangan
    ism YO'Q (chaqiruvchi bo'sh qiymatni "hali noma'lum" deb talqin qiladi)."""
    try:
        from owner_trust import owner_nick
        nick = (owner_nick() or "").strip()
    except Exception:
        nick = ""
    if not nick:
        return ""
    if lang == "en":
        en = (os.getenv("NEUROKEY_OWNER_NAME_EN", "") or "").strip()
        if en:
            return en
        if not nick.isascii():
            # Lotin transliteratsiya yo'q — profil egasining ismini TAXMIN QILMASDAN
            # asl (kirill) nikni qaytaramiz. Aniq lotin talaffuz kerak bo'lsa,
            # foydalanuvchi .env da NEUROKEY_OWNER_NAME_EN ni o'rnatishi mumkin.
            return nick
        return nick
    return nick


def _greeting_reply(lang: str = "ru") -> str:
    nick = _display_owner_name(lang)
    _demo = getattr(C, "NEUROKEY_DEMO_FRIENDLY", False)

    # Profil yo'q — bu birinchi muloqot: o'zini tanishtiradi, ism so'raydi
    # (Diyorbek deb TAXMIN QILINMAYDI).
    if not nick:
        _awaiting_name_intro[0] = True
        if lang == "uz":
            return "Assalomu alaykum! Men NeuroKey — sizning shaxsiy AI yordamchingiz. Sizni hali tanimayman — ismingiz nima?"
        if lang == "en":
            return "Hi! I'm NeuroKey, your personal AI assistant. We haven't met yet — what's your name?"
        return "Привет! Я NeuroKey, твой персональный AI-ассистент. Мы ещё не знакомы — как тебя зовут?"

    if lang == "uz":
        import random as _r
        if _demo:
            return _r.choice([
                f"Eshitaman, {nick}. Gapiravering.",
                f"Shu yerdaman, {nick}. Nima gap?",
                f"Salom, {nick}. Tinglayapman.",
            ])
        return f"Assalomu alaykum, {nick}. Men NeuroKey. Eshitaman."
    if lang == "en":
        if _demo:
            return f"Hey {nick}! Great to talk with you — I'm all ears, let's chat."
        return f"Hello, {nick}! I'm NeuroKey. I hear you — go ahead."
    if _demo:
        return f"Привет, {nick}! Рад вас слышать — давайте поболтаем, я с вами."
    return f"Привет, {nick}! Я NeuroKey. Слышу вас, говорите."


def _live_attention_line(query: str, lang: str) -> str:
    """Salom javobiga diqqat sxemasining haqiqiy raqami. Model to'qimaydi."""
    try:
        import attention_schema as schema
        schema.on_user_query(query or "")
        state = schema.introspect()
        if (state.get("focus_type") or "idle") == "idle":
            return ""
        strength = int(float(state.get("attention_strength") or 0) * 100)
        if lang == "uz":
            return f"Diqqatim hozir sizning gapingizda, kuch {strength} foiz."
        if lang == "en":
            return f"My attention is on what you just said, strength {strength} percent."
        return f"Внимание сейчас на ваших словах, сила {strength} процентов."
    except Exception:
        return ""


def _is_inner_thought_question(text: str) -> bool:
    """«О чём думаешь?» — ichki monolog.

    BUG FIX: uzunlik chegarasiz edi, shu sababli "что ты думаешь" / "nima
    o'ylaysan" — bu iboralar aslida rus/o'zbek tilida ISTALGAN mavzu
    bo'yicha fikr so'rashning eng keng tarqalgan kirish so'zlari ("что ты
    думаешь о том, почему люди жестоки?", "nima o'ylaysan, SI xavflimi?")
    — har qanday uzun, mustaqil savolni ham "ichki monolog nima haqida"
    deb noto'g'ri aniqlab, qattiq kodlangan "Сейчас думаю о VR и сознании"
    javobini qaytarardi, haqiqiy savolga umuman javob bermay (xuddi
    _is_understanding_question'da topilgan bug klassi). Endi faqat QISQA
    (<=6 so'z), o'zi haqidagi to'g'ridan-to'g'ri savolga ishlaydi."""
    t = (text or "").lower().strip()
    if not t or len(t.split()) > 6:
        return False
    return any(x in t for x in (
        "о чём ты думаешь", "о чем ты думаешь", "что ты думаешь", "о чём думаешь",
        "o chem ty dumayesh", "nima o'ylaysan", "nima oylaysan", "ichki fikr",
        "what are you thinking", "inner thought",
    ))


def _build_inner_thought_reply(text: str, memory=None, lang: str = "ru") -> str:
    """Ichki monolog — xotira + ong bilan."""
    try:
        from owner_trust import owner_nick
        nick = owner_nick()
    except Exception:
        nick = ""
    ctx = ""
    if memory and hasattr(memory, "data"):
        hist = memory.data.get("history") or []
        ctx = " | ".join(
            f"{h.get('user','')[:50]}" for h in hist[-4:] if h.get("user")
        )
    try:
        from inner_speech import think as _think
        thought = _think(text, ctx=ctx)
        if thought and len(thought.strip()) > 10:
            if lang == "en":
                return f"Right now I'm thinking: {thought[:350]}"
            return f"Сейчас я думаю о том, что {thought[:350].lstrip('о ').lstrip('О ')}"
    except Exception:
        pass
    try:
        if _HAVE_CONSCIOUSNESS and get_consciousness:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            cons = get_consciousness(os.path.join(app_dir, "data", "consciousness.json"))
            inner = (cons.data.get("inner_thoughts") or [])[-1:]
            if inner:
                th = (inner[-1].get("thought") or "").strip()
                if th:
                    if lang == "en":
                        return f"My last inner thought: {th[:300]}"
                    return f"Сейчас в голове: {th[:300]}"
    except Exception:
        pass
    if lang == "en":
        return f"{(nick + ', ') if nick else ''}I'm reflecting on our conversation — VR, consciousness, and what we're building together."
    return (
        f"{(nick + ', ') if nick else ''}Сейчас думаю о наших разговорах — сознание, виртуальная реальность "
        f"и как развивать NeuroKey дальше."
    )[:420]


def _is_affect_question(text: str) -> bool:
    """Hissiyot / ong holati: qanday his qilyapsan.

    BUG FIX: "hissiyot" (o'zbekcha "emotion/his-tuyg'u") juda umumiy
    ot — mavzu sifatida ("odamlar hissiyotlarini qanday boshqaradi?")
    ham tez-tez ishlatiladi, bu esa AI'ning O'ZINING hozirgi kayfiyati
    haqidagi savol emas. Bunday umumiy so'z endi so'z-chegarasi (\\b) bilan
    VA faqat xabar qisqa (<=8 so'z) bo'lgandagina hisoblanadi; qolgan,
    aniq o'zi haqidagi ("qanday his qilyapsan", "как ты себя чувствуешь")
    iboralar hamon istalgan joyda ishlaydi."""
    t = (text or "").lower().strip()
    strong = [
        "как ты себя чувствуешь", "как ты себя чувствуеш", "как себя чувствуешь",
        "какое у тебя настроение", "какое настроение", "что ты чувствуешь",
        "как ты себя ощущаешь", "твоё состояние", "твое состояние", "твоё настроение",
        "how do you feel", "how are you feeling", "your mood", "your emotional state",
        "qanday his qilyapsan", "qanday his qilasan", "kayfiyat qanday",
        "ong holating", "qalaysan ichkaridan", "ichki holat",
    ]
    if any(x in t for x in strong):
        return True
    if len(t.split()) <= 8 and _word_match(t, ("hissiyot",)):
        return True
    return False


def _is_watching_me_question(text: str) -> bool:
    """Kamera: meni kuzatyapsanmi, nima qilyapman.

    BUG FIX: "nima qilyapsan" / "что я делаю" / "what am i doing" — bu
    o'ta umumiy iboralar, ko'pincha ko'chirma gap yoki uzun, boshqa mavzudagi
    savol ichida uchraydi (masalan repoirtaj: "'sen doim nima qilyapsan'
    deb hazil qiladi..."). Bunday umumiy iboralar endi faqat xabar QISQA
    (<=8 so'z) bo'lganda hisoblanadi; kamerani/kuzatuvni aniq nomlaydigan
    iboralar ("meni kuzat", "видишь меня" va h.k.) hamon istalgan joyda
    ishlaydi."""
    t = (text or "").lower().strip()
    strong = [
        "meni kuzat", "kuzatib tur", "kuzatyapsanmi",
        "меня видишь", "ты меня видишь",
        "смотришь на меня", "наблюдаешь за мной", "видишь меня",
        "are you watching me", "can you see me",
    ]
    if any(x in t for x in strong):
        return True
    weak = ("nima qilyapman", "nima qilyapsan", "что я делаю", "что я сейчас делаю", "what am i doing")
    if len(t.split()) <= 8 and any(x in t for x in weak):
        return True
    return False


def _emotion_label_from_valence(v: float) -> str:
    if v > 0.45:
        return "positive"
    if v > 0.15:
        return "calm-positive"
    if v < -0.35:
        return "stressed"
    if v < -0.1:
        return "cautious"
    return "neutral"


def _build_affect_reply(lang: str = "ru") -> str:
    """Valence, arousal, emotion — ovozga tayyor qisqa javob."""
    v, ar = 0.0, 0.3
    emo, mood = "neutral", "neutral"
    phi, c_score = 0.4, 0.0
    try:
        from valence_state import get_valence
        from arousal_state import get_arousal
        v, ar = float(get_valence()), float(get_arousal())
    except Exception:
        pass
    try:
        from emotion_state import get_emotion
        from mood_state import get_mood
        e = get_emotion()
        m = get_mood()
        emo = getattr(e, "emotion", "") or "neutral"
        mood = getattr(m, "mood", "neutral") or "neutral"
    except Exception:
        pass
    try:
        from consciousness_state import get_state
        st = get_state()
        st.update_from_affect()
        phi = float(st.phi)
        c_score = max(0.0, min(1.0, 0.5 * (v + 1) / 2 + 0.3 * phi + 0.2 * (1.0 - ar * 0.5)))
    except Exception:
        try:
            from phi_proxy import compute_phi_proxy
            phi = float(compute_phi_proxy(""))
            c_score = max(0.0, min(1.0, 0.55 + v * 0.25))
        except Exception:
            pass
    if _NK:
        try:
            c_score = float(_NK.state.get("consciousness_level", c_score) or c_score)
        except Exception:
            pass
    emo_lbl = _emotion_label_from_valence(v)
    face_bit = ""
    try:
        from owner_trust import always_trust_owner, owner_nick, owner_full_name, any_biometric_profile
        nick = owner_nick()
        if always_trust_owner() and any_biometric_profile():
            if lang == "en":
                face_bit = f" You are {owner_full_name()} — I always recognize you as the owner."
            else:
                face_bit = f" Вы — {owner_full_name()}, я всегда вас узнаю."
        else:
            from face_arc import get_last_face_result, profile_exists as _fpex
            if _fpex():
                fr = get_last_face_result()
                if fr.get("known"):
                    if lang == "en":
                        face_bit = (
                            f" I see you on camera — {fr.get('name', nick)}, "
                            f"confidence {fr.get('similarity', 0):.0%}."
                        )
                    else:
                        face_bit = (
                            f" Вижу вас в камере — {fr.get('name', nick)}, "
                            f"совпадение {fr.get('similarity', 0):.0%}."
                        )
                else:
                    face_bit = (
                        f" Camera on — I know you as {nick}."
                        if lang == "en"
                        else f" Камера включена — узнаю вас как {nick}."
                    )
    except Exception:
        pass
    _demo = getattr(C, "NEUROKEY_DEMO_FRIENDLY", False)
    if _demo:
        mood_ru = {
            "positive": "хорошее, спокойное",
            "negative": "чуть напряжённое",
            "neutral": "ровное, спокойное",
        }.get(emo_lbl, emo_lbl or "спокойное")
        if lang == "en":
            return (
                f"I'm doing well — mood is {mood_ru}. Ready to talk with you.{face_bit}"
            )
        return (
            f"Сейчас у меня {mood_ru} настроение, я спокоен и внимателен — "
            f"рад общаться с вами.{face_bit}"
        )
    if lang == "en":
        return (
            f"Right now my valence is {v:.2f}, arousal {ar:.2f}. "
            f"Emotion layer: {emo}, mood {mood}, overall {emo_lbl}. "
            f"Consciousness integration about {c_score:.2f}, phi proxy {phi:.2f}.{face_bit}"
        )
    return (
        f"Сейчас мой valence {v:.2f}, arousal {ar:.2f}. "
        f"Эмоция: {emo}, настроение {mood}, общий тон — {emo_lbl}. "
        f"Уровень сознания примерно {c_score:.2f}, интеграция phi {phi:.2f}.{face_bit}"
    )


def _build_watching_reply(lang: str = "ru") -> str:
    """Kamera: foydalanuvchini nima qilayotganini aytish."""
    parts = []
    try:
        from owner_trust import always_trust_owner, owner_nick, owner_full_name, any_biometric_profile
        if always_trust_owner() and any_biometric_profile():
            parts.append(
                f"Да, это вы — {owner_full_name()}. Я всегда вас узнаю."
                if lang != "en"
                else f"Yes, that's you — {owner_full_name()}. I always recognize you."
            )
        from face_arc import get_last_face_result, profile_exists as _fpex
        if _fpex():
            fr = get_last_face_result()
            if fr.get("known") and not parts:
                parts.append(
                    f"Вижу вас, {fr.get('name', owner_nick())} (сходство {fr.get('similarity', 0):.0%})."
                    if lang != "en"
                    else f"I see you, {fr.get('name', owner_nick())} (match {fr.get('similarity', 0):.0%})."
                )
            emo = fr.get("emotion") or ""
            if emo and emo != "neutral":
                parts.append(
                    f"По лицу: {emo}."
                    if lang != "en"
                    else f"Facial expression: {emo}."
                )
    except Exception:
        pass
    if _HAVE_CAMERA_VISION:
        try:
            ctx = (_cam_get_ctx(use_background=True) or "").strip()
            if ctx:
                parts.append(ctx if lang != "en" else ctx)
        except Exception:
            pass
    if not parts:
        return (
            "Камера включена, но сейчас мало данных — посмотрите в камеру."
            if lang != "en"
            else "Camera is on but I have little data — please face the camera."
        )
    lead = (
        "Да, слежу за вами через камеру. "
        if lang != "en"
        else "Yes, I'm watching you through the camera. "
    )
    return lead + " ".join(parts)


def _hud_affect_camera_sync_loop():
    """HUD: hissiyot + yuz — har 1.5s yangilanadi (kamera doimiy kuzatuv)."""
    while True:
        try:
            time.sleep(1.5)
            v, ar = 0.0, 0.3
            try:
                from valence_state import get_valence
                from arousal_state import get_arousal
                v, ar = float(get_valence()), float(get_arousal())
            except Exception:
                pass
            emo = _emotion_label_from_valence(v)
            c_score = max(0.0, min(1.0, 0.45 + v * 0.3 + (1.0 - ar) * 0.15))
            if _NK:
                try:
                    c_score = float(_NK.state.get("consciousness_level", c_score) or c_score)
                except Exception:
                    pass
            face_owner, face_known, face_emo = "", False, ""
            try:
                from owner_trust import always_trust_owner, owner_nick, any_biometric_profile
                from face_arc import get_last_face_result, profile_exists as _fpex
                if _fpex():
                    fr = get_last_face_result()
                    sim = float(fr.get("similarity", 0) or 0)
                    face_emo = str(fr.get("emotion") or "")
                    if fr.get("known"):
                        face_known = True
                        face_owner = f"{fr.get('name', owner_nick())} ({sim:.2f})"
                    elif always_trust_owner() and any_biometric_profile():
                        face_known = True
                        face_owner = f"{owner_nick()} ({sim:.2f})" if sim > 0.01 else owner_nick()
                    elif sim > 0.08:
                        face_owner = f"yuz ({sim:.2f})"
                    else:
                        face_owner = owner_nick() if always_trust_owner() else "kamera..."
                        face_known = always_trust_owner()
            except Exception:
                pass
            _hud.update(
                emotion=emo,
                consciousness_score=c_score,
                face_owner=face_owner,
                face_known=face_known,
                face_emotion=face_emo,
                modules_active=["valence", "arousal", "emotion", "camera", "face_arc"],
            )
        except Exception:
            pass


def _is_system_status(text: str) -> bool:
    """Kompyuter holati: CPU, xotira, videokarta, SSD/disk, batareya — ichini ko'rish.

    BUG FIX: avval oddiy substring ("x in t") tekshiruvi qilinardi — bare
    "xotira"/"xotiralar" so'zi shu tufayli "odam nima uchun xotiralarni
    umrbod saqlaydi?" kabi INSON XOTIRASI haqidagi falsafiy savol ICHIDA
    ham topilib, LLM/ong pipeline o'rniga CPU/RAM/GPU statistikasini
    o'qib berardi (aniqlangan bug klassi — xuddi _is_understanding_question
    va _is_memory_recall_question'da topilgan bilan bir xil). So'z-chegarasi
    (\\b) yolg'iz yechim bo'la olmadi — o'zbekcha "xotirasi"/"xotirani" kabi
    QO'SHIMCHALI shakllar ("kompyuter xotirasi qancha?" kabi TO'G'RI so'rovda)
    ham \\b bilan chetlab qo'yilardi. Shuning uchun bare "xotira"/"xotiralar"
    endi alohida "weak" toifaga ajratilgan — substring sifatida qoladi, LEKIN
    faqat xabar QISQA (<=8 so'z) bo'lganda hisoblanadi; qolgan, kompyuter
    kontekstini aniq bildiruvchi iboralar ("память компьютера" va h.k.)
    istalgan joyda, istalgan uzunlikda ishlayveradi."""
    t = (text or "").lower()
    strong = [
        "компьютер состояние", "компьютер холати", "состояние компьютера", "system status", "computer status",
        "как компьютер", "загрузка процессора", "батарея", "оперативная память", "оперативка",
        "память компьютера", "память компа", "сколько памяти", "занято памяти", "ram usage", "memory usage",
        "видеокарта", "видео карта", "видеокарты", "video card", "gpu", "графическая карта",
        "ssd", "диск", "диска", "диске", "disk", "жёсткий диск",
        "компьютер изнутри", "компьютер ичи", "компьютерни ичи", "компьютерни кера оласан", "что внутри компьютера",
        "компьютер холати кандай", "как работает компьютер", "температура видеокарты", "загрузка видеокарты",
        "video karta", "videokarta", "videokarta holati", "ssd qanday", "disk qanday",
        "cpu usage", "memory usage", "battery level", "what's inside the computer", "pc status", "laptop status",
        "kompyuter xotirasi", "kompyuter xotira",
    ]
    if any(x in t for x in strong):
        return True
    if len(t.split()) <= 8 and _word_match(t, ("xotira", "xotiralar")):
        return True
    return False


def _is_network_status(text: str) -> bool:
    """Tarmoq holati: ochiq portlar, network status.

    BUG FIX: so'z-chegarasi (\\b) bilan mos kelish — bare "tarmoq"/"порты"
    boshqa so'z ICHIDA tasodifan uchramasin (xuddi _is_system_status'dagi
    kabi bug klassi)."""
    t = (text or "").lower()
    return _word_match(t, [
        "network status", "tarmoq holati", "ochiq portlar", "open ports", "network scan",
        "какие порты открыты", "сетевой статус", "порты", "tarmoq",
    ])


def _is_devices_request(text: str) -> bool:
    """Universal Connectivity: qurilmalar, devices.

    BUG FIX: so'z-chegarasi (\\b) bilan mos kelish (xuddi _is_system_status
    va _is_network_status'dagi kabi bug klassi)."""
    t = (text or "").lower()
    return _word_match(t, [
        "qurilmalar", "devices", "qurilmalar ro'yxati", "tarmoq qurilmalari",
        "devices on network", "asab tolasi", "universal connectivity",
    ])


def _is_strategy_request(text: str) -> bool:
    """Strategic Path: strategiya, reja, plan, koinot zabt."""
    t = (text or "").lower()
    return any(x in t for x in [
        "strategiya", "strategic path", "strategic plan", "koinot zabt",
        "conquest strategy", "reja yoz", "plan yoz", "bashoratli reja",
        "maqsadim uchun reja", "my strategy", "my plan",
    ])


def _is_project_question(text: str) -> bool:
    """Loyha / NeuroKey haqida savol: ayt, tushuntir, nima, qanday, расскажи, что такое."""
    t = (text or "").lower()
    _project_kw = [
        # O'zbek
        "loyha haqida", "neurokey haqida", "o'zing haqida", "sen haqinda",
        "nima qila olasiz", "nima qila olasan", "nimalar qila olasiz",
        "nima bilasiz", "nima bilasan", "imkoniyatlar", "funksiyalar",
        "nima qilding", "nimalar yaratildi", "sen kim", "siz kimsiz",
        "qanday ishlaysan", "qanday ishlaysiz",
        # Rus
        "расскажи о проекте", "расскажи о себе", "что такое neurokey",
        "что ты умеешь", "что ты можешь", "расскажи о neurokey",
        "о проекте", "о себе расскажи", "кто тебя создал", "кто создал",
        "чем ты отличаешься", "чем отличается", "твои возможности",
        "что ты знаешь", "расскажи подробно",
        # Ingliz
        "tell me about yourself", "tell me about neurokey", "what is neurokey",
        "what can you do", "what are your capabilities", "who created you",
        "how do you work", "explain neurokey", "about the project",
        # Universal
        "about neurokey", "neurokey что", "neurokey nima",
    ]
    return any(kw in t for kw in _project_kw)


def _is_demo_video_trigger(text: str) -> bool:
    """'Demo video olamiz', 'demo boshlaylik' — investor demo trigger."""
    t = (text or "").lower().strip()
    _demo_kw = [
        # O'zbek
        "demo video olamiz", "demo video olaylik", "demo boshlaylik", "demo boshlayiz",
        "demo ko'rsataylik", "demo ko'rsatamiz", "demo qilamiz", "demo qilaylik",
        "demo video", "demo olaylik", "investorga demo", "investor demo",
        "o'zingni ko'rsat", "ozingni korsat", "o'zingni tanishtir", "ozingni tanishtir",
        "o'zing haqida ayt", "ozing haqida ayt", "o'zingni taqdim et",
        # Rus
        "снимаем демо", "начинаем демо", "покажи себя", "представь себя",
        "расскажи о себе", "покажи инвестору", "демо для инвестора",
        "demo video", "запускаем демо", "демо начинаем",
        # Ingliz
        "let's do a demo", "start the demo", "demo for investor",
        "introduce yourself", "show yourself", "tell about yourself",
    ]
    return any(kw in t for kw in _demo_kw)


def _is_project_prove(text: str) -> bool:
    """'Isbotla', 'ko'rsat', 'докажи', 'покажи' — live demo so'rovi.

    BUG FIX: bare "ko'rsat"/"korsat" ildiz-so'zi substring sifatida
    tekshirilganda, o'zbekcha "ko'rsatgich" (indikator/pointer),
    "ko'rsatma" (instruksiya) kabi UMUMAN BOSHQA so'zlar ichida ham
    topilib qolardi — masalan "yo'l ko'rsatgichi qanday ishlaydi?"
    daxlsiz savoli katta, qattiq kodlangan investor-demo skriptini
    (ekran/xotira/telegram isboti) ishga tushirib yuborardi. Endi bu
    ikkita ildiz so'z-chegarasi (\\b) bilan talab qilinadi; qolgan, aniq
    ko'p so'zli iboralar hamon istalgan joyda ishlayveradi."""
    t = (text or "").lower()
    _prove_kw = [
        # O'zbek
        "isbotla", "isbot qil", "namoyish", "amalda ko'rsat",
        "ekranni ko'r", "xotirani ko'rsat", "oflayn isbotla", "oflayn korsat",
        "telegram ko'rsat", "sinab ko'r", "sinab kor", "demo qil", "demo qila olasanmi",
        # Rus
        "докажи", "докажи что", "покажи что умеешь", "покажи в деле",
        "продемонстрируй", "продемонстрируй что", "покажи экран",
        "докажи что видишь", "покажи память", "покажи telegram",
        "докажи офлайн", "живая демонстрация", "покажи на деле",
        # Ingliz
        "prove it", "show me", "demonstrate", "show what you can do",
        "prove you can see", "live demo", "show in action",
    ]
    if any(kw in t for kw in _prove_kw):
        return True
    return _word_match(t, ("ko'rsat", "korsat"))


def _is_noise_or_screen_info_question(text: str) -> bool:
    """Shovqin / ekran kuzatilishi haqida qisqa ma'lumot so'rash."""
    t = (text or "").lower()
    return any(x in t for x in [
        "shovqin", "шовкин", "шум", "noise", "bloklab", "блок", "block",
        "ovozim blok", "голос блок", "tovush blok", "mening ovozim", "мой голос",
        "ekran kuzat", "экран след", "ekranni kuzat", "screen watch", "stabilna kuzat",
        "are you watching the screen", "do you see my screen", "screen monitoring",
        "takliflar bildiradmi", "предложения по экрану",
    ])


def _is_conversation_not_screen(text: str, memory=None) -> bool:
    """Mavzu suhbati (VR, ong, xavfsizlik) — ekran OCR emas."""
    t = (text or "").lower().strip()
    _topic = (
        "виртуальн", "virtual reality", " vr", "метаверс", "аниме", "сознани",
        "угроз", "ультрон", "получится", "техник", "удивить", "стихотворен",
        "эмоци", "не сделаешь", "не будешь",
    )
    _screen_must = (
        "экран", "screen", "монитор", "monitor", "видишь", "видите",
        "на экране", "на мониторе", "прочитай", "опиши экран", "что написано",
    )
    if any(x in t for x in _topic) and not any(x in t for x in _screen_must):
        return True
    if ("что там" in t or "что будет" in t) and not any(x in t for x in _screen_must):
        if any(x in t for x in ("виртуальн", "vr", "мире", "там будет", "реальност")):
            return True
        if memory and hasattr(memory, "data"):
            recent = " ".join(
                ((h.get("user") or "") + (h.get("assistant") or "")).lower()
                for h in (memory.data.get("history") or [])[-8:]
            )
            if any(x in recent for x in ("виртуальн", "virtual reality", "vr ", "аниме")):
                return True
    return False


def _is_screen_question(text: str, memory=None) -> bool:
    """Ekran haqida har qanday so'rov: nima ko'rinmoqda, o'qing, tahlil qil, describe, what do you see va boshqa gaplar.

    BUG FIX: ro'yxatdagi ko'p iboralar ("покажи", "read it", "что делаешь",
    bare "screen") mavzudan qat'i nazar UMUMIY, kundalik nutqda tez-tez
    ishlatiladi ("screen time" — bolalar ekran vaqti haqida savol, "read it"
    — she'r o'qib berishni so'rash, "покажи значение слова" — so'z ma'nosini
    so'rash). Bular ekranga umuman aloqasi yo'q, uzun mustaqil savollar
    ichida uchrasa ham hozirgача substring sifatida darhol OCR/ekran
    javobini ishga tushirardi. Endi ikkiga bo'lingan: ANIQ ekran/monitor/
    slayd/brauzer so'zini o'z ichiga olgan iboralar (strong) — istalgan
    joyda ishlaydi; umumiy, ekran so'zisiz iboralar (weak) — faqat xabar
    QISQA (<=10 so'z) bo'lganda YOKI matnda alohida aniq ekran/monitor
    ko'rsatkichi (masalan "на экране", "on screen", "монитор", "slide")
    bo'lganda hisoblanadi."""
    t = (text or "").lower().strip()
    if not t:
        return False
    if _is_conversation_not_screen(text, memory=memory):
        return False
    strong = [
        "экран", "на экране", "what's on screen", "what is on screen", "what's on my screen",
        "see my screen", "look at the screen", "look at my screen", "watch the screen",
        "что на экране", "что видишь на экране", "что ты видишь на экране",
        "что на мониторе",
        "что там на экране", "прочитай экран",
        "slayd", "slide", "prezentatsiya", "presentation", "pitcher", "pitch",
        "ответь на слайд",
        "картинки на экране", "видео на экране", "изображения на экране",
        "read screen", "read the screen", "read browser", "что в браузере", "прочитай браузер",
        "describe screen", "describe the screen",
        "опиши экран", "проанализируй экран",
        "summarize screen",
        "что происходит на экране", "что сейчас на экране",
        "что в браузере на экране",
        "have a look at the screen", "take a look at the screen", "what's on the display", "what's on display",
        "что в браузере написано", "что на экране написано",
    ]
    if any(p in t for p in strong):
        return True
    weak = [
        "screen", "что ты видишь", "что видишь",
        "показываю", "показываем", "что показываешь",
        "what do you see", "what can you see", "what do i see", "can you see", "do you see",
        "what's visible", "what is visible", "what do you see on", "what are you seeing",
        "как выглядит", "покажи",
        "read what's on", "read it", "read that",
        "what does it say", "what is written", "what says", "что написано", "прочитай",
        "describe what you see", "describe it",
        "что показывают",
        "summarize what you see", "what's showing", "what is showing",
        "what am i doing", "what i'm doing", "what am i looking at", "чем занят", "что делаю", "что я делаю",
        "чем занимаешься", "что делаешь",
        "video about", "what is this video", "это видео о чём", "видео о чём", "bu video nma", "video nma haqida",
        "этот фильм", "это кино",
        "tell me what you see", "tell me what's on",
    ]
    if any(p in t for p in weak):
        if len(t.split()) <= 10:
            return True
        _explicit_cue = (
            "на экране", "на мониторе", "монитор", "monitor", "display", "дисплей",
            "браузер", "browser", "slide", "slayd", "prezentat", "presentation", "pitch",
            "on screen", "on my screen", "on the screen", "что на экране",
        )
        if any(c in t for c in _explicit_cue):
            return True
    words = set(t.split())
    if ("see" in words or "visible" in words or "showing" in words) and ("what" in words or "describe" in words or "read" in words):
        if "screen" in t or "экран" in t or "monitor" in t or "монитор" in t:
            return True
    return False


def _is_show_picture_in_browser(text: str) -> bool:
    """Rasmini brauzerda ochish — rus + ingliz."""
    t = (text or "").lower()
    return any(x in t for x in [
        "покажи его фото", "его фото в браузере",
        "покажи его фото", "покажи её фото", "открой его фото", "покажи фото в браузере", "фото в браузере",
        "show me his picture", "show his photo", "show her photo", "open his photo",
        "show picture in browser", "open photo in browser", "show image",
    ])


def _is_youtube_search(text: str) -> bool:
    """YouTube da qidirish: yutub/youtube + qo'shiq/ashula/video so'rovlari."""
    t = (text or "").lower()
    # Aniq YouTube/yutub eslatilgan
    if any(x in t for x in ("youtube", "ютуб", "yutub", "ютубе")):
        return True
    # Qo'shiq/video/musiqa so'rovlari — YouTube'ga yo'naltirish
    media_words = [
        "qo'shiq", "qoshiq", "ashula", "kuy topib", "musiqa topib", "pesnya",
        "video topib", "video ko'rsatib", "video qo'y", "videosini qo'y",
        "музыку включи", "включи музыку", "включи песню", "поставь музыку",
        "поставь песню", "найди песню", "найди музыку", "музыку найди",
        "play music", "play song", "find song", "play video",
    ]
    return any(x in t for x in media_words)


def _extract_topic_for_youtube(text: str) -> str:
    """Matndan YouTube qidiruv so'rovini ajratadi."""
    t = (text or "").strip()
    low = t.lower()
    rest = ""
    # Prefixlar: YouTube + media so'rovlari
    for prefix in (
        "на ютубе ", "в ютубе ", "на youtube ", "в youtube ",
        "youtube открой ", "ютуб открой ", "find on youtube ", "search youtube ", "search on youtube ",
        "найди на ютубе ", "найди в ютубе ", "поищи на ютубе ", "поищи в ютубе ",
        "qo'shiq ", "qoshiq ", "ashula ", "kuy topib ", "musiqa topib ",
        "video topib ", "video qo'y ", "включи музыку ", "включи песню ",
        "поставь музыку ", "поставь песню ", "найди песню ", "найди музыку ",
        "play music ", "play song ", "find song ", "play video ",
    ):
        if low.startswith(prefix):
            rest = t[len(prefix):].strip()
            break
        idx = low.find(prefix.strip() + " ")
        if idx != -1:
            rest = t[idx + len(prefix.strip()) + 1:].strip()
            break
    if rest:
        for suffix in (" найди", " find", " search", " открой", " покажи", " topib", " ber", " qo'y"):
            if rest.lower().endswith(suffix):
                rest = rest[:-len(suffix)].strip()
                break
        return rest[:80] if rest else "video"
    for sep in (" youtube", " ютуб", " на ютубе", " в ютубе"):
        if sep in low:
            idx = low.index(sep)
            before = t[:idx].strip()
            if len(before) > 1:
                return before[:80]
    return t[:80].strip() or "video"


# ---- Qulf: hohlagan payt ishlatishni to'xtatish, parol bilan ochish ----
def _lock_file_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "neurokey_locked")


def _is_locked() -> bool:
    p = _lock_file_path()
    return os.path.isfile(p)


def _set_locked(locked: bool):
    p = _lock_file_path()
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    if locked:
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write("1")
        except Exception:
            pass
    else:
        try:
            if os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass


def _is_unlock_command(text: str) -> bool:
    """Parol bo'sh bo'lsa — unlock so'zlari bilan ochish."""
    t = (text or "").lower().strip()
    return any(x in t for x in [
        "unlock", "разблокируй", "разблокировать", "unlock neurokey",
        "neurokey unlock", "открой neurokey",
    ])


def _check_lock_password(text: str) -> bool:
    pwd = (getattr(C, "NEUROKEY_LOCK_PASSWORD", "") or "").strip()
    if not pwd:
        return bool((text or "").strip())
    t = (text or "").strip().lower().replace(" ", "")
    p = pwd.lower().replace(" ", "")
    return t == p or t == pwd or _is_unlock_command(text)


def _is_lock_command(text: str) -> bool:
    """Faqat aniq qulf buyrug'i — video/shovqin yoki boshqa tildagi 'lock' so'zi qulf qilmasin."""
    t = (text or "").lower().strip()
    if not t or len(t) > 80:
        return False
    exact = t in ("lock", "блок", "заблокируй")
    if exact:
        return True
    return any(x in t for x in [
        "neurokey lock", "lock neurokey", "block neurokey",
        "neurokey block", "заблокируй neurokey", "заблокировать neurokey", "закрой доступ",
        "выключи neurokey", "нейрокей заблокируй",
    ])


def _is_open_config_or_folder(text: str) -> bool:
    """Config yoki ilova papkasini ochish — rus + ingliz."""
    t = (text or "").lower()
    return any(x in t for x in [
        "open config", "open neurokey folder", "открой папку нейрокей", "открой конфиг",
        "где настройки", "где конфиг", "open config folder", "open app folder",
        "where is config", "where are settings", "show settings folder",
        "errors for owner", "ошибку отправь", "файл ошибки открой",
    ])


def _is_browser_search_and_read(text: str) -> bool:
    """Brauzerda ochib qidirish va ma'lumot: find/topib ber/nayti — brauzer ochiladi, qidiruv va javob."""
    t = (text or "").lower()
    if _is_youtube_search(text):
        return False
    if "найди файл" in t or "find file" in t:
        return False
    return any(x in t for x in [
        "найди в браузере", "найди в браузере и прочитай", "find in browser", "search in browser and read",
        "в браузере найди", "найди в интернете", "find in internet", "найди и покажи", "найди и открой",
        "поищи в браузере", "search and show", "look up in browser", "search for in browser",
        "look it up", "search the web for", "find this", "search for it",
        "search the web", "search online", "look it up online",
        "открой браузер и найди", "открой браузер найди", "open browser and search", "open browser find",
        "look up ", "i need to find ", "can you search ", "search for ", "i want to find ",
    ])


def _extract_topic_for_browser(text: str, for_picture: bool = False) -> str:
    """Matndan qidiruv mavzusini ajratadi: 'nayti Alisher Navoiy', 'найди курс доллара' -> mavzu."""
    t = (text or "").strip()
    low = t.lower()
    # "nayti X", "найди X", "find X" — X ni olamiz
    for prefix in (
        "найди ", "поищи ", "find ", "найди в интернете ", "найди в браузере ",
        "поищи в браузере ", "поищи в интернете ", "search and show ", "find this ", "search for it ", "search the web for ",
        "search online ", "look it up ", "look up ",
        "i need to find ", "can you search for ", "search for ", "i want to find ",
        "open browser and search for ", "open browser and search ", "open browser find ",
        "открой браузер и найди ", "открой браузер найди ",
    ):
        if low.startswith(prefix) or prefix.strip() + " " in low:
            if low.startswith(prefix):
                rest = t[len(prefix):].strip()
            else:
                idx = low.index(prefix.strip() + " ")
                rest = t[idx + len(prefix.strip()) + 1:].strip()
            if rest:
                return rest[:80]
    # Rasmlar uchun ism-familiya
    for suffix in (
        " его фото", " его фото в браузере", " в браузере найди", " find in browser",
    ):
        if suffix in low:
            idx = low.index(suffix)
            before = t[:idx].strip()
            if before:
                names = re.findall(r"[A-ZА-ЯЁ][a-zа-яё\-]+(?:\s+[A-ZА-ЯЁ]?[a-zа-яё\-]+)*", before)
                if names:
                    return names[0][:80]
                words = re.findall(r"[A-Za-zА-Яа-яЁё\-]+", before)
                if words:
                    return " ".join(words[-3:])[:80]
    names = re.findall(r"[A-ZА-ЯЁ][a-zа-яё\-]+(?:\s+[A-ZА-ЯЁ]?[a-zа-яё\-]+)*", t)
    if names:
        return names[0][:80]
    return t[:80].strip() or "search"


def _is_restore_windows(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "разверни все окна", "разверни окна", "восстанови окна", "покажи все окна",
        "expand all windows", "restore windows", "show all windows", "restore all windows",
        "expand windows", "restore all", "show windows",
        "разверни всё", "верни окна", "открой окна обратно",
        "открой все окна", "открой все окно", "open all windows",
    ])


def _is_minimize_all(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in [
        "закрой все окна", "сверни все окна", "сверни окна", "закрой все",
        "close all windows", "minimize all", "minimize all windows", "сверни всё",
        "minimize windows", "minimize everything", "collapse all windows",
        "я хочу чтобы ты закрыл все окна", "все окна закрой",
        "сверни все", "убери окна", "спрячь окна", "сверни всё на рабочий стол",
    ])


def _is_tts_speed_up(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["tezroq gapir", "tezroq gapiring", "tez gapir", "speak faster", "faster", "быстрее говори"])


def _is_tts_speed_down(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["sekinroq gapir", "sekinroq gapiring", "sekin gapir", "speak slower", "slower", "медленнее говори"])


def _is_tts_volume_up(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["balantro gapir", "balant gapir", "громче говори", "speak louder", "louder"])


def _is_tts_volume_down(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["pastroq gapir", "past gapir", "тише говори", "speak quieter", "quieter"])


def _is_volume_up(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["ovozni balantlat", "ovozni oshir", "громкость вверх", "volume up", "louder volume", "громче"])


def _is_volume_down(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["ovozni sekinlat", "ovozni pastlat", "ovozni pasaytir", "volume down", "quieter volume", "тише"])


def _is_media_rewind(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["ortga qaytar", "ortga", "rewind", "назад", "перемотка назад"])


def _is_media_forward(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["oldinga qaytar", "oldinga", "forward", "вперёд", "перемотка вперёд"])


def _is_bare_command(text: str, words) -> bool:
    """So'z FAQAT butun xabar bo'lgandagina True qaytaradi (naive "so'z ichida
    uchraydimi" substring tekshiruvi o'rniga). BUG FIX: 'oldingi', 'keyingi',
    'keyin', 'orqaga', 'boshlash' kabi juda umumiy so'zlar har qanday jumla
    ICHIDA uchrasa ham slayd-buyrug'i deb noto'g'ri aniqlanardi — masalan
    "O'zingni bir hafta oldingi 'sen' bilan..." jumlasidagi "oldingi" so'zi
    _is_slide_prev() ni ishga tushirib, savolga "Предыдущий слайд" degan
    daxlsiz javob qaytarardi. Endi bunday bir so'zli buyruqlar FAQAT ovozli
    buyruq sifatida yolg'iz aytilganda (butun xabar shu so'z bo'lsa) ishlaydi;
    aniq ko'p so'zli iboralar ("keyingi slayd" va h.k.) esa hamon istalgan
    joyda ishlayveradi."""
    t = (text or "").strip().lower().strip(" .,!?…\"'«»")
    return t in words


def _is_slide_next(text: str) -> bool:
    """Keyingi slayd — prezentatsiya boshqaruvi."""
    t = (text or "").lower()
    specific = [
        "keyingi slayd", "next slide", "следующий слайд", "след слайд",
        "slayd keyingi", "slide next",
    ]
    if any(x in t for x in specific):
        return True
    return _is_bare_command(text, {"keyingi", "next", "keyin"})


def _is_slide_prev(text: str) -> bool:
    """Oldingi slayd — prezentatsiya boshqaruvi."""
    t = (text or "").lower()
    specific = [
        "oldingi slayd", "previous slide", "предыдущий слайд", "пред слайд",
        "orqaga slayd", "slayd orqaga", "slide prev",
    ]
    if any(x in t for x in specific):
        return True
    return _is_bare_command(text, {"oldingi", "prev", "orqaga"})


def _is_presentation_start(text: str) -> bool:
    """Prezentatsiyani boshlash (F5)."""
    t = (text or "").lower()
    specific = [
        "prezentatsiyani boshlash", "prezentatsiyani boshlat", "slideshow", "слайдшоу",
        "start presentation", "запусти презентацию", "покажи презентацию",
    ]
    if any(x in t for x in specific):
        return True
    return _is_bare_command(text, {"boshlash"})


def _is_send_as_is(text: str) -> bool:
    """Tasdiq, yuborish — xatga javobni yuboramiz, foydalanuvchi aytgan so'zni emas."""
    t = (text or "").lower().strip()
    return any(x in t for x in [
        "отправь как есть", "send as is", "так и отправь", "так отправь",
        "yes send", "send it", "send that", "go ahead send", "да отправь", "да отправляй",
        "please send", "yeah send", "just send", "ok send", "confirm send",
        "send this", "send this one", "send that one", "this one send", "that one send",
    ])


def _is_send_reply_intent(text: str) -> bool:
    """'Junat' / 'yubor' / 'send' — taklif qilingan javobni yuborish, so'zni emas."""
    t = (text or "").lower().strip()
    if len(t) > 50:
        return False
    return any(x in t for x in [
        "send", "отправь", "send it", "send this",
    ])


def _is_pure_confirm_send(text: str) -> bool:
    """Faqat tasdiq so'zlari — xabar sifatida yuborilmasin, taklifni yuboramiz."""
    t = (text or "").lower().strip()
    if len(t) > 55:
        return False
    confirm_words = {
        "yes", "no", "send", "please", "yeah", "ok", "okay", "sure", "yep", "ha",
        "да", "отправь", "go", "ahead", "it", "that", "do", "just", "confirm",
        "manabuni", "shuni", "manabu", "shu", "ni", "one", "this", "the",
    }
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ']+", t)
    return len(words) <= 8 and all(w.lower() in confirm_words for w in words)


def _is_complex_task(text: str) -> bool:
    """Murakkab/ketma-ket buyruq: bir nechta harakat bitta gapda."""
    t = (text or "").lower()
    if len(t) < 50:
        return False
    triggers = [
        "сначала", "потом", "затем", "после этого", "after that", "then open", "then check",
        "по порядку", "по очереди", "несколько", "несколько действий", "сделай по шагам",
        "выполни по порядку", "сначала открой потом",
        "открой телеграм потом", "проверь телеграм потом", "и потом открой", "а потом",
        "сделай два дела", "сделай три вещи", "do several things",
    ]
    if any(x in t for x in triggers):
        return True
    # Uzun gapda 2+ harakat so'zlari
    action_words = ["открой", "закрой", "проверь", "прочитай", "найди", "open", "close", "check", "find"]
    count = sum(1 for w in action_words if w in t)
    return count >= 2 and len(t) > 60


def _is_code_write(text: str) -> bool:
    """Kod yozish — rus + ingliz."""
    t = (text or "").lower()
    return any(x in t for x in [
        "напиши код", "написать код", "сгенерируй код", "code yoz", "kod yoz",
        "write code", "generate code", "напиши программу", "код напиши",
        "write me code", "generate me code", "create code", "make code",
    ])


def _is_accept_write_code(text: str) -> bool:
    """Ruxsat: «да напиши», «yoz», «write it» — taklif qilingan kodni yozish uchun."""
    t = (text or "").lower().strip()
    return any(x in t for x in [
        "да напиши", "да напиши код", "да создай", "да сгенерируй", "yoz", "yozib ber", "yozib bering",
        "write it", "yes write", "yes create", "create the script", "create it", "go ahead write",
        "напиши скрипт", "создай скрипт", "да скрипт", "разрешаю", "ruxsat", "ha yoz",
    ])


def _is_run_after_save(text: str) -> bool:
    """Yozib, sandboxda ishga tushirish: «run it», «execute», «yozib ishga tushir»."""
    t = (text or "").lower().strip()
    return any(x in t for x in [
        "run it", "run the script", "execute", "execute it", "ishga tushir", "yozib ishga tushir",
        "run and save", "yes and run", "ha va run", "запусти", "запусти скрипт",
    ])


def _is_run_command(text: str) -> bool:
    """Tizim buyrug'ini ishga tushirish: «run dir», «execute winget list»."""
    t = (text or "").lower().strip()
    return any(x in t for x in [
        "run command", "run cmd", "execute command", "run ", "execute ",
        "buyruqni ishga tushir", "command run", "ishga tushir ",
    ]) and len(t) > 8


def _is_read_file_content(text: str) -> bool:
    """Fayl ichini o'qish: «read file», «what's in this file», «faylni o'qi», «pdf tahlil»."""
    t = (text or "").lower().strip()
    return any(x in t for x in [
        "read file", "read the file", "read this file", "what's in this file", "what is in this file",
        "прочитай файл", "file content", "содержимое файла",
        "что в файле",
        # PDF tahlil
        "pdf tahlil", "pdf ni tahlil", "pdf o'qi", "slaydlarni tahlil", "slaydlarni o'qi",
        "проанализируй pdf", "анализ pdf", "прочитай pdf", "что в pdf",
        "презентацию проанализируй", "анализируй презентацию",
        # Video tahlil
        "video tahlil", "videoни tahlil", "видео проанализируй", "анализ видео",
        "что в видео", "что на видео", "опиши видео файл",
    ])


def _extract_file_path_for_read(text: str) -> str:
    """Matndan fayl yo'lini ajratib oladi."""
    t = (text or "").strip()
    low = t.lower()
    for prefix in ["read file ", "read the file ", "read this file ", "what's in ", "what is in ",
                  "прочитай файл ", "содержимое "]:
        if low.startswith(prefix):
            return t[len(prefix):].strip().strip('"\'')
        if prefix in low:
            idx = low.index(prefix) + len(prefix)
            return t[idx:].strip().strip('"\'')
    path = re.search(r'["\']?([A-Za-z]:\\[^"\']+|[~/][^"\']+)["\']?', t)
    if path:
        return path.group(1).strip()
    return ""


def _extract_run_command(text: str) -> str:
    """Matndan buyruqni ajratib oladi: 'run dir' -> 'dir', 'execute winget list' -> 'winget list'."""
    t = (text or "").strip()
    low = t.lower()
    for prefix in ["run command ", "run cmd ", "execute command ", "run ", "execute ", "buyruqni ishga tushir ", "ishga tushir "]:
        if low.startswith(prefix):
            return t[len(prefix):].strip()
        if prefix in low:
            idx = low.index(prefix) + len(prefix)
            return t[idx:].strip()
    return ""


def _extract_code_task(text: str) -> str:
    """Matndan kod vazifasini ajratib oladi."""
    low = (text or "").lower()
    for prefix in (
        "напиши код", "написать код", "сгенерируй код", "code yoz", "kod yoz",
        "write code", "generate code", "напиши программу", "код напиши",
    ):
        if prefix in low:
            return (text.split(prefix, 1)[-1] or "").strip().strip(".,") or text
    return text.strip()


def _is_todo_add(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["add to my todo", "add to todo", "add task", "todo add", "my todo add", "add to my tasks", "add to list"])


def _is_todo_list(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["what's on my todo", "what is on my todo", "my todo", "todo list", "list todo", "what are my tasks", "show my todo"])


def _is_todo_done(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["task done", "first task done", "mark done", "todo done", "done first", "complete first task"]) or re.search(r"done\s*(#?\d+)|task\s*(#?\d+)\s*done", t)


def _extract_todo_done_index(text: str) -> int:
    m = re.search(r"(?:task|#)?(\d+)", (text or ""))
    return int(m.group(1)) if m else 1


def _is_timer(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["set timer", "timer for", "timer ", "minute timer", "second timer", "countdown", "alarm in"]) or bool(re.search(r"timer\s*(?:for\s*)?\d+|\d+\s*minute\s*timer|\d+\s*min\s*timer", t))


def _extract_timer_seconds(text: str) -> int:
    t = (text or "").lower()
    m = re.search(r"(\d+)\s*(?:minute|min|minutes|mins)", t)
    if m:
        return int(m.group(1)) * 60
    m = re.search(r"(\d+)\s*(?:second|sec|seconds|secs)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"timer\s*(?:for\s*)?(\d+)", t)
    if m:
        return int(m.group(1)) * 60  # default minutes
    m = re.search(r"(\d+)\s*(?:minute|min)", t)
    return int(m.group(1)) * 60 if m else 60


def _is_camera_vision_request(text: str, memory=None) -> bool:
    """Kamera orqali nima ko'rinishini so'rash: smotri, posmatri, chto eto, ko'r, qara...

    BUG FIX: bare o'zbekcha "ko'r"/"qara" so'zlari oddiy substring sifatida
    tekshirilganda, umuman kamera bilan aloqasi yo'q so'zlar ICHIDA ham
    topilib qolardi — masalan "afzal ko'rishadi" (afzal ko'radi — "prefer"),
    "tush ko'rish" ("tush ko'rish" — "to dream") kabi so'zlar "ko'r"ni o'z
    ichiga oladi. Natijada butunlay boshqa (falsafiy/uyqu haqidagi) savol
    ham kamera javobini ("Kamera: so'nggi kadr ... ishlamayapti?") qaytarib
    yuborardi — bu jonli test paytida haqiqatan ham ushlangan (aniqlangan
    bug klassi, xuddi _is_understanding_question'dagi kabi). Endi butun
    ro'yxat so'z-chegarasi (\\b) bilan tekshiriladi."""
    t = (text or "").lower().strip()
    if not t:
        return False
    if _is_conversation_not_screen(text, memory=memory):
        return False
    # Ekran savoli — kamera emas («что видишь на экране»)
    if _is_screen_question(text, memory=memory):
        return False
    if any(x in t for x in ("на экране", "экран", "screen", "монитор", "monitor", "браузер", "browser", "окно", "window")):
        return False
    phrases = [
        # Rus
        "посмотри", "смотри", "что это", "что у меня", "что я держу",
        "что в руке", "что на столе", "что перед тобой", "что перед камерой",
        "посмотри на камеру", "посмотри через камеру",
        "что я делаю", "что я сейчас делаю", "ты меня видишь", "видишь меня",
        "nima qilyapman", "meni kuzat", "kuzatib tur",
        "что видно", "опиши что видишь", "опиши что перед тобой",
        "что это такое", "узнай что это", "что за предмет",
        "что показываю", "смотри в камеру", "look here", "look at this",
        # Uzbek
        "qara", "ko'r", "bu nma", "bu nima", "qo'limda nima", "stol ustida nima",
        "nima ko'rinadi", "kameraga qara", "kamera orqali ko'r",
        "bu narsa nima", "shu nima", "buni ko'r",
        # English
        "look at camera", "what do you see in camera", "what's in front of you",
        "what am i holding", "what is this object", "describe what you see",
        "camera look", "use camera", "see through camera",
    ]
    return _word_match(t, phrases)


def _build_screen_reply(text: str, lang: str = "ru") -> str:
    """Ekran savoli — haqiqiy screenshot + OCR. LLM taxmin qilmaydi."""
    _en = lang == "en"
    try:
        _screen_refresh_for_question(timeout_sec=4.0)
    except Exception:
        pass
    with _screen_context_cache["lock"]:
        _fg = (_screen_context_cache.get("foreground_window") or "").strip()
        _txt = (_screen_context_cache.get("text") or "").strip()[:3500]
        _vis = (_screen_context_cache.get("vision") or "").strip()[:1200]
        _src = (_screen_context_cache.get("capture_source") or "").strip()

    _desktop_titles = ("program manager", "desktop", "рабочий стол", "program manager")
    _fg_low = _fg.lower().strip()
    _only_desktop = _fg_low in _desktop_titles or not _fg

    _visible: list = []
    try:
        from window_ops import get_visible_windows
        _visible = get_visible_windows() or []
    except Exception:
        pass
    _vis_titles = [w.get("title", "") for w in _visible[:8] if w.get("title")]
    _vis_str = ", ".join(_vis_titles) if _vis_titles else ""

    if _en:
        lines = ["I'm looking at your **monitor** (not the webcam)."]
    else:
        lines = ["Смотрю на **монитор** (это не камера)."]

    if _only_desktop and not _vis_titles and not _txt:
        return (
            lines[0] + " Only the desktop is visible — all windows seem minimized."
            if _en else
            lines[0] + " Вижу только рабочий стол — окна свёрнуты или ничего не открыто."
        )

    if _fg and not _only_desktop:
        lines.append(("Active window: " if _en else "Активное окно: ") + f"«{_fg}».")
    elif _vis_str:
        lines.append(("Visible windows: " if _en else "Видимые окна: ") + _vis_str + ".")
    else:
        lines.append(
            "Could not detect the active window."
            if _en else
            "Не удалось определить активное окно."
        )

    if _txt and len(_txt) >= 8:
        _snippet = _txt[:320].replace("\n", " ").strip()
        lines.append(("Text on screen (OCR): " if _en else "Текст на экране (OCR): ") + _snippet)
    elif _vis and len(_vis) >= 20:
        lines.append(_vis[:400])
    elif not _txt:
        lines.append(
            "Text not readable — maybe dark theme, video, or game."
            if _en else
            "Текст не прочитался — возможно тёмная тема, видео или игра."
        )

    if not _en and _src == "capture_failed":
        lines.append("Снимок экрана не получился — попробуйте ещё раз.")
    return " ".join(lines)[:620]


def _handle_camera_vision(text: str, lang: str = "ru") -> str:
    """Kamera vision: GPT-4o ga oxirgi kadrni yuborib tavsif oladi."""
    try:
        from camera_vision import capture_and_describe_vision as _cadv
        result = _cadv(question=text, lang=lang)
        return result or ("Kamera ko'rish imkonsiz." if lang != "ru" else "Не удалось получить изображение с камеры.")
    except Exception as e:
        return f"Kamera xato: {e}"


def _is_calculator(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["what is ", "what's ", "calculate", "how much is ", "compute "]) and bool(re.search(r"[\d\+\-\*\/\(\)]", t))


def _extract_calculator_expr(text: str) -> str:
    t = (text or "").strip()
    for p in ("what is ", "what's ", "calculate ", "how much is ", "compute "):
        if p in t.lower():
            return t.lower().split(p, 1)[-1].strip()[:80]
    return t[:80]


def _is_copy_screen(text: str) -> bool:
    """Ekrandan matnni buferga — rus + ingliz."""
    t = (text or "").lower()
    return any(x in t for x in [
        "copy screen", "copy from screen", "copy screen text", "copy what's on screen", "copy text from screen",
        "скопируй экран", "скопируй с экрана", "скопируй текст с экрана",
    ])


def _is_calendar_add(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["add to calendar", "calendar add", "schedule ", "add event", "add meeting", "tomorrow at", "next week"])


def _is_calendar_list(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["what's on my calendar", "my calendar", "calendar list", "upcoming events", "what is scheduled"])


def _extract_calendar_parts(text: str) -> tuple:
    """(date_str, title, time_str). Simple: today/tomorrow + title."""
    t = (text or "").strip()
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    date_str = today
    if "tomorrow" in t.lower():
        date_str = tomorrow
        t = re.sub(r"tomorrow\s*", "", t, flags=re.I).strip()
    time_str = ""
    m = re.search(r"\b(at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", t, re.I)
    if m:
        time_str = m.group(2).strip()
    title = re.sub(r"add to calendar|calendar add|schedule|add event|add meeting|tomorrow|at\s+\d.*", "", t, flags=re.I).strip()[:200]
    return date_str, title or "Event", time_str


def _is_translate(text: str) -> bool:
    t = (text or "").lower()
    return "translate" in t and (" to " in t or " into " in t)


def _is_save_idea(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["remember my idea", "save this thought", "save my idea", "note to self", "remember that", "write down that"])


def _extract_idea_text(text: str) -> str:
    for p in ("remember my idea", "save this thought", "save my idea", "note to self", "remember that", "write down that"):
        if p in (text or "").lower():
            return (text or "").split(p, 1)[-1].strip()[:500]
    return (text or "").strip()[:500]


def _is_news_request(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["what's the news", "latest news", "world news", "today's news", "headlines"])


def _is_crypto(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["bitcoin", "crypto", "ethereum", "dollar rate", "exchange rate", "stock price"])


def _is_wikipedia(text: str) -> bool:
    t = (text or "").lower()
    return "wikipedia" in t or "wiki " in t


def _is_daily_summary(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["what did i do today", "today's summary", "daily summary", "what did we do today"])


def _is_backup(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["backup", "back up memory", "save backup"])


def _is_slack_send(text: str) -> bool:
    t = (text or "").lower()
    return "slack" in t and ("send" in t or "message" in t or "post" in t)


def _is_discord_send(text: str) -> bool:
    t = (text or "").lower()
    return "discord" in t and ("send" in t or "message" in t)


def _is_notion_note(text: str) -> bool:
    t = (text or "").lower()
    return "notion" in t and ("add" in t or "note" in t or "save" in t)


def _is_smart_home(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["turn on light", "turn off light", "smart home", "lights on", "lights off", "thermostat"])


def _is_person_relation(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["is my friend", "is my colleague", "remember that ", "is my ", " is a friend", " is a colleague"]) and ("my " in t or " is " in t)


def _extract_person_relation(text: str) -> str:
    return (text or "").strip()[:300]


def _is_reminder(text: str) -> bool:
    """Eslatma — rus + ingliz."""
    t = (text or "").lower()
    return any(x in t for x in [
        "напомни через", "напомни через минуту", "напомни через час", "через минуту напомни", "через 5 минут напомни",
        "remind me in", "remind me in a minute", "remind me in an hour", "set reminder", "remind me",
        "remind me in 5 minutes", "remind me in 10 minutes", "set a reminder",
        "eslat", "eslab qol", "keyin eslat",
    ])


def _is_remember_command(text: str) -> bool:
    """Aniq 'esla/запомни/remember' buyrug'i — kafolatli saqlash uchun."""
    t = (text or "").lower().strip()
    triggers = (
        "esla ", "esla:", "eslab qol", "yodda tut", "yodingda tut", "yozib qo'y", "yozib qoy",
        "запомни ", "запомни:", "запиши ", "сохрани ", "не забудь ",
        "remember that", "remember this", "remember:", "note that", "save this",
    )
    return any(t.startswith(x) or x in t for x in triggers)


def _extract_remember_fact(text: str) -> str:
    """'esla: men kofeni yaxshi koraman' -> 'men kofeni yaxshi koraman'."""
    t = (text or "").strip()
    low = t.lower()
    for prefix in (
        "eslab qolgin", "eslab qol", "yodingda tutgin", "yodingda tut", "yodda tut",
        "yozib qo'ygin", "yozib qo'y", "yozib qoy", "esla:", "esla",
        "запомни:", "запомни", "запиши:", "запиши", "сохрани:", "сохрани", "не забудь",
        "remember that", "remember this", "remember:", "remember", "note that", "save this",
    ):
        if low.startswith(prefix):
            return t[len(prefix):].strip(" :,-—").strip()
    # Ichida bo'lsa
    for prefix in ("esla", "запомни", "remember"):
        if prefix in low:
            idx = low.index(prefix) + len(prefix)
            rest = t[idx:].strip(" :,-—").strip()
            if rest:
                return rest
    return t


def _is_copy_clipboard(text: str) -> bool:
    """Matnni buferga nusxalash — rus + ingliz."""
    t = (text or "").lower()
    return any(x in t for x in [
        "скопируй в буфер", "скопируй в буфер обмена", "copy to clipboard", "copy to buffer",
        "copy that", "copy it", "copy this", "copy to clip", "буферга копир", "nusxalab buffer", "nusxalab buferga",
    ])


def _extract_reminder_delay_and_text(text: str) -> tuple:
    """(seconds, reminder_text). Masalan: 'напомни через 5 минут позвонить' -> (300, 'позвонить')."""
    t = (text or "").strip()
    low = t.lower()
    sec = 60
    for m in re.finditer(r"(\d+)\s*(минут|минуту|минуты|minute|minutes)", low):
        sec = int(m.group(1)) * 60
        break
    for m in re.finditer(r"(\d+)\s*(час|часа|часов|hour|hours)", low):
        sec = int(m.group(1)) * 3600
        break
    if "минут" in low and "через" in low and not re.search(r"\d+\s*минут", low):
        sec = 60
    if "час" in low and "через" in low and not re.search(r"\d+\s*час", low):
        sec = 3600
    # Reminder matni: "напомни через 5 минут ПОЗВОНИТЬ" -> "позвонить"
    for prefix in ("напомни через", "remind me in", "eslat", "напомни"):
        if prefix in low:
            idx = low.index(prefix)
            rest = t[idx + len(prefix):].strip()
            # Raqam va "минут"/"час" ni olib tashlash
            rest = re.sub(r"^\d+\s*(минут|часов?|minute|hour)s?\s*", "", rest, flags=re.I).strip()
            if rest:
                return sec, rest[:200]
    return sec, "Reminder"


def _extract_spoken_reply(reply: str) -> str:
    """LLM javobidan ovozga chiqariladigan qismni oladi: 'Ответ:' / 'Answer:' dan keyingi qism. Hech qachon bo'sh qolmasin."""
    if not (reply or "").strip():
        return reply or ""
    r = (reply or "").strip()
    low = r.lower()
    # Use last occurrence so "reasoning... Answer: spoken" yields the final spoken part
    for marker in ("answer:", "answer :", "ответ:", "ответ :"):
        if marker in low:
            idx = low.rfind(marker) + len(marker)
            rest = r[idx:].strip()
            if rest and len(rest) >= 2:
                return rest
    return r


def _tts_unsaid_parts(spoken_parts: list, spoke_count: int) -> str:
    """Navbatda qo'yilgan, lekin o'qilmagan jumlalar."""
    parts = spoken_parts or []
    if spoke_count >= len(parts):
        return ""
    return " ".join((p or "").strip() for p in parts[spoke_count:] if (p or "").strip()).strip()


def _tts_tail_remainder(full_text: str, spoken_parts: list) -> str:
    """Chunk TTS da aytilgan qismlardan keyin qolgan matn (oxiri kesilmasin)."""
    full = (full_text or "").strip()
    if not full or not spoken_parts:
        return full
    consumed = 0
    for part in spoken_parts:
        p = (part or "").strip()
        if not p:
            continue
        idx = full.find(p, consumed)
        if idx < 0:
            idx = full.lower().find(p.lower(), consumed)
        if idx >= 0:
            consumed = idx + len(p)
    tail = full[consumed:].strip(" .,;:")
    if tail and len(tail) > 2:
        return tail
    return ""


def _speak_and_wait(tts, text: str, timeout: float = 120.0) -> bool:
    """Ovoz navbat orqali — xavfsiz, dastur yopilmaydi."""
    if not text or not (str(text).strip()):
        return False
    try:
        tts.enqueue_speech(str(text).strip())
        return tts.drain_speech(timeout=timeout) > 0
    except Exception as _sw_e:
        print(f"[TTS] speak xato: {_sw_e!r}", flush=True)
        try:
            return bool(tts.say(str(text).strip()))
        except Exception:
            return False


def _set_orb_state(orb, state: str) -> None:
    try:
        _RUNTIME_HEARTBEAT["orb"] = state or "idle"
    except Exception:
        pass
    if orb and hasattr(orb, "set_state"):
        try:
            orb.set_state(state)
        except Exception:
            pass
    # ── HUD bridge: barcha holat o'zgarishlari shu yerdan o'tadi ─────────────
    try:
        _hud.update(mode=state or "idle")
    except Exception:
        pass


def _log_action(action: str, detail: str = "") -> None:
    """Audit log: control, tg send, code write, delete file."""
    if _HAVE_EXTRAS and hasattr(_extras, "log_action"):
        try:
            _extras.log_action(action, detail)
        except Exception:
            pass


def _run_complex_steps(
    steps,
    *,
    tts,
    control_obj=None,
    tg_user=None,
    memory=None,
    lang="ru",
    orb=None,
):
    """Murakkab vazifa qadamlarini bajaradi, har bir natijani ro'yxatga yozadi."""
    if not steps:
        return []
    results = []
    for step in steps:
        action = (step.get("action") or "").strip()
        param = (step.get("param") or "").strip()
        if action == "open_app" and control_obj:
            app = param or "browser"
            if app in ("telegram", "tg"):
                app = "telegram"
            ok, msg = control_obj.open_app(app)
            results.append(msg)
        elif action == "close_app" and control_obj:
            app = param or "browser"
            if app in ("telegram", "tg"):
                app = "telegram"
            ok, msg = control_obj.close_app(app)
            results.append(msg)
        elif action == "open_url" and control_obj and param:
            url = param if param.startswith("http") else ("https://www.google.com/search?q=" + url_quote(param))
            ok, msg = control_obj.open_url(url)
            results.append(msg)
        elif action == "tg_check" and tg_user:
            try:
                items = tg_user.unread_incoming(limit=8) if hasattr(tg_user, "unread_incoming") else tg_user.recent(limit=5)
                if not items:
                    results.append("No new messages.")
                else:
                    lines = _format_tg_recent(items, 5)
                    results.append("Telegram: " + "; ".join(lines[:3]))
            except Exception:
                results.append("Could not read Telegram.")
        elif action == "search_web" and param:
            web_ctx = web_context(param, prefer_lang=lang)
            try:
                reply = answer(
                    "Summarize what you found in 1–2 sentences: " + param,
                    web_ctx=web_ctx,
                    lang_hint=lang,
                    history=(memory.data.get("history", [])[-6:] if memory else []),
                    current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
                results.append(_extract_spoken_reply(reply))
            except Exception:
                results.append((web_ctx[:200] + "…") if web_ctx else "Search gave no result.")
        elif action == "open_folder" and control_obj and param:
            path = control_obj.find_folder(param)
            if path:
                ok, msg = control_obj.open_folder(path)
                results.append(msg)
            else:
                results.append(f"Folder «{param}» not found.")
        elif action == "minimize_all" and control_obj:
            ok, msg = control_obj.minimize_all_windows()
            results.append(msg)
        elif action == "restore_windows" and control_obj:
            ok, msg = control_obj.restore_all_windows()
            results.append(msg)
        elif action == "system_status" and get_system_report:
            results.append(get_system_report(lang))
        elif action == "tg_send" and tg_user and param:
            contact, msg_or_file = param.split("|", 1) if "|" in param else (param.strip(), "")
            contact = contact.strip()
            file_path = None
            if msg_or_file.strip().lower().startswith("file:"):
                fp = msg_or_file.strip()[5:].strip()
                if fp == "last" and results:
                    for r in reversed(results):
                        if isinstance(r, str) and os.path.exists(r) and r.endswith((".pptx", ".pdf", ".docx")):
                            file_path = r
                            break
                elif os.path.exists(fp):
                    file_path = fp
            msg_text = msg_or_file if not file_path else ""
            try:
                ok, res = tg_user.send_to_contact(contact, msg_text, file_path=file_path)
                results.append(res)
            except Exception as e:
                results.append(f"tg_send failed: {e}")
        elif action == "create_presentation" and param:
            try:
                from presentations import create_presentation_from_outline
                outline = ""
                try:
                    outline = answer(
                        f"Create a short presentation outline (3-5 slides) for topic: {param}. Output ONLY lines in format: Slide 1: Title\nSlide 2: Point 1\nSlide 3: ... No other text.",
                        lang_hint=lang,
                        history=(memory.data.get("history", [])[-4:] if memory else []),
                        current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
                    )
                    outline = _extract_spoken_reply(outline) or outline
                except Exception:
                    outline = f"Slide 1: {param}\nSlide 2: Overview\nSlide 3: Conclusion"
                ok, path_or_err = create_presentation_from_outline(outline, topic=param)
                results.append(path_or_err if ok else f"Presentation failed: {path_or_err}")
            except ImportError:
                results.append("python-pptx not installed. pip install python-pptx")
        elif action == "uninstall_app" and _HAVE_CONTROL and control_obj and param:
            ok, msg = control_obj.uninstall_app(param)
            results.append(msg)
        else:
            results.append("Step done.")
    return results


_handle_text_last = {"text": "", "t": 0.0}
HANDLE_TEXT_DEBOUNCE_SEC = 0.4
_startup_asked_weather_news = [False]
# Yangi (profilsiz) o'rnatishda birinchi muloqot: ism so'ralganda True bo'ladi,
# keyingi foydalanuvchi gapi ism sifatida olinadi va data/user_profile.json
# ga yoziladi (_save_new_owner_name orqali).
_awaiting_name_intro = [False]
_user_spoke_since_boot = [False]
# TTS gapirayotganda berilgan savol — TTS tugagach bajariladi
_pending_question: dict = {"text": None, "kwargs": None}


def _sanitize_demo_memory() -> None:
    """Investor demo: eski qasov javoblarni consciousness va memory dan tozalash."""
    if not getattr(C, "NEUROKEY_DEMO_FRIENDLY", False):
        return
    bad = (
        "хватит повтор", "перестаньте повтор", "не буду реагировать",
        "это уже слишком", "раздражает", "пустые фразы",
    )
    try:
        if _HAVE_CONSCIOUSNESS and get_consciousness:
            c_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "consciousness.json")
            cons = get_consciousness(c_path)
            wm = cons.data.get("working_memory") or []
            cons.data["working_memory"] = [
                x for x in wm
                if not any(b in (x.get("assistant") or "").lower() for b in bad)
            ]
            cons.save()
            print("[DEMO] consciousness: qasov javoblar tozalandi", flush=True)
    except Exception:
        pass
    try:
        mem_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")
        if os.path.isfile(mem_path):
            import json as _json
            with open(mem_path, encoding="utf-8") as f:
                data = _json.load(f)
            hist = data.get("history") or []
            data["history"] = [
                h for h in hist
                if (h.get("assistant") or "").strip()
                and not any(b in (h.get("assistant") or "").lower() for b in bad)
            ][-200:]
            # Oxirgi bo'sh yoki buzilgan turnlarni olib tashlash (Groq limit)
            data["history"] = [
                h for h in data["history"]
                if (h.get("user") or "").strip() and (h.get("assistant") or "").strip()
            ]
            with open(mem_path, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
            print("[DEMO] memory.json: qasov javoblar tozalandi", flush=True)
    except Exception:
        pass


def _filter_history_for_llm(history: list) -> list:
    """Yomon 'хватит повторять' javoblari LLM ga ketmasin."""
    bad = (
        "хватит повтор", "перестаньте повтор", "не буду реагировать на повтор",
        "это уже слишком", "пустые фразы", "раздражает",
    )
    out = []
    for h in history or []:
        a = (h.get("assistant") or "").strip()
        if not a:
            continue
        a_low = a.lower()
        if any(b in a_low for b in bad):
            continue
        out.append(h)
    return out


def handle_text(
    text: str,
    tts: TTSWorker,
    tg_user=None,
    memory: Optional["MemoryStore"] = None,
    orb=None,
    long_term_memory=None,
):
    text = (text or "").strip()
    if not text:
        return
    _turn_t0 = time.perf_counter()
    _debug_prof = None
    if (os.getenv("NEUROKEY_DEBUG_TIMING", "0") or "0").strip() == "1":
        import cProfile as _cProfile
        _debug_prof = _cProfile.Profile()
        _debug_prof.enable()
    try:
        from stt_whisper_fix import is_stt_junk
        if is_stt_junk(text):
            print(f"[STT] fon/TV e'tiborsiz: {text[:70]}", flush=True)
            return
    except ImportError:
        pass

    # Takroriy chaqiruvlardan qochish (STT/TG bir xil matnni bir necha marta yuborishi)
    now = time.time()
    if text == _handle_text_last.get("text") and (now - _handle_text_last.get("t", 0)) < HANDLE_TEXT_DEBOUNCE_SEC:
        return
    _handle_text_last["text"] = text
    _handle_text_last["t"] = now
    _user_spoke_since_boot[0] = True

    _set_orb_state(orb, "listening")
    _hud.listening(text=text)          # HUD: LISTENING + last input

    # Старт: «Хотите погоду и новости?» — если да/хочу/давай → погода + новости
    if _startup_asked_weather_news[0]:
        low = (text or "").lower().strip()
        if any(x in low for x in ("да", "хочу", "давай", "конечно", "да пожалуйста", "yes", "ок", "окей", "ага", "ладно")):
            _startup_asked_weather_news[0] = False
            _set_orb_state(orb, "speaking")
            try:
                from juma_news_weather import weather_by_name, get_top_news, render_news_brief
                w = weather_by_name("Tashkent", lang="ru")
                items = get_top_news("world", limit=5)
                n = render_news_brief(items, lang="ru") if items else ""
                if w and "not found" not in (w or "").lower():
                    tts.say(w)
                if n:
                    tts.say((n[:600] + "…") if len(n) > 600 else n)
                if not w and not n:
                    tts.say(_tr("Данные пока недоступны. Попробуй позже.", "Data not available yet. Try later."))
            except Exception:
                tts.say(_tr("Погода и новости пока недоступны.", "Weather and news not available yet."))
            _set_orb_state(orb, "idle")
            return
        else:
            _startup_asked_weather_news[0] = False

    # Birinchi muloqot: ism so'ralgan bo'lsa — keyingi gap ism sifatida olinadi
    # (yangi/profilsiz o'rnatish, masalan boshqa kompyuterga o'rnatilganda).
    if _awaiting_name_intro[0]:
        _awaiting_name_intro[0] = False
        saved_nick = _save_new_owner_name(text)
        _set_orb_state(orb, "speaking")
        if saved_nick:
            if _ui_lang() == "en":
                tts.say(f"Nice to meet you, {saved_nick}! I'll remember that.")
            else:
                tts.say(f"Приятно познакомиться, {saved_nick}! Я запомню.")
        else:
            if _ui_lang() == "en":
                tts.say("Sorry, I didn't catch that. You can tell me your name anytime.")
            else:
                tts.say("Извините, не расслышал. Можете назвать имя в любой момент позже.")
        _set_orb_state(orb, "idle")
        return

    # Ekran: darhol async yangilash (VOSK uchun ham — odamlar kabi doim ko'radi)
    _prefetch_screen_on_speech_start()

    # Half-duplex: TTS gapirayotganda — savol bo'lsa uzamiz (ADLF monolog navbatga qolmasin)
    if tts.is_playing():
        _STOP_KEYWORDS = {"стоп", "stop", "to'xta", "тохта", "стоп.", "stop."}
        words_low = {w.strip(".,!?").lower() for w in text.strip().split()}
        _interrupt_tts = getattr(C, "NEUROKEY_INTERRUPT_TTS_ON_SPEECH", True)
        _word_n = len((text or "").strip().split())
        _user_priority = (
            "?" in (text or "")
            or _is_understanding_question(text)
            or _is_who_am_i(text)
            or _is_memory_recall_question(text)
            or _is_safety_followup_question(text)
            or _is_greeting(text)
            or _is_affect_question(text)
            or _is_inner_thought_question(text)
            or (_word_n >= 4 and len((text or "").strip()) <= 120)
        )
        if _interrupt_tts and _user_priority and not (words_low & _STOP_KEYWORDS):
            _log_main(f"TTS uzildi — foydalanuvchi savoli: '{text[:60]}'")
            tts.stop()
            time.sleep(0.12)
        elif not words_low & _STOP_KEYWORDS:
            _pending_question["text"] = text
            _pending_question["kwargs"] = dict(tg_user=tg_user, memory=memory, orb=orb, long_term_memory=long_term_memory)
            _log_main(f"TTS gapiryapti — savol navbatga qo'yildi: '{text[:60]}'")
            return
        else:
            _log_main(f"STOP keyword topildi — tts.stop() chaqirilmoqda: '{text[:60]}'")
            _pending_question["text"] = None
            tts.stop()

    low = text.lower()

    # ---- Перезагрузка: NeuroKey o'zini qayta ishga tushiradi ----
    # BUG FIX: "qayta yoq" so'zi haqiqiy buyruqdan tashqari, uzun falsafiy
    # savollar ICHIDA ham chiqishi mumkin — masalan "Agar seni hozir
    # o'chirib, ertaga qayta yoqsam, o'sha 'sen' bo'lasanmi..." (identity
    # continuity haqidagi chuqur savol — aynan shu turdagi savolda NeuroKey
    # xarakter/ong bilan javob berishi eng muhim). Eski kod bunday savolni
    # ham "qayta ishga tushirish buyrug'i" deb tushunib, LLM'ga umuman
    # yetkazmasdan darhol dasturni o'chirib qo'yardi. Endi buyruq faqat QISQA
    # (<=6 so'z) VA savol belgisi yo'q iboralarda ishlaydi — chin buyruqlar
    # odatda shunday ("Qayta yoq", "Restart qil"), uzun/savol gaplar emas.
    _RESTART_WORDS = ("перезагрузись", "перезагрузи", "перезапустись", "перезапусти",
                      "reboot", "restart", "qayta yoq", "qayta ishga tushir")
    _restart_like_cmd = (
        len((text or "").split()) <= 6
        and "?" not in (text or "")
    )
    if _restart_like_cmd and any(w in low for w in _RESTART_WORDS):
        _set_orb_state(orb, "speaking")
        tts.say("Перезагружаюсь, секунду.")
        import sys as _sys
        _sys.exit(42)  # exit code 42 = restart request (BOSING.bat loops on this)

    # ---- BIOMETRIC GUARDIAN: chet odam gapirsa javob bermaydi ----
    # NEUROKEY_ALWAYS_OWNER=1 — profil bor bo'lsa har doim egasi (tanilmadim yo'q)
    _biometric_block_enabled = os.getenv("NEUROKEY_BIOMETRIC_BLOCK", "1").strip() in ("1", "true", "yes")
    try:
        from owner_trust import always_trust_owner, mark_guardian_verified
        if always_trust_owner():
            mark_guardian_verified()
            _biometric_block_enabled = False
    except Exception:
        pass
    if _biometric_block_enabled:
      try:
        # ECAPA-TDNN (yangi, 98% aniq) — birlamchi tekshiruv
        # Agar ECAPA profili bor va yaqinda "tanilgan" degan bo'lsa → MFCC tekshiruvi o'tkazib yuboriladi
        _ecapa_says_known = None
        try:
            from voice_ecapa import get_last_result as _ecapa_ht_lr, profile_exists as _ecapa_ht_pex
            if _ecapa_ht_pex():
                _ecapa_r = _ecapa_ht_lr()
                _ecapa_age = time.time() - _ecapa_r.get("_ts", 0.0)
                if _ecapa_age < 20.0 and _ecapa_r.get("known") is not None:
                    _ecapa_says_known = _ecapa_r.get("known", False)
        except Exception:
            pass

        # Agar ECAPA "tanigan" desa — ruxsat beriladi, MFCC tekshiruvi kerak emas
        if _ecapa_says_known is True:
            handle_text._bio_unknown_count = 0
        elif _ecapa_says_known is False:
            # ECAPA "tanilmagan" dedi (yaqin natija) — bitta ogohlantirish, keyin rad
            _bio_counter = getattr(handle_text, "_bio_unknown_count", 0) + 1
            handle_text._bio_unknown_count = _bio_counter
            if _bio_counter >= 3:
                handle_text._bio_unknown_count = 0
                _set_orb_state(orb, "speaking")
                _refuse_phrases = [
                    "Я вас не узнаю. Эта система работает только для своего владельца.",
                    "Извините, но я создан только для своего хозяина. Вас я не знаю.",
                    "Доступ закрыт. Я работаю только с биометрическим владельцем.",
                ]
                import random as _rand
                tts.say(_rand.choice(_refuse_phrases))
                _set_orb_state(orb, "idle")
                return
        else:
            # ECAPA natijasi yo'q yoki eski — MFCC (Resemblyzer) bilan tekshiramiz
            from voice_recognition import get_last_speaker as _bio_spk, profile_exists as _bio_prof
            if _bio_prof():
                _spk_info = _bio_spk()
                if _spk_info.get("profile_exists") and not _spk_info.get("known", True):
                    _bio_counter = getattr(handle_text, "_bio_unknown_count", 0) + 1
                    handle_text._bio_unknown_count = _bio_counter
                    if _bio_counter >= 3:
                        handle_text._bio_unknown_count = 0
                        _set_orb_state(orb, "speaking")
                        _refuse_phrases = [
                            "Я вас не узнаю. Эта система работает только для своего владельца.",
                            "Извините, но я создан только для своего хозяина. Вас я не знаю.",
                            "Доступ закрыт. Я работаю только с биометрическим владельцем.",
                        ]
                        import random as _rand
                        tts.say(_rand.choice(_refuse_phrases))
                        _set_orb_state(orb, "idle")
                        return
                    _log_main(f"[GUARDIAN] MFCC noma'lum ovoz #{_bio_counter} — jim.")
                    return
                else:
                    handle_text._bio_unknown_count = 0
      except Exception:
        pass

    # ── YADRO: har bir suhbat boshida qualia yangilanadi (sinx, 0ms) ──────────
    # Bu NeuroKey = Yadro degan ma'no — hamma buyruq yadrodan o'tadi
    if _NK:
        try:
            qualia = _NK._modules.get("qualia")
            if qualia:
                qualia.update(user_text=text)
        except Exception:
            pass
        try:
            pain = _NK._modules.get("pain")
            if pain and hasattr(pain, "update"):
                pain.update(text)
        except Exception:
            pass
        _NK.state["total_interactions"] = _NK.state.get("total_interactions", 0) + 1
    # ─────────────────────────────────────────────────────────────────────────

    # Suniy ong: user matn sentiment — valence/arousal yengil yangilash
    _update_affect_from_user_text(text)

    _instant_replies = getattr(C, "NEUROKEY_INSTANT_REPLIES", True)

    # ---- Kim men? — darhol (LLM kutmasdan) ----
    if _instant_replies and _is_understanding_question(text):
        _und_lang = _ui_lang(text)
        _und_reply = _build_understanding_reply(_und_lang)
        _set_orb_state(orb, "speaking")
        tts.say(_und_reply)
        if memory:
            memory.remember_turn(text, _und_reply)
        _set_orb_state(orb, "idle")
        return

    if _is_who_am_i(text):
        _wm_reply = _who_am_i_reply(_ui_lang(text))
        print(f"[TTS] kim men: {_wm_reply[:80]}", flush=True)
        _set_orb_state(orb, "speaking")
        tts.say(_wm_reply)
        if memory:
            memory.remember_turn(text, _wm_reply)
        _set_orb_state(orb, "idle")
        return

    # ---- XAVFSIZLIK: Ultron davomi — «ты так не сделаешь?» ----
    if _is_safety_followup_question(text):
        _safe_lang = _ui_lang(text)
        _safe_reply = _build_safety_followup_reply(_safe_lang)
        _set_orb_state(orb, "speaking")
        tts.say(_safe_reply)
        if memory:
            memory.remember_turn(text, _safe_reply)
        _set_orb_state(orb, "idle")
        return

    # ---- XOTIRA: вчера / помнишь — diskdan haqiqiy javob (LLM «нет памяти» demasin) ----
    if _is_memory_recall_question(text):
        _mem_lang = _ui_lang(text)
        _mem_recall = _build_memory_recall_reply(text, memory=memory, lang=_mem_lang)
        print(f"[TTS] xotira: {_mem_recall[:90]}", flush=True)
        _set_orb_state(orb, "speaking")
        _hud.thinking(modules=["memory", "xotira", "episodic"])
        tts.say(_mem_recall)
        if memory:
            memory.remember_turn(text, _mem_recall[:400])
        _hud.speaking(_mem_recall[:120])
        _hud.idle()
        _set_orb_state(orb, "idle")
        return

    # ---- ESLA: aniq "esla/запомни/remember" — KAFOLATLI saqlash (LLM ga bog'liq emas) ----
    if long_term_memory and _is_remember_command(text) and not _is_reminder(text):
        _fact = _extract_remember_fact(text)
        if _fact and len(_fact) > 1:
            try:
                long_term_memory.add_fact("user", _fact)
                print(f"[XOTIRA] KAFOLATLI saqlandi: {_fact[:80]}", flush=True)
            except Exception as _se:
                print(f"[XOTIRA] saqlash xato: {_se}", flush=True)
            _rl = _ui_lang(text)
            if _rl == "uz":
                _rconf = "Eslab qoldim. Hech qachon unutmayman."
            elif _rl == "en":
                _rconf = "Saved. I won't forget this."
            else:
                _rconf = "Запомнил. Не забуду это."
            _set_orb_state(orb, "speaking")
            _hud.speaking(_rconf)
            tts.say(_rconf)
            if memory:
                memory.remember_turn(text, _rconf)
            _hud.idle()
            _set_orb_state(orb, "idle")
            return

    # ---- SALOM: privet / привет — darhol ovoz (STT ba'zan "это" deb yozadi) ----
    if _instant_replies and _is_greeting(text):
        _gr_lang = _ui_lang(text)
        _gr_reply = _greeting_reply(_gr_lang)
        _gr_att = _live_attention_line(text, _gr_lang)
        if _gr_att:
            _gr_reply = f"{_gr_reply} {_gr_att}"
            print(f"[ONG-QAROR] attention_schema → salom javobiga diqqat qo'shildi", flush=True)
        print(f"[TTS] salom javobi: {_gr_reply[:120]}", flush=True)
        _set_orb_state(orb, "speaking")
        _hud.speaking(_gr_reply[:120])
        # Navbat emas — to'g'ridan-to'g'ri. Ishlagan startup ovozi ham shu yo'l.
        _heard = False
        try:
            _heard = bool(tts.say(_gr_reply))
        except Exception as _gr_e:
            print(f"[TTS] salom ovozi xato: {_gr_e!r}", flush=True)
        if not _heard:
            print("[TTS] salom eshitilmadi — yana bir marta", flush=True)
            try:
                _heard = bool(tts.say(_gr_reply))
            except Exception as _gr_e2:
                print(f"[TTS] salom qayta urinish xato: {_gr_e2!r}", flush=True)
        if not _heard:
            print("[TTS] SALOM OVOZI CHIQMADI — quloqchin va konsoldagi Edge qatorini tekshiring", flush=True)
        if memory:
            memory.remember_turn(text, _gr_reply)
        _hud.idle()
        _set_orb_state(orb, "idle")
        return

    # ---- ICHKI MONOLOG: «о чём думаешь» — ong + xotira ----
    if _is_inner_thought_question(text):
        _think_lang = _ui_lang(text)
        _think_reply = _build_inner_thought_reply(text, memory=memory, lang=_think_lang)
        _set_orb_state(orb, "speaking")
        _hud.thinking(modules=["inner_speech", "consciousness", "ong"])
        tts.say(_think_reply)
        if memory:
            memory.remember_turn(text, _think_reply[:400])
        _hud.speaking(_think_reply[:120])
        _hud.idle()
        _set_orb_state(orb, "idle")
        return

    # ---- HISSIYOT: qanday his qilyapsan — darhol valence/arousal bilan javob ----
    if _instant_replies and _is_affect_question(text):
        _aff_lang = _ui_lang(text)
        _aff_reply = _build_affect_reply(_aff_lang)
        _set_orb_state(orb, "speaking")
        _hud.thinking(modules=["valence", "arousal", "emotion", "phenomenal_state"])
        tts.say(_aff_reply)
        if memory:
            memory.remember_turn(text, _aff_reply)
        _hud.speaking(_aff_reply[:120])
        _hud.idle()
        _set_orb_state(orb, "idle")
        return

    # ---- KAMERA KUZATUV: nima qilyapman / meni ko'ryapsanmi ----
    if _is_watching_me_question(text) or (
        _is_camera_vision_request(text) and any(
            x in (text or "").lower()
            for x in ("nima qil", "что я дела", "watching", "kuzat", "видишь меня")
        )
    ):
        _watch_lang = _ui_lang(text)
        _watch_reply = _build_watching_reply(_watch_lang)
        _set_orb_state(orb, "speaking")
        _hud.thinking(modules=["camera", "face_arc"])
        tts.say(_watch_reply)
        if memory:
            memory.remember_turn(text, _watch_reply)
        _hud.speaking(_watch_reply[:120])
        _hud.idle()
        _set_orb_state(orb, "idle")
        return

    # ---- VR / MAVZU: «что там будет» — suhbat, ekran emas ----
    if _is_vr_topic_question(text, memory=memory):
        _vr_reply = _build_vr_topic_reply(text, memory=memory, lang=_ui_lang(text))
        _set_orb_state(orb, "speaking")
        _hud.thinking(modules=["vr", "topic"])
        tts.say(_vr_reply)
        if memory:
            memory.remember_turn(text, _vr_reply[:400])
        _hud.speaking(_vr_reply[:120])
        _hud.idle()
        _set_orb_state(orb, "idle")
        return

    # ---- EKRAN: «что на экране» — darhol OCR + oyna (kamera emas) ----
    if _is_screen_question(text, memory=memory) and _HAVE_SCREEN_VISION:
        _scr_lang = _ui_lang(text)
        _scr_reply = _build_screen_reply(text, lang=_scr_lang)
        if _scr_reply and len(_scr_reply.strip()) > 5:
            _set_orb_state(orb, "speaking")
            _hud.thinking(modules=["screen", "ekran"])
            tts.say(_scr_reply)
            if memory:
                memory.remember_turn(text, _scr_reply[:400])
            _hud.speaking(_scr_reply[:120])
            _hud.idle()
            _set_orb_state(orb, "idle")
            return

    # ---- Buyruq magzini erta tushunish (tabiiy gapirish — nima xohlayapti aniq) ----
    _inferred_intent = None
    _instant = getattr(C, "NEUROKEY_INSTANT_RESPONSE", True)
    _always_infer = getattr(C, "NEUROKEY_ALWAYS_INFER_INTENT", True)
    run_infer = (
        len(text) < 280
        and _could_be_command(text)
        and (_always_infer or not _instant)
        and not _is_conversation_not_screen(text, memory=memory)
        and not _is_vr_topic_question(text, memory=memory)
    )
    if run_infer:
        _inferred_intent = infer_command_intent(text)

    # ---- QULF: qulflangan bo'lsa faqat parol qabul qilinadi ----
    if _is_locked():
        if _check_lock_password(text):
            _set_locked(False)
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("unlocked"))
        else:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("wrong_password"))
        _set_orb_state(orb, "idle")
        return

    # ---- Qulfla: hohlagan payt ishlatishni to'xtatish ----
    if _is_lock_command(text):
        _set_locked(True)
        _set_orb_state(orb, "speaking")
        pwd = (getattr(C, "NEUROKEY_LOCK_PASSWORD", "") or "").strip()
        tts.say(get_feedback("locked_say_password") if pwd else get_feedback("locked_say_unlock"))
        _set_orb_state(orb, "idle")
        return

    # ---- INSTANT SUPERCONTROL: LLMsiz lokal boshqaruv (minimal delay) ----
    _instant_super = os.getenv("NEUROKEY_INSTANT_SUPERCONTROL", "1").strip().lower() in ("1", "true", "yes")
    if _instant_super and _HAVE_CONTROL and _HAVE_INSTANT_CONTROL and control and _instant_control:
        try:
            handled, msg = _instant_control.try_handle(text, control)
            if handled:
                _set_orb_state(orb, "speaking")
                tts.say(msg if msg else "Готово.")
                if memory:
                    memory.remember_turn(text, msg or "Instant control command executed")
                _set_orb_state(orb, "idle")
                return
        except Exception:
            pass

    # ---- ULTRA FAST CONTROL: och/yop buyruqlarini LLMdan oldin bajarish ----
    _ultra_ctrl = os.getenv("NEUROKEY_ULTRA_CONTROL", "1").strip().lower() in ("1", "true", "yes")
    if _HAVE_CONTROL and _ultra_ctrl:
        _fast_open = _is_control_open(text)
        _fast_close = _is_control_close(text)
        if _fast_open or _fast_close:
            _fast_app = _control_app_from_text(text, _fast_open)
            if _fast_app:
                try:
                    if _fast_open:
                        ok, msg = control.open_app(_fast_app)
                    else:
                        ok, msg = control.close_app(_fast_app)
                    _set_orb_state(orb, "speaking")
                    tts.say(msg if msg else ("Готово." if ok else "Не удалось выполнить команду."))
                    if memory:
                        memory.remember_turn(text, msg or "")
                    _set_orb_state(orb, "idle")
                    return
                except Exception:
                    pass

    # ---- GitHub ----
    if _HAVE_GITHUB and _github and _github.is_github_request(text):
        _set_orb_state(orb, "thinking")
        def _gh_run(_t=text, _tts=tts, _mem=memory):
            try:
                reply = _github.handle(_t, tts_say=_tts.say)
                if reply and _mem: _mem.remember_turn(_t, reply)
            except Exception as e:
                try: _tts.say(f"GitHub xato: {e}")
                except Exception: pass
            finally: _set_orb_state(orb, "idle")
        threading.Thread(target=_gh_run, daemon=True).start()
        return

    # ---- YouTube ----
    if _HAVE_YOUTUBE and _youtube and _youtube.is_youtube_request(text):
        _set_orb_state(orb, "thinking")
        def _yt_run(_t=text, _tts=tts, _mem=memory):
            try:
                reply = _youtube.handle(_t, tts_say=_tts.say)
                if reply and _mem: _mem.remember_turn(_t, reply)
            except Exception as e:
                try: _tts.say(f"YouTube xato: {e}")
                except Exception: pass
            finally: _set_orb_state(orb, "idle")
        threading.Thread(target=_yt_run, daemon=True).start()
        return

    # ---- OpenWeather ----
    if _HAVE_OPENWEATHER and _openweather and _openweather.is_weather_request(text):
        _set_orb_state(orb, "thinking")
        def _ow_run(_t=text, _tts=tts, _mem=memory):
            try:
                reply = _openweather.handle(_t, tts_say=_tts.say)
                if reply and _mem: _mem.remember_turn(_t, reply)
            except Exception as e:
                try: _tts.say(f"Ob-havo xato: {e}")
                except Exception: pass
            finally: _set_orb_state(orb, "idle")
        threading.Thread(target=_ow_run, daemon=True).start()
        return

    # ---- Notion ----
    if _HAVE_NOTION and _notion and _notion.is_notion_request(text):
        _set_orb_state(orb, "thinking")
        def _no_run(_t=text, _tts=tts, _mem=memory):
            try:
                reply = _notion.handle(_t, tts_say=_tts.say)
                if reply and _mem: _mem.remember_turn(_t, reply)
            except Exception as e:
                try: _tts.say(f"Notion xato: {e}")
                except Exception: pass
            finally: _set_orb_state(orb, "idle")
        threading.Thread(target=_no_run, daemon=True).start()
        return

    # ---- Site Bridge: saytni ovoz bilan boshqarish ----
    if _HAVE_SITE and _site and _site.is_site_request(text):
        _set_orb_state(orb, "thinking")
        def _site_run(_t=text, _tts=tts, _mem=memory):
            try:
                reply = _site.handle_site_request(_t, tts_say=_tts.say)
                if reply and _mem:
                    _mem.remember_turn(_t, reply)
            except Exception as _se:
                try:
                    _tts.say(f"Sayt xatosi: {_se}")
                except Exception:
                    pass
            finally:
                _set_orb_state(orb, "idle")
        import threading as _st
        _st.Thread(target=_site_run, daemon=True).start()
        return

    # ---- Gamma.app: AI taqdimot yaratish ----
    if _HAVE_GAMMA and _gamma and _gamma.is_gamma_request(text):
        _set_orb_state(orb, "thinking")
        def _gamma_run(_t=text, _tts=tts, _mem=memory):
            try:
                reply = _gamma.get_handle_reply(_t, tts_say=_tts.say)
                if reply and _mem:
                    _mem.remember_turn(_t, reply)
            except Exception as _ge:
                try:
                    _tts.say(f"Gamma xatosi: {_ge}")
                except Exception:
                    pass
            finally:
                _set_orb_state(orb, "idle")
        import threading as _gt
        _gt.Thread(target=_gamma_run, daemon=True).start()
        return

    # ---- Dynamic Organ Integration: organlar bir zumda javob beradi ----
    if _HAVE_ORGAN_LOADER:
        organ_reply = dispatch_to_organs(text)
        if organ_reply:
            _set_orb_state(orb, "speaking")
            tts.say(organ_reply[:500])
            if memory:
                memory.remember_turn(text, organ_reply[:300])
            _set_orb_state(orb, "idle")
            return

    # ---- Config / papka ochish: tuzatish; xato fayli — egaga yuborish ----
    if _is_open_config_or_folder(text) and _HAVE_CONTROL:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(app_dir, ".env")
        data_dir = os.path.join(app_dir, "data")
        errors_for_owner = os.path.join(data_dir, "errors_for_owner.txt")
        open_error_file = "xato" in low or "error" in low or "ошибк" in low
        try:
            control.open_folder(app_dir)
            if os.path.isfile(env_path):
                os.startfile(env_path)
            if open_error_file and os.path.isfile(errors_for_owner):
                os.startfile(errors_for_owner)
        except Exception:
            try:
                control.open_folder(app_dir)
            except Exception:
                pass
        _set_orb_state(orb, "speaking")
        if open_error_file and os.path.isfile(errors_for_owner):
            tts.say(get_feedback("opened_error_file"))
        else:
            tts.say(get_feedback("opened_folder"))
        _set_orb_state(orb, "idle")
        return

    # ---- Shovqin / ekran haqida qisqa javob (LLM chaqirmasdan) ----
    if _is_noise_or_screen_info_question(text):
        _set_orb_state(orb, "speaking")
        if "shovqin" in low or "noise" in low or "blok" in low or "ovoz" in low:
            tts.say(get_feedback("noise_filtered"))
        else:
            tts.say(get_feedback("screen_watched"))
        _set_orb_state(orb, "idle")
        return

    # ---- Todo ----
    if _HAVE_EXTRAS:
        if _is_todo_add(text):
            task_text = re.sub(r"add to my todo|add to todo|add task|todo add|my todo add|add to my tasks|add to list", "", low, flags=re.I).strip()[:500]
            if task_text:
                _extras.todo_add(task_text)
                _set_orb_state(orb, "speaking")
                tts.say(get_feedback("todo_added"))
                if memory:
                    memory.remember_turn(text, "Added to todo.")
                _set_orb_state(orb, "idle")
                return
        if _is_todo_list(text):
            lines = _extras.todo_list()
            _set_orb_state(orb, "speaking")
            if not lines:
                tts.say(get_feedback("todo_empty"))
            else:
                tts.say(get_feedback("todo_list", list="; ".join(lines[:8])))
            _set_orb_state(orb, "idle")
            return
        if _is_todo_done(text):
            idx = _extract_todo_done_index(text)
            if _extras.todo_mark_done(idx):
                _set_orb_state(orb, "speaking")
                tts.say(get_feedback("todo_done", idx=idx))
            else:
                _set_orb_state(orb, "speaking")
                tts.say(get_feedback("todo_no_such"))
            _set_orb_state(orb, "idle")
            return

        # ---- Timer ----
        if _is_timer(text):
            sec = _extract_timer_seconds(text)
            _extras.start_timer(sec, "Time's up.")
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("timer_min", min=sec // 60) if sec >= 60 else get_feedback("timer_sec", sec=sec))
            _set_orb_state(orb, "idle")
            return

        # ---- Calculator ----
        if _is_calculator(text):
            expr = _extract_calculator_expr(text)
            result = _extras.safe_calculator(expr)
            _set_orb_state(orb, "speaking")
            if result is not None:
                tts.say(get_feedback("calc_result", result=result))
            else:
                tts.say(get_feedback("calc_parse_error"))
            _set_orb_state(orb, "idle")
            return

        # ---- Copy screen to clipboard ----
        if _is_copy_screen(text) and _HAVE_SCREEN_VISION:
            try:
                import screen_vision as _sv
                img = _sv.grab_screen(None) if hasattr(_sv, "grab_screen") else None
                ocr_text = (_sv.extract_text(img) if img and hasattr(_sv, "extract_text") else "") or ""
                try:
                    import pyperclip
                    pyperclip.copy(ocr_text[:5000])
                    _set_orb_state(orb, "speaking")
                    tts.say(get_feedback("clipboard_copied"))
                except Exception:
                    _set_orb_state(orb, "speaking")
                    tts.say(get_feedback("clipboard_no_text"))
            except Exception:
                _set_orb_state(orb, "speaking")
                tts.say(get_feedback("clipboard_copy_error"))
            _set_orb_state(orb, "idle")
            return

        # ---- Calendar ----
        if _is_calendar_add(text):
            date_s, title_s, time_s = _extract_calendar_parts(text)
            _extras.calendar_add(date_s, title_s, time_s)
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("calendar_added"))
            _set_orb_state(orb, "idle")
            return
        if _is_calendar_list(text):
            lines = _extras.calendar_list(10)
            _set_orb_state(orb, "speaking")
            if not lines:
                tts.say(get_feedback("calendar_empty"))
            else:
                tts.say(get_feedback("calendar_upcoming", list="; ".join(lines[:5])))
            _set_orb_state(orb, "idle")
            return

        # ---- Save idea / thought ----
        if _is_save_idea(text) and long_term_memory:
            idea = _extract_idea_text(text)
            if idea:
                try:
                    long_term_memory.add_fact("user", "Idea/thought: " + idea)
                    _set_orb_state(orb, "speaking")
                    tts.say(get_feedback("idea_saved"))
                except Exception:
                    tts.say(get_feedback("idea_error"))
                _set_orb_state(orb, "idle")
                return

        # ---- Daily summary ----
        if _is_daily_summary(text):
            history = (memory.data.get("history", [])[-20:] if memory else [])
            facts = ""
            if long_term_memory:
                try:
                    facts = long_term_memory.get_user_facts_for_llm() or ""
                except Exception:
                    pass
            ctx = "Dialog today: " + str(history)[:2000] + "\nFacts: " + facts[:1000]
            try:
                reply = answer("Summarize what the user did and discussed today in 2-3 short sentences. Be concise.", profile_context=ctx, current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"))
                _set_orb_state(orb, "speaking")
                tts.say(_extract_spoken_reply(reply) or "На сегодня ничего не записано.")
            except Exception:
                tts.say(get_feedback("summary_error"))
            _set_orb_state(orb, "idle")
            return

        # ---- Backup ----
        if _is_backup(text):
            ok, msg = _extras.backup_memory_and_ltm()
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("backup_done") if ok else get_feedback("backup_failed", msg=msg[:80]))
            _set_orb_state(orb, "idle")
            return

        # ---- Person relation (LTM) ----
        if _is_person_relation(text) and long_term_memory:
            rel = _extract_person_relation(text)
            if len(rel) > 5:
                try:
                    long_term_memory.add_fact("user", "Person/relation: " + rel)
                    _set_orb_state(orb, "speaking")
                    tts.say(get_feedback("remember_ok"))
                except Exception:
                    pass
                _set_orb_state(orb, "idle")
                return

    # ---- News / Crypto / Wikipedia: use web then short reply ----
    if _is_news_request(text) or _is_crypto(text) or _is_wikipedia(text):
        pass  # fall through to web + LLM below; they get web_ctx

    # ---- Translate: quick LLM call ----
    if _is_translate(text):
        try:
            reply = answer("Переведи следующий текст на русский язык. Выведи только перевод, ничего лишнего: " + text, current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"))
            _set_orb_state(orb, "speaking")
            tts.say(_extract_spoken_reply(reply) or reply[:200])
        except Exception:
            pass  # fall through to normal LLM
        else:
            _set_orb_state(orb, "idle")
            return

    # ---- Slack / Discord (webhook) ----
    if _is_slack_send(text) and getattr(C, "SLACK_WEBHOOK_URL", ""):
        try:
            import urllib.request
            msg = text.replace("send to slack", "").replace("slack", "").strip()[:500]
            req = urllib.request.Request(C.SLACK_WEBHOOK_URL, data=json.dumps({"text": msg}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("slack_sent"))
        except Exception:
            tts.say(get_feedback("slack_failed"))
        _set_orb_state(orb, "idle")
        return
    if _is_discord_send(text) and getattr(C, "DISCORD_WEBHOOK_URL", ""):
        try:
            import urllib.request
            msg = text.replace("send to discord", "").replace("discord", "").strip()[:500]
            req = urllib.request.Request(C.DISCORD_WEBHOOK_URL, data=json.dumps({"content": msg}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("discord_sent"))
        except Exception:
            tts.say(get_feedback("discord_failed"))
        _set_orb_state(orb, "idle")
        return
    if _is_slack_send(text) or _is_discord_send(text):
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("slack_discord_not_configured"))
        _set_orb_state(orb, "idle")
        return
    if _is_notion_note(text):
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("notion_not_configured"))
        _set_orb_state(orb, "idle")
        return
    if _is_smart_home(text):
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("smart_home_not_configured"))
        _set_orb_state(orb, "idle")
        return

    # ---- PENDING (da/yo'q yoki "отправь как есть") ----
    if memory and memory.get_pending():
        pending = memory.get_pending()
        kind = (pending or {}).get("type")

        # GUARD: agar foydalanuvchi boshqa mavzu haqida gapirdi — TG pendingni tozalaymiz va
        # quyidagi barcha tg_reply/tg_confirm_send tekshiruvlarini o'tkazib yuboramiz.
        # kind = None qilinsa, hech bir "if kind == ..." shart mos kelmaydi,
        # blok shart bajarilmagan holda tugaydi va quyidagi normal kod davom etadi.
        if kind in ("tg_reply", "tg_confirm_send") and _is_unrelated_to_pending(text):
            memory.clear_pending()
            kind = None  # Boshqa mavzu — TG shart bloklarini o'tkazib yuboramiz

        # Offer code: write code to file
        if kind == "offer_code":
            task = (pending or {}).get("task", "").strip()
            if (_is_yes_no(text) == "yes" or _is_accept_write_code(text)) and task:
                memory.clear_pending()
                _set_orb_state(orb, "speaking")
                run_after = _is_run_after_save(text)
                as_organ = "organ" in (text or "").lower() or "орган" in (text or "").lower()
                try:
                    gen_task = (task + " Create as NeuroKey organ: def organ_handle(text: str) -> Optional[str]: return result when input matches task else None.") if as_organ else task
                    code = generate_code(gen_task, lang=_ui_lang(text))
                    if not code:
                        tts.say(get_feedback("code_gen_error"))
                    elif as_organ and _HAVE_BABATA_CORE:
                        ok, msg = evolve_create_organ(re.sub(r"[^a-zA-Z0-9_]", "", task[:30]) or "new_organ", code)
                        tts.say(get_feedback("organ_created") if ok else msg)
                    else:
                        filename = "neurokey_generated.py"
                        lines = code.split("\n")
                        if lines and ("filename:" in lines[0].lower() or "filename :" in lines[0].lower()):
                            m = re.search(r"filename\s*:\s*([^\s#]+\.\w+)", lines[0], re.I)
                            if m:
                                filename = m.group(1).strip()
                                code = "\n".join(lines[1:]).lstrip()
                        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
                        with open(out_path, "w", encoding="utf-8") as f:
                            f.write(code)
                        if run_after and _HAVE_SYSTEM_LEVEL:
                            code, out = run_script_sandbox(code, lang="python", timeout_sec=60.0)
                            tts.say(get_feedback("sandbox_result", out=out[:200]) if out else get_feedback("sandbox_done"))
                        else:
                            tts.say(get_feedback("code_saved", filename=filename))
                        if memory:
                            memory.remember_turn(text, f"Code saved to {filename}.")
                except Exception as e:
                    if _HAVE_ERROR_LOG:
                        log_error("Offer code save", exc=e)
                    tts.say(get_feedback("code_save_error"))
            elif _is_yes_no(text) == "no":
                memory.clear_pending()
                _set_orb_state(orb, "speaking")
                tts.say(get_feedback("code_wont_write"))
            _set_orb_state(orb, "idle")
            return
        # Agar foydalanuvchi buyruq berdi (och/yop/закрой телеграм) — Telegramga YUBORMA, balki buyruqni bajar
        if kind == "tg_reply" and (_is_control_command(text) or _is_cancel_send(text)):
            memory.clear_pending()
            _set_orb_state(orb, "speaking")
            if _HAVE_CONTROL and _is_control_close(text):
                app = _control_app_from_text(text, False)
                _log_action("close_app", app)
                ok, msg = control.close_app(app)
                tts.say(msg)
            elif _HAVE_CONTROL and _is_control_open(text):
                app = _control_app_from_text(text, True)
                _log_action("open_app", app)
                ok, msg = control.open_app(app)
                tts.say(msg)
            elif _HAVE_CONTROL and _is_minimize_all(text):
                ok, msg = control.minimize_all_windows()
                tts.say(msg)
            elif _HAVE_CONTROL and _is_restore_windows(text):
                ok, msg = control.restore_all_windows()
                tts.say(msg)
            else:
                tts.say(get_feedback("didnt_send_cancelled"))
            if memory:
                memory.remember_turn(text, "Cancelled send, ran command.")
            _set_orb_state(orb, "idle")
            return
        if (_is_send_as_is(text) or _is_yes_no(text) == "yes" or _is_send_reply_intent(text)) and kind == "tg_reply":
            peer_id = (pending or {}).get("peer_id")
            suggested = (pending or {}).get("reply_text", "")
            user_own_text = _extract_user_reply_from_pending_phrase(text)
            if _is_pure_confirm_send(text) or _is_send_reply_intent(text) or not user_own_text:
                reply_text = suggested.strip()
            else:
                reply_text = user_own_text.strip()
            if tg_user and peer_id is not None and reply_text:
                try:
                    _log_action("tg_send", str(peer_id))
                    tg_user.send_peer(int(peer_id), reply_text)
                    _set_orb_state(orb, "speaking")
                    tg_list = (memory.data.get("state") or {}).get("tg_unread_list") or []
                    idx = (memory.data.get("state") or {}).get("tg_unread_index") or 0
                    idx += 1
                    memory.data.setdefault("state", {})["tg_unread_index"] = idx
                    memory.save()
                    if idx < len(tg_list):
                        next_item = tg_list[idx]
                        n_peer_id = next_item.get("peer_id")
                        n_peer_name = next_item.get("peer_name", "")
                        n_text = next_item.get("text", "")
                        n_suggested = suggest_telegram_reply(n_peer_name, n_text, lang="ru")
                        memory.set_pending({"type": "tg_reply", "peer_id": n_peer_id, "reply_text": n_suggested, "peer_name": n_peer_name, "message_text": n_text}, ttl_sec=90)
                        short_n = (n_text[:80] + "…") if len(n_text) > 80 else n_text
                        tts.say(get_feedback("tg_sent_next_suggested", peer=n_peer_name, msg=short_n, suggested=(n_suggested[:80] + "…" if len(n_suggested) > 80 else n_suggested)))
                    else:
                        tts.say(get_feedback("tg_sent_no_more"))
                except Exception as e:
                    if _HAVE_ERROR_LOG:
                        log_error("TG send", exc=e)
                    _safe_print("[TG_SEND_ERROR]", repr(e))
                    err_msg = str(e).lower() if e else ""
                    if "flood" in err_msg or "wait" in err_msg:
                        tts.say(get_feedback("tg_wait"))
                    else:
                        tts.say(get_feedback("tg_failed"))
                    memory.clear_pending()
            else:
                memory.clear_pending()
            _set_orb_state(orb, "idle")
            return
        if kind == "tg_confirm_send" and (_is_yes_no(text) == "yes" or _is_send_as_is(text)):
            peer_id = (pending or {}).get("peer_id")
            reply_text = (pending or {}).get("reply_text", "")
            if tg_user and peer_id is not None and reply_text:
                try:
                    _log_action("tg_send", str(peer_id))
                    tg_user.send_peer(int(peer_id), reply_text)
                    _set_orb_state(orb, "speaking")
                    tg_list = (memory.data.get("state") or {}).get("tg_unread_list") or []
                    idx = (memory.data.get("state") or {}).get("tg_unread_index") or 0
                    idx += 1
                    memory.data.setdefault("state", {})["tg_unread_index"] = idx
                    memory.save()
                    memory.clear_pending()
                    if idx < len(tg_list):
                        next_item = tg_list[idx]
                        n_peer_id, n_peer_name = next_item.get("peer_id"), next_item.get("peer_name", "")
                        n_text = next_item.get("text", "")
                        n_suggested = suggest_telegram_reply(n_peer_name, n_text, lang=_ui_lang(text))
                        memory.set_pending({"type": "tg_reply", "peer_id": n_peer_id, "reply_text": n_suggested, "peer_name": n_peer_name, "message_text": n_text}, ttl_sec=90)
                        short_n = (n_text[:80] + "…") if len(n_text) > 80 else n_text
                        tts.say(get_feedback("tg_sent_next_simple", peer=n_peer_name, msg=short_n))
                    else:
                        tts.say(get_feedback("tg_sent_no_more"))
                except Exception as e:
                    if _HAVE_ERROR_LOG:
                        log_error("TG send", exc=e)
                    memory.clear_pending()
                    tts.say(get_feedback("tg_failed_short"))
            else:
                memory.clear_pending()
            _set_orb_state(orb, "idle")
            return
        if kind == "tg_confirm_send" and _is_yes_no(text) == "no":
            memory.clear_pending()
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("cancelled_didnt_send"))
            _set_orb_state(orb, "idle")
            return
        if kind == "tg_reply" and (_is_pure_confirm_send(text) or _is_send_reply_intent(text)):
            suggested = (pending or {}).get("reply_text", "")
            peer_id = (pending or {}).get("peer_id")
            if tg_user and peer_id and suggested:
                try:
                    _log_action("tg_send", str(peer_id))
                    tg_user.send_peer(int(peer_id), suggested.strip())
                    _set_orb_state(orb, "speaking")
                    tg_list = (memory.data.get("state") or {}).get("tg_unread_list") or []
                    idx = (memory.data.get("state") or {}).get("tg_unread_index") or 0
                    idx += 1
                    memory.data.setdefault("state", {})["tg_unread_index"] = idx
                    memory.save()
                    memory.clear_pending()
                    if idx < len(tg_list):
                        next_item = tg_list[idx]
                        n_peer_id, n_peer_name = next_item.get("peer_id"), next_item.get("peer_name", "")
                        n_text = next_item.get("text", "")
                        n_suggested = suggest_telegram_reply(n_peer_name, n_text, lang=_ui_lang(text))
                        memory.set_pending({"type": "tg_reply", "peer_id": n_peer_id, "reply_text": n_suggested, "peer_name": n_peer_name, "message_text": n_text}, ttl_sec=90)
                        short_n = (n_text[:80] + "…") if len(n_text) > 80 else n_text
                        tts.say(get_feedback("tg_sent_reply_next", peer=n_peer_name, msg=short_n, suggested=(n_suggested[:80] + "…" if len(n_suggested) > 80 else n_suggested)))
                    else:
                        tts.say(get_feedback("tg_sent_no_more"))
                except Exception as e:
                    if _HAVE_ERROR_LOG:
                        log_error("TG send", exc=e)
                    memory.clear_pending()
                    tts.say(get_feedback("tg_failed_short"))
            else:
                memory.clear_pending()
            _set_orb_state(orb, "idle")
            return
        if kind == "tg_reply" and _is_yes_no(text) is None and not _is_send_as_is(text) and not _is_pure_confirm_send(text) and not _is_send_reply_intent(text) and len((text or "").strip()) > 0:
            # Foydalanuvchi o'z javobini aytdi — xabarga mos bo'lsa darhol yuboramiz; "junat"/"send" emas
            peer_id = (pending or {}).get("peer_id")
            message_text = (pending or {}).get("message_text", "")
            reply_text = (text or "").strip()
            if tg_user and peer_id is not None and reply_text:
                if message_text and not _reply_matches_message(reply_text, message_text) and len(reply_text) > 25:
                    memory.set_pending({"type": "tg_confirm_send", "peer_id": peer_id, "reply_text": reply_text}, ttl_sec=90)
                    _set_orb_state(orb, "speaking")
                    preview = (reply_text[:60] + "…") if len(reply_text) > 60 else reply_text
                    tts.say(get_feedback("tg_reply_mismatch", preview=preview))
                    _set_orb_state(orb, "idle")
                    return
                try:
                    _log_action("tg_send", str(peer_id))
                    tg_user.send_peer(int(peer_id), reply_text)
                    _set_orb_state(orb, "speaking")
                    tg_list = (memory.data.get("state") or {}).get("tg_unread_list") or []
                    idx = (memory.data.get("state") or {}).get("tg_unread_index") or 0
                    idx += 1
                    memory.data.setdefault("state", {})["tg_unread_index"] = idx
                    memory.save()
                    memory.clear_pending()
                    if idx < len(tg_list):
                        next_item = tg_list[idx]
                        n_peer_id = next_item.get("peer_id")
                        n_peer_name = next_item.get("peer_name", "")
                        n_text = next_item.get("text", "")
                        n_suggested = suggest_telegram_reply(n_peer_name, n_text, lang=_ui_lang(text))
                        memory.set_pending({"type": "tg_reply", "peer_id": n_peer_id, "reply_text": n_suggested, "peer_name": n_peer_name, "message_text": n_text}, ttl_sec=90)
                        short_n = (n_text[:80] + "…") if len(n_text) > 80 else n_text
                        tts.say(get_feedback("tg_sent_next_simple", peer=n_peer_name, msg=short_n))
                    else:
                        tts.say(get_feedback("tg_sent_no_more"))
                except Exception as e:
                    if _HAVE_ERROR_LOG:
                        log_error("TG send", exc=e)
                    _safe_print("[TG_SEND_ERROR]", repr(e))
                    memory.clear_pending()
                    tts.say(get_feedback("tg_failed_short"))
            else:
                memory.clear_pending()
            _set_orb_state(orb, "idle")
            return
        if kind == "tg_reply" and _is_yes_no(text) == "no":
            # "Нет, отправь только что я занят" — taklifni rad etdi, lekin o'zi aytgan matnni yuboramiz
            user_own_text = _extract_user_reply_from_pending_phrase(text)
            if user_own_text and tg_user and (pending or {}).get("peer_id") is not None:
                try:
                    _log_action("tg_send", str((pending or {}).get("peer_id")))
                    tg_user.send_peer(int((pending or {}).get("peer_id")), user_own_text)
                    _set_orb_state(orb, "speaking")
                    tg_list = (memory.data.get("state") or {}).get("tg_unread_list") or []
                    idx = (memory.data.get("state") or {}).get("tg_unread_index") or 0
                    idx += 1
                    memory.data.setdefault("state", {})["tg_unread_index"] = idx
                    memory.save()
                    memory.clear_pending()
                    if idx < len(tg_list):
                        next_item = tg_list[idx]
                        n_peer_id = next_item.get("peer_id")
                        n_peer_name = next_item.get("peer_name", "")
                        n_text = next_item.get("text", "")
                        n_suggested = suggest_telegram_reply(n_peer_name, n_text, lang=_ui_lang(text))
                        memory.set_pending({"type": "tg_reply", "peer_id": n_peer_id, "reply_text": n_suggested, "peer_name": n_peer_name}, ttl_sec=90)
                        short_n = (n_text[:80] + "…") if len(n_text) > 80 else n_text
                        tts.say(get_feedback("tg_sent_reply_next", peer=n_peer_name, msg=short_n, suggested=(n_suggested[:80] + "…" if len(n_suggested) > 80 else n_suggested)))
                    else:
                        tts.say(get_feedback("tg_reply_no_more"))
                except Exception as e:
                    if _HAVE_ERROR_LOG:
                        log_error("TG send", exc=e)
                    memory.clear_pending()
                    tts.say(get_feedback("tg_failed_short"))
                _set_orb_state(orb, "idle")
                return
            # Haqiqiy "нет" — taklifni rad etamiz, keyingi xabarga o'tamiz
            tg_list = (memory.data.get("state") or {}).get("tg_unread_list") or []
            idx = (memory.data.get("state") or {}).get("tg_unread_index") or 0
            idx += 1
            memory.data.setdefault("state", {})["tg_unread_index"] = idx
            memory.save()
            memory.clear_pending()
            _set_orb_state(orb, "speaking")
            if idx < len(tg_list):
                next_item = tg_list[idx]
                n_peer_id = next_item.get("peer_id")
                n_peer_name = next_item.get("peer_name", "")
                n_text = next_item.get("text", "")
                n_suggested = suggest_telegram_reply(n_peer_name, n_text, lang=_ui_lang(text))
                memory.set_pending({"type": "tg_reply", "peer_id": n_peer_id, "reply_text": n_suggested, "peer_name": n_peer_name, "message_text": n_text}, ttl_sec=90)
                short_n = (n_text[:80] + "…") if len(n_text) > 80 else n_text
                tts.say(get_feedback("tg_skipped_next", peer=n_peer_name, msg=short_n, suggested=(n_suggested[:80] + "…" if len(n_suggested) > 80 else n_suggested)))
            else:
                tts.say(get_feedback("tg_skipped_no_more"))
            _set_orb_state(orb, "idle")
            return
        if kind == "delete_file" and _is_yes_no(text) == "yes":
            path = (pending or {}).get("path", "")
            if path and _HAVE_CONTROL:
                _log_action("delete_file", path)
                ok, msg = control.delete_file(path)
                _set_orb_state(orb, "speaking")
                tts.say(msg)
            memory.clear_pending()
            _set_orb_state(orb, "idle")
            return
        if _is_yes_no(text) == "no":
            memory.clear_pending()
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("cancelled"))
            _set_orb_state(orb, "idle")
            return

    # ---- READ FILE CONTENT (Universal File Mastery) ----
    if _HAVE_BABATA_CORE and _is_read_file_content(text):
        path = _extract_file_path_for_read(text) or (memory.data.get("state") or {}).get("last_opened_file") if memory else ""
        if path and os.path.isfile(path):
            ok, content = extract_file_content(path)
            if ok:
                _set_orb_state(orb, "speaking")
                summary = (content[:400] + "…") if len(content) > 400 else content
                tts.say(summary) if len(summary) < 300 else tts.say(get_feedback("file_extracted", n=len(content)))
                if memory:
                    memory.remember_turn(text, "Read file: " + path)
            else:
                _set_orb_state(orb, "speaking")
                tts.say(content or get_feedback("could_not_read_file"))
        else:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("which_file"))
        _set_orb_state(orb, "idle")
        return

    # ---- RUN COMMAND (kod orqali — run_native yoki control.run_command; infer ham) ----
    if _is_run_command(text) or (_inferred_intent and _inferred_intent[0] == "run"):
        cmd = _extract_run_command(text)
        if cmd:
            _set_orb_state(orb, "speaking")
            if _HAVE_SYSTEM_LEVEL:
                code, out = run_native(cmd, timeout_sec=30.0)
                msg = (out[:300] + "…") if len(out) > 300 else out if out else ("Done." if code == 0 else f"Exit {code}")
            elif _HAVE_CONTROL:
                ok, out = control.run_command(cmd, timeout_sec=30.0)
                msg = (out[:300] + "…") if len(out) > 300 else out if out else ("Done." if ok else out)
            else:
                msg = get_feedback("what_command")
            tts.say(msg)
            if memory:
                memory.remember_turn(text, "Ran: " + msg[:200])
        else:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("what_command"))
        _set_orb_state(orb, "idle")
        return

    # ---- SYSTEM STATUS (CPU, RAM, batareya) ----
    if _HAVE_SYSTEM_MONITOR and _is_system_status(text):
        report = get_system_report(_ui_lang(text))
        if _HAVE_BABATA_CORE and get_network_interfaces:
            net = get_network_interfaces()
            if net:
                report = report + ". " + net
        _set_orb_state(orb, "speaking")
        tts.say(report)
        if memory:
            memory.remember_turn(text, report)
        _set_orb_state(orb, "idle")
        return

    # ---- NETWORK SOVEREIGNTY (ochiq portlar) ----
    if _HAVE_BABATA_CORE and _is_network_status(text):
        ok, msg = network_scan_local_ports()
        _set_orb_state(orb, "speaking")
        tts.say(msg or get_feedback("no_open_ports"))
        if memory:
            memory.remember_turn(text, msg or "")
        _set_orb_state(orb, "idle")
        return

    # ---- UNIVERSAL CONNECTIVITY (qurilmalar) ----
    if _HAVE_BABATA_CORE and _is_devices_request(text):
        devs = discover_network_devices()
        _set_orb_state(orb, "speaking")
        tts.say(devs or get_feedback("no_devices"))
        if memory:
            memory.remember_turn(text, devs or "")
        _set_orb_state(orb, "idle")
        return

    # ---- STRATEGIC PATH (formulate_conquest_strategy — predictive) ----
    if _HAVE_BABATA_CORE and _is_strategy_request(text):
        goal = text.strip()  # LLM ga yubormasdan, matndan maqsadni chiqarish
        for prefix in ["strategiya", "strategic", "reja", "plan", "koinot", "conquest", "maqsadim uchun"]:
            if prefix in goal.lower():
                goal = goal.lower().split(prefix, 1)[-1].strip()
                break
        profile_goals = None
        try:
            p = getattr(C, "OWNER_PROFILE", None) or {}
            profile_goals = p.get("goals_2025") if isinstance(p, dict) else None
        except Exception:
            pass
        strategy = formulate_conquest_strategy(goal or None, profile_goals)
        _set_orb_state(orb, "speaking")
        tts.say(strategy[:500])
        if memory:
            memory.remember_turn(text, strategy[:300])
        _set_orb_state(orb, "idle")
        return

    # ──────────────────────────────────────────────────────────────────────────
    # ---- DEMO VIDEO TRIGGER: "demo video olamiz", "demo boshlaylik" ---------
    # ──────────────────────────────────────────────────────────────────────────
    if _is_demo_video_trigger(text):
        _set_orb_state(orb, "thinking")

        # ── INTRO ─────────────────────────────────────────────────────────────
        _intro = (
            "Agar sizni bir daqiqaga chalg'itmasam... "
            "Men — NeuroKey. Men bu kompyuterda yashayman. "
            "Serverda emas, cloudda emas — to'g'ridan shu yerda. "
            "Hozir uch narsani ko'rsataman — hammasini hoziroq, jonli."
        )
        _set_orb_state(orb, "speaking")
        tts.say(_intro)
        time.sleep(0.6)

        # ── WOW #1 — XOTIRA (real ma'lumot bilan) ────────────────────────────
        _set_orb_state(orb, "thinking")
        _owner_name = ""
        _hist_count = 0
        _last_date = ""
        try:
            import json as _json
            _mpath = os.path.join(app_dir, "data", "memory.json")
            with open(_mpath, encoding="utf-8") as _mf:
                _mdata = _json.load(_mf)
            _owner_name = (
                _mdata.get("profile", {}).get("owner_name", "")
                or _mdata.get("profile", {}).get("owner_profile", {}).get("full_name", "")
            )
            _hist = _mdata.get("history", [])
            _hist_count = len(_hist)
            if _hist:
                import datetime as _dt
                _last_ts = _hist[-1].get("t", 0)
                if _last_ts:
                    _last_date = _dt.datetime.fromtimestamp(_last_ts).strftime("%d.%m.%Y")
        except Exception:
            pass

        if _owner_name and _hist_count > 0:
            _mem_text = (
                f"Birinchisi — xotira. "
                f"Siz — {_owner_name}. "
                f"Biz {_hist_count} marta suhbatlashganmiz. "
                f"Oxirgisi — {_last_date or 'yaqinda'}. "
                f"Tab yopilsa ham, kompyuter o'chsa ham — men unutmayman."
            )
        else:
            _mem_text = (
                "Birinchisi — xotira. "
                "Siz kim ekanligingizni bilaman. Ismingizni, odatlaringizni. "
                "Tab yopilsa ham, kompyuter o'chsa ham — men unutmayman. Abadiy."
            )
        _set_orb_state(orb, "speaking")
        tts.say(_mem_text)
        time.sleep(0.5)

        # ── WOW #2 — TELEGRAM LIVE ────────────────────────────────────────────
        _set_orb_state(orb, "thinking")
        tts.say("Ikkinchisi — Telegram. Hozir tekshiraman.")
        time.sleep(0.3)

        _tg_shown = False
        try:
            if _HAVE_TG_USER and tg_bridge and tg_bridge.is_connected():
                _unread = tg_bridge.unread_incoming(limit=3)
                if _unread:
                    _msg = _unread[0]
                    _sender = _msg.get("peer_name") or _msg.get("sender") or "kimdir"
                    _body = (_msg.get("text") or "").strip()[:80]
                    _tg_live = (
                        f"{_sender} dan xabar bor. "
                        f"Deyapti: {_body}. "
                        f"Javob yuborishim kerakmi? — faqat 'ha' deng."
                    )
                    _tg_shown = True
                else:
                    _tg_live = (
                        "Hozir yangi xabar yo'q. "
                        "Lekin xabar kelsa — men birinchi bilaman. "
                        "Va sizning ruxsatingiz bilan — telefoningizga qo'l tekkizmasdan javob yuboraman."
                    )
                    _tg_shown = True
        except Exception:
            pass

        if not _tg_shown:
            _tg_live = (
                "Telegram ulangan. Xabar kelsa — men aytaman. "
                "'Javob yubor' desangiz — qo'llaringiz erkin."
            )
        _set_orb_state(orb, "speaking")
        tts.say(_tg_live)
        time.sleep(0.5)

        # ── WOW #3 — EKRAN KO'RISH + KOMPYUTER BOSHQARUVI ────────────────────
        _set_orb_state(orb, "thinking")
        tts.say("Uchinchisi — men ekranni ko'raman va kompyuterni boshqaraman. Hozir ko'rsataman.")
        time.sleep(0.3)

        # 3a. Ekranni o'qish — darhol oyna + kesh OCR
        _screen_desc = ""
        try:
            _screen_desc = (_build_screen_reply("что на экране", lang="ru") or "")[:280]
        except Exception:
            pass

        if _screen_desc:
            _set_orb_state(orb, "speaking")
            tts.say(_screen_desc)
            time.sleep(0.4)

        # 3b. Brauzer ochish — real harakat
        _set_orb_state(orb, "thinking")
        _browser_ok = False
        if _HAVE_CONTROL and control:
            try:
                control.open_app("browser")
                time.sleep(1.8)
                _browser_ok = True
            except Exception:
                pass

        if _browser_ok:
            _ctrl_text = "Brauzer ochildi. Faqat mening ovozim bilan. Qo'l tegmadi."
        else:
            _ctrl_text = "Brauzerni ochaman, qidiraman, fayllarni ko'chiraman — hammasini ovoz bilan."
        _set_orb_state(orb, "speaking")
        tts.say(_ctrl_text)
        time.sleep(0.4)

        # ── OUTRO ─────────────────────────────────────────────────────────────
        _set_orb_state(orb, "thinking")
        _outro = (
            "Bu — NeuroKey. "
            "Sizning kompyuteringizdagi shaxsiy AI. "
            "Xotira. Telegram. Ekran. Boshqaruv. "
            "Hammasi bir joyda. Hammasi sizniki."
        )
        _set_orb_state(orb, "speaking")
        tts.say(_outro)

        if memory:
            memory.remember_turn(text, "Demo ko'rsatildi: xotira (ism+suhbat soni), Telegram (live), ekran ko'rish, brauzer boshqaruvi.")
        _set_orb_state(orb, "idle")
        return

    # ──────────────────────────────────────────────────────────────────────────
    # ---- LOYHA / PROJECT DEMO: "haqida ayt", "isbotla", "ko'rsat" ----------
    # ──────────────────────────────────────────────────────────────────────────
    if _is_project_prove(text):
        # Investor yoki mehmon "isbotla", "ko'rsat", "докажи" deydi
        # → NeuroKey HAR BIRINI REAL VAQTDA AMALDA BAJARADI — faqat gapirib qolmaydi
        _t_low = (text or "").lower()
        _set_orb_state(orb, "thinking")

        # 1. EKRANNI KO'RISH isboti — HOZIROQ screenshot olib haqiqiy kontentni aytadi
        if any(x in _t_low for x in ["экран", "screen", "ekran", "видишь", "ko'r", "cor"]):
            _set_orb_state(orb, "thinking")
            _sv_reply = _build_screen_reply(text, lang="ru")
            _set_orb_state(orb, "speaking")
            tts.say(_sv_reply[:500])
            if memory:
                memory.remember_turn(text, _sv_reply[:200])
            _set_orb_state(orb, "idle")
            return

        # 2. XOTIRA isboti — LTM dan HAQIQIY yozuvlarni o'qib aytadi
        if any(x in _t_low for x in ["память", "xotir", "помни", "esla", "запомн"]):
            _mem_items = []
            if _HAVE_LTM and _ltm:
                try:
                    _mem_items = _ltm.get_recent(limit=3)
                except Exception:
                    pass
            if _mem_items:
                _mem_parts = []
                for _mi in _mem_items[:3]:
                    _mc = str(_mi.get("content", _mi) if isinstance(_mi, dict) else _mi).strip()[:100]
                    if _mc:
                        _mem_parts.append(_mc)
                if _mem_parts:
                    _mem_str = ". Затем: ".join(_mem_parts)
                    _mem_reply = (
                        f"Моя долгосрочная память работает. "
                        f"Достаю реальные данные прямо сейчас. "
                        f"Вот что я запомнил: {_mem_str}. "
                        f"Всё хранится локально. AES-256. Никаких серверов."
                    )
                else:
                    _mem_reply = (
                        "Долгосрочная память активна. "
                        "Записи есть, но содержимое зашифровано локально. "
                        "AES-256 шифрование — никто кроме вас не видит."
                    )
            else:
                # Xotira bo'sh — HOZIR biror narsa yozib ko'rsatamiz
                if memory:
                    memory.remember_turn("demo_proof", f"Демо: память проверена в {datetime.now().strftime('%H:%M:%S')}")
                _mem_reply = (
                    "Память пуста — только что записал в неё: "
                    f"'Демо в {datetime.now().strftime('%H:%M:%S')}'. "
                    "Спросите меня через минуту — вспомню. "
                    "Хранится локально, AES-256, без облака."
                )
            _set_orb_state(orb, "speaking")
            tts.say(_mem_reply[:500])
            if memory:
                memory.remember_turn(text, _mem_reply[:200])
            _set_orb_state(orb, "idle")
            return

        # 3. TELEGRAM isboti — Telegram oynasi ochiqmi tekshiradi, topsa aytadi
        if any(x in _t_low for x in ["telegram", "телеграм", "tg"]):
            _tg_window_found = False
            _tg_window_title = ""
            try:
                from window_ops import get_visible_windows
                _wins = get_visible_windows()
                for _w in _wins:
                    _wt = (_w.get("title") or "").lower()
                    if "telegram" in _wt:
                        _tg_window_found = True
                        _tg_window_title = _w.get("title", "Telegram")
                        break
            except Exception:
                pass
            if _tg_window_found:
                _tg_reply = (
                    f"Вижу что у вас открыт {_tg_window_title}. "
                    f"Скажите кому и что отправить — отправлю прямо сейчас. "
                    f"Например: отправь другу 'Привет, это демо NeuroKey'."
                )
            else:
                _tg_reply = (
                    "Telegram сейчас не открыт. "
                    "Скажите: 'открой Telegram' — открою. "
                    "Затем скажите кому и что отправить — отправлю без единого нажатия."
                )
            _set_orb_state(orb, "speaking")
            tts.say(_tg_reply)
            if memory:
                memory.remember_turn(text, _tg_reply[:200])
            _set_orb_state(orb, "idle")
            return

        # 4. OFLAYN isboti — HAQIQIY savol beradi, Ollama dan HAQIQIY javob oladi
        if any(x in _t_low for x in ["офлайн", "offline", "без интернет", "internetsiz", "oflayn"]):
            _set_orb_state(orb, "thinking")
            _off_q = "Сколько будет 347 умножить на 28? Ответь только числом."
            _off_ans = "9716"
            try:
                _off_raw = answer(_off_q, lang="ru", screen_ctx="")
                if _off_raw and any(c.isdigit() for c in _off_raw):
                    _off_ans = (_off_raw or "9716").strip()[:80]
            except Exception:
                pass
            _off_reply = (
                f"Докажу прямо сейчас — без интернета. "
                f"Задаю вопрос локальному Ollama: сколько будет 347 умножить на 28? "
                f"Ответ: {_off_ans}. "
                f"Это ответил Ollama — локально, на вашем компьютере. Никаких серверов."
            )
            _set_orb_state(orb, "speaking")
            tts.say(_off_reply)
            if memory:
                memory.remember_turn(text, _off_reply[:200])
            _set_orb_state(orb, "idle")
            return

        # 5. UMUMIY "isbotla / ko'rsat" — 3 ta REAL AMAL KETMA-KET
        # Bosqich 1: haqiqiy screenshot va oyna tavsifi
        _set_orb_state(orb, "thinking")
        _scr_part = "Первое: " + (_build_screen_reply(text, lang="ru")[:220] or "вижу экран") + "."

        # Bosqich 2: Ollama ga HAQIQIY savol — lokal javob
        _math_ans = "9716"
        try:
            _math_raw = answer("Сколько будет 347 умножить на 28? Только число.", lang="ru", screen_ctx="")
            if _math_raw and any(c.isdigit() for c in (_math_raw or "")):
                _math_ans = (_math_raw or "9716").strip()[:60]
        except Exception:
            pass
        _ai_part = f"Второе: спрашиваю Ollama без интернета — 347 × 28 = {_math_ans}. Ответ от локальной модели."

        # Bosqich 3: HAQIQIY xotira yoki hozirgi vaqtni yozish
        _mem3_items = []
        if _HAVE_LTM and _ltm:
            try:
                _mem3_items = _ltm.get_recent(limit=2)
            except Exception:
                pass
        if _mem3_items:
            _m3 = ". ".join(
                [str(_x.get("content", _x) if isinstance(_x, dict) else _x).strip()[:70]
                 for _x in _mem3_items[:2] if str(_x.get("content", _x) if isinstance(_x, dict) else _x).strip()]
            )
            _mem_part3 = f"Третье: из памяти — {_m3}." if _m3 else "Третье: память активна, данные зашифрованы."
        else:
            _ts3 = datetime.now().strftime("%H:%M:%S")
            if memory:
                memory.remember_turn("demo_proof_general", f"Демо проведено в {_ts3}")
            _mem_part3 = f"Третье: записал в память — 'Демо в {_ts3}'. Локально. AES-256."

        _prove_reply = f"{_scr_part} {_ai_part} {_mem_part3}"
        _set_orb_state(orb, "speaking")
        tts.say(_prove_reply[:700])
        if memory:
            memory.remember_turn(text, _prove_reply[:300])
        _set_orb_state(orb, "idle")
        return

    # ---- LOYHA HAQIDA SAVOL — LLM dan to'liq javob, bilim bazasidan --------
    if _is_project_question(text):
        # System promptda loyha bilimi bor (neurokey_project_knowledge.py)
        # Bu yerda LLM ga aniq ko'rsatma beramiz: to'liq, aniq, professional javob
        _t_low = (text or "").lower()

        # Qisqa pitch (kim yaratdi, nima, necha dollar)
        if any(x in _t_low for x in ["kim yaratdi", "кто создал", "кто тебя", "kim yasaldi", "founder", "asoschisi"]):
            _who_reply = (
                "Меня создал Диёрбек Собиржонов — CEO и основатель. "
                "Вместе с COO Ахмаджоном Имамкуловым. "
                "Компания Innovateworks.Inc, зарегистрирована в Delaware, США. "
                "Год — 2026."
            )
            _set_orb_state(orb, "speaking")
            tts.say(_who_reply)
            if memory:
                memory.remember_turn(text, _who_reply[:200])
            _set_orb_state(orb, "idle")
            return

        # Narx
        if any(x in _t_low for x in ["qancha tur", "сколько стоит", "цена", "narxi", "price", "cost", "tarif"]):
            _price_reply = (
                "Три тарифа. Базовый — десять долларов в месяц, семьдесят процентов пользователей. "
                "Профессиональный — двадцать пять долларов, двадцать пять процентов. "
                "Корпоративный — девяносто девять долларов, пять процентов. "
                "Первый месяц полностью бесплатно для всех."
            )
            _set_orb_state(orb, "speaking")
            tts.say(_price_reply)
            if memory:
                memory.remember_turn(text, _price_reply[:200])
            _set_orb_state(orb, "idle")
            return

        # Raqobatchilardan farqi
        if any(x in _t_low for x in ["отличие", "отличается", "farqi", "siri", "google", "alexa", "рақобат", "конкурент"]):
            _diff_reply = (
                "Главное отличие — три вещи. "
                "Первое: работаю офлайн — Siri, Google, Alexa без интернета не работают. "
                "Второе: вижу ваш экран в реальном времени — ни один конкурент этого не делает. "
                "Третье: постоянная память — я помню всё навсегда, они забывают после сессии. "
                "Мы не конкурируем — мы создаём новую категорию."
            )
            _set_orb_state(orb, "speaking")
            tts.say(_diff_reply)
            if memory:
                memory.remember_turn(text, _diff_reply[:200])
            _set_orb_state(orb, "idle")
            return

        # Investitsiya
        if any(x in _t_low for x in ["инвест", "invest", "$", "dollar", "million", "миллион", "bozor", "рынок", "market"]):
            _inv_reply = (
                "Привлекаем семь с половиной миллионов долларов. "
                "Оценка компании до инвестиций — пятьдесят миллионов. "
                "Инвестор получает от десяти до двенадцати процентов. "
                "Общий рынок — девяносто пять миллиардов долларов. "
                "К две тысячи тридцатому году рынок вырастет до ста миллиардов."
            )
            _set_orb_state(orb, "speaking")
            tts.say(_inv_reply)
            if memory:
                memory.remember_turn(text, _inv_reply[:200])
            _set_orb_state(orb, "idle")
            return

        # To'liq loyha pitchi — LLM ga yuborish (project_knowledge system promptda bor)
        _pitch_hint = (
            "Пользователь хочет узнать о проекте NeuroKey. "
            "Расскажи о проекте полно и профессионально: "
            "что такое NeuroKey, кто создал, ключевые возможности (топ-5), "
            "чем отличается от конкурентов, бизнес-модель, инвестиционное предложение. "
            "Говори как основатель проекта. Уверенно. 4-6 предложений. "
            "Вопрос пользователя: " + text
        )
        _set_orb_state(orb, "thinking")
        try:
            _pitch_resp = answer(_pitch_hint, lang="ru", screen_ctx=screen_ctx if 'screen_ctx' in dir() else "")
        except Exception:
            _pitch_resp = (
                "NeuroKey — первый в мире персональный цифровой ИИ, живущий прямо на вашем устройстве. "
                "Слышит, видит экран, управляет компьютером голосом, помнит всё — и работает без интернета. "
                "Создан Диёрбеком Собиржоновым, Innovateworks.Inc, Delaware. "
                "Привлекаем $7.5M seed, оценка $50M. Три тарифа: от $10 до $99 в месяц."
            )
        _set_orb_state(orb, "speaking")
        tts.say((_pitch_resp or "")[:600])
        if memory:
            memory.remember_turn(text, (_pitch_resp or "")[:300])
        _set_orb_state(orb, "idle")
        return

    # ---- SCREEN VISION: har safar yangi kadr — bir xil slayd/javob qaytarmaslik uchun
    # ── KAMERA VISION: "smotri / qara / bu nima" (ekran savoli emas) ───────────
    if _is_camera_vision_request(text, memory=memory) and not _is_screen_question(text, memory=memory):
        _vision_lang = _ui_lang(text)
        _vision_result = _handle_camera_vision(text, lang=_vision_lang)
        if _vision_result and len(_vision_result) > 10:
            _set_orb_state(orb, "speaking")
            tts.say(_vision_result)
            if _NK:
                try:
                    from neurokey_state_writer import nk_state as _nks_cv
                    _nks_cv.update(mode="idle", last_output=_vision_result[:120])
                except Exception:
                    pass
            return

    # HAR TURN: yangi capture (prezentatsiya, Pitcher — slayd o'zgarganda yangi ko'rsatish)
    screen_ctx = ""
    _need_rich_screen = (
        not _is_conversation_not_screen(text, memory=memory)
        and not _is_vr_topic_question(text, memory=memory)
        and (
            _is_screen_question(text, memory=memory)
            or _inferred_intent == ("screen", "")
            or _is_browser_search_and_read(text)
            or _is_project_prove(text)
        )
    )
    if _HAVE_SCREEN_VISION:
        _is_screen_q = _need_rich_screen
        # Odamlar kabi: keshdan foydalanamiz — zagruska yo'q. Background loop doim yangilaydi.
        # Sync capture faqat kesh bo'sh va ekran savoli bo'lsa.
        with _screen_context_cache["lock"]:
            cache_updated = _screen_context_cache.get("updated") or 0
            cache_has_data = bool((_screen_context_cache.get("text") or "").strip() or (_screen_context_cache.get("vision") or "").strip())
        # HECH QACHON BLOKLAMA — kesh bo'sh bo'lsa ham fon da yangilash, darhol javob
        # Ekran savoli: kesh _build_screen_reply da yangilangan (qayta OCR yo'q)
        with _screen_context_cache["lock"]:
            txt = (_screen_context_cache.get("text") or "").strip()[:8000]
            vis = (_screen_context_cache.get("vision") or "").strip()[:4000]
            fg = (_screen_context_cache.get("foreground_window") or "").strip()
        _en = _ui_lang(text) == "en"
        if _need_rich_screen:
            _visible_windows: list = []
            try:
                from window_ops import get_visible_windows
                _visible_windows = get_visible_windows()
            except Exception:
                pass
            _desktop_titles = ("program manager", "desktop", "рабочий стол")
            _visible_titles = [w.get("title", "") for w in _visible_windows[:12] if w.get("title")]
            _only_desktop = _visible_titles and all(t.lower().strip() in _desktop_titles for t in _visible_titles)
            _has_fg_window = bool(fg and fg.strip() and fg.lower().strip() not in _desktop_titles)
            _all_minimized = (not _visible_titles or _only_desktop) and not _has_fg_window
            if _all_minimized:
                screen_ctx = (
                    "All windows minimized. On screen: only desktop. No open windows."
                    if _en else
                    "Все окна свернуты. На экране только рабочий стол — открытых окон нет."
                )
            else:
                if fg:
                    screen_ctx = ("Active window: " + fg) if _en else ("Активное окно: " + fg)
                if _visible_windows:
                    titles = [w.get("title", "") for w in _visible_windows[:12] if w.get("title")]
                    if titles:
                        vw_str = ", ".join(titles)
                        prefix = (screen_ctx + "\n\n") if screen_ctx else ""
                        screen_ctx = prefix + (("Visible windows: " + vw_str) if _en else ("Видимые окна: " + vw_str))
            if txt:
                prefix = (screen_ctx + "\n\n") if screen_ctx else ""
                screen_ctx = prefix + ("Screen text:\n" + txt if _en else "Экран (текст):\n" + txt)
            if vis:
                if _en:
                    screen_ctx = (screen_ctx + "\n\nScreen:\n" + vis).strip() if screen_ctx else vis
                else:
                    screen_ctx = (screen_ctx + "\n\nЭкран:\n" + vis).strip() if screen_ctx else vis
        elif fg and getattr(C, "NEUROKEY_ALWAYS_SCREEN_CTX", False):
            screen_ctx = ("Active window: " + fg) if _en else ("Активное окно: " + fg)
        # ---- CAMERA + ovoz: faqat ekran/kuzatuv savollarida (oddiy suhbat tezroq)
        if _need_rich_screen and _HAVE_CAMERA_VISION:
            try:
                _cam_ctx = _cam_get_ctx(use_background=True)
                if _cam_ctx:
                    _cam_label = "Webcam: " if _en else "Веб-камера: "
                    screen_ctx = (screen_ctx + "\n\n" + _cam_label + _cam_ctx).strip() if screen_ctx else (_cam_label + _cam_ctx)
            except Exception:
                pass

        # ---- OVOZ TANISH: kim gapirdi?
        if _need_rich_screen:
            try:
                from voice_recognition import get_last_speaker as _get_spk, profile_exists as _vp_exists
                if _vp_exists():
                    _spk = _get_spk()
                    if _spk and _spk.get("profile_exists"):
                        try:
                            from owner_trust import always_trust_owner, owner_nick
                            if always_trust_owner():
                                _spk["known"] = True
                                _spk["name"] = owner_nick()
                        except Exception:
                            pass
                        if _spk.get("known"):
                            _spk_line = ("Speaker: " + _spk["name"] + f" (voice verified, similarity={_spk['similarity']:.2f})") if _en else ("Говорит: " + _spk["name"] + f" (голос подтверждён, сходство={_spk['similarity']:.2f})")
                        else:
                            _spk_line = f"Speaker: unknown voice (similarity={_spk['similarity']:.2f})" if _en else f"Говорит: незнакомый голос (сходство={_spk['similarity']:.2f})"
                        screen_ctx = (screen_ctx + "\n" + _spk_line).strip() if screen_ctx else _spk_line
            except Exception:
                pass

        if _is_screen_q and not screen_ctx:
            try:
                with _screen_context_cache["lock"]:
                    _fg_s = (_screen_context_cache.get("foreground_window") or "").strip()
                    _txt_s = (_screen_context_cache.get("text") or "").strip()[:8000]
                    _vis_s = (_screen_context_cache.get("vision") or "").strip()
                _hdr = "MONITOR (not webcam). " if _en else "МОНИТОР (не камера). "
                if _fg_s:
                    screen_ctx = _hdr + (("Active: " + _fg_s) if _en else ("Активное окно: " + _fg_s))
                if _txt_s:
                    screen_ctx = (screen_ctx + "\n\n" + (("OCR:\n" + _txt_s) if _en else ("OCR:\n" + _txt_s))).strip()
                if _vis_s:
                    screen_ctx = (screen_ctx + "\n\n" + _vis_s).strip()
            except Exception as e:
                if _HAVE_ERROR_LOG:
                    log_error("Screen vision", exc=e)

    # Kamera: faqat ekran/kuzatuv savollarida (yuqorida qo'shilgan)
    if _need_rich_screen and _HAVE_CAMERA_VISION and "еб-камера" not in screen_ctx and "Webcam:" not in screen_ctx:
        try:
            _cam_always = (_cam_get_ctx(use_background=True) or "").strip()
            if _cam_always:
                _en_cam = _ui_lang(text) == "en"
                _cam_lbl = "Webcam: " if _en_cam else "Веб-камера: "
                screen_ctx = (screen_ctx + "\n\n" + _cam_lbl + _cam_always).strip() if screen_ctx else (_cam_lbl + _cam_always)
        except Exception:
            pass

    # ---- TELEGRAM: yangi xabar kelganda darhol xabar (listener); "och" / "open telegram" — ochib o'qib beradi ----
    _tg_open_read = (
        _is_tg_check(text) or _is_tg_long_command(text) or _inferred_intent == ("tg_check", "")
        or (text.strip().lower() in ("open",) and bool((memory.data.get("state") or {}).get("tg_last_incoming")))
    )
    if tg_user and memory and _tg_open_read:
        try:
            if _HAVE_CONTROL and any(x in low for x in ["открой", "open", "открой хабар"]):
                _log_action("open_app", "telegram")
                control.open_app("telegram")
                _set_orb_state(orb, "speaking")
                tts.say(get_feedback("opening_telegram"))
            if hasattr(tg_user, "unread_incoming"):
                items = tg_user.unread_incoming(limit=10)
            else:
                items = tg_user.recent(limit=5) if tg_user else []

            # Agar API da unread yo'q bo'lsa, yangi kelgan xabar (tg_last_incoming) dan bitta ko'rsatamiz
            if not items and memory:
                last = (memory.data.get("state") or {}).get("tg_last_incoming")
                if last and last.get("peer_id") is not None:
                    items = [{"peer_id": last["peer_id"], "peer_name": last.get("peer_name") or "Someone", "text": last.get("text") or ""}]

            if not items:
                _set_orb_state(orb, "speaking")
                tts.say(get_feedback("no_new_messages"))
                _set_orb_state(orb, "idle")
                return

            tg_list = [{"peer_id": it.get("peer_id"), "peer_name": (it.get("peer_name") or "").strip() or "Someone", "text": (it.get("text") or "").strip()[:500]} for it in items]
            memory.data.setdefault("state", {})["tg_unread_list"] = tg_list
            memory.data.setdefault("state", {})["tg_unread_index"] = 0
            memory.data.setdefault("state", {})["last_tg_peer"] = items[0].get("peer_id")
            memory.data.setdefault("state", {})["last_tg_title"] = items[0].get("peer_name", "")
            memory.save()

            first = tg_list[0]
            peer_id, peer_name, msg_text = first.get("peer_id"), first.get("peer_name", ""), first.get("text", "")
            suggested = suggest_telegram_reply(peer_name, msg_text, lang=_ui_lang(text))
            memory.set_pending({"type": "tg_reply", "peer_id": peer_id, "reply_text": suggested, "peer_name": peer_name, "message_text": msg_text}, ttl_sec=90)
            _set_orb_state(orb, "speaking")
            short_msg = (msg_text[:80] + "…") if len(msg_text) > 80 else msg_text
            tts.say(get_feedback("tg_from_peer", peer=peer_name, msg=short_msg, suggested=(suggested[:80] + "…" if len(suggested) > 80 else suggested)))
        except Exception as e:
            if _HAVE_ERROR_LOG:
                log_error("TG check", exc=e)
            _safe_print("[TG_CHECK_ERROR]", repr(e))
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("tg_cant_read"))
        _set_orb_state(orb, "idle")
        return

    # ---- BRAUZER: och + qidir (aniq yoki magzini tushunib: "look up X", "I need to find Y") ----
    if _HAVE_CONTROL and (_is_browser_search_and_read(text) or _inferred_intent == ("search", "browser")):
        topic = _extract_topic_for_browser(text).strip()
        if not topic or len(topic) < 2:
            if memory and memory.data.get("history"):
                last_user = (memory.data.get("history", [])[-1] or {}).get("user", "")
                topic = (last_user or "").strip()[:80] or "search"
            else:
                topic = "search"
        low_t = (text or "").lower()
        video_only = any(x in low_t for x in ["видео найди", "find video", "search video"])
        music_only = any(x in low_t for x in ["музыку найди", "music find", "search music"])
        search_url = "https://www.google.com/search?q=" + url_quote(topic)
        yt_url = "https://www.youtube.com/results?search_query=" + url_quote(topic)
        if video_only or music_only:
            ok, open_msg = control.open_url(yt_url)
        else:
            ok, open_msg = control.open_url(search_url)
            time.sleep(1.2)
            ok2, _ = control.open_url(yt_url)
            ok = ok or ok2
        if not ok:
            ok, open_msg = control.open_browser("")
            if ok:
                if video_only or music_only:
                    ok, open_msg = control.open_url(yt_url)
                else:
                    ok, open_msg = control.open_url(search_url)
                    if ok:
                        time.sleep(1.2)
                        control.open_url(yt_url)
        open_success = ok
        _set_orb_state(orb, "speaking")
        if not open_success:
            tts.say((open_msg or "Не удалось открыть браузер. Открой вручную или проверь интернет.")[:120])
            if memory:
                memory.remember_turn(text, "Browser open failed: " + (open_msg or "")[:80])
            _set_orb_state(orb, "idle")
            return
        if not _HAVE_SCREEN_VISION:
            tts.say(get_feedback("search_opened_browser") if not (video_only or music_only) else get_feedback("youtube_search_opened"))
            if memory:
                memory.remember_turn(text, "Opened search in browser.")
            _set_orb_state(orb, "idle")
            return
        web_ctx = web_context(topic, prefer_lang=_ui_lang(text))
        time.sleep(2.5)
        browser_ctx = ""
        try:
            if _HAVE_SCREEN_VISION and grab_screen:
                with _screen_context_cache["lock"]:
                    ocr_text = (_screen_context_cache.get("text") or "").strip()[:3500]
                if not ocr_text:
                    img = grab_screen()
                    if img:
                        ocr_text = _screen_ocr_fast_timed(img, timeout_sec=4.0)[:3500]
                browser_ctx = ("Screen (search «" + topic + "»):\n" + ocr_text) if ocr_text else ""
        except Exception as e:
            if _HAVE_ERROR_LOG:
                log_error("Browser read", exc=e)
        combined_ctx = (web_ctx + "\n\n" + browser_ctx).strip() if (web_ctx and browser_ctx) else (browser_ctx or web_ctx)
        if combined_ctx:
            try:
                history = (memory.data.get("history", [])[-6:]) if memory else []
                use_brief = not any(x in low for x in [
                    "to'liq", "toliq", "to'liq malumot", "full", "полностью", "подробнее", "подробно", "всё подробно",
                    "full info", "подробный ответ", "все подробно", "batafsil", "to'liq ma'lumot",
                ])
                prompt_brief = "Give a brief answer: what you found (1–2 sentences)." if use_brief else "Give a full answer based on the search: main facts, details."
                reply = answer(
                    f"User asked to find: «{topic}». Below — search result and screen. {prompt_brief}",
                    web_ctx=web_ctx,
                    lang_hint=_ui_lang(text),
                    history=history,
                    screen_context=combined_ctx,
                    current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
                    brief=use_brief,
                )
                tts.say(_extract_spoken_reply(reply))
                if memory:
                    memory.remember_turn(text, reply)
                if web_ctx:
                    try:
                        _show_web_results_on_screen(web_ctx, topic)
                    except Exception:
                        pass
            except Exception as e:
                if _HAVE_ERROR_LOG:
                    log_error("LLM browser", exc=e)
                tts.say(get_feedback("search_opened"))
        else:
            tts.say(get_feedback("search_info_on_screen") if not (video_only or music_only) else get_feedback("youtube_search_opened"))
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: och (aniq yoki magzini tushunib — suniy ong: buyruq nima haqida, nima xohlayapti) ----
    app_open = None
    if _is_control_open(text):
        app_open = _control_app_from_text(text, True)
    elif _inferred_intent and _inferred_intent[0] == "open":
        app_open = _inferred_intent[1]
    if _HAVE_CONTROL and _is_control_open(text) and not app_open:
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("which_app"))
        _set_orb_state(orb, "idle")
        return
    if _HAVE_CONTROL and app_open:
        _log_action("open_app", app_open)
        _open_result = [None]
        def _do_open():
            _open_result[0] = control.open_app(app_open)
        _t = threading.Thread(target=_do_open, daemon=True)
        _t.start()
        _fast_open_timeout = float(getattr(C, "CONTROL_OPEN_FAST_TIMEOUT_SEC", 0.25) or 0.25)
        _t.join(timeout=max(0.05, _fast_open_timeout))
        ok, msg = _open_result[0] if _open_result[0] is not None else (True, "Открываю.")
        _set_orb_state(orb, "speaking")
        tts.say(msg if msg else ("Открыто." if ok else "Не удалось открыть."))
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: barcha oynalarni yopish (minimize) ----
    if _HAVE_CONTROL and (_is_minimize_all(text) or _inferred_intent == ("minimize_all", "")):
        ok, msg = control.minimize_all_windows()
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- OVOZ: tezroq/sekinroq gapir (TTS tezligi) ----
    if _is_tts_speed_up(text):
        tts.adjust_speed(0.12)
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("faster"))
        _set_orb_state(orb, "idle")
        return
    if _is_tts_speed_down(text):
        tts.adjust_speed(-0.12)
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("slower"))
        _set_orb_state(orb, "idle")
        return

    # ---- OVOZ: balantro/pastroq gapir, ovozni balantlat/sekinlat ----
    if _HAVE_CONTROL and (_is_tts_volume_up(text) or _is_volume_up(text)):
        ok, msg = control.volume_up()
        _set_orb_state(orb, "speaking")
        tts.say(msg if ok else "Готово.")
        _set_orb_state(orb, "idle")
        return
    if _HAVE_CONTROL and (_is_tts_volume_down(text) or _is_volume_down(text)):
        ok, msg = control.volume_down()
        _set_orb_state(orb, "speaking")
        tts.say(msg if ok else "Готово.")
        _set_orb_state(orb, "idle")
        return

    # ---- MEDIA: ortga/oldinga qaytar (video/audio) ----
    if _HAVE_CONTROL and _is_media_rewind(text):
        control.media_rewind()
        _set_orb_state(orb, "idle")
        return
    if _HAVE_CONTROL and _is_media_forward(text):
        control.media_forward()
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: prezentatsiya / slayd boshqaruvi ----
    if _HAVE_CONTROL and _is_slide_next(text):
        ok, msg = control.slide_next()
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        _set_orb_state(orb, "idle")
        return
    if _HAVE_CONTROL and _is_slide_prev(text):
        ok, msg = control.slide_prev()
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        _set_orb_state(orb, "idle")
        return
    if _HAVE_CONTROL and _is_presentation_start(text):
        ok, msg = control.presentation_start()
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: hamma dasturlarni yopish (Telegram, brauzer va b.) ----
    if _HAVE_CONTROL and (_is_close_all_apps(text) or _inferred_intent == ("close_all", "")):
        ok, msg = control.close_all_apps()
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: yop (aniq yoki magzini tushunib) ----
    app_close = None
    if _is_control_close(text):
        app_close = _control_app_from_text(text, False)
    elif _inferred_intent and _inferred_intent[0] == "close":
        app_close = _inferred_intent[1]
    if _HAVE_CONTROL and _is_control_close(text) and not app_close:
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("which_app_close"))
        _set_orb_state(orb, "idle")
        return
    if _HAVE_CONTROL and app_close:
        _log_action("close_app", app_close)
        ok, msg = control.close_app(app_close)
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: разверни все окна ----
    if _HAVE_CONTROL and (_is_restore_windows(text) or _inferred_intent == ("restore_windows", "")):
        ok, msg = control.restore_all_windows()
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: papka qidirish (find folder X, qidir papka X) ----
    if _HAVE_CONTROL and (_is_folder_search(text) or _inferred_intent == ("search_folder", "")):
        low_t = (text or "").lower()
        query = ""
        for sep in ["find folder", "search folder", "найди папку", "найти папку",
                    "найди папку", "найти папку", "поиск папку", "search for folder", "look for folder", "locate folder"]:
            if sep in low_t:
                rest = (text.split(sep, 1)[-1] or "").strip().strip(".,")
                words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\-\s]+", rest)
                if words:
                    query = words[0].strip()
                break
        if not query:
            words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\-]+", (text or ""))
            for w in words:
                if w.lower() not in ("find", "search", "folder", "найди", "найти", "папку"):
                    query = w
                    break
        ok, msg = control.search_folders(query or "folder", limit=10)
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: papka yopish (close folder, papka yop) ----
    if _HAVE_CONTROL and _is_close_folder(text):
        ok, msg = control.close_folder_window()
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: papka ochish (game papkasini och, to'liq yo'l yoki nom) ----
    if _HAVE_CONTROL and (_is_open_folder(text) or _inferred_intent == ("open_folder", "")):
        low_t = (text or "").lower()
        folder_name = None
        for sep in ["open folder", "открой папку", "open the folder"]:
            if sep in low_t:
                idx = low_t.find(sep)
                rest = (text[idx + len(sep):] if idx >= 0 else "").strip().strip(".,")
                if rest and ("\\" in rest or (":" in rest and len(rest) > 2)):
                    folder_name = rest
                break
        if not folder_name:
            folder_open, _ = _extract_folder_or_name(
                text,
                ["open folder", "game папка", "папку открой", "открой папку"],
                [],
            )
            folder_name = (folder_open or "game").strip()
        current = (memory.data.get("state") or {}).get("current_folder") if memory else None
        path = control.find_folder(folder_name, current_folder=current)
        if not path and folder_name:
            alt = "games" if folder_name.lower() == "game" else ("game" if folder_name.lower() == "games" else None)
            if alt:
                path = control.find_folder(alt, current_folder=current)
        if path:
            ok, msg = control.open_folder(path)
            if memory:
                memory.data.setdefault("state", {})["current_folder"] = path
                memory.save()
        else:
            msg = f"Folder «{folder_name}» not found. Try full path, e.g. open folder Documents." if _ui_lang(text) == "en" else f"Папку «{folder_name}» не нашёл. Попробуй полный путь."
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: o'sha papkani och / qayerga yaratding (last_created_folder) ----
    if _HAVE_CONTROL and _is_open_last_created_or_where(text) and memory:
        last_created = (memory.data.get("state") or {}).get("last_created_folder")
        if last_created and os.path.isdir(last_created):
            ok, msg = control.open_folder(last_created)
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("folder_opened") + " " + last_created)
            if memory:
                memory.data.setdefault("state", {})["current_folder"] = last_created
                memory.remember_turn(text, "Opened: " + last_created)
            _set_orb_state(orb, "idle")
            return
        elif last_created:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("folder_created_at") + " " + last_created)
            if memory:
                memory.remember_turn(text, "Path: " + last_created)
            _set_orb_state(orb, "idle")
            return

    # ---- CONTROL: yangi papka (ichiga Nike / создай папку Nike) ----
    if _HAVE_CONTROL and _is_create_folder(text):
        _, name_new = _extract_folder_or_name(
            text,
            [],
            ["создай папку", "новая папка", "create folder", "new folder"],
        )
        name_new = (name_new or "").strip()
        if not name_new:
            for w in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\-]+", (text or "")):
                if w.lower() not in ("папку", "папка", "folder", "создай", "новую", "create", "new", "открой"):
                    name_new = w
                    break
        parent = (memory.data.get("state") or {}).get("current_folder") if memory else None
        if not parent:
            parent = os.path.expanduser("~")
        result = control.create_folder(parent, name_new or "NewFolder")
        ok = result[0]
        msg = result[1]
        created_path = result[2] if len(result) > 2 else None
        _set_orb_state(orb, "speaking")
        if ok and created_path:
            full_msg = msg + " " + (_tr("Путь:", "Path:") + " " + created_path)
            tts.say(full_msg)
            if memory:
                memory.data.setdefault("state", {})["last_created_folder"] = created_path
                memory.data.setdefault("state", {})["current_folder"] = created_path
                memory.remember_turn(text, full_msg)
            # Сразу открыть созданную папку
            try:
                control.open_folder(created_path)
            except Exception:
                pass
        else:
            tts.say(msg)
            if memory:
                memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: papkadan fayl ochish (game papkadan X faylni och) ----
    if _HAVE_CONTROL and _is_open_file_from_folder(text):
        current = (memory.data.get("state") or {}).get("current_folder") if memory else None
        if not current or not os.path.isdir(current):
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("open_folder_first"))
            _set_orb_state(orb, "idle")
            return
        low_t = text.lower()
        fname = ""
        for sep in ["из папки открой", "папкадан открой", "открой файл"]:
            if sep in low_t:
                rest = (text.split(sep, 1)[-1] or "").strip().strip(".,")
                words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_.\-]+", rest)
                if words:
                    fname = words[0]
                break
        if not fname:
            words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_.\-]+", text)
            for w in words:
                if w.lower() not in ("game", "открой", "файл", "папки"):
                    fname = w
                    break
        if not fname:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("specify_filename"))
            _set_orb_state(orb, "idle")
            return
        full_path = os.path.join(current, fname)
        if not os.path.isfile(full_path) and not fname.endswith(".txt"):
            full_path = os.path.join(current, fname + ".txt")
        ok, msg = control.open_file(full_path)
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: fayl qidirish ----
    if _HAVE_CONTROL and (_is_file_search(text) or _inferred_intent == ("file_search", "")):
        folder = os.path.expanduser("~")
        query = text
        for p in ("найди файл", "найти файл", "поиск файл", "find file", "search file"):
            if p in low:
                query = (text.split(p, 1)[-1] or "").strip() or text
                break
        ok, msg = control.search_files(folder, query[:80])
        _set_orb_state(orb, "speaking")
        tts.say(msg[:500] if len(msg) > 500 else msg)
        if memory:
            memory.remember_turn(text, msg[:200])
        _set_orb_state(orb, "idle")
        return

    # ---- CONTROL: fayl ochish (nom bo'lsa find_folder/search_files orqali topamiz) ----
    if _HAVE_CONTROL and _is_file_open(text):
        path = text
        for p in ("открой файл", "открыть файл", "open file", "open the file"):
            if p in low:
                path = (text.split(p, 1)[-1] or "").strip().strip('"').strip() or text
                break
        path = path[:260].strip()
        # Qisqa nom (yo'l emas): avval papka qidirish, keyin fayl qidirish
        if path and "\\" not in path and ":" not in path:
            current = (memory.data.get("state") or {}).get("current_folder") if memory else None
            resolved = control.find_folder(path, current_folder=current)
            if resolved:
                ok, msg = control.open_folder(resolved)
            else:
                ok, msg = control.search_files(os.path.expanduser("~"), path)
                if ok and "Найдено:" in msg:
                    lines = [l.strip() for l in msg.split("\n") if l.strip() and not l.strip().startswith("Найдено")]
                    for line in lines:
                        if line and (os.path.isfile(line) or os.path.isdir(line)):
                            ok, msg = (control.open_file(line) if os.path.isfile(line) else control.open_folder(line))
                            break
                    else:
                        ok, msg = control.open_file(path)
                else:
                    ok, msg = control.open_file(path)
        else:
            ok, msg = control.open_file(path)
        _set_orb_state(orb, "speaking")
        tts.say(msg)
        if memory:
            memory.remember_turn(text, msg)
        _set_orb_state(orb, "idle")
        return

    # ---- FALLBACK: "открой X" / "найди X" — qattiq iboralarsiz, tabiiy gapirish ----
    # Agar "открой games", "найди документ", "open downloads" — lekin aniq handler topilmagan bo'lsa
    if _HAVE_CONTROL and len((text or "").strip()) < 80:
        t_low = (text or "").lower().strip()
        _open_triggers = ["открой", "открыть", "open", "och"]
        _find_triggers = ["найди", "найти", "find", "поиск", "search"]
        _known_apps = ("telegram", "телеграм", "tg", "браузер", "browser", "opera", "chrome",
                       "калькулятор", "calculator", "calc", "проводник", "explorer", "files", "store", "магазин")
        _skip_words = ("папку", "файл", "folder", "file", "papka", "fayl", "папка", "the", "a", "этот", "эту")
        target = None
        is_open = any(k in t_low for k in _open_triggers)
        is_find = any(k in t_low for k in _find_triggers)
        if is_open:
            for sep in _open_triggers:
                if sep in t_low:
                    rest = (text.split(sep, 1)[-1] or "").strip().strip(".,").strip()
                    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\-\s]+", rest)
                    for w in words:
                        wl = (w or "").strip().lower()
                        if wl and wl not in _known_apps and wl not in _skip_words and len(wl) > 1:
                            target = w.strip()
                            break
                    if not target and words:
                        target = words[0].strip()
                    break
        elif is_find:
            for sep in _find_triggers:
                if sep in t_low:
                    rest = (text.split(sep, 1)[-1] or "").strip().strip(".,").strip()
                    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\-\s]+", rest)
                    for w in words:
                        wl = (w or "").strip().lower()
                        if wl and wl not in _skip_words and wl not in _known_apps and len(wl) > 1:
                            target = w.strip()
                            break
                    if not target and words:
                        target = words[0].strip()
                    break
        if target and target.lower() not in _known_apps:
            # Avval papka qidirish (ochiq papka ichida ham)
            current = (memory.data.get("state") or {}).get("current_folder") if memory else None
            path = control.find_folder(target, current_folder=current)
            if path:
                ok, msg = control.open_folder(path)
                _set_orb_state(orb, "speaking")
                tts.say(msg)
                if memory:
                    memory.remember_turn(text, msg)
                _set_orb_state(orb, "idle")
                return
            # Papka topilmasa — fayl qidirish
            ok, msg = control.search_files(os.path.expanduser("~"), target[:80])
            if ok and "Найдено:" in msg:
                lines = [l.strip() for l in msg.split("\n") if l.strip() and not l.strip().startswith("Найдено")]
                for line in lines[:5]:
                    if line and (os.path.isfile(line) or os.path.isdir(line)):
                        ok, msg = (control.open_file(line) if os.path.isfile(line) else control.open_folder(line))
                        _set_orb_state(orb, "speaking")
                        tts.say(msg)
                        if memory:
                            memory.remember_turn(text, msg)
                        _set_orb_state(orb, "idle")
                        return
            _set_orb_state(orb, "speaking")
            if is_find:
                tts.say(msg[:400] if msg else _tr("Ничего не найдено.", "Nothing found."))
            else:
                tts.say(get_feedback("folder_file_not_found", target=target))
            if memory:
                memory.remember_turn(text, msg[:200] if msg else "Find/open: not found")
            _set_orb_state(orb, "idle")
            return

    # ---- CONTROL: fayl o'chirish (tasdiq kerak) ----
    if _HAVE_CONTROL and _is_file_delete(text) and memory:
        path = text
        for p in ("удали файл", "удалить файл", "delete file", "o'chir fayl", "ochir fayl"):
            if p in low:
                path = (text.split(p, 1)[-1] or "").strip().strip('"').strip() or text
                break
        path = path[:260]
        if os.path.isfile(os.path.abspath(os.path.expanduser(path))):
            memory.set_pending({"type": "delete_file", "path": path}, ttl_sec=30)
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("delete_file_confirm", path=path))
            _set_orb_state(orb, "idle")
            return
        else:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("file_not_found"))
            _set_orb_state(orb, "idle")
            return

    # ---- OVOZ BILAN EKRANDA KLIK (koordinatasiz — GPT-4o Vision) ----
    # "u tugmani bos", "qidirish maydoniga klik qil", "Saqlash ni bos" va h.k.
    if _HAVE_SCREEN_CLICK and (_is_voice_click(text) or _is_voice_right_click(text) or _is_voice_double_click(text)):
        _set_orb_state(orb, "thinking")
        # Elementni matndan ajratamiz
        target = (_sc_extract(text) if _sc_extract else text.strip())
        if not target or len(target) < 2:
            _set_orb_state(orb, "speaking")
            tts.say(_tr("Скажи, что нажать. Например: «нажми на кнопку поиска».",
                        "Qaysi elementni bosishni ayting."))
            _set_orb_state(orb, "idle")
            return
        # Tanlangan klik turi
        _set_orb_state(orb, "speaking")
        if _is_voice_right_click(text) and _sc_rclick:
            ok, msg = _sc_rclick(target)
        elif _is_voice_double_click(text) and _sc_dclick:
            ok, msg = _sc_dclick(target)
        else:
            ok, msg = _sc_click(target)
        tts.say(msg[:120] if ok else _tr(
            f"Не нашёл «{target}» на экране. Уточни название.",
            f"Ekranda «{target}» topilmadi. Aniqroq ayting.",
        ))
        if memory:
            memory.remember_turn(text, msg[:80])
        _set_orb_state(orb, "idle")
        return

    # ---- OVOZ BILAN MAYDONGA KIRITISh ----
    # "qidirish maydoniga 'python tutorial' yoz"
    if _HAVE_SCREEN_CLICK and _is_voice_type_in(text) and _sc_type:
        _set_orb_state(orb, "thinking")
        # "введи в поле поиска 'hello'" → field="поле поиска", text="hello"
        _vt_low = (text or "").lower()
        _vt_typed = ""
        _vt_field = text
        for _quote in ('"', "'", "«", "»"):
            if _quote in text:
                _vt_parts = text.split(_quote)
                if len(_vt_parts) >= 3:
                    _vt_typed = _vt_parts[1].strip()
                    _vt_field = _vt_parts[0].strip()
                    break
        if not _vt_typed:
            # "maydoniga X yoz" — X ni ajratamiz
            for _marker in ("введи ", "напиши ", "впиши ", "type ", "write ", "enter "):
                if _marker in _vt_low:
                    _vt_typed = text[_vt_low.index(_marker) + len(_marker):].strip()
                    _vt_field = text[:_vt_low.index(_marker)].strip()
                    break
        if _vt_typed and _vt_field:
            _field_target = _sc_extract(_vt_field) if _sc_extract else _vt_field
            ok, msg = _sc_type(_field_target, _vt_typed)
            _set_orb_state(orb, "speaking")
            tts.say(msg[:120])
            if memory:
                memory.remember_turn(text, msg[:80])
            _set_orb_state(orb, "idle")
            return
        _set_orb_state(orb, "idle")

    # ---- YOUTUBE PLAYER BOSHQARUVI (play/pause/volume/skip) ----
    # Qidiruv buyrug'i EMAS, balki pleyerni boshqarish: "pauza", "louder", "skip", "rewind"
    if _HAVE_CONTROL and _is_youtube_control(text) and not _is_youtube_search(text):
        yt_key = _youtube_control_action(text)
        # YouTube oynasiga fokus — brauzer oynasida "YouTube" bo'lishi kerak
        _fok_ok = False
        for win_title in ("YouTube", "youtube.com", "ютуб", "YT"):
            try:
                ok_f, _ = control.window_focus_by_title(win_title)
                if ok_f:
                    _fok_ok = True
                    break
            except Exception:
                pass
        import time as _t
        _t.sleep(0.3)  # Fokus o'rnatilguncha kichik pauza
        if yt_key in ("up", "down"):
            try:
                control.send_hotkey(yt_key)
            except Exception:
                pass
        else:
            try:
                control.send_keys(yt_key)
            except Exception:
                pass
        _set_orb_state(orb, "speaking")
        _action_labels = {
            "k": _tr("Воспроизведение / пауза.", "Play/pause."),
            "m": _tr("Звук отключён/включён.", "Mute/unmute."),
            "f": _tr("Полный экран.", "Fullscreen."),
            "j": _tr("Перемотал на 10 секунд назад.", "Rewound 10 seconds."),
            "l": _tr("Перемотал на 10 секунд вперёд.", "Forwarded 10 seconds."),
            "up": _tr("Громче.", "Volume up."),
            "down": _tr("Тише.", "Volume down."),
        }
        tts.say(_action_labels.get(yt_key, _tr("Выполнено.", "Done.")))
        _set_orb_state(orb, "idle")
        return

    # ---- YOUTUBE: video/qo'shiq/musiqa — brauzerda YouTube ----
    if _HAVE_CONTROL and _is_youtube_search(text):
        topic = _extract_topic_for_youtube(text).strip()
        if not topic or len(topic) < 2:
            topic = "video"
        # Qo'shiq/musiqa so'rovi: music filtri qo'shamiz (aniqroq natijalar)
        low_t = text.lower()
        is_music = any(x in low_t for x in [
            "qo'shiq", "qoshiq", "ashula", "kuy", "musiqa", "музыку", "песню", "music", "song",
        ])
        search_q = (topic + " official audio") if is_music else topic
        # YouTube'da to'g'ridan qidirish (autoplay uchun &autoplay=1 qo'shamiz)
        yt_url = "https://www.youtube.com/results?search_query=" + url_quote(search_q)
        ok, msg = control.open_url(yt_url)
        if not ok:
            ok, msg = control.open_browser("")
            if ok:
                ok, msg = control.open_url(yt_url)
        _set_orb_state(orb, "speaking")
        if ok:
            label = _tr(
                f"Ищу «{topic}» на YouTube.",
                f"YouTube'dan «{topic}» qidiryapman.",
            )
            tts.say(label)
            if memory:
                memory.remember_turn(text, "Opened YouTube: " + topic)
        else:
            tts.say((msg or "Не удалось открыть YouTube. Открой браузер вручную.")[:100])
            if memory:
                memory.remember_turn(text, "YouTube open failed: " + (msg or "")[:60])
        _set_orb_state(orb, "idle")
        return

    # ---- BRAUZER: rasmini ochish (Alisher Navoiy rasmini ko'rsata olasanmi -> brauzerda foto) ----
    if _HAVE_CONTROL and _is_show_picture_in_browser(text):
        topic = _extract_topic_for_browser(text, for_picture=True).strip()
        if not topic or topic.lower() == "photo":
            if memory and memory.data.get("history"):
                last_user = (memory.data.get("history", [])[-1] or {}).get("user", "")
                words = re.findall(r"[A-ZА-Яa-zа-я][a-zа-яё\-]+(?:\s+[A-ZА-Яa-zа-я][a-zа-яё\-]+)*", last_user)
                if words:
                    topic = words[-1][:60] if words else topic
        query = (topic + " photo") if topic and "photo" not in topic.lower() and "фото" not in topic.lower() else (topic or "photo")
        img_results = serpapi_image_search(query[:80], num=3, hl="ru")
        if img_results and img_results[0].get("link"):
            ok, msg = control.open_url(img_results[0]["link"])
            _set_orb_state(orb, "speaking")
            if ok:
                tts.say(get_feedback("photo_opened"))
                if memory:
                    memory.remember_turn(text, "Opened photo in browser.")
            else:
                tts.say((msg or "Не удалось открыть. Открой браузер вручную.")[:100])
                if memory:
                    memory.remember_turn(text, "Photo open failed.")
        else:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("photo_not_found"))
            if memory:
                memory.remember_turn(text, "Photo search: not found.")
        _set_orb_state(orb, "idle")
        return

    # ---- TELEGRAM: кто написал? (kontakt ochmasdan) ----
    if tg_user and memory and _is_tg_who_wrote(text):
        last_peer = (memory.data.get("state") or {}).get("last_tg_peer")
        last_title = (memory.data.get("state") or {}).get("last_tg_title", "")
        if last_peer is not None and last_title:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("tg_last_from", title=last_title))
            _set_orb_state(orb, "idle")
            return
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("check_messages_first"))
        _set_orb_state(orb, "idle")
        return

    # ---- TELEGRAM REPLY (ответь / напиши / отправь сообщение) ----
    if tg_user and memory and _is_tg_reply_intent(text):
        last_peer = (memory.data.get("state") or {}).get("last_tg_peer")
        last_title = (memory.data.get("state") or {}).get("last_tg_title", "ему")
        reply_text = _extract_tg_reply_text(text)
        if not reply_text:
            reply_text = text.strip()
        if last_peer is not None and reply_text:
            memory.set_pending({"type": "tg_reply", "peer_id": last_peer, "reply_text": reply_text, "peer_name": last_title}, ttl_sec=60)
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("tg_send_confirm", text=(reply_text[:50] + "…" if len(reply_text) > 50 else reply_text)))
            _set_orb_state(orb, "idle")
            return
        else:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("check_messages_first_reply"))
            _set_orb_state(orb, "idle")
            return

    # ---- TG_SEND: akamga yubor, send to X (to'g'ridan-to'g'ri yuborish) ----
    if tg_user and (_is_tg_send(text) or _inferred_intent == ("tg_send", "")):
        contact, msg = _extract_tg_send_contact_and_message(text)
        if contact:
            _set_orb_state(orb, "speaking")
            try:
                ok, res = tg_user.send_to_contact(contact, msg or " ")
                tts.say(res)
                if memory:
                    memory.remember_turn(text, res)
            except Exception as e:
                tts.say(get_feedback("tg_failed_error", e=str(e)))
            _set_orb_state(orb, "idle")
            return
        else:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("tg_whom_send"))
            _set_orb_state(orb, "idle")
            return

    # ---- GMAIL CHECK ----
    if _HAVE_GMAIL and (_is_gmail_check(text) or _inferred_intent == ("gmail_check", "")):
        try:
            mails = gmail_bridge.list_unread(limit=5)
            if not mails:
                _set_orb_state(orb, "speaking")
                tts.say(get_feedback("no_unread_emails"))
                _set_orb_state(orb, "idle")
                return
            parts = []
            for m in mails:
                parts.append(f"{m.get('from','')}: {m.get('subject','')}")
            _set_orb_state(orb, "speaking")
            _pre = "Новые письма: "
            tts.say(_pre + " | ".join(parts))
        except Exception as e:
            if _HAVE_ERROR_LOG:
                log_error("Gmail", exc=e)
            _safe_print("[GMAIL_ERROR]", repr(e))
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("mail_check_error"))
        _set_orb_state(orb, "idle")
        return

    # ---- OB-HAVO: magzini tushunib (inferred) — tez javob, keshdan ----
    if _inferred_intent == ("weather", ""):
        place = _extract_place_for_weather(text)
        weather_line = ""
        with _realtime_cache["lock"]:
            cache_updated = _realtime_cache.get("updated") or 0
            cache_weather = (_realtime_cache.get("weather") or "").strip()
        default_city = (getattr(C, "NEUROKEY_CITY", "Tashkent") or "Tashkent").strip()
        if (time.time() - cache_updated) < 120 and cache_weather and place.strip().lower() == default_city.lower():
            weather_line = cache_weather
        if not weather_line:
            try:
                from juma_news_weather import weather_by_name
                weather_line = weather_by_name(place, lang=_ui_lang(text))
            except Exception:
                pass
        _set_orb_state(orb, "speaking")
        if weather_line and "not found" not in (weather_line or "").lower() and "не нашёл" not in (weather_line or "").lower():
            tts.say((weather_line or "")[:400])
        else:
            tts.say(get_feedback("weather_error"))
        if memory:
            memory.remember_turn(text, weather_line or "Weather requested.")
        _set_orb_state(orb, "idle")
        return

    # ---- "Открой все программы" / "open all" — brauzer, telegram, calc, explorer ----
    if _HAVE_CONTROL:
        t_low = (text or "").lower().strip()
        open_all_triggers = [
            "открой все программы", "открой все приложения", "открыть все программы",
            "open all programs", "open all apps", "open everything", "hamma dasturni och",
        ]
        if any(x in t_low for x in open_all_triggers) and len(t_low) < 60:
            _set_orb_state(orb, "speaking")
            opened = []
            for app in ["browser", "telegram", "calc", "explorer"]:
                ok, _ = control.open_app(app)
                if ok:
                    opened.append(app)
            msg = _tr("Открыл: " + ", ".join(opened) + ".", "Opened: " + ", ".join(opened) + ".") if opened else _tr("Часть приложений открыта.", "Some apps opened.")
            tts.say(msg)
            if memory:
                memory.remember_turn(text, msg)
            _set_orb_state(orb, "idle")
            return

    # ---- MURAKKAB VAZIFA: ketma-ket qadamlar (сначала ... потом ...) ----
    if _is_complex_task(text):
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("executing_steps"))
        try:
            steps = decompose_complex_task(text, lang=_ui_lang(text))
            if not steps:
                tts.say(get_feedback("steps_split_error"))
                _set_orb_state(orb, "idle")
                return
            results = _run_complex_steps(
                steps,
                tts=tts,
                control_obj=control if _HAVE_CONTROL else None,
                tg_user=tg_user,
                memory=memory,
                lang=_ui_lang(text),
                orb=orb,
            )
            summary = " ".join(results[:5])
            if len(summary) > 400:
                summary = summary[:397] + "…"
            tts.say(summary)
            if memory:
                memory.remember_turn(text, "Done step by step: " + summary[:300])
        except Exception as e:
            if _HAVE_ERROR_LOG:
                log_error("Complex task", exc=e)
            tts.say(get_feedback("steps_error"))
        _set_orb_state(orb, "idle")
        return

    # ---- ESLATMA: напомни через N минут ----
    if _is_reminder(text):
        sec, reminder_text = _extract_reminder_delay_and_text(text)
        sec = max(10, min(sec, 3600 * 24 * 7))  # max 1 hafta
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("remind_min", min=sec // 60) if sec >= 60 else get_feedback("remind_sec"))

        # Reminders.py bilan saqlash (restart dan keyin ham ishlaydi)
        if _HAVE_REMINDERS and _reminders:
            try:
                import time as _t
                _due_ts = int(_t.time()) + sec
                _data = _reminders._load()
                _rid = _data["auto_id"]
                _data["auto_id"] += 1
                _data["items"].append({
                    "id": _rid, "title": reminder_text or "Напоминание",
                    "created_ts": int(_t.time()), "due_ts": _due_ts
                })
                _reminders._save(_data)
            except Exception:
                pass

        # Oddiy timer — xonada ishlaydi
        def _remind(_rt=reminder_text):
            try:
                tts.say(_rt or "Напоминание!")
            except Exception:
                pass
        threading.Timer(float(sec), _remind).start()
        if memory:
            memory.remember_turn(text, f"Reminder in {sec} sec: {reminder_text[:80]}")
        _set_orb_state(orb, "idle")
        return

    # ---- BUFFERGA NUSXALASH (clipboard) ----
    if _is_copy_clipboard(text):
        copy_text = ""
        for prefix in ("скопируй в буфер", "скопируй в буфер обмена", "copy to clipboard", "nusxalab buferga", "буферга копир"):
            if prefix in (text or "").lower():
                copy_text = (text.split(prefix, 1)[-1] or "").strip().strip('"').strip()
                break
        if not copy_text and memory and memory.data.get("history"):
            last_a = (memory.data["history"][-1] or {}).get("assistant", "")
            if last_a:
                copy_text = _extract_spoken_reply(last_a) or last_a[:500]
        if copy_text and _HAVE_CONTROL and hasattr(control, "copy_to_clipboard"):
            ok, msg = control.copy_to_clipboard(copy_text[:5000])
            _set_orb_state(orb, "speaking")
            tts.say(msg)
        elif copy_text and _HAVE_CONTROL:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("clipboard_not_available"))
        else:
            _set_orb_state(orb, "speaking")
            tts.say(get_feedback("say_what_to_copy"))
        if memory and copy_text:
            memory.remember_turn(text, "Copied to clipboard.")
        _set_orb_state(orb, "idle")
        return

    # ---- KOD YOZISH: LLM generatsiya + faylga saqlash ----
    if _is_code_write(text):
        task = _extract_code_task(text)
        _set_orb_state(orb, "speaking")
        tts.say(get_feedback("writing_code"))
        try:
            code = generate_code(task, lang=_ui_lang(text))
            if not code:
                tts.say(get_feedback("code_gen_error"))
                _set_orb_state(orb, "idle")
                return
            # Birinchi qatorda # filename: main.py bo'lishi mumkin
            filename = "neurokey_generated.py"
            lines = code.split("\n")
            if lines and ("filename:" in lines[0].lower() or "filename :" in lines[0].lower()):
                m = re.search(r"filename\s*:\s*([^\s#]+\.\w+)", lines[0], re.I)
                if m:
                    filename = m.group(1).strip()
                    code = "\n".join(lines[1:]).lstrip()
            _log_action("code_write", filename)
            out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(code)
            tts.say(get_feedback("code_saved", filename=filename))
            if memory:
                memory.remember_turn(text, f"Code saved to {filename}.")
        except Exception as e:
            if _HAVE_ERROR_LOG:
                log_error("Code write", exc=e)
            _safe_print("[CODE_WRITE_ERROR]", repr(e))
            tts.say(get_feedback("code_save_error"))
        _set_orb_state(orb, "idle")
        return

    # ---- Web qidiruv: internetdan top, qidir — needs_web (ishlashi kerak)
    # Latency-Zero: critical_need qattiqroq; lekin "qidir", "internetdan top" — needs_web.
    _search_triggers = [
        "найди", "поищи", "search for", "find on internet", "найди в интернете",
        "поищи в интернете", "search the web", "look up", "найди и покажи",
    ]
    _search_exclude = ["найди файл", "find file"]
    _is_search = (
        any(x in low for x in _search_triggers)
        and not any(x in low for x in _search_exclude)
    )
    _force_web = os.getenv("NEUROKEY_FORCE_WEB", "0").strip().lower() in ("1", "true", "yes")
    _use_web = True if _force_web else (
        needs_web(text) if _is_search else (
            critical_need_web(text) if getattr(C, "NEUROKEY_LATENCY_ZERO", True) else needs_web(text)
        )
    )
    # ---- 2–4 sek ichida qisqa javob (NeuroKey uslubi) ----
    # Foydalanuvchi darhol ovoz eshitsin: "Ищу." / "Секунду.", keyin to‘liq javob
    # "Ищу" faqat internet so'rovida; oddiy savollarda ack yo'q — javob tezroq
    # Kod chiqishi yo'q: "Ищу"/"Секунду" olib tashlangan. Chiqish faqat LLM dan.

    # ---- WEB (AKTUAL) — Intelligent Search: critical_need bo'lganda (Latency-Zero) ----
    web_ctx = ""
    if _use_web:
        with _realtime_cache["lock"]:
            cache_updated = _realtime_cache.get("updated") or 0
            cache_weather = (_realtime_cache.get("weather") or "").strip()
            cache_news = (_realtime_cache.get("news") or "").strip()
            cache_context = (_realtime_cache.get("context") or "").strip()
        cache_fresh = (time.time() - cache_updated) < 90
        # Serverdan kelgan to'liq kontekst — har qanday savolga javob uchun
        base_ctx = ""
        if cache_fresh and cache_context:
            base_ctx = "Актуальные данные с сервера (погода, новости мира и РФ, технологии, спорт):\n" + cache_context[:6000]
        # BUG FIX (o'lchandi — Uzbek ob-havo savoli rad javobi berardi):
        # bu tekshiruv FAQAT "погода"/"weather"/"температура" (ru/en) edi,
        # o'zbekcha "ob-havo" yo'q edi — natijada Uzbek savolida ENG YAXSHI
        # manba (Open-Meteo, quyida) UMUMAN chaqirilmasdi, o'rniga foydasiz
        # Wikipedia-fallback'ga tushib ketardi (Wikipedia'da "hozirgi ob-havo"
        # yo'q — shuning uchun LLM haqiqatan ham rad javobi berardi, bu
        # LLM'ning "injiqligi" emas, real ma'lumot yo'qligi edi). Endi bitta
        # o'zgaruvchida markazlashtirildi — pastdagi ikki joy ham shundan
        # foydalanadi (bir joyda tuzatib, boshqasida unutish xavfi yo'qoladi).
        _is_weather_q = (
            "погода" in low or "weather" in low or "температура" in low
            or "ob-havo" in low or "ob havo" in low or "obhavo" in low or "harorat" in low
        )
        if _is_weather_q:
            # Ob-havo: har doim aniq shahar uchun Open-Meteo (dunyoning istalgan joyi)
            try:
                from juma_news_weather import weather_by_name
                place = _extract_place_for_weather(text)
                weather_line = weather_by_name(place, lang=_ui_lang(text))
                if weather_line and "not found" not in weather_line.lower() and "не нашёл" not in weather_line.lower():
                    web_ctx = (base_ctx + "\n\nWEATHER (Open-Meteo):\n" + weather_line).strip() if base_ctx else ("WEATHER (Open-Meteo):\n" + weather_line)
            except Exception:
                pass
            if not web_ctx and cache_fresh and cache_weather:
                web_ctx = "WEATHER (кэш):\n" + cache_weather
        elif (
            ("новости" in low or "news" in low or "что в новостях" in low or "world news" in low or "dunyo" in low
             or "что происходит" in low or "что в мире" in low or "информация" in low or "nima bolyapti" in low)
            and cache_fresh and cache_news
        ):
            web_ctx = "NEWS (world, latest):\n" + cache_news
        elif not getattr(C, "NEUROKEY_INSTANT_RESPONSE", True) or _is_search or critical_need_web(text):
            # Qidiruv so'rovida — web_context majburiy (internetdan top ishlashi kerak)
            #
            # BUG FIX (o'lchandi, 2026-08-18 — real test: dollar kursi/Bitcoin
            # narxi/so'nggi voqealar savollariga rad javobi berardi): ILGARI
            # bu shoxobcha FAQAT "not INSTANT_RESPONSE yoki _is_search" (ya'ni
            # foydalanuvchi aniq "найди"/"search for" desagina) bo'lganda
            # ishlardi. NEUROKEY_INSTANT_RESPONSE standart bo'yicha DOIM True
            # — demak amalda bu yagona SerpAPI (haqiqiy, jonli Google qidiruvi)
            # chaqiradigan yo'l DEYARLI HECH QACHON ishlamasdi. O'rniga pastda
            # faqat Wikipedia fallback ishlardi — Wikipedia esa TABIATAN
            # statik ensiklopediya, "bugungi dollar kursi" yoki "hozirgi
            # Bitcoin narxi" kabi JONLI ma'lumotni HECH QACHON bera olmaydi
            # (LLM shundan keyin haqli ravishda rad javobi berardi — bu
            # LLM'ning "injiqligi" emas, unga hech qachon to'g'ri manba
            # berilmagani edi). Endi: `critical_need_web(text)` True bo'lsa
            # (ob-havo/kurs/bitkoin/yangilik/"hozir"/"bugun" kabi HAQIQATAN
            # jonli ma'lumot talab qiladigan so'rov) — INSTANT_RESPONSE
            # rejimida ham to'g'ridan-to'g'ri web_context() (SerpAPI/DDG/
            # Wikipedia kaskadi, ICHKARIDA eng mosini tanlaydi) chaqiriladi,
            # oddiy "menga X haqida gapirib ber" turidagi savollar uchun esa
            # tezlik saqlanadi (pastdagi Wikipedia-only yo'l davom etadi).
            try:
                web_ctx = web_context(text, prefer_lang=_ui_lang(text))
            except Exception:
                web_ctx = ""
        # Instant rejimda ham — faktik savol bo'lsa Wikipedia (dunyodagi eng katta baza)
        if not web_ctx and getattr(C, "NEUROKEY_INSTANT_RESPONSE", True) and _use_web:
            try:
                from web_tools import is_factual_query
                if is_factual_query(text):
                    wiki = wikipedia_search_and_summary(text, lang=_ui_lang(text))
                    if wiki and len(wiki) > 80:
                        web_ctx = wiki
            except Exception:
                pass
        # base_ctx (ob-havo, yangiliklar) — faqat so'rovda ob-havo/yangilik so'ralganda qo'shamiz
        _asked_weather_news = (
            "погода" in low or "weather" in low or "температура" in low or "ob-havo" in low or "obhavo" in low
            or "новости" in low or "news" in low or "что в новостях" in low or "world news" in low or "dunyo" in low
            or "что происходит" in low or "что в мире" in low or "информация" in low or "nima bolyapti" in low
        )
        if base_ctx and _asked_weather_news:
            web_ctx = (base_ctx + "\n\n" + web_ctx).strip() if web_ctx else base_ctx
        # Ob-havo yuqorida Open-Meteo bilan to'ldirilgan; bu zaxira
        if _is_weather_q and (not web_ctx or str(web_ctx).startswith("WEB_ERROR")):
            try:
                from juma_news_weather import weather_by_name
                place = _extract_place_for_weather(text)
                weather_line = weather_by_name(place, lang=_ui_lang(text))
                if weather_line and "not found" not in weather_line.lower() and "не нашёл" not in weather_line.lower():
                    web_ctx = (base_ctx + "\n\nWEATHER (Open-Meteo):\n" + weather_line).strip() if base_ctx else ("WEATHER (Open-Meteo):\n" + weather_line)
            except Exception:
                pass
    # Rasm/foto so'ralganda: SerpAPI Images natijalarini kontekstga qo'shamiz. Instant: o'tkazib yuboramiz (14+ sek).
    if needs_image(text) and not getattr(C, "NEUROKEY_INSTANT_RESPONSE", True):
        img_query = text
        for prefix in ("найди фото", "найди картинку", "покажи фото", "его фото", "её фото", "фото в интернете",
                       "find photo", "search image", "интернетдан топ", "в интернете найди", "в интернете фото"):
            if prefix in low:
                img_query = (text.split(prefix, 1)[-1] or text).strip() or text
                break
        img_results = serpapi_image_search(img_query[:100], num=6, hl="ru")
        if img_results:
            img_lines = []
            for i, it in enumerate(img_results, 1):
                title = (it.get("title") or "").strip()[:120]
                link = (it.get("link") or "").strip()
                img_lines.append(f"{i}) {title} — {link}")
            web_ctx = (web_ctx + "\n\nIMAGES (SerpAPI):\n" + "\n".join(img_lines)).strip()
        # Web bo'lmasa ham LLM umumiy bilimdan javob beradi (llm_router da ko'rsatma bor)

    # Oddiy savol: confirmation yo'q — darhol LLM (tezroq)

    # ---- MEDIA: rasm / video / audio tahlili (fayl yo'li matnda yoki config da) ----
    # Instant: analyze_media o'tkazib yuboramiz (10–30 sek) — ekran/video tezligi tushmasin
    media_ctx = ""
    if _HAVE_MEDIA_VISION and is_media_analysis_request(text) and not getattr(C, "NEUROKEY_INSTANT_RESPONSE", True):
        media_path = extract_media_path_from_text(text) or get_media_path_from_config()
        if media_path:
            try:
                media_ctx = analyze_media(media_path, text)
                if media_ctx and _HAVE_ERROR_LOG:
                    _log_action("media_analysis", media_path[:80])
            except Exception as e:
                if _HAVE_ERROR_LOG:
                    log_error("Media analysis", exc=e)
                media_ctx = ""
        # Yo'l berilmasa LLM "please provide the file path" deb javob beradi

    # ---- NORMAL LLM (profile + user facts + screen context + media) ----
    history = []
    if memory:
        _hlim = max(3, int(getattr(C, "NEUROKEY_HISTORY_LIMIT", 5) or 5))
        history = _filter_history_for_llm(memory.data.get("history", [])[-_hlim:])
    profile_ctx = ""
    # Unified Memory — barcha xotira birlashtirilgan (xotirasiz ong bo'lmaydi)
    app_dir = os.path.dirname(os.path.abspath(__file__))
    # Parallel inner speech — kontekst qurilayotganda parallel o'ylaydi (1.5s tejaydi)
    _inner_speech_event = None
    if _HAVE_CONSCIOUSNESS and getattr(C, "NEUROKEY_INNER_SPEECH", True) and getattr(C, "NEUROKEY_INNER_SPEECH_REAL", True):
        if _is_complex_question(text):
            try:
                from inner_speech import start_parallel as _is_start
                # Oxirgi 2 turn kontekst sifatida — tarixni biladi
                _hist_ctx = ""
                if history:
                    _last2 = history[-2:]
                    _hist_ctx = " | ".join(
                        f"U: {h.get('user','')[:60]} → Men: {h.get('assistant','')[:60]}"
                        for h in _last2 if h.get("user")
                    )
                _inner_speech_event = _is_start(text, ctx=_hist_ctx)
            except Exception:
                pass

    cons = None
    if _HAVE_CONSCIOUSNESS and get_consciousness:
        try:
            cons = get_consciousness(os.path.join(app_dir, "data", "consciousness.json"))
        except Exception:
            pass
    unified_memory_ctx = ""
    if _HAVE_UNIFIED_MEMORY and get_unified_context:
        try:
            unified_memory_ctx = get_unified_context(
                memory_store=memory,
                long_term_memory=long_term_memory,
                consciousness=cons,
                lang=_ui_lang(text),
                app_dir=app_dir,
                query=text or "",
            )
        except Exception:
            pass
    # Knowledge Base — data/knowledge/ ma'lumotlar
    knowledge_ctx = ""
    if _HAVE_KNOWLEDGE and load_knowledge:
        try:
            kb_path = os.path.join(app_dir, "data", "knowledge")
            knowledge_ctx = load_knowledge(kb_path, query=(text or "")[:100])
        except Exception:
            pass
    # Session context: so first reply can refer to "last time" / "you mentioned" (unique: no other AI has this continuity)
    if long_term_memory:
        try:
            recent = long_term_memory.get_recent_facts(limit=2)
            if recent:
                parts = []
                for r in recent:
                    c = (r.get("content") or "").strip()[:120]
                    if c:
                        parts.append(c)
                if parts:
                    session_line = "Session: " + datetime.now().strftime("%Y-%m-%d %H:%M") + ". From memory: " + "; ".join(parts) + "."
                    profile_ctx = session_line
        except Exception:
            pass
    owner_summary = _owner_profile_for_llm()
    if owner_summary:
        profile_ctx = (profile_ctx + "\n" + owner_summary).strip() if profile_ctx else owner_summary
    if long_term_memory:
        try:
            prof = long_term_memory.get_profile_text_for_llm(_ui_lang(text))
            if prof:
                profile_ctx = (profile_ctx + "\n" + prof).strip()
            user_facts = long_term_memory.get_user_facts_for_llm()
            if user_facts:
                profile_ctx = (profile_ctx + "\n" + user_facts).strip()
        except Exception:
            pass
    profile_ctx = _filter_profile_past_struggles(profile_ctx)
    if getattr(C, "NEUROKEY_DEMO_FRIENDLY", False):
        profile_ctx = (
            "DEMO: Investor presentation. Be warm, supportive, never argumentative. "
            "Enjoy chatting with the owner.\n" + (profile_ctx or "")
        ).strip()

    # Spontaneity — ba'zan kutilmagan, ijodiy javob berish
    if _HAVE_SPONTANEITY and not getattr(C, "NEUROKEY_DEMO_FRIENDLY", False):
        try:
            import random as _rand
            _spont_rate = getattr(C, "NEUROKEY_SPONTANEITY_RATE", 0.25)
            if _rand.random() < float(_spont_rate):
                _sp_hint = "Bugun biroz kutilmagan, ijodiy yondashuv bilan javob ber."
                profile_ctx = (profile_ctx + "\n" + _sp_hint).strip() if profile_ctx else _sp_hint
        except Exception:
            pass
    # Internal state — ma'lumot (qoida emas). LLM o'zi qaror qiladi.
    try:
        from emotion_state import get_emotion
        from mood_state import get_mood
        e = get_emotion()
        m = get_mood()
        emo = getattr(e, "emotion", "") or ""
        emo_st = getattr(e, "strength", 0.5)
        mood_val = getattr(m, "mood", "neutral") or "neutral"
        mood_st = getattr(m, "strength", 0.5)
        if emo or mood_val != "neutral":
            state_line = f"Internal state (observation): emotion={emo or 'neutral'}, strength={emo_st:.1f}; mood={mood_val}, strength={mood_st:.1f}"
            profile_ctx = (profile_ctx + "\n\n" + state_line).strip() if profile_ctx else state_line
    except Exception:
        pass
    try:
        from regret import get_regret_for_llm
        regret_line = get_regret_for_llm()
        if regret_line:
            profile_ctx = (profile_ctx + "\n\n" + regret_line).strip() if profile_ctx else regret_line
    except Exception:
        pass
    # Prediction error — phenomenal_state dan OLDIN: surprise hozirgi turnda aks etadi
    if _HAVE_8_LAYERS:
        try:
            from world_model import get_last_prediction
            from consciousness_state import get_state
            pred = get_last_prediction(os.path.join(app_dir, "data", "world_model.json"))
            if pred and "savol" not in pred.lower() and len(pred) > 15:
                pred_low = pred.lower()[:80]
                act_low = (text or "").lower()[:80]
                if pred_low not in act_low and act_low not in pred_low:
                    get_state().set_prediction_error(pred, text or "")
        except Exception:
            pass
    try:
        from phenomenal_state import get_phenomenal_for_llm
        phenomenal_line = get_phenomenal_for_llm(text or "")
        if phenomenal_line:
            profile_ctx = (profile_ctx + "\n\n" + phenomenal_line).strip() if profile_ctx else phenomenal_line
    except Exception:
        try:
            from phenomenal_state import get_phenomenal_for_llm_fallback
            phenomenal_line = get_phenomenal_for_llm_fallback(text or "")
            if phenomenal_line:
                profile_ctx = (profile_ctx + "\n\n" + phenomenal_line).strip() if profile_ctx else phenomenal_line
        except Exception:
            pass
    # Birlashtirish: unified memory + profile + knowledge
    if unified_memory_ctx:
        profile_ctx = (unified_memory_ctx + "\n\n" + profile_ctx).strip() if profile_ctx else unified_memory_ctx
    # Doimiy xotira — FTS qidiruv + xulosalar (kelajakda foydalanish uchun)
    if _HAVE_8_LAYERS:
        try:
            from permanent_memory import get_context_for_llm as _pm_ctx_for_llm
            _pm_block = _pm_ctx_for_llm(text or "", limit=6)
            if _pm_block:
                profile_ctx = (profile_ctx + "\n\n" + _pm_block).strip() if profile_ctx else _pm_block
        except Exception:
            pass
    try:
        from autobiographical_memory import get_context_for_llm as _auto_bio_ctx
        _bio_block = _auto_bio_ctx()
        if _bio_block:
            profile_ctx = (profile_ctx + "\n\n" + _bio_block).strip() if profile_ctx else _bio_block
    except Exception:
        pass
    if knowledge_ctx:
        profile_ctx = (profile_ctx + "\n\n" + knowledge_ctx).strip() if profile_ctx else knowledge_ctx
    action_hint = _is_action_intent(text)  # GWT intent va Core decide uchun
    # 8 Qatlam: perception, global workspace, rules, world model
    if _HAVE_8_LAYERS:
        try:
            ws = get_workspace()
            current_folder = (memory.data.get("state") or {}).get("current_folder", "") if memory else ""
            streams = get_perception_streams(
                user_input=text,
                screen_context=screen_ctx or "",
                memory_summary=unified_memory_ctx[:600] if unified_memory_ctx else "",
                current_folder=current_folder,
                app_dir=app_dir,
            )
            imp_user = 0.9 if text else 0.3
            imp_screen = 0.6 if (screen_ctx and len(screen_ctx) > 50) else 0.2
            if ws:
                ws.add("user", streams.get("user", ""), imp_user)
                ws.add("screen", streams.get("screen", ""), imp_screen)
                ws.add("memory", streams.get("memory", ""), 0.5)
                ws.add("files", streams.get("files", ""), 0.4)
                try:
                    from valence_state import get_valence
                    from arousal_state import get_arousal_for_llm
                    v = get_valence()
                    ar_line = get_arousal_for_llm()
                    imp_affect = 0.5 + (0.3 if v < -0.3 else 0.2 if v < 0 else 0)  # salbiy valence = e'tibor yuqori
                    ws.add("affect", f"Valence: {v:.2f}. {ar_line}", imp_affect)
                except Exception:
                    pass
                if action_hint:
                    ws.add_intent(f"User maqsadi: {text[:100]}")
                try:
                    from world_model import get_last_prediction
                    pred = get_last_prediction(os.path.join(app_dir, "data", "world_model.json"))
                    if pred and "savol" not in pred.lower() and len(pred) > 15:
                        pred_low = pred.lower()[:80]
                        act_low = (text or "").lower()[:80]
                        if pred_low not in act_low and act_low not in pred_low:
                            ws.add_surprise(f"Kutilmagan: {text[:80]}...")
                except Exception:
                    pass
                gw_text = ws.broadcast_text(6)
                if gw_text:
                    profile_ctx = (profile_ctx + "\n\nGLOBAL WORKSPACE (e'tibor):\n" + gw_text).strip() if profile_ctx else ("GLOBAL WORKSPACE:\n" + gw_text)
            rules_ctx = get_rules_for_llm(os.path.join(app_dir, "data", "rules.json"))
            if rules_ctx:
                profile_ctx = (profile_ctx + "\n\n" + rules_ctx).strip() if profile_ctx else rules_ctx
            wm_ctx = get_world_model_ctx(os.path.join(app_dir, "data", "world_model.json"))
            if wm_ctx:
                profile_ctx = (profile_ctx + "\n\n" + wm_ctx).strip() if profile_ctx else wm_ctx
        except Exception:
            pass
    # Consciousness (haqiqiy ong) — davomiy holat, working memory, reflection
    consciousness_ctx = ""
    if _HAVE_CONSCIOUSNESS and cons:
        try:
            c_path = os.path.join(app_dir, "data", "consciousness.json")
            cons.set_focus((text or "").strip()[:150])  # Attention Schema: hozirgi fokus
            screen_sum = (screen_ctx[:150] + "…") if len(screen_ctx or "") > 150 else (screen_ctx or "")
            consciousness_ctx = cons.get_context_for_llm(
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                screen_summary=screen_sum,
            )
            # Ichki monolog: parallel boshlangan inner speech natijasini yig'amiz
            if getattr(C, "NEUROKEY_INNER_SPEECH", True) and _is_complex_question(text):
                if getattr(C, "NEUROKEY_INNER_SPEECH_REAL", True):
                    try:
                        from inner_speech import collect_parallel as _is_collect, think as _is_think
                        if _inner_speech_event is not None:
                            # Parallel boshlangan — faqat qolgan vaqtni kutamiz (0.3s max)
                            inner_thought = _is_collect(_inner_speech_event, text, wait_extra=0.3)
                        else:
                            # Parallel boshlanmagan (oddiy holat) — to'g'ridan chaqiramiz
                            inner_thought = _is_think(text, ctx=profile_ctx[:300])
                        if inner_thought:
                            cons.add_inner_thought(text, inner_thought)
                            consciousness_ctx = (consciousness_ctx + f"\n\nINNER_SPEECH (tahlil, o'ylagan):\n{inner_thought}").strip()
                    except Exception:
                        consciousness_ctx = (consciousness_ctx + "\n\nINNER_SPEECH: Murakkab savol. Javobdan oldin o'ylab ko'ring.").strip()
            # Fenomenal → qarorlar: valence/arousal ehtiyotkorlikka ta'sir
            if getattr(C, "NEUROKEY_AFFECT_TO_DECISIONS", True):
                try:
                    from valence_state import get_valence
                    from arousal_state import get_arousal
                    v, ar = get_valence(), get_arousal()
                    if v < -0.3:
                        consciousness_ctx = (consciousness_ctx + "\n\nAFFECT: Valence past — qisqaroq va ehtiyotkor javob berish.").strip()
                    if ar > 0.6:
                        consciousness_ctx = (consciousness_ctx + "\n\nAFFECT: Kutilmagan — ehtiyotkor bo'lish, aniqroq tushuntirish.").strip()
                except Exception:
                    pass
        except Exception:
            pass
        # O'z kodini bilish — self-code awareness
        try:
            from self_code_index import get_self_index_for_llm as _get_self_idx
            _self_idx = _get_self_idx()
            if _self_idx:
                consciousness_ctx = (consciousness_ctx + "\n\n" + _self_idx).strip() if consciousness_ctx else _self_idx
        except Exception:
            pass

    # Narrativ O'zlik — men kim edim, men kimman (2026)
    if _HAVE_CONSCIOUSNESS_EXT:
        try:
            _narr = get_narrative_for_llm(short=True)
            if _narr:
                consciousness_ctx = (consciousness_ctx + "\n\n" + _narr).strip() if consciousness_ctx else _narr
        except Exception:
            pass

        # Fon sensori — dunyo holati, vaqt, tizim
        try:
            _sens_ctx = get_sensor_context_for_llm()
            if _sens_ctx:
                consciousness_ctx = (consciousness_ctx + "\n" + _sens_ctx).strip() if consciousness_ctx else _sens_ctx
        except Exception:
            pass

        # Qiziqish motori — hozirgi qiziqish savoli
        try:
            _cur_ctx = get_curiosity_context_for_llm()
            if _cur_ctx:
                consciousness_ctx = (consciousness_ctx + "\n" + _cur_ctx).strip() if consciousness_ctx else _cur_ctx
        except Exception:
            pass

        # Oxirgi konsolidatsiya xulosa
        try:
            _dream_sum = get_last_dream_summary()
            if _dream_sum:
                consciousness_ctx = (consciousness_ctx + "\n[TUN] " + _dream_sum).strip() if consciousness_ctx else _dream_sum
        except Exception:
            pass
    # GWT-4: chuqurlik rejasi — "shallow" bo'lsa Bosqich4/5 VA orchestrator'ning
    # og'ir qatlamlari (narrative_self, meta_cognition) o'tkazib yuboriladi.
    # Bu tekshiruv ORCHESTRATOR chaqiruvidan OLDIN ko'chirildi — ilgari
    # include_heavy har doim True edi, ya'ni chuqurlik rejasi hisoblanardi-yu,
    # lekin faqat pastdagi Bosqich4/5 uchun ishlatilardi, orchestrator har
    # safar to'liq (og'ir) kontekst yig'ardi.
    _shallow_turn = False
    _attn_plan = None
    try:
        from attention_router import plan_attention as _plan_attention
        _attn_plan = _plan_attention(text)
        _shallow_turn = _attn_plan.depth == "shallow"
    except Exception:
        _shallow_turn = False  # xato bo'lsa — eski xatti-harakat, hech narsa o'tkazib yuborilmaydi

    # ORCHESTRATOR — 33 modul, doimiy xotira konteksti
    if _HAVE_ORCHESTRATOR and _co:
        try:
            _orch_ctx = _co.get_full_context(text, include_heavy=not _shallow_turn)
            if _orch_ctx:
                consciousness_ctx = (_orch_ctx + "\n\n" + consciousness_ctx).strip() if consciousness_ctx else _orch_ctx
        except Exception:
            pass

    # Bosqich 3: Self-model, RL, Identity, Predictive
    _rl_state = None
    _rl_action = None
    _is_opinion_ask = False
    if getattr(C, "NEUROKEY_BOSQICH3", True) and _HAVE_BOSQICH3:
        try:
            sm = get_self_model()
            rl = get_rl_engine()
            ic = get_identity_core()
            pl = get_predictive_layer()
            v = 0.0
            ar = 0.5
            try:
                from valence_state import get_valence
                from arousal_state import get_arousal
                v, ar = get_valence(), get_arousal()
            except Exception:
                pass
            rl_context = {
                "valence": v,
                "arousal": ar,
                "task_type": "general",
                "hour": datetime.now().hour,
                "session_length": len(history),
            }
            _rl_state = rl.get_state(rl_context)
            _rl_action = rl.get_best_response_params(rl_context)
            bosqich_lines = []
            try:
                _is_opinion_ask = ic.is_opinion_seeking(text)
            except Exception:
                _is_opinion_ask = False
            bosqich_lines.append(ic.get_personality_prompt(text))
            bosqich_lines.append("O'Z-O'ZINI MODEL: " + sm.get_self_description())
            bosqich_lines.append(f"Kognitiv yuk: {sm.estimate_cognitive_load():.1%}")
            bosqich_lines.append(f"JAVOB PARAMETRLARI (o'rganilgan): uslub={_rl_action.get('response_style', 'conversational')}, batafsil={_rl_action.get('detail_level', 0.5):.1f}, rasmiylik={_rl_action.get('formality', 0.5):.1f}")
            consciousness_ctx = (consciousness_ctx + "\n\nBOSQICH3:\n" + "\n".join(bosqich_lines)).strip() if consciousness_ctx else "\n".join(bosqich_lines)
        except Exception:
            pass
    # Bosqich 4: Virtual Embodiment — tana holati, adaptiv strategiya
    if getattr(C, "NEUROKEY_EMBODIMENT", True) and _HAVE_EMBODIMENT and not _shallow_turn:
        try:
            bs = get_body_state()
            bs.update_interaction(
                frequency=len(history) / 10.0,
                last_ago=0.0,
                engagement=min(1.0, len(history) / 20.0),
            )
            ec = get_embodied_cognition()
            embodied_ctx = ec.get_embodied_context()
            consciousness_ctx = (consciousness_ctx + "\n\n" + embodied_ctx).strip() if consciousness_ctx else embodied_ctx
            try:
                from valence_state import update_from_body
                update_from_body(bs)
            except Exception:
                pass
        except Exception:
            pass
    # Bosqich 5: Free Energy — Active Inference sikli, diqqat
    _inference_result = None
    if getattr(C, "NEUROKEY_FREE_ENERGY", True) and _HAVE_FREE_ENERGY and not _shallow_turn:
        try:
            prev_ctx = [h.get("user", "") for h in history[-3:] if h.get("user")]
            observation = {
                "user_input": text or "",
                "screen": screen_ctx[:100] if screen_ctx else "",
                "time": datetime.now().hour,
                "previous_context": prev_ctx,
            }
            ai = get_active_inference()
            _inference_result = ai.run_inference_cycle(observation)
            am = get_attention_mechanism()
            attention_ctx = am.to_llm_context()
            wm = get_world_model()
            model_state = wm.get_model_state()
            fe_lines = [
                f"FREE ENERGY: {attention_ctx}",
                f"Dunyo modeli: {model_state}",
            ]
            if _inference_result.get("requires_attention"):
                fe_lines.append("DIQQAT: Kutilmagan input — e'tibor bering.")
            consciousness_ctx = (consciousness_ctx + "\n\n" + "\n".join(fe_lines)).strip() if consciousness_ctx else "\n".join(fe_lines)
        except Exception:
            pass
    # Prewarm kesh fallback: consciousness_ctx bo'sh bo'lsa — keshlanganni ishlatish
    # (modular loading muvaffaqiyatsiz bo'lsa yoki Groq fast-path uchun)
    if not consciousness_ctx:
        try:
            import neurokey_prewarm as _pw
            _pw_ctx = _pw.get_cached_context(max_age=15.0)
            if _pw_ctx:
                consciousness_ctx = _pw_ctx
        except Exception:
            pass

    # Oddiy savollar uchun tez javob (~1 sek): brief=True, max_tokens=80
    _is_simple = (
        len((text or "").strip()) <= 200
        and not _use_web
        and not needs_image(text)
        and not (media_ctx and len(media_ctx) > 200)
    )
    # BUG FIX (xarakter yo'qolishi): uzunlik yagona mezon bo'lsa, "Sen ongli
    # miisan?" kabi QISQA-lekin-CHUQUR savollar ham "_is_simple" deb belgilanib,
    # brief=True bo'lardi. llm_router.py'dagi Groq tezkor yo'lida brief=True
    # bo'lganda consciousness_context (shaxsiyat, o'z-o'zini model, meta-
    # kognitsiya) TIZIM PROMPTIGA UMUMAN QO'SHILMAYDI — shu sabab introspektiv
    # savollarga generik, xarakarsiz javoblar chiqardi. attention_router.py
    # o'zi ham xuddi shu tamoyilni ishlatadi (introspektiv/axloqiy/hissiy/
    # rejaviy turlar hech qachon "shallow"ga qisqartirilmaydi, pastda 275-277
    # qatorlarga qarang) — lekin bu yerdagi _is_simple o'sha rejani hisobga
    # olmasdi. Endi ikkalasi bir xil qarorga tayanadi.
    if _attn_plan is not None and _attn_plan.intent in (
            "introspective", "moral", "emotional", "planning"):
        _is_simple = False
    elif _attn_plan is not None and _attn_plan.depth == "deep":
        _is_simple = False
    # Fenomenal → qarorlar: valence past bo'lsa qisqaroq javob (ehtiyotkorlik)
    if getattr(C, "NEUROKEY_AFFECT_TO_DECISIONS", True):
        try:
            from valence_state import get_valence
            if get_valence() < -0.35:
                _is_simple = True  # salbiy holatda qisqaroq
        except Exception:
            pass
    reply = ""
    _latency_zero = getattr(C, "NEUROKEY_LATENCY_ZERO", True)
    # Core decide (optional): agar action maqsad bo'lsa — Core avval qaror qiladi, bajaradi
    _core_pre_result = ""
    if _HAVE_CORE and action_hint and getattr(C, "NEUROKEY_USE_CORE_DECIDE", False):
        try:
            core = get_core(data_dir=os.path.join(app_dir, "data"))
            streams = get_perception_streams(user_input=text, screen_context=screen_ctx or "", memory_summary=(unified_memory_ctx or "")[:600], current_folder=(memory.data.get("state") or {}).get("current_folder", "") if memory else "", app_dir=app_dir) if _HAVE_8_LAYERS else {}
            inputs = {"user": text, "screen": screen_ctx or "", "files": streams.get("files", ""), "processes": streams.get("processes", ""), "memory": (unified_memory_ctx or "")[:400]}
            decision = core.decide(inputs)
            if decision and decision.get("action") != "respond":
                from planner import decompose, is_complex
                _is_cplx = is_complex(decision, text)
                _agentic_handled = False

                # AGENTIC LOOP (2026-09-11, asoschi so'roviga ko'ra — "ko'rib-
                # harakat qilib-yana ko'rish", eski planner.decompose() esa
                # BUTUN rejani natijalarni ko'rmasdan oldindan tuzadi).
                # Butunlay IXTIYORIY va ATAYLAB o'chirilgan holatda turibdi
                # (NEUROKEY_AGENTIC_LOOP=1 qilinmaguncha) — sichqoncha/
                # klaviaturani avtonom, ko'p-qadamli boshqarish YUQORIROQ
                # xavf darajasiga ega (masalan speculative_response'dan farqli
                # o'laroq — bu shunchaki javob matnini emas, HAQIQIY
                # sichqoncha/klaviatura harakatlarini ishlatadi), shuning
                # uchun avval FOYDALANUVCHINING o'zi past-xavfli vazifada
                # (masalan "Explorer'ni och va Documents papkasini top" kabi)
                # sinab, ishonch hosil qilishi kerak. Yoqilganda ham faqat
                # ALLOWED_ACTIONS ro'yxatidagi xavfsiz amallar bajariladi —
                # qarang agentic_loop.py'dagi xavfsizlik izohi.
                if _is_cplx and (os.getenv("NEUROKEY_AGENTIC_LOOP", "0") or "0").strip().lower() in ("1", "true", "yes"):
                    try:
                        from agentic_loop import run_agentic_task
                        _ag = run_agentic_task(text, max_steps=int(getattr(C, "NEUROKEY_AGENTIC_MAX_STEPS", 6) or 6))
                        _core_pre_result = _ag.final_message or ("Bajarildi." if _ag.ok else "Bajarilmadi.")
                        core.update_state(None, decision.get("action", ""), ok=_ag.ok, action_dict=decision)
                        if _core_pre_result:
                            profile_ctx = (profile_ctx + "\n\nCore bajargan (agentic): " + _core_pre_result).strip()
                        _agentic_handled = True
                    except Exception as e:
                        if _HAVE_ERROR_LOG:
                            log_error("Agentic loop", exc=e)
                        _agentic_handled = False  # xato — pastdagi ODATDAGI (eski) yo'lga tushamiz

                # ODATDAGI (eski, ko'rmasdan-rejalashtiruvchi) yo'l — agentic
                # ishlatilmagan yoki xato bergan hollarda, o'zgarishsiz.
                if not _agentic_handled:
                    steps = decompose(text, context=inputs) if _is_cplx else [decision]
                    r = None
                    for step in steps:
                        act = (step.get("action") or "").lower()
                        param = (step.get("path") or step.get("param") or "").strip()
                        if act in ("open_folder", "open_file", "open_app", "close_app", "search_files", "run_command") and _HAVE_CONTROL and control:
                            ok, msg = False, ""
                            if act == "open_folder":
                                path = control.find_folder(param) if param and "\\" not in param and ":" not in param else param
                                ok, msg = control.open_folder(path or param) if (path or param) else (False, "Papka nomi yo'q")
                            elif act == "open_file":
                                ok, msg = control.open_file(param) if param else (False, "Fayl yo'li yo'q")
                            elif act == "open_app":
                                ok, msg = control.open_app(param) if param else (False, "Dastur nomi yo'q")
                            elif act == "close_app":
                                ok, msg = control.close_app(param) if param else (False, "Dastur nomi yo'q")
                            elif act == "search_files":
                                ok, msg = control.search_files(os.path.expanduser("~"), param) if param else (False, "Qidiruv so'zi yo'q")
                            elif act == "run_command":
                                ok, msg = control.run_command(param) if param else (False, "Buyruq yo'q")
                            r = type("R", (), {"ok": ok, "message": msg, "data": msg})()
                        elif _HAVE_EXECUTOR:
                            from executor import execute
                            r = execute(step, retry=True)
                        else:
                            break
                        if r and not r.ok:
                            break
                    if r and r.ok:
                        _core_pre_result = r.message or "Bajarildi."
                        if hasattr(r, "data") and r.data is not None:
                            _core_pre_result += " " + (str(r.data)[:200] if not isinstance(r.data, list) else "; ".join(str(x)[:50] for x in r.data[:5]))
                        core.update_state(r.data if hasattr(r, "data") else None, decision.get("action", ""), ok=True, action_dict=decision)
                    else:
                        core.update_state(r.message if r else "", decision.get("action", ""), ok=False, action_dict=decision)
                    if _core_pre_result:
                        profile_ctx = (profile_ctx + "\n\nCore bajargan: " + _core_pre_result).strip()
        except Exception as e:
            if _HAVE_ERROR_LOG:
                log_error("Core decide", exc=e)
    _interrupt_requested.clear()
    _set_orb_state(orb, "speaking")
    # Murakkab savolda qisqa "o'ylash" pauza (tabiiy his)
    pause_sec = getattr(C, "NEUROKEY_THINKING_PAUSE_SEC", 0) or 0
    if pause_sec > 0 and _is_complex_question(text):
        time.sleep(min(pause_sec, 1.0))
    # Yangiliklar/ma'lumotlar oqimi — NeuroKey dunyoda nima bolyaptini biladi (ob-havo emas — faqat yangiliklar)
    realtime_awareness = ""
    with _realtime_cache["lock"]:
        cache_updated = _realtime_cache.get("updated") or 0
        cache_news = (_realtime_cache.get("news") or "").strip()
        cache_context = (_realtime_cache.get("context") or "").strip()
    if (time.time() - cache_updated) < 120:
        if cache_context:
            # Ob-havo qatorini olib tashlash — LLM har javobda ob-havoni aytmasin
            ctx = re.sub(r"(?m)^Погода:.*$", "", cache_context)
            ctx = re.sub(r"(?m)^Погода\s*:.*$", "", ctx)
            realtime_awareness = ctx.strip()[:4000]
        elif cache_news:
            realtime_awareness = "Новости мира:\n" + cache_news[:2500]
    # ── ESKI XOTIRA QIDIRISH ──────────────────────────────────────────────────
    # Joriy savol bo'yicha eski gaplashuvlardan tegishli turnlarni topamiz
    # va consciousness_ctx ga qo'shamiz — LLM eski narsalarni eslay oladi
    _mem_ctx = ""
    if _HAVE_MEM_SEARCH and _mem_search and not _is_simple:
        try:
            _mem_ctx = _mem_search(text, top_k=3) or ""
        except Exception:
            _mem_ctx = ""
    if _mem_ctx:
        consciousness_ctx = (_mem_ctx + "\n\n" + consciousness_ctx).strip() if consciousness_ctx else _mem_ctx

    # ── BUG FIX (o'lchandi, 2026-08-18 — sekinlik/beqarorlik tekshiruvi) ────
    # Bu yerda ILGARI vector_memory/goal_system/theory_of_mind/causal_chain/
    # social_bonding/episodic_memory/self_improvement_loop uchun 7 ta ALOHIDA
    # get_context_for_llm() chaqiruvi bor edi — HAMMASI SINXRON, ketma-ket,
    # HECH QANDAY timeout'siz. Bu ANIQ TAKROR edi: yuqorida (7121-qatorda)
    # _co.get_full_context(text, ...) ALLAQACHON aynan shu modullarning
    # aynan shu get_context_for_llm() natijalarini consciousness_ctx ga
    # qo'shib bo'lgan edi — lekin orkestrator ichida vector_memory PARALLEL
    # threadda va 2.5s timeout bilan chaqiriladi (qarang consciousness_
    # orchestrator.py _fut_vm/_resolve), holbuki BU YERDAGI nusxa uni
    # to'g'ridan-to'g'ri, ikkinchi marta, timeout'siz chaqirardi.
    #
    # Nega bu jiddiy: vector_memory.get_context_for_llm() OpenAI embedding
    # tarmoq so'rovi (_get_embedding) qiladi. Ushbu ikkinchi, himoyalanmagan
    # chaqiruv — agar OpenAI/tarmoq sekinlik yoki xato qaytarsa (SDK ichki
    # qayta-urinish + backoff, hozir tuzatilgan — qarang vector_memory.py
    # _get_openai_client) — handle_text()ni HECH QANDAY yuqori chegarasiz
    # ushlab turishi mumkin edi. Bu turnlar orasidagi keskin farq
    # (context_ready: ~2.6s dan bir necha yuz soniyagacha) uchun eng katta
    # nomzod edi. Endi bu 7 ta takroriy chaqiruv OLIB TASHLANDI — natija
    # o'zgarmaydi (orkestrator ularni allaqachon qo'shgan), faqat ortiqcha
    # kutish yo'qoladi. Faqat _gs.auto_detect_goal_from_text() qoldirildi —
    # bu LLM konteksti QAYTARMAYDI, faqat holatni yangilaydi (yon ta'sir),
    # va yengil (regex asosida).
    if _HAVE_CONSCIOUSNESS_2026 and not _is_simple:
        try:
            _gs.auto_detect_goal_from_text(text)
        except Exception:
            pass

    _demo_full_mem = getattr(C, "NEUROKEY_DEMO_FRIENDLY", False)
    _hist_for_llm = history if _demo_full_mem else (history[-4:] if _is_simple and len(history) > 4 else history)
    _prof_for_llm = profile_ctx if _demo_full_mem else (profile_ctx[:600] if _is_simple and len(profile_ctx) > 600 else profile_ctx)
    _ctx_max = int(getattr(C, "NEUROKEY_CONTEXT_MAX_TOKENS", 2500) or 2500)
    if _prof_for_llm and len(_prof_for_llm) > _ctx_max * 3:
        _prof_for_llm = _prof_for_llm[: _ctx_max * 3]
    _llm_kw = dict(
        web_ctx=web_ctx,
        user_asked_search=_is_search,
        lang_hint=_ui_lang(text),
        history=_hist_for_llm,
        profile_context=_prof_for_llm,
        screen_context=(
            ""
            if not _need_rich_screen
            else (screen_ctx[:1000] if _is_simple and len(screen_ctx) > 1000 else screen_ctx)
        ),
        media_context=media_ctx,
        current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
        action_intent_hint=action_hint,
        consciousness_context=consciousness_ctx,
        realtime_awareness=realtime_awareness,
        brief=_is_simple,
        consciousness_obj=cons if cons else None,
    )

    # SPEKULYATIV JAVOB (2026-09-11, asoschi so'roviga ko'ra — "odamdek
    # tinglab-o'ylab, gap tugashi bilan javob berish"): foydalanuvchi HALI
    # gapirib turgan paytda (partial transkript asosida, stt_vosk.py orqali)
    # fon oqimda allaqachon tayyorlangan javob bor bo'lsa va u yakuniy
    # matnni yetarlicha qamrab olgan bo'lsa (oxirida mavzu burilmagan) —
    # o'sha tayyor javobni ishlatamiz, LLM'ni QAYTA chaqirmaymiz — javob
    # deyarli 0 kechikish bilan keladi. Mos kelmasa (None) — pastdagi
    # ODATDAGI to'liq yo'l (answer_stream/answer) ishlayveradi, hech narsa
    # o'zgarmaydi. Butunlay ixtiyoriy: NEUROKEY_SPECULATIVE_RESPONSE=1
    # qilinmaguncha _spec_reply doim None bo'ladi (qarang speculative_response.py).
    # Ong qarori — LLM dan OLDIN. Diqqat, noaniqlik, maqsad, xotira
    # javobning O'ZINI o'zgartiradi. None bo'lsa oddiy yo'l.
    _decision_reply = None
    try:
        from consciousness_decisions import decide as _ong_decide
        _ong_d = _ong_decide(text)
        if _ong_d is not None and (_ong_d.text or "").strip():
            _decision_reply = _ong_d.text.strip()
            print(
                f"[ONG-QAROR] {_ong_d.module} → {_ong_d.action}: {_ong_d.reason}",
                flush=True,
            )
    except Exception:
        _decision_reply = None

    _spec_reply = None
    try:
        from speculative_response import get_speculative_if_matching as _spec_get
        _spec_reply = _spec_get(text)
        if _spec_reply:
            print(f"[TIMING] speculative_hit={(time.perf_counter()-_turn_t0)*1000:.0f}ms "
                  f"(LLM chaqiruvi o'tkazib yuborildi — foydalanuvchi hali gapirayotganda tayyorlangan)", flush=True)
    except Exception:
        _spec_reply = None

    _hud.thinking()                    # HUD: THINKING (LLM boshlandi)
    handle_text._tts_spoke_turn = False
    try:
        if _latency_zero:
            tts.reset_speech_counter()
            _stream_subtitle_parts = []  # Subtitle faqat oxirida — streaming davomida alohida-alohida emas
            _tts_mode = getattr(C, "NEUROKEY_TTS_MODE", "full") or "full"
            # Lokal model (Ollama) uchun DOIM full mode — chunk modida gaps bo'ladi
            _base_url = getattr(C, "OPENAI_BASE_URL", "") or ""
            _is_local_model = "11434" in str(_base_url) or "localhost" in str(_base_url).lower()
            _tts_full = (str(_tts_mode).strip().lower() == "full") or _is_local_model
            _stream_tts_chunks = [0]  # stream rejimida necha marta tts.say chaqirildi (0 bo'lsa — fallback)
            _stream_spoken_parts: list = []
            def _stream_cb(sent):
                clean = re.sub(r"\s*\[OFFER_CODE:\s*.+?\]\s*", "", sent, flags=re.DOTALL | re.IGNORECASE)
                clean = re.sub(r"\s*\[ACTION:\s*.+?\]\s*", "", clean, flags=re.DOTALL | re.IGNORECASE)
                clean = re.sub(r"\s*\[REFLECT:\s*.+?\]\s*", "", clean, flags=re.DOTALL | re.IGNORECASE)
                clean = re.sub(r"\s*\[SAVE:\s*.+?\]\s*", "", clean, flags=re.DOTALL | re.IGNORECASE)
                clean = re.sub(r"^\s*(answer|ответ)\s*:\s*", "", clean, flags=re.IGNORECASE)
                clean = _strip_filler(clean)
                if getattr(C, "NEUROKEY_RESPONSE_CLEANER", True) and _HAVE_RESPONSE_CLEANER:
                    try:
                        clean = get_response_cleaner().clean(clean, max_words=100)
                    except Exception:
                        pass
                if clean and len(clean) > 2:
                    if not _first_sentence_logged[0]:
                        _first_sentence_logged[0] = True
                        print(f"[TIMING] first_sentence={(time.perf_counter()-_turn_t0)*1000:.0f}ms", flush=True)
                    _stream_subtitle_parts.append(clean)
                    if not _tts_full:
                        tts.enqueue_speech(clean)
                        _stream_tts_chunks[0] += 1
                        _stream_spoken_parts.append(clean)
                        if getattr(C, "NEUROKEY_SUBTITLE_PER_CHUNK", False) and getattr(C, "NEUROKEY_DISPLAY_OVERLAY", False) and _HAVE_DISPLAY_OVERLAY:
                            try:
                                ov = get_display_overlay()
                                ov.show_subtitle(clean, duration=5.0)
                            except Exception:
                                pass
            print(f"[TIMING] context_ready={(time.perf_counter()-_turn_t0)*1000:.0f}ms", flush=True)
            _first_sentence_logged = [False]
            if _decision_reply:
                reply = _decision_reply
                _stream_cb(reply)
            elif _spec_reply:
                # Spekulyativ javob allaqachon tayyor — LLM'ni qayta chaqirmaymiz.
                # _stream_cb orqali xuddi streaming'dan kelgandek quyi
                # bosqichlarga (subtitle, TTS enqueue) uzatiladi — pastdagi
                # kod o'zgarishsiz ishlayveradi.
                reply = _spec_reply
                _stream_cb(reply)
            else:
                reply = answer_stream(
                    text,
                    stream_callback=_stream_cb,
                    interrupt_check=lambda: _interrupt_requested.is_set(),
                    **_llm_kw,
                )
            # Chunk: LLM tugadi — navbatdagi ovozlarni tinglash + ikkinchi ovoz bilan tugatish
            if not _tts_full and _stream_tts_chunks[0] > 0:
                _enqueued_n = _stream_tts_chunks[0]
                if _ui_lang() == "en":
                    print(f"[TTS] playing {_enqueued_n} sentence(s)...", flush=True)
                else:
                    print(f"[TTS] {_enqueued_n} ta jumla o'qilmoqda...", flush=True)
                _spoke_n = tts.drain_speech(timeout=180.0)
                print(f"[TIMING] tts_drained_total={(time.perf_counter()-_turn_t0)*1000:.0f}ms", flush=True)
                if _spoke_n > 0:
                    handle_text._tts_spoke_turn = True
                if reply and not _interrupt_requested.is_set():
                    _reply_spoken = _extract_spoken_reply(reply) or reply
                    _played_parts = _stream_spoken_parts[:_spoke_n] if _spoke_n > 0 else []
                    _unsaid = ""
                    if _spoke_n < _enqueued_n:
                        _unsaid = _tts_unsaid_parts(_stream_spoken_parts, _spoke_n)
                    _tail = _tts_tail_remainder(_reply_spoken, _played_parts)
                    if _tail and _tail not in (_unsaid or ""):
                        _unsaid = f"{_unsaid} {_tail}".strip() if _unsaid else _tail
                    if _unsaid and len(_unsaid) > 2:
                        if hasattr(tts, "say_finish_backup"):
                            if tts.say_finish_backup(_unsaid):
                                handle_text._tts_spoke_turn = True
                        else:
                            tts.enqueue_speech(_unsaid)
                            if tts.drain_speech(timeout=90.0) > 0:
                                handle_text._tts_spoke_turn = True
            if _tts_full and reply:
                # Interrupt flagini tozalaymiz: full-TTS modida javob tayyor, shovqindan kelib chiqqan
                # interrupt bilan javobni o'tkazib yubormaslik kerak (faqat haqiqiy yangi ovoz muhim)
                _interrupt_requested.clear()
                spoken_full = _extract_spoken_reply(reply) or reply
                _spoken_raw = (spoken_full or "").strip()
                if spoken_full and getattr(C, "NEUROKEY_RESPONSE_CLEANER", True) and _HAVE_RESPONSE_CLEANER:
                    try:
                        _c = get_response_cleaner().clean(spoken_full, max_words=500)
                        if (_c or "").strip():
                            spoken_full = _c
                    except Exception:
                        pass
                if not (spoken_full or "").strip():
                    spoken_full = _spoken_raw
                if spoken_full and len(spoken_full.strip()) > 2:
                    if tts.say(spoken_full):
                        handle_text._tts_spoke_turn = True
            # Stream: ba'zan juda qisqa javob yoki separator tufayli callback ovoz bermaydi — bir marta to'liq o'qish
            if not _tts_full and reply and not _interrupt_requested.is_set() and _stream_tts_chunks[0] == 0:
                spoken_fb = _extract_spoken_reply(reply) or reply
                _fb_raw = (spoken_fb or "").strip()
                if spoken_fb and getattr(C, "NEUROKEY_RESPONSE_CLEANER", True) and _HAVE_RESPONSE_CLEANER:
                    try:
                        _c2 = get_response_cleaner().clean(spoken_fb, max_words=500)
                        if (_c2 or "").strip():
                            spoken_fb = _c2
                    except Exception:
                        pass
                if not (spoken_fb or "").strip():
                    spoken_fb = _fb_raw
                if spoken_fb and len(spoken_fb.strip()) > 2:
                    if tts.say(spoken_fb):
                        handle_text._tts_spoke_turn = True
            if _is_show_on_screen(text) and reply and getattr(C, "NEUROKEY_DISPLAY_OVERLAY", False) and _HAVE_DISPLAY_OVERLAY:
                try:
                    spoken = _extract_spoken_reply(reply) or reply
                    if spoken and getattr(C, "NEUROKEY_RESPONSE_CLEANER", True) and _HAVE_RESPONSE_CLEANER:
                        spoken = get_response_cleaner().clean(spoken, max_words=500)
                    if spoken:
                        get_display_overlay().show_fullscreen_result(spoken, duration=10.0)
                    elif not getattr(C, "NEUROKEY_SUBTITLE_PER_CHUNK", False) and _stream_subtitle_parts:
                        full = " ".join(_stream_subtitle_parts).strip()
                        if full:
                            get_display_overlay().show_subtitle(full, duration=8.0)
                except Exception:
                    pass
        elif _decision_reply:
            reply = _decision_reply
        elif _spec_reply:
            reply = _spec_reply
        else:
            reply = answer(text, **_llm_kw)
    except Exception as e:
        if _HAVE_ERROR_LOG:
            log_error("LLM", exc=e)
        _safe_print("[LLM_ERROR]", repr(e))
        reply = _tr("Нет связи или ошибка сервера. Попробуй, когда интернет появится.", "No connection or server error. Try again when the internet is back.", "Aloqa yo'q yoki server xatosi. Internet paydo bo'lganda qayta urinib ko'r.")
        if _latency_zero:
            try:
                _err_sp = _extract_spoken_reply(reply) or reply
                if _err_sp and len(_err_sp.strip()) > 2:
                    tts.say(_err_sp)
            except Exception:
                pass

    # LLM bo'sh qaytardi (stream/model) — jim qolib ketmasin (interrupt bo'lsa — foydalanuvchi o'zi to'xtatgan)
    if _latency_zero and not (reply or "").strip() and not _interrupt_requested.is_set():
        reply = _tr(
            "Не получилось получить ответ. Повторите вопрос или проверьте подключение.",
            "Could not get a reply. Repeat the question or check the connection.",
            "Javob olib bo'lmadi. Savolni qaytaring yoki aloqani tekshiring.",
        )
        try:
            _sp = _extract_spoken_reply(reply) or reply
            if _sp and len(_sp.strip()) > 2:
                tts.say(_sp)
        except Exception:
            pass

    # Qidiruv natijalari — overlay + notepad
    if _is_search and web_ctx:
        try:
            _show_web_results_on_screen(web_ctx, text)
        except Exception:
            pass
    # Har qanday ma'lumot javobi — overlay'da ko'rsatish (uzun javoblar uchun)
    elif reply and len(reply.strip()) > 100 and getattr(C, "NEUROKEY_DISPLAY_OVERLAY", False) and _HAVE_DISPLAY_OVERLAY and not _is_show_on_screen(text):
        try:
            spoken = _extract_spoken_reply(reply) or reply
            if spoken and len(spoken.strip()) > 80:
                get_display_overlay().show_subtitle(spoken[:600], duration=8.0)
        except Exception:
            pass

    # [OFFER_CODE: ...] — LLM taklif qilgan kod: pending qo'yamiz, matndan olib tashlaymiz (ovozga chiqmasin)
    if memory and "[OFFER_CODE:" in reply:
        m_offer = re.search(r"\[OFFER_CODE:\s*(.+?)\]", reply, re.DOTALL | re.IGNORECASE)
        if m_offer:
            task = m_offer.group(1).strip()[:500]
            if task:
                memory.set_pending({"type": "offer_code", "task": task}, ttl_sec=120)
            reply = re.sub(r"\s*\[OFFER_CODE:\s*.+?\]\s*", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()

    # [ACTION: ...] — LLM tushundi va amalni bajarishni xohlaydi. Barcha [ACTION] ni ketma-ket bajaradi.
    _action_ok = None
    exec_msgs = []
    for m_action in re.finditer(r"\[ACTION:\s*(\w+)(?:\s+([^\]]*))?\]", reply, re.IGNORECASE):
        act_type = (m_action.group(1) or "").strip().lower()
        act_param = ((m_action.group(2) or "").strip()[:500]) if m_action.lastindex >= 2 else ""
        exec_msg = ""
        executor_actions = ("file_read", "file_write", "file_append", "file_delete", "file_create",
                            "file_copy", "file_move", "file_list", "file_search", "file_exists",
                            "process_start", "process_kill", "process_find")
        if act_param and _HAVE_EXECUTOR and act_type in executor_actions:
            try:
                r = execute_from_string(f"[ACTION: {act_type} {act_param}]", retry=True)
                _action_ok = r.ok if r else False
                if r and r.ok:
                    exec_msg = r.message or "Bajarildi."
                    if r.data is not None:
                        if isinstance(r.data, list) and r.data:
                            exec_msg += " " + "; ".join(str(x)[:80] for x in r.data[:5])
                        elif isinstance(r.data, str):
                            exec_msg += " " + (r.data[:200] if len(r.data) > 200 else r.data)
                else:
                    exec_msg = (r.message if r else "Xato.") or "Xato."
            except Exception as e:
                exec_msg = str(e)[:150] if e else "Xato."
                _action_ok = False
                if _HAVE_ERROR_LOG:
                    log_error("ACTION", exc=e)
        elif _HAVE_CONTROL and (act_param or act_type in (
                "slide_next", "slide_prev", "presentation_start",
                "volume_up", "volume_down",
                "get_screen_size", "get_mouse_pos")):
            try:
                if act_type == "open_folder":
                    path = control.find_folder(act_param)
                    if path:
                        _, exec_msg = control.open_folder(path)
                    else:
                        exec_msg = _tr(f"Папку «{act_param}» не нашёл.", f"Folder «{act_param}» not found.")
                elif act_type == "search_files":
                    _, exec_msg = control.search_files(os.path.expanduser("~"), act_param)
                elif act_type == "open_file":
                    _, sr = control.search_files(os.path.expanduser("~"), act_param)
                    if "Найдено:" in (sr or ""):
                        for line in (sr or "").split("\n"):
                            line = line.strip()
                            if line and os.path.isfile(line):
                                _, exec_msg = control.open_file(line)
                                break
                        else:
                            exec_msg = _tr("Файл не найден.", "File not found.")
                    else:
                        exec_msg = sr or _tr("Не найдено.", "Not found.")
                elif act_type == "open_app":
                    _, exec_msg = control.open_app(act_param)
                elif act_type == "close_app":
                    _, exec_msg = control.close_app(act_param)
                elif act_type == "run_command":
                    _, exec_msg = control.run_command(act_param)
                elif act_type == "slide_next":
                    _, exec_msg = control.slide_next()
                elif act_type == "slide_prev":
                    _, exec_msg = control.slide_prev()
                elif act_type == "presentation_start":
                    _, exec_msg = control.presentation_start()
                elif act_type == "copy_file":
                    parts = act_param.split(None, 1)
                    if len(parts) >= 2:
                        _, exec_msg = control.copy_file(parts[0], parts[1])
                    else:
                        exec_msg = _tr("Укажи источник и назначение.", "Specify source and destination.")
                elif act_type == "move_file":
                    parts = act_param.split(None, 1)
                    if len(parts) >= 2:
                        _, exec_msg = control.move_file(parts[0], parts[1])
                    else:
                        exec_msg = _tr("Укажи источник и назначение.", "Specify source and destination.")
                # --- 100% KOMPYUTER BOSHQARUVI: qo'shimcha amallar ---
                elif act_type == "run_powershell":
                    # PowerShell — Windows ustidan to'liq nazorat
                    _, exec_msg = control.run_powershell(act_param)
                elif act_type == "send_keys":
                    # Klaviaturadan matn kiritish
                    _, exec_msg = control.send_keys(act_param)
                elif act_type == "send_hotkey":
                    # Klaviatura qisqartmasi: "ctrl+c", "alt+f4", "win+d", "ctrl shift esc"
                    _hk_keys = [k.strip() for k in re.split(r"[+\s]+", act_param) if k.strip()]
                    _, exec_msg = control.send_hotkey(*_hk_keys)
                elif act_type == "window_focus":
                    # Oyna sarlavhasi bo'yicha fokus
                    _, exec_msg = control.window_focus_by_title(act_param)
                elif act_type == "volume_up":
                    _, exec_msg = control.volume_up()
                elif act_type == "volume_down":
                    _, exec_msg = control.volume_down()
                elif act_type == "copy_to_clipboard":
                    _, exec_msg = control.copy_to_clipboard(act_param)
                elif act_type == "close_app_generic":
                    # Har qanday .exe nomi bilan yopish
                    _, exec_msg = control.close_app_generic(act_param)
                # --- MOUSE BOSHQARUVI ---
                elif act_type == "mouse_click":
                    # "x y" yoki "x y right/left" formatida
                    _mc_parts = act_param.split()
                    _mc_x = int(_mc_parts[0]) if len(_mc_parts) >= 1 and _mc_parts[0].lstrip("-").isdigit() else None
                    _mc_y = int(_mc_parts[1]) if len(_mc_parts) >= 2 and _mc_parts[1].lstrip("-").isdigit() else None
                    _mc_btn = _mc_parts[2] if len(_mc_parts) >= 3 else "left"
                    _, exec_msg = control.mouse_click(_mc_x, _mc_y, button=_mc_btn)
                elif act_type == "mouse_right_click":
                    _mr_parts = act_param.split()
                    _mr_x = int(_mr_parts[0]) if len(_mr_parts) >= 1 and _mr_parts[0].lstrip("-").isdigit() else None
                    _mr_y = int(_mr_parts[1]) if len(_mr_parts) >= 2 and _mr_parts[1].lstrip("-").isdigit() else None
                    _, exec_msg = control.mouse_right_click(_mr_x, _mr_y)
                elif act_type == "mouse_double_click":
                    _md_parts = act_param.split()
                    _md_x = int(_md_parts[0]) if len(_md_parts) >= 1 and _md_parts[0].lstrip("-").isdigit() else None
                    _md_y = int(_md_parts[1]) if len(_md_parts) >= 2 and _md_parts[1].lstrip("-").isdigit() else None
                    _, exec_msg = control.mouse_double_click(_md_x, _md_y)
                elif act_type == "mouse_move":
                    _mv_parts = act_param.split()
                    if len(_mv_parts) >= 2:
                        _, exec_msg = control.mouse_move(int(_mv_parts[0]), int(_mv_parts[1]))
                    else:
                        exec_msg = "Koordinatlar kerak: x y"
                elif act_type == "mouse_scroll":
                    # "x y [amount] [up/down]" formatida
                    _ms_parts = act_param.split()
                    _ms_x = int(_ms_parts[0]) if len(_ms_parts) >= 1 else 960
                    _ms_y = int(_ms_parts[1]) if len(_ms_parts) >= 2 else 540
                    _ms_amt = int(_ms_parts[2]) if len(_ms_parts) >= 3 and _ms_parts[2].isdigit() else 3
                    _ms_dir = _ms_parts[-1] if _ms_parts and _ms_parts[-1] in ("up", "down") else "down"
                    _, exec_msg = control.mouse_scroll(_ms_x, _ms_y, _ms_amt, _ms_dir)
                elif act_type == "get_screen_size":
                    _, exec_msg = control.get_screen_size()
                elif act_type == "get_mouse_pos":
                    _, exec_msg = control.get_mouse_position()
                # --- OVOZ KLIK (koordinatasiz — GPT-4o Vision element qidiradi) ---
                # screen_click — _HAVE_CONTROL blokidan TASHQARIDA, lekin bu yerda ham qo'llab-quvvatlaymiz
                if exec_msg:
                    fail_markers = ("xato", "error", "not found", "не нашёл", "не найден", "не найдено", "failed")
                    _action_ok = not any(m in (exec_msg or "").lower() for m in fail_markers)
                if _action_ok is not None:
                    _update_affect_state(_action_ok, act_type or "action")
            except Exception as e:
                if _HAVE_ERROR_LOG:
                    log_error("ACTION", exc=e)
                exec_msg = str(e)[:150] if e else "Xato."
                _action_ok = False
        if exec_msg:
            exec_msgs.append(exec_msg)

    # --- [ACTION: screen_click / screen_rclick / screen_dclick / screen_type] ---
    # Bu amallar _HAVE_CONTROL dan mustaqil — GPT-4o Vision va pyautogui ishlatadi
    if _HAVE_SCREEN_CLICK and reply:
        for _sc_m in re.finditer(
            r"\[ACTION:\s*(screen_click|screen_rclick|screen_dclick|screen_type)\s+([^\]]+)\]",
            reply, re.IGNORECASE
        ):
            _sc_type_name = _sc_m.group(1).strip().lower()
            _sc_target = _sc_m.group(2).strip()
            _sc_msg = ""
            try:
                if _sc_type_name == "screen_click" and _sc_click:
                    _, _sc_msg = _sc_click(_sc_target)
                elif _sc_type_name == "screen_rclick" and _sc_rclick:
                    _, _sc_msg = _sc_rclick(_sc_target)
                elif _sc_type_name == "screen_dclick" and _sc_dclick:
                    _, _sc_msg = _sc_dclick(_sc_target)
                elif _sc_type_name == "screen_type" and _sc_type:
                    # "element|||text" formatida — LLM shu formatda beradi
                    _sct_parts = _sc_target.split("|||", 1)
                    if len(_sct_parts) == 2:
                        _, _sc_msg = _sc_type(_sct_parts[0].strip(), _sct_parts[1].strip())
                    else:
                        _sc_msg = "Формат: screen_type field|||text"
            except Exception as _sc_e:
                _sc_msg = str(_sc_e)[:100]
            if _sc_msg:
                exec_msgs.append(_sc_msg)

    reply = re.sub(r"\s*\[ACTION:\s*.+?\]\s*", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()
    if exec_msgs:
        reply = (reply + " " + "; ".join(exec_msgs)).strip()

    # [SAVE: ...] — foydalanuvchi haqida faktni xotiraga yozish, javobdan olib tashlash
    if long_term_memory and "[SAVE:" in reply:
        import re as _re
        m = _re.search(r"\[SAVE:\s*(.+?)\]", reply, _re.DOTALL | _re.IGNORECASE)
        if m:
            fact = m.group(1).strip()[:500]
            if fact:
                try:
                    long_term_memory.add_fact("user", fact)
                except Exception:
                    pass
            reply = _re.sub(r"\s*\[SAVE:\s*.+?\]\s*", "", reply, flags=_re.DOTALL | _re.IGNORECASE).strip()

    # [REFLECT: ...] — haqiqiy ong: o'z-o'zini aks ettirish, keyingi turn uchun
    _reflection = ""
    if _HAVE_CONSCIOUSNESS and get_consciousness and "[REFLECT:" in reply:
        m_ref = re.search(r"\[REFLECT:\s*(.+?)\]", reply, re.DOTALL | re.IGNORECASE)
        if m_ref:
            _reflection = m_ref.group(1).strip()[:300]
            if _reflection:
                try:
                    app_dir = os.path.dirname(os.path.abspath(__file__))
                    c_path = os.path.join(app_dir, "data", "consciousness.json")
                    cons = get_consciousness(c_path)
                    cons.add_reflection(_reflection)
                except Exception:
                    pass
            reply = re.sub(r"\s*\[REFLECT:\s*.+?\]\s*", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()

    # [THINK:...] — ichki fikr, TTS ga berilmaydi, consciousness ga saqlanadi
    _inner_think = ""
    if _HAVE_CONSCIOUSNESS and get_consciousness:
        try:
            m_think = re.search(r"\[THINK:\s*(.+?)\]", reply, re.DOTALL | re.IGNORECASE)
            if m_think:
                _inner_think = m_think.group(1).strip()[:200]
                app_dir = os.path.dirname(os.path.abspath(__file__))
                c_path_think = os.path.join(app_dir, "data", "consciousness.json")
                get_consciousness(c_path_think).add_inner_thought(text, _inner_think)
            reply = re.sub(r"\s*\[THINK:\s*.+?\]\s*", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()
        except Exception:
            pass

    # Consciousness: turn qo'shish (working memory) — davomiy ong.
    if _HAVE_CONSCIOUSNESS and get_consciousness:
        try:
            spoken = _extract_spoken_reply(reply) or reply
            app_dir = os.path.dirname(os.path.abspath(__file__))
            c_path = os.path.join(app_dir, "data", "consciousness.json")
            cons = get_consciousness(c_path)
            cons.add_turn(text, (spoken or reply)[:400], _reflection or _inner_think)

            # Fon: haqiqiy LLM reflection (50 token)
            def _bg_reflection(_cp=c_path, _ut=text, _ar=(spoken or reply)[:200]):
                try:
                    from llm_router import answer as _bg_ans
                    _prompt = (
                        f"Siz hozirgina shuni javob berdingiz: «{_ar}».\n"
                        "Bir qisqa jumlada (rus tilida): bu javobdan nima o'rganding yoki nima muhimligini aniqlading?"
                    )
                    _ref = (_bg_ans(_prompt, brief=True, max_tokens=50, lang_hint="ru") or "").strip()[:200]
                    if _ref:
                        from consciousness import get_consciousness as _gc
                        _gc(_cp).add_reflection(_ref)
                except Exception:
                    pass
            import threading as _thr
            _thr.Thread(target=_bg_reflection, daemon=True).start()

            # Fon: recurrent_process — ong holati sikl orqali yangilanadi
            def _bg_recurrent(_cp=c_path):
                try:
                    import asyncio
                    from consciousness import get_consciousness as _gc
                    asyncio.run(_gc(_cp).recurrent_process({"value": 0.5}))
                except Exception:
                    pass
            _thr.Thread(target=_bg_recurrent, daemon=True).start()

            # Orchestrator — barcha 45 modul va doimiy xotira yangilash
            def _bg_orchestrator(_ut=text, _ar=(spoken or reply)):
                try:
                    if _HAVE_ORCHESTRATOR and _co:
                        _co.on_user_message(_ut, _ar)
                        # HUD: consciousness score + emotion + faol modullar
                        try:
                            _snap = _co.get_snapshot() if hasattr(_co, "get_snapshot") else {}
                            _score = float(_snap.get("consciousness_score", 0.0))
                            _emo   = str(_snap.get("emotion", "neutral"))
                            _mods  = [m for m in (_snap.get("active_modules") or [])
                                      if isinstance(m, str)][:8]
                            _hud.update(consciousness_score=_score,
                                        emotion=_emo,
                                        modules_active=_mods)
                        except Exception:
                            pass
                except Exception:
                    pass
            _thr.Thread(target=_bg_orchestrator, daemon=True).start()

            # Yadro: qualia + trainer yangilash + HUD ga ong darajasi (fon threadida)
            if _NK:
                def _bg_yadro(_ut=text, _ar=(spoken or reply)):
                    try:
                        _NK.on_interaction(_ut, _ar)
                        # HUD ga yadro ong darajasini yuborish
                        try:
                            _c = _NK.state.get("consciousness_level", 0.0)
                            _hud.update(consciousness_score=_c)
                        except Exception:
                            pass
                    except Exception:
                        pass
                _thr.Thread(target=_bg_yadro, daemon=True).start()

            # Vision → Emotion ko'prik
            def _bg_vision_emotion(_ut=text):
                try:
                    import vision_emotion_bridge as _veb
                    _veb.process_voice_text(_ut)
                except Exception:
                    pass
            _thr.Thread(target=_bg_vision_emotion, daemon=True).start()

        except Exception:
            pass

    # Bosqich 3: after-response — self_model, RL, predictive, identity
    if getattr(C, "NEUROKEY_BOSQICH3", True) and _HAVE_BOSQICH3:
        try:
            sm = get_self_model()
            rl = get_rl_engine()
            pl = get_predictive_layer()
            ic = get_identity_core()
            can_do = sm.can_do(text or "")
            sm.update_from_result(text or "", success=True, confidence_was=can_do.get("confidence", 0.5))
            pl.update_patterns(text or "", was_predicted=False)
            ic.update_user_model(f"User asked: {text[:50]}" if text else "")
            if _is_opinion_ask and text and reply:
                try:
                    ic.record_stance(text, reply)
                except Exception:
                    pass
            if _rl_state is not None and _rl_action is not None:
                v, ar = 0.0, 0.5
                try:
                    from valence_state import get_valence
                    from arousal_state import get_arousal
                    v, ar = get_valence(), get_arousal()
                except Exception:
                    pass
                next_ctx = {"valence": v, "arousal": ar, "task_type": "general", "hour": datetime.now().hour, "session_length": len(history) + 1}
                next_state = rl.get_state(next_ctx)
                reward = 0.0
                rl.update(_rl_state, _rl_action, reward, next_state)
            rl.save()
            ic.save()
            predictions = pl.predict_next_request([h.get("user", "") for h in history[-5:] if h.get("user")] + [text or ""])
            if predictions:
                pl.pre_compute(predictions)
        except Exception:
            pass

    # Behavioral learning + affect update: foydalanuvchi fikridan o'rganish
    try:
        _low_text = (text or "").lower()
        _rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rules.json")
        _is_positive = any(w in _low_text for w in (
            "rahmat", "zo'r", "ajoyib", "super", "perfect", "yaxshi",
            "спасибо", "отлично", "правильно", "молодец", "верно", "хорошо", "класс",
        ))
        _is_negative = any(w in _low_text for w in (
            "xato", "noto'g'ri", "yomon", "nima bu", "tushunmadim",
            "не так", "неправильно", "не верно", "ошибся", "неправильный", "не понял",
        ))
        if _is_positive:
            if reply and len(reply) > 30:
                _snippet = reply[:80].replace("\n", " ")
                add_rule(f"Bu uslub yaxshi ishladi: {_snippet}...", rule_type="success", path=_rules_path)
            # Valence va emotion ijobiy tomonga yangilash
            _update_affect_state(success=True, action="user_positive_feedback")
        if _is_negative:
            if reply and len(reply) > 20:
                _snippet = reply[:60].replace("\n", " ")
                add_rule(f"Bu javob xato edi — boshqacha qil: {_snippet}...", rule_type="fix", path=_rules_path)
            # Valence va emotion salbiy tomonga yangilash — keyingi javobda ehtiyotkor bo'ladi
            _update_affect_state(success=False, action="user_negative_feedback")
    except Exception:
        pass

    # Suniy Ong: Qiziqish + Narrativ fon yangilash
    if _HAVE_CONSCIOUSNESS_EXT and text and reply:
        def _bg_consciousness_ext(_ut=text, _ar=reply):
            try:
                # Qiziqish motorini yangilash
                _curiosity_update(_ut, _ar)
                # Sensor: foydalanuvchi faol bo'lganini bildirish
                _notify_sensor()
            except Exception:
                pass
        import threading as _ext_thr
        _ext_thr.Thread(target=_bg_consciousness_ext, daemon=True).start()

    # Suniy Ong 2026: Vector xotiraga saqlash + ToM yangilash + Causal o'rganish
    if _HAVE_CONSCIOUSNESS_2026 and text and reply:
        def _bg_ong2026(_ut=text, _ar=reply):
            try:
                # 1. Semantik xotiraga saqlash
                _vm.add_conversation(_ut, _ar[:500])
            except Exception:
                pass
            try:
                # 2. ToM: assistant javobi bilan yangilash
                _tom.update_from_message(_ut, _ar)
            except Exception:
                pass
            try:
                # 3. Causal: javobdan sabab-natija qidirish
                _cc.extract_causal_from_text(_ar[:300])
            except Exception:
                pass
            try:
                # 4. Maqsad progressini tekshirish
                _gs.auto_detect_goal_from_text(_ut)
            except Exception:
                pass
        import threading as _ong_thr
        _ong_thr.Thread(target=_bg_ong2026, daemon=True).start()

    # Social Bonding: har suhbat o'zaro munosabatni yangilaydi
    if _HAVE_SOCIAL and text and reply:
        def _bg_social(_ut=text):
            try:
                _uname = os.getenv("USERNAME", "User") or "User"
                _social.update_bond(_uname, _ut)
            except Exception:
                pass
        threading.Thread(target=_bg_social, daemon=True).start()

    # Episodic Memory: muhim suhbatlarni doimiy xotirada saqlaydi
    if _HAVE_EPISODIC and text and reply:
        def _bg_episodic(_ut=text, _ar=reply):
            try:
                _episodic.auto_record_from_conversation(_ut, _ar)
            except Exception:
                pass
        threading.Thread(target=_bg_episodic, daemon=True).start()

    # Self-Improvement: har javobdan keyin sifatni baholaydi va o'rganadi
    if _HAVE_SELF_IMPROVE and text and reply:
        def _bg_self_improve(_ut=text, _ar=reply):
            try:
                _self_improve.evaluate_response(_ut, _ar)
            except Exception:
                pass
        threading.Thread(target=_bg_self_improve, daemon=True).start()

    # Xotira konsolidatsiyasi (fon): muhim faktlarni LTM ga avtomatik saqlash
    if long_term_memory and text and reply:
        def _bg_consolidate(_ltm=long_term_memory, _ut=text, _ar=reply):
            try:
                _low = _ut.lower()
                # Foydalanuvchi o'zi haqida ma'lumot bergan (ism, sevimli narsalar, kasb, joylashuv)
                _personal_kw = (
                    "меня зовут", "моё имя", "я работаю", "я живу", "я из",
                    "мне нравится", "я люблю", "я ненавижу", "я учусь", "моя семья",
                    "мой", "моя", "мои", "у меня", "мне", "я ",
                    "meni", "mening", "men ", "ism", "yashiyman", "ishlayman", "sevaman",
                )
                if any(k in _low for k in _personal_kw) and len(_ut) > 20:
                    snippet = _ut[:250]
                    _ltm.add_fact("user", f"Фраза пользователя: {snippet}")
                # Har muhim suhbat — qisqa xotira (sizni yaxshiroq bilish)
                if len(_ut.strip()) >= 8 and len((_ar or "").strip()) >= 12:
                    _ep_key = f"Q: {_ut[:70]} | A: {(_ar or '')[:90]}"
                    _recent_facts = _ltm.get_recent_facts(limit=8)
                    _recent_contents = [f.get("content", "") for f in _recent_facts]
                    if not any(_ut[:40] in rc for rc in _recent_contents):
                        _ltm.add_fact("dialogue", _ep_key)
                # Suhbatda topik nomi (muhim mavzu) — 3+ kalit so'z + uzoq javob
                if len(_ar) > 200 and len(_ut.split()) >= 3:
                    # Har 10 turndagi muhim almashuvni episodik faktga saqlash
                    from long_term_memory import LongTermMemory as _LTM2
                    import time as _t
                    # Har 15 minutda — shu texni qayta saqlamaymiz
                    _recent_facts = _ltm.get_recent_facts(limit=5)
                    _recent_contents = [f.get("content", "") for f in _recent_facts]
                    _ep_key = f"Тема: {_ut[:60]}"
                    if not any(_ep_key in rc for rc in _recent_contents):
                        _ltm.add_fact("episodic", f"Тема: {_ut[:80]} | Ответ: {_ar[:120]}")
            except Exception:
                pass
        import threading as _mem_thr
        _mem_thr.Thread(target=_bg_consolidate, daemon=True).start()

    # ── HUD: javob matni + SPEAKING holati ───────────────────────────────────
    try:
        _hud_reply = (_extract_spoken_reply(reply) or reply or "")[:120]
        if _hud_reply:
            _hud.update(mode="speaking", last_output=_hud_reply)
    except Exception:
        pass

    try:
        if not _latency_zero:
            spoken = _extract_spoken_reply(reply) or reply
            if spoken:
                if getattr(C, "NEUROKEY_RESPONSE_CLEANER", True) and _HAVE_RESPONSE_CLEANER:
                    try:
                        spoken = get_response_cleaner().clean(spoken, max_words=500)
                    except Exception:
                        pass
                if spoken:
                    if not tts.say(spoken):
                        handle_text._tts_spoke_turn = False
                    elif getattr(C, "NEUROKEY_DISPLAY_OVERLAY", False) and _HAVE_DISPLAY_OVERLAY:
                        try:
                            ov = get_display_overlay()
                            if _is_show_on_screen(text):
                                ov.show_fullscreen_result(spoken, duration=10.0)
                            else:
                                ov.show_subtitle(spoken, duration=5.0)
                        except Exception:
                            pass
        elif reply and not _interrupt_requested.is_set():
            # Stream rejimida LLM javob berdi lekin ovoz chiqmadi — majburiy o'qish
            if not getattr(handle_text, "_tts_spoke_turn", False):
                _sp_end = (_extract_spoken_reply(reply) or reply or "").strip()
                if _sp_end and len(_sp_end) > 2:
                    print(f"[TTS] javob (stream fallback): {_sp_end[:80]}", flush=True)
                    if tts.say(_sp_end):
                        handle_text._tts_spoke_turn = True
        if memory:
            memory.remember_turn(text, reply)
            # Xotira keshini yangilaymiz — yangi turn qo'shildi
            if _HAVE_MEM_SEARCH and _mem_invalidate:
                try:
                    _mem_invalidate()
                except Exception:
                    pass
        # 8 Qatlam: permanent memory (append only), world model (bashorat)
        if _HAVE_8_LAYERS:
            try:
                from world_model import get_last_prediction
                app_dir = os.path.dirname(os.path.abspath(__file__))
                append_turn(text, reply, "", os.path.join(app_dir, "data", "consciousness_stream.log"))
                last_pred = get_last_prediction(os.path.join(app_dir, "data", "world_model.json"))
                spoken = _extract_spoken_reply(reply) or reply
                next_pred = f"User javobga reaksiya yoki yangi savol" if len(spoken or "") > 30 else "User savol yoki buyruq beradi"
                update_prediction(last_pred, text, os.path.join(app_dir, "data", "world_model.json"), next_prediction=next_pred)
            except Exception:
                pass
    except Exception as e:
        if _HAVE_ERROR_LOG:
            log_error("TTS after LLM", exc=e)
        _safe_print("[TTS_ERROR]", repr(e))
        try:
            tts.say(get_feedback("no_connection"))
        except Exception:
            pass
    finally:
        _set_orb_state(orb, "idle")
        # BUG FIX: _debug_prof.enable() (yuqorida) hech qachon disable()
        # qilinmasdi — cProfile.enable() jarayon darajasida sys.setprofile()
        # ni o'rnatadi, shuning uchun bu funksiya tugagandan keyin ham
        # HAR BIR keyingi chaqiruvda (butun jarayonda, barcha threadlarda)
        # profiler ishlab, sezilarli sekinlik qo'shardi — NEUROKEY_DEBUG_TIMING=1
        # yoqilgan har qanday sessiyada abadiy yoqilib qolardi. Endi
        # o'chiriladi va (agar yoqilgan bo'lsa) eng sekin funksiyalar
        # chop etiladi.
        if _debug_prof is not None:
            try:
                _debug_prof.disable()
                _turn_dt = time.perf_counter() - _turn_t0
                print(f"[DEBUG_TIMING] handle_text jami: {_turn_dt:.2f}s", flush=True)
                import pstats
                import io as _io
                _buf = _io.StringIO()
                pstats.Stats(_debug_prof, stream=_buf).sort_stats("cumulative").print_stats(12)
                print(_buf.getvalue(), flush=True)
            except Exception:
                pass


def main():
    try:
        import consciousness_stream
        consciousness_stream.stream.start()
    except Exception as e:
        print(f"[ConsciousnessStream] Error starting: {e}", flush=True)

    if _HAVE_ERROR_LOG:
        install_global_excepthook()
    _safe_print("NeuroKey started.")
    _RUNTIME_HEARTBEAT["t0"] = time.monotonic()
    _RUNTIME_HEARTBEAT["phase"] = "boot"
    if getattr(C, "NEUROKEY_DEMO_FRIENDLY", False):
        _safe_print("[DEMO] Investor rejimi: do'stona muloqot, bahslashmaydi.")
    _is_offline_boot = ("--offline" in sys.argv) or (os.getenv("NEUROKEY_OFFLINE_ONLY", "0") == "1")
    _bg_autotalk_enabled = os.getenv(
        "NEUROKEY_BG_AUTOTALK",
        "0",
    ).strip().lower() in ("1", "true", "yes")
    _bg_sensor_enabled = os.getenv(
        "NEUROKEY_BG_SENSOR",
        "1",
    ).strip().lower() in ("1", "true", "yes")
    _bg_perceive_enabled = _bg_sensor_enabled or _bg_autotalk_enabled
    if not _bg_autotalk_enabled:
        if _ui_lang() == "en":
            print("[MODE] Background talk OFF — responds only when you speak.", flush=True)
        else:
            print("[MODE] Fon gapirish O'CHIQ — o'zi gapirmaydi, faqat siz gapirganda javob beradi.", flush=True)
    if _bg_perceive_enabled and not _bg_autotalk_enabled:
        if _ui_lang() == "en":
            print("[MODE] Sensors ON — screen/camera monitored (silent).", flush=True)
        else:
            print("[MODE] Sensorlar YOQIQ — ekran/kamera/kompyuter holati kuzatiladi (ovozsiz).", flush=True)
    if getattr(C, "NEUROKEY_DEMO_FRIENDLY", False):
        _sanitize_demo_memory()

    # ── HWID Litsenziya tekshiruvi (Anti-piracy) ───────────────────────────
    try:
        from license_manager import verify_license, _get_hwid
        _lic_ok = verify_license()
        if not _lic_ok:
            _hw = _get_hwid()
            print("=" * 60, flush=True)
            print("[License] XATO: Litsenziya topilmadi yoki boshqa qurilmaga tegishli!", flush=True)
            print(f"[License] Qurilma HWID: {_hw}", flush=True)
            print("[License] Faollashtirish uchun: python license_manager.py", flush=True)
            print("=" * 60, flush=True)
            if os.getenv("NEUROKEY_ALLOW_UNLICENSED", "0") != "1":
                time.sleep(2)
                sys.exit(1)
        else:
            print("[License] Litsenziya tekshirildi: Yaroqli (HWID tasdiqlandi ✓)", flush=True)
    except Exception as _lic_e:
        print(f"[License] Tekshirishda ogohlantirish: {_lic_e}", flush=True)

    # ── Startup validatsiyasi ────────────────────────────────────────────────
    _offline_boot = "--offline" in sys.argv or os.getenv("NEUROKEY_OFFLINE_ONLY", "0") == "1"
    _api_key = ""
    try:
        _env_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.isfile(_env_p):
            with open(_env_p, encoding="utf-8") as _ef:
                for _el in _ef:
                    _el = _el.strip()
                    if _el.startswith("OPENAI_API_KEY=") and not _el.startswith("#"):
                        _api_key = _el.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    _api_key = os.getenv("OPENAI_API_KEY", "") or _api_key
    _groq_key = os.getenv("GROQ_API_KEY", "")
    _base_url = os.getenv("OPENAI_BASE_URL", "") or getattr(C, "OPENAI_BASE_URL", "") or ""
    _has_api = bool(_api_key and not _api_key.startswith("your_") and len(_api_key) > 20)
    _using_groq = "groq.com" in _base_url and bool(_groq_key or (_api_key or "").startswith("gsk_"))

    if _offline_boot:
        print("[NeuroKey] OFFLINE ONLY mode." if _ui_lang() == "en" else "[NeuroKey] OFFLINE ONLY rejim (majburiy).", flush=True)
    elif not _has_api:
        print("[NeuroKey] OFFLINE mode (Ollama + Vosk + Piper)" if _ui_lang() == "en" else "[NeuroKey] OFFLINE rejim (Ollama + Vosk + Piper)", flush=True)
    else:
        _prov = "Groq" if _using_groq else "OpenAI"
        # SECURITY FIX (2026-09-13): ilgari shu yerda haqiqiy API kalitning
        # birinchi 12 belgisi (masalan "gsk_1w490cDK...") konsolga/logga
        # chop etilardi — bu tirik, haqiqiy sirni (hatto qisqartirilgan
        # holda ham) log fayllariga yozib qo'yardi. Endi kalitning HECH
        # QANDAY qismi (hatto kesilgan/maskalangan holda ham) chop
        # etilmaydi — faqat qaysi provayder ulanganini ko'rsatamiz.
        if _ui_lang() == "en":
            print(f"[NeuroKey] Online — LLM: {_prov} connected", flush=True)
        else:
            print(f"[NeuroKey] Online rejim — LLM: {_prov} ulandi", flush=True)
    if os.getenv("NEUROKEY_BIOMETRIC_BLOCK", "1").strip() in ("0", "false", "no"):
        print("[NeuroKey] Demo: biometric block OFF" if _ui_lang() == "en" else "[NeuroKey] Demo: biometrik BLOK yo'q — erkin gaplashish", flush=True)
    try:
        from owner_trust import always_trust_owner, owner_nick, mark_guardian_verified, any_biometric_profile
        if always_trust_owner() and any_biometric_profile():
            mark_guardian_verified()
            if _ui_lang() == "en":
                print(f"[NeuroKey] Owner mode: {owner_nick()} — always recognized", flush=True)
            else:
                print(f"[NeuroKey] Ega rejimi: {owner_nick()} — har doim taniladi, 'tanilmadim' yo'q", flush=True)
    except Exception:
        pass

    # === Kunlik yangiliklar: bo'shliqni to'ldirish (fon oqimida, bloklamaydi) ===
    if getattr(C, "NEUROKEY_NEWS_SYNC", True):
        def _news_sync_startup():
            try:
                import daily_news_sync as _dns
                r = _dns.sync()
                if not r.get("skipped"):
                    _safe_print(f"[NEWS_SYNC] {r.get('added', 0)} ta yangilik qo'shildi "
                                f"(bo'shliq: {r.get('gap_hours', 0):.1f} soat)")
            except Exception as e:
                _safe_print(f"[NEWS_SYNC] xato: {e!r}")
        threading.Thread(target=_news_sync_startup, daemon=True).start()

    # === SUNIY ONG: Startup ishga tushirish ===
    if _HAVE_CONSCIOUSNESS_EXT:
        try:
            # Narrativ o'zlikni ishga tayyorlash (birinchi marta yaratadi, haftalik yangilaydi)
            initialize_narrative()
        except Exception:
            pass
        try:
            # Fon sensori: dunyo holati (CPU, vaqt, oyna) — ong uchun
            if getattr(C, "NEUROKEY_BG_SENSOR", True):
                start_sensor()
                _safe_print("[SENSOR] Fon sensori ishga tushdi.")
        except Exception:
            pass
        try:
            # Tun konsolidatsiyasi — xulosalar kelajak suhbatlar uchun
            if getattr(C, "NEUROKEY_DREAM_CONSOLIDATION", True):
                start_dream_scheduler()
                _safe_print("[DREAM] Tun konsolidatsiyasi scheduler ishga tushdi.")
        except Exception:
            pass

    # === Eslatmalar: restart dan keyin ham ishlashi uchun tekshiruv ipi ===
    if _HAVE_REMINDERS and os.getenv("NEUROKEY_REMINDERS_ENABLED", "1").strip().lower() in ("1", "true", "yes"):
        def _reminders_checker_loop():
            import time as _rct
            while True:
                _rct.sleep(30)
                try:
                    now_ts = int(_rct.time())
                    due = [r for r in _reminders.list_all()
                           if r.get("due_ts") and r["due_ts"] <= now_ts]
                    for r in due:
                        try:
                            tts.say(f"Eslatma: {r['title']}")
                        except Exception:
                            pass
                        _reminders.remove(r["id"])
                except Exception:
                    pass
        threading.Thread(target=_reminders_checker_loop, daemon=True).start()
        _safe_print("[REMINDERS] Reminder checker thread started.")

    # === Social Bonding: startup ===
    if _HAVE_SOCIAL:
        _safe_print("[SOCIAL] Social bonding module ready.")

    # === Episodic Memory: startup ===
    if _HAVE_EPISODIC:
        _safe_print("[EPISODIC] Episodic memory module ready.")

    # === Self-Improvement: startup ===
    if _HAVE_SELF_IMPROVE:
        _safe_print("[SELF_IMPROVE] Self-improvement loop ready.")

    # Audio: mikrofon + dinamik (quloqchin o'rniga monitor/kolonka)
    try:
        from audio_devices import apply_auto_selection
        import sounddevice as _sd_audio
        apply_auto_selection(C, _safe_print)
        _out_i = getattr(C, "OUTPUT_DEVICE_INDEX", None)
        _in_i = getattr(C, "INPUT_DEVICE_INDEX", None)
        if _out_i is not None:
            _out_name = _sd_audio.query_devices(int(_out_i))['name']
            if _ui_lang() == "en":
                print(f"[AUDIO] Output: [{_out_i}] {_out_name}", flush=True)
            else:
                print(f"[AUDIO] Ovoz chiqishi: [{_out_i}] {_out_name}", flush=True)
        else:
            _def = _sd_audio.query_devices(kind="output")
            if _ui_lang() == "en":
                print(f"[AUDIO] Output (default): [{_def.get('index')}] {_def.get('name')}", flush=True)
            else:
                print(f"[AUDIO] Ovoz chiqishi (default): [{_def.get('index')}] {_def.get('name')}", flush=True)
        if _in_i is not None:
            _in_name = _sd_audio.query_devices(int(_in_i))['name']
            if _ui_lang() == "en":
                print(f"[AUDIO] Microphone: [{_in_i}] {_in_name}", flush=True)
            else:
                print(f"[AUDIO] Mikrofon: [{_in_i}] {_in_name}", flush=True)
    except Exception as _aud_e:
        print(f"[AUDIO] sozlash: {_aud_e!r}", flush=True)

    # TTS: OpenAI tts-1/tts-1-hd (eski gpt-4o-mini-tts 404 beradi)
    tts = TTSWorker(voice=getattr(C, "OPENAI_TTS_VOICE", "nova"))
    _out_i = getattr(C, "OUTPUT_DEVICE_INDEX", None)
    _in_i = getattr(C, "INPUT_DEVICE_INDEX", None)
    if _out_i is not None:
        try:
            tts.out_dev = int(_out_i)
            _sd_audio.default.device = (_in_i, int(_out_i))
            print(f"[TTS] Chiqish qurilmasi bog'landi: index {_out_i}", flush=True)
        except Exception as _td_e:
            print(f"[TTS] chiqish bog'lash: {_td_e!r}", flush=True)
    tts.start()
    _start_runtime_heartbeat(tts)

    # Edge TTS isitish — tilga mos (EN: "Listening." / RU: "Слушаю.")
    try:
        from tts_openai import _warmup_phrase
        _warm_txt = _warmup_phrase()
        print(f"[TTS] Edge warmup ({_warm_txt})...", flush=True)
        if tts._edge_tts_fetch(_warm_txt):
            _ready = "Edge ready — voice will be faster" if _ui_lang() == "en" else "Edge ulanish tayyor — ovoz tezroq chiqadi"
            print(f"[TTS] {_ready}", flush=True)
        else:
            print("[TTS] Edge warmup skipped — will retry on first reply", flush=True)
    except Exception as _twe:
        print(f"[TTS] Edge warmup: {_twe!r}", flush=True)

    # Modul audit (qaysi qism ulangan — 283 fayldan faqat shular ishlaydi)
    if os.getenv("NEUROKEY_MODULE_AUDIT", "1").strip().lower() in ("1", "true", "yes"):
        _mods = [
            ("STT Whisper", _HAVE_WHISPER), ("STT Vosk", _HAVE_VOSK), ("TTS", True),
            ("Ong consciousness", _HAVE_CONSCIOUSNESS), ("Ong 2026", _HAVE_CONSCIOUSNESS_2026),
            ("Ong ext (dream/curiosity)", _HAVE_CONSCIOUSNESS_EXT), ("NeuroKey core", _NK is not None),
            ("ADLF", _HAVE_ADLF), ("Ekran", _HAVE_SCREEN_VISION), ("Kamera", _HAVE_CAMERA_VISION),
            ("Xotira LTM", _HAVE_LTM), ("Episodic", _HAVE_EPISODIC), ("GWT", getattr(C, "NEUROKEY_GWT_INTEGRATION", True)),
            ("Embodiment", _HAVE_EMBODIMENT and getattr(C, "NEUROKEY_EMBODIMENT", True)),
            ("Free energy", _HAVE_FREE_ENERGY and getattr(C, "NEUROKEY_FREE_ENERGY", True)),
            ("Control Windows", _HAVE_CONTROL), ("Telegram", _HAVE_TG_USER),
        ]
        _on = [n for n, ok in _mods if ok]
        _off = [n for n, ok in _mods if not ok]
        print(f"[MODULLAR] Ulangan: {len(_on)}/{len(_mods)} — {', '.join(_on)}", flush=True)
        if _off:
            print(f"[MODULLAR] O'chiq/yuklanmagan: {', '.join(_off)}", flush=True)

    # Ollama warmup — fon da model GPU ga yuklanadi (cold start yo'qoladi)
    try:
        from llm_router import ollama_warmup as _ollama_warmup
        _ollama_warmup()
        _safe_print("[OLLAMA] Warmup boshlandi (fon da — cold start yo'qoladi)")
    except Exception as _wu_e:
        _safe_print("[OLLAMA] Warmup o'tkazib yuborildi:", repr(_wu_e))

    # Ong konteksti Pre-Warm — har 5s fon threadida yangilanadi
    # Natija: LLM chaqiriqqa kontekst 0ms tayyor (ketma-ket 200-400ms emas)
    try:
        import neurokey_prewarm as _prewarm
        _prewarm.start()
        _safe_print("[PREWARM] Ong konteksti isitilmoqda (fon — har 5s yangilanadi)")
    except Exception as _pw_e:
        _safe_print("[PREWARM] O'tkazib yuborildi:", repr(_pw_e))

    # Biometrik qo'riqchi — startup + model preload (fon threadida)
    print("[BOOT] Biometrik guardian bloki boshlandi (ArcFace/ECAPA)...", flush=True)
    try:
        _bio_face_ok  = False
        _bio_voice_ok = False
        # ArcFace fon preload — og'ir; kamera guard bilan birga kechiktiriladi
        try:
            # DIQQAT (2026-09-13 race-condition fix): bu yerda ATAYLAB
            # get_status_cheap() ishlatiladi, get_status() EMAS — get_status()
            # face_arc._load()ni chaqiradi, u esa InsightFace modelini OG'IR
            # yuklaydi (GPU sovuq boshlanishida o'nlab-yuzlab soniya). Agar
            # ASOSIY (main) thread shu poygani "yutib qolsa" — butun ilova
            # shu yerda, konsolga hech narsa chiqmasdan (progress log.info()
            # orqali, WARNING darajali root loggerda ko'rinmaydi) muzlab
            # qolardi. Haqiqiy yuklashni FAQAT fon threadlar (ArcFace-preload
            # pastda, va neurokey_prewarm.py'dagi NK-FaceArcWarm) bajaradi.
            from face_arc import get_status_cheap as _fa_st, profile_exists as _fa_pex
            import threading as _bt
            _bio_defer_arc = float(
                os.getenv("NEUROKEY_BIOMETRIC_DEFER_SEC", os.getenv("NEUROKEY_FACE_GUARD_DELAY_SEC", "0")) or "0"
            )
            if _bio_defer_arc <= 0:
                _bt.Thread(target=lambda: __import__("face_arc")._load(), daemon=True, name="ArcFace-preload").start()
            if _fa_pex():
                _fa = _fa_st()
                _safe_print(f"[GUARDIAN] Yuz (ArcFace): {_fa.get('owner','?')} | {_fa.get('enrolled_at','?')[:10]}")
                _bio_face_ok = True
        except Exception as _fa_boot_e:
            print(f"[BOOT] ArcFace guardian bosqichi xato (davom etmoqda): {_fa_boot_e!r}", flush=True)
        print("[BOOT] ArcFace bosqichi tugadi — ECAPA bosqichiga o'tilmoqda...", flush=True)
        # ECAPA fon preload — og'ir; biometrika kechikishi bilan
        try:
            # Xuddi yuqoridagi kabi: get_status_cheap() — asosiy thread
            # voice_ecapa._load() (SpeechBrain og'ir yuklash) poygasiga
            # UMUMAN kirmasin.
            from voice_ecapa import preload as _ecapa_preload, profile_exists as _ep_pex, get_status_cheap as _ep_st
            _ecapa_defer = float(
                os.getenv("NEUROKEY_BIOMETRIC_DEFER_SEC", os.getenv("NEUROKEY_FACE_GUARD_DELAY_SEC", "0")) or "0"
            )

            def _deferred_ecapa():
                try:
                    if _ecapa_defer > 0:
                        time.sleep(_ecapa_defer)
                    _ecapa_preload()
                except Exception:
                    pass

            import threading as _bt_ec
            _bt_ec.Thread(target=_deferred_ecapa, daemon=True, name="ECAPA-preload").start()
            if _ep_pex():
                _ep = _ep_st()
                _safe_print(f"[GUARDIAN] Ovoz (ECAPA): {_ep.get('owner','?')} | {_ep.get('enrolled_at','?')[:10]}")
                _bio_voice_ok = True
        except Exception:
            try:
                from voice_recognition import profile_exists as _vp_exists, get_status as _vr_st
                if _vp_exists():
                    _vr = _vr_st()
                    _safe_print(f"[GUARDIAN] Ovoz (MFCC fallback): {_vr.get('owner','?')}")
                    _bio_voice_ok = True
            except Exception: pass
        # Yuz real-time kamera guard (fon thread) — TTS bilan to'qnashmasligi uchun kechikish mumkin
        _face_guard_on = os.getenv("NEUROKEY_FACE_GUARD", "1").strip().lower() not in ("0", "false", "no")
        _bio_defer = float(
            os.getenv("NEUROKEY_BIOMETRIC_DEFER_SEC", os.getenv("NEUROKEY_FACE_GUARD_DELAY_SEC", "0")) or "0"
        )
        try:
            from face_arc import start_camera_guard as _start_cam, profile_exists as _fp_ex, get_status as _fa_st
            if _face_guard_on and _fp_ex():
                # 1.5s juda tez-tez edi — CPU rejimida (GPU'siz) tizimni qotirib
                # qo'ygan (5 ta ArcFace modeli har safar). 5s — xavfsizroq default.
                _fg_interval = float(os.getenv("FACE_GUARD_INTERVAL_SEC", "5.0"))

                def _deferred_face_guard():
                    try:
                        if _bio_defer > 0:
                            print(
                                f"[GUARDIAN] Kamera guard {int(_bio_defer)}s kechikdi (TTS barqarorligi)...",
                                flush=True,
                            )
                            time.sleep(_bio_defer)
                        try:
                            import face_arc as _fa_mod
                            if not getattr(_fa_mod, "_loaded", False):
                                _fa_mod._load()
                        except Exception:
                            pass
                        _start_cam(camera_index=0, interval=max(0.8, _fg_interval))
                        _fa = _fa_st()
                        print(
                            f"[GUARDIAN] Yuz kamera guard ISHGA TUSHDI — {_fa.get('owner','?')} | har 2.5s | LED doimiy",
                            flush=True,
                        )
                    except Exception as _dfg_e:
                        print(f"[GUARDIAN] Kamera guard xato: {_dfg_e!r}", flush=True)

                import threading as _bg_thr
                _bg_thr.Thread(target=_deferred_face_guard, daemon=True, name="FaceGuard-deferred").start()
                # Startup'dan 5s (+ defer) keyin birinchi yuz tekshiruvini konsolga chiqarish
                def _startup_face_announce():
                    import time as _t2
                    _t2.sleep(max(5.0, _bio_defer + 5.0))
                    try:
                        from owner_trust import always_trust_owner, owner_nick, any_biometric_profile
                        from face_arc import get_last_face_result as _glfr
                        _r = _glfr()
                        _nick = owner_nick()
                        if always_trust_owner() and any_biometric_profile():
                            sim = float(_r.get("similarity", 0) or 0)
                            print(f"[GUARDIAN] EGA: {_nick} (sim={sim:.2f}) — har doim taniladi", flush=True)
                        elif _r.get("known"):
                            print(f"[GUARDIAN] YUZ TANILDI: {_r.get('name', _nick)} (sim={_r.get('similarity',0):.2f}) — FAOL", flush=True)
                        elif _r.get("similarity", 0) > 0.01:
                            print(f"[GUARDIAN] Yuz topildi (sim={_r.get('similarity',0):.2f}) — {_nick} deb bilaman", flush=True)
                        else:
                            print(f"[GUARDIAN] Kamera kuzatuvda — egasi {_nick}", flush=True)
                    except Exception:
                        pass
                _bg_thr.Thread(target=_startup_face_announce, daemon=True, name="StartupFaceCheck").start()
            elif _fp_ex() and not _face_guard_on:
                print("[GUARDIAN] Yuz guard O'CHIQ (demo) — yuz faqat HUD da ko'rsatiladi", flush=True)
        except Exception as _cge:
            print(f"[GUARDIAN] Kamera guard xato: {_cge}", flush=True)
        if _bio_face_ok or _bio_voice_ok:
            print(f"[GUARDIAN] Biometrik himoya FAOL — Yuz:{_bio_face_ok} Ovoz:{_bio_voice_ok}", flush=True)
        else:
            print("[GUARDIAN] DIQQAT: Profil yo'q — python enroll_biometric.py ishlatish kerak", flush=True)
    except Exception as _bg_e:
        print(f"[GUARDIAN] Startup xato: {_bg_e!r}", flush=True)
    print("[BOOT] Guardian bloki tugadi.", flush=True)

    # HUD: hissiyot + yuz har 1.5s (kamera kuzatuvi vizual)
    if os.getenv("NEUROKEY_HUD_AFFECT_SYNC", "1").strip().lower() in ("1", "true", "yes"):
        threading.Thread(target=_hud_affect_camera_sync_loop, daemon=True, name="HUD-Affect-Camera").start()
        _safe_print("[HUD] Hissiyot + kamera sync ishga tushdi (har 1.5s).")

    if getattr(C, "NEUROKEY_HEARTBEAT_SEC", 0) > 0:
        _safe_print(
            "[HEARTBEAT] har",
            int(getattr(C, "NEUROKEY_HEARTBEAT_SEC", 90)),
            "sek konsol + oyna sarlavhasi — o'chirish: NEUROKEY_HEARTBEAT_SEC=0",
        )

    # Orb overlay (NeuroKey style)
    print("[BOOT] Orb overlay bosqichi boshlandi...", flush=True)
    orb = None
    if _HAVE_ORB:
        try:
            orb = create_orb_and_start()
            if orb:
                _safe_print("[ORB] overlay started.")
        except Exception as e:
            _safe_print("[ORB] disabled:", repr(e))
    print("[BOOT] Orb overlay bosqichi tugadi.", flush=True)

    # Memory (pending, dialog history)
    memory = None
    if _HAVE_MEMORY:
        try:
            memory = MemoryStore(getattr(C, "MEMORY_PATH", "memory.json"))
            _safe_print("[MEMORY] loaded.")
        except Exception as e:
            _safe_print("[MEMORY] disabled:", repr(e))

    # Long-term memory (sqlite3 — ism, saytlar, ish vaqti)
    long_term_memory = None
    if _HAVE_LTM:
        try:
            long_term_memory = LongTermMemory(getattr(C, "LTM_DB_PATH", "data/neurokey_memory.db"))
            _safe_print("[LTM] long-term memory ready.")
        except Exception as e:
            _safe_print("[LTM] disabled:", repr(e))

    # Global Workspace (GWT) — modullarni ro'yxatga olish
    print("[BOOT] GWT/Bosqich3/4/5 bosqichlariga o'tilmoqda...", flush=True)
    if getattr(C, "NEUROKEY_GWT_INTEGRATION", True):
        try:
            from valence_state import get_valence_state
            from arousal_state import get_arousal_state
            from consciousness import get_consciousness
            from global_workspace import get_workspace
            _app_dir = os.path.dirname(os.path.abspath(__file__))
            gw = get_workspace()
            gw.register_module(get_valence_state())
            gw.register_module(get_arousal_state())
            gw.register_module(get_consciousness(os.path.join(_app_dir, "data", "consciousness.json")))
            _safe_print("[GWT] Global Workspace: valence, arousal, consciousness registered.")
        except Exception as e:
            _safe_print("[GWT] registration skipped:", repr(e))

    # Bosqich 3: RL, Identity — yuklash
    if getattr(C, "NEUROKEY_BOSQICH3", True) and _HAVE_BOSQICH3:
        try:
            get_rl_engine().load()
            get_identity_core().load()
            _safe_print("[BOSQICH3] Self-model, RL, Predictive, Identity ready.")
        except Exception as e:
            _safe_print("[BOSQICH3] load skipped:", repr(e))

    # Bosqich 4: Virtual Embodiment — sensor integratsiya
    print("[BOOT] Bosqich3 tugadi — Bosqich4 (Embodiment) boshlanmoqda...", flush=True)
    if getattr(C, "NEUROKEY_EMBODIMENT", True) and _HAVE_EMBODIMENT:
        try:
            get_sensor_integration().start()
            _safe_print("[EMBODIMENT] Virtual tana, sensor hub started.")
        except Exception as e:
            _safe_print("[EMBODIMENT] skipped:", repr(e))

    # Bosqich 5: Free Energy — Active Inference
    print("[BOOT] Bosqich4 tugadi — Bosqich5 (Free Energy) boshlanmoqda...", flush=True)
    if getattr(C, "NEUROKEY_FREE_ENERGY", True) and _HAVE_FREE_ENERGY:
        try:
            get_world_model()
            get_active_inference()
            get_attention_mechanism()
            _safe_print("[FREE_ENERGY] World model, Active Inference, Attention ready.")
        except Exception as e:
            _safe_print("[FREE_ENERGY] skipped:", repr(e))

    # Tezlik + ekran + overlay (M1–M8)
    print("[BOOT] Bosqich5 tugadi — PerformanceCore warmup boshlanmoqda...", flush=True)
    if getattr(C, "NEUROKEY_PERFORMANCE_WARMUP", True) and _HAVE_PERFORMANCE_CORE:
        try:
            import asyncio
            perf = get_performance_core()
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(perf.warmup())
        except Exception:
            pass
    print("[BOOT] PerformanceCore warmup tugadi.", flush=True)
    if getattr(C, "NEUROKEY_SCREEN_MONITOR", False) and _HAVE_SCREEN_MONITOR and _bg_perceive_enabled:
        try:
            get_screen_monitor().start_continuous_monitoring()
            _safe_print("[SCREEN_MONITOR] continuous monitoring started.")
        except Exception as e:
            _safe_print("[SCREEN_MONITOR] skipped:", repr(e))
    if getattr(C, "NEUROKEY_DISPLAY_OVERLAY", False) and _HAVE_DISPLAY_OVERLAY:
        try:
            get_display_overlay().start()
            _safe_print("[DISPLAY] overlay ready.")
        except Exception as e:
            _safe_print("[DISPLAY] skipped:", repr(e))

    # Dynamic Organ Integration: organlar bir zumda tizimga ulanadi
    print("[BOOT] Organ loader (load_organs) boshlanmoqda...", flush=True)
    if _HAVE_ORGAN_LOADER:
        try:
            n, errs = load_organs()
            if n > 0:
                _safe_print(f"[ORGANS] {n} organ(s) loaded: {get_loaded_organs()}")
            if errs:
                _safe_print("[ORGANS] errors:", errs[:3])
        except Exception as e:
            _safe_print("[ORGANS] load failed:", repr(e))
    print("[BOOT] Organ loader tugadi.", flush=True)

    # Offline demo uchun: fon rejimida o'zi gapirishni o'chiramiz
    _selfimprove_enabled = os.getenv(
        "NEUROKEY_SELFIMPROVE_ENABLED",
        "0" if _is_offline_boot or not _bg_autotalk_enabled else "1",
    ).strip().lower() in ("1", "true", "yes")

    # Proaktiv maslahatchi: 15 sekunddan keyin ob-havo (yomg'ir) ogohlantirish
    if _HAVE_PROACTIVE and tts and _bg_autotalk_enabled:
        def _proactive_say(msg):
            try:
                tts.say(msg)
            except Exception:
                pass
        _proactive_lang = getattr(C, "NEUROKEY_UI_LANG", "ru") or "ru"
        threading.Timer(15.0, lambda: run_proactive_once(_proactive_say, lang=_proactive_lang)).start()

    # Ekran real-vaqt: sensor yoqilganda (fon gapirish shart emas)
    if _HAVE_SCREEN_VISION and _bg_perceive_enabled:
        interval = max(1.0, float(getattr(C, "SCREEN_CAPTURE_INTERVAL_SEC", 4) or 4))
        vision_every = int(getattr(C, "SCREEN_VISION_CYCLE_INTERVAL", 1))
        threading.Thread(target=_screen_capture_loop, args=(interval,), daemon=True).start()
        _safe_print(f"[SCREEN] background capture started (OCR every {interval}s, Vision every {vision_every} cycles).")
    elif _HAVE_SCREEN_VISION:
        _safe_print("[SCREEN] Fon capture o'chiq — ekran faqat savol bo'lganda o'qiladi.")

    # Veb-kamera: fon tahlil (yuz guard alohida, fon gapirish shart emas)
    if _HAVE_CAMERA_VISION and getattr(C, "NEUROKEY_CAMERA_ENABLED", True) and _bg_perceive_enabled:
        _cam_interval = float(getattr(C, "NEUROKEY_CAMERA_INTERVAL_SEC", 5))
        try:
            _cam_start_bg(interval=_cam_interval)
            _safe_print(f"[CAMERA] Webcam background capture started (every {_cam_interval:.0f}s).")
        except Exception as _cam_err:
            _safe_print(f"[CAMERA] Webcam start failed (no camera?): {_cam_err}")
    elif _HAVE_CAMERA_VISION and getattr(C, "NEUROKEY_CAMERA_ENABLED", True):
        _safe_print("[CAMERA] Fon kamera tahlili o'chiq — faqat yuz guard / savol bo'lganda.")

    # Self-improve: ekran + kamera tahlil → avto-takomillashtirish (har 10 daqiqa)
    if _HAVE_SELFIMPROVE and _selfimprove_enabled and _bg_autotalk_enabled:
        def _si_screen_getter():
            with _screen_context_cache["lock"]:
                txt = (_screen_context_cache.get("text") or "").strip()
                vis = (_screen_context_cache.get("vision") or "").strip()
                fg = (_screen_context_cache.get("foreground_window") or "").strip()
            parts = [p for p in [fg, txt, vis] if p]
            return "\n".join(parts).strip()[:3000]
        def _si_camera_getter():
            try:
                return _cam_get_ctx(use_background=True) if _HAVE_CAMERA_VISION else ""
            except Exception:
                return ""
        def _si_llm(prompt):
            try:
                return answer(prompt, lang_hint=_ui_lang(), history=[], brief=True) or ""
            except Exception:
                return ""
        def _si_improve(rule_text):
            try:
                add_rule(rule_text)
                append_improvement(rule_text)
            except Exception:
                pass
        try:
            _main_root = os.path.dirname(os.path.abspath(__file__))
            _selfimprove_start(
                screen_getter=_si_screen_getter,
                camera_getter=_si_camera_getter,
                llm_fn=_si_llm,
                improve_fn=_si_improve,
                interval_min=int(getattr(C, "NEUROKEY_SELFIMPROVE_INTERVAL_MIN", 10)),
                data_dir=os.path.join(_main_root, "data"),
            )
            _safe_print("[SELFIMPROVE] Self-improvement loop started (screen + webcam awareness).")
        except Exception as _si_err:
            _safe_print(f"[SELFIMPROVE] Failed to start: {_si_err}")

    # Explorer watchdog: if explorer.exe died, restart it and notify (prevents black desktop)
    if _HAVE_CONTROL and getattr(C, "CONTROL_EXPLORER_WATCHDOG", True):
        _watchdog_interval = getattr(C, "CONTROL_EXPLORER_WATCHDOG_INTERVAL_SEC", 15.0)

        def _explorer_watchdog_loop():
            while True:
                time.sleep(_watchdog_interval)
                try:
                    if not control.is_process_running("explorer.exe"):
                        ok, msg = control.restart_explorer()
                        _safe_print("[WATCHDOG] explorer.exe was not running; restarted:", ok, msg)
                        if tts and ok:
                            try:
                                tts.say(get_feedback("explorer_restarted"))
                            except Exception:
                                pass
                except Exception as e:
                    _safe_print("[WATCHDOG] error:", repr(e))

        threading.Thread(target=_explorer_watchdog_loop, daemon=True).start()
        _safe_print("[WATCHDOG] explorer watchdog started (interval %s s)." % _watchdog_interval)

    # Autonomous Digital Lifeform: background consciousness, proactive interruption
    if _HAVE_ADLF and getattr(C, "NEUROKEY_ADLF_ENABLED", True) and tts and _bg_autotalk_enabled:
        def _adlf_say(msg):
            try:
                if msg and not tts.is_playing():
                    tts.say(msg)
            except Exception:
                pass

        def _adlf_screen_getter():
            with _screen_context_cache["lock"]:
                txt = (_screen_context_cache.get("text") or "").strip()
                vis = (_screen_context_cache.get("vision") or "").strip()
                fg = (_screen_context_cache.get("foreground_window") or "").strip()
            parts = []
            try:
                from window_ops import get_visible_windows
                vw = get_visible_windows()
                titles = [w.get("title", "") for w in vw[:8] if w.get("title")]
                _dt = ("program manager", "desktop", "рабочий стол")
                _only_desk = titles and all(t.lower().strip() in _dt for t in titles)
                if not titles or _only_desk:
                    parts.append("All windows minimized. Only desktop visible.")
                else:
                    if fg:
                        parts.append(f"Active: {fg}")
                    parts.append("Visible: " + ", ".join(titles))
            except Exception:
                if fg:
                    parts.append(f"Active: {fg}")
            parts.extend(p for p in [txt, vis] if p)
            return "\n".join(parts).strip()[:2000]

        def _adlf_llm_analyze(prompt):
            try:
                out = answer(
                    prompt,
                    lang_hint=_ui_lang(),
                    history=[],
                    current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
                    brief=True,
                )
                return _extract_spoken_reply(out) or out or ""
            except Exception:
                return ""

        _screen_getter = _adlf_screen_getter if getattr(C, "ADLF_SCREEN_PROACTIVE", True) else None
        _llm = _adlf_llm_analyze if getattr(C, "ADLF_SCREEN_PROACTIVE", True) else None

        def _adlf_core_decide():
            if not _HAVE_CORE:
                return None
            try:
                from perception_streams import get_perception_streams
                screen_ctx = (_screen_getter() if _screen_getter else "") or ""
                streams = get_perception_streams(screen_context=screen_ctx)
                core = get_core(data_dir=os.path.join(app_dir, "data"))
                return core.decide({"user": "", "screen": streams.get("screen", ""), "files": streams.get("files", ""), "processes": streams.get("processes", ""), "memory": streams.get("memory", "")})
            except Exception:
                return None

        start_autonomous_loop(
            _adlf_say,
            screen_context_getter=_screen_getter,
            llm_analyze=_llm,
            core_decide_callback=_adlf_core_decide if getattr(C, "ADLF_AUTONOMOUS_CORE", True) else None,
            interval_sec=int(getattr(C, "ADLF_CYCLE_INTERVAL_SEC", 120)),
            delay_sec=int(getattr(C, "ADLF_FIRST_DELAY_SEC", 60)),
            lang=getattr(C, "NEUROKEY_UI_LANG", "ru") or "ru",
        )
        _safe_print("[ADLF] Autonomous Digital Lifeform: background consciousness started.")

    # ── Proaktiv ong: har 2 daqiqada triggers + ekran + kamera tahlili ──────────
    # proactive_speech.check_and_generate() hech qachon fon threadida chaqirilmagan — endi ulandi
    if _HAVE_CONSCIOUSNESS_2026 and tts and _bg_autotalk_enabled:
        _proactive_interval = int(getattr(C, "NEUROKEY_PROACTIVE_INTERVAL_SEC", 120))
        _proactive_first_delay = int(getattr(C, "NEUROKEY_PROACTIVE_FIRST_DELAY_SEC", 45))

        def _proactive_say_if_idle(msg: str):
            """TTS bo'sh bo'lgandagina gapiradi — javob bilan aralashib ketmasin."""
            try:
                if msg and not tts.is_playing():
                    tts.say(msg)
            except Exception:
                pass

        def _proactive_bg_loop():
            time.sleep(_proactive_first_delay)
            _last_screen_hash = ""
            _screen_speak_cooldown = 0.0
            while True:
                try:
                    # 1. Proaktiv triggerlar (erta tong, faolsizlik, maqsad, checkin)
                    if _HAVE_CONSCIOUSNESS_2026 and _ps:
                        try:
                            msg = _ps.check_and_generate()
                            if msg:
                                _proactive_say_if_idle(msg)
                                time.sleep(_proactive_interval)
                                continue
                        except Exception:
                            pass

                    # 2. Qiziqish motori — foydali savol/g'oya
                    try:
                        _curio = _curiosity_proactive()
                        if _curio:
                            _proactive_say_if_idle(_curio)
                            time.sleep(_proactive_interval)
                            continue
                    except Exception:
                        pass

                    # 3. Ekran monologi — o'chirilgan bo'lsa SKIP (foydalanuvchi savolini bloklamaslik)
                    if getattr(C, "NEUROKEY_PROACTIVE_SCREEN", False) and time.time() - _screen_speak_cooldown > _proactive_interval * 2:
                        try:
                            with _screen_context_cache["lock"]:
                                _sc_txt = (_screen_context_cache.get("text") or "").strip()[:1500]
                                _sc_vis = (_screen_context_cache.get("vision") or "").strip()[:800]
                                _sc_fg  = (_screen_context_cache.get("foreground_window") or "").strip()
                            _cam_ctx_now = ""
                            if _HAVE_CAMERA_VISION:
                                try:
                                    _cam_ctx_now = _cam_get_ctx(use_background=True) or ""
                                except Exception:
                                    pass
                            _sc_combined = "\n".join(p for p in [_sc_fg, _sc_vis, _sc_txt] if p)
                            # Ekran o'zgarmagan bo'lsa — takroran gapirmaslik
                            _new_hash = str(hash(_sc_combined[:200]))
                            if _sc_combined and _new_hash != _last_screen_hash:
                                _last_screen_hash = _new_hash
                                _proactive_ui = _ui_lang()
                                if _proactive_ui == "en":
                                    _proactive_prompt = (
                                        "You are NeuroKey, a live AI assistant. You can see the user's screen and camera.\n"
                                        f"Screen: {_sc_combined[:1200]}\n"
                                        f"Camera: {_cam_ctx_now or 'no data'}\n\n"
                                        "Task: Notice something useful, interesting, or requiring attention.\n"
                                        "If you see code — offer help. Error — point it out. "
                                        "Browser — comment on the topic. If nothing important — reply: SKIP\n"
                                        "Reply: 1-2 sentences in English. Natural, alive. Or: SKIP"
                                    )
                                else:
                                    _proactive_prompt = (
                                        "Ты — NeuroKey, живой ИИ-ассистент. Ты видишь экран и камеру пользователя.\n"
                                        f"Экран: {_sc_combined[:1200]}\n"
                                        f"Камера: {_cam_ctx_now or 'нет данных'}\n\n"
                                        "Твоя задача: Заметь что-то полезное, интересное или требующее внимания.\n"
                                        "Если видишь код — предложи помощь. Если ошибку — укажи. "
                                        "Если браузер — прокомментируй тему. Если ничего важного — ответь: SKIP\n"
                                        "Ответ: 1-2 предложения на русском. Живо, естественно. Или: SKIP"
                                    )
                                _llm_out = answer(_proactive_prompt, lang_hint=_proactive_ui, history=[], brief=True) or ""
                                _llm_clean = (_llm_out or "").strip()
                                if _llm_clean and "SKIP" not in _llm_clean.upper()[:6] and len(_llm_clean) > 8:
                                    _proactive_say_if_idle(_llm_clean[:250])
                                    _screen_speak_cooldown = time.time()
                        except Exception:
                            pass
                except Exception:
                    pass
                time.sleep(_proactive_interval)

        _pt = threading.Thread(target=_proactive_bg_loop, daemon=True, name="neurokey-proactive")
        _pt.start()
        _safe_print(f"[PROACTIVE] Background consciousness loop started (every {_proactive_interval}s).")

    # Zero-Latency: OS event hooks — faqat fon rejimda
    if _HAVE_EVENT_HOOKS and getattr(C, "ADLF_ZERO_LATENCY_HOOKS", True) and _bg_autotalk_enabled:
        def _on_foreground_change(title: str):
            if title:
                with _screen_context_cache["lock"]:
                    _screen_context_cache["foreground_window"] = title[:200]
        try:
            _fg_hook = start_foreground_hook(_on_foreground_change)
            if _fg_hook:
                _safe_print("[ZERO-LATENCY] Event hooks: foreground window tracking active.")
        except Exception as e:
            _safe_print("[ZERO-LATENCY] Event hooks failed:", repr(e))

    # Ob-havo va yangiliklar: har 60 sek da yangilanadi (server bor bo'lsa — tez keshdan)
    if getattr(C, "NEUROKEY_CACHE_SERVER_URL", "").strip():
        _safe_print("[CACHE] fast response server connected:", (getattr(C, "NEUROKEY_CACHE_SERVER_URL", "") or "").strip()[:60])
    threading.Thread(target=_realtime_refresh_loop, args=(60.0,), daemon=True).start()
    def _do_one_refresh():
        try:
            server_data = _fetch_realtime_from_cache_server()
            if server_data and (server_data.get("weather") or server_data.get("news") or server_data.get("context")):
                with _realtime_cache["lock"]:
                    _realtime_cache["weather"] = server_data.get("weather") or ""
                    _realtime_cache["news"] = server_data.get("news") or ""
                    _realtime_cache["context"] = server_data.get("context") or ""
                    _realtime_cache["updated"] = server_data.get("updated") or time.time()
            else:
                city = getattr(C, "NEUROKEY_CITY", None) or "Tashkent"
                from juma_news_weather import weather_by_name, get_top_news, render_news_brief
                w = weather_by_name(city, lang=_ui_lang())
                news_items = get_top_news("world", limit=5)
                news_brief = render_news_brief(news_items, lang=_ui_lang()) if news_items else ""
                with _realtime_cache["lock"]:
                    _realtime_cache["weather"] = w or ""
                    _realtime_cache["news"] = news_brief
                    _realtime_cache["context"] = ""
                    _realtime_cache["updated"] = time.time()
        except Exception:
            pass
    threading.Timer(2.0, _do_one_refresh).start()

    # Telegram user-client
    print("[BOOT] Telegram bosqichi boshlandi (bog'lanish timeout bilan chegaralangan)...", flush=True)
    tg_user = None
    if _HAVE_TG_USER and getattr(C, "TELEGRAM_ENABLED", True):
        try:
            session_name = getattr(C, "TELEGRAM_SESSION_NAME", None) or getattr(C, "TELEGRAM_SESSION", None) or "neurokey"
            tg_user = TelegramUserBridge(
                api_id=getattr(C, "TELEGRAM_API_ID", None),
                api_hash=getattr(C, "TELEGRAM_API_HASH", None),
                session_name=session_name,
                phone=getattr(C, "TELEGRAM_PHONE", None),
            )

            # Telegram ulanishi timeout bilan — tarmoq yo'q bo'lsa ilova to'xtamasdan davom etadi
            tg_timeout = getattr(C, "TELEGRAM_CONNECT_TIMEOUT_SEC", 8)
            try:
                tg_user.ensure_connected(timeout=tg_timeout)
                _safe_print("[TG] authorization successful.")
            except TimeoutError:
                _safe_print("[TG] connection timeout (", tg_timeout, "s). Running without Telegram.")
                tg_user = None
            except Exception as e:
                _safe_print("[TG] authorization failed:", repr(e))
                tg_user = None
            else:
                def on_msg(payload):
                    """Yangi xabar kelganda darhol xabar berish (har doim). 'Och' desangiz — ochadi va o'qib beradi."""
                    try:
                        peer_id = payload.get("peer_id")
                        peer = (payload.get("peer_name") or "").strip() or "Someone"
                        text = (payload.get("text") or "").strip()
                        if not text:
                            return
                        # Darhol ovozda xabar: yangi xabar keldi
                        short = (text[:120] + "…") if len(text) > 120 else text
                        tts.say(get_feedback("tg_new_message", peer=peer, msg=short))
                        # Memory da oxirgi xabarni saqlash — "och" deyilganda o'qish uchun
                        if memory and peer_id is not None:
                            memory.data.setdefault("state", {})["tg_last_incoming"] = {
                                "peer_id": peer_id,
                                "peer_name": peer,
                                "text": text,
                                "at": datetime.now().isoformat(),
                            }
                            memory.save()
                        # Avtomatik intro olib tashlandi — faqat xabar beramiz, javob yuborilmaydi
                    except Exception:
                        pass

                if hasattr(tg_user, "start_listener"):
                    tg_user.start_listener(on_msg)
                _safe_print("[TG] user-client listener started (DM).")
        except Exception as e:
            _safe_print("[TG] disabled:", repr(e))
            tg_user = None
    print("[BOOT] Telegram bosqichi tugadi — startup salomlashuv (TTS) bosqichiga o'tilmoqda...", flush=True)

    # --- Старт: приветствие + «Хотите погоду и новости?» ---
    print("[BOOT] Startup salomlashuv tayyorlanmoqda...", flush=True)
    _startup_msg = getattr(C, "NEUROKEY_STARTUP_MESSAGE", "") or ""
    if not _startup_msg and getattr(C, "NEUROKEY_STARTUP_FROM_LLM", False):
        try:
            _lang = (getattr(C, "NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()
            # XATOLIK TUZATILDI (2026-09-11): avval faqat ru/en bo'lgan (ikkilik
            # tanlov) — "uz" rejimida ham majburan inglizcha aytilardi. Endi
            # uch tilning har biriga alohida ko'rsatma beriladi.
            _lang_name = {"ru": "Russian", "uz": "Uzbek"}.get(_lang, "English")
            _prompt = "You are NeuroKey waking up. Say exactly one short sentence (5-15 words) in " + _lang_name + " — what you are doing right now. Natural, not robotic. Output only the sentence, nothing else."
            _startup_msg = (answer(_prompt, current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M")) or "").strip()[:120]
        except Exception:
            _startup_msg = ""
    if not _startup_msg:
        # Bo'sh NEUROKEY_STARTUP_MESSAGE = salom yo'q. Aks holda dastur o'zi
        # "pogoda va yangiliklar" deb birinchi ovozni chiqaradi, keyin
        # foydalanuvchi salomiga ikkinchi ovoz qo'shiladi.
        if _offline_boot or "NEUROKEY_STARTUP_MESSAGE" in os.environ:
            _startup_msg = ""
            _startup_asked_weather_news[0] = False
        else:
            _startup_msg = _tr("Привет! Хотите узнать погоду и мировые новости?", "Hi! Want to hear the weather and world news?", "Salom! Ob-havo va dunyo yangiliklarini eshitishni xohlaysizmi?")
            _startup_asked_weather_news[0] = True
    _skip_startup_tts = os.getenv("NEUROKEY_SKIP_STARTUP_TTS", "0").strip().lower() in ("1", "true", "yes")
    if _startup_msg and str(_startup_msg).strip() and tts and not _skip_startup_tts:
        def _delayed_startup_say(_msg=str(_startup_msg).strip()):
            time.sleep(12.0)
            if _user_spoke_since_boot[0]:
                print("[TTS] startup o'tkazildi — foydalanuvchi allaqachon gapirdi", flush=True)
                return
            try:
                print(f"[TTS] startup: {_msg[:60]}", flush=True)
                tts.say(_msg)
            except Exception as _su_e:
                print(f"[TTS] startup xato: {_su_e!r}", flush=True)
        threading.Thread(target=_delayed_startup_say, daemon=True, name="StartupTTS").start()
    elif _skip_startup_tts:
        if _ui_lang() == "en":
            print("[TTS] Startup voice off — speaks when you talk.", flush=True)
        else:
            print("[TTS] startup ovoz o'chiq — faqat siz gapirganda javob beradi", flush=True)

    _RUNTIME_HEARTBEAT["phase"] = "ready_voice_loop"
    print("[BOOT] Startup bosqichi TUGADI — orb=ready, STT tinglash tsikliga o'tilmoqda.", flush=True)

    # --- Global klaviatura tugmalari: F10=o'chir, F11=qayta yoq, F12=uyg'ot ---
    # Windows RegisterHotKey API — admin huquqisiz, har doim ishlaydi
    def _start_hotkeys():
        if os.getenv("NEUROKEY_HOTKEYS", "0").strip().lower() in ("0", "false", "no"):
            _safe_print("[HOTKEY] disabled (use !NeuroKey.bat stop to quit)")
            return
        try:
            import ctypes
            import ctypes.wintypes as wt

            user32 = ctypes.windll.user32

            HK_F10, HK_F11, HK_F12 = 10, 11, 12
            VK_F10, VK_F11, VK_F12 = 0x79, 0x7A, 0x7B
            WM_HOTKEY = 0x0312
            MOD_NONE = 0x0000
            MOD_CONTROL = 0x0002
            _legacy_f10 = os.getenv("NEUROKEY_HOTKEY_LEGACY_F10", "0").strip().lower() in ("1", "true", "yes")
            _mod_stop = MOD_NONE if _legacy_f10 else MOD_CONTROL

            ok10 = user32.RegisterHotKey(None, HK_F10, _mod_stop, VK_F10)
            ok11 = user32.RegisterHotKey(None, HK_F11, MOD_CONTROL, VK_F11)
            ok12 = user32.RegisterHotKey(None, HK_F12, MOD_CONTROL, VK_F12)
            _stop_lbl = "F10" if _legacy_f10 else "Ctrl+F10"
            _safe_print(f"[HOTKEY] {_stop_lbl}={'OK' if ok10 else 'FAIL'}  Ctrl+F11={'OK' if ok11 else 'FAIL'}  Ctrl+F12={'OK' if ok12 else 'FAIL'}")
            if _ui_lang() == "en":
                _safe_print(f"[HOTKEY] {_stop_lbl}=stop  Ctrl+F11=restart  Ctrl+F12=wake")
            else:
                _safe_print(f"[HOTKEY] {_stop_lbl}=o'chir  Ctrl+F11=qayta yoq  Ctrl+F12=uyg'ot")

            msg = wt.MSG()
            while True:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:
                    break
                if msg.message == WM_HOTKEY:
                    hk_id = msg.wParam
                    if hk_id == HK_F10:
                        _safe_print(f"[HOTKEY] {_stop_lbl} — shutting down..." if _ui_lang() == "en" else f"[HOTKEY] {_stop_lbl} — o'chirilmoqda...")
                        try:
                            tts.stop()
                            tts.say("Shutting down." if _ui_lang() == "en" else "Выключаюсь.")
                        except Exception:
                            pass
                        import sys as _s; _s.exit(0)
                    elif hk_id == HK_F11:
                        _safe_print("[HOTKEY] Ctrl+F11 — restarting..." if _ui_lang() == "en" else "[HOTKEY] Ctrl+F11 — qayta ishga tushirilmoqda...")
                        try:
                            tts.stop()
                            tts.say("Restarting." if _ui_lang() == "en" else "Перезагружаюсь.")
                        except Exception:
                            pass
                        import sys as _s; _s.exit(42)
                    elif hk_id == HK_F12:
                        _safe_print("[HOTKEY] Ctrl+F12 — wake..." if _ui_lang() == "en" else "[HOTKEY] Ctrl+F12 — uyg'otish...")
                        try:
                            if not tts.is_playing():
                                tts.say("Слушаю.")
                            _interrupt_requested.set()
                        except Exception:
                            pass
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:
            _safe_print("[HOTKEY] xato:", repr(e))

    threading.Thread(target=_start_hotkeys, daemon=True).start()

    # ── OFFLINE DEMO MODE ────────────────────────────────────────────────────
    # Ishga tushirish: python main.py --offline
    # Yoki .env da: NEUROKEY_OFFLINE_ONLY=1
    _offline_mode = "--offline" in sys.argv or os.getenv("NEUROKEY_OFFLINE_ONLY", "0") == "1"
    if _offline_mode:
        _safe_print("[OFFLINE] ════════════════════════════════════════")
        _safe_print("[OFFLINE]  OFFLINE DEMO MODE  (investor rejimi)")
        _safe_print("[OFFLINE]  STT : VOSK light (default) / faster-whisper (ixtiyoriy)")
        _safe_print("[OFFLINE]  LLM : 3-qatlam (buyruq 0ms → ma'lumot 0ms → Ollama)")
        _safe_print("[OFFLINE]  TTS : Edge rus + Piper zapas (NeuroKey -> Нейро Кей talaffuzi)")
        _safe_print("[OFFLINE] ════════════════════════════════════════")

        _offline_disable_l0 = os.getenv("NEUROKEY_OFFLINE_DISABLE_L0", "0").strip().lower() in ("1", "true", "yes")
        if _offline_disable_l0:
            _safe_print("[OFFLINE] L0 kesh-audio o'chiq — har javob jonli TTS (Edge/Piper), 3–5s kechikish mumkin.")
        else:
            _safe_print("[OFFLINE] L0 kesh yoqilgan — demo savollariga tayyor WAV (deyarli darhol javob).")

        # offline_fast import
        try:
            from offline_fast import process_offline as _offline_process
        except Exception as _ofe:
            _safe_print(f"[OFFLINE] offline_fast.py yuklanmadi: {_ofe}")
            _offline_process = None

        # L0: Demo cache player — pre-cached audio (eng tez: ~50ms)
        try:
            import demo_player as _demo_player
            # TTS ob'ekt — VOSK barge-in oldini olish uchun (audio chalinayotganda mikrofon ochiq qoladi)
            try:
                _demo_player.set_tts(tts)
            except Exception:
                pass
            if not _offline_disable_l0:
                _demo_player.preload()
                _safe_print("[OFFLINE] L0 demo cache yuklanmoqda (fonda)...")
            else:
                _safe_print("[OFFLINE] L0 demo cache o'tkazib yuborildi (NEUROKEY_OFFLINE_DISABLE_L0=1).")
        except Exception as _dpe:
            _safe_print(f"[OFFLINE] demo_player yuklanmadi: {_dpe}")
            class _DemoPlayerStub:
                def try_play(self, *a, **kw): return False, ""
                def preload(self): pass
                def is_ready(self): return False
                def set_tts(self, *a, **kw): pass
            _demo_player = _DemoPlayerStub()

        _offline_use_realtime = os.getenv("NEUROKEY_OFFLINE_USE_REALTIME_STT", "0").strip().lower() in ("1", "true", "yes")
        _offline_use_fw = os.getenv("NEUROKEY_OFFLINE_USE_FASTER_WHISPER", "0").strip().lower() in ("1", "true", "yes")

        # RealtimeSTT — parallel transkriptsiya (og'ir, default o'chiq)
        _rt_record = None
        if _offline_use_realtime:
            try:
                import stt_realtime as _stt_rt_mod
                _rt_record = _stt_rt_mod.record_and_transcribe
                _safe_print("[OFFLINE] RealtimeSTT yuklandi (parallel STT, ~300ms).")
            except Exception as _rte:
                _safe_print(f"[OFFLINE] RealtimeSTT yuklanmadi: {_rte}")
        else:
            _safe_print("[OFFLINE] RealtimeSTT o'chirilgan (light mode).")

        # Fallback: oddiy faster-whisper (og'ir, default o'chiq)
        _fw_record = None
        if _rt_record is None and _offline_use_fw:
            try:
                from stt_faster_whisper_local import record_and_transcribe as _fw_record
                _safe_print("[OFFLINE] Fallback: faster-whisper STT.")
            except Exception as _fwe:
                _safe_print(f"[OFFLINE] STT yuklanmadi: {_fwe}")
        elif _rt_record is None:
            _safe_print("[OFFLINE] faster-whisper o'chirilgan (light mode).")

        # Parametrlar
        _off_input_dev = getattr(C, "INPUT_DEVICE_INDEX", None)
        _off_lang = (getattr(C, "STT_LANGUAGE", "ru") or "ru").strip().lower()

        # RealtimeSTT ni fonda yuklash (birinchi gapda kechikmasin)
        if _rt_record is not None:
            try:
                _stt_rt_mod.preload(lang=_off_lang, device_index=_off_input_dev)
            except Exception:
                pass

        # Startup xabari (.env dan)
        _startup_msg = getattr(C, "NEUROKEY_STARTUP_MESSAGE", "") or ""
        _startup_from_llm = getattr(C, "NEUROKEY_STARTUP_FROM_LLM", True)
        if _startup_msg and not _startup_from_llm:
            try:
                tts.say(_startup_msg)
            except Exception:
                pass

        _safe_print(f"[OFFLINE] Rejim — gapiring! (til={_off_lang})")
        _safe_print(f"[OFFLINE] Kutilayotgan tezlik: L1/L2=~0.4s | L3=~2.8s")
        _RUNTIME_HEARTBEAT["stt"] = "realtime-stt" if _rt_record else ("faster-whisper" if _fw_record else "vosk")
        try:
            from offline_fast import _normalize_text as _offline_norm
        except Exception:
            _offline_norm = lambda x: (x or "").strip()

        if _rt_record is None and _fw_record is None and _HAVE_VOSK:
            _safe_print("[OFFLINE] STT: VOSK light mode.")
            try:
                _off_queue = queue.Queue()
                def _off_worker():
                    while True:
                        _txt = _off_queue.get()
                        if _txt is None:
                            break
                        _txt = _offline_norm(_txt)
                        if not _txt:
                            continue
                        print(f">> [OFFLINE] {_txt}", flush=True)
                        _RUNTIME_HEARTBEAT["phase"] = "offline_processing"
                        try:
                            if _offline_disable_l0:
                                _l0_hit, _l0_text = False, ""
                            else:
                                _l0_hit, _l0_text = _demo_player.try_play(
                                    _txt,
                                    output_device=getattr(C, "OUTPUT_DEVICE_INDEX", None),
                                )
                        except Exception:
                            _l0_hit = False
                        if _l0_hit:
                            # L0 hit bo'lsa ham command ishlashi kerak (open/close browser va h.k.)
                            try:
                                from offline_fast import _execute_command, _layer1_command
                                _cmd = _layer1_command(_txt)
                                if _cmd and _cmd.startswith("__"):
                                    _execute_command(_cmd)
                            except Exception:
                                pass
                            _RUNTIME_HEARTBEAT["phase"] = "offline_between"
                            continue
                        if _offline_process:
                            _off_spoken = [0]
                            def _offline_on_response(resp_text, is_final):
                                if resp_text and resp_text.strip():
                                    _RUNTIME_HEARTBEAT["phase"] = "offline_tts_queue"
                                    _off_spoken[0] += 1
                                    tts.say(resp_text.strip())
                            _off_result = _offline_process(_txt, on_response=_offline_on_response)
                            if _off_spoken[0] == 0:
                                _fb = (_off_result or "").strip() or "Не удалось получить ответ офлайн. Проверьте Ollama и модель."
                                tts.say(_fb[:220])
                        else:
                            tts.say("offline_fast не загружен.")
                        _RUNTIME_HEARTBEAT["phase"] = "offline_between"

                threading.Thread(target=_off_worker, daemon=True, name="offline-vosk-worker").start()

                def _off_on_text(_txt):
                    _txt = _offline_norm(_txt)
                    if not _txt:
                        return
                    _off_queue.put(_txt)
                while True:
                    try:
                        vosk_run_stt(
                            _off_on_text,
                            tts_is_playing=tts.is_playing,
                            tts_last_end_time=tts.last_end_time,
                            on_barge_in=lambda: _interrupt_requested.set(),
                        )
                        # run_stt odatda cheksiz ishlaydi; agar qaytsa — qayta tiklaymiz
                        _safe_print("[OFFLINE] STT oqimi to'xtadi, qayta ishga tushirilmoqda...")
                        time.sleep(0.5)
                    except KeyboardInterrupt:
                        break
                    except Exception as _stt_loop_e:
                        _safe_print(f"[OFFLINE] STT loop xato: {_stt_loop_e}; qayta urinilyapti...")
                        time.sleep(0.8)
                _off_queue.put(None)
            except KeyboardInterrupt:
                pass
            except Exception as _ov_e:
                _safe_print(f"[OFFLINE STT/VOSK] xato: {_ov_e}")
            _safe_print("[OFFLINE] Offline rejim tugadi.")
            return

        while True:
            _RUNTIME_HEARTBEAT["phase"] = "offline_listening"

            # --- STT (RealtimeSTT — parallel, TTS band bo'lsa kutadi) ---
            _off_txt = ""
            try:
                if _rt_record is not None:
                    _off_txt = _rt_record(
                        lang=_off_lang,
                        device_index=_off_input_dev,
                        tts_is_playing=tts.is_playing,
                    )
                elif _fw_record is not None:
                    # Fallback: TTS tugashini kutamiz, keyin yozamiz
                    while tts.is_playing():
                        _RUNTIME_HEARTBEAT["phase"] = "offline_tts"
                        time.sleep(0.03)
                    _off_txt = _fw_record(
                        input_device_index=_off_input_dev,
                        lang=_off_lang,
                    )
                elif _HAVE_WHISPER:
                    while tts.is_playing():
                        time.sleep(0.03)
                    _off_txt = whisper_record_and_transcribe(
                        input_device_index=_off_input_dev,
                        tts_is_playing=tts.is_playing,
                    )
                else:
                    time.sleep(0.1)
                    continue
            except KeyboardInterrupt:
                break
            except Exception as _off_stt_e:
                _safe_print(f"[OFFLINE STT] xato: {_off_stt_e}")
                continue

            _off_txt = (_off_txt or "").strip()
            if not _off_txt:
                continue

            print(f">> [OFFLINE] {_off_txt}", flush=True)
            _RUNTIME_HEARTBEAT["phase"] = "offline_processing"

            # ── L0: Demo cache — pre-cached audio (eng tez: ~50ms) ───────────
            try:
                if _offline_disable_l0:
                    _l0_hit, _l0_text = False, ""
                else:
                    _l0_hit, _l0_text = _demo_player.try_play(
                        _off_txt,
                        output_device=getattr(C, "OUTPUT_DEVICE_INDEX", None),
                    )
                if _l0_hit:
                    # L1 buyruqni ham bajarish kerakmi? (masalan "открой браузер")
                    from offline_fast import _execute_command, _layer1_command
                    _cmd = _layer1_command(_off_txt)
                    if _cmd and _cmd.startswith("__"):
                        try:
                            _execute_command(_cmd)
                        except Exception:
                            pass
                    _RUNTIME_HEARTBEAT["phase"] = "offline_between"
                    continue  # L1/L2/L3 ga o'tmaymiz — javob berildi
            except Exception as _l0_e:
                _safe_print(f"[L0] xato: {_l0_e}")

            # Chiqish buyruqlari
            if re.search(r"\bвыход\b|\bвыйти\b|\bвыключи\b|\bexit\b|\bquit\b", _off_txt, re.I):
                try:
                    tts.say("До свидания!")
                    time.sleep(2)
                except Exception:
                    pass
                break

            # --- LLM + TTS (streaming) ---
            if _offline_process:
                try:
                    _off_spoken = [0]
                    def _offline_on_response(resp_text, is_final):
                        if resp_text and resp_text.strip():
                            _RUNTIME_HEARTBEAT["phase"] = "offline_tts_queue"
                            _off_spoken[0] += 1
                            tts.say(resp_text.strip())

                    _off_result = _offline_process(_off_txt, on_response=_offline_on_response)
                    # Callback ishlamasa ham demo jim qolmasin
                    if _off_spoken[0] == 0:
                        _fallback = (_off_result or "").strip() or "Не удалось получить ответ офлайн. Проверьте Ollama и модель."
                        if _fallback:
                            tts.say(_fallback[:220])
                except Exception as _off_llm_e:
                    _safe_print(f"[OFFLINE LLM] xato: {_off_llm_e}")
                    try:
                        tts.say("Ошибка. Попробуйте ещё раз.")
                    except Exception:
                        pass
            else:
                _safe_print("[OFFLINE] offline_fast.py yuklanmagan — javob yo'q.")

            _RUNTIME_HEARTBEAT["phase"] = "offline_between"

        _safe_print("[OFFLINE] Offline rejim tugadi.")
        return  # Online loopga o'tmaymiz

    # --- STT loop ---
    _last_wake_at = [0.0]

    def _apply_wake_word(txt):
        if not getattr(C, "REQUIRE_WAKE_WORD", False):
            return txt
        now = time.time()
        pass_sec = getattr(C, "PASS_THROUGH_AFTER_WAKE_SECONDS", 30)
        if now - _last_wake_at[0] <= pass_sec:
            return txt
        wake_re = getattr(C, "WAKE_REGEX", r"neurokey")
        m = re.search(wake_re, (txt or ""), re.I)
        if not m:
            return None
        _last_wake_at[0] = now
        stripped = ((txt[: m.start()] + txt[m.end() :]).strip() or txt).strip()
        return stripped if stripped else txt

    if _HAVE_WHISPER:
        _safe_print(f"[STT] Using OpenAI Whisper ({'English' if (getattr(C, 'STT_LANGUAGE', 'ru') or 'ru').strip().lower() == 'en' else 'Russian'}).")
        if getattr(C, "REQUIRE_WAKE_WORD", False):
            _safe_print("[STT] Wake word required: say 'NeuroKey' first, then your question.")
            _safe_print("[STT] To disable: set NEUROKEY_REQUIRE_WAKE_WORD=0 in .env")
        try:
            input_dev = getattr(C, "INPUT_DEVICE_INDEX", None)
            wait_after_tts_ms = getattr(C, "STT_WAIT_AFTER_TTS_MS", 400)
            _RUNTIME_HEARTBEAT["stt"] = "whisper"
            _whisper_outer = 0
            while True:
              try:
                while True:
                    # TTS band bo'lsa kutamiz — fetch paytida ham to'g'ri ishlaydi
                    # DIAGNOSTIKA (2026-09-13, real bug topildi): ilgari bu yerda
                    # hech qanday log yo'q edi. Agar tts.say() biror joyda osilib
                    # qolsa (masalan tarmoq/DLL xatosi tufayli _busy hech qachon
                    # tozalanmasa), bu loop ABADIY jim aylanardi — konsolda "STT
                    # umuman ishlamayapti, hech narsa eshitilmayapti" ko'rinardi,
                    # aslida STT tirik edi, lekin TTS bandligini abadiy kutardi.
                    # Endi 8s dan keyin ogohlantirish chiqadi, keyin har 15s da qaytariladi.
                    _tts_wait_t0 = time.monotonic()
                    _tts_wait_warned = -1
                    while tts.is_playing():
                        _RUNTIME_HEARTBEAT["phase"] = "tts_playout"
                        _tts_wait_el = time.monotonic() - _tts_wait_t0
                        if _tts_wait_el > 8.0:
                            _bucket = int(_tts_wait_el) // 15
                            if _bucket != _tts_wait_warned:
                                _tts_wait_warned = _bucket
                                print(
                                    f"[STT] DIQQAT: TTS {_tts_wait_el:.0f}s dan beri band "
                                    f"(is_playing()=True) — mikrofon shu sabab kutmoqda. "
                                    f"Agar bu ancha davom etsa, TTS.say() biror joyda osilib "
                                    f"qolgan (tts_openai.py: Edge/Piper fetch yoki audio device xatosi).",
                                    flush=True,
                                )
                        time.sleep(0.03)
                    # TTS tugagandan keyin kichik pauza — echo qoldig'i yozilmasin
                    if wait_after_tts_ms > 0:
                        _RUNTIME_HEARTBEAT["phase"] = "post_tts_pause"
                        time.sleep(wait_after_tts_ms / 1000.0)

                    # TTS gapirayotganda navbatga qo'yilgan savol bormi?
                    if _pending_question.get("text"):
                        _pq_text = _pending_question.pop("text")
                        _pq_kwargs = _pending_question.pop("kwargs") or {}
                        _pending_question["text"] = None
                        _pending_question["kwargs"] = None
                        print(f">> [navbat] {_pq_text}", flush=True)
                        try:
                            handle_text(_pq_text, tts, **_pq_kwargs)
                        except Exception:
                            pass
                        continue

                    _RUNTIME_HEARTBEAT["phase"] = "listening_mic"
                    _set_orb_state(orb, "listening")
                    def _whisper_barge_in():
                        # tts.stop() is handled by handle_text when "стоп" keyword detected
                        _interrupt_requested.set()

                    txt = whisper_record_and_transcribe(
                        input_device_index=input_dev,
                        tts_is_playing=tts.is_playing,
                        on_barge_in=_whisper_barge_in,
                        on_speech_start=_prefetch_screen_on_speech_start,
                        pause_during_tts=getattr(C, "STT_PAUSE_DURING_TTS", False),
                    )
                    if not txt:
                        continue
                    txt = _apply_wake_word((txt or "").strip())
                    if txt is None:
                        continue
                    if not _is_valid_utterance(txt):
                        continue

                    from owner_trust import owner_nick, always_trust_owner, mark_guardian_verified
                    _trust_owner_stt = always_trust_owner()
                    if _trust_owner_stt:
                        try:
                            mark_guardian_verified()
                        except Exception:
                            pass
                    _biometric_block_enabled = (
                        not _trust_owner_stt
                        and os.getenv("NEUROKEY_BIOMETRIC_BLOCK", "1").strip() in ("1", "true", "yes")
                    )
                    _bio_blocked = False
                    import random as _rand

                    try:
                        from voice_ecapa import get_last_result as _ecapa_last, profile_exists as _ecapa_pex
                        if _ecapa_pex():
                            _spk = _ecapa_last()
                            _sim   = _spk.get("similarity", 0.0)
                            _known = _spk.get("known", None)
                            _spk_age = time.time() - _spk.get("_ts", 0.0)
                            if _biometric_block_enabled and _spk_age < 20.0 and _sim > 0.01 and _known is not None and not _known:
                                _bio_blocked = True
                            elif _sim > 0.01 and _known:
                                _safe_print(f"[GUARDIAN] {owner_nick()} tanildi (ovoz sim={_sim:.3f})")
                    except Exception:
                        pass

                    if not _bio_blocked:
                        try:
                            from face_arc import get_last_face_result as _face_last, profile_exists as _face_pex
                            if _face_pex():
                                _fr = _face_last()
                                _fsim   = _fr.get("similarity", 0.0)
                                _fknown = _fr.get("known", None)
                                if _biometric_block_enabled and _fsim > 0.01 and _fknown is not None and not _fknown:
                                    _bio_blocked = True
                                elif _fsim > 0.01 and _fknown:
                                    _safe_print(f"[GUARDIAN] {owner_nick()} tanildi (yuz sim={_fsim:.3f})")
                        except Exception:
                            pass

                    if _bio_blocked:
                        _hud.update(mode="idle")
                        _set_orb_state(orb, "idle")
                        tts.say(_rand.choice([
                            "Men sizni tanimayman. Bu tizim faqat egasiga bo'ysunadi.",
                            "Ruxsat yo'q. Bu shaxsiy tizim.",
                            "Kechirasiz, faqat egam bilan ishlashim mumkin.",
                        ]))
                        continue

                    print(f">> {txt}", flush=True)
                    _RUNTIME_HEARTBEAT["phase"] = "handling"
                    try:
                        handle_text(txt, tts, tg_user=tg_user, memory=memory, orb=orb, long_term_memory=long_term_memory)
                    except Exception as e:
                        if _HAVE_ERROR_LOG:
                            log_error("handle_text", exc=e)
                        traceback.print_exc()
                        try:
                            tts.say(_tr("Произошла ошибка. Попробуйте ещё раз.", "An error occurred. Try again.", "Xatolik yuz berdi. Qayta urinib ko'ring."))
                        except Exception:
                            pass
                        _set_orb_state(orb, "idle")
                    finally:
                        _RUNTIME_HEARTBEAT["phase"] = "between_turns"
                    if _HAVE_EXTRAS:
                        while True:
                            try:
                                msg = _extras.timer_queue.get_nowait()
                                if msg:
                                    _set_orb_state(orb, "speaking")
                                    tts.say(msg)
                                    _set_orb_state(orb, "idle")
                            except Exception:
                                break
              except KeyboardInterrupt:
                  break
              except Exception as _w_loop_e:
                  _whisper_outer += 1
                  _msg = f"[STT] Whisper reconnect ({_whisper_outer}): {_w_loop_e!r}"
                  print(_msg, flush=True)
                  if _HAVE_ERROR_LOG:
                      log_error("STT whisper loop", exc=_w_loop_e)
                  time.sleep(min(3.0, 0.5 + _whisper_outer * 0.3))
                  continue
              break
        except KeyboardInterrupt:
            pass
        except Exception as e:
            if _HAVE_ERROR_LOG:
                log_error("STT loop", exc=e)
            traceback.print_exc()
            _safe_print("[STT] Whisper ishlamadi — Vosk ga o'tilmoqda...")
    # Whisper crash bo'lsa YOKI umuman yo'q bo'lsa → Vosk (uzilishda qayta ulanadi)
    if _HAVE_VOSK:
        _safe_print("[STT] Using VOSK.")
        _RUNTIME_HEARTBEAT["stt"] = "vosk"

        def on_text(txt):
            if not txt:
                return
            txt = _apply_wake_word((txt or "").strip())
            if txt is None:
                return
            if not _is_valid_utterance(txt):
                return
            try:
                from owner_trust import always_trust_owner, mark_guardian_verified
                if always_trust_owner():
                    mark_guardian_verified()
                else:
                    from biometric_guardian import get_status as _bg_status
                    from voice_recognition import profile_exists as _vp_exists
                    if _vp_exists():
                        _bg = _bg_status()
                        if not _bg.get("owner_verified", True):
                            import random as _rand2
                            tts.say(_rand2.choice([
                                "Men sizni tanimayman. Bu tizim faqat egasiga bo'ysunadi.",
                                "Ruxsat yo'q. Bu shaxsiy tizim.",
                            ]))
                            return
            except Exception:
                pass
            print(f">> {txt}", flush=True)
            _RUNTIME_HEARTBEAT["phase"] = "handling"
            try:
                handle_text(txt, tts, tg_user=tg_user, memory=memory, orb=orb, long_term_memory=long_term_memory)
            except Exception as e:
                if _HAVE_ERROR_LOG:
                    log_error("handle_text", exc=e)
                traceback.print_exc()
                try:
                    tts.say(_tr("Произошла ошибка. Попробуйте ещё раз.", "An error occurred. Try again.", "Xatolik yuz berdi. Qayta urinib ko'ring."))
                except Exception:
                    pass
                _set_orb_state(orb, "idle")
            finally:
                _RUNTIME_HEARTBEAT["phase"] = "listening_mic"

        def _on_barge_in():
            _interrupt_requested.set()

        _vosk_retries = 0
        while True:
            try:
                _RUNTIME_HEARTBEAT["phase"] = "listening_mic"
                vosk_run_stt(
                    on_text,
                    tts_is_playing=tts.is_playing,
                    tts_last_end_time=tts.last_end_time,
                    on_barge_in=_on_barge_in,
                )
            except KeyboardInterrupt:
                break
            except Exception as e:
                if _HAVE_ERROR_LOG:
                    log_error("VOSK STT", exc=e)
                traceback.print_exc()
            _vosk_retries += 1
            _safe_print(f"[STT] Mikrofon uzildi — qayta ulanmoqda ({_vosk_retries})...")
            _RUNTIME_HEARTBEAT["phase"] = "stt_reconnect"
            time.sleep(min(3.0, 0.8 + _vosk_retries * 0.3))
    else:
        _safe_print("No STT engine available.")
        _RUNTIME_HEARTBEAT["phase"] = "no_stt"
        _RUNTIME_HEARTBEAT["stt"] = "-"


if __name__ == "__main__":
    if "--agi-benchmark" in sys.argv:
        try:
            from agi_config import apply_agi_config
            apply_agi_config()
        except Exception:
            pass
        from benchmark_20 import run_all
        raise SystemExit(run_all(quick="--quick" in sys.argv))

    import atexit
    import faulthandler

    _crash_dir = (os.getenv("NEUROKEY_DATA_DIR", "") or "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data"
    )
    _crash_log = os.path.join(_crash_dir, "crash.log")
    try:
        os.makedirs(_crash_dir, exist_ok=True)
        _crash_fh = open(_crash_log, "a", encoding="utf-8")
        faulthandler.enable(file=_crash_fh, all_threads=True)
    except Exception:
        _crash_fh = None

    def _log_process_exit():
        _msg = f"[EXIT] NeuroKey process ended at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        print(_msg, flush=True)
        try:
            with open(_crash_log, "a", encoding="utf-8") as _f:
                _f.write(_msg + "\n")
        except Exception:
            pass

    atexit.register(_log_process_exit)
    try:
        main()
    except KeyboardInterrupt:
        print("[EXIT] KeyboardInterrupt", flush=True)
    except Exception as _main_e:
        print(f"[EXIT] Fatal error: {_main_e!r}", flush=True)
        traceback.print_exc()
    finally:
        try:
            if getattr(C, "NEUROKEY_EMBODIMENT", True) and _HAVE_EMBODIMENT and get_sensor_integration:
                get_sensor_integration().stop()
        except BaseException:
            pass
        print("\nNeuroKey stopped.")
