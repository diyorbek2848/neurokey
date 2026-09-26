# -*- coding: utf-8 -*-
"""
NeuroKey — AGI yo'li uchun standart muhit (env).

!NeuroKey_AGI.bat va agi_runner.py shu defaultlardan foydalanadi.
Mavjud env o'zgartirilmaydi — faqat hali o'rnatilmagan kalitlar.
"""
from __future__ import annotations

import os

AGI_ENV: dict[str, str] = {
    # Tier — RAM bo'yicha (boot_tier.py)
    "NEUROKEY_AUTO_TIER": "1",
    "NEUROKEY_USE_LARGE_KB": "0",
    "NEUROKEY_KB_PREWARM": "0",
    # Ong — vaziyat bo'yicha (attention_router)
    "NEUROKEY_GWT_INTEGRATION": "1",
    "NEUROKEY_INNER_SPEECH": "1",
    "NEUROKEY_NARRATIVE_SELF": "1",
    # Agent (xavfsiz allowlist — agentic_loop.py)
    "NEUROKEY_AGENTIC_LOOP": "1",
    "NEUROKEY_AGENTIC_MAX_STEPS": "6",
    # Fon va og'ir narsalar o'chiq
    "NEUROKEY_BG_AUTOTALK": "0",
    "NEUROKEY_ADLF_ENABLED": "0",
    "NEUROKEY_SELFIMPROVE_ENABLED": "0",
    "NEUROKEY_CAMERA_ENABLED": "0",
    "NEUROKEY_SCREEN_MONITOR": "0",
    "NEUROKEY_CURIOSITY_ENGINE": "0",
    "NEUROKEY_DREAM_CONSOLIDATION": "0",
    # Tez javob
    "NEUROKEY_INSTANT_REPLIES": "1",
    "NEUROKEY_LATENCY_ZERO": "1",
    "NEUROKEY_HISTORY_LIMIT": "6",
    "LLM_MAX_TOKENS_DEFAULT": "160",
    # UI
    "NEUROKEY_DISPLAY_OVERLAY": "0",
    "NEUROKEY_HOTKEYS": "0",
    "PYTHONIOENCODING": "utf-8",
}

YENGIL_ENV: dict[str, str] = {
    **AGI_ENV,
    "NEUROKEY_BOOT_TIER": "lite",
    "NEUROKEY_OFFLINE_ONLY": "1",
    "OLLAMA_MODEL": "qwen2.5:1.5b",
    "FASTER_WHISPER_MODEL": "tiny",
    "NEUROKEY_AGENTIC_LOOP": "0",
}


def apply_env(defaults: dict[str, str]) -> None:
    for key, val in defaults.items():
        if os.getenv(key) is None:
            os.environ[key] = val


def prefer_groq_llm() -> None:
    """!NeuroKey.bat kabi — Groq kalit bo'lsa, invalid OpenAI o'rniga Groq."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass
    groq = (os.getenv("GROQ_API_KEY") or "").strip()
    if groq.startswith("gsk_"):
        os.environ["OPENAI_BASE_URL"] = "https://api.groq.com/openai/v1"
        os.environ["OPENAI_API_KEY"] = groq
        os.environ.setdefault("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
        os.environ.setdefault("OPENAI_CHAT_MODEL", "openai/gpt-oss-20b")


def apply_agi_config() -> None:
    apply_env(AGI_ENV)
    prefer_groq_llm()


def apply_yengil_config() -> None:
    apply_env(YENGIL_ENV)
