# Pi Dashboard

A personal dark-themed web dashboard built for Raspberry Pi. Combines live weather, curated news with images, market tickers, GitHub activity, Google Calendar, system monitoring, and Docker status — all in one glanceable page.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.129-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

| Panel | Source | Refresh |
|-------|--------|---------|
| **Weather** | Open-Meteo API (London) — current + 5-day forecast | 30 min |
| **Markets** | Yahoo Finance — S&P 500, NASDAQ, FTSE 100, Dow Jones, BTC, ETH | 5 min |
| **Finance News** | Bloomberg, FT, Economist, MarketWatch, BBC Business, CNBC (RSS) | 15 min |
| **Tech News** | Ars Technica, TechCrunch, Nature, MIT Tech Review, Hacker News (JSON API) | 15 min |
| **GitHub Activity** | Contribution graph + recent events via GitHub API | 5 min |
| **Google Calendar** | Upcoming 14 days via private ICS feed | 10 min |
| **System Monitor** | CPU per-core, temperature, RAM, disk, network, uptime (psutil) | 5 sec |
| **Docker** | Container status via Unix socket API | 10 sec |
| **AI Summaries** | Optional one-line article summaries via local Ollama (qwen2.5:3b) | Continuous |

## Tech Stack

- **Backend**: Python 3.11 + FastAPI + Jinja2
- **Frontend**: HTMX (polling partials, no JS framework) + custom dark CSS
- **Data**: SQLite (WAL mode) for caching feeds/weather; psutil for live stats
- **APIs**: Open-Meteo (weather), Yahoo Finance (markets), GitHub REST/GraphQL, Google Calendar ICS
- **News**: RSS via feedparser + Hacker News JSON API + og:image scraping for thumbnails
- **AI**: Optional Ollama integration for article summaries

## Screenshots

The dashboard features a modern dark theme with CSS Grid layout, responsive breakpoints, and HTMX-powered live updates without page reloads.

## Quick Start

### Prerequisites

- Python 3.11+
- `gh` CLI authenticated (for GitHub panel)
- Docker running (for Docker panel)
- Ollama with `qwen2.5:3b` (optional, for AI summaries)

### Install

```bash
git clone https://github.com/MehmetMelik/pi-dashboard.git
cd pi-dashboard
pip install -r requirements.txt
```

### Configure

Create a `.env` file for your Google Calendar (optional):

```bash
echo 'GOOGLE_CALENDAR_ICS=https://calendar.google.com/calendar/ical/YOUR_CALENDAR/basic.ics' > .env
```

To get your ICS URL: Google Calendar > Settings > Settings for my calendars > [your calendar] > "Secret address in iCal format".

### Run

```bash
python3 run.py
```

Open `http://localhost:8080` in your browser.

### Run as a systemd service

```bash
# Edit pi-dashboard.service to match your paths if needed
sudo cp pi-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pi-dashboard
```

## Project Structure

```
app/
  config.py              — All constants: feed URLs, API params, intervals
  database.py            — SQLite setup, schema, read/write helpers
  main.py                — FastAPI app, lifespan background tasks, HTMX routes
  services/
    weather.py           — Open-Meteo client
    market.py            — Yahoo Finance tickers
    news.py              — RSS parser + HN API + og:image scraping
    github.py            — GitHub events + contribution graph (GraphQL)
    calendar.py          — Google Calendar ICS parser
    system.py            — psutil: CPU, temp, RAM, disk, network, uptime
    docker.py            — Docker Unix socket client
    ollama.py            — Optional AI summarization
static/
  style.css              — Dark theme, CSS Grid, responsive layout
templates/
  base.html              — HTML shell with HTMX + Inter font
  index.html             — Dashboard grid with HTMX polling sections
  partials/              — One HTML fragment per panel (system, weather, etc.)
```

## Configuration

All settings are in `app/config.py`. Key options:

| Setting | Default | Description |
|---------|---------|-------------|
| `PORT` | 8080 | Server port |
| `WEATHER_LAT/LON` | London | Weather location coordinates |
| `OLLAMA_ENABLED` | True | Enable/disable AI summaries |
| `OLLAMA_MODEL` | qwen2.5:3b | Ollama model for summaries |
| `HN_MAX_STORIES` | 20 | Number of Hacker News stories to fetch |
| `ARTICLES_PER_CATEGORY` | 15 | Articles shown per news panel |

## How It Works

- **Background tasks** (FastAPI lifespan + asyncio) fetch weather, news, markets, and calendar on their own intervals and cache results in SQLite / memory
- **HTMX polling** — each panel independently polls its own `/partials/*` endpoint at its own interval
- **Partials** return HTML fragments; HTMX swaps them into the page — no full page reloads
- **News images** are extracted from RSS media tags and og:image scraping; articles with images are prioritized for the featured cards

## License

[MIT](LICENSE)
