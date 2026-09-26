# -*- coding: utf-8 -*-
"""Qatlam 1: Complex pattern-matching — parallel oqimlar (7+ stream).

Kompyuter holati, foydalanuvchi, ekran, xotira, fayllar, protsesslar, vaqt — hammasi.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from process_ops import list_all as process_list_all
    _HAVE_PROCESS = True
except ImportError:
    _HAVE_PROCESS = False

try:
    import pyperclip
    _HAVE_CLIPBOARD = True
except ImportError:
    _HAVE_CLIPBOARD = False


def get_perception_streams(
    user_input: str = "",
    screen_context: str = "",
    memory_summary: str = "",
    current_folder: str = "",
    app_dir: str = "",
) -> Dict[str, Any]:
    """Parallel oqimlar — perception (Qatlam 1). 7+ stream."""
    streams: Dict[str, Any] = {
        "user": (user_input or "").strip()[:500],
        "screen": (screen_context or "").strip()[:800],
        "memory": (memory_summary or "").strip()[:600],
        "files": "",
        "processes": "",
        "time": "",
        "clipboard": "",
    }
    # Files — current folder yoki Documents
    try:
        base = current_folder or os.path.expanduser("~\\Documents")
        if os.path.isdir(base):
            items = os.listdir(base)[:15]
            streams["files"] = ", ".join(items[:10]) if items else "(bo'sh)"
    except Exception:
        streams["files"] = ""
    # Processes — ishlayotgan dasturlar
    if _HAVE_PROCESS:
        try:
            procs = process_list_all()
            names = list({(p.get("name") or "").strip() for p in procs[:30] if p.get("name")})[:15]
            streams["processes"] = ", ".join(names) if names else ""
        except Exception:
            streams["processes"] = ""
    # Time
    streams["time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Clipboard
    if _HAVE_CLIPBOARD:
        try:
            cb = (pyperclip.paste() or "").strip()[:200]
            streams["clipboard"] = cb if cb else ""
        except Exception:
            streams["clipboard"] = ""
    return streams
