# -*- coding: utf-8 -*-
"""NeuroKey — Semantik (Vector) Xotira.

FAISS + OpenAI text-embedding-3-small yordamida
barcha suhbatlar ma'no bo'yicha saqlanadi va qidiriladi.

Oddiy kalit so'z izlash emas:
  "Python loop" → "for sikl", "iteratsiya", "while" ham topiladi.
  "Kasal bo'ldim" → "yaxshi emas edi", "ishlay olmadim" ham topiladi.

Arxitektura:
  - FAISS: vektorlar indeksi (tez qidirish)
  - SQLite: matn + metadata (id, content, date, category)
  - OpenAI text-embedding-3-small: matndan vektor (1536 o'lcham)
  - Fallback: OpenAI yo'q bo'lsa — oddiy SQLite LIKE search

2026-yil suniy ong — assotsiativ xotira qatlami.
"""
from __future__ import annotations

try: import permanent_memory as _vm_pm
except ImportError: _vm_pm = None
try: import episodic_memory as _vm_em
except ImportError: _vm_em = None

import json
import logging
import os
import sqlite3
import struct
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DB_PATH   = os.path.join(_BASE_DIR, "data", "vector_memory.db")
_IDX_PATH  = os.path.join(_BASE_DIR, "data", "vector_memory.faiss")

# ── EMBEDDING BACKEND ───────────────────────────────────────────────────────
# ROOT-CAUSE FIX (2026-09-25, o'lchov bilan topildi):
#   [ORCH_SLOW_MODULE] vector_memory.get_context_for_llm = 4870ms
#   [ONG-TASHLANDI] timeout: vector_memory(2515ms)
# Sabab: _get_embedding() HAR savolda OpenAI `text-embedding-3-small` ga
# TARMOQ so'rovi yuborardi. `.env` dagi OPENAI_API_KEY esa yaroqsiz
# (401 Incorrect API key — jurnalda tasdiqlangan), ustiga-ustak
# OPENAI_BASE_URL Groq'ga yo'naltirilgan bo'lsa Groq embedding API'ni
# umuman qo'llab-quvvatlamaydi. Natijada har turnda 8s timeout'li
# muvaffaqiyatsiz so'rov + orkestrator 0.6s timeout bilan qatlamni
# TASHLAB ketardi. Isbot: stats -> total_memories=857, faiss_vectors=80
# (ya'ni 857 xotiradan faqat 80 tasi vektor olgan — qolgani API xatosi).
#
# Yechim: LOKAL model (knowledge_index.py ALLAQACHON shu modelni
# ishlatadi — `paraphrase-multilingual-MiniLM-L12-v2`, 384 o'lcham).
# Model bir marta yuklanadi va IKKI modul o'rtasida BO'LISHILADI —
# qo'shimcha RAM yo'q. Tarmoq kerak emas, xarajat yo'q, uz/ru/en ni
# qo'llab-quvvatlaydi.
#
# OpenAI'ga qaytish: NEUROKEY_EMBED_BACKEND=openai (kalit haqiqiy
# OpenAI kaliti bo'lishi SHART — Groq bilan ishlamaydi).
_EMBED_BACKEND = (os.getenv("NEUROKEY_EMBED_BACKEND", "local") or "local").strip().lower()

_LOCAL_EMBED_DIM = 384     # paraphrase-multilingual-MiniLM-L12-v2
_OPENAI_EMBED_DIM = 1536   # text-embedding-3-small

EMBED_DIM = _LOCAL_EMBED_DIM if _EMBED_BACKEND == "local" else _OPENAI_EMBED_DIM
MAX_ENTRIES = 10_000       # maksimal yozuv soni
TOP_K_DEFAULT = 5          # standart qidiruv natijasi

_lock = threading.Lock()

# ─── FAISS YUKLANISHI ────────────────────────────────────────────────────────
try:
    import faiss as _faiss
    _HAVE_FAISS = True
except ImportError:
    _faiss = None
    _HAVE_FAISS = False
    log.warning("[VectorMem] faiss topilmadi — fallback SQLite LIKE ishlatiladi")

