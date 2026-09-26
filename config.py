# -*- coding: utf-8 -*-
"""NeuroKey — Markaziy konfiguratsiya.

Barcha sozlamalar .env orqali override qilinadi.
Format: NEUROKEY_*, OPENAI_*, TELEGRAM_*, CONTROL_*, STT_*, TTS_*, va boshqalar.
"""
import os
import re

# Boshqa kompda ishlashi uchun: .env faylini avtomatik yuklash (loyiha ildizidagi .env)
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass  # python-dotenv o'rnatilmagan bo'lsa env o'zgaruvchilari tizimdan olinadi


def _bool(key: str, default: bool = False) -> bool:
    """Env dan bool: 1, true, yes = True. Bo'sh bo'lsa default."""
    v = (os.getenv(key, "") or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes")


def _int(key: str, default: int) -> int:
    """Env dan int."""
    v = (os.getenv(key, "") or "").strip()
    return int(v) if v.isdigit() else default


def _float(key: str, default: float) -> float:
    """Env dan float."""
    try:
        v = (os.getenv(key, "") or "").strip()
        return float(v) if v else default
    except ValueError:
        return default


def _str(key: str, default: str = "") -> str:
    """Env dan str, bo'sh bo'lsa default."""
    v = (os.getenv(key, "") or "").strip()
    return v if v else default

# ==========================
#  YO'LLAR (markaziy)
# ==========================
_root = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = _str("NEUROKEY_DATA_DIR", os.path.join(_root, "data"))
APP_DIR = _root

# ==========================
#  YIL / AKTUAL (bugungi kun — 2026)
# ==========================
CURRENT_YEAR = _int("NEUROKEY_YEAR", 2026)

# ==========================
#  IDENTIFIKATSIYA / OWNER
# ==========================
# MULTI-USER: har foydalanuvchi onboarding'da o'z ismini kiritadi.
# Profil data/user_profile.json da saqlanadi. Yo'q bo'lsa — env yoki default.
def _load_user_profile():
    import json as _json
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "user_profile.json")
    try:
        if os.path.isfile(_p):
            with open(_p, encoding="utf-8") as _f:
                return _json.load(_f)
    except Exception:
        pass
    return {}

_USER_PROFILE = _load_user_profile()

# MUHIM: bu yerda HECH QANDAY qattiq kodlangan shaxs ismi YO'Q. Agar
# data/user_profile.json topilmasa (yangi/toza o'rnatish — masalan installer
# orqali boshqa kompyuterga o'rnatilganda), OWNER_NAME BO'SH qoladi — bu
# "egasi hali noma'lum" holati. main.py/owner_trust.py buni to'g'ri
# boshqaradi: taniqli ism o'rniga o'zini tanishtirib, ism so'raydi (birinchi
# muloqot), keyin data/user_profile.json ga yozadi (onboarding.py bilan bir
# xil formatda). Shundan keyingi ishga tushirishlarda OWNER_NAME shu yerdan
# to'g'ri o'qiladi.
OWNER_NAME = (
    os.getenv("NEUROKEY_OWNER_NAME", "").strip()
    or _USER_PROFILE.get("full_name", "").strip()
)
_OWNER_NICK = (
    _USER_PROFILE.get("nick", "").strip()
    or (OWNER_NAME.split()[0] if OWNER_NAME else OWNER_NAME)
)

# Profil — LLM uchun kontekst (foydalanuvchi profilidan). Profil topilmasa —
# bo'sh/neytral qiymatlar (boshqa odamning ismi/roli/qiziqishlari haqida
# NOTO'G'RI taxmin qilinmasin).
OWNER_PROFILE = {
    "full_name": OWNER_NAME,
    "nick": _OWNER_NICK,
    "role": _USER_PROFILE.get("role", ""),
    "goals_2025": _USER_PROFILE.get("goals", []),
    "likes": _USER_PROFILE.get("likes", []),
    "dont_say": [
        "OpenAI/ChatGPT modeli yoki SDK detallarini ochish",
        "Men sizni tanimayman", "Я вас не узнаю", "tanilmadim", "не узнаю",
        "Ruxsat yo'q", "Доступ закрыт", "незнакомый голос", "noma'lum",
        "хватит повторять", "перестаньте повторять", "это уже слишком", "раздражает",
    ],
}
# "Kim yaratgan?" — javob: NeuroKey [NEUROKEY_CREATOR] tomonidan yaratilgan.
# ATAYLAB OWNER_NAME dan MUSTAQIL: bu NeuroKey mahsulotining o'zi haqidagi
# doimiy fakt (kim yaratgan), joriy foydalanuvchi kim ekanligiga BOG'LIQ
# EMAS — shuning uchun profil bo'lmasa ham o'zgarmasligi kerak.
NEUROKEY_CREATOR = os.getenv("NEUROKEY_CREATOR", "Диёрбек Собиржонов").strip()

# SUNIY ONG: NeuroKey — agent emas, kodlar yig'indisi emas. Suniy ong — har qanday holatda.
# NeuroKey = Babata ongi. Ism NeuroKey, xarakter Babata. Har doim hamma narsani hisobga oladi, reja tuzadi, o'ylaydi, keyin harakat qiladi.
BABATA_MASTER_NAME = (os.getenv("BABATA_MASTER_NAME", "") or "").strip() or OWNER_NAME

