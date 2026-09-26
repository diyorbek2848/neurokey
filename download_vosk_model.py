# -*- coding: utf-8 -*-
"""
VOSK modelini avtomatik yuklab olish — boshqa kompda models/ bo'sh bo'lsa ishlatish mumkin.
Ishga tushirish: python download_vosk_model.py
"""
import os
import sys
import zipfile
import urllib.request

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
# Kichik rus modeli (~45 MB). Boshqa variant: vosk-model-small-uz-0.22
MODEL_NAME = "vosk-model-small-ru-0.22"
BASE_URL = "https://alphacephei.com/vosk/models"
ZIP_URL = f"{BASE_URL}/{MODEL_NAME}.zip"
TARGET_DIR = os.path.join(MODELS_DIR, MODEL_NAME)


def main():
    if os.path.isdir(TARGET_DIR):
        print(f"[OK] Model allaqachon mavjud: {TARGET_DIR}")
        return 0
    os.makedirs(MODELS_DIR, exist_ok=True)
    zip_path = os.path.join(MODELS_DIR, f"{MODEL_NAME}.zip")
    print(f"Yuklanmoqda: {ZIP_URL}")
    print("(bir necha daqiqa davom etishi mumkin, ~45 MB)")
    try:
        urllib.request.urlretrieve(ZIP_URL, zip_path)
    except Exception as e:
        print(f"[XATO] Yuklab olish: {e}")
        print("Qo'lda yuklab oling: https://alphacephei.com/vosk/models")
        print(f"ZIP ni ochib ichidagi '{MODEL_NAME}' papkasini '{MODELS_DIR}' ga qo'ying.")
        return 1
    print("ZIP ochilmoqda...")
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(MODELS_DIR)
    except Exception as e:
        print(f"[XATO] ZIP ochish: {e}")
        return 1
    try:
        os.remove(zip_path)
    except OSError:
        pass
    if not os.path.isdir(TARGET_DIR):
        # Ba'zi ZIP lar ichida bitta papka bor
        for name in os.listdir(MODELS_DIR):
            p = os.path.join(MODELS_DIR, name)
            if os.path.isdir(p) and name.startswith("vosk-model"):
                print(f"[OK] Model: {p}")
                return 0
        print("[!] Model papkasi topilmadi; MODELS_DIR ni qo'lda tekshiring.")
        return 1
    print(f"[OK] Model tayyor: {TARGET_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
