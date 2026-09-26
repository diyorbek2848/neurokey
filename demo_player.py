# -*- coding: utf-8 -*-
"""
NeuroKey - L0 Demo Player.
Pre-cached WAV fayllarni darhol o'ynaydi.
Savol pattern bilan mos kelsa -> WAV o'ynaydi -> True qaytaradi.

KRITIK: Audio chalinayotganda VOSK keyingi gapni qabul qilmasligi uchun
tts._is_playing flag ni True qilamiz (VOSK uni tekshiradi va kutib turadi).
"""
import os, re, json, wave, time, threading, sys
import numpy as np

# Windows console UTF-8 fix
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_CACHE_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_cache")
_INDEX_FILE = os.path.join(_CACHE_DIR, "index.json")

_index    = {}      # {pattern: {"file": path, "text": text}}
_loaded   = False
_lock     = threading.Lock()
_play_lock = threading.Lock()  # Bir vaqtda faqat bitta L0 audio chalinsin

# Pre-loaded audio - RAM dan o'ynaydi (disk I/O yo'q)
_audio_cache = {}   # {wav_path: (np.float32, sample_rate)}

# TTS objektni eslab qolamiz - is_playing flag uchun
_tts_ref = None


def set_tts(tts_obj):
    """main.py dan tts ob'ektini olish — VOSK ni bloklash uchun."""
    global _tts_ref
    _tts_ref = tts_obj


def _load_index():
    global _index, _loaded
    with _lock:
        if _loaded:
            return
        if not os.path.isfile(_INDEX_FILE):
            _loaded = True
            return
        try:
            with open(_INDEX_FILE, "r", encoding="utf-8") as f:
                _index = json.load(f)
            # Hamma WAV ni RAM ga yuklab olish
            for pattern, info in _index.items():
                fpath = info.get("file", "")
                if fpath and os.path.isfile(fpath) and fpath not in _audio_cache:
                    try:
                        with wave.open(fpath, "rb") as wf:
                            frames = wf.readframes(wf.getnframes())
                            sr     = wf.getframerate()
                        audio = (np.frombuffer(frames, dtype=np.int16)
                                   .astype(np.float32) / 32768.0)
                        _audio_cache[fpath] = (audio, sr)
                    except Exception as e:
                        print(f"[L0] WAV o'qib bo'lmadi {fpath}: {e}", flush=True)
            _loaded = True
            print(f"[L0] Demo cache: {len(_index)} savol, "
                  f"{len(_audio_cache)} audio RAM da tayyor.", flush=True)
        except Exception as e:
            print(f"[L0] Cache yuklanmadi: {e}", flush=True)
            _loaded = True


def preload():
    """Startup da fonda cache yuklansin."""
    threading.Thread(target=_load_index, daemon=True, name="demo-cache-load").start()


def _play_audio(audio: np.ndarray, sr: int, output_device=None) -> float:
    """
    Audio chalish - VOSK ni bloklash bilan.
    Qaytaradi: haqiqiy chalish davomiyligi (sekund).
    """
    duration = len(audio) / float(sr) if sr > 0 else 0.0

    # TTS flag — VOSK shuni tekshirib, mikrofondan input qabul qilmaydi
    if _tts_ref is not None:
        try:
            _tts_ref._is_playing = True
        except Exception:
            pass

    t0 = time.monotonic()
    try:
        import sounddevice as sd
        # Avvalgi har qanday playback ni to'xtatish
        try:
            sd.stop()
        except Exception:
            pass
        # Yangi audioni boshlash
        sd.play(audio, samplerate=sr, device=output_device)
        # Tugaguncha kutish — sd.wait() blocking=True dan ishonchliroq
        sd.wait()
    except Exception as e:
        print(f"[L0] Audio xato: {type(e).__name__}: {e}", flush=True)
    finally:
        # TTS flag ni ozod qilish — endi VOSK input qabul qila oladi
        if _tts_ref is not None:
            try:
                _tts_ref._is_playing = False
                # last_end_time ni yangilash (VOSK echo bloklash uchun)
                if hasattr(_tts_ref, '_last_end_time'):
                    _tts_ref._last_end_time = time.monotonic()
            except Exception:
                pass

    return time.monotonic() - t0


def try_play(text: str, output_device=None) -> tuple:
    """
    Matn demo cache ga mos kelishini tekshiradi.
    Mos kelsa -> WAV o'ynaydi -> (True, javob_matni) qaytaradi.
    Mos kelmasa -> (False, "") qaytaradi.

    Bir vaqtda faqat bitta playback (lock bilan) -> overlap bo'lmaydi.
    """
    if not _loaded:
        _load_index()

    t_lower = text.strip().lower()

    matched_info = None
    for pattern, info in _index.items():
        try:
            if re.search(pattern, t_lower, re.IGNORECASE):
                matched_info = info
                break
        except Exception as _pat_e:
            print(f"[L0] pattern xato: {_pat_e}", flush=True)
            continue

    if matched_info is None:
        return False, ""

    fpath = matched_info.get("file", "")
    answer_text = matched_info.get("text", "")

    # Audio yuklash (RAM da bo'lmasa diskdan)
    audio = sr = None
    if fpath in _audio_cache:
        audio, sr = _audio_cache[fpath]
    elif fpath and os.path.isfile(fpath):
        try:
            with wave.open(fpath, "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                sr     = wf.getframerate()
            audio = (np.frombuffer(frames, dtype=np.int16)
                       .astype(np.float32) / 32768.0)
            _audio_cache[fpath] = (audio, sr)
        except Exception as e:
            print(f"[L0] Audio yuklab bo'lmadi: {e}", flush=True)
            return False, ""

    if audio is None or sr is None:
        return False, ""

    # Lock bilan: bir vaqtda faqat bitta L0 audio chalinishi
    with _play_lock:
        play_dur = _play_audio(audio, sr, output_device)
        expected_dur = len(audio) / float(sr) if sr else 0.0
        # Agar playback kutilganidan sezilarli oldin tugasa, to'liq matnni TTS bilan qayta aytamiz.
        if _tts_ref is not None and expected_dur > 1.2 and play_dur < (expected_dur * 0.65):
            try:
                print("[L0] audio erta tugadi — TTS fallback ishlatilyapti.", flush=True)
                _tts_ref.say(answer_text)
            except Exception:
                pass
        _preview = answer_text[:220].encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        print(f"[L0] {play_dur*1000:.0f}ms (audio={expected_dur:.1f}s) -> {_preview}", flush=True)

    return True, answer_text


def is_ready() -> bool:
    """Cache index mavjudmi?"""
    return os.path.isfile(_INDEX_FILE) and bool(_index)
