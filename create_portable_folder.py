# -*- coding: utf-8 -*-
"""NeuroKey — boshqa kompyuterga ko'chirish uchun tayyor PAPKA yaratadi.
Papka ichida: barcha kerakli kodlar, setup.bat, .env.example.
.venv, .env, katta modellar kiritilmaydi.
Ishga tushirish: python create_portable_folder.py yoki PAPKA_yarat.bat
"""
import os
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.dirname(ROOT)
FOLDER_NAME = f"NeuroKey_boshqa_komp_{datetime.now().strftime('%Y%m%d_%H%M')}"
OUTPUT = os.path.join(OUTPUT_DIR, FOLDER_NAME)

EXCLUDE_DIRS = {
    ".venv", "__pycache__", ".git", ".cache", "__pyphi_cache__",
    "GPT-SoVITS", ".torch-cache", "neurokey_logs",
    "Новая папка", "Новая папка (2)", "Новая папка (3)",
}
EXCLUDE_EXT = {".pyc", ".pyo", ".log"}
EXCLUDE_FILES = {".env", "credentials.json", "token.json", "$null"}
EXCLUDE_SESSION = (".session", ".session-journal")
EXCLUDE_DATA_PATTERNS = (".db", "backup")
# SHAXSIY/BIOMETRIK ma'lumot — boshqa kompga CHIQMAYDI (har kim o'zini yozadi)
EXCLUDE_PERSONAL = {
    "user_profile.json",
    "face_arc_profile.npy", "face_arc_info.json",
    "voice_ecapa_profile.npy", "voice_ecapa_info.json",
    "voice_profile.npy", "voice_info.json",
    "owner_info.json", "face_model.yml", "faces.npy",
}
MAX_MODEL_MB = 5  # models/ ichida shundan katta fayllar kiritilmaydi


def should_include(dirpath: str, name: str, fullpath: str = "", is_dir: bool = False) -> bool:
    if name in EXCLUDE_DIRS or name in EXCLUDE_FILES:
        return False
    if name in EXCLUDE_PERSONAL:
        return False
    if name.endswith(EXCLUDE_SESSION):
        return False
    parts = dirpath.replace("\\", "/").split("/")
    if any(p in EXCLUDE_DIRS for p in parts):
        return False
    if is_dir and "data" in parts and name == "backup":
        return False
    if not is_dir:
        ext = os.path.splitext(name)[1].lower()
        if ext in EXCLUDE_EXT:
            return False
        rel = os.path.relpath(fullpath or os.path.join(dirpath, name), ROOT)
        if rel.replace("\\", "/").startswith("data/"):
            if any(p in name for p in EXCLUDE_DATA_PATTERNS) or "backup" in rel:
                return False
        if rel.replace("\\", "/").startswith("models/") and os.path.isfile(fullpath):
            try:
                if os.path.getsize(fullpath) > MAX_MODEL_MB * 1024 * 1024:
                    return False
            except Exception:
                pass
    return True


def create_portable_folder():
    if os.path.exists(OUTPUT):
        try:
            shutil.rmtree(OUTPUT)
        except Exception as e:
            print("Eski papka o'chirilmadi:", e)
            return None
    os.makedirs(OUTPUT, exist_ok=True)
    total = 0

    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if should_include(dirpath, d, "", is_dir=True)]
        rel = os.path.relpath(dirpath, ROOT)
        if rel == ".":
            dest_dir = OUTPUT
        else:
            dest_dir = os.path.join(OUTPUT, rel)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        for f in filenames:
            src = os.path.join(dirpath, f)
            if not should_include(dirpath, f, src, is_dir=False):
                continue
            dest = os.path.join(dest_dir, f)
            try:
                shutil.copy2(src, dest)
                total += 1
            except Exception as e:
                print("Skip", src, ":", e)

    # Bo'sh papkalar (boshqa kompda setup.bat yaratadi, lekin bo'lsa yaxshi)
    for folder in ("data", "memory", "neurokey_logs", "models"):
        path = os.path.join(OUTPUT, folder)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

    # Qisqa ko'rsatma papka ichida
    readme = """================================================================================
  NEUROKEY — BOSHQA KOMPYUTERGA KO'CHIRISH UCHUN TAYYOR PAPKA
================================================================================

Bu papkani USB yoki boshqa usul bilan boshqa kompyuterga ko'chiring.
Ichida barcha kerakli kodlar bor. .venv va .env kiritilmagan (boshqa kompda yangilanadi).

BOSHQA KOMPDA:
  1. Python 3.10 yoki 3.11 o'rnating (Add Python to PATH belgilang)
  2. Bu papkani oching va setup.bat ni ikki marta bosing
  3. .env faylini ochib OPENAI_API_KEY=sk-... kiriting
  4. Run_NeuroKey.bat ni ishga tushiring

To'liq ko'rsatma: BOSHQA_KOMPDA_ISHLATISH.txt
================================================================================
"""
    readme_path = os.path.join(OUTPUT, "OQISH_MANI.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    total += 1

    print()
    print("Tayyor papka:", OUTPUT)
    print("Fayllar soni:", total)
    print()
    print("Bu papkani boshqa kompga ko'chiring (USB, cloud, ...).")
    print("Boshqa kompda: setup.bat -> .env da kalit -> Run_NeuroKey.bat")
    print()
    return OUTPUT


if __name__ == "__main__":
    create_portable_folder()
