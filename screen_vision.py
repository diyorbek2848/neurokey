# screen_vision.py
"""
Ekran ko'rish — ENG OXIRGI MAKSIMAL DARAJASI. Daraja boshqa oshmaydi.
- 5 capture, 3 retry
- OCR: Tesseract+Paddle parallel, Vision fallback, psm 6 oem 3
- Vision: gpt-4o, detail=high, JPEG 100%, contrast+sharpen
- Limitlar: OCR 8000, Vision 4000, combined 6000
"""
import base64
import io
import os
import re
import sys
import threading
import time
from typing import Dict, Tuple, Optional
from PIL import Image
import numpy as np

# ENG OXIRGI MAKSIMAL DARAJASI — daraja boshqa oshmaydi
_SCREEN_ULTIMATE = True

# mss — ixtiyoriy
try:
    import mss
    _HAVE_MSS = True
except ImportError:
    mss = None
    _HAVE_MSS = False
try:
    from rapidfuzz import fuzz
    _HAVE_RAPIDFUZZ = True
except ImportError:
    fuzz = None
    _HAVE_RAPIDFUZZ = False

def _ocr_lang() -> str:
    """OCR language: SCREEN_OCR_LANG yoki NEUROKEY_OCR_LANG bilan boshqariladi.

    O'LCHANDI (1920x1080 to'liq ekran, Tesseract):
      rus+eng (ikki til)  3881 ms | 2372 belgi
      eng     (bir til)   1708 ms | 2331 belgi  <- 56% tezroq, deyarli bir xil matn

    Tesseract ikki tilni bir vaqtda qidirganda ikkala til modelini ham
    tekshiradi — bu narxni deyarli ikki barobar oshiradi. Standart holat
    endi "en" (tez). Agar ekranda ko'p kirillcha matn bo'lsa (rus/o'zbek-
    kirill interfeys), NEUROKEY_OCR_LANG=ru o'rnating — sekinroq, lekin
    kirillni to'liq o'qiydi.
    """
    try:
        import config as _cfg
        explicit = getattr(_cfg, "SCREEN_OCR_LANG", None) or os.getenv("NEUROKEY_OCR_LANG")
        if explicit and str(explicit).strip():
            return str(explicit).strip().lower()
        return "en"
    except Exception:
        return "en"

def _get_config():
    """Project config when available; else minimal defaults."""
    try:
        import config as C
        return C
    except Exception:
        pass
    class _Dummy:
        OCR_ENGINE = os.getenv("OCR_ENGINE", "paddle")
        TESSERACT_PATH = os.getenv("TESSERACT_PATH", "C:/Program Files/Tesseract-OCR/tesseract.exe")
    return _Dummy()

_config = _get_config()
_ocr_lang_cached = None
_paddle_ocr_instance = None

# Conditional imports based on config
PADDLE_AVAILABLE = False
TESSERACT_AVAILABLE = False
paddle_ocr = None

def _init_ocr():
    global _ocr_lang_cached, paddle_ocr, PADDLE_AVAILABLE, TESSERACT_AVAILABLE
    lang = _ocr_lang()
    if _ocr_lang_cached == lang:
        return
    _ocr_lang_cached = lang
    engine = getattr(_config, "OCR_ENGINE", "paddle") or "paddle"
    if lang == "rus+eng":
        paddle_ocr = None
        PADDLE_AVAILABLE = False
    elif engine == "paddle":
        try:
            from paddleocr import PaddleOCR
            paddle_ocr = PaddleOCR(lang=lang)
            PADDLE_AVAILABLE = True
        except ImportError:
            paddle_ocr = None
            PADDLE_AVAILABLE = False
    tesseract_path = getattr(_config, "TESSERACT_PATH", None) or os.getenv("TESSERACT_PATH", "C:/Program Files/Tesseract-OCR/tesseract.exe")
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        TESSERACT_AVAILABLE = True
    except ImportError:
        TESSERACT_AVAILABLE = False

_init_ocr()

