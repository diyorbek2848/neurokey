# -*- coding: utf-8 -*-
"""
voice_recognition.py — NeuroKey ovoz tanish moduli
====================================================
Kimning ovozi ekanligini aniqlaydi.
Resemblyzer d-vector (256-o'lchamli) asosida cosine o'xshashlik.

Foydalanish:
  from voice_recognition import identify_speaker, is_owner_speaking
  result = identify_speaker(audio_np_array, sample_rate=16000)
  # {"known": True, "name": "Diyorbek", "similarity": 0.87}
"""
from __future__ import annotations
import os
import json
import logging
import threading
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROFILE_PATH = os.path.join(DATA_DIR, "voice_profile.npy")
VINFO_PATH   = os.path.join(DATA_DIR, "voice_owner.json")

# ─── Lazy-load state ─────────────────────────────────────────────────────────
_encoder        = None
_owner_profile  = None   # np.ndarray — normalize qilingan embedding
_owner_info     = {}
_lock           = threading.Lock()
_load_attempted = False


def _load():
    """Encoder va profil bir marta yuklanadi."""
    global _encoder, _owner_profile, _owner_info, _load_attempted
    if _load_attempted:
        return
    with _lock:
        if _load_attempted:
            return
        _load_attempted = True

        # Egasi profili
        if not os.path.exists(PROFILE_PATH):
            log.info("[VOICE] Profil yo'q: %s — voice_enroll.py ishlatish kerak", PROFILE_PATH)
            return
        try:
            _owner_profile = np.load(PROFILE_PATH)
            _owner_profile = _owner_profile / (np.linalg.norm(_owner_profile) + 1e-8)
        except Exception as e:
            log.warning("[VOICE] Profil yuklanmadi: %s", e)
            return

        if os.path.exists(VINFO_PATH):
            try:
                with open(VINFO_PATH, encoding="utf-8") as f:
                    _owner_info = json.load(f)
            except Exception:
                pass

        # Resemblyzer encoder — CPU majburlash (RTX 5070 eski PyTorch bilan mos emas)
        try:
            import os as _os
            _os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # CPU ga majburlash
            from resemblyzer import VoiceEncoder
            _encoder = VoiceEncoder(device="cpu")
            log.info("[VOICE] Resemblyzer encoder yuklandi (CPU). Profil: %s (%s)",
                     _owner_info.get("name", "?"),
                     _owner_info.get("enrolled_at", "?"))
        except Exception as e:
            log.warning("[VOICE] Resemblyzer yuklanmadi: %s — MFCC fallback ishlatiladi", e)


def _compute_embedding(audio: np.ndarray, sr: int = 16000) -> Optional[np.ndarray]:
    """Audio → 256-o'lchamli d-vector (yoki MFCC fallback)."""
    if audio is None or len(audio) < sr * 0.5:
        return None
    # Resemblyzer
    if _encoder is not None:
        try:
            from resemblyzer import preprocess_wav
            wav = preprocess_wav(audio.astype(np.float32), source_sr=sr)
            if len(wav) < 1600:
                return None
            embed = _encoder.embed_utterance(wav)
            return embed / (np.linalg.norm(embed) + 1e-8)
        except Exception as e:
            log.debug("[VOICE] embed xatosi: %s", e)

    # MFCC fallback
    try:
        pre = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])
        frame_len  = int(0.025 * sr)
        frame_step = int(0.010 * sr)
        num_frames = 1 + (len(pre) - frame_len) // frame_step
        if num_frames < 5:
            return None
        frames_mat = np.stack([
            pre[i * frame_step: i * frame_step + frame_len]
            for i in range(num_frames)
        ])
        window = np.hamming(frame_len)
        powered = np.abs(np.fft.rfft(frames_mat * window, n=512)) ** 2 / 512
        # Simplified mel filterbank
        n_mel, n_fft = 26, powered.shape[1]
        filterbank = np.zeros((n_mel, n_fft))
        mel_pts = np.linspace(0, n_fft, n_mel + 2, dtype=int)
        for m in range(1, n_mel + 1):
            for k in range(mel_pts[m - 1], mel_pts[m]):
                filterbank[m - 1, k] = (k - mel_pts[m - 1]) / max(mel_pts[m] - mel_pts[m - 1], 1)
            for k in range(mel_pts[m], mel_pts[m + 1]):
                filterbank[m - 1, k] = (mel_pts[m + 1] - k) / max(mel_pts[m + 1] - mel_pts[m], 1)
        log_mel = np.log(np.dot(powered, filterbank.T) + 1e-6)
        import scipy.fft as sfft
        n_mfcc = min(40, log_mel.shape[0])
        mfcc = sfft.dct(log_mel, type=2, n=n_mfcc, axis=1, norm="ortho")
        embed = mfcc.mean(axis=0)
        return embed / (np.linalg.norm(embed) + 1e-8)
    except Exception:
        return None


