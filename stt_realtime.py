# -*- coding: utf-8 -*-
"""
NeuroKey — RealtimeSTT wrapper.
Gapirish bilan PARALLEL transkriptsiya → STT overhead: ~100-300ms
(vs oldingi: 700ms jim kutish + 325ms GPU = 1025ms)
"""
import os, time, threading
from typing import Optional

_recorder = None
_recorder_lock = threading.Lock()
_current_lang = None
_current_device = None


def _patch_silero_disabled():
    """
    silero-vad yuklanishini bloklash (SSL/GitHub xatosi bo'lsa).
    silero_sensitivity=0.0 bo'lgani uchun dummy model foydalanilmaydi —
    faqat WebRTC VAD ishlaydi.
    """
    try:
        import torch
        _orig_hub_load = torch.hub.load

        class _DummySileroModel:
            """Hech qachon speech aniqlamaydigan stub (sensitivity=0 bilan mos)."""
            def __call__(self, audio_chunk, sample_rate=16000):
                return torch.tensor(0.0)  # 0.0 < (1 - 0.0 = 1.0) → speech yo'q

        def _safe_hub_load(repo_or_dir, model_name=None, *args, **kwargs):
            if "silero" in str(repo_or_dir).lower():
                return _DummySileroModel(), None
            return _orig_hub_load(repo_or_dir, model_name, *args, **kwargs)

        torch.hub.load = _safe_hub_load
    except Exception:
        pass


def _make_recorder(lang: str = "ru", device_index=None):
    # Barcha debug/info loglarni o'chirish
    import logging, warnings
    warnings.filterwarnings("ignore")
    for name in ("RealtimeSTT", "realtimestt", "RealTimeSTT",
                 "faster_whisper", "silero", "openwakeword",
                 "torch", "urllib3", "requests"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    logging.getLogger().setLevel(logging.CRITICAL)

    # silero yuklanishini bloklash (SSL xatosi bor, demo uchun kerak emas)
    _patch_silero_disabled()

    from RealtimeSTT import AudioToTextRecorder

    # GPU ishlatish (RTX 5070 CUDA)
    use_gpu = os.getenv("FASTER_WHISPER_DEVICE", "cuda").lower() in ("cuda", "gpu")
    compute = "float16" if use_gpu else "int8"
    device   = "cuda"   if use_gpu else "cpu"

    rec = AudioToTextRecorder(
        # Asosiy model — final transkriptsiya uchun
        model                          = os.getenv("FASTER_WHISPER_MODEL", "base"),
        language                       = lang,
        device                         = device,
        compute_type                   = compute,

        # Real-vaqt model — gapirayotganda ko'rsatish uchun (kichikroq)
        enable_realtime_transcription  = True,
        realtime_model_type            = "tiny",
        realtime_processing_pause      = 0.1,   # har 100ms yangilanadi

        # VAD sozlamalari
        # silero=0 → faqat WebRTC VAD (silero SSL yuklab bo'lmaydi)
        silero_sensitivity             = 0.0,
        webrtc_sensitivity             = 1,     # 0=eng sezgir, 3=eng qattiq. 1 = demo uchun optimal
        post_speech_silence_duration   = 0.5,   # 500ms jimlik = gap tugadi
        min_length_of_recording        = 0.2,   # 200ms dan qisqa = tasodifiy shovqin
        min_gap_between_recordings     = 0.1,

        # UI — spinner va debug chiqmassin
        spinner                        = False,
        level                          = 50,    # logging.CRITICAL = 50, hamma log o'chadi
        debug_mode                     = False,

        # Qurilma
        input_device_index             = device_index,

        # Wake word O'CHIRILGAN — demo rejimda kerak emas
        wake_words                     = "",
    )
    return rec


def get_recorder(lang: str = "ru", device_index=None):
    """Singleton recorder — bir marta yaratiladi, qayta ishlatiladi."""
    global _recorder, _current_lang, _current_device
    with _recorder_lock:
        if (_recorder is None
                or _current_lang != lang
                or _current_device != device_index):
            if _recorder is not None:
                try:
                    _recorder.stop()
                except Exception:
                    pass
            print(f"[RealtimeSTT] Recorder yaratilmoqda (lang={lang}, device={device_index})...",
                  flush=True)
            t0 = time.monotonic()
            _recorder = _make_recorder(lang=lang, device_index=device_index)
            _current_lang = lang
            _current_device = device_index
            print(f"[RealtimeSTT] Tayyor: {(time.monotonic()-t0)*1000:.0f}ms", flush=True)
    return _recorder


def record_and_transcribe(
    lang: str = "ru",
    device_index=None,
    on_realtime_update=None,   # ixtiyoriy: real-vaqt matn callback
    tts_is_playing=None,       # TTS gapirayotganda kutish
    **kwargs,
) -> str:
    """
    Mikrofon dan gapirish → parallel STT → matn.
    TTS gapirayotganda kirmaydi (echo bloklash).
    """
    # TTS band bo'lsa — max 8s kutamiz (stuck bo'lib qolmasin)
    if callable(tts_is_playing):
        _tts_wait_start = time.monotonic()
        while tts_is_playing():
            time.sleep(0.02)
            if time.monotonic() - _tts_wait_start > 8.0:
                break  # 8s dan oshsa — baribir tinglashni boshlaymiz

    rec = get_recorder(lang=lang, device_index=device_index)

    if on_realtime_update is not None:
        rec.on_realtime_transcription_update = on_realtime_update

    try:
        text = rec.text()
        return (text or "").strip()
    except Exception as e:
        print(f"[RealtimeSTT] xato: {e}", flush=True)
        return ""


def preload(lang: str = "ru", device_index=None):
    """Startup da fonda yuklab olish — birinchi so'rovda kechikish bo'lmasin."""
    def _load():
        try:
            get_recorder(lang=lang, device_index=device_index)
        except Exception as e:
            print(f"[RealtimeSTT] preload xato: {e}", flush=True)
    threading.Thread(target=_load, daemon=True, name="realtime-stt-preload").start()
