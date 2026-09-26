# -*- coding: utf-8 -*-
"""
NeuroKey — Mobile Bridge Server (WebSockets + WebRTC Signaling + Screen/Audio Stream)
Telefon orqali kompyuterni ko'rish, boshqarish va ovozli suhbat qurish serveri.
"""
import asyncio
import base64
import io
import json
import logging
import os
import sys
from typing import Set

import mss
import pyautogui
from PIL import Image
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MobileBridge")

# Faol mijozlar
connected_clients: Set[websockets.WebSocketServerProtocol] = set()

# Ekran rasmga olish funksiyasi (optimallashgan JPEG)
def _capture_screen_jpeg(quality: int = 55, scale: float = 0.5) -> str:
    try:
        with mss.mss() as sct:
            # Asosiy monitor
            mon = sct.monitors[1]
            sct_img = sct.grab(mon)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # O'lchamni kichraytirish (tez uzatish uchun)
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
            
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        log.error(f"Ekran suratga olish xatosi: {e}")
        return ""

# LLM javob olish (thread ichida bloklamasdan)
def _get_llm_reply(user_text: str) -> str:
    try:
        from llm_router import answer as llm_answer
        return llm_answer(user_text)
    except Exception as e:
        log.error(f"LLM javob xatosi: {e}")
        return f"Xatolik yuz berdi: {e}"

async def handler(websocket, path):
    connected_clients.add(websocket)
    remote = websocket.remote_address
    log.info(f"[Ulandi] Yangi mijoz: {remote}. Jami: {len(connected_clients)}")
    
    # Holat yuborish
    await websocket.send(json.dumps({
        "type": "welcome",
        "message": "NeuroKey Mobile Bridge aloqada",
        "screen_supported": True,
        "control_supported": True
    }))
    
    try:
        async for raw_msg in websocket:
            try:
                data = json.loads(raw_msg)
            except Exception:
                continue
                
            cmd = data.get("cmd")
            
            # 1. Ekran so'rovi (Bir martalik yoki jonli oqim)
            if cmd == "screen_request":
                loop = asyncio.get_running_loop()
                q = data.get("quality", 55)
                sc = data.get("scale", 0.5)
                img_b64 = await loop.run_in_executor(None, _capture_screen_jpeg, q, sc)
                if img_b64:
                    await websocket.send(json.dumps({
                        "type": "screen_frame",
                        "image": img_b64
                    }))
            
            # 2. Telefondan ovozli/matnli buyruq kelganda
            elif cmd == "audio_command" or cmd == "text_command":
                text = (data.get("text") or "").strip()
                log.info(f"[Buyruq] Telefondan keldi: {text}")
                if text:
                    loop = asyncio.get_running_loop()
                    reply = await loop.run_in_executor(None, _get_llm_reply, text)
                    await websocket.send(json.dumps({
                        "type": "response",
                        "user_text": text,
                        "text": reply
                    }))
            
            # 3. Sichqoncha boshqaruvi (Mouse click/move)
            elif cmd == "mouse_click":
                x = data.get("x")
                y = data.get("y")
                button = data.get("button", "left")
                if x is not None and y is not None:
                    pyautogui.click(x=x, y=y, button=button)
                    await websocket.send(json.dumps({"type": "ack", "status": "click_done"}))
                    
            elif cmd == "mouse_move":
                x = data.get("x")
                y = data.get("y")
                if x is not None and y is not None:
                    pyautogui.moveTo(x=x, y=y)
            
            # 4. Klaviaturadan yozish
            elif cmd == "type_text":
                text_to_type = data.get("text", "")
                if text_to_type:
                    pyautogui.write(text_to_type)
                    await websocket.send(json.dumps({"type": "ack", "status": "typed"}))
            
            # 5. WebRTC Signaling (Offer, Answer, ICE Candidate)
            elif cmd in ["offer", "answer", "ice-candidate"]:
                for client in connected_clients:
                    if client != websocket:
                        try:
                            await client.send(raw_msg)
                        except Exception as e:
                            log.error(f"Signaling xatosi: {e}")
                            
            else:
                log.warning(f"Noma'lum buyruq: {cmd}")
                
    except websockets.exceptions.ConnectionClosed as e:
        log.info(f"[Uzildi] Mijoz uzildi: {remote} ({e})")
    finally:
        connected_clients.discard(websocket)
        log.info(f"Mijoz o'chirildi. Qolgan faol mijozlar: {len(connected_clients)}")

async def main():
    port = int(os.getenv("NEUROKEY_MOBILE_PORT", "8765"))
    server = await websockets.serve(handler, "0.0.0.0", port)
    log.info(f"============================================================")
    log.info(f" NeuroKey Mobile Bridge Server ISHGA TUSHDI")
    log.info(f" WebSocket manzili: ws://0.0.0.0:{port}")
    log.info(f" Kompyuterni telefondan boshqarish va ekran oqimi tayyor.")
    log.info(f"============================================================")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
