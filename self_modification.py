# -*- coding: utf-8 -*-
"""Qatlam 4: Self-modification — qoidalarni tajriba asosida o'zgartirish.

Xato → yangi qoida. G'alaba → mavjud qoida success.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List


DEFAULT_PATH = "data/rules.json"
MAX_RULES = 100


def _load_rules(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_rules(path: str, rules: List[Dict[str, Any]]) -> None:
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_rule(rule: str, rule_type: str = "fix", success: int = 1, path: str = "") -> None:
    """Yangi qoida qo'shish (xatodan o'rganish)."""
    p = path or os.path.join(os.path.dirname(__file__), DEFAULT_PATH)
    p = os.path.normpath(p)
    rules = _load_rules(p)
    # Takrorlanishni tekshirish
    rstr = (rule or "").strip()[:200]
    if not rstr:
        return
    for r in rules:
        if (r.get("rule") or "").strip() == rstr:
            r["success"] = r.get("success", 0) + success
            _save_rules(p, rules)
            return
    rules.append({"t": time.time(), "rule": rstr, "type": rule_type, "success": success})
    if len(rules) > MAX_RULES:
        rules = sorted(rules, key=lambda x: x.get("t", 0))[-MAX_RULES:]
    _save_rules(p, rules)


def check_blocked(candidate: Dict[str, Any], path: str = "") -> bool:
    """Candidate qoidalar tomonidan bloklanganmi?
    Qoidalar "Bunday qilma" turi — candidate tekshiriladi.
    """
    p = path or os.path.join(os.path.dirname(__file__), DEFAULT_PATH)
    p = os.path.normpath(p)
    rules = _load_rules(p)
    act = (candidate.get("action") or "").lower()
    path_val = (candidate.get("path") or candidate.get("src") or "").strip()
    cand_str = f"{act} {path_val}"[:150]
    for r in rules:
        rule = (r.get("rule") or "").strip().lower()
        if not rule:
            continue
        if "blok" in rule or "qilma" in rule or "o'chirma" in rule:
            if path_val and path_val.lower() in rule:
                return True
            if act in rule:
                return True
    return False


def get_rules_for_llm(path: str = "", limit: int = 15) -> str:
    """LLM uchun qoidalar matni."""
    p = path or os.path.join(os.path.dirname(__file__), DEFAULT_PATH)
    p = os.path.normpath(p)
    rules = _load_rules(p)
    if not rules:
        return ""
    # Success bo'yicha tartiblash
    sorted_rules = sorted(rules, key=lambda x: (-x.get("success", 0), -x.get("t", 0)))[:limit]
    lines = [f"- {r.get('rule', '')} (ishladi: {r.get('success', 0)})" for r in sorted_rules if r.get("rule")]
    return "O'zing qo'ygan qoidalar (xatolardan o'rganish):\n" + "\n".join(lines) if lines else ""
