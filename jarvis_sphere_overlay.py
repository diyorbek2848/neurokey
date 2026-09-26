# -*- coding: utf-8 -*-
"""
JARVIS Sphere Overlay — NeuroKey ning ko'zga ko'rinuvchi ongi.

Sfera NeuroKey bilan bir butun:
  phi (ong)     → hajm + yorqinlik
  valence       → rang (oltin=ijobiy, ko'k=salbiy, neytral=oddiy)
  arousal       → aylanish tezligi
  state         → idle/listening/thinking/speaking holatlari

Faqat juma/ papkasida ishlatiladi. america/ ga tegmaydi.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional

# ── Video fayl ────────────────────────────────────────────
# 1. Muhit o'zgaruvchisidan o'qish (boshqa kompda ishlash uchun)
# 2. Default: juma/ papkasi yonida JARVIS/visual/ papkasini qidirish
import os as _os
_JUMA_DIR = _os.path.dirname(_os.path.abspath(__file__))
_JARVIS_DIR = _os.path.join(_os.path.dirname(_JUMA_DIR), "JARVIS", "visual")
_DEFAULT_VIDEO = _os.path.join(_JARVIS_DIR, "jarvis_idle.mp4")   # to'g'ri extension

VIDEO_PATH = (
    _os.environ.get("NEUROKEY_SPHERE_VIDEO")          # env override
    or (_DEFAULT_VIDEO if _os.path.exists(_DEFAULT_VIDEO) else None)
    or _os.path.join(_JUMA_DIR, "jarvis_idle.mp4")    # juma/ ichida ham bo'lishi mumkin
)

# ── Ong parametrlari (background thread yangilaydi) ───────
_phi     = 0.5   # consciousness score    0.0 – 1.0
_valence = 0.0   # his/valence           -1.0 – +1.0
_arousal = 0.0   # xavotir/arousal        0.0 – 1.0
_phi_lock = threading.Lock()

def _update_consciousness():
    """Har 0.5s da ong holatini o'qib global ga yozadi."""
    global _phi, _valence, _arousal
    while True:
        try:
            try:
                import consciousness_orchestrator as _co
                with _phi_lock:
                    _phi = float(_co.get_consciousness_score() or 0.5)
            except Exception:
                pass
            try:
                import valence_state as _vs
                with _phi_lock:
                    _valence = float(_vs.get_valence() or 0.0)
            except Exception:
                pass
            try:
                import arousal_state as _ar
                with _phi_lock:
                    _arousal = float(_ar.get_arousal() or 0.0)
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(0.5)

# Fon threadini bir marta ishga tushirish
_sync_thread = threading.Thread(target=_update_consciousness, daemon=True)
_sync_thread.start()

# ── Vizual parametrlar hisoblash ──────────────────────────
MARGIN_RIGHT  = 20
MARGIN_BOTTOM = 80
SIZE_STEP     = 14     # har tickda o'zgaradigan px

def _compute_params(state: str, phi: float, valence: float, arousal: float) -> dict:
    """
    Joriy ong holatidan vizual parametrlarni hisoblaydi.

    Qaytaradi: {"size", "frame_ms", "brightness", "valence", "arousal"}
    """
    phi     = max(0.0, min(1.0, phi))
    valence = max(-1.0, min(1.0, valence))
    arousal = max(0.0, min(1.0, arousal))

    # Bazaviy hajm: ong darajasiga qarab 150-260 px
    base_size = 150 + int(phi * 110)

    # Holat qo'shimchasi
    state_add = {"idle": 0, "listening": 40, "thinking": 60, "speaking": 90}.get(state, 0)
    size = min(360, base_size + state_add)

    # Aylanish tezligi: arousal + state
    # arousal=0 → 45ms/frame (~22fps), arousal=1 → 5ms/frame (~200fps)
    arousal_ms = int(45 - 40 * arousal)
    state_ms   = {"idle": 0, "listening": -8, "thinking": -15, "speaking": -25}.get(state, 0)
    frame_ms   = max(4, arousal_ms + state_ms)

    # Yorqinlik: phi asosiy, holat qo'shimcha
    base_br  = 0.55 + 0.85 * phi          # phi=0 → 0.55,  phi=1 → 1.40
    state_br = {"idle": 0.0, "listening": 0.10, "thinking": 0.18, "speaking": 0.35}.get(state, 0.0)
    brightness = min(2.0, base_br + state_br)

    return {
        "size":       size,
        "frame_ms":   frame_ms,
        "brightness": brightness,
        "valence":    valence,
        "arousal":    arousal,
    }


