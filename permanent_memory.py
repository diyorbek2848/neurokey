# -*- coding: utf-8 -*-
"""NeuroKey — Doimiy Xotira (Permanent Memory).

HECH QACHON ESDAN CHIQARMAYDI.
Ochib-yonsa ham, qayta ishga tushsa ham — hamma narsa saqlanadi.

Arxitektura:
  - SQLite WAL mode  — crash-safe, elektr uzilsa ham saqlanadi
  - FTS5 full-text   — har qanday so'z bo'yicha qidirish
  - Hissiy teglash   — qaysi his bilan bog'liq
  - Shaxs indeksi    — kim haqida
  - Vaqt indeksi     — qachon bo'lgan
  - DELETE YO'Q      — faqat INSERT va UPDATE

Jadvallar:
  conversations   — barcha suhbatlar (user + bot), cheksiz
  episodes        — muhim voqealar, hissiy teglangan
  reflections     — fikrlar va xulosalar
  knowledge       — o'rganilgan bilimlar
  inner_thoughts  — ichki fikrlar
  emotions        — his-tuyg'u tarixi
  rules           — o'rganilgan qoidalar
  goals_archive   — tugagan maqsadlar ham saqlanadi

2026-yil suniy ong — abadiy xotira qatlami.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DB_PATH  = os.path.join(_BASE_DIR, "data", "permanent_memory.db")

# ─────────────────────────────────────────────────────────────
# DB ulanish va jadvallar
# ─────────────────────────────────────────────────────────────
#
# ROOT-CAUSE FIX (2026-08-19, real ko'p-turnli test bilan topildi): ilgari
# HAR bir chaqiruv (remember_conversation, recall, get_stats, ...) o'zining
# YANGI sqlite3 connection'ini ochib-yopardi (`with _db():` har safar
# _connect() chaqirardi). consciousness_orchestrator.py da ~25 ta modul
# on_user_message() orqali PARALLEL (ThreadPoolExecutor) shu faylga
# yozadi/o'qiydi — ya'ni bir vaqtning o'zida ko'plab MUSTAQIL connection
# bitta faylga murojaat qilardi. Real testda bu real, o'lchangan qulf-
# kutishga olib keldi: permanent_memory.get_stats() bitta chaqiruvda
# 11.5s, boshqa safar 14.8s/17.7s cho'zildi (ORCH_SLOW_MODULE logi) — WAL
# rejimi yordam bermadi, chunki muammo aynan "bir nechta mustaqil
# connection bir faylni bir vaqtda band qilishi" edi, WAL o'zi buni to'liq
# hal qilmaydi (bitta yozuvchi qulfi hamon bitta bo'lib qoladi, va har bir
# YANGI connection ochish/PRAGMA sozlash ham qo'shimcha xarajat).
#
# Endi: process ichida FAQAT BITTA doimiy connection bor, va unga murojaat
# `_conn_lock` (oddiy Python Lock) orqali navbatma-navbat qilinadi. Bu
# SQLite fayl darajasidagi qulf-kutish (OS darajasida, sekin, oldindan
# aytib bo'lmaydigan) ni tez, process-ichi Python Lock navbatiga
# almashtiradi — har bir operatsiya alohida millisekundlarda tugaydi,
# navbatda kutish esa haqiqiy ish vaqtining o'zi (millisekundlar), 15s
# busy-timeout emas. Xuddi shu naqsh vector_memory.py da FAISS uchun
# tasdiqlangan (bu sessiyada) — bu yerda takrorlanmoqda, lekin
# vector_memory.py ning o'zi TEGILMAGAN.
_conn_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(_DB_PATH, timeout=10, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")      # Crash-safe
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.execute("PRAGMA cache_size=-32000")     # 32 MB kesh
        _conn.execute("PRAGMA temp_store=MEMORY")
    return _conn


@contextmanager
def _db():
    """Barcha chaqiruvchilar shu orqali BITTA doimiy connection'ni
    navbatma-navbat (RLock bilan) ishlatadi — API o'zgarmagan (hali ham
    `with _db() as conn:`), shuning uchun quyidagi ~30 funksiyaning
    HECH biri o'zgarishi shart emas."""
    with _conn_lock:
        conn = _get_conn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            log.error("[PM] DB xato: %s", e)
            raise


