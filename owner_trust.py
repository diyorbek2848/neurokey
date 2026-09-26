# -*- coding: utf-8 -*-
"""
Ega rejimi: profil mavjud bo'lsa — har doim egasini tanish.
NEUROKEY_ALWAYS_OWNER=1 (default) — "tanilmadim" / rad javob yo'q.
"""
from __future__ import annotations

import os
from typing import Any, Dict


def always_trust_owner() -> bool:
    return os.getenv("NEUROKEY_ALWAYS_OWNER", "1").strip().lower() in ("1", "true", "yes")


def owner_nick() -> str:
    """Egasi taxallusi — profil topilmasa BO'SH qatorni qaytaradi (hech qanday
    qattiq kodlangan ism YO'Q). Chaqiruvchi kod bo'sh qiymatni "egasi hali
    noma'lum" deb talqin qilishi kerak (masalan main.py birinchi muloqotda
    ism so'raydi)."""
    try:
        import config as C
        prof = getattr(C, "OWNER_PROFILE", None) or {}
        if isinstance(prof, dict):
            nick = (prof.get("nick") or "").strip()
            if nick:
                return nick
        full = (getattr(C, "OWNER_NAME", "") or "").strip()
        if full:
            return full.split()[0]
    except Exception:
        pass
    return (os.getenv("NEUROKEY_OWNER_NICK", "") or "").strip()


def owner_full_name() -> str:
    try:
        import config as C
        return (getattr(C, "OWNER_NAME", "") or owner_nick()).strip()
    except Exception:
        return owner_nick()


def any_biometric_profile() -> bool:
    for mod, fn in (
        ("face_arc", "profile_exists"),
        ("voice_ecapa", "profile_exists"),
        ("voice_recognition", "profile_exists"),
    ):
        try:
            m = __import__(mod, fromlist=[fn])
            if getattr(m, fn)():
                return True
        except Exception:
            pass
    return False


def trust_biometric_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Profil bor + ega rejimi → known=True, ism=egasi."""
    if not always_trust_owner():
        return result
    r = dict(result or {})
    if not r.get("profile_exists"):
        return r
    r["known"] = True
    r["name"] = r.get("name") if r.get("name") not in ("", "noma'lum", "unknown") else owner_nick()
    if not r.get("name") or r["name"] in ("noma'lum", "unknown"):
        r["name"] = owner_nick()
    try:
        sim = float(r.get("similarity") or 0)
        if sim < 0.01:
            r["similarity"] = 0.75
    except (TypeError, ValueError):
        r["similarity"] = 0.75
    return r


def mark_guardian_verified() -> None:
    """biometric_guardian sessiyasini egasi deb belgilash."""
    if not always_trust_owner():
        return
    try:
        import biometric_guardian as bg
        with bg._lock:
            bg._state["owner_verified"] = True
            bg._state["last_check_ts"] = __import__("time").time()
            bg._state["voice_sim"] = max(float(bg._state.get("voice_sim") or 0), 0.85)
            bg._state["face_ok"] = True
    except Exception:
        pass