# ─── NUMPY ───────────────────────────────────────────────────────────────────
try:
    import numpy as _np
    _HAVE_NUMPY = True
except ImportError:
    _np = None
    _HAVE_NUMPY = False


# ════════════════════════════════════════════════════════════════════════════
#  SQLite yordamchi funksiyalar
# ════════════════════════════════════════════════════════════════════════════

# ROOT-CAUSE FIX (2026-09-13, real test bilan topildi — permanent_memory.py
# da 2026-08-19 da tasdiqlangan bilan BIR XIL naqsh, qarang shu faylning
# tarixi): ilgari HAR bir chaqiruv (_count_entries, add, search->_get_by_id,
# _search_sqlite, _prune_old, _init_db) o'zining YANGI sqlite3.connect()
# ulanishini ochardi VA HECH QACHON conn.close() qilmasdi (`with conn:`
# faqat commit/rollback qiladi, ulanishni yopmaydi) — 7 ta chaqiruv joyi,
# har biri cheksiz ko'payadigan ulanish oqishi (leak) edi.
#
# O'lchandi (leak_test.py, 2026-09-13): 2000 tagacha ochiq-qolgan ulanish
# yangi connect()+SELECT vaqtiga sezilarli ta'sir qilmadi (<5ms) — ya'ni
# leak yolg'iz o'zi ORCH_SLOW_MODULE logidagi 22413ms kechikishning sababi
# EMAS edi. Lekin alohida o'lchandi (stress_test.py): consciousness_
# orchestrator._EXECUTOR (max_workers=10) namunasidagi 10 ta parallel
# thread bir vaqtda shu naqsh bilan (har yozuvda yangi connection) faylga
# yozganda, oddiy SELECT COUNT(*) o'qishi 60-130ms gacha sekinlashdi —
# haqiqiy, o'lchanadigan qulf-raqobat, garchi yolg'iz o'zi 22s ni
# tushuntirmasa ham. Qolgan farq GIL/CPU raqobati bilan tushuntiriladi:
# gil_test.py bilan o'lchandi — InsightFace 5 ta ONNX modelini CPU'da
# fon threadida yuklash paytida (bug 3, face_arc.py) asosiy thread'dagi
# ODDIY (hech qanday SQLite'ga bog'liq bo'lmagan) Python operatsiyasi ham
# 813ms gacha to'xtab qoldi — vector_memory.get_stats() aynan shu CPU
# model-yuklash oynasida ishlagan (logda ikkalasi ketma-ket ko'rinadi),
# shuning uchun ikkala effekt (GIL raqobati + SQLite ulanish-per-call
# xarajati) BIRGALIKDA 22.4s ni beradi.
#
# Yechim — permanent_memory.py da tasdiqlangan bir xil arxitektura:
# process ichida FAQAT BITTA doimiy connection, navbatma-navbat
# _conn_lock (RLock) orqali. FAISS holati (_faiss_index/_faiss_id_map)
# ni himoya qiluvchi yuqoridagi `_lock` BUTUNLAY TEGILMAGAN — bu boshqa
# qulf, boshqa maqsad uchun (add()/search() ning native FAISS chaqiruv
# qismlari, ataylab lock hold time minimal qilingan, shu sessiyada
# tasdiqlangan — qayta o'zgartirilmaydi).
_conn_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    """Process ichida bir marta ochiladigan doimiy SQLite connection.
    DIQQAT: to'g'ridan-to'g'ri chaqirmang — _db_lock() context manager
    yoki (faqat o'qish uchun, tez yo'l) _conn_lock bilan birga ishlating,
    aks holda bir nechta thread bitta connection ustida poyga qiladi."""
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(_DB_PATH, timeout=10, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA temp_store=MEMORY")
    return _conn


@contextmanager
def _db():
    """Barcha yozuvchi chaqiruvlar shu orqali BITTA doimiy connection'ni
    navbatma-navbat (_conn_lock bilan) ishlatadi — xato bo'lsa rollback,
    aks holda commit (permanent_memory.py dagi _db() bilan bir xil)."""
    with _conn_lock:
        conn = _get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise


def _init_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                content  TEXT    NOT NULL,
                category TEXT    DEFAULT 'conversation',
                summary  TEXT    DEFAULT '',
                created  REAL    NOT NULL,
                date_str TEXT    NOT NULL,
                faiss_id INTEGER DEFAULT -1
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON memories(created)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON memories(category)")


# ════════════════════════════════════════════════════════════════════════════
#  FAISS indeks boshqaruvi
# ════════════════════════════════════════════════════════════════════════════

_faiss_index = None
_faiss_id_map: List[int] = []   # faiss_pos → db_id


def _load_faiss() -> None:
    """FAISS indeksini diskdan yuklash."""
    global _faiss_index, _faiss_id_map
    if not _HAVE_FAISS or not _HAVE_NUMPY:
        return
    try:
        if os.path.exists(_IDX_PATH) and os.path.exists(_IDX_PATH + ".map"):
            _loaded = _faiss.read_index(_IDX_PATH)
            # O'LCHAM MOS KELMASA — eski indeks boshqa embedding modeli bilan
            # qurilgan (masalan OpenAI 1536, hozir lokal 384). Aralashtirib
            # bo'lmaydi: qo'shish xato beradi, qidiruv ma'nosiz natija qaytaradi.
            # Eski faylni O'CHIRMAYMIZ — `.bak_<dim>` deb saqlaymiz, keyin
            # kerak bo'lsa qaytarish mumkin.
            if _loaded.d != EMBED_DIM:
                _bak = f"{_IDX_PATH}.bak_dim{_loaded.d}"
                log.warning(
                    "[VectorMem] Indeks o'lchami mos emas (%d != %d) — yangi "
                    "indeks yaratildi, eskisi saqlandi: %s",
                    _loaded.d, EMBED_DIM, os.path.basename(_bak))
                del _loaded
                for _src, _dst in ((_IDX_PATH, _bak),
                                   (_IDX_PATH + ".map", _bak + ".map")):
                    try:
                        if os.path.exists(_src):
                            os.replace(_src, _dst)
                    except OSError as _e:
                        log.debug("[VectorMem] zaxira xato: %s", _e)
                _faiss_index = _faiss.IndexFlatIP(EMBED_DIM)
                _faiss_id_map = []
                return
            _faiss_index = _loaded
            with open(_IDX_PATH + ".map", "r", encoding="utf-8") as f:
                _faiss_id_map = json.load(f)
            log.debug("[VectorMem] FAISS indeks yuklandi: %d vektor", _faiss_index.ntotal)
        else:
            _faiss_index = _faiss.IndexFlatIP(EMBED_DIM)  # Inner Product (cosine uchun normalize qilinadi)
            _faiss_id_map = []
    except Exception as e:
        log.warning("[VectorMem] FAISS yuklash xato: %s — yangi indeks yaratildi", e)
        _faiss_index = _faiss.IndexFlatIP(EMBED_DIM)
        _faiss_id_map = []


def _save_faiss() -> None:
    """FAISS indeksini diskka saqlash."""
    global _faiss_index, _faiss_id_map
    if not _HAVE_FAISS or _faiss_index is None:
        return
    try:
        os.makedirs(os.path.dirname(_IDX_PATH), exist_ok=True)
        _faiss.write_index(_faiss_index, _IDX_PATH)
        with open(_IDX_PATH + ".map", "w", encoding="utf-8") as f:
            json.dump(_faiss_id_map, f)
    except Exception as e:
        log.warning("[VectorMem] FAISS saqlash xato: %s", e)


# ════════════════════════════════════════════════════════════════════════════
#  Embedding funksiyasi
# ════════════════════════════════════════════════════════════════════════════

_embed_cache: Dict[str, List[float]] = {}   # {text_hash: vector}

# ─── OpenAI mijoz — BIR MARTA yaratiladi, qayta ishlatiladi ─────────────────
# BUG FIX (o'lchandi): ilgari _get_embedding() HAR CHAQIRISHDA yangi
# openai.OpenAI(...) mijoz yaratardi — bu har safar yangi httpx ulanish
# hovuzi (va potentsial yangi TCP+TLS handshake) degani edi. Jonli suhbat
# yo'lida bu qo'shimcha ~0.2-0.5s behuda kutish edi. Endi mijoz modul
# darajasida BIR MARTA yaratiladi va _prewarm() orqali fon threadida
# oldindan isitiladi (TCP+TLS+auth so'rovdan OLDIN ochiladi) — xuddi
# neurokey_prewarm._groq_prewarm() Groq uchun qilganidek.
_openai_client = None
_client_lock = threading.Lock()
_prewarm_done = False
_prewarm_lock = threading.Lock()


def _get_openai_client():
    """Keshlangan OpenAI mijozini qaytaradi — kerak bo'lsa bir marta yaratadi."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    with _client_lock:
        if _openai_client is None:
            import openai
            # BUG FIX (o'lchandi): max_retries ko'rsatilmagan edi — OpenAI SDK
            # standart bo'yicha max_retries=2 bilan ICHKI qayta-urinish +
            # eksponensial backoff qiladi (429/5xx/tarmoq xatosida). Har urinish
            # o'zining timeout=8.0 chegarasiga ega, LEKIN 3 urinish + backoff
            # (SDK MAX_RETRY_DELAY=8s gacha) yig'indisi ~30-40s gacha borishi
            # mumkin — bitta "oddiy" xotira qidiruvi uchun juda ko'p, ayniqsa bu
            # chaqiruv ko'pincha ORTIQCHA (ikkinchi marta, allaqachon orkestrator
            # parallel+timeout bilan chaqirgandan keyin) sodir bo'lardi (qarang
            # main.py'dagi 2026-08-18 tuzatish). Groq mijozi (llm_router.py)
            # ANIQ shu sabab bilan max_retries=0 ishlatadi — bu yerda ham xuddi
            # shunday: bitta muvaffaqiyatsiz urinish = darhol bo'sh natija
            # (chaqiruvchi _resolve()/timeout orqali navbatdagi turnda davom
            # etadi), cheksiz/uzun kutish emas.
            _openai_client = openai.OpenAI(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                timeout=8.0,
                max_retries=0,
            )
        return _openai_client


def _looks_like_openai_key() -> bool:
    """Haqiqiy OpenAI kaliti bormi? Groq kaliti (`gsk_`) yoki Groq'ga
    yo'naltirilgan base_url bo'lsa — embedding API ishlamaydi, shuning
    uchun so'rovni UMUMAN yubormaymiz (8s behuda kutishdan qochamiz)."""
    key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    base = (os.getenv("OPENAI_BASE_URL", "") or "").strip().lower()
    if "groq.com" in base:
        return False
    return key.startswith("sk-") and len(key) > 20


def _get_local_embedding(text: str) -> Optional[List[float]]:
    """Lokal SentenceTransformer orqali vektor — tarmoq kerak emas.

    knowledge_index.embed() qayta ishlatiladi, shuning uchun model
    xotirada BITTA nusxada bo'ladi (ikki modul bo'lishadi)."""
    try:
        import knowledge_index as _ki
        vecs = _ki.embed([text])
        if vecs is None or len(vecs) == 0:
            return None
        return [float(x) for x in vecs[0]]
    except Exception as e:
        log.debug("[VectorMem] lokal embedding xato: %s", e)
        return None


def _get_embedding(text: str) -> Optional[List[float]]:
    """Matndan vektor. Default — LOKAL model (tarmoqsiz)."""
    if not text or not text.strip():
        return None

    text = text.strip()[:2000]
    cache_key = str(hash(text))
    if cache_key in _embed_cache:
        return _embed_cache[cache_key]

    if _EMBED_BACKEND == "local":
        vec = _get_local_embedding(text)
        if vec is not None:
            _embed_cache[cache_key] = vec
            if len(_embed_cache) > 500:
                for k in list(_embed_cache.keys())[:100]:
                    del _embed_cache[k]
        return vec

    # OpenAI backend — faqat HAQIQIY OpenAI kaliti bilan
    if not _looks_like_openai_key():
        log.debug("[VectorMem] OpenAI embedding o'tkazildi — kalit mos emas")
        return None

    try:
        client = _get_openai_client()
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            dimensions=EMBED_DIM,
        )
        vec = resp.data[0].embedding
        _embed_cache[cache_key] = vec
        # Kesh hajmini cheklash
        if len(_embed_cache) > 500:
            oldest = list(_embed_cache.keys())[:100]
            for k in oldest:
                del _embed_cache[k]
        return vec
    except Exception as e:
        log.debug("[VectorMem] Embedding xato: %s", e)
        return None


