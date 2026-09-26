# -*- coding: utf-8 -*-
"""NeuroKey — Vektor bilim indeksi (Semantic Knowledge Index).

Maqsad: har qanday savolga <1 soniyada javob — LOKAL, tarmoqqa chiqmasdan.

Ultron tezligi tarmoqqa borishdan emas, ma'lumot ALLAQACHON qurilma ichida
bo'lishidan keladi. Bu modul aynan shuni beradi:

  1. Matn -> chunk -> embedding (RTX GPU) -> FAISS indeks (diskda)
  2. Savol -> embedding -> FAISS qidiruv -> eng yaqin bo'laklar (kosinus)
  3. Qidiruv vaqti: millisekundlar (indeks xotirada)

Eski knowledge_base.py (kalit-so'z fayl yuklovchi) saqlanadi — bu semantik
qatlam uning ustiga qo'shiladi.

Manbalar bosqichma-bosqich:
  - Sizning 16 093 xotira yozuvingiz (permanent_memory)
  - Starter faktlar (build_knowledge.py)
  - To'liq Wikipedia (build_wikipedia_index.py — kechasi ishga tushiriladi)

MODEL: paraphrase-multilingual-MiniLM-L12-v2 (384-o'lchamli, RU/EN/UZ).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
# Indeks D: da saqlanadi (joy ko'p: 397GB). Qidiruv RAM da bo'lgani uchun
# disk joyi tezlikka ta'sir qilmaydi. NEUROKEY_KB_DIR bilan o'zgartiriladi.
# MUHIM (2026-09): D: dagi 15GB indeks faqat NEUROKEY_USE_LARGE_KB=1 bo'lsa
# tanlanadi — aks holda kichik data/knowledge_index (8GB RAM uchun).
def _default_kb_dir() -> str:
    explicit = (os.getenv("NEUROKEY_KB_DIR") or "").strip()
    if explicit:
        return explicit
    use_large = os.getenv("NEUROKEY_USE_LARGE_KB", "0").strip().lower() in ("1", "true", "yes")
    large_path = r"D:\neurokey_knowledge"
    if use_large and os.path.isdir(large_path):
        return large_path
    return os.path.join(_BASE_DIR, "data", "knowledge_index")


_KB_DIR     = _default_kb_dir()
_INDEX_PATH = os.path.join(_KB_DIR, "kb.faiss")
_META_PATH  = os.path.join(_KB_DIR, "kb_meta.jsonl")

_MODEL_NAME = os.getenv("NEUROKEY_KB_MODEL",
                        "paraphrase-multilingual-MiniLM-L12-v2")
_DIM = 384

_lock = threading.Lock()
_model_lock = threading.Lock()
_model = None
_index = None
_meta: List[dict] = []


# ── Model (lazy, GPU) ────────────────────────────────────────────────────────

def _get_model():
    """Bloklovchi: model xotirada bo'lmasa, yuklab bo'lguncha kutadi.

    _model_lock bilan himoyalangan — ilgari lock YO'Q edi, ya'ni ikki
    thread (masalan startup prewarm va foydalanuvchi savoli) BIR VAQTDA
    SentenceTransformer(...) ni ikki marta yuklashga urinishi mumkin edi
    (GPU xotira isrofi + sekinlik). Endi faqat bitta thread yuklaydi,
    boshqalari tayyor bo'lguncha shu yerda kutadi."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("[KB] model yuklanmoqda (%s) -> %s", _MODEL_NAME, dev)
        _model = SentenceTransformer(_MODEL_NAME, device=dev)
    return _model


def is_model_ready() -> bool:
    """Bloklamasdan: embedding modeli (SentenceTransformer) xotirada
    tayyor turibdimi? Katta bilim bazasi indeksidan MUSTAQIL — model
    yengil, lekin baribir birinchi yuklanishda soniyalab vaqt oladi.

    Jonli suhbat yo'lida (question_memory kabi) embed() ni chaqirishdan
    OLDIN shu bilan tekshirish kerak — aks holda tayyor bo'lmagan modelni
    so'rov threadida yuklab, javobni bloklab qo'yish xavfi bor."""
    return _model is not None


def embed(texts: List[str]):
    """Matnlarni normalize qilingan vektorga (kosinus qidiruv uchun)."""
    m = _get_model()
    vecs = m.encode(texts, batch_size=64, show_progress_bar=False,
                    convert_to_numpy=True, normalize_embeddings=True)
    return vecs.astype("float32")


