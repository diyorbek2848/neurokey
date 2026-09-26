# -*- coding: utf-8 -*-
"""
O'z kompingizda fayl/kod o'zgartirsangiz — avtomatik build qiladi va (agar NEUROKEY_UPDATE_FOLDER
qo'yilgan bo'lsa) yangi NeuroKey.zip ni shu papkaga yuboradi. Boshqa kompda shu papka sinxron
(OneDrive, Dropbox) bo'lsa — o'yin yangilanishi kabi avtomatik yangilanish keladi.

Ishga tushirish: python neurokey_autobuild.py   (oldinga qoldiring)
To'xtatish: Ctrl+C
"""
import os
import sys
import time
import subprocess

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECK_INTERVAL = 25  # sekund
SKIP_NAMES = {".venv", "__pycache__", "NeuroKey_Ilova", ".git", ".cache", ".torch-cache"}


def _max_mtime(path: str) -> float:
    """Papka yoki faylning oxirgi o'zgarish vaqtini qaytaradi."""
    if not os.path.exists(path):
        return 0.0
    if os.path.isfile(path):
        return os.path.getmtime(path)
    m = 0.0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_NAMES]
        for f in files:
            if f.endswith((".pyc", ".session")):
                continue
            p = os.path.join(root, f)
            try:
                m = max(m, os.path.getmtime(p))
            except OSError:
                pass
    return m


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(SOURCE_DIR, ".env"))
    except ImportError:
        pass
    update_folder = os.getenv("NEUROKEY_UPDATE_FOLDER", "").strip()
    if update_folder:
        print(f"Yangilanish papkasi: {update_folder}")
        print("O'zgarish kuzatilmoqda — fayl saqlasangiz build va yuborish avtomatik.")
    else:
        print("NEUROKEY_UPDATE_FOLDER .env da qo'ymang — build faqat loyihada, yuborish yo'q.")
    print("To'xtatish: Ctrl+C\n")
    last_build = 0.0
    last_mtime = _max_mtime(SOURCE_DIR)
    while True:
        time.sleep(CHECK_INTERVAL)
        try:
            now_mtime = _max_mtime(SOURCE_DIR)
            if now_mtime > last_mtime or (last_build == 0 and now_mtime > 0):
                print(f"[{time.strftime('%H:%M:%S')}] O'zgarish aniqlandi, build...")
                last_mtime = now_mtime
                r = subprocess.run(
                    [sys.executable, "build_ilova.py"],
                    cwd=SOURCE_DIR,
                    capture_output=False,
                )
                if r.returncode == 0:
                    last_build = time.time()
                    print("[OK] Build tugadi. Boshqa komp sinxron bo'lsa — yangilanish bor.\n")
                else:
                    print("[!] Build xato.\n")
        except KeyboardInterrupt:
            print("\nTo'xtatildi.")
            break
        except Exception as e:
            print(f"[!] {e}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
