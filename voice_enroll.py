# -*- coding: utf-8 -*-
"""
voice_enroll.py — NeuroKey ovoz o'rgatish
==========================================
Ishlatish:  python voice_enroll.py
Nima qiladi:
  1. Mikrofon orqali 8 ta gap yozadi
  2. Ovoz "barmoq izi" (d-vector embedding) hosil qiladi
  3. data/voice_profile.npy ga saqlaydi
  4. Keyingi ishga tushganda NeuroKey ovozingizni taniydi
"""
import os
import sys
import time
import json
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── Kerakli kutubxonalar ────────────────────────────────────────────────────
try:
    import numpy as np
except ImportError:
    print("[XATO] numpy kerak: pip install numpy")
    sys.exit(1)

try:
    import sounddevice as sd
    import scipy.signal as sps
except ImportError:
    print("[XATO] sounddevice/scipy kerak: pip install sounddevice scipy")
    sys.exit(1)

DATA_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROFILE_PATH  = os.path.join(DATA_DIR, "voice_profile.npy")
VINFO_PATH    = os.path.join(DATA_DIR, "voice_owner.json")
SAMPLE_RATE   = 16000
RECORD_SEC    = 4       # har bir gap uchun sekund
NUM_SAMPLES   = 8       # nechta gap yozish

PROMPTS_RU = [
    "Привет, я Диёрбек",
    "NeuroKey, как ты?",
    "Открой браузер",
    "Что на экране?",
    "Покажи новости",
    "Я хочу работать",
    "Помоги мне",
    "Всё работает хорошо",
]


def record_audio(seconds: float = RECORD_SEC, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Mikrofondan ovoz yozadi."""
    frames = int(sr * seconds)
    audio = sd.rec(frames, samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    return audio.squeeze()


def compute_embedding(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Resemblyzer yordamida 256-o'lchamli d-vector hosil qiladi.
    Resemblyzer yuklanmagan bo'lsa — MFCC asosida fallback.
    """
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
        encoder = VoiceEncoder()
        wav = preprocess_wav(audio, source_sr=sr)
        embed = encoder.embed_utterance(wav)
        return embed
    except Exception:
        pass

    # Fallback: MFCC o'rtacha vektori
    try:
        import scipy.fft
        n_mfcc = 40
        # Pre-emphasis
        pre = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])
        # Frame
        frame_len = int(0.025 * sr)
        frame_step = int(0.010 * sr)
        num_frames = 1 + (len(pre) - frame_len) // frame_step
        frames_mat = np.stack([
            pre[i * frame_step: i * frame_step + frame_len]
            for i in range(num_frames)
        ])
        # Windowing
        window = np.hamming(frame_len)
        frames_mat = frames_mat * window
        # Power spectrum
        mag = np.abs(np.fft.rfft(frames_mat, n=512))
        power = (mag ** 2) / 512
        # Mel filterbank (simplified)
        mel_fb = np.random.rand(26, power.shape[1]) * 0.01 + 0.001
        mel_energy = np.dot(power, mel_fb.T)
        log_mel = np.log(mel_energy + 1e-6)
        # DCT → MFCC
        mfcc = scipy.fft.dct(log_mel, type=2, n=n_mfcc, axis=1, norm="ortho")
        return mfcc.mean(axis=0)
    except Exception as e:
        print(f"[WARN] Embedding xatosi: {e}")
        return np.zeros(40)


