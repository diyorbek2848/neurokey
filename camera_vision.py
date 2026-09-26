"""
camera_vision.py — NeuroKey Ko'z: Kamera va Video

NeuroKey ning haqiqiy ko'zi — ekran emas, webcam.
100% lokal, internet kerak emas.

Imkoniyatlar:
- Webcam dan real-time frame olish
- Yuz aniqlash (OpenCV haarcascades)
- Matn o'qish (OCR)
- Harakat aniqlash
- Tasvirni tavsif qilish (lokal BLIP/CLIP yoki OCR asosida)
- Video fayldan kadr olish

Foydalanish:
  from camera_vision import get_camera_context
  ctx = get_camera_context()  → LLM uchun tavsif
"""
from __future__ import annotations
import os, time, logging, threading, base64
from typing import Optional, Tuple

log = logging.getLogger(__name__)

# ─── Opsional import ─────────────────────────────────────────────────────────

try:
    import os as _os_cv
    # Suppress noisy MSMF/DirectShow warnings from OpenCV on Windows
    _os_cv.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
    _os_cv.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    import cv2
    try:
        cv2.setLogLevel(3)  # LOG_LEVEL_ERROR only (suppress WARN)
    except AttributeError:
        pass  # older OpenCV versions don't have setLogLevel
    import numpy as np
    _CV2_OK = True
except ImportError:
    cv2 = None
    np = None
    _CV2_OK = False

try:
    from PIL import Image, ImageEnhance
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import pytesseract
    _TESSERACT_OK = True
except ImportError:
    _TESSERACT_OK = False


# ─── Haarcascade yo'llari (OpenCV bilan birga keladi) ───────────────────────

def _get_cascade_path(name: str) -> Optional[str]:
    if not _CV2_OK:
        return None
    cascade_dir = os.path.join(os.path.dirname(cv2.__file__), "data")
    path = os.path.join(cascade_dir, name)
    return path if os.path.exists(path) else None


# ─── Yuz tanish (LBPH model) ────────────────────────────────────────────────

_DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_MODEL_PATH = os.path.join(_DATA_DIR, "face_model.yml")
_OWNER_PATH = os.path.join(_DATA_DIR, "face_owner.json")

_face_recognizer = None   # LBPH recognizer (lazy loaded)
_owner_info: dict = {}    # {"name": "Diyorbek", "confidence_threshold": 85, ...}
_recognizer_lock = threading.Lock()


def _load_recognizer():
    """LBPH modelini bir marta yuklaydi."""
    global _face_recognizer, _owner_info
    if _face_recognizer is not None:
        return _face_recognizer
    if not _CV2_OK:
        return None
    if not os.path.exists(_MODEL_PATH):
        return None
    if not hasattr(cv2, "face"):
        log.debug("[KAMERA] opencv-contrib yo'q (cv2.face) — LBPH o'tkazildi, ArcFace ishlatiladi")
        return None
    try:
        with _recognizer_lock:
            if _face_recognizer is not None:
                return _face_recognizer
            rec = cv2.face.LBPHFaceRecognizer_create()
            rec.read(_MODEL_PATH)
            _face_recognizer = rec
            # Egasi ma'lumotlarini yuklash
            if os.path.exists(_OWNER_PATH):
                import json
                with open(_OWNER_PATH, encoding="utf-8") as f:
                    _owner_info = json.load(f)
            log.info("[KAMERA] Yuz tanish modeli yuklandi: %s", _MODEL_PATH)
            return rec
    except Exception as e:
        log.warning("[KAMERA] Model yuklanmadi: %s", e)
        return None


def recognize_face(gray_img, x: int, y: int, w: int, h: int) -> dict:
    """
    Yuzni taniydi.
    Returns: {
        "known": bool,        — tanilgan shaxs
        "name": str,          — ism (agar tanilsa)
        "confidence": float,  — ishonch darajasi (past = yaxshiroq)
        "label": int,
    }
    """
    rec = _load_recognizer()
    if rec is None:
        return {"known": False, "name": "noma'lum", "confidence": 999.0, "label": -1}
    try:
        face = gray_img[y:y+h, x:x+w]
        face = cv2.resize(face, (200, 200))
        face = cv2.equalizeHist(face)
        label, confidence = rec.predict(face)
        threshold = float(_owner_info.get("confidence_threshold", 85))
        known = confidence < threshold
        name = _owner_info.get("name", "egasi") if known else "noma'lum"
        return {"known": known, "name": name, "confidence": round(confidence, 1), "label": label}
    except Exception as e:
        log.debug("[KAMERA] Tanish xatosi: %s", e)
        return {"known": False, "name": "noma'lum", "confidence": 999.0, "label": -1}


def is_owner_present(frame) -> tuple:
    """
    Egasi kamerada bormi?
    Returns: (is_present: bool, name: str, confidence: float)
    """
    if not _CV2_OK or frame is None:
        return False, "", 999.0
    cascade_path = _get_cascade_path("haarcascade_frontalface_default.xml")
    if not cascade_path:
        return False, "", 999.0
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cascade_path)
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        for (x, y, w, h) in faces:
            result = recognize_face(gray, x, y, w, h)
            if result["known"]:
                return True, result["name"], result["confidence"]
        return False, "", 999.0
    except Exception:
        return False, "", 999.0


# ─── Kamera holati ───────────────────────────────────────────────────────────

_last_frame = None          # Oxirgi kadr (numpy array)
_last_capture_time = 0.0    # Oxirgi olish vaqti
_camera_lock = threading.Lock()
_bg_capture_active = False

CAPTURE_INTERVAL = 3.0      # soniyada bir kadr
CAMERA_INDEX = 0            # birinchi kamera


# ─── Asosiy funksiyalar ──────────────────────────────────────────────────────

def capture_frame(camera_index: int = CAMERA_INDEX) -> Optional[object]:
    """Kameradan bir kadr oladi."""
    if not _CV2_OK:
        log.warning("[KAMERA] OpenCV yo'q. pip install opencv-python")
        return None
    try:
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            log.warning("[KAMERA] %d raqamli kamera topilmadi", camera_index)
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        ret, frame = cap.read()
        cap.release()
        if ret:
            return frame
        return None
    except Exception as e:
        log.warning("[KAMERA] kadr olish xatosi: %s", e)
        return None


def frame_to_pil(frame) -> Optional[object]:
    """OpenCV frame → PIL Image."""
    if not _CV2_OK or not _PIL_OK or frame is None:
        return None
    try:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    except Exception:
        return None


def frame_to_base64(frame) -> Optional[str]:
    """OpenCV frame → base64 JPEG (LLM API uchun)."""
    if not _CV2_OK or frame is None:
        return None
    try:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buf.tobytes()).decode("utf-8")
    except Exception:
        return None


def describe_with_gpt_vision(frame=None, question: str = "", lang: str = "ru") -> str:
    """
    Kadr yoki face_arc oxirgi kadrini GPT-4o vision bilan tahlil qiladi.
    frame=None → face_arc.get_last_frame() ishlatiladi (kamera konflikti yo'q).
    Qaytaradi: tavsif matni (str).
    """
    # Kadrni olish
    if frame is None:
        try:
            from face_arc import get_last_frame as _glf, get_last_frame_age as _glfa
            age = _glfa()
            if age > 10.0:
                return "Kamera: so'nggi kadr 10+ soniya oldin (kamera ishlamayapti?)" if lang != "ru" else "Камера: последний кадр устарел (10+ сек). Камера работает?"
            frame = _glf()
        except Exception as e:
            return f"Kamera frame olishda xato: {e}"

    if frame is None:
        return "Kadr mavjud emas." if lang != "ru" else "Кадр недоступен."

    b64 = frame_to_base64(frame)
    if not b64:
        return "Kadrni base64 ga o'tkazib bo'lmadi."

    # Savol tuzish
    if lang == "ru":
        sys_prompt = (
            "Ты — NeuroKey, ИИ-ассистент с реальным зрением через веб-камеру. "
            "Опиши что видишь на изображении подробно и живо. "
            "Если показывают предмет — назови что это, цвет, форму. "
            "Если показывают текст — прочитай его. "
            "Если человек — опиши эмоцию, позу. Отвечай 2-4 предложениями."
        )
        user_q = question if question else "Что ты видишь на камере? Опиши подробно."
    else:
        sys_prompt = (
            "You are NeuroKey, an AI assistant with real webcam vision. "
            "Describe what you see in the image in detail. "
            "If shown an object — name it, color, shape. "
            "If text — read it. If a person — describe emotion, pose. "
            "Reply in 2-4 sentences."
        )
        user_q = question if question else "What do you see on camera? Describe in detail."

    # GPT-4o vision API (Groq/OpenAI placeholder kalitda ishlamaydi)
    try:
        import openai as _oai, os as _os
        _key = _os.environ.get("OPENAI_API_KEY", "")
        _base = (_os.environ.get("OPENAI_BASE_URL", "") or "").strip()
        if not _key or "groq.com" in _base or _key.startswith("gsk_"):
            return describe_frame(frame)
        client = _oai.OpenAI(api_key=_key, base_url=_base if _base else None)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": [
                    {"type": "text",       "text": user_q},
                    {"type": "image_url",  "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
                ]},
            ],
            max_tokens=300,
            temperature=0.5,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning("[VISION] GPT-4o xato: %s", e)
        # Fallback: oddiy tavsif
        return describe_frame(frame)


def capture_and_describe_vision(question: str = "", lang: str = "ru") -> str:
    """
    face_arc oxirgi kadrini olib GPT-4o vision bilan tahlil qiladi.
    main.py dan chaqirish uchun qulay wrapper.
    """
    return describe_with_gpt_vision(frame=None, question=question, lang=lang)


# ─── Tahlil funksiyalari ─────────────────────────────────────────────────────

def detect_faces(frame) -> list:
    """
    Yuzlarni aniqlaydi va taniydi.
    Returns: [{"x":int, "y":int, "w":int, "h":int,
               "known":bool, "name":str, "confidence":float}, ...]
    """
    if not _CV2_OK or frame is None:
        return []
    cascade_path = _get_cascade_path("haarcascade_frontalface_default.xml")
    if not cascade_path:
        return []
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cascade_path)
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) == 0:
            return []
        result = []
        for (x, y, w, h) in faces:
            entry = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
            rec_result = recognize_face(gray, x, y, w, h)
            entry.update(rec_result)
            result.append(entry)
        return result
    except Exception as e:
        log.debug("[KAMERA] yuz aniqlash xatosi: %s", e)
        return []


def detect_motion(frame1, frame2, threshold: int = 25) -> float:
    """
    Ikkita kadr orasida harakat darajasini hisoblaydi.
    Returns: 0.0 (harakat yo'q) → 1.0 (katta harakat)
    """
    if not _CV2_OK or frame1 is None or frame2 is None:
        return 0.0
    try:
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray1, gray2)
        _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
        motion_ratio = np.sum(thresh > 0) / thresh.size
        return float(motion_ratio)
    except Exception:
        return 0.0


def extract_text_from_frame(frame) -> str:
    """Kadrdan matn o'qiydi (OCR)."""
    if not _CV2_OK or not _TESSERACT_OK or frame is None:
        return ""
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Kontrastni oshirish
        gray = cv2.equalizeHist(gray)
        text = pytesseract.image_to_string(gray, lang="rus+eng", timeout=5)
        return text.strip()[:500]
    except Exception as e:
        log.debug("[KAMERA] OCR xatosi: %s", e)
        return ""


def analyze_brightness(frame) -> str:
    """Yorug'lik darajasini aniqlaydi."""
    if not _CV2_OK or frame is None:
        return "noma'lum"
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        if brightness < 50:   return "juda qorong'i"
        if brightness < 100:  return "qorong'i"
        if brightness < 180:  return "normal"
        if brightness < 230:  return "yorug'"
        return "juda yorug'"
    except Exception:
        return "noma'lum"


def get_dominant_colors(frame, n: int = 3) -> list[str]:
    """Kadrdagi asosiy ranglarni aniqlaydi."""
    if not _CV2_OK or frame is None:
        return []
    try:
        small = cv2.resize(frame, (50, 50))
        pixels = small.reshape(-1, 3).astype(float)
        # K-means o'rniga oddiy usul — eng ko'p uchraydigan ranglar
        # BGR → RGB
        pixels_rgb = pixels[:, ::-1]
        avg = pixels_rgb.mean(axis=0)
        r, g, b = int(avg[0]), int(avg[1]), int(avg[2])
        color_name = _rgb_to_name(r, g, b)
        return [color_name]
    except Exception:
        return []


