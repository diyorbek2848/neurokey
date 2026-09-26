# -*- coding: utf-8 -*-
"""NeuroKey o'rnatish — barcha holatda ishlaydi, xatolar log faylga yoziladi."""
import os
import sys
import subprocess
import shutil
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
LOG_FILE = os.path.join(ROOT, "neurokey_install.log")

# ── MUHIM: har doim o'rnatilishi KERAK bo'lgan paketlar ──────────────────────
CRITICAL = [
    "openai",
    "python-dotenv",
    "requests",
    "psutil",
    "sounddevice",
    "numpy",
    "vosk",
    "telethon",
    "python-pptx",
    "pillow",
    "pywin32",
    "pyperclip",
    "rapidfuzz",
    "langdetect",
    "aiohttp",
    "faiss-cpu",
    "pydub",
    "edge-tts",
    "pygetwindow",
    "mss",
    "pyautogui",
    "keyboard",
    "readability-lxml",
    "imageio-ffmpeg",
]

# ── IXTIYORIY: fail bo'lsa ham davom etadi ───────────────────────────────────
OPTIONAL = [
    # torch katta, lekin faqat lokal model uchun kerak
    ("torch==2.3.0", "torch"),
    ("torchaudio==2.3.0", "torchaudio"),
    # C++ Build Tools talab qiladi — yo'q bo'lsa o'tkazib yuboriladi
    ("simpleaudio", "simpleaudio"),
    # Murakkab paket — Python versiyasiga bog'liq
    ("pyphi", "pyphi"),
    # OCR — tesseract alohida o'rnatilishi kerak
    ("pytesseract", "pytesseract"),
    # OpenCV — ba'zan conflict bo'ladi
    ("opencv-python", "cv2"),
]


def log(msg):
    print(msg, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def run_pip(args, label=""):
    """pip ni ishga tushiradi, natijani qaytaradi."""
    cmd = [venv_py, "-m", "pip"] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            log(f"  pip xato ({label}): {(r.stderr or r.stdout or '')[:300].strip()}")
        return r.returncode
    except subprocess.TimeoutExpired:
        log(f"  pip timeout ({label}) — paket juda katta yoki internet sekin")
        return 1
    except Exception as e:
        log(f"  pip exception ({label}): {repr(e)}")
        return 1


# ─────────────────────────────────────────────────────────────────────────────

log("")
log("=" * 56)
log("  NeuroKey — o'rnatish")
log("=" * 56)
log(f"  Papka: {ROOT}")
log(f"  Log:   {LOG_FILE}")
log("")

# ── Loyiha fayllari mavjudligini tekshirish ──────────────────────────────────
if not os.path.isfile(os.path.join(ROOT, "main.py")):
    log("[XATO] main.py topilmadi — install.py ni loyiha papkasida ishga tushiring!")
    input("Chiqish uchun Enter bosing...")
    sys.exit(1)

log("[OK] Loyiha papkasi to'g'ri")

# ── Papkalar yaratish ─────────────────────────────────────────────────────────
for d in ("data", "memory", "neurokey_logs", "models"):
    os.makedirs(os.path.join(ROOT, d), exist_ok=True)
log("[OK] Papkalar: data, memory, neurokey_logs, models")

# ── .env fayl ────────────────────────────────────────────────────────────────
env_path = os.path.join(ROOT, ".env")
env_example = os.path.join(ROOT, ".env.example")
if not os.path.isfile(env_path):
    if os.path.isfile(env_example):
        shutil.copy(env_example, env_path)
        log("[!] .env yaratildi (.env.example dan)")
    else:
        log("[!] .env yo'q — keyinchalik OPENAI_API_KEY kiriting")
else:
    log("[OK] .env mavjud")

# ── Python yo'li ──────────────────────────────────────────────────────────────
py_cmd = sys.executable
log(f"[OK] Python: {py_cmd}  ({sys.version.split()[0]})")

venv_dir = os.path.join(ROOT, ".venv")
venv_py = os.path.join(venv_dir, "Scripts", "python.exe")

# Eski buzilgan .venv ni tozalash
if os.path.isfile(venv_py):
    r = subprocess.run([venv_py, "--version"], capture_output=True)
    if r.returncode != 0:
        log("[!] Eski .venv buzilgan, o'chirilmoqda...")
        try:
            shutil.rmtree(venv_dir)
            log("[OK] Eski .venv o'chirildi")
        except Exception as e:
            log(f"[XATO] .venv o'chirib bo'lmadi: {e}")
            input("Chiqish uchun Enter bosing...")
            sys.exit(1)

# ── Virtual muhit yaratish ────────────────────────────────────────────────────
if not os.path.isdir(venv_dir):
    log("Virtual muhit yaratilmoqda (.venv)...")
    r = subprocess.run([py_cmd, "-m", "venv", venv_dir], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"[XATO] .venv yaratib bo'lmadi: {r.stderr[:300]}")
        input("Chiqish uchun Enter bosing...")
        sys.exit(1)
    log("[OK] .venv yaratildi")
else:
    log("[OK] .venv mavjud")

if not os.path.isfile(venv_py):
    log("[XATO] .venv\\Scripts\\python.exe topilmadi")
    input("Chiqish uchun Enter bosing...")
    sys.exit(1)

# ── pip yangilash ─────────────────────────────────────────────────────────────
log("pip yangilanmoqda...")
run_pip(["install", "--upgrade", "pip", "--quiet"], "pip upgrade")

# ── MUHIM paketlarni o'rnatish ────────────────────────────────────────────────
log("")
log(f"MUHIM paketlar o'rnatilmoqda ({len(CRITICAL)} ta)...")
critical_failed = []
for pkg in CRITICAL:
    log(f"  -> {pkg}")
    code = run_pip(["install", pkg, "--quiet", "--no-warn-script-location"], pkg)
    if code != 0:
        critical_failed.append(pkg)
        log(f"  [!] {pkg} o'rnatilmadi — keyinroq qayta urinib ko'ring")

if critical_failed:
    log("")
    log(f"[!] {len(critical_failed)} ta muhim paket o'rnatilmadi: {', '.join(critical_failed)}")
    log("    NeuroKey ishlashi uchun qayta urinib ko'ring.")
else:
    log("[OK] Barcha muhim paketlar o'rnatildi")

# ── IXTIYORIY paketlarni o'rnatish ───────────────────────────────────────────
log("")
log(f"Ixtiyoriy paketlar o'rnatilmoqda ({len(OPTIONAL)} ta, xato bo'lsa o'tkaziladi)...")
optional_failed = []
for pkg, label in OPTIONAL:
    log(f"  -> {pkg}")
    code = run_pip(["install", pkg, "--quiet", "--no-warn-script-location"], label)
    if code != 0:
        optional_failed.append(label)
        log(f"  [skip] {label} o'rnatilmadi — bu ixtiyoriy, davom etilmoqda")

if optional_failed:
    log(f"[!] O'tkazilgan ixtiyoriy paketlar: {', '.join(optional_failed)}")
    log("    NeuroKey asosiy funksiyalari ishlaydi.")

# ── Yakuniy natija ────────────────────────────────────────────────────────────
log("")
log("=" * 56)
if critical_failed:
    log("  O'rnatish QISMAN tugadi (ba'zi muhim paketlar yo'q)")
    log(f"  Muammo: {', '.join(critical_failed)}")
    log("  BOSING.bat ni qayta ishga tushiring.")
else:
    log("  O'rnatish MUVAFFAQIYATLI tugadi!")
    log("  NeuroKey ishga tushmoqda...")
log("=" * 56)
log("")