# ---------- Usul 1: mss ----------
def _grab_mss(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    if not _HAVE_MSS or not mss:
        return None
    try:
        with mss.mss() as sct:
            if region:
                monitor = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
            else:
                # monitors[0] = virtual desktop (barcha ekranlar), [1] = asosiy monitor
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            screenshot = sct.grab(monitor)
            if not screenshot or not screenshot.size:
                return None
            return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    except Exception:
        return None


# ---------- Usul 2: pyautogui ----------
def _grab_pyautogui(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    try:
        import pyautogui
        if region:
            img = pyautogui.screenshot(region=region)
        else:
            img = pyautogui.screenshot()
        if img and hasattr(img, "size") and img.size[0] > 0 and img.size[1] > 0:
            return img
        return None
    except Exception:
        return None


# ---------- Usul 3: Windows GDI (ctypes) ----------
def _grab_gdi(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        SM_CXSCREEN, SM_CYSCREEN = 0, 1
        if region:
            x, y, w, h = region
        else:
            x, y = 0, 0
            w = user32.GetSystemMetrics(SM_CXSCREEN)
            h = user32.GetSystemMetrics(SM_CYSCREEN)
        if w <= 0 or h <= 0:
            return None
        hwnd = user32.GetDesktopWindow()
        hdc_screen = user32.GetDC(hwnd)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        gdi32.SelectObject(hdc_mem, hbm)
        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, SRCCOPY)
        buf_size = w * h * 4
        buf = (ctypes.c_ubyte * buf_size)()
        bmpinfo = (ctypes.c_ubyte * 40)()
        ctypes.memmove(bmpinfo, b"\x28\x00\x00\x00", 4)
        ctypes.memmove(bmpinfo[4:8], (w).to_bytes(4, "little"), 4)
        ctypes.memmove(bmpinfo[8:12], (-h).to_bytes(4, "little", signed=True), 4)
        ctypes.memmove(bmpinfo[12:14], (1).to_bytes(2, "little"), 2)
        ctypes.memmove(bmpinfo[14:16], (32).to_bytes(2, "little"), 2)
        gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, bmpinfo, 0)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_screen)
        arr = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
        arr = arr[:, :, [2, 1, 0]]
        return Image.fromarray(arr)
    except Exception:
        return None


