# -*- coding: utf-8 -*-
"""NeuroKey — Bufer almashtirish. get, set (matn)."""

from __future__ import annotations

from typing import Optional

try:
    import pyperclip
    _HAVE_PYPERCLIP = True
except ImportError:
    pyperclip = None
    _HAVE_PYPERCLIP = False


def clipboard_get() -> Optional[str]:
    """Buferdan matn olish."""
    if not _HAVE_PYPERCLIP or not pyperclip:
        return None
    try:
        return pyperclip.paste()
    except Exception:
        return None


def clipboard_set(text: str) -> bool:
    """Matnni buferga nusxalash."""
    if not _HAVE_PYPERCLIP or not pyperclip:
        return False
    try:
        pyperclip.copy(text or "")
        return True
    except Exception:
        return False
