# file_vision.py
"""
PDF (slaydli, rasmli) va video fayllarni vizual tahlil qilish.
- PDF: har sahifani rasm sifatida Ollama vision ga beradi
- Video: kalit freymlarni ajratib Ollama vision ga beradi
- Internet kerak emas (Ollama lokal)
"""
import os
import io
import time
import base64
import threading
from typing import List, Optional, Tuple
from PIL import Image

# ---------- Ollama vision yordamchi ----------

def _ollama_vision(image: Image.Image, prompt: str, model: str = None, timeout: int = 45) -> str:
    """PIL rasmni Ollama vision ga yuborish."""
    try:
        import urllib.request, json
        _model = model or os.getenv("OLLAMA_VISION_MODEL", "") or "gemma3:4b"
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        payload = json.dumps({
            "model": _model,
            "prompt": prompt,
            "images": [b64],
            "stream": False,
            "options": {"num_predict": 400}
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return (data.get("response") or "").strip()
    except Exception as e:
        return ""


def _resize_for_vision(img: Image.Image, max_side: int = 1024) -> Image.Image:
    """Vision uchun katta rasmni kichraytirish."""
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    ratio = max_side / max(w, h)
    return img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)


# ---------- PDF tahlil ----------

def analyze_pdf(path: str, max_pages: int = 30, lang: str = "ru") -> str:
    """
    PDF faylni sahifa-sahifa tahlil qilish.
    - Matnli sahifalar: to'g'ridan matn olish (tez)
    - Rasmli/slaydli sahifalar: Ollama vision orqali tahlil
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return _pdf_text_only(path)

    if not os.path.isfile(path):
        return f"Fayl topilmadi: {path}"

    _reply_lang = "по-русски" if lang == "ru" else "in English"
    results = []

    try:
        doc = fitz.open(path)
        total = min(len(doc), max_pages)
        print(f"[file_vision] PDF: {total} sahifa tahlil boshlanmoqda...", flush=True)

        for i in range(total):
            page = doc[i]
            page_num = i + 1

            # 1. Matn olish (OCR shart emas — vektor matn)
            text = page.get_text("text").strip()

            # 2. Rasmlar bormi?
            images = page.get_images(full=True)
            has_images = len(images) > 0

            # 3. Matn kam va rasm ko'p bo'lsa — vision ishlatish
            if len(text) < 50 or has_images:
                # Sahifani rasm sifatida render qilish
                mat = fitz.Matrix(1.5, 1.5)  # 1.5x zoom — sifat uchun
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("jpeg")
                img = Image.open(io.BytesIO(img_data))
                img = _resize_for_vision(img)

                prompt = (
                    f"Это страница {page_num} из PDF документа. "
                    f"Опиши подробно: текст, заголовки, графики, изображения, таблицы, схемы. "
                    f"Отвечай {_reply_lang}."
                    if lang == "ru" else
                    f"This is page {page_num} of a PDF. Describe: text, headings, charts, images, tables, diagrams. Reply in English."
                )
                vision_desc = _ollama_vision(img, prompt, timeout=40)

                if vision_desc:
                    results.append(f"[Sahifa {page_num}]: {vision_desc}")
                elif text:
                    results.append(f"[Sahifa {page_num}]: {text[:500]}")
            else:
                # Matnli sahifa — to'g'ridan olish
                results.append(f"[Sahifa {page_num}]: {text[:800]}")

        doc.close()

        if not results:
            return "PDF bo'sh yoki o'qib bo'lmadi."

        combined = "\n\n".join(results)
        print(f"[file_vision] PDF tahlil tugadi: {len(results)} sahifa", flush=True)
        return combined[:12000]

    except Exception as e:
        print(f"[file_vision] PDF xato: {e}", flush=True)
        return _pdf_text_only(path)


def _pdf_text_only(path: str) -> str:
    """Fallback: faqat matn olish (pdfplumber)."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages[:20]):
                t = (page.extract_text() or "").strip()
                if t:
                    pages.append(f"[Sahifa {i+1}]: {t[:600]}")
            return "\n\n".join(pages) or "PDF matn topilmadi."
    except Exception as e:
        return f"PDF o'qib bo'lmadi: {e}"


# ---------- Video tahlil ----------

def analyze_video(path: str, max_frames: int = 8, interval_sec: float = None, lang: str = "ru") -> str:
    """
    Video fayldan kalit freymlarni olib Ollama vision ga berish.
    - Qotib qolmaydi: har kadr uchun timeout bor
    - max_frames kadr tahlil qilinadi (teng oraliqda)
    """
    try:
        import cv2 as _cv2
    except ImportError:
        return "cv2 kutubxonasi yo'q — video tahlil mumkin emas."

    if not os.path.isfile(path):
        return f"Video fayl topilmadi: {path}"

    _reply_lang = "по-русски" if lang == "ru" else "in English"

    try:
        cap = _cv2.VideoCapture(path)
        if not cap.isOpened():
            return "Video ochilmadi."

        total_frames = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(_cv2.CAP_PROP_FPS) or 25
        duration_sec = total_frames / fps

        # Oraliq: teng bo'lingan N ta freym
        if interval_sec:
            step = int(interval_sec * fps)
        else:
            step = max(1, total_frames // max_frames)

        frame_positions = list(range(0, total_frames, step))[:max_frames]

        print(f"[file_vision] Video: {duration_sec:.0f}s, {len(frame_positions)} freym tahlil...", flush=True)

        results = []
        for pos in frame_positions:
            cap.set(_cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if not ret:
                continue

            time_sec = pos / fps
            # BGR → RGB
            rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img = _resize_for_vision(img, max_side=768)

            prompt = (
                f"Это кадр из видео на {time_sec:.1f} секунде. "
                f"Опиши: что происходит, кто/что на экране, текст, действия. "
                f"Отвечай {_reply_lang}, 2-3 предложения."
                if lang == "ru" else
                f"This is a video frame at {time_sec:.1f}s. Describe: what's happening, who/what is visible, text, actions. Reply in English, 2-3 sentences."
            )

            desc = _ollama_vision(img, prompt, timeout=35)
            if desc:
                results.append(f"[{time_sec:.0f}s]: {desc}")

        cap.release()

        if not results:
            return "Video freymlaridan tavsif olib bo'lmadi."

        summary_parts = [f"Video davomiyligi: {duration_sec:.0f} sekund\n"]
        summary_parts.extend(results)
        return "\n\n".join(summary_parts)[:8000]

    except Exception as e:
        print(f"[file_vision] Video xato: {e}", flush=True)
        return f"Video tahlil xatosi: {e}"


# ---------- Umumiy kirish nuqtasi ----------

def analyze_file(path: str, lang: str = "ru") -> Tuple[bool, str]:
    """
    Har qanday fayl — PDF yoki video — tahlil qilish.
    Returns: (success, result_text)
    """
    if not path or not os.path.isfile(path):
        return False, "Fayl topilmadi."

    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        result = analyze_pdf(path, lang=lang)
        return bool(result), result

    if ext in (".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"):
        result = analyze_video(path, lang=lang)
        return bool(result), result

    return False, f"Qo'llab-quvvatlanmaydigan format: {ext}"
