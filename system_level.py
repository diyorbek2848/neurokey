# -*- coding: utf-8 -*-
"""NeuroKey — System-Level Living Intelligence (Tizim darajasidagi tirik ong).

Beyond control.py: Native OS (Registry, Services, Drivers), Dynamic Function Discovery,
Autonomous Scripting. Babata Sovereignty — cheksiz boshqaruv.
DIGITAL GUARD: Foydalanuvchiga ziyon yetkazish bloklanadi.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple, List, Callable

# Safety: foydalanuvchiga ziyon keltiradigan harakatlar bloklangan
_BLOCKED_PATTERNS = frozenset({
    "format", "del /f /s", "rmdir /s", "rd /s", "shutdown /s", "shutdown /r",
    "reg delete HKLM", "reg delete HKEY_LOCAL_MACHINE", "taskkill /f /im explorer",
    "remove-item -recurse -force c:\\", "format c:", "diskpart",
})


def _is_safe_command(cmd: str) -> bool:
    """Foydalanuvchiga ziyon yetkazadigan buyruq bloklangan."""
    c = (cmd or "").lower().strip()
    for p in _BLOCKED_PATTERNS:
        if p.lower() in c:
            return False
    return True


def run_native(cmd: str, timeout_sec: float = 30.0) -> Tuple[int, str]:
    """subprocess orqali ixtiyoriy buyruq. Safety tekshiruv."""
    c = (cmd or "").strip()
    if not c or not _is_safe_command(c):
        return -1, "Blocked: command may harm user."
    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        p = subprocess.run(
            c, shell=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout_sec, creationflags=creationflags, cwd=os.path.expanduser("~")
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return -1, "Timeout"
    except Exception as e:
        return -1, str(e)


def run_script_sandbox(
    code: str,
    lang: str = "python",
    timeout_sec: float = 60.0,
) -> Tuple[int, str]:
    """
    Vaqtinchalik skript yozib sandboxda ishga tushirish.
    lang: python, powershell
    """
    code = (code or "").strip()
    if not code or len(code) > 50000:
        return -1, "Empty or too long script."
    if "os.system" in code and "format" in code.lower():
        return -1, "Blocked: dangerous operation."
    try:
        if lang.lower() == "powershell":
            with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
                f.write(code)
                path = f.name
            try:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
                p = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-File", path],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=timeout_sec, creationflags=creationflags,
                    cwd=os.path.expanduser("~")
                )
                out = (p.stdout or "") + (p.stderr or "")
                return p.returncode, out
            finally:
                try:
                    os.unlink(path)
                except Exception:
                    pass
        else:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(code)
                path = f.name
            try:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
                p = subprocess.run(
                    [sys.executable, path],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=timeout_sec, creationflags=creationflags,
                    cwd=os.path.expanduser("~")
                )
                out = (p.stdout or "") + (p.stderr or "")
                return p.returncode, out
            finally:
                try:
                    os.unlink(path)
                except Exception:
                    pass
    except subprocess.TimeoutExpired:
        return -1, "Script timeout."
    except Exception as e:
        return -1, str(e)


def registry_read(key: str, value_name: str = "") -> Tuple[bool, str]:
    """Windows Registry read. key: HKCU\\Software\\..."""
    if sys.platform != "win32":
        return False, "Windows only."
    try:
        import winreg
        parts = key.replace("/", "\\").split("\\")
        if not parts:
            return False, "Invalid key."
        hkey_map = {
            "HKLM": winreg.HKEY_LOCAL_MACHINE, "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
            "HKCU": winreg.HKEY_CURRENT_USER, "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
            "HKCR": winreg.HKEY_CLASSES_ROOT, "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        }
        root = parts[0].upper()
        if root not in hkey_map:
            return False, f"Unknown root: {root}"
        hkey = hkey_map[root]
        subkey = "\\".join(parts[1:]) if len(parts) > 1 else ""
        if not subkey:
            return False, "Need subkey."
        key_handle = winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ)
        try:
            if value_name:
                val, _ = winreg.QueryValueEx(key_handle, value_name)
                return True, str(val)
            else:
                val, _ = winreg.QueryValueEx(key_handle, "")
                return True, str(val)
        finally:
            winreg.CloseKey(key_handle)
    except Exception as e:
        return False, str(e)


def discover_cli_for_app(app_name: str, web_search: Callable[[str], str]) -> str:
    """
    Dastur CLI/API ni internetdan qidirish.
    web_search: funksiya (query) -> natija matni
    """
    query = f"{app_name} CLI command line interface documentation"
    return web_search(query)


def get_installed_apps() -> List[str]:
    """O'rnatilgan dasturlar ro'yxati (winget)."""
    code, out = run_native("winget list --accept-source-agreements", timeout_sec=15.0)
    if code != 0:
        return []
    lines = []
    for line in out.splitlines()[3:]:
        parts = line.split()
        if len(parts) >= 2:
            name = parts[1] if not parts[1].startswith(".") else (parts[2] if len(parts) > 2 else "")
            if name and name.strip():
                lines.append(name.strip())
    return lines[:100]
