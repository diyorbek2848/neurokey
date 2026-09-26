# -*- coding: utf-8 -*-
"""Proaktiv maslahatchi: ob-havo va vaqt bo'yicha kutilmagan ogohlantirishlar."""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

# Rain/snow WMO codes (juma_news_weather.WMO)
RAIN_SNOW_CODES = {51, 53, 55, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}


def _get_weather_for_place(place: str, lang: str = "ru") -> Optional[dict]:
    try:
        from juma_news_weather import geocode_place, get_weather
        g = geocode_place(place, lang=lang)
        if not g:
            return None
        data = get_weather(g["latitude"], g["longitude"], lang=lang)
        return {"place": place, "data": data, "geo": g}
    except Exception:
        return None


def _check_rain_advice(place: str, lang: str = "ru") -> Optional[str]:
    w = _get_weather_for_place(place, lang=lang)
    if not w:
        return None
    cur = (w.get("data") or {}).get("current") or {}
    code = int(cur.get("weather_code") or 0)
    if code in RAIN_SNOW_CODES:
        # XATOLIK TUZATILDI (2026-09-11): avval faqat ru/en bor edi — "uz"
        # rejimida ham bu ingliz tilida chiqib ketardi (NEUROKEY_UI_LANG=uz
        # bo'lsa ham). Endi uchinchi tilga alohida matn qo'shildi.
        if lang == "ru":
            return "Ожидается дождь или снег. Рекомендую взять зонт или одеться потеплее."
        if lang == "uz":
            return "Yomg'ir yoki qor kutilmoqda. Zontik olib chiqishni yoki issiqroq kiyinishni maslahat beraman."
        return "Rain or snow expected. Consider taking an umbrella or dressing warmer."
    hourly = (w.get("data") or {}).get("hourly") or {}
    precip_probs = hourly.get("precipitation_probability") or []
    if precip_probs:
        max_prob = max(precip_probs[:12]) if len(precip_probs) >= 12 else max(precip_probs)
        if max_prob and max_prob > 60:
            if lang == "ru":
                return f"В ближайшие часы вероятность осадков до {max_prob:.0f}%. Можешь взять зонт."
            if lang == "uz":
                return f"Keyingi bir necha soatda yomg'ir ehtimoli {max_prob:.0f}% gacha. Zontik olib chiqsang bo'ladi."
            return f"Chance of precipitation in the next hours up to {max_prob:.0f}%. Consider an umbrella."
    return None


def run_proactive_once(say_callback: Callable[[str], None], city: Optional[str] = None, lang: str = "ru") -> None:
    """Bir marta ob-havoni tekshirib, kerak bo'lsa ogohlantirish aytadi."""
    place = (city or os.getenv("NEUROKEY_CITY") or "Tashkent").strip()
    msg = _check_rain_advice(place, lang=lang)
    if msg:
        say_callback(msg)


def start_proactive_loop(
    say_callback: Callable[[str], None],
    city: Optional[str] = None,
    lang: str = "ru",
    interval_sec: int = 1800,
    delay_sec: int = 15,
) -> threading.Event:
    """Background: delay_sec dan keyin birinchi marta, keyin har interval_sec da tekshiradi. stop_event.set() bilan to'xtatish."""
    stop = threading.Event()

    def loop():
        time.sleep(delay_sec)
        while not stop.is_set():
            try:
                run_proactive_once(say_callback, city=city, lang=lang)
            except Exception:
                pass
            stop.wait(timeout=interval_sec)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return stop
