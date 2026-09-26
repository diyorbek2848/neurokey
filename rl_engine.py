# -*- coding: utf-8 -*-
"""NeuroKey — Reinforcement Learning Engine.

NeuroKey har interaksiyadan o'rganadi.
Model: State → Action → Reward → Update.
"""

from __future__ import annotations

import json
import os
import random
import threading
from typing import Any, Dict, List, Optional, Tuple

RESPONSE_STYLES = ("detailed", "brief", "conversational")


def _discretize(val: float, bins: int) -> int:
    return min(bins - 1, max(0, int(val * bins)))


def _hashable_state(
    valence: float,
    arousal: float,
    task_type: str,
    hour: int,
    session_len: int,
) -> Tuple:
    v_bin = _discretize((valence + 1) / 2, 3)
    a_bin = _discretize(arousal, 3)
    h_bin = 0 if 6 <= hour < 12 else (1 if 12 <= hour < 18 else 2)
    s_bin = 0 if session_len < 5 else (1 if session_len < 15 else 2)
    tt = (task_type or "general")[:20]
    return (v_bin, a_bin, tt, h_bin, s_bin)


class RLEngine:
    """Oddiy RL: State → Action → Reward → Update."""

    def __init__(self, storage_path: Optional[str] = None) -> None:
        if storage_path is None:
            _root = os.path.dirname(os.path.abspath(__file__))
            storage_path = os.path.join(_root, "data", "rl_memory.json")
        self.storage_path = storage_path
        self._lock = threading.RLock()
        self.q_table: Dict[str, Dict[str, float]] = {}
        self.experience_buffer: List[Dict[str, Any]] = []
        self.learning_rate = 0.1
        self.discount_factor = 0.9
        self.epsilon = 0.1
        self._max_buffer = 100

    def get_state(self, context: Dict[str, Any]) -> Tuple:
        valence = float(context.get("valence", 0.0))
        arousal = float(context.get("arousal", 0.5))
        task_type = str(context.get("task_type", "general"))
        hour = int(context.get("hour", 12))
        session_len = int(context.get("session_length", 0))
        return _hashable_state(valence, arousal, task_type, hour, session_len)

    def _state_key(self, state: Tuple) -> str:
        return str(state)

    def _action_key(self, action: Dict[str, Any]) -> str:
        style = action.get("response_style", "conversational")
        detail = _discretize(action.get("detail_level", 0.5), 3)
        form = _discretize(action.get("formality", 0.5), 3)
        proact = _discretize(action.get("proactivity", 0.3), 3)
        use_ex = 1 if action.get("use_examples", False) else 0
        return f"{style}_{detail}_{form}_{proact}_{use_ex}"

    def _default_action(self) -> Dict[str, Any]:
        return {
            "response_style": "conversational",
            "detail_level": 0.5,
            "proactivity": 0.3,
            "formality": 0.5,
            "use_examples": False,
        }

    def _random_action(self) -> Dict[str, Any]:
        return {
            "response_style": random.choice(RESPONSE_STYLES),
            "detail_level": random.uniform(0.2, 0.9),
            "proactivity": random.uniform(0.0, 0.6),
            "formality": random.uniform(0.2, 0.8),
            "use_examples": random.random() > 0.6,
        }

    def choose_action(self, state: Tuple) -> Dict[str, Any]:
        with self._lock:
            if random.random() < self.epsilon:
                return self._random_action()
            sk = self._state_key(state)
            actions = self.q_table.get(sk, {})
            if not actions:
                return self._default_action()
            best_key = max(actions, key=actions.get)
            parts = best_key.split("_")
            if len(parts) >= 5:
                return {
                    "response_style": parts[0] if parts[0] in RESPONSE_STYLES else "conversational",
                    "detail_level": int(parts[1]) / 3.0 if parts[1].isdigit() else 0.5,
                    "formality": int(parts[2]) / 3.0 if parts[2].isdigit() else 0.5,
                    "proactivity": int(parts[3]) / 3.0 if parts[3].isdigit() else 0.3,
                    "use_examples": parts[4] == "1" if len(parts) > 4 else False,
                }
            return self._default_action()

    def infer_reward(self, user_response: str, response_time: float = 0.0) -> float:
        text = (user_response or "").lower().strip()
        reward = 0.0
        pos = ["rahmat", "thanks", "spasibo", "yaxshi", "great", "zo'r", "ha", "da", "yes"]
        neg = ["yo'q", "no", "xato", "wrong", "yomon", "tushunmadim", "boshqa", "нет", "не то"]
        if any(p in text for p in pos):
            reward += 0.8
        if any(n in text for n in neg):
            reward -= 0.7
        if response_time > 0:
            if response_time < 2.0 and len(text) < 50:
                reward += 0.1
            elif response_time > 30:
                reward -= 0.2
        return max(-1.0, min(1.0, reward))

    def update(
        self,
        state: Tuple,
        action: Dict[str, Any],
        reward: float,
        next_state: Tuple,
    ) -> None:
        try:
            with self._lock:
                sk = self._state_key(state)
                ak = self._action_key(action)
                nsk = self._state_key(next_state)
                if sk not in self.q_table:
                    self.q_table[sk] = {}
                q_sa = self.q_table[sk].get(ak, 0.0)
                max_next = 0.0
                if nsk in self.q_table and self.q_table[nsk]:
                    max_next = max(self.q_table[nsk].values())
                new_q = q_sa + self.learning_rate * (
                    reward + self.discount_factor * max_next - q_sa
                )
                self.q_table[sk][ak] = new_q
                self.experience_buffer.append({"state": state, "action": action, "reward": reward})
                if len(self.experience_buffer) > self._max_buffer:
                    self.experience_buffer = self.experience_buffer[-self._max_buffer:]
        except Exception:
            pass

    def get_best_response_params(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            state = self.get_state(context)
            return self.choose_action(state)
        except Exception:
            return self._default_action()

    def save(self) -> None:
        try:
            with self._lock:
                data = {"q_table": dict(self.q_table), "learning_rate": self.learning_rate, "epsilon": self.epsilon}
                d = os.path.dirname(self.storage_path)
                if d and not os.path.isdir(d):
                    os.makedirs(d, exist_ok=True)
                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=0)
        except Exception:
            pass

    def load(self) -> None:
        try:
            if os.path.isfile(self.storage_path):
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with self._lock:
                    self.q_table = data.get("q_table", {})
                    self.learning_rate = float(data.get("learning_rate", self.learning_rate))
                    self.epsilon = float(data.get("epsilon", self.epsilon))
        except Exception:
            pass


_SINGLETON: Optional[RLEngine] = None
_SINGLETON_LOCK = threading.Lock()


def get_rl_engine(storage_path: Optional[str] = None) -> RLEngine:
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = RLEngine(storage_path=storage_path)
                _SINGLETON.load()
    return _SINGLETON
