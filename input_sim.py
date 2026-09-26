# -*- coding: utf-8 -*-
"""NeuroKey — Sichqoncha va klaviatura simulyatsiya. mouse_move, click, key_press, key_type, hotkey."""

from __future__ import annotations

from typing import Optional, Tuple

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    _HAVE_PYAUTOGUI = True
except ImportError:
    pyautogui = None
    _HAVE_PYAUTOGUI = False


def mouse_move(x: int, y: int) -> bool:
    """Sichqonchani (x, y) ga ko'chirish."""
    if not _HAVE_PYAUTOGUI or not pyautogui:
        return False
    try:
        pyautogui.moveTo(x, y, duration=0.1)
        return True
    except Exception:
        return False


def mouse_click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> bool:
    """Click. (x,y) berilsa — o'sha joyda, aks holda — joriy joyda."""
    if not _HAVE_PYAUTOGUI or not pyautogui:
        return False
    try:
        if x is not None and y is not None:
            pyautogui.click(x, y, button=button)
        else:
            pyautogui.click(button=button)
        return True
    except Exception:
        return False


def mouse_double_click(x: Optional[int] = None, y: Optional[int] = None) -> bool:
    """Ikki marta click."""
    if not _HAVE_PYAUTOGUI or not pyautogui:
        return False
    try:
        if x is not None and y is not None:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.doubleClick()
        return True
    except Exception:
        return False


def key_press(key: str) -> bool:
    """Tugma bosish (keydown + keyup). Masalan: 'enter', 'tab', 'space'."""
    if not _HAVE_PYAUTOGUI or not pyautogui:
        return False
    try:
        pyautogui.press(key)
        return True
    except Exception:
        return False


def key_type(text: str, interval: float = 0.05) -> bool:
    """Matn yozish (har bir belgi uchun key_press)."""
    if not _HAVE_PYAUTOGUI or not pyautogui:
        return False
    try:
        pyautogui.write(text, interval=interval)
        return True
    except Exception:
        return False


def hotkey(*keys: str) -> bool:
    """Bir nechta tugmani birga bosish. Masalan: hotkey('ctrl', 'c'), hotkey('alt', 'f4')."""
    if not _HAVE_PYAUTOGUI or not pyautogui:
        return False
    try:
        pyautogui.hotkey(*keys)
        return True
    except Exception:
        return False
