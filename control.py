# -*- coding: utf-8 -*-
"""NeuroKey Control — Windows ustidan 100% nazorat (Superuser darajasida).

NeuroKey kompyuter ichida yashaydi — hamma dasturlar ustidan hukmron.
Ochish, yopish, buyruq ishga tushirish, papka/fayl, oyna, klaviatura, sichqoncha.
DIGITAL SHIELD: Foydalanuvchiga ziyon yetkazish dastur darajasida imkonsiz.
Safety: explorer.exe hech qachon o'chirilmaydi. BLOCKED_IMAGES, ALLOWED_CLOSE_IMAGES.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import ctypes
from ctypes import wintypes
from datetime import datetime
from typing import Optional, Tuple, List

# Config (lazy to avoid circular import)
def _control_cfg(name: str, default):
    try:
        import config as _cfg
        return getattr(_cfg, name, default)
    except Exception:
        return default


def _msg(en: str, ru: str = "") -> str:
    """NeuroKey — ТОЛЬКО РУССКИЙ. Все сообщения пользователю на русском."""
    return (ru or en)


def _supercontrol_enabled() -> bool:
    """Unsafe-less mode for trusted owner machine control."""
    v = (os.getenv("NEUROKEY_SUPERCONTROL", "0") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")

# ---------- Safety: never taskkill these (system / shell) ----------
BLOCKED_IMAGES = frozenset({
    "explorer.exe", "taskkill.exe", "cmd.exe", "conhost.exe",
    "csrss.exe", "winlogon.exe", "dwm.exe", "sihost.exe", "runtimebroker.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "systemsettings.exe",
    "searchhost.exe", "textinputhost.exe", "applicationframehost.exe",
})
# Apps that are allowed to be closed (strict whitelist)
ALLOWED_CLOSE_IMAGES = frozenset({
    "Telegram.exe", "opera.exe", "chrome.exe", "msedge.exe", "firefox.exe",
    "CalculatorApp.exe", "WinStore.App.exe", "Code.exe", "notepad.exe",
    "Spotify.exe", "Discord.exe", "slack.exe", "Teams.exe", "zoom.exe",
})


def _control_log(action: str, detail: str = "", success: bool = True) -> None:
    """Append one line to control.log if config sets CONTROL_LOG_PATH."""
    try:
        from importlib import import_module
        cfg = import_module("config")
        path = getattr(cfg, "CONTROL_LOG_PATH", None) if cfg else None
        if not path:
            return
        msg = f"{datetime.now().isoformat()} | {action} | {detail} | ok={success}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass


def _run(cmd: str, timeout_sec: float = 3.0) -> Tuple[int, str]:
    """Run command; on Windows use CREATE_NO_WINDOW for speed and no console flash."""
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        p = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout_sec, creationflags=creationflags
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return -1, "Timeout"
    except Exception:
        p = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout_sec,
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out


def _run_start(cmd: str) -> Tuple[int, str]:
    """start buyrug'i uchun — Popen, darhol qaytadi, bolani kutmaydi."""
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
        return 0, ""
    except Exception as e:
        return -1, str(e)


# ---------- Tasklist cache (tezroq, bir necha marta chaqirilsa) ----------
_tasklist_cache: Tuple[float, str] = (0.0, "")
_exe_cache: dict = {}
_exe_cache_lock = threading.Lock()
def _tasklist_cached() -> str:
    global _tasklist_cache
    ttl = _control_cfg("CONTROL_TASKLIST_CACHE_SEC", 0.3)
    now = time.perf_counter()
    if now - _tasklist_cache[0] <= ttl and _tasklist_cache[1]:
        return _tasklist_cache[1]
    _, out = _run("tasklist /NH /FO CSV", timeout_sec=4.0)
    _tasklist_cache = (now, out)
    return out


def _cache_get_exe(name: str) -> Optional[str]:
    """Fast cache for executable resolution."""
    key = (name or "").strip().lower()
    if not key:
        return None
    ttl = float(_control_cfg("CONTROL_EXE_CACHE_SEC", 600.0))
    now = time.perf_counter()
    with _exe_cache_lock:
        item = _exe_cache.get(key)
        if not item:
            return None
        ts, val = item
        if now - ts <= ttl and val and os.path.isfile(val):
            return val
        if now - ts <= ttl and val is None:
            return None
        _exe_cache.pop(key, None)
    return None


def _cache_set_exe(name: str, value: Optional[str]) -> None:
    key = (name or "").strip().lower()
    if not key:
        return
    with _exe_cache_lock:
        _exe_cache[key] = (time.perf_counter(), value)


