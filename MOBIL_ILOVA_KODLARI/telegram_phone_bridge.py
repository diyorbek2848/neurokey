# -*- coding: utf-8 -*-
"""
NeuroKey — Telefon orqali Telegram ko'prigi (vaqtinchalik, investitsiyasiz)
============================================================================

MAQSAD
------
Asl NeuroKey "miya"sini (main.py ichidagi handle_text() — xotira, bilim bazasi,
shaxsiyat, hammasi desktop ilova bilan BIR XIL) sizning shaxsiy Telegram
akkountingiz orqali telefoningizdan foydalanish imkonini beradi. Bulutli
infratuzilma uchun pul sarflamasdan — bu PC yoqilgan turgan vaqtdagi vaqtinchalik
yechim.

QANDAY ISHLAYDI
----------------
1. Bu skript sizning ShAXSIY Telegram akkountingizga (bot EMAS — .env dagi
   TELEGRAM_API_ID/HASH/PHONE bilan) Telethon orqali ulanadi (mavjud
   "neurokey.session" fayli orqali — qayta login kerak emas).
2. Telegram ilovangizdagi "Saved Messages" (O'zingizga yozilgan xabarlar / Избранное)
   bo'limini tinglaydi — FAQAT shu chatni. Boshqa odamlar sizga yozgan xabarlarga
   HECH QACHON javob bermaydi (LLM chaqirilmaydi — pul/vaqt isrofi bo'lmaydi).
3. Matnli xabar kelsa: main.py dagi asl handle_text() orqali (memory.json,
   long-term memory, shaxsiyat, bilim bazasi bilan) javob generatsiya qilinadi va
   Telegram orqali matn sifatida qaytariladi.
4. Ovozli xabar kelsa: yuklab olinadi, matnga aylantiriladi (STT), xuddi shu
   handle_text() orqali javob olinadi, so'ng ovozga aylantirilib (TTS) ovozli
   xabar sifatida qaytariladi (matn bilan birga).

XAVFSIZLIK
----------
- Faqat "Saved Messages" (o'z-o'zingizga yozilgan chat) orqali kelgan xabarlarga
  javob beradi. Xohlasangiz .env da TELEGRAM_BRIDGE_ALLOWED_PEER=<user_id> orqali
  boshqa bitta shaxsiy chatni ruxsat etilgan qilib belgilashingiz mumkin.
- Javoblar oldiga "🤖 " belgisi qo'shiladi — shu orqali bot o'zining javoblarini
  qayta o'qib, cheksiz tsiklga tushib qolmasligi ta'minlanadi (va telefon
  ekranida qaysi xabar AI javobi ekani ko'rinib turadi).

MUHIM ESLATMA
--------------
Bu skript va desktop "!NeuroKey.bat" BIR XIL Telegram sessiyasidan
("neurokey.session") foydalanadi. Ikkalasini BIR VAQTDA ishga tushirmang —
Telethon session fayli bir vaqtda faqat bitta jarayon tomonidan ishlatilishi
kerak. Birini tanlang: yo desktop ilova, yo shu telefon ko'prigi.

ISHGA TUSHIRISH
----------------
    !NeuroKey_Telefon.bat

yoki to'g'ridan-to'g'ri:

    .venv\\Scripts\\python.exe telegram_phone_bridge.py
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from typing import Optional

# ── Muhit sozlamalari: main.py import qilinishidan OLDIN o'rnatiladi ────────
# (Desktop !NeuroKey.bat dagi bilan bir xil "miya" xatti-harakati uchun —
#  faqat mikrofon/kamera/HUD/orb kabi faqat-desktopga xos narsalar o'chirilgan.)
os.environ.setdefault("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
os.environ.setdefault("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
os.environ.setdefault("OPENAI_CHAT_MODEL", "openai/gpt-oss-20b")
# BUG FIX (til): "ru" bilan qattiq belgilash O'CHIRILDI. STT_LANGUAGE=auto —
# Whisper har bir ovozli xabar uchun tilni o'zi aniqlaydi (stt_openai_whisper.py /
# stt_faster_whisper_local.py "auto" ni maxsus qiymat sifatida allaqachon qo'llab-
# quvvatlaydi). NEUROKEY_UI_LANG — bu yerda faqat BOSHLANG'ICH standart (birinchi
# xabar kelgunga qadar) — egasining asosiy tili o'zbekcha. Har bir real xabar uchun
# _generate_reply() ichida language_detect.py orqali QAYTA aniqlanadi va shu env
# o'zgaruvchi shunga mos yangilanadi (pastga qarang).
os.environ.setdefault("STT_LANGUAGE", "auto")
os.environ.setdefault("NEUROKEY_UI_LANG", "uz")
# OPENAI_API_KEY .env da TTS/Whisper uchun yaroqsiz bo'lishi mumkin (faqat GROQ_API_KEY
# chat uchun ishlaydi) — desktop !NeuroKey.bat kabi TTS ni Edge TTS ga yo'naltiramiz.
os.environ.setdefault("TTS_SKIP_OPENAI", "1")
os.environ.setdefault("TTS_USE_EDGE_RUSSIAN", "1")
os.environ.setdefault("TTS_EDGE_RUSSIAN_VOICE", "ru-RU-DmitryNeural")
os.environ.setdefault("TTS_EDGE_UZBEK_VOICE", "uz-UZ-MadinaNeural")
os.environ.setdefault("LLM_TEMPERATURE", "0.45")
os.environ.setdefault("LLM_MAX_TOKENS_DEFAULT", "220")
os.environ.setdefault("NEUROKEY_HISTORY_LIMIT", "6")
os.environ.setdefault("NEUROKEY_ALWAYS_OWNER", "1")
os.environ.setdefault("NEUROKEY_BIOMETRIC_BLOCK", "0")
os.environ.setdefault("NEUROKEY_REQUIRE_WAKE_WORD", "0")
os.environ.setdefault("NEUROKEY_OFFLINE_ONLY", "0")
os.environ.setdefault("NEUROKEY_FORCE_WEB", "1")
os.environ.setdefault("NEUROKEY_BG_AUTOTALK", "0")
os.environ.setdefault("NEUROKEY_CAMERA_ENABLED", "0")
os.environ.setdefault("NEUROKEY_SCREEN_MONITOR", "0")
os.environ.setdefault("NEUROKEY_SKIP_STARTUP_TTS", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONWARNINGS", "ignore")

# BUG FIX (konsol kodировка): os.environ.setdefault("PYTHONIOENCODING", ...)
# JORIY jarayonning sys.stdout/stderr oqimiga ta'sir QILMAYDI — bu faqat
# Python ISHGA TUSHISHIDAN OLDIN o'qiladi. Agar konsol kodировkasi UTF-8
# bo'lmasa (masalan cp1251/cp866 — !NeuroKey_Telefon.bat "chcp 65001"
# qiladi, lekin skript boshqa yo'l bilan (IDE/vazifa rejalashtiruvchi/log
# fayl orqali) ishga tushirilsa bu YO'Q), o'zbekcha/ruscha matnni print()
# qilish UnicodeEncodeError bilan QULAYDI — bu esa /api/talk kabi HTTP
# so'rov ishlovchisi ichida bo'lsa, butun so'rovni 500-xato bilan
# BUZADI (aniqlangan: test paytida xuddi shu sabab bilan chindan ham
# ushlangan). reconfigure() joriy oqimni DARHOL UTF-8 ga o'tkazadi va
# kodировka qila olmagan belgilarni ("errors=replace") jimgina almashtiradi
# — hech qachon qulamaydi.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPLY_MARKER = "🤖 "  # bot javobi belgisi — o'z-o'zini qayta o'qib cheksiz tsiklga tushmasligi uchun
# (Ko'rinmas/zero-width belgilar Telegram tomonidan tozalanib ketishi mumkin —
#  tsikl oldini olish mexanizmi 100% ishonchli bo'lishi uchun oddiy, ko'rinadigan
#  belgi ishlatiladi. Bonus: telefon ekranida qaysi xabar AI javobi ekani ko'rinib turadi.)
VOICE_LOCAL_PLAYBACK = os.getenv("NEUROKEY_BRIDGE_LOCAL_AUDIO", "0").strip().lower() in ("1", "true", "yes")

print("=" * 70, flush=True)
print(" NeuroKey — Telefon/Telegram ko'prigi ishga tushmoqda...", flush=True)
print(" (Miya yuklanmoqda — bu 15-25 soniya olishi mumkin, kuting)", flush=True)
print("=" * 70, flush=True)

_t_boot = time.time()
import main as nk  # noqa: E402  — handle_text(), MemoryStore, LongTermMemory shu yerdan
import config as C  # noqa: E402
from tts_openai import TTSWorker  # noqa: E402
from stt_openai_whisper import whisper_transcribe_int16  # noqa: E402
from language_detect import detect as _detect_lang_full  # noqa: E402 — Bug fix (til)
import neurokey_prewarm  # noqa: E402 — Bug fix (sovuq start)
import consciousness_orchestrator as _co  # noqa: E402 — "tinglash paytida o'ylash" prewarm

from telethon import TelegramClient, events  # noqa: E402

print(f"[BRIDGE] Miya yuklandi ({time.time() - _t_boot:.1f}s).", flush=True)

# ─────────────────────────────────────────────────────────────────────────
# BUG FIX (sovuq start — 51s kutish): desktop !NeuroKey.bat ichidagi main()
# funksiyasi ishga tushganda neurokey_prewarm.start() ni chaqiradi — bu bilim
# bazasi embedding modelini (paraphrase-multilingual-MiniLM) va ong kontekstini
# fon threadida oldindan yuklaydi. Bu ko'prik hech qachon nk.main() ni
# chaqirmaydi (faqat nk.handle_text() ni to'g'ridan-to'g'ri) — shuning uchun
# prewarm HECH QACHON boshlanmagan, va birinchi haqiqiy xabar embedding
# modelini o'zi (sinxron, ~40-50s) yuklashga majbur bo'lgan. Buni ENG BIRINCHI
# ishga tushiramiz — Telegramga ulanish (bir necha soniya) davomida ham fonda
# yuklanishda davom etadi, shunda birinchi xabar kelganda deyarli tayyor bo'ladi.
try:
    neurokey_prewarm.start()
    print("[BRIDGE] Bilim bazasi + ong konteksti fon rejimida isitilmoqda "
          "(endi birinchi xabar sekin bo'lmaydi)...", flush=True)
except Exception as _pw_boot_e:
    print("[BRIDGE] Prewarm boshlanmadi (o'tkazib yuborildi):", repr(_pw_boot_e), flush=True)


# ─────────────────────────────────────────────────────────────────────────
# 1) CapturingTTS — handle_text() qanday javob "gapirmoqchi" bo'lsa, ovoz
#    o'rniga MATN sifatida yig'ib oladi (PC dinamigidan ovoz chiqmaydi,
#    faqat NEUROKEY_BRIDGE_LOCAL_AUDIO=1 bo'lsa chiqadi). Telegram uchun
#    alohida (haqiqiy) ovoz sintezi kerak bo'lsa _fetch_audio() orqali olinadi.
# ─────────────────────────────────────────────────────────────────────────
class CapturingTTS(TTSWorker):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.captured: list[str] = []

    def _capture(self, text: str) -> bool:
        t = (text or "").strip()
        if t:
            self.captured.append(t)
        return bool(t)

    def say(self, text: str) -> bool:  # noqa: D401
        ok = self._capture(text)
        if VOICE_LOCAL_PLAYBACK and ok:
            try:
                return super().say(text)
            except Exception:
                pass
        return ok

    def say_finish_backup(self, text: str) -> bool:
        t = (text or "").strip()
        if not t or len(t) < 3:
            return False
        return self._capture(text)

    def reset_captured(self) -> None:
        self.captured = []

    def reply_text(self) -> str:
        seen = set()
        out = []
        for t in self.captured:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return " ".join(out).strip()


# ─────────────────────────────────────────────────────────────────────────
# 2) Real "miya" holati — desktop ilova ishlatadigan XUDDI SHU memory.json va
#    long-term memory DB fayllari (davomiylik saqlanadi).
# ─────────────────────────────────────────────────────────────────────────
memory = None
if nk._HAVE_MEMORY:
    try:
        memory = nk.MemoryStore(getattr(C, "MEMORY_PATH", "memory.json"))
        print("[BRIDGE] Memory yuklandi (desktop bilan bir xil fayl).", flush=True)
    except Exception as e:
        print("[BRIDGE] Memory xato:", repr(e), flush=True)

long_term_memory = None
if nk._HAVE_LTM:
    try:
        long_term_memory = nk.LongTermMemory(getattr(C, "LTM_DB_PATH", "data/neurokey_memory.db"))
        print("[BRIDGE] Long-term memory yuklandi.", flush=True)
    except Exception as e:
        print("[BRIDGE] LTM xato:", repr(e), flush=True)

tts = CapturingTTS(voice=getattr(C, "OPENAI_TTS_VOICE", "nova"))
print("[BRIDGE] TTS worker tayyor.", flush=True)

_proc_lock = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────────
# BUG FIX (til — har doim ruscha javob): avval NEUROKEY_UI_LANG butun jarayon
# davomida BIR MARTA o'rnatilgan qiymat edi (bat faylda "ru" qattiq yozilgan).
# main.py._ui_lang() va llm_router.py ning Groq-yo'li HAM shu env o'zgaruvchini
# jonli (har chaqiriqda) o'qiydi — lekin uni HECH KIM xabar matniga qarab
# YANGILAMAGAN. language_detect.py (uz/ru/en aniqlash) allaqachon bor edi va
# llm_router._detect_lang() unga delegatsiya qilardi — lekin _detect_lang()
# HECH QAYERDA chaqirilmasdi (o'lik kod). Bu yerda HAR BIR xabar uchun til
# haqiqatan ham aniqlanadi va NEUROKEY_UI_LANG shunga mos yangilanadi — bu esa
# _ui_lang() / Groq system-prompt tanlovi / TTS ovoz tanlovi (tts_openai.py)
# uchun BIR JOYDAN to'g'ri ishlaydi (hammasi shu env ni jonli o'qiydi).
def _resolve_reply_lang(text: str) -> str:
    try:
        r = _detect_lang_full(text or "")
        if r.lang in ("uz", "ru", "en") and r.confidence >= 0.35:
            return r.lang
    except Exception:
        pass
    # Noaniq/aniqlanmadi ("other", juda past ishonch) — egasining ASOSIY
    # tiliga (o'zbek) qaytamiz, ruschaga EMAS (avvalgi xato xatti-harakat).
    return "uz"


def _generate_reply(user_text: str) -> str:
    """Sync — handle_text() ni chaqiradi va gapirilgan matnni qaytaradi.
    Alohida threadda ishga tushiriladi (asyncio loop bloklanmasin)."""
    _reply_lang = _resolve_reply_lang(user_text)
    os.environ["NEUROKEY_UI_LANG"] = _reply_lang
    print(f"[BRIDGE] Til aniqlandi: {_reply_lang!r} (matn: {user_text[:40]!r})", flush=True)
    tts.reset_captured()
    try:
        nk.handle_text(
            user_text,
            tts,
            tg_user=None,
            memory=memory,
            orb=None,
            long_term_memory=long_term_memory,
        )
    except Exception:
        traceback.print_exc()
    try:
        tts.drain_speech(timeout=45.0)
    except Exception:
        pass
    reply = tts.reply_text()
    if not reply:
        reply = (
            "Kechirasiz, javob generatsiya qilishda muammo bo'ldi. Qaytadan urinib ko'ring."
            if (os.getenv("NEUROKEY_UI_LANG", "ru") or "ru") != "en"
            else "Sorry, something went wrong generating a reply. Please try again."
        )
    return reply


def _synthesize_voice_reply(text: str) -> Optional[str]:
    """Javob matnini haqiqiy ovoz faylga aylantiradi (Telegram voice-note uchun).
    Muvaffaqiyatsiz bo'lsa None qaytaradi — chaqiruvchi shunda faqat matn bilan
    javob beradi."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        import numpy as np
        from scipy.io import wavfile

        data = tts._fetch_audio(text[:1500])  # xom audio, dinamikka chiqmaydi
        if not data:
            return None
        audio, sr = data
        pcm16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="nk_tg_reply_")
        os.close(fd)
        wavfile.write(wav_path, sr, pcm16)

        # OGG/Opus ga aylantirish — Telegram "ovozli xabar" pufakchasi uchun (ixtiyoriy)
        try:
            import imageio_ffmpeg

            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            ogg_path = wav_path[:-4] + ".ogg"
            r = subprocess.run(
                [ffmpeg_exe, "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "32k", ogg_path],
                capture_output=True,
                timeout=30,
            )
            if r.returncode == 0 and os.path.isfile(ogg_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
                return ogg_path
        except Exception as e:
            print("[BRIDGE] OGG konvertatsiya o'tkazib yuborildi:", repr(e), flush=True)
        return wav_path
    except Exception:
        traceback.print_exc()
        return None


def _decode_audio_bytes(data: bytes):
    """Telegram voice-note (OGG/Opus) baytlarini int16 PCM + sample-rate ga aylantiradi."""
    import av
    import numpy as np

    container = av.open(io.BytesIO(data))
    stream = container.streams.audio[0]
    sr = stream.rate
    frames = []
    for packet in container.demux(stream):
        for frame in packet.decode():
            frames.append(frame.to_ndarray())
    container.close()
    if not frames:
        return None, None
    audio = np.concatenate(frames, axis=-1).flatten().astype(np.float32)
    if audio.max() > 1.5:
        audio = audio / 32768.0
    pcm16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
    return pcm16, sr


# ─────────────────────────────────────────────────────────────────────────
# 2b) Skrinshot, fayl qidirish/yuborish — "Diqqat: main.py da control.py orqali
#     shunga o'xshash voice-buyruqlar bor (masalan _is_folder_search /
#     control.search_files), va executor.py da telegram_bridge.get_bridge()
#     orqali 'telegram_screenshot'/'telegram_send' amallari bor. Skrinshot
#     olishning o'zi uchun XUDDI SHU screen_vision.grab_screen() ni qayta
#     ishlatamiz (screen_vision — bitta markazlashgan ekran-olish motori,
#     telegram_bridge.py da ham shu orqali ishlaydi). Fayl qidirish uchun esa
#     control.search_files/search_folders ATAYLAB qayta ishlatilmadi — ular
#     hech qanday xavfsizlik filtri qilmasdan (.env, .git, .venv va h.k.)
#     butun user-home'ni qidiradi; bu yerda telefon-orqali-tashqi-dunyoga-
#     ochiq kanal bo'lgani uchun qat'iyroq, o'z xavfsizlik qatlamimiz bilan
#     qidiramiz (faqat Documents/Desktop/Downloads, sezgir fayllar chiqarib
#     tashlanadi)."
# ─────────────────────────────────────────────────────────────────────────
_USER_HOME = os.path.expanduser("~")
SAFE_SEARCH_ROOTS = [
    os.path.join(_USER_HOME, "Documents"),
    os.path.join(_USER_HOME, "Desktop"),
    os.path.join(_USER_HOME, "Downloads"),
]

# Bu papka nomlari uchralsa — ichiga UMUMAN kirilmaydi (qidiruv paytida kesib tashlanadi)
_EXCLUDED_DIR_NAMES = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".cache", "site-packages", ".idea", ".vscode", "AppData",
    ".ssh", ".aws", ".gnupg",
}
# Bu aniq fayl nomlari — hech qachon natija sifatida qaytarilmaydi/yuborilmaydi
_EXCLUDED_FILENAMES = {".env", "credentials.json", "token.json"}
# Nomida shu qatorlardan biri bo'lsa — sezgir deb hisoblanadi, chetlab o'tiladi
_EXCLUDED_NAME_SUBSTRINGS = (
    ".session", ".session-journal", "secret", "password", "parol",
    "api_key", "apikey", "private_key", "id_rsa",
)
_MAX_SEND_BYTES = 50 * 1024 * 1024  # 50MB — telefon/mobil internet uchun oqilona chegara


def _is_safe_search_result(path: str) -> bool:
    norm = os.path.normpath(path)
    parts = {p for p in norm.split(os.sep)}
    if parts & _EXCLUDED_DIR_NAMES:
        return False
    name = os.path.basename(norm).lower()
    if name in _EXCLUDED_FILENAMES:
        return False
    if any(s in name for s in _EXCLUDED_NAME_SUBSTRINGS):
        return False
    return True


def _search_user_files(query: str, max_results: int = 6):
    """Documents/Desktop/Downloads ichida (faqat!) fayl nomi bo'yicha qidirish.
    D:\\neurokey_knowledge, .git/.venv, .env/credentials.json/token.json va h.k.
    sezgir narsalar hech qachon qamrovga kirmaydi/natija bo'lolmaydi."""
    query = (query or "").strip().lower()
    if not query:
        return []
    candidates = []
    for root in SAFE_SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in _EXCLUDED_DIR_NAMES and not d.startswith(".")
            ]
            for name in filenames:
                if query in name.lower():
                    full = os.path.join(dirpath, name)
                    if _is_safe_search_result(full):
                        candidates.append(full)
            if len(candidates) >= max_results * 8:
                break
        if len(candidates) >= max_results * 8:
            break

    def _score(p):
        name = os.path.basename(p).lower()
        stem = os.path.splitext(name)[0]
        exact = 0 if (name == query or stem == query) else 1
        try:
            recency = -os.path.getmtime(p)
        except OSError:
            recency = 0
        return (exact, recency)

    candidates.sort(key=_score)
    return candidates[:max_results]


