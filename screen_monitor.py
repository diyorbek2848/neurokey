# -*- coding: utf-8 -*-
"""NeuroKey — Doimiy ekran monitoring. M2 + M3 + M7.

Doimiy ko'rish, to'g'ri oyna holati (minimized ajratish), video tahlil.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import mss
    _HAVE_MSS = True
except ImportError:
    mss = None
    _HAVE_MSS = False

try:
    import cv2
    _HAVE_CV2 = True
except ImportError:
    cv2 = None
    _HAVE_CV2 = False

try:
    import win32gui
    import win32con
    _HAVE_WIN32 = True
except ImportError:
    win32gui = None
    win32con = None
    _HAVE_WIN32 = False


class ScreenMonitor:
    """
    Doimiy ekran monitoring.
    OLDIN: Savol kelsa → screenshot → tahlil.
    KEYIN: Doim ko'radi → har 0.5s yangilanadi → savol kelsa tayyor tahlil.
    """

    def __init__(self, capture_interval: float = 0.5, change_threshold: float = 0.05):
        self.current_frame: Optional[np.ndarray] = None
        self.previous_frame: Optional[np.ndarray] = None
        self.frame_analysis: Dict[str, Any] = {}
        self.is_running = False
        self.capture_interval = capture_interval
        self.change_threshold = change_threshold
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.sct = mss.mss() if _HAVE_MSS and mss else None

    def start_continuous_monitoring(self) -> None:
        """Background thread da doimiy ishlaydi."""
        if self.is_running:
            return
        self.is_running = True
        self._monitor_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="ScreenMonitor",
        )
        self._monitor_thread.start()

    def stop(self) -> None:
        """Monitoring to'xtatish."""
        self.is_running = False

    def _capture_loop(self) -> None:
        """Doimiy ekran yozib olish."""
        while self.is_running:
            try:
                frame = self._capture_screen()
                if frame is not None:
                    with self._lock:
                        change = self._detect_change(self.current_frame, frame)
                        if change > self.change_threshold:
                            self.frame_analysis["last_change"] = time.time()
                        self.previous_frame = self.current_frame
                        self.current_frame = frame
            except Exception:
                pass
            time.sleep(self.capture_interval)

    def _capture_screen(self) -> Optional[np.ndarray]:
        """mss bilan ekran rasmi."""
        if not self.sct or not _HAVE_MSS:
            return None
        try:
            monitor = self.sct.monitors[1]
            img = self.sct.grab(monitor)
            arr = np.array(img)
            if len(arr.shape) == 3:
                return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR) if _HAVE_CV2 and cv2 else arr
            return arr
        except Exception:
            return None

    def get_true_window_state(self) -> Dict[str, Any]:
        """
        M3: Minimized oynalarni to'g'ri aniqlash.
        visible_windows = ekranda KO'RINADIGAN
        minimized_windows = MINIMIZED (ekranda yo'q)
        """
        if not _HAVE_WIN32 or not win32gui:
            return {
                "visible_windows": [],
                "minimized_windows": [],
                "foreground": "",
                "desktop_only": True,
                "total_open": 0,
            }
        visible: List[str] = []
        minimized: List[str] = []
        foreground_name = ""
        fg_hwnd = win32gui.GetForegroundWindow()

        def enum_cb(hwnd, _):
            nonlocal foreground_name
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                title = win32gui.GetWindowText(hwnd)
                if not title or not title.strip():
                    return True
                if win32gui.IsIconic(hwnd):
                    minimized.append(title)
                else:
                    visible.append(title)
                if hwnd == fg_hwnd:
                    foreground_name = title
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass
        desktop_only = foreground_name in ("", "Program Manager", "Рабочий стол")
        return {
            "visible_windows": visible,
            "minimized_windows": minimized,
            "foreground": foreground_name,
            "desktop_only": desktop_only,
            "total_open": len(visible) + len(minimized),
        }

    def get_screen_for_llm(self, quality: str = "fast") -> str:
        """
        Hozirgi ekranni LLM ga yuborish uchun base64.
        quality: fast (640x360, 60%) | normal | full
        """
        with self._lock:
            frame = self.current_frame
        if frame is None:
            frame = self._capture_screen()
        if frame is None:
            return ""
        if not _HAVE_CV2 or not cv2:
            return ""
        try:
            if quality == "fast":
                frame = cv2.resize(frame, (640, 360))
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            elif quality == "normal":
                frame = cv2.resize(frame, (1280, 720))
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            else:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return base64.b64encode(buf.tobytes()).decode("utf-8")
        except Exception:
            return ""

    def _detect_change(self, prev: Optional[np.ndarray], curr: Optional[np.ndarray]) -> float:
        """Ikki kadr orasidagi farq 0.0–1.0."""
        if prev is None or curr is None:
            return 1.0
        if not _HAVE_CV2 or not cv2:
            return 0.0
        try:
            if prev.shape != curr.shape:
                return 1.0
            diff = cv2.absdiff(prev, curr)
            return float(diff.mean()) / 255.0
        except Exception:
            return 0.0

    def get_context_summary(self) -> str:
        """LLM uchun qisqa kontekst — oyna holati + tayyor frame bor."""
        ws = self.get_true_window_state()
        parts = []
        if ws.get("desktop_only"):
            parts.append("На экране только рабочий стол, открытых окон нет.")
        else:
            vis = ws.get("visible_windows", [])
            min_w = ws.get("minimized_windows", [])
            fg = ws.get("foreground", "")
            if fg:
                parts.append(f"Активное окно: {fg}")
            if vis:
                parts.append(f"Видимые окна: {', '.join(vis[:8])}")
            if min_w:
                parts.append(f"Свёрнуты (не на экране): {', '.join(min_w[:5])}")
        return " ".join(parts) if parts else "Состояние экрана неизвестно."

    async def analyze_with_vision(self, question: Optional[str] = None) -> str:
        """
        LLM Vision API bilan tahlil.
        current_frame allaqachon tayyor — tez.
        """
        ctx = self.get_context_summary()
        try:
            from screen_vision import get_screen_context_safe, get_screen_full_analysis
            ocr_txt, vision_txt = get_screen_context_safe()
            parts = [ctx]
            if vision_txt:
                parts.append(vision_txt)
            if ocr_txt:
                parts.append(f"OCR: {ocr_txt[:500]}")
            return "\n".join(parts).strip() or ctx
        except Exception:
            return ctx

    async def analyze_video_stream(self, duration_seconds: int = 5) -> str:
        """
        M7: Video tahlil — kadrlar ketma-ketligi.
        """
        frames: List[np.ndarray] = []
        seen_hashes: set = set()
        start = time.time()
        while time.time() - start < duration_seconds:
            frame = self._capture_screen()
            if frame is not None:
                h = hashlib.md5(frame.tobytes()[::100]).hexdigest()
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    if _HAVE_CV2 and cv2:
                        small = cv2.resize(frame, (320, 180))
                        frames.append(small)
            await asyncio.sleep(0.5)
        if not frames:
            return "Ekranda o'zgarish ko'rinmadi."
        try:
            from screen_vision import get_screen_full_analysis
            return get_screen_full_analysis() or "Tahlil mavjud emas."
        except Exception:
            return "Video tahlil xato."


