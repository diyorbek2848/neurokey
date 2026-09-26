# -*- coding: utf-8 -*-
"""NeuroKey — Protsess operatsiyalari. To'g'ridan-to'g'ri, control dan mustaqil.

Har qanday dastur. Xotirida qanday programma bo'lsa — ochish, yopish, boshqarish.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Dict, List, Optional, Any

try:
    import psutil
    _HAVE_PSUTIL = True
except ImportError:
    _HAVE_PSUTIL = False


def _creation_flags() -> int:
    """Windows da CREATE_NO_WINDOW — konsol yonmaydi."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def list_all() -> List[Dict[str, Any]]:
    """Barcha protsesslar ro'yxati: pid, name, cpu, memory."""
    if not _HAVE_PSUTIL:
        return _list_all_tasklist()
    result: List[Dict[str, Any]] = []
    try:
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = p.info
                mem = info.get("memory_info")
                mem_mb = round(mem.rss / (1024 * 1024), 1) if mem else 0
                result.append({
                    "pid": info.get("pid", 0),
                    "name": (info.get("name") or "").strip(),
                    "cpu": info.get("cpu_percent") or 0,
                    "memory_mb": mem_mb,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return result


def _list_all_tasklist() -> List[Dict[str, Any]]:
    """psutil yo'q bo'lsa — tasklist orqali."""
    result: List[Dict[str, Any]] = []
    try:
        p = subprocess.run(
            "tasklist /NH /FO CSV",
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=_creation_flags(),
        )
        for line in (p.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [x.strip('"') for x in line.split(",")]
            if len(parts) >= 2:
                try:
                    pid = int(parts[1])
                    name = (parts[0] or "").strip()
                    result.append({"pid": pid, "name": name, "cpu": 0, "memory_mb": 0})
                except ValueError:
                    pass
    except Exception:
        pass
    return result


def start(path: str, cwd: Optional[str] = None) -> int:
    """Dasturni ishga tushirish. Qaytadi: pid yoki 0 (muvaffaqiyat), -1 (xato)."""
    if not path or not isinstance(path, str):
        return -1
    path = path.strip()
    norm_path = os.path.normpath(path)
    # To'liq path — fayl mavjud
    if os.path.isfile(norm_path):
        try:
            proc = subprocess.Popen(
                [norm_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=cwd or os.path.dirname(norm_path),
                creationflags=_creation_flags(),
            )
            return proc.pid
        except Exception:
            pass
    # Windows: start buyrug'i orqali (calc, notepad, "C:\path\app.exe")
    if sys.platform == "win32":
        try:
            subprocess.Popen(
                f'start "" "{norm_path}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_creation_flags(),
            )
            return 0
        except Exception:
            pass
    return -1


def kill(pid: int) -> bool:
    """Protsessni to'xtatish."""
    if pid <= 0:
        return False
    if _HAVE_PSUTIL:
        try:
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=3)
            except psutil.TimeoutExpired:
                p.kill()
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    try:
        subprocess.run(f"taskkill /F /PID {pid}", shell=True, timeout=5, creationflags=_creation_flags())
        return True
    except Exception:
        return False


def find_by_name(name: str) -> List[int]:
    """Nom bo'yicha protsesslarni topish. Qaytadi: pid ro'yxati."""
    if not name or not isinstance(name, str):
        return []
    name_lower = name.strip().lower()
    if not name_lower.endswith(".exe"):
        name_lower += ".exe"
    pids: List[int] = []
    if _HAVE_PSUTIL:
        try:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if (p.info.get("name") or "").lower() == name_lower:
                        pids.append(p.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
    else:
        for proc in _list_all_tasklist():
            if (proc.get("name") or "").lower() == name_lower:
                pids.append(proc["pid"])
    return pids


def get_info(pid: int) -> Optional[Dict[str, Any]]:
    """Protsess haqida ma'lumot."""
    if pid <= 0:
        return None
    if _HAVE_PSUTIL:
        try:
            p = psutil.Process(pid)
            mem = p.memory_info()
            return {
                "pid": pid,
                "name": p.name(),
                "exe": p.exe(),
                "cpu_percent": p.cpu_percent(),
                "memory_mb": round(mem.rss / (1024 * 1024), 1),
                "status": p.status(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
    for proc in _list_all_tasklist():
        if proc.get("pid") == pid:
            return proc
    return None
