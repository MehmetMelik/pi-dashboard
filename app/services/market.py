"""Market ticker data via Yahoo Finance API (no key required)."""

import httpx

TICKERS = [
    {"symbol": "^GSPC", "name": "S&P 500", "icon": "S"},
    {"symbol": "^IXIC", "name": "NASDAQ", "icon": "N"},
    {"symbol": "^FTSE", "name": "FTSE 100", "icon": "F"},
    {"symbol": "^DJI", "name": "Dow Jones", "icon": "D"},
    {"symbol": "BTC-USD", "name": "Bitcoin", "icon": "B"},
    {"symbol": "ETH-USD", "name": "Ethereum", "icon": "E"},
]

YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"


def _make_sparkline_svg(values: list[float], up: bool) -> str:
    if len(values) < 2:
        return ""
    w, h = 80, 24
    color = "#34d399" if up else "#f87171"
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    points = []
    for i, v in enumerate(values):
        x = round(i / (len(values) - 1) * w, 1)
        y = round(h - (v - mn) / rng * (h - 2) - 1, 1)
        points.append(f"{x},{y}")
    polyline = " ".join(points)
    return (
        f'<svg viewBox="0 0 {w} {h}" class="sparkline">'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


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
                    params={"interval": "15m", "range": "1d"},
                )
                resp.raise_for_status()
                data = resp.json()
                result = data["chart"]["result"][0]
                meta = result["meta"]
                price = meta.get("regularMarketPrice", 0)
                prev = meta.get("chartPreviousClose", meta.get("previousClose", 0))

                change = price - prev if prev else 0
                change_pct = (change / prev * 100) if prev else 0

                # Extract sparkline data from intraday closes
                closes = []
                indicators = result.get("indicators", {})
                quotes = indicators.get("quote", [{}])
                if quotes:
                    raw = quotes[0].get("close", [])
                    closes = [v for v in raw if v is not None]

                results.append({
                    "symbol": t["symbol"],
                    "name": t["name"],
                    "icon": t["icon"],
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "up": change >= 0,
                    "url": f"https://finance.yahoo.com/quote/{t['symbol']}",
                    "sparkline": _make_sparkline_svg(closes, change >= 0),
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
                    "url": f"https://finance.yahoo.com/quote/{t['symbol']}",
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
