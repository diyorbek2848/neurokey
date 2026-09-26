# -*- coding: utf-8 -*-
"""
NeuroKey ilova paketini yig'ish — hozirgi loyihadan "oddiy ilova" uchun
alohida papka yaratadi va bitta NeuroKey.zip fayl qiladi.

Ishga tushirish: python build_ilova.py
Chiqish: NeuroKey_Ilova/ papka va NeuroKey.zip (bitta fayl — boshqa kompga shuni tashlang).
"""
import os
import shutil
import sys
import zipfile

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SOURCE_DIR, "NeuroKey_Ilova")

# Nusxalanadigan papkalar (ichida .py va kerakli fayllar)
COPY_DIRS = [
    "stt", "tts", "utils", "neurokey_logs", "src",
]

# Nusxalanadigan bitta fayllar (kengaytma bo'yicha yoki aniq)
COPY_FILES_GLOB = [
    "*.py", "*.bat", "*.ps1", "*.txt", "*.md", "*.json",
]
COPY_FILES_EXACT = [
    "requirements.txt", ".env.example", "config.py", "main.py",
    "NeuroKey_Bittada.bat",
    "Install_NeuroKey.bat", "Run_NeuroKey.bat", "Run_NeuroKey_Notebook.bat",
    "setup.bat", "setup.ps1", "download_vosk_model.py", "neurokey_check_update.py", "NeuroKey_CheckUpdate.bat",
    "PORTABLE.md", "ILOVA_README.txt", "README.txt", "README_NEUROKEY_SERVER.md",
    "README_GMAIL.md", "README_TELEGRAM_USER.txt",
]

# O'tkazib yuboriladigan (ilova paketiga kirmaydi)
SKIP_NAMES = {
    ".venv", "__pycache__", ".cache", ".torch-cache", ".git",
    "NeuroKey_Ilova", "Новая папка", "Новая папка (2)",
    "node_modules", ".env",
}
SKIP_SUFFIXES = (".pyc", ".session", ".session-journal", ".log", ".db")
# Tarqatishda kirmaydi (har bir kompda o'zi yaratiladi)
SKIP_FILES = {"credentials.json", "token.json", "conversation.json", "memory.json", "memory.jsonl"}

# Bo'sh papkalar (ilova ichida yaratiladi)
EMPTY_DIRS = ["data", "memory", "models"]


def should_skip(name):
    if name in SKIP_NAMES or name in SKIP_FILES:
        return True
    if any(name.endswith(s) for s in SKIP_SUFFIXES):
        return True
    return False


def copy_tree(src_dir, dst_dir, dirs_to_copy):
    for d in dirs_to_copy:
        src = os.path.join(src_dir, d)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(dst_dir, d)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=lambda _dir, names: [n for n in names if should_skip(n)])


def copy_single_files(src_dir, dst_dir):
    for name in os.listdir(src_dir):
        if should_skip(name):
            continue
        src = os.path.join(src_dir, name)
        if not os.path.isfile(src):
            continue
        if name == ".env":
            continue
        dst = os.path.join(dst_dir, name)
        shutil.copy2(src, dst)


def main():
    if os.path.exists(OUT_DIR):
        print(f"O'chirilmoqda: {OUT_DIR}")
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)
    print(f"Yig'ilmoqda: {OUT_DIR}")
    print()

    # Bitta fayllar
    copy_single_files(SOURCE_DIR, OUT_DIR)
    # Aniq kerakli fayllar (bazada bo'lmasa ham)
    for name in COPY_FILES_EXACT:
        src = os.path.join(SOURCE_DIR, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUT_DIR, name))

    # Papkalar
    copy_tree(SOURCE_DIR, OUT_DIR, COPY_DIRS)

    # models — faqat struktura yoki mavjud modellarni nusxalash (katta)
    src_models = os.path.join(SOURCE_DIR, "models")
    dst_models = os.path.join(OUT_DIR, "models")
    if os.path.isdir(src_models):
        if os.path.exists(dst_models):
            shutil.rmtree(dst_models)
        shutil.copytree(src_models, dst_models, ignore=lambda _d, n: [x for x in n if should_skip(x)])
    else:
        os.makedirs(dst_models, exist_ok=True)

    # data, memory — bo'sh
    for d in EMPTY_DIRS:
        path = os.path.join(OUT_DIR, d)
        os.makedirs(path, exist_ok=True)
        # data da .gitkeep yoki README
        readme = os.path.join(path, "README.txt")
        if d == "data" and not os.path.isfile(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write("Session va xotira fayllari shu yerda saqlanadi.\n")

    print("[OK] NeuroKey_Ilova tayyor.")
    # Bitta ZIP yaratish — boshqa kompga shuni tashlash yetadi
    zip_path = os.path.join(SOURCE_DIR, "NeuroKey.zip")
    print(f"ZIP yaratilmoqda: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(OUT_DIR):
            for name in files:
                if should_skip(name):
                    continue
                path = os.path.join(root, name)
                arc = os.path.relpath(path, OUT_DIR)
                zf.write(path, "NeuroKey/" + arc)
    print(f"[OK] NeuroKey.zip tayyor — boshqa kompga shu bitta faylni tashlang.")
    # Yangilanish serveri uchun: update_release papkaga nusxala (o'z kompda server ishlasa boshqa komp shu yerdan yuklaydi)
    update_release = os.path.join(SOURCE_DIR, "update_release")
    os.makedirs(update_release, exist_ok=True)
    try:
        shutil.copy2(zip_path, os.path.join(update_release, "NeuroKey.zip"))
    except Exception:
        pass
    # Avtomatik yangilanish: ZIP ni sinxron papkaga (OneDrive/Dropbox) nusxalash — ixtiyoriy
    update_folder = os.getenv("NEUROKEY_UPDATE_FOLDER", "").strip()
    if update_folder and os.path.isdir(update_folder):
        try:
            dest = os.path.join(update_folder, "NeuroKey.zip")
            shutil.copy2(zip_path, dest)
            print(f"[OK] Yangilanish yuborildi: {dest}")
            print("     Boshqa kompda shu papka sinxron bo'lsa (OneDrive/Dropbox) — yangilanish avtomatik keladi.")
        except Exception as e:
            print(f"[!] Sinxron papkaga nusxalash xato: {e}")
    elif update_folder:
        print(f"[!] NEUROKEY_UPDATE_FOLDER papka topilmadi: {update_folder}")
    print()
    print("O'z kompda o'zgarish qilsangiz — build_ilova.py yoki NeuroKey_AutoBuild.bat ni ishga tushiring;")
    print("  NEUROKEY_UPDATE_FOLDER qo'ysangiz, yangi ZIP avtomatik shu papkaga tushadi (boshqa komp sinxron qilsa — upgrade).")
    print()
    print("Boshqa kompda:")
    print("  1. NeuroKey.zip ni oching (Extract) yoki sinxron papkadagi yangi NeuroKey.zip ni oching.")
    print("  2. NeuroKey_Bittada.bat ni ishga tushiring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
