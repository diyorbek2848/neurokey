# -*- coding: utf-8 -*-
"""
vision_core.py — Real-time screen understanding for Juma
- Multiple OCR backends: Tesseract -> EasyOCR -> MSER region crops (OpenCV) -> fallback
- CV hints: play/progress/face/big-image + text density
- Clean text, detect language, classify screen type, extract entities, suggestions
- Background watcher + one-shot OCR
API:
    start(screen=True, every_ms=500, on_insight=None, tts_is_playing=None)
    stop()
    ensure_snapshot(timeout_s=1.2) -> bool
    ocr_once() -> bool
    get_snapshot() -> dict
"""

from __future__ import annotations
import os, time, re, hashlib, threading
from dataclasses import dataclass, asdict
from typing import Optional, Callable, Dict, Any, Tuple, List

# Soft deps
try:
    import mss
    from PIL import Image, ImageOps, ImageFilter
except Exception:
    mss = None
    Image = None
    ImageOps = None
    ImageFilter = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import easyocr
except Exception:
    easyocr = None

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

try:
    from langdetect import detect as _langdetect
except Exception:
    _langdetect = None

# Optional: active window title (Windows only)
try:
    import win32gui
    def _active_window_title() -> str:
        try:
            return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or ""
        except Exception:
            return ""
except Exception:
    def _active_window_title() -> str:
        return ""

import config as C


# ============ State ============
@dataclass
class ScreenState:
    text: str = ""
    lang: str = "ru"
    updated_ts: float = 0.0
    hash: str = ""
    analysis: Dict[str, Any] | None = None

_state = ScreenState()
_thr: Optional[threading.Thread] = None
_stop = threading.Event()

_backend = {
    "tess": False,
    "easy": False,
    "easy_reader": None,
    "ready": False,
    "warned": False
}


# ============ Utils ============
_RE_URL   = re.compile(r"https?://[^\s]+", re.I)
_RE_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_RE_PHONE = re.compile(r"(?:\+\d{1,3}\s?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3}[\s-]?\d{2}[\s-]?\d{2}")

