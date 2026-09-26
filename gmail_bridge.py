# -*- coding: utf-8 -*-
import os, base64, re, argparse
from typing import Dict, Any, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

def _b64url_decode(data: str) -> bytes:
    data = data.replace("-", "+").replace("_", "/")
    pad = "=" * (-len(data) % 4)
    return base64.b64decode(data + pad)

def _extract_plain_text(payload: Dict[str, Any]) -> str:
    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}
    data = body.get("data")
    if data and mime in ("text/plain", "text/html"):
        raw = _b64url_decode(data)
        txt = raw.decode("utf-8", errors="ignore")
        if mime == "text/html":
            txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt
    for part in payload.get("parts", []) or []:
        txt = _extract_plain_text(part)
        if txt:
            return txt
    return ""

def _get_header(headers, name: str) -> str:
    name_low = name.lower()
    for h in headers or []:
        if (h.get("name", "").lower() == name_low):
            return h.get("value", "")
    return ""

class GmailBridge:
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json", user_id: str = "me"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.user_id = user_id
        self._svc = None

    def auth(self):
        creds: Optional[Credentials] = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        if not creds or not creds.valid:
            if not os.path.exists(self.credentials_path):
                raise FileNotFoundError(f"credentials.json topilmadi: {self.credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(self.token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

        self._svc = build("gmail", "v1", credentials=creds)

    def _ensure(self):
        if self._svc is None:
            self.auth()

    def list_unread(self, limit: int = 5, query: str = "is:unread"):
        self._ensure()
        res = self._svc.users().messages().list(userId=self.user_id, q=query, maxResults=max(1, min(limit, 50))).execute()
        return res.get("messages", []) or []

    def get_message(self, message_id: str) -> dict:
        self._ensure()
        msg = self._svc.users().messages().get(userId=self.user_id, id=message_id, format="full").execute()
        payload = msg.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        frm = _get_header(headers, "From")
        subj = _get_header(headers, "Subject")
        snippet = (msg.get("snippet") or "").strip()
        body = _extract_plain_text(payload)
        return {"id": message_id, "from": frm, "subject": subj, "snippet": snippet, "body": body[:2000]}

def main():
    p = argparse.ArgumentParser(prog="gmail_bridge.py")
    p.add_argument("cmd", nargs="?", default="unread", choices=["auth", "unread", "check", "debug"])
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--query", type=str, default="is:unread")
    p.add_argument("--credentials", type=str, default="credentials.json")
    p.add_argument("--token", type=str, default="token.json")
    args = p.parse_args()

    gb = GmailBridge(credentials_path=args.credentials, token_path=args.token)

    if args.cmd == "auth":
        gb.auth()
        print(f"OK: token saqlandi -> {os.path.abspath(args.token)}")
        return

    if args.cmd in ("unread", "check"):
        msgs = gb.list_unread(limit=args.limit, query=args.query)
        if not msgs:
            print("UNREAD yo‘q (yoki query bo‘yicha topilmadi).")
            return
        for m in msgs:
            info = gb.get_message(m["id"])
            print("-" * 60)
            print("From   :", info["from"])
            print("Subject:", info["subject"])
            print("Snippet:", info["snippet"])
        return

    if args.cmd == "debug":
        print("cwd:", os.getcwd())
        print("credentials:", os.path.abspath(args.credentials), "exists=", os.path.exists(args.credentials))
        print("token      :", os.path.abspath(args.token), "exists=", os.path.exists(args.token))
        gb.auth()
        labels = gb._svc.users().labels().list(userId="me").execute().get("labels", [])
        print("labels:", len(labels))
        print("ok: gmail service ishladi")
        return

if __name__ == "__main__":
    main()


# ── Module-level singleton (main.py bunlarni chaqiradi) ──────────────────────
_bridge: Optional[GmailBridge] = None

def _get_bridge() -> GmailBridge:
    """Lazy singleton — bir marta auth qilinadi, keyin qayta ishlatiladi."""
    global _bridge
    if _bridge is None:
        _bridge = GmailBridge()
    return _bridge


def list_unread(limit: int = 5, query: str = "is:unread") -> list:
    """O'qilmagan xatlarni to'liq ma'lumot bilan qaytaradi (from, subject, snippet, body).
    main.py tomonidan chaqiriladi: gmail_bridge.list_unread(limit=5)
    """
    bridge = _get_bridge()
    try:
        bridge._ensure()  # auth qiladi (token.json dan yoki yangi auth)
        res = bridge._svc.users().messages().list(
            userId=bridge.user_id,
            q=query,
            maxResults=max(1, min(limit, 20))
        ).execute()
        items = res.get("messages") or []
        messages = []
        for item in items[:limit]:
            try:
                msg = bridge.get_message(item["id"])
                messages.append(msg)
            except Exception:
                pass
        return messages
    except Exception:
        return []


def send_message(to: str, subject: str, body: str) -> bool:
    """Gmail orqali xat yuborish."""
    import email.mime.text
    import base64
    bridge = _get_bridge()
    bridge._ensure()
    try:
        msg = email.mime.text.MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        bridge._svc.users().messages().send(
            userId=bridge.user_id, body={"raw": raw}
        ).execute()
        return True
    except Exception:
        return False
