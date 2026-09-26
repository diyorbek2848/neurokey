# -*- coding: utf-8 -*-
"""
Birinchi o'rnatish: GitHub da yo'q modellarni yuklab oladi.

  - Vosk (rus, mikrofon zaxirasi) ~45 MB
  - Piper ovoz (Irina) ~60 MB
  - Whisper base (mikrofon) — Hugging Face keshiga
  - MiniLM (xotira qidiruvi) — Hugging Face keshiga

Yuz (InsightFace) va ovoz tanish (ECAPA) birinchi ishga tushirishda
o'zlari yuklanadi. Bu skript xato bersa ham keyingi qadamga o'tadi.
"""
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _download(url: str, dest: str) -> bool:
    if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
        _log(f"  [bor] {os.path.basename(dest)}")
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    _log(f"  yuklanmoqda {os.path.basename(dest)}")
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        _log(f"  [xato] {os.path.basename(dest)}: {e}")
        return False


def vosk() -> None:
    _log("[1] Vosk rus modeli")
    try:
        import download_vosk_model
        download_vosk_model.main()
    except Exception as e:
        _log(f"  [xato] {e}")


def piper() -> None:
    _log("[2] Piper ovoz (Irina)")
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium"
    folder = os.path.join(ROOT, "models", "piper")
    _download(f"{base}/ru_RU-irina-medium.onnx", os.path.join(folder, "ru_RU-irina-medium.onnx"))
    _download(f"{base}/ru_RU-irina-medium.onnx.json", os.path.join(folder, "ru_RU-irina-medium.onnx.json"))


def whisper_and_memory() -> None:
    _log("[3] Whisper (eshitish) va MiniLM (xotira)")
    try:
        from faster_whisper import WhisperModel
        WhisperModel("base", device="cpu", compute_type="int8")
        _log("  [ok] faster-whisper base")
    except Exception as e:
        _log(f"  [keyinroq] Whisper birinchi gapirishda yuklanadi: {e}")
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        _log("  [ok] MiniLM")
    except Exception as e:
        _log(f"  [keyinroq] xotira modeli birinchi savolda yuklanadi: {e}")


def main() -> int:
    vosk()
    piper()
    whisper_and_memory()
    _log("[tayyor] Modellar. Yuz va ovoz tanish birinchi NeuroKey ochilishida yuklanadi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