def _rgb_to_name(r: int, g: int, b: int) -> str:
    """RGB dan rang nomi."""
    if r > 200 and g < 100 and b < 100: return "qizil"
    if r < 100 and g > 200 and b < 100: return "yashil"
    if r < 100 and g < 100 and b > 200: return "ko'k"
    if r > 200 and g > 200 and b < 100: return "sariq"
    if r > 200 and g > 200 and b > 200: return "oq"
    if r < 60  and g < 60  and b < 60:  return "qora"
    if r > 150 and g > 150 and b > 150: return "kulrang"
    return f"aralash (r={r},g={g},b={b})"


# ─── To'liq tavsif ───────────────────────────────────────────────────────────

def describe_frame(frame) -> str:
    """
    Kadrni tahlil qilib tavsif beradi.
    LLM uchun kontekst sifatida ishlatiladi.
    """
    if frame is None:
        return "Kamera: kadr olinmadi"

    parts = []

    # Yuzlar + tanish
    faces = detect_faces(frame)
    if faces:
        known = [f for f in faces if f.get("known")]
        unknown = [f for f in faces if not f.get("known")]
        desc_parts = []
        if known:
            names = ", ".join(f["name"] for f in known)
            desc_parts.append(f"{names} ko'rinadi (tanildi)")
        if unknown:
            desc_parts.append(f"{len(unknown)} ta noma'lum shaxs")
        parts.append("; ".join(desc_parts) if desc_parts else f"{len(faces)} ta odam ko'rinadi")
    else:
        if os.path.exists(_MODEL_PATH):
            parts.append("egasi kamerada ko'rinmaydi")
        else:
            parts.append("kamerada odam ko'rinmaydi")

    # Yorug'lik
    brightness = analyze_brightness(frame)
    parts.append(f"yorug'lik: {brightness}")

    # Rang
    colors = get_dominant_colors(frame)
    if colors:
        parts.append(f"asosiy rang: {colors[0]}")

    # Matn (agar bor bo'lsa)
    text = extract_text_from_frame(frame)
    if text and len(text) > 10:
        parts.append(f"ko'rinadigan matn: '{text[:100]}'")

    h, w = frame.shape[:2] if hasattr(frame, 'shape') else (0, 0)
    if w and h:
        parts.append(f"o'lchov: {w}x{h}")

    return "Kamera: " + " | ".join(parts)


# ─── Video fayl ──────────────────────────────────────────────────────────────

