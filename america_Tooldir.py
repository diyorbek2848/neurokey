# -*- coding: utf-8 -*-
"""america papkasini barcha kerakli kodlar va setup bilan to'ldiradi.
Ishga tushirish: python america_Tooldir.py yoki America_Tooldir.bat
"""
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(ROOT, "america")

EXCLUDE_DIRS = {
    ".venv", "__pycache__", ".git", ".cache", "__pyphi_cache__",
    "GPT-SoVITS", ".torch-cache", "neurokey_logs",
    "Новая папка", "Новая папка (2)", "Новая папка (3)",
    "america",  # america ichiga america nusxalamaymiz
}
EXCLUDE_EXT = {".pyc", ".pyo", ".log"}
EXCLUDE_FILES = {"credentials.json", "token.json", "$null",
                 "america_Tooldir.py", "America_Tooldir.bat"}
EXCLUDE_SESSION = (".session", ".session-journal")
EXCLUDE_DATA_PATTERNS = (".db", "backup")
MAX_MODEL_MB = 5


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
        if rel.replace("\\", "/").startswith("models/") and os.path.isfile(fullpath):
            try:
                if os.path.getsize(fullpath) > MAX_MODEL_MB * 1024 * 1024:
                    return False
            except Exception:
                pass
    return True


def copy_to_america():
    if not os.path.exists(OUTPUT):
        os.makedirs(OUTPUT, exist_ok=True)
        print("america papkasi yaratildi.")
    total = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if should_include(dirpath, d, "", is_dir=True)]
        rel = os.path.relpath(dirpath, ROOT)
        if rel.startswith("america"):
            continue
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
    for folder in ("data", "memory", "neurokey_logs", "models"):
        path = os.path.join(OUTPUT, folder)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
    # Boshqa kompda pyphi C++ kompilyator talab qiladi — portable requirements ishlatamiz
    portable_req = os.path.join(ROOT, "requirements-portable.txt")
    if os.path.isfile(portable_req):
        shutil.copy(portable_req, os.path.join(OUTPUT, "requirements.txt"))
        print("america ga requirements-portable.txt (pyphi siz) yozildi.")
    readme = """================================================================================
  NEUROKEY — BOSHQA KOMP UCHUN (faqat Python, .bat kerak emas)
================================================================================

BOSHQA KOMPDA FAQAT 2 TA BUYRUQ:

  1) Birinchi marta o'rnatish (bir marta):
     CMD yoki PowerShell oching, BU PAPKAGA kiring (cd papka_yoli).
     Yozing:  python install.py
     (2–5 min kuting)

  2) .env faylini oching (Notepad), OPENAI_API_KEY=sk-... kiriting, saqlang.

  3) Dasturni ishga tushirish (har safar):
     python run.py

.bat fayllar kerak emas — faqat python install.py va python run.py.
Python yo'q bo'lsa: python.org — 3.10 yoki 3.11, "Add Python to PATH" belgilang.
Bu papkada pyphi (IIT) o'rnatilmaydi — C++ kompilyator kerak emas. Asosiy funksiyalar ishlaydi.
================================================================================
"""
    with open(os.path.join(OUTPUT, "OQISH_MANI.txt"), "w", encoding="utf-8") as f:
        f.write(readme)
    total += 1
    env_help = """================================================================================
  OPENAI_API_KEY .env da to'g'ri yozish
================================================================================
.env ni oching. Aniq shunday qator: OPENAI_API_KEY=sk-proj-...
= dan keyin bo'sh joy YO'Q, qo'shtirnoq YO'Q. Saqlang.
Tekshirish: python check_env.py   Keyin: python run.py
================================================================================
"""
    with open(os.path.join(OUTPUT, "ENV_KALIT_YORIQNOMASI.txt"), "w", encoding="utf-8") as f:
        f.write(env_help)
    total += 1
    print()
    print("Tayyor: america papkasi to'ldirildi.")
    print("Fayllar:", total)
    print("Ichida: kodlar, install.py, run.py, requirements.txt, .env.example.")
    print("Boshqa kompda: python install.py (bir marta), keyin python run.py.")
    print()
    return OUTPUT


if __name__ == "__main__":
    copy_to_america()
