# -*- coding: utf-8 -*-
"""NeuroKey — Executor. Core qarorini bajarish. Retry, alternativ. To'siq yo'q."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from file_ops import read as file_read, write as file_write, append as file_append
    from file_ops import rename as file_rename, delete as file_delete, create as file_create
    from file_ops import copy as file_copy, move as file_move, exists as file_exists
    from file_ops import list_dir as file_list_dir, search as file_search
except ImportError:
    file_read = file_write = file_append = file_rename = file_delete = None
    file_create = file_copy = file_move = file_exists = file_list_dir = file_search = None

try:
    from process_ops import list_all as process_list_all, start as process_start
    from process_ops import kill as process_kill, find_by_name as process_find_by_name
except ImportError:
    process_list_all = process_start = process_kill = process_find_by_name = None

try:
    from window_ops import window_list as _window_list, window_focus as _window_focus
    from window_ops import window_minimize as _window_minimize, window_maximize as _window_maximize
    from window_ops import window_close as _window_close, window_by_title as _window_by_title
except ImportError:
    _window_list = _window_focus = _window_minimize = _window_maximize = None
    _window_close = _window_by_title = None

try:
    from input_sim import mouse_move as _mouse_move, mouse_click as _mouse_click
    from input_sim import mouse_double_click as _mouse_double_click
    from input_sim import key_press as _key_press, key_type as _key_type, hotkey as _hotkey
except ImportError:
    _mouse_move = _mouse_click = _mouse_double_click = _key_press = _key_type = _hotkey = None

try:
    from clipboard_ops import clipboard_get as _clipboard_get, clipboard_set as _clipboard_set
except ImportError:
    _clipboard_get = _clipboard_set = None


@dataclass
class ExecuteResult:
    """Bajarish natijasi."""
    ok: bool
    message: str = ""
    data: Any = None


def parse_action(text: str) -> Optional[Dict[str, Any]]:
    """Matndan action dict parse qilish.
    ACTION: file_read C:\\path
    ACTION: file_write C:\\path content
    ACTION: process_start calc
    """
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    # [ACTION: ...] format
    m = re.search(r"\[?ACTION:\s*(\w+)\s+([^\]]*)\]?", text, re.IGNORECASE)
    if m:
        act = (m.group(1) or "").strip().lower()
        param = (m.group(2) or "").strip()
        return _parse_action_params(act, param)
    # Oddiy: action param1 param2
    parts = text.split(None, 1)
    if len(parts) >= 2:
        return _parse_action_params(parts[0].lower(), parts[1])
    return None


def _parse_action_params(action: str, param: str) -> Dict[str, Any]:
    """Param stringdan action dict."""
    param = param.strip()
    if action in ("file_read", "file_delete", "file_list", "file_exists"):
        return {"action": action, "path": param}
    if action in ("file_write", "file_append"):
        # path va content — oxirgi | yoki :: bilan ajratilgan bo'lishi mumkin
        if " | " in param:
            p, c = param.split(" | ", 1)
            return {"action": action, "path": p.strip(), "content": c.strip()}
        if " :: " in param:
            p, c = param.split(" :: ", 1)
            return {"action": action, "path": p.strip(), "content": c.strip()}
        # path bo'sh bo'lishi mumkin
        return {"action": action, "path": param, "content": ""}
    if action in ("file_rename", "file_copy", "file_move"):
        parts = param.split(None, 1)
        if len(parts) >= 2:
            return {"action": action, "src": parts[0], "dst": parts[1]}
        return {"action": action, "src": param, "dst": ""}
    if action in ("file_search", "search_files"):
        parts = param.split(None, 1)
        root = os.path.expanduser("~") if len(parts) < 2 else parts[0]
        pattern = parts[-1]
        return {"action": "file_search", "root": root, "pattern": pattern}
    if action in ("process_start", "open_app"):
        return {"action": "process_start", "path": param}
    if action in ("process_kill", "close_app"):
        return {"action": "process_kill", "name_or_pid": param}
    if action == "process_find":
        return {"action": "process_find", "name": param}
    if action in ("window_focus", "window_minimize", "window_maximize", "window_close"):
        try:
            hwnd = int(param)
            return {"action": action, "hwnd": hwnd}
        except ValueError:
            return {"action": action, "title": param}
    if action == "window_by_title":
        return {"action": "window_by_title", "title": param}
    if action == "window_list":
        return {"action": "window_list"}
    if action == "mouse_move":
        parts = param.replace(",", " ").split()
        if len(parts) >= 2:
            try:
                return {"action": "mouse_move", "x": int(parts[0]), "y": int(parts[1])}
            except ValueError:
                pass
        return {"action": "mouse_move", "path": param}
    if action in ("mouse_click", "mouse_double_click"):
        parts = param.replace(",", " ").split()
        x = y = None
        if len(parts) >= 2:
            try:
                x, y = int(parts[0]), int(parts[1])
            except ValueError:
                pass
        return {"action": action, "x": x, "y": y}
    if action == "key_press":
        return {"action": "key_press", "key": param}
    if action == "key_type":
        return {"action": "key_type", "text": param}
    if action == "hotkey":
        keys = [k.strip() for k in param.split() if k.strip()]
        return {"action": "hotkey", "keys": keys}
    if action == "clipboard_get":
        return {"action": "clipboard_get"}
    if action == "clipboard_set":
        return {"action": "clipboard_set", "text": param}
    return {"action": action, "path": param}


def _try_execute(action: Dict[str, Any]) -> ExecuteResult:
    """Bitta urinish — bajarish."""
    act = (action.get("action") or "").lower()
    if not act:
        return ExecuteResult(ok=False, message="Action yo'q")

    # file_ops
    if act == "file_read" and file_read:
        try:
            path = action.get("path", "")
            if path:
                return ExecuteResult(ok=True, data=file_read(path), message="O'qildi")
        except FileNotFoundError as e:
            return ExecuteResult(ok=False, message=str(e))
        except Exception as e:
            return ExecuteResult(ok=False, message=str(e))

    if act == "file_write" and file_write:
        ok = file_write(action.get("path", ""), action.get("content", ""))
        return ExecuteResult(ok=ok, message="Yozildi" if ok else "Xato")

    if act == "file_append" and file_append:
        ok = file_append(action.get("path", ""), action.get("content", ""))
        return ExecuteResult(ok=ok, message="Qo'shildi" if ok else "Xato")

    if act == "file_delete" and file_delete:
        ok = file_delete(action.get("path", ""))
        return ExecuteResult(ok=ok, message="O'chirildi" if ok else "Xato")

    if act == "file_create" and file_create:
        ok = file_create(action.get("path", ""))
        return ExecuteResult(ok=ok, message="Yaratildi" if ok else "Xato")

    if act == "file_copy" and file_copy:
        ok = file_copy(action.get("src", ""), action.get("dst", ""))
        return ExecuteResult(ok=ok, message="Nusxalandi" if ok else "Xato")

    if act == "file_move" and file_move:
        ok = file_move(action.get("src", ""), action.get("dst", ""))
        return ExecuteResult(ok=ok, message="Ko'chirildi" if ok else "Xato")

    if act == "file_list" and file_list_dir:
        path = (action.get("path") or "").strip()
        if path and "*" in path:
            path = (path.split("*")[0] or path).rstrip("\\/")
        if not path or path in ("Documents", "Doc"):
            path = os.path.expanduser("~\\Documents") if os.name == "nt" else os.path.expanduser("~/Documents")
        else:
            path = os.path.expanduser(path)
        data = file_list_dir(path)
        return ExecuteResult(ok=True, data=data, message=f"{len(data)} ta")

    if act == "file_search" and file_search:
        root = action.get("root", os.path.expanduser("~"))
        pattern = action.get("pattern", "*")
        data = file_search(root, pattern)
        return ExecuteResult(ok=True, data=data, message=f"Topildi: {len(data)} ta")

    # process_ops
    if act == "process_start" and process_start:
        path = action.get("path", "")
        pid = process_start(path)
        return ExecuteResult(ok=(pid >= 0), message="Ishga tushdi" if pid >= 0 else "Xato", data=pid)

    if act == "process_kill" and process_kill:
        name_or_pid = action.get("name_or_pid", "")
        try:
            pid = int(name_or_pid)
            ok = process_kill(pid)
        except ValueError:
            pids = process_find_by_name(name_or_pid) if process_find_by_name else []
            ok = False
            for p in pids:
                if process_kill(p):
                    ok = True
                    break
        return ExecuteResult(ok=ok, message="To'xtatildi" if ok else "Topilmadi")

    if act == "process_find" and process_find_by_name:
        pids = process_find_by_name(action.get("name", ""))
        return ExecuteResult(ok=True, data=pids, message=f"{len(pids)} ta")

    if act == "file_exists" and file_exists:
        return ExecuteResult(ok=file_exists(action.get("path", "")), message="Mavjud" if file_exists(action.get("path", "")) else "Yo'q")

    # window_ops
    def _resolve_hwnd(a: Dict[str, Any]) -> Optional[int]:
        hwnd = a.get("hwnd")
        if hwnd is not None:
            return int(hwnd)
        title = a.get("title", "").strip()
        if title and _window_by_title:
            wins = _window_by_title(title, partial=True)
            if wins:
                return int(wins[0]["hwnd"])
        return None

    if act == "window_list" and _window_list:
        data = _window_list()
        return ExecuteResult(ok=True, data=data, message=f"{len(data)} ta oyna")

    if act == "window_by_title" and _window_by_title:
        title = action.get("title", "").strip()
        wins = _window_by_title(title, partial=True)
        return ExecuteResult(ok=True, data=wins, message=f"{len(wins)} ta")

    if act == "window_focus" and _window_focus:
        hwnd = _resolve_hwnd(action)
        ok = hwnd is not None and _window_focus(hwnd)
        return ExecuteResult(ok=ok, message="Oldinga" if ok else "Topilmadi")

    if act == "window_minimize" and _window_minimize:
        hwnd = _resolve_hwnd(action)
        ok = hwnd is not None and _window_minimize(hwnd)
        return ExecuteResult(ok=ok, message="Minimize" if ok else "Topilmadi")

    if act == "window_maximize" and _window_maximize:
        hwnd = _resolve_hwnd(action)
        ok = hwnd is not None and _window_maximize(hwnd)
        return ExecuteResult(ok=ok, message="Maximize" if ok else "Topilmadi")

    if act == "window_close" and _window_close:
        hwnd = _resolve_hwnd(action)
        ok = hwnd is not None and _window_close(hwnd)
        return ExecuteResult(ok=ok, message="Yopildi" if ok else "Topilmadi")

    # input_sim
    if act == "mouse_move" and _mouse_move:
        x, y = action.get("x"), action.get("y")
        if x is not None and y is not None:
            ok = _mouse_move(x, y)
            return ExecuteResult(ok=ok, message="Ko'chirildi" if ok else "Xato")
    if act == "mouse_click" and _mouse_click:
        ok = _mouse_click(action.get("x"), action.get("y"))
        return ExecuteResult(ok=ok, message="Click" if ok else "Xato")
    if act == "mouse_double_click" and _mouse_double_click:
        ok = _mouse_double_click(action.get("x"), action.get("y"))
        return ExecuteResult(ok=ok, message="Double click" if ok else "Xato")
    if act == "key_press" and _key_press:
        ok = _key_press(action.get("key", ""))
        return ExecuteResult(ok=ok, message="Bosildi" if ok else "Xato")
    if act == "key_type" and _key_type:
        ok = _key_type(action.get("text", ""))
        return ExecuteResult(ok=ok, message="Yozildi" if ok else "Xato")
    if act == "hotkey" and _hotkey:
        keys = action.get("keys", [])
        ok = bool(keys) and _hotkey(*keys)
        return ExecuteResult(ok=ok, message="Hotkey" if ok else "Xato")

    # clipboard_ops
    if act == "clipboard_get" and _clipboard_get:
        data = _clipboard_get()
        return ExecuteResult(ok=data is not None, data=data, message="O'qildi" if data is not None else "Xato")
    if act == "clipboard_set" and _clipboard_set:
        ok = _clipboard_set(action.get("text", ""))
        return ExecuteResult(ok=ok, message="Nusxalandi" if ok else "Xato")

    # telegram_ops — zanjirda: masalan veb qidiruv -> skrinshot -> yuborish
    if act == "telegram_send":
        try:
            import telegram_bridge
            bridge = telegram_bridge.get_bridge() if hasattr(telegram_bridge, "get_bridge") else None
            if bridge is None:
                return ExecuteResult(ok=False, message="Telegram ulanmagan")
            peer = action.get("peer_id")
            path = action.get("path", "")
            caption = action.get("caption", "")
            if path:
                bridge.send_file(peer, path, caption=caption)
            else:
                bridge.send_peer(peer, action.get("text", caption))
            return ExecuteResult(ok=True, message="Yuborildi")
        except Exception as e:
            return ExecuteResult(ok=False, message=f"Telegram xato: {e}")

    if act == "telegram_screenshot":
        try:
            import telegram_bridge
            bridge = telegram_bridge.get_bridge() if hasattr(telegram_bridge, "get_bridge") else None
            if bridge is None:
                return ExecuteResult(ok=False, message="Telegram ulanmagan")
            peer = action.get("peer_id")
            caption = action.get("caption", "")
            bridge.send_screenshot(peer, caption=caption)
            return ExecuteResult(ok=True, message="Skrinshot yuborildi")
        except Exception as e:
            return ExecuteResult(ok=False, message=f"Telegram xato: {e}")

    return ExecuteResult(ok=False, message=f"Unknown action: {act}")


def get_alternatives(action: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Alternativ amallar — boshqa yo'l, boshqa usul."""
    act = (action.get("action") or "").lower()
    alts: List[Dict[str, Any]] = []

    if act == "file_read" and file_search:
        path = action.get("path", "")
        if path:
            name = os.path.basename(path)
            for search_root in [os.path.expanduser("~\\Documents"), os.path.expanduser("~"), "C:\\"]:
                if search_root and os.path.isdir(search_root):
                    found = file_search(search_root, name, max_results=1)
                    if found:
                        alts.append({"action": "file_read", "path": found[0]})
                        break

    if act == "file_search":
        root = action.get("root", "")
        pattern = action.get("pattern", "")
        # Boshqa rootlar
        for r in [os.path.expanduser("~\\Documents"), os.path.expanduser("~"), "C:\\"]:
            if r and r != root and os.path.isdir(r):
                alts.append({"action": "file_search", "root": r, "pattern": pattern})

    return alts[:5]  # 5 ta alternativ