# ── Indeks ───────────────────────────────────────────────────────────────────

_HNSW_M = 32
_HNSW_EF_CONSTRUCTION = 200
_HNSW_EF_SEARCH = 64


class _LazyMeta:
    """kb_meta.jsonl'ni TO'LIQ xotiraga yuklamasdan indekslaydi.

    Nega kerak (o'lchandi, taxmin emas): 8 460 152 qatorli (4.85GB) faylni
    json.loads bilan qatorma-qator to'liq parse qilish ~124s CPU-bound ish
    (68k qator/s). Bu vaqt davomida GIL boshqa threadlarni (jonli suhbat
    so'rovlarini bajaruvchi) sekinlashtiradi va 8.46M dict obyekti (~GB lab
    xotira + GC bosimi) yaratadi — holbuki bitta qidiruv atigi k=3 ta
    yozuvni ishlatadi.

    Buning o'rniga: yuklashda faqat qator BOSHLANISH offsetlarini
    skanerlaymiz (json.loads YO'Q — atigi \\n qidirish, ~48s, ~2.6x tezroq,
    deyarli GC bosimisiz), keyin har bir yozuvni FAQAT kerak bo'lganda
    (qidiruv natijasida topilganda) diskdan seek+readline+json.loads bilan
    o'qiymiz. Runtime'da qo'shilgan yangi yozuvlar (build/append) xotirada
    (_overlay) turadi — xuddi eskicha ishlagandek."""

    def __init__(self, path: str):
        self._path = path
        self._offsets: List[int] = []
        self._overlay: List[dict] = []
        self._fh = None
        self._rlock = threading.Lock()

    def _cache_paths(self):
        d = os.path.dirname(self._path)
        base = os.path.basename(self._path)
        return (os.path.join(d, base + ".offsets.npy"),
                os.path.join(d, base + ".offsets.meta.json"))

    def build_offsets(self) -> None:
        """Har bir qator boshlanish pozitsiyasini topadi (parse qilmasdan).

        Endi natija DISKKA keshlanadi (offset skaneri ~48s+ edi — katta
        faylda har SOVUQ jarayon boshlanishida qayta bajarilardi, garchi
        manba fayl o'zgarmagan bo'lsa ham). Kesh manba faylning hajmi+mtime
        bilan bog'liq: mos kelmasa (fayl yangilangan/o'sgan) avtomatik
        qayta hisoblanadi. Kesh o'qish — millisekundlar (N*8 bayt np.load),
        to'liq skanerlash esa fayl hajmiga proportsional (soniyalar)."""
        try:
            st = os.stat(self._path)
        except OSError:
            self._offsets = []
            return
        cache_path, meta_path = self._cache_paths()
        if os.path.exists(cache_path) and os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    cmeta = json.load(f)
                if cmeta.get("size") == st.st_size and cmeta.get("mtime") == st.st_mtime:
                    import numpy as np
                    arr = np.load(cache_path)
                    self._offsets = arr  # numpy int64 array — len()/indexing ishlaydi
                    log.info("[KB] offset kesh ishlatildi: %d qator (skanerlanmadi)",
                             len(arr))
                    return
            except Exception as e:
                log.debug("[KB] offset kesh o'qish xato (qayta skanerlanadi): %s", e)

        t0 = time.time()
        offsets: List[int] = []
        with open(self._path, "rb") as f:
            pos = f.tell()
            line = f.readline()
            while line:
                if line.strip():
                    offsets.append(pos)
                pos = f.tell()
                line = f.readline()
        self._offsets = offsets
        log.info("[KB] offset skaneri: %d qator, %.1fs", len(offsets), time.time() - t0)

        try:
            import numpy as np
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            # DIQQAT: np.save nomi ".npy" bilan tugamasa, o'zi ".npy"
            # qo'shadi — shuning uchun tmp nomi ham ".npy" bilan tugashi
            # SHART, aks holda haqiqiy fayl "<tmp>.npy" bo'lib qoladi va
            # keyingi os.replace(tmp, cache_path) topilmay xato beradi.
            tmp = cache_path + ".tmp.npy"
            np.save(tmp, np.array(offsets, dtype=np.int64))
            os.replace(tmp, cache_path)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"size": st.st_size, "mtime": st.st_mtime,
                           "count": len(offsets)}, f)
        except Exception as e:
            # Kesh yozib bo'lmasa (masalan diskka yozish huquqi yo'q) — jiddiy
            # emas, keyingi safar shunchaki qayta skanerlanadi.
            log.debug("[KB] offset kesh yozish xato (davom etadi): %s", e)

    def __len__(self) -> int:
        return len(self._offsets) + len(self._overlay)

    def __getitem__(self, i: int) -> dict:
        n_disk = len(self._offsets)
        if i < 0:
            i += len(self)
        if i < n_disk:
            with self._rlock:
                if self._fh is None:
                    self._fh = open(self._path, "rb")
                self._fh.seek(self._offsets[i])
                line = self._fh.readline()
            return json.loads(line)
        return self._overlay[i - n_disk]

    def extend(self, items) -> None:
        self._overlay.extend(items)

    def append(self, item) -> None:
        self._overlay.append(item)


