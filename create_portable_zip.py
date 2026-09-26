# -*- coding: utf-8 -*-
"""NeuroKey — boshqa kompyuterga ko'chirish uchun ZIP yaratadi.
Ishga tushirish: python create_portable_zip.py
ZIP ichida: kod, setup.bat, .env.example, SETUP_RU.txt. .env va venv kiritilmaydi.
"""
import os
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.dirname(ROOT)
ZIP_NAME = f"NeuroKey_portable_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
OUTPUT = os.path.join(OUTPUT_DIR, ZIP_NAME)

EXCLUDE_DIRS = {
    ".venv", "__pycache__", ".git", ".cache", "__pyphi_cache__",
    "GPT-SoVITS", ".torch-cache", "neurokey_logs",
    "america", "blobs", "Unreal Projects",
    "Новая папка", "Новая папка (2)", "Новая папка (3)",
}
EXCLUDE_EXT = {".pyc", ".pyo", ".log", ".zip"}
EXCLUDE_FILES = {"credentials.json", "token.json", "$null"}
EXCLUDE_SESSION = (".session", ".session-journal")
# Katta/yoki shaxsiy fayllar — boshqa kompda qayta yaratiladi
EXCLUDE_DATA_PATTERNS = (".db", "backup")  # data/*.db, data/backup/*


def should_include(dirpath: str, name: str, fullpath: str = "", is_dir: bool = False) -> bool:
    if name in EXCLUDE_DIRS or name in EXCLUDE_FILES:
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
        # models/ ichidagi katta model fayllarini kiritma (VOSK boshqa kompda yuklanadi)
        if rel.replace("\\", "/").startswith("models/") and os.path.isfile(fullpath):
            try:
                if os.path.getsize(fullpath) > 5 * 1024 * 1024:
                    return False
            except Exception:
                pass
    return True


def create_zip():
    total = 0
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
        # NOUTBUK_README (qisqa; to'liq: SETUP_RU.txt — walk orqali kiritiladi)
        noutbuk_readme = """NeuroKey — boshqa kompda: ZIP ni oching, setup.bat ni ishga tushiring, .env da OPENAI_API_KEY kiriting. To'liq: SETUP_RU.txt"""
        zf.writestr("juma/NOUTBUK_README.txt", noutbuk_readme.encode("utf-8"))
        total += 1

        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if should_include(dirpath, d, "", is_dir=True)]
            rel = os.path.relpath(dirpath, ROOT)
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not should_include(dirpath, f, fp, is_dir=False):
                    continue
                arc = os.path.join("juma", rel, f) if rel != "." else os.path.join("juma", f)
                try:
                    zf.write(fp, arc)
                    total += 1
                except Exception as e:
                    print("Skip", fp, ":", e)

    print("ZIP tayyor:", OUTPUT)
    print("Fayllar soni:", total)
    print()
    print("Boshqa kompyuterga:")
    print("  1. ZIP ni oching, 'juma' papkasini chiqaring.")
    print("  2. setup.bat ni ishga tushiring (2 marta bosing).")
    print("  3. .env da OPENAI_API_KEY ni kiriting.")
    print("  4. Run_NeuroKey.bat yoki run_neurokey_startup.bat bilan ishga tushiring.")
    print("  To'liq ko'rsatma: SETUP_RU.txt")
    return OUTPUT


if __name__ == "__main__":
    create_zip()