def get_screen_complexity() -> float:
    """
    Ekran murakkabligini 0-1 da qaytaradi.
    Piksel o'zgarishi + aktiv oynalar soni asosida.
    """
    try:
        monitor = get_screen_monitor()
        ws = monitor.get_true_window_state()
        active = len(ws.get("visible_windows", [])) + len(ws.get("minimized_windows", []))
        base = min(1.0, active / 10.0)
        if monitor.frame_analysis:
            last_change = monitor.frame_analysis.get("last_change", 0)
            if last_change and (time.time() - last_change) < 2:
                base = min(1.0, base + 0.2)
        return base
    except Exception:
        return 0.0


def get_motion_level() -> float:
    """
    Ekrandagi harakat darajasi (0-1).
    Video ko'rilayaptimi, animatsiya bormi.
    """
    try:
        monitor = get_screen_monitor()
        if monitor.frame_analysis:
            last_change = monitor.frame_analysis.get("last_change", 0)
            if last_change and (time.time() - last_change) < 1:
                return 0.8
        return 0.0
    except Exception:
        return 0.0


_monitor: Optional[ScreenMonitor] = None


def get_screen_monitor() -> ScreenMonitor:
    """Singleton."""
    global _monitor
    if _monitor is None:
        _monitor = ScreenMonitor()
    return _monitor
