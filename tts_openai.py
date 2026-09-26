# -*- coding: utf-8 -*-
"""
NeuroKey TTS — OpenAI + Parallel Pre-fetch.

MUAMMOLAR TUZATILDI:
1. is_playing() endi BUTUN say() davomida True qaytaradi (fetch + play).
   Oldin: fetch paytida False edi → STT mikrofon ochib, interrupt o'rnatardi.
2. Parallel pre-fetch: chunk N chalayotganda chunk N+1 API dan olinadi.
   Natija: jumlalar orasida to'xtash yo'q, nutq uzluksiz.
3. _busy flag: say() boshlangandan tugaguncha True → STT hech qachon oralab kirmaydi.
"""
from __future__ import annotations

import io
import os
import re
import time
import wave
import threading
import queue
from typing import List, Optional

import numpy as np
import sounddevice as sd
from openai import OpenAI

import config as C

try:
    from neurokey_debug_log import log_tts as _log
except Exception:
    def _log(msg): pass  # suppress TTS debug in VOICE_ONLY_UI mode

OPENAI_TTS_MAX_CHARS = 4095
_PREFETCH_AHEAD = 1  # qancha chunk oldin fetch qilinadi
_EDGE_FETCH_LOCK = threading.Lock()  # Edge asyncio — bir vaqtda bitta (Windows deadlock oldini)


