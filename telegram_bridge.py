# -*- coding: utf-8 -*-
"""
Telegram USER client bridge (Telethon)
- Faqat личка (private chat)
- Incoming xabarlarni o‘qiydi
- Javob yuboradi
- api_id unexpected keyword muammosi YO‘Q
"""

import asyncio
import threading
from typing import Callable, Dict, List, Optional

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import User

import config as C


class TelegramUserBridge:
    def __init__(
        self,
        api_id=None,
        api_hash=None,
        session_name=None,
        phone=None,
        **kwargs
    ):
        # 🔑 CONFIG bilan moslash
        self.api_id = api_id or getattr(C, "TELEGRAM_API_ID", None)
        self.api_hash = api_hash or getattr(C, "TELEGRAM_API_HASH", None)
        self.session_name = session_name or getattr(C, "TELEGRAM_SESSION_NAME", "neurokey")
        self.phone = phone or getattr(C, "TELEGRAM_PHONE", None)

        if not self.api_id or not self.api_hash:
            raise ValueError("TELEGRAM_API_ID / TELEGRAM_API_HASH yo‘q")

        self._client: Optional[TelegramClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()

    # ---------------- internal ----------------

    def _ensure_loop(self):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()

    async def _ensure_client(self):
        if self._client is None:
            self._client = TelegramClient(
                self.session_name,
                int(self.api_id),
                str(self.api_hash),
            )

        if not self._client.is_connected():
            await self._client.connect()

        if not await self._client.is_user_authorized():
            if not self.phone:
                self.phone = input("Telegram phone (+998...): ").strip()

            await self._client.send_code_request(self.phone)
            code = input("Telegram code: ").strip()

            try:
                await self._client.sign_in(self.phone, code)
            except SessionPasswordNeededError:
                pw = input("Telegram 2FA password: ").strip()
                await self._client.sign_in(password=pw)

    def _run(self, coro):
        self._ensure_loop()

        if self._thread is None or not self._thread.is_alive():
            def runner():
                asyncio.set_event_loop(self._loop)
                self._started.set()
                self._loop.run_forever()

            self._thread = threading.Thread(target=runner, daemon=True)
            self._thread.start()
            self._started.wait(5)

        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    # ---------------- PUBLIC API ----------------

    def start_listener(
        self,
        on_message: Callable[[Dict], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        async def _listen():
            try:
                await self._ensure_client()

                @self._client.on(events.NewMessage(incoming=True))
                async def handler(event):
                    try:
                        if event.out:
                            return

                        sender = await event.get_sender()
                        if not isinstance(sender, User):
                            return  # faqat lichka

                        text = event.message.message or ""
                        if not text.strip():
                            return

                        payload = {
                            "peer_id": sender.id,
                            "peer_name": f"{sender.first_name or ''} {sender.last_name or ''}".strip(),
                            "text": text,
                            "date": str(event.message.date),
                        }
                        on_message(payload)

                    except Exception as e:
                        if on_error:
                            on_error(e)

                await self._client.run_until_disconnected()

            except Exception as e:
                if on_error:
                    on_error(e)

        self._run(_listen())
        print("[TG] user-client listener started (личка).", flush=True)

    def unread_incoming(self, limit: int = 10) -> List[Dict]:
        async def _fetch():
            await self._ensure_client()
            out: List[Dict] = []

            async for dialog in self._client.iter_dialogs():
                if not isinstance(dialog.entity, User):
                    continue

                if dialog.unread_count <= 0:
                    continue

                async for msg in self._client.iter_messages(
                    dialog.entity,
                    reverse=True,  # 🔥 tepadan pastga
                    limit=50,
                ):
                    if not msg.unread or msg.out:
                        continue
                    if not (msg.message or "").strip():
                        continue

                    out.append({
                        "peer_id": dialog.entity.id,
                        "peer_name": f"{dialog.entity.first_name or ''} {dialog.entity.last_name or ''}".strip(),
                        "text": msg.message,
                        "msg_id": msg.id,
                        "date": str(msg.date),
                    })

                    if len(out) >= limit:
                        break

                if len(out) >= limit:
                    break

            return out

        return self._run(_fetch())

    def send_peer(self, peer_id: int, text: str):
        async def _send():
            await self._ensure_client()
            await self._client.send_message(peer_id, text)

        return self._run(_send())

    def send_file(self, peer_id: int, file_path: str, caption: str = ""):
        """Fayl, rasm yoki skrinshot yuborish (Telethon send_file).

        file_path — mavjud fayl yo'li (masalan screen_vision.grab_screen()
        natijasi diskka saqlangan PNG). caption — ixtiyoriy izoh matni.
        """
        async def _send():
            await self._ensure_client()
            return await self._client.send_file(peer_id, file_path, caption=caption or None)

        return self._run(_send())

    def send_screenshot(self, peer_id: int, caption: str = ""):
        """Joriy ekranni olib, to'g'ridan-to'g'ri Telegramga yuboradi.

        Vaqtinchalik faylga saqlaydi (Telethon fayl yo'li talab qiladi),
        yuborilgach o'chiradi."""
        import os
        import tempfile

        import screen_vision as sv

        img = sv.grab_screen()
        if img is None:
            raise RuntimeError("Ekranni olib bo'lmadi")

        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="nk_screenshot_")
        os.close(fd)
        try:
            img.save(tmp_path, "PNG")
            return self.send_file(peer_id, tmp_path, caption=caption)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ── Singleton — executor.py va boshqa modullar shu orqali foydalanadi ──────

_bridge_instance: Optional["TelegramUserBridge"] = None


def get_bridge() -> Optional["TelegramUserBridge"]:
    """Global TelegramUserBridge — bir marta yaratiladi, keyin qayta ishlatiladi.

    TELEGRAM_API_ID/HASH sozlanmagan bo'lsa None qaytaradi (xato tashlamaydi) —
    executor.py buni 'Telegram ulanmagan' deb halol xabar qiladi."""
    global _bridge_instance
    if _bridge_instance is not None:
        return _bridge_instance
    try:
        if not getattr(C, "TELEGRAM_API_ID", None) or not getattr(C, "TELEGRAM_API_HASH", None):
            return None
        _bridge_instance = TelegramUserBridge()
        return _bridge_instance
    except Exception:
        return None
