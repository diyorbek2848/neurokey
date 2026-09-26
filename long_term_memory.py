# -*- coding: utf-8 -*-
"""Uzoq muddatli xotira: sqlite3 — ism, sevimli saytlar, ish vaqti va boshqalar."""

from __future__ import annotations

try: import permanent_memory as _ltm_pm
except ImportError: _ltm_pm = None
try: import episodic_memory as _ltm_em
except ImportError: _ltm_em = None

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

DEFAULT_DB = "data/neurokey_memory.db"


class LongTermMemory:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = (db_path or os.getenv("NEUROKEY_MEMORY_DB") or DEFAULT_DB).strip()
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._db_conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                content TEXT,
                created_at REAL
            )
        """)
        conn.commit()
        conn.close()

    def set(self, key: str, value: Any) -> None:
        import time as _time
        conn = sqlite3.connect(self.db_path)
        v = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO profile (key, value, updated_at) VALUES (?, ?, ?)",
            (key.strip().lower(), v, _time.time()),
        )
        conn.commit()
        conn.close()

    def get(self, key: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT value FROM profile WHERE key = ?", (key.strip().lower(),)).fetchone()
        conn.close()
        return row[0] if row else None

    def get_all_profile(self) -> Dict[str, str]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT key, value FROM profile").fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}

    def get_profile_text_for_llm(self, lang: str = "ru") -> str:
        """LLM uchun qisqa profil matni."""
        raw = self.get_all_profile()
        if not raw:
            return ""
        lines = []
        labels_ru = {
            "name": "Имя",
            "owner_name": "Владелец",
            "favorite_sites": "Любимые сайты",
            "work_hours": "Обычное рабочее время",
            "city": "Город",
            "timezone": "Часовой пояс",
        }
        labels_en = {
            "name": "Name",
            "owner_name": "Owner",
            "favorite_sites": "Favorite sites",
            "work_hours": "Usual work hours",
            "city": "City",
            "timezone": "Timezone",
        }
        labels = labels_en if lang == "en" else labels_ru
        for k, v in raw.items():
            if not v:
                continue
            label = labels.get(k, k)
            lines.append(f"{label}: {v}")
        if not lines:
            return ""
        return "User profile (remember and use):\n" + "\n".join(lines) if lang == "en" else "Профиль пользователя (запомни и используй):\n" + "\n".join(lines)

    def add_fact(self, kind: str, content: str) -> None:
        import time as _time
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO facts (kind, content, created_at) VALUES (?, ?, ?)", (kind, content[:2000], _time.time()))
        conn.commit()
        conn.close()

    def get_recent_facts(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT kind, content, created_at FROM facts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [{"kind": r[0], "content": r[1], "created_at": r[2]} for r in rows]

    def get_user_facts_for_llm(self, limit: int = 30) -> str:
        """Foydalanuvchi haqida o'rganilgan faktlar (kind='user') — LLM konteksti uchun."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT content FROM facts WHERE kind = ? ORDER BY id DESC LIMIT ?",
            ("user", limit),
        ).fetchall()
        conn.close()
        if not rows:
            return ""
        lines = [r[0].strip() for r in rows if (r[0] or "").strip()]
        return "Learned about the user (use in replies and when asked about them):\n" + "\n".join(lines[:25])

    def search_facts_by_keywords(self, query: str, limit: int = 10) -> str:
        """Kalit so'zlar bo'yicha barcha faktlardan qidiruv — episodic + user."""
        if not query:
            return ""
        stop = {"что", "как", "это", "для", "все", "вот", "ты", "да", "нет", "мне", "он", "она", "они", "в", "и", "на", "с", "по", "к", "не"}
        words = [w.lower().strip(".,!?;:()[]") for w in query.split() if len(w.strip(".,!?;:()[]")) >= 3 and w.lower() not in stop]
        if not words:
            return ""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT kind, content FROM facts ORDER BY id DESC LIMIT 500").fetchall()
        conn.close()
        scored = []
        for kind, content in rows:
            low = (content or "").lower()
            score = sum(1 for w in words if w in low)
            if score > 0:
                scored.append((score, kind, content))
        scored.sort(key=lambda x: -x[0])
        top = scored[:limit]
        if not top:
            return ""
        lines = [f"[{k}] {c[:150]}" for _, k, c in top]
        return "Из памяти (релевантные факты):\n" + "\n".join(lines)

    @staticmethod
    def search_episodic_memory(
        query: str,
        history: List[Dict[str, Any]],
        limit: int = 5,
        min_turns_ago: int = 40,
    ) -> List[Dict[str, Any]]:
        """
        Keyword-based qidiruv — barcha eski suhbatlardan mos keluvchi turnlarni topadi.
        Faqat min_turns_ago dan eski turnlarda qidiradi (yangilari allaqachon kontekstda bor).
        """
        if not query or not history:
            return []
        # Rus/o'zbek stopwords
        _stop = {
            "что", "как", "это", "для", "все", "вот", "ты", "ну", "да", "нет",
            "мне", "он", "она", "они", "мы", "вы", "его", "её", "их", "на",
            "в", "и", "а", "но", "с", "по", "к", "от", "из", "за", "до",
            "не", "бы", "же", "ли", "уж", "хоть", "или", "то", "со", "об",
            "men", "sen", "u", "biz", "siz", "bu", "shu", "va", "ham", "esa",
            "bo'ldi", "qil", "kerak", "qanday", "nima", "kim", "qaysi",
        }
        raw_words = query.replace(",", " ").replace(".", " ").replace("?", " ").split()
        keywords = [w.lower().strip(".,!?;:()[]") for w in raw_words if len(w.strip(".,!?;:()[]")) >= 3]
        keywords = [w for w in keywords if w not in _stop]
        if not keywords:
            return []
        # Faqat eski turnlar (yangilari allaqachon unified_memory da bor)
        cutoff = max(0, len(history) - min_turns_ago)
        old_history = history[:cutoff]
        if not old_history:
            return []
        scored = []
        for i, turn in enumerate(old_history):
            combined = ((turn.get("user") or "") + " " + (turn.get("assistant") or "")).lower()
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                scored.append((score, i, turn))
        scored.sort(key=lambda x: -x[0])
        return [t for _, _, t in scored[:limit]]
