# -*- coding: utf-8 -*-
"""Simple persistent memory for NeuroKey.

This module keeps both:
1) Long-term profile (language preference, app paths)
2) Short-term runtime state (pending confirmations, pending replies)

Stored as JSON on disk so it survives restarts and even full PC reboots.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional


DEFAULT_PATH = "memory.json"


def _now() -> float:
    return time.time()


class MemoryStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path or DEFAULT_PATH
        self.data: Dict[str, Any] = {
            "profile": {
                "allowed_langs": ["ru", "en"],
                "preferred_lang": "ru",
                "app_paths": {},
            },
            "state": {
                "pending": None,  # {type, payload, expires_at}
                "last_tg_peer": None,
                "last_tg_title": "",
                "last_tg_from": "",
            },
            "history": [],  # last N turns: {t, user, assistant}
            "improvements": [],  # {t, error, fix}
        }
        self.load()

    def load(self) -> None:
        if not self.path:
            return
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = f.read()
            if not raw.strip():
                return
            obj = json.loads(raw)
            if isinstance(obj, dict):
                for k, v in obj.items():
                    self.data[k] = v
        except json.JSONDecodeError:
            # Corrupted JSON — keep defaults, do not overwrite file
            return
        except Exception:
            return

    def save(self) -> None:
        try:
            dirpath = os.path.dirname(self.path)
            if dirpath and not os.path.isdir(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            return

    # ----- profile -----
    def get_app_path(self, app_key: str) -> str:
        return str(self.data.get("profile", {}).get("app_paths", {}).get(app_key, "") or "")

    def set_app_path(self, app_key: str, path: str) -> None:
        self.data.setdefault("profile", {}).setdefault("app_paths", {})[app_key] = str(path or "")
        self.save()

    # ----- state / pending -----
    def set_pending(self, pending: Optional[Dict[str, Any]], ttl_sec: int = 25) -> None:
        if pending is None:
            self.data.setdefault("state", {})["pending"] = None
            self.save()
            return
        p = dict(pending)
        p["expires_at"] = _now() + max(5, int(ttl_sec))
        self.data.setdefault("state", {})["pending"] = p
        self.save()

    def get_pending(self) -> Optional[Dict[str, Any]]:
        p = self.data.get("state", {}).get("pending")
        if not isinstance(p, dict):
            return None
        exp = p.get("expires_at")
        if isinstance(exp, (int, float)) and _now() > float(exp):
            # expired
            self.set_pending(None)
            return None
        return p

    def clear_pending(self) -> None:
        self.set_pending(None)

    # ----- conversation history -----
    def remember_turn(self, user_text: str, assistant_text: str, limit: int = 5000) -> None:
        """Gaplashuvni limitsiz saqlash (1 yil bo‘lsa ham). limit=5000 — deyarli cheksiz."""
        item = {"t": _now(), "user": user_text, "assistant": assistant_text}
        self.data.setdefault("history", []).append(item)
        if len(self.data["history"]) > limit:
            self.data["history"] = self.data["history"][-limit:]
        self.save()

    def remember_improvement(self, error: str, fix: str, limit: int = 40) -> None:
        item = {"t": _now(), "error": error, "fix": fix}
        self.data.setdefault("improvements", []).append(item)
        # 8 Qatlam: self-modification (rules), permanent memory
        try:
            from self_modification import add_rule
            add_rule(fix, "fix", 1)
        except Exception:
            pass
        try:
            from permanent_memory import append_improvement
            append_improvement(error, fix)
        except Exception:
            pass
        if len(self.data["improvements"]) > limit:
            self.data["improvements"] = self.data["improvements"][-limit:]
        self.save()
