# -*- coding: utf-8 -*-
"""
biometric_guardian.py — NeuroKey Biometrik Qo'riqchi
=====================================================
Bu tizim faqat egasiga bo'ysunadi.

Startup da yoki "kim bu?" savolida:
  → Ovoz + yuz tekshiriladi
  → Mos kelmasa: "Bu tizim faqat biometrik egasiga bo'ysunadi."
  → Tizim to'xtaydi yoki javob bermaydi

Investor ko'z oldida:
  Diyorbek gapiradi → tizim ishlaydi
  Investor gapiradi → "Men sizni tanimayman."

Bu boshqa hech bir AI da yo'q.
"""
from __future__ import annotations

import os
import logging
import threading
import time
from typing import Optional, Tuple

log = logging.getLogger(__name__)
_BASE = os.path.dirname(os.path.abspath(__file__))

# Kalit sozlamalar
VOICE_THRESHOLD  = 0.60   # Ovoz o'xshashligi minimal darajasi
FACE_CONFIDENCE  = 100.0  # LBPH confidence max (pastroq = yaxshiroq)
LOCK_ON_FAIL     = False  # True = tanilmasa tizim o'chadi; False = ogohlantiradi

# Rad javoblar (egasiga tegmaydi)
_REFUSE_MESSAGES = [
    "Bu tizim faqat biometrik egasiga bo'ysunadi. Men sizni tanimayman.",
    "Ruxsat yo'q. Bu shaxsiy tizim.",
    "Faqat egam bilan ishlashim mumkin.",
]

# Holat
_state = {
    "owner_verified": False,
    "last_check_ts": 0.0,
    "verify_timeout_s": 300,  # 5 daqiqa — qayta tekshirishsiz ishlash
    "voice_sim": 0.0,
    "face_ok": False,
}
_lock = threading.Lock()


# ── Ovoz tekshirish — ECAPA-TDNN (birlamchi) → MFCC fallback ────────────────
def verify_voice(audio_np=None, sample_rate: int = 16000) -> Tuple[bool, float]:
    """
    Audio numpy array → egasining ovozimi?
    ECAPA-TDNN (~98%) → eski MFCC fallback (~65%)
    Returns: (is_owner, similarity_score)
    """
    if audio_np is None:
        return False, 0.0

    # 1. ECAPA-TDNN (yangi, maksimal aniqlik)
    try:
        from voice_ecapa import identify as _ecapa_id, profile_exists as _ecapa_pex
        if _ecapa_pex():
            r = _ecapa_id(audio_np)
            is_owner = r.get("known", False)
            sim      = r.get("similarity", 0.0)
            log.debug("[GUARDIAN] ECAPA ovoz: known=%s, sim=%.3f", is_owner, sim)
            return is_owner, sim
    except Exception as e:
        log.debug("[GUARDIAN] ECAPA yuklanmadi: %s", e)

    # 2. Eski MFCC fallback (voice_recognition.py)
    try:
        from voice_recognition import identify_speaker
        result   = identify_speaker(audio_np, sample_rate)
        is_owner = result.get("known", False)
        sim      = result.get("similarity", 0.0)
        if sim > 0.01:          # dim mismatch bo'lsa sim=0 → o'tkazib yuborish
            log.debug("[GUARDIAN] MFCC ovoz: known=%s, sim=%.3f", is_owner, sim)
            return is_owner, sim
    except Exception as e:
        log.debug("[GUARDIAN] MFCC fallback xato: %s", e)

    return False, 0.0


# ── Yuz tekshirish — ArcFace (birlamchi) → LBPH fallback ────────────────────
def verify_face(frame=None) -> Tuple[bool, float]:
    """
    OpenCV frame → egasining yuzi mi?
    ArcFace (~99%) → LBPH fallback (~75%)
    Returns: (is_owner, similarity_or_confidence)
    """
    # 1. ArcFace (yangi, maksimal aniqlik)
    try:
        from face_arc import identify as _arc_id, identify_from_camera as _arc_cam
        from face_arc import profile_exists as _arc_pex
        if _arc_pex():
            if frame is not None:
                r = _arc_id(frame)
            else:
                r = _arc_cam()
            is_owner = r.get("known", False)
            sim      = r.get("similarity", 0.0)
            log.debug("[GUARDIAN] ArcFace yuz: known=%s, sim=%.3f", is_owner, sim)
            return is_owner, sim
    except Exception as e:
        log.debug("[GUARDIAN] ArcFace yuklanmadi: %s", e)

    # 2. LBPH fallback (eski, opencv-contrib kerak)
    try:
        import cv2
        model_path = os.path.join(_BASE, "data", "face_model.yml")
        if not os.path.exists(model_path) or not hasattr(cv2, "face"):
            return False, 999.0
        recognizer   = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(model_path)
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        if frame is None:
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return False, 999.0
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 5)
        for (x, y, w, h) in faces:
            roi = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            label, conf = recognizer.predict(roi)
            if conf < FACE_CONFIDENCE:
                return True, conf
        return False, 999.0
    except Exception as e:
        log.debug("[GUARDIAN] LBPH fallback xato: %s", e)
        return False, 999.0


