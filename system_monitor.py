# -*- coding: utf-8 -*-
"""Tizim monitoringi: CPU, RAM, batareya, videokarta (GPU), disk/SSD (psutil + nvidia-smi)."""

from __future__ import annotations

import os
import subprocess
from typing import Optional, List, Tuple

try:
    import psutil
    _HAVE_PSUTIL = True
except ImportError:
    psutil = None
    _HAVE_PSUTIL = False


def get_cpu_usage() -> float:
    if not _HAVE_PSUTIL:
        return 0.0
    try:
        return float(psutil.cpu_percent(interval=0.3))
    except Exception:
        return 0.0


def get_ram_info() -> Tuple[float, float, float]:
    """(used_gb, total_gb, percent)"""
    if not _HAVE_PSUTIL:
        return 0.0, 0.0, 0.0
    try:
        v = psutil.virtual_memory()
        used_gb = v.used / (1024 ** 3)
        total_gb = v.total / (1024 ** 3)
        return used_gb, total_gb, float(v.percent)
    except Exception:
        return 0.0, 0.0, 0.0


def get_battery_info() -> Optional[dict]:
    """Batareya: percent, charging, time_left (min)."""
    if not _HAVE_PSUTIL:
        return None
    try:
        bat = psutil.sensors_battery()
        if bat is None:
            return None
        return {
            "percent": bat.percent,
            "power_plugged": bat.power_plugged,
            "sec_left": bat.secsleft if bat.secsleft not in (0, -1) else None,
        }
    except Exception:
        return None


def get_gpu_info() -> Optional[dict]:
    """Videokarta: name, usage %, temp °C, memory used/total. NVIDIA: nvidia-smi, boshqalar: WMI nomi."""
    info = {"name": "", "usage_percent": None, "temp_c": None, "mem_used_gb": None, "mem_total_gb": None}
    try:
        # NVIDIA: nvidia-smi
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        if r.returncode == 0 and r.stdout:
            line = r.stdout.strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 1:
                info["name"] = parts[0].strip(' "')[:60]
            if len(parts) >= 2:
                try:
                    info["usage_percent"] = int(parts[1])
                except ValueError:
                    pass
            if len(parts) >= 3:
                try:
                    info["temp_c"] = int(parts[2])
                except ValueError:
                    pass
            if len(parts) >= 4:
                try:
                    info["mem_used_gb"] = float(parts[3]) / 1024
                except ValueError:
                    pass
            if len(parts) >= 5:
                try:
                    info["mem_total_gb"] = float(parts[4]) / 1024
                except ValueError:
                    pass
            return info
    except Exception:
        pass
    # Windows: videokarta nomi (WMI)
    if os.name == "nt":
        try:
            r = subprocess.run(
                'wmic path win32_VideoController get Name /format:value',
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode == 0 and "Name=" in (r.stdout or ""):
                for line in (r.stdout or "").splitlines():
                    if line.strip().startswith("Name="):
                        info["name"] = line.split("=", 1)[-1].strip()[:60]
                        break
        except Exception:
            pass
    return info if info.get("name") or info.get("usage_percent") is not None else None


def get_disk_info() -> List[Tuple[str, float, float, float]]:
    """Har bir disk/razdel: (mount, used_gb, total_gb, percent). C:, D: va b."""
    if not _HAVE_PSUTIL:
        return []
    out = []
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                used_gb = usage.used / (1024 ** 3)
                total_gb = usage.total / (1024 ** 3)
                pct = usage.percent
                out.append((part.mountpoint, used_gb, total_gb, pct))
            except Exception:
                continue
    except Exception:
        pass
    return out[:6]


def get_system_report(lang: str = "ru") -> str:
    """To'liq hisobot: CPU, xotira (RAM), videokarta (GPU), disk/SSD, batareya — kompyuter ichi."""
    if not _HAVE_PSUTIL:
        return "Модуль мониторинга не установлен. Установи psutil." if lang == "ru" else "Monitoring module not installed. Install psutil."

    parts = []
    cpu = get_cpu_usage()
    if lang == "ru":
        parts.append(f"Процессор загружен на {cpu:.0f} процентов.")
    else:
        parts.append(f"CPU usage is {cpu:.0f} percent.")

    used_gb, total_gb, ram_pct = get_ram_info()
    if lang == "ru":
        parts.append(f"Оперативная память: {used_gb:.1f} из {total_gb:.1f} гигабайт, занято {ram_pct:.0f} процентов.")
    else:
        parts.append(f"RAM: {used_gb:.1f} of {total_gb:.1f} GB, {ram_pct:.0f} percent used.")

    gpu = get_gpu_info()
    if gpu:
        name = (gpu.get("name") or "").strip()
        if name:
            if lang == "ru":
                parts.append(f"Видеокарта: {name}.")
            else:
                parts.append(f"GPU: {name}.")
        u = gpu.get("usage_percent")
        if u is not None:
            if lang == "ru":
                parts.append(f"Загрузка видеокарты {u} процентов.")
            else:
                parts.append(f"GPU load {u} percent.")
        temp = gpu.get("temp_c")
        if temp is not None:
            if lang == "ru":
                parts.append(f"Температура видеокарты {temp} градусов.")
            else:
                parts.append(f"GPU temperature {temp} degrees.")
        mem_u, mem_t = gpu.get("mem_used_gb"), gpu.get("mem_total_gb")
        if mem_u is not None and mem_t is not None and mem_t > 0:
            if lang == "ru":
                parts.append(f"Память видеокарты: {mem_u:.1f} из {mem_t:.1f} гигабайт.")
            else:
                parts.append(f"GPU memory: {mem_u:.1f} of {mem_t:.1f} GB.")
    else:
        if lang == "ru":
            parts.append("Видеокарта: данные не получены (нужен драйвер NVIDIA и nvidia-smi в PATH для деталей).")
        else:
            parts.append("GPU: no details (install NVIDIA driver and nvidia-smi for usage and temperature).")

    disks = get_disk_info()
    for mount, used_gb, total_gb, pct in disks[:3]:
        if total_gb < 0.1:
            continue
        if lang == "ru":
            parts.append(f"Диск {mount}: {used_gb:.0f} из {total_gb:.0f} ГБ, занято {pct:.0f} процентов.")
        else:
            parts.append(f"Disk {mount}: {used_gb:.0f} of {total_gb:.0f} GB, {pct:.0f} percent used.")

    bat = get_battery_info()
    if bat:
        pct = bat.get("percent") or 0
        plugged = bat.get("power_plugged", False)
        if lang == "ru":
            if plugged:
                parts.append(f"Батарея {pct:.0f} процентов, зарядка подключена.")
            else:
                parts.append(f"Батарея {pct:.0f} процентов.")
                if bat.get("sec_left"):
                    mins = bat["sec_left"] // 60
                    parts.append(f"Осталось примерно {mins} минут.")
        else:
            if plugged:
                parts.append(f"Battery {pct:.0f} percent, charging.")
            else:
                parts.append(f"Battery {pct:.0f} percent.")
                if bat.get("sec_left"):
                    mins = bat["sec_left"] // 60
                    parts.append(f"About {mins} minutes left.")
    else:
        if lang == "ru":
            parts.append("Батарея не обнаружена (стационарный ПК).")
        else:
            parts.append("No battery (desktop).")

    return " ".join(parts)
