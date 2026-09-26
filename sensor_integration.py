# -*- coding: utf-8 -*-
"""NeuroKey — Sensor Integratsiya Hub.

Barcha sensorlarni bir joyda boshqaruvchi hub.
Ekran, mikrofon, tizim, kamera (opsional).
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import psutil
    _HAVE_PSUTIL = True
except ImportError:
    psutil = None
    _HAVE_PSUTIL = False

try:
    import sounddevice as sd
    import numpy as np
    _HAVE_SOUNDDEVICE = True
except ImportError:
    sd = None
    np = None
    _HAVE_SOUNDDEVICE = False


class SensorIntegration:
    """
    Barcha sensorlarni bir joyda boshqaruvchi hub.
    """

    def __init__(self, body_state: Any) -> None:
        self.body_state = body_state
        self.screen_buffer: List[Dict[str, Any]] = []
        self.audio_buffer: List[Dict[str, Any]] = []
        self.system_buffer: List[Dict[str, Any]] = []
        self.update_interval = 1.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._max_screen = 5
        self._max_audio = 10
        self._max_system = 20
        self._last_system: Dict[str, float] = {}  # Anomaly uchun

    def start(self) -> None:
        """Background thread da doimiy sensor o'qish."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._integrate_loop,
            daemon=True,
            name="SensorIntegration",
        )
        self._thread.start()

    def stop(self) -> None:
        """Sensorlarni to'xtatish. Chiqishda traceback chiqmasligi uchun xatoliklar yutiladi."""
        self._running = False
        if self._thread:
            try:
                self._thread.join(timeout=2.0)
            except BaseException:
                pass
            self._thread = None

    def _read_screen_sensor(self) -> Dict[str, Any]:
        """
        screen_monitor.py dan ekran ma'lumotini olish.
        """
        try:
            from screen_monitor import get_screen_monitor, get_screen_complexity, get_motion_level
            monitor = get_screen_monitor()
            try:
                complexity = get_screen_complexity()
            except Exception:
                complexity = 0.0
            try:
                motion = get_motion_level()
            except Exception:
                motion = 0.0
            ws = monitor.get_true_window_state()
            active = len(ws.get("visible_windows", [])) + len(ws.get("minimized_windows", []))
            return {
                "complexity": complexity,
                "active_windows": active,
                "motion": motion > 0.3,
                "brightness": 0.5,
                "face_present": False,
            }
        except Exception:
            return {"complexity": 0.0, "active_windows": 0, "motion": False, "brightness": 0.5, "face_present": False}

    def _read_audio_sensor(self) -> Dict[str, Any]:
        """
        Mikrofondan audio ma'lumot (passiv, faqat o'lchov).
        Foydalanuvchi ruxsati bo'lmasa - skip.
        """
        # Mikrofonni bu yerda ochmaymiz. STT va TTS PortAudio ni ushlab turadi.
        # Fon threadidan sd.rec() Windows da 0xc0000374 (heap buzilishi) beradi,
        # ovoz xirillaydi va dastur o'zi yopiladi.
        return {"level": 0.0, "has_speech": False, "emotion": "", "noise": 0.0}

    def _read_system_sensor(self) -> Dict[str, Any]:
        """
        psutil orqali tizim holati.
        """
        if not _HAVE_PSUTIL or not psutil:
            return {"cpu": 0.0, "memory": 0.0, "latency": 0.0, "disk": 0.0}
        try:
            cpu = psutil.cpu_percent(interval=0.1) / 100.0
            mem = psutil.virtual_memory().percent / 100.0
            disk = 0.0
            try:
                disk = psutil.disk_usage("C:").percent / 100.0
            except Exception:
                pass
            latency = 0.0
            try:
                r = subprocess.run(
                    ["ping", "-n", "1", "-w", "500", "8.8.8.8"],
                    capture_output=True,
                    timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                if r.returncode == 0 and r.stdout:
                    for line in r.stdout.decode("utf-8", errors="replace").splitlines():
                        if "ms" in line and "time=" in line.lower():
                            import re
                            m = re.search(r"(\d+)\s*ms", line)
                            if m:
                                latency = float(m.group(1))
                                break
            except Exception:
                pass
            return {"cpu": cpu, "memory": mem, "latency": latency, "disk": disk}
        except Exception:
            return {"cpu": 0.0, "memory": 0.0, "latency": 0.0, "disk": 0.0}

    def _integrate_all(self) -> None:
        """Barcha sensorlarni birlashtirish."""
        try:
            screen_data = self._read_screen_sensor()
            self.body_state.update_from_visual(screen_data)
            with self._lock:
                self.screen_buffer.append(screen_data)
                if len(self.screen_buffer) > self._max_screen:
                    self.screen_buffer = self.screen_buffer[-self._max_screen:]

            audio_data = self._read_audio_sensor()
            self.body_state.update_from_audio(audio_data)
            with self._lock:
                self.audio_buffer.append(audio_data)
                if len(self.audio_buffer) > self._max_audio:
                    self.audio_buffer = self.audio_buffer[-self._max_audio:]

            system_data = self._read_system_sensor()
            self.body_state.update_from_system({
                "cpu": system_data.get("cpu", 0),
                "memory": system_data.get("memory", 0),
                "latency": system_data.get("latency", 0) * 1000,
            })
            with self._lock:
                self.system_buffer.append(system_data)
                self._last_system = system_data
                if len(self.system_buffer) > self._max_system:
                    self.system_buffer = self.system_buffer[-self._max_system:]
        except Exception:
            pass

    def _integrate_loop(self) -> None:
        """Background loop."""
        while self._running:
            try:
                self._integrate_all()
            except Exception:
                pass
            time.sleep(self.update_interval)

    def get_current_sensation(self) -> Dict[str, Any]:
        """Hozirgi jamlangan sensor holati."""
        try:
            with self._lock:
                screen = self.screen_buffer[-1] if self.screen_buffer else {}
                audio = self.audio_buffer[-1] if self.audio_buffer else {}
                system = self.system_buffer[-1] if self.system_buffer else {}
            return {
                "screen": screen,
                "audio": audio,
                "system": system,
            }
        except Exception:
            return {"screen": {}, "audio": {}, "system": {}}

    def detect_anomaly(self) -> List[Dict[str, Any]]:
        """
        Kutilmagan o'zgarishlarni aniqlash.
        """
        anomalies: List[Dict[str, Any]] = []
        try:
            with self._lock:
                sys_data = self._last_system.copy()
            cpu = sys_data.get("cpu", 0)
            mem = sys_data.get("memory", 0)
            disk = sys_data.get("disk", 0)
            if cpu > 0.95:
                anomalies.append({"type": "cpu_critical", "severity": 0.9, "description": "CPU kritik 95%+ ga yetdi"})
            elif cpu > 0.85:
                anomalies.append({"type": "cpu_high", "severity": 0.6, "description": "CPU yuqori yuklangan"})
            if mem > 0.95:
                anomalies.append({"type": "memory_critical", "severity": 0.9, "description": "RAM kritik"})
            if disk > 0.95:
                anomalies.append({"type": "disk_full", "severity": 0.9, "description": "Disk to'ldi"})
        except Exception:
            pass
        return anomalies


_SINGLETON: Optional[SensorIntegration] = None
_SINGLETON_LOCK = threading.Lock()


def get_sensor_integration(body_state: Optional[Any] = None) -> SensorIntegration:
    """Singleton SensorIntegration."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                from body_state import get_body_state
                bs = body_state or get_body_state()
                _SINGLETON = SensorIntegration(bs)
    return _SINGLETON