def prewarm() -> None:
    """FON THREADIDA chaqirilishi kerak (masalan neurokey_prewarm.start()
    orqali) — OpenAI mijozini yaratadi VA bitta arzon so'rov yuboradi, shu
    orqali TCP+TLS+auth handshake jonli suhbatdan OLDIN sodir bo'ladi.
    Hech qachon chaqiruvchi threadni bloklamasin deb, faqat shu funksiyaning
    o'zi threadda ishga tushirilishi kerak (bu yerning ichida bloklaydi)."""
    global _prewarm_done
    with _prewarm_lock:
        if _prewarm_done:
            return
        try:
            _get_embedding("prewarm")
            _prewarm_done = True
            log.info("[VectorMem] OpenAI embedding ulanishi isitildi")
        except Exception as e:
            log.debug("[VectorMem] prewarm xato: %s", e)


def is_ready() -> bool:
    """Bloklamasdan: embedding ulanishi isitilganmi?"""
    return _prewarm_done


def _vec_to_numpy(vec: List[float]):
    """Vektorni normalized numpy arrayga aylantirish (cosine similarity uchun)."""
    if not _HAVE_NUMPY:
        return None
    arr = _np.array([vec], dtype=_np.float32)
    # L2 normalizatsiya — Inner Product = cosine similarity
    norm = _np.linalg.norm(arr, axis=1, keepdims=True)
    if norm[0, 0] > 0:
        arr = arr / norm
    return arr


