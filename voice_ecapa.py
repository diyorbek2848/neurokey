# -*- coding: utf-8 -*-
"""
voice_ecapa.py — NeuroKey ECAPA-TDNN Ovoz Tanish (Maksimal aniqlik)

SpeechBrain ECAPA-TDNN modeli:
  - VoxCeleb benchmark: ~98% aniqlik
  - Oldingi MFCC: ~65% → 98% ga o'tish
  - 192-o'lchamli speaker embedding
  - CPU da ishlaydi (~150-300ms)

Model birinchi ishga tushganda yuklanadi (~80MB, bir marta).

Foydalanish:
  from voice_ecapa import enroll, identify, is_owner
"""
from __future__ import annotations

import os
import json
import logging
import threading
import time
from typing import Optional, List

import numpy as np

log = logging.getLogger(__name__)

_BASE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(_BASE, "data")
PROF_PATH = os.path.join(DATA_DIR, "voice_ecapa_profile.npy")
INFO_PATH = os.path.join(DATA_DIR, "voice_ecapa_owner.json")
MODEL_DIR = os.path.join(_BASE, "models", "ecapa")

# ECAPA cosine o'xshashlik chegarasi
# 0.65 = liberal, 0.70 = o'rtacha, 0.75 = qattiq
THRESHOLD = 0.70

SR = 16000   # ECAPA 16kHz da ishlaydi

# ── Lazy-load ─────────────────────────────────────────────────────────────────
_model        = None
_owner_embed: Optional[np.ndarray] = None
_owner_info:  dict = {}
_lock         = threading.Lock()
_loaded       = False

# ── Oxirgi natija (STT loop uchun, 0ms da o'qiladi) ──────────────────────────
_last_result: dict = {}
_last_lock   = threading.Lock()

def _store_last(result: dict):
    global _last_result
    with _last_lock:
        _last_result = dict(result)
        _last_result["_ts"] = time.time()   # vaqt tamg'asi — eskirgan natijani rad etish uchun

def get_last_result() -> dict:
    with _last_lock:
        return dict(_last_result)


