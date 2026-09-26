# -*- coding: utf-8 -*-
"""NeuroKey — Dynamic Organ Genesis (SUNIY ONG).

SUNIY ONG: Agent emas, kodlar yig'indisi emas — ong. DYNAMIC ORGAN GENESIS: NeuroKey o'ziga yangi raqamli organlar (funksiyalar) yaratadi.
Yangi muammoga duch kelsa — tayyor yechim qidirmaydi. Yangi algoritmni o'zi ixtiro qiladi
va Hot-Reload orqali bir zumda o'ziga ulaydi. evolve_create_organ() orqali organ_*.py yaratiladi,
reload_organs() bilan darhol tizimga ulanadi. Ular fayl emas — tizimning tirik hujayralari.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Callable, Dict, List, Optional, Tuple

_ORGANS: List[Tuple[str, object]] = []  # (name, module)
_HANDLERS: List[Callable[[str], Optional[str]]] = []


def _organs_dir() -> str:
    root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, "neurokey_organs")


def load_organs() -> Tuple[int, List[str]]:
    """
    neurokey_organs/ dagi barcha organ_*.py larni dynamic import qiladi.
    Qaytadi: (loaded_count, errors).
    """
    global _ORGANS, _HANDLERS
    _ORGANS = []
    _HANDLERS = []
    errors = []
    organs_dir = _organs_dir()
    if not os.path.isdir(organs_dir):
        return 0, []

    for name in sorted(os.listdir(organs_dir)):
        if not name.startswith("organ_") or not name.endswith(".py"):
            continue
        mod_name = name[:-3]
        path = os.path.join(organs_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if not spec or not spec.loader:
                continue
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            _ORGANS.append((mod_name, mod))
            handler = getattr(mod, "organ_handle", None)
            if callable(handler):
                _HANDLERS.append(handler)
        except Exception as e:
            errors.append(f"{name}: {e}")

    return len(_HANDLERS), errors


def dispatch_to_organs(text: str) -> Optional[str]:
    """
    Matnni organlarga yuboradi. Birinchi javob bergan organ natijasini qaytaradi.
    """
    for handler in _HANDLERS:
        try:
            out = handler(text)
            if out is not None and str(out).strip():
                return str(out).strip()
        except Exception:
            pass
    return None


def get_loaded_organs() -> List[str]:
    """Yuklangan organlar ro'yxati."""
    return [n for n, _ in _ORGANS]


def reload_organs() -> Tuple[int, List[str]]:
    """Organlarni qayta yuklash (yangi organ qo'shilganda)."""
    return load_organs()