_SCHEMA_STMTS = [
    # Suhbatlar — cheksiz
    """CREATE TABLE IF NOT EXISTS conversations (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ts         TEXT    NOT NULL DEFAULT (datetime('now')),
        session_id TEXT    DEFAULT '',
        role       TEXT    NOT NULL,
        content    TEXT    NOT NULL,
        emotion    TEXT    DEFAULT '',
        person     TEXT    DEFAULT '',
        topic      TEXT    DEFAULT '',
        importance REAL    DEFAULT 0.5
    )""",

    # FTS qidiruv
    """CREATE VIRTUAL TABLE IF NOT EXISTS conv_fts
       USING fts5(content, content='conversations', content_rowid='id')""",

    # Muhim voqealar
    """CREATE TABLE IF NOT EXISTS episodes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ts         TEXT    NOT NULL DEFAULT (datetime('now')),
        title      TEXT    NOT NULL,
        description TEXT   NOT NULL,
        emotion    TEXT    DEFAULT '',
        importance REAL    DEFAULT 0.5,
        persons    TEXT    DEFAULT '',
        tags       TEXT    DEFAULT ''
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS ep_fts
       USING fts5(title, description, content='episodes', content_rowid='id')""",

    # Fikrlar va xulosalar
    """CREATE TABLE IF NOT EXISTS reflections (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        ts       TEXT    NOT NULL DEFAULT (datetime('now')),
        content  TEXT    NOT NULL,
        ref_type TEXT    DEFAULT 'general',
        importance REAL  DEFAULT 0.5
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS refl_fts
       USING fts5(content, content='reflections', content_rowid='id')""",

    # Bilimlar
    """CREATE TABLE IF NOT EXISTS knowledge (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ts         TEXT    NOT NULL DEFAULT (datetime('now')),
        topic      TEXT    NOT NULL,
        content    TEXT    NOT NULL,
        source     TEXT    DEFAULT '',
        confidence REAL    DEFAULT 0.7,
        verified   INTEGER DEFAULT 0
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS know_fts
       USING fts5(topic, content, content='knowledge', content_rowid='id')""",

    # Ichki fikrlar
    """CREATE TABLE IF NOT EXISTS inner_thoughts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ts         TEXT    NOT NULL DEFAULT (datetime('now')),
        query      TEXT    DEFAULT '',
        thought    TEXT    NOT NULL,
        confidence REAL    DEFAULT 0.7
    )""",

    # His-tuyg'u tarixi
    """CREATE TABLE IF NOT EXISTS emotions (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        TEXT    NOT NULL DEFAULT (datetime('now')),
        emotion   TEXT    NOT NULL,
        intensity REAL    DEFAULT 0.5,
        trigger   TEXT    DEFAULT '',
        valence   REAL    DEFAULT 0.0
    )""",

    # Qoidalar
    """CREATE TABLE IF NOT EXISTS rules (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        TEXT    NOT NULL DEFAULT (datetime('now')),
        content   TEXT    NOT NULL,
        rule_type TEXT    DEFAULT 'general',
        source    TEXT    DEFAULT '',
        active    INTEGER DEFAULT 1
    )""",

    # Maqsadlar arxivi (tugagan maqsadlar ham saqlanadi)
    """CREATE TABLE IF NOT EXISTS goals_archive (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_created  TEXT    NOT NULL DEFAULT (datetime('now')),
        ts_completed TEXT   DEFAULT NULL,
        title       TEXT    NOT NULL,
        description TEXT    DEFAULT '',
        goal_type   TEXT    DEFAULT 'short_term',
        priority    INTEGER DEFAULT 3,
        final_progress REAL DEFAULT 0.0,
        status      TEXT    DEFAULT 'active',
        notes       TEXT    DEFAULT ''
    )""",

    # Indekslar
    "CREATE INDEX IF NOT EXISTS idx_conv_ts      ON conversations(ts)",
    "CREATE INDEX IF NOT EXISTS idx_conv_person  ON conversations(person)",
    "CREATE INDEX IF NOT EXISTS idx_conv_emotion ON conversations(emotion)",
    "CREATE INDEX IF NOT EXISTS idx_ep_imp       ON episodes(importance DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ep_ts        ON episodes(ts)",
    "CREATE INDEX IF NOT EXISTS idx_know_topic   ON knowledge(topic)",
    "CREATE INDEX IF NOT EXISTS idx_refl_ts      ON reflections(ts)",
]


