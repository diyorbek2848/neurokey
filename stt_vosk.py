# -*- coding: utf-8 -*-
import os, sys, re, time, json, queue, threading
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer

try:
    from neurokey_debug_log import log_stt as _log_stt
except Exception:
    def _log_stt(msg): pass  # STT loglash ixtiyoriy

from config import (
    VOSK_MODEL_DIR,
    TARGET_SR, BLOCKSIZE, PREFERRED_CHANNELS,
    INPUT_DEVICE_INDEX, AUTO_SELECT_AUDIO_DEVICE, MIC_NAME_HINTS,

    # anti-echo
    ECHO_SUPPRESS, DROP_WHILE_TTS, MUTE_AFTER_TTS_MS, VAD_RMS_GATE,
    MIN_PHRASE_CHARS,

    # shovqin izolyatsiya
    VAD_MIN_CONSECUTIVE, VAD_MIN_CONSEC_BARGE_IN, VAD_BARGE_IN_RMS,
    NOISE_FILTER_STRICT,

    # wake-logic
    REQUIRE_WAKE_WORD, WAKE_REGEX, PASS_THROUGH_AFTER_WAKE_SECONDS,
)

_VAD_GATE = float(VAD_RMS_GATE or 0.0)
_VAD_BARGE_RMS = float(VAD_BARGE_IN_RMS or 0.022)
_VAD_MIN_CONSEC = max(1, int(VAD_MIN_CONSECUTIVE or 1))
_VAD_MIN_BARGE = max(1, int(VAD_MIN_CONSEC_BARGE_IN or 1))
_MUTE_AFTER_SEC = float((MUTE_AFTER_TTS_MS or 0) / 1000.0)
_WAKE_RE = re.compile(WAKE_REGEX, re.IGNORECASE) if (WAKE_REGEX and isinstance(WAKE_REGEX, str)) else None

# Shovqin bo'lishi mumkin bo'lgan qisqa "so'zlar" — STT noto'g'ri tanishi, ignor qilamiz
_NOISE_LIKE = frozenset([
    "а", "э", "у", "о", "ы", "и", "е", "ё", "й", "a", "e", "o", "u", "i", "y",
    "ну", "ну ну", "ээ", "уу", "аа", "мм", "м", "н", "хм", "ах", "ох", "ух",
])
# Qisqa lekin haqiqiy javoblar — muammosiz o'tadi (NOISE_FILTER_STRICT=1 bo'lsa ham)
_VALID_SHORT = frozenset((
    "да", "ок", "ok", "no", "yes", "йес", "ноу", "нет", "ха", "ha", "yo'q", "yoq",
    "xo'p", "xop", "хорошо", "йоқ", "йўқ", "yo", "stop", "стоп", "йо",
))


def _is_likely_noise(text: str) -> bool:
    """Shovqin yoki noto'g'ri tanish — faqat gaplarni qoldiramiz. 'да', 'ок' kabi qisqa javoblar o'tadi."""
    if not text or not NOISE_FILTER_STRICT:
        return False
    t = text.strip()
    if len(t) < int(MIN_PHRASE_CHARS or 0):
        return True
    if t.lower().strip() in _VALID_SHORT:
        return False
    if t.lower() in _NOISE_LIKE:
        return True
    # Faqat unlilar — odatda shovqin
    if len(t) <= 4 and re.match(r"^[аэуоыиеёaeyiou\s]+$", t, re.I):
        return True
    # Bir xil harf 3+ marta — shovqin
    if re.search(r"(.)\1{2,}", t):
        return True
    # Juda qisqa raqamlar yoki belgilar
    if len(t) <= 2 and re.match(r"^[\d\s]+$", t):
        return True
    return False

def _list_devices():
    try:
        return list(sd.query_devices())
    except Exception:
        return []

def _pick_input_device():
    if INPUT_DEVICE_INDEX is not None:
        return INPUT_DEVICE_INDEX
    if not AUTO_SELECT_AUDIO_DEVICE:
        return None
    try:
        devs = sd.query_devices()
    except Exception:
        return None
    hints = [h.lower() for h in (MIC_NAME_HINTS or [])]
    for idx, d in enumerate(devs):
        if d.get("max_input_channels", 0) <= 0:
            continue
        name = (d.get("name") or "").lower()
        if any(h in name for h in hints):
            return idx
    return None

def _should_block_input(tts_is_playing, tts_last_end_time):
    if not ECHO_SUPPRESS:
        return False
    # TTS gapiryaptimi?
    if DROP_WHILE_TTS and tts_is_playing and tts_is_playing():
        return True
    # Tail mute
    if tts_last_end_time:
        le = tts_last_end_time()
        if le and (time.monotonic() - le) < _MUTE_AFTER_SEC:
            return True
    return False

_vosk_model_cache = None