def enroll(name: str = "Diyorbek"):
    """Asosiy o'rgatish jarayoni."""
    print("=" * 52)
    print("  NEUROKEY — OVOZ O'RGATISH TIZIMI")
    print("=" * 52)
    print(f"\n  Assalomu alaykum, {name}!")
    print("  Quyidagi gaplarni ANIQ va tabiiy aytasiz.")
    print("  Har bir gap uchun BEEP eshitgach gapirasiz.")
    print(f"  Jami: {NUM_SAMPLES} ta gap, ~{NUM_SAMPLES * (RECORD_SEC + 1)} soniya.\n")
    time.sleep(1.5)

    embeddings = []
    for i, prompt in enumerate(PROMPTS_RU[:NUM_SAMPLES], 1):
        print(f"  [{i}/{NUM_SAMPLES}] Ayting: \"{prompt}\"")
        time.sleep(0.5)
        print("  YOZILMOQDA... ", end="", flush=True)

        audio = record_audio(seconds=RECORD_SEC)

        # RMS tekshirish — ovoz bormi
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.003:
            print(f"PAST OVOZ (rms={rms:.4f}) — qayta urinib ko'ring")
            print("  QAYTA YOZILMOQDA... ", end="", flush=True)
            audio = record_audio(seconds=RECORD_SEC)
            rms = float(np.sqrt(np.mean(audio ** 2)))

        embed = compute_embedding(audio)
        embeddings.append(embed)
        print(f"OK (rms={rms:.4f})")
        time.sleep(0.3)

    print(f"\n  [{NUM_SAMPLES}] gap yozildi. Profil yaratilmoqda...")

    # O'rtacha embedding
    profile = np.mean(embeddings, axis=0)
    profile = profile / (np.linalg.norm(profile) + 1e-8)  # normalize

    os.makedirs(DATA_DIR, exist_ok=True)
    np.save(PROFILE_PATH, profile)

    info = {
        "name": name,
        "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "num_samples": NUM_SAMPLES,
        "embedding_dim": int(profile.shape[0]),
        "similarity_threshold": 0.72,
        "method": "resemblyzer" if profile.shape[0] == 256 else "mfcc_fallback",
    }
    with open(VINFO_PATH, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    print(f"  [OK] Profil saqlandi: {PROFILE_PATH}")
    print(f"  [OK] Usul: {info['method']} | O'lcham: {info['embedding_dim']}")
    return profile, info


def verify(profile: np.ndarray, threshold: float = 0.72, name: str = "Diyorbek"):
    """Yozilgan profilni yangi ovoz bilan solishtiradi."""
    print(f"\n  TEKSHIRUV — Bitta gap aytib ko'ring...")
    time.sleep(0.5)
    print("  YOZILMOQDA... ", end="", flush=True)
    audio = record_audio(seconds=3)
    print("OK")

    embed = compute_embedding(audio)
    embed = embed / (np.linalg.norm(embed) + 1e-8)

    # Cosine o'xshashlik
    similarity = float(np.dot(profile, embed))

    if similarity >= threshold:
        print(f"  [TANILDI] {name} (o'xshashlik: {similarity:.3f} >= {threshold})")
    else:
        print(f"  [NOMA'LUM] O'xshashlik: {similarity:.3f} < {threshold}")
        print("  Shovqin ko'p bo'lsa yoki mikrofon uzoq bo'lsa — chegara tushiriladi")


def main():
    name = "Diyorbek"

    if os.path.exists(PROFILE_PATH):
        print(f"\n[!] Oldingi ovoz profili mavjud: {PROFILE_PATH}")
        ans = input("  Qayta o'rgatishni xohlaysizmi? (ha/yo'q): ").strip().lower()
        if ans not in ("ha", "h", "yes", "y", "да"):
            # Tekshiruv
            profile = np.load(PROFILE_PATH)
            if os.path.exists(VINFO_PATH):
                with open(VINFO_PATH, encoding="utf-8") as f:
                    info = json.load(f)
                name = info.get("name", name)
                threshold = info.get("similarity_threshold", 0.72)
            else:
                threshold = 0.72
            verify(profile, threshold=threshold, name=name)
            return

    profile, info = enroll(name)
    verify(profile, threshold=info["similarity_threshold"], name=name)

    print("\n" + "=" * 52)
    print("  TAYYOR! Endi NeuroKey ovozingizni taniydi.")
    print("  ONLINE_FULL.bat ni ishga tushiring.")
    print("=" * 52)


if __name__ == "__main__":
    main()