def _init_db() -> None:
    try:
        with _db() as conn:
            for stmt in _SCHEMA_STMTS:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as e:
                    if "already exists" not in str(e).lower():
                        log.debug("[PM] schema: %s", e)
    except Exception as e:
        log.error("[PM] init xato: %s", e)


# ─────────────────────────────────────────────────────────────
# SAQLASH funksiyalari
# ─────────────────────────────────────────────────────────────

def remember_conversation(user_msg: str, bot_msg: str,
                          emotion: str = "", person: str = "",
                          session_id: str = "", topic: str = "") -> None:
    """Suhbatni ikki tomon bilan saqlash. Hech qachon o'chmaydi."""
    ts = datetime.now().isoformat()
    try:
        with _db() as conn:
            for role, content in [("user", user_msg), ("assistant", bot_msg)]:
                content = (content or "").strip()
                if not content:
                    continue
                cur = conn.execute(
                    "INSERT INTO conversations(ts,session_id,role,content,emotion,person,topic,importance)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (ts, session_id or "", role, content,
                     emotion or "", person or "", topic or "", 0.6)
                )
                rid = cur.lastrowid
                try:
                    conn.execute(
                        "INSERT INTO conv_fts(rowid,content) VALUES(?,?)", (rid, content)
                    )
                except Exception:
                    pass
    except Exception as e:
        log.error("[PM] conv saqlash xato: %s", e)


def remember_episode(title: str, description: str,
                     emotion: str = "", importance: float = 0.7,
                     persons: str = "", tags: str = "") -> int:
    """Muhim voqeani saqlash."""
    ts = datetime.now().isoformat()
    try:
        with _db() as conn:
            cur = conn.execute(
                "INSERT INTO episodes(ts,title,description,emotion,importance,persons,tags)"
                " VALUES(?,?,?,?,?,?,?)",
                (ts, title[:200], description[:1000],
                 emotion, importance, persons, tags)
            )
            rid = cur.lastrowid
            try:
                conn.execute(
                    "INSERT INTO ep_fts(rowid,title,description) VALUES(?,?,?)",
                    (rid, title[:200], description[:1000])
                )
            except Exception:
                pass
            return rid
    except Exception as e:
        log.error("[PM] episode saqlash xato: %s", e)
    return -1


def remember_reflection(content: str, ref_type: str = "general",
                        importance: float = 0.5) -> int:
    """Fikr / xulosa saqlash."""
    content = (content or "").strip()
    if not content:
        return -1
    ts = datetime.now().isoformat()
    try:
        with _db() as conn:
            cur = conn.execute(
                "INSERT INTO reflections(ts,content,ref_type,importance) VALUES(?,?,?,?)",
                (ts, content, ref_type, importance)
            )
            rid = cur.lastrowid
            try:
                conn.execute("INSERT INTO refl_fts(rowid,content) VALUES(?,?)", (rid, content))
            except Exception:
                pass
            return rid
    except Exception as e:
        log.error("[PM] reflection xato: %s", e)
    return -1


