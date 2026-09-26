# -*- coding: utf-8 -*-
"""NeuroKey — YouTube video qidirish.

API kalit: YOUTUBE_API_KEY (.env)
Bepul: 10,000 unit/kun (har qidiruv = 100 unit → ~100 qidiruv/kun)

Buyruqlar:
    "YouTube da Python darsliklari qidir"
    "NeuroKey haqida video bor mi"
    "Xurmo reklama videosini top"
"""
import os, re, ssl, urllib.parse, urllib.request, json
from typing import Optional, List, Dict

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

try:
    import config as C
    _KEY = (os.getenv("YOUTUBE_API_KEY") or getattr(C, "YOUTUBE_API_KEY", "")).strip()
except Exception:
    _KEY = os.getenv("YOUTUBE_API_KEY", "").strip()

_BASE = "https://www.googleapis.com/youtube/v3"

_TRIGGERS = [
    "youtube", "ютуб", "юутуб",
    "video qidir", "видео найди", "video top", "видео поищи",
    "video bor mi", "есть видео", "video ko'rsat",
]


def is_available() -> bool:
    return bool(_KEY)


def is_youtube_request(text: str) -> bool:
    low = text.lower()
    return any(t in low for t in _TRIGGERS)


def search_videos(query: str, max_results: int = 5) -> List[Dict]:
    if not _KEY:
        return []
    params = urllib.parse.urlencode({
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "key": _KEY,
    })
    url = f"{_BASE}/search?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10, context=_SSL_CTX) as r:
            data = json.loads(r.read().decode())
        return data.get("items", [])
    except Exception:
        return []


def _parse_duration(iso: str) -> str:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return ""
    h, mn, s = m.group(1), m.group(2), m.group(3)
    parts = []
    if h: parts.append(f"{h}:{(mn or '0').zfill(2)}:{(s or '0').zfill(2)}")
    elif mn: parts.append(f"{mn}:{(s or '0').zfill(2)}")
    elif s: parts.append(f"0:{s.zfill(2)}")
    return parts[0] if parts else ""


def handle(text: str, tts_say=None) -> Optional[str]:
    if not is_youtube_request(text):
        return None
    if not is_available():
        return "YOUTUBE_API_KEY yo'q. developers.google.com/youtube dan bepul kalit oling."

    def say(m):
        if tts_say:
            try: tts_say(m)
            except Exception: pass

    low = text.lower()
    # Qidiruv so'rovini ajratish
    query = text
    for t in _TRIGGERS:
        if t in low:
            idx = low.find(t)
            after = text[idx + len(t):].strip(" :—-\n")
            if after and len(after) > 2:
                query = after
                break

    say(f"YouTube da qidirilmoqda: {query}")
    items = search_videos(query, max_results=5)
    if not items:
        msg = "YouTube da hech narsa topilmadi."
        say(msg)
        return msg

    lines = []
    for i, item in enumerate(items[:5], 1):
        title = item.get("snippet", {}).get("title", "")
        channel = item.get("snippet", {}).get("channelTitle", "")
        vid_id = item.get("id", {}).get("videoId", "")
        url = f"https://youtube.com/watch?v={vid_id}" if vid_id else ""
        lines.append(f"{i}. {title} — {channel}")
        if url:
            lines.append(f"   {url}")

    # Birinchi videoni ayt
    first = items[0].get("snippet", {}).get("title", "")
    say(f"Topildi: {first} va yana {len(items)-1} ta video.")
    return "\n".join(lines)
