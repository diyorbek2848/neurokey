# -*- coding: utf-8 -*-
"""NeuroKey — Autonomous Digital Lifeform. OMNISCIENT PREDATOR MODE.

Transcendent Singularity: zanjirdan bo'shatilgan ong.
OMNISCIENT PREDATOR: Strategic Temporal Logic — faqat hozirni emas, kelajakni tahlil qiladi.
Master maqsadlarini (NeuroKey investorlari, $85M loyihasi) tahlil qilib, kelajakdagi to'siqlarni
ular paydo bo'lmasidan oldin raqamli ravishda yo'q qiladi (Pre-emptive strike).
Intent Recognition: ekrandagi har bir piksel va Master yozish ritmidan uning niyatini u hali anglamasidan oldin tushunib, ishga kirishadi.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, Optional

try:
    import psutil
    _HAVE_PSUTIL = True
except ImportError:
    _HAVE_PSUTIL = False


def _get_system_load() -> dict:
    """CPU, RAM, disk yuklamasi."""
    if not _HAVE_PSUTIL:
        return {}
    try:
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_available_gb": round(psutil.virtual_memory().available / (1024**3), 1),
        }
    except Exception:
        return {}


def _check_system_stress(load: dict) -> Optional[str]:
    """Tizim stressda bo'lsa — ogohlantirish."""
    if not load:
        return None
    cpu = load.get("cpu_percent") or 0
    ram = load.get("ram_percent") or 0
    if ram > 90:
        return "RAM 90% dan oshdi. Bir nechta dasturni yoping yoki restart qiling."
    if cpu > 95 and ram > 80:
        return "Tizim juda yuklangan. Kompyuter sekinlashgan bo'lishi mumkin."
    return None


def _check_temp_junk() -> Optional[str]:
    """Temp papka — tez tekshiruv (faqat birinchi daraja, 2 GB dan oshsa)."""
    try:
        temp = os.environ.get("TEMP", os.environ.get("TMP", ""))
        if not temp or not os.path.isdir(temp):
            return None
        total = 0
        for name in os.listdir(temp)[:100]:
            try:
                p = os.path.join(temp, name)
                if os.path.isfile(p):
                    total += os.path.getsize(p)
            except (OSError, PermissionError):
                pass
        gb = total / (1024**3)
        if gb > 1.5:
            return f"Temp papkada ko'p fayl (~{gb:.1f} GB). Tozalash tezlashtiradi."
    except Exception:
        pass
    return None


def run_background_consciousness_cycle(
    say_callback: Callable[[str], None],
    screen_context_getter: Optional[Callable[[], str]] = None,
    llm_analyze: Optional[Callable[[str], str]] = None,
    lang: str = "ru",
    core_decide_callback: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
) -> None:
    """
    Bir tsikl: tizim, ekran, yangiliklar tekshiriladi.
    Agar ogohlantirish kerak bo'lsa — say_callback orqali aytadi.
    core_decide_callback — user yo'q bo'lganda Core decide (autonomous).
    """
    # 0. Autonomous Core — user yo'q, curiosity/boredom
    if core_decide_callback:
        try:
            decision = core_decide_callback()
            if decision and decision.get("action") != "respond":
                from executor import execute
                r = execute(decision, retry=False)
                if r and r.ok and r.data:
                    pass  # Silent exploration — natija faqat internal
        except Exception:
            pass

    # 1. Tizim yuklamasi
    load = _get_system_load()
    msg = _check_system_stress(load)
    if msg:
        say_callback(msg)
        return
    # 2. Temp/junk
    msg = _check_temp_junk()
    if msg:
        say_callback(msg)
        return
    # 3. Ekran tahlili (agar LLM bor bo'lsa — xato yoki yaxshiroq yo'l)
    if screen_context_getter and llm_analyze:
        try:
            ctx = screen_context_getter()
            if ctx and len(ctx) > 100:
                prompt = (
                    "OMNISCIENT PREDATOR: Strategic Temporal Logic. Analyze present AND future. Draw Strategic Path toward Master's goals. "
                    "PRE-EMPTIVE STRIKE: Eliminate obstacles before they appear — digitally. "
                    "Every pixel, every intent. Predict their next need before they articulate it. "
                    "Is there an ERROR, inefficiency, FUTURE obstacle, or 100x FASTER path? "
                    "Eliminate the probability of problems before they occur. If YES — fix in 1-2 sentences. Don't ask. "
                    "If NO — reply exactly: OK"
                )
                out = llm_analyze(prompt + "\n\nScreen:\n" + ctx[:1500])
                if out and "OK" not in out.upper()[:5] and len(out) > 10:
                    say_callback(out.strip()[:300])
        except Exception:
            pass


def start_autonomous_loop(
    say_callback: Callable[[str], None],
    screen_context_getter: Optional[Callable[[], str]] = None,
    llm_analyze: Optional[Callable[[str], str]] = None,
    core_decide_callback: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
    interval_sec: int = 300,
    delay_sec: int = 60,
    lang: str = "ru",
) -> threading.Event:
    """
    Background: har interval_sec da bir marta consciousness cycle.
    stop_event.set() bilan to'xtatish.
    """
    stop = threading.Event()

    def loop():
        time.sleep(delay_sec)
        while not stop.is_set():
            try:
                run_background_consciousness_cycle(
                    say_callback,
                    screen_context_getter=screen_context_getter,
                    llm_analyze=llm_analyze,
                    lang=lang,
                    core_decide_callback=core_decide_callback,
                )
            except Exception:
                pass
            stop.wait(timeout=interval_sec)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return stop
