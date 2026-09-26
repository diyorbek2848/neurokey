# -*- coding: utf-8 -*-
"""NeuroKey — Dunyo Modeli (World Model).

Friston: har tizim o'zi yashaydigan muhitning ichki modelini saqlashi kerak.
NeuroKey uchun "dunyo" = foydalanuvchi + kompyuter + vazifalar.
"""

from __future__ import annotations

import collections
import math
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

_MAX_PREDICTION_HISTORY = 100
_MAX_TASK_PATTERNS = 50


class WorldModel:
    """
    NeuroKey ning dunyo haqidagi ichki modeli.
    Friston: har tizim o'zi yashaydigan muhitning ichki modelini saqlashi kerak.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

        # Foydalanuvchi modeli
        self.user_model: Dict[str, Any] = {
            "current_task": None,
            "mood": "neutral",
            "expertise_level": 0.5,
            "preferred_style": "medium",
            "activity_pattern": [],
            "typical_requests": {},
        }

        # Muhit modeli
        self.environment_model: Dict[str, Any] = {
            "time_of_day": None,
            "day_of_week": None,
            "screen_state": "unknown",
            "system_state": "normal",
            "active_apps": [],
        }

        # Vazifa modeli
        self.task_model: Dict[str, Any] = {
            "pending_tasks": [],
            "completed_tasks": [],
            "task_patterns": {},  # prev -> [(next, count)]
            "difficulty_map": {},
        }

        self.prediction_history: List[Tuple[str, str, float]] = []
        self.model_confidence: float = 0.5
        self._context_window: List[str] = []
        self._max_context = 10

    def _normalize(self, s: str) -> str:
        s = (s or "").strip().lower()[:80]
        s = re.sub(r"\s+", " ", s)
        return " ".join(s.split()[:5]) if s else ""

    def predict(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Keyingi holatni bashorat qilish.
        """
        try:
            with self._lock:
                ctx_list = context.get("context", context.get("previous_context", []))
                if isinstance(ctx_list, dict):
                    ctx_list = []
                prev = self._normalize(ctx_list[-1]) if ctx_list else ""
                time_hour = context.get("time", time.localtime().tm_hour)
                if isinstance(time_hour, (list, tuple)):
                    time_hour = context.get("hour", 12)

                next_req = ""
                next_prob = 0.0
                patterns = self.task_model.get("task_patterns", {})
                if prev and prev in patterns:
                    total = sum(c for _, c in patterns[prev])
                    if total > 0:
                        best = max(patterns[prev], key=lambda x: x[1])
                        next_req = best[0]
                        next_prob = best[1] / total

                if not next_req:
                    # Fallback: eng tez-tez
                    all_next: List[Tuple[str, int]] = []
                    for lst in patterns.values():
                        all_next.extend(lst)
                    if all_next:
                        counter = collections.Counter()
                        for n, c in all_next:
                            counter[n] += c
                        if counter:
                            next_req, cnt = counter.most_common(1)[0]
                            next_prob = cnt / sum(counter.values())

                return {
                    "next_request": next_req,
                    "next_request_prob": min(1.0, next_prob * 1.2),
                    "user_mood_next": self.user_model.get("mood", "neutral"),
                    "task_completion": 0.0,
                    "attention_needed": next_prob < 0.5,
                    "confidence": self.model_confidence,
                }
        except Exception:
            return {
                "next_request": "",
                "next_request_prob": 0.0,
                "user_mood_next": "neutral",
                "task_completion": 0.0,
                "attention_needed": True,
                "confidence": 0.5,
            }

    def update(self, actual_input: str, context: Dict[str, Any]) -> None:
        """
        Haqiqat kelganda modelni yangilash.
        """
        actual = self._normalize(actual_input)
        if not actual:
            return
        try:
            with self._lock:
                self._context_window.append(actual_input)
                if len(self._context_window) > self._max_context:
                    self._context_window = self._context_window[-self._max_context:]

                if len(self._context_window) >= 2:
                    prev = self._normalize(self._context_window[-2])
                    patterns = self.task_model["task_patterns"]
                    if prev not in patterns:
                        patterns[prev] = []
                    found = False
                    for i, (nxt, cnt) in enumerate(patterns[prev]):
                        if nxt == actual:
                            patterns[prev][i] = (nxt, cnt + 1)
                            found = True
                            break
                    if not found:
                        patterns[prev].append((actual, 1))

                # Typical requests
                typical = self.user_model["typical_requests"]
                typical[actual] = typical.get(actual, 0) + 1
                if len(typical) > 50:
                    self.user_model["typical_requests"] = dict(
                        sorted(typical.items(), key=lambda x: -x[1])[:30]
                    )
        except Exception:
            pass

    def calculate_surprise(self, actual: str, predicted: Dict[str, Any]) -> float:
        """
        Surprise = -log P(actual | predicted)
        Yuqori surprise = kutilmagan.
        """
        pred_req = self._normalize(predicted.get("next_request", ""))
        pred_prob = predicted.get("next_request_prob", 0.0)
        act = self._normalize(actual)
        if not act:
            return 0.0
        if pred_req == act:
            p = max(0.01, pred_prob)
            return 0.0 if p > 0.9 else -math.log(p)
        else:
            p = max(0.01, 1.0 - pred_prob)
            return min(1.0, -math.log(p) / 5.0)

    def get_model_state(self) -> str:
        """LLM uchun dunyo modeli tavsifi."""
        try:
            with self._lock:
                parts = [
                    f"Foydalanuvchi: {self.user_model.get('mood', 'neutral')} kayfiyat.",
                    f"Model ishonch: {self.model_confidence:.0%}.",
                ]
                if self.task_model.get("task_patterns"):
                    parts.append("Vazifa patternlari o'rganilgan.")
                return " ".join(parts)
        except Exception:
            return "Dunyo modeli: odatiy holat."

    def infer_user_intent(self, partial_input: str) -> List[Dict[str, Any]]:
        """
        Foydalanuvchi gapini tugatmasa ham niyatni tushunish.
        """
        partial = self._normalize(partial_input)
        if not partial or len(partial) < 2:
            return []
        try:
            with self._lock:
                results = []
                patterns = self.task_model.get("task_patterns", {})
                for prev, next_list in patterns.items():
                    if partial in prev or prev.startswith(partial):
                        for nxt, cnt in next_list:
                            total = sum(c for _, c in next_list)
                            prob = cnt / total if total > 0 else 0
                            results.append({
                                "intent": nxt,
                                "probability": prob,
                                "completion": nxt,
                            })
                results.sort(key=lambda x: -x["probability"])
                return results[:5]
        except Exception:
            return []


_SINGLETON: Optional[WorldModel] = None
_SINGLETON_LOCK = threading.Lock()


def get_world_model() -> WorldModel:
    """Singleton WorldModel."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = WorldModel()
    return _SINGLETON
