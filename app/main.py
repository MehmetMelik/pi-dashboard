"""Pi Dashboard — FastAPI application."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    WEATHER_INTERVAL, NEWS_INTERVAL, FIRESTORE_ENRICH_INTERVAL,
    FIRESTORE_QUOTA_BACKOFF,
    MARKET_INTERVAL, GITHUB_INTERVAL, CALENDAR_INTERVAL,
    PIHOLE_INTERVAL, WIREGUARD_INTERVAL, HEALTH_INTERVAL,
    SPEEDTEST_INTERVAL, BOOKMARKS,
)
from app.database import init_db, save_system_stats, load_system_stats
from app.services import system, weather, news, docker, summaries, market, github
from app.services import calendar as cal_service
from app.services import pihole, wireguard, health, speedtest, customfeed

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Cache-bust static CSS by its mtime so browsers always fetch the current file
# after a redeploy (the service restarts on deploy, re-evaluating this).
_css_file = BASE_DIR / "static" / "style.css"
templates.env.globals["css_version"] = int(_css_file.stat().st_mtime) if _css_file.exists() else 0


async def weather_loop():
    while True:
        try:
            await weather.fetch_weather()
        except Exception as e:
            print(f"[bg] weather error: {e}")
        await asyncio.sleep(WEATHER_INTERVAL)


async def news_loop():
    while True:
        try:
            await news.fetch_all_news()
        except Exception as e:
            print(f"[bg] news error: {e}")
        await asyncio.sleep(NEWS_INTERVAL)


async def market_loop():
    while True:
        try:
            await market.refresh_market()
        except Exception as e:
            print(f"[bg] market error: {e}")
        await asyncio.sleep(MARKET_INTERVAL)


async def calendar_loop():
    while True:
        try:
            await cal_service.refresh_calendar()
        except Exception as e:
            print(f"[bg] calendar error: {e}")
        await asyncio.sleep(CALENDAR_INTERVAL)


async def summaries_loop():
    # AI summaries come from the news-firebase pipeline: primarily via a local
    # SQLite mirror (no Firestore reads), with Firestore as a fallback. Both do
    # blocking I/O, so every call runs in a worker thread to keep the loop free.
    await asyncio.sleep(30)
    if not await asyncio.to_thread(summaries.is_available):
        print("[bg] Summary source not available, skipping AI summaries")
        return
    print("[bg] Summary source available, enriching news with AI summaries")
    while True:
        delay = FIRESTORE_ENRICH_INTERVAL
        try:
            n = await asyncio.to_thread(summaries.enrich_unsummarized)
            if n:
                print(f"[bg] enriched {n} articles with AI summaries")
        except Exception as e:
            # Only the Firestore fallback can hit this; back off so we never
            # starve the news-firebase pipeline, which shares the same quota.
            if "quota" in str(e).lower() or "ResourceExhausted" in type(e).__name__:
                delay = FIRESTORE_QUOTA_BACKOFF
                print(f"[bg] firestore read quota exceeded, backing off {delay}s")
            else:
                print(f"[bg] summary enrich error: {e}")
        await asyncio.sleep(delay)


async def pihole_loop():
    while True:
        try:
            await pihole.refresh_pihole()
        except Exception as e:
            print(f"[bg] pihole error: {e}")
        await asyncio.sleep(PIHOLE_INTERVAL)


async def wireguard_loop():
    while True:
        try:
            await wireguard.refresh_wireguard()
        except Exception as e:
            print(f"[bg] wireguard error: {e}")
        await asyncio.sleep(WIREGUARD_INTERVAL)


async def health_loop():
    while True:
        try:
            await health.refresh_health()
        except Exception as e:
            print(f"[bg] health error: {e}")
        await asyncio.sleep(HEALTH_INTERVAL)


async def speedtest_loop():
    from app.database import load_speedtests
    import time
    while True:
        rows = load_speedtests(1)
        last_run = rows[0]["tested_at"] if rows else 0
        elapsed = time.time() - last_run
        if elapsed < SPEEDTEST_INTERVAL:
            await asyncio.sleep(SPEEDTEST_INTERVAL - elapsed)
            continue
        try:
            await speedtest.refresh_speedtest()
        except Exception as e:
            print(f"[bg] speedtest error: {e}")
        await asyncio.sleep(SPEEDTEST_INTERVAL)


async def system_stats_loop():
    while True:
        try:
            cores = system.get_cpu_percent_per_core()
            temp = system.get_cpu_temp()
            save_system_stats(temp, cores)
        except Exception as e:
            print(f"[bg] system_stats error: {e}")
        await asyncio.sleep(60)


async def customfeed_loop():
    while True:
        try:
            await customfeed.refresh_custom_feeds()
        except Exception as e:
            print(f"[bg] customfeed error: {e}")
        await asyncio.sleep(NEWS_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tasks = [
        asyncio.create_task(weather_loop()),
        asyncio.create_task(news_loop()),
        asyncio.create_task(market_loop()),
        asyncio.create_task(calendar_loop()),
        asyncio.create_task(summaries_loop()),
        asyncio.create_task(pihole_loop()),
        asyncio.create_task(wireguard_loop()),
        asyncio.create_task(health_loop()),
        asyncio.create_task(speedtest_loop()),
        asyncio.create_task(customfeed_loop()),
        asyncio.create_task(system_stats_loop()),
    ]
    yield
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Pi Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# --- Main page ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# --- HTMX Partials ---

def _status_pills() -> list[dict]:
    """Aggregate an at-a-glance health summary for the top status strip."""
    pills: list[dict] = []
    uptime = None
    try:
        stats = system.get_all_stats()
        temp = stats.get("cpu_temp")
        cores = stats.get("cpu_cores") or []
        cpu = round(sum(cores) / len(cores)) if cores else None
        mem = (stats.get("memory") or {}).get("percent")
        uptime = stats.get("uptime")
        if temp is not None:
            lvl = "ok" if temp < 60 else "warn" if temp < 75 else "crit"
            pills.append({"label": "SYS", "value": f"{temp:.0f}°C", "level": lvl})
        if cpu is not None:
            lvl = "ok" if cpu < 70 else "warn" if cpu < 90 else "crit"
            pills.append({"label": "CPU", "value": f"{cpu}%", "level": lvl})
        if mem is not None:
            lvl = "ok" if mem < 75 else "warn" if mem < 90 else "crit"
            pills.append({"label": "MEM", "value": f"{mem:.0f}%", "level": lvl})
    except Exception:
        pass
    try:
        h = health.get_health()
        if h:
            up = sum(1 for s in h if s.get("up"))
            lvl = "ok" if up == len(h) else "warn" if up else "crit"
            pills.append({"label": "SVC", "value": f"{up}/{len(h)}", "level": lvl})
    except Exception:
        pass
    try:
        clients = wireguard.get_wireguard()
        if clients is not None:
            conn = sum(1 for c in clients if c.get("connected"))
            pills.append({"label": "VPN", "value": f"{conn} up", "level": "ok" if conn else "idle"})
    except Exception:
        pass
    try:
        p = pihole.get_pihole()
        pct = (p or {}).get("percent_blocked")
        if pct is not None:
            pills.append({"label": "BLOCK", "value": f"{pct:.0f}%", "level": "ok"})
    except Exception:
        pass
    if uptime:
        pills.append({"label": "UPTIME", "value": uptime, "level": "idle"})
    return pills


@app.get("/partials/status", response_class=HTMLResponse)
async def partial_status(request: Request):
    return templates.TemplateResponse("partials/status.html", {
        "request": request,
        "pills": _status_pills(),
    })


@app.get("/partials/system", response_class=HTMLResponse)
async def partial_system(request: Request):
    stats = system.get_all_stats()
    return templates.TemplateResponse("partials/system.html", {
        "request": request,
        "stats": stats,
    })


@app.get("/partials/sys_history", response_class=HTMLResponse)
async def partial_sys_history(request: Request):
    return templates.TemplateResponse("partials/sys_history.html", {"request": request})


@app.get("/api/system/history")
async def api_system_history():
    rows = load_system_stats(hours=24)
    core_count = len(rows[0]["cpu_cores"]) if rows else 0
    timestamps = [r["sampled_at"] for r in rows]
    temps = [r["cpu_temp"] for r in rows]
    cores = [[r["cpu_cores"][i] if i < len(r["cpu_cores"]) else None for r in rows] for i in range(core_count)]
    return JSONResponse({
        "timestamps": timestamps,
        "cpu_temp": temps,
        "cpu_cores": cores,
        "core_count": core_count,
    })


@app.get("/partials/weather", response_class=HTMLResponse)
async def partial_weather(request: Request):
    w = weather.get_weather()
    return templates.TemplateResponse("partials/weather.html", {
        "request": request,
        "weather": w,
    })


@app.get("/partials/market", response_class=HTMLResponse)
async def partial_market(request: Request):
    tickers = market.get_market()
    return templates.TemplateResponse("partials/market.html", {
        "request": request,
        "tickers": tickers,
    })


@app.get("/partials/news/finance", response_class=HTMLResponse)
async def partial_news_finance(request: Request):
    articles = news.get_finance_articles()
    return templates.TemplateResponse("partials/news_finance.html", {
        "request": request,
        "articles": articles,
    })


@app.get("/partials/news/tech", response_class=HTMLResponse)
async def partial_news_tech(request: Request):
    articles = news.get_tech_articles()
    return templates.TemplateResponse("partials/news_tech.html", {
        "request": request,
        "articles": articles,
    })


@app.get("/partials/docker", response_class=HTMLResponse)
async def partial_docker(request: Request):
    containers = docker.get_containers()
    return templates.TemplateResponse("partials/docker.html", {
        "request": request,
        "containers": containers,
    })


@app.get("/partials/github", response_class=HTMLResponse)
async def partial_github(request: Request):
    activity = github.get_activity()
    return templates.TemplateResponse("partials/github.html", {
        "request": request,
        "activity": activity,
    })


@app.get("/partials/calendar", response_class=HTMLResponse)
async def partial_calendar(request: Request):
    events = cal_service.get_events()
    return templates.TemplateResponse("partials/calendar.html", {
        "request": request,
        "events": events,
    })


@app.get("/partials/pihole", response_class=HTMLResponse)
async def partial_pihole(request: Request):
    stats = pihole.get_pihole()
    return templates.TemplateResponse("partials/pihole.html", {
        "request": request,
        "stats": stats,
    })


@app.get("/partials/wireguard", response_class=HTMLResponse)
async def partial_wireguard(request: Request):
    clients = wireguard.get_wireguard()
    return templates.TemplateResponse("partials/wireguard.html", {
        "request": request,
        "clients": clients,
    })


@app.get("/partials/health", response_class=HTMLResponse)
async def partial_health(request: Request):
    services = health.get_health()
    return templates.TemplateResponse("partials/health.html", {
        "request": request,
        "services": services,
    })


@app.get("/partials/speedtest", response_class=HTMLResponse)
async def partial_speedtest(request: Request):
    speed = speedtest.get_speedtest()
    history = speedtest.get_speedtest_history()
    return templates.TemplateResponse("partials/speedtest.html", {
        "request": request,
        "speed": speed,
        "history": history,
    })


@app.get("/partials/bookmarks", response_class=HTMLResponse)
async def partial_bookmarks(request: Request):
    return templates.TemplateResponse("partials/bookmarks.html", {
        "request": request,
        "bookmarks": BOOKMARKS,
    })


@app.get("/partials/customfeed", response_class=HTMLResponse)
async def partial_customfeed(request: Request):
    articles = customfeed.get_custom_feeds()
    return templates.TemplateResponse("partials/customfeed.html", {
        "request": request,
        "articles": articles,
    })