def _capture_screenshot() -> Optional[str]:
    """screen_vision.grab_screen() orqali (mavjud, markazlashgan ekran-olish
    motori) joriy ekranni oladi va vaqtinchalik PNG faylga saqlaydi."""
    try:
        import screen_vision as sv

        img = sv.grab_screen()
        if img is None:
            return None
        fd, path = tempfile.mkstemp(suffix=".png", prefix="nk_tg_screenshot_")
        os.close(fd)
        img.save(path, "PNG")
        return path
    except Exception:
        traceback.print_exc()
        return None


def _capture_screenshot_b64() -> Optional[str]:
    """_capture_screenshot() bilan bir xil, lekin veb-sahifa (JSON javob)
    uchun base64 satr sifatida qaytaradi — vaqtinchalik faylni o'zi tozalaydi
    (Telegram yo'lidagi kabi 'faylni yubor -> keyin o'chir' emas, chunki bu
    yerda HTTP javobiga to'g'ridan-to'g'ri qo'shiladi)."""
    path = _capture_screenshot()
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return base64.b64encode(raw).decode("ascii")
    except Exception:
        traceback.print_exc()
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ── Tabiiy tilda niyatni aniqlash (uz/ru/en) — faqat Telegram ko'prigiga xos ──
_SCREENSHOT_TRIGGERS = (
    "skrinshot", "screenshot", "скриншот", "ekran rasmi", "ekranni korsat",
    "ekranni ko'rsat", "show screen", "show me the screen", "show my screen",
    "покажи экран", "экран покажи", "send screenshot", "send a screenshot",
)