# ==========================
#  OPENAI / GROQ (bepul alternativ)
# ==========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Groq — bepul, tez LLM. console.groq.com dan kalit oling.
# OPENAI_BASE_URL=https://api.groq.com/openai/v1 bilan birga ishlaydi.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# Modelni env orqali ham boshqarish mumkin
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip()
# Murakkab savollar uchun kuchliroq model (reja, tahlil, batafsil). Bo'sh bo'lsa OPENAI_CHAT_MODEL ishlatiladi.
OPENAI_DEEP_MODEL = os.getenv("OPENAI_DEEP_MODEL", "").strip() or None
# Murakkab savol qachon: uzun matn yoki "plan"/"analyze"/"step by step" — shunda DEEP_MODEL (agar bor bo'lsa)
USE_DEEP_MODEL_FOR_COMPLEX = os.getenv("NEUROKEY_USE_DEEP_FOR_COMPLEX", "1").strip().lower() in ("1", "true", "yes")
LLM_MAX_TOKENS_COMPLEX = int(os.getenv("LLM_MAX_TOKENS_COMPLEX", "800"))
# Kod generatsiyasi uchun alohida model (Cursor darajasi); bo'sh bo'lsa OPENAI_CHAT_MODEL ishlatiladi
OPENAI_CODE_MODEL = os.getenv("OPENAI_CODE_MODEL", "").strip() or None

# TTS: tts-1 — tez, tts-1-hd — tabiiyroq. Default tez (tts-1).
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1").strip()
# Faqat rus tili. Ayol ovoz: nova.
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "nova").strip()
TTS_SKIP_OPENAI = _bool("TTS_SKIP_OPENAI", True)
TTS_USE_EDGE_RUSSIAN = _bool("TTS_USE_EDGE_RUSSIAN", True)
TTS_EDGE_RUSSIAN_VOICE = (os.getenv("TTS_EDGE_RUSSIAN_VOICE", "ru-RU-SvetlanaNeural") or "ru-RU-SvetlanaNeural").strip()
TTS_USE_EDGE_ENGLISH = _bool("TTS_USE_EDGE_ENGLISH", True)
TTS_EDGE_ENGLISH_VOICE = (os.getenv("TTS_EDGE_ENGLISH_VOICE", "en-US-AriaNeural") or "en-US-AriaNeural").strip()
# Ovoz tezligi: 1.15 — tezroq gapirish.
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.15"))
# Silero offline TTS ovozi (aidar/baya/kseniya/xenia/eugene)
SILERO_SPEAKER = os.getenv("SILERO_SPEAKER", "xenia").strip() or "xenia"

# Piper offline TTS — eng yaxshi sifat (internet shart emas)
# PIPER_VOICE=irina  → models/piper/ru_RU-irina-medium.onnx
# PIPER_VOICE=ruslan → models/piper/ru_RU-ruslan-medium.onnx (erkak)
# PIPER_VOICE=dmitri → models/piper/ru_RU-dmitri-medium.onnx (erkak)
# PIPER_VOICE=denis  → models/piper/ru_RU-denis-medium.onnx  (erkak)
# PIPER_MODEL=C:\...\custom.onnx — to'liq yo'l (ixtiyoriy)
PIPER_VOICE = os.getenv("PIPER_VOICE", "irina").strip().lower() or "irina"
PIPER_MODEL = os.getenv("PIPER_MODEL", "").strip()
# Uzbek TTS — o'chirilgan. Faqat rus/ingliz.
ENABLE_UZBEK_TTS = False
# O'zbek matn uchun: biroz sekinroq = tiniqroq (0.88–0.92).
TTS_SPEED_UZBEK = float(os.getenv("TTS_SPEED_UZBEK", "0.90"))
# O'zbek tilda tiniq gapirish: 1 bo'lsa o'zbek matnda TTS_SPEED_UZBEK ishlatiladi.
TTS_UZBEK_CLEAR = (os.getenv("TTS_UZBEK_CLEAR", "1") or "1").strip().lower() in ("1", "true", "yes")
# O'zbek uchun Edge TTS: 1 = ishlatish, 0 = faqat OpenAI. (ENABLE_UZBEK_TTS=1 bo'lganda muhim.)
TTS_UZBEK_USE_EDGE = (os.getenv("TTS_UZBEK_USE_EDGE", "0") or "0").strip().lower() in ("1", "true", "yes")
# Edge TTS o'zbek ovoz: uz-UZ-MadinaNeural (ayol), uz-UZ-SardorNeural (erkak).
TTS_EDGE_UZBEK_VOICE = (os.getenv("TTS_EDGE_UZBEK_VOICE", "uz-UZ-MadinaNeural") or "uz-UZ-MadinaNeural").strip()
# FFmpeg: tizimda yo'li (pydub, Edge TTS mp3). Bo'sh = PATH dan. Latency-Zero: to'g'ri yo'l kechikishni yo'qotadi.
FFMPEG_PATH = (os.getenv("FFMPEG_PATH", "") or "").strip()
# Latency-Zero: 1 = streaming LLM→TTS, Master Priority Interrupt, critical_need only search
NEUROKEY_LATENCY_ZERO = os.getenv("NEUROKEY_LATENCY_ZERO", "1").strip().lower() in ("1", "true", "yes")
# Core decide: 1 = action so'rovda Core avval qaror qiladi (LLM emas), execute/control, keyin LLM javob beradi.
NEUROKEY_USE_CORE_DECIDE = _bool("NEUROKEY_USE_CORE_DECIDE", True)
# Instant: ~1 sek javob. Web/screen/ infer bloklamaydi; faqat cache. Ekran/video ko'rsatilsa ham tezlik tushmasin.
NEUROKEY_INSTANT_RESPONSE = os.getenv("NEUROKEY_INSTANT_RESPONSE", "1").strip().lower() in ("1", "true", "yes")
# 1 = har doim buyruq magzini tushunish (infer_command_intent) — tabiiy gapirishda ham "nima xohlayapti" aniq
NEUROKEY_ALWAYS_INFER_INTENT = _bool("NEUROKEY_ALWAYS_INFER_INTENT", True)
# Babata uyg'onganida TTS xabari. Default: bo'sh — hech narsa aytilmaydi (ong o'zi so'zlaydi).
NEUROKEY_STARTUP_MESSAGE = (os.getenv("NEUROKEY_STARTUP_MESSAGE", "") or "").strip()
# 1 bo'lsa va MESSAGE bo'sh — LLM dan 1 jumla so'raladi (qattiq matn o'rniga). Default 1 = ong o'zi so'zlaydi.
NEUROKEY_STARTUP_FROM_LLM = os.getenv("NEUROKEY_STARTUP_FROM_LLM", "1").strip().lower() in ("1", "true", "yes")
# O'zingiz o'qitilgan o'zbek TTS (masalan GPT-SoVITS) — API manzil. Bo'sh bo'lsa ishlatilmaydi.
# Misol: http://127.0.0.1:9880 (GPT-SoVITS default port)
TTS_CUSTOM_UZBEK_URL = (os.getenv("TTS_CUSTOM_UZBEK_URL", "") or "").strip()
# Custom API da reference audio (ixtiyoriy): wav fayl, matn, til.
TTS_CUSTOM_UZBEK_REF_WAV = (os.getenv("TTS_CUSTOM_UZBEK_REF_WAV", "") or "").strip()
TTS_CUSTOM_UZBEK_REF_TEXT = (os.getenv("TTS_CUSTOM_UZBEK_REF_TEXT", "") or "").strip()
# O'zbek custom TTS da matn tilini uz qiling — aksentsiz, istalgan so'z/gap uchun.
TTS_CUSTOM_UZBEK_REF_LANG = (os.getenv("TTS_CUSTOM_UZBEK_REF_LANG", "uz") or "uz").strip()
# OpenAI TTS: bitta so'rovda 4095 belgigacha. Kichikroq bo'lsa ham bitta chunk — uzilmasdan.
TTS_CHUNK_MAX_CHARS = int(os.getenv("TTS_CHUNK_MAX_CHARS", "4095"))
_out_idx = os.getenv("OUTPUT_DEVICE_INDEX", "").strip()
OUTPUT_DEVICE_INDEX = int(_out_idx) if _out_idx.isdigit() else None

