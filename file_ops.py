# -*- coding: utf-8 -*-
"""NeuroKey — Fayl operatsiyalari. To'g'ridan-to'g'ri, control dan mustaqil.

Har qanday path. Cheklov yo'q. Path berilsa — bajaradi.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
from typing import List, Optional


def read(path: str) -> str:
    """Fayl ichini o'qiydi. Path — har qanday."""
    if not path or not isinstance(path, str):
        return ""
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Fayl topilmadi: {path}")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write(path: str, content: str) -> bool:
    """Fayl ichiga yozadi. Mavjud bo'lsa — ustiga."""
    if not path or not isinstance(path, str):
        return False
    path = os.path.normpath(path)
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content or "")
        return True
    except (OSError, IOError):
        return False


def append(path: str, content: str) -> bool:
    """Fayl oxiriga qo'shadi."""
    if not path or not isinstance(path, str):
        return False
    path = os.path.normpath(path)
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content or "")
        return True
    except (OSError, IOError):
        return False


def rename(old_path: str, new_path: str) -> bool:
    """Fayl yoki papka nomini o'zgartiradi."""
    if not old_path or not new_path:
        return False
    old_path = os.path.normpath(old_path)
    new_path = os.path.normpath(new_path)
    if not os.path.exists(old_path):
        return False
    try:
        os.rename(old_path, new_path)
        return True
    except (OSError, IOError):
        return False


def delete(path: str) -> bool:
    """Fayl yoki papkani o'chiradi. Papka — ichi bilan."""
    if not path or not isinstance(path, str):
        return False
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return True
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return True
    except (OSError, IOError):
        return False


def create(path: str) -> bool:
    """Yangi bo'sh fayl yaratadi."""
    if not path or not isinstance(path, str):
        return False
    path = os.path.normpath(path)
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            pass
        return True
    except (OSError, IOError):
        return False


def copy(src: str, dst: str) -> bool:
    """Faylni boshqa joyga nusxalaydi."""
    if not src or not dst:
        return False
    src = os.path.normpath(src)
    dst = os.path.normpath(dst)
    if not os.path.exists(src):
        return False
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            d = os.path.dirname(dst)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            shutil.copy2(src, dst)
        return True
    except (OSError, IOError):
        return False


def move(src: str, dst: str) -> bool:
    """Fayl yoki papkani ko'chiradi."""
    if not src or not dst:
        return False
    src = os.path.normpath(src)
    dst = os.path.normpath(dst)
    if not os.path.exists(src):
        return False
    try:
        d = os.path.dirname(dst)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        shutil.move(src, dst)
        return True
    except (OSError, IOError):
        return False


def exists(path: str) -> bool:
    """Fayl yoki papka mavjudmi."""
    if not path or not isinstance(path, str):
        return False
    return os.path.exists(os.path.normpath(path))


def list_dir(path: str) -> List[str]:
    """Papkadagi fayl va papkalar ro'yxati."""
    if not path or not isinstance(path, str):
        return []
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return []
    try:
        return os.listdir(path)
    except (OSError, PermissionError):
        return []


def search(root: str, pattern: str, max_results: int = 500) -> List[str]:
    """Root ostida pattern bo'yicha qidirish. fnmatch: *.txt, *doc*."""
    if not root or not isinstance(root, str):
        return []
    root = os.path.normpath(root)
    if not os.path.isdir(root):
        return []
    pattern = pattern or "*"
    results: List[str] = []
    try:
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    results.append(os.path.join(dirpath, name))
                    if len(results) >= max_results:
                        return results
    except (OSError, PermissionError):
        pass
    return results


def get_size(path: str) -> int:
    """Fayl hajmi (bayt). Papka — 0."""
    if not path or not os.path.isfile(path):
        return 0
    try:
        return os.path.getsize(path)
    except (OSError, IOError):
        return 0


def get_modified(path: str) -> float:
    """Oxirgi o'zgarish vaqti (timestamp)."""
    if not path or not os.path.exists(path):
        return 0.0
    try:
        return os.path.getmtime(path)
    except (OSError, IOError):
        return 0.0