_FILE_REQUEST_TRIGGERS = (
    "faylni yubor", "fayl yubor", "faylni top", "kerakli faylni top",
    "fayl top", "faylni qidir", "fayl qidir", "faylni izla",
    "find file", "find the file", "search file", "search for file",
    "send file", "send the file", "send me the file", "send me file",
    "найди файл", "найти файл", "отправь файл", "пришли файл",
    "поиск файл", "ищи файл", "поищи файл",
)

_STOP_WORDS_RE = re.compile(
    r"\b(iltimos|please|пожалуйста|menga|мне)\b",
    re.IGNORECASE,
)


def _is_screenshot_request(text: str) -> bool:
    low = (text or "").lower()
    return any(t in low for t in _SCREENSHOT_TRIGGERS)


def _extract_file_query(text: str) -> Optional[str]:
    """Fayl-so'rov iborasi topilsa — undan qolgan qismini (taxminiy fayl nomi/
    tavsifi) qaytaradi. Iborasi yo'q bo'lsa None (bu fayl so'rovi emas)."""
    low = (text or "").lower()
    matched = None
    for t in _FILE_REQUEST_TRIGGERS:
        if t in low:
            matched = t
            break
    if matched is None:
        return None
    idx = low.find(matched)
    remainder = (text[:idx] + " " + text[idx + len(matched):]).strip()
    remainder = _STOP_WORDS_RE.sub(" ", remainder)
    remainder = remainder.strip(" .,:;\"'-")
    return remainder


# ─────────────────────────────────────────────────────────────────────────
# 4) JONLI OVOZ — telefon brauzeridan to'g'ridan-to'g'ri gaplashish (LAN, HTTPS)
# ─────────────────────────────────────────────────────────────────────────
# Nega Telegram ovozli xabar (yuqoridagi _process_voice) "jonli suhbat" EMAS:
# Telegram xabar-asosli — yozib, yuborib, kutib, faylni qabul qilish kerak.
# Chinakam "gaplashish" uchun bu yerda telefon brauzerida ochiladigan mahalliy
# veb-sahifa qo'shildi: mikrofonga gapirasiz -> jim qolganingizni sahifa o'zi
# aniqlaydi (VAD) -> avtomatik yuboradi -> STT->handle_text()->TTS xuddi shu
# quyoridagi _generate_reply()/_synthesize_voice_reply() orqali (KOD
# TAKRORLANMAYDI) -> javob ovozi avtomatik ijro etiladi. Bu YARIM-duplex
# (navbat bilan gaplashish — "walkie-talkie"/telefon suhbati kabi: siz
# gapirasiz -> u javob beradi -> siz yana gapirasiz), TO'LIQ bir vaqtda
# gaplashadigan (ikkalasi bir vaqtda eshitadi/gapiradi) tizim EMAS — bunga
# STT/TTS dvigatellari (Whisper/Edge, oqim emas, butun jumla kerak) tabiatan
# mos emas. "Avto-tsikl" yoqilsa, javob tugagach sahifa o'zi qayta tinglashni
# boshlaydi — qo'lda bosish shart emas, deyarli uzluksiz suhbat hissi beradi.
#
# Telefon brauzerlari (Chrome/Safari) mikrofonni FAQAT "xavfsiz kontekst"da
# beradi: https:// yoki localhost. LAN IP orqali oddiy http:// ishlamaydi —
# shuning uchun bu yerda mahalliy (self-signed, faqat shu PC uchun) HTTPS
# sertifikat avtomatik yaratiladi (openssl orqali). Brauzer birinchi marta
# "xavfsiz emas" ogohlantirishi ko'rsatadi — bu KUTILGAN (chunki sertifikat
# hech qanday tashqi organ tomonidan tasdiqlanmagan, faqat shu PC o'zi
# yaratgan) — "Advanced -> Proceed" bosilishi SHART, aks holda mikrofon
# ishlamaydi.
# ─────────────────────────────────────────────────────────────────────────
import base64  # noqa: E402


