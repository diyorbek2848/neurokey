# -*- coding: utf-8 -*-
"""
NeuroKey: rasm, video va audio yozuvlarni tahlil qilish.
- Rasm: OpenAI Vision (tahlil, nima ko‘rinmoqda).
- Video: kadrlar ajratib, har birini Vision bilan tahlil, keyin birlashtirish.
- Audio: Whisper transkripsiya + qisqa xulosa.
"""
import base64
import io
import os
import re
from typing import Optional

# PIL — screen_vision da ham bor
try:
    from PIL import Image
except ImportError:
    Image = None


def _openai_client():
    try:
        from openai import OpenAI
        import config as _cfg
        api_key = (getattr(_cfg, "OPENAI_API_KEY", "") or "").strip()
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key:
            return OpenAI(api_key=api_key)
    except Exception:
        pass
    return None


def _vision_model():
    try:
        import config as C
        return getattr(C, "OPENAI_VISION_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    except Exception:
        return "gpt-4o-mini"


# --- Rasm tahlili ---

def analyze_image_file(file_path: str, user_question: str = "") -> str:
    """
    Foydalanuvchi yuborgan rasm faylini OpenAI Vision orqali tahlil qiladi.
    Qo‘llab-quvvatlanadi: .jpg, .jpeg, .png, .gif, .webp, .bmp.
    """
    if not file_path or not os.path.isfile(file_path):
        return ""
    if not Image:
        return "[Error: PIL not installed for image analysis.]"
    try:
        with Image.open(file_path) as img:
            img = img.convert("RGB")
    except Exception as e:
        if os.getenv("NEUROKEY_DEBUG", "").strip().lower() in ("1", "true", "yes"):
            print("[media_vision] image open failed:", repr(e), flush=True)
        return ""
    client = _openai_client()
    if not client:
        return ""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    prompt = (
        "The user shared an image (photo or picture). Analyze it in detail.\n"
        "Describe: (1) What is in the image — objects, people, places, text if any. "
        "(2) Setting and context. (3) Mood or activity if visible. "
        "Reply in English, 2–4 short paragraphs. Be precise — only what is actually visible."
    )
    if (user_question or "").strip():
        prompt += f"\nUser also asked: {user_question.strip()[:200]}"
    try:
        r = client.chat.completions.create(
            model=_vision_model(),
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]}
            ],
            max_tokens=800,
        )
        out = (r.choices[0].message.content or "").strip()
        return out[:3000] if out else ""
    except Exception as e:
        if os.getenv("NEUROKEY_DEBUG", "").strip().lower() in ("1", "true", "yes"):
            print("[media_vision] image vision failed:", repr(e), flush=True)
        return ""


# --- Video: kadrlar olish ---

def _video_frames_opencv(path: str, max_frames: int = 6):
    """OpenCV bilan video dan max_frames ta kadr (vaqt bo‘yicha teng taqsimlangan)."""
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return []
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        indices = []
        for i in range(max_frames):
            pos = int((i + 0.5) / max_frames * total) if total > 0 else i * 30
            indices.append(min(pos, total - 1) if total else 0)
        frames = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                frame_rgb = frame[:, :, ::-1]  # BGR -> RGB
                frames.append(Image.fromarray(frame_rgb))
        cap.release()
        return frames
    except Exception:
        return []


