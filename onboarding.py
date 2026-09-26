# -*- coding: utf-8 -*-
"""
NeuroKey — Onboarding (yangi foydalanuvchi sozlamasi)
=====================================================
Har bir yangi foydalanuvchi uchun:
  1. Ism so'raydi
  2. Yuzini ro'yxatdan o'tkazadi (kamera)
  3. Ovozini ro'yxatdan o'tkazadi (mikrofon)
  4. Profil saqlaydi (data/user_profile.json)

Ishlatish:  python onboarding.py
"""
import os, sys, json, time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
PROFILE_PATH = os.path.join(DATA_DIR, "user_profile.json")


def banner(t):
    print("\n" + "=" * 60)
    print("  " + t)
    print("=" * 60)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    banner("NEUROKEY — XUSH KELIBSIZ! (Yangi foydalanuvchi sozlamasi)")
    print("""
  NeuroKey — bu faqat SIZNI taniydigan shaxsiy AI.
  3 qadamda sozlaymiz: ism, yuz, ovoz.
""")

    # ── 1. ISM ──────────────────────────────────────────────
    banner("[1/3] Ismingiz")
    name = ""
    while not name.strip():
        try:
            name = input("  To'liq ismingizni kiriting: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bekor qilindi.")
            return
    nick = name.split()[0] if name.split() else name

    profile = {
        "full_name": name,
        "nick": nick,
        "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "role": "",
        "goals": [],
        "likes": ["tezkor yechimlar", "aniq reja"],
    }
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print(f"  Saqlandi. Salom, {nick}!")

    # ── 2. YUZ ──────────────────────────────────────────────
    banner("[2/3] Yuzingizni ro'yxatdan o'tkazish")
    print("  Kameraga to'g'ri qarang. Yorug' joyda o'tiring.")
    print("  Boshingizni asta o'ngga-chapga buring.\n")
    face_ok = False
    try:
        import face_arc
        input("  Tayyor bo'lsangiz ENTER bosing...")
        face_ok = face_arc.enroll_from_camera(camera_index=0, n_frames=120, name=name)
        print("  [OK] Yuz saqlandi!" if face_ok else "  [!] Yuz saqlanmadi — keyin qayta urinib ko'ring.")
    except Exception as e:
        print(f"  [!] Yuz xato: {e}")

    # ── 3. OVOZ ─────────────────────────────────────────────
    banner("[3/3] Ovozingizni ro'yxatdan o'tkazish")
    print("  Mikrofonga tabiiy gapiring (istalgan gap).")
    voice_ok = False
    try:
        import voice_ecapa
        voice_ok = voice_ecapa.enroll_from_mic(n_chunks=6, chunk_sec=5.0, name=name)
        print("  [OK] Ovoz saqlandi!" if voice_ok else "  [!] Ovoz saqlanmadi — keyin qayta urinib ko'ring.")
    except Exception as e:
        print(f"  [!] Ovoz xato: {e}")

    # ── YAKUN ───────────────────────────────────────────────
    banner("TAYYOR!")
    print(f"""
  Salom, {nick}! NeuroKey endi sizni taniydi.

  Yuz  : {'OK' if face_ok else 'keyin sozlanadi'}
  Ovoz : {'OK' if voice_ok else 'keyin sozlanadi'}

  Endi NeuroKey ni ishga tushiring:  !NeuroKey.bat
""")


if __name__ == "__main__":
    main()
