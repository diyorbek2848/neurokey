# -*- coding: utf-8 -*-
"""NeuroKey — Notion ovoz bilan boshqarish.

API kalit: NOTION_TOKEN (.env)  [notion.so/my-integrations dan oling]
Bepul: Shaxsiy foydalanish bepul, 3 req/sek

Buyruqlar:
    "Notion da yangi eslatma yoz — bugun meeting soat 15:00"
    "Notion da g'oyalarni qidir"
    "Notion sahifalarimni ko'rsat"
"""
import os, json, ssl, urllib.request, urllib.error
from typing import Optional, List, Dict

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

try:
    import config as C
    _TOKEN = (os.getenv("NOTION_TOKEN") or getattr(C, "NOTION_TOKEN", "")).strip()
except Exception:
    _TOKEN = os.getenv("NOTION_TOKEN", "").strip()

_BASE = "https://api.notion.com/v1"
_VERSION = "2022-06-28"

_TRIGGERS = [
    "notion", "нотион", "заметка", "eslatma", "note",
    "notion da yoz", "notion ga saqlash", "notion qidir",
]


def is_available() -> bool:
    return bool(_TOKEN)


def is_notion_request(text: str) -> bool:
    low = text.lower()
    return any(t in low for t in _TRIGGERS)


def _headers() -> Dict:
    return {
        "Authorization": f"Bearer {_TOKEN}",
        "Notion-Version": _VERSION,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, body: dict = None) -> Optional[dict]:
    url = f"{_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise Exception(f"Notion API {e.code}: {err_body[:200]}")
    except Exception as e:
        raise Exception(f"Notion so'rov xatosi: {e}")


def search_pages(query: str = "", limit: int = 5) -> List[Dict]:
    body = {"page_size": limit}
    if query:
        body["query"] = query
    data = _request("POST", "/search", body)
    return (data or {}).get("results", [])


def create_page(title: str, content: str = "", parent_page_id: str = "") -> Dict:
    """Yangi sahifa yaratish. parent_page_id bo'lmasa — workspace root da."""
    body: Dict = {
        "properties": {
            "title": [{"text": {"content": title}}]
        },
        "children": [],
    }
    if parent_page_id:
        body["parent"] = {"page_id": parent_page_id}
    else:
        # Database yo'q bo'lsa — parent sifatida birinchi sahifani topib ulash
        body["parent"] = {"type": "workspace", "workspace": True}

    if content:
        body["children"] = [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": content[:2000]}}]},
        }]
    return _request("POST", "/pages", body)


def append_to_page(page_id: str, content: str) -> Dict:
    body = {"children": [{
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"text": {"content": content[:2000]}}]},
    }]}
    return _request("PATCH", f"/blocks/{page_id}/children", body)


def handle(text: str, tts_say=None) -> Optional[str]:
    if not is_notion_request(text):
        return None
    if not is_available():
        return ("NOTION_TOKEN yo'q. notion.so/my-integrations da yangi integration yarating, "
                "keyin .env ga NOTION_TOKEN=... qo'shing.")

    def say(m):
        if tts_say:
            try: tts_say(m)
            except Exception: pass

    low = text.lower()
    import re as _re

    # Yangi sahifa / eslatma yozish
    if any(w in low for w in ["yoz", "saqlash", "создай", "добавь", "qo'sh"]):
        m = _re.search(r"[—\-:]\s*(.{3,})", text)
        content = m.group(1).strip() if m else text
        # Sarlavha: birinchi 60 belgi
        title = content[:60]
        try:
            result = create_page(title, content)
            page_url = result.get("url", "")
            msg = f"Notion da saqlandi: '{title}'"
            if page_url:
                msg += f"\n{page_url}"
            say(f"Notion da saqlandi: {title}")
            return msg
        except Exception as e:
            msg = f"Notion xato: {e}"
            say(msg)
            return msg

    # Qidirish
    if any(w in low for w in ["qidir", "найди", "search", "ko'rsat", "список"]):
        q_m = _re.search(r"[—\-:]\s*(.{2,})", text)
        query = q_m.group(1).strip() if q_m else ""
        try:
            pages = search_pages(query, limit=5)
            if not pages:
                msg = "Notion da hech narsa topilmadi."
            else:
                lines = []
                for p in pages[:5]:
                    props = p.get("properties", {})
                    title_data = props.get("title", {})
                    if isinstance(title_data, list):
                        t = "".join(x.get("plain_text", "") for x in title_data)
                    elif isinstance(title_data, dict):
                        t = "".join(x.get("plain_text", "") for x in title_data.get("title", []))
                    else:
                        t = p.get("id", "")[:8]
                    lines.append(f"• {t}")
                msg = "Notion sahifalar:\n" + "\n".join(lines)
            say(msg[:200])
            return msg
        except Exception as e:
            msg = f"Notion qidiruv xato: {e}"
            say(msg)
            return msg

    return None