def _lan_ip() -> str:
    """Shu PC ning WiFi/LAN IP manzilini topadi (haqiqiy paket yubormaydi —
    faqat OS marshrutlash jadvalidan qaysi interfeys ishlatilishini so'raydi)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        try:
            import socket as _sk
            return _sk.gethostbyname(_sk.gethostname())
        except Exception:
            return "127.0.0.1"


def _ensure_web_voice_cert(cert_dir: str):
    """Self-signed HTTPS sertifikat (bir marta yaratiladi, keyingi safar qayta
    ishlatiladi). openssl.exe kerak (Git for Windows bilan odatda birga keladi).
    Muvaffaqiyatsiz bo'lsa None qaytaradi — chaqiruvchi shunda HTTP ga tushadi
    (faqat shu PC dan http://127.0.0.1 orqali ishlaydi, telefondan emas)."""
    import shutil as _shutil
    try:
        os.makedirs(cert_dir, exist_ok=True)
        cert_path = os.path.join(cert_dir, "webvoice_cert.pem")
        key_path = os.path.join(cert_dir, "webvoice_key.pem")
        if os.path.isfile(cert_path) and os.path.isfile(key_path):
            return cert_path, key_path

        openssl = _shutil.which("openssl") or "openssl"
        ip = _lan_ip()
        san = f"subjectAltName=DNS:localhost,IP:127.0.0.1,IP:{ip}"
        cmd = [
            openssl, "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_path, "-out", cert_path,
            "-days", "3650", "-nodes",
            "-subj", "/CN=neurokey-local",
            "-addext", san,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
        if r.returncode != 0 or not (os.path.isfile(cert_path) and os.path.isfile(key_path)):
            print("[BRIDGE][WEB-VOICE] Sertifikat yaratilmadi (openssl xatosi):",
                  (r.stderr or "")[:300], flush=True)
            return None
        print("[BRIDGE][WEB-VOICE] Yangi mahalliy HTTPS sertifikat yaratildi "
              f"({cert_dir}).", flush=True)
        return cert_path, key_path
    except FileNotFoundError:
        print("[BRIDGE][WEB-VOICE] openssl topilmadi — HTTPS sertifikat "
              "yaratib bo'lmadi (HTTP bilan davom etiladi, faqat shu PC dan "
              "ishlaydi).", flush=True)
        return None
    except Exception as e:
        print("[BRIDGE][WEB-VOICE] Sertifikat xatosi:", repr(e), flush=True)
        return None


def _try_open_firewall_port(port: int) -> None:
    """Windows Firewall'da inbound qoida qo'shishga urinadi (best-effort —
    administrator huquqi bo'lmasa jim o'tkazib yuboriladi, faqat xabar
    chiqariladi)."""
    try:
        rule_name = f"NeuroKey Web Voice {port}"
        check = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
            capture_output=True, timeout=10, text=True,
        )
        if check.returncode == 0 and "No rules match" not in (check.stdout or ""):
            return  # qoida allaqachon bor
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={rule_name}", "dir=in", "action=allow", "protocol=TCP",
             f"localport={port}"],
            capture_output=True, timeout=10, text=True,
        )
        if r.returncode == 0:
            print(f"[BRIDGE][WEB-VOICE] Windows Firewall qoidasi qo'shildi (port {port}).", flush=True)
        else:
            print(f"[BRIDGE][WEB-VOICE] OGOHLANTIRISH: Firewall qoidasini avtomatik "
                  f"qo'sha olmadim (administrator huquqi kerak bo'lishi mumkin). "
                  f"Agar telefon ulanmasa: Windows Defender Firewall -> Advanced "
                  f"settings -> Inbound Rules -> New Rule -> Port {port} TCP -> Allow.",
                  flush=True)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# 3b) PWA (Progressive Web App) — "haqiqiy ilova" hissi: telefon bosh ekraniga
#     ikonka sifatida o'rnatiladi, to'liq ekranda ochiladi (brauzer manzil
#     satrisiz), tarmoq sekin bo'lsa ham sahifa qobig'i darhol yuklanadi.
#
#     MUHIM (halollik uchun): bu HAQIQIY App Store/Play Store ilova EMAS —
#     Swift/Kotlin bilan tuzilgan native ilova emas. Bu "Progressive Web App"
#     — veb-texnologiya, lekin telefon uni "Bosh ekranga qo'shish" orqali xuddi
#     oddiy ilovadek ko'rsatadi: alohida ikonka, to'liq ekran, manzil satrisiz.
#     Kod ichida "native app" yoki "App Store" degan da'vo YO'Q va bo'lmasligi
#     kerak — README/hisobotlarda ham shu farq aniq ko'rsatilishi shart.
#
#     - manifest.json: nom, ikonkalar (logo/neurokey_logo_*.png dan olingan —
#       haqiqiy NeuroKey logotipi, generic placeholder EMAS), display:standalone.
#     - sw.js: faqat sahifa "qobig'i"ni (HTML/manifest/ikonkalar) keshlaydi —
#       /api/talk (haqiqiy AI so'rovi) HECH QACHON keshlanmaydi/oflayn ishlamaydi,
#       faqat sahifaning o'zi tezroq/ishonchliroq yuklanishi uchun.
#     - Android Chrome: manifest.json + display:standalone yetarli.
#     - iOS Safari: alohida apple-mobile-web-app-* meta teglar + apple-touch-icon
#       kerak (Apple manifest.json ni to'liq qo'llab-quvvatlamaydi).
# ─────────────────────────────────────────────────────────────────────────
_PWA_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pwa_icons")
_PWA_ICON_FILES = {
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "icon-192-maskable.png": "image/png",
    "icon-512-maskable.png": "image/png",
    "apple-touch-icon.png": "image/png",
}

_PWA_THEME_COLOR = "#0a121c"   # sahifaning o'zi bilan bir xil to'q-ko'k fon
_PWA_BG_COLOR = "#060a10"

_PWA_MANIFEST_JSON = """{
  "name": "NeuroKey",
  "short_name": "NeuroKey",
  "description": "NeuroKey — jonli ovozli AI yordamchi",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "%(bg)s",
  "theme_color": "%(theme)s",
  "lang": "uz",
  "icons": [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    {"src": "/icons/icon-192-maskable.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
    {"src": "/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
""" % {"bg": _PWA_BG_COLOR, "theme": _PWA_THEME_COLOR}

_PWA_SERVICE_WORKER_JS = """// NeuroKey web-voice — offline "shell" keshi.
// FAQAT sahifa qobig'ini (HTML/manifest/ikonkalar) keshlaydi — /api/talk
// (haqiqiy AI javobi) hech qachon ushlanmaydi/keshlanmaydi, hamisha jonli
// tarmoq orqali ishlaydi (AI javobining o'zi oflayn ishlamaydi, faqat
// sahifaning o'zi tezroq va ishonchliroq ochiladi).
var CACHE_NAME = 'neurokey-shell-v1';
var SHELL_FILES = [
  '/',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/apple-touch-icon.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(SHELL_FILES);
    }).catch(function () { /* birinchi ishga tushishda tarmoq yo'q bo'lsa ham qulamasin */ })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE_NAME; }).map(function (k) {
        return caches.delete(k);
      }));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;               // /api/talk POST — hech qachon ushlanmaydi
  var url = new URL(req.url);
  if (url.pathname === '/api/talk') return;        // qo'shimcha xavfsizlik: aniq chetlab o'tish
  if (url.origin !== self.location.origin) return; // faqat o'z serverimiz (masalan kelajakdagi bulut manzili emas)
  event.respondWith(
    caches.match(req).then(function (cached) {
      var network = fetch(req).then(function (resp) {
        if (resp && resp.status === 200) {
          var clone = resp.clone();
          caches.open(CACHE_NAME).then(function (cache) { cache.put(req, clone); });
        }
        return resp;
      }).catch(function () { return cached; });
      return cached || network;
    })
  );
});
"""


async def _web_manifest(request):
    from aiohttp import web as _web
    return _web.Response(text=_PWA_MANIFEST_JSON, content_type="application/manifest+json", charset="utf-8")


async def _web_service_worker(request):
    from aiohttp import web as _web
    resp = _web.Response(text=_PWA_SERVICE_WORKER_JS, content_type="application/javascript", charset="utf-8")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