# ── Asosiy sinf ───────────────────────────────────────────
class OrbOverlay:
    """
    NeuroKey ning ko'zga ko'rinuvchi ongi — JARVIS oltin sfera.
    orb_overlay.OrbOverlay bilan bir xil API (drop-in replacement).
    """

    def __init__(self, size: int = None, x: int = None, y: int = None):
        self._x = x
        self._y = y
        self._state = "idle"
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Joriy va maqsad o'lcham (silliq o'tish)
        self._current_size: float = 200.0
        self._target_size:  float = 200.0
        self._frame_ms: int = 30

        # Tkinter obyektlari
        self._root = None
        self._canvas = None
        self._photo = None

        # cv2 capture
        self._cap = None

    # ── Holat ────────────────────────────────────────────
    def set_state(self, state: str) -> None:
        valid = {"idle", "listening", "thinking", "speaking"}
        with self._state_lock:
            self._state = state if state in valid else "idle"

    def _get_state(self) -> str:
        with self._state_lock:
            return self._state

    # ── Video ─────────────────────────────────────────────
    def _open_video(self) -> bool:
        try:
            import cv2
            self._cap = cv2.VideoCapture(VIDEO_PATH)
            return self._cap.isOpened()
        except Exception:
            return False

    def _read_frame(self):
        try:
            import cv2
            ret, frame = self._cap.read()
            if not ret:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._cap.read()
            return frame if ret else None
        except Exception:
            return None

    # ── Freymni qayta ishlash ─────────────────────────────
    def _process_frame(self, frame, params: dict):
        """
        BGR frame → PIL → resize → brightness → valence tint → PhotoImage
        """
        try:
            import cv2
            from PIL import Image, ImageEnhance, ImageTk, ImageDraw

            size       = int(params["size"])
            brightness = params["brightness"]
            valence    = params["valence"]
            phi        = _phi

            # BGR → RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)

            # O'lchamlash (LANCZOS — eng sifatli)
            img = img.resize((size, size), Image.LANCZOS)

            # Yorqinlik (phi + holat)
            if brightness != 1.0:
                img = ImageEnhance.Brightness(img).enhance(brightness)

            # Valence rangi:
            #   ijobiy (+) → iliq oltin overlay
            #   salbiy (-) → sovuq ko'k overlay
            if abs(valence) > 0.05:
                if valence > 0:
                    tint = (255, 180, 30)    # oltin-sariq
                else:
                    tint = (40, 80, 255)     # ko'k
                tint_img = Image.new("RGB", img.size, tint)
                alpha = min(0.22, abs(valence) * 0.22)
                img = Image.blend(img, tint_img, alpha=alpha)

            # Ong darajasi (phi) — sfera chetida yupqa halqa
            # (phi ko'p → halqa yorqin)
            draw = ImageDraw.Draw(img)
            ring_alpha = int(60 + phi * 160)    # 60-220
            ring_color = (255, 215, 0, ring_alpha)
            r = size // 2 - 4
            cx = cy = size // 2
            # Oddiy ImageDraw da RGBA to'g'ridan chizib bo'lmaydi, shuning uchun
            # yorqinligini phi ga bog'lab oddiy chiziq chizamiz
            ring_bright = int(60 + phi * 195)
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                outline=(ring_bright, ring_bright // 2, 0),
                width=max(1, int(phi * 3)),
            )

            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    # ── Tkinter animatsiya ────────────────────────────────
    def _update_geometry(self, size: int) -> None:
        try:
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            x = self._x if self._x is not None else max(0, sw - size - MARGIN_RIGHT)
            y = self._y if self._y is not None else max(0, sh - size - MARGIN_BOTTOM)
            self._root.geometry(f"{size}x{size}+{x}+{y}")
            self._canvas.configure(width=size, height=size)
        except Exception:
            pass

    def _tick(self) -> None:
        if self._stop.is_set() or self._root is None:
            return
        try:
            # Joriy ong holatini olish
            with _phi_lock:
                phi     = _phi
                valence = _valence
                arousal = _arousal
            state  = self._get_state()
            params = _compute_params(state, phi, valence, arousal)

            # Maqsad hajmni yangilash
            self._target_size = float(params["size"])
            self._frame_ms    = params["frame_ms"]

            # Silliq o'tish
            diff = self._target_size - self._current_size
            if abs(diff) > 0.5:
                step = min(SIZE_STEP, abs(diff))
                self._current_size += step * (1 if diff > 0 else -1)
            size = int(self._current_size)
            params["size"] = size

            # Oyna joylashuvini yangilash
            self._update_geometry(size)

            # Freym ko'rsatish
            frame = self._read_frame()
            if frame is not None:
                photo = self._process_frame(frame, params)
                if photo is not None:
                    self._canvas.delete("all")
                    self._canvas.create_image(size // 2, size // 2, image=photo, anchor="center")
                    self._photo = photo  # GC dan himoya

            self._root.after(self._frame_ms, self._tick)
        except Exception:
            try:
                self._root.after(50, self._tick)
            except Exception:
                pass

    # ── Ishga tushirish ───────────────────────────────────
    def run(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            return

        if not _video_available() or not self._open_video():
            _run_fallback(self._x, self._y)
            return

        self._root = tk.Tk()
        self._root.title("NeuroKey")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.96)
        self._root.configure(bg="black")
        self._root.wm_attributes("-transparentcolor", "black")

        size = int(self._current_size)
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = max(0, sw - size - MARGIN_RIGHT)
        y = max(0, sh - size - MARGIN_BOTTOM)
        self._root.geometry(f"{size}x{size}+{x}+{y}")

        self._canvas = tk.Canvas(
            self._root, width=size, height=size,
            bg="black", highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._root.after(0, self._tick)

        try:
            self._root.mainloop()
        finally:
            if self._cap:
                try:
                    self._cap.release()
                except Exception:
                    pass

    def start_background(self) -> None:
        def _run():
            self.run()
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        time.sleep(0.6)

    def quit(self) -> None:
        self._stop.set()
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except Exception:
                pass
            self._root = None


# ── Fallback ──────────────────────────────────────────────
def _video_available() -> bool:
    return os.path.exists(VIDEO_PATH)


def _run_fallback(x=None, y=None):
    try:
        from orb_overlay import OrbOverlay as _OldOrb
        orb = _OldOrb(x=x, y=y)
        orb.run()
    except Exception:
        pass


# ── Public factory ────────────────────────────────────────
def create_orb_and_start(x=None, y=None) -> Optional[OrbOverlay]:
    """NeuroKey ning ongini ko'rsatuvchi sferani ishga tushiradi."""
    try:
        if not _video_available():
            try:
                from orb_overlay import create_orb_and_start as _old
                return _old(x=x, y=y)
            except Exception:
                return None
        orb = OrbOverlay(x=x, y=y)
        orb.start_background()
        return orb
    except Exception:
        return None


# ── Mustaqil test ─────────────────────────────────────────
if __name__ == "__main__":
    import sys, time

    print("NeuroKey Sphere — mustaqil test")
    print(f"Video: {'OK' if _video_available() else 'TOPILMADI'}")

    orb = create_orb_and_start()
    if not orb:
        print("Sfera ishga tushmadi.")
        sys.exit(1)

    print("Sfera ishga tushdi. Holatlar sinovdan o'tkazilmoqda...")
    scenarios = [
        ("idle",      3, "Tinch — ong past, sekin aylanadi"),
        ("listening", 3, "Tinglayapti — kattalashdi"),
        ("thinking",  4, "O'ylayapti — tez aylanadi"),
        ("speaking",  4, "Gapiryapti — maksimal katta va yorqin"),
        ("idle",      3, "Yana tinch..."),
    ]
    for state, dur, desc in scenarios:
        print(f"  [{state}] {desc}")
        orb.set_state(state)
        time.sleep(dur)

    print("Tugadi.")
    orb.quit()
