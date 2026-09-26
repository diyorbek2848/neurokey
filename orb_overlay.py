# -*- coding: utf-8 -*-
"""Vizual Orb (Jarvis-style overlay): shaffof, animatsiyali doira.
Gapirganda — pulsatsiya, tinglayotganda — rang o'zgaradi.
Tkinter, qo'shimcha kutubxona yo'q."""

from __future__ import annotations

import math
import threading
import time
import tkinter as tk
from typing import Optional

ORB_IDLE_COLOR = "#1a7f37"      # yashil
ORB_LISTENING_COLOR = "#2563eb" # ko'k (tinglayapti)
ORB_SPEAKING_COLOR = "#7c3aed"  # binafsha (gapiryapti)
ORB_SIZE = 56
ORB_PULSE_MIN = 0.85
ORB_PULSE_MAX = 1.15
FPS = 24


class OrbOverlay:
    def __init__(
        self,
        size: int = ORB_SIZE,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ):
        self.size = size
        self.x = x  # None = o'ng past
        self.y = y
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._state = "idle"  # idle | listening | speaking
        self._pulse_phase = 0.0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._after_id: Optional[str] = None

    def _place_window(self) -> None:
        if self._root is None:
            return
        w, h = self.size + 20, self.size + 20
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = self.x if self.x is not None else max(0, sw - w - 24)
        y = self.y if self.y is not None else max(0, sh - h - 80)
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    def _draw_orb(self) -> None:
        if self._canvas is None:
            return
        self._canvas.delete("all")
        cx = (self.size + 20) // 2
        cy = (self.size + 20) // 2
        if self._state == "speaking":
            scale = ORB_PULSE_MIN + (ORB_PULSE_MAX - ORB_PULSE_MIN) * (0.5 + 0.5 * math.sin(self._pulse_phase))
            r = (self.size / 2) * scale
            color = ORB_SPEAKING_COLOR
        elif self._state == "listening":
            color = ORB_LISTENING_COLOR
            r = self.size / 2
        else:
            color = ORB_IDLE_COLOR
            r = self.size / 2
        self._canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline=color, width=0)
        self._pulse_phase += 0.35

    def _tick(self) -> None:
        if self._root is None or self._stop.is_set():
            return
        try:
            self._draw_orb()
            self._after_id = self._root.after(max(1, 1000 // FPS), self._tick)
        except Exception:
            pass

    def set_state(self, state: str) -> None:
        """state: 'idle' | 'listening' | 'speaking'"""
        if state in ("idle", "listening", "speaking"):
            self._state = state

    def run(self) -> None:
        self._root = tk.Tk()
        self._root.title("NeuroKey Orb")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.92)
        self._root.configure(bg="black")
        self._root.wm_attributes("-transparentcolor", "black")
        self._place_window()
        self._canvas = tk.Canvas(
            self._root,
            width=self.size + 20,
            height=self.size + 20,
            bg="black",
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._draw_orb()
        self._tick()
        try:
            self._root.mainloop()
        finally:
            self._after_id = None

    def start_background(self) -> None:
        def run():
            self.run()
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        time.sleep(0.3)

    def quit(self) -> None:
        self._stop.set()
        if self._root:
            try:
                if self._after_id:
                    self._root.after_cancel(self._after_id)
                self._root.quit()
                self._root.destroy()
            except Exception:
                pass
            self._root = None


def create_orb_and_start(x: Optional[int] = None, y: Optional[int] = None) -> Optional[OrbOverlay]:
    """Orb ni ishga tushiradi (background thread). Qaytaradi: OrbOverlay yoki None."""
    try:
        orb = OrbOverlay(x=x, y=y)
        orb.start_background()
        return orb
    except Exception:
        return None