def remember_knowledge(topic: str, content: str, source: str = "",
                       confidence: float = 0.7) -> int:
    """Bilim saqlash."""
    content = (content or "").strip()
    if not content:
        return -1
    ts = datetime.now().isoformat()
    try:
        with _db() as conn:
            cur = conn.execute(
                "INSERT INTO knowledge(ts,topic,content,source,confidence) VALUES(?,?,?,?,?)",
                (ts, topic or "general", content, source, confidence)
            )
            rid = cur.lastrowid
            try:
                conn.execute(
                    "INSERT INTO know_fts(rowid,topic,content) VALUES(?,?,?)",
                    (rid, topic or "general", content)
                )
            except Exception:
                pass
            return rid
    except Exception as e:
        log.error("[PM] knowledge xato: %s", e)
    return -1


def remember_thought(thought: str, query: str = "", confidence: float = 0.7) -> int:
    """Ichki fikr saqlash."""
    thought = (thought or "").strip()
    if not thought:
        return -1
    ts = datetime.now().isoformat()
    try:
        with _db() as conn:
            cur = conn.execute(
                "INSERT INTO inner_thoughts(ts,query,thought,confidence) VALUES(?,?,?,?)",
                (ts, query or "", thought, confidence)
            )
            return cur.lastrowid
    except Exception as e:
        log.error("[PM] thought xato: %s", e)
    return -1


def remember_emotion(emotion: str, intensity: float = 0.5,
                     trigger: str = "", valence: float = 0.0) -> int:
    """His-tuyg'uni saqlash."""
    ts = datetime.now().isoformat()
    try:
        with _db() as conn:
            cur = conn.execute(
                "INSERT INTO emotions(ts,emotion,intensity,trigger,valence) VALUES(?,?,?,?,?)",
                (ts, emotion, intensity, trigger, valence)
            )
            return cur.lastrowid
    except Exception as e:
        log.error("[PM] emotion xato: %s", e)
    return -1


def remember_rule(content: str, rule_type: str = "general", source: str = "") -> int:
    """Qoida saqlash."""
    content = (content or "").strip()
    if not content:
        return -1
    ts = datetime.now().isoformat()
    try:
        with _db() as conn:
            cur = conn.execute(
                "INSERT INTO rules(ts,content,rule_type,source,active) VALUES(?,?,?,?,1)",
                (ts, content, rule_type, source)
            )
            return cur.lastrowid
    except Exception as e:
        log.error("[PM] rule xato: %s", e)
    return -1


# ─────────────────────────────────────────────────────────────
# ESLASH funksiyalari
# ─────────────────────────────────────────────────────────────

import re as _re

# Qidiruvda foydasiz so'zlar — RU / EN / UZ
_SEARCH_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "in", "on",
    "at", "for", "and", "or", "but", "it", "this", "that", "you", "your", "me",
    "my", "we", "they", "what", "how", "why", "when", "where", "who", "do",
    "does", "did", "can", "could", "would", "should", "about", "with", "tell",
    "что", "как", "это", "мы", "ты", "я", "он", "она", "они", "мой", "твой",
    "не", "на", "в", "с", "по", "и", "или", "но", "чём", "чем", "о", "об",
    "bilan", "uchun", "bu", "shu", "men", "sen", "biz", "ular", "ham", "va",
    "nima", "qanday", "nega", "qachon", "kim", "yoki", "lekin", "juda",
}

_SEARCH_WORD = _re.compile(r"[^\W\d_]{3,}", _re.UNICODE)


def _search_terms(text: str, max_terms: int = 6) -> List[str]:
    """Jumladan qidiruvga yaroqli so'zlarni ajratadi."""
    words = [w.lower() for w in _SEARCH_WORD.findall(text or "")]
    seen, out = set(), []
    for w in words:
        if w in _SEARCH_STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
    # Uzunroq so'z odatda mazmunliroq
    out.sort(key=len, reverse=True)
    return out[:max_terms]