def _new_index():
    """HNSW — millionlab bo'lakda ham millisekundlarda qidirish uchun.

    Taxminiy (exact emas), lekin sinovda flat bilan bir xil top-1 natija
    berdi, 40-50x tezroq (1M vektorda o'lchandi)."""
    import faiss
    idx = faiss.IndexHNSWFlat(_DIM, _HNSW_M, faiss.METRIC_INNER_PRODUCT)
    idx.hnsw.efConstruction = _HNSW_EF_CONSTRUCTION
    idx.hnsw.efSearch = _HNSW_EF_SEARCH
    return idx


def migrate_flat_to_hnsw(src_index_path: str, dst_index_path: str,
                          M: int = 32, ef_construction: int = 200,
                          ef_search: int = 64) -> dict:
    """Mavjud IndexFlatIP'ni IndexHNSWFlat'ga o'tkazadi (qayta embedding QILMAYDI).

    Katta indeksda (millionlab bo'lak) IndexFlatIP chiziqli qidiradi — sekin.
    HNSW taxminiy, lekin log(n) tezlikda qidiradi. Vektorlar flat indeksdan
    to'g'ridan-to'g'ri o'qiladi (reconstruct), qayta hisoblanmaydi.

    Xavfsiz: src faylga tegmaydi, faqat o'qiydi. dst — yangi fayl."""
    import faiss
    import numpy as np

    src = faiss.read_index(src_index_path)
    n = src.ntotal
    if n == 0:
        raise ValueError("manba indeks bo'sh")

    vecs = np.zeros((n, _DIM), dtype="float32")
    for i in range(n):
        vecs[i] = src.reconstruct(i)

    dst = faiss.IndexHNSWFlat(_DIM, M, faiss.METRIC_INNER_PRODUCT)
    dst.hnsw.efConstruction = ef_construction
    dst.hnsw.efSearch = ef_search
    dst.add(vecs)

    faiss.write_index(dst, dst_index_path)
    return {"vectors": n, "src_type": type(src).__name__, "dst_type": type(dst).__name__}


def _do_load() -> bool:
    """Haqiqiy yuklash ishi — chaqiruvchi _lock'ni ushlab turgan bo'lishi kerak."""
    global _index, _meta
    if not (os.path.exists(_INDEX_PATH) and os.path.exists(_META_PATH)):
        return False
    try:
        import faiss
        _index = faiss.read_index(_INDEX_PATH)
        if hasattr(_index, "hnsw"):
            _index.hnsw.efSearch = _HNSW_EF_SEARCH
        # Lazy: to'liq json.loads emas — faqat offset skaneri (tezroq,
        # GIL'ni kamroq band qiladi). Qarang: _LazyMeta docstring.
        lazy_meta = _LazyMeta(_META_PATH)
        lazy_meta.build_offsets()
        _meta = lazy_meta
        # SINXRON TEKSHIRUVI — faiss vektorlari va meta qatorlari mos
        # kelishi SHART. Aks holda har qidiruv noto'g'ri matn qaytaradi
        # (ishonchli axlat). Bu foydalanuvchi eng yomon ko'rgan holat.
        if _index.ntotal != len(_meta):
            log.error("[KB] BUZUQ INDEKS: faiss=%d != meta=%d — "
                      "qidiruv o'chirildi", _index.ntotal, len(_meta))
            _index = None
            _meta = []
            return False
        log.info("[KB] indeks yuklandi: %d bo'lak (sinxron OK)", len(_meta))
        return True
    except Exception as e:
        log.warning("[KB] yuklash xato: %s", e)
        _index = None
        return False


