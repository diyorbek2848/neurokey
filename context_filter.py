# -*- coding: utf-8 -*-
"""NeuroKey — Kontekst filtri (axborot darvozasi).

Muammo: 29 ta bo'limdan 19 tasi har qanday savolga so'zma-so'z bir xil
matn chiqaradi. O'lchandi (ablation_test.py): kontekstning ~73% i
o'zgarmas. O'zgarmas matn LLM uchun 0 bit ma'lumot beradi — u faqat
ishlaydigan signalni suyultiradi va har so'rovda token yeydi.

Yechim: qattiq "taqiq ro'yxati" emas — o'z-o'zini sozlaydigan darvoza.
Har bo'limning oxirgi K ta TURLI savoldagi qiymati eslab qolinadi.
Agar hammasi bir xil bo'lsa — bo'lim so'ndiriladi. Modul tuzatilib,
javob bera boshlasa — darvoza uni avtomatik qaytaradi.

Bu GWT-4 (holatga bog'liq diqqat) uchun ham zamin: keyingi bosqichda
tanlov statistikaga emas, savol turiga qarab qilinadi.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "context_filter.json")

# Nechta turli savol kuzatilsa — shuncha bir xil bo'lsa so'ndiriladi
_WINDOW = 5
# Shundan kamida shuncha kuzatuv bo'lmaguncha hech narsa so'ndirilmaydi
_MIN_OBSERVATIONS = 4

# Hech qachon so'ndirilmaydigan bo'limlar — PREFIKS bo'yicha solishtiriladi.
# Sarlavhalar "DOIMIY XOTIRA — tarix" kabi qo'shimchali bo'lgani uchun
# aniq moslik ishlamaydi: xotira bo'limlari bexosdan so'ndirilib qolardi.
#
# Xotira — ablatsiyada eng kuchli hissa qo'shgan qatlam (permanent_memory
# yolg'iz o'zi 8 834 belgi). U doimiy ko'rinsa ham, davomiylik hissi
# aynan shundan keladi.
# Bu bo'limlar GWT-4 (attention_router) tomonidan allaqachon savol turiga
# qarab qo'shiladi — ya'ni ular chiqsa, DEMAK dolzarb. Statistik "doimiy"
# filtri bu yerda ortiqcha va zararli (maqsad umumiy savolda bir xil ko'rinsa
# ham kerak). Shuning uchun ular oq ro'yxatda.
_ALWAYS_KEEP_PREFIX = (
    "VAQT",
    "SEMANTIK XOTIRA",
    "DOIMIY XOTIRA",
    "MUHIM VOQEALAR",
    "ДОЛГОСРОЧНАЯ ПАМЯТЬ",
    "HAYOT HIKOYASI",
    "САМОСТЬ",
    "ICHKI FIK",
    "HISSIYOT",
    "MAQSAD",          # AE-1 — GWT-4 faqat planning turida chaqiradi
    "METAKOGNITSIYA",  # HOT-2/3 — faqat ishonch past bo'lganda chiqadi
    "DIQQAT",          # GWT-4 rejasi — har savolda o'zgaradi
)


def _always_keep(name: str) -> bool:
    n = (name or "").strip().upper()
    return any(n.startswith(p.upper()) for p in _ALWAYS_KEEP_PREFIX)

_lock = threading.Lock()
_state: Dict[str, List[str]] | None = None


# ── Holat ────────────────────────────────────────────────────────────────────

def _load() -> Dict[str, List[str]]:
    global _state
    if _state is not None:
        return _state
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _state = {k: list(v)[-_WINDOW:] for k, v in data.get("sections", {}).items()}
            return _state
    except Exception as e:
        log.warning("[CtxFilter] yuklash xato: %s", e)
    _state = {}
    return _state


def _save() -> None:
    if _state is None:
        return
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        tmp = _STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"sections": _state, "window": _WINDOW}, f, ensure_ascii=False)
        os.replace(tmp, _STATE_PATH)   # atomik — yozish paytida to'xtasa buzilmaydi
    except Exception as e:
        log.warning("[CtxFilter] saqlash xato: %s", e)


def reset() -> None:
    """Kuzatuv tarixini tozalash."""
    global _state
    with _lock:
        _state = {}
        _save()


# ── Ajratish ─────────────────────────────────────────────────────────────────

def split_sections(context: str) -> List[Tuple[str, str]]:
    """Kontekstni [(sarlavha, to'liq_matn), ...] ga ajratadi.

    Sarlavhasiz boshlang'ich matn "" nomi bilan qaytadi — u hech qachon
    so'ndirilmaydi.
    """
    out: List[Tuple[str, str]] = []
    cur_name, buf = "", []
    for line in (context or "").splitlines():
        if line.startswith("[") and "]" in line:
            if buf:
                out.append((cur_name, "\n".join(buf)))
            cur_name = line[1:line.find("]")]
            buf = [line]
        else:
            buf.append(line)
    if buf:
        out.append((cur_name, "\n".join(buf)))
    return out


def _digest(text: str) -> str:
    return hashlib.md5(text.strip().encode("utf-8", "replace")).hexdigest()[:12]


def _is_stale(name: str, digests: List[str]) -> bool:
    """Bo'lim oxirgi K ta turli savolda o'zgarmadimi?"""
    if len(digests) < _MIN_OBSERVATIONS:
        return False
    return len(set(digests[-_WINDOW:])) == 1


# ── Asosiy API ───────────────────────────────────────────────────────────────

def filter_context(context: str, query: str = "") -> str:
    """O'zgarmas bo'limlarni olib tashlaydi.

    Har chaqiruvda bo'lim qiymatlari qayd etiladi. Kuzatuv yetarli
    to'planmaguncha (_MIN_OBSERVATIONS) hech narsa o'chirilmaydi —
    ya'ni birinchi ishga tushirishlarda xatti-harakat o'zgarmaydi.
    """
    if not context:
        return context

    sections = split_sections(context)
    if not sections:
        return context

    with _lock:
        state = _load()
        kept: List[str] = []
        dropped: List[str] = []
        seen: Dict[str, str] = {}      # sarlavha -> matn xesh (dublikat nazorati)

        for name, text in sections:
            # Dublikat: bir xil sarlavha bir xil matn bilan ikkinchi marta.
            # vision_emotion_bridge [HISSIYOT-27] ni qayta chiqarardi —
            # kontekstda bir bo'lim ikki marta turardi.
            if name:
                d0 = _digest(text)
                if seen.get(name) == d0:
                    dropped.append(name + " (dublikat)")
                    continue
                seen[name] = d0

            if not name or _always_keep(name):
                kept.append(text)
                continue

            hist = state.setdefault(name, [])
            stale = _is_stale(name, hist)

            # Qayd etish — faqat savol berilgan bo'lsa (turli savollar kerak)
            if query:
                d = _digest(text)
                if not hist or hist[-1] != d or len(set(hist)) > 1:
                    hist.append(d)
                else:
                    hist.append(d)
                del hist[:-_WINDOW]

            if stale:
                dropped.append(name)
            else:
                kept.append(text)

        _save()

    if dropped:
        log.info("[CtxFilter] so'ndirildi (%d): %s", len(dropped), ", ".join(dropped[:6]))
    return "\n".join(kept)


def get_stats() -> Dict[str, object]:
    """Qaysi bo'limlar so'ndirilgan va qaysilari faol."""
    with _lock:
        state = _load()
        stale = [n for n, h in state.items() if _is_stale(n, h)]
        active = [n for n, h in state.items() if not _is_stale(n, h)]
    return {
        "kuzatilgan":  len(state),
        "so'ndirilgan": sorted(stale),
        "faol":         sorted(active),
        "oyna":         _WINDOW,
    }