# ════════════════════════════════════════════════════════════════════════════
#  Asosiy API
# ════════════════════════════════════════════════════════════════════════════

def initialize() -> None:
    """Bir marta chaqirish — DB va FAISS tayyorlash."""
    _init_db()
    _load_faiss()
    log.info("[VectorMem] Tayyor. FAISS=%s, entries=%d",
             _HAVE_FAISS, _count_entries())


def _count_entries() -> int:
    try:
        with _conn_lock:
            conn = _get_conn()
            row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def add(content: str,
        category: str = "conversation",
        summary: str = "") -> int:
    """Yangi xotira qo'shish.

    Args:
        content:  To'liq matn (user+assistant yoki har qanday)
        category: 'conversation' | 'fact' | 'reflection' | 'goal' | 'lesson'
        summary:  Qisqa xulosa (bo'sh bo'lsa avtomatik qisqartiriladi)

    Returns: db id
    """
    if not content or not content.strip():
        return -1

    content = content.strip()[:3000]
    if not summary:
        summary = content[:120].replace("\n", " ")

    now = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # DB ga qo'shish — _lock kerak emas, faiss global holatiga tegmaydi.
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO memories (content, category, summary, created, date_str, faiss_id) "
            "VALUES (?, ?, ?, ?, ?, -1)",
            (content, category, summary, now, date_str),
        )
        db_id = cur.lastrowid

    # FAISS ga vektor qo'shish
    if _HAVE_FAISS and _HAVE_NUMPY:
        # RACE FIX: embedding — tarmoq so'rovi (sekin, ~onlab-yuzlab ms,
        # ba'zan soniyalar). ATAYLAB _lock DAN TASHQARIDA hisoblanadi —
        # aks holda search() shu network chaqiruv tugaguncha bloklanib
        # qolardi (lock hold time ni minimallashtirish uchun).
        vec = _get_embedding(content)
        if vec:
            arr = _vec_to_numpy(vec)
            if arr is not None:
                # RACE FIX (asosiy tuzatish): _faiss_index/_faiss_id_map ga
                # yagona haqiqiy MUTATSIYA shu yerda — search() bilan bir
                # xil _lock orqali himoyalangan. Faqat native FAISS .add()
                # chaqiruvi + ro'yxatga qo'shish shu yerda — tarmoq/SQLite
                # ishlari qulfdan TASHQARIDA, kritik bo'limni minimal
                # ushlab turish uchun.
                with _lock:
                    if _faiss_index is not None:
                        faiss_pos = len(_faiss_id_map)
                        _faiss_index.add(arr)
                        _faiss_id_map.append(db_id)
                    else:
                        faiss_pos = None

                if faiss_pos is not None:
                    # DB da faiss_id ni yangilash — qulfdan tashqarida
                    with _db() as conn:
                        conn.execute(
                            "UPDATE memories SET faiss_id=? WHERE id=?",
                            (faiss_pos, db_id),
                        )
                    # Har 20 qo'shishda saqlash. RACE FIX: _save_faiss()
                    # ham _faiss_index/_faiss_id_map ni o'qiydi (diskka
                    # yozish uchun), shuning uchun u ham _lock ostida —
                    # aks holda diskka yozish paytida boshqa thread native
                    # .add()/.search() chaqirsa, xuddi asl bug kabi race
                    # bo'lardi. Bu 20 qo'shishda bir marta sodir bo'ladi —
                    # jonli suhbat yo'lida (add/search) emas, shuning
                    # uchun latency maqsadiga ta'sir qilmaydi.
                    if (faiss_pos + 1) % 20 == 0:
                        with _lock:
                            _save_faiss()

    # MAX_ENTRIES dan oshsa — eng eski 10% ni o'chirish
    count = _count_entries()
    if count > MAX_ENTRIES:
        _prune_old(int(MAX_ENTRIES * 0.1))

    return db_id


