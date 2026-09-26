# -*- coding: utf-8 -*-
"""
face_enroll.py — NeuroKey yuz o'rgatish
========================================
Ishlatish:  python face_enroll.py
Nima qiladi:
  1. Kameradan 40 ta yuz rasmi oladi
  2. LBPH modeli o'rgatadi
  3. data/face_model.yml ga saqlaydi
  4. Keyingi ishga tushganda NeuroKey sizni taniydi

Talab: kameraga to'g'ri qarang, yaxshi yoritilgan bo'lsin.
"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

try:
    import cv2
    import numpy as np
except ImportError:
    print("[XATO] OpenCV o'rnatilmagan: pip install opencv-python")
    sys.exit(1)

# ─── Sozlamalar ──────────────────────────────────────────────────────────────
DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MODEL_PATH   = os.path.join(DATA_DIR, "face_model.yml")
OWNER_PATH   = os.path.join(DATA_DIR, "face_owner.json")
SAMPLES_DIR  = os.path.join(DATA_DIR, "face_samples")
NUM_SAMPLES  = 40          # nechta rasm olish
OWNER_LABEL  = 1           # 1 = egasi (Diyorbek)
CASCADE_NAME = "haarcascade_frontalface_default.xml"
CAMERA_INDEX = 0
MIN_FACE_SIZE = (60, 60)   # minimum yuz o'lchovi pikselda


def _get_cascade():
    cascade_dir = os.path.join(os.path.dirname(cv2.__file__), "data")
    path = os.path.join(cascade_dir, CASCADE_NAME)
    if not os.path.exists(path):
        print(f"[XATO] Cascade topilmadi: {path}")
        return None
    return cv2.CascadeClassifier(path)


def _preprocess_face(gray_img, x, y, w, h, target=(200, 200)):
    """Yuz regionini ajratib, standart o'lchamga o'tkazadi."""
    face = gray_img[y:y+h, x:x+w]
    face = cv2.resize(face, target)
    face = cv2.equalizeHist(face)   # kontrast tenglashtirish
    return face


def capture_samples(name: str = "Diyorbek"):
    """Kameradan yuz namunalari oladi."""
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    cascade = _get_cascade()
    if cascade is None:
        return []

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("[XATO] Kamera topilmadi!")
        return []

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print(f"\n[O'RGATISH] Assalomu alaykum, {name}!")
    print("[O'RGATISH] Kameraga to'g'ri qarang.")
    print("[O'RGATISH] Biroz harakatlaning — chapga, o'ngga, yuqoriga.")
    print(f"[O'RGATISH] {NUM_SAMPLES} ta rasm olinadi. Boshlayapmiz...\n")
    time.sleep(1.5)

    faces_data = []
    count = 0
    last_count_time = time.time()

    while count < NUM_SAMPLES:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=MIN_FACE_SIZE,
        )

        for (x, y, w, h) in faces:
            face_roi = _preprocess_face(gray, x, y, w, h)
            faces_data.append(face_roi)
            count += 1

            # Namunani saqlash
            sample_path = os.path.join(SAMPLES_DIR, f"face_{count:03d}.jpg")
            cv2.imwrite(sample_path, face_roi)

            now = time.time()
            if now - last_count_time > 0.3:
                bar = "#" * count + "." * (NUM_SAMPLES - count)
                pct = int(count / NUM_SAMPLES * 100)
                print(f"\r  [{bar}] {pct}% ({count}/{NUM_SAMPLES})", end="", flush=True)
                last_count_time = now

            if count >= NUM_SAMPLES:
                break

        # Kichik pauza — turli burchakda olish uchun
        time.sleep(0.12)

    cap.release()
    print(f"\n\n[OK] {count} ta rasm olindi.")
    return faces_data


def train_model(faces_data: list, label: int = OWNER_LABEL):
    """LBPH yuz tanish modelini o'rgatadi va saqlaydi."""
    if not faces_data:
        print("[XATO] Yuz rasmlari yo'q, o'rgatib bo'lmaydi.")
        return False

    os.makedirs(DATA_DIR, exist_ok=True)

    labels = np.array([label] * len(faces_data), dtype=np.int32)
    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=2,
        neighbors=8,
        grid_x=8,
        grid_y=8,
    )

    print(f"[O'RGATISH] Model o'rganyapti ({len(faces_data)} ta rasm)...")
    t0 = time.time()
    recognizer.train(faces_data, labels)
    elapsed = int((time.time() - t0) * 1000)
    recognizer.save(MODEL_PATH)
    print(f"[OK] Model saqlandi: {MODEL_PATH} ({elapsed}ms)")
    return True


def save_owner_info(name: str):
    """Egasi ma'lumotlarini JSON ga saqlaydi."""
    info = {
        "label": OWNER_LABEL,
        "name": name,
        "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "num_samples": NUM_SAMPLES,
        "confidence_threshold": 85,   # <85 = tanildi, >85 = noma'lum
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OWNER_PATH, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"[OK] Egasi ma'lumotlari: {OWNER_PATH}")
    print(f"     Ism: {name}")
    print(f"     Ishonch chegarasi: <{info['confidence_threshold']} = tanildi")


def verify_model(name: str):
    """O'rgatilgan modelni bir rasm bilan tekshiradi."""
    if not os.path.exists(MODEL_PATH):
        return

    cascade = _get_cascade()
    if cascade is None:
        return

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(MODEL_PATH)

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print(f"\n[TEKSHIRUV] Modelni tekshiramiz — kameraga qarang...")
    time.sleep(1)

    for _ in range(30):  # 30 ta frame ichida yuz topmoq
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=MIN_FACE_SIZE)
        for (x, y, w, h) in faces:
            face_roi = _preprocess_face(gray, x, y, w, h)
            label, confidence = recognizer.predict(face_roi)
            threshold = 85
            if confidence < threshold:
                print(f"[OK] Tanildi: {name}! (ishonch: {confidence:.1f}, chegara: <{threshold})")
            else:
                print(f"[~] Noma'lum shaxs (ishonch: {confidence:.1f}, chegara: <{threshold})")
            cap.release()
            return

    cap.release()
    print("[~] Tekshiruvda yuz topilmadi — normal ishda ishlaydi.")


def main():
    print("=" * 52)
    print("  NEUROKEY — YUZ O'RGATISH TIZIMI")
    print("  LBPH (Local Binary Pattern Histogram)")
    print("=" * 52)

    name = "Diyorbek"

    # Agar avval o'rgatilgan bo'lsa
    if os.path.exists(MODEL_PATH):
        print(f"\n[!] Oldingi model mavjud: {MODEL_PATH}")
        ans = input("  Qayta o'rgatishni xohlaysizmi? (ha/yo'q): ").strip().lower()
        if ans not in ("ha", "h", "yes", "y", "да"):
            print("[SKIP] O'rgatish o'tkazib yuborildi.")
            verify_model(name)
            return

    # Namunalar olish
    faces = capture_samples(name)
    if not faces:
        print("[XATO] Rasm olinmadi. Kamerani tekshiring.")
        return

    # Model o'rgatish
    ok = train_model(faces, label=OWNER_LABEL)
    if not ok:
        return

    # Egasi ma'lumotlarini saqlash
    save_owner_info(name)

    # Modelni tekshirish
    verify_model(name)

    print("\n" + "=" * 52)
    print("  TAYYOR! Endi NeuroKey sizni taniydi.")
    print("  ONLINE_FULL.bat ni ishga tushiring va")
    print("  'Кто я?' deb so'rang.")
    print("=" * 52)


if __name__ == "__main__":
    main()
