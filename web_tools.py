# -*- coding: utf-8 -*-
"""Web tools for NeuroKey.

Two-path strategy:
1) If SERPAPI_API_KEY is available -> use SerpAPI (Google results)
2) Otherwise -> lightweight fallbacks (DuckDuckGo Instant Answer + Wikipedia)

This module is intentionally dependency-light (requests only).
"""

from __future__ import annotations

import os
import re
import json
import urllib.parse
from typing import List, Dict, Optional

import requests


def _get_serpapi_key() -> str:
    return (os.getenv("SERPAPI_API_KEY") or "").strip()


def serpapi_search(
    query: str,
    *,
    num: int = 6,
    hl: str = "en",
    gl: str = "us",
    use_last_24h: bool = False,
) -> List[Dict[str, str]]:
    """Search with SerpAPI. use_last_24h=True => tbs=qdr:d (har kungi eng yangi ma'lumot)."""
    key = _get_serpapi_key()
    if not key:
        return []
    try:
        import config as _cfg
        num = int(getattr(_cfg, "SERPAPI_NUM_RESULTS", 6) or 6)
        timeout_sec = int(getattr(_cfg, "SERPAPI_TIMEOUT_SEC", 10) or 10)
        if not gl or gl == "uz":
            gl = getattr(_cfg, "WEB_GL", "us") or "us"
    except Exception:
        timeout_sec = 10
        num = int(num)
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": (query or "").strip()[:500],
        "api_key": key,
        "num": min(num, 10),
        "hl": hl,
        "gl": gl,
    }
    if use_last_24h:
        params["tbs"] = "qdr:d"  # oxirgi 24 soat
    data = None
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, timeout=timeout_sec)
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, requests.Timeout, ValueError, KeyError):
            if attempt == 1:
                return []
    if not data:
        return []
    out = []
    for item in (data.get("organic_results") or [])[:num]:
        out.append({
            "title": str(item.get("title") or ""),
            "snippet": str(item.get("snippet") or ""),
            "link": str(item.get("link") or ""),
        })
    return out


def serpapi_image_search(query: str, *, num: int = 6, hl: str = "ru") -> List[Dict[str, str]]:
    """SerpAPI Google Images. Returns list of {title, link, thumbnail}. Retry 1 marta."""
    key = _get_serpapi_key()
    if not key:
        return []
    timeout_sec = 14
    try:
        import config as _cfg
        timeout_sec = int(getattr(_cfg, "SERPAPI_TIMEOUT_SEC", 14) or 14)
    except Exception:
        pass
    for attempt in range(2):
        try:
            url = "https://serpapi.com/search.json"
            params = {
                "engine": "google_images",
                "q": (query or "").strip()[:200],
                "api_key": key,
                "num": min(int(num), 10),
                "hl": hl,
            }
            r = requests.get(url, params=params, timeout=timeout_sec)
            r.raise_for_status()
            data = r.json()
            out = []
            for item in (data.get("images_results") or [])[:num]:
                out.append({
                    "title": str(item.get("title") or ""),
                    "link": str(item.get("link") or item.get("original") or ""),
                    "thumbnail": str(item.get("thumbnail") or ""),
                })
            return out
        except Exception:
            if attempt == 1:
                return []
    return []


def needs_image(text: str) -> bool:
    """Foydalanuvchi rasm/foto qidirishni xohlaydimi."""
    if not (text or "").strip():
        return False
    t = (text or "").lower().strip()
    triggers = [
        "фото", "фотографи", "картинк", "изображени", "photo", "image", "picture", "rasm", "surat",
        "найди фото", "найди картинку", "покажи фото", "find photo", "search image",
        "интернетдан топ", "интернетдан топиб", "в интернете найди", "в интернете фото",
        "его фото", "её фото", "её картинку", "фото в интернете", "photo on internet",
    ]
    return any(x in t for x in triggers)