def _fts_query(text: str) -> str:
    """FTS5 uchun xavfsiz so'rov: prefiks moslik va OR.

    Ilgari butun jumla MATCH ga uzatilardi. FTS5 uni so'rov sintaksisi
    deb o'qiydi: "Помнишь, о чём мы вчера говорили?" tinish belgilari
    sabab xato beradi, xato bo'lmasa ham BARCHA so'zlar mos kelishini
    talab qiladi — shuning uchun deyarli hech narsa topilmasdi.

    Prefiks (`слов*`) rus tili qo'shimchalarini ham qamrab oladi:
    "рекурсия" saqlangan bo'lsa "рекурсию" ham topiladi.
    """
    terms = _search_terms(text)
    if not terms:
        return ""
    return " OR ".join('"%s"*' % t.replace('"', '') for t in terms)


# Avtomatik yaratilgan xulosa yozuvlari — bular haqiqiy suhbat emas,
# lekin har qidiruvda birinchi bo'lib chiqib natijani ifloslantiradi.
# Prefiks bo'yicha emas, ICHIDAN qidiriladi: apostrof belgisi turlicha
# yozilgan (' va ') va prefiks moslik ishlamasdi.
_NOISE_MARKERS = (
    "suhbatda eng ko",          # "So'nggi 50 suhbatda eng ko'p mavzular:"
    "eng ko'p mavzular",
    "самые частые темы",
    "most frequent topics",
)


def _is_noise(content: str) -> bool:
    c = (content or "").lower()
    return any(m in c for m in _NOISE_MARKERS)


def _flatten(text: str) -> str:
    """Ko'p qatorli yozuvni bir qatorga keltiradi va rol belgilarini tozalaydi.

    Eski yozuvlar "[User]: ...\\n[Bot]: ..." shaklida saqlangan. Kontekstga
    shundayligicha tushsa, "[Bot]:" qatori YANGI BO'LIM sarlavhasi deb
    o'qiladi — ablatsiyada soxta "[Bot]" bo'limi paydo bo'lgan edi.
    """
    t = " ".join((text or "").split())
    for marker, repl in (("[User]:", "Siz:"), ("[Bot]:", "Men:"),
                         ("[user]:", "Siz:"), ("[bot]:", "Men:")):
        t = t.replace(marker, repl)
    # Qolgan qator boshidagi kvadrat qavsni zararsizlantirish
    if t.startswith("["):
        t = "· " + t[1:]
    return t.strip()


