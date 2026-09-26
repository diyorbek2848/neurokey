# -*- coding: utf-8 -*-
"""audio_devices.py - Windows-friendly audio device auto-detection.

Goals:
 - Detect and warn if selected INPUT device looks like loopback (Stereo Mix / loopback / system audio)
 - Auto-pick a better microphone / speaker when AUTO_SELECT_AUDIO_DEVICE=True
 - Provide readable device dump for debugging

This module is best-effort and never raises (returns None if sounddevice unavailable).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple


BAD_INPUT_PATTERNS = [
    r"stereo\s*mix",
    r"what\s*u\s*hear",
    r"loopback",
    r"system\s*audio",
    r"cable\s*output",
    r"virtual",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _looks_bad_input(name: str) -> bool:
    n = _norm(name)
    return any(re.search(p, n) for p in BAD_INPUT_PATTERNS)


def list_devices() -> Optional[List[Dict[str, Any]]]:
    try:
        import sounddevice as sd
    except Exception:
        return None
    out = []
    try:
        devs = sd.query_devices()
        for i, d in enumerate(devs):
            out.append({
                "index": i,
                "name": d.get("name"),
                "max_input_channels": d.get("max_input_channels"),
                "max_output_channels": d.get("max_output_channels"),
                "hostapi": d.get("hostapi"),
            })
    except Exception:
        return None
    return out


def pick_best_devices(
    mic_hints: List[str],
    spk_hints: List[str],
    prefer_input: Optional[int] = None,
    prefer_output: Optional[int] = None,
) -> Tuple[Optional[int], Optional[int], List[str]]:
    """Return (input_index, output_index, warnings)."""
    warnings: List[str] = []
    devs = list_devices()
    if not devs:
        return prefer_input, prefer_output, warnings

    def score_input(d: Dict[str, Any]) -> int:
        if int(d.get("max_input_channels") or 0) <= 0:
            return -10_000
        name = str(d.get("name") or "")
        s = 0
        if _looks_bad_input(name):
            s -= 500
        nlow = _norm(name)
        for h in mic_hints:
            if _norm(h) and _norm(h) in nlow:
                s += 50
        # generic mic keywords
        if "mic" in nlow or "microphone" in nlow or "микроф" in nlow:
            s += 30
        return s

    def score_output(d: Dict[str, Any]) -> int:
        if int(d.get("max_output_channels") or 0) <= 0:
            return -10_000
        name = str(d.get("name") or "")
        nlow = _norm(name)
        # Mikrofon nomi bilan chiqish qurilmasi — ovoz chiqmaydi (Windows xato mapping)
        if "microphone" in nlow or "микроф" in nlow or "fifine" in nlow and "mic" in nlow:
            return -10_000
        if "microphone" in nlow or "микроф" in nlow:
            return -10_000
        s = 0
        for h in spk_hints:
            if _norm(h) and _norm(h) in nlow:
                s += 30
        if "headphone" in nlow or "науш" in nlow or "hd audio headphone" in nlow:
            s += 90
        if "high definition audio" in nlow and "headphone" in nlow:
            s += 85
        if "msi" in nlow or "mp273" in nlow:
            s += 15
        if "speaker" in nlow or "динами" in nlow or "колон" in nlow:
            s += 20
        if "monitor" in nlow or "display" in nlow:
            s += 10
        return s

    # Validate preferred first
    in_idx = prefer_input
    out_idx = prefer_output
    if in_idx is not None and 0 <= int(in_idx) < len(devs):
        if _looks_bad_input(str(devs[int(in_idx)].get("name") or "")):
            warnings.append(
                f"[AUDIO] INPUT_DEVICE_INDEX={in_idx} looks like loopback: '{devs[int(in_idx)].get('name')}'. "
                "This will cause echo/self-transcription."
            )
    # pick best
    best_in = None
    best_in_score = -10_000
    for d in devs:
        sc = score_input(d)
        if sc > best_in_score:
            best_in_score = sc
            best_in = int(d["index"])

    best_out = None
    best_out_score = -10_000
    for d in devs:
        sc = score_output(d)
        if sc > best_out_score:
            best_out_score = sc
            best_out = int(d["index"])

    # If preferred is bad, recommend best_in
    if in_idx is not None and best_in is not None:
        if _looks_bad_input(str(devs[int(in_idx)].get("name") or "")) and best_in != int(in_idx):
            warnings.append(f"[AUDIO] Recommended mic index: {best_in} ('{devs[best_in].get('name')}').")

    return best_in if best_in is not None else in_idx, best_out if best_out is not None else out_idx, warnings


def apply_auto_selection(C: Any, printer=print) -> None:
    """Mutates config module attributes (INPUT_DEVICE_INDEX/OUTPUT_DEVICE_INDEX) if enabled."""
    try:
        auto = bool(getattr(C, "AUTO_SELECT_AUDIO_DEVICE", False))
        mic_hints = list(getattr(C, "MIC_NAME_HINTS", []) or [])
        spk_hints = list(getattr(C, "SPEAKER_NAME_HINTS", []) or [])
        prefer_in = getattr(C, "INPUT_DEVICE_INDEX", None)
        prefer_out = getattr(C, "OUTPUT_DEVICE_INDEX", None)
        best_in, best_out, warns = pick_best_devices(mic_hints, spk_hints, prefer_in, prefer_out)
        for w in warns:
            try:
                printer(w)
            except Exception:
                pass
        _env_out = (os.getenv("OUTPUT_DEVICE_INDEX", "") or "").strip()
        _env_in = (os.getenv("INPUT_DEVICE_INDEX", "") or "").strip()
        if auto:
            if best_in is not None and not _env_in.isdigit():
                setattr(C, "INPUT_DEVICE_INDEX", int(best_in))
            if best_out is not None and not _env_out.isdigit():
                setattr(C, "OUTPUT_DEVICE_INDEX", int(best_out))
            elif _env_out.isdigit() and devs and 0 <= int(_env_out) < len(devs):
                setattr(C, "OUTPUT_DEVICE_INDEX", int(_env_out))
            try:
                printer(f"[AUDIO] Auto-selected devices: input={getattr(C,'INPUT_DEVICE_INDEX',None)}, output={getattr(C,'OUTPUT_DEVICE_INDEX',None)}")
            except Exception:
                pass
    except Exception:
        return