def _ensure_loaded() -> bool:
    """Bloklovchi versiya — kerak bo'lsa yuklanish tugashini kutadi.

    Katta indeks (millionlab bo'lak) uchun bu daqiqalab davom etishi
    mumkin. Jonli suhbat yo'lida BUNI emas, is_ready()/get_context_for_llm
    orqali bloklamaydigan tekshiruvni ishlating."""
    global _index
    if _index is not None:
        return True
    with _lock:
        if _index is not None:
            return True
        return _do_load()


_bg_load_thread: Optional[threading.Thread] = None
_bg_load_thread_lock = threading.Lock()


def _kick_off_background_load() -> None:
    """Indeks yuklashni FON THREADIDA boshlaydi (agar hali boshlanmagan
    bo'lsa) — hech qachon chaqiruvchi threadni bloklamaydi."""
    global _bg_load_thread

    def _bg():
        with _lock:
            if _index is None:
                _do_load()

    with _bg_load_thread_lock:
        if _bg_load_thread is not None and _bg_load_thread.is_alive():
            return
        _bg_load_thread = threading.Thread(target=_bg, daemon=True,
                                            name="KI-BgLoad")
        _bg_load_thread.start()


def is_ready() -> bool:
    """Bloklamasdan tekshiradi: indeks xotirada tayyor turibdimi?

    BUG FIX (o'lchandi — 271s sovuq turnda): ilgari, agar HECH KIM _lock'ni
    ushlamagan bo'lsa (masalan prewarm hali ki.search()'ga yetib bormagan,
    hali modelni yuklayotgan bo'lsa), bu funksiya '_lock.acquire(blocking=
    False)' bilan qulfni MUVAFFAQIYATLI olardi va keyin _do_load() ni O'ZI,
    O'Z THREADIDA (ya'ni jonli suhbat so'rovi threadida!) sinxron bajarardi
    — bu esa aynan oldini olishga mo'ljallangan bloklanishning o'ZI edi.
    "Bloklamaydi" degani faqat BOSHQA thread ALLAQACHON yuklayotgan bo'lsa
    to'g'ri ishlardi; birinchi chaqiruvchi (prewarm hali ulgurmagan bo'lsa —
    live turn ham bo'lishi mumkin) baribir daqiqalab bloklanardi.

    Endi: qulf bo'sh bo'lsa ham, bu yerda HECH QACHON o'zi yuklamaydi —
    faqat fon threadida yuklashni BOSHLAYDI (agar hali boshlanmagan bo'lsa)
    va DARHOL False qaytaradi. Haqiqiy yuklash fon threadida davom etadi,
    keyingi so'rovlar tayyor indeksni topadi."""
    global _index
    if _index is not None:
        return True
    acquired = _lock.acquire(blocking=False)
    if acquired:
        _lock.release()
        # Hech kim yuklamayapti — fon threadida boshlanadi, LEKIN shu
        # chaqiruvchi (jonli suhbat bo'lishi mumkin) buni KUTMAYDI.
        _kick_off_background_load()
    # acquired=False bo'lsa — allaqachon kimdir (fon prewarm yoki oldingi
    # _kick_off_background_load) yuklamoqda, qo'shimcha ish shart emas.
    return False


def _write_index_atomic():
    """FAISS indeksni vaqtinchalik faylga yozib, so'ng almashtiradi.

    Jarayon yozish o'rtasida to'xtasa ham asosiy fayl buzilmaydi.

    Windows: os.replace nishon fayl band bo'lsa (antivirus, indekslash)
    xato beradi. Shuning uchun bir necha marta urinamiz va kerak bo'lsa
    nishonni oldin o'chiramiz."""
    import faiss
    tmp = _INDEX_PATH + ".tmp"
    faiss.write_index(_index, tmp)
    for attempt in range(5):
        try:
            os.replace(tmp, _INDEX_PATH)
            return
        except PermissionError:
            time.sleep(0.5 * (attempt + 1))
            try:
                if os.path.exists(_INDEX_PATH):
                    os.remove(_INDEX_PATH)
            except Exception:
                pass
    # Oxirgi urinish — to'g'ridan-to'g'ri yozish (atomik emas, lekin ishlaydi)
    try:
        os.replace(tmp, _INDEX_PATH)
    except Exception:
        faiss.write_index(_index, _INDEX_PATH)