def _resample_audio(audio: np.ndarray, sr: int, target_sr: int) -> tuple:
    """HDMI/monitor uchun qurilma default_samplerate ga moslashtirish."""
    if target_sr <= 0 or sr <= 0 or target_sr == sr or len(audio) < 4:
        return audio, sr
    n_out = max(1, int(len(audio) * target_sr / sr))
    x_old = np.linspace(0.0, 1.0, len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    out = np.interp(x_new, x_old, np.asarray(audio, dtype=np.float32).flatten()).astype(np.float32)
    return out, int(target_sr)


def _device_target_samplerate(device_index: Optional[int], fallback_sr: int) -> int:
    if device_index is None:
        return int(fallback_sr)
    try:
        info = sd.query_devices(int(device_index))
        ds = info.get("default_samplerate")
        if ds and float(ds) > 8000:
            return int(float(ds))
    except Exception:
        pass
    return int(fallback_sr)


def _use_simple_playback() -> bool:
    v = (os.getenv("NEUROKEY_TTS_SIMPLE_PLAYBACK", "") or "").strip().lower()
    if v in ("0", "false", "no"):
        return False
    if v in ("1", "true", "yes"):
        return True
    return os.name == "nt"


def _dual_finish_enabled() -> bool:
    return os.getenv("NEUROKEY_TTS_DUAL_FINISH", "1").strip().lower() not in ("0", "false", "no")


def _tts_ui_lang() -> str:
    lang = (os.getenv("NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()
    return lang if lang in ("en", "ru", "uz") else "ru"


def _edge_voice_candidates() -> List[str]:
    """Edge TTS ovozlari — birinchi ishlamasa keyingisi."""
    lang = _tts_ui_lang()
    seen: set = set()
    out: List[str] = []

    def _add(v: str) -> None:
        v = (v or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)

    if lang == "en":
        _add(os.getenv("TTS_EDGE_ENGLISH_VOICE", "") or getattr(C, "TTS_EDGE_ENGLISH_VOICE", "") or "en-US-GuyNeural")
        _add(os.getenv("TTS_EDGE_BACKUP_VOICE", "") or "en-US-AriaNeural")
        for v in ("en-US-GuyNeural", "en-US-AriaNeural", "en-US-JennyNeural", "en-GB-SoniaNeural"):
            _add(v)
    elif lang == "uz":
        # Bug fix: ilgari "uz" ham "else" (rus) shoxobchasiga tushib, o'zbekcha
        # matn rus ovozida o'qilardi. config.py da TTS_EDGE_UZBEK_VOICE ALLAQACHON
        # bor edi (uz-UZ-MadinaNeural) — lekin bu yerda hech qachon ishlatilmagan edi.
        _add(os.getenv("TTS_EDGE_UZBEK_VOICE", "") or getattr(C, "TTS_EDGE_UZBEK_VOICE", "") or "uz-UZ-MadinaNeural")
        _add(os.getenv("TTS_EDGE_BACKUP_VOICE", "") or "uz-UZ-SardorNeural")
        for v in ("uz-UZ-MadinaNeural", "uz-UZ-SardorNeural"):
            _add(v)
    else:
        _add(os.getenv("TTS_EDGE_RUSSIAN_VOICE", "") or getattr(C, "TTS_EDGE_RUSSIAN_VOICE", "") or "ru-RU-DmitryNeural")
        _add(os.getenv("TTS_EDGE_BACKUP_VOICE", "") or "ru-RU-SvetlanaNeural")
        for v in ("ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"):
            _add(v)
    return out


def _warmup_phrase() -> str:
    if _tts_ui_lang() == "en":
        return "Listening."
    return "Слушаю."


def _brand_for_russian_tts(t: str) -> str:
    """Latin NeuroKey -> rus talaffuzi (Piper/Edge bir xil to'g'ri o'qishi uchun)."""
    if not t:
        return t
    rep = (os.getenv("NEUROKEY_TTS_BRAND_READING", "Нейро Кей") or "Нейро Кей").strip() or "Нейро Кей"
    # Bo'shliqli: "Neuro Key"
    t = re.sub(r"\bneuro\s+key\b", rep, t, flags=re.IGNORECASE)
    # Bitlashtirilgan: NeuroKey, NEUROKEY
    t = re.sub(r"\bneurokey\b", rep, t, flags=re.IGNORECASE)
    return t


def _normalize(text: str) -> str:
    """Matnni TTS uchun tozalaydi: markdown, kod, belgilar, emoji olib tashlanadi."""
    if not text:
        return ""
    t = str(text).strip()
    t = _brand_for_russian_tts(t)

    # Kod bloklari: ```...``` → o'tkazib yuborish (kod o'qilmasin)
    t = re.sub(r"```[\w]*\n?[\s\S]*?```", " ", t)
    # Inline kod: `code` → bo'sh joy
    t = re.sub(r"`[^`]+`", " ", t)

    # Markdown headers: ### Sarlavha → Sarlavha
    t = re.sub(r"^\s*#{1,6}\s+", "", t, flags=re.MULTILINE)

    # Bold/italic kombinatsiyalari: ***text*** **text** *text* __text__ _text_
    t = re.sub(r"\*{3}(.+?)\*{3}", r"\1", t, flags=re.DOTALL)
    t = re.sub(r"\*{2}(.+?)\*{2}", r"\1", t, flags=re.DOTALL)
    t = re.sub(r"\*([^*\n]+)\*",   r"\1", t)
    t = re.sub(r"_{3}(.+?)_{3}",   r"\1", t, flags=re.DOTALL)
    t = re.sub(r"_{2}(.+?)_{2}",   r"\1", t, flags=re.DOTALL)
    t = re.sub(r"_([^_\n]+)_",     r"\1", t)

    # Blockquote: > text → text
    t = re.sub(r"^\s*>\s*", "", t, flags=re.MULTILINE)

    # Gorizontal chiziq
    t = re.sub(r"^\s*[-=_*]{3,}\s*$", "", t, flags=re.MULTILINE)

    # Ro'yxat: "- item", "* item", "• item" → item
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\n\s*[-*•]\s+", " ", t)
    # Raqamli ro'yxat: "1. item" yoki "1) item" → item
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.MULTILINE)

    # URLs
    t = re.sub(r"https?://\S+", "", t)

    # Emoji va maxsus belgilar (unicode simbollar: arrows, checkmarks, boxes, ...)
    t = re.sub(r"[✓✗✔✘→←↑↓⇒⇐⟹⟸►◄▶◀▷◁▸‣❯❮❱❰»«»›‹]", " ", t)
    t = re.sub(r"[╔╗╚╝║═╠╣╦╩╬┌┐└┘│─┼├┤┬┴]", " ", t)
    t = re.sub(r"[★☆♦♣♠♥♡♢♤●○◆◇■□▪▫]", " ", t)
    # Emoji unicode bloki (U+1F000–U+1FFFF va boshqalar)
    t = re.sub(r"[\U0001F000-\U0001FFFF]", " ", t)
    t = re.sub(r"[\U00002600-\U000027BF]", " ", t)
    t = re.sub(r"[\U0001F300-\U0001F9FF]", " ", t)

    # Qolgan yolg'iz * va _ belgilar
    t = re.sub(r"(?<!\w)[*_#|~^]+(?!\w)", " ", t)

    # Edge TTS % < > ni SSML deb o'qiydi va audio qaytarmaydi (NoAudioReceived).
    # Matn konsolda qoladi, karnaydan chiqmaydi.
    t = t.replace("%", " процентов ")
    t = t.replace("&", " и ")
    t = re.sub(r"[<>]", " ", t)

    # Ko'p bo'sh joy va yangi satrlarni birlashtirish
    t = re.sub(r"\n+", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()

    return t.strip(".,;:–—")


def _split_into_chunks(text: str, max_chars: int = OPENAI_TTS_MAX_CHARS) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks = []
    sep = re.compile(r"(?<=[.!?…])\s+|\n+")
    parts = sep.split(text)
    current = ""
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if len(current) + len(p) + 1 <= max_chars:
            current = (current + " " + p).strip() if current else p
        else:
            if current:
                chunks.append(current)
            if len(p) > max_chars:
                while p:
                    idx = p.rfind(" ", 0, max_chars + 1)
                    if idx <= 0:
                        idx = max_chars
                    chunks.append(p[:idx].strip())
                    p = p[idx:].strip()
                current = ""
            else:
                current = p
    if current:
        chunks.append(current)
    return chunks


def _split_into_speech_chunks(text: str, max_chars: int) -> List[str]:
    return _split_into_chunks(text, max_chars)


def _wav_to_float32(wav_bytes: bytes):
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        pcm = wf.readframes(wf.getnframes())
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


class TTSWorker:
    """
    OpenAI TTS + Parallel Pre-fetch.

    ASOSIY XUSUSIYATLAR:
    - is_playing() → say() boshlangandan tugaguncha DOIM True.
      Bu STT ni oralab kirishdan saqlaydi.
    - Parallel pre-fetch: audio chalayotganda keyingi chunk API dan olinadi.
      Jumlalar orasida to'xtash yo'q.
    - say() BLOCKING — navbat yo'q, barcha bo'laklar shu threadda.
    """

    def __init__(self, voice: str = "nova"):
        self.voice = (voice or getattr(C, "OPENAI_TTS_VOICE", "nova") or "nova").strip()
        self.model = getattr(C, "OPENAI_TTS_MODEL", None) or os.getenv("OPENAI_TTS_MODEL", "tts-1") or "tts-1"
        self.speed = float(getattr(C, "TTS_SPEED", "1.15") or 1.15)
        self.out_dev = getattr(C, "OUTPUT_DEVICE_INDEX", None)
        self._env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        self._cached_key = ""
        self.client = self._make_client()

        # STT bilan koordinatsiya uchun: BUTUN say() davomida True
        self._busy = threading.Event()   # is_playing() bu ni qaytaradi
        self._interrupt = False
        self._last_end = time.monotonic()
        self._say_lock = threading.Lock()  # bir vaqtda faqat bitta say()
        self._active_stream = None       # joriy sd.OutputStream (interrupt uchun)

        # Piper offline TTS — fonda yuklanadi (yagona offline ovoz)
        self._piper_voice = None
        self._piper_lock = threading.Lock()
        # Silero zaxira (Piper .onnx yo'q bo'lsa)
        self._silero_model = None
        self._silero_apply = None
        self._silero_sr = 48000
        self._silero_lock = threading.Lock()
        threading.Thread(target=self._preload_piper, daemon=True).start()

        # Jumla navbati — LLM stream bloklanmasin (Groq timeout oldini)
        self._speech_q: queue.Queue = queue.Queue()
        self._speech_spoken = 0
        self._speech_worker = threading.Thread(target=self._speech_worker_loop, daemon=True, name="TTS-SpeechQueue")
        self._speech_worker.start()

        # Sticky engine: bitta say() davomida bir xil ovoz (openai yoki piper)
        # Birinchi muvaffaqiyatli engine keyingi chunklarga ham yopishadi — aralash ovoz bo'lmaydi
        self._session_engine: Optional[str] = None  # None = hali tanlanmagan

        if self.out_dev is not None:
            try:
                sd.default.device = (None, self.out_dev)
            except Exception:
                pass

    # ── API key hot-reload ────────────────────────────────────────────────────

    def _read_key(self) -> str:
        """Har safar .env dan o'qiydi — restart shart emas."""
        try:
            if os.path.isfile(self._env_path):
                with open(self._env_path, encoding="utf-8") as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if _line.startswith("OPENAI_API_KEY=") and not _line.startswith("#"):
                            _k = _line.split("=", 1)[1].strip().strip('"').strip("'")
                            if _k and not _k.startswith("your_") and len(_k) > 20:
                                return _k
        except Exception:
            pass
        return getattr(C, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")

    def _make_client(self) -> OpenAI:
        key = self._read_key()
        self._cached_key = key
        return OpenAI(api_key=key)

    def _get_tts_client(self) -> OpenAI:
        """Client ni qaytaradi; kalit o'zgarganda yangilaydi."""
        key = self._read_key()
        if key != self._cached_key:
            self.client = self._make_client()
        return self.client

    # ── Tashqi interfeys ──────────────────────────────────────────────────────

    def start(self):
        pass

    def enqueue_speech(self, text: str) -> None:
        """Jumlani ovoz navbatiga qo'yadi (LLM stream bloklanmaydi)."""
        t = (text or "").strip()
        if t:
            self._speech_q.put(t)

    def drain_speech(self, timeout: float = 180.0) -> int:
        """Navbatdagi barcha jumlalar o'qilguncha kutadi. Qaytadi: muvaffaqiyatli soni."""
        deadline = time.monotonic() + max(5.0, float(timeout))
        while time.monotonic() < deadline:
            pending = self._speech_q.unfinished_tasks
            if pending == 0 and not self.is_playing():
                return int(self._speech_spoken)
            time.sleep(0.04)
        print(f"[TTS] drain timeout ({self._speech_q.unfinished_tasks} pending, spoke={self._speech_spoken})", flush=True)
        return int(self._speech_spoken)

    def reset_speech_counter(self) -> None:
        self._speech_spoken = 0

    def _speech_worker_loop(self) -> None:
        while True:
            text = self._speech_q.get()
            try:
                if text is None:
                    return
                time.sleep(0.07)
                if self.say(text):
                    self._speech_spoken += 1
            except Exception as _qe:
                print(f"[TTS] queue xato: {_qe!r}", flush=True)
            finally:
                self._speech_q.task_done()

    def stop(self):
        self.interrupt()

    def interrupt(self):
        """TTS ni darhol to'xtatadi."""
        import traceback as _tb
        caller = "".join(_tb.format_stack(limit=4)[:-1]).strip().replace("\n", " | ")
        _log(f"interrupt() chaqirildi | caller: {caller[-200:]}")
        self._interrupt = True
        # Aktiv OutputStream ni darhol to'xtat (gapless playback uchun)
        s = self._active_stream
        if s is not None:
            self._active_stream = None
            try:
                s.abort()
                _log("OutputStream.abort() OK")
            except Exception as e:
                _log(f"OutputStream.abort() xato: {repr(e)}")
        # Eski sd.play() uchun ham to'xtat
        try:
            sd.stop()
        except Exception:
            pass
        # _busy.clear() BU YERDA EMAS — faqat say() finally blokida tozalanadi
        self._last_end = time.monotonic()

    def is_playing(self) -> bool:
        """
        True — TTS hozir band (fetch YOKI playback YOKI jumlalar orasida).
        STT bu flagni ko'rib mikrofon ochishni kechiktiradi.
        """
        return self._busy.is_set()

    def set_speed(self, speed: float):
        self.speed = max(0.5, min(2.0, float(speed)))

    def adjust_speed(self, delta: float):
        self.speed = max(0.5, min(2.0, self.speed + delta))

    def last_end_time(self) -> float:
        return float(self._last_end)

    # ── Asosiy say() ─────────────────────────────────────────────────────────

    def say(self, text: str) -> bool:
        """
        Matnni ovozga o'zgartiradi va chaladi.
        BLOCKING. is_playing()=True shu funksiya davomida HAMISHA.
        True qaytaradi faqat kamida bitta audio chunk eshitilganda.
        """
        if not text:
            return False
        raw = str(text).strip()
        if raw:
            print(f"[TTS] gapiryapman: {raw[:100]}", flush=True)
            _prep = "preparing audio" if _tts_ui_lang() == "en" else "ovoz tayyorlanmoqda"
            print(f"[TTS] {_prep} (Edge, 3-10s)...", flush=True)
        normalized = _normalize(raw)
        if not normalized:
            print("[TTS] matn bo'sh (normalize dan keyin) — ovoz chiqmaydi", flush=True)
            return False

        # Bir vaqtda bitta playback; parallel thread (eslatma, TG) blocking=False da JAVOBNI yo'qotardi.
        # Navbat: oldingi say tugaguncha kutamiz (maks ~3 daqiqa), keyin o'qiymiz.
        if not self._say_lock.acquire(timeout=180.0):
            _log(f"say() DROPPED (lock 180s timeout): {normalized[:60]}")
            print(f"[TTS] lock timeout — o'tkazib yuborildi: {normalized[:60]}", flush=True)
            return False

        _log(f"say() BOSHLANDI: {normalized[:80]}")
        # _busy ni HOZIROQ o'rnatamiz — STT mikrofon ochishni kutadi
        self._interrupt = False
        self._busy.set()
        self._session_engine = None  # har yangi say() uchun engine qayta tanlanadi
        played_ok = False

        try:
            chunks = _split_into_chunks(normalized, OPENAI_TTS_MAX_CHARS)
            _log(f"say() {len(chunks)} chunk ga bo'lindi")
            if not chunks:
                return False
            stats = self._play_with_prefetch(chunks)
            played_ok = bool(
                stats
                and (
                    int(stats.get("chunks_played") or 0) > 0
                    or float(stats.get("played_sec") or 0) > 0.05
                )
            )
            if stats and _dual_finish_enabled() and not self._interrupt:
                before = played_ok
                self._dual_finish_speech(normalized, chunks, stats)
                if not before and not self._interrupt:
                    played_ok = bool(float(stats.get("played_sec") or 0) > 0.05)
            if not played_ok and not self._interrupt:
                # Edge osilib qolsa — Piper ni sinxron yuklab, bir marta qayta urinamiz
                if self._piper_voice is None:
                    self._preload_piper()
                _em = self._fetch_piper_only(normalized[:500])
                if _em:
                    dur = self._play_audio_block(_em[0], _em[1])
                    played_ok = dur > 0.05
        except Exception as _say_e:
            _log(f"say() EXCEPTION: {repr(_say_e)}")
            print(f"[TTS] xato (tuzatildi, dastur davom etadi): {_say_e!r}", flush=True)
            played_ok = False
        finally:
            # Hammasi tugagach yoki interrupt bo'lganda — busy tozalanadi
            self._busy.clear()
            self._last_end = time.monotonic()
            self._say_lock.release()
            _log(f"say() TUGADI (interrupt={self._interrupt}, played={played_ok})")
            if played_ok:
                print(f"[TTS] tugadi: OK (dev={self.out_dev})", flush=True)
            elif self._interrupt:
                print("[TTS] tugadi: UZILDI", flush=True)
            else:
                print("[TTS] tugadi: XATO — ovoz chiqmadi", flush=True)

        if not played_ok and not self._interrupt:
            print(
                "[TTS] OVOZ CHIQMADI — Edge/Piper audio yuklanmadi. "
                "Tekshiring: pip install av edge-tts",
                flush=True,
            )
        return played_ok

    # ── Parallel pre-fetch mexanizmi ─────────────────────────────────────────

    def _preload_piper(self):
        """Startup da fonda Piper ONNX ni yuklab qo'yadi — eng yaxshi offline ovoz."""
        try:
            from piper import PiperVoice as _PV
            import glob as _g
            _base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "piper")
            # 1. To'liq yo'l (PIPER_MODEL env yoki config)
            _model_env = (getattr(C, "PIPER_MODEL", "") or os.getenv("PIPER_MODEL", "") or "").strip()
            if _model_env and os.path.isfile(_model_env):
                _model_path = _model_env
            else:
                # 2. PIPER_VOICE=irina/ruslan/dmitri/denis → avtomatik fayl topish
                _voice_name = (getattr(C, "PIPER_VOICE", "") or "irina").strip().lower()
                _named = _g.glob(os.path.join(_base, f"*{_voice_name}*.onnx"))
                if _named:
                    _model_path = sorted(_named)[0]
                else:
                    # 3. models/piper/ da birinchi .onnx
                    _cands = [p for p in _g.glob(os.path.join(_base, "*.onnx"))
                              if not p.lower().endswith(".onnx.json")]
                    if not _cands:
                        _log("Piper: models/piper/ da .onnx yo'q (faqat .json?) — Silero zaxira")
                        return
                    _model_path = sorted(_cands, key=lambda p: (
                        0 if "medium" in p.lower() else 1 if "high" in p.lower() else 2
                    ))[0]
            with self._piper_lock:
                if self._piper_voice is not None:
                    return
                _voice = _PV.load(_model_path)
                # Isitish — birinchi chaqiruv sekin bo'lmasligi uchun
                list(_voice.synthesize("Привет."))
                self._piper_voice = _voice
                _log(f"Piper yuklandi OK: {os.path.basename(_model_path)} @ {_voice.config.sample_rate}Hz")
        except Exception as _e:
            _log(f"Piper preload xato: {repr(_e)}")

    def _edge_tts_fetch_one(self, text: str, voice: str) -> Optional[tuple]:
        """Bitta Edge ovoz bilan audio olish."""
        import edge_tts as _etts
        import asyncio as _asyncio
        import io as _io

        _rate = f"{int((float(getattr(self, 'speed', 1.0) or 1.0) - 1.0) * 100):+d}%"

        async def _fetch(rate: str):
            comm = _etts.Communicate(text[:4096], voice, rate=rate)
            buf = _io.BytesIO()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        import concurrent.futures as _cf
        global _EDGE_BROKEN
        if globals().get("_EDGE_BROKEN", False):
            return None

        with _EDGE_FETCH_LOCK:
            ex = _cf.ThreadPoolExecutor(max_workers=1)
            fut = ex.submit(_asyncio.run, _fetch(_rate))
            try:
                mp3_data = fut.result(timeout=6)
            except _cf.TimeoutError:
                _log(f"Edge TTS fetch TIMEOUT (6s, voice={voice}) — tarmoq/DNS osilib qolgan bo'lishi mumkin")
                print(f"[TTS] Edge fetch 6s ichida javob bermadi (voice={voice}) — Edge o'chirildi, backup ovozga o'tilmoqda", flush=True)
                globals()["_EDGE_BROKEN"] = True
                ex.shutdown(wait=False)
                return None
            except Exception as _fe:
                _log(f"Edge TTS fetch xato: {repr(_fe)}")
                print(f"[TTS] Edge fetch xato: {_fe!r}", flush=True)
                _ename = type(_fe).__name__
                _no_audio = _ename == "NoAudioReceived" or "No audio was received" in str(_fe)
                if _no_audio:
                    print("[TTS] Edge bo'sh qaytdi — oddiy tezlikda qayta", flush=True)
                    try:
                        fut2 = ex.submit(_asyncio.run, _fetch("+0%"))
                        mp3_data = fut2.result(timeout=6)
                    except Exception as _fe2:
                        print(f"[TTS] Edge qayta urinish xato: {_fe2!r}", flush=True)
                        ex.shutdown(wait=False)
                        return None
                else:
                    globals()["_EDGE_BROKEN"] = True
                    ex.shutdown(wait=False)
                    return None
            ex.shutdown(wait=False)

        if not mp3_data:
            return None
        decoded = self._mp3_bytes_to_float32(mp3_data)
        if decoded is None:
            return None
        audio, sr = decoded
        _log(f"Edge TTS OK ({len(audio)/sr:.1f}s @ {sr}Hz, voice={voice})")
        return audio, sr

    def _edge_tts_fetch(self, text: str) -> Optional[tuple]:
        """Edge TTS — bir nechta ovoz sinab ko'riladi (NoAudioReceived oldini)."""
        text = (text or "").strip()
        if not text:
            return None
        last_err = None
        voices = _edge_voice_candidates()
        for voice in voices:
            try:
                result = self._edge_tts_fetch_one(text, voice)
                if result is not None:
                    return result
            except Exception as _ee:
                last_err = _ee
                _log(f"Edge TTS xato (voice={voice}): {repr(_ee)}")
        # Bir marta qayta: Edge ba'zan ikkinchi gapda bo'sh audio qaytaradi.
        if voices and not globals().get("_EDGE_BROKEN", False):
            time.sleep(0.4)
            try:
                result = self._edge_tts_fetch_one(text, voices[0])
                if result is not None:
                    return result
            except Exception as _ee:
                last_err = _ee
        if last_err is not None:
            print(f"[TTS] Edge xato (barcha ovozlar): {last_err!r}", flush=True)
        return None

    def _mp3_bytes_to_float32(self, mp3_data: bytes) -> Optional[tuple]:
        """MP3 bytes -> (float32 mono, sample_rate). PyAV, keyin pydub+imageio-ffmpeg."""
        import io as _io2
        import numpy as _np2

        # 1) PyAV (eng yaxshi)
        try:
            import av as _av
            container = _av.open(_io2.BytesIO(mp3_data), format="mp3")
            stream = container.streams.audio[0]
            sr = stream.rate
            frames = []
            for packet in container.demux(stream):
                for frame in packet.decode():
                    frames.append(frame.to_ndarray())
            container.close()
            if frames:
                audio = _np2.concatenate(frames, axis=-1).flatten().astype(_np2.float32)
                if audio.max() > 1.5:
                    audio /= 32768.0
                return audio, sr
        except ImportError:
            _log("PyAV yo'q — pydub fallback")
        except Exception as _av_e:
            _log(f"PyAV decode xato: {_av_e!r}")

        # 2) pydub + imageio-ffmpeg (loyihada bor)
        try:
            from pydub import AudioSegment
            try:
                import imageio_ffmpeg
                _ff = imageio_ffmpeg.get_ffmpeg_exe()
                if _ff:
                    AudioSegment.converter = _ff
                    AudioSegment.ffprobe = _ff
            except Exception:
                pass
            seg = AudioSegment.from_file(_io2.BytesIO(mp3_data), format="mp3")
            sr = int(seg.frame_rate)
            samples = _np2.array(seg.get_array_of_samples(), dtype=_np2.float32)
            if seg.channels > 1:
                samples = samples.reshape(-1, seg.channels).mean(axis=1)
            if samples.max() > 1.5:
                samples /= 32768.0
            return samples, sr
        except Exception as _pd_e:
            _log(f"pydub decode xato: {_pd_e!r}")
            print(
                "[TTS] MP3 dekoder yo'q. O'rnating: pip install av",
                flush=True,
            )
        return None

    def _fetch_audio(self, text: str) -> Optional[tuple]:
        """Audio olib keladi.
        Zanjir (API kalit bo'lsa):  1) OpenAI nova  →  2) Edge TTS  →  3) Piper
        Zanjir (kalit yo'q/offline): 1) Edge TTS  →  2) Piper

        Sticky engine: _session_engine birinchi muvaffaqiyatli engine ni eslab qoladi.
        Piper doim fallback sifatida sinab ko'riladi (airplane mode recovery).
        """
        _api_key_ok = bool(self._read_key())
        _tts_skip_openai = (
            os.getenv("TTS_SKIP_OPENAI", "0") == "1"
            or getattr(C, "TTS_SKIP_OPENAI", False)
        )

        # ── 1. OpenAI nova (API kalit bo'lsa — aksentsz, sifatli) ────────────
        _skip_openai = not _api_key_ok or self._session_engine in ("edge", "piper") or _tts_skip_openai
        if not _skip_openai and not self._interrupt:
            for attempt in range(2):
                if self._interrupt:
                    break
                try:
                    resp = self._get_tts_client().audio.speech.create(
                        model=self.model, voice=self.voice,
                        input=text, response_format="wav", speed=self.speed,
                    )
                    result = _wav_to_float32(resp.read())
                    if result is not None:
                        self._session_engine = "openai"
                        return result
                except Exception as e:
                    _estr = str(e)
                    _log(f"OpenAI TTS xato (urinish {attempt+1}/2): {repr(e)}")
                    if any(x in _estr for x in ("429", "quota", "insufficient_quota")):
                        break  # kredit tugagan — Edge ga o'tamiz
                    if self._interrupt or attempt == 1:
                        break
                    time.sleep(0.5)

        # ── 2. Edge TTS (ixtiyoriy; OFFLINE demoda odatda o'chiq — faqat Piper) ─
        _edge_env = (os.getenv("TTS_USE_EDGE_RUSSIAN", "") or "").strip().lower()
        _edge_en_env = (os.getenv("TTS_USE_EDGE_ENGLISH", "") or "").strip().lower()
        _ui_lang_now = (os.getenv("NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()

        if _ui_lang_now == "en":
            _use_edge_ru = _edge_en_env in ("1", "true", "yes", "on") or bool(getattr(C, "TTS_USE_EDGE_ENGLISH", False))
        else:
            if _edge_env in ("0", "false", "no", "off"):
                _use_edge_ru = False
            elif _edge_env in ("1", "true", "yes", "on"):
                _use_edge_ru = True
            else:
                _use_edge_ru = bool(getattr(C, "TTS_USE_EDGE_RUSSIAN", False))

        _skip_edge = (self._session_engine in ("piper",)) or (not _use_edge_ru)
        if not _skip_edge and not self._interrupt:
            result = self._edge_tts_fetch(text)
            if result is not None:
                self._session_engine = "edge"
                return result

        # ── 3. Piper ONNX (lokal, offline — faqat rus) ───────────────────────
        if not self._interrupt and _tts_ui_lang() != "en":
            try:
                import numpy as _np
                for _ in range(30):  # max 3s kutish
                    if self._piper_voice is not None:
                        break
                    time.sleep(0.1)
                with self._piper_lock:
                    if self._piper_voice is None:
                        raise RuntimeError("Piper yuklanmadi")
                    _pv = self._piper_voice
                _PIPER_SR = _pv.config.sample_rate
                _piper_chunks, _pbuf = [], ""
                for _ps in re.split(r"(?<=[.!?…])\s+|\n+", text[:3000]):
                    _ps = (_ps or "").strip()
                    if not _ps:
                        continue
                    if len(_pbuf) + len(_ps) + 1 <= 250:
                        _pbuf = (_pbuf + " " + _ps).strip() if _pbuf else _ps
                    else:
                        if _pbuf: _piper_chunks.append(_pbuf)
                        _pbuf = _ps[:250]
                if _pbuf: _piper_chunks.append(_pbuf)
                if not _piper_chunks: _piper_chunks = [text[:250]]
                _parts = []
                for _pc in _piper_chunks:
                    if self._interrupt: break
                    for _ac in _pv.synthesize(_pc):
                        _arr = _np.array(_ac.audio_int16_array, dtype=np.int16)
                        if len(_arr) > 0:
                            _parts.append(_arr)
                if _parts:
                    _audio = _np.concatenate(_parts).astype(np.float32) / 32768.0
                    _log(f"Piper OK ({len(_audio)/_PIPER_SR:.1f}s @ {_PIPER_SR}Hz)")
                    self._session_engine = "piper"
                    return _audio, _PIPER_SR
            except Exception as _pe:
                _log(f"Piper xato: {repr(_pe)}")

        # ── 4. Silero (lokal, faqat rus) ────────────────────────────────────
        if not self._interrupt and _tts_ui_lang() != "en":
            result = self._fetch_silero(text)
            if result is not None:
                self._session_engine = "silero"
                return result

        _log("TTS: OpenAI, Edge, Piper, Silero — hech biri ishlamadi")
        return None

    def _fetch_silero(self, text: str) -> Optional[tuple]:
        """Silero RU — internet/Edge ishlamasa offline zaxira."""
        if self._interrupt or not (text or "").strip():
            return None
        try:
            import torch
            with self._silero_lock:
                if self._silero_model is None:
                    print("[TTS] Silero yuklanmoqda (birinchi marta, ~15s)...", flush=True)
                    torch.set_grad_enabled(False)
                    res = torch.hub.load(
                        repo_or_dir="snakers4/silero-models",
                        model="silero_tts",
                        language="ru",
                        speaker="v4_ru",
                        trust_repo=True,
                        force_reload=False,
                    )
                    if isinstance(res, tuple):
                        self._silero_model = res[0]
                        self._silero_sr = int(res[2]) if len(res) >= 3 else 48000
                    else:
                        self._silero_model = res
                    self._silero_apply = self._silero_model.apply_tts
                    self._silero_model.eval()
                    list(self._silero_apply(text="ок", speaker="baya", sample_rate=self._silero_sr))
                    _log("Silero yuklandi OK")
                model = self._silero_model
                apply = self._silero_apply
                sr = self._silero_sr
            parts = []
            for chunk in _split_into_chunks((text or "")[:2000], 180):
                if self._interrupt:
                    break
                with torch.inference_mode():
                    audio = apply(text=chunk, speaker="baya", sample_rate=sr)
                if isinstance(audio, torch.Tensor):
                    audio = audio.to("cpu").numpy()
                if audio is not None and len(audio):
                    parts.append(np.asarray(audio, dtype=np.float32))
            if not parts:
                return None
            merged = np.concatenate(parts)
            peak = float(np.max(np.abs(merged))) if len(merged) else 0.0
            if peak > 0:
                merged = merged / peak
            _log(f"Silero OK ({len(merged)/sr:.1f}s @ {sr}Hz)")
            return merged.astype(np.float32), int(sr)
        except Exception as _se:
            _log(f"Silero xato: {repr(_se)}")
            print(f"[TTS] Silero xato: {_se!r}", flush=True)
            return None

    def _fetch_piper_only(self, text: str) -> Optional[tuple]:
        """Faqat Piper — ikkinchi ovoz / backup."""
        if self._interrupt or not (text or "").strip():
            return None
        try:
            import numpy as _np
            for _ in range(30):
                if self._piper_voice is not None:
                    break
                time.sleep(0.1)
            with self._piper_lock:
                if self._piper_voice is None:
                    return None
                _pv = self._piper_voice
            _PIPER_SR = _pv.config.sample_rate
            _parts = []
            for _pc in re.split(r"(?<=[.!?…])\s+|\n+", (text or "")[:3000]):
                _pc = (_pc or "").strip()
                if not _pc or self._interrupt:
                    continue
                for _ac in _pv.synthesize(_pc[:250]):
                    _arr = _np.array(_ac.audio_int16_array, dtype=np.int16)
                    if len(_arr) > 0:
                        _parts.append(_arr)
            if not _parts:
                return None
            _audio = _np.concatenate(_parts).astype(np.float32) / 32768.0
            _log(f"Piper backup OK ({len(_audio)/_PIPER_SR:.1f}s)")
            return _audio, _PIPER_SR
        except Exception as e:
            _log(f"Piper backup xato: {repr(e)}")
            return None

    def _fetch_audio_backup(self, text: str) -> Optional[tuple]:
        """Birinchi engine ishlamasa — boshqa Edge ovozlar, keyin Piper (rus)."""
        prev = self._session_engine
        tried = {self._session_engine} if self._session_engine else set()
        for _alt in _edge_voice_candidates():
            if _alt in tried:
                continue
            tried.add(_alt)
            try:
                decoded = self._edge_tts_fetch_one((text or "")[:4096], _alt)
                if decoded:
                    self._session_engine = "edge_alt"
                    return decoded
            except Exception as e:
                _log(f"Edge backup voice xato ({_alt}): {repr(e)}")

        if _tts_ui_lang() != "en":
            self._session_engine = "piper"
            data = self._fetch_piper_only(text)
            if data:
                return data
        self._session_engine = prev
        return None

    def _play_audio_block(self, audio: np.ndarray, sr: int) -> float:
        """Bitta audio blokini TO'LIQ chaladi (OutputStream — Windows da ishonchli)."""
        if audio is None or len(audio) == 0 or sr <= 0:
            return 0.0
        if self.out_dev is not None:
            try:
                sd.default.device = (None, int(self.out_dev))
            except Exception:
                pass
        target_sr = _device_target_samplerate(self.out_dev, sr)
        if target_sr != sr:
            audio, sr = _resample_audio(audio, sr, target_sr)
        _gain = float(os.getenv("TTS_VOLUME_GAIN", "2.0") or "2.0")
        if _gain != 1.0 and _gain > 0:
            audio = np.clip(audio * _gain, -1.0, 1.0)
        flat = np.asarray(audio, dtype=np.float32).flatten()
        expected = len(flat) / float(sr)
        peak = float(np.max(np.abs(flat))) if len(flat) else 0.0
        if expected < 0.05:
            return 0.0

        # Windows: avval sd.play (ba'zi drayverlarda OutputStream jim qoladi)
        if _use_simple_playback() and os.name == "nt":
            try:
                sd.play(flat, int(sr), device=self.out_dev)
                deadline = time.monotonic() + expected + 1.0
                while time.monotonic() < deadline:
                    if self._interrupt:
                        sd.stop()
                        print("[TTS] uzildi (sd.play)", flush=True)
                        return 0.0
                    try:
                        st = sd.get_stream()
                        if st is None or not st.active:
                            break
                    except Exception:
                        break
                    time.sleep(0.04)
                if not self._interrupt:
                    sd.wait()
                played = expected if not self._interrupt else 0.0
                time.sleep(0.06)
                print(
                    f"[TTS] o'ynaldi: {played:.1f}s peak={peak:.2f} dev={self.out_dev} sr={sr}",
                    flush=True,
                )
                return played
            except Exception as e:
                print(f"[TTS] sd.play xato: {e!r} — OutputStream sinanmoqda", flush=True)

        stream = None
        try:
            stream = sd.OutputStream(
                samplerate=int(sr),
                channels=1,
                device=self.out_dev,
                dtype="float32",
                blocksize=0,
            )
            stream.start()
            self._active_stream = stream
            block = max(2048, int(sr * 0.08))
            for start in range(0, len(flat), block):
                if self._interrupt:
                    stream.abort()
                    self._active_stream = None
                    print(f"[TTS] uzildi {start/len(flat)*100:.0f}% da", flush=True)
                    return (start / len(flat)) * expected
                stream.write(flat[start : start + block])
            if not self._interrupt:
                stream.stop()  # bufer tugaguncha kutadi — to'liq ovoz
            else:
                stream.abort()
        except Exception as e:
            print(f"[TTS] OutputStream xato: {e!r}", flush=True)
            try:
                sd.play(flat, int(sr), device=self.out_dev)
                sd.wait()
            except Exception as e2:
                print(f"[TTS] sd.play fallback xato: {e2!r}", flush=True)
                return 0.0
        finally:
            self._active_stream = None
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

        played = expected if not self._interrupt else 0.0
        print(
            f"[TTS] o'ynaldi: {played:.1f}s peak={peak:.2f} dev={self.out_dev} sr={sr}",
            flush=True,
        )
        return played

    def say_finish_backup(self, text: str) -> bool:
        """Ikkinchi ovoz — birinchi to'xtasa yoki qisqarsa qolgan matnni tugatadi."""
        t = (text or "").strip()
        if not t or len(t) < 3:
            return False
        if _tts_ui_lang() == "en":
            print(f"[TTS] SECOND VOICE — finishing ({len(t)} chars)", flush=True)
        else:
            print(f"[TTS] IKKINCHI OVOZ — tugatish ({len(t)} belgi)", flush=True)
        if not self._say_lock.acquire(timeout=90.0):
            print("[TTS] backup lock timeout", flush=True)
            return False
        played_ok = False
        try:
            self._interrupt = False
            self._busy.set()
            data = self._fetch_audio_backup(t)
            if not data:
                data = self._fetch_audio(t)
            if data:
                dur = self._play_audio_block(data[0], data[1])
                played_ok = dur > 0.05
        except Exception as _bfe:
            print(f"[TTS] backup xato: {_bfe!r}", flush=True)
        finally:
            self._busy.clear()
            self._last_end = time.monotonic()
            self._say_lock.release()
            if played_ok:
                print(f"[TTS] tugadi: OK (backup, dev={self.out_dev})", flush=True)
        return played_ok

    def _dual_finish_speech(self, full_text: str, chunks: List[str], stats: dict) -> None:
        """
        Offline demo kabi: birinchi ovoz erta tugasa yoki chunk o'tkazilsa —
        ikkinchi engine qolgan matnni tugatadi.
        """
        if self._interrupt or not stats:
            return
        missed = list(stats.get("missed_indices") or [])
        played = float(stats.get("played_sec") or 0)
        expected = float(stats.get("expected_sec") or 0)

        remainder = ""
        if missed:
            remainder = " ".join((chunks[i] or "").strip() for i in missed if i < len(chunks)).strip()
        elif expected > 0.4 and played < expected * 0.82:
            ratio = min(0.97, max(0.0, played / expected))
            cut = int(len(full_text) * ratio)
            remainder = full_text[cut:].strip(" .,;:")
            if remainder:
                for sep in (". ", "! ", "? ", "; "):
                    si = remainder.find(sep)
                    if 0 <= si < 48:
                        remainder = remainder[si + len(sep) :].strip()
                        break

        if not remainder or len(remainder) < 3:
            return

        if _tts_ui_lang() == "en":
            print(f"[TTS] SECOND VOICE — completing ({len(remainder)} chars)", flush=True)
        else:
            print(f"[TTS] IKKINCHI OVOZ — tugatish ({len(remainder)} belgi)", flush=True)
        was_int = self._interrupt
        self._interrupt = False
        data = self._fetch_audio_backup(remainder)
        if not data:
            data = self._fetch_audio(remainder)
        if data:
            self._play_audio_block(data[0], data[1])
        self._interrupt = was_int

    def _play_with_prefetch(self, chunks: List[str]):
        """
        Parallel pre-fetch + gapless OutputStream playback.

        - Har chunk alohida thread da fetch qilinadi (parallel)
        - Natijalar dict da saqlandi — tartibi DOIM to'g'ri
        - sd.OutputStream — bitta ochiq stream, chunklar orasida qurilma yopilmaydi
        - _interrupt har 50ms da tekshiriladi (chunk o'rtasida ham to'xtatish mumkin)
        """
        if not chunks:
            return {"chunks_total": 0, "chunks_played": 0, "expected_sec": 0.0, "played_sec": 0.0, "missed_indices": []}

        n = len(chunks)
        stats = {
            "chunks_total": n,
            "chunks_played": 0,
            "expected_sec": 0.0,
            "played_sec": 0.0,
            "missed_indices": [],
        }
        results: dict = {}
        results_lock = threading.Lock()
        results_event = threading.Event()

        def _worker(idx: int):
            if idx >= n or self._interrupt:
                with results_lock:
                    results[idx] = None
                results_event.set()
                return
            _log(f"chunk {idx+1}/{n} fetch boshlanmoqda...")
            if idx == 0:
                _load = "loading audio" if _tts_ui_lang() == "en" else "audio yuklanmoqda"
                print(f"[TTS] {_load} (part {idx+1}/{n})...", flush=True)
            t0 = time.monotonic()
            try:
                data = self._fetch_audio(chunks[idx])
            except Exception as e:
                _log(f"chunk {idx+1}/{n} fetch EXCEPTION: {repr(e)}")
                data = None
            elapsed = time.monotonic() - t0
            if data is None:
                _log(f"chunk {idx+1}/{n} fetch MUVAFFAQIYATSIZ ({elapsed:.1f}s)")
            else:
                _log(f"chunk {idx+1}/{n} fetch OK ({elapsed:.1f}s, {len(data[0])} sample, {data[1]}Hz)")
            with results_lock:
                results[idx] = data
            results_event.set()

        # Birinchi ikki chunk ni darhol boshlash
        threading.Thread(target=_worker, args=(0,), daemon=True).start()
        if n > 1:
            threading.Thread(target=_worker, args=(1,), daemon=True).start()

        stream = None

        for i in range(n):
            if self._interrupt:
                break

            # Chunk i+2 ni fonda boshlash (i+1 hali fetch bo'lmoqda)
            if i + 2 < n:
                threading.Thread(target=_worker, args=(i + 2,), daemon=True).start()

            # Aynan chunk i ni kuting (boshqa chunkni emas)
            # Oxirgi chunklar uchun biroz ko'proq vaqt (kesilmasin)
            deadline = time.monotonic() + (45 if i == n - 1 else 30)
            audio_data = None
            while True:
                if self._interrupt:
                    break
                with results_lock:
                    if i in results:
                        audio_data = results.pop(i)
                        break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    print(f"[TTS] chunk {i}/{n} timeout — o'tkazib yuborilmoqda", flush=True)
                    break
                results_event.wait(timeout=min(0.05, remaining))
                results_event.clear()

            if self._interrupt:
                _log(f"chunk {i+1}/{n} kutish paytida interrupt — to'xtatildi")
                break
            if audio_data is None:
                _log(f"chunk {i+1}/{n} backup engine sinanmoqda...")
                audio_data = self._fetch_audio_backup(chunks[i])
            if audio_data is None:
                _log(f"chunk {i+1}/{n} o'tkazib yuborildi (fetch failed)")
                stats["missed_indices"].append(i)
                if i == 0:
                    print("[TTS] OVOZ XATO: Edge/Piper ishlamadi — bat da: pip install av edge-tts", flush=True)
                continue

            audio, sr = audio_data
            chunk_expected = len(audio) / float(sr) if sr else 0
            stats["expected_sec"] += chunk_expected
            _log(f"chunk {i+1}/{n} o'ynalmoqda ({chunk_expected:.2f}s audio)")

            if _use_simple_playback():
                dur = self._play_audio_block(audio, sr)
                stats["played_sec"] += dur
                if not self._interrupt:
                    stats["chunks_played"] += 1
                if i + 1 < n and not self._interrupt:
                    time.sleep(0.02)
                continue

            # Birinchi chunkda stream ochiladi — keyingilar uchun ham shu stream
            if stream is None:
                try:
                    stream = sd.OutputStream(
                        samplerate=sr,
                        channels=1,
                        device=self.out_dev,
                        dtype='float32',
                    )
                    stream.start()
                    self._active_stream = stream
                    _log(f"OutputStream ochildi (sr={sr}, dev={self.out_dev})")
                except Exception as e:
                    _log(f"OutputStream ochib bo'lmadi: {repr(e)} — sd.play() fallback")
                    # Fallback: eski sd.play() usuli
                    try:
                        sd.play(audio, sr, device=self.out_dev, blocking=True)
                        _log(f"sd.play() fallback OK")
                    except Exception as pe:
                        _log(f"sd.play() fallback XATO: {repr(pe)}")
                        break
                    if i + 1 < n and not self._interrupt:
                        time.sleep(0.02)
                    continue

            # Audio ni 50ms bloklarda yozamiz — _interrupt har blokda tekshiriladi
            flat = audio if audio.ndim == 1 else audio.flatten()
            block_size = max(512, int(sr * 0.05))  # 50ms

            for start in range(0, len(flat), block_size):
                if self._interrupt:
                    _log(f"chunk {i+1}/{n} o'rtasida interrupt — stream.abort()")
                    break
                block = flat[start:start + block_size]
                try:
                    stream.write(block)
                except Exception as e:
                    _log(f"stream.write XATO: {repr(e)}")
                    self._interrupt = True
                    break

        # Tozalash
        self._active_stream = None
        if stream is not None:
            try:
                if not self._interrupt:
                    _log("stream.stop() — bufer tugashini kutmoqda...")
                    stream.stop()
                    try:
                        sd.wait()
                    except Exception:
                        pass
                    _log("stream.stop() OK")
                    print(f"[TTS] o'ynaldi (stream) dev={self.out_dev}", flush=True)
                else:
                    stream.abort()  # Darhol to'xtatadi
            except Exception as e:
                _log(f"stream cleanup xato: {repr(e)}")
            try:
                stream.close()
            except Exception:
                pass

        return stats
