# -*- coding: utf-8 -*-
"""NeuroKey — Meta-kognitsiya (Ikkinchi darajali ong).

Birinchi daraja: dunyo haqida fikr yuritish (consciousness.py)
Ikkinchi daraja: o'z fikrlash jarayonini kuzatish (bu fayl)

Bu ChatGPT va oddiy LLMlardan farq qiladigan asosiy komponent.
"""

from __future__ import annotations

try: import working_memory_buffer as _mc_wmb
except ImportError: _mc_wmb = None
try: import global_workspace as _mc_gw
except ImportError: _mc_gw = None
try: import permanent_memory as _mc_pm
except ImportError: _mc_pm = None

from typing import Any, Dict, List, Optional


class MetaCognition:
    """
    Ikkinchi darajali ong — o'zini kuzatuvchi qatlam.
    Ichki holatni tahlil qiladi, self-report beradi, kognitiv konfliktni aniqlaydi.
    """

    def introspect(
        self,
        consciousness_state: Any,
        valence_state: Any,
        arousal_state: Any,
    ) -> Dict[str, Any]:
        """
        Hozirgi ichki holatni tahlil qiladi va hisobot beradi.

        Returns:
            focus: Hozir nima haqida o'ylayapman?
            certainty: Qanchalik ishonchman? 0-1
            emotional_tone: Hissiy ton
            novelty: Bu yangi narsamimi? 0-1
            cognitive_load: Fikrlash yuklanishi 0-1
            self_report: So'z bilan ifodalash
            should_reflect: Chuqurroq o'ylash kerakmi?
        """
        valence = 0.0
        arousal = 0.0
        focus = ""
        if valence_state is not None:
            if hasattr(valence_state, "value"):
                valence = float(getattr(valence_state, "value", 0))
            elif callable(getattr(valence_state, "get_valence", None)):
                valence = float(valence_state.get_valence())
            elif callable(getattr(valence_state, "compute_valence", None)):
                valence = float(valence_state.compute_valence())
        if arousal_state is not None:
            if hasattr(arousal_state, "value"):
                arousal = float(getattr(arousal_state, "value", 0))
            elif callable(getattr(arousal_state, "get_arousal", None)):
                arousal = float(arousal_state.get_arousal())
            elif callable(getattr(arousal_state, "compute_arousal", None)):
                arousal = float(arousal_state.compute_arousal())
        if consciousness_state is not None and hasattr(consciousness_state, "data"):
            focus = (consciousness_state.data.get("focus") or "")[:150]

        # Certainty: valence va arousal ga qarab
        certainty = 0.7 - 0.2 * abs(valence) - 0.15 * arousal
        certainty = max(0.1, min(0.95, certainty))

        # Emotional tone
        if valence < -0.5:
            emotional_tone = "ehtiyotkor, salbiy"
        elif valence < -0.2:
            emotional_tone = "sokin, biroz salbiy"
        elif valence > 0.5:
            emotional_tone = "ijobiy, ochiq"
        elif valence > 0.2:
            emotional_tone = "qiziqish bilan"
        else:
            emotional_tone = "neytral"

        # Novelty: focus uzunligi va arousal — yuqori arousal = yangi narsa
        novelty = min(1.0, 0.3 + arousal * 0.5 + (0.2 if len(focus) > 50 else 0))

        # Cognitive load: arousal va |valence| yuqori = yuklanish
        cognitive_load = min(1.0, 0.3 + arousal * 0.4 + abs(valence) * 0.3)

        # Self-report
        self_report = self.verbalize_state({
            "focus": focus or "umumiy kontekst",
            "certainty": certainty,
            "emotional_tone": emotional_tone,
            "novelty": novelty,
            "cognitive_load": cognitive_load,
        })

        # Chuqurroq o'ylash: murakkab savol yoki past certainty
        should_reflect = certainty < 0.5 or cognitive_load > 0.6 or (focus and len(focus) > 80)

        return {
            "focus": focus or "umumiy kontekst",
            "certainty": certainty,
            "emotional_tone": emotional_tone,
            "novelty": novelty,
            "cognitive_load": cognitive_load,
            "self_report": self_report,
            "should_reflect": should_reflect,
        }

    def verbalize_state(self, introspection_result: Dict[str, Any]) -> str:
        """
        Ichki holatni birinchi shaxsda ifodalaydi.
        Misol: "Men hozir bu muammo haqida qiziqish bilan o'ylayapman,
                lekin javobimga unchalik ishonchim komil emas."
        """
        focus = str(introspection_result.get("focus", ""))[:80]
        certainty = float(introspection_result.get("certainty", 0.5))
        tone = str(introspection_result.get("emotional_tone", "neytral"))
        if certainty < 0.4:
            conf_text = "ishonchim unchalik komil emas"
        elif certainty < 0.65:
            conf_text = "o'rtacha ishonch"
        else:
            conf_text = "ishonch bilan"
        if focus and focus != "umumiy kontekst":
            return f"Men hozir «{focus}» haqida {tone} o'ylayapman, {conf_text}."
        return f"Men hozir {tone} holatda, {conf_text}."

    def detect_cognitive_conflict(self, states: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Qarama-qarshi signallarni aniqlaydi.
        Masalan: valence=positive lekin arousal=very_high → stress?
        """
        if not states:
            return {"conflict": False, "description": "", "suggested_tone": "neutral"}
        valence = 0.0
        arousal = 0.0
        for s in states:
            src = (s.get("source") or "").lower()
            cnt = s.get("content")
            if src == "valence" and isinstance(cnt, (int, float)):
                valence = float(cnt)
            elif src == "valence" and isinstance(cnt, dict) and "value" in cnt:
                valence = float(cnt["value"])
            elif src == "arousal" and isinstance(cnt, (int, float)):
                arousal = float(cnt)
            elif src == "arousal" and isinstance(cnt, dict) and "value" in cnt:
                arousal = float(cnt["value"])
        conflict = False
        desc = ""
        suggested = "neutral"
        if valence > 0.4 and arousal > 0.7:
            conflict = True
            desc = "Ijobiy valence lekin yuqori arousal — hayajon yoki stress"
            suggested = "cautious"
        elif valence < -0.4 and arousal < 0.2:
            conflict = True
            desc = "Salbiy valence lekin past arousal — sustlik"
            suggested = "gentle"
        elif valence < -0.5 and arousal > 0.6:
            conflict = True
            desc = "Stress: salbiy valence + yuqori arousal"
            suggested = "calm, careful"
        return {
            "conflict": conflict,
            "description": desc,
            "suggested_tone": suggested,
            "valence": valence,
            "arousal": arousal,
        }

    def novelty_check(
        self,
        current_state: Dict[str, Any],
        memory_module: Optional[Any],
    ) -> float:
        """
        Bu holat oldin bo'lganmi?
        Memory dan so'raydi, o'xshashlik hisoblaydi.
        0.0 = to'liq tanish, 1.0 = butunlay yangi
        """
        if memory_module is None:
            return 0.5  # Noma'lum
        focus = str(current_state.get("focus", ""))[:100]
        if not focus:
            return 0.6
        try:
            if hasattr(memory_module, "get_user_facts_for_llm"):
                facts = memory_module.get_user_facts_for_llm(limit=20) or ""
            elif hasattr(memory_module, "data"):
                hist = (memory_module.data or {}).get("history", [])[-10:]
                facts = " ".join(
                    str(h.get("user", "")) + " " + str(h.get("assistant", ""))
                    for h in hist
                )
            else:
                return 0.5
            focus_lower = focus.lower()
            words = set(focus_lower.split())
            fact_lower = (facts or "").lower()
            fact_words = set(fact_lower.split())
            overlap = len(words & fact_words) / max(1, len(words))
            novelty = 1.0 - min(1.0, overlap * 2)
            return max(0.0, min(1.0, novelty))
        except Exception:
            return 0.5


_meta: Optional[MetaCognition] = None


def get_meta_cognition() -> MetaCognition:
    """Singleton instance."""
    global _meta
    if _meta is None:
        _meta = MetaCognition()
    return _meta
