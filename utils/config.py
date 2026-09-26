# utils/config.py
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# STT
VOSK_MODEL_DIR = str(ROOT / "models" / "vosk-model-small-uz-0.22")
MIC_SAMPLE_RATE = 16000
MIC_BLOCKSIZE = 8000  # vosk uchun

# TTS
XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
XTTS_SPEAKER = None      # default speaker
XTTS_STYLE_WAV = None    # masalan: r"C:\path\myvoice_10s.wav" qo‘ysangiz yanada tabiiy bo‘ladi

# FASTER-WHISPER
FW_MODEL_SIZE = "small"  # "tiny"/"base"/"small"/"medium" — RTX 5070 uchun "small" yaxshi balans
FW_DEVICE = "cuda"       # GPU
FW_COMPUTE_TYPE = "float16"  # tezlik uchun

# API kalitlar (istasa muhitdan oladi)
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
