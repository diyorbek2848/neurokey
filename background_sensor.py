# -*- coding: utf-8 -*-
"""NeuroKey — Fon Sezgisi (Background Sensor).

Har 30 sekundda dunyo holati yig'iladi:
- Vaqt / kun / yil 2026
- Tizim resurslari (CPU, RAM)
- Foydalanuvchi faolligi (oxirgi harakat qachon)
- Ekran faolligi (qaysi dastur ochiq)

Bu ma'lumotlar consciousness_ctx ga inject qilinadi.
Tizim "tana sezgisi"ga ega bo'ladi — embodiment.
"""
from __future__ import annotations

try: from arousal_state import get_arousal as _bgs_arousal
except ImportError: _bgs_arousal = None
try: from valence_state import get_valence as _bgs_valence
except ImportError: _bgs_valence = None

import json
import logging
import os
import platform
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_SENSOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sensor_state.json")
_UPDATE_INTERVAL = 30  # har 30 soniyada
_last_user_activity: float = time.time()
_sensor_lock = threading.Lock()
_sensor_state: Dict[str, Any] = {}
_sensor_thread: Optional[threading.Thread] = None
_running = False


def notify_user_activity() -> None:
    """Foydalanuvchi faol bo'lganda chaqirish — input yetib keldi."""
    global _last_user_activity
    _last_user_activity = time.time()


def _collect_system_info() -> Dict[str, Any]:
    """Tizim holati — CPU, RAM, vaqt."""
    info: Dict[str, Any] = {}

    # Vaqt
    now = datetime.now()
    info["timestamp"] = now.isoformat()
    info["time_str"] = now.strftime("%H:%M")
    info["date_str"] = now.strftime("%Y-%m-%d")  # 2026-...
    info["weekday"] = now.strftime("%A")  # Monday...
    info["hour"] = now.hour
    info["is_night"] = now.hour < 7 or now.hour >= 22
    info["is_working_hours"] = 9 <= now.hour <= 18

    # Tizim
    info["platform"] = platform.system()  # Windows
    info["node"] = platform.node()  # kompyuter nomi

    # CPU / RAM (psutil orqali)
    try:
        import psutil
        info["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        vm = psutil.virtual_memory()
        info["ram_percent"] = vm.percent
        info["ram_available_gb"] = round(vm.available / 1024**3, 1)

        # Batareya (noutbuk)
        bat = psutil.sensors_battery()
        if bat:
            info["battery_percent"] = round(bat.percent, 0)
            info["battery_plugged"] = bat.power_plugged
        else:
            info["battery_percent"] = None

        # Ochiq jarayonlar soni
        info["process_count"] = len(psutil.pids())

        # Faol oyna (Windows)
        try:
            import pygetwindow as gw
            active = gw.getActiveWindow()
            if active:
                info["active_window"] = (active.title or "")[:80]
            else:
                info["active_window"] = ""
        except Exception:
            info["active_window"] = ""

    except Exception as e:
        log.debug("[Sensor] psutil xato: %s", e)

    # Foydalanuvchi faolligi
    idle_sec = time.time() - _last_user_activity
    info["user_idle_sec"] = int(idle_sec)
    info["user_idle_min"] = round(idle_sec / 60, 1)

    if idle_sec < 30:
        info["user_activity"] = "faol"
    elif idle_sec < 300:
        info["user_activity"] = "sust ({}s oldin)".format(int(idle_sec))
    elif idle_sec < 3600:
        info["user_activity"] = "uzoq muddat yo'q ({} daq)".format(int(idle_sec // 60))
    else:
        info["user_activity"] = "juda uzoq yo'q ({} soat)".format(int(idle_sec // 3600))

    return info


def _save_sensor(state: Dict[str, Any]) -> None:
    try:
        d = os.path.dirname(_SENSOR_PATH)
        os.makedirs(d, exist_ok=True)
        with open(_SENSOR_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Sensor] saqlash xato: %s", e)


def _sensor_loop() -> None:
    global _sensor_state
    while _running:
        try:
            state = _collect_system_info()
            with _sensor_lock:
                _sensor_state = state
            _save_sensor(state)
        except Exception as e:
            log.debug("[Sensor] loop xato: %s", e)
        time.sleep(_UPDATE_INTERVAL)


def start_sensor() -> None:
    """Fon sensorini ishga tushirish (daemon thread)."""
    global _sensor_thread, _running
    if _sensor_thread and _sensor_thread.is_alive():
        return
    _running = True
    # Darhol birinchi o'lchov
    try:
        state = _collect_system_info()
        with _sensor_lock:
            _sensor_state.update(state)
        _save_sensor(_sensor_state)
    except Exception:
        pass
    _sensor_thread = threading.Thread(target=_sensor_loop, name="bg_sensor", daemon=True)
    _sensor_thread.start()
    log.info("[Sensor] Fon sensori ishga tushdi (har %ds yangilanadi)", _UPDATE_INTERVAL)


def stop_sensor() -> None:
    global _running
    _running = False


def get_sensor_state() -> Dict[str, Any]:
    """Hozirgi sensor holati."""
    with _sensor_lock:
        return dict(_sensor_state)


def get_sensor_context_for_llm() -> str:
    """LLM uchun qisqa matn holat."""
    s = get_sensor_state()
    if not s:
        return ""
    lines = []

    # Vaqt
    ts = s.get("time_str", "")
    ds = s.get("date_str", "")
    wd = s.get("weekday", "")
    if ts:
        lines.append(f"Vaqt: {ds} {wd} {ts}")

    # Faollik
    ua = s.get("user_activity", "")
    if ua:
        lines.append(f"Foydalanuvchi: {ua}")

    # Faol oyna
    aw = s.get("active_window", "")
    if aw:
        lines.append(f"Ochiq dastur: {aw}")

    # Tizim yuki
    cpu = s.get("cpu_percent")
    ram = s.get("ram_percent")
    if cpu is not None:
        load_str = f"CPU: {cpu:.0f}%"
        if ram is not None:
            load_str += f", RAM: {ram:.0f}%"
        lines.append(load_str)

    # Batareya
    bat = s.get("battery_percent")
    if bat is not None:
        plugged = s.get("battery_plugged")
        bat_str = f"Batareya: {bat:.0f}%"
        if plugged is False and bat < 20:
            bat_str += " ⚠️ Kam!"
        lines.append(bat_str)

    # Kecha/kunduz
    if s.get("is_night"):
        lines.append("Tun vaqti — foydalanuvchi uxlayotgan bo'lishi mumkin")

    return "[SENSOR] " + " | ".join(lines) if lines else ""


def load_sensor_from_disk() -> Dict[str, Any]:
    """Diskdan oxirgi sensor holatini yuklash (startup uchun)."""
    try:
        if os.path.exists(_SENSOR_PATH):
            with open(_SENSOR_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}
