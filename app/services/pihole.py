"""Pi-hole stats via v6 API."""

import httpx

PIHOLE_URL = "http://10.2.0.3"
PIHOLE_PASSWORD = "REDACTED"

_cache: dict = {}
_sid: str = ""


async def _authenticate(client: httpx.AsyncClient) -> str:
    global _sid
    resp = await client.post(
        f"{PIHOLE_URL}/api/auth",
        json={"password": PIHOLE_PASSWORD},
    )
    resp.raise_for_status()
    _sid = resp.json().get("session", {}).get("sid", "")
    return _sid


async def refresh_pihole():
    global _cache
    async with httpx.AsyncClient(timeout=10) as client:
        sid = _sid or await _authenticate(client)

        resp = await client.get(
            f"{PIHOLE_URL}/api/stats/summary",
            headers={"sid": sid},
        )
        if resp.status_code == 401:
            sid = await _authenticate(client)
            resp = await client.get(
                f"{PIHOLE_URL}/api/stats/summary",
                headers={"sid": sid},
            )
        resp.raise_for_status()
        data = resp.json()

        q = data.get("queries", {})
        c = data.get("clients", {})
        g = data.get("gravity", {})

        _cache = {
            "total_queries": q.get("total", 0),
            "blocked": q.get("blocked", 0),
            "percent_blocked": round(q.get("percent_blocked", 0), 1),
            "domains_blocked": g.get("domains_being_blocked", 0),
            "cached": q.get("cached", 0),
            "forwarded": q.get("forwarded", 0),
            "active_clients": c.get("active", 0),
        }
        print(f"[pihole] refreshed: {_cache['total_queries']} queries, {_cache['percent_blocked']}% blocked")


def get_pihole() -> dict:
    return _cache