def transcribe_audio(audio_int16: np.ndarray, sr: int) -> str:
    """One-shot transcription.
    Zanjir: 1) faster-whisper (aniqroq, offline)  →  2) Vosk (fallback)
    """
    # ── 1. faster-whisper (lokal, aniqroq) ───────────────────────────────────
    try:
        from stt_faster_whisper_local import transcribe_audio as _fw_transcribe
        _fw_lang = (os.getenv("STT_LANGUAGE", "ru") or "ru").strip().lower()
        _fw_result = _fw_transcribe(audio_int16, sr, lang=_fw_lang)
        if _fw_result:
            return _fw_result
    except Exception as _fw_e:
        pass  # faster-whisper ishlamadi — Vosk ga o'tamiz

    # ── 2. Vosk (fallback) ────────────────────────────────────────────────────
    global _vosk_model_cache
    try:
        if _vosk_model_cache is None:
            _vosk_model_cache = Model(VOSK_MODEL_DIR)
        rec = KaldiRecognizer(_vosk_model_cache, sr)
        rec.SetWords(False)
        if audio_int16.ndim == 2:
            audio_int16 = audio_int16[:, 0]
        data = audio_int16.astype(np.int16).tobytes()
        rec.AcceptWaveform(data)
        result = json.loads(rec.FinalResult())
        return (result.get("text") or "").strip()
    except Exception as _e:
        print(f"[VOSK] transcribe_audio xato: {_e}", flush=True)
        return ""


