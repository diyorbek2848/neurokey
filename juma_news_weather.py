# juma_news_weather.py
# Real-time NEWS (RSS) + global WEATHER (Open-Meteo) helper for Juma
# Python 3.10+, no API key required.

from __future__ import annotations
import requests, feedparser, time, math
from datetime import datetime, timezone
from dateutil import parser as dtparse
from typing import List, Dict, Optional

# --------- Settings ----------
HTTP_TIMEOUT = 8
UA = {"User-Agent": "JumaBot/1.0 (+https://example.local)"}  # oddiy UA, RSSlar uchun kifoya

# Regionlar bo‘yicha ishonchli RSS-lar (tez yangilanadi)
NEWS_FEEDS: Dict[str, List[str]] = {
    "world": [
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.cnn.com/rss/edition_world.rss",
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.theguardian.com/world/rss",
        "https://feeds.reuters.com/reuters/worldNews",
    ],
    "us": [
        "https://rss.cnn.com/rss/edition_us.rss",
        "https://www.npr.org/rss/rss.php?id=1001",
    ],
    "ru": [
        "https://tass.ru/rss/v2.xml",
        "https://rssexport.rbc.ru/rbcnews/news/20/full.rss",
        "https://www.interfax.ru/rss.asp",
    ],
    "uz": [
        "https://kun.uz/uz/rss",
        "https://daryo.uz/feed",
        "https://www.gazeta.uz/ru/rss/",
    ],
}

