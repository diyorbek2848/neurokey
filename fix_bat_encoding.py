# -*- coding: utf-8 -*-
"""Batch fayllardan BOM olib tashlaydi va qator oxirini \\r\\n qiladi - CMD 'tle', 'cho' xatolarini oldini olish."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
BATS = [
    "setup.bat",
    "Install.bat",
    "Run_NeuroKey.bat",
    "run_neurokey_startup.bat",
    "America_Tooldir.bat",
    "PAPKA_yarat.bat",
    "ZIP_yarat.bat",
    "fix_bat_encoding.bat",
    "Run_Setup_Saklab.bat",
    "Setup_Tuzat_va_Ishga_Tushir.bat",
]

def fix(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as e:
        print("O'qilmadi", path, e)
        return False
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except Exception:
        text = raw.decode("cp1252")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))
    print("OK:", path)
    return True

if __name__ == "__main__":
    for name in BATS:
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            fix(path)
        else:
            print("Topilmadi:", name)
    print("\nTugadi. Endi setup.bat ni qayta ishga tushiring.")