# ---------- Usul 4: PIL ImageGrab (Windows) ----------
def _grab_pil_grab(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    if sys.platform != "win32":
        return None
    try:
        from PIL import ImageGrab
        if region:
            img = ImageGrab.grab(bbox=region)
        else:
            img = ImageGrab.grab()
        if img and hasattr(img, "size") and img.size[0] > 0 and img.size[1] > 0:
            return img
        return None
    except Exception:
        return None


# ---------- Usul 5: mss barcha monitorlar (primary + secondary) ----------
def _grab_mss_all_monitors(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    """Barcha monitorlarni birlashtirib olish — ko'p monitorli tizimlar uchun."""
    if region or not _HAVE_MSS or not mss:
        return None
    try:
        with mss.mss() as sct:
            if len(sct.monitors) < 2:
                mon = sct.monitors[0]
                shot = sct.grab(mon)
                if not shot or not shot.size:
                    return None
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            total_left = min(m["left"] for m in sct.monitors[1:])
            total_top = min(m["top"] for m in sct.monitors[1:])
            total_right = max(m["left"] + m["width"] for m in sct.monitors[1:])
            total_bottom = max(m["top"] + m["height"] for m in sct.monitors[1:])
            w = total_right - total_left
            h = total_bottom - total_top
            if w < 100 or h < 100:
                mon = sct.monitors[0]
                shot = sct.grab(mon)
                if not shot or not shot.size:
                    return None
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            monitor = {"left": total_left, "top": total_top, "width": w, "height": h}
            screenshot = sct.grab(monitor)
            if not screenshot or not screenshot.size:
                return None
            return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    except Exception:
        return None


# ---------- Barcha usullarni ketma-ket sinash; ishlaganini qaytarish ----------
_GRAB_METHODS = [
    ("mss", _grab_mss),
    ("mss_all", _grab_mss_all_monitors),
    ("pyautogui", _grab_pyautogui),
    ("gdi", _grab_gdi),
    ("pil_grab", _grab_pil_grab),
]
_working_grab_method: Optional[str] = None


def grab_screen(region: Optional[Tuple[int, int, int, int]] = None, retries: int = 3) -> Optional[Image.Image]:
    """
    Ekranni olish — 5 usul, qayta urinish. Hech qachon xato chiqarmaydi.
    """
    global _working_grab_method
    methods = [(n, f) for n, f in _GRAB_METHODS if n == _working_grab_method] if _working_grab_method else _GRAB_METHODS
    for attempt in range(max(1, retries)):
        for name, fn in methods:
            try:
                img = fn(region)
                if img and hasattr(img, "size") and img.size[0] > 10 and img.size[1] > 10:
                    _working_grab_method = name
                    return img
            except Exception:
                pass
        if attempt < retries - 1:
            time.sleep(0.15)
    _working_grab_method = None
    return None

def _vision_jpeg_quality() -> int:
    return int(getattr(_config, "SCREEN_VISION_JPEG_QUALITY", 100) or 100)


def _enhance_for_vision(image: Image.Image) -> Image.Image:
    """Vision uchun kontrast va keskinlik — maksimal."""
    try:
        from PIL import ImageEnhance
        img = image.copy()
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Sharpness(img).enhance(1.4)
        return img
    except Exception:
        return image


def _describe_via_ollama_vision(image: "Image.Image", prompt: str, timeout: int = 30) -> str:
    """Ollama gemma3:4b lokal vision — tez, kichik rasm, qisqa javob."""
    try:
        import httpx as _hx
        # Rasm kichraytirish: kichik = tez (640px yetarli)
        w, h = image.size
        if max(w, h) > 640:
            ratio = 640 / max(w, h)
            image = image.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        _buf = io.BytesIO()
        image.save(_buf, format="JPEG", quality=65)
        _b64 = base64.b64encode(_buf.getvalue()).decode("utf-8")
        _model = os.getenv("OLLAMA_VISION_MODEL", "") or os.getenv("OLLAMA_OFFLINE_MODEL", "gemma3:4b") or "gemma3:4b"
        _resp = _hx.post(
            "http://localhost:11434/api/generate",
            json={"model": _model, "prompt": prompt, "images": [_b64], "stream": False,
                  "options": {"num_predict": 200, "temperature": 0}},
            timeout=timeout,
        )
        _resp.raise_for_status()
        _out = (_resp.json().get("response") or "").strip()
        return _out
    except Exception as _e:
        return ""


def _extract_text_via_vision(image: Image.Image) -> str:
    """Vision API orqali ekrandagi matnni olish — OCR ishlamasa fallback.
    1) OpenAI gpt-4o-mini  →  2) Ollama gemma3:4b (lokal, API siz)
    """
    try:
        use_fallback = getattr(_config, "SCREEN_OCR_FALLBACK_VISION", True)
        if not use_fallback:
            return ""
        from openai import OpenAI
        api_key = (getattr(_config, "OPENAI_API_KEY", "") or "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            # OpenAI yo'q — Ollama lokal vision ishlatamiz
            return _describe_via_ollama_vision(
                image,
                "List ALL text visible on this screenshot. Extract every word, button, label, title, menu item, URL. One item per line. If no text visible, reply: (no text)",
                timeout=30,
            )
        img = _enhance_for_vision(image)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_vision_jpeg_quality())
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        client = OpenAI(api_key=api_key)
        model = getattr(_config, "OPENAI_VISION_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        img_url = {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "List ALL text visible on this screenshot. Extract every word, button label, title, menu item, URL. One line per line of text. If no text, reply: (no text)"},
                {"type": "image_url", "image_url": img_url}
            ]}],
            max_tokens=2500,
        )
        out = (r.choices[0].message.content or "").strip()
        if out and "(no text)" not in out.lower():
            return out
        return ""
    except Exception:
        return ""


def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """OCR uchun rasmni maksimal yaxshilash."""
    try:
        img = image.copy()
        w, h = img.size
        if w < 1400 or h < 900:
            scale = min(2560 / max(w, 1), 1440 / max(h, 1), 2.5)
            if scale > 1.1:
                new_w, new_h = int(w * scale), int(h * scale)
                img = img.resize((new_w, new_h), getattr(Image, "Resampling", Image).LANCZOS)
        try:
            from PIL import ImageEnhance
            img = ImageEnhance.Contrast(img).enhance(1.15)
            img = ImageEnhance.Sharpness(img).enhance(1.25)
        except Exception:
            pass
        return img
    except Exception:
        return image


