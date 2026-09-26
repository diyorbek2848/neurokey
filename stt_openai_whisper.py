# -*- coding: utf-8 -*-
"""
OpenAI Whisper STT for NeuroKey/Juma.

When STT_LANGUAGE=en: only English; long utterances use STT_MAX_UTTERANCE_SEC / STT_SILENCE_HOLD_SEC.

Usage (minimal):
    from stt_openai_whisper import record_and_transcribe
    text = record_and_transcribe(input_device_index=C.INPUT_DEVICE_INDEX)

This module records a single utterance with a simple RMS-based VAD.
"""

import os
import time
import tempfile
from typing import Optional, Tuple

import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from openai import OpenAI


DEFAULT_SR = 16000
DEFAULT_CHANNELS = 1

# --- VAD parametrlari ---
SILENCE_RMS = 0.012        # sezuvchanlik: 0.008-0.015
SILENCE_HOLD_SEC = 3.0     # jim qolgandan keyin qancha kutish
MAX_UTTERANCE_SEC = 35.0   # maksimal yozib olish vaqti
MIN_UTTERANCE_SEC = 0.55   # juda qisqa (shovqin) — o'tkazib yuborish

_client = None
_client_key = ""
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def _load_key_and_url_from_env():
    """Har safar .env dan o'qiydi — restart kerak emas.
    Groq base URL bo'lsa — GROQ_API_KEY ishlatiladi (Whisper bepul)."""
    groq_key = ""
    openai_key = ""
    base_url = ""
    try:
        if os.path.isfile(_ENV_PATH):
            with open(_ENV_PATH, encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line.startswith("#"):
                        continue
                    if _line.startswith("GROQ_API_KEY="):
                        _k = _line.split("=", 1)[1].strip().strip('"').strip("'")
                        if _k and len(_k) > 10:
                            groq_key = _k
                    elif _line.startswith("OPENAI_API_KEY="):
                        _k = _line.split("=", 1)[1].strip().strip('"').strip("'")
                        if _k and not _k.startswith("your_") and not _k.startswith("sk-...") and len(_k) > 20:
                            openai_key = _k
                    elif _line.startswith("OPENAI_BASE_URL="):
                        base_url = _line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    if not base_url:
        base_url = os.environ.get("OPENAI_BASE_URL", "")
    # Groq Whisper — bepul, tez
    if "groq.com" in base_url:
        gk = groq_key or os.environ.get("GROQ_API_KEY", "")
        if gk:
            return gk, "https://api.groq.com/openai/v1"
    key = openai_key or os.environ.get("OPENAI_API_KEY", "") or ""
    return key, ""

def _load_key_from_env() -> str:
    key, _ = _load_key_and_url_from_env()
    return key

def _get_client():
    """Har safar .env dan yangi kalit o'qiydi — hot-reload. Groq Whisper qo'llab-quvvatlaydi."""
    global _client, _client_key
    key, base_url = _load_key_and_url_from_env()
    cache_id = f"{key}|{base_url}"
    if _client is None or cache_id != _client_key:
        if base_url:
            _client = OpenAI(api_key=key, base_url=base_url)
        else:
            _client = OpenAI(api_key=key)
        _client_key = cache_id
    return _client

def _stt_language():
    try:
        import config as C
        return (getattr(C, "STT_LANGUAGE", None) or "ru").strip().lower() or "ru"
    except Exception:
        return "ru"


def _rms(x: np.ndarray) -> float:
    x = x.astype(np.float32)
    return float(np.sqrt(np.mean(x * x)) + 1e-9)


def record_utterance(
    input_device_index: Optional[int] = None,
    sr: int = DEFAULT_SR,
    channels: int = DEFAULT_CHANNELS,
    silence_rms: float = SILENCE_RMS,
    silence_hold_sec: float = SILENCE_HOLD_SEC,
    max_sec: float = MAX_UTTERANCE_SEC,
    tts_is_playing=None,
    on_barge_in=None,
    on_speech_start=None,
    barge_in_rms: Optional[float] = None,
    pause_during_tts: bool = False,
) -> Tuple[np.ndarray, int]:
    """
    Listen and capture one utterance:
    - wait until sound >= silence_rms to "start"
    - stop when silence persists for silence_hold_sec
    - or max_sec reached
    Returns: int16 audio array (N, channels), sample rate
    """
    block_ms = 30
    block = int(sr * block_ms / 1000)

    started = False
    silence_start = None
    frames = []
    start_time = time.time()
    _tts_busy_since = None
    _tts_busy_warned = -1

    with sd.InputStream(
        device=input_device_index,
        samplerate=sr,
        channels=channels,
        dtype="int16",
        blocksize=block,
    ) as stream:
        while True:
            data, _ = stream.read(block)

            # int16 -> float mono
            mono = data[:, 0].astype(np.float32) / 32768.0
            level = _rms(mono)
            now = time.time()

            # TTS band bo'lsa — mikrofon ochiq bo'lsa ham frameni SAQLAMAYMIZ
            # Bu echo/feedback ni to'liq bloklaydi
            try:
                tts_busy = tts_is_playing() if callable(tts_is_playing) else bool(tts_is_playing)
            except Exception:
                tts_busy = False

            if tts_busy:
                # DIAGNOSTIKA + XAVFSIZLIK TARMOG'I (2026-09-13, real bug topildi):
                # ilgari bu tarmoqda `continue` pastdagi max_sec tekshiruvidan
                # OLDIN ishlardi — ya'ni tts_is_playing() biror sababdan (masalan
                # tts_openai.py.say() ichida osilib qolgan network chaqiruv)
                # ABADIY True qaytarsa, bu while-loop CHEKSIZ aylanardi: hech
                # qachon max_sec ga yetmasdi, hech qanday log chiqmasdi — "STT
                # umuman ishlamayapti" ko'rinishi aynan shu yerdan kelib chiqardi.
                # Asosiy tuzatish main.py'dagi tashqi `while tts.is_playing()`
                # darvozasida (u yerda ham diagnostika qo'shildi), lekin bu
                # funksiya boshqa joydan (masalan offline-rejim) to'g'ridan-to'g'ri
                # chaqirilsa ham himoyalanishi uchun shu yerga ham mustaqil
                # xavfsizlik chegarasi va log qo'shildi.
                if _tts_busy_since is None:
                    _tts_busy_since = now
                _busy_el = now - _tts_busy_since
                if _busy_el > 10.0:
                    _bucket = int(_busy_el) // 15
                    if _bucket != _tts_busy_warned:
                        _tts_busy_warned = _bucket
                        print(
                            f"[STT] DIQQAT: mikrofon {_busy_el:.0f}s dan beri TTS bandligi "
                            f"sabab kutmoqda (tts_is_playing()=True) — agar bu ancha davom "
                            f"etsa, TTS o'zi osilib qolgan bo'lishi mumkin.",
                            flush=True,
                        )
                # Mutlaq xavfsizlik chegarasi: TTS haqiqatan ham abadiy osilib
                # qolgan bo'lsa ham, mikrofon funksiyasi abadiy qulflanib
                # qolmasin — max_sec ning 4 barobaridan keyin (yoki kamida 120s)
                # baribir chiqib ketamiz, bo'sh audio qaytarib chaqiruvchiga
                # nazoratni beramiz.
                if (now - start_time) >= max(max_sec * 4.0, 120.0):
                    print(
                        f"[STT] TTS {_busy_el:.0f}s dan beri band — xavfsizlik chegarasi "
                        f"({max(max_sec * 4.0, 120.0):.0f}s) ga yetdi, mikrofon funksiyasi "
                        f"bo'sh natija bilan chiqmoqda.",
                        flush=True,
                    )
                    break
                # TTS gapirayotganda — hech narsa qilmaymiz, faqat kutamiz
                # Barge-in — faqat juda baland ovozda (foydalanuvchi aniq gapirsa)
                if (callable(on_barge_in) and not pause_during_tts
                        and barge_in_rms is not None and level >= barge_in_rms):
                    try:
                        on_barge_in()
                    except Exception:
                        pass
                    time.sleep(0.08)
                continue  # TTS band → bu frameni o'tkazib yuboramiz
            else:
                _tts_busy_since = None
                _tts_busy_warned = -1

            # TTS band emas — odatdagi yozib olish
            frames.append(data.copy())

            if not started and level >= silence_rms:
                if callable(on_speech_start):
                    try:
                        on_speech_start()
                    except Exception:
                        pass
                started = True
                silence_start = None

            if started:
                if level < silence_rms:
                    if silence_start is None:
                        silence_start = now
                    elif (now - silence_start) >= silence_hold_sec:
                        break
                else:
                    silence_start = None

            if (now - start_time) >= max_sec:
                break

    if not frames:
        # Xavfsizlik chegarasi frame yozilmasdan turib chiqqan bo'lishi mumkin
        # (masalan yuqoridagi TTS-band abadiy osilib qolish holati) — bo'sh
        # massiv bilan np.concatenate ValueError berardi.
        return np.zeros((0, channels), dtype=np.int16), sr
    audio = np.concatenate(frames, axis=0)
    return audio, sr


def whisper_transcribe_int16(audio_int16: np.ndarray, sr: int) -> str:
    if audio_int16 is None or len(audio_int16) == 0:
        return ""

    if audio_int16.ndim == 2:
        audio_mono = audio_int16[:, 0]
    else:
        audio_mono = audio_int16

    dur = len(audio_mono) / float(sr)
    if dur < MIN_UTTERANCE_SEC:
        return ""

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    wavfile.write(wav_path, sr, audio_mono)

    try:
        lang = _stt_language()
        _, _base = _load_key_and_url_from_env()
        # Groq Whisper → whisper-large-v3-turbo (bepul, tez, ko'p til)
        _model = "whisper-large-v3-turbo" if "groq.com" in (_base or "") else "whisper-1"
        with open(wav_path, "rb") as f:
            kwargs = {"model": _model, "file": f}
            if lang in ("en", "ru", "es", "fr", "de", "it", "pt", "tr", "uk", "uz"):
                kwargs["language"] = lang
            r = _get_client().audio.transcriptions.create(**kwargs)
        return (r.text or "").strip()
    except Exception as _e:
        _estr = str(_e).lower()
        # Har qanday OpenAI API xatosida → Vosk ga fallback
        # (429 quota, 401 auth, connection error, timeout, network, offline)
        _api_fail = any(x in _estr for x in (
            "429", "quota", "insufficient", "ratelimit", "rate limit",
            "401", "authentication", "invalid api key", "incorrect api",
            "404", "not found", "model_not_found", "does not exist",
            "connection", "timeout", "network", "unreachable",
            "503", "502", "failed to connect", "apiconnectionerror",
            "connecterror", "nodename", "name or service",
        ))
        if _api_fail:
            # 1) faster-whisper lokal (aniqroq, offline)
            try:
                from stt_faster_whisper_local import transcribe_audio as _fw_transcribe
                import os as _os
                _fw_lang = (_os.getenv("STT_LANGUAGE", "ru") or "ru").strip().lower()
                _fw_result = _fw_transcribe(audio_mono, sr, lang=_fw_lang)
                if _fw_result:
                    return _fw_result
            except Exception:
                pass
            # 2) Vosk (fallback)
            try:
                from stt_vosk import transcribe_audio as _vosk_transcribe
                _vosk_result = _vosk_transcribe(audio_mono, sr)
                return _vosk_result or ""
            except Exception:
                pass
            return ""
        raise
    finally:
        try:
            os.remove(wav_path)
        except Exception:
            pass


def record_and_transcribe(
    input_device_index: Optional[int] = None,
    sr: int = DEFAULT_SR,
    channels: int = DEFAULT_CHANNELS,
    silence_rms: Optional[float] = None,
    silence_hold_sec: Optional[float] = None,
    max_sec: Optional[float] = None,
    tts_is_playing=None,
    on_barge_in=None,
    on_speech_start=None,
    barge_in_rms: Optional[float] = None,
    pause_during_tts: Optional[bool] = None,
) -> str:
    try:
        import config as C
        _max = getattr(C, "STT_MAX_UTTERANCE_SEC", None)
        _hold = getattr(C, "STT_SILENCE_HOLD_SEC", None)
        _rms = getattr(C, "STT_SILENCE_RMS", None)
        _barge_rms = getattr(C, "STT_BARGE_IN_RMS", None)
        _pause = getattr(C, "STT_PAUSE_DURING_TTS", False)
        if _max is not None and max_sec is None:
            max_sec = float(_max)
        if _hold is not None and silence_hold_sec is None:
            silence_hold_sec = float(_hold)
        if _rms is not None and silence_rms is None:
            silence_rms = float(_rms)
        if _barge_rms is not None and barge_in_rms is None:
            barge_in_rms = float(_barge_rms)
        if pause_during_tts is None:
            pause_during_tts = _pause
    except Exception:
        pass
    audio, sr = record_utterance(
        input_device_index=input_device_index,
        sr=sr,
        channels=channels,
        silence_rms=(silence_rms if silence_rms is not None else SILENCE_RMS),
        silence_hold_sec=(silence_hold_sec if silence_hold_sec is not None else SILENCE_HOLD_SEC),
        max_sec=(max_sec if max_sec is not None else MAX_UTTERANCE_SEC),
        tts_is_playing=tts_is_playing,
        on_barge_in=on_barge_in,
        on_speech_start=on_speech_start,
        barge_in_rms=barge_in_rms,
        pause_during_tts=bool(pause_during_tts),
    )
    # Ovoz tanish — Whisper bilan parallel (sekinlashtirmaydi)
    try:
        import threading as _thr
        audio_f32 = audio.astype(np.float32) / 32768.0

        def _run_bio():
            # 1. Resemblyzer (mavjud)
            try:
                from voice_recognition import identify_speaker as _id_spk, _store_last
                _store_last(_id_spk(audio_f32, sample_rate=sr))
            except Exception:
                pass
            # 2. ECAPA-TDNN (yangi, aniqroq)
            try:
                from voice_ecapa import identify as _ecapa_id, _store_last as _ecapa_store
                _ecapa_store(_ecapa_id(audio_f32))
            except Exception:
                pass

        _thr.Thread(target=_run_bio, daemon=True).start()
    except Exception:
        pass
    raw = whisper_transcribe_int16(audio, sr)
    try:
        from stt_whisper_fix import fix_whisper_text
        return fix_whisper_text(raw)
    except Exception:
        return raw
