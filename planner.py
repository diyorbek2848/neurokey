# -*- coding: utf-8 -*-
"""NeuroKey — Planner. Murakkab vazifani bosqichlarga bo'lish.

"X top, och va 5-qatorni o'zgartir" → [file_search, file_read, file_write]
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

try:
    from llm_router import _client, _coerce_str
    import config as C
    _HAVE_LLM = True
except ImportError:
    _HAVE_LLM = False


def decompose(task: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Vazifani bosqichlarga bo'lish. Har qadam — alohida amal.
    Qaytadi: [{"action": "...", ...}, ...]
    """
    if not (task or "").strip():
        return []

    # Oddiy pattern: "X top va och" → file_search, file_list, process_start
    task_lower = task.lower().strip()
    steps: List[Dict[str, Any]] = []

    # Pattern: "top" + "och" → file_list yoki file_search, keyin explorer
    if ("top" in task_lower or "find" in task_lower or "qidir" in task_lower) and ("och" in task_lower or "open" in task_lower):
        docs = os.path.expanduser("~\\Documents") if os.name == "nt" else os.path.expanduser("~/Documents")
        if "document" in task_lower or "papka" in task_lower or "docs" in task_lower or "fayl" in task_lower:
            steps.append({"action": "file_list", "path": docs})
        else:
            steps.append({"action": "file_search", "root": docs, "pattern": "*"})
        steps.append({"action": "process_start", "path": "explorer"})
        return steps

    # Pattern: "o'qish" / "read" → file_search, file_read
    if "o'qi" in task_lower or "read" in task_lower or "ko'rsat" in task_lower:
        steps.append({"action": "file_search", "root": os.path.expanduser("~\\Documents"), "pattern": "*"})
        steps.append({"action": "file_read", "path": ""})  # path keyingi qadamda to'ldiriladi
        return steps

    # LLM orqali — murakkab vazifa
    if _HAVE_LLM:
        return _decompose_llm(task, context or {})

    return [{"action": "respond", "content": task}]


def _decompose_llm(task: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """LLM orqali bosqichlarga bo'lish."""
    prompt = (
        f"User vazifasi: «{task}»\n\n"
        "Bu vazifani bosqichlarga bo'ling. Har qadam — bitta amal.\n"
        "Format: har qatorda ACTION param\n"
        "Masalan:\n"
        "  open_folder Documents\n"
        "  open_app telegram\n"
        "  open_app calc\n"
        "  file_search ~ Documents *.txt\n"
        "  file_read [topilgan path]\n"
        "  file_write [path] [content]\n"
        "  process_start calc\n"
        "  respond (agar faqat javob kerak bo'lsa)\n"
        "Allowed: open_folder, open_app, close_app (control); file_search, file_read, file_write, file_delete, file_list, process_start, process_kill, respond.\n"
        "Javob: faqat har qadam bitta qatorda. Boshqa matn yo'q."
    )
    try:
        r = _client().chat.completions.create(
            model=getattr(C, "OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
            timeout=10,
        )
        out = _coerce_str(r.choices[0].message.content).strip()
        return _parse_steps(out)
    except Exception:
        return [{"action": "respond", "content": task}]


def _parse_steps(text: str) -> List[Dict[str, Any]]:
    """Matndan step dict lar."""
    steps: List[Dict[str, Any]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\w+)\s+(.*)$", line)
        if m:
            act = m.group(1).lower()
            param = m.group(2).strip()
            if act == "file_search":
                parts = param.split(None, 1)
                root = os.path.expanduser("~") if len(parts) < 2 else parts[0]
                pattern = parts[-1] if parts else "*"
                steps.append({"action": "file_search", "root": root, "pattern": pattern})
            elif act == "file_read":
                steps.append({"action": "file_read", "path": param})
            elif act == "file_write":
                parts = param.split(" ", 1)
                steps.append({"action": "file_write", "path": parts[0] if parts else "", "content": parts[1] if len(parts) > 1 else ""})
            elif act == "file_list":
                steps.append({"action": "file_list", "path": param or os.path.expanduser("~\\Documents")})
            elif act == "process_start":
                steps.append({"action": "process_start", "path": param})
            elif act == "process_kill":
                steps.append({"action": "process_kill", "name_or_pid": param})
            elif act in ("open_folder", "open_app", "close_app"):
                steps.append({"action": act, "path": param})
            elif act == "respond":
                steps.append({"action": "respond", "content": param})
            else:
                steps.append({"action": act, "path": param})
    return steps if steps else [{"action": "respond", "content": ""}]


def is_complex(action: Dict[str, Any], user_input: str = "") -> bool:
    """Bu amal murakkabmi — bir necha qadam kerakmi?"""
    act = (action.get("action") or "").lower()
    content = (action.get("content") or user_input or "").lower()
    # "top va och", "qidir va o'qi" — murakkab
    if "va" in content or " and " in content:
        return True
    if act == "respond" and ("top" in content or "qidir" in content or "find" in content or "open" in content):
        return True
    return False
