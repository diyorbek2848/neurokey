# -*- coding: utf-8 -*-
"""
avatar_window.py — NeuroKey VRM Avatar Desktop Pet

Transparent, frameless, always-on-top oyna.
Three.js + VRM model ichida anime personaj.

Ishga tushirish:
  python avatar_window.py              # default (idle)
  python avatar_window.py --debug      # debug rejimi (devtools)
  python avatar_window.py --state thinking
"""

from __future__ import annotations

import argparse
import ctypes
import http.server
import json
import os
import socket
import sys
import threading
import time

# ─── pywebview ───────────────────────────────────────────────────────────────
try:
    import webview
    _WEBVIEW_OK = True
except ImportError:
    _WEBVIEW_OK = False
    print("[!] pywebview o'rnatilmagan. O'rnatilmoqda...")
    ret = os.system(f'"{sys.executable}" -m pip install pywebview')
    if ret == 0:
        import webview
        _WEBVIEW_OK = True
    else:
        print("[XATO] pip install pywebview muvaffaqiyatsiz")
        sys.exit(1)

# ─── win32 ───────────────────────────────────────────────────────────────────
try:
    import win32gui
    import win32con
    import win32api
    _WIN32_OK = True
except ImportError:
    _WIN32_OK = False

# ─── Manzillar ───────────────────────────────────────────────────────────────
_BASE      = os.path.dirname(os.path.abspath(__file__))
HTML_PATH  = os.path.join(_BASE, "neurokey_avatar.html")
STATE_FILE = os.path.join(_BASE, "data", "neurokey_state.json")
ASSETS_DIR = os.path.join(_BASE, "assets")

# ─── Local HTTP server (file:// CORS muammosini hal qilish) ──────────────────
_SERVER_PORT = None

def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]

class _NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """Kesh o'chirilgan HTTP handler — yangi HTML har doim yuklanadi."""
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    def log_message(self, *a):
        pass  # logni o'chirish