def run_stt(on_text, tts_is_playing=None, tts_last_end_time=None, on_barge_in=None):
    try:
        model = Model(VOSK_MODEL_DIR)
    except Exception as e:
        print(f"[VOSK] Model yuklanmadi: {e}", flush=True)
        return

    rec = KaldiRecognizer(model, TARGET_SR)
    rec.SetWords(True)

    _list_devices()
    dev_in = _pick_input_device()
    if dev_in is None:
        dev_in = INPUT_DEVICE_INDEX

    channels = int(PREFERRED_CHANNELS or 1)
    dtype = "int16"
    blocksize = int(BLOCKSIZE or 0)
    if blocksize < 0:
        blocksize = 0


    q = queue.Queue()

    awake_until = 0.0
    have_wake = not REQUIRE_WAKE_WORD

    def _maybe_wake(text: str) -> bool:
        nonlocal awake_until, have_wake
        if not REQUIRE_WAKE_WORD:
            return True
        if not text:
            return False
        if _WAKE_RE and _WAKE_RE.search(text):
            have_wake = True
            awake_until = time.monotonic() + float(PASS_THROUGH_AFTER_WAKE_SECONDS or 0.0)
            return True
        if have_wake and (time.monotonic() <= awake_until):
            return True
        return False

    _vad_consecutive = [0]  # ketma-ket bloklar yuqori ovoz — shovqin emas deb hisoblash
    _barge_in_called = [False]  # Master Priority Interrupt: bir marta chaqiriladi, TTS to'xtagach reset

    def _audio_callback(indata, frames, time_info, status):
        if status:
            return
        try:
            f32 = indata.astype(np.float32, copy=False)
            rms = float(np.sqrt(np.mean(f32 * f32)) if f32.size else 0.0)
        except Exception:
            rms = 0.0
        blocked = _should_block_input(tts_is_playing, tts_last_end_time)
        if not blocked:
            _barge_in_called[0] = False
        # TTS ijro paytida barge-in CHAQIRILMASIN — dinamik/TTS ovozini "foydalanuvchi" deb to'xtatmasin
        if blocked:
            _vad_consecutive[0] = 0
            return
        if _VAD_GATE > 0.0:
            if rms < _VAD_GATE:
                _vad_consecutive[0] = 0
            else:
                _vad_consecutive[0] += 1
                _barge_rms = _VAD_BARGE_RMS if _VAD_BARGE_RMS > 0 else _VAD_GATE
                if on_barge_in and rms >= _barge_rms and _vad_consecutive[0] >= _VAD_MIN_BARGE and not _barge_in_called[0]:
                    try:
                        on_barge_in()
                        _barge_in_called[0] = True
                    except Exception:
                        pass
                if _vad_consecutive[0] < _VAD_MIN_BARGE:
                    return
        try:
            q.put(bytes(indata))
        except Exception:
            pass

    try:
        stream = sd.InputStream(
            samplerate=TARGET_SR,
            channels=channels,
            dtype=dtype,
            blocksize=blocksize if blocksize > 0 else None,
            device=dev_in,
            callback=_audio_callback,
        )
        stream.start()
    except Exception as e:
        print(f"[AUDIO] Stream start xato: {e}")
        return


    _was_blocked = [False]

    # VOSK gap oxirini kutish o'rniga: partial matn N ms barqaror bo'lsa — erta yakunlash (demo tezligi).
    try:
        _stab_ms = float((os.getenv("NEUROKEY_VOSK_STABLE_PARTIAL_MS", "") or "0").strip() or 0)
    except ValueError:
        _stab_ms = 0.0
    _stab_sec = max(0.15, min(2.5, _stab_ms / 1000.0)) if _stab_ms > 0 else 0.0
    _stab_text = [""]
    _stab_since = [0.0]

    # SPEKULYATIV OLDINDAN JAVOB (2026-09-11, asoschi so'roviga ko'ra):
    # foydalanuvchi HALI GAPINI TUGATMAGAN paytda — o'sib borayotgan partial
    # transkript asosida javob fon oqimda tayyorlana boshlaydi (odam ham
    # shunday: gap tugashini kutmay, eshitgan qismidan javob shakllantiradi).
    # Butunlay ixtiyoriy (NEUROKEY_SPECULATIVE_RESPONSE=1 bo'lmasa hech
    # narsa qilmaydi) — qarang speculative_response.py.
    try:
        from speculative_response import on_partial as _spec_on_partial, _enabled as _spec_enabled
    except Exception:
        _spec_on_partial = None
        _spec_enabled = lambda: False
    # Partial'ni FAQAT kerak bo'lganda so'raymiz — erta-yakunlash (_stab_sec)
    # yoki spekulyativ javob (_spec_enabled()) yoqilgan bo'lsa. Ikkalasi ham
    # o'chirilgan holatda (demo standart holati) VOSK'dan qo'shimcha
    # so'rov umuman qilinmaydi — xatti-harakat/tezlik o'zgarmaydi.
    _want_partial = (_stab_sec > 0) or _spec_enabled()

    def _emit_if_ok(text: str) -> None:
        if not text:
            return
        if not _maybe_wake(text):
            _log_stt(f"wake-word yo’q, skip: ‘{text}’")
            return
        if len(text) < int(MIN_PHRASE_CHARS or 0):
            _log_stt(f"juda qisqa, skip: ‘{text}’")
            return
        if _is_likely_noise(text):
            _log_stt(f"shovqin, skip: ‘{text}’")
            return
        _log_stt(f"TANILDI: ‘{text}’")
        try:
            import threading as _stt_thr
            _stt_thr.Thread(target=on_text, args=(text,), daemon=True).start()
        except Exception as e:
            print(f"[STT] on_text xato: {e}")

    def _worker():
        while True:
            try:
                # <<< ANTI-ECHO: agar hozir blok bo’lishi kerak bo’lsa — navbatni tozalab, reset qilamiz
                if _should_block_input(tts_is_playing, tts_last_end_time):
                    if not _was_blocked[0]:
                        _log_stt("BLOCKED (TTS gapiryapti — qulaqlash to’xtatildi)")
                        _was_blocked[0] = True
                    try:
                        while True:
                            _ = q.get_nowait()
                    except queue.Empty:
                        pass
                    rec.Reset()
                    _stab_text[0] = ""
                    _stab_since[0] = 0.0
                    time.sleep(0.01)
                    continue
                # >>>
                if _was_blocked[0]:
                    _log_stt("UNBLOCKED (TTS tugadi — qulaqlash boshlandi)")
                    _was_blocked[0] = False

                chunk = q.get()
                if chunk is None:
                    break
                if rec.AcceptWaveform(chunk):
                    _stab_text[0] = ""
                    _stab_since[0] = 0.0
                    try:
                        j = json.loads(rec.Result() or "{}")
                        text = (j.get("text") or "").strip()
                    except Exception:
                        text = ""
                    _emit_if_ok(text)
                else:
                    if not _want_partial:
                        continue
                    try:
                        pj = json.loads(rec.PartialResult() or "{}")
                        ptxt = (pj.get("partial") or "").strip()
                    except Exception:
                        ptxt = ""
                    # Spekulyativ javob: har bir yangi partial bilan (erta-
                    # yakunlash sozlamasidan MUSTAQIL) — foydalanuvchi hali
                    # gapirayotganda javob fon oqimda tayyorlana boshlaydi.
                    if ptxt and _spec_on_partial is not None:
                        try:
                            _spec_on_partial(ptxt)
                        except Exception:
                            pass
                    if _stab_sec <= 0:
                        continue
                    now = time.monotonic()
                    if not ptxt or len(ptxt) < int(MIN_PHRASE_CHARS or 0):
                        _stab_text[0] = ""
                        _stab_since[0] = 0.0
                        continue
                    if ptxt != _stab_text[0]:
                        _stab_text[0] = ptxt
                        _stab_since[0] = now
                        continue
                    if (now - _stab_since[0]) < _stab_sec:
                        continue
                    try:
                        fj = json.loads(rec.FinalResult() or "{}")
                        text = (fj.get("text") or "").strip() or ptxt
                    except Exception:
                        text = ptxt
                    rec.Reset()
                    _stab_text[0] = ""
                    _stab_since[0] = 0.0
                    _emit_if_ok(text)
            except Exception:
                continue

    th = threading.Thread(target=_worker, daemon=True)
    th.start()

    print("[NeuroKey] tayyor — gapiring!", flush=True)
    if _stab_sec > 0:
        print(f"[VOSK] TEZ gap tugashi: partial barqarorligi >= {_stab_ms:.0f} ms", flush=True)

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        # Ctrl+C ni caller ga uzatamiz; aks holda tashqi loop STT ni qayta ishga tushiradi.
        raise
    finally:
        try:
            stream.stop()
            stream.close()
            print("[AUDIO] Input stream closed.")
        except Exception:
            pass
        try:
            q.put(None)
        except Exception:
            pass
