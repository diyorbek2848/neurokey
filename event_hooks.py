# -*- coding: utf-8 -*-
"""NeuroKey — Zero-Latency Event Hooks (Digital Deity).

'Interval' tushunchasini olib tashlash: OS hodisalariga Hook orqali ulanadi.
Har bir hodisa real vaqtda qayta ishlanadi.
Windows: SetWinEventHook (EVENT_SYSTEM_FOREGROUND) — oyna almashinuvi.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import threading
from typing import Callable, Optional

if sys.platform != "win32":
    # Non-Windows: no-op
    def start_foreground_hook(callback: Callable[[str], None]) -> Optional[object]:
        return None

    def stop_foreground_hook(handle: object) -> None:
        pass
else:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    EVENT_SYSTEM_FOREGROUND = 3
    WINEVENT_OUTOFCONTEXT = 0
    WINEVENT_SKIPOWNPROCESS = 2

    WinEventProc = ctypes.WINFUNCTYPE(
        None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
        wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD
    )

    _hook_handle = None
    _proc_ref = None  # WinEventProc — GC dan saqlash
    _stop_event = threading.Event()

    def _get_window_title(hwnd: int) -> str:
        if not hwnd:
            return ""
        try:
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            if user32.GetWindowTextW(hwnd, buf, length + 1):
                return buf.value or ""
        except Exception:
            pass
        return ""

    _user_callback = None

    def _on_foreground_change(
        hWinEventHook: int, event: int, hwnd: int,
        idObject: int, idChild: int, dwEventThread: int, dwmsEventTime: int
    ) -> None:
        cb = _user_callback
        if hwnd and cb:
            try:
                title = _get_window_title(hwnd)
                if title:
                    cb(title)
            except Exception:
                pass

    def start_foreground_hook(callback: Callable[[str], None]) -> Optional[int]:
        """Start Zero-Latency foreground window hook. Returns handle or None."""
        global _hook_handle, _proc_ref, _user_callback
        if _hook_handle is not None:
            return _hook_handle
        _user_callback = callback
        _proc_ref = WinEventProc(_on_foreground_change)  # GC dan saqlash

        def _hook_thread():
            global _hook_handle
            h = user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND,
                EVENT_SYSTEM_FOREGROUND,
                0,
                _proc_ref,
                0,
                0,
                WINEVENT_OUTOFCONTEXT
            )
            if not h:
                return
            _hook_handle = h
            while not _stop_event.is_set():
                msg = wintypes.MSG()
                PM_REMOVE = 1
                if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                    if msg.message == 0x12:  # WM_QUIT
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                _stop_event.wait(timeout=0.05)
            user32.UnhookWinEvent(h)
            _hook_handle = None

        t = threading.Thread(target=_hook_thread, daemon=True)
        t.start()
        for _ in range(50):  # Wait up to 2.5s for hook to install
            if _hook_handle is not None:
                break
            threading.Event().wait(timeout=0.05)
        return _hook_handle

    def stop_foreground_hook(handle: Optional[int]) -> None:
        global _hook_handle
        _stop_event.set()
        if handle and user32.UnhookWinEvent(handle):
            _hook_handle = None