def identify_speaker(
    audio: np.ndarray,
    sample_rate: int = 16000,
) -> dict:
    """
    Audio yozuvidan kim gapirganini aniqlaydi.

    Returns:
        {
          "known": bool,          — egasi ovozimi
          "name": str,            — ism (tanilsa) yoki "noma'lum"
          "similarity": float,    — o'xshashlik (0–1, yuqori = yaxshiroq)
          "threshold": float,     — chegara qiymati
          "profile_exists": bool, — profil yuklanganmi
        }
    """
    _load()

    if _owner_profile is None:
        return {
            "known": False,
            "name": "noma'lum",
            "similarity": 0.0,
            "threshold": 0.72,
            "profile_exists": False,
        }

    threshold = float(_owner_info.get("similarity_threshold", 0.72))
    owner_name = _owner_info.get("name", "egasi")

    embed = _compute_embedding(audio, sr=sample_rate)
    if embed is None:
        return {
            "known": False,
            "name": "noma'lum",
            "similarity": 0.0,
            "threshold": threshold,
            "profile_exists": True,
        }

    # Profil o'lchami farq qilishi mumkin (resemblyzer=256, mfcc=40)
    if embed.shape[0] != _owner_profile.shape[0]:
        return {
            "known": False,
            "name": "noma'lum",
            "similarity": 0.0,
            "threshold": threshold,
            "profile_exists": True,
        }

    similarity = float(np.dot(_owner_profile, embed))
    known = similarity >= threshold

    out = {
        "known": known,
        "name": owner_name if known else "noma'lum",
        "similarity": round(similarity, 3),
        "threshold": threshold,
        "profile_exists": True,
    }
    try:
        from owner_trust import trust_biometric_result
        return trust_biometric_result(out)
    except Exception:
        return out


def is_owner_speaking(
    audio: np.ndarray,
    sample_rate: int = 16000,
) -> bool:
    """Tez tekshiruv — egasi gapiraptimi?"""
    result = identify_speaker(audio, sample_rate)
    return result["known"]


def get_owner_name() -> str:
    """Ro'yxatdan o'tgan egasi ismi. Yo'q bo'lsa bo'sh string."""
    _load()
    return _owner_info.get("name", "")


# ─── Oxirgi natija (main.py dan o'qish uchun) ────────────────────────────────
_last_result: dict = {}
_last_lock = threading.Lock()


def _store_last(result: dict) -> None:
    """Oxirgi tanish natijasini saqlaydi (parallel threaddan chaqiriladi)."""
    global _last_result
    with _last_lock:
        _last_result = result


def get_last_speaker() -> dict:
    """Oxirgi tanish natijasini qaytaradi. Thread-safe."""
    with _last_lock:
        return dict(_last_result)


def profile_exists() -> bool:
    """Ovoz profili mavjudmi?"""
    return os.path.exists(PROFILE_PATH)


def get_status() -> dict:
    """Modul holati."""
    _load()
    return {
        "profile_exists": os.path.exists(PROFILE_PATH),
        "owner": _owner_info.get("name", ""),
        "enrolled_at": _owner_info.get("enrolled_at", ""),
        "method": _owner_info.get("method", ""),
        "encoder_loaded": _encoder is not None,
        "threshold": _owner_info.get("similarity_threshold", 0.72),
    }
