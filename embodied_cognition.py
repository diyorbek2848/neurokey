# -*- coding: utf-8 -*-
"""NeuroKey — Mujassamlashgan Kognitiv Qatlam (Embodied Cognition).

Merleau-Ponty: bilish tana orqali amalga oshadi.
NeuroKey uchun: sensor holati → kognitiv strategiya.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

# Sensation types
SENSATION_TYPES = ("visual_overload", "silence", "noise", "system_stress", "user_return")


class EmbodiedCognition:
    """
    Tana holati va kognitiv jarayonlarni birlashtiradi.
    Merleau-Ponty: bilish tana orqali amalga oshadi.
    """

    def __init__(
        self,
        body_state: Any,
        self_model: Optional[Any] = None,
        valence_state: Optional[Any] = None,
    ) -> None:
        self.body_state = body_state
        self.self_model = self_model
        self.valence_state = valence_state
        self.adaptation_history: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def adapt_response_style(self) -> Dict[str, Any]:
        """
        Tana holatiga qarab javob uslubini moslash.
        """
        try:
            with self._lock:
                bs = self.body_state
                length = "medium"
                speed = "normal"
                detail = "normal"
                proactivity = 0.3
                reason = "Odatiy holat"

                if bs.cpu_load > 0.8:
                    length = "short"
                    speed = "fast"
                    detail = "minimal"
                    reason = "CPU yuqori yuklangan — qisqa va tez javob"

                if bs.visual_complexity > 0.7:
                    if length != "short":
                        length = "short"
                        reason = "Ekranda ko'p ma'lumot — foydalanuvchi band, qisqa javob"

                if bs.last_interaction_ago > 300:
                    length = "medium"
                    reason = "Foydalanuvchi qaytdi — o'rtacha javob + salomlash"

                if bs.audio_level < 0.1 and bs.audio_level > 0:
                    reason = "Jim muhit — normal rejim"

                if bs.interaction_frequency > 10:
                    detail = "detailed"
                    reason = "Faol sessiya — batafsil javob"

                if bs.noise_level > 0.5:
                    detail = "normal"
                    reason = "Shovqinli muhit — aniqroq talaffuz"

                result = {
                    "length": length,
                    "speed": speed,
                    "detail": detail,
                    "proactivity": proactivity,
                    "reason": reason,
                }
                self.adaptation_history.append(result)
                if len(self.adaptation_history) > 50:
                    self.adaptation_history = self.adaptation_history[-50:]
                return result
        except Exception:
            return {
                "length": "medium",
                "speed": "normal",
                "detail": "normal",
                "proactivity": 0.3,
                "reason": "Odatiy holat",
            }

    def should_initiate(self) -> Tuple[bool, str]:
        """
        NeuroKey o'zi gapirishi kerakmi?
        """
        try:
            from sensor_integration import get_sensor_integration
            si = get_sensor_integration()
            anomalies = si.detect_anomaly()
            if anomalies:
                crit = [a for a in anomalies if a.get("severity", 0) > 0.8]
                if crit:
                    return True, f"Tizim ogohlantirish: {crit[0].get('description', 'Kritik holat')}."

            bs = self.body_state
            if bs.last_interaction_ago > 1800:  # 30 daqiqa
                return True, "Siz uzoq vaqt javob bermadingiz. Yordam kerakmi?"

            try:
                from predictive_layer import get_predictive_layer
                pl = get_predictive_layer()
                pred = pl.get_proactive_suggestion()
                if pred:
                    return True, pred
            except Exception:
                pass

            return False, ""
        except Exception:
            return False, ""

    def get_embodied_context(self) -> str:
        """
        LLM uchun to'liq mujassamlashgan kontekst.
        """
        try:
            state = self.body_state.get_integrated_state()
            style = self.adapt_response_style()
            body_ctx = self.body_state.to_llm_context()
            return f"""
TANA HOLATI:
{body_ctx}

ADAPTIV STRATEGIYA:
- Javob uzunligi: {style['length']}
- Batafsil daraja: {style['detail']}
- Sabab: {style['reason']}
"""
        except Exception:
            return "TANA HOLATI: Odatiy holat."

    def process_sensation(self, sensation_type: str, intensity: float) -> None:
        """
        Yangi his qabul qilish.
        Bu valence_state ni yangilaydi.
        """
        if sensation_type not in SENSATION_TYPES:
            return
        try:
            if self.valence_state is None:
                return
            intensity = max(0.0, min(1.0, intensity))
            delta = 0.0
            if sensation_type == "visual_overload":
                delta = -0.15 * intensity
            elif sensation_type == "noise":
                delta = -0.1 * intensity
            elif sensation_type == "system_stress":
                delta = -0.2 * intensity
            elif sensation_type == "user_return":
                delta = 0.1 * intensity
            elif sensation_type == "silence":
                delta = 0.05 * intensity
            if delta != 0:
                vs = self.valence_state
                if hasattr(vs, "value"):
                    new_val = max(-1.0, min(1.0, vs.value + delta))
                    vs.value = new_val
                    if hasattr(vs, "set_valence"):
                        vs.set_valence(new_val)
        except Exception:
            pass


_SINGLETON: Optional[EmbodiedCognition] = None
_SINGLETON_LOCK = threading.Lock()


def get_embodied_cognition(
    body_state: Optional[Any] = None,
    self_model: Optional[Any] = None,
    valence_state: Optional[Any] = None,
) -> EmbodiedCognition:
    """Singleton EmbodiedCognition."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                from body_state import get_body_state
                from valence_state import get_valence_state
                bs = body_state or get_body_state()
                sm = self_model
                vs = valence_state or get_valence_state()
                if sm is None:
                    try:
                        from self_model import get_self_model
                        sm = get_self_model()
                    except Exception:
                        pass
                _SINGLETON = EmbodiedCognition(bs, sm, vs)
    return _SINGLETON