# ── Asosiy tekshirish ─────────────────────────────────────────────────────────
def is_owner_present(
    audio_np=None,
    frame=None,
    mode: str = "voice",  # "voice" | "face" | "both" | "any"
) -> bool:
    """
    Egasi bormi?
    mode="voice" — faqat ovoz
    mode="face"  — faqat yuz
    mode="any"   — ikkalasidan biri yetarli
    mode="both"  — ikkalasi ham kerak
    """
    try:
        from owner_trust import always_trust_owner, any_biometric_profile, mark_guardian_verified
        if always_trust_owner() and any_biometric_profile():
            mark_guardian_verified()
            return True
    except Exception:
        pass
    with _lock:
        # Yaqinda tekshirilgan bo'lsa — qayta tekshirmaydi
        now = time.time()
        if (_state["owner_verified"] and
                now - _state["last_check_ts"] < _state["verify_timeout_s"]):
            return True

    voice_ok, voice_sim = (True, 1.0)
    face_ok,  face_conf  = (True, 0.0)

    if mode in ("voice", "any", "both"):
        voice_ok, voice_sim = verify_voice(audio_np)

    if mode in ("face", "any", "both"):
        face_ok, face_conf = verify_face(frame)

    if mode == "voice":
        result = voice_ok
    elif mode == "face":
        result = face_ok
    elif mode == "any":
        result = voice_ok or face_ok
    else:  # both
        result = voice_ok and face_ok

    with _lock:
        _state["owner_verified"] = result
        _state["last_check_ts"]  = time.time()
        _state["voice_sim"]      = voice_sim
        _state["face_ok"]        = face_ok

    if result:
        log.info("[GUARDIAN] Egasi tasdiqlandi. Ovoz: %.2f", voice_sim)
    else:
        log.warning("[GUARDIAN] Egasi tanilmadi. Ovoz: %.2f, Yuz: %s",
                    voice_sim, "OK" if face_ok else "YO'Q")

    return result


def refuse_message() -> str:
    """Rad javob — tasodifiy tanlaydi."""
    import random
    return random.choice(_REFUSE_MESSAGES)


def reset_session() -> None:
    """Yangi foydalanuvchi kelganda sessiyani qayta boshlash."""
    with _lock:
        _state["owner_verified"] = False
        _state["last_check_ts"]  = 0.0
        _state["voice_sim"]      = 0.0
        _state["face_ok"]        = False


def get_status() -> dict:
    """Joriy holat."""
    with _lock:
        return {
            "owner_verified": _state["owner_verified"],
            "voice_similarity": round(_state["voice_sim"], 3),
            "face_recognized": _state["face_ok"],
        }


# ── neurokey_core.py ga integratsiya ─────────────────────────────────────────
def guard_response(text: str, audio_np=None, frame=None) -> Optional[str]:
    """
    Har bir javob oldidan chaqiriladi.
    Agar egasi tanilmasa — rad javob qaytaradi.
    Agar egasi tanilsa — None (normal ishlash davom etadi).

    Foydalanish:
        from biometric_guardian import guard_response
        refusal = guard_response(user_text, audio_np)
        if refusal:
            speak(refusal)
            return
        # ... normal processing
    """
    # "demo" rejimi: faqat ovoz bor bo'lsa tekshirish
    if audio_np is not None:
        owner = is_owner_present(audio_np=audio_np, mode="voice")
    else:
        # Ovoz yo'q — tekshirib bo'lmaydi, o'tkazib yuboramiz
        # (matnli interfeys uchun biometrik shart emas)
        return None

    try:
        from owner_trust import always_trust_owner, any_biometric_profile
        if always_trust_owner() and any_biometric_profile():
            return None
    except Exception:
        pass

    if not owner:
        return refuse_message()

    return None