def execute(action: Dict[str, Any], retry: bool = True) -> ExecuteResult:
    """Amalni bajarish. Fail bo'lsa — retry, alternativ."""
    result = _try_execute(action)
    if result.ok:
        return result
    if not retry:
        return result
    if not file_read and not process_start:
        return result
    alts = get_alternatives(action)
    for alt in alts:
        r = _try_execute(alt)
        if r.ok:
            return r
    return result


def execute_from_string(text: str, retry: bool = True) -> ExecuteResult:
    """Matndan parse qilib bajarish."""
    action = parse_action(text)
    if not action:
        return ExecuteResult(ok=False, message="Parse xato")
    return execute(action, retry=retry)


def execute_steps(steps: list, retry: bool = True) -> ExecuteResult:
    """Ketma-ket bosqichlarni bajarish. Har qadam natijasi keyingisiga path beradi."""
    if not steps:
        return ExecuteResult(ok=False, message="Bosqich yo'q")
    last_result = None
    for i, step in enumerate(steps):
        # file_read path bo'sh bo'lsa — oldingi file_search natijasidan olish
        if (step.get("action") == "file_read" and not step.get("path")) and last_result and isinstance(last_result.data, list) and last_result.data:
            step = dict(step)
            step["path"] = last_result.data[0]
        r = execute(step, retry=retry)
        last_result = r
        if not r.ok:
            return r
    return last_result or ExecuteResult(ok=True, message="Bajarildi")