def extract_text(image: Optional[Image.Image]) -> str:
    """
    Extract text from image. Maksimal: Tesseract + Paddle birlashtirish, Vision fallback.
    Hech qachon xato chiqarmaydi — xato bo'lsa bo'sh qator.
    """
    if image is None:
        return ""
    try:
        img = _preprocess_for_ocr(image)
        text = ""
        engine = getattr(_config, "OCR_ENGINE", "paddle") or "paddle"
        lang = _ocr_lang()
        tesseract_lang = "eng" if lang in ("en", "eng") else "rus+eng"
        tesseract_txt = ""
        paddle_txt = ""

        # Usul 1 va 2: Tesseract + Paddle parallel (tezroq)
        tesseract_txt, paddle_txt = "", ""
        def _run_tesseract():
            nonlocal tesseract_txt
            if TESSERACT_AVAILABLE:
                try:
                    import pytesseract
                    tesseract_txt = pytesseract.image_to_string(img, lang=tesseract_lang, config="--psm 6 --oem 3")
                except Exception:
                    pass
        def _run_paddle():
            nonlocal paddle_txt
            if engine == "paddle" and PADDLE_AVAILABLE and paddle_ocr is not None:
                try:
                    result = paddle_ocr.ocr(np.array(img), cls=False)
                    if result and result[0]:
                        paddle_txt = " ".join([line[1][0] for line in result[0] if line[1][0]])
                except Exception:
                    pass
        t1 = threading.Thread(target=_run_tesseract, daemon=True)
        t2 = threading.Thread(target=_run_paddle, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=8.0)
        t2.join(timeout=8.0)

        # Maksimal: ikkala natijani birlashtirish (takrorlarsiz)
        if tesseract_txt and paddle_txt:
            if len(tesseract_txt.strip()) > len(paddle_txt.strip()):
                text = tesseract_txt
                extra = [w for w in paddle_txt.split() if w not in text and len(w) > 2]
                if extra:
                    text = (text + " " + " ".join(extra[:100])).strip()
            else:
                text = paddle_txt
                extra = [w for w in tesseract_txt.split() if w not in text and len(w) > 2]
                if extra:
                    text = (text + " " + " ".join(extra[:100])).strip()
        else:
            text = tesseract_txt or paddle_txt

        # Usul 3: Vision API fallback (har doim sinab ko'rish)
        if not text or len(text.strip()) < 10:
            vision_txt = _extract_text_via_vision(image)
            if vision_txt:
                text = vision_txt

        return (text or "").strip()
    except Exception:
        return ""


def extract_text_fast(image: Optional[Image.Image]) -> str:
    """Tez OCR — faqat Tesseract, Vision fallback yo'q (ekran savoli <8s)."""
    if image is None:
        return ""
    try:
        img = _preprocess_for_ocr(image)
        lang = _ocr_lang()
        tesseract_lang = "eng" if lang in ("en", "eng") else "rus+eng"
        if not TESSERACT_AVAILABLE:
            return ""
        import pytesseract
        out = pytesseract.image_to_string(img, lang=tesseract_lang, config="--psm 6 --oem 3")
        return (out or "").strip()
    except Exception:
        return ""


def summarize(text: str, max_chars: int = 400) -> str:
    """
    Summarize text using heuristic approach.
    
    Args:
        text: Input text to summarize
        max_chars: Maximum number of characters in summary
        
    Returns:
        Summarized text in Russian
    """
    if not text:
        return ""
    
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return text[:max_chars] if len(text) > max_chars else text
    
    # Score sentences by length and similarity to overall text
    scores = []
    for sentence in sentences:
        # Length score (longer sentences are often more informative)
        length_score = min(len(sentence) / 100, 1.0)
        
        # Similarity score to full text (rapidfuzz optional)
        if _HAVE_RAPIDFUZZ and fuzz:
            similarity_score = fuzz.ratio(text, sentence) / 100.0
        else:
            similarity_score = min(len(sentence) / max(len(text), 1), 1.0) * 0.5
        
        # Combined score
        combined_score = 0.7 * length_score + 0.3 * similarity_score
        scores.append((sentence, combined_score))
    
    # Sort by score and select top sentences
    scores.sort(key=lambda x: x[1], reverse=True)
    
    # Build summary
    summary = ""
    for sentence, _ in scores:
        if len(summary) + len(sentence) + 1 <= max_chars:
            summary += sentence + ". "
        else:
            break
    
    return summary.strip() or text[:max_chars]