def extract_frames_from_video(video_path: str, num_frames: int = 5) -> list:
    """Video fayldan N ta kadr oladi."""
    if not _CV2_OK:
        return []
    if not os.path.exists(video_path):
        log.warning("[VIDEO] Fayl topilmadi: %s", video_path)
        return []
    try:
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        duration = total / fps

        frames = []
        step = max(1, total // num_frames)
        for i in range(num_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(i * step, total - 1))
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        cap.release()
        log.info("[VIDEO] %s: %d kadr olindi (%.1fs)", video_path, len(frames), duration)
        return frames
    except Exception as e:
        log.warning("[VIDEO] xato: %s", e)
        return []


def describe_video(video_path: str) -> str:
    """Video faylni tavsif qiladi."""
    frames = extract_frames_from_video(video_path, num_frames=5)
    if not frames:
        return f"Video: '{video_path}' o'qib bo'lmadi"

    descriptions = []
    face_counts = []
    texts = []

    for frame in frames:
        faces = detect_faces(frame)
        face_counts.append(len(faces))
        text = extract_text_from_frame(frame)
        if text and len(text) > 5:
            texts.append(text[:80])

    avg_faces = sum(face_counts) / len(face_counts) if face_counts else 0
    if avg_faces > 0.5:
        descriptions.append(f"o'rtacha {avg_faces:.0f} odam ko'rinadi")
    unique_texts = list(set(texts))[:3]
    if unique_texts:
        descriptions.append(f"matn: {' | '.join(unique_texts)}")

    result = f"Video '{os.path.basename(video_path)}': {len(frames)} kadr tahlil qilindi"
    if descriptions:
        result += " — " + ", ".join(descriptions)
    return result


# ─── Fon ushlab turish ───────────────────────────────────────────────────────

def start_background_capture(interval: float = CAPTURE_INTERVAL) -> None:
    """Fon threadida kameradan doimiy kadr oladi."""
    global _bg_capture_active
    if _bg_capture_active:
        return
    _bg_capture_active = True

    def _loop():
        global _last_frame, _last_capture_time
        while _bg_capture_active:
            frame = capture_frame()
            if frame is not None:
                with _camera_lock:
                    _last_frame = frame
                    _last_capture_time = time.monotonic()
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    log.info("[KAMERA] Fon ushlab turish boshlandi (%ds)", int(interval))


def stop_background_capture() -> None:
    global _bg_capture_active
    _bg_capture_active = False


def get_last_frame():
    """Oxirgi olingan kadrni qaytaradi."""
    with _camera_lock:
        return _last_frame


# ─── LLM kontekst ────────────────────────────────────────────────────────────

def get_camera_context(use_background: bool = True) -> str:
    """LLM uchun kamera konteksti."""
    if not _CV2_OK:
        return ""

    frame = None
    if use_background:
        frame = get_last_frame()
        # Agar fon kadr juda eski bo'lsa — yangi ol
        if frame is None or (time.monotonic() - _last_capture_time) > 30:
            frame = capture_frame()
    else:
        frame = capture_frame()

    if frame is None:
        return ""

    description = describe_frame(frame)
    return description


def get_context_for_llm() -> str:
    """Modul konteksti — llm_router uchun. Egasini tanisa — ismini qaytaradi."""
    if os.getenv("NEUROKEY_CAMERA_ENABLED", "1").strip() in ("0", "false", "no"):
        return ""
    try:
        from owner_trust import always_trust_owner, owner_nick, any_biometric_profile
        if always_trust_owner() and any_biometric_profile():
            nick = owner_nick()
            try:
                from face_arc import get_last_face_result, profile_exists as _fpex
                if _fpex():
                    fr = get_last_face_result()
                    sim = float(fr.get("similarity") or 0.5)
                    if fr.get("known") or sim > 0.01:
                        return f"Kamera: {nick} ko'rinadi (egasi, ishonch {sim:.0%})"
            except Exception:
                pass
            return f"Kamera: {nick} — egasi (doimiy tanish rejimi)"
    except Exception:
        pass
    frame = get_last_frame()
    if frame is None:
        return ""
    # Egasi mavjudmi — tez tekshirish
    present, name, conf = is_owner_present(frame)
    if present:
        return f"Kamera: {name} ko'rinadi (yuz tanildi, ishonch: {conf:.0f})"
    # Oddiy tavsif
    ctx = get_camera_context()
    return ctx if ctx else ""


# ─── CLI test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    if not _CV2_OK:
        print("[XATO] OpenCV o'rnatilmagan!")
        print("       pip install opencv-python")
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "photo"

    if cmd == "photo":
        print("Kameradan kadr olinmoqda...")
        frame = capture_frame()
        if frame is None:
            print("[XATO] Kamera topilmadi yoki ishlamayapti.")
            sys.exit(1)
        print(describe_frame(frame))

        # Rasmni saqlash
        out = os.path.join(os.path.dirname(__file__), "data", "test_frame.jpg")
        cv2.imwrite(out, frame)
        print(f"Rasm saqlandi: {out}")

    elif cmd == "video" and len(sys.argv) > 2:
        print(describe_video(sys.argv[2]))

    elif cmd == "live":
        print("Live kamera tahlili (Ctrl+C → to'xtatish)")
        start_background_capture(interval=2.0)
        try:
            while True:
                ctx = get_camera_context()
                if ctx:
                    print(f"\r{ctx}", end="", flush=True)
                time.sleep(2)
        except KeyboardInterrupt:
            stop_background_capture()
            print("\nTo'xtatildi.")
    else:
        print("Foydalanish: python camera_vision.py [photo|live|video PATH]")
