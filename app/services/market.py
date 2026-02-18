"""Market ticker data via Yahoo Finance API (no key required)."""

import httpx

TICKERS = [
    {"symbol": "^GSPC", "name": "S&P 500", "icon": "S"},
    {"symbol": "^IXIC", "name": "NASDAQ", "icon": "N"},
    {"symbol": "^FTSE", "name": "FTSE 100", "icon": "F"},
    {"symbol": "BTC-USD", "name": "Bitcoin", "icon": "B"},
    {"symbol": "ETH-USD", "name": "Ethereum", "icon": "E"},
    {"symbol": "^DJI", "name": "Dow Jones", "icon": "D"},
]

YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"


async def fetch_tickers() -> list[dict]:
    results = []
    async with httpx.AsyncClient(
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0 (compatible; PiDashboard/1.0)"},
    ) as client:
        for t in TICKERS:
            try:
                resp = await client.get(
                    YF_URL.format(t["symbol"]),
                    params={"interval": "1d", "range": "2d"},
                )
                resp.raise_for_status()
                data = resp.json()
                result = data["chart"]["result"][0]
                meta = result["meta"]
                price = meta.get("regularMarketPrice", 0)
                prev = meta.get("chartPreviousClose", meta.get("previousClose", 0))

                change = price - prev if prev else 0
                change_pct = (change / prev * 100) if prev else 0

                results.append({
                    "symbol": t["symbol"],
                    "name": t["name"],
                    "icon": t["icon"],
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "up": change >= 0,
                })
            except Exception as e:
                print(f"[market] error fetching {t['symbol']}: {e}")
                results.append({
                    "symbol": t["symbol"],
                    "name": t["name"],
                    "icon": t["icon"],
                    "price": None,
                    "change": 0,
                    "change_pct": 0,
                    "up": True,
                })
    return results


# Cache in memory (updated by background loop)
_cache: list[dict] = []


async def refresh_market():
    global _cache
    _cache = await fetch_tickers()
    valid = sum(1 for t in _cache if t["price"] is not None)
    print(f"[market] refreshed {valid}/{len(_cache)} tickers")


def get_market() -> list[dict]:
    return _cache