def _video_frames_imageio(path: str, max_frames: int = 6):
    """imageio bilan video dan kadrlar."""
    try:
        import imageio.v3 as iio
        meta = iio.immeta(path)
        count = meta.get("nframes") or 0
        if count <= 0:
            # stream: take first N frames
            frames = []
            for i, fr in enumerate(iio.imiter(path)):
                if i >= max_frames:
                    break
                if hasattr(fr, "__array__"):
                    arr = fr
                else:
                    arr = fr
                try:
                    from PIL import Image as PImage
                    if arr.ndim == 2:
                        arr = __import__("numpy").stack([arr, arr, arr], axis=-1)
                    frames.append(PImage.fromarray(arr))
                except Exception:
                    pass
            return frames
        step = max(1, count // max_frames)
        frames = []
        for i in range(0, min(count, max_frames * step), step):
            try:
                fr = iio.imread(path, index=i)
                from PIL import Image as PImage
                frames.append(PImage.fromarray(fr))
            except Exception:
                pass
            if len(frames) >= max_frames:
                break
        return frames
    except Exception:
        return []


def analyze_video_file(file_path: str, max_frames: int = 6, user_question: str = "") -> str:
    """
    Video faylni tahlil qiladi: bir nechta kadrni Vision API ga yuboradi va javoblarni birlashtiradi.
    Qo‘llab-quvvatlanadi: .mp4, .avi, .mov, .mkv va boshqalar (opencv yoki imageio qo‘llab-quvvatlasa).
    """
    if not file_path or not os.path.isfile(file_path):
        return ""
    if not Image:
        return "[Error: PIL not installed for video frame analysis.]"
    frames = _video_frames_opencv(file_path, max_frames)
    if not frames:
        frames = _video_frames_imageio(file_path, max_frames)
    if not frames:
        return "[Could not extract frames from video. Install opencv-python or imageio with ffmpeg.]"
    client = _openai_client()
    if not client:
        return ""
    descriptions = []
    for i, img in enumerate(frames):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        prompt = (
            f"This is frame {i + 1} of a video (evenly spaced). Describe what is happening in this frame: "
            "scene, people, actions, text on screen, setting. One short paragraph in English."
        )
        try:
            r = client.chat.completions.create(
                model=_vision_model(),
                messages=[
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]}
                ],
                max_tokens=300,
            )
            out = (r.choices[0].message.content or "").strip()
            if out:
                descriptions.append(f"Frame {i + 1}: {out}")
        except Exception:
            pass
    if not descriptions:
        return ""
    combined = "\n\n".join(descriptions)
    if (user_question or "").strip():
        # Optional: one more LLM call to summarize and answer user question
        try:
            r = client.chat.completions.create(
                model=_vision_model(),
                messages=[
                    {"role": "user", "content": (
                        "Video analysis (from key frames):\n\n" + combined[:4000] + "\n\n"
                        "User asked: " + user_question.strip()[:300] + "\n\n"
                        "Summarize what happens in the video and answer the user's question in 2–4 short paragraphs in English."
                    )}
                ],
                max_tokens=600,
            )
            return (r.choices[0].message.content or "").strip()[:2500] or combined
        except Exception:
            pass
    return combined[:3500]


# --- Audio yozuv tahlili ---

def analyze_audio_file(file_path: str, user_question: str = "") -> str:
    """
    Audio yozuvni Whisper orqali transkripsiya qiladi; kerak bo‘lsa qisqa xulosa.
    Qo‘llab-quvvatlanadi: .wav, .mp3, .m4a, .mp4, .webm (OpenAI 25 MB gacha).
    """
    if not file_path or not os.path.isfile(file_path):
        return ""
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > 24:
        return "[Audio file too large for transcription (max 25 MB).]"
    ext = (os.path.splitext(file_path)[1] or "").lower()
    allowed = (".wav", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".webm")
    if ext not in allowed:
        return f"[Unsupported audio format: {ext}. Use one of: {', '.join(allowed)}]"
    client = _openai_client()
    if not client:
        return ""
    try:
        with open(file_path, "rb") as f:
            r = client.audio.transcriptions.create(model="whisper-1", file=f)
        transcript = (r.text or "").strip()
        if not transcript:
            return "[No speech detected in the recording.]"
        if not (user_question or "").strip():
            return "Transcript:\n" + transcript[:4000]
        # User asked something specific — add short summary/answer
        try:
            rr = client.chat.completions.create(
                model=_vision_model(),
                messages=[
                    {"role": "user", "content": (
                        "Recording transcript:\n\n" + transcript[:3500] + "\n\n"
                        "User asked: " + user_question.strip()[:300] + "\n\n"
                        "Answer based on the transcript in 2–4 short sentences in English."
                    )}
                ],
                max_tokens=400,
            )
            summary = (rr.choices[0].message.content or "").strip()
            return "Transcript:\n" + transcript[:2000] + "\n\nAnswer based on recording:\n" + summary
        except Exception:
            return "Transcript:\n" + transcript[:4000]
    except Exception as e:
        if os.getenv("NEUROKEY_DEBUG", "").strip().lower() in ("1", "true", "yes"):
            print("[media_vision] audio transcribe failed:", repr(e), flush=True)
        return ""


# --- Fayl turi va yo‘l aniqlash ---

