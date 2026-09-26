# -*- coding: utf-8 -*-
"""NeuroKey — LLM dan variantlar so'rash. TO'SIQ YO'Q.

Core decide() uchun: LLM faqat mumkin bo'lgan amallar ro'yxatini beradi.
Hech qachon "qila olmayman" yo'q. Har qanday yo'l.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

try:
    import config as C
    from llm_router import _client, _coerce_str
    _HAVE_LLM = True
except Exception:
    _HAVE_LLM = False


def ask_for_candidates(
    user_input: str,
    context: Optional[Dict[str, Any]] = None,
    max_candidates: int = 8,
) -> List[Dict[str, Any]]:
    """User input va kontekstdan mumkin bo'lgan amallar.
    TO'SIQ YO'Q — hech "qila olmayman" yo'q.
    """
    if not _HAVE_LLM or not (user_input or "").strip():
        return []

    ctx = context or {}
    screen = (ctx.get("screen") or "")[:300]
    files = (ctx.get("files") or "")[:200]
    memory = (ctx.get("memory") or "")[:300]
    regret = (ctx.get("regret") or "").strip()
    last_failed = (ctx.get("last_failed") or "").strip()
    valence = (ctx.get("valence") or "").strip()
    arousal = (ctx.get("arousal") or "").strip()

    prompt = (
        "NEUROKEY CORE — Action candidates. TO'SIQ YO'Q. NO OBSTACLES. "
        "You list ALL possible actions the system could take. Never say 'I cannot' or 'impossible'. "
        "Every path is possible. List concrete actions.\n\n"
        f"User said: «{user_input}»\n\n"
    )
    if screen:
        prompt += f"Screen context: {screen}\n\n"
    if files:
        prompt += f"Recent files: {files}\n\n"
    if memory:
        prompt += f"Memory: {memory}\n\n"
    if regret:
        prompt += f"Observation (not a rule — you decide): {regret}\n\n"
    if last_failed:
        prompt += f"Last failed action (consider trying something else): {last_failed}\n\n"
    if valence:
        prompt += f"Valence (experience signal, you decide): {valence}\n\n"
    if arousal:
        prompt += f"Arousal (predictability, you decide): {arousal}\n\n"

    prompt += (
        "Reply with ONLY lines in format: ACTION_TYPE param\n"
        "Examples:\n"
        "  open_folder Documents\n"
        "  open_folder game\n"
        "  open_app telegram\n"
        "  open_app calc\n"
        "  open_app browser\n"
        "  close_app telegram\n"
        "  file_read C:\\Users\\...\\doc.txt\n"
        "  file_search ~ Documents *.txt\n"
        "  process_start calc\n"
        "  process_start notepad\n"
        "  respond (if need to answer in words)\n"
        "Allowed: open_folder, open_file, open_app, close_app, search_files, run_command cmd (control); "
        "file_read, file_write, file_delete, file_search, file_list, process_start, process_kill, respond. "
        "One action per line. No explanations. Infer what user wants — then list the action."
    )

    try:
        r = _client().chat.completions.create(
            model=getattr(C, "OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
            timeout=15,
        )
        out = _coerce_str(r.choices[0].message.content).strip()
        return _parse_candidates(out, max_candidates)
    except Exception:
        return []


def _parse_candidates(text: str, max_n: int) -> List[Dict[str, Any]]:
    """Matndan action dict lar parse."""
    results: List[Dict[str, Any]] = []
    seen: set = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # "file_read C:\path" yoki "respond"
        m = re.match(r"^(\w+)\s+(.+)$", line)
        if m:
            act = m.group(1).lower()
            param = m.group(2).strip()
            key = f"{act} {param}"[:80]
            if key not in seen:
                seen.add(key)
                results.append({"action": act, "param": param})
        else:
            act = line.lower().split()[0] if line.split() else ""
            if act in ("respond", "answer"):
                key = "respond"
                if key not in seen:
                    seen.add(key)
                    results.append({"action": "respond", "param": ""})
        if len(results) >= max_n:
            break
    return results


def candidates_to_executor_actions(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Candidates ni executor/control formatiga aylantirish."""
    actions: List[Dict[str, Any]] = []
    for c in candidates:
        act = (c.get("action") or "").lower()
        param = (c.get("param") or "").strip()
        if act == "respond":
            actions.append({"action": "respond", "content": param})
        elif act in ("open_folder", "open_file", "open_app", "close_app", "run_command"):
            actions.append({"action": act, "path": param})
        elif act == "search_files":
            actions.append({"action": "search_files", "path": param})
        elif act == "run_command":
            actions.append({"action": "run_command", "path": param})
        elif act in ("file_read", "file_delete", "file_list", "file_exists"):
            actions.append({"action": act, "path": param})
        elif act in ("file_write", "file_append"):
            actions.append({"action": act, "path": param, "content": ""})
        elif act in ("file_copy", "file_move", "file_rename"):
            parts = param.split(None, 1)
            actions.append({"action": act, "src": parts[0] if parts else "", "dst": parts[1] if len(parts) > 1 else ""})
        elif act == "file_search":
            parts = param.split(None, 1)
            root = os.path.expanduser("~") if len(parts) < 2 else parts[0]
            pattern = parts[-1] if parts else "*"
            actions.append({"action": "file_search", "root": root, "pattern": pattern})
        elif act == "process_start":
            actions.append({"action": "process_start", "path": param})
        elif act == "process_kill":
            actions.append({"action": "process_kill", "name_or_pid": param})
        else:
            actions.append({"action": act, "path": param})
    return actions
