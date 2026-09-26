# -*- coding: utf-8 -*-
"""
web_search_rag.py — API'siz Oflayn Qidiruv (Local RAG)

Bu skript DuckDuckGo Lite (yoki boshqa bepul qidiruv tizimi) orqali
API kalitisiz (bepul) internetdan matnlarni "scrape" qilib oladi va 
oflayn LLM (Llama 3 / Phi) uchun kontekst sifatida beradi.
"""

import urllib.request
import urllib.parse
from html.parser import HTMLParser
import ssl
import re

def fetch_duckduckgo_lite(query: str, num_results: int = 3) -> list:
    """DuckDuckGo Lite orqali qidiradi va API'siz natijalarni oladi."""
    try:
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({'q': query}).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'uz-UZ,uz;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            html = response.read().decode('utf-8')
            
            # Use basic regex to parse DDG Lite HTML (more robust than HTMLParser for this specific ugly HTML)
            results = []
            
            # Find snippets
            snippets = re.findall(r'<td class=\'result-snippet\'[^>]*>(.*?)</td>', html, re.DOTALL | re.IGNORECASE)
            # Remove HTML tags from snippets
            clean_snippets = [re.sub(r'<[^>]+>', '', s).strip() for s in snippets]
            
            for snip in clean_snippets[:num_results]:
                if snip:
                    results.append({"snippet": snip})
            
            return results

    except Exception as e:
        print(f"[web_search_rag] Xato: {e}")
        return []

def get_fresh_context(query: str) -> str:
    """LLM ga berish uchun qidiruv natijalarini formatlaydi."""
    results = fetch_duckduckgo_lite(query)
    if not results:
        return ""
        
    context = "INTERNETDAN YULIB OLINGAN HAQIQIY VAQT MA'LUMOTLARI (Faktlar):\n"
    for idx, r in enumerate(results):
        context += f"Fakt {idx+1}: {r['snippet']}\n"
    
    return context.strip()

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print("Test qidiruv: 'Real Madrid match result yesterday'")
    print(get_fresh_context("Real Madrid match result yesterday"))