def search(query: str,
           top_k: int = TOP_K_DEFAULT,
           category: str = "") -> List[Dict[str, Any]]:
    """Semantik qidirish.

    Avval FAISS vektor qidirish (semantic).
    FAISS yo'q bo'lsa — SQLite LIKE fallback.

    Returns: [{id, content, summary, date_str, category, score}]
    """
    if not query or not query.strip():
        return []

    # === FAISS semantik qidirish ===
    if _HAVE_FAISS and _HAVE_NUMPY:
        # Tezkor bo'sh-indeks tekshiruvi — indeks hali bo'sh bo'lsa, qimmat
        # embedding (tarmoq) so'rovini umuman yubormaymiz. `.ntotal` o'qishi
        # ham _lock ostida — u ham xuddi shu global holatga tegadi.
        with _lock:
            _index_empty = _faiss_index is None or _faiss_index.ntotal == 0
        if _index_empty:
            return _search_sqlite(query, top_k, category)
        try:
            # Embedding — tarmoq/kesh, _lock DAN TASHQARIDA (add() bilan bir xil
            # sabab: qulfni tarmoq kutish vaqtiga qadar ushlab turmaslik).
            vec = _get_embedding(query)
            if vec:
                arr = _vec_to_numpy(vec)
                if arr is not None:
                    # RACE FIX: bu yerda ilgari _faiss_index.ntotal/.search()
                    # va _faiss_id_map hech qanday qulfsiz o'qilardi, add()
                    # esa ularni boshqa threadda _lock ostida mutatsiya
                    # qilardi. FAISS ning native add()/search() chaqiruvlari
                    # og'ir hisoblash paytida GIL ni bo'shatishi mumkin —
                    # shuning uchun bir vaqtda mutatsiya+o'qish native
                    # darajada aniqlanmagan xatti-harakat (eng yomon holatda
                    # process crash). Endi add() bilan BIR XIL _lock orqali
                    # himoyalangan — faqat native FAISS o'qish + id_map
                    # ko'chirish shu yerda, DB o'qish (_get_by_id) qulfdan
                    # TASHQARIDA — kritik bo'limni minimal ushlab turish
                    # uchun (lock hold time = faqat faiss.search() ishlash
                    # muddati, SQLite/tarmoq kutish vaqti emas).
                    with _lock:
                        if _faiss_index is None or _faiss_index.ntotal == 0:
                            scored_ids: List[Tuple[float, int]] = []
                        else:
                            k = min(top_k * 2, _faiss_index.ntotal)
                            scores, indices = _faiss_index.search(arr, k)
                            scored_ids = [
                                (float(s), _faiss_id_map[idx])
                                for s, idx in zip(scores[0], indices[0])
                                if 0 <= idx < len(_faiss_id_map)
                            ]

                    results = []
                    for score, db_id in scored_ids:
                        row = _get_by_id(db_id)
                        if row:
                            if category and row["category"] != category:
                                continue
                            results.append({
                                "id": row["id"],
                                "content": row["content"],
                                "summary": row["summary"],
                                "date_str": row["date_str"],
                                "category": row["category"],
                                "score": score,
                            })
                    results.sort(key=lambda x: x["score"], reverse=True)
                    return results[:top_k]
        except Exception as e:
            log.debug("[VectorMem] FAISS qidirish xato: %s — fallback", e)

    # === SQLite LIKE fallback ===
    return _search_sqlite(query, top_k, category)