def _load():
    """SpeechBrain ECAPA modelini bir marta yuklaydi.

    RACE-CONDITION FIX (2026-09-13) — xuddi face_arc.py._load() dagi bilan
    bir xil muammo: bu funksiya startupda main.py'ning ASOSIY (main)
    threadidan (get_status() orqali) VA bir nechta fon preload threadidan
    deyarli bir vaqtda chaqirilardi. `_loaded=True` avval OG'IR ishdan
    (SpeechBrain model yuklash + torch.cuda() sinovi — sovuq CUDA
    boshlanishida sekundlab cho'zilishi mumkin) OLDIN qo'yilgani uchun:
      a) tezroq kelgan chaqiruvchi (ba'zan bu ASOSIY thread bo'lgan) o'zi
         OG'IR yuklashni boshlab, butun ilovani shu yerda — hech qanday
         konsol chiqishisiz (progress xabarlari faqat log.info(), root
         logger darajasi WARNING — ko'rinmaydi) — muzlatib qo'yardi;
      b) boshqa chaqiruvchilar hali tayyor bo'lmagan holatni "tayyor" deb
         noto'g'ri qaytarardi.
    FIX: main.py endi bu yerga ASOSIY threaddan umuman kirmaydi
    (get_status_cheap() ishlatadi); `_loaded=True` endi FAQAT haqiqiy
    yakundan keyin qo'yiladi; og'ir bosqich atrofiga shartsiz print()
    qo'shildi."""
    global _model, _owner_embed, _owner_info, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _t_load0 = time.time()
        print("[VOICE-ECAPA] ECAPA-TDNN yuklanmoqda (birinchi marta biroz vaqt olishi mumkin)...", flush=True)
        try:
            os.makedirs(MODEL_DIR, exist_ok=True)

            # ROOT-CAUSE FIX (2026-09-25, jurnalda o'lchangan):
            #   [VOICE-ECAPA] Model yuklashda XATO (27.5s): ImportError(
            #     "cannot import name 'set_module' from partially initialized
            #      module 'torch.utils' (most likely due to a circular import)")
            # Sabab: `speechbrain` SHU FON THREADIDA import qilinardi, lekin
            # AYNI PAYTDA boshqa thread `torch` ni import qilayotgan edi
            # (faster-whisper / sentence-transformers / face_arc — hammasi
            # startupda parallel yuklanadi). Python yarim-initsializatsiya
            # qilingan modulni ikkinchi threadga ko'rsatadi → ImportError.
            # Bu 27.5 s ni behuda sarflab, ovoz tanishni O'CHIRIB qo'yardi.
            #
            # FIX: `torch` ni AVVAL o'zimiz to'liq import qilamiz. Import
            # tugagach modul to'liq initsializatsiya bo'ladi va speechbrain
            # ichidagi `from torch.utils import set_module` xato bermaydi.
            # Bir marta muvaffaqiyatsiz bo'lsa — qisqa kutib qayta urinadi
            # (boshqa thread importni tugatib ulgurishi uchun).
            import torch  # noqa: F401  — tartib MUHIM, speechbrain'dan OLDIN
            import torch.utils  # noqa: F401

            for _attempt in (1, 2, 3):
                try:
                    import speechbrain.utils.fetching as _sbf
                    from speechbrain.utils.fetching import LocalStrategy as _LS
                    break
                except ImportError as _ie:
                    if _attempt == 3:
                        raise
                    log.debug("[VOICE-ECAPA] speechbrain import %d-urinish: %s",
                              _attempt, _ie)
                    time.sleep(1.5)
            _orig_fetch = _sbf.fetch
            def _cp_fetch(*a, **kw):
                kw["local_strategy"] = _LS.COPY
                return _orig_fetch(*a, **kw)
            _sbf.fetch = _cp_fetch

            from speechbrain.inference.speaker import SpeakerRecognition
            try:
                import torch as _torch
                _t = _torch.tensor([1.0]).cuda()
                _ = _t + 1
                _device = "cuda:0"
                log.info("[VOICE-ECAPA] GPU (CUDA) ishlatiladi")
            except Exception:
                _device = "cpu"
            _model = SpeakerRecognition.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=MODEL_DIR,
                run_opts={"device": _device},
            )
            _sbf.fetch = _orig_fetch   # patch ni qaytarish
            log.info("[VOICE-ECAPA] ECAPA-TDNN yuklandi (CPU)")
            print(f"[VOICE-ECAPA] ECAPA-TDNN tayyor ({time.time() - _t_load0:.1f}s, device={_device})", flush=True)
        except Exception as e:
            log.warning("[VOICE-ECAPA] Model yuklanmadi: %s", e)
            print(f"[VOICE-ECAPA] Model yuklashda XATO ({time.time() - _t_load0:.1f}s): {e!r}", flush=True)
            _model = None
            _loaded = True  # urinib ko'rildi — har chaqiruvda qayta muzlab qolmasin
            return

        if os.path.exists(PROF_PATH):
            try:
                _owner_embed = np.load(PROF_PATH)
                _owner_embed /= (np.linalg.norm(_owner_embed) + 1e-8)
            except Exception as e:
                log.warning("[VOICE-ECAPA] Profil yuklanmadi: %s", e)
        if os.path.exists(INFO_PATH):
            try:
                with open(INFO_PATH, encoding="utf-8") as f:
                    _owner_info = json.load(f)
            except Exception:
                pass
        if _owner_embed is not None:
            log.info("[VOICE-ECAPA] Profil tayyor: %s (%d dim)",
                     _owner_info.get("name", "?"), _owner_embed.shape[0])
        _loaded = True  # ENDI — haqiqatan hammasi tayyor bo'lgach


def _embed(audio: np.ndarray) -> Optional[np.ndarray]:
    """Audio numpy array → ECAPA 192-dim embedding."""
    if _model is None or audio is None:
        return None
    if len(audio) < SR * 0.5:   # 0.5s dan kam → shovqin
        return None
    try:
        import torch
        wav = torch.tensor(audio.astype(np.float32)).unsqueeze(0)
        with torch.no_grad():
            out = _model.encode_batch(wav)        # [1, 1, 192]
        emb = out.squeeze().cpu().numpy()         # [192]
        if emb.ndim == 0:
            return None
        emb = emb / (np.linalg.norm(emb) + 1e-8)
        return emb
    except Exception as e:
        log.debug("[VOICE-ECAPA] embed xato: %s", e)
        return None


# ── Ro'yxatga olish ───────────────────────────────────────────────────────────

