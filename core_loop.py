# -*- coding: utf-8 -*-
"""NeuroKey — Consciousness Core loop.

Uzluksiz loop. State. decide() — LLM variantlar, Core tanlash.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from llm_variants import ask_for_candidates, candidates_to_executor_actions
    _HAVE_LLM_VARIANTS = True
except ImportError:
    _HAVE_LLM_VARIANTS = False

try:
    from self_modification import check_blocked
    _HAVE_RULES = True
except ImportError:
    def check_blocked(c): return False
    _HAVE_RULES = False

try:
    from permanent_memory import recall_similar
    _HAVE_MEMORY = True
except ImportError:
    def recall_similar(q, **k): return []
    _HAVE_MEMORY = False

try:
    from emotion_state import update as emotion_update
    _HAVE_EMOTION = True
except ImportError:
    def emotion_update(*a): pass
    _HAVE_EMOTION = False

try:
    from executor import execute
    _HAVE_EXECUTOR = True
except ImportError:
    execute = None
    _HAVE_EXECUTOR = False

try:
    from planner import decompose, is_complex
    _HAVE_PLANNER = True
except ImportError:
    def decompose(t, **k): return [{"action": "respond", "content": t}] if isinstance(t, str) else [t]
    def is_complex(a, **k): return False
    _HAVE_PLANNER = False

try:
    from mood_state import spontaneity_rate as mood_spontaneity_rate
    from spontaneity import choose_with_spontaneity
    _HAVE_SPONTANEITY = True
except ImportError:
    def mood_spontaneity_rate(**k): return 0.0
    def choose_with_spontaneity(c, r): return (c[0] if c else None, False)
    _HAVE_SPONTANEITY = False

try:
    from regret import add_fail as regret_add_fail
    _HAVE_REGRET = True
except ImportError:
    def regret_add_fail(a): pass
    _HAVE_REGRET = False

try:
    from mood_state import update as mood_update
    from boredom import update as boredom_update, seek_novelty as boredom_seek_novelty
    from energy_state import update as energy_update
    _HAVE_LIFESTATE = True
except ImportError:
    def mood_update(*a): pass
    def boredom_update(*a): pass
    def boredom_seek_novelty(): return False
    def energy_update(*a): pass
    _HAVE_LIFESTATE = False

try:
    from autonomous_candidates import autonomous_candidates
    _HAVE_AUTONOMOUS = True
except ImportError:
    def autonomous_candidates(*a, **k): return []
    _HAVE_AUTONOMOUS = False

try:
    from score_candidates import score_candidates
    _HAVE_SCORE = True
except ImportError:
    def score_candidates(c, **k): return c[:5] if c else []
    _HAVE_SCORE = False

try:
    from world_model import add_pattern as world_add_pattern
    _HAVE_WORLD = True
except ImportError:
    def world_add_pattern(*a, **k): pass
    _HAVE_WORLD = False


@dataclass
class CoreState:
    """Core holati — har qarorda yangilanadi."""
    focus: str = ""
    intention: str = ""
    emotion: str = ""
    last_result: str = ""
    last_action: str = ""
    last_ok: bool = False


@dataclass
class CoreLoop:
    """Consciousness Core — asosiy loop."""
    state: CoreState = field(default_factory=CoreState)
    _running: bool = False
    _interval_sec: float = 1.0
    _data_dir: str = ""

    def decide(self, inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Input dan qaror. LLM variantlar yoki autonomous (user yo'q).
        Qoidalar + xotira + emotion → filter → score → spontanlik → tanlash.
        """
        user = (inputs.get("user") or "").strip()
        has_user = bool(user)

        # 1. Variantlar — user bor: LLM, user yo'q: autonomous (curiosity, boredom)
        candidates: List[Dict[str, Any]] = []
        if has_user:
            if _HAVE_LLM_VARIANTS:
                ctx = {
                    "screen": inputs.get("screen", ""),
                    "files": inputs.get("files", ""),
                    "memory": inputs.get("memory", ""),
                    "processes": inputs.get("processes", ""),
                }
                if _HAVE_REGRET:
                    from regret import get_regret_for_llm
                    ctx["regret"] = get_regret_for_llm()
                last_fail = self.state.last_action if not self.state.last_ok else None
                if last_fail:
                    ctx["last_failed"] = last_fail
                try:
                    from valence_state import get_valence_for_llm
                    ctx["valence"] = get_valence_for_llm()
                except ImportError:
                    pass
                try:
                    from arousal_state import get_arousal_for_llm
                    ctx["arousal"] = get_arousal_for_llm()
                except ImportError:
                    pass
                raw = ask_for_candidates(user, context=ctx, max_candidates=8)
                candidates = candidates_to_executor_actions(raw)
            else:
                candidates = [{"action": "respond", "content": user}]
        else:
            if _HAVE_AUTONOMOUS:
                seek = boredom_seek_novelty() if _HAVE_LIFESTATE else False
                candidates = autonomous_candidates(inputs, seek_novelty=seek)
            if not candidates:
                return None

        if not candidates:
            return {"action": "respond", "content": user} if has_user else None

        # 2. Qoidalar — blocked
        if _HAVE_RULES:
            data_dir = self._data_dir or os.path.join(os.path.dirname(__file__), "data")
            rules_path = os.path.join(data_dir, "rules.json")
            candidates = [c for c in candidates if not check_blocked(c, path=rules_path)]

        # 3. Xotira — o'xshash vazifada yomon bo'lsa, respond ni ustun qilish
        if _HAVE_MEMORY and candidates:
            mem_path = os.path.join(self._data_dir or os.path.dirname(__file__), "data", "consciousness_stream.log")
            similar = recall_similar(user, path=mem_path, limit=5)
            fail_count = sum(1 for s in similar if not s.get("ok", True))
            if fail_count >= 2 and len(candidates) > 1:
                respond = next((c for c in candidates if c.get("action") == "respond"), None)
                if respond:
                    candidates = [respond] + [c for c in candidates if c != respond]

        if not candidates:
            return {"action": "respond", "content": user} if has_user else None

        # 4. Emotion, regret — LLM ga ma'lumot (ask_for_candidates context). Biz qoida qo'ymaymiz.
        # 5. Scoring — world_model, emotion, mood
        if _HAVE_SCORE and candidates:
            data_dir = self._data_dir or os.path.join(os.path.dirname(__file__), "data")
            top_k = score_candidates(candidates, query=user, data_dir=data_dir)
            if top_k:
                candidates = top_k

        # 7. Tanlash — spontanlik yoki birinchi
        if _HAVE_SPONTANEITY:
            rate = mood_spontaneity_rate()
            chosen, _ = choose_with_spontaneity(candidates, rate)
            if chosen:
                return chosen
        return candidates[0]

    def update_state(self, result: Any, action: str = "", ok: bool = False, action_dict: Optional[Dict[str, Any]] = None) -> None:
        """Natija state ga ta'sir qiladi."""
        self.state.last_result = str(result)[:200] if result else ""
        self.state.last_action = (action or "")[:100]
        self.state.last_ok = ok
        if ok:
            self.state.emotion = "satisfaction"
        else:
            self.state.emotion = "frustration"
        if _HAVE_EMOTION:
            emotion_update(ok, action)
        try:
            from valence_state import update as valence_update
            valence_update(ok, action)
        except ImportError:
            pass
        try:
            from arousal_state import update as arousal_update
            arousal_update(ok, action)
        except ImportError:
            pass
        if _HAVE_LIFESTATE:
            mood_update(ok, action)
            boredom_update(ok, action)
            energy_update(ok, action)
        if _HAVE_REGRET and not ok and action_dict:
            regret_add_fail(action_dict)
        if _HAVE_WORLD and ok and action_dict:
            act = action_dict.get("action", "")
            path = action_dict.get("path") or action_dict.get("root") or ""
            if act:
                pattern = f"{act} {path}".strip()[:80]
                if pattern:
                    data_dir = self._data_dir or os.path.join(os.path.dirname(__file__), "data")
                    world_add_pattern(pattern, path=os.path.join(data_dir, "world_model.json"))

    def run_once(self, inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Bir tsikl: input → decide → (execute tashqarida)."""
        return self.decide(inputs)

    def get_state(self) -> Dict[str, Any]:
        """State dict."""
        return {
            "focus": self.state.focus,
            "intention": self.state.intention,
            "emotion": self.state.emotion,
            "last_result": self.state.last_result,
            "last_action": self.state.last_action,
            "last_ok": self.state.last_ok,
        }


# Global instance
_core: Optional[CoreLoop] = None


def get_core(data_dir: str = "") -> CoreLoop:
    """Singleton Core."""
    global _core
    if _core is None:
        _core = CoreLoop()
    if data_dir:
        _core._data_dir = data_dir
    return _core