def _search_sqlite(query: str,
                   top_k: int,
                   category: str = "") -> List[Dict[str, Any]]:
    """Oddiy kalit so'z izlash (FAISS yo'q bo'lganda)."""
    try:
        words = query.lower().split()[:5]
        if not words:
            return []
        conditions = ["content LIKE ?"] * len(words)
        params = [f"%{w}%" for w in words]
        cat_clause = " AND category=?" if category else ""
        if category:
            params.append(category)
        sql = (
            f"SELECT id, content, summary, date_str, category FROM memories "
            f"WHERE {' OR '.join(conditions)}{cat_clause} "
            f"ORDER BY created DESC LIMIT ?"
        )
        params.append(top_k)
        with _conn_lock:
            conn = _get_conn()
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": r["id"],
                "content": r["content"],
                "summary": r["summary"],
                "date_str": r["date_str"],
                "category": r["category"],
                "score": 0.5,
            }
            for r in rows
        ]
    except Exception as e:
        log.debug("[VectorMem] SQLite qidirish xato: %s", e)
        return []


def _get_by_id(db_id: int) -> Optional[sqlite3.Row]:
    try:
        with _conn_lock:
            conn = _get_conn()
            return conn.execute(
                "SELECT id, content, summary, date_str, category FROM memories WHERE id=?",
                (db_id,),
            ).fetchone()
    except Exception:
        return None


