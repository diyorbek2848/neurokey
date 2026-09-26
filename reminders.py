# -*- coding: utf-8 -*-
import json, os, time, re, datetime as dt
from typing import List, Dict, Any, Optional
import config as C

PATH = C.REMINDERS_PATH

def _load() -> Dict[str, Any]:
    if os.path.exists(PATH):
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"auto_id": 1, "items": []}

def _save(data: Dict[str, Any]):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --------- time parsing (rus) ----------
_WORDS = {
    "сегодня": 0,
    "завтра": 1,
    "послезавтра": 2
}

def _parse_dt(text: str) -> Optional[int]:
    """
    Qabul qiladi: 
    - 'сегодня 18:45', 'завтра 09:00', 'послезавтра 14:30'
    - '10.09.2025 16:00' yoki '10.09 16:00' (yil bo'lmasa – hozirgi yil)
    - faqat vaqt '18:30' -> bugun shu vaqt (agar allaqachon o‘tgan bo‘lsa, ertaga)
    """
    t = text.strip().lower()

    # templates
    m = re.search(r"(сегодня|завтра|послезавтра)\s+(\d{1,2}):(\d{2})", t)
    if m:
        base = dt.date.today() + dt.timedelta(days=_WORDS[m.group(1)])
        hh, mm = int(m.group(2)), int(m.group(3))
        d = dt.datetime.combine(base, dt.time(hh, mm))
        return int(d.timestamp())

    m = re.search(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s+(\d{1,2}):(\d{2})", t)
    if m:
        day, mon, year = int(m.group(1)), int(m.group(2)), m.group(3)
        year = int(year) if year else dt.date.today().year
        hh, mm = int(m.group(4)), int(m.group(5))
        try:
            d = dt.datetime(year, mon, day, hh, mm)
            return int(d.timestamp())
        except Exception:
            return None

    m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        today = dt.datetime.now().replace(second=0, microsecond=0, hour=hh, minute=mm)
        if today.timestamp() <= time.time():
            today = today + dt.timedelta(days=1)
        return int(today.timestamp())

    return None

# --------- API ----------
def add(text: str) -> int:
    """
    Matndan (ixtiyoriy) muddatni ajratib oladi, qolganini 'title' sifatida saqlaydi.
    """
    data = _load()
    due_ts = _parse_dt(text)
    title = text
    if due_ts is not None:
        # vaqt ifodalarini chiqarib tashlashga harakat
        title = re.sub(r"(сегодня|завтра|послезавтра)\s+\d{1,2}:\d{2}", "", title, flags=re.I)
        title = re.sub(r"\d{1,2}\.\d{1,2}(?:\.\d{4})?\s+\d{1,2}:\d{2}", "", title)
        title = re.sub(r"\b\d{1,2}:\d{2}\b", "", title)
    title = title.strip(" .;,-")

    rid = data["auto_id"]
    data["auto_id"] += 1
    item = {
        "id": rid,
        "title": title if title else "Напоминание",
        "created_ts": int(time.time()),
        "due_ts": due_ts
    }
    data["items"].append(item)
    _save(data)
    return rid

def list_all() -> List[Dict[str, Any]]:
    return _load().get("items", [])

def remove(reminder_id: int) -> bool:
    data = _load()
    before = len(data["items"])
    data["items"] = [x for x in data["items"] if x.get("id") != reminder_id]
    _save(data)
    return len(data["items"]) < before

def clear_all() -> int:
    data = _load()
    n = len(data["items"])
    data["items"] = []
    _save(data)
    return n