def _start_http_server(port: int):
    """_BASE papkasini localhost:PORT orqali xizmat qiladi."""
    os.chdir(_BASE)
    srv = http.server.HTTPServer(('127.0.0.1', port), _NoCacheHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv

WIN_W = 320
WIN_H = 580

# ─────────────────────────────────────────────────────────────────────────────
# Python ↔ JS ko'prik (pywebview JS API)
# ─────────────────────────────────────────────────────────────────────────────
class AvatarJSAPI:
    """
    Python da chaqiriladigan metodlar.
    pywebview js_api sifatida uzatiladi.
    JS tomondan: window.pywebview.api.method_name(args)
    """

    def __init__(self):
        self._window = None
        self._drag_x = 0
        self._drag_y = 0

    def _set_window(self, w):
        self._window = w

    # ── JS chaqiradigan metodlar ──────────────────────────────────────────────

    def drag_start(self, sx: int, sy: int):
        """JS tomondan: drag boshlanganda ekran koordinatalari."""
        if self._window:
            self._drag_x = sx - self._window.x
            self._drag_y = sy - self._window.y

    def get_state(self) -> str:
        """Joriy NeuroKey holati."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    d = json.load(f)
                return d.get("state", "idle")
        except Exception:
            pass
        return "idle"


# ─────────────────────────────────────────────────────────────────────────────
# Avatar oyna
# ─────────────────────────────────────────────────────────────────────────────
class AvatarWindow:

    def __init__(self, initial_state: str = "idle", debug: bool = False):
        self._state   = initial_state
        self._debug   = debug
        self._window  = None
        self._api     = AvatarJSAPI()
        self._hwnd    = None
        self._running = False

    # ── Ekran o'lchami ────────────────────────────────────────────────────────
    @staticmethod
    def _screen_size():
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    # ── Oynani ishga tushirish ─────────────────────────────────────────────────
    def start(self):
        """Bloklovchi — asosiy thread da chaqiring."""
        self._running = True

        # Modelni tekshirish
        vrm_path = os.path.join(ASSETS_DIR, "avatar.vrm")
        if not os.path.exists(vrm_path):
            print(f"[!] Model topilmadi: {vrm_path}")
            import download_avatar
            ok = download_avatar.download()
            if not ok:
                print("[XATO] Model yuklanmadi.")
                return

        # Local HTTP server ishga tushirish (CORS muammosini hal qiladi)
        global _SERVER_PORT
        _SERVER_PORT = _find_free_port()
        _start_http_server(_SERVER_PORT)
        html_url = f"http://127.0.0.1:{_SERVER_PORT}/neurokey_avatar.html?v={int(time.time())}"
        print(f"[HA] HTTP server: http://127.0.0.1:{_SERVER_PORT}")
        print(f"[i]  URL: {html_url}")

        # Oyna joylashuvi (o'ng pastki burchak)
        sw, sh = self._screen_size()
        wx = sw - WIN_W - 18
        wy = sh - WIN_H - 56

        # pywebview oyna yaratish
        self._window = webview.create_window(
            title        = "NeuroKey",
            url          = html_url,
            width        = WIN_W,
            height       = WIN_H,
            x            = wx,
            y            = wy,
            frameless    = True,
            on_top       = True,
            transparent  = True,
            resizable    = False,
            shadow       = False,
            easy_drag    = False,       # o'zimiz drag boshqaramiz
            js_api       = self._api,
            min_size     = (WIN_W, WIN_H),
        )
        self._api._set_window(self._window)

        # Event handlerlari
        self._window.events.loaded  += self._on_loaded
        self._window.events.closed  += self._on_closed

        # NeuroKey state sync thread
        t = threading.Thread(target=self._sync_loop, daemon=True)
        t.start()

        # pywebview main loop (bloklovchi)
        webview.start(debug=self._debug)

    # ── Oyna yuklanganda ──────────────────────────────────────────────────────
    def _on_loaded(self):
        time.sleep(0.4)   # WebView2 o'rnatilishini kutish

        # Win32: oynani doim ustda qilish + layered
        self._apply_win32()

        # Boshlang'ich holat
        self._set_anim(self._state)
        print(f"[HA] Avatar tayyor. Holat: {self._state}")

    def _on_closed(self):
        self._running = False
        print("[i] Avatar yopildi.")

    # ── Win32 oyna xususiyatlari ───────────────────────────────────────────────
    def _apply_win32(self):
        if not _WIN32_OK:
            return
        try:
            # "NeuroKey" nomli oynani topish
            hwnd = win32gui.FindWindow(None, "NeuroKey")
            if not hwnd:
                # Boshqa yo'l bilan qidirish
                def _enum(h, _):
                    if "NeuroKey" in win32gui.GetWindowText(h):
                        self._hwnd = h
                win32gui.EnumWindows(_enum, None)
                hwnd = self._hwnd
            else:
                self._hwnd = hwnd

            if hwnd:
                # EX_LAYERED qo'shish (shaffoflik uchun)
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(
                    hwnd, win32con.GWL_EXSTYLE,
                    ex | win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST
                )
                # Doim ustda
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
                # Qora piksellarni shaffof qilish (LWA_COLORKEY)
                # crKey=0 → #000000 (qora), LWA_COLORKEY=1
                try:
                    win32api.SetLayeredWindowAttributes(hwnd, 0, 0, win32con.LWA_COLORKEY)
                    print("[HA] Shaffoflik (LWA_COLORKEY) qo'yildi")
                except Exception as _e:
                    print(f"[!] SetLayeredWindowAttributes xato: {_e}")
                print(f"[HA] Win32 sozlandi. HWND={hwnd}")
            else:
                print("[!] HWND topilmadi — win32 sozlash o'tkazib yuborildi")
        except Exception as e:
            print(f"[!] Win32 sozlash xatosi: {e}")

    # ── JS chaqirish ─────────────────────────────────────────────────────────
    def _js(self, code: str):
        if self._window:
            try:
                self._window.evaluate_js(code)
            except Exception as e:
                pass   # oyna yopilayotganda xato normal

    def _set_anim(self, state: str):
        """Animatsiya holatini o'zgartirish."""
        anim_map = {
            "idle":      "idle",
            "listening": "idle",
            "thinking":  "thinking",
            "speaking":  "speaking",
            "loading":   "thinking",
            "walking":   "walking",
            "happy":     "happy",
            "surprised": "surprised",
            "error":     "thinking",
        }
        anim = anim_map.get(state, "idle")
        self._js(f'window.setAnimation("{anim}")')

        # Gapirayotganda lip sync yoqish
        lip = "1.0" if state == "speaking" else "0.0"
        self._js(f'window.setLipSync({lip})')

    # ── NeuroKey state sync ───────────────────────────────────────────────────
    def _sync_loop(self):
        """data/neurokey_state.json ni o'qib holat sinxronlaydi."""
        prev = None
        while self._running:
            try:
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    raw = data.get("state", "idle")
                    if raw != prev:
                        prev = raw
                        self._state = raw
                        self._set_anim(raw)
            except Exception:
                pass
            time.sleep(0.4)

    # ── Public API ────────────────────────────────────────────────────────────
    def set_state(self, state: str):
        """Tashqaridan holat o'zgartirish."""
        self._state = state
        self._set_anim(state)

    def set_lip_sync(self, val: float):
        """0.0–1.0 oralig'ida lip sync qiymati."""
        self._js(f'window.setLipSync({max(0.0, min(1.0, val))})')

    def set_expression(self, name: str, val: float):
        """VRM expression: happy, sad, angry, surprised, relaxed, ..."""
        self._js(f'window.setExpression("{name}", {max(0.0, min(1.0, val))})')

    def stop(self):
        """Oynani yopish."""
        self._running = False
        if self._window:
            self._window.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Kirish nuqtasi
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="NeuroKey VRM Avatar")
    ap.add_argument("--state", default="idle",
                    choices=["idle","thinking","speaking","walking","happy","surprised"],
                    help="Boshlang'ich holat")
    ap.add_argument("--debug", action="store_true",
                    help="Debug rejimi (F12 DevTools)")
    ap.add_argument("--download", action="store_true",
                    help="Modelni yuklab olish va chiqish")
    args = ap.parse_args()

    if args.download:
        import download_avatar
        download_avatar.download()
        return

    print("=" * 50)
    print("  NeuroKey Avatar")
    print("=" * 50)
    print(f"  Holat    : {args.state}")
    print(f"  Debug    : {args.debug}")
    print(f"  HTML     : {HTML_PATH}")
    print(f"  Model    : {os.path.join(ASSETS_DIR, 'avatar.vrm')}")
    print("=" * 50)

    av = AvatarWindow(initial_state=args.state, debug=args.debug)
    av.start()


if __name__ == "__main__":
    main()
