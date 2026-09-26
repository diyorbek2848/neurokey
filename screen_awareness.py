# -*- coding: utf-8 -*-
"""NeuroKey — Ekran ongi (Screen Awareness).

NeuroKey ekranda nima bo'layotganini to'liq bilishi kerak:
  - Hozir QAYSI oyna faol (foreground)?
  - Qaysi oynalar ochiq, qaysilari minimize (svernutiy)?
  - Qaysi oyna maximize (razvernutiy)?
  - Faol oynada nima yozilgan (OCR)?

window_ops da primitivlar bor edi (minimize/maximize aniqlash), lekin
yagona to'liq holat rasmini beradigan qatlam yo'q edi. Bu modul shuni
beradi — bir chaqiruvda butun ekran holati.

Windows-first (win32gui). Boshqa OSlarda qisman ishlaydi.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger(__name__)

_IS_WIN = sys.platform == "win32"

try:
    import win32gui
    import win32con
    _WIN32 = True
except Exception:
    _WIN32 = False


@dataclass
class WindowState:
    hwnd: int
    title: str
    state: str        # active | maximized | minimized | normal
    is_foreground: bool = False


@dataclass
class ScreenState:
    active_title: str = ""
    active_state: str = ""
    windows: List[WindowState] = field(default_factory=list)
    minimized: List[str] = field(default_factory=list)
    maximized: List[str] = field(default_factory=list)
    open_count: int = 0

    def summary(self) -> str:
        """Qisqa, LLM uchun bir-ikki qatorli ekran holati."""
        parts = [f"[EKRAN] Faol: {self.active_title[:50] or '(nomsiz)'}"]
        if self.active_state and self.active_state != "active":
            parts[0] += f" ({self.active_state})"
        vis = [w.title for w in self.windows
               if w.state in ("normal", "maximized", "active") and w.title]
        if vis:
            parts.append("Ochiq: " + ", ".join(t[:24] for t in vis[:4]))
        if self.minimized:
            parts.append("Svernutiy: " + ", ".join(t[:20] for t in self.minimized[:3]))
        return " | ".join(parts)


def _window_placement_state(hwnd: int) -> str:
    """Oynaning holati: maximized | minimized | normal."""
    if not _WIN32:
        return "normal"
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        show = placement[1]
        if show == win32con.SW_SHOWMINIMIZED:
            return "minimized"
        if show == win32con.SW_SHOWMAXIMIZED:
            return "maximized"
        return "normal"
    except Exception:
        return "normal"


def get_screen_state() -> ScreenState:
    """Butun ekran holatini bir chaqiruvda qaytaradi."""
    st = ScreenState()
    if not _WIN32:
        # Zaxira: window_ops orqali cheklangan ma'lumot
        try:
            import window_ops as wo
            wins = wo.window_list() or []
            st.windows = [WindowState(w.get("hwnd", 0), w.get("title", ""), "normal")
                          for w in wins if w.get("title")]
            st.open_count = len(st.windows)
        except Exception as e:
            log.warning("[EkranOng] window_ops zaxira xato: %s", e)
        return st

    try:
        fg_hwnd = win32gui.GetForegroundWindow()
    except Exception:
        fg_hwnd = 0

    def _enum(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                # minimize bo'lgan oynalar ham hisobga olinsin
                if not win32gui.IsIconic(hwnd):
                    return
            title = win32gui.GetWindowText(hwnd) or ""
            if not title.strip():
                return
            state = _window_placement_state(hwnd)
            is_fg = (hwnd == fg_hwnd)
            if is_fg and state != "minimized":
                state_label = "active"
            else:
                state_label = state
            ws = WindowState(hwnd, title, state_label, is_fg)
            st.windows.append(ws)
            if state == "minimized":
                st.minimized.append(title)
            elif state == "maximized":
                st.maximized.append(title)
            if is_fg:
                st.active_title = title
                st.active_state = state_label
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_enum, None)
    except Exception as e:
        log.warning("[EkranOng] EnumWindows xato: %s", e)

    st.open_count = len(st.windows)
    return st


def get_active_window_text(max_chars: int = 400) -> str:
    """Faol oynadagi matn — screen_vision OCR orqali."""
    try:
        import screen_vision as sv
        img = sv.grab_screen()
        if img is None:
            return ""
        txt = sv.extract_text_fast(img) or ""
        return txt[:max_chars]
    except Exception as e:
        log.debug("[EkranOng] OCR xato: %s", e)
        return ""


def get_context_for_llm(query: str = "", include_text: bool = False) -> str:
    """Orkestrator uchun ekran holati konteksti.

    include_text=True bo'lsa faol oynadagi matn ham qo'shiladi (sekinroq).
    """
    st = get_screen_state()
    if st.open_count == 0:
        return ""
    line = st.summary()
    if include_text:
        txt = get_active_window_text(200)
        if txt:
            line += f"\n  Matn: {txt[:150]}"
    return line


def get_stats() -> dict:
    st = get_screen_state()
    return {
        "open": st.open_count,
        "active": st.active_title[:40],
        "minimized": len(st.minimized),
        "maximized": len(st.maximized),
        "win32": _WIN32,
    }