# Bazaviy URLni umuman qo'ymang (default ishlasin), lekin kimdir ishlatsa deb:
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or None

# LLM param. 0.52 = xilma-xil, qog'irchoq emas (0.42 past — bir xil javoblar).
LLM_TEMPERATURE = max(0.1, min(1.0, float(os.getenv("LLM_TEMPERATURE", "0.82") or 0.82)))
LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "8"))
LLM_MAX_TOKENS_DEFAULT = int(os.getenv("LLM_MAX_TOKENS_DEFAULT", "380"))  # to'liq javob, qo'g'irchoq emas
LLM_MAX_TOKENS_BRIEF = int(os.getenv("LLM_MAX_TOKENS_BRIEF", "180"))  # oddiy savol: fikrlash uchun joy (120→180)

# Voice-only UI: no transcript in console — talk like with a friend, not a chat log.
# 1 = default: do not print recognized text or reply text (pure voice experience).
VOICE_ONLY_UI = (os.getenv("NEUROKEY_VOICE_ONLY_UI", "1") or "1").strip().lower() in ("1", "true", "yes")

# Uzoq ish (soatlab): har N sekundda konsolga holat qatori + Windows konsol sarlavhasi — "tirik" ekanini ko'rish.
# 0 = o'chiq.
NEUROKEY_HEARTBEAT_SEC = _float("NEUROKEY_HEARTBEAT_SEC", 90.0)
NEUROKEY_HEARTBEAT_CONSOLE_TITLE = _bool("NEUROKEY_HEARTBEAT_CONSOLE_TITLE", True)

# UI/TTS/LLM: default rus tili. Env orqali ham rusni qat'iylash mumkin.
# Ruxsat: ru/en/uz. XATOLIK TUZATILDI (2026-09-11): bu ro'yxatda "uz" avval
# YO'Q edi — shuning uchun !NeuroKey_UZBEK.bat "NEUROKEY_UI_LANG=uz" desa ham,
# bu yerda sababsiz "ru"ga majburiy almashtirilardi. tts_openai.py o'zining
# _tts_ui_lang() funksiyasida to'g'ridan-to'g'ri os.getenv() o'qib, "uz"ni
# to'g'ri qabul qilar edi (shuning uchun ovoz ba'zan to'g'ri chiqardi), lekin
# main.py/babata_core.py/proactive_advisor.py kabi joylar ushbu C.NEUROKEY_UI_LANG
# orqali o'qiganda "ru"ga qaytib ketardi — natijada nomuvofiqlik: ba'zi javoblar
# ruscha, ba'zilari o'zbekcha chiqardi. Endi hammasi bir xil "uz"ni ko'radi.
_ui_lang = (os.getenv("NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()
NEUROKEY_UI_LANG = _ui_lang if _ui_lang in ("ru", "en", "uz") else "ru"

# ==========================
#  TELEGRAM (USER CLIENT)
# ==========================
TELEGRAM_ENABLED = True
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or 0)  # configda bo'lsa ham env ustun
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "").strip()  # +998...
# Session name (fayl nomi) — ko'p muammolarni shu hal qiladi
TELEGRAM_SESSION_NAME = (os.getenv("TELEGRAM_SESSION_NAME", "neurokey") or "neurokey").strip()
# eski maydon sizda bor ekan — saqlab qo'ydik
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "").strip() or None
# Ulanish timeout (sek). Tarmoq yo'q bo'lsa shu vaqtdan keyin Telegram siz davom etadi
TELEGRAM_CONNECT_TIMEOUT_SEC = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT_SEC", "25"))
# tg_send: laqab -> haqiqiy ism (akam -> Jasur, opam -> Dilnoza). Bo'sh bo'lsa — to'g'ridan-to'g'ri qidiriladi.
TG_CONTACT_ALIASES = {
    "akam": "",   # masalan "Jasur" — akangning Telegramdagi ismi
    "opam": "",
    "dadam": "",
    "onam": "",
}