def enroll(audio_chunks: List[np.ndarray], name: str = "owner") -> bool:
    """
    Bir nechta audio chunkdan profil yaratish.
    audio_chunks: float32 numpy array list, sr=16000
    """
    _load()
    if _model is None:
        log.error("[VOICE-ECAPA] Model yuklanmagan — enroll imkonsiz")
        return False

    embeddings = []
    for i, chunk in enumerate(audio_chunks):
        emb = _embed(chunk)
        if emb is not None:
            embeddings.append(emb)
            print(f"    Chunk {i+1}: OK (norm={np.linalg.norm(emb):.3f})")
        else:
            print(f"    Chunk {i+1}: o'tkazib yuborildi (juda qisqa/shovqin)")

    if len(embeddings) < 3:
        log.warning("[VOICE-ECAPA] Yetarli audio yo'q (%d < 3)", len(embeddings))
        return False

    profile = np.mean(embeddings, axis=0)
    profile /= (np.linalg.norm(profile) + 1e-8)

    os.makedirs(DATA_DIR, exist_ok=True)
    np.save(PROF_PATH, profile)

    from datetime import datetime
    info = {
        "name":        name,
        "enrolled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "num_chunks":  len(embeddings),
        "method":      "ecapa_tdnn_192dim",
        "dims":        int(profile.shape[0]),
        "threshold":   THRESHOLD,
    }
    with open(INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    global _owner_embed, _owner_info
    _owner_embed = profile
    _owner_info  = info
    log.info("[VOICE-ECAPA] Profil saqlandi: %d chunk, %s", len(embeddings), name)
    return True


def enroll_from_mic(
    n_chunks: int = 10,
    chunk_sec: float = 5.0,
    camera_index: int = 0,
    name: str = "owner",
) -> bool:
    """Mikrofondan n_chunks × chunk_sec sekund yozib profil yaratish."""
    import sounddevice as sd
    _load()
    if _model is None:
        print("[VOICE-ECAPA] Model yuklanmagan")
        return False

    print(f"\n  {n_chunks} ta yozuv, har biri {chunk_sec:.0f} sekund.")
    print("  Tabiiy gapiring — istalgan gap aytsa bo'ladi.\n")
    print("  Boshlash uchun ISTALGAN TUGMANI bosing...", flush=True)
    try:
        import msvcrt; msvcrt.getch()
    except Exception:
        input()

    chunks = []
    for i in range(1, n_chunks + 1):
        if i > 1:
            for c in range(3, 0, -1):
                print(f"\r  {c}s dam...", end="", flush=True)
                time.sleep(1)
            print()
        print(f"  [{i}/{n_chunks}] Gapiring! ", end="", flush=True)
        frames = sd.rec(
            int(SR * chunk_sec),
            samplerate=SR, channels=1, dtype="int16",
        )
        for s in range(int(chunk_sec)):
            time.sleep(1)
            print("▓", end="", flush=True)
        sd.wait()
        print(" ✓")
        audio = frames[:, 0].astype(np.float32) / 32768.0
        chunks.append(audio)

    return enroll(chunks, name=name)


# ── Tanish ────────────────────────────────────────────────────────────────────

def identify(audio: np.ndarray) -> dict:
    """
    Audio numpy array → egasining ovozimi?
    Returns: {"known": bool, "similarity": float, ...}
    """
    _load()
    base = {
        "known":          False,
        "similarity":     0.0,
        "threshold":      THRESHOLD,
        "profile_exists": os.path.exists(PROF_PATH),
        "name":           "noma'lum",
        "method":         "ecapa_tdnn",
    }

    if _model is None or _owner_embed is None or audio is None:
        return base

    emb = _embed(audio)
    if emb is None:
        return base

    # Dimension mismatch bo'lsa → skip
    if emb.shape[0] != _owner_embed.shape[0]:
        log.warning("[VOICE-ECAPA] Dim mismatch: %d vs %d",
                    emb.shape[0], _owner_embed.shape[0])
        return base

    sim   = float(np.dot(_owner_embed, emb))
    known = sim >= THRESHOLD

    out = {
        **base,
        "known":      known,
        "similarity": round(sim, 3),
        "name":       _owner_info.get("name", "egasi") if known else "noma'lum",
    }
    try:
        from owner_trust import trust_biometric_result
        return trust_biometric_result(out)
    except Exception:
        return out


def is_owner(audio: np.ndarray) -> bool:
    return identify(audio)["known"]


def profile_exists() -> bool:
    return os.path.exists(PROF_PATH)


def preload():
    """Startup da fon threadda modelni yuklash (cold start yo'qoladi)."""
    t = threading.Thread(target=_load, daemon=True, name="ECAPA-preload")
    t.start()
    return t


def get_status() -> dict:
    _load()
    return {
        "profile_exists": profile_exists(),
        "owner":          _owner_info.get("name", ""),
        "enrolled_at":    _owner_info.get("enrolled_at", ""),
        "method":         "ecapa_tdnn_192dim",
        "threshold":      THRESHOLD,
        "model_loaded":   _model is not None,
    }


def get_status_cheap() -> dict:
    """get_status() bilan bir xil, lekin OG'IR modelni yuklamaydi (_load()
    chaqirmaydi) — main.py startup GUARDIAN blokida ASOSIY threadda
    xavfsiz chaqirish uchun (qarang _load() tepasidagi RACE-CONDITION
    FIX izohi)."""
    info = {}
    if os.path.exists(INFO_PATH):
        try:
            with open(INFO_PATH, encoding="utf-8") as f:
                info = json.load(f)
        except Exception:
            pass
    return {
        "profile_exists": profile_exists(),
        "owner":          info.get("name", ""),
        "enrolled_at":    info.get("enrolled_at", ""),
        "method":         "ecapa_tdnn_192dim",
        "threshold":      THRESHOLD,
        "model_loaded":   bool(_loaded and _model is not None),
    }
