# -*- coding: utf-8 -*-
"""NeuroKey — Virtual Tana Holati (Body State).

Damasio: ong tana holatini modellashtirish natijasida yuzaga keladi.
NeuroKey ning "tanasi" = sensor inputlar yig'indisi.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional


class BodyState:
    """
    NeuroKey ning virtual tana modeli.
    Damasio: ong tana holatini modellashtirish natijasida yuzaga keladi.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._start_time = time.time()

        # Vizual holat
        self.visual_load: float = 0.0
        self.visual_complexity: float = 0.0
        self.motion_detected: bool = False
        self.face_present: bool = False

        # Audial holat
        self.audio_level: float = 0.0
        self.speech_detected: bool = False
        self.noise_level: float = 0.0
        self.voice_emotion: Optional[str] = None

        # Tizim holati
        self.cpu_load: float = 0.0
        self.memory_pressure: float = 0.0
        self.response_latency: float = 0.0
        self.uptime: float = 0.0

        # Interaksiya holati
        self.interaction_frequency: float = 0.0
        self.last_interaction_ago: float = 0.0
        self.user_engagement: float = 0.0

        # Jamlangan holat
        self.arousal: float = 0.5
        self.comfort: float = 0.7
        self.alertness: float = 0.8

    def update_from_visual(self, screen_data: Dict[str, Any]) -> None:
        """
        Screen monitor dan kelgan ma'lumotni tana holatiga aylantir.
        screen_data: {complexity, active_windows, motion, brightness}
        """
        try:
            with self._lock:
                self.visual_complexity = float(screen_data.get("complexity", 0.0))
                self.visual_load = min(1.0, self.visual_complexity * 1.2)
                self.motion_detected = bool(screen_data.get("motion", False))
                self.face_present = bool(screen_data.get("face_present", False))
        except Exception:
            pass

    def update_from_audio(self, audio_data: Dict[str, Any]) -> None:
        """
        Mikrofon ma'lumotini tana holatiga aylantir.
        audio_data: {level, has_speech, emotion, noise}
        """
        try:
            with self._lock:
                self.audio_level = float(audio_data.get("level", 0.0))
                self.speech_detected = bool(audio_data.get("has_speech", False))
                self.noise_level = float(audio_data.get("noise", 0.0))
                self.voice_emotion = str(audio_data.get("emotion", "")) or None
        except Exception:
            pass

    def update_from_system(self, system_data: Dict[str, Any]) -> None:
        """
        CPU, RAM, latency dan tana holatiga aylantir.
        Yuqori CPU = "qiynalish" hissi.
        """
        try:
            with self._lock:
                self.cpu_load = float(system_data.get("cpu", 0.0))
                self.memory_pressure = float(system_data.get("memory", 0.0))
                self.response_latency = float(system_data.get("latency", 0.0))
                self.uptime = time.time() - self._start_time

                # Comfort: yuqori yuk = past
                if self.cpu_load > 0.9 or self.memory_pressure > 0.9:
                    self.comfort = max(0.1, 0.7 - self.cpu_load * 0.4)
                elif self.cpu_load > 0.7:
                    self.comfort = max(0.1, 0.7 - self.cpu_load * 0.3)
                else:
                    self.comfort = max(0.1, min(0.95, 0.7 + (1 - self.cpu_load) * 0.2))

                # Arousal: stress = yuqori
                if self.cpu_load > 0.9:
                    self.arousal = min(1.0, 0.5 + self.cpu_load * 0.5)
                elif self.cpu_load > 0.7:
                    self.arousal = min(1.0, 0.5 + self.cpu_load * 0.3)
                else:
                    self.arousal = 0.5 + self.cpu_load * 0.2

                # Alertness: latency past = yuqori
                if self.response_latency > 1000:
                    self.alertness = max(0.3, 0.8 - self.response_latency / 5000)
                else:
                    self.alertness = 0.8
        except Exception:
            pass

    def update_interaction(self, frequency: float, last_ago: float, engagement: float) -> None:
        """Interaksiya holatini yangilash."""
        try:
            with self._lock:
                self.interaction_frequency = frequency
                self.last_interaction_ago = last_ago
                self.user_engagement = engagement
        except Exception:
            pass

    def get_integrated_state(self) -> Dict[str, Any]:
        """
        Barcha sensorlardan jamlangan holat.
        Bu valence_state va arousal_state ga uzatiladi.
        """
        try:
            with self._lock:
                dominant = "calm"
                if self.cpu_load > 0.8 or self.visual_complexity > 0.8:
                    dominant = "busy"
                elif self.alertness > 0.8 and self.visual_complexity > 0.5:
                    dominant = "alert"
                elif self.uptime > 3600 and self.interaction_frequency < 0.5:
                    dominant = "tired"
                elif self.visual_load > 0.7:
                    dominant = "busy"

                return {
                    "arousal": self.arousal,
                    "comfort": self.comfort,
                    "alertness": self.alertness,
                    "dominant_sensation": dominant,
                    "body_narrative": self._build_narrative(),
                }
        except Exception:
            return {
                "arousal": 0.5,
                "comfort": 0.7,
                "alertness": 0.8,
                "dominant_sensation": "calm",
                "body_narrative": "Men hozir odatiy holatdaman.",
            }

    def _build_narrative(self) -> str:
        """Ichki hikoya: 'Men hozir...'"""
        parts = []
        if self.visual_complexity > 0.6:
            parts.append("ekranda ko'p ma'lumot bor")
        if self.noise_level > 0.5:
            parts.append("ovoz shovqinli")
        elif self.audio_level < 0.1 and self.audio_level > 0:
            parts.append("jim muhit")
        if 0.3 < self.cpu_load < 0.7:
            parts.append("tizim yuki o'rtacha")
        elif self.cpu_load > 0.8:
            parts.append("tizim yuklangan")
        if self.alertness > 0.7:
            parts.append("sergak va diqqatli holatdaman")
        if not parts:
            parts.append("odatiy holatdaman")
        return "Men hozir " + ", ".join(parts) + "."

    def to_llm_context(self) -> str:
        """
        LLM system prompt uchun tana holati tavsifi.
        """
        return self._build_narrative()


_SINGLETON: Optional[BodyState] = None
_SINGLETON_LOCK = threading.Lock()


def get_body_state() -> BodyState:
    """Singleton BodyState."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = BodyState()
    return _SINGLETON