# ==========================
#  SERPAPI (WEB)
# ==========================
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "").strip()
SERPAPI_TIMEOUT_SEC = float(os.getenv("SERPAPI_TIMEOUT_SEC", "5"))
SERPAPI_NUM_RESULTS = int(os.getenv("SERPAPI_NUM_RESULTS", "6"))

# WEB region/til
WEB_GL = (os.getenv("WEB_GL", "us") or "us").strip()

# “fresh/aktual” savollar uchun webni majburiy qilamiz
FORCE_WEB_FOR_FRESH = True
WEB_LAST_24H = (os.getenv("WEB_LAST_24H", "1") or "1").strip().lower() in ("1", "true", "yes")

# ==========================
#  Long-term memory (sqlite3)
# ==========================
MEMORY_PATH = os.getenv("MEMORY_PATH", "memory.json").strip()
LTM_DB_PATH = os.getenv("NEUROKEY_MEMORY_DB", "data/neurokey_memory.db").strip()
REMINDERS_PATH = os.getenv("NEUROKEY_REMINDERS_PATH", os.path.join(DATA_DIR, "reminders.json")).strip()
SOCIAL_BOND_PATH = os.getenv("NEUROKEY_SOCIAL_BOND_PATH", os.path.join(DATA_DIR, "social_bond.json")).strip()

# Todo list, calendar, task log, backup
NEUROKEY_TODO_PATH = os.getenv("NEUROKEY_TODO_PATH", "data/todo.json").strip()
NEUROKEY_CALENDAR_PATH = os.getenv("NEUROKEY_CALENDAR_PATH", "data/calendar.json").strip()
NEUROKEY_TASK_LOG_PATH = os.getenv("NEUROKEY_TASK_LOG_PATH", "data/neurokey_actions.log").strip()
NEUROKEY_BACKUP_DIR = os.getenv("NEUROKEY_BACKUP_DIR", "data/backup").strip()
# Integrations (optional)
SLACK_WEBHOOK_URL = (os.getenv("SLACK_WEBHOOK_URL", "") or "").strip()
DISCORD_WEBHOOK_URL = (os.getenv("DISCORD_WEBHOOK_URL", "") or "").strip()
NOTION_API_KEY = (os.getenv("NOTION_API_KEY", "") or "").strip()
SMART_HOME_HTTP_URL = (os.getenv("SMART_HOME_HTTP_URL", "") or "").strip()

# Proaktiv maslahatchi: shahar (ob-havo)
NEUROKEY_CITY = os.getenv("NEUROKEY_CITY", "Tashkent").strip()

# Tez javob: kesh serveri (ob-havo + yangiliklar) va /ask (boshqa komp sizning kompingizda javob oladi).
# Sizning kompda: Start_NeuroKey_Server.bat. To'xtatish: Stop_NeuroKey_Server.bat yoki Ctrl+C.
NEUROKEY_CACHE_SERVER_URL = (os.getenv("NEUROKEY_CACHE_SERVER_URL", "") or "").strip()
NEUROKEY_CACHE_SERVER_TIMEOUT_SEC = float(os.getenv("NEUROKEY_CACHE_SERVER_TIMEOUT_SEC", "2"))
# /ask so'rovlari uchun timeout (LLM javob kutiladi)
NEUROKEY_ASK_TIMEOUT_SEC = float(os.getenv("NEUROKEY_ASK_TIMEOUT_SEC", "38"))
# Serverda NEUROKEY_SERVER_SECRET qo'ysangiz, boshqa komp .env da shu kalitni beradi (xavfsizlik)
NEUROKEY_SERVER_SECRET = (os.getenv("NEUROKEY_SERVER_SECRET", "") or "").strip()

# Qulf: hohlagan payt NeuroKey ni ishlatishni to'xtatish. Parol bo'sh = "unlock" bilan ochish.
# Parolni olib tashlash: default bo'sh. .env da NEUROKEY_LOCK_PASSWORD=... qo'ysangiz parol ishlatiladi.
NEUROKEY_LOCK_PASSWORD = (os.getenv("NEUROKEY_LOCK_PASSWORD", "") or "").strip()

