# -*- coding: utf-8 -*-
"""NeuroKey — Global Workspace Theory (Bernard Baars).

GWT: markaziy sahna, e'tibor tanlash (compete), barcha modullarga broadcast.
Signal format: {'source': str, 'content': any, 'salience': float 0-1, 'timestamp': float}
"""

from __future__ import annotations

try: from valence_state import get_valence as _gw_valence
except ImportError: _gw_valence = None
try: from arousal_state import get_arousal as _gw_arousal
except ImportError: _gw_arousal = None

import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional, Protocol

log = logging.getLogger(__name__)

MAX_BROADCAST_HISTORY = 50


class BroadcastReceiver(Protocol):
    """Modul bu interfeysni qo'llab-quvvatlashi kerak."""

    def receive_broadcast(self, signal: Dict[str, Any]) -> None:
        """Broadcast qilingan signalni qabul qiladi."""
        ...


class GlobalWorkspace:
    """Bernard Baars Global Workspace Theory — compete, spotlight, broadcast."""

    _EMA_ALPHA  = 0.40   # EMA og'irligi (yangi kuzatuv ulushi) — tezroq moslashish
    _HYSTERESIS = 0.02   # Spotlight almashtirish uchun zarur minimal ustunlik

    def __init__(self, max_buffer: int = 20, max_history: int = MAX_BROADCAST_HISTORY):
        self.max_buffer = max_buffer
        self.max_history = max_history
        self._buffer: List[Dict[str, Any]] = []
        self._modules: List[BroadcastReceiver] = []
        self._spotlight: Optional[Dict[str, Any]] = None
        self._broadcast_history: List[Dict[str, Any]] = []
        self._ema: Dict[str, float] = {}   # {source: EMA salience}

    def register_module(self, module: BroadcastReceiver) -> None:
        """Modulni ro'yxatga oladi. receive_broadcast(signal) metodi bo'lishi kerak."""
        if module not in self._modules:
            self._modules.append(module)

    def unregister_module(self, module: BroadcastReceiver) -> None:
        """Modulni ro'yxatdan olib tashlaydi."""
        if module in self._modules:
            self._modules.remove(module)

    def compete(self, signals: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Eng yuqori salience ga ega signal yutadi → spotlight ga kiradi.
        EMA smoothing + hysteresis: shovqinga chidamli tanlov.
        Keyin broadcast() avtomatik chaqiriladi.
        """
        if not signals:
            return None
        valid = [
            s for s in signals
            if isinstance(s, dict)
            and "source" in s
            and "salience" in s
        ]
        if not valid:
            return None

        # EMA yangilash: har signal manbasining silliqlashtrilgan salience'ini saqlaydi
        for s in valid:
            src = s["source"]
            raw = max(0.0, min(1.0, float(s.get("salience", 0))))
            if src in self._ema:
                self._ema[src] = self._EMA_ALPHA * raw + (1 - self._EMA_ALPHA) * self._ema[src]
            else:
                self._ema[src] = raw  # birinchi marta — to'g'ridan boshlash

        # Tenglashuv holatida tasodifiy tanlash (tie-breaking)
        shuffled = list(valid)
        random.shuffle(shuffled)

        # EMA bo'yicha g'olibni aniqlash
        winner = max(shuffled, key=lambda x: self._ema.get(x["source"], float(x.get("salience", 0))))

        # Hysteresis: shovqinga chidamlilik uchun.
        # Qoidalar:
        #   1. Joriy spotlight shu turda qatnashayotgan bo'lsa (cur_in_round)
        #   2. Joriy EMA g'olibdan aniq va sezilarli ustun bo'lsa (gap >= HYSTERESIS)
        #   3. Tenglik holatida (ema diff < HYSTERESIS) — erkin almashtirish (shuffle qaytaradi)
        if self._spotlight and winner["source"] != self._spotlight.get("source"):
            cur_src = self._spotlight.get("source", "")
            cur_in_round = any(s.get("source") == cur_src for s in valid)
            if cur_in_round:
                cur_ema = self._ema.get(cur_src, 0.0)
                win_ema = self._ema.get(winner["source"], float(winner.get("salience", 0)))
                # Saqlash: faqat joriy ANIQ ustun bo'lsa (strictly greater + gap)
                if cur_ema > win_ema and (cur_ema - win_ema) >= self._HYSTERESIS:
                    return dict(self._spotlight)

        winner = dict(winner)
        if "timestamp" not in winner:
            winner["timestamp"] = time.time()
        self._spotlight = winner
        self._broadcast(winner)
        log.info(
            "[GWT] spotlight: %s salience=%.2f",
            winner.get("source", "?"),
            float(winner.get("salience", 0)),
        )
        return winner

    def _broadcast(self, signal: Dict[str, Any]) -> None:
        """G'olib signalni barcha ro'yxatga olingan modullarga yuboradi."""
        for mod in self._modules:
            try:
                if hasattr(mod, "receive_broadcast"):
                    mod.receive_broadcast(signal)
            except Exception as e:
                log.warning("[GWT] broadcast to %s: %s", type(mod).__name__, e)
        self._broadcast_history.append(dict(signal))
        if len(self._broadcast_history) > self.max_history:
            self._broadcast_history = self._broadcast_history[-self.max_history:]

    async def compete_async(self, signals: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Async compete — asyncio uchun."""
        return self.compete(signals)

    def get_current_spotlight(self) -> Optional[Dict[str, Any]]:
        """Hozir ongda (spotlight da) nima borligini qaytaradi."""
        return dict(self._spotlight) if self._spotlight else None

    @property
    def broadcast_history(self) -> List[Dict[str, Any]]:
        """Oxirgi N ta broadcast."""
        return list(self._broadcast_history)

    # --- Eski API (backward compatibility: main.py, get_workspace) ---
    def add(self, source: str, content: str, importance: float = 0.5) -> None:
        """Ma'lumot qo'shish. Source: user, screen, memory, affect, intent, surprise.
        Eski API — buffer + compete() orqali EMA ham yangilanadi."""
        if not content or not str(content).strip():
            return
        importance = max(0.0, min(1.0, float(importance)))
        item = {
            "t": time.time(),
            "source": source,
            "content": (str(content) or "").strip()[:2000],
            "importance": importance,
            "salience": importance,
        }
        self._buffer.append(item)
        if len(self._buffer) > self.max_buffer:
            self._buffer = self._buffer[-self.max_buffer:]
        # EMA ham yangilash — eski va yangi API uyg'unligi
        src = source
        raw = importance
        if src in self._ema:
            self._ema[src] = self._EMA_ALPHA * raw + (1 - self._EMA_ALPHA) * self._ema[src]
        else:
            self._ema[src] = raw

    def add_intent(self, intent: str) -> None:
        """User niyati — e'tibor uchun."""
        if intent:
            self.add("intent", intent, 0.85)

    def add_surprise(self, msg: str) -> None:
        """Kutilmagan — e'tibor oshadi."""
        if msg:
            self.add("surprise", msg, 0.9)

    def broadcast(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """Eng muhim n ta — barcha modullarga (LLM ga)."""
        return self.attention_select(top_n)

    def attention_select(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """E'tibor: importance × recency × novelty × surprise."""
        if not self._buffer:
            return []
        now = time.time()
        seen_content: set = set()
        scored: List[tuple] = []
        for item in self._buffer:
            imp = item.get("importance", 0.5)
            t = item.get("t", now)
            recency = max(0, 1 - (now - t) / 3600)
            content_key = (item.get("content") or "")[:100]
            novelty = 0.2 if content_key not in seen_content else 0
            seen_content.add(content_key)
            src = (item.get("source") or "").lower()
            surprise = 0.25 if src == "surprise" else 0.15 if src in ("error", "alert", "unexpected") else 0
            score = imp * (1 + recency * 0.5) * (1 + novelty) * (1 + surprise)
            scored.append((score, item))
        scored.sort(key=lambda x: -x[0])
        return [item for _, item in scored[:top_n]]

    def broadcast_text(self, top_n: int = 5) -> str:
        """Broadcast matn sifatida."""
        items = self.broadcast(top_n)
        if not items:
            return ""
        lines = []
        for it in items:
            src = it.get("source", "?")
            cnt = (it.get("content") or "")[:1000]
            lines.append(f"[{src}] {cnt}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Buffer tozalash."""
        self._buffer = []


_workspace: Optional[GlobalWorkspace] = None


def get_workspace() -> GlobalWorkspace:
    """Global instance."""
    global _workspace
    if _workspace is None:
        _workspace = GlobalWorkspace()
    return _workspace
