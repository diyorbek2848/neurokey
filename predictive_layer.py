# -*- coding: utf-8 -*-
"""NeuroKey — Bashorat Qilish Qatlami (Predictive Layer).

Karl Friston Free Energy Principle: miya doim bashorat qiladi va xatoni kamaytiradi.
Bosqich 5: world_model va active_inference orqali to'liq Active Inference.
Fail-safe: xato bo'lsa eski pattern matching ga qaytadi.
"""

from __future__ import annotations

import collections
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

_MAX_PATTERN_LEN = 3
_MIN_OCCURRENCES = 2
_HIGH_CONFIDENCE = 0.85


class PredictiveLayer:
    """
    Active Inference: world_model.predict() ga delegatsiya.
    Fail-safe: world_model/active_inference yo'q bo'lsa — eski pattern matching.
    """

    def __init__(
        self,
        world_model: Optional[Any] = None,
        active_inference: Optional[Any] = None,
    ) -> None:
        self._lock = threading.RLock()
        self.world_model = world_model
        self.active_inference = active_inference

        # Legacy fallback
        self.conversation_patterns: Dict[str, List[Tuple[str, int]]] = {}
        self.prediction_accuracy: List[bool] = []
        self.active_predictions: List[Dict[str, Any]] = []
        self.context_window: List[str] = []
        self._max_context = 10
        self._max_accuracy_history = 50

    def _normalize_request(self, req: str) -> str:
        s = (req or "").strip().lower()[:80]
        s = re.sub(r"\s+", " ", s)
        words = s.split()[:5]
        return " ".join(words) if words else ""

    def _extract_pattern(self, context: List[str], length: int = 2) -> str:
        if not context or length < 1:
            return ""
        recent = context[-length:]
        return " | ".join(self._normalize_request(r) for r in recent)

    def _legacy_predict(self, current_context: List[str]) -> List[Dict[str, Any]]:
        """Eski pattern matching — fail-safe."""
        if not current_context:
            return []
        try:
            with self._lock:
                pattern = self._extract_pattern(current_context, 2)
                if not pattern:
                    return []
                candidates: List[Tuple[str, float]] = []
                for p, next_list in self.conversation_patterns.items():
                    if pattern in p or p in pattern:
                        total = sum(c for _, c in next_list)
                        for next_req, count in next_list:
                            prob = count / total if total > 0 else 0
                            candidates.append((next_req, prob))
                if not candidates:
                    all_next = []
                    for next_list in self.conversation_patterns.values():
                        all_next.extend(next_list)
                    if all_next:
                        counter = collections.Counter()
                        for n, c in all_next:
                            counter[n] += c
                        for pred, cnt in counter.most_common(3):
                            candidates.append((pred, cnt / sum(counter.values())))
                candidates.sort(key=lambda x: x[1], reverse=True)
                return [
                    {"prediction": p, "probability": prob}
                    for p, prob in candidates[:3]
                    if prob > 0.05
                ]
        except Exception:
            return []

    def predict_next_request(self, current_context: List[str]) -> List[Dict[str, Any]]:
        """
        Keyingi so'rov nima bo'lishi mumkin?
        world_model orqali yoki legacy fallback.
        """
        if not current_context:
            return []
        try:
            if self.world_model and self.active_inference:
                ctx = {"context": current_context}
                pred = self.world_model.predict(ctx)
                next_req = pred.get("next_request", "")
                next_prob = pred.get("next_request_prob", 0.0)
                if next_req and next_prob > 0.05:
                    return [{"prediction": next_req, "probability": next_prob}]
        except Exception:
            pass
        return self._legacy_predict(current_context)

    def pre_compute(self, predictions: List[Dict[str, Any]]) -> None:
        """Bashorat qilingan so'rovlarni saqlash."""
        if not predictions:
            return
        try:
            with self._lock:
                self.active_predictions = predictions[:3]
        except Exception:
            pass

    def update_patterns(self, actual_request: str, was_predicted: bool) -> None:
        """
        Haqiqat kelganda yangilash.
        active_inference orqali yoki legacy.
        """
        actual = self._normalize_request(actual_request)
        if not actual:
            return
        try:
            if self.world_model and self.active_inference:
                self.active_inference.perceive({"input": actual_request})
                self.world_model.update(actual_request, {"context": self.context_window})
            with self._lock:
                self.prediction_accuracy.append(was_predicted)
                if len(self.prediction_accuracy) > self._max_accuracy_history:
                    self.prediction_accuracy = self.prediction_accuracy[-self._max_accuracy_history:]
                self.context_window.append(actual_request)
                if len(self.context_window) > self._max_context:
                    self.context_window = self.context_window[-self._max_context:]
                if len(self.context_window) >= 2:
                    prev = self._extract_pattern(self.context_window[:-1], 1)
                    if prev:
                        key = prev
                        if key not in self.conversation_patterns:
                            self.conversation_patterns[key] = []
                        found = False
                        for i, (nxt, cnt) in enumerate(self.conversation_patterns[key]):
                            if nxt == actual:
                                self.conversation_patterns[key][i] = (nxt, cnt + 1)
                                found = True
                                break
                        if not found:
                            self.conversation_patterns[key].append((actual, 1))
        except Exception:
            pass

    def get_proactive_suggestion(self) -> Optional[str]:
        """Faqat yuqori ishonch (>0.85) da taklif."""
        try:
            with self._lock:
                if not self.active_predictions:
                    return None
                top = self.active_predictions[0]
                prob = top.get("probability", 0)
                if prob >= _HIGH_CONFIDENCE:
                    pred = top.get("prediction", "")
                    if pred:
                        return f"O'ylaymanki siz «{pred}» ni ham xohlashingiz mumkin."
        except Exception:
            pass
        return None

    def calculate_prediction_error(self, expected: str, actual: str) -> float:
        """Free Energy: bashorat vs haqiqat farqi."""
        exp = self._normalize_request(expected)
        act = self._normalize_request(actual)
        if not exp or not act:
            return 1.0
        if exp == act:
            return 0.0
        exp_w = set(exp.split())
        act_w = set(act.split())
        overlap = len(exp_w & act_w) / max(1, len(exp_w | act_w))
        return 1.0 - overlap


_SINGLETON: Optional[PredictiveLayer] = None
_SINGLETON_LOCK = threading.Lock()


def get_predictive_layer(
    world_model: Optional[Any] = None,
    active_inference: Optional[Any] = None,
) -> PredictiveLayer:
    """Singleton PredictiveLayer. NEUROKEY_FREE_ENERGY bo'lsa world_model bilan."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                wm, ai = None, None
                try:
                    import config as C
                    if getattr(C, "NEUROKEY_FREE_ENERGY", True):
                        from world_model import get_world_model
                        from active_inference import get_active_inference
                        wm = get_world_model()
                        ai = get_active_inference()
                except Exception:
                    pass
                _SINGLETON = PredictiveLayer(world_model=wm or world_model, active_inference=ai or active_inference)
    return _SINGLETON