async def _web_icon(request):
    from aiohttp import web as _web
    name = request.match_info.get("name", "")
    mime = _PWA_ICON_FILES.get(name)
    if not mime:
        return _web.Response(status=404, text="Topilmadi")
    path = os.path.join(_PWA_ICON_DIR, name)
    if not os.path.isfile(path):
        return _web.Response(status=404, text="Ikonka fayli topilmadi")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception as e:
        return _web.Response(status=500, text=f"Xato: {e}")
    return _web.Response(body=data, content_type=mime)


_WEB_VOICE_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<title>NeuroKey — Jonli ovoz</title>
<meta name="description" content="NeuroKey — jonli ovozli AI yordamchi">

<!-- PWA: manifest (Android Chrome "Add to Home screen" / "Install app" shu orqali ishlaydi) -->
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0a121c">

<!-- PWA: Android Chrome standalone rejimi -->
<meta name="mobile-web-app-capable" content="yes">

<!-- PWA: iOS Safari — Apple manifest.json ni to'liq qo'llamaydi, alohida teglar kerak -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="NeuroKey">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="/icons/icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="/icons/icon-512.png">

<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body {
    margin: 0; padding: 0; height: 100%;
    background: radial-gradient(ellipse at top, #14202e 0%, #060a10 70%);
    color: #e7eef7; font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    overscroll-behavior: none; user-select: none;
  }
  .wrap { min-height: 100%; display: flex; flex-direction: column; align-items: center;
          justify-content: space-between; padding: 24px 16px 32px; }
  h1 { font-size: 18px; font-weight: 600; color: #8ec6ff; margin: 8px 0 0; letter-spacing: .3px; }
  .sub { font-size: 12.5px; color: #7387a1; margin-top: 4px; text-align: center; }
  .stage { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 22px; width: 100%; }
  #status { font-size: 15px; color: #a9c3de; min-height: 20px; text-align: center; }
  #micBtn {
    width: 148px; height: 148px; border-radius: 50%; border: none; cursor: pointer;
    background: radial-gradient(circle at 35% 30%, #2f6fed, #163a8a);
    box-shadow: 0 0 0 0 rgba(63,120,255,.55);
    display: flex; align-items: center; justify-content: center;
    transition: transform .12s ease, box-shadow .3s ease, background .3s ease;
    touch-action: manipulation;
  }
  #micBtn:active { transform: scale(0.96); }
  #micBtn.listening {
    background: radial-gradient(circle at 35% 30%, #ff5b5b, #8a1616);
    animation: pulse 1.1s ease-out infinite;
  }
  #micBtn.sending { background: radial-gradient(circle at 35% 30%, #d99a25, #7a4e05); }
  #micBtn.speaking { background: radial-gradient(circle at 35% 30%, #35c46a, #0f5c2c); }
  #micBtn svg { width: 58px; height: 58px; fill: #eaf2ff; }
  @keyframes pulse {
    0%   { box-shadow: 0 0 0 0 rgba(255,90,90,.55); }
    70%  { box-shadow: 0 0 0 26px rgba(255,90,90,0); }
    100% { box-shadow: 0 0 0 0 rgba(255,90,90,0); }
  }
  .autorow { display: flex; align-items: center; gap: 8px; font-size: 13.5px; color: #9db3cc; }
  .autorow input { width: 18px; height: 18px; }
  #log { width: 100%; max-width: 480px; max-height: 34vh; overflow-y: auto;
         font-size: 13.5px; line-height: 1.5; border-radius: 12px;
         background: rgba(255,255,255,.04); padding: 10px 14px; }
  #log .u { color: #8ec6ff; }
  #log .a { color: #9be79b; }
  #log .e { color: #ff8a8a; }
  #log p { margin: 4px 0; }
  .hint { font-size: 11.5px; color: #5c7290; text-align: center; max-width: 320px; margin-top: 6px; }
  audio { display: none; }
  #shotWrap { display: none; width: 100%; max-width: 480px; margin-top: 10px; }
  #shotWrap img { width: 100%; border-radius: 10px; border: 1px solid rgba(255,255,255,.08); }
  #gearBtn {
    position: fixed; top: max(10px, env(safe-area-inset-top)); right: 12px; z-index: 20;
    width: 34px; height: 34px; border-radius: 50%; border: none;
    background: rgba(255,255,255,.08); color: #9db3cc; font-size: 16px;
    display: flex; align-items: center; justify-content: center; cursor: pointer;
  }
  #settingsModal {
    display: none; position: fixed; inset: 0; z-index: 30;
    background: rgba(3,6,10,.72); align-items: center; justify-content: center; padding: 20px;
  }
  #settingsModal .box {
    background: #0f1a28; border: 1px solid rgba(255,255,255,.08); border-radius: 14px;
    padding: 18px; width: 100%; max-width: 360px;
  }
  #settingsModal h2 { font-size: 15px; margin: 0 0 6px; color: #8ec6ff; }
  #settingsModal p { font-size: 12px; color: #7387a1; margin: 0 0 12px; line-height: 1.5; }
  #settingsModal input {
    width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,.12);
    background: #08101a; color: #e7eef7; font-size: 14px; margin-bottom: 12px;
  }
  #settingsModal .row { display: flex; gap: 8px; }
  #settingsModal button.act {
    flex: 1; padding: 10px; border-radius: 8px; border: none; font-size: 13.5px; cursor: pointer;
  }
  #settingsModal .save { background: #2f6fed; color: #fff; }
  #settingsModal .reset { background: rgba(255,255,255,.08); color: #cdd8e6; }
  #settingsModal .cur { font-size: 11px; color: #5c7290; margin-top: 10px; word-break: break-all; }
