# -*- coding: utf-8 -*-
"""
NeuroKey tez javob serveri (2025).
- GET: ob-havo, yangiliklar (realtime, context, weather, news).
- POST /ask: boshqa komp savol yuboradi — sizning kompingiz LLM da javob beradi (tez, optimal).
Siz istaganingizda serverni o'chirib qo'yasiz — boshqa komp local rejimda ishlaydi.
Ishga tushirish: python neurokey_cache_server.py [port]
To'xtatish: Ctrl+C yoki Stop_NeuroKey_Server.bat
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Ixtiyoriy: faqat shu kalit bilan /ask so'rovlari qabul qilinadi (boshqa komp .env da beradi)
SERVER_SECRET = (os.getenv("NEUROKEY_SERVER_SECRET") or "").strip()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Barcha ma'lumotlar — har savolga javob uchun
CACHE = {
    "weather": "",
    "news": "",
    "news_ru": "",
    "news_tech": "",
    "news_sport": "",
    "context": "",  # bitta to'liq matn: LLM ga berish uchun
    "updated": 0.0,
}
CACHE_LOCK = threading.Lock()
REFRESH_INTERVAL = int(os.getenv("NEUROKEY_CACHE_REFRESH_SEC", "30"))  # 30 sek — har kungi yangi ma'lumot
CITY = os.getenv("NEUROKEY_CITY", "Tashkent")

# Qo'shimcha RSS (texnika, sport) — server o'zi yuklaydi
EXTRA_FEEDS = {
    "tech": [
        "https://techcrunch.com/feed/",
        "https://feeds.feedburner.com/TechCrunch/",
    ],
    "sport": [
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.espn.com/espn/rss/news",
    ],
}


def _fetch_rss_titles(feed_urls: list, limit: int = 4) -> str:
    """RSS dan sarlavhalarni olib qisqa matn qaytaradi."""
    try:
        import requests
        import feedparser
    except ImportError:
        return ""
    lines = []
    seen = set()
    for url in feed_urls[:3]:
        try:
            r = requests.get(url, headers={"User-Agent": "NeuroKey/1.0"}, timeout=8)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for e in (feed.entries or [])[:limit]:
                title = (e.get("title") or "").strip()
                if title and title not in seen:
                    seen.add(title)
                    lines.append(f"• {title[:120]}")
                    if len(lines) >= limit:
                        break
        except Exception:
            continue
        if len(lines) >= limit:
            break
    return "\n".join(lines) if lines else ""


def refresh_cache():
    """Barcha ma'lumotlarni yangilaydi — to'xtovsiz ishlaydi."""
    try:
        from juma_news_weather import weather_by_name, get_top_news, render_news_brief

        w = weather_by_name(CITY, lang="ru")
        news_world = get_top_news("world", limit=8)  # dunyo bo'ylab ko'proq yangilik
        news_ru = get_top_news("ru", limit=4)
        brief_world = render_news_brief(news_world, lang="ru") if news_world else ""
        brief_ru = render_news_brief(news_ru, lang="ru") if news_ru else ""

        tech_titles = _fetch_rss_titles(EXTRA_FEEDS["tech"], 3)
        sport_titles = _fetch_rss_titles(EXTRA_FEEDS["sport"], 3)

        tech_block = ("Технологии:\n" + tech_titles) if tech_titles else ""
        sport_block = ("Спорт:\n" + sport_titles) if sport_titles else ""

        # Bitta to'liq kontekst — har qanday savolga javob uchun
        parts = [
            "Актуальные данные (постоянно обновляются, 2025):",
            "",
            "Погода: " + (w or "—"),
            "",
            "Новости мира:",
            (brief_world or "—"),
            "",
            "Новости РФ:",
            (brief_ru or "—"),
        ]
        if tech_block:
            parts.extend(["", tech_block])
        if sport_block:
            parts.extend(["", sport_block])
        parts.extend([
            "",
            "Используй эти данные для ответов на вопросы о погоде, новостях, событиях, технологиях, спорте и общем положении дел.",
        ])
        context = "\n".join(parts)

        with CACHE_LOCK:
            CACHE["weather"] = w or ""
            CACHE["news"] = brief_world
            CACHE["news_ru"] = brief_ru
            CACHE["news_tech"] = tech_block
            CACHE["news_sport"] = sport_block
            CACHE["context"] = context
            CACHE["updated"] = time.time()
    except Exception:
        pass


def refresh_loop():
    """Har REFRESH_INTERVAL sekunda yangilab turadi — to'xtamaydi."""
    while True:
        time.sleep(REFRESH_INTERVAL)
        refresh_cache()


class RealtimeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        with CACHE_LOCK:
            data = dict(CACHE)

        if path in ("/realtime", "/realtime/", ""):
            self._send_json(data)
        elif path in ("/context", "/context/"):
            self._send_json({"context": data.get("context", ""), "updated": data.get("updated", 0)})
        elif path in ("/weather", "/weather/"):
            self._send_json({"weather": data.get("weather", ""), "updated": data.get("updated", 0)})
        elif path in ("/news", "/news/"):
            self._send_json({"news": data.get("news", ""), "updated": data.get("updated", 0)})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in ("/ask", "/ask/"):
            self.send_response(404)
            self.end_headers()
            return
        # Secret tekshiruvi
        if SERVER_SECRET:
            secret = self.headers.get("X-NeuroKey-Secret", "").strip()
            if not secret:
                try:
                    clen = int(self.headers.get("Content-Length", 0) or 0)
                    if clen and clen < 10000:
                        body = self.rfile.read(clen).decode("utf-8", errors="ignore")
                        payload = json.loads(body) if body.strip() else {}
                        secret = (payload.get("secret") or "").strip()
                except Exception:
                    pass
            if secret != SERVER_SECRET:
                self.send_response(403)
                self.end_headers()
                return
        try:
            clen = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(clen).decode("utf-8", errors="ignore") if clen else "{}"
            payload = json.loads(body) if body.strip() else {}
        except Exception:
            self._send_json({"error": "Invalid JSON"})
            return
        text = (payload.get("text") or "").strip()
        if not text:
            self._send_json({"error": "text required"})
            return
        web_ctx = (payload.get("web_ctx") or "").strip()
        lang = (payload.get("lang") or "ru").strip() or "ru"
        brief = bool(payload.get("brief"))
        try:
            from llm_router import answer
            reply = answer(
                text,
                web_ctx=web_ctx,
                lang_hint=lang,
                history=payload.get("history") or [],
                profile_context=(payload.get("profile_context") or "").strip(),
                screen_context=(payload.get("screen_context") or "").strip(),
                current_datetime=payload.get("current_datetime") or "",
                brief=brief,
            )
            self._send_json({"reply": (reply or "").strip()})
        except Exception as e:
            self._send_json({"error": str(e)[:200]})

    def _send_json(self, obj):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    # PID fayl — Stop_NeuroKey_Server.bat to'xtatish uchun
    try:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        pid_path = os.path.join(data_dir, "neurokey_server.pid")
        with open(pid_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pid_path = None
    refresh_cache()
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()
    server = HTTPServer(("0.0.0.0", port), RealtimeHandler)
    print(f"NeuroKey server: http://0.0.0.0:{port}/  (GET: realtime, context; POST /ask: savol->javob). Ctrl+C yoki Stop_NeuroKey_Server.bat — to'xtatish.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.shutdown()
    if pid_path and os.path.isfile(pid_path):
        try:
            os.remove(pid_path)
        except Exception:
            pass


if __name__ == "__main__":
    main()