def recall(query: str, limit: int = 10) -> List[Dict]:
    """Universal qidirish — hamma joydan."""
    results = []
    q = (query or "").strip()
    if not q:
        return results
    fts_q = _fts_query(q)
    terms = _search_terms(q)

    try:
        with _db() as conn:
            # Suhbatlardan
            try:
                rows = conn.execute(
                    "SELECT c.id,c.ts,c.role,c.content,c.emotion,c.person"
                    " FROM conversations c JOIN conv_fts f ON c.id=f.rowid"
                    " WHERE f.content MATCH ? ORDER BY rank LIMIT ?",
                    (fts_q or q, limit)
                ).fetchall()
            except Exception:
                rows = []
            if not rows and terms:
                # Zaxira: har SO'Z bo'yicha LIKE. Ilgari butun jumla
                # qidirilardi va deyarli hech qachon mos kelmasdi.
                where = " OR ".join("content LIKE ?" for _ in terms)
                rows = conn.execute(
                    "SELECT id,ts,role,content,emotion,person FROM conversations"
                    f" WHERE {where} ORDER BY ts DESC LIMIT ?",
                    tuple(f"%{t}%" for t in terms) + (limit,)
                ).fetchall()
            for r in rows:
                if _is_noise(r["content"]):
                    continue
                results.append({
                    "type": "conversation", "ts": r["ts"],
                    "role": r["role"], "content": r["content"][:200],
                    "emotion": r["emotion"], "person": r["person"]
                })

            # Voqealardan
            try:
                rows = conn.execute(
                    "SELECT e.id,e.ts,e.title,e.description,e.emotion,e.importance"
                    " FROM episodes e JOIN ep_fts f ON e.id=f.rowid"
                    " WHERE f.description MATCH ? ORDER BY rank LIMIT ?",
                    (fts_q or q, max(1, limit // 2))
                ).fetchall()
            except Exception:
                rows = conn.execute(
                    "SELECT id,ts,title,description,emotion,importance FROM episodes"
                    " WHERE description LIKE ? OR title LIKE ?"
                    " ORDER BY importance DESC LIMIT ?",
                    (f"%{q}%", f"%{q}%", limit // 2)
                ).fetchall()
            for r in rows:
                results.append({
                    "type": "episode", "ts": r["ts"],
                    "title": r["title"], "content": r["description"][:200],
                    "emotion": r["emotion"], "importance": r["importance"]
                })

            # Bilimlardan
            try:
                rows = conn.execute(
                    "SELECT k.id,k.ts,k.topic,k.content,k.confidence"
                    " FROM knowledge k JOIN know_fts f ON k.id=f.rowid"
                    " WHERE f.content MATCH ? ORDER BY rank LIMIT ?",
                    (fts_q or q, limit // 2)
                ).fetchall()
            except Exception:
                rows = conn.execute(
                    "SELECT id,ts,topic,content,confidence FROM knowledge"
                    " WHERE content LIKE ? OR topic LIKE ? ORDER BY confidence DESC LIMIT ?",
                    (f"%{q}%", f"%{q}%", limit // 2)
                ).fetchall()
            for r in rows:
                results.append({
                    "type": "knowledge", "ts": r["ts"],
                    "topic": r["topic"], "content": r["content"][:200],
                    "confidence": r["confidence"]
                })

            # Fikrlardan
            try:
                rows = conn.execute(
                    "SELECT id,ts,content,ref_type FROM reflections"
                    " WHERE content LIKE ? ORDER BY ts DESC LIMIT ?",
                    (f"%{q}%", limit // 2)
                ).fetchall()
                for r in rows:
                    results.append({
                        "type": "reflection", "ts": r["ts"],
                        "content": r["content"][:200], "ref_type": r["ref_type"]
                    })
            except Exception:
                pass

    except Exception as e:
        log.error("[PM] recall xato: %s", e)

    results.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return _clean_results(results, limit)


def _clean_results(rows: List[Dict], limit: int) -> List[Dict]:
    """Shovqin va takrorlarni olib tashlash.

    Ikki muammo o'lchangan edi:
      1. Avtomatik xulosa yozuvlari ("So'nggi 50 suhbatda eng ko'p
         mavzular: ...") har qidiruvda yuqorida chiqardi. Ular
         reflections jadvalidan keladi, shuning uchun faqat
         conversations'ga qo'yilgan filtr ularni tutmasdi.
      2. Bir xil matn 3 marta qaytardi (user va bot nusxalari +
         FTS takrori) va uchta o'rinni egallardi.
    """
    seen: set = set()
    out: List[Dict] = []
    for r in rows:
        txt = _flatten(r.get("content") or r.get("title") or "")
        if not txt or _is_noise(txt):
            continue
        if r.get("content"):
            r = {**r, "content": txt}
        key = " ".join(txt.lower().split())[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= limit:
            break
    return out


def recall_about_person(name: str, limit: int = 30) -> List[Dict]:
    """Biror shaxs haqidagi barcha xotiralar — hech qachon o'chmagan."""
    results = []
    name = (name or "").strip()
    if not name:
        return results
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT id,ts,role,content,emotion FROM conversations"
                " WHERE person LIKE ? OR content LIKE ?"
                " ORDER BY ts DESC LIMIT ?",
                (f"%{name}%", f"%{name}%", limit)
            ).fetchall()
            for r in rows:
                results.append({
                    "type": "conversation", "ts": r["ts"],
                    "role": r["role"], "content": r["content"][:200],
                    "emotion": r["emotion"]
                })
    except Exception as e:
        log.error("[PM] person recall xato: %s", e)
    return results


def recall_by_emotion(emotion: str, limit: int = 20) -> List[Dict]:
    """His-tuyg'u bo'yicha xotiralar."""
    results = []
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT id,ts,role,content,emotion FROM conversations"
                " WHERE emotion LIKE ? ORDER BY ts DESC LIMIT ?",
                (f"%{emotion}%", limit)
            ).fetchall()
            for r in rows:
                results.append({
                    "ts": r["ts"], "role": r["role"],
                    "content": r["content"][:200], "emotion": r["emotion"]
                })
            # Emotion jadvalidan ham
            rows2 = conn.execute(
                "SELECT ts,emotion,intensity,trigger FROM emotions"
                " WHERE emotion LIKE ? ORDER BY ts DESC LIMIT ?",
                (f"%{emotion}%", limit // 2)
            ).fetchall()
            for r in rows2:
                results.append({
                    "type": "emotion_event", "ts": r["ts"],
                    "emotion": r["emotion"], "intensity": r["intensity"],
                    "content": r["trigger"]
                })
    except Exception as e:
        log.error("[PM] emotion recall xato: %s", e)
    return results


def recall_recent_conversations(limit: int = 30) -> List[Dict]:
    """Oxirgi suhbatlar — hech qachon o'chirilmagan tarix."""
    results = []
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT ts,role,content,emotion,person FROM conversations"
                " ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
            for r in rows:
                results.append({
                    "ts": r["ts"], "role": r["role"],
                    "content": r["content"][:300],
                    "emotion": r["emotion"], "person": r["person"]
                })
    except Exception as e:
        log.error("[PM] recent xato: %s", e)
    return list(reversed(results))


def recall_all_episodes(limit: int = 100) -> List[Dict]:
    """Barcha muhim voqealar — eng muhimi birinchi."""
    results = []
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT ts,title,description,emotion,importance,persons"
                " FROM episodes ORDER BY importance DESC, ts DESC LIMIT ?",
                (limit,)
            ).fetchall()
            for r in rows:
                results.append({
                    "ts": r["ts"], "title": r["title"],
                    "description": r["description"][:200],
                    "emotion": r["emotion"], "importance": r["importance"],
                    "persons": r["persons"]
                })
    except Exception as e:
        log.error("[PM] episodes xato: %s", e)
    return results


def recall_rules(active_only: bool = True, limit: int = 50) -> List[Dict]:
    """O'rganilgan qoidalar."""
    results = []
    try:
        with _db() as conn:
            q = "SELECT ts,content,rule_type FROM rules"
            if active_only:
                q += " WHERE active=1"
            q += " ORDER BY ts DESC LIMIT ?"
            rows = conn.execute(q, (limit,)).fetchall()
            for r in rows:
                results.append({
                    "ts": r["ts"], "content": r["content"],
                    "rule_type": r["rule_type"]
                })
    except Exception as e:
        log.error("[PM] rules xato: %s", e)
    return results


def get_full_history_count() -> Dict[str, int]:
    """Barcha xotira jadvallari statistikasi."""
    stats: Dict[str, int] = {}
    tables = ["conversations","episodes","reflections","knowledge",
              "inner_thoughts","emotions","rules","goals_archive"]
    try:
        with _db() as conn:
            for t in tables:
                try:
                    row = conn.execute(f"SELECT COUNT(*) as c FROM {t}").fetchone()
                    stats[t] = row["c"] if row else 0
                except Exception:
                    stats[t] = 0
        stats["total"] = sum(stats.values())
        if os.path.exists(_DB_PATH):
            stats["db_size_mb"] = round(os.path.getsize(_DB_PATH) / 1024 / 1024, 2)
    except Exception as e:
        log.error("[PM] stats xato: %s", e)
    return stats


def get_stats() -> Dict[str, Any]:
    return get_full_history_count()


def get_context_for_llm(query: str = "", limit: int = 5) -> str:
    """LLM uchun doimiy xotiradan dolzarb kontekst.

    Tartib muhim: SO'ROVGA OID xotira birinchi, davomiylik ikkinchi.

    Ilgari teskari edi — birinchi o'rinda har doim bir xil oxirgi 5 ta
    yozuv turardi. O'lchov (ablation_test.py) buni ko'rsatdi: bo'lim
    8 xil savolga 1 xil chiqish berardi, ya'ni 0 bit ma'lumot. Savolga
    oid natija esa pastda, e'tibordan chetda qolardi.
    """
    parts: List[str] = []

    # 1. So'rovga oid xotira — ENG MUHIMI, birinchi o'rinda
    found = recall(query, limit=limit) if query else []
    if found:
        parts.append("[XOTIRA — so'rovingizga oid]")
        for f in found[:3]:
            txt = (f.get("content") or f.get("title") or "").strip()
            if not txt:
                continue
            ts_short = (f.get("ts") or "")[:10]
            parts.append(f"  • [{ts_short}] {txt[:110]}")

    # 2. Oxirgi almashinuv — suhbat ipini yo'qotmaslik uchun.
    #    5 emas 3 ta: qolgani doimiy to'ldiruvchi edi.
    recent = recall_recent_conversations(limit=6)
    if recent:
        parts.append("[DOIMIY XOTIRA — oxirgi suhbat]")
        for r in recent[-3:]:
            role_lbl = "Siz" if r["role"] == "user" else "Men"
            ts_short = r["ts"][:16] if r["ts"] else ""
            parts.append(f"  {role_lbl} [{ts_short}]: {r['content'][:80]}")

    # 3. Muhim voqealar — faqat so'rovga oid natija topilmaganda.
    #    Aks holda ular har javobda takrorlanib, o'rinni egallaydi.
    if not found:
        eps = recall_all_episodes(limit=3)
        if eps:
            parts.append("[MUHIM VOQEALAR]")
            for ep in eps[:2]:
                parts.append(f"  • {ep['title']}: {ep['description'][:60]}")

    return "\n".join(parts) if parts else ""


# Eskilikdan moslik — append_turn saqlanadi
def append_turn(user: str, assistant: str, result: str = "", path: str = "") -> None:
    """Eski interfeys — endi SQLite ga saqlaydi."""
    remember_conversation(
        user_msg=user,
        bot_msg=assistant,
        topic=result[:50] if result else ""
    )


def append_improvement(error: str, fix: str, path: str = "") -> None:
    """Eski interfeys — endi SQLite ga saqlaydi."""
    remember_reflection(
        content=f"Xato: {error[:150]} | Yechim: {fix[:150]}",
        ref_type="lesson",
        importance=0.7
    )


def recall_similar(query: str, path: str = "",
                   limit: int = 10) -> List[Dict[str, Any]]:
    """Eski interfeys — endi SQLite qidiruv."""
    found = recall(query, limit=limit)
    results = []
    for f in found:
        results.append({
            "user":      f.get("content", "")[:150] if f.get("role") == "user" else "",
            "assistant": f.get("content", "")[:150] if f.get("role") == "assistant" else "",
            "result":    "",
            "ok":        True,
        })
    return results


# ─────────────────────────────────────────────────────────────
# Ishga tushganda init
# ─────────────────────────────────────────────────────────────
_init_db()
