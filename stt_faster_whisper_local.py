# -*- coding: utf-8 -*-
"""
NeuroKey — Lokal offline STT: faster-whisper (Whisper tiny/base model).

OpenAI API yo'q bo'lganda Vosk small dan ko'ra ANCHA yaxshi aniqlik beradi:
  tiny  model  ~74MB  — tez, aniqlik ~80%
  base  model ~148MB  — yaxshiroq, aniqlik ~85%
  small model ~488MB  — eng yaxshi, aniqlik ~90%

Birinchi marta ishlaganda model internet orqali yuklanadi.
Keyingi safar cache dan o'qiladi (~/.cache/huggingface/).
"""
from __future__ import annotations

import io
import os
import time
import numpy as np
import threading
from typing import Optional

try:
    import sounddevice as sd
except ImportError:
    sd = None

# If faster-whisper is not installed, fail the import here so main.py falls back to VOSK
from faster_whisper import WhisperModel

_FW_MODEL = None
_FW_LOCK = threading.Lock()
_FW_MODEL_SIZE = os.getenv("FASTER_WHISPER_MODEL", "base").strip() or "base"
# base = 148MB, tiny = 74MB, small = 488MB
# compute_type: int8 = tezroq, float16 = aniqroq (GPU bor bo'lsa)


def _get_model():
    """Model singleton — birinchi chaqiruvda yuklanadi.
    GPU (CUDA) birinchi sinaydi — RTX 5070 (sm_120) CTranslate2 bilan ishlaydi!
    GPU ishlamasa CPU int8 ga fallback.
    """
    global _FW_MODEL
    with _FW_LOCK:
        if _FW_MODEL is not None:
            return _FW_MODEL
        try:
            # GPU sinash (CTranslate2 sm_120 qo'llaydi, PyTorch qo'llamasa ham)
            _use_gpu = os.getenv("FASTER_WHISPER_DEVICE", "cuda").strip().lower()
            if _use_gpu in ("cuda", "gpu", "auto"):
                try:
                    t0 = time.monotonic()
                    print(f"[FW-STT] GPU (CUDA float16) sinaydi...", flush=True)
                    _FW_MODEL = WhisperModel(
                        _FW_MODEL_SIZE, device="cuda", compute_type="float16"
                    )
                    print(f"[FW-STT] GPU model yuklandi: {time.monotonic()-t0:.1f}s ✓", flush=True)
                    return _FW_MODEL
                except Exception as _gpu_e:
                    print(f"[FW-STT] GPU ishlamadi ({_gpu_e}) — CPU ga fallback.", flush=True)
                    _FW_MODEL = None
            # CPU fallback
            print(f"[FW-STT] CPU (int8) yuklanmoqda: {_FW_MODEL_SIZE}...", flush=True)
            t0 = time.monotonic()
            _FW_MODEL = WhisperModel(_FW_MODEL_SIZE, device="cpu", compute_type="int8")
            print(f"[FW-STT] CPU model yuklandi: {time.monotonic()-t0:.1f}s", flush=True)
            return _FW_MODEL
        except Exception as e:
            print(f"[FW-STT] Model yuklanmadi: {e}", flush=True)
            return None


def transcribe_audio(audio_int16: np.ndarray, sr: int = 16000, lang: str = "ru") -> str:
    """
    Audio (numpy int16 array) ni matnга o'giradi.
    Vosk transcribe_audio() ga drop-in replacement sifatida ishlatiladi.
    """
    model = _get_model()
    if model is None:
        return ""
    try:
        # int16 → float32 normalizatsiya
        audio_f32 = audio_int16.astype(np.float32) / 32768.0
        if audio_f32.ndim == 2:
            audio_f32 = audio_f32.mean(axis=1)
        # faster-whisper float32 array dan to'g'ridan-to'g'ri o'qiydi
        segments, _info = model.transcribe(
            audio_f32,
            language=lang if lang != "auto" else None,
            beam_size=3,
            vad_filter=True,          # Ovoz bo'lmagan joylarni o'tkazib yuboradi
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        # Whisper gallyutsinatsiyalari — jimlik yoki shovqindan kelib chiqadi
        _hallucinations = (
            "продолжение следует", "субтитры сделаны", "субтитры",
            "subtitles by", "amara.org", "translation by", "transcribed by",
            "www.", ".com", "subscribe", "like and subscribe",
            "thanks for watching", "thank you for watching",
            "пожалуйста подпишитесь", "не забудьте подписаться",
        )
        if any(h in text.lower() for h in _hallucinations):
            return ""
        return text
    except Exception as e:
        print(f"[FW-STT] transcribe_audio xato: {e}", flush=True)
        return ""


def record_and_transcribe(
    input_device_index=None,
    lang: str = "ru",
    silence_rms: float = 0.012,
    silence_hold_sec: float = 2.5,
    max_sec: float = 35.0,
    on_barge_in=None,
    **kwargs
) -> str:
    """
    Mikrofon dan yozib, faster-whisper bilan matnga o'giradi.
    stt_openai_whisper.record_and_transcribe() ga drop-in replacement.
    """
    if sd is None:
        return ""

    SR = 16000
    BLOCK = int(SR * 0.03)  # 30ms

    import queue as _q
    q: _q.Queue = _q.Queue()

    def _cb(indata, frames, tinfo, status):
        q.put(indata.copy())

    chunks = []
    recording = False
    silent_since = None
    start_t = time.monotonic()

    try:
        with sd.InputStream(
            samplerate=SR, channels=1, dtype="int16",
            blocksize=BLOCK, device=input_device_index,
            callback=_cb,
        ):
            while True:
                elapsed = time.monotonic() - start_t
                if elapsed > max_sec:
                    break
                try:
                    block = q.get(timeout=0.1)
                except _q.Empty:
                    continue

                rms = float(np.sqrt(np.mean(block.astype(np.float32) ** 2))) / 32768.0

                if rms > silence_rms:
                    recording = True
                    silent_since = None
                    chunks.append(block)
                elif recording:
                    chunks.append(block)
                    if silent_since is None:
                        silent_since = time.monotonic()
                    elif time.monotonic() - silent_since > silence_hold_sec:
                        break  # Silence tugadi — yozishni to'xtat
    except Exception as e:
        print(f"[FW-STT] Mikrofon xato: {e}", flush=True)
        return ""

    if not chunks:
        return ""

    audio = np.concatenate(chunks, axis=0).flatten().astype(np.int16)
    duration = len(audio) / SR
    if duration < 0.3:
        return ""

    print(f"[FW-STT] {duration:.1f}s audio yozildi — matnga o'girilmoqda...", flush=True)
    return transcribe_audio(audio, SR, lang)


# Startup da fonda model yuklanadi (birinchi so'rovda kechikish bo'lmasin)
def _preload():
    try:
        _get_model()
    except Exception:
        pass

threading.Thread(target=_preload, daemon=True, name="fw-stt-preload").start()
