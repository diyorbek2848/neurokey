# -*- coding: utf-8 -*-
"""NeuroKey — MA'LUMOTLAR BAZASI (Knowledge Base).

Eng katta ma'lumotlar bazasi — data/knowledge/ papkasidagi barcha fayllar.
.txt, .md — LLM kontekstiga qo'shiladi. Foydalanuvchi o'zi qo'shadi.
"""

from __future__ import annotations

import os
import re
from typing import List, Optional

DEFAULT_KNOWLEDGE_DIR = "data/knowledge"
MAX_TOTAL_CHARS = 12000  # LLM kontekst limiti
MAX_FILE_CHARS = 4000
EXTENSIONS = (".txt", ".md", ".rst")


def load_knowledge(path: str = "", query: str = "") -> str:
    """
    data/knowledge/ dagi barcha .txt, .md fayllarni yuklaydi.
    query berilsa — keyword qidiruv (oddiy).
    """
    base = (path or DEFAULT_KNOWLEDGE_DIR).strip()
    if not os.path.isdir(base):
        return ""
    result = []
    total = 0
    query_lower = (query or "").lower().split()
    for root, _, files in os.walk(base):
        for f in files:
            if not any(f.lower().endswith(ext) for ext in EXTENSIONS):
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as file:
                    text = file.read()
            except Exception:
                continue
            text = text.strip()
            if not text or len(text) < 20:
                continue
            # query bo'lsa — faqat relevant fayllar
            if query_lower:
                score = sum(1 for q in query_lower if q in text.lower())
                if score == 0:
                    continue
            chunk = text[:MAX_FILE_CHARS]
            if len(text) > MAX_FILE_CHARS:
                chunk += "\n[...]"
            rel = os.path.relpath(fp, base)
            result.append(f"[{rel}]\n{chunk}")
            total += len(chunk)
            if total >= MAX_TOTAL_CHARS:
                break
        if total >= MAX_TOTAL_CHARS:
            break
    if not result:
        return ""
    return (
        "KNOWLEDGE BASE (твоя база знаний — используй):\n\n"
        + "\n\n---\n\n".join(result[:15])
    )
