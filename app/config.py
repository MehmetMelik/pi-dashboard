"""Dashboard configuration constants."""

import os

# Server
HOST = "0.0.0.0"
PORT = 8080

# Database
DB_PATH = "dashboard.db"

# Weather — Open-Meteo (London)
WEATHER_LAT = 51.5074
WEATHER_LON = -0.1278
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_INTERVAL = 1800  # 30 minutes

# News refresh interval
NEWS_INTERVAL = 900  # 15 minutes

# Ollama
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_SUMMARY_DELAY = 3  # seconds between summaries
OLLAMA_ENABLED = True

# Market tickers
MARKET_INTERVAL = 300  # 5 minutes

# GitHub activity
GITHUB_INTERVAL = 300  # 5 minutes

# Google Calendar (set GOOGLE_CALENDAR_ICS env var)
GOOGLE_CALENDAR_ICS = os.environ.get("GOOGLE_CALENDAR_ICS", "")
CALENDAR_INTERVAL = 600  # 10 minutes

# Docker socket
DOCKER_SOCKET = "/var/run/docker.sock"

# RSS Feeds — Finance / Economics
FINANCE_FEEDS = [
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "finance"),
    ("Financial Times", "https://www.ft.com/rss/home", "finance"),
    ("The Economist", "https://www.economist.com/finance-and-economics/rss.xml", "finance"),
    ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/", "finance"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "finance"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "finance"),
]

# RSS Feeds — Tech / Science
TECH_FEEDS = [
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "tech"),
    ("TechCrunch", "https://techcrunch.com/feed/", "tech"),
    ("Nature", "https://www.nature.com/nature.rss", "tech"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/", "tech"),
]

# Hacker News API
HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_MAX_STORIES = 20

# Articles per category to display
ARTICLES_PER_CATEGORY = 15