def _prune_old(n: int) -> None:
    """Eng eski n ta yozuvni o'chirish."""
    try:
        with _db() as conn:
            conn.execute(
                "DELETE FROM memories WHERE id IN "
                "(SELECT id FROM memories ORDER BY created ASC LIMIT ?)",
                (n,),
            )
    except Exception as e:
        log.debug("[VectorMem] Tozalash xato: %s", e)


def add_conversation(user: str, assistant: str) -> int:
    """Suhbat turnini qo'shish (user + assistant)."""
    content = f"Foydalanuvchi: {user}\nNeuroKey: {assistant}"
    summary = (user[:60] + " → " + assistant[:60]).replace("\n", " ")
    return add(content, category="conversation", summary=summary)


def add_fact(content: str) -> int:
    """Muhim fakt qo'shish."""
    return add(content, category="fact")


def add_reflection(content: str) -> int:
    """Refleksiya qo'shish."""
    return add(content, category="reflection")


def get_context_for_llm(query: str, top_k: int = 3) -> str:
    """LLM uchun tegishli xotiralarni matn sifatida qaytarish."""
    results = search(query, top_k=top_k)
    if not results:
        return ""
    lines = ["[SEMANTIK XOTIRA — o'xshash suhbatlar:]"]
    for i, r in enumerate(results, 1):
        date = r.get("date_str", "")
        summary = r.get("summary", r.get("content", ""))[:150]
        score = r.get("score", 0)
        lines.append(f"  {i}. [{date}] {summary}  (o'xshashlik: {score:.0%})")
    return "\n".join(lines)


