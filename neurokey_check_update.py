# -*- coding: utf-8 -*-
"""
Boshqa kompda: eganing kompidan yangilanishni yuklab oladi va o'rnatadi.
.env da: NEUROKEY_UPDATE_URL=http://EGA_KOMP_IP:8766  (masalan http://192.168.1.100:8766)

Ishga tushirish: python neurokey_check_update.py
yoki NeuroKey_CheckUpdate.bat
"""
import os
import sys
import zipfile
import shutil
import tempfile

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

APP_DIR = os.path.dirname(os.path.abspath(__file__))
URL = (os.getenv("NEUROKEY_UPDATE_URL") or "").strip().rstrip("/")


def main():
    if not URL or not URL.startswith("http"):
        print("NEUROKEY_UPDATE_URL .env da qo'ying: http://EGA_KOMP_IP:8766")
        return 1
    zip_url = URL + "/NeuroKey.zip"
    print(f"Yuklanmoqda: {zip_url}")
    try:
        import urllib.request
        req = urllib.request.Request(zip_url, headers={"User-Agent": "NeuroKey-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except Exception as e:
        print(f"Yuklab olish xato: {e}")
        print("Ega kompida NeuroKey_UpdateServer.bat ishlayotganini va IP to'g'riligini tekshiring.")
        return 1
    if not data:
        print("Fayl bo'sh.")
        return 1
    data_dir = os.path.join(APP_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    zip_path = os.path.join(data_dir, "NeuroKey_new.zip")
    with open(zip_path, "wb") as f:
        f.write(data)
    tmpdir = tempfile.mkdtemp(prefix="neurokey_upd_")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)
        inner = os.path.join(tmpdir, "NeuroKey")
        if not os.path.isdir(inner):
            inner = tmpdir
        # Fayllarni app papkaga nusxalash; .env va data/*.session saqlanadi
        skip_dirs = {".venv", "data", "__pycache__"}
        skip_files = (".env", "neurokey_locked", "neurokey_server.pid")
        copied = 0
        for root, dirs, files in os.walk(inner):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            rel = os.path.relpath(root, inner)
            for name in files:
                if name.endswith((".session", ".session-journal")) or name in skip_files:
                    continue
                if rel == "." and name in skip_files:
                    continue
                src = os.path.join(root, name)
                dst_dir = os.path.join(APP_DIR, rel) if rel != "." else APP_DIR
                os.makedirs(dst_dir, exist_ok=True)
                dst = os.path.join(dst_dir, name)
                try:
                    shutil.copy2(src, dst)
                    copied += 1
                except Exception:
                    pass
        print(f"[OK] Yangilanish qo'llanildi ({copied} fayl). NeuroKey ni qayta ishga tushiring.")
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
        try:
            os.remove(zip_path)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