def build(chunks: List[Tuple[str, str]], append: bool = False,
          save: bool = True) -> int:
    """Indeks quradi. chunks = [(text, source), ...].

    append=True  -> mavjud indeksga QO'SHADI (Wikipedia partiyalari uchun)
    save=False   -> diskka yozmaydi (partiyalar orasida tez, oxirida flush)

    Meta INKREMENTAL yoziladi (butun faylni qayta yozmaydi) — bu katta
    indeks uchun O(n) emas, O(1) har partiya.
    """
    global _index, _meta
    os.makedirs(_KB_DIR, exist_ok=True)

    pairs = [(c[0].strip(), c[1]) for c in chunks if c[0] and c[0].strip()]
    if not pairs:
        return len(_meta)
    texts = [p[0] for p in pairs]

    if append:
        _ensure_loaded()
        if _index is None:
            _index, _meta = _new_index(), []
    else:
        _index, _meta = _new_index(), []
        # Yangi qurish — meta faylni KESIB tashlash ("w" rejimi).
        # os.remove ishonchsiz edi (fayl band bo'lsa qolib ketardi va
        # keyingi append'lar to'planib sinxronni buzardi).
        try:
            open(_META_PATH, "w", encoding="utf-8").close()
        except Exception:
            pass

    t0 = time.time()
    vecs = embed(texts)
    with _lock:
        _index.add(vecs)
        new_meta = [{"text": t[:500], "source": s} for t, s in pairs]
        _meta.extend(new_meta)
        # Meta INKREMENTAL — faqat yangi qatorlarni qo'shadi
        with open(_META_PATH, "a", encoding="utf-8") as f:
            for m in new_meta:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        if save:
            _write_index_atomic()

    log.info("[KB] +%d bo'lak (%.1fs), jami %d",
             len(texts), time.time() - t0, len(_meta))
    return len(_meta)


def flush():
    """Indeksni diskка atomik yozadi (save=False partiyalaridan keyin)."""
    with _lock:
        if _index is not None:
            _write_index_atomic()


def search(query: str, k: int = 3, block: bool = True) -> List[dict]:
    """Savolga eng yaqin bo'laklar. Returns: [{text, source, score}, ...].

    block=False: agar indeks hali yuklanmagan/yuklanayotgan bo'lsa, KUTMASDAN
    bo'sh ro'yxat qaytaradi (jonli suhbat uchun — daqiqalab bloklanmaslik)."""
    if not query:
        return []
    loaded = is_ready() if not block else _ensure_loaded()
    if not loaded or not _meta:
        return []
    try:
        qv = embed([query])
        scores, idxs = _index.search(qv, min(k, len(_meta)))
        out = []
        for score, i in zip(scores[0], idxs[0]):
            if 0 <= i < len(_meta):
                m = _meta[i]
                out.append({"text": m["text"], "source": m.get("source", ""),
                            "score": round(float(score), 3)})
        return out
    except Exception as e:
        log.warning("[KB] qidiruv xato: %s", e)
        return []


def get_context_for_llm(query: str = "", k: int = 3, min_score: float = 0.35) -> str:
    """Orkestrator uchun — bilim bazasidan tegishli faktlar.

    Bloklamaydi: agar indeks hali (startup prewarm orqali) yuklanayotgan
    bo'lsa, javobni daqiqalab kutmasdan, bo'sh kontekst bilan davom etadi."""
    if not query:
        return ""
    hits = [h for h in search(query, k, block=False) if h["score"] >= min_score]
    if not hits:
        return ""
    lines = ["[BILIM BAZASI]"]
    for h in hits:
        src = f" ({h['source']})" if h["source"] else ""
        lines.append(f"  • {h['text'][:160]}{src}")
    return "\n".join(lines)


def get_stats() -> dict:
    loaded = _ensure_loaded()
    return {
        "indexed_chunks": len(_meta) if loaded else 0,
        "index_exists": os.path.exists(_INDEX_PATH),
        "model": _MODEL_NAME,
    }
