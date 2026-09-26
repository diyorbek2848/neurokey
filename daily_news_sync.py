# -*- coding: utf-8 -*-
"""NeuroKey — kunlik yangiliklarni bilim bazasiga qo'shish.

Har ishga tushganda (yoki uzoq tanaffusdan keyin) so'nggi yangiliklarni
RSS orqali olib, qisqa bo'laklarga aylantirib, knowledge_index'ga qo'shadi.

MUHIM CHEGARA: RSS manbalar odatda faqat so'nggi 1-3 kunlik yozuvni
saqlaydi (arxiv emas). Agar tanaffus uzoqroq bo'lsa, "o'sha davrga oid"
emas, balki "hozir RSS'da mavjud eng so'nggi" yangiliklar olinadi.
Bu — to'liq tarixiy orqaga to'ldirish emas, "bazani jonlantirish".
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, List, Tuple

import juma_news_weather as nw
import knowledge_index as kb

log = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_BASE_DIR, "data", "news_sync_state.json")
_MIN_GAP_HOURS = 3.0          # bundan tezroq qayta sinxronlanmaydi
_REGIONS = ("world", "ru", "uz")
_LIMIT_PER_REGION = 15


def _load_state() -> dict:
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_sync": 0.0}


def _save_state(ts: float) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    tmp = _STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"last_sync": ts}, f)
    os.replace(tmp, _STATE_PATH)


def _collect_chunks(regions: Tuple[str, ...], limit: int) -> List[Tuple[str, str]]:
    chunks = []
    for region in regions:
        try:
            items = nw.get_top_news(region=region, limit=limit)
        except Exception as e:
            log.warning("[NEWS_SYNC] %s mintaqa xato: %s", region, e)
            continue
        for it in items:
            date_str = (time.strftime("%Y-%m-%d", time.localtime(it["ts"]))
                        if it.get("ts") else "?")
            title = (it.get("title") or "").strip()
            summary = (it.get("summary") or "").strip()[:300]
            if not title:
                continue
            text = f"[{date_str}] {title}. {summary}".strip()
            src = f"news:{region}:{(it.get('link') or '')[:70]}"
            chunks.append((text, src))
    return chunks


def sync(force: bool = False) -> Dict[str, object]:
    """Bo'shliqni tekshiradi, kerak bo'lsa yangiliklarni bazaga qo'shadi.

    Returns: {"skipped": bool, "added": int, "gap_hours": float}
    """
    state = _load_state()
    last_ts = float(state.get("last_sync", 0.0))
    gap_hours = (time.time() - last_ts) / 3600.0 if last_ts else 999.0

    if not force and gap_hours < _MIN_GAP_HOURS:
        return {"skipped": True, "added": 0, "gap_hours": round(gap_hours, 2)}

    chunks = _collect_chunks(_REGIONS, _LIMIT_PER_REGION)
    added = 0
    if chunks:
        kb.build(chunks, append=True, save=True)
        added = len(chunks)

    _save_state(time.time())
    log.info("[NEWS_SYNC] %d ta yangilik qo'shildi (bo'shliq: %.1f soat)",
              added, gap_hours)
    return {"skipped": False, "added": added, "gap_hours": round(gap_hours, 2)}


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    result = sync(force=force)
    print(result)