def is_media_analysis_request(text: str) -> bool:
    """Foydalanuvchi rasm/video/audio tahlilini so‘rayaptimi."""
    if not (text or "").strip():
        return False
    low = text.lower().strip()
    triggers = [
        "analyze this image", "analyze this picture", "analyze this photo", "analyze image", "analyze picture", "analyze photo",
        "describe this image", "describe this picture", "describe this photo", "what's in this image", "what's in this picture",
        "analyze this video", "analyze video", "what's in this video", "describe this video", "video haqida", "video nima",
        "analyze this recording", "analyze this audio", "analyze recording", "analyze audio", "transcribe this", "what's said in this",
        "tahlil qil rasm", "rasmni tahlil", "videoni tahlil", "yozuvni tahlil", "ovoz yozuv"
    ]
    return any(t in low for t in triggers)


def extract_media_path_from_text(text: str) -> Optional[str]:
    """
    Matndan fayl yo‘lini oladi: qo‘shtirnoq ichidagi yo‘l yoki .png/.jpg/.mp4/.wav va h.k. bilan tugaydigan so‘z.
    """
    if not text:
        return None
    # "C:\path\to\file.png" or 'C:\path\to\file.png'
    m = re.search(r'["\']([^"\']+\.(?:png|jpe?g|gif|webp|bmp|mp4|avi|mov|mkv|webm|wav|mp3|m4a|mpga|mpeg))["\']', text, re.IGNORECASE)
    if m:
        p = m.group(1).strip()
        if os.path.isfile(p):
            return p
    # Path without quotes: word that looks like path ending with extension
    m = re.search(r'(?:\b[A-Za-z]:\\[^\s]+\.(?:png|jpe?g|gif|webp|bmp|mp4|avi|mov|mkv|webm|wav|mp3|m4a|mpga|mpeg)\b|\b/[^\s]+\.(?:png|jpe?g|gif|webp|bmp|mp4|avi|mov|mkv|webm|wav|mp3|m4a|mpga|mpeg)\b)', text, re.IGNORECASE)
    if m:
        p = m.group(0).strip()
        if os.path.isfile(p):
            return p
    return None


def get_media_path_from_config() -> Optional[str]:
    """Config yoki muhit orqali oxirgi media fayl yo‘lini olish."""
    try:
        import config as C
        path = getattr(C, "NEUROKEY_LAST_MEDIA_PATH", None) or os.getenv("NEUROKEY_LAST_MEDIA_PATH", "").strip()
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    return None


def analyze_media(file_path: str, text: str, kind: Optional[str] = None) -> str:
    """
    Fayl turiga qarab rasm / video / audio tahlilini qaytaradi.
    kind: "image" | "video" | "audio" | None (avto).
    """
    if not file_path or not os.path.isfile(file_path):
        return ""
    ext = (os.path.splitext(file_path)[1] or "").lower()
    if kind is None:
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            kind = "image"
        elif ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
            kind = "video"
        elif ext in (".wav", ".mp3", ".m4a", ".mpga", ".mpeg"):
            kind = "audio"
        else:
            return ""
    user_q = (text or "").strip()[:300]
    if kind == "image":
        return analyze_image_file(file_path, user_q)
    if kind == "video":
        return analyze_video_file(file_path, user_question=user_q)
    if kind == "audio":
        return analyze_audio_file(file_path, user_q)
    return ""


def analyze_any_media(
    file_path: Optional[str] = None,
    text: str = "",
    include_screen: bool = True,
) -> str:
    """
    Barcha media turlarini birlashtirib tahlil: ekran, rasm, video, audio.
    - file_path bo'lsa: fayl turiga qarab tahlil
    - file_path bo'lmasa va include_screen=True: ekranni grab qilib Vision bilan tahlil
    Gapirish/ko'rsatish uchun qisqa tavsif qaytaradi.
    """
    user_q = (text or "").strip()[:300]
    if file_path and os.path.isfile(file_path):
        return analyze_media(file_path, text, kind=None)
    if include_screen:
        try:
            from screen_vision import grab_screen, describe_screen_with_vision, extract_text
            img = grab_screen() if grab_screen else None
            if img:
                desc = describe_screen_with_vision(img) if describe_screen_with_vision else ""
                if desc:
                    return desc.strip()[:2000]
                txt = extract_text(img) if extract_text else ""
                if txt:
                    return txt.strip()[:1500]
        except Exception:
            pass
    return ""
