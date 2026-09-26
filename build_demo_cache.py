# -*- coding: utf-8 -*-
"""
Demo audio cache generator.
Piper bilan barcha javoblarni WAV ga o'giradi -> demo_cache/ papkasiga saqlaydi.
Bir marta ishga tushiriladi. Keyin demo_player.py ularni darhol o'ynaydi.
"""
import os, sys, time, hashlib, wave, struct, json, re
import numpy as np


def _brand_for_piper_tts(text: str) -> str:
    """L0 WAV: latin NeuroKey -> rus talaffuzi (tts_openai bilan bir xil)."""
    t = text or ""
    t = re.sub(r"\bneuro\s+key\b", "Нейро Кей", t, flags=re.IGNORECASE)
    t = re.sub(r"\bneurokey\b", "Нейро Кей", t, flags=re.IGNORECASE)
    return t

# Windows console UTF-8 fix
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_cache")
INDEX_FILE = os.path.join(CACHE_DIR, "index.json")

os.makedirs(CACHE_DIR, exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def text_to_id(text: str) -> str:
    """Matn → fayl nomi (hash)"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def save_wav(path: str, audio: np.ndarray, sr: int):
    audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int16.tobytes())


def generate_with_piper(text: str, piper_voice) -> tuple:
    """Piper bilan audio yaratish -> (np.float32 array, sample_rate)
    Yangi API: synthesize() -> Iterable[AudioChunk] qaytaradi.
    """
    sr = piper_voice.config.sample_rate
    chunks = list(piper_voice.synthesize(text))
    if not chunks:
        raise RuntimeError("Piper: hech qanday audio chunk yaratilmadi")
    audio = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
    return audio, sr


def main():
    print("=== Demo cache yaratilmoqda ===\n")

    # Piper yuklash
    print("Piper yuklanmoqda...")
    import config as C
    t0 = time.monotonic()
    try:
        from piper import PiperVoice
        _base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "piper")
        _model_env = (getattr(C, "PIPER_MODEL", "") or os.getenv("PIPER_MODEL", "") or "").strip()
        if _model_env and os.path.isfile(_model_env):
            model_path = _model_env
        else:
            # models/piper/ dan topish
            candidates = [f for f in os.listdir(_base) if f.endswith(".onnx")]
            if not candidates:
                print("XATO: models/piper/ da .onnx fayl topilmadi")
                return
            model_path = os.path.join(_base, candidates[0])
        piper_voice = PiperVoice.load(model_path)
        print(f"Piper yuklandi: {os.path.basename(model_path)} ({(time.monotonic()-t0)*1000:.0f}ms)")
    except Exception as e:
        print(f"XATO: Piper yuklanmadi: {e}")
        return

    # Javoblarni yaratish
    from demo_responses import DEMO_QA
    index = {}
    ok, skip, fail = 0, 0, 0

    for i, (pattern, text) in enumerate(DEMO_QA):
        text_speak = _brand_for_piper_tts(text)
        fid = text_to_id(text_speak)
        wav_path = os.path.join(CACHE_DIR, f"{fid}.wav")

        if os.path.isfile(wav_path):
            print(f"  [{i+1:2d}/{len(DEMO_QA)}] mavjud: {text_speak[:45]}...")
            index[pattern] = {"file": wav_path, "text": text_speak}
            skip += 1
            continue

        try:
            t0 = time.monotonic()
            audio, sr = generate_with_piper(text_speak, piper_voice)
            save_wav(wav_path, audio, sr)
            ms = (time.monotonic()-t0)*1000
            dur = len(audio)/sr
            print(f"  [{i+1:2d}/{len(DEMO_QA)}] {ms:4.0f}ms -> {dur:.1f}s audio: {text_speak[:45]}...")
            index[pattern] = {"file": wav_path, "text": text_speak}
            ok += 1
        except Exception as e:
            print(f"  [{i+1:2d}/{len(DEMO_QA)}] XATO: {e}")
            fail += 1

    # Index saqlash
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\nTayyor: {ok} yangi, {skip} mavjud, {fail} xato")
    print(f"Index: {INDEX_FILE}")
    print(f"{len(index)} ta savol uchun audio tayyor -> demo_cache/")


if __name__ == "__main__":
    main()