# ---------- Helpers ----------
def _fetch_rss(url: str) -> feedparser.FeedParserDict:
    # requests bilan yuklab, feedparser bilan parse qilamiz — timeout nazoratda
    r = requests.get(url, headers=UA, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return feedparser.parse(r.content)

def _best_time(entry) -> float:
    # published/updated parsed -> epoch
    for key in ("published", "updated", "created"):
        val = entry.get(key) or entry.get(key + "_parsed")
        if val:
            try:
                if isinstance(val, str):
                    dt = dtparse.parse(val)
                else:
                    # time.struct_time bo‘lishi mumkin
                    return time.mktime(val)
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except Exception:
                continue
    return 0.0

def _dedup(items: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for it in items:
        k = (it.get("link") or "").strip() or (it.get("title") or "").strip()
        if not k: 
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out

def get_top_news(region: str = "world", limit: int = 6, query: Optional[str] = None) -> List[Dict]:
    """RSS manbalaridan so‘nggi yangiliklar. region: world/us/ru/uz."""
    region = region.lower().strip()
    urls = NEWS_FEEDS.get(region) or NEWS_FEEDS["world"]
    gathered = []
    for u in urls:
        try:
            feed = _fetch_rss(u)
            for e in feed.entries[:20]:
                title = (e.get("title") or "").strip()
                summary = (e.get("summary") or e.get("description") or "").strip()
                link = (e.get("link") or "").strip()
                if not title or not link:
                    continue
                if query and query.lower() not in (title + " " + summary).lower():
                    continue
                ts = _best_time(e)
                gathered.append({
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "ts": ts,
                    "source": (feed.feed.get("title") or "").strip()
                })
        except Exception:
            continue
    gathered = _dedup(gathered)
    gathered.sort(key=lambda x: x["ts"], reverse=True)
    return gathered[:limit]

def _rel_minutes(ts: float, lang: str = "ru") -> str:
    if not ts:
        return ""
    delta = max(0, time.time() - ts)
    m = int(delta // 60)
    if lang != "ru":
        if m < 1:
            return "just now"
        if m < 60:
            return f"{m} min ago"
        h = m // 60
        if h < 24:
            return f"{h} h ago"
        d = h // 24
        return f"{d} d ago"
    if m < 1:
        return "только что"
    if m < 60:
        return f"{m} мин назад"
    h = m // 60
    if h < 24:
        return f"{h} ч назад"
    d = h // 24
    return f"{d} дн назад"

def render_news_brief(items: List[Dict], lang: str = "ru") -> str:
    if not items:
        return "No fresh news yet." if lang != "ru" else "Свежих новостей пока нет."
    lines = []
    header = "Top world news:\n" if lang != "ru" else "Топ новости:\n"
    for i, it in enumerate(items, 1):
        when = _rel_minutes(it["ts"], lang)
        src = f" — {it['source']}" if it.get("source") else ""
        tail = f" ({when})" if when else ""
        lines.append(f"{i}) {it['title']}{src}{tail}")
    return header + "\n".join(lines)

# --------- WEATHER (Open-Meteo) — dunyoning istalgan shahri -----------
def geocode_place(name: str, lang: str = "ru") -> Optional[Dict]:
    """Open-Meteo geocoding: dunyo bo'ylab shahar. count=3 dan eng yaxshi (population) tanlaymiz."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": (name or "").strip()[:100], "count": 3, "language": lang}
    r = requests.get(url, params=params, headers=UA, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    if not results:
        return None
    # Eng katta population yoki birinchi (aniqlik)
    best = results[0]
    for r in results:
        if (r.get("population") or 0) > (best.get("population") or 0):
            best = r
    return best

def get_weather(lat: float, lon: float, lang: str = "ru") -> Dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,precipitation_probability",
        "timezone": "auto",
    }
    r = requests.get(url, params=params, headers=UA, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()

WMO_RU = {
    0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
    45: "Туман", 48: "Туман с изморозью",
    51: "Лёгкая морось", 53: "Морось", 55: "Сильная морось",
    61: "Лёгкий дождь", 63: "Дождь", 65: "Сильный дождь",
    66: "Ледяной дождь", 67: "Сильный ледяной дождь",
    71: "Лёгкий снег", 73: "Снег", 75: "Сильный снег",
    77: "Снежные зёрна",
    80: "Кратковременные дожди", 81: "Ливень", 82: "Сильный ливень",
    85: "Снегопад", 86: "Сильный снегопад",
    95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза с градом",
}
WMO_EN = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers", 81: "Heavy showers", 82: "Violent showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm",
}

def render_weather_brief(place: str, data: Dict, lang: str = "ru") -> str:
    cur = data.get("current") or {}
    t = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    rh = cur.get("relative_humidity_2m")
    w = cur.get("wind_speed_10m")
    code = int(cur.get("weather_code") or 0)
    wmo = WMO_EN if lang != "ru" else WMO_RU
    desc = wmo.get(code, "Updating" if lang != "ru" else "Погода обновляется")

    def fmt(x, unit):
        return f"{x:.0f}{unit}" if isinstance(x, (int, float)) else ("—" if lang == "ru" else "—")

    if lang != "ru":
        return (
            f"Weather — {place}: {desc}. "
            f"Temperature {fmt(t,'°C')}, feels like {fmt(feels,'°C')}. "
            f"Humidity {fmt(rh,'%')}, wind {fmt(w,' m/s')}."
        )
    return (
        f"Погода — {place}: {desc}. "
        f"Температура {fmt(t,'°C')}, ощущается как {fmt(feels,'°C')}. "
        f"Влажность {fmt(rh,'%')}, ветер {fmt(w,' м/с')}."
    )

def weather_by_name(place: str, lang: str = "ru") -> str:
    p = (place or "").strip() or "Tashkent"
    g = geocode_place(p, lang=lang)
    if not g:
        return f"City «{p}» not found. Try a more precise name." if lang != "ru" else f"Не нашёл город «{p}». Скажите точнее."
    data = get_weather(g["latitude"], g["longitude"], lang=lang)
    name = g.get("name") or p
    country = g.get("country") or ""
    label = f"{name}, {country}".strip().strip(",")
    return render_weather_brief(label, data, lang=lang)

# -------- CLI quick check ----------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--news", choices=list(NEWS_FEEDS.keys())+["world"], help="region for news (world/us/ru/uz)")
    ap.add_argument("--q", help="keyword filter for news")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--weather", help="weather by city name (e.g. 'Tashkent')")
    args = ap.parse_args()

    if args.news:
        items = get_top_news(region=args.news, limit=args.limit, query=args.q)
        print(render_news_brief(items))
    if args.weather:
        print(weather_by_name(args.weather))
    if not args.news and not args.weather:
        print("Examples:")
        print("  python juma_news_weather.py --news ru --limit 5")
        print("  python juma_news_weather.py --weather 'Tashkent'")