def duckduckgo_instant(query: str) -> Optional[str]:
    """DuckDuckGo Instant Answer (no key). Returns a short abstract if available."""
    try:
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        })
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        abstract = (data.get("AbstractText") or "").strip()
        if abstract:
            return abstract
        heading = (data.get("Heading") or "").strip()
        related = data.get("RelatedTopics") or []
        if related and isinstance(related, list):
            # pick first text
            for t in related:
                if isinstance(t, dict) and (t.get("Text") or "").strip():
                    return f"{heading}: {t.get('Text').strip()}" if heading else t.get("Text").strip()
        return None
    except Exception:
        return None


def wikipedia_summary(query: str, *, lang: str = "ru") -> Optional[str]:
    """Wikipedia REST summary — to'g'ridan-to'g'ri sahifa nomi bilan."""
    try:
        title = query.strip().replace(" ", "_")
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
        r = requests.get(url, timeout=10, headers={"User-Agent": "NeuroKey/1.0 (https://juma.ai)"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        extract = (data.get("extract") or "").strip()
        return extract or None
    except Exception:
        return None


def wikipedia_search(query: str, *, lang: str = "ru", limit: int = 5) -> List[Dict[str, str]]:
    """Wikipedia qidiruv — MediaWiki API. Dunyodagi eng katta ma'lumotlar bazasi."""
    q = (query or "").strip()[:200]
    if not q:
        return []
    try:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": q,
            "srlimit": min(limit, 10),
            "format": "json",
            "origin": "*",
        }
        r = requests.get(url, params=params, timeout=12, headers={"User-Agent": "NeuroKey/1.0 (https://juma.ai)"})
        r.raise_for_status()
        data = r.json()
        results = []
        for item in (data.get("query", {}).get("search") or [])[:limit]:
            title = (item.get("title") or "").strip()
            snippet = (item.get("snippet") or "").replace("<span class=\"searchmatch\">", "").replace("</span>", "").strip()
            if title:
                results.append({"title": title, "snippet": snippet})
        return results
    except Exception:
        return []


def wikipedia_search_and_summary(query: str, *, lang: str = "ru", max_chars: int = 4000) -> Optional[str]:
    """
    Wikipedia qidiruv + eng yaxshi natija summary.
    Dunyodagi eng katta ma'lumotlar bazasi — API kalitsiz, bepul.
    """
    q = (query or "").strip()
    if not q or len(q) < 2:
        return None
    results = wikipedia_search(q, lang=lang, limit=3)
    if not results:
        direct = wikipedia_summary(q, lang=lang)
        return ("WIKIPEDIA:\n\n" + direct) if direct else None
    out_parts = []
    for r in results[:3]:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        summary = wikipedia_summary(title, lang=lang)
        if summary:
            text = f"{title}:\n{summary}"
        elif snippet:
            text = f"{title}: {snippet}"
        else:
            continue
        out_parts.append(text)
        if sum(len(p) for p in out_parts) >= max_chars:
            break
    if not out_parts:
        direct = wikipedia_summary(q, lang=lang)
        return ("WIKIPEDIA:\n\n" + direct) if direct else None
    return "WIKIPEDIA (dunyodagi eng katta ma'lumotlar bazasi):\n\n" + "\n\n---\n\n".join(out_parts)[:max_chars]


def critical_need_web(text: str) -> bool:
    """Intelligent Search: faqat critical_need bo'lganda web qidiruv. Oddiy savollar kesh + Organs.

    BUG FIX (o'lchandi, 2026-08-18 — real test: 5 ta "joriy ma'lumot"
    savolidan aksariyati rad javobi berdi): kalit so'zlar ro'yxati FAQAT
    rus/ingliz tilida edi — o'zbekcha (lotin yozuvi) so'zlar UMUMAN yo'q edi
    ("ob-havo", "bitkoin/bitcoin", "kurs", "necha so'm", "yangilik/voqea").
    Natijada masalan "Hozir Toshkentda ob-havo qanday?" hech qanday kalit
    so'zga to'g'ri kelmasdi va `_use_web` HECH QACHON True bo'lmasdi — LLM
    web'siz, umumiy bilimidan javob berishga majbur bo'lardi (haqiqiy joriy
    ma'lumot yo'qligi uchun tabiiy tarzda rad javobi/umumiy gap chiqarardi).
    Bu — bir nechta shu turdagi bugning yana biri (matchai naqsh: klassifikator
    faqat bitta til/alifboni qamrab olgan, "доллар" (kirill) va "dollar"
    (lotin) alohida-alohida yozilishi kerak edi, chunki substring taqqoslash
    alifbo farqini avtomatik tushunmaydi)."""
    if not (text or "").strip():
        return False
    t = (text or "").lower().strip()
    if len(t) < 20:
        return False
    critical = [
        "погода", "weather", "температура", "ob-havo", "ob havo", "obhavo", "harorat",
        "новости", "news", "что в новостях", "world news", "yangilik", "yangilikl",
        "voqea", "xabar",
        "курс", "доллар", "dollar", "евро", "euro", "exchange rate", "kurs",
        "bitcoin", "биткоин", "bitkoin", "kripto", "crypto", "necha so'm", "necha pul",
        "narxi qancha", "qancha turadi", "valyuta",
        "latest", "сегодня", "сейчас", "today", "now", "актуальн",
        "hozir", "hozirgi", "bugun", "bugungi", "so'nggi", "songgi", "oxirgi", "yaqinda",
        "найди в интернете", "find on internet", "search for", "internetdan top", "internetda top",
    ]
    return any(x in t for x in critical)


def needs_web(text: str) -> bool:
    """Babata (Swallowed Star): Har joyda ma'lumotlarni qidirib topish. Internetning har qanday burchagidan — global qidiruv."""
    if not (text or "").strip():
        return False
    t = (text or "").lower().strip()
    # Короткая команда (открой, закрой) — web не нужен
    if len(t) < 25 and any(x in t for x in ["открой", "закрой", "open", "close"]):
        return False
    # Babata: deyarli har narsa uchun web — dasturlash, psixologiya, koinot, past darajadagi odamlar xatolari ham
    triggers = [
        "погода", "погоду", "weather", "курс", "доллар", "доллара", "dollar", "евро", "euro",
        "новости", "новост", "news", "latest", "сегодня", "сейчас", "today", "now", "актуальн",
        "какой курс", "сколько стоит", "температура", "temperature", "что с погодой", "курс валют",
        "exchange rate", "что в новостях",
        # O'zbekcha (lotin) — bug fix, qarang critical_need_web() izohi
        "ob-havo", "ob havo", "obhavo", "harorat", "kurs", "necha so'm", "necha pul",
        "bitcoin", "bitkoin", "kripto", "narxi qancha", "qancha turadi",
        "yangilik", "yangilikl", "voqea", "xabar", "hozir", "hozirgi", "bugun", "bugungi",
        "so'nggi", "songgi", "oxirgi", "yaqinda",
        "кино", "фильм", "movie", "film", "актёр", "actor", "режиссёр", "director",
        "что такое", "кто такой", "какой", "найди", "find", "search", "поиск", "топ",
        "найди в интернете", "find on internet",
        "информация о", "information about", "биография", "biography", "расскажи о", "tell me about",
        "что это", "что за", "когда", "где", "почему", "when", "where", "why", "сколько",
        "последние", "последняя", "последний", "latest", "новый", "new", "текущ",
        "предмет", "вещь", "thing", "фото", "картинк", "photo", "image",
        "справочник", "reference", "данные", "data", "факт", "fact",
        "programming", "code", "github", "scientific", "psychology",
        "cosmos", "universe", "law", "rule", "explain",
    ]
    if any(x in t for x in triggers):
        return True
    # Savol belgisi va uzunroq so‘rov — deyarli hamma narsa uchun web
    if "?" in t and len(t) > 8:
        return True
    if re.search(r"\b(кто|что|какой|какая|какое|как|где|когда|почему|сколько)\b", t) and len(t) > 10:
        return True
    if re.search(r"\b(who|what|which|how|where|when|why)\b", t) and len(t) > 10:
        return True
    # 20+ belgi — ehtimol faktik savol, qidiruv qilamiz
    if len(t) > 20:
        return True
    return False


def _wants_fresh(query_lower: str) -> bool:
    """Savol oxirgi kun/soat yangiligini xohlaydimi."""
    fresh = (
        "latest", "today", "now", "current", "recent", "сегодня", "сейчас", "последн", "актуальн",
        "новост", "news", "last 24", "past day", "daily",
    )
    return any(x in query_lower for x in fresh)


def _github_raw_if_url(q: str) -> str:
    """Agar so'rovda GitHub URL bo'lsa — raw kodni o'qib qo'shamiz (Internet as Brain)."""
    m = re.search(r"https?://(?:www\.)?github\.com/[^\s]+", q)
    if not m:
        return ""
    try:
        from babata_core import github_raw_fetch
        ok, text = github_raw_fetch(m.group(0), timeout_sec=10)
        if ok and text:
            return "GITHUB RAW (on-the-fly):\n" + text[:8000]
    except Exception:
        pass
    return ""


def is_factual_query(q: str) -> bool:
    """Faktik savol — Wikipedia eng yaxshi (dunyodagi eng katta baza)."""
    t = (q or "").lower().strip()
    factual = [
        "что такое", "кто такой", "что за", "что это", "кто это", "какой", "какая", "какое",
        "what is", "who is", "what are", "who are", "define", "definition",
        "расскажи о", "tell me about", "информация о", "information about",
        "биография", "biography", "история", "history", "nima", "kim", "qanday",
    ]
    return any(x in t for x in factual) or (len(t) > 15 and "?" in t)


def web_context(query: str, *, prefer_lang: str = "ru", use_last_24h: Optional[bool] = None) -> str:
    """Babata: Har joyda ma'lumot — Wikipedia (eng katta baza), Google, DuckDuckGo, GitHub. Muammosiz qidirib topish."""
    q = (query or "").strip()
    if not q:
        return ""
    gh = _github_raw_if_url(q)
    q_lower = q.lower()
    if use_last_24h is None:
        try:
            import config as _cfg
            use_last_24h = getattr(_cfg, "WEB_LAST_24H", True) or _wants_fresh(q_lower)
        except Exception:
            use_last_24h = _wants_fresh(q_lower)

    # 0) Wikipedia FIRST — dunyodagi eng katta ma'lumotlar bazasi, API kalitsiz
    if is_factual_query(q) and not _wants_fresh(q_lower):
        wiki = wikipedia_search_and_summary(q, lang=("ru" if prefer_lang == "ru" else "en"))
        if wiki and len(wiki) > 100:
            if gh:
                return gh + "\n\n" + wiki
            return wiki

    # 1) SerpAPI if available (tez + aniq: 6 ta natija, 24h agar kerak)
    key = _get_serpapi_key()
    if key:
        try:
            hl = "ru" if prefer_lang == "ru" else "en"
            gl = "us"
            try:
                import config as _cfg
                gl = (getattr(_cfg, "WEB_GL", None) or "us").strip() or "us"
            except Exception:
                pass
            results = serpapi_search(q, num=8, hl=hl, gl=gl, use_last_24h=use_last_24h)
            if results:
                lines = []
                for i, it in enumerate(results, 1):
                    title = (it.get("title") or "").strip()
                    snip = (it.get("snippet") or "").strip()
                    link = (it.get("link") or "").strip()
                    if len(snip) > 280:
                        snip = snip[:280] + "…"
                    lines.append(f"{i}) {title} — {snip} ({link})")
                out = "BABATA GLOBAL SEARCH (Google, latest):\n" + "\n".join(lines)
                if gh:
                    out = gh + "\n\n" + out
                return out
        except Exception as e:
            err_msg = str(e)[:200]
            try:
                from web_search_rag import get_fresh_context
                rag_res = get_fresh_context(q)
                if rag_res:
                    return rag_res
            except Exception:
                pass
            return f"WEB SEARCH ERROR: {err_msg}"

    # 2) Fallbacks without key
    if gh:
        return gh
    try:
        from web_search_rag import get_fresh_context
        rag_res = get_fresh_context(q)
        if rag_res:
            return rag_res
    except Exception:
        pass
    wiki = wikipedia_summary(q, lang=("ru" if prefer_lang == "ru" else "en"))
    if wiki:
        return "WEB (Wikipedia):\n" + wiki
    return ""