def _normalize_text(txt: str) -> str:
    if not txt:
        return ""
    txt = txt.replace("\u2014", "-").replace("\u2013", "-").replace("\u2212", "-")
    txt = txt.replace("\u00ab", '"').replace("\u00bb", '"').replace("’", "'").replace("“", '"').replace("”", '"')
    txt = re.sub(r"-\s*\n\s*", "", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()

def _detect_lang(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "ru"
    if _langdetect:
        try:
            code = _langdetect(t)
            return "ru" if code.startswith("ru") else code[:2]
        except Exception:
            pass
    cyr = sum("а" <= ch <= "я" or "А" <= ch <= "Я" or ch in "ёЁ" for ch in t)
    lat = sum("a" <= ch <= "z" or "A" <= ch <= "Z" for ch in t)
    return "ru" if cyr >= lat else "en"


# ============ CV hints ============
def _cv_hints_from_rgb(img_rgb) -> Dict[str, Any]:
    hints = {"has_play": False, "has_progress": False, "has_big_image": False, "faces": 0, "text_density": 0.0}
    if cv2 is None or np is None or Image is None:
        return hints
    try:
        bgr = cv2.cvtColor(np.array(img_rgb), cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        # text density
        th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 41, 9)
        cnts,_ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        text_area = sum(cv2.contourArea(c) for c in cnts if cv2.contourArea(c) > 100)
        hints["text_density"] = float(min(1.0, text_area / max(1.0, w * h)))

        # progress bar: long line near bottom
        edges = cv2.Canny(gray, 80, 160)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=int(w*0.3), maxLineGap=10)
        if lines is not None:
            for x1, y1, x2, y2 in lines[:, 0]:
                if abs(y1 - y2) < 6 and y1 > int(h * 0.7):
                    hints["has_progress"] = True
                    break

        # play icon (triangle)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thbin = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cnts,_ = cv2.findContours(thbin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.04 * peri, True)
            if len(approx) == 3 and cv2.contourArea(c) > (w * h) * 0.0008:
                hints["has_play"] = True
                break

        # faces
        try:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            faces = face_cascade.detectMultiScale(gray, 1.2, 3, minSize=(40, 40))
            hints["faces"] = int(len(faces))
        except Exception:
            hints["faces"] = 0

        # big image (rough)
        if np.var(gray) < 400 and (w * h) > 300000:
            hints["has_big_image"] = True

    except Exception:
        pass
    return hints


# ============ Backends init ============
def _init_backends() -> None:
    if _backend["ready"]:
        return

    # Tesseract
    if pytesseract is not None:
        try:
            tess_exe = getattr(C, "TESSERACT_EXE", None)
            if tess_exe and os.path.isfile(tess_exe):
                pytesseract.pytesseract.tesseract_cmd = tess_exe
            _ = pytesseract.get_tesseract_version()
            _backend["tess"] = True
        except Exception:
            _backend["tess"] = False

    # EasyOCR — GPU kerak emas
    if easyocr is not None:
        try:
            lang_cfg = getattr(C, "OCR_LANGS", "rus+eng")
            langs = []
            if "ru" in lang_cfg or "rus" in lang_cfg: langs.append("ru")
            if "en" in lang_cfg or "eng" in lang_cfg: langs.append("en")
            if not langs: langs = ["ru", "en"]
            _backend["easy_reader"] = easyocr.Reader(langs, gpu=False, verbose=False)
            _backend["easy"] = True
        except Exception:
            _backend["easy"] = False

    _backend["ready"] = bool(_backend.get("tess") or _backend.get("easy"))
    if not _backend["ready"] and not _backend["warned"]:
        print("[VISION] OCR backends not available (Tesseract/EasyOCR). Vision limited.")
        _backend["warned"] = True


# ============ OCR helpers ============
def _ocr_tesseract(pil_gray: "Image.Image") -> Tuple[str, float]:
    if not _backend.get("tess") or pytesseract is None:
        return "", 0.0
    try:
        out = pytesseract.image_to_string(
            pil_gray,
            lang=getattr(C, "OCR_LANGS", "rus+eng"),
            config="--oem 1 --psm 6",
        ) or ""
        t = _normalize_text(out)
        return t, float(len(t))
    except Exception:
        return "", 0.0

def _ocr_easy(pil_rgb: "Image.Image") -> Tuple[str, float]:
    if not _backend.get("easy") or easyocr is None:
        return "", 0.0
    try:
        reader = _backend.get("easy_reader")
        res = reader.readtext(np.array(pil_rgb), detail=0, paragraph=True)
        out = "\n".join([r.strip() for r in res if r and r.strip()])
        t = _normalize_text(out)
        return t, float(len(t))
    except Exception:
        return "", 0.0

def _merge_boxes(boxes: List[Tuple[int,int,int,int]], iou_thresh: float = 0.15) -> List[Tuple[int,int,int,int]]:
    if not boxes:
        return []
    b = [list(x) for x in boxes]
    out = []
    while b:
        ax0, ay0, ax1, ay1 = b.pop(0)
        changed = True
        while changed:
            changed = False
            i = 0
            while i < len(b):
                bx0, by0, bx1, by1 = b[i]
                ix0, iy0 = max(ax0, bx0), max(ay0, by0)
                ix1, iy1 = min(ax1, bx1), min(ay1, by1)
                if ix1 > ix0 and iy1 > iy0:
                    inter = (ix1 - ix0) * (iy1 - iy0)
                    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
                    if union > 0 and (inter / union) > iou_thresh:
                        ax0, ay0, ax1, ay1 = min(ax0, bx0), min(ay0, by0), max(ax1, bx1), max(ay1, by1)
                        b.pop(i)
                        changed = True
                        continue
                i += 1
        out.append((ax0, ay0, ax1, ay1))
    out.sort(key=lambda r: (r[2]-r[0])*(r[3]-r[1]), reverse=True)
    return out

def _ocr_regions_with_mser(pil_rgb: "Image.Image") -> Tuple[str, float]:
    if cv2 is None or np is None or Image is None:
        return "", 0.0
    try:
        img = np.array(pil_rgb)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        # MSER
        mser = cv2.MSER_create(_delta=5)
        regions, _ = mser.detectRegions(gray)
        h, w = gray.shape[:2]
        boxes = []
        for r in regions:
            x, y, wr, hr = cv2.boundingRect(r.reshape(-1, 1, 2))
            if wr < 20 or hr < 10:
                continue
            pad = 4
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(w, x + wr + pad), min(h, y + hr + pad)
            if (x1 - x0) * (y1 - y0) > 0.001 * w * h and (y1 - y0) < 0.9 * h:
                boxes.append((x0, y0, x1, y1))
        boxes = _merge_boxes(boxes)
        parts = []
        total = 0
        for (x0, y0, x1, y1) in boxes[:15]:
            crop = Image.fromarray(img[y0:y1, x0:x1])
            t1, _ = _ocr_easy(crop)
            if len(t1) > 6:
                parts.append(t1); total += len(t1); continue
            t2, _ = _ocr_tesseract(ImageOps.grayscale(crop))
            if len(t2) > 6:
                parts.append(t2); total += len(t2)
        return ("\n".join(parts)).strip(), float(total)
    except Exception:
        return "", 0.0


# ============ High-level pipeline ============
def _classify_text_and_hints(text: str, hints: Dict[str, Any]) -> str:
    low = (text or "").lower()
    if re.search(r"(логин|парол|войти|sign in|username|password|otp|код подтверждения)", low):
        return "login_form"
    if re.search(r"(форма|анкета|заполните|required|введите|enter your|телефон|email|адрес|date of birth|first name|last name)", low) and ":" in low:
        return "form"
    if hints.get("has_play") or hints.get("has_progress"):
        return "video"
    if re.search(r"(class |def |import |public |private |function |var |;|#include|using namespace)", text):
        return "code"
    if re.search(r"(page \d+ of \d+|adobe acrobat|pdf)", low):
        return "pdf"
    if hints.get("has_big_image") or hints.get("faces", 0) >= 1:
        return "image"
    if len(text) > 600:
        return "article"
    if re.search(r"\b\d{1,2}:\d{2}\b", low) and len(low.splitlines()) > 6:
        return "chat"
    return "unknown"

def _derive_suggestions(kind: str, txt: str, lang: str, hints: Dict[str,Any]) -> List[str]:
    s = []
    if kind in ("login_form", "form"):
        s += ["Проверить поля формы", "Предложить примеры ответов", "Перевести подсказки"]
    if kind == "article":
        s += ["Кратко пересказать основное", "Выделить даты/имена/цифры"]
    if kind == "video":
        s += ["Описать тему ролика", "Найти кнопки управления (play/pause)"]
    if kind == "code":
        s += ["Объяснить, что делает код", "Предложить исправления"]
    if lang != "ru":
        s = ["Перевести на русский и зачитать"] + s
    if not s:
        s = ["Кратко рассказать, что на экране", "Ответить на вопрос по тексту"]
    return s

def _analyze_text_and_entities(text: str, hints: Dict[str, Any]) -> Dict[str, Any]:
    lang = _detect_lang(text)
    kind = _classify_text_and_hints(text, hints)
    urls = _RE_URL.findall(text)
    emails = _RE_EMAIL.findall(text)
    phones = _RE_PHONE.findall(text)
    return {
        "lang": lang,
        "type": kind,
        "title": _active_window_title(),
        "entities": {"urls": urls[:8], "emails": emails[:8], "phones": phones[:8]},
        "hints": hints,
        "suggestions": _derive_suggestions(kind, text, lang, hints)
    }

def _process_frame(pil_rgb: "Image.Image") -> Tuple[str, float, Dict[str, Any]]:
    _init_backends()
    try:
        pil_gray = ImageOps.grayscale(pil_rgb)
    except Exception:
        pil_gray = None

    # sinovchilar: easy -> tess -> mser
    candidates: List[Tuple[str, str, float]] = []

    if _backend.get("easy"):
        t, s = _ocr_easy(pil_rgb)
        candidates.append(("easy_full", t, s))

    if _backend.get("tess") and pil_gray is not None:
        t, s = _ocr_tesseract(pil_gray)
        candidates.append(("tess_full", t, s))

    t, s = _ocr_regions_with_mser(pil_rgb)
    candidates.append(("mser", t, s))

    best_tag, best_text, best_score = max(candidates, key=lambda it: it[2] if it else 0.0)

    # qo'shimcha fallback: psm=3
    if (not best_text or best_score < 6) and _backend.get("tess") and pil_gray is not None:
        try:
            out = pytesseract.image_to_string(
                pil_gray,
                lang=getattr(C, "OCR_LANGS", "rus+eng"),
                config="--oem 1 --psm 3"
            ) or ""
            out = _normalize_text(out)
            if len(out) > len(best_text):
                best_text, best_score, best_tag = out, float(len(out)), "tess_psm3"
        except Exception:
            pass

    hints = _cv_hints_from_rgb(pil_rgb)
    analysis = _analyze_text_and_entities(best_text, hints)
    return best_text, best_score, analysis


# ============ Public API ============
def get_snapshot() -> Dict[str, Any]:
    return asdict(_state)

def get_last_text() -> str:
    return _state.text

def get_last_lang() -> str:
    return _state.lang

def get_last_ts() -> float:
    return _state.updated_ts


# --------- MONITOR TANLASH: avtomatik yoki config bilan ---------
def _grab_screen_pil() -> Tuple[Optional["Image.Image"], int, int]:
    """
    Monitor tanlash:
      - config.MONITOR_INDEX == 0 -> avtomatik: eng “jonli” (dispersioni katta) monitor
      - >0 -> o‘sha indeksdagi monitor (mss.monitors bo‘yicha)
    """
    if mss is None or Image is None:
        return None, 0, 0
    try:
        sct = mss.mss()
        mons = sct.monitors
        if not mons or len(mons) == 0:
            return None, 0, 0

        idx_cfg = int(getattr(C, "MONITOR_INDEX", 0))

        def _grab(idx):
            raw = sct.grab(mons[idx])
            img = Image.frombytes("RGB", raw.size, raw.rgb)
            return img, raw.size[0], raw.size[1]

        if idx_cfg > 0 and idx_cfg < len(mons):
            return _grab(idx_cfg)

        # Avtomatik: barcha monitorlardan eng “jonli”sini tanlash
        best = None
        best_score = -1.0
        for i in range(1, len(mons)):  # 1..N (0 — virtual)
            try:
                img, w, h = _grab(i)
                if cv2 is not None and np is not None:
                    g = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
                    score = float(np.var(g))
                else:
                    score = float(w * h)
                if score > best_score:
                    best, best_score = (img, w, h), score
            except Exception:
                continue
        if best:
            return best
        # zaxira: primary
        return _grab(1)
    except Exception:
        return None, 0, 0


def ocr_once() -> bool:
    """Single capture → OCR → cache update. Returns True if text found."""
    if mss is None or Image is None:
        if not _backend["warned"]:
            print("[VISION] mss/Pillow not available; install requirements.")
            _backend["warned"] = True
        return False

    _init_backends()
    if not _backend["ready"]:
        if not _backend["warned"]:
            print("[VISION] OCR backends not ready (Tesseract/EasyOCR).")
            _backend["warned"] = True
        return False

    try:
        pil, w, h = _grab_screen_pil()
        if pil is None:
            return False
        # downscale = 1.0, shunchaki kontrast
        pil_proc = ImageOps.autocontrast(pil)
        text, score, analysis = _process_frame(pil_proc)
        if not text or score < int(getattr(C, "VISION_MIN_TEXT_LEN", 4)):
            return False

        hsh = hashlib.sha1(text.encode("utf-8")).hexdigest()
        _state.text = text
        _state.lang = analysis.get("lang", "ru")
        _state.analysis = analysis
        _state.updated_ts = time.time()
        _state.hash = hsh
        return True
    except Exception:
        return False

def ensure_snapshot(timeout_s: float = 1.2) -> bool:
    """If cache is empty → try ocr_once()."""
    if (get_last_text() or "").strip():
        return True
    return ocr_once()

def start(
    screen: bool = True,
    every_ms: int = 500,
    on_insight: Optional[Callable[[dict], None]] = None,
    tts_is_playing: Optional[Callable[[], bool]] = None,
):
    """Start background watcher. If OCR backends missing → stays silent."""
    global _thr
    if not screen:
        return
    if _thr and _thr.is_alive():
        return

    if mss is None or Image is None:
        if not _backend["warned"]:
            print("[VISION] mss/Pillow missing; can't start vision.")
            _backend["warned"] = True
        return

    _init_backends()
    if not _backend["ready"]:
        if not _backend["warned"]:
            print("[VISION] OCR backends not ready; background vision disabled.")
            _backend["warned"] = True
        return

    _stop.clear()

    def _loop():
        last_hash = _state.hash
        period = max(100, int(every_ms))
        while not _stop.is_set():
            try:
                if tts_is_playing and tts_is_playing():
                    time.sleep(period / 1000.0)
                    continue

                pil, w, h = _grab_screen_pil()
                if pil is None:
                    time.sleep(period / 1000.0)
                    continue

                pil_proc = ImageOps.autocontrast(pil)
                text, score, analysis = _process_frame(pil_proc)
                if not text or score < int(getattr(C, "VISION_MIN_TEXT_LEN", 4)):
                    time.sleep(period / 1000.0)
                    continue

                hsh = hashlib.sha1(text.encode("utf-8")).hexdigest()
                if hsh == last_hash:
                    time.sleep(period / 1000.0)
                    continue
                last_hash = hsh

                _state.text = text
                _state.lang = analysis.get("lang", "ru")
                _state.analysis = analysis
                _state.updated_ts = time.time()
                _state.hash = hsh

                if on_insight:
                    try:
                        on_insight({
                            "type": "screen_text",
                            "text": text,
                            "analysis": analysis,
                            "updated_ts": _state.updated_ts
                        })
                    except Exception:
                        pass

                time.sleep(period / 1000.0)

            except Exception:
                time.sleep(0.5)

    _thr = threading.Thread(target=_loop, daemon=True)
    _thr.start()

def stop():
    _stop.set()
    global _thr
    if _thr and _thr.is_alive():
        _thr.join(timeout=0.7)
    _thr = None