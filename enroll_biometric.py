# -*- coding: utf-8 -*-
"""
enroll_biometric.py — NeuroKey Biometrik Ro'yxatga Olish
=========================================================
Yuz + Ovoz — ikkalasini bir skriptda ro'yxatga oladi.

Ishlatish:
  python enroll_biometric.py           → ikkalasi
  python enroll_biometric.py --face    → faqat yuz
  python enroll_biometric.py --voice   → faqat ovoz
  python enroll_biometric.py --test    → mavjud profilni sinash

Natija:
  data/face_arc_profile.npy   — ArcFace 512-dim
  data/voice_ecapa_profile.npy — ECAPA-TDNN 192-dim
"""
import os, sys, time, argparse
import numpy as np

def _anykey(msg="  Boshlash uchun ISTALGAN TUGMANI bosing..."):
    """Enter kutmasdan istalgan tugma bilan davom etish (Windows)."""
    print(msg, flush=True)
    try:
        import msvcrt
        msvcrt.getch()
    except Exception:
        input()

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

NAME = "Diyorbek"

# Rang kodlari
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"

def banner(title):
    print(f"\n{C}{'='*54}{X}")
    print(f"{B}  {title}{X}")
    print(f"{C}{'='*54}{X}")


# ─────────────────────────────────────────────────────────────────────────────
# YUZ RO'YXATDAN O'TISH — ArcFace
# ─────────────────────────────────────────────────────────────────────────────
def enroll_face():
    banner("YUZ — ArcFace (512-dim, ~99% aniqlik)")
    print(f"""
  Talab:
    ✓ Yaxshi yorug'lik (kunda yoki lampada)
    ✓ Kameraga to'g'ri qarang
    ✓ Asta-sekin boshingizni chap/o'ng/yuqori/pastga aylantiring
    ✓ Ko'zoynak bor bo'lsa — ko'zoynak bilan ham, usiz ham gapiring

  {Y}120 ta kadr olinadi (~30 sekund).{X}
""")
    _anykey()

    print("\n  Model yuklanmoqda (birinchi marta: ~15s)...")
    from face_arc import enroll_from_camera, get_status

    ok = enroll_from_camera(camera_index=0, n_frames=120, name=NAME)
    if ok:
        st = get_status()
        print(f"\n  {G}✓ Yuz profili saqlandi!{X}")
        print(f"    Metod:   {st['method']}")
        print(f"    Chegara: {st['threshold']}")
    else:
        print(f"\n  {R}✗ Yuz ro'yxatdan o'tmadi. Yorug'lik yetarli emas yoki kamera yo'q.{X}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# OVOZ RO'YXATDAN O'TISH — ECAPA-TDNN
# ─────────────────────────────────────────────────────────────────────────────
def enroll_voice():
    banner("OVOZ — ECAPA-TDNN (192-dim, ~98% aniqlik)")
    print(f"""
  Talab:
    ✓ Jimroq joy
    ✓ Mikrofonga yaqin (15-30sm)
    ✓ Tabiiy, oddiy ovozda gapiring
    ✓ Har xil gap aytsa bo'ladi (savol, hikoya, raqamlar)

  {Y}10 ta yozuv, har biri 5 sekund (jami ~1 daqiqa).{X}
""")

    print("  Model yuklanmoqda (birinchi marta: ~30s)...")
    from voice_ecapa import enroll_from_mic, get_status

    ok = enroll_from_mic(n_chunks=10, chunk_sec=5.0, name=NAME)
    if ok:
        st = get_status()
        print(f"\n  {G}✓ Ovoz profili saqlandi!{X}")
        print(f"    Metod:   {st['method']}")
        print(f"    Chegara: {st['threshold']}")
    else:
        print(f"\n  {R}✗ Ovoz ro'yxatdan o'tmadi.{X}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# SINASH — Mavjud profilni tekshirish
# ─────────────────────────────────────────────────────────────────────────────
def test_biometric():
    banner("SINASH — Mavjud profilni tekshirish")

    # Yuz sinash
    print(f"\n  {C}[YUZ SINASH]{X}")
    try:
        from face_arc import identify_from_camera, profile_exists, get_status
        if not profile_exists():
            print(f"  {Y}Profil yo'q — avval enroll qiling{X}")
        else:
            st = get_status()
            print(f"  Profil: {st['owner']} ({st['enrolled_at'][:10]})")
            print("  Kameraga qarang...")
            time.sleep(1)
            result = identify_from_camera()
            sim  = result.get("similarity", 0)
            known = result.get("known", False)
            status = f"{G}✓ TANILDI{X}" if known else f"{R}✗ TANILMADI{X}"
            print(f"  Natija: {status} | O'xshashlik: {sim:.3f} (chegara: {result.get('threshold', 0.45):.2f})")
    except Exception as e:
        print(f"  {R}Xato: {e}{X}")

    # Ovoz sinash
    print(f"\n  {C}[OVOZ SINASH]{X}")
    try:
        import sounddevice as sd
        from voice_ecapa import identify, profile_exists as vp_exists, get_status as vg_status

        if not vp_exists():
            print(f"  {Y}Profil yo'q — avval enroll qiling{X}")
        else:
            st = vg_status()
            print(f"  Profil: {st['owner']} ({st['enrolled_at'][:10]})")
            print("  5 sekund gapiring... (tabiiy gapiravering)")
            frames = sd.rec(int(16000 * 5), samplerate=16000, channels=1, dtype="int16")
            for i in range(5, 0, -1):
                print(f"  {i}...", end=" ", flush=True)
                time.sleep(1)
            sd.wait()
            print()
            audio = frames[:, 0].astype(np.float32) / 32768.0
            result = identify(audio)
            sim  = result.get("similarity", 0)
            known = result.get("known", False)
            status = f"{G}✓ TANILDI{X}" if known else f"{R}✗ TANILMADI{X}"
            print(f"  Natija: {status} | O'xshashlik: {sim:.3f} (chegara: {result.get('threshold', 0.75):.2f})")
    except Exception as e:
        print(f"  {R}Xato: {e}{X}")

    print()


# ─────────────────────────────────────────────────────────────────────────────
# BIOMETRIK GUARDIAN YANGILASH
# ─────────────────────────────────────────────────────────────────────────────
def update_guardian():
    """biometric_guardian.py ni yangi modullarga ulab qo'yish (runtime)."""
    try:
        import biometric_guardian as bg
        # Yangi verify funksiyalarini override qilish
        from face_arc  import identify_from_camera as _face_id
        from voice_ecapa import identify as _voice_id

        def _new_verify_face(frame=None):
            r = _face_id() if frame is None else __import__('face_arc').identify(frame)
            return r.get("known", False), r.get("similarity", 0.0)

        def _new_verify_voice(audio_np=None, sample_rate=16000):
            if audio_np is None:
                return False, 0.0
            r = _voice_id(audio_np)
            return r.get("known", False), r.get("similarity", 0.0)

        bg.verify_face  = _new_verify_face
        bg.verify_voice = _new_verify_voice
        print(f"  {G}✓ Guardian yangilandi — ArcFace + ECAPA aktiv{X}")
    except Exception as e:
        print(f"  {Y}Guardian yangilanmadi (runtime): {e}{X}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NeuroKey Biometrik Ro'yxatdan O'tish")
    parser.add_argument("--face",  action="store_true", help="Faqat yuz")
    parser.add_argument("--voice", action="store_true", help="Faqat ovoz")
    parser.add_argument("--test",  action="store_true", help="Sinash")
    args = parser.parse_args()

    if args.test:
        test_biometric()
        return

    banner(f"NeuroKey Biometrik Ro'yxatdan O'tish — {NAME}")
    print(f"""
  Bu skript ikki narsani o'rgatadi:
    1. {C}Yuz (ArcFace){X}  — 99% aniqlik, kamera orqali
    2. {C}Ovoz (ECAPA){X}  — 98% aniqlik, mikrofon orqali

  Shundan keyin NeuroKey FAQAT sizning yuz va ovozingizni taniydi.
  Boshqa kishi gapirsa — rad etadi.
""")

    if args.face:
        enroll_face()
    elif args.voice:
        enroll_voice()
    else:
        # Ikkalasi
        face_ok = enroll_face()
        print()
        voice_ok = enroll_voice()
        print()
        banner("NATIJA")
        print(f"  Yuz  (ArcFace):  {'✓ TAYYOR' if face_ok  else '✗ XATO'}")
        print(f"  Ovoz (ECAPA):    {'✓ TAYYOR' if voice_ok else '✗ XATO'}")
        if face_ok or voice_ok:
            print(f"\n  {G}NeuroKey biometrik himoya faollashdi!{X}")
            print(f"  START_NEUROKEY.bat qayta ishga tushiring.\n")
        else:
            print(f"\n  {R}Hech biri o'tmadi. Qayta urinib ko'ring.{X}\n")

    update_guardian()


if __name__ == "__main__":
    main()