</style>
</head>
<body>
<button id="gearBtn" aria-label="Sozlamalar">&#9881;</button>
<div id="settingsModal">
  <div class="box">
    <h2>Server manzili</h2>
    <p>Bo'sh qoldiring — shu qurilma/WiFi orqali mahalliy PC ishlatiladi (odatiy holat).
       Kelajakda bulut server (masalan Hetzner) sozlansa, shu yerga uning manzilini
       kiriting (masalan: https://1.2.3.4:8765).</p>
    <input id="serverInput" type="text" placeholder="https://server-manzili:port" autocapitalize="off" autocorrect="off" spellcheck="false">
    <div class="row">
      <button class="act save" id="saveServerBtn">Saqlash</button>
      <button class="act reset" id="resetServerBtn">Mahalliyga qaytarish</button>
    </div>
    <div class="cur" id="curServerInfo"></div>
  </div>
</div>
<div class="wrap">
  <div>
    <h1>NeuroKey — Jonli ovoz</h1>
    <div class="sub">Tugmani bosing, gapiring — jim qolsangiz o'zi yuboradi</div>
  </div>
  <div class="stage">
    <div id="status">Tayyor</div>
    <button id="micBtn" aria-label="Gaplashish">
      <svg viewBox="0 0 24 24"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z"/><path d="M19 11a7 7 0 0 1-14 0H3a9 9 0 0 0 8 8.94V23h2v-3.06A9 9 0 0 0 21 11h-2z"/></svg>
    </button>
    <label class="autorow"><input type="checkbox" id="autoLoop"> Avtomatik davom ettirish (navbat bilan)</label>
    <div class="hint">Ushlab turish shart emas — bir marta bosing, gapiring, tugatgach avtomatik yuboriladi. Majburiy tugatish uchun tugmani yana bosing.</div>
  </div>
  <div id="shotWrap"><img id="shotImg" alt="Skrinshot"></div>
  <div id="log"></div>
</div>
<audio id="player"></audio>
<script>
(function(){
  var micBtn = document.getElementById('micBtn');
  var statusEl = document.getElementById('status');
  var logEl = document.getElementById('log');
  var autoLoopEl = document.getElementById('autoLoop');
  var player = document.getElementById('player');
  var shotWrap = document.getElementById('shotWrap');
  var shotImg = document.getElementById('shotImg');

  // ── Server manzili sozlamasi (kelajakda mahalliy WiFi -> bulut server) ──
  // Bo'sh bo'lsa — joriy sahifa manzili ishlatiladi (odatiy, hozirgi xatti-harakat).
  // To'ldirilsa (masalan https://1.2.3.4:8765) — /api/talk shu manzilga yuboriladi.
  var SERVER_KEY = 'nk_server_base';
  function getBase(){
    try { return (localStorage.getItem(SERVER_KEY) || '').trim().replace(/\/+$/, ''); }
    catch (e) { return ''; }
  }
  function setBase(v){
    try {
      v = (v || '').trim().replace(/\/+$/, '');
      if (v) localStorage.setItem(SERVER_KEY, v); else localStorage.removeItem(SERVER_KEY);
    } catch (e) {}
  }
  function apiUrl(path){
    var base = getBase();
    return base ? (base + path) : path;
  }

  var gearBtn = document.getElementById('gearBtn');
  var settingsModal = document.getElementById('settingsModal');
  var serverInput = document.getElementById('serverInput');
  var curServerInfo = document.getElementById('curServerInfo');
  function refreshCurInfo(){
    var b = getBase();
    curServerInfo.textContent = b ? ('Hozirgi: ' + b) : ('Hozirgi: mahalliy (' + window.location.origin + ')');
  }
  gearBtn.addEventListener('click', function(){
    serverInput.value = getBase();
    refreshCurInfo();
    settingsModal.style.display = 'flex';
  });
  settingsModal.addEventListener('click', function(e){
    if (e.target === settingsModal) settingsModal.style.display = 'none';
  });
  document.getElementById('saveServerBtn').addEventListener('click', function(){
    setBase(serverInput.value);
    refreshCurInfo();
    settingsModal.style.display = 'none';
  });
  document.getElementById('resetServerBtn').addEventListener('click', function(){
    setBase('');
    serverInput.value = '';
    refreshCurInfo();
    settingsModal.style.display = 'none';
  });

  // ── PWA service worker — sahifa "qobig'i"ni keshlaydi (AI javobining o'zi
  // oflayn ishlamaydi, faqat sahifa tezroq/ishonchliroq ochilishi uchun) ──
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function(){
      navigator.serviceWorker.register('/sw.js').catch(function(e){
        console.warn('SW registration failed:', e);
      });
    });
  }

  var micStream = null, audioCtx = null, analyser = null, dataArray = null;
  var recorder = null, chunks = [];
  var speaking = false, speechStartTime = 0, silenceTimer = null, recordStartTs = 0;
  var rafId = null;
  var busy = false;

  var SPEECH_RMS = 0.018;
  var SILENCE_MS = 1100;
  var MIN_SPEECH_MS = 350;
  var MAX_RECORD_MS = 25000;

  function setStatus(mode, text){
    micBtn.className = mode;
    statusEl.textContent = text;
  }
  function log(cls, text){
    var p = document.createElement('p');
    p.className = cls;
    p.textContent = text;
    logEl.appendChild(p);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function pickMime(){
    var cands = ['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/webm','audio/mp4'];
    for (var i=0;i<cands.length;i++){
      if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(cands[i])) return cands[i];
    }
    return '';
  }

  async function initMic(){
    if (micStream) return true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
      setStatus('idle', 'Mikrofon mavjud emas (HTTPS orqali oching, sertifikat ogohlantirishini qabul qiling)');
      return false;
    }
    try {
      micStream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation:true, noiseSuppression:true, autoGainControl:true}});
    } catch (e) {
      setStatus('idle', 'Mikrofonga ruxsat berilmadi: ' + e.message);
      return false;
    }
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    var src = audioCtx.createMediaStreamSource(micStream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    src.connect(analyser);
    dataArray = new Uint8Array(analyser.fftSize);
    return true;
  }

  function rmsLevel(){
    analyser.getByteTimeDomainData(dataArray);
    var sum = 0;
    for (var i=0;i<dataArray.length;i++){
      var v = (dataArray[i]-128)/128;
      sum += v*v;
    }
    return Math.sqrt(sum/dataArray.length);
  }

  function vadLoop(){
    if (!recorder || recorder.state !== 'recording') return;
    var level = rmsLevel();
    var now = Date.now();
    if (level > SPEECH_RMS){
      if (!speaking){ speaking = true; speechStartTime = now; }
      if (silenceTimer){ clearTimeout(silenceTimer); silenceTimer = null; }
    } else if (speaking && !silenceTimer){
      silenceTimer = setTimeout(function(){
        if (Date.now() - speechStartTime >= MIN_SPEECH_MS) stopTurn();
      }, SILENCE_MS);
    }
    if (now - recordStartTs >= MAX_RECORD_MS){ stopTurn(); return; }
    rafId = requestAnimationFrame(vadLoop);
  }

  async function startTurn(){
    if (busy) return;
    var ok = await initMic();
    if (!ok) return;
    chunks = [];
    speaking = false; speechStartTime = 0;
    if (silenceTimer){ clearTimeout(silenceTimer); silenceTimer = null; }
    var mime = pickMime();
    try {
      recorder = mime ? new MediaRecorder(micStream, {mimeType: mime}) : new MediaRecorder(micStream);
    } catch (e) {
      setStatus('idle', 'Yozib olishni boshlab bo\\'lmadi: ' + e.message);
      return;
    }
    recorder.ondataavailable = function(e){ if (e.data && e.data.size > 0) chunks.push(e.data); };
    recorder.onstop = onRecStop;
    recorder.start();
    recordStartTs = Date.now();
    setStatus('listening', 'Tinglayapman... (gapiring, tugagach jim qoling)');
    vadLoop();
  }

  function stopTurn(){
    if (rafId){ cancelAnimationFrame(rafId); rafId = null; }
    if (silenceTimer){ clearTimeout(silenceTimer); silenceTimer = null; }
    if (recorder && recorder.state === 'recording') recorder.stop();
  }

  async function onRecStop(){
    var mimeType = (chunks[0] && chunks[0].type) || 'audio/webm';
    var blob = new Blob(chunks, {type: mimeType});
    if (blob.size < 900){
      setStatus('idle', 'Tayyor');
      return;
    }
    busy = true;
    setStatus('sending', 'NeuroKey o\\'ylayapti...');
    try {
      var resp = await fetch(apiUrl('/api/talk'), {method: 'POST', body: blob, headers: {'Content-Type': mimeType}});
      var data = await resp.json();
      if (!data.ok){
        log('e', 'Xato: ' + (data.error || 'nomalum xato'));
        setStatus('idle', 'Tayyor');
        busy = false;
        maybeLoop();
        return;
      }
      if (data.user_text) log('u', 'Siz: ' + data.user_text);
      if (data.reply_text) log('a', 'NeuroKey: ' + data.reply_text);
      if (data.image_b64){
        shotImg.src = 'data:' + (data.image_mime || 'image/png') + ';base64,' + data.image_b64;
        shotWrap.style.display = 'block';
      } else {
        shotWrap.style.display = 'none';
      }
      if (data.audio_b64){
        player.src = 'data:' + (data.audio_mime || 'audio/ogg') + ';base64,' + data.audio_b64;
        setStatus('speaking', 'Javob berayapti...');
        player.onended = function(){ setStatus('idle', 'Tayyor'); busy = false; maybeLoop(); };
        player.play().catch(function(){ setStatus('idle', 'Tayyor'); busy = false; maybeLoop(); });
      } else {
        setStatus('idle', 'Tayyor (ovoz sintez qilinmadi)');
        busy = false;
        maybeLoop();
      }
    } catch (e) {
      log('e', 'Tarmoq xatosi: ' + e.message);
      setStatus('idle', 'Tayyor');
      busy = false;
      maybeLoop();
    }
  }

  function maybeLoop(){
    if (autoLoopEl.checked){
      setTimeout(function(){ if (autoLoopEl.checked && !busy) startTurn(); }, 450);
    }
  }

  micBtn.addEventListener('click', function(){
    if (recorder && recorder.state === 'recording'){
      stopTurn();
    } else if (!busy) {
      startTurn();
    }
  });
})();
</script>
</body>
</html>
"""


async def _web_index(request):
    from aiohttp import web as _web
    return _web.Response(text=_WEB_VOICE_HTML, content_type="text/html", charset="utf-8")


async def _web_talk(request):
    from aiohttp import web as _web
    try:
        data = await request.read()
    except Exception as e:
        return _web.json_response({"ok": False, "error": f"So'rovni o'qib bo'lmadi: {e}"}, status=400)
    if not data:
        return _web.json_response({"ok": False, "error": "Bo'sh audio keldi."}, status=400)

    loop = asyncio.get_event_loop()
    async with _proc_lock:
        try:
            pcm16, sr = await loop.run_in_executor(None, _decode_audio_bytes, data)
        except Exception as e:
            print("[BRIDGE][WEB-VOICE] Dekod xato:", repr(e), flush=True)
            return _web.json_response({"ok": False, "error": "Audio formatini o'qiy olmadim."}, status=200)
        if pcm16 is None:
            return _web.json_response({"ok": False, "error": "Audio bo'sh yoki noto'g'ri format."}, status=200)

        # "Tinglash paytida o'ylash" (Stivers va boshq. 2009, PNAS): odam gap
        # tugashini kutmaydi, javobni gap DAVOMIDA tayyorlay boshlaydi. Bu
        # yerda aynan shu bosqich — endi audio yozib olindi (foydalanuvchi
        # gapirib bo'ldi), lekin STT (transkripsiya, tarmoq so'rovi, odatda
        # 1-3s) hali BOSHLANMAGAN. consciousness_orchestrator.get_full_context()
        # dagi ~21 ta qatlam SO'ROV MATNIGA umuman bog'liq emas (theory_of_mind,
        # narrative_self, global_workspace, embodied_grounding va h.k. — ular
        # foydalanuvchi ANIQ nima deganidan qat'iy nazar bir xil natija
        # beradi). Shularni STT bilan BIR VAQTDA, alohida threadda hisoblab
        # qo'yamiz — STT tugab, matn tayyor bo'lganda ular allaqachon keshda
        # turadi va get_full_context() qayta hisoblamaydi (_indep(), qarang
        # consciousness_orchestrator.py). Fire-and-forget: natijani KUTMAYMIZ —
        # agar STT prewarmdan tezroq tugasa, get_full_context() qolgan
        # qatlamlarni oddiy (eski) yo'l bilan o'zi hisoblaydi, hech narsa
        # buzilmaydi, faqat bu safar tezlashish kam bo'ladi.
        _prewarm_t0 = time.perf_counter()

        def _run_prewarm():
            try:
                _dt = _co.prewarm_independent_context()
                print(f"[BRIDGE][WEB-VOICE][TIMING] prewarm_independent_context="
                      f"{_dt*1000:.0f}ms (STT bilan bir vaqtda, fon threadida)", flush=True)
            except Exception as _e:
                print(f"[BRIDGE][WEB-VOICE] prewarm xato (e'tiborsiz qoldiriladi): {_e!r}", flush=True)

        threading.Thread(target=_run_prewarm, daemon=True, name="NK-TurnPrewarm").start()

        text = await loop.run_in_executor(None, whisper_transcribe_int16, pcm16, sr)
        print(f"[BRIDGE][WEB-VOICE][TIMING] stt={(time.perf_counter()-_prewarm_t0)*1000:.0f}ms "
              f"(prewarm shu vaqt ichida fonda ishladi)", flush=True)
        text = (text or "").strip()
        if not text:
            return _web.json_response(
                {"ok": False, "error": "Gapingizni tushunmadim, yana urinib ko'ring."}, status=200
            )

        print(f"[BRIDGE][WEB-VOICE] Ovozdan matn: {text[:100]!r}", flush=True)

        # Skrinshot so'rovi — Telegram yo'lidagi _route_text bilan BIR XIL
        # niyat-aniqlash (_is_screenshot_request), lekin bu yerda natija
        # event.reply/send_file EMAS — to'g'ridan-to'g'ri JSON javobga
        # base64 rasm sifatida qo'shiladi (veb-sahifa buni <img> qilib
        # ko'rsatadi). LLM chaqirilmaydi — Telegram yo'lidagi kabi tez va
        # bepul (token sarflanmaydi).
        image_b64 = ""
        image_mime = ""
        if _is_screenshot_request(text):
            print("[BRIDGE][WEB-VOICE] Skrinshot so'raldi.", flush=True)
            image_b64 = await loop.run_in_executor(None, _capture_screenshot_b64)
            image_b64 = image_b64 or ""
            if image_b64:
                image_mime = "image/png"
                reply = ("Mana, ekranning joriy skrinshoti."
                         if os.getenv("NEUROKEY_UI_LANG", "uz") == "uz"
                         else "Here is the current screenshot.")
            else:
                reply = ("Kechirasiz, skrinshot olishda xato bo'ldi."
                         if os.getenv("NEUROKEY_UI_LANG", "uz") == "uz"
                         else "Sorry, I couldn't capture the screen.")
        else:
            t0 = time.time()
            reply = await loop.run_in_executor(None, _generate_reply, text)
            print(f"[BRIDGE][WEB-VOICE] Javob tayyor ({time.time() - t0:.1f}s): {reply[:100]!r}", flush=True)

        voice_path = await loop.run_in_executor(None, _synthesize_voice_reply, reply)

    audio_b64 = ""
    audio_mime = ""
    if voice_path:
        try:
            with open(voice_path, "rb") as f:
                raw = f.read()
            audio_b64 = base64.b64encode(raw).decode("ascii")
            audio_mime = "audio/ogg" if voice_path.endswith(".ogg") else "audio/wav"
        except Exception as e:
            print("[BRIDGE][WEB-VOICE] Javob audio faylini o'qishda xato:", repr(e), flush=True)
        finally:
            try:
                os.remove(voice_path)
            except OSError:
                pass
    else:
        print("[BRIDGE][WEB-VOICE] Ovozli javob sintez qilinmadi — faqat matn qaytariladi.", flush=True)

    return _web.json_response({
        "ok": True,
        "user_text": text,
        "reply_text": reply,
        "audio_b64": audio_b64,
        "audio_mime": audio_mime,
        "image_b64": image_b64,
        "image_mime": image_mime,
    })


async def _start_web_voice_server():
    enabled = (os.getenv("NEUROKEY_WEB_VOICE_ENABLED", "1") or "1").strip().lower() not in ("0", "false", "no")
    if not enabled:
        print("[BRIDGE][WEB-VOICE] O'chirilgan (NEUROKEY_WEB_VOICE_ENABLED=0).", flush=True)
        return
    try:
        from aiohttp import web as _web
    except Exception as e:
        print("[BRIDGE][WEB-VOICE] aiohttp topilmadi — jonli ovoz sahifasi ishga tushmaydi:", repr(e), flush=True)
        return

    port = int(os.getenv("NEUROKEY_WEB_VOICE_PORT", "8765") or "8765")
    cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "web_voice_certs")
    cert_info = _ensure_web_voice_cert(cert_dir)

    app = _web.Application(client_max_size=20 * 1024 * 1024)
    app.router.add_get("/", _web_index)
    app.router.add_post("/api/talk", _web_talk)
    app.router.add_get("/manifest.json", _web_manifest)
    app.router.add_get("/sw.js", _web_service_worker)
    app.router.add_get("/icons/{name}", _web_icon)

    runner = _web.AppRunner(app)
    await runner.setup()

    ip = _lan_ip()
    ssl_ctx = None
    scheme = "http"
    if cert_info:
        try:
            import ssl as _ssl
            ssl_ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(cert_info[0], cert_info[1])
            scheme = "https"
        except Exception as e:
            print("[BRIDGE][WEB-VOICE] SSL kontekst yaratilmadi, HTTP bilan davom etiladi:", repr(e), flush=True)
            ssl_ctx = None

    try:
        site = _web.TCPSite(runner, "0.0.0.0", port, ssl_context=ssl_ctx)
        await site.start()
    except Exception as e:
        print(f"[BRIDGE][WEB-VOICE] Port {port} da server ishga tushmadi:", repr(e), flush=True)
        return

    _try_open_firewall_port(port)

    print("=" * 70, flush=True)
    print(" JONLI OVOZ (telefon brauzeri) TAYYOR:", flush=True)
    print(f"   {scheme}://{ip}:{port}/   (telefon shu WiFi tarmog'ida bo'lishi kerak)", flush=True)
    if scheme == "https":
        print("   Birinchi ochganda brauzer 'Bog'lanish maxfiy emas' / 'Not secure'", flush=True)
        print("   ogohlantirishi chiqaradi — bu KUTILGAN (mahalliy o'z-sertifikat,", flush=True)
        print("   hech qanday tashqi kompaniya emas, faqat shu PC uni yaratdi).", flush=True)
        print("   'Advanced' / 'Kengaytirilgan' -> 'Proceed to ... (unsafe)' /", flush=True)
        print("   'Baribir davom etish' tugmasini bosish SHART — aks holda mikrofon", flush=True)
        print("   brauzerga ochilmaydi (bu Chrome/Safari ning xavfsizlik qoidasi).", flush=True)
    else:
        print("   OGOHLANTIRISH: HTTPS sertifikat yaratilmadi (openssl topilmadimi?)", flush=True)
        print(f"   — telefon http:// orqali mikrofonga ruxsat BERMAYDI. Faqat shu PC", flush=True)
        print(f"   dan http://127.0.0.1:{port} ishlaydi (test uchun).", flush=True)
    print("=" * 70, flush=True)


# ─────────────────────────────────────────────────────────────────────────
# 3) Telegram (Telethon) — o'z shaxsiy akkount sessiyasi orqali
# ─────────────────────────────────────────────────────────────────────────
async def main_async():
    api_id = getattr(C, "TELEGRAM_API_ID", None)
    api_hash = getattr(C, "TELEGRAM_API_HASH", None)
    phone = getattr(C, "TELEGRAM_PHONE", None) or None
    session_name = getattr(C, "TELEGRAM_SESSION_NAME", None) or "neurokey"

    if not api_id or not api_hash:
        print("[BRIDGE] XATO: TELEGRAM_API_ID / TELEGRAM_API_HASH .env da yo'q.", flush=True)
        return

    client = TelegramClient(session_name, int(api_id), str(api_hash))
    print("[BRIDGE] Telegramga ulanmoqda...", flush=True)
    await client.connect()
    if not await client.is_user_authorized():
        print("", flush=True)
        print("=" * 70, flush=True)
        print(" BIR MARTALIK SOZLASH: Telegram akkountingizga kirish kerak.", flush=True)
        print(" Hozir Telegram (yoki SMS) orqali telefoningizga tasdiqlash", flush=True)
        print(" kodi keladi. Shu oynaga o'sha kodni kiriting va Enter bosing.", flush=True)
        print(" (Bu faqat BIRINCHI marta kerak — keyingi safar so'ralmaydi.)", flush=True)
        print("=" * 70, flush=True)
        try:
            await client.start(phone=phone)
        except EOFError:
            print("", flush=True)
            print("[BRIDGE] XATO: Kod kiritish uchun interaktiv konsol kerak.", flush=True)
            print("[BRIDGE] Bu skriptni to'g'ridan-to'g'ri !NeuroKey_Telefon.bat orqali", flush=True)
            print("[BRIDGE] oching (fon jarayon sifatida emas) — u yerda kod so'raladi.", flush=True)
            return
    me = await client.get_me()
    print(f"[BRIDGE] Telegram ulandi. Akkaunt: {me.first_name or ''} (id bor).", flush=True)

    allowed_peer_env = (os.getenv("TELEGRAM_BRIDGE_ALLOWED_PEER", "") or "").strip()
    allowed_peer_id = int(allowed_peer_env) if allowed_peer_env.isdigit() else me.id

    if allowed_peer_id == me.id:
        print("[BRIDGE] Ruxsat etilgan chat: 'Saved Messages' (o'zingizga yozilgan xabarlar).", flush=True)
    else:
        print(f"[BRIDGE] Ruxsat etilgan chat: peer_id={allowed_peer_id} (.env TELEGRAM_BRIDGE_ALLOWED_PEER).", flush=True)
    print("[BRIDGE] Tayyor — telefoningizdan xabar yozishingiz mumkin.", flush=True)
    print("=" * 70, flush=True)

    @client.on(events.NewMessage())
    async def _handler(event):
        try:
            if not event.is_private:
                return
            if event.chat_id != allowed_peer_id:
                return  # begona/boshqa chat — e'tiborsiz, LLM chaqirilmaydi

            msg = event.message
            raw_text = (msg.message or "").strip()

            if raw_text.startswith(REPLY_MARKER):
                return  # bu bizning o'zimiz yuborgan javob — cheksiz tsikl oldi olinadi

            async with _proc_lock:
                if msg.voice or (msg.media and getattr(msg, "audio", None)):
                    await _process_voice(event)
                elif raw_text:
                    await _process_text(event, raw_text)
        except Exception:
            print("[BRIDGE] handler xato:", flush=True)
            traceback.print_exc()

    async def _handle_screenshot_request(event):
        print("[BRIDGE] Skrinshot so'raldi.", flush=True)
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, _capture_screenshot)
        if not path:
            await event.reply(REPLY_MARKER + "Skrinshot olishda xato bo'ldi (ekranni ololmadim).")
            return
        try:
            await client.send_file(event.chat_id, path, caption=REPLY_MARKER + "Skrinshot")
            print("[BRIDGE] Skrinshot yuborildi.", flush=True)
        except Exception as e:
            print("[BRIDGE] Skrinshot yuborishda xato:", repr(e), flush=True)
            await event.reply(REPLY_MARKER + f"Skrinshotni yuborolmadim: {e}")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    async def _handle_file_request(event, query: str):
        query = (query or "").strip()
        if not query:
            await event.reply(
                REPLY_MARKER
                + "Qaysi faylni qidirishim kerak? Nomini ayting, masalan: "
                  "“hisobot.pdf faylni top”."
            )
            return
        print(f"[BRIDGE] Fayl so'ralmoqda: {query!r}", flush=True)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _search_user_files, query)
        if not results:
            await event.reply(
                REPLY_MARKER
                + f"«{query}» bo'yicha Documents/Desktop/Downloads "
                  "papkalarida hech narsa topilmadi."
            )
            return

        best = results[0]
        others = results[1:]
        size = 0
        try:
            size = os.path.getsize(best)
        except OSError:
            pass
        if size > _MAX_SEND_BYTES:
            await event.reply(
                REPLY_MARKER
                + f"Topdim, lekin fayl juda katta ({size / 1024 / 1024:.0f}MB): {best}\n"
                  "Telefon orqali yuborish uchun juda og'ir — PCdan qo'lda yuboring."
            )
            return

        caption = os.path.basename(best)
        if others:
            caption += "\n\nBoshqa topilganlar (agar shu emas bo'lsa, aniqroq nom yozing):\n"
            caption += "\n".join(f"- {os.path.basename(o)}" for o in others)
        try:
            await client.send_file(event.chat_id, best, caption=REPLY_MARKER + caption)
            print(f"[BRIDGE] Fayl yuborildi: {best}", flush=True)
        except Exception as e:
            print("[BRIDGE] Fayl yuborishda xato:", repr(e), flush=True)
            await event.reply(REPLY_MARKER + f"Faylni yuborolmadim: {e}")

    async def _route_text(event, text: str):
        """Skrinshot/fayl-so'rovlarini asosiy LLM javobidan OLDIN ushlab qoladi."""
        if _is_screenshot_request(text):
            await _handle_screenshot_request(event)
            return True
        file_query = _extract_file_query(text)
        if file_query is not None:
            await _handle_file_request(event, file_query)
            return True
        return False

    async def _process_text(event, text: str):
        print(f"[BRIDGE] Matn keldi: {text[:100]!r}", flush=True)
        if await _route_text(event, text):
            return
        loop = asyncio.get_event_loop()
        t0 = time.time()
        reply = await loop.run_in_executor(None, _generate_reply, text)
        print(f"[BRIDGE] Javob tayyor ({time.time() - t0:.1f}s): {reply[:100]!r}", flush=True)
        await event.reply(REPLY_MARKER + reply)

    async def _process_voice(event):
        print("[BRIDGE] Ovozli xabar keldi — yuklab olinmoqda...", flush=True)
        try:
            data = await event.download_media(file=bytes)
        except Exception as e:
            print("[BRIDGE] Ovoz yuklab olishda xato:", repr(e), flush=True)
            await event.reply(REPLY_MARKER + "Ovozli xabarni yuklab bo'lmadi.")
            return

        loop = asyncio.get_event_loop()
        try:
            pcm16, sr = await loop.run_in_executor(None, _decode_audio_bytes, data)
        except Exception as e:
            print("[BRIDGE] Ovoz dekod xato:", repr(e), flush=True)
            pcm16, sr = None, None

        if pcm16 is None:
            await event.reply(REPLY_MARKER + "Ovozli xabarni o'qiy olmadim (format muammosi).")
            return

        # Xuddi _web_talk() dagi kabi — STT bilan bir vaqtda, fon threadida
        # query'ga bog'liq bo'lmagan kontekst qatlamlarini oldindan hisoblash
        # ("tinglash paytida o'ylash", qarang _web_talk() dagi izoh).
        def _run_prewarm():
            try:
                _dt = _co.prewarm_independent_context()
                print(f"[BRIDGE][TIMING] prewarm_independent_context={_dt*1000:.0f}ms "
                      f"(STT bilan bir vaqtda, fon threadida)", flush=True)
            except Exception as _e:
                print(f"[BRIDGE] prewarm xato (e'tiborsiz qoldiriladi): {_e!r}", flush=True)

        threading.Thread(target=_run_prewarm, daemon=True, name="NK-TurnPrewarm").start()

        text = await loop.run_in_executor(None, whisper_transcribe_int16, pcm16, sr)
        text = (text or "").strip()
        if not text:
            await event.reply(REPLY_MARKER + "Ovozli xabarni tushunmadim, qaytadan urinib ko'ring yoki yozing.")
            return

        print(f"[BRIDGE] Ovozdan matn: {text[:100]!r}", flush=True)

        # Ovoz orqali ham "skrinshot yubor" / "faylni top" kabi so'rovlar ishlaydi
        if await _route_text(event, text):
            return

        t0 = time.time()
        reply = await loop.run_in_executor(None, _generate_reply, text)
        print(f"[BRIDGE] Javob tayyor ({time.time() - t0:.1f}s): {reply[:100]!r}", flush=True)

        await event.reply(REPLY_MARKER + f"(eshitdim: “{text}”)\n\n{reply}")

        try:
            voice_path = await loop.run_in_executor(None, _synthesize_voice_reply, reply)
            if voice_path:
                await client.send_file(
                    event.chat_id,
                    voice_path,
                    voice_note=voice_path.endswith(".ogg"),
                    caption=None,
                )
                try:
                    os.remove(voice_path)
                except OSError:
                    pass
                print("[BRIDGE] Ovozli javob yuborildi.", flush=True)
            else:
                print("[BRIDGE] Ovozli javob sintez qilinmadi — faqat matn yuborildi.", flush=True)
        except Exception:
            print("[BRIDGE] Ovozli javob yuborishda xato:", flush=True)
            traceback.print_exc()

    # Jonli ovoz (telefon brauzeri) — Telegram bilan BIR XIL jarayonda, bir
    # xil memory/tts/_proc_lock ishlatib, parallel ishga tushiriladi (fayl
    # yozish poyga holati bo'lmasligi uchun ikkita alohida jarayon EMAS).
    try:
        await _start_web_voice_server()
    except Exception:
        print("[BRIDGE][WEB-VOICE] Ishga tushmadi:", flush=True)
        traceback.print_exc()

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[BRIDGE] To'xtatildi.", flush=True)
