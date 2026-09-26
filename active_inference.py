# -*- coding: utf-8 -*-
"""NeuroKey — Active Inference Engine.

Friston Active Inference: har input kuzatiladi, bashorat qilinadi,
xato hisoblanadi, va xatoni kamaytirish uchun model yangilanadi yoki harakat qilinadi.
"""

from __future__ import annotations

try: import meta_cognition as _ai_mc
except ImportError: _ai_mc = None
try: import predictive_layer as _ai_pl
except ImportError: _ai_pl = None
try: import global_workspace as _ai_gw
except ImportError: _ai_gw = None

import math
import threading
import time
from typing import Any, Dict, List, Optional

_MAX_INFERENCE_LOG = 50


class ActiveInference:
    """
    Friston Active Inference implementatsiyasi.
    Asosiy loop: perceive → predict → minimize_free_energy → update.
    """

    def __init__(
        self,
        world_model: Any,
        body_state: Optional[Any] = None,
        valence_state: Optional[Any] = None,
    ) -> None:
        self.world_model = world_model
        self.body_state = body_state
        self.valence_state = valence_state
        self._lock = threading.RLock()

        self.prediction_error: float = 0.0
        self.free_energy: float = 0.0
        self.precision: float = 1.0

        self.learning_rate: float = 0.1
        self.action_threshold: float = 0.7
        self.surprise_threshold: float = 0.6

        self.inference_log: List[Dict[str, Any]] = []
        self._prediction_errors: List[float] = []

    def perceive(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Yangi kuzatishni qayta ishlash.
        """
        try:
            with self._lock:
                user_input = observation.get("user_input", observation.get("input", ""))
                context = {
                    "context": observation.get("previous_context", []),
                    "time": observation.get("time", time.localtime().tm_hour),
                }
                prediction = self.world_model.predict(context)
                surprise = self.world_model.calculate_surprise(
                    str(user_input)[:200], prediction
                )
                pred_error = surprise
                self.prediction_error = pred_error

                # Precision: ko'p xato → past
                self._prediction_errors.append(pred_error)
                if len(self._prediction_errors) > 20:
                    self._prediction_errors = self._prediction_errors[-20:]
                avg_err = sum(self._prediction_errors) / len(self._prediction_errors)
                self.precision = max(0.1, min(1.0, 1.0 - avg_err * 0.8))

                self.free_energy = self.calculate_free_energy(
                    observation, prediction
                )

                return {
                    "surprise_level": surprise,
                    "prediction_error": pred_error,
                    "free_energy": self.free_energy,
                    "requires_attention": surprise > self.surprise_threshold,
                    "update_needed": pred_error > 0.3,
                }
        except Exception:
            return {
                "surprise_level": 0.0,
                "prediction_error": 0.0,
                "free_energy": 0.0,
                "requires_attention": False,
                "update_needed": False,
            }

    def minimize_free_energy(self, perception_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Free Energy minimizatsiya.
        """
        try:
            with self._lock:
                pred_err = perception_result.get("prediction_error", 0)
                if pred_err < 0.2:
                    return {
                        "strategy": "update_model",
                        "action": None,
                        "model_update": {"confidence_boost": 0.05},
                        "confidence": self.precision,
                    }
                if pred_err > self.action_threshold:
                    return {
                        "strategy": "both",
                        "action": "clarify",
                        "model_update": {"learning_rate": self.learning_rate},
                        "confidence": self.precision,
                    }
                return {
                    "strategy": "update_model",
                    "action": None,
                    "model_update": {},
                    "confidence": self.precision,
                }
        except Exception:
            return {
                "strategy": "update_model",
                "action": None,
                "model_update": None,
                "confidence": 0.5,
            }

    def calculate_free_energy(
        self,
        observation: Dict[str, Any],
        prediction: Dict[str, Any],
    ) -> float:
        """
        F = prediction_error + model_complexity_penalty
        """
        try:
            user_input = observation.get("user_input", observation.get("input", ""))
            surprise = self.world_model.calculate_surprise(
                str(user_input)[:200], prediction
            )
            complexity = 0.1 * (1.0 - self.world_model.model_confidence)
            return min(2.0, surprise + complexity)
        except Exception:
            return 0.0

    def update_precision(self, prediction_errors: List[float]) -> None:
        """Precision yangilash."""
        try:
            with self._lock:
                self._prediction_errors.extend(prediction_errors[-10:])
                if len(self._prediction_errors) > 30:
                    self._prediction_errors = self._prediction_errors[-30:]
                avg = sum(self._prediction_errors) / len(self._prediction_errors)
                self.precision = max(0.1, min(1.0, 1.0 - avg * 0.8))
        except Exception:
            pass

    def generate_action(
        self,
        goal: str,
        current_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Maqsadga erishish uchun harakat tanlash.
        """
        return {
            "action_type": "respond",
            "parameters": {"goal": goal},
            "expected_outcome": {"goal_met": True},
            "confidence": self.precision,
        }

    def run_inference_cycle(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        To'liq bir inference sikli.
        """
        start = time.perf_counter()
        try:
            perc = self.perceive(observation)
            min_result = self.minimize_free_energy(perc)
            user_input = observation.get("user_input", observation.get("input", ""))
            self.world_model.update(str(user_input)[:200], observation)

            if min_result.get("model_update"):
                conf = min_result["model_update"].get("confidence_boost", 0)
                if conf:
                    self.world_model.model_confidence = min(
                        0.95,
                        self.world_model.model_confidence + conf,
                    )

            result = {
                "strategy": min_result.get("strategy", "update_model"),
                "surprise": perc.get("surprise_level", 0),
                "free_energy": perc.get("free_energy", 0),
                "requires_attention": perc.get("requires_attention", False),
                "confidence": min_result.get("confidence", 0.5),
            }
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed < 50:
                self.inference_log.append({"observation": observation, "result": result})
                if len(self.inference_log) > _MAX_INFERENCE_LOG:
                    self.inference_log = self.inference_log[-_MAX_INFERENCE_LOG:]
            return result
        except Exception:
            return {
                "strategy": "update_model",
                "surprise": 0.0,
                "free_energy": 0.0,
                "requires_attention": False,
                "confidence": 0.5,
            }


_SINGLETON: Optional[ActiveInference] = None
_SINGLETON_LOCK = threading.Lock()


def get_active_inference(
    world_model: Optional[Any] = None,
    body_state: Optional[Any] = None,
    valence_state: Optional[Any] = None,
) -> ActiveInference:
    """Singleton ActiveInference."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                from world_model import get_world_model
                wm = world_model or get_world_model()
                if body_state is None:
                    try:
                        from body_state import get_body_state
                        body_state = get_body_state()
                    except Exception:
                        pass
                if valence_state is None:
                    try:
                        from valence_state import get_valence_state
                        valence_state = get_valence_state()
                    except Exception:
                        pass
                _SINGLETON = ActiveInference(wm, body_state, valence_state)
    return _SINGLETON
