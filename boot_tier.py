# -*- coding: utf-8 -*-
"""
NeuroKey — Boot Tier (RAM bo'yicha avtomatik rejim).

Maqsad: 50 ta ong moduli KODDA qoladi, lekin 8 GB RAM li noutbukda
ishga tushganda og'ir narsalar (15 GB bilim bazasi, ArcFace prewarm,
kamera fon, curiosity/dream) avtomatik o'chadi yoki kechiktiriladi.

Tier:
  LITE     — RAM <= 10 GB  (8 GB noutbuk)
  STANDARD — RAM <= 20 GB
  FULL     — RAM > 20 GB  (hozirgi investor/demo konfiguratsiya)

O'zgartirish: NEUROKEY_BOOT_TIER=lite|standard|full (avtomatikni bekor qiladi)
"""
from __future__ import annotations

import os
import sys

_TIER: str | None = None
_RAM_GB: float = 0.0

# Env kalit → default qiymat (faqat hali o'rnatilmagan bo'lsa)
_LITE_DEFAULTS: dict[str, str] = {
    "NEUROKEY_KB_PREWARM": "0",
    "NEUROKEY_FACE_PREWARM": "0",
    "NEUROKEY_VECTOR_PREWARM": "0",
    "NEUROKEY_CAMERA_ENABLED": "0",
    "NEUROKEY_BG_SENSOR": "0",
    "NEUROKEY_SCREEN_MONITOR": "0",
    "NEUROKEY_CURIOSITY_ENGINE": "0",
    "NEUROKEY_DREAM_CONSOLIDATION": "0",
    "NEUROKEY_INNER_SPEECH_REAL": "0",
    "NEUROKEY_EMBODIMENT": "0",
    "NEUROKEY_FREE_ENERGY": "0",
    "NEUROKEY_BOSQICH3": "0",
    "NEUROKEY_GWT_INTEGRATION": "1",
    "NEUROKEY_ADLF_ENABLED": "0",
    "NEUROKEY_SELFIMPROVE_ENABLED": "0",
    "NEUROKEY_PERFORMANCE_WARMUP": "1",
    "NEUROKEY_USE_LARGE_KB": "0",
    "FASTER_WHISPER_MODEL": "tiny",
}

_STANDARD_DEFAULTS: dict[str, str] = {
    "NEUROKEY_KB_PREWARM": "0",
    "NEUROKEY_FACE_PREWARM": "0",
    "NEUROKEY_VECTOR_PREWARM": "1",
    "NEUROKEY_CAMERA_ENABLED": "0",
    "NEUROKEY_BG_SENSOR": "1",
    "NEUROKEY_CURIOSITY_ENGINE": "0",
    "NEUROKEY_DREAM_CONSOLIDATION": "0",
    "NEUROKEY_INNER_SPEECH_REAL": "0",
    "NEUROKEY_EMBODIMENT": "0",
    "NEUROKEY_FREE_ENERGY": "0",
    "NEUROKEY_BOSQICH3": "1",
    "NEUROKEY_USE_LARGE_KB": "0",
    "FASTER_WHISPER_MODEL": "base",
}

_FULL_DEFAULTS: dict[str, str] = {
    # 15 GB KB hech qachon startda emas — faqat chuqur savolda (lazy)
    "NEUROKEY_KB_PREWARM": "0",
    # O'LCHANGAN (2026-09-25, measure_main_ram.py):
    #   USE_LARGE_KB=1  ->  main.py peak 13 039 MB (13 GB)
    #   USE_LARGE_KB=0  ->  main.py peak  1 283 MB (1.3 GB)
    # 10 barobar farq. 32 GB li kompyuterda ham 13 GB — bu "qotish"ning
    # asosiy sababi. Shuning uchun FULL tier'da ham default 0: katta baza
    # faqat ATAYLAB yoqilganda ishlatiladi.
    #   Yoqish: set NEUROKEY_USE_LARGE_KB=1
    "NEUROKEY_USE_LARGE_KB": "0",
    "NEUROKEY_FACE_PREWARM": "0",
}


def _detect_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 16.0


def detect_tier() -> str:
    """lite | standard | full"""
    forced = (os.getenv("NEUROKEY_BOOT_TIER") or "").strip().lower()
    if forced in ("lite", "standard", "full"):
        return forced
    if os.getenv("NEUROKEY_AUTO_TIER", "1").strip().lower() in ("0", "false", "no"):
        return "full"
    ram = _detect_ram_gb()
    if ram <= 10.0:
        return "lite"
    if ram <= 20.0:
        return "standard"
    return "full"


def _apply_defaults(defaults: dict[str, str]) -> None:
    for key, val in defaults.items():
        if os.getenv(key) is None:
            os.environ[key] = val


def apply_boot_tier(verbose: bool = True) -> str:
    """main.py eng boshida chaqiriladi — env defaultlarini tier bo'yicha o'rnatadi."""
    global _TIER, _RAM_GB
    _RAM_GB = _detect_ram_gb()
    _TIER = detect_tier()

    if _TIER == "lite":
        _apply_defaults(_LITE_DEFAULTS)
    elif _TIER == "standard":
        _apply_defaults(_STANDARD_DEFAULTS)
    else:
        _apply_defaults(_FULL_DEFAULTS)

    # Kichik bilim indeksi (D: dagi 15 GB faqat FULL + opt-in)
    use_large = os.getenv("NEUROKEY_USE_LARGE_KB", "0").strip().lower() in ("1", "true", "yes")
    if not use_large and os.getenv("NEUROKEY_KB_DIR") is None:
        base = os.path.dirname(os.path.abspath(__file__))
        os.environ["NEUROKEY_KB_DIR"] = os.path.join(base, "data", "knowledge_index")

    if verbose:
        print(
            f"[BOOT-TIER] {_TIER.upper()} — RAM {_RAM_GB:.1f} GB | "
            f"ong modullari saqlanadi, faqat kerak bo'lganda yoqiladi",
            flush=True,
        )
        if _TIER != "full":
            print(
                "[BOOT-TIER] Og'ir yuklash o'chirildi (15GB KB, kamera fon, curiosity). "
                "To'liq rejim: NEUROKEY_BOOT_TIER=full",
                flush=True,
            )
    return _TIER


def get_tier() -> str:
    return _TIER or detect_tier()


def get_ram_gb() -> float:
    return _RAM_GB or _detect_ram_gb()


if __name__ == "__main__":
    apply_boot_tier()
    print("Tier:", get_tier(), "RAM GB:", round(get_ram_gb(), 1))
