# -*- coding: utf-8 -*-
"""
download_avatar.py — NeuroKey VRM model yuklovchi

Bepul VRM model manbalar:
  1. three-vrm rasmiy test modeli (GitHub, MIT litsenziya)
  2. VRoid Hub (bepul modellar — https://hub.vroid.com)
  3. VRoid Studio (bepul yaratish — https://vroid.com/en/studio)

Ishga tushirish: python download_avatar.py
"""

import os
import sys
import urllib.request
import ssl

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
VRM_PATH   = os.path.join(ASSETS_DIR, "avatar.vrm")

# three-vrm rasmiy sample modellar (MIT litsenziya)
VRM_URLS = [
    # VRM 1.0 namuna model
    "https://raw.githubusercontent.com/pixiv/three-vrm/dev/packages/three-vrm/tests/models/VRM1_Constraint_Twist.vrm",
    # VRM 0.x namuna model (kengaytirilgan moslik)
    "https://raw.githubusercontent.com/vrm-c/vrm-specification/master/samples/Seed-san/vrm/Seed-san.vrm",
    # Zaqiuddin texnik model
    "https://github.com/vrm-c/VRM_CORE_SPEC/raw/main/samples/AliciaSolid.vrm",
]

def download(force: bool = False) -> bool:
    """
    VRM modelni yuklab oladi.
    force=True bo'lsa mavjud faylni ham qayta yuklab oladi.
    """
    os.makedirs(ASSETS_DIR, exist_ok=True)

    if os.path.exists(VRM_PATH) and not force:
        size = os.path.getsize(VRM_PATH)
        print(f"[HA] Model mavjud: {VRM_PATH} ({size // 1024} KB)")
        return True

    # SSL sertifikat tekshirishni o'chirib qo'yamiz (korporativ proxy uchun)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE

    for i, url in enumerate(VRM_URLS, 1):
        try:
            print(f"[{i}/{len(VRM_URLS)}] Yuklanmoqda: {url}")
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 NeuroKey/1.0"
            })
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                data = resp.read()
            with open(VRM_PATH, "wb") as f:
                f.write(data)
            size = os.path.getsize(VRM_PATH)
            if size < 1000:
                print(f"  [!] Juda kichik fayl ({size} bayt), o'tkazildi")
                os.unlink(VRM_PATH)
                continue
            print(f"[HA] Yuklandi: {VRM_PATH} ({size // 1024} KB)")
            return True
        except Exception as e:
            print(f"  [XATO] {e}")

    print()
    print("=" * 60)
    print("[!] Avtomatik yuklash muvaffaqiyatsiz.")
    print()
    print("Qo'lda bajarish (ikkitadan biri):")
    print()
    print("VARIANT 1 — VRoid Studio (TAVSIYA, bepul, go'zal model):")
    print("  1. https://vroid.com/en/studio")
    print("  2. Yuklab o'rnating")
    print("  3. Anime qiz personajini yarating")
    print("  4. File → Export VRM")
    print(f"  5. Saqlash joyi: {VRM_PATH}")
    print()
    print("VARIANT 2 — VRoid Hub (tayyor bepul modellar):")
    print("  1. https://hub.vroid.com")
    print("  2. Bepul model tanlang (CC0 yoki CC-BY)")
    print("  3. Yuklab oling (.vrm fayl)")
    print(f"  4. Ko'chiring: {VRM_PATH}")
    print("=" * 60)
    return False


def check() -> bool:
    """Modelning mavjudligini tekshiradi."""
    if not os.path.exists(VRM_PATH):
        print(f"[YOQ] Model topilmadi: {VRM_PATH}")
        return False
    size = os.path.getsize(VRM_PATH)
    if size < 1000:
        print(f"[!] Model fayli shubhali ({size} bayt): {VRM_PATH}")
        return False
    print(f"[HA] Model: {VRM_PATH} ({size // 1024} KB)")
    return True


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NeuroKey VRM model yuklovchi")
    ap.add_argument("--force", action="store_true", help="Qayta yuklash")
    ap.add_argument("--check", action="store_true", help="Faqat tekshirish")
    args = ap.parse_args()

    if args.check:
        ok = check()
        sys.exit(0 if ok else 1)
    else:
        ok = download(force=args.force)
        sys.exit(0 if ok else 1)
