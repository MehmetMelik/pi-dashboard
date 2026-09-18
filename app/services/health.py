"""Service health checks."""

import httpx

SERVICES = [
    {"name": "Gitea", "url": "http://192.168.86.40:3300", "icon": "G"},
    {"name": "Ollama", "url": "http://localhost:11434", "icon": "O"},
    {"name": "Open WebUI", "url": "http://localhost:3000", "icon": "W"},
    {"name": "Pi-hole", "url": "http://10.2.0.3/admin", "icon": "P"},
    {"name": "wg-easy", "url": "http://localhost:51821", "icon": "V"},
]

_cache: list[dict] = []


async def refresh_health():
    global _cache
    results = []
    async with httpx.AsyncClient(timeout=5) as client:
        for svc in SERVICES:
            try:
                resp = await client.get(svc["url"])
                up = resp.status_code < 500
            except Exception:
                up = False
            results.append({
                "name": svc["name"],
                "icon": svc["icon"],
                "up": up,
            })
    _cache = results
    up_count = sum(1 for s in _cache if s["up"])
    print(f"[health] {up_count}/{len(_cache)} services up")


def get_health() -> list[dict]:
    return _cache