def describe_screen_fast(image: Optional[Image.Image], lang: str = "ru") -> str:
    """Tez ekran tavsifi — faqat OCR + qisqa xulosa (LLM/Ollama kutmasdan)."""
    if image is None:
        return ""
    try:
        ocr = (extract_text_fast(image) or "").strip()
    except Exception:
        ocr = ""
    if not ocr:
        return ""
    _ru = (lang or "ru").strip().lower() == "ru"
    short = summarize(ocr, max_chars=420)
    if _ru:
        return "На экране (OCR): " + short
    return "On screen (OCR): " + short


def describe_screen_with_vision(image: Optional[Image.Image], lang: str = "ru") -> str:
    """
    Ekrandagi kontentni ENG MAKSIMAL tahlil — gpt-4o, detail=high, 1500 token.
    SCREEN_VISION_USE_LLM=0 yoki Groq — faqat describe_screen_fast.
    """
    if image is None:
        return ""
    _use_llm = getattr(_config, "SCREEN_VISION_USE_LLM", False)
    _base_url_now = (getattr(_config, "OPENAI_BASE_URL", "") or "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
    _using_groq = "groq.com" in _base_url_now
    if not _use_llm or _using_groq:
        return describe_screen_fast(image, lang=lang)[:4000]
    model = "gpt-4o"
    max_tokens = 1500
    quality = _vision_jpeg_quality()
    _reply_lang = "in Russian (по-русски)" if (lang or "").strip().lower() == "ru" else "in English"
    _empty_desktop = " If the screen shows ONLY the desktop (wallpaper, taskbar, no open windows): say exactly: На экране только рабочий стол, открытых окон нет." if (lang or "").strip().lower() == "ru" else " If only desktop is visible (no open windows): say 'Only desktop visible, no open windows.'"
    prompt_full = (
        "You see a screenshot of the user's screen. Analyze it in MAXIMUM detail.\n"
        "1) Text: ALL visible text — titles, buttons, labels, URLs, menu items, errors, notifications. Copy exactly.\n"
        "2) Apps: which programs are OPEN and visible (browser, Telegram, player, editor), tab/window titles, URLs in address bar.\n"
        "3) Video/movie/game: if video is playing — describe the CURRENT FRAME: scene, characters, actions. Game: name and state.\n"
        "4) Images/photos: if MULTIPLE images — describe EACH one. People, places, objects.\n"
        "5) Layout: where things are (left panel, center, status bar).\n"
        "6) Overall: what is on screen. Reply " + _reply_lang + ", 4–6 detailed paragraphs. Be precise — only what is visible."
        + _empty_desktop
    )
    prompt_short = (
        "Describe this screen: what apps, text, images, or video are visible. "
        "If only desktop — say so clearly. Reply " + _reply_lang + ", 2–3 paragraphs." + _empty_desktop
    )
    img_for_vision = _enhance_for_vision(image)
    prompts = [prompt_full, prompt_short]
    # API yo'q yoki placeholder bo'lsa — darhol Ollama lokal vision ga o'tamiz
    _api_key_check = (getattr(_config, "OPENAI_API_KEY", "") or "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    # Groq base_url bo'lsa yoki placeholder kalit bo'lsa — OpenAI vision ishlamaydi, darhol Ollama
    _base_url_now = (getattr(_config, "OPENAI_BASE_URL", "") or "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
    _key_is_placeholder = (not _api_key_check or _api_key_check.startswith("sk-...") or _api_key_check == "sk-" or len(_api_key_check) < 20)
    _using_groq_vision = "groq.com" in _base_url_now
    if not _api_key_check or _key_is_placeholder or _using_groq_vision:
        _ol_prompt = (
            "Describe this screenshot in detail. What apps are open? What text is visible? "
            "What is happening on screen? Reply in Russian (по-русски), 2-4 paragraphs."
            if (lang or "ru") == "ru" else
            "Describe this screenshot in detail. What apps are open? What text is visible? Reply in English, 2-4 paragraphs."
        )
        _ol_out = _describe_via_ollama_vision(img_for_vision, _ol_prompt, timeout=45)
        if _ol_out:
            return _ol_out[:4000]
        return ""

    for attempt, prompt in enumerate(prompts):
        try:
            from openai import OpenAI
            api_key = (getattr(_config, "OPENAI_API_KEY", "") or "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                return ""
            buf = io.BytesIO()
            img_for_vision.save(buf, format="JPEG", quality=quality)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            img_url = {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}
            client = OpenAI(api_key=api_key)
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": img_url}
                ]}],
                max_tokens=max_tokens,
            )
            out = (r.choices[0].message.content or "").strip()
            if out:
                return out[:4000]
        except Exception as e:
            if attempt == 0:
                model = getattr(_config, "OPENAI_VISION_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
            if os.getenv("NEUROKEY_DEBUG", "").strip().lower() in ("1", "true", "yes"):
                print("[screen_vision] describe_screen_with_vision:", repr(e), flush=True)

    # OpenAI ham ishlamadi — Ollama lokal vision (gemma3:4b) ga fallback
    try:
        _fb_prompt = (
            "Скрин экрана. Коротко: какие приложения открыты, что видно, заголовки окон. По-русски, 3-4 предложения."
            if (lang or "ru") == "ru" else
            "Screenshot. Briefly: what apps are open, what is visible, window titles. 3-4 sentences."
        )
        _fb_out = _describe_via_ollama_vision(img_for_vision, _fb_prompt, timeout=30)
        if _fb_out:
            return _fb_out[:4000]
    except Exception:
        pass
    return ""


def get_screen_context_safe() -> Tuple[str, str]:
    """
    Ekran matni va Vision tavsifini xavfsiz olish. Maksimal rejimda kengroq limit.
    Returns: (ocr_text, vision_description)
    """
    txt, vision = "", ""
    try:
        img = grab_screen()
        if img:
            txt = extract_text(img)
            try:
                vision = describe_screen_with_vision(img)
            except Exception:
                pass
    except Exception:
        pass
    return ((txt or "").strip()[:8000], (vision or "").strip()[:4000])


def get_screen_description_for_speech() -> str:
    """
    Ekrandagi kontentni gapirish uchun tavsif. 2–3 usul: Vision, OCR, birlashtirish.
    Rasm, video, audio player — barcha tahlil qilinadi. Hech qachon xato chiqarmaydi.
    """
    try:
        img = grab_screen()
        if not img:
            return ""
        order = (getattr(_config, "SCREEN_ANALYSIS_ORDER", "vision,ocr") or "vision,ocr").strip().lower()
        vision_desc, ocr_txt = "", ""

        # Vision va OCR parallel yoki ketma-ket
        if "vision" in order:
            try:
                vision_desc = describe_screen_with_vision(img)
            except Exception:
                pass
        if "ocr" in order:
            try:
                ocr_txt = extract_text(img)
            except Exception:
                pass

        # Birlashtirish: Vision birinchi, OCR zaxira — maksimal limit
        if vision_desc:
            return vision_desc.strip()[:2500]
        if ocr_txt and len(ocr_txt) > 20:
            return ("On screen: " + ocr_txt).strip()[:2000]
        if vision_desc or ocr_txt:
            return (vision_desc or ocr_txt).strip()[:1500]
        return ""
    except Exception:
        return ""


def get_screen_full_analysis() -> str:
    """
    Ekrandagi barcha kontentni to'liq tahlil — rasm, video, matn, dasturlar.
    Maksimal rejim: Vision + OCR to'liq birlashtiriladi.
    """
    try:
        img = grab_screen()
        if not img:
            return ""
        parts = []
        vision_desc = ""
        try:
            vision_desc = describe_screen_with_vision(img)
            if vision_desc:
                parts.append(vision_desc.strip()[:3500])
        except Exception:
            pass
        ocr_txt = ""
        try:
            ocr_txt = extract_text(img)
            if ocr_txt and len(ocr_txt) > 20:
                if not parts:
                    parts.append("Text on screen: " + ocr_txt[:2500])
                else:
                    extra = [w for w in ocr_txt.split() if w not in vision_desc and len(w) > 2][:200]
                    if extra:
                        parts.append("Additional text: " + " ".join(extra))
        except Exception:
            pass
        if parts:
            return "\n\n".join(parts)[:6000]
        return ""
    except Exception:
        return ""


def get_working_grab_method() -> Optional[str]:
    """Qaysi ekran usuli hozir ishlayapti (mss, pyautogui, gdi, pil_grab)."""
    return _working_grab_method
