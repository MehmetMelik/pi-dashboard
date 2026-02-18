"""System stats via psutil."""

import time
import psutil


def get_cpu_percent_per_core() -> list[float]:
    return psutil.cpu_percent(interval=0.5, percpu=True)


def get_cpu_temp() -> float | None:
    temps = psutil.sensors_temperatures()
    if not temps:
        return None
    for name in ("cpu_thermal", "cpu-thermal", "coretemp"):
        if name in temps and temps[name]:
            return temps[name][0].current
    first = next(iter(temps.values()), [])
    return first[0].current if first else None


def get_memory() -> dict:
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 1),
        "used_gb": round(mem.used / (1024**3), 1),
        "percent": mem.percent,
    }


def get_disk() -> dict:
    disk = psutil.disk_usage("/")
    return {
        "total_gb": round(disk.total / (1024**3), 1),
        "used_gb": round(disk.used / (1024**3), 1),
        "free_gb": round(disk.free / (1024**3), 1),
        "percent": disk.percent,
    }


def get_network() -> dict:
    counters = psutil.net_io_counters()
    return {
        "bytes_sent_mb": round(counters.bytes_sent / (1024**2), 1),
        "bytes_recv_mb": round(counters.bytes_recv / (1024**2), 1),
    }


def get_uptime() -> str:
    boot = psutil.boot_time()
    delta = int(time.time() - boot)
    days = delta // 86400
    hours = (delta % 86400) // 3600
    mins = (delta % 3600) // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


def get_all_stats() -> dict:
    return {
        "cpu_cores": get_cpu_percent_per_core(),
        "cpu_temp": get_cpu_temp(),
        "memory": get_memory(),
        "disk": get_disk(),
        "network": get_network(),
        "uptime": get_uptime(),
    }
