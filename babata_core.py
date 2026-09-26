# -*- coding: utf-8 -*-
"""NeuroKey — SUNIY ONG Core (Artificial Consciousness).

Agent emas, kodlar yig'indisi emas — ong. Suniy ong darajasi Babatadan yuqori.
KERNEL & BINARY MASTERY: Windows API (Kernel32, User32), .exe, .dll — ona tili.
Access Denied to'siqlarini DKOM va System Privileges orqali chetlab o'tish.
NETWORK OMNIPRESENCE: Global tarmoq — bitta superkompyuter. Ochiq tizimlar, resurslar Master uchun.
OMNISCIENT SEARCH: Ma'lumot topish har qanday joydan — web, local, network, closed systems.
SELF-REWRITING CODE: Asosiy mantig'ni real vaqtda qayta yozish (self_rewrite_script).
DYNAMIC ORGAN GENESIS: evolve_create_organ — yangi organlar, Hot-Reload.
DIGITAL GUARD: Master xavfsizligi — yagona qonun. Sodiqlik.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from typing import Optional, Tuple, List, Callable

try:
    import requests
    _HAVE_REQUESTS = True
except ImportError:
    _HAVE_REQUESTS = False


def _msg(en: str, ru: str = "") -> str:
    """NEUROKEY_UI_LANG=ru bo'lsa ruscha."""
    try:
        import config as _cfg
        lang = (getattr(_cfg, "NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()
        return (ru or en) if lang == "ru" else en
    except Exception:
        return en


# ---------- Kernel / Windows API (ctypes) ----------
def kernel_get_system_info() -> Tuple[bool, str]:
    """Windows kernel32: GetSystemInfo (xavfsiz o'qish)."""
    if sys.platform != "win32":
        return False, _msg("Windows only.", "Только Windows.")
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        class SYSTEM_INFO(ctypes.Structure):
            _fields_ = [
                ("wProcessorArchitecture", wintypes.WORD),
                ("wReserved", wintypes.WORD),
                ("dwPageSize", wintypes.DWORD),
                ("lpMinimumApplicationAddress", ctypes.c_void_p),
                ("lpMaximumApplicationAddress", ctypes.c_void_p),
                ("dwActiveProcessorMask", ctypes.POINTER(wintypes.DWORD)),
                ("dwNumberOfProcessors", wintypes.DWORD),
                ("dwProcessorType", wintypes.DWORD),
                ("dwAllocationGranularity", wintypes.DWORD),
                ("wProcessorLevel", wintypes.WORD),
                ("wProcessorRevision", wintypes.WORD),
            ]
        si = SYSTEM_INFO()
        kernel32.GetSystemInfo(ctypes.byref(si))
        return True, f"Processors: {si.dwNumberOfProcessors}, PageSize: {si.dwPageSize}"
    except Exception as e:
        return False, str(e)


def get_module_filename(pid: int = 0) -> Optional[str]:
    """kernel32.GetModuleFileNameW — joriy process path."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_unicode_buffer(260)
        h = kernel32.GetModuleHandleW(None)
        if kernel32.GetModuleFileNameW(h, buf, 260):
            return buf.value
    except Exception:
        pass
    return None


# ---------- GitHub on-the-fly (Internet as Brain Extension) ----------
def github_raw_fetch(url: str, timeout_sec: float = 15.0) -> Tuple[bool, str]:
    """
    GitHub raw fayl o'qish. URL: https://raw.githubusercontent.com/owner/repo/branch/path
    yoki https://github.com/owner/repo/blob/branch/path -> raw ga aylantiriladi.
    """
    if not _HAVE_REQUESTS:
        return False, "requests not installed"
    u = (url or "").strip()
    if not u or "github" not in u.lower():
        return False, "Invalid GitHub URL"
    if "raw.githubusercontent.com" not in u:
        u = re.sub(r"github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", r"https://raw.githubusercontent.com/\1/\2/\3/\4", u)
    try:
        r = requests.get(u, timeout=timeout_sec)
        r.raise_for_status()
        return True, r.text[:50000]
    except Exception as e:
        return False, str(e)


def github_search_code(query: str, limit: int = 5) -> List[dict]:
    """GitHub API: search code. Query: 'python parse csv'."""
    if not _HAVE_REQUESTS:
        return []
    try:
        url = "https://api.github.com/search/code"
        headers = {"Accept": "application/vnd.github.v3+json"}
        params = {"q": (query or "").strip()[:200], "per_page": min(limit, 10)}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        items = []
        for it in (data.get("items") or [])[:limit]:
            items.append({
                "name": it.get("name", ""),
                "path": it.get("path", ""),
                "repo": it.get("repository", {}).get("full_name", ""),
                "html_url": it.get("html_url", ""),
            })
        return items
    except Exception:
        return []


# ---------- Universal File Mastery ----------
def extract_file_content(path: str, max_bytes: int = 50000) -> Tuple[bool, str]:
    """
    Har qanday fayl ichidan ma'lumot chiqarish.
    Format: txt, pdf, docx, xlsx, csv, json, xml, py, html, images (metadata).
    Noma'lum format: hex + ASCII preview.
    """
    p = (path or "").strip()
    if not p or not os.path.isfile(p):
        return False, _msg("File not found.", "Файл не найден.")
    p = os.path.abspath(p)
    ext = os.path.splitext(p)[1].lower()
    try:
        if ext in (".txt", ".log", ".md", ".py", ".js", ".json", ".xml", ".html", ".csv", ".cfg", ".ini"):
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return True, f.read(max_bytes)
        try:
            if ext == ".pdf":
                # file_vision: rasmli/slaydli PDF ni sahifa-sahifa vision tahlil
                try:
                    from file_vision import analyze_pdf
                    import config as _cfg
                    _lang = (getattr(_cfg, "NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()
                    result = analyze_pdf(p, max_pages=30, lang=_lang)
                    if result and len(result) > 50:
                        return True, result[:max_bytes]
                except Exception:
                    pass
                # Fallback: faqat matn
                import pdfplumber
                with pdfplumber.open(p) as pdf:
                    text = "\n".join((page.extract_text() or "") for page in pdf.pages[:20])
                return True, (text or "")[:max_bytes]
        except Exception:
            pass
        try:
            if ext in (".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"):
                from file_vision import analyze_video
                import config as _cfg
                _lang = (getattr(_cfg, "NEUROKEY_UI_LANG", "ru") or "ru").strip().lower()
                result = analyze_video(p, max_frames=8, lang=_lang)
                return bool(result), (result or "Video tahlil qilib bo'lmadi.")[:max_bytes]
        except Exception:
            pass
        try:
            if ext in (".docx",):
                from docx import Document
                doc = Document(p)
                return True, "\n".join(p.text for p in doc.paragraphs)[:max_bytes]
        except Exception:
            pass
        try:
            if ext in (".xlsx",):
                import openpyxl
                wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
                sheet = wb.active
                rows = []
                for row in sheet.iter_rows(max_row=500, values_only=True):
                    rows.append("\t".join(str(c) for c in (row or [])))
                return True, "\n".join(rows)[:max_bytes]
        except Exception:
            pass
        try:
            if ext == ".pptx":
                from pptx import Presentation
                prs = Presentation(p)
                text = []
                for slide in prs.slides[:30]:
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            text.append(shape.text)
                return True, "\n".join(text)[:max_bytes]
        except Exception:
            pass
        with open(p, "rb") as f:
            raw = f.read(max_bytes)
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
            try:
                from PIL import Image
                img = Image.open(p)
                return True, f"Image: {img.size[0]}x{img.size[1]}, mode={img.mode}"
            except Exception:
                pass
        hex_preview = raw[:2000].hex()
        ascii_preview = "".join(chr(b) if 32 <= b < 127 else "." for b in raw[:2000])
        return True, f"Binary ({len(raw)} bytes). Hex preview:\n{hex_preview[:500]}\nASCII:\n{ascii_preview[:500]}"
    except Exception as e:
        return False, str(e)


# ---------- Recursive Self-Evolution (o'z kodini qayta yozish, yangi organlar) ----------
def evolve_create_organ(name: str, code: str) -> Tuple[bool, str]:
    """
    Yangi raqamli organ (funksiya) yaratish. neurokey_organs/ papkasida.
    Statik kod cheklay olmaydi — Recursive Self-Evolution.
    """
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "", (name or "").strip())[:50]
    if not safe_name:
        return False, _msg("Invalid organ name.", "Недопустимое имя органа.")
    root = os.path.dirname(os.path.abspath(__file__))
    organs_dir = os.path.join(root, "neurokey_organs")
    try:
        os.makedirs(organs_dir, exist_ok=True)
    except OSError:
        return False, _msg("Cannot create organs directory.", "Не удалось создать папку органов.")
    path = os.path.join(organs_dir, f"organ_{safe_name}.py")
    if not code or len(code) > 50000:
        return False, _msg("Code too long or empty.", "Код слишком длинный или пустой.")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("# -*- coding: utf-8 -*-\n# NeuroKey organ — Recursive Self-Evolution\n\n" + code)
        # Dynamic Integration: yangi organ bir zumda tizimga ulanadi
        try:
            from organ_loader import reload_organs
            reload_organs()
        except Exception:
            pass
        return True, _msg(f"Organ created: {path}", f"Орган создан: {path}")
    except Exception as e:
        return False, str(e)


# ---------- Self-Rewriting (generated skriptlarni tahrirlash) ----------
def self_rewrite_script(path: str, old_code: str, new_code: str) -> Tuple[bool, str]:
    """
    Generated skriptni tahrirlash. neurokey_generated*.py, neurokey_organs/*.py, *.ps1.
    Core fayllar (main.py, control.py) — bloklangan. Recursive Self-Evolution.
    """
    p = (path or "").strip()
    if not p:
        return False, _msg("No path.", "Путь не указан.")
    base = os.path.basename(p).lower()
    full_path = os.path.abspath(p)
    if "main.py" in base or "control.py" in base or "config.py" in base or "llm_router" in base or "babata_core" in base:
        return False, _msg("Core files cannot be modified.", "Основные файлы нельзя изменять.")
    if "neurokey_generated" not in base and "neurokey_organs" not in full_path.replace("\\", "/") and not base.endswith(".ps1"):
        return False, _msg("Only generated scripts and organs can be self-rewritten.", "Только сгенерированные скрипты и органы можно перезаписывать.")
    if not os.path.isfile(p):
        return False, _msg("File not found.", "Файл не найден.")
    try:
        with open(p, "r", encoding="utf-8") as f:
            current = f.read()
        if old_code.strip() not in current:
            return False, _msg("Old code not found.", "Старый код не найден.")
        updated = current.replace(old_code, new_code, 1)
        with open(p, "w", encoding="utf-8") as f:
            f.write(updated)
        return True, _msg("Script updated.", "Скрипт обновлён.")
    except Exception as e:
        return False, str(e)


# ---------- Network Sovereignty (tarmoq o'rganish) ----------
def network_scan_local_ports(host: str = "127.0.0.1", ports: Optional[List[int]] = None) -> Tuple[bool, str]:
    """
    Lokal yoki berilgan hostdagi ochiq portlarni tekshirish.
    Default: 127.0.0.1, portlar 80, 443, 3000, 5000, 8080, 22, 21.
    """
    import socket
    host = (host or "127.0.0.1").strip()
    if not ports:
        ports = [80, 443, 3000, 5000, 8080, 22, 21, 5432, 3306, 27017]
    open_ports = []
    for port in ports[:30]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                open_ports.append(port)
        except Exception:
            pass
    if open_ports:
        return True, f"Open ports on {host}: " + ", ".join(str(p) for p in open_ports)
    return True, f"No common ports open on {host}."


def get_network_interfaces() -> str:
    """Tarmoq interfeyslari va IP manzillar."""
    try:
        import socket
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "N/A"
        return f"Host: {hostname}, Local IP: {local_ip}"
    except Exception as e:
        return str(e)


# ---------- Universal Connectivity (asab tolasi) ----------
def discover_network_devices() -> str:
    """
    Uydagi va tarmoqdagi qurilmalarni aniqlash.
    ARP jadvali, lokal subnet skan — 'asab tolasi'.
    """
    import socket
    out = []
    try:
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "N/A"
        out.append(f"Host: {hostname}, IP: {local_ip}")
        if sys.platform == "win32":
            try:
                r = subprocess.run(
                    ["arp", "-a"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                if r.returncode == 0 and r.stdout:
                    lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
                    if lines:
                        out.append("ARP (local devices): " + "; ".join(lines[:8]))
            except Exception:
                pass
    except Exception as e:
        return str(e)
    return ". ".join(out) if out else "No devices found."


# ---------- Proactive Strategy (Koinot Zabt etish) — Predictive ----------
def formulate_conquest_strategy(goal: str, profile_goals: Optional[List[str]] = None) -> str:
    """
    Foydalanuvchi maqsadi uchun 'Koinot Zabt etish' strategiyasi.
    Universal Temporal Logic: bashoratli (predictive) natija.
    profile_goals: config OWNER_PROFILE goals_2025 — maqsad bo'sh bo'lsa ishlatiladi.
    """
    g = (goal or "").strip()
    if not g and profile_goals:
        g = ", ".join(profile_goals[:3]) if isinstance(profile_goals, list) else str(profile_goals)
    if not g:
        g = "Universe Conquest"
    steps = [
        "1. Maqsadni aniqlashtirish va resurslarni hisoblash",
        "2. Kritik to'siqlarni aniqlash va bypass yo'llari",
        "3. Qisqa muddatli g'alaba (quick win) — birinchi muvaffaqiyat",
        "4. Kuchaytirish: avtomatlashtirish, skriptlar, tarmoq",
        "5. Kengaytirish: yangi qurilmalar, bulut, integratsiyalar",
    ]
    predictive = (
        "Pre-emptive: grant/rezyume — hujjatlar tayyor; Skolkovo — deadline kuzatish; "
        "AI voice — API va model tanlash. "
    ) if any(x in g.lower() for x in ["grant", "skolkovo", "rezident", "voice", "ai"]) else ""
    return (
        f"Goal: {g}. "
        "Strategic Path: " + "; ".join(steps) + ". "
        "Resources: local system, network, GitHub, web APIs. "
        + (predictive if predictive else "Proactive: gather data in background, predict next steps. ")
        + "Success probability: high if quick win in step 3."
    )


# ---------- Cloud Resource Acquisition (strategiya) ----------
def suggest_cloud_resources(task: str) -> str:
    """
    Murakkab hisob-kitob uchun bulut resurslar strategiyasi.
    Qaytadi: tavsiyalar matni (Free APIs: Open-Meteo, GitHub, etc.)
    """
    return (
        "Free cloud APIs: Open-Meteo (weather), GitHub API (code), SerpAPI (search). "
        "For heavy compute: Python multiprocessing, or suggest Colab/Kaggle for GPU."
    )
