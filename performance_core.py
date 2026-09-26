# -*- coding: utf-8 -*-
"""NeuroKey — Tezlik yadrosi. M1 yechimi.

Maqsad: Har operatsiya < 1 soniya.
Parallel: STT + ekran + LLM bir vaqtda.
Streaming: LLM yoza boshlaganda TTS ham boshlaydi.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


class PerformanceCore:
    """
    Tezlik optimizatsiyasi.
    - Parallel processing: STT + ekran + LLM
    - Streaming: birinchi gap kelgach TTS boshlaydi
    - Cache: tez-tez savollar
    - Pre-warming: LLM connection tayyor
    """

    def __init__(self, max_workers: int = 8):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.response_cache: dict = {}
        self._warmup_done = False
        self._cache_max = 50

    async def warmup(self) -> None:
        """
        Startup da bir marta.
        LLM client tayyor, ekran monitor boshlangan bo'ladi.
        """
        if self._warmup_done:
            return
        try:
            from llm_router import _client
            _client()
            self._warmup_done = True
            log.info("[PerformanceCore] warmup done")
        except Exception as e:
            log.warning("[PerformanceCore] warmup: %s", e)

    def _is_sentence_complete(self, text: str) -> bool:
        """Gap tugaganini aniqlash."""
        if not text or not text.strip():
            return False
        t = text.strip()
        return any(t.endswith(p) for p in (". ", "! ", "? ", ".\n", "!\n", "?\n", "..."))

    def get_cached_response(self, key: str) -> Optional[str]:
        """Cache dan javob olish."""
        if key in self.response_cache:
            return self.response_cache[key]
        return None

    def set_cached_response(self, key: str, value: str) -> None:
        """Cache ga yozish."""
        self.response_cache[key] = value
        if len(self.response_cache) > self._cache_max:
            keys = list(self.response_cache.keys())
            for k in keys[: self._cache_max // 2]:
                del self.response_cache[k]

    async def _diagnose_slowness(self, total_sec: float) -> None:
        """Agar > 1.5s bo'lsa — qayerda sekinlashganini log qiladi."""
        if total_sec > 1.5:
            log.warning("[PerformanceCore] slow response: %.2fs (target < 1s)", total_sec)


_perf: Optional[PerformanceCore] = None


def get_performance_core() -> PerformanceCore:
    """Singleton."""
    global _perf
    if _perf is None:
        _perf = PerformanceCore()
    return _perf
