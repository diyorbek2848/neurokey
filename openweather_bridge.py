# -*- coding: utf-8 -*-
"""NeuroKey — OpenWeatherMap aniqroq ob-havo va 5 kunlik prognoz.

API kalit: OPENWEATHERMAP_KEY (.env)
Bepul: 1,000 ta/kun, bugungi + 5 kun prognoz

Buyruqlar:
    "Toshkentda ob-havo qanday"
    "Ertaga yomg'ir yog'adimi"
    "5 kunlik prognoz"
    "Samarqanddagi havo"
"""
import os, json, ssl, urllib.parse, urllib.request
from typing import Optional, Dict
from datetime import datetime

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

try:
    import config as C
    _KEY = (os.getenv("OPENWEATHERMAP_KEY") or os.getenv("OPENWEATHERMAP_API_KEY")
            or getattr(C, "OPENWEATHERMAP_KEY", "")).strip()
    _CITY = getattr(C, "NEUROKEY_CITY", "Tashkent") or "Tashkent"
except Exception:
    _KEY = os.getenv("OPENWEATHERMAP_KEY", "").strip()
    _CITY = "Tashkent"

_BASE = "https://api.openweathermap.org/data/2.5"

_TRIGGERS = [
    "ob-havo", "обхаво", "погода", "havo", "weather",
    "yomg'ir", "дождь", "rain", "qor", "снег", "snow",
    "temperature", "temp", "градус", "daraja", "issiq", "sovuq",
    "прогноз", "forecast", "prognoz",
]

_CONDITION_MAP = {
    "clear sky": "Toza osmon, quyoshli",
    "few clouds": "Oz bulutli",
    "scattered clouds": "Tarqoq bulutlar",
    "broken clouds": "Ko'p bulutli",
    "overcast clouds": "Bulutli",
    "light rain": "Yengil yomg'ir",
    "moderate rain": "O'rtacha yomg'ir",
    "heavy intensity rain": "Kuchli yomg'ir",
    "thunderstorm": "Momaqaldiroq",
    "snow": "Qor",
    "light snow": "Yengil qor",
    "mist": "Tuman",
    "fog": "Qalin tuman",
}


def is_available() -> bool:
    return bool(_KEY)


def is_weather_request(text: str) -> bool:
    low = text.lower()
    return any(t in low for t in _TRIGGERS)


def _fetch(endpoint: str, params: dict) -> Optional[dict]:
    params["appid"] = _KEY
    params["units"] = "metric"
    params["lang"] = "ru"
    url = f"{_BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10, context=_SSL_CTX) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def get_current(city: str) -> str:
    data = _fetch("weather", {"q": city})
    if not data:
        return f"{city} uchun ob-havo olinmadi."
    temp = data["main"]["temp"]
    feels = data["main"]["feels_like"]
    humidity = data["main"]["humidity"]
    desc = data["weather"][0]["description"]
    wind = data["wind"]["speed"]
    loc = data.get("name", city)
    uz_desc = _CONDITION_MAP.get(data["weather"][0].get("main", "").lower(), desc)
    return (f"{loc}: {temp:.0f}°C (his qilish {feels:.0f}°C). "
            f"{uz_desc}. Shamol {wind:.0f} m/s. Namlik {humidity}%.")


def get_forecast(city: str, days: int = 3) -> str:
    data = _fetch("forecast", {"q": city, "cnt": days * 8})
    if not data:
        return f"{city} uchun prognoz olinmadi."
    # Kunlik o'rtachani hisoblash
    day_data: Dict[str, list] = {}
    for item in data.get("list", []):
        dt = datetime.fromtimestamp(item["dt"])
        day = dt.strftime("%d.%m (%A)")
        if day not in day_data:
            day_data[day] = []
        day_data[day].append(item)
    lines = []
    for day, items in list(day_data.items())[:days]:
        temps = [x["main"]["temp"] for x in items]
        descs = [x["weather"][0]["description"] for x in items]
        tmin, tmax = min(temps), max(temps)
        main_desc = max(set(descs), key=descs.count)
        uz_desc = _CONDITION_MAP.get(main_desc, main_desc)
        lines.append(f"{day}: {tmin:.0f}–{tmax:.0f}°C, {uz_desc}")
    loc = data.get("city", {}).get("name", city)
    return f"{loc} {days} kunlik prognoz:\n" + "\n".join(lines)


def _extract_city(text: str) -> str:
    """Matndan shahar nomini ajratib olish."""
    import re
    city_patterns = [
        r"(?:в|в городе|in|da|дa)\s+([а-яёА-ЯЁa-zA-Zа-яa-z\s]{3,20})(?:\s|$|обхаво|погода|weather|ob-havo)",
        r"([А-ЯЁа-яё]{4,}(?:да|дagi)?)\s*(?:обхаво|погода|ob-havo)",
    ]
    for pat in city_patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return _CITY


def handle(text: str, tts_say=None) -> Optional[str]:
    if not is_weather_request(text):
        return None

    def say(m):
        if tts_say:
            try: tts_say(m)
            except Exception: pass

    low = text.lower()
    city = _extract_city(text)
    is_forecast = any(w in low for w in ["прогноз", "forecast", "prognoz", "5 kun", "3 kun", "ertaga", "завтра"])

    # OpenWeatherMap (kalit bo'lsa)
    if is_available():
        if is_forecast:
            days = 5 if "5" in low else 3
            result = get_forecast(city, days)
        else:
            result = get_current(city)
        say(result)
        return result

    # Bepul fallback: Open-Meteo (API kalit shart emas)
    try:
        from juma_news_weather import weather_by_name
        result = weather_by_name(city)
        if result:
            say(result)
            return result
    except Exception:
        pass

    # SerpAPI orqali Google qidiruv (SerpAPI ulangan bo'lsa)
    try:
        from web_tools import serpapi_search
        results = serpapi_search(f"погода {city} сегодня", num=3)
        if results:
            snippet = results[0].get("snippet", "")
            if snippet:
                say(snippet)
                return snippet
    except Exception:
        pass

    return f"{city} ob-havosi olinmadi."
