"""Periodic speed test via speedtest-cli."""

import asyncio
import json
import os
from datetime import datetime

from app.database import save_speedtest, load_speedtests

_cache: dict = {}
_history: list[dict] = []

_SPEEDTEST_BIN = "/home/melik/.local/bin/ookla-speedtest"


def _load_history():
    global _history
    rows = load_speedtests(10)
    _history = []
    for r in rows:
        dt = datetime.fromtimestamp(r["tested_at"])
        _history.append({
            "download": r["download"],
            "upload": r["upload"],
            "ping": r["ping"],
            "server": r["server"] or "",
            "time": dt.strftime("%d %b %H:%M"),
        })


async def _run_speedtest_once() -> dict | None:
    proc = await asyncio.create_subprocess_exec(
        _SPEEDTEST_BIN,
        "--accept-license", "--accept-gdpr", "--format=json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
    if proc.returncode != 0:
        err = stderr.decode().strip()
        print(f"[speedtest] error: {err}")
        return None
    return json.loads(stdout.decode())


async def refresh_speedtest():
    global _cache
    if not os.path.isfile(_SPEEDTEST_BIN):
        print(f"[speedtest] {_SPEEDTEST_BIN} not found, skipping")
        return

    data = None
    for attempt in range(1, 4):
        try:
            data = await _run_speedtest_once()
            if data:
                break
        except asyncio.TimeoutError:
            print(f"[speedtest] timed out after 120s (attempt {attempt}/3)")
        except FileNotFoundError:
            print("[speedtest] speedtest-cli not installed, skipping")
            return
        except Exception as e:
            print(f"[speedtest] error (attempt {attempt}/3): {e}")
        if attempt < 3:
            await asyncio.sleep(60)

    if not data:
        print("[speedtest] all 3 attempts failed")
        return

    try:
        # Ookla format: bandwidth in bytes/sec, ping.latency in ms
        dl = round(data["download"]["bandwidth"] * 8 / 1_000_000, 1)
        ul = round(data["upload"]["bandwidth"] * 8 / 1_000_000, 1)
        ping = round(data["ping"]["latency"], 1)
        srv = data.get("server", {}) or {}
        server_parts = [p for p in (srv.get("name"), srv.get("location")) if p]
        server = " - ".join(server_parts)

        _cache = {"download": dl, "upload": ul, "ping": ping, "server": server}
        save_speedtest(dl, ul, ping, server)
        _load_history()
        print(f"[speedtest] {dl} Mbps down, {ul} Mbps up, {ping}ms ping")
    except Exception as e:
        print(f"[speedtest] parse error: {e}")


def get_speedtest() -> dict:
    return _cache


def get_speedtest_history() -> list[dict]:
    if not _history:
        _load_history()
    return _history