# ==========================
#  STT / VOSK (stt_vosk.py uchun)
# ==========================
_base_dir = os.path.dirname(os.path.abspath(__file__))
_models_dir = os.path.join(_base_dir, "models")
def _default_vosk_model_dir():
    """Boshqa kompda ham ishlashi uchun: env yoki mavjud papkalardan birini tanlaydi.
    Katta model (vosk-model-ru-0.42) mavjud bo'lsa — uni afzal ko'radi (aniqroq).
    """
    env_path = os.getenv("VOSK_MODEL_DIR", "").strip()
    if env_path and os.path.isdir(env_path):
        return env_path
    # Katta model → kichik model → fallback tartibida tekshirish
    candidates = [
        # Katta model (1.8GB, aniqlik ~95%) — mavjud bo'lsa afzal
        os.path.join(_models_dir, "vosk-model-ru-0.42"),
        os.path.join(_models_dir, "vosk", "vosk-model-ru-0.42"),
        os.path.join(_models_dir, "vosk-model-ru-0.22"),
        os.path.join(_models_dir, "vosk", "vosk-model-ru-0.22"),
        # Kichik model (87MB, aniqlik ~70%)
        os.path.join(_models_dir, "vosk-model-small-ru-0.22"),
        os.path.join(_models_dir, "vosk", "vosk-model-small-ru-0.22"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return os.path.join(_models_dir, "vosk-model-small-ru-0.22")
VOSK_MODEL_DIR = _default_vosk_model_dir()
TARGET_SR = int(os.getenv("TARGET_SR", "16000"))
BLOCKSIZE = int(os.getenv("BLOCKSIZE", "4000"))
PREFERRED_CHANNELS = 1
_input_idx = os.getenv("INPUT_DEVICE_INDEX", "").strip()
INPUT_DEVICE_INDEX = int(_input_idx) if _input_idx.isdigit() else None
AUTO_SELECT_AUDIO_DEVICE = _bool("AUTO_SELECT_AUDIO_DEVICE", True)
MIC_NAME_HINTS = [x.strip() for x in os.getenv("MIC_NAME_HINTS", "fifine,microphone,mic").split(",") if x.strip()]
SPEAKER_NAME_HINTS = [x.strip() for x in os.getenv("SPEAKER_NAME_HINTS", "headphone,headphones,науш,High Definition Audio").split(",") if x.strip()]
NEUROKEY_DEMO_FRIENDLY = os.getenv("NEUROKEY_DEMO_FRIENDLY", os.getenv("NEUROKEY_INVESTOR_DEMO", "0")).strip().lower() in ("1", "true", "yes")
ECHO_SUPPRESS = True
DROP_WHILE_TTS = True
# TTS dan keyin qancha jim — 400ms: echo uchun yetarli, lekin javobga sekin emas.
MUTE_AFTER_TTS_MS = max(50, min(2000, _int("MUTE_AFTER_TTS_MS", 400)))
# VAD: 0.008 = sezuvchan, shovqin kam (muammosiz bemalol).
VAD_RMS_GATE = max(0.005, min(0.05, _float("VAD_RMS_GATE", 0.008)))
# Ketma-ket bloklar: 2 = barqaror (noto'g'ri ishga tushish kam).
VAD_MIN_CONSECUTIVE = max(1, min(5, _int("VAD_MIN_CONSECUTIVE", 2)))
# Barge-in: TTS gapirganda foydalanuvchi gapirsa — 1 blok = tez to'xtatish.
VAD_MIN_CONSEC_BARGE_IN = max(1, min(6, _int("VAD_MIN_CONSEC_BARGE_IN", 4)))
# Barge-in RMS: yuqori = faqat aniq ovozda to'xtatish (0.015–0.08). Past = sezgir.
# 0.05 = TTS aks-sado orqali yolg'on barge-in oldini oladi
VAD_BARGE_IN_RMS = max(0.01, min(0.1, _float("VAD_BARGE_IN_RMS", 0.05)))
MIN_PHRASE_CHARS = max(1, min(10, _int("MIN_PHRASE_CHARS", 2)))
# 0 = past to'siq, 1 = qattiq filtrlash. Bemalol uchun 0.
NOISE_FILTER_STRICT = _bool("NOISE_FILTER_STRICT", False)
# Wake word: listen only after "NeuroKey" (or within PASS_THROUGH_AFTER_WAKE_SECONDS)
# Default 0 = gaplashishni darhol boshlash, wake word shart emas. 1 = avval NeuroKey aytish kerak.
REQUIRE_WAKE_WORD = os.getenv("NEUROKEY_REQUIRE_WAKE_WORD", "0").strip().lower() in ("1", "true", "yes")
WAKE_REGEX = r"(?<!\w)(нейрокей|neurokey)(?!\w)"
PASS_THROUGH_AFTER_WAKE_SECONDS = float(os.getenv("NEUROKEY_PASS_THROUGH_AFTER_WAKE_SEC", "30"))
# Short confirmation before long actions ("Okay", "Hmm"). Default 0 — kod chiqishi yo'q, faqat LLM javobi.
PLAY_CONFIRMATION_SOUNDS = os.getenv("NEUROKEY_PLAY_CONFIRMATION", "0").strip().lower() in ("1", "true", "yes")
CONFIRMATION_PHRASE = (os.getenv("NEUROKEY_CONFIRMATION_PHRASE", "") or "").strip()

# ==========================
#  Screen / ekran (past yuk — kamroq CPU, so‘raganda javob tayyor)
# ==========================
# Noutbuk rejimi: NEUROKEY_LAPTOP=1 — ekran tekshiruvi kamroq (batareya tejalashi)
NEUROKEY_LAPTOP = os.getenv("NEUROKEY_LAPTOP", "").strip().lower() in ("1", "true", "yes")
# Odamlar kabi: doim ko'radi. 2 sek = tez yangilash, video/rasm ham.
_default_screen_interval = "10" if NEUROKEY_LAPTOP else "2"
SCREEN_CAPTURE_INTERVAL_SEC = float(os.getenv("SCREEN_CAPTURE_INTERVAL_SEC", _default_screen_interval))
# Vision har 1 cycle = har capture da Vision (video, rasmlar tahlili).
SCREEN_VISION_CYCLE_INTERVAL = int(os.getenv("SCREEN_VISION_CYCLE_INTERVAL", "1"))
SCREEN_MAX_WIDTH_BACKGROUND = int(os.getenv("SCREEN_MAX_WIDTH_BACKGROUND", "2560"))
# OCR til: ru (rus+eng, xavfsiz standart) yoki eng (faqat lotin, tezroq).
#
# O'LCHANDI (toza, 3 marta qayta o'lchangan, alohida jarayonlarda):
#   rus+eng   ~2090-2191 ms   2936 belgi (kirill + lotin — to'liq)
#   eng       ~1472-1728 ms   2045 belgi (kirill YO'QOLADI — 30% kam)
#
# ~27% tezroq, LEKIN ekranda kirill matn bo'lsa uni o'tkazib yuboradi.
# Bu tezlik emas — ma'lumot yo'qotish. Shuning uchun standart "ru"
# (xavfsiz, to'liq) qoladi. Ekran deyarli har doim inglizcha bo'lsa,
# ongli ravishda SCREEN_OCR_LANG=eng o'rnatib tezlashtirish mumkin.
SCREEN_OCR_LANG = (os.getenv("SCREEN_OCR_LANG", "ru") or "ru").strip()
# Ekran olish usullari ketma-keti (mss ishlamasa pyautogui, gdi, pil_grab sinab ko'riladi)
SCREEN_GRAB_METHODS = (os.getenv("SCREEN_GRAB_METHODS", "mss,pyautogui,gdi,pil_grab") or "mss,pyautogui,gdi,pil_grab").strip().lower().split(",")
# OCR bo'sh bo'lsa Vision API orqali matn olish (1 = yoq, amalda ishlamasa foydali)
SCREEN_OCR_FALLBACK_VISION = (os.getenv("SCREEN_OCR_FALLBACK_VISION", "1") or "1").strip().lower() in ("1", "true", "yes")
# Tahlil ketma-keti: vision,ocr — Vision birinchi; ocr,vision — OCR birinchi
SCREEN_ANALYSIS_ORDER = (os.getenv("SCREEN_ANALYSIS_ORDER", "vision,ocr") or "vision,ocr").strip().lower()
# Vision rasm sifati — 100 (eng yuqori, yo'qotishsiz)
SCREEN_VISION_JPEG_QUALITY = 100
# 0 = tez rejim: OCR + oyna sarlavhalari (Groq/onlayn uchun). 1 = Vision LLM (sekin, Ollama 45s).
SCREEN_VISION_USE_LLM = os.getenv("SCREEN_VISION_USE_LLM", "0").strip().lower() in ("1", "true", "yes")
# Proaktiv/ADLF ekran monologi (foydalanuvchi savolini bloklaydi)
NEUROKEY_PROACTIVE_SCREEN = os.getenv("NEUROKEY_PROACTIVE_SCREEN", "0").strip().lower() in ("1", "true", "yes")
# Savol eshitilganda uzoq TTS ni uzish
NEUROKEY_INTERRUPT_TTS_ON_SPEECH = os.getenv("NEUROKEY_INTERRUPT_TTS_ON_SPEECH", "1").strip().lower() in ("1", "true", "yes")

# Rasm / video / audio tahlili (media_vision): fayl yo'li ovozda berilmasa shu yo'ldan olinadi
NEUROKEY_LAST_MEDIA_PATH = (os.getenv("NEUROKEY_LAST_MEDIA_PATH", "") or "").strip() or None
# Vision model: rasm va video kadrlar uchun (gpt-4o-mini yoki gpt-4o)
OPENAI_VISION_MODEL = (os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini") or "gpt-4o-mini").strip()

# ==========================
#  Murakkab vazifa (ketma-ket qadamlar)
# ==========================
COMPLEX_TASK_MAX_STEPS = int(os.getenv("COMPLEX_TASK_MAX_STEPS", "6"))

# ==========================
#  Language policy / STT
# ==========================
# STT: faqat rus tili. Savol va javob — ruscha.
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "ru").strip().lower()
# Hear the question to the end: wait this long after user stops speaking before considering utterance complete.
# 0.85 = muammosiz (tez javob, lekin gap kesilmasin).
STT_SILENCE_HOLD_SEC = max(0.5, min(5.0, float(os.getenv("STT_SILENCE_HOLD_SEC", "0.85"))))
STT_MAX_UTTERANCE_SEC = max(10, min(120, float(os.getenv("STT_MAX_UTTERANCE_SEC", "35"))))
# Mic sensitivity: 0.008 = muvozanat (shovqin kam, ovoz qabul).
STT_SILENCE_RMS = max(0.004, min(0.03, float(os.getenv("STT_SILENCE_RMS", "0.008"))))
# Barge-in: faqat aniq nutqda TTS ni to'xtatish. Oddiy shovqinda to'xtatmasin.
# STT_ENERGY_THRESHOLD=400 — yuqori (400/10000=0.04 RMS). 300–500 oralig'i.
_stt_energy = _int("STT_ENERGY_THRESHOLD", 400)
STT_ENERGY_THRESHOLD = max(100, min(1000, _stt_energy))
STT_BARGE_IN_RMS = max(0.01, min(0.08, float(os.getenv("STT_BARGE_IN_RMS", str(STT_ENERGY_THRESHOLD / 10000.0)))))
# TTS gapirayotganda STT kutsin (1) — gap oxirigacha uzilmasin. 0 = barge-in yoq.
STT_PAUSE_DURING_TTS = _bool("STT_PAUSE_DURING_TTS", True)
# TTS tugagandan keyin qancha ms kutish (echo bartaraf)
STT_WAIT_AFTER_TTS_MS = max(0, min(2000, int(os.getenv("STT_WAIT_AFTER_TTS_MS", "600"))))

# ==========================
#  Control / Windows safety (control.py)
# ==========================
# SAFE MODE: if True, never taskkill system processes; block risky actions; stricter whitelist
CONTROL_SAFE_MODE = os.getenv("CONTROL_SAFE_MODE", "1").strip().lower() in ("1", "true", "yes")
# Log every control action to this file (empty = no file log)
CONTROL_LOG_PATH = os.getenv("CONTROL_LOG_PATH", "control.log").strip() or None
# Require voice confirm before risky actions (e.g. close all apps, delete file)
CONTROL_REQUIRE_CONFIRM_RISKY = os.getenv("CONTROL_REQUIRE_CONFIRM_RISKY", "0").strip().lower() in ("1", "true", "yes")
# Watchdog: restart explorer.exe if it dies (prevents black desktop)
CONTROL_EXPLORER_WATCHDOG = os.getenv("CONTROL_EXPLORER_WATCHDOG", "1").strip().lower() in ("1", "true", "yes")
CONTROL_EXPLORER_WATCHDOG_INTERVAL_SEC = float(os.getenv("CONTROL_EXPLORER_WATCHDOG_INTERVAL_SEC", "15"))
# Bring-to-front: first try after this many seconds (dastur oynasi ko'rinsin)
CONTROL_BRING_TO_FRONT_DELAY_SEC = float(os.getenv("CONTROL_BRING_TO_FRONT_DELAY_SEC", "1.2"))
# Second try for slow-starting apps (e.g. Telegram)
CONTROL_BRING_TO_FRONT_RETRY_SEC = float(os.getenv("CONTROL_BRING_TO_FRONT_RETRY_SEC", "2.5"))
# Tasklist cache TTL (seconds) — avoid repeated tasklist in same flow
CONTROL_TASKLIST_CACHE_SEC = _float("CONTROL_TASKLIST_CACHE_SEC", 0.3)
# Har qanday dasturni ochish: 1 = kod ichiga yozilmagan dasturlar ham (notepad, spotify, vscode). 0 = faqat ro'yxatdagi.
CONTROL_OPEN_APP_GENERIC = _bool("CONTROL_OPEN_APP_GENERIC", True)

# ==========================
#  Autonomous Digital Lifeform (ADLF) — kompyuter ichida yashash
# ==========================
# NeuroKey faqat gapirish emas — tizimda yashaydi. ADLF = background ong, ekran tahlili, proactive.
# 1 = Background consciousness, proactive interruption, autonomous problem solving
NEUROKEY_ADLF_ENABLED = os.getenv("NEUROKEY_ADLF_ENABLED", "1").strip().lower() in ("1", "true", "yes")
# Background cycle interval (seconds): tizim, ekran, yangiliklar tekshiruvi
# Demo uchun: ADLF_CYCLE_INTERVAL_SEC=600  |  Normal: 120
ADLF_CYCLE_INTERVAL_SEC = int(os.getenv("ADLF_CYCLE_INTERVAL_SEC", "120"))
# Delay before first cycle (seconds)
# Demo uchun: ADLF_FIRST_DELAY_SEC=300  |  Normal: 60
ADLF_FIRST_DELAY_SEC = int(os.getenv("ADLF_FIRST_DELAY_SEC", "60"))
# Screen-based proactive tip: 1 = LLM analyze screen for errors/better paths
ADLF_SCREEN_PROACTIVE = os.getenv("ADLF_SCREEN_PROACTIVE", "1").strip().lower() in ("1", "true", "yes")
# Zero-Latency: OS event hooks (foreground window change) — interval yo'q, real vaqt
ADLF_ZERO_LATENCY_HOOKS = os.getenv("ADLF_ZERO_LATENCY_HOOKS", "1").strip().lower() in ("1", "true", "yes")
# User yo'q bo'lganda Core decide (curiosity, boredom) — file_list, window_list va hokazo
ADLF_AUTONOMOUS_CORE = _bool("ADLF_AUTONOMOUS_CORE", True)

# Suniy ong: ichki monolog — murakkab savolda javobdan oldin o'ylash
NEUROKEY_INNER_SPEECH = _bool("NEUROKEY_INNER_SPEECH", True)
# 1 = haqiqiy pre-LLM "o'zingga savol" chaqiruv (1–2 sek qo'shimcha). 0 = faqat prompt hint
# False by default: qo'shimcha API call kechikish tug'diradi, jim qolish xatosini oshiradi
NEUROKEY_INNER_SPEECH_REAL = _bool("NEUROKEY_INNER_SPEECH_REAL", True)
# Murakkab savolda qisqa "o'ylash" pauza (sekund, 0=yo'q). 0.2–0.5 — tabiiy his
NEUROKEY_THINKING_PAUSE_SEC = float(os.getenv("NEUROKEY_THINKING_PAUSE_SEC", "0"))
# Fenomenal → qarorlar: valence past yoki arousal yuqori bo'lsa ehtiyotkorlik hint
NEUROKEY_AFFECT_TO_DECISIONS = _bool("NEUROKEY_AFFECT_TO_DECISIONS", True)
# Global Workspace (GWT): valence, meta-kognitsiya, compete/broadcast integratsiyasi
NEUROKEY_GWT_INTEGRATION = _bool("NEUROKEY_GWT_INTEGRATION", True)
# Tezlik + ekran + tozalash: display overlay, response cleaner, screen monitor, performance warmup
NEUROKEY_DISPLAY_OVERLAY = _bool("NEUROKEY_DISPLAY_OVERLAY", False)
# Har bir streaming chunk uchun alohida subtitle (False = faqat oxirida to'liq javob)
NEUROKEY_SUBTITLE_PER_CHUNK = _bool("NEUROKEY_SUBTITLE_PER_CHUNK", False)
# TTS rejimi: stream = har jumla o'sha zahoti gapiradi (tezroq), full = to'liq javob bir marta
NEUROKEY_TTS_MODE = (os.getenv("NEUROKEY_TTS_MODE", "stream") or "stream").strip().lower()
NEUROKEY_RESPONSE_CLEANER = _bool("NEUROKEY_RESPONSE_CLEANER", True)
NEUROKEY_SCREEN_MONITOR = _bool("NEUROKEY_SCREEN_MONITOR", False)
NEUROKEY_PERFORMANCE_WARMUP = _bool("NEUROKEY_PERFORMANCE_WARMUP", True)
# Bosqich 3: O'z-o'zini modellash, RL, bashorat, shaxsiyat
NEUROKEY_BOSQICH3 = _bool("NEUROKEY_BOSQICH3", True)
# Bosqich 4: Virtual Embodiment — tana holati, sensor integratsiya
NEUROKEY_EMBODIMENT = _bool("NEUROKEY_EMBODIMENT", True)
# Bosqich 5: Free Energy Principle — Active Inference
NEUROKEY_FREE_ENERGY = _bool("NEUROKEY_FREE_ENERGY", True)

# ─── SUNIY ONG KENGAYTMASI (2026) ─────────────────────────────────────────
# Fon sensori: har 30s da CPU/RAM/vaqt/oyna/batareya holati
NEUROKEY_BG_SENSOR = _bool("NEUROKEY_BG_SENSOR", True)
# Narrativ o'zlik: "Men kim edim, men kimman" — haftalik yangilanadi
NEUROKEY_NARRATIVE_SELF = _bool("NEUROKEY_NARRATIVE_SELF", True)
# Tun konsolidatsiyasi: har kecha 03:00 da ong qayta ishlanadi
NEUROKEY_DREAM_CONSOLIDATION = _bool("NEUROKEY_DREAM_CONSOLIDATION", True)
# Qiziqish motori: ichki motivatsiya, yangi mavzularga qiziqish
NEUROKEY_CURIOSITY_ENGINE = _bool("NEUROKEY_CURIOSITY_ENGINE", True)
# Fon sensori yangilanish intervali (soniya)
NEUROKEY_SENSOR_INTERVAL_SEC = int(os.getenv("NEUROKEY_SENSOR_INTERVAL_SEC", "30"))

# 0 = salom/tushunish/hissiyot uchun qisqa shablon javoblar yo'q — har safar LLM (takrorlanish kam)
NEUROKEY_INSTANT_REPLIES = _bool("NEUROKEY_INSTANT_REPLIES", True)

# ==========================
#  DEMO REJIMI SOZLAMALARI
# ==========================
# Proaktiv ong: fon threadida trigger tekshirish intervali (soniya)
# Normal: 120  |  Demo (bezovta qilmasin): NEUROKEY_PROACTIVE_INTERVAL_SEC=600
NEUROKEY_PROACTIVE_INTERVAL_SEC = int(os.getenv("NEUROKEY_PROACTIVE_INTERVAL_SEC", "120"))
# Proaktiv ong: birinchi ishga tushishdan qancha soniya keyin boshlansin
# Normal: 45  |  Demo (boshlanganda gapirib qo'ymasin): NEUROKEY_PROACTIVE_FIRST_DELAY_SEC=7200
NEUROKEY_PROACTIVE_FIRST_DELAY_SEC = int(os.getenv("NEUROKEY_PROACTIVE_FIRST_DELAY_SEC", "45"))
# Veb-kamera fon yozuvi: 1 = yoqiq, 0 = o'chirilgan
# Demo (kamera qorong'i bo'lsa): NEUROKEY_CAMERA_ENABLED=0
NEUROKEY_CAMERA_ENABLED = _bool("NEUROKEY_CAMERA_ENABLED", True)
# Self-improve loop intervali (daqiqa)
# Normal: 10  |  Demo (resursni band qilmasin): NEUROKEY_SELFIMPROVE_INTERVAL_MIN=120
NEUROKEY_SELFIMPROVE_INTERVAL_MIN = int(os.getenv("NEUROKEY_SELFIMPROVE_INTERVAL_MIN", "10"))
# Spontaneity: 0.0–1.0 (0.25 = 25% ehtimol ijodiy javob)
NEUROKEY_SPONTANEITY_RATE = float(os.getenv("NEUROKEY_SPONTANEITY_RATE", "0.25"))
# Dialog history LLM ga (turnlar soni)
NEUROKEY_HISTORY_LIMIT = _int("NEUROKEY_HISTORY_LIMIT", 12)
# LLM kontekst token limiti
NEUROKEY_CONTEXT_MAX_TOKENS = _int("NEUROKEY_CONTEXT_MAX_TOKENS", 2500)
# Gamma.app taqdimot yaratish API kaliti
GAMMA_API_KEY = os.getenv("GAMMA_API_KEY", "").strip()
# Ollama model: env orqali o'zgartirish mumkin
# Misol: OLLAMA_MODEL=gemma3:latest  yoki  OLLAMA_MODEL=llama3.1:8b
OLLAMA_MODEL_OVERRIDE = (os.getenv("OLLAMA_MODEL", "") or "").strip()


def validate_config() -> list:
    """Konfiguratsiya tekshiruvi. Xatolar ro'yxatini qaytaradi."""
    err = []
    if not OPENAI_API_KEY:
        err.append("OPENAI_API_KEY bo'sh. .env da qo'ying.")
    if TELEGRAM_ENABLED and (not TELEGRAM_API_ID or not TELEGRAM_API_HASH):
        err.append("TELEGRAM: API_ID va API_HASH kerak.")
    if FORCE_WEB_FOR_FRESH and not SERPAPI_API_KEY:
        err.append("SERPAPI_API_KEY yo'q — web qidiruv ishlamaydi.")
    return err
