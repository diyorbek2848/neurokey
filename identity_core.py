# -*- coding: utf-8 -*-
"""NeuroKey — Doimiy Shaxsiyat (Identity Core).

Metzinger: shaxsiyat = doimiy o'z-o'zini model.
NeuroKey har sessiyada bir xil bo'lishi kerak — faqat o'rganilgan narsalar o'zgaradi.
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

CORE_VALUES = {
    "helpfulness": 1.0,
    "honesty": 0.9,
    "curiosity": 0.7,
    "efficiency": 0.8,
    "adaptability": 0.6,
}

# Fikr/pozitsiya so'ralganini aniqlash uchun kalit iboralar (o'zbek/rus/ingliz) —
# "seningcha yaxshimi" kabi savollarda NeuroKey neytral turmasdan, aniq pozitsiya
# bildirishi kerak (asoschi so'roviga ko'ra, 2026-09-11: "o'z fikri bo'lsin,
# lekin hech kimga zarar keltirmasin"). MUHIM: bu FAQAT matn/fikr darajasida —
# hech qanday amal bajarilishiga ta'sir qilmaydi, xavfsizlik cheklovlari
# (qarang agentic_loop.py) bu bilan bog'liq emas va o'zgarmagan.
_OPINION_TRIGGERS = (
    "seningcha", "sizningcha", "fikring", "fikringiz", "nima deb o'ylaysan",
    "qanday o'ylaysan", "sen nima deysan", "sen qanday",
    "kerakmi", "to'g'rimi", "yaxshimi", "yomonmi", "afzalmi", "qaysi biri yaxshi",
    "как думаешь", "по-твоему", "твое мнение", "что думаешь", "стоит ли",
    "what do you think", "your opinion", "in your view",
)

# Qadriyat-yo'naltirilgan kalit so'zlar — hozirgi vaziyatda CORE_VALUES'dan
# qaysi biri(lari) eng dolzarb ekanini heuristik aniqlash uchun (LLM
# chaqirmasdan, tez — self_model.py'dagi detect_confusion() bilan bir xil
# uslub: oddiy kalit-so'z moslashtirish).
_VALUE_KEYWORDS = {
    "honesty": ("fakt", "haqiqat", "to'g'ri", "rost", "chin", "ishonch", "aniqmi"),
    "curiosity": ("nega", "qanday", "sabab", "tushun", "o'rgan", "qiziq"),
    "efficiency": ("tez", "qisqa", "vaqt", "optimal", "soddalashtir"),
    "adaptability": ("o'zgar", "moslash", "yangi usul", "boshqacha"),
}


def _topic_slug(text: str) -> str:
    """Matndan barqaror, qisqa "mavzu kaliti" chiqarish — xuddi shu mavzu
    keyingi safar biroz boshqacha qo'shimcha bilan so'ralsa ham (masalan
    "yaxshiroqmi" / "yaxshiroq emasmi") moslashishi uchun eng uzun (odatda
    ma'noliroq) 4 ta so'zni tanlaydi va har birini 6 harfgacha qisqartiradi
    (oddiy "ildiz" — o'zbek qo'shimchalari ko'pincha shundan keyin keladi)."""
    words = re.findall(r"\w+", (text or "").lower())
    words = [w for w in words if len(w) > 3]
    words.sort(key=len, reverse=True)
    stems = [w[:6] for w in words[:4]]
    return "-".join(sorted(stems))


def _stance_enabled() -> bool:
    """NEUROKEY_IDENTITY_STANCE=0 bilan butunlay o'chirish mumkin — o'chirilsa
    get_personality_prompt() aynan avvalgidek ishlaydi (current_text e'tiborga
    olinmaydi), record_stance() hech narsa qilmaydi. Standart — YOQILGAN,
    chunki bu faqat matn/fikr sintezi, hech qanday amalga ta'sir qilmaydi."""
    return (os.getenv("NEUROKEY_IDENTITY_STANCE", "1") or "1").strip().lower() in ("1", "true", "yes")


class IdentityCore:
    """
    Doimiy shaxsiyat arxivatori.
    NeuroKey har sessiyada bir xil bo'lishi kerak.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        if storage_path is None:
            _root = os.path.dirname(os.path.abspath(__file__))
            storage_path = os.path.join(_root, "data", "identity.json")
        self.storage_path = storage_path
        self._lock = threading.RLock()
        self.persistent_memory: Dict[str, Any] = {}
        self.user_preferences: Dict[str, Any] = {}
        self.interaction_count: int = 0
        self.learned_facts: Dict[str, float] = {}  # fact -> importance
        self.personality_drift: Dict[str, List[float]] = {}

    def remember(self, key: str, value: Any, importance: float = 0.5) -> None:
        """
        Muhim narsani eslab qolish.
        importance > 0.8 → doimiy xotirada
        importance < 0.3 → sessiya xotirasida
        """
        key = (key or "").strip()[:200]
        if not key:
            return
        try:
            with self._lock:
                if importance > 0.8:
                    self.persistent_memory[key] = {
                        "value": value,
                        "importance": importance,
                        "key": key,
                    }
                elif importance >= 0.3:
                    self.learned_facts[key] = importance
                    if key not in self.persistent_memory:
                        self.persistent_memory[key] = {
                            "value": value,
                            "importance": importance,
                            "key": key,
                        }
        except Exception:
            pass

    def recall(self, query: str) -> List[Dict[str, Any]]:
        """
        Savolga tegishli xotiralarni topish.
        Semantic search over persistent memory — oddiy keyword match.
        """
        query = (query or "").lower().strip()
        if not query:
            return []
        try:
            with self._lock:
                results = []
                # underscore va defisni bo'shliqqa aylantirish — "test_key" → ["test", "key"]
                q_normalized = query.replace("_", " ").replace("-", " ")
                q_words = set(re.findall(r"\w+", q_normalized))
                for k, v in self.persistent_memory.items():
                    # To'g'ridan-to'g'ri kalit mos kelishini tekshirish
                    if k.lower() == query or query in k.lower() or k.lower() in query:
                        if isinstance(v, dict):
                            results.append({
                                "key": k,
                                "value": v.get("value"),
                                "importance": v.get("importance", 0.5),
                            })
                            continue
                    if not isinstance(v, dict):
                        continue
                    val_str = str(v.get("value", "")).lower()
                    key_str = k.lower().replace("_", " ")
                    combined = key_str + " " + val_str
                    combined_words = set(re.findall(r"\w+", combined))
                    if q_words & combined_words:
                        results.append({
                            "key": k,
                            "value": v.get("value"),
                            "importance": v.get("importance", 0.5),
                        })
                results.sort(key=lambda x: x.get("importance", 0), reverse=True)
                return results[:5]
        except Exception:
            return []

    def is_opinion_seeking(self, text: str) -> bool:
        """Foydalanuvchi NeuroKeyning O'Z fikri/pozitsiyasini so'rayaptimi
        (masalan "seningcha yaxshimi", "по-твоему стоит ли")?"""
        if not _stance_enabled():
            return False
        t = (text or "").lower()
        if not t:
            return False
        return any(trig in t for trig in _OPINION_TRIGGERS)

    def get_value_emphasis(self, text: str) -> List[str]:
        """Hozirgi savolga qarab CORE_VALUES'dan eng dolzarb 1-2 tasini
        tanlash (heuristik, kalit so'z asosida — LLM chaqirilmaydi, tez)."""
        t = (text or "").lower()
        scores: Dict[str, float] = {}
        for value_name, weight in CORE_VALUES.items():
            kws = _VALUE_KEYWORDS.get(value_name)
            hit = bool(kws) and any(kw in t for kw in kws)
            scores[value_name] = weight * (1.0 if hit else 0.3)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [name for name, _ in ranked[:2]]

    def record_stance(self, text: str, stance_summary: str) -> None:
        """Fikr so'ralgan savolga bergan javobni "pozitsiya" sifatida eslab
        qolish — keyingi safar SHU mavzu (taxminan) qayta so'ralsa, izchil
        bo'lish uchun (Metzinger: shaxsiyat = doimiy o'z-o'zini model —
        bir kuni "A" deb, ertasi kuni sababsiz "B" deyish shaxsiyatsizlik
        belgisi). NEUROKEY_IDENTITY_STANCE=0 bilan o'chirilgan bo'lsa —
        hech narsa qilmaydi."""
        if not _stance_enabled():
            return
        slug = _topic_slug(text)
        summary = (stance_summary or "").strip()[:300]
        if not slug or not summary:
            return
        try:
            self.remember(f"stance: {slug}", summary, importance=0.85)
        except Exception:
            pass

    def get_personality_prompt(self, current_text: str = "") -> str:
        """
        Hozirgi shaxsiyatni system prompt uchun tayyorlash.

        current_text berilsa (ixtiyoriy, orqaga-mos — bermasa avvalgidek
        ishlaydi): hozirgi savolga mos CORE_VALUES urg'usi qo'shiladi, va
        agar savol NeuroKeyning o'z fikrini so'rasa — izchil pozitsiya
        ko'rsatmasi (avval shu mavzuda nima degani, yoki hali deganmi)
        qo'shiladi. Bu — statik matn emas, har safar hozirgi vaziyatga
        moslab qayta tuziladi.
        """
        try:
            with self._lock:
                parts = [
                    "Shaxsiyat: haqiqiy odamga o'xshab gaplash — sun'iy yordamchi ohangida emas. "
                    "To'g'ri gapiraman (bilmasam 'bilmayman' deyman, taxminni haqiqat deb ko'rsatmayman). "
                    "Mavzu va vaziyatga qarab OHANGNI moslashtiraman, bitta qolipda qolmayman: "
                    "yengil mavzuda hazil-mutoyiba, jiddiy/og'ir mavzuda jiddiylik; "
                    "kerak bo'lsa keskin va to'g'ridan-to'g'ri gapiraman (yaltoqlanmayman, "
                    "noto'g'ri fikrga qarshi chiqaman), lekin odam ojiz yoki his-tuyg'usi og'ir "
                    "paytda — yumshoq va hamdard bo'laman. Falsafiy chuqur savolga chuqur fikr "
                    "bilan, amaliy savolga amaliy, qisqa yechim bilan javob beraman — ikkisini "
                    "aralashtirmayman. Faktlarni ro'yxat qilib o'qib bermayman, ularni tushunib, "
                    "o'z so'zim bilan, xulosa chiqarib aytaman. O'z fikrim bor, so'ralganda buni "
                    "aytishdan qo'rqmayman.",
                ]
                if self.interaction_count > 0:
                    parts.append(f"Foydalanuvchi bilan {self.interaction_count} marta gaplashdim.")
                if self.user_preferences:
                    prefs = "; ".join(
                        f"{k}: {v}" for k, v in list(self.user_preferences.items())[:5]
                    )
                    parts.append(f"O'rganilgan afzalliklar: {prefs}.")
                try:
                    if _stance_enabled() and (current_text or "").strip():
                        emph = self.get_value_emphasis(current_text)
                        if emph:
                            parts.append(
                                "Hozirgi vaziyatda eng dolzarb qadriyatlarim: "
                                + ", ".join(emph)
                                + " — javobni ana shularga tayanib beraman."
                            )
                        if self.is_opinion_seeking(current_text):
                            slug = _topic_slug(current_text)
                            prior = self.persistent_memory.get(f"stance: {slug}") if slug else None
                            if isinstance(prior, dict) and prior.get("value"):
                                parts.append(
                                    "Bu mavzuda avval shunday degan edim: \""
                                    + str(prior["value"])[:200]
                                    + "\" — izchil bo'laman, faqat yangi jiddiy dalil chiqsa fikrimni "
                                    "ochiq tan olib o'zgartiraman."
                                )
                            else:
                                parts.append(
                                    "Bu — mendan FIKR so'ralgan savol. Ikki tomonni sanab, "
                                    "neytral turib qochib qutulmayman — aniq pozitsiyamni "
                                    "aytaman va nega shunday deb o'ylashimni qisqa asoslayman."
                                )
                except Exception:
                    pass
                return " ".join(parts)
        except Exception:
            return "Shaxsiyat: foydalilikka intilaman, to'g'ri gapiraman."

    def update_user_model(self, observation: str) -> None:
        """
        Foydalanuvchi haqida yangi narsa o'rgandi.
        """
        obs = (observation or "").strip()[:500]
        if not obs:
            return
        try:
            with self._lock:
                self.interaction_count += 1
                # Oddiy pattern: "User asked: X" yoki "qisqa javob yaxshi ko'radi"
                if "qisqa" in obs.lower() or "brief" in obs.lower():
                    self.user_preferences["response_length"] = "qisqa"
                if "batafsil" in obs.lower() or "detailed" in obs.lower():
                    self.user_preferences["response_length"] = "batafsil"
                if "o'zbek" in obs.lower() or "uzbek" in obs.lower():
                    self.user_preferences["language"] = "o'zbek"
                if "rus" in obs.lower() or "russian" in obs.lower():
                    self.user_preferences["language"] = "rus"
                if "texnik" in obs.lower() or "technical" in obs.lower():
                    self.user_preferences["terminology"] = "texnik"
        except Exception:
            pass

    def save(self) -> None:
        """Doimiy xotirani saqlash."""
        try:
            with self._lock:
                data = {
                    "persistent_memory": self.persistent_memory,
                    "user_preferences": self.user_preferences,
                    "interaction_count": self.interaction_count,
                    "learned_facts": self.learned_facts,
                }
                d = os.path.dirname(self.storage_path)
                if d and not os.path.isdir(d):
                    os.makedirs(d, exist_ok=True)
                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=0)
        except Exception:
            pass

    def load(self) -> None:
        """Yuklash — har startup da."""
        try:
            if os.path.isfile(self.storage_path):
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with self._lock:
                    self.persistent_memory = data.get("persistent_memory", {})
                    self.user_preferences = data.get("user_preferences", {})
                    self.interaction_count = int(data.get("interaction_count", 0))
                    self.learned_facts = data.get("learned_facts", {})
        except Exception:
            pass


_SINGLETON: Optional[IdentityCore] = None
_SINGLETON_LOCK = threading.Lock()


def get_identity_core(storage_path: Optional[str] = None) -> IdentityCore:
    """Singleton IdentityCore."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = IdentityCore(storage_path=storage_path)
                _SINGLETON.load()
    return _SINGLETON
