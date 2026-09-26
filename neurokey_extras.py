# -*- coding: utf-8 -*-
"""Extra features: todo, timer, calendar, calculator, task log, backup."""

import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

import config as C

# Timer: when fire, put message into this queue; main loop plays via TTS
timer_queue: Queue = Queue()


def _todo_path() -> str:
    return getattr(C, "NEUROKEY_TODO_PATH", "data/todo.json") or "data/todo.json"


def todo_load() -> List[Dict[str, Any]]:
    path = _todo_path()
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def todo_save(items: List[Dict[str, Any]]) -> None:
    path = _todo_path()
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def todo_add(text: str) -> None:
    items = todo_load()
    items.append({"text": (text or "").strip()[:500], "done": False, "added_at": datetime.now().isoformat()})
    todo_save(items)


def todo_list() -> List[str]:
    items = todo_load()
    return [f"{i+1}. {'[done] ' if x.get('done') else ''}{x.get('text', '')}" for i, x in enumerate(items)]


def todo_mark_done(index: int) -> bool:
    items = todo_load()
    if 1 <= index <= len(items):
        items[index - 1]["done"] = True
        todo_save(items)
        return True
    return False


def start_timer(seconds: float, message: str = "Time's up.") -> None:
    def _fire():
        try:
            timer_queue.put(message)
        except Exception:
            pass

    t = threading.Timer(max(0.1, seconds), _fire)
    t.daemon = True
    t.start()


def _calendar_path() -> str:
    return getattr(C, "NEUROKEY_CALENDAR_PATH", "data/calendar.json") or "data/calendar.json"


def calendar_load() -> List[Dict[str, Any]]:
    path = _calendar_path()
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def calendar_save(items: List[Dict[str, Any]]) -> None:
    path = _calendar_path()
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def calendar_add(date_str: str, title: str, time_str: Optional[str] = None) -> None:
    items = calendar_load()
    items.append({"date": date_str[:20], "title": (title or "").strip()[:300], "time": (time_str or "").strip()[:20] or None})
    calendar_save(items)


def calendar_list(limit: int = 20) -> List[str]:
    items = calendar_load()
    items = sorted(items, key=lambda x: (x.get("date", ""), x.get("time", "")))[:limit]
    return [f"{x.get('date', '')} {x.get('time', '') or ''} — {x.get('title', '')}" for x in items]


# Safe calculator: only digits, + - * / ( ) . and spaces
_calc_re = re.compile(r"^[\d\s\+\-\*\/\.\(\)]+$")


def safe_calculator(expr: str) -> Optional[float]:
    s = (expr or "").strip().replace(" ", "")
    if not s or not _calc_re.match(s):
        return None
    try:
        return float(eval(s))
    except Exception:
        return None


def log_action(action: str, detail: str = "") -> None:
    path = getattr(C, "NEUROKEY_TASK_LOG_PATH", "data/neurokey_actions.log") or None
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} | {action} | {detail}\n")
    except Exception:
        pass


def backup_memory_and_ltm() -> Tuple[bool, str]:
    """Copy memory.json and LTM db to backup dir with timestamp. Returns (success, message)."""
    backup_dir = getattr(C, "NEUROKEY_BACKUP_DIR", "data/backup") or "data/backup"
    app_dir = os.path.dirname(os.path.abspath(__file__))
    memory_path = os.path.join(app_dir, getattr(C, "MEMORY_PATH", "memory.json"))
    ltm_path = os.path.join(app_dir, getattr(C, "LTM_DB_PATH", "data/neurokey_memory.db"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(app_dir, backup_dir, stamp)
    try:
        os.makedirs(out_dir, exist_ok=True)
        if os.path.isfile(memory_path):
            shutil.copy2(memory_path, os.path.join(out_dir, "memory.json"))
        if os.path.isfile(ltm_path):
            shutil.copy2(ltm_path, os.path.join(out_dir, "neurokey_memory.db"))
        return True, f"Backup saved to {backup_dir}/{stamp}"
    except Exception as e:
        return False, str(e)
