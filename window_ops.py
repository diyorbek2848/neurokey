# -*- coding: utf-8 -*-
"""NeuroKey — Oynalar boshqaruvi. list, focus, minimize, maximize, close, by_title."""

from __future__ import annotations

import sys
import ctypes
from typing import Any, Dict, List, Optional, Tuple

if sys.platform == "win32":
    try:
        import pygetwindow as gw
        _HAVE_PYGETWINDOW = True
    except ImportError:
        gw = None
        _HAVE_PYGETWINDOW = False
else:
    gw = None
    _HAVE_PYGETWINDOW = False


def _hwnd_from_window(win: Any) -> Optional[int]:
    """Window objectdan hwnd olish (pygetwindow)."""
    if win is None:
        return None
    try:
        return getattr(win, "_hWnd", None) or getattr(win, "hwnd", None)
    except Exception:
        return None


def _is_window_minimized(hwnd: int) -> bool:
    """Windows: oyna minimize bo'lsa True."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        return bool(user32.IsIconic(hwnd))
    except Exception:
        return False


def _is_window_visible(hwnd: int) -> bool:
    """Windows: oyna ko'rinadigan bo'lsa True (IsWindowVisible, minimize emas)."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        if not user32.IsWindowVisible(hwnd):
            return False
        if user32.IsIconic(hwnd):
            return False
        return True
    except Exception:
        return False


def get_visible_windows() -> List[Dict[str, Any]]:
    """Faqat ekranda ko'rinadigan oynalar (IsWindowVisible, !IsIconic). visible_only pipeline."""
    if not _HAVE_PYGETWINDOW or not gw:
        return []
    try:
        wins = gw.getAllWindows()
        out: List[Dict[str, Any]] = []
        for w in wins:
            try:
                hwnd = _hwnd_from_window(w)
                if not hwnd:
                    continue
                if not _is_window_visible(int(hwnd)):
                    continue
                title = (getattr(w, "title", None) or "").strip()
                if not title:
                    continue
                out.append({"hwnd": int(hwnd), "title": title})
            except Exception:
                pass
        return out
    except Exception:
        return []


def window_list() -> List[Dict[str, Any]]:
    """Barcha ko'rinadigan (minimize emas) oynalar ro'yxati. [{"hwnd": int, "title": str}, ...]"""
    if not _HAVE_PYGETWINDOW or not gw:
        return []
    try:
        wins = gw.getAllWindows()
        out: List[Dict[str, Any]] = []
        for w in wins:
            try:
                if not getattr(w, "visible", True):
                    continue
                hwnd = _hwnd_from_window(w)
                if not hwnd:
                    continue
                if sys.platform == "win32" and _is_window_minimized(int(hwnd)):
                    continue
                title = (getattr(w, "title", None) or "").strip()
                out.append({"hwnd": int(hwnd), "title": title or "(no title)"})
            except Exception:
                pass
        return out
    except Exception:
        return []


def window_focus(hwnd_or_title: Any) -> bool:
    """Oynani oldinga olib chiqish (svernutiy bo'lsa tepaga ko'taradi)."""
    if not _HAVE_PYGETWINDOW or not gw:
        return False
    try:
        # Check if argument is title (str) or hwnd (int)
        if isinstance(hwnd_or_title, str):
            wins = gw.getWindowsWithTitle(hwnd_or_title)
        else:
            wins = gw.getWindowsWithTitle("")
            wins = [w for w in wins if _hwnd_from_window(w) == hwnd_or_title]
            
        if not wins:
            return False
            
        w = wins[0]
        hwnd = _hwnd_from_window(w)
        
        # Tasdiqlash Qatlami: Agar oyna pastga tushirilgan (minimized) bo'lsa, uni restore qilamiz
        if hwnd and _is_window_minimized(int(hwnd)):
            if sys.platform == "win32":
                user32 = ctypes.windll.user32
                user32.ShowWindow(int(hwnd), 9) # SW_RESTORE = 9
                
        w.activate()
        return True
    except Exception as e:
        return False


def window_minimize(hwnd: int) -> bool:
    """Oynani minimize qilish."""
    if not _HAVE_PYGETWINDOW or not gw:
        return False
    try:
        wins = gw.getWindowsWithTitle("")
        for w in wins:
            if _hwnd_from_window(w) == hwnd:
                w.minimize()
                return True
        return False
    except Exception:
        return False


def window_maximize(hwnd: int) -> bool:
    """Oynani maximize qilish."""
    if not _HAVE_PYGETWINDOW or not gw:
        return False
    try:
        wins = gw.getWindowsWithTitle("")
        for w in wins:
            if _hwnd_from_window(w) == hwnd:
                w.maximize()
                return True
        return False
    except Exception:
        return False


def window_close(hwnd: int) -> bool:
    """Oynani yopish (WM_CLOSE)."""
    if not _HAVE_PYGETWINDOW or not gw:
        return False
    try:
        wins = gw.getWindowsWithTitle("")
        for w in wins:
            if _hwnd_from_window(w) == hwnd:
                w.close()
                return True
        return False
    except Exception:
        return False


def window_by_title(title: str, partial: bool = True) -> List[Dict[str, Any]]:
    """Sarlavha bo'yicha oynalarni topish. partial=True — qisman moslash."""
    if not _HAVE_PYGETWINDOW or not gw:
        return []
    title = (title or "").strip()
    if not title:
        return []
    try:
        wins = gw.getWindowsWithTitle(title)
        if not partial:
            wins = [w for w in wins if (getattr(w, "title", None) or "").strip() == title]
        out: List[Dict[str, Any]] = []
        for w in wins:
            try:
                t = (getattr(w, "title", None) or "").strip()
                hwnd = _hwnd_from_window(w)
                if hwnd:
                    out.append({"hwnd": int(hwnd), "title": t or "(no title)"})
            except Exception:
                pass
        return out
    except Exception:
        return []
