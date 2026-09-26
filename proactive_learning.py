import requests
import logging
import json
import os
from typing import Optional, List
from datetime import datetime

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

log = logging.getLogger(__name__)

# O'rganilgan ma'lumotlarni saqlash uchun baza (World Model ning bir qismi)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROACTIVE_KNOWLEDGE_PATH = os.path.join(_BASE_DIR, "data", "proactive_knowledge.json")

def _load_knowledge() -> list:
    if os.path.exists(_PROACTIVE_KNOWLEDGE_PATH):
        try:
            with open(_PROACTIVE_KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_knowledge(data: list):
    try:
        os.makedirs(os.path.dirname(_PROACTIVE_KNOWLEDGE_PATH), exist_ok=True)
        with open(_PROACTIVE_KNOWLEDGE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"[Proactive] Bilimni saqlashda xato: {e}")

def _safe_search_duckduckgo(query: str) -> List[str]:
    """DuckDuckGo Lite versiyasi orqali yengil va maxfiy qidiruv."""
    if not BeautifulSoup:
        log.error("[Proactive] BeautifulSoup o'rnatilmagan. Qidiruv bekor qilindi.")
        return []
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    url = "https://lite.duckduckgo.com/lite/"
    payload = {'q': query}
    
    try:
        log.info(f"[Proactive] Tarmoqdan izlanmoqda: {query}")
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        
        # DDG Lite natijalarini parsing qilish
        for tr in soup.find_all('tr'):
            td = tr.find('td', class_='result-snippet')
            if td:
                results.append(td.text.strip())
                
        return results[:3] # Eng muhim 3 ta xulosani qaytaramiz
    except Exception as e:
        log.error(f"[Proactive] Internetdan qidirishda xatolik: {e}")
        return []

def fetch_and_learn(topic: str) -> bool:
    """Mavzu bo'yicha ma'lumot qidiradi va uni lokal xotiraga xulosa qilib yozadi."""
    log.info(f"[Proactive] '{topic}' mavzusi bo'yicha mustaqil o'rganish boshlandi...")
    
    snippets = _safe_search_duckduckgo(topic)
    if not snippets:
        log.info(f"[Proactive] '{topic}' bo'yicha yangi ma'lumot topilmadi.")
        return False
        
    # Haqiqiy LLM orqali xulosa qilish o'rniga hozircha to'g'ridan-to'g'ri saqlaymiz.
    # (LLM_router orqali xulosalash bu yerga ulanishi mumkin)
    combined_insight = " ".join(snippets)
    
    knowledge = _load_knowledge()
    
    new_fact = {
        "topic": topic,
        "date_learned": datetime.now().isoformat(),
        "insight": combined_insight,
        "used_in_conversation": False
    }
    
    knowledge.append(new_fact)
    _save_knowledge(knowledge)
    
    log.info(f"[Proactive] Yangi bilim o'zlashtirildi: {topic}")
    return True

def get_proactive_conversation_starter() -> Optional[str]:
    """Ertalab yoki yangi suhbat boshlanganda foydalanuvchiga qiziq mavzu taklif qilish."""
    knowledge = _load_knowledge()
    for fact in reversed(knowledge): # Eng yangilaridan boshlaymiz
        if not fact.get("used_in_conversation", False):
            fact["used_in_conversation"] = True
            _save_knowledge(knowledge)
            
            topic = fact["topic"]
            insight = fact["insight"][:150] + "..." # Qisqa pre-view
            
            starter = (f"[Proaktiv O'rganish] Kecha men '{topic}' haqida o'yladim "
                       f"va internetdan shuni topdim: '{insight}'. Bu haqida fikringiz qanday?")
            return starter
            
    return None
