"""Pi Dashboard — FastAPI application."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    WEATHER_INTERVAL, NEWS_INTERVAL, OLLAMA_SUMMARY_DELAY,
    MARKET_INTERVAL, GITHUB_INTERVAL, CALENDAR_INTERVAL,
)
from app.database import init_db
from app.services import system, weather, news, docker, ollama, market, github
from app.services import calendar as cal_service

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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


async def ollama_loop():
    await asyncio.sleep(30)
    if not await ollama.is_available():
        print("[bg] Ollama not available, skipping AI summaries")
        return
    print("[bg] Ollama available, starting AI summaries")
    while True:
        try:
            did_work = await ollama.summarize_one()
            if not did_work:
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(OLLAMA_SUMMARY_DELAY)
        except Exception as e:
            print(f"[bg] ollama error: {e}")
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tasks = [
        asyncio.create_task(weather_loop()),
        asyncio.create_task(news_loop()),
        asyncio.create_task(market_loop()),
        asyncio.create_task(calendar_loop()),
        asyncio.create_task(ollama_loop()),
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

@app.get("/partials/system", response_class=HTMLResponse)
async def partial_system(request: Request):
    stats = system.get_all_stats()
    return templates.TemplateResponse("partials/system.html", {
        "request": request,
        "stats": stats,
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
