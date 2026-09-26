# -*- coding: utf-8 -*-
import asyncio
import concurrent.futures
import os
import threading
from typing import Callable, Dict, List, Optional, Any, Tuple

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import User

import config as C


class TelegramUserBridge:
    def __init__(self, api_id=None, api_hash=None, session_name=None, session_path=None, phone=None, **kwargs):
        self.api_id = api_id or getattr(C, "TELEGRAM_API_ID", None) or kwargs.get("TELEGRAM_API_ID")
        self.api_hash = api_hash or getattr(C, "TELEGRAM_API_HASH", None) or kwargs.get("TELEGRAM_API_HASH")
        self.session_name = session_name or getattr(C, "TELEGRAM_SESSION_NAME", "neurokey") or kwargs.get("session_name")
        self.session_path = session_path or getattr(C, "TELEGRAM_SESSION", None) or kwargs.get("session_path")
        self.phone = phone or getattr(C, "TELEGRAM_PHONE", None) or kwargs.get("phone")

        if not self.api_id or not self.api_hash:
            raise ValueError("TELEGRAM_API_ID / TELEGRAM_API_HASH yo'q (config.py yoki env)")

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._client: Optional[TelegramClient] = None
        self._ready = threading.Event()

    def _ensure_thread(self):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        if self._thread and self._thread.is_alive():
            return

        def runner():
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        self._ready.wait(5)

    def _run(self, coro, timeout: Optional[float] = None):
        """Run coroutine in loop. If timeout (seconds) given, raise TimeoutError when exceeded."""
        self._ensure_thread()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        if timeout is not None and timeout > 0:
            try:
                return fut.result(timeout=timeout)
            except (TimeoutError, concurrent.futures.TimeoutError) as e:
                raise TimeoutError(f"Telegram connection timed out after {timeout}s") from e
        return fut.result()

    def ensure_connected(self, timeout: Optional[float] = None):
        """Avval ulanish va (kerak bo'lsa) kod kiritish. timeout berilsa — shu sekunddan keyin TimeoutError."""
        t = timeout
        if t is None:
            t = getattr(C, "TELEGRAM_CONNECT_TIMEOUT_SEC", None)
        return self._run(self._ensure_client(), timeout=t)

    async def _ensure_client(self):
        if self._client is None:
            self._client = TelegramClient(self.session_name, int(self.api_id), str(self.api_hash))

        if not self._client.is_connected():
            await self._client.connect()

        if not await self._client.is_user_authorized():
            raise RuntimeError(
                "Telegram session autentifikatsiya yo'q. "
                "Alohida autentifikatsiya qiling: python telegram_user_bridge.py auth"
            )

    def start_listener(self, on_message: Callable[[Dict[str, Any]], None]):
        async def _listen():
            await self._ensure_client()

            @self._client.on_new_message
            async def handler(event):
                msg = event.message
                if msg.out:
                    return
                # Faqat lichka (DM). Kanal va guruh xabarlarini ignore qilamiz.
                if not getattr(event, "is_private", False):
                    return
                sender = await event.get_sender()
                if not isinstance(sender, User):
                    return
                text = (msg.message or "").strip()
                if not text:
                    return
                payload = {
                    "peer_id": event.chat_id,
                    "peer_name": f"{getattr(sender,'first_name','') or ''} {getattr(sender,'last_name','') or ''}".strip(),
                    "from_id": msg.sender_id,
                    "text": text,
                    "date": str(msg.date),
                    "msg_id": msg.id,
                }
                on_message(payload)

            await self._client.run_until_disconnected()

        self._ensure_thread()
        asyncio.run_coroutine_threadsafe(_listen(), self._loop)
        print("[TG] user-client listener started (личка).", flush=True)

    def unread_incoming(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Faqat yangi (o'qilmagan) kiruvchi xabarlarni qaytaradi. Eski o'qilganlarni hisobga olmaydi."""
        async def _fetch():
            await self._ensure_client()
            out: List[Dict[str, Any]] = []
            async for dialog in self._client.iter_dialogs():
                ent = dialog.entity
                if not isinstance(ent, User):
                    continue
                if getattr(dialog, "unread_count", 0) <= 0:
                    continue
                # Faqat o'qilmaganlar: id > read_inbox_max_id bo'lgan xabarlar (eski o'qilganlarni olmaymiz)
                read_max = getattr(dialog, "read_inbox_max_id", None)
                if read_max is None:
                    read_max = 0
                unread_count = getattr(dialog, "unread_count", 0)
                take_from_dialog = 0
                fetch_limit = min(50, max(limit, unread_count + 5))
                async for msg in self._client.iter_messages(ent, limit=fetch_limit):
                    if len(out) >= limit:
                        break
                    if msg.out:
                        continue
                    if read_max and msg.id <= read_max:
                        continue
                    if not read_max and take_from_dialog >= unread_count:
                        break
                    take_from_dialog += 1
                    text = (msg.message or "").strip()
                    if not text:
                        continue
                    out.append({
                        "peer_id": ent.id,
                        "peer_name": f"{getattr(ent,'first_name','') or ''} {getattr(ent,'last_name','') or ''}".strip() or "User",
                        "from_id": msg.sender_id,
                        "text": text,
                        "date": str(msg.date),
                        "msg_id": msg.id,
                    })
                if len(out) >= limit:
                    break
            return out[:limit]
        return self._run(_fetch())

    def recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        return self.unread_incoming(limit=limit)

    def send_peer(self, peer_id: int, text: str):
        async def _send():
            await self._ensure_client()
            await self._client.send_message(peer_id, text)
        return self._run(_send())

    def get_peer_by_name(self, name: str, timeout: Optional[float] = 15.0) -> Optional[int]:
        """Kontakt nomi bo'yicha peer_id topish (akam, brother, ism, username)."""

        async def _search():
            await self._ensure_client()
            name_raw = (name or "").strip()
            name_lower = name_raw.lower()
            if not name_lower:
                return None
            # Config dagi laqab -> ism (akam -> Jasur)
            aliases = getattr(C, "TG_CONTACT_ALIASES", None) or {}
            resolved = (aliases.get(name_lower) or "").strip() or name_raw
            search_terms = [resolved.lower(), name_lower] if resolved.lower() != name_lower else [name_lower]
            async for dialog in self._client.iter_dialogs(limit=200):
                ent = dialog.entity
                if not isinstance(ent, User):
                    continue
                first = (getattr(ent, "first_name", "") or "").strip()
                last = (getattr(ent, "last_name", "") or "").strip()
                username = (getattr(ent, "username", "") or "").strip().lower()
                full = f"{first} {last}".strip().lower()
                for term in search_terms:
                    if term and (term in full or term in first.lower() or term in last.lower() or term in username):
                        return ent.id
            return None

        try:
            return self._run(_search(), timeout=timeout)
        except Exception:
            return None

    def send_to_contact(
        self,
        contact_name: str,
        text: str,
        file_path: Optional[str] = None,
        timeout: Optional[float] = 20.0,
    ) -> Tuple[bool, str]:
        """Kontakt nomiga xabar yoki fayl yuborish. (success, message)."""
        peer_id = self.get_peer_by_name(contact_name, timeout=timeout)
        if peer_id is None:
            return False, f"Contact «{contact_name}» not found in Telegram."
        try:
            if file_path and os.path.exists(file_path):
                async def _send_file():
                    await self._ensure_client()
                    await self._client.send_file(peer_id, file_path, caption=text or None)
                self._run(_send_file(), timeout=timeout)
                return True, f"Sent file to {contact_name}."
            self.send_peer(peer_id, text or "")
            return True, f"Sent to {contact_name}."
        except Exception as e:
            err = str(e).lower()
            if "flood" in err or "wait" in err:
                return False, "Telegram asks to wait. Try again in a minute."
            return False, f"Failed to send: {e}"