def reindex_all(batch: int = 64, progress: bool = True) -> Dict[str, int]:
    """SQLite dagi BARCHA xotirani qayta vektorlaydi (embedding backend
    o'zgarganda kerak).

    Nega kerak: embedding modeli o'zgarsa (OpenAI 1536 -> lokal 384) eski
    FAISS indeks ishlatilmaydi va `faiss_vectors` 0 bo'lib qoladi — ya'ni
    semantik xotira BO'SH, garchi SQLite da 857 yozuv turgan bo'lsa ham.
    Bu funksiya shu bo'shliqni to'ldiradi.

    Fon threadida yoki qo'lda ishga tushirilishi kerak (jonli suhbat
    yo'lida EMAS — yuzlab embedding hisoblanadi):

        python -c "import vector_memory as v; v.reindex_all()"

    Returns: {"total": ..., "indexed": ..., "skipped": ...}
    """
    global _faiss_index, _faiss_id_map
    if not (_HAVE_FAISS and _HAVE_NUMPY):
        log.warning("[VectorMem] reindex: faiss/numpy yo'q")
        return {"total": 0, "indexed": 0, "skipped": 0}

    with _conn_lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, content FROM memories ORDER BY created"
        ).fetchall()

    total = len(rows)
    if progress:
        print(f"[VectorMem] reindex: {total} xotira, backend={_EMBED_BACKEND}, "
              f"o'lcham={EMBED_DIM}", flush=True)

    # Toza indeks — eskisi boshqa o'lchamda bo'lishi mumkin
    with _lock:
        _faiss_index = _faiss.IndexFlatIP(EMBED_DIM)
        _faiss_id_map = []

    indexed = skipped = 0
    for start in range(0, total, batch):
        chunk = rows[start:start + batch]
        vecs, ids = [], []
        for row in chunk:
            db_id, content = row[0], row[1]
            vec = _get_embedding(content or "")
            if not vec:
                skipped += 1
                continue
            arr = _vec_to_numpy(vec)
            if arr is None:
                skipped += 1
                continue
            vecs.append(arr)
            ids.append(db_id)

        if vecs:
            stacked = _np.vstack(vecs)
            with _lock:
                pos0 = _faiss_index.ntotal
                _faiss_index.add(stacked)
                _faiss_id_map.extend(ids)
            with _conn_lock:
                conn = _get_conn()
                with conn:
                    for offset, db_id in enumerate(ids):
                        conn.execute("UPDATE memories SET faiss_id=? WHERE id=?",
                                     (pos0 + offset, db_id))
            indexed += len(ids)

        if progress:
            print(f"  ... {min(start + batch, total)}/{total} "
                  f"(indekslandi {indexed}, o'tkazildi {skipped})", flush=True)

    _save_faiss()
    if progress:
        print(f"[VectorMem] reindex TUGADI: {indexed} vektor, {skipped} o'tkazildi",
              flush=True)
    return {"total": total, "indexed": indexed, "skipped": skipped}


def get_stats() -> Dict[str, Any]:
    """Statistika."""
    count = _count_entries()
    with _lock:
        faiss_count = _faiss_index.ntotal if (_HAVE_FAISS and _faiss_index) else 0
    return {
        "total_memories": count,
        "faiss_vectors": faiss_count,
        "have_faiss": _HAVE_FAISS,
        "have_numpy": _HAVE_NUMPY,
        "db_path": _DB_PATH,
    }


def save() -> None:
    """Faiss indeksini darhol saqlash."""
    _save_faiss()


# ════════════════════════════════════════════════════════════════════════════
#  Modul yuklanishida avtomatik init
# ════════════════════════════════════════════════════════════════════════════
try:
    initialize()
except Exception as _e:
    log.warning("[VectorMem] Initialize xato: %s", _e)
