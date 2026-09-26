# -*- coding: utf-8 -*-
"""NeuroKey — Javobni ekranda ko'rsatish. M4 yechimi.

Subtitle pozitsiyasida yoki o'rtada katta ko'rinadi.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class DisplayOverlay:
    """
    Javobni ekranda subtitles kabi ko'rsatadi.
    Ekranning pastki qismida, yarim shaffof, 5s dan keyin yo'qoladi.
    """

    def __init__(self):
        self.root = None
        self.label = None
        self._thread: Optional[threading.Thread] = None
        self._auto_hide_timer = None
        self.is_visible = False
        self._ready = threading.Event()

    def start(self) -> None:
        """Background thread da tkinter window yaratadi."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._init_window, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def _init_window(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            return
        try:
            self.root = tk.Tk()
            self.root.title("")
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.85)
            self.root.configure(bg="black")
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w, h = sw - 200, 120
            x, y = 100, sh - h - 80
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.label = tk.Label(
                self.root,
                text="",
                font=("Segoe UI", 14),
                fg="white",
                bg="black",
                wraplength=sw - 240,
                justify="center",
                padx=20,
                pady=15,
            )
            self.label.pack(fill="both", expand=True)
            self.root.withdraw()
            self._ready.set()
            self.root.mainloop()
        except Exception:
            self._ready.set()

    def show_subtitle(self, text: str, duration: float = 5.0) -> None:
        """Pastda subtitle sifatida ko'rsatadi."""
        if not self.root or not text or not str(text).strip():
            return
        try:
            self.root.after(0, lambda: self._show(str(text).strip()[:500], duration))
        except Exception:
            pass

    def show_fullscreen_result(self, text: str, duration: float = 10.0) -> None:
        """O'rtada katta ko'rsatadi. 'Ekranda ko'rsat' buyrug'i uchun."""
        if not self.root or not text or not str(text).strip():
            return
        try:
            self.root.after(0, lambda: self._show_center(str(text).strip()[:2000], duration))
        except Exception:
            pass

    def _show(self, text: str, duration: float) -> None:
        try:
            self.label.config(text=text, font=("Segoe UI", 14))
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw - 200}x100+100+{sh - 180}")
            self.root.deiconify()
            self.is_visible = True
            if self._auto_hide_timer:
                self.root.after_cancel(self._auto_hide_timer)
            self._auto_hide_timer = self.root.after(int(duration * 1000), self.hide)
        except Exception:
            pass

    def _show_center(self, text: str, duration: float) -> None:
        try:
            self.label.config(text=text, font=("Segoe UI", 18, "bold"))
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w, h = min(sw - 100, 900), 300
            x, y = (sw - w) // 2, (sh - h) // 2
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.deiconify()
            self.is_visible = True
            if self._auto_hide_timer:
                self.root.after_cancel(self._auto_hide_timer)
            self._auto_hide_timer = self.root.after(int(duration * 1000), self.hide)
        except Exception:
            pass

    def hide(self) -> None:
        """Overlay ni yashirish."""
        if self.root:
            try:
                self.root.after(0, self.root.withdraw)
            except Exception:
                pass
            self.is_visible = False
        self._auto_hide_timer = None


_overlay: Optional[DisplayOverlay] = None


def get_display_overlay() -> DisplayOverlay:
    """Singleton."""
    global _overlay
    if _overlay is None:
        _overlay = DisplayOverlay()
    return _overlay
