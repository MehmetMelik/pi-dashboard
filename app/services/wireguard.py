"""WireGuard client status via wg-easy API."""

import os
import httpx
from datetime import datetime, timezone

WGEASY_URL = "http://localhost:51821"
WGEASY_PASSWORD = os.environ.get("WGEASY_PASSWORD", "")  # from .env (gitignored)

_cache: list[dict] = []
_cookies: dict = {}


async def _authenticate(client: httpx.AsyncClient):
    global _cookies
    resp = await client.post(
        f"{WGEASY_URL}/api/session",
        json={"password": WGEASY_PASSWORD},
    )
    resp.raise_for_status()
    _cookies = dict(resp.cookies)


def _format_handshake(ts: str | None) -> str:
    if not ts:
        return "never"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def _format_transfer(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1048576:
        return f"{b / 1024:.1f} KB"
    if b < 1073741824:
        return f"{b / 1048576:.1f} MB"
    return f"{b / 1073741824:.1f} GB"


async def refresh_wireguard():
    global _cache
    async with httpx.AsyncClient(timeout=10) as client:
        if not _cookies:
            await _authenticate(client)

        resp = await client.get(
            f"{WGEASY_URL}/api/wireguard/client",
            cookies=_cookies,
        )
        if resp.status_code in (401, 500):
            await _authenticate(client)
            resp = await client.get(
                f"{WGEASY_URL}/api/wireguard/client",
                cookies=_cookies,
            )
        resp.raise_for_status()
        clients = resp.json()

        _cache = []
        for c in clients:
            handshake = c.get("latestHandshakeAt")
            # Consider "connected" if handshake within last 3 minutes
            connected = False
            if handshake:
                dt = datetime.fromisoformat(handshake.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - dt
                connected = delta.total_seconds() < 180

            _cache.append({
                "name": c.get("name", "unknown"),
                "address": c.get("address", ""),
                "enabled": c.get("enabled", False),
                "connected": connected,
                "handshake": _format_handshake(handshake),
                "rx": _format_transfer(c.get("transferRx", 0)),
                "tx": _format_transfer(c.get("transferTx", 0)),
            })

        online = sum(1 for c in _cache if c["connected"])
        print(f"[wireguard] refreshed: {online}/{len(_cache)} clients connected")


def get_wireguard() -> list[dict]:
    return _cache