def _bring_process_windows_to_front(process_name: str) -> bool:
    """Ochilgan dastur oynasini oldinga olib chiqish. Title bo'lmasa ham oyna qo'shiladi; SW_RESTORE minimize bo'lsa."""
    try:
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        name_lower = (process_name or "").strip().lower()
        if not name_lower.endswith(".exe"):
            name_lower += ".exe"
        out = _tasklist_cached()
        target_pids = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip('"') for p in line.split(",")]
            if len(parts) >= 2 and parts[0].lower() == name_lower:
                try:
                    target_pids.append(int(parts[1]))
                except ValueError:
                    pass
        if not target_pids:
            return False
        target_set = frozenset(target_pids)
        candidates: List[Tuple[int, int]] = []  # (title_len, hwnd) — title uzunroq = asosiy oyna

        def enum_cb(hwnd: int, _: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in target_set:
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            candidates.append((length, hwnd))
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        if not candidates:
            return False
        candidates.sort(key=lambda x: -x[0])
        best_hwnd = candidates[0][1]
        fore = user32.GetForegroundWindow()
        _dummy = wintypes.DWORD()
        fore_tid = user32.GetWindowThreadProcessId(fore, ctypes.byref(_dummy))
        our_tid = user32.GetWindowThreadProcessId(best_hwnd, ctypes.byref(_dummy))
        if fore_tid != our_tid:
            user32.AttachThreadInput(fore_tid, our_tid, True)
        try:
            user32.ShowWindow(best_hwnd, SW_RESTORE)
            user32.BringWindowToTop(best_hwnd)
            user32.SetForegroundWindow(best_hwnd)
            user32.SetActiveWindow(best_hwnd)
        finally:
            if fore_tid != our_tid:
                user32.AttachThreadInput(fore_tid, our_tid, False)
        return True
    except Exception:
        pass
    return False


def restart_explorer() -> Tuple[bool, str]:
    """Start explorer.exe if not running (recovery after crash). Safe to call anytime."""
    if is_process_running("explorer.exe"):
        return True, "Explorer already running."
    _control_log("restart_explorer", "starting", success=True)
    try:
        code, _ = _run("start explorer")
        if code == 0:
            return True, "Explorer started."
        return False, "Failed to start explorer."
    except Exception as e:
        _control_log("restart_explorer_error", str(e), success=False)
        return False, str(e)


def _tasklist() -> str:
    return _tasklist_cached() or _run("tasklist", timeout_sec=4.0)[1]


def is_process_running(image_name: str) -> bool:
    if not image_name:
        return False
    tl = _tasklist_cached().lower()
    if not tl:
        _, tl = _run("tasklist", timeout_sec=4.0)
        tl = tl.lower()
    return image_name.lower() in tl


def _find_opera_gx_launcher() -> Optional[str]:
    """Opera GX, Opera, Chrome, Edge — birinchi topilganini qaytaradi."""
    manual = (os.environ.get("NEUROKEY_BROWSER_PATH") or "").strip()
    if manual and os.path.exists(manual):
        return manual
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    candidates = []
    if local:
        candidates.extend([
            os.path.join(local, "Programs", "Opera GX", "launcher.exe"),
            os.path.join(local, "Programs", "Opera GX", "opera.exe"),
            os.path.join(local, "Programs", "Opera", "launcher.exe"),
            os.path.join(local, "Programs", "Opera", "opera.exe"),
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe"),
        ])
    if pf:
        candidates.extend([
            os.path.join(pf, "Opera GX", "launcher.exe"),
            os.path.join(pf, "Opera GX", "opera.exe"),
            os.path.join(pf, "Opera", "launcher.exe"),
            os.path.join(pf, "Opera", "opera.exe"),
            os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        ])
    if pf86:
        candidates.extend([
            os.path.join(pf86, "Opera GX", "launcher.exe"),
            os.path.join(pf86, "Opera", "opera.exe"),
            os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
        ])
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def open_browser(opera_gx_path: str = "") -> Tuple[bool, str]:
    path = opera_gx_path.strip() if opera_gx_path else ""
    if path and not os.path.exists(path):
        return False, f"Не нашёл Opera GX по пути: {path}"
    if not path:
        path = _find_opera_gx_launcher() or ""
    if path:
        code, _ = _run_start(f'start "" "{path}"')
        if code == 0:
            return True, _msg("Opened browser.", "Открыл браузер.")
        try:
            subprocess.Popen([path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, _msg("Opened browser.", "Открыл браузер.")
        except Exception as e:
            return False, f"Не смог запустить: {e}"
    for url in ("https://www.google.com", "about:blank"):
        code, _ = _run_start(f'start "" "{url}"')
        if code == 0:
            _defer_bring_browser_to_front()
            return True, _msg("Opened default browser.", "Открыл браузер.")
    return False, _msg("Could not open browser.", "Не удалось открыть браузер.")


def open_url(url: str, opera_gx_path: str = "", bring_to_front: bool = True) -> Tuple[bool, str]:
    """Открыть URL в браузере. bring_to_front=True — результат виден на экране."""
    url = (url or "").strip()
    if not url:
        return False, "Пустой URL."
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    path = opera_gx_path.strip() if opera_gx_path else ""
    if path and os.path.exists(path):
        code, _ = _run_start(f'start "" "{path}" "{url}"')
        if code == 0:
            if bring_to_front:
                _defer_bring_browser_to_front()
            return True, f"Opened: {url}"
    code, _ = _run_start(f'start "" "{url}"')
    if code == 0:
        if bring_to_front:
            _defer_bring_browser_to_front()
        return True, f"Opened: {url}"
    return False, _msg(f"Could not open: {url}", f"Не удалось открыть: {url}")


def _find_telegram_desktop() -> Optional[str]:
    """Telegram Desktop exe ni topish (barcha standart yo‘llar)."""
    appdata = os.environ.get("APPDATA", "")
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    candidates = []
    if appdata:
        candidates.append(os.path.join(appdata, "Telegram Desktop", "Telegram.exe"))
    if local:
        candidates.extend([
            os.path.join(local, "Telegram Desktop", "Telegram.exe"),
            os.path.join(local, "Programs", "Telegram Desktop", "Telegram.exe"),
        ])
    if pf:
        candidates.append(os.path.join(pf, "Telegram Desktop", "Telegram.exe"))
    if pf86:
        candidates.append(os.path.join(pf86, "Telegram Desktop", "Telegram.exe"))
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _find_exe_in_paths(name: str) -> Optional[str]:
    """Program Files, PATH, LocalAppData da name.exe qidirish. Har qanday dastur.
    Tez: 1) where.exe  2) LocalAppData\\Programs  3) Program Files (cheklangan)"""
    if not name or len(name) < 2:
        return None
    base = name.strip().replace(".exe", "")
    cached = _cache_get_exe(base)
    if cached is not None:
        return cached

    # 1. PATH + App Paths registri (juda tez — bu eng yaxshi usul)
    try:
        code, out = _run("where " + base, timeout_sec=2)
        if code == 0 and out.strip():
            for line in out.strip().splitlines():
                p = line.strip()
                if p and os.path.isfile(p):
                    _cache_set_exe(base, p)
                    return p
    except Exception:
        pass

    # 2. PowerShell Get-Command (PATH dan ham qidiradi, WindowsApps ham)
    try:
        ps_cmd = f'powershell -NoProfile -Command "(Get-Command {base} -ErrorAction SilentlyContinue).Source"'
        code2, out2 = _run(ps_cmd, timeout_sec=3)
        if code2 == 0 and out2.strip():
            p2 = out2.strip().splitlines()[0].strip()
            if p2 and os.path.isfile(p2):
                _cache_set_exe(base, p2)
                return p2
    except Exception:
        pass

    if sys.platform != "win32":
        return None

    # 3. LocalAppData\Programs — VS Code, Cursor, GitHub Desktop, Slack va boshqalar
    local_app = os.environ.get("LOCALAPPDATA", "")
    for ldir in [os.path.join(local_app, "Programs"), local_app]:
        if not ldir or not os.path.isdir(ldir):
            continue
        try:
            for d1 in os.listdir(ldir)[:60]:
                p1 = os.path.join(ldir, d1)
                if not os.path.isdir(p1):
                    continue
                exe_path = os.path.join(p1, base + ".exe")
                if os.path.isfile(exe_path):
                    _cache_set_exe(base, exe_path)
                    return exe_path
                # 1 daraja chuqur
                try:
                    for d2 in os.listdir(p1)[:10]:
                        p2 = os.path.join(p1, d2)
                        if os.path.isdir(p2):
                            ep2 = os.path.join(p2, base + ".exe")
                            if os.path.isfile(ep2):
                                _cache_set_exe(base, ep2)
                                return ep2
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass

    # 4. Program Files — faqat 2 daraja, CHEKLANGAN (sekin — eng oxirgi)
    for pf in [os.environ.get("ProgramFiles", "C:\\Program Files"),
               os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")]:
        if not pf or not os.path.isdir(pf):
            continue
        try:
            for d1 in os.listdir(pf)[:50]:  # 80 dan 50 ga kamaytirdik
                p1 = os.path.join(pf, d1)
                if not os.path.isdir(p1):
                    continue
                exe_path = os.path.join(p1, base + ".exe")
                if os.path.isfile(exe_path):
                    _cache_set_exe(base, exe_path)
                    return exe_path
                for d2 in os.listdir(p1)[:10]:  # 20 dan 10 ga kamaytirdik
                    p2 = os.path.join(p1, d2)
                    if os.path.isdir(p2):
                        exe_path = os.path.join(p2, base + ".exe")
                        if os.path.isfile(exe_path):
                            _cache_set_exe(base, exe_path)
                            return exe_path
        except (OSError, PermissionError):
            pass
    _cache_set_exe(base, None)
    return None


def _open_app_generic(app: str, a: str) -> Tuple[bool, str]:
    """Kod ichiga yozilmagan dasturlarni ochish. Windows start, Program Files, PATH."""
    if not a:
        return False, _msg("Specify app name.", "Укажи имя приложения.")
    # To'liq path — fayl mavjud
    if os.path.isfile(app.strip()):
        code, _ = _run_start(f'start "" "{app.strip()}"')
        return (code == 0, _msg(f"Opened: {app}", f"Открыл: {app}") if code == 0 else _msg("Could not open.", "Не удалось открыть."))
    if "\\" in app or "/" in app or (len(app) > 2 and app[1] == ":"):
        path = os.path.abspath(os.path.expanduser(app.strip()))
        if os.path.isfile(path):
            code, _ = _run_start(f'start "" "{path}"')
            return (code == 0, _msg(f"Opened: {app}", f"Открыл: {app}") if code == 0 else _msg("Could not open.", "Не удалось открыть."))
    # Windows start — Start menu, App Paths, PATH qidiradi
    code, _ = _run_start(f'start "" "{app.strip()}"')
    if code == 0:
        return True, _msg(f"Opened: {app}", f"Открыл: {app}")
    # Oddiy nom: start notepad, start notepad.exe
    code, _ = _run_start(f"start {a}")
    if code == 0:
        return True, _msg(f"Opened: {app}", f"Открыл: {app}")
    # Program Files qidirish
    found = _find_exe_in_paths(a.replace(".exe", ""))
    if found:
        code, _ = _run_start(f'start "" "{found}"')
        if code == 0:
            return True, _msg(f"Opened: {app}", f"Открыл: {app}")
    return False, _msg(f"Could not find or open: {app}", f"Не удалось найти или открыть: {app}")


def open_app(app: str) -> Tuple[bool, str]:
    a = (app or "").lower().strip()
    if not a:
        return False, "Не понял, что открыть."
    _control_log("open_app", f"app={a}", success=True)
    exe_for_front = None
    if a in ("telegram", "телеграм", "tg"):
        p = _find_telegram_desktop()
        if p:
            code, _ = _run_start(f'start "" "{p}"')
            if code == 0:
                exe_for_front = "Telegram.exe"
                _defer_bring_to_front(exe_for_front)
                return True, _msg("Opened Telegram.", "Открыл Telegram.")
            try:
                subprocess.Popen([p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=os.path.dirname(p))
                exe_for_front = "Telegram.exe"
                _defer_bring_to_front(exe_for_front)
                return True, _msg("Opened Telegram.", "Открыл Telegram.")
            except Exception:
                pass
        code, _ = _run_start('start "" "telegram:"')
        if code == 0:
            _defer_bring_to_front("Telegram.exe")
            return True, _msg("Opened Telegram.", "Открыл Telegram.")
        return False, _msg("Telegram not found. Install from telegram.org.", "Telegram не найден. Установи с telegram.org.")
    if a in ("calc", "калькулятор", "calculator"):
        code, _ = _run_start("start calc")
        if code == 0:
            _defer_bring_to_front("CalculatorApp.exe")
            return True, _msg("Opened calculator.", "Открыл калькулятор.")
        return False, _msg("Could not open calculator.", "Не удалось открыть калькулятор.")
    if a in ("explorer", "проводник", "files"):
        code, _ = _run_start("start explorer")
        if code == 0:
            return True, _msg("Opened File Explorer.", "Открыл проводник.")
        return False, _msg("Could not open Explorer.", "Не удалось открыть проводник.")
    # My Computer / This PC / Mening kompyuterim
    if a in ("mycomputer", "this pc", "my computer", "mening kompyuterim", "kompyuterim", "moy kompyuter", "moy komp"):
        code, _ = _run_start('explorer "::{20D04FE0-3AEA-1069-A2D8-08002B30309D}"')
        if code == 0:
            return True, _msg("Opened My Computer.", "Открыл «Мой компьютер».")
        code, _ = _run_start("start explorer")
        return (code == 0, _msg("Opened File Explorer.", "Открыл проводник.") if code == 0 else _msg("Could not open.", "Не удалось открыть."))
    if a in ("browser", "браузер", "opera", "opera gx", "opera gtx", "operagx", "опера", "gtx"):
        ok, msg = open_browser("")
        if ok:
            _defer_bring_browser_to_front()
        return (ok, msg)
    if a in ("store", "microsoft store", "магазин", "маркет", "ms store"):
        code, _ = _run_start("start ms-windows-store:")
        if code == 0:
            return True, _msg("Opened Microsoft Store.", "Открыл Microsoft Store.")
        return False, _msg("Could not open Microsoft Store.", "Не удалось открыть Microsoft Store.")
    if a in ("notepad", "блокнот", "bloknot", "notepad++"):
        code, _ = _run_start("start notepad")
        if code == 0:
            _defer_bring_to_front("notepad.exe")
            return True, _msg("Opened Notepad.", "Открыл блокнот.")
    if a in ("vscode", "code", "vs code", "visual studio code"):
        found = _find_exe_in_paths("code")
        if found:
            code, _ = _run_start(f'start "" "{found}"')
            if code == 0:
                _defer_bring_to_front("Code.exe")
                return True, _msg("Opened VS Code.", "Открыл VS Code.")
        code, _ = _run_start("code")
        if code == 0:
            return True, _msg("Opened VS Code.", "Открыл VS Code.")
    if a in ("chrome", "хром", "google chrome"):
        code, _ = _run_start("start chrome")
        if code == 0:
            _defer_bring_to_front("chrome.exe")
            return True, _msg("Opened Chrome.", "Открыл Chrome.")
    if a in ("edge", "msedge", "microsoft edge", "эдж"):
        code, _ = _run_start("start msedge")
        if code == 0:
            _defer_bring_to_front("msedge.exe")
            return True, _msg("Opened Edge.", "Открыл Edge.")
    if a in ("spotify", "спотифай"):
        code, _ = _run_start("start spotify")
        if code == 0:
            _defer_bring_to_front("Spotify.exe")
            return True, _msg("Opened Spotify.", "Открыл Spotify.")
    if a in ("discord", "дискорд"):
        found = _find_exe_in_paths("Discord")
        if found:
            code, _ = _run_start(f'start "" "{found}"')
            if code == 0:
                _defer_bring_to_front("Discord.exe")
                return True, _msg("Opened Discord.", "Открыл Discord.")
    # Generic: har qanday dastur (config.CONTROL_OPEN_APP_GENERIC)
    if _control_cfg("CONTROL_OPEN_APP_GENERIC", True):
        return _open_app_generic(app, a)
    return False, _msg(f"App not in list: {app}", f"Приложение не в списке: {app}")


def _defer_bring_to_front(exe_name: str, delay_sec: Optional[float] = None) -> None:
    """Ochilgan dastur oynasini oldinga olib chiqish — kechikish va qayta urinish."""
    delay = delay_sec if delay_sec is not None else _control_cfg("CONTROL_BRING_TO_FRONT_DELAY_SEC", 1.2)
    retry_delay = _control_cfg("CONTROL_BRING_TO_FRONT_RETRY_SEC", 2.5)

    def _do():
        time.sleep(delay)
        if _bring_process_windows_to_front(exe_name):
            return
        time.sleep(max(0, retry_delay - delay))
        if _bring_process_windows_to_front(exe_name):
            return
        time.sleep(1.0)
        _bring_process_windows_to_front(exe_name)
    threading.Thread(target=_do, daemon=True).start()


def _defer_bring_browser_to_front() -> None:
    """Brauzer ochilganda — opera, chrome, msedge ketma-ket urinish."""
    exes = ["opera.exe", "chrome.exe", "msedge.exe"]
    delay = _control_cfg("CONTROL_BRING_TO_FRONT_DELAY_SEC", 1.2)
    retry_delay = _control_cfg("CONTROL_BRING_TO_FRONT_RETRY_SEC", 2.5)

    def _do():
        time.sleep(delay)
        for exe in exes:
            if _bring_process_windows_to_front(exe):
                return
        time.sleep(max(0, retry_delay - delay))
        for exe in exes:
            if _bring_process_windows_to_front(exe):
                return
    threading.Thread(target=_do, daemon=True).start()


def close_app(app: str) -> Tuple[bool, str]:
    a = (app or "").lower().strip()
    mapping = {
        "telegram": "Telegram.exe",
        "телеграм": "Telegram.exe",
        "tg": "Telegram.exe",
        "opera": "opera.exe",
        "opera gx": "opera.exe",
        "opera gtx": "opera.exe",
        "gtx": "opera.exe",
        "опера": "opera.exe",
        "browser": "__ALL_BROWSERS__",
        "браузер": "__ALL_BROWSERS__",
        "chrome": "chrome.exe",
        "хром": "chrome.exe",
        "edge": "msedge.exe",
        "msedge": "msedge.exe",
        "store": "WinStore.App.exe",
        "microsoft store": "WinStore.App.exe",
        "магазин": "WinStore.App.exe",
        "calc": "CalculatorApp.exe",
        "калькулятор": "CalculatorApp.exe",
        "notepad": "notepad.exe",
        "блокнот": "notepad.exe",
        "vscode": "Code.exe",
        "code": "Code.exe",
        "spotify": "Spotify.exe",
        "discord": "Discord.exe",
        # NEVER add explorer/explorer.exe — killing it breaks desktop, taskbar, Start menu
    }
    image = mapping.get(a)
    if not image:
        if a in ("explorer", "проводник", "files", "file explorer"):
            return False, "Проводник закрыть нельзя — сломается рабочий стол. Скажи «сверни все окна»."
        # Generic: har qanday dasturni nomi bo'yicha yopish
        if _control_cfg("CONTROL_OPEN_APP_GENERIC", True):
            return close_app_generic(a)
        return False, "Не понял, что закрыть."
    if image == "__ALL_BROWSERS__":
        # Ultra-fast close: javobni ushlamasdan fon rejimida yopamiz.
        def _kill_browsers_bg():
            _run('taskkill /F /IM "msedge.exe" /IM "chrome.exe" /IM "firefox.exe" /IM "opera.exe"', timeout_sec=2.5)
        threading.Thread(target=_kill_browsers_bg, daemon=True).start()
        return True, "Закрываю браузер."
    if image in BLOCKED_IMAGES:
        _control_log("close_app_blocked", f"app={app} image={image}", success=False)
        return False, "Это приложение нельзя закрыть — системная безопасность."
    try:
        safe_mode = False
        try:
            import config as _cfg
            safe_mode = getattr(_cfg, "CONTROL_SAFE_MODE", True)
        except Exception:
            safe_mode = True
        if _supercontrol_enabled():
            safe_mode = False
        if safe_mode and image not in ALLOWED_CLOSE_IMAGES:
            _control_log("close_app_blocked_safe", f"app={app} image={image}", success=False)
            return False, "Это приложение не в списке разрешённых к закрытию."
    except Exception:
        pass
    _control_log("close_app", f"app={app} image={image}", success=True)
    try:
        code, out = _run(f'taskkill /IM "{image}" /F')
        if code == 0:
            return True, f"Закрыл {app}."
        if not is_process_running(image):
            return True, f"{app} уже закрыт."
        return False, f"Не смог закрыть {app}."
    except Exception as e:
        _control_log("close_app_error", f"app={app} {e}", success=False)
        return False, f"Error: {e}"


def close_all_apps() -> Tuple[bool, str]:
    """Close allowed apps only. NEVER includes explorer.exe (would break desktop)."""
    allowed = [e for e in ("Telegram.exe", "opera.exe", "chrome.exe", "msedge.exe", "CalculatorApp.exe") if e not in BLOCKED_IMAGES]
    closed = []
    _control_log("close_all_apps", "start", success=True)
    try:
        for exe in allowed:
            if is_process_running(exe):
                code, _ = _run(f'taskkill /IM "{exe}" /F')
                if code == 0:
                    closed.append(exe.replace(".exe", ""))
        if closed:
            return True, "Закрыл: " + ", ".join(closed) + "."
        return True, "Все приложения уже закрыты."
    except Exception as e:
        _control_log("close_all_apps_error", str(e), success=False)
        return False, str(e)


def search_folders(query: str, limit: int = 15) -> Tuple[bool, str]:
    """Papka nomi bo'yicha qidirish — user home, Desktop, Documents, C:\\."""
    query = (query or "").strip().lower()
    if not query:
        return False, "Укажи, какую папку искать."
    user = os.path.expanduser("~")
    found = []
    roots = [user, os.path.join(user, "Desktop"), os.path.join(user, "Documents"),
             os.path.join(user, "Downloads"), "C:\\"]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for item in os.listdir(root):
                if query in item.lower() and os.path.isdir(os.path.join(root, item)):
                    found.append(os.path.join(root, item))
                    if len(found) >= limit:
                        break
        except (OSError, PermissionError):
            pass
        if len(found) >= limit:
            break
    if not found:
        return True, f"Папок по запросу «{query}» не найдено."
    lines = found[:limit]
    return True, "Найдено:\n" + "\n".join(lines)


def search_files(folder: str, query: str, limit: int = 20) -> Tuple[bool, str]:
    """Papkada fayl qidirish (Windows: dir /s /b).
    DIQQAT: C:\\ berilsa avtomatik user home ga o'tiladi — C:\\ juda sekin."""
    folder = (folder or "").strip() or os.path.expanduser("~")
    query = (query or "").strip()
    if not query:
        return False, "Укажи, что искать."
    # C:\ yoki C:/ berilsa — foydalanuvchi home papkasiga cheklaymiz (C:\ juda sekin)
    folder_norm = folder.rstrip("\\/").lower()
    if folder_norm in ("c:", "c:\\", "c:/", "/"):
        folder = os.path.expanduser("~")
    if not os.path.isdir(folder):
        return False, f"Папка не найдена: {folder}"
    try:
        # Windows: dir /s /b | findstr — 8 soniya timeout (yetarli)
        q_esc = query.replace('"', "").strip()
        code, out = _run(f'cd /d "{folder}" && dir /s /b 2>nul | findstr /i "{q_esc}"',
                         timeout_sec=8.0)
        lines = [l.strip() for l in out.splitlines() if l.strip()][:limit]
        if not lines:
            return True, f"По запросу «{query}» ничего не найдено в {folder}."
        return True, "Найдено:\n" + "\n".join(lines[:15])
    except Exception as e:
        return False, str(e)


def open_file(path: str) -> Tuple[bool, str]:
    """Faylni default dastur bilan ochish."""
    path = (path or "").strip()
    if not path:
        return False, "Укажи путь к файлу."
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path):
        return False, f"Файл не найден: {path}"
    try:
        os.startfile(path)
        return True, f"Открыл: {path}"
    except Exception as e:
        code, _ = _run(f'start "" "{path}"')
        if code == 0:
            return True, f"Открыл: {path}"
        return False, str(e)


def delete_file(path: str) -> Tuple[bool, str]:
    """Faylni o'chirish (aslida main.py da tasdiq kerak)."""
    path = (path or "").strip()
    if not path:
        return False, "Укажи путь к файлу."
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        return False, f"Файл не найден: {path}"
    try:
        os.remove(path)
        return True, f"Удалил: {path}"
    except Exception as e:
        return False, str(e)


def open_folder(path: str) -> Tuple[bool, str]:
    """Papkani Explorer da ochish. My Computer CLSID qo'llab-quvvatlanadi."""
    path = (path or "").strip()
    if not path:
        return False, "Укажи путь к папке."
    # My Computer / This PC (CLSID)
    if path.startswith("::") or "20D04FE0" in path:
        code, _ = _run_start(f'explorer "{path}"')
        return (code == 0, _msg("Opened My Computer.", "Открыл «Мой компьютер».") if code == 0 else _msg("Could not open.", "Не удалось открыть."))
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        return False, f"Папка не найдена: {path}"
    try:
        os.startfile(path)
        return True, f"Открыл папку: {path}"
    except Exception:
        code, _ = _run(f'explorer "{path}"')
        if code == 0:
            return True, f"Открыл папку: {path}"
        return False, _msg("Could not open folder.", "Не удалось открыть папку.")


def create_folder(parent_path: str, name: str) -> Tuple[bool, str, Optional[str]]:
    """Parent papka ichida yangi papka yaratish (masalan Nike). Qaytaradi: (ok, msg, full_path)."""
    parent = (parent_path or "").strip() or os.path.expanduser("~")
    name = (name or "").strip().replace("/", "").replace("\\", "")[:100]
    if not name:
        return False, "Укажи имя папки.", None
    parent = os.path.abspath(os.path.expanduser(parent))
    if not os.path.isdir(parent):
        return False, f"Папка не найдена: {parent}", None
    new_path = os.path.join(parent, name)
    if os.path.exists(new_path):
        return True, f"Папка уже есть: {new_path}", new_path
    try:
        os.makedirs(new_path, exist_ok=True)
        return True, f"Создал папку: {name}", new_path
    except Exception as e:
        return False, str(e), None


def find_folder(name: str, current_folder: Optional[str] = None) -> Optional[str]:
    """User home va umumiy joylarda papka nomi bo‘yicha qidirish (masalan game)."""
    raw = (name or "").strip()
    if not raw:
        return None
    name_lower = raw.lower()
    # My Computer / This PC
    if name_lower in ("my computer", "this pc", "mycomputer", "мой компьютер", "компьютер"):
        return "::{20D04FE0-3AEA-1069-A2D8-08002B30309D}"
    if ("\\" in raw or (len(raw) > 2 and raw[1] == ":")):
        p = os.path.abspath(os.path.expanduser(raw.replace("/", "\\")))
        if os.path.isdir(p):
            return p
    # Avval ochiq papka ichida qidirish (ichki papka nomi)
    if current_folder and os.path.isdir(current_folder):
        direct = os.path.join(current_folder, raw)
        if os.path.isdir(direct):
            return direct
        try:
            for item in os.listdir(current_folder):
                if item.lower() == name_lower:
                    p = os.path.join(current_folder, item)
                    if os.path.isdir(p):
                        return p
        except (OSError, PermissionError):
            pass
        try:
            for sub in os.listdir(current_folder)[:50]:
                sub_path = os.path.join(current_folder, sub)
                if os.path.isdir(sub_path):
                    inner = os.path.join(sub_path, raw)
                    if os.path.isdir(inner):
                        return inner
                    for item in os.listdir(sub_path):
                        if item.lower() == name_lower:
                            p = os.path.join(sub_path, item)
                            if os.path.isdir(p):
                                return p
        except (OSError, PermissionError):
            pass
    user = os.path.expanduser("~")
    prof = os.environ.get("USERPROFILE", "") or user
    _folder_map = {
        "документы": "Documents", "документ": "Documents", "documents": "Documents",
        "рабочий стол": "Desktop", "desktop": "Desktop",
        "загрузки": "Downloads", "downloads": "Downloads",
        "игры": "Games", "игра": "Games", "games": "Games", "game": "Games",
        "изображения": "Pictures", "видео": "Videos", "музыка": "Music",
        "pictures": "Pictures", "images": "Pictures",
        "videos": "Videos", "music": "Music",
        "projects": "Projects",
    }
    _rus_folders = ("Documents", "Desktop", "Downloads", "Games", "Pictures", "Videos", "Music",
                    "Документы", "Рабочий стол", "Загрузки", "Игры", "Изображения", "Видео", "Музыка")
    mapped = _folder_map.get(name_lower) or raw
    candidates = [
        os.path.join(user, raw),
        os.path.join(user, mapped),
        os.path.join(prof, raw),
        os.path.join(prof, mapped),
    ]
    for base in _rus_folders:
        candidates.append(os.path.join(user, base, raw))
        candidates.append(os.path.join(user, base, mapped))
        candidates.append(os.path.join(user, base))
    candidates.extend([
        os.path.join("C:\\", raw),
        os.path.join("C:\\", mapped),
        os.path.join("C:\\", "Games", raw),
        os.path.join("C:\\", "Program Files", raw),
        os.path.join("C:\\", "Program Files (x86)", raw),
        os.path.join("C:\\", "Users", "Public", raw),
        os.path.join(user, "AppData", "Local", raw),
        os.path.join(user, "AppData", "Roaming", raw),
    ])
    for p in candidates:
        if p and os.path.isdir(p):
            return p
    try:
        for root in [user, "C:\\"]:
            if not os.path.isdir(root):
                continue
            try:
                for item in os.listdir(root):
                    if item.lower() == name_lower:
                        p = os.path.join(root, item)
                        if os.path.isdir(p):
                            return p
            except (OSError, PermissionError):
                pass
        # Ikkinchi daraja (Documents, Desktop, ...) — limit 80 ta papka tezlik uchun
        for root in [user, "C:\\"]:
            if not os.path.isdir(root):
                continue
            try:
                listed = os.listdir(root)
                for parent in listed[:80]:
                    parent_path = os.path.join(root, parent)
                    if not os.path.isdir(parent_path):
                        continue
                    try:
                        for item in os.listdir(parent_path):
                            if item.lower() == name_lower:
                                p = os.path.join(parent_path, item)
                                if os.path.isdir(p):
                                    return p
                    except (OSError, PermissionError):
                        pass
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    # Babata Self-Correction: alternativ nomlar bilan qayta urinish
    _alts = {"game": ["games", "Games"], "games": ["game", "Games"], "document": ["documents", "Documents"],
             "documents": ["document", "Documents"], "download": ["downloads", "Downloads"],
             "downloads": ["download", "Downloads"]}
    for alt in _alts.get(name_lower, []):
        found = _find_folder_impl(alt)
        if found:
            return found
    return None


def _find_folder_impl(name: str) -> Optional[str]:
    """Ichki: bitta nom uchun qidirish (find_folder dan chaqiriladi)."""
    raw = (name or "").strip()
    if not raw:
        return None
    name_lower = raw.lower()
    if name_lower in ("my computer", "this pc", "mycomputer", "mening kompyuterim", "kompyuterim", "moy kompyuter", "moy komp"):
        return "::{20D04FE0-3AEA-1069-A2D8-08002B30309D}"
    if ("\\" in raw or (len(raw) > 2 and raw[1] == ":")):
        p = os.path.abspath(os.path.expanduser(raw.replace("/", "\\")))
        if os.path.isdir(p):
            return p
    user = os.path.expanduser("~")
    prof = os.environ.get("USERPROFILE", "") or user
    _folder_map = {
        "документы": "Documents", "документ": "Documents", "documents": "Documents",
        "рабочий стол": "Desktop", "desktop": "Desktop",
        "загрузки": "Downloads", "downloads": "Downloads",
        "игры": "Games", "игра": "Games", "games": "Games", "game": "Games",
        "изображения": "Pictures", "видео": "Videos", "музыка": "Music",
        "pictures": "Pictures", "images": "Pictures",
        "videos": "Videos", "music": "Music",
        "projects": "Projects",
    }
    _rus_folders = ("Documents", "Desktop", "Downloads", "Games", "Pictures", "Videos", "Music",
                    "Документы", "Рабочий стол", "Загрузки", "Игры", "Изображения", "Видео", "Музыка")
    mapped = _folder_map.get(name_lower) or raw
    candidates = [
        os.path.join(user, raw), os.path.join(user, mapped),
        os.path.join(prof, raw), os.path.join(prof, mapped),
    ]
    for base in _rus_folders:
        candidates.append(os.path.join(user, base, raw))
        candidates.append(os.path.join(user, base, mapped))
        candidates.append(os.path.join(user, base))
    candidates.extend([
        os.path.join("C:\\", raw), os.path.join("C:\\", mapped),
        os.path.join("C:\\", "Games", raw), os.path.join("C:\\", "Program Files", raw),
        os.path.join("C:\\", "Program Files (x86)", raw), os.path.join("C:\\", "Users", "Public", raw),
        os.path.join(user, "AppData", "Local", raw), os.path.join(user, "AppData", "Roaming", raw),
    ])
    for p in candidates:
        if p and os.path.isdir(p):
            return p
    try:
        for root in [user, "C:\\"]:
            if not os.path.isdir(root):
                continue
            try:
                for item in os.listdir(root):
                    if item.lower() == name_lower:
                        p = os.path.join(root, item)
                        if os.path.isdir(p):
                            return p
            except (OSError, PermissionError):
                pass
        for root in [user, "C:\\"]:
            if not os.path.isdir(root):
                continue
            try:
                for parent in (os.listdir(root) or [])[:80]:
                    parent_path = os.path.join(root, parent)
                    if not os.path.isdir(parent_path):
                        continue
                    try:
                        for item in os.listdir(parent_path):
                            if item.lower() == name_lower:
                                p = os.path.join(parent_path, item)
                                if os.path.isdir(p):
                                    return p
                    except (OSError, PermissionError):
                        pass
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    return None


def restore_all_windows() -> Tuple[bool, str]:
    """Restore visible app windows. Skips desktop/taskbar to avoid shell issues."""
    _control_log("restore_all_windows", "start", success=True)
    try:
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        hwnds: List[int] = []
        max_class = 256
        buf = ctypes.create_unicode_buffer(max_class)

        def enum_cb(hwnd: int, _: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            if user32.GetClassNameW(hwnd, buf, max_class):
                cls = buf.value.lower()
                if "progman" in cls or "shell_traywnd" in cls or "shell_secondarytraywnd" in cls:
                    return True
            hwnds.append(hwnd)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        cb = WNDENUMPROC(enum_cb)
        user32.EnumWindows(cb, 0)
        for hwnd in hwnds:
            try:
                user32.ShowWindow(hwnd, SW_RESTORE)
            except Exception:
                pass
        return True, "Окна развёрнуты."
    except Exception as e:
        _control_log("restore_all_windows_error", str(e), success=False)
        return False, f"Не удалось развернуть окна: {e}"


# Babata: dasturlarni o'chirish — faqat whitelist dagi "keraksiz axlat" dasturlar
UNINSTALL_WHITELIST = frozenset({
    "candy crush", "candycrush", "microsoft solitaire", "solitaire collection",
    "xbox game bar", "xbox game bar plugin", "spotify music", "spotify",
    "skype", "teams", "microsoft teams", "zoom", "discord",
    "mcafee", "norton", "avast", "avg", "kaspersky",
    "bing", "bing news", "msn", "get help", "feedback hub",
    "mixed reality portal", "3d viewer", "paint 3d", "groove music",
    "movies & tv", "mail", "calendar", "people", "tips",
    "adobe acrobat reader", "adobe reader", "ccleaner",
    "utorrent", "bittorrent", "winzip", "winrar",
})


def uninstall_app(app_name: str) -> Tuple[bool, str]:
    """
    winget orqali dasturni o'chirish. Faqat UNINSTALL_WHITELIST dagi dasturlar.
    app_name: "Candy Crush", "McAfee", "Skype" va hokazo.
    """
    raw = (app_name or "").strip()
    name_lower = raw.lower()
    if not name_lower:
        return False, "Укажи имя приложения."
    allowed = False
    for w in UNINSTALL_WHITELIST:
        if name_lower in w or w in name_lower:
            allowed = True
            break
    if not allowed:
        return False, f"«{raw}» не в списке разрешённых к удалению. Babata o'chiradi faqat keraksiz axlat dasturlarni."
    _control_log("uninstall_app", f"app={raw}", success=True)
    try:
        code, out = _run(f'winget uninstall --name "{raw}" --silent --accept-source-agreements --accept-package-agreements', timeout_sec=60.0)
        if code == 0:
            return True, f"O'chirildi: {raw}."
        if "No package found" in out or "No installed package" in out:
            return False, f"«{raw}» topilmadi yoki o'rnatilmagan."
        return False, f"winget xato: {out[:200]}"
    except subprocess.TimeoutExpired:
        return False, "O'chirish vaqti tugadi. Qo'lda tekshiring."
    except Exception as e:
        _control_log("uninstall_app_error", str(e), success=False)
        return False, str(e)


def volume_up() -> Tuple[bool, str]:
    """Tizim ovozini oshirish (Volume Up tugmasi)."""
    try:
        import ctypes
        VK_VOLUME_UP = 0xAF
        ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
        return True, "Громче."
    except Exception as e:
        return False, str(e)


def volume_down() -> Tuple[bool, str]:
    """Tizim ovozini pasaytirish (Volume Down tugmasi)."""
    try:
        import ctypes
        VK_VOLUME_DOWN = 0xAE
        ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
        return True, "Тише."
    except Exception as e:
        return False, str(e)


def media_rewind() -> Tuple[bool, str]:
    """Video/audio ortga qaytarish (Left arrow — 10 sek)."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.press("left")
        return True, "Назад."
    except Exception as e:
        return False, str(e)


def media_forward() -> Tuple[bool, str]:
    """Video/audio oldinga qaytarish (Right arrow — 10 sek)."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.press("right")
        return True, "Вперёд."
    except Exception as e:
        return False, str(e)


def slide_next() -> Tuple[bool, str]:
    """Keyingi slayd (PowerPoint, prezentatsiya). Page Down yoki Right."""
    ok, msg = send_hotkey("pagedown")
    if ok:
        return True, _msg("Next slide.", "Следующий слайд.")
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.press("right")
        return True, _msg("Next slide.", "Следующий слайд.")
    except Exception:
        return False, _msg("Could not change slide.", "Не удалось переключить слайд.")


def slide_prev() -> Tuple[bool, str]:
    """Oldingi slayd (PowerPoint, prezentatsiya). Page Up yoki Left."""
    ok, msg = send_hotkey("pageup")
    if ok:
        return True, _msg("Previous slide.", "Предыдущий слайд.")
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.press("left")
        return True, _msg("Previous slide.", "Предыдущий слайд.")
    except Exception:
        return False, _msg("Could not change slide.", "Не удалось переключить слайд.")


def presentation_start() -> Tuple[bool, str]:
    """Prezentatsiyani boshlash (F5 — PowerPoint slideshow)."""
    ok, msg = send_hotkey("f5")
    if ok:
        return True, _msg("Presentation started.", "Презентация запущена.")
    return False, _msg("Could not start presentation.", "Не удалось запустить презентацию.")


def close_folder_window() -> Tuple[bool, str]:
    """Joriy fokusdagi oynani yopish (Alt+F4). Papka oynasi fokusda bo'lsa yopiladi."""
    _control_log("close_folder_window", "start", success=True)
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.hotkey("alt", "f4")
        return True, "Окно закрыто."
    except ImportError:
        return False, "pyautogui не установлен."
    except Exception as e:
        _control_log("close_folder_window_error", str(e), success=False)
        return False, str(e)


def minimize_all_windows() -> Tuple[bool, str]:
    """Minimize visible app windows. Skips desktop (Progman) and taskbar (Shell_TrayWnd) to avoid breaking shell."""
    _control_log("minimize_all_windows", "start", success=True)
    try:
        user32 = ctypes.windll.user32
        SW_MINIMIZE = 6
        hwnds: List[int] = []
        max_class = 256
        buf = ctypes.create_unicode_buffer(max_class)

        def enum_cb(hwnd: int, _: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            if user32.GetClassNameW(hwnd, buf, max_class):
                cls = buf.value.lower()
                if "progman" in cls or "shell_traywnd" in cls or "shell_secondarytraywnd" in cls:
                    return True
            hwnds.append(hwnd)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        cb = WNDENUMPROC(enum_cb)
        user32.EnumWindows(cb, 0)
        for hwnd in hwnds:
            try:
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            except Exception:
                pass
        return True, "Все окна свернуты."
    except Exception as e:
        _control_log("minimize_all_windows_error", str(e), success=False)
        return False, f"Не удалось свернуть окна: {e}"


def run_powershell(script: str, timeout_sec: float = 30.0) -> Tuple[bool, str]:
    """Выполнить скрипт PowerShell."""
    script = (script or "").strip()
    if not script:
        return False, "Скрипт пустой."
    _control_log("run_powershell", script[:80], success=True)
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ps1", delete=False) as f:
            f.write(script.encode("utf-8", errors="replace"))
            path = f.name
        try:
            code, out = _run(f'powershell -NoProfile -ExecutionPolicy Bypass -File "{path}"', timeout_sec=timeout_sec)
            out = (out or "").strip()
            return (code == 0, out if out else ("OK" if code == 0 else f"Exit {code}"))
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass
    except Exception as e:
        _control_log("run_powershell_error", str(e), success=False)
        return False, str(e)


def window_focus_by_title(title: str) -> Tuple[bool, str]:
    """Переключить фокус на окно по заголовку."""
    try:
        from window_ops import window_by_title
        wins = window_by_title(title, partial=True)
        if not wins:
            return False, f"Окно не найдено: {title}"
        hwnd = int(wins[0].get("hwnd", 0))
        if not hwnd:
            return False, "Окно не найдено."
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True, f"В фокусе: {title}"
    except ImportError:
        return False, "window_ops не найден."
    except Exception as e:
        return False, str(e)


def send_hotkey(*keys: str) -> Tuple[bool, str]:
    """Клавиатурные сочетания. Например: send_hotkey('ctrl', 'c'), send_hotkey('alt', 'f4')."""
    try:
        from input_sim import hotkey
        if hotkey(*keys):
            return True, "Выполнено."
        return False, "Ошибка."
    except ImportError:
        return False, "input_sim (pyautogui) не установлен."
    except Exception as e:
        return False, str(e)


def send_keys(text: str) -> Tuple[bool, str]:
    """Ввод текста с клавиатуры."""
    text = (text or "").strip()
    if not text:
        return False, "Текст пустой."
    try:
        from input_sim import key_type
        if key_type(text):
            return True, "Напечатано."
        return False, "Ошибка."
    except ImportError:
        return False, "input_sim (pyautogui) не установлен."
    except Exception as e:
        return False, str(e)


def run_command(cmd: str, timeout_sec: float = 30.0) -> Tuple[bool, str]:
    """Har qanday buyruqni bajarish. 100% kompyuter boshqaruvi. dir, winget, pip, npm, git — hammasi."""
    cmd = (cmd or "").strip()
    if not cmd:
        return False, _msg("Specify command.", "Укажи команду.")
    _control_log("run_command", cmd[:100], success=True)
    low = cmd.lower()
    # Safety: destructive filesystem reset/hard-reset blocks
    blocked_fragments = (
        "format ", "diskpart", "del /f /s /q c:\\", "rd /s /q c:\\",
        "rmdir /s /q c:\\", "shutdown /p", "bcdedit /delete", "cipher /w:",
    )
    if (not _supercontrol_enabled()) and any(x in low for x in blocked_fragments):
        return False, "Команда заблокирована политикой безопасности."
    try:
        code, out = _run(cmd, timeout_sec=timeout_sec)
        if code == 0:
            return True, (out.strip()[:2000] if out.strip() else _msg("Done.", "Выполнено."))
        return False, (out.strip()[:500] if out.strip() else f"Exit code: {code}")
    except subprocess.TimeoutExpired:
        return False, _msg("Timeout.", "Таймаут.")
    except Exception as e:
        _control_log("run_command_error", str(e), success=False)
        return False, str(e)[:300]


def lock_workstation() -> Tuple[bool, str]:
    """Lock current Windows session."""
    try:
        ok = bool(ctypes.windll.user32.LockWorkStation())
        return (ok, "Сеанс заблокирован." if ok else "Не удалось заблокировать сеанс.")
    except Exception as e:
        return False, str(e)


def sleep_pc() -> Tuple[bool, str]:
    """Put PC to sleep."""
    try:
        code, out = _run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", timeout_sec=5.0)
        return (code == 0, "Укладываю компьютер в сон." if code == 0 else "Не удалось перевести в сон.")
    except Exception as e:
        return False, str(e)


def restart_pc(delay_sec: int = 0) -> Tuple[bool, str]:
    """Restart Windows safely."""
    delay = max(0, int(delay_sec))
    code, out = _run(f"shutdown /r /t {delay}", timeout_sec=5.0)
    return (code == 0, f"Перезагружаю через {delay} сек." if code == 0 else f"Не удалось перезагрузить: {out[:120]}")


def shutdown_pc(delay_sec: int = 0) -> Tuple[bool, str]:
    """Shutdown Windows safely."""
    delay = max(0, int(delay_sec))
    code, out = _run(f"shutdown /s /t {delay}", timeout_sec=5.0)
    return (code == 0, f"Выключаю через {delay} сек." if code == 0 else f"Не удалось выключить: {out[:120]}")


def logoff_user() -> Tuple[bool, str]:
    """Log off current user session."""
    code, out = _run("shutdown /l", timeout_sec=5.0)
    return (code == 0, "Выход из текущего сеанса." if code == 0 else f"Не удалось выйти из сеанса: {out[:120]}")


def close_app_generic(name: str) -> Tuple[bool, str]:
    """Har qanday dasturni yopish (exe nomi). explorer.exe — hech qachon."""
    a = (name or "").strip()
    if not a:
        return False, _msg("Specify app name.", "Укажи имя приложения.")
    if not a.lower().endswith(".exe"):
        a = a + ".exe"
    a_lower = a.lower()
    if a_lower in BLOCKED_IMAGES:
        return False, _msg("Cannot close system process.", "Системный процесс закрыть нельзя.")
    _control_log("close_app_generic", a, success=True)
    try:
        code, out = _run(f'taskkill /IM "{a}" /F', timeout_sec=5)
        if code == 0:
            return True, _msg(f"Closed: {a}", f"Закрыл: {a}")
        if not is_process_running(a):
            return True, _msg(f"{a} already closed.", f"{a} уже закрыт.")
        return False, _msg(f"Could not close: {a}", f"Не удалось закрыть: {a}")
    except Exception as e:
        return False, str(e)[:200]


def copy_file(src: str, dst: str) -> Tuple[bool, str]:
    """Копировать файл или папку. shutil.copy2 (файл) или shutil.copytree (папка)."""
    src = (src or "").strip()
    dst = (dst or "").strip()
    if not src or not dst:
        return False, "Укажи путь источника и назначения."
    src = os.path.abspath(os.path.expanduser(src))
    dst = os.path.abspath(os.path.expanduser(dst))
    if not os.path.exists(src):
        return False, f"Не найден: {src}"
    try:
        import shutil
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            return True, f"Скопировал файл в {dst}"
        if os.path.isdir(src):
            if os.path.exists(dst):
                return False, f"Папка назначения уже есть: {dst}"
            shutil.copytree(src, dst)
            return True, f"Скопировал папку в {dst}"
        return False, "Не файл и не папка."
    except Exception as e:
        return False, f"Ошибка копирования: {e}"


def move_file(src: str, dst: str) -> Tuple[bool, str]:
    """Переместить файл или папку. shutil.move."""
    src = (src or "").strip()
    dst = (dst or "").strip()
    if not src or not dst:
        return False, "Укажи путь источника и назначения."
    src = os.path.abspath(os.path.expanduser(src))
    dst = os.path.abspath(os.path.expanduser(dst))
    if not os.path.exists(src):
        return False, f"Не найден: {src}"
    try:
        import shutil
        shutil.move(src, dst)
        return True, f"Переместил в {dst}"
    except Exception as e:
        return False, f"Ошибка перемещения: {e}"


def copy_to_clipboard(text: str) -> Tuple[bool, str]:
    """Скопировать текст в буфер обмена (Windows — pyperclip или ctypes)."""
    text = (text or "").strip()
    if not text:
        return False, "Нечего копировать."
    try:
        try:
            import pyperclip
            pyperclip.copy(text)
            return True, "Скопировал в буфер обмена."
        except ImportError:
            pass
        # Windows ctypes fallback
        if os.name == "nt":
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            CF_UNICODETEXT = 13
            data = (text + "\x00").encode("utf-16-le")
            n = len(data)
            GMEM_MOVEABLE = 0x0002
            mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, n)
            if not mem:
                return False, "Буфер недоступен."
            ptr = kernel32.GlobalLock(mem)
            if not ptr:
                kernel32.GlobalFree(mem)
                return False, "Буфер недоступен."
            ctypes.memmove(ptr, data, n)
            kernel32.GlobalUnlock(mem)
            if not user32.OpenClipboard(0):
                kernel32.GlobalFree(mem)
                return False, "Буфер занят."
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, mem):
                user32.CloseClipboard()
                kernel32.GlobalFree(mem)
                return False, "Не удалось записать в буфер."
            user32.CloseClipboard()
            return True, "Скопировал в буфер обмена."
    except Exception as e:
        return False, f"Ошибка буфера: {e}"


# ── MOUSE BOSHQARUVI (pyautogui orqali) ────────────────────────────────────
def mouse_move(x: int, y: int) -> Tuple[bool, str]:
    """Sichqonchani (x, y) ga ko'chirish."""
    try:
        from input_sim import mouse_move as _mm
        ok = _mm(int(x), int(y))
        return (ok, "Ko'chirildi." if ok else "input_sim xato.")
    except ImportError:
        return False, "input_sim (pyautogui) o'rnatilmagan."
    except Exception as e:
        return False, str(e)[:200]


def mouse_click(x: Optional[int] = None, y: Optional[int] = None,
                button: str = "left") -> Tuple[bool, str]:
    """Sichqoncha klik. (x,y) berilsa — o'sha joyda, aks holda — joriy joyda."""
    try:
        from input_sim import mouse_click as _mc
        ok = _mc(int(x) if x is not None else None,
                 int(y) if y is not None else None,
                 button=button)
        return (ok, "Klik bajarildi." if ok else "input_sim xato.")
    except ImportError:
        return False, "input_sim (pyautogui) o'rnatilmagan."
    except Exception as e:
        return False, str(e)[:200]


def mouse_right_click(x: Optional[int] = None, y: Optional[int] = None) -> Tuple[bool, str]:
    """O'ng tugma klik (kontekst menyu)."""
    return mouse_click(x, y, button="right")


def mouse_double_click(x: Optional[int] = None, y: Optional[int] = None) -> Tuple[bool, str]:
    """Ikki marta klik."""
    try:
        from input_sim import mouse_double_click as _mdc
        ok = _mdc(int(x) if x is not None else None,
                  int(y) if y is not None else None)
        return (ok, "Ikki marta klik bajarildi." if ok else "input_sim xato.")
    except ImportError:
        return False, "input_sim (pyautogui) o'rnatilmagan."
    except Exception as e:
        return False, str(e)[:200]


def mouse_scroll(x: int, y: int, clicks: int = 3,
                 direction: str = "down") -> Tuple[bool, str]:
    """Sichqoncha g'ildiragi (scroll). direction: 'up' yoki 'down'."""
    try:
        import pyautogui
        amount = -abs(clicks) if direction == "down" else abs(clicks)
        pyautogui.scroll(amount, x=int(x), y=int(y))
        return True, f"Scroll {direction} bajarildi."
    except ImportError:
        return False, "pyautogui o'rnatilmagan."
    except Exception as e:
        return False, str(e)[:200]


def get_screen_size() -> Tuple[bool, str]:
    """Ekran o'lchamini qaytaradi: '1920x1080' formatida."""
    try:
        import pyautogui
        w, h = pyautogui.size()
        return True, f"{w}x{h}"
    except ImportError:
        # ctypes orqali
        try:
            user32 = ctypes.windll.user32
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            return True, f"{w}x{h}"
        except Exception:
            pass
        return False, "Ekran o'lchamini ololmadi."
    except Exception as e:
        return False, str(e)[:200]


def get_mouse_position() -> Tuple[bool, str]:
    """Joriy sichqoncha pozitsiyasini qaytaradi: 'x=123 y=456'."""
    try:
        import pyautogui
        x, y = pyautogui.position()
        return True, f"x={x} y={y}"
    except ImportError:
        try:
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return True, f"x={pt.x} y={pt.y}"
        except Exception:
            pass
        return False, "Pozitsiya ololmadi."
    except Exception as e:
        return False, str(e)[:200]
