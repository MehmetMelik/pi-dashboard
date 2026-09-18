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

# AI summaries — produced by the news-firebase pipeline (a superset of these
# feeds, summarized with a local LLM, keyed by sha256(url)[:16]). The dashboard
# reuses those summaries instead of running its own summarizer.
#
# Primary source is a local SQLite mirror news-firebase writes on the same box —
# zero network, zero Firestore reads. Firestore is only a fallback used when that
# mirror file is absent (e.g. news-firebase hasn't created it yet). Read-only;
# degrades gracefully — unmatched articles just stay unsummarized and retry.
SUMMARY_MIRROR_PATH = os.environ.get(
    "SUMMARY_MIRROR_PATH", "/home/melik/dev/news-firebase/summaries.db"
)
FIRESTORE_ENABLED = True             # fallback only, when the local mirror is unavailable
FIREBASE_CRED_PATH = os.environ.get(
    "FIREBASE_CRED_PATH", "/home/melik/dev/news-firebase/service-account.json"
)
FIRESTORE_COLLECTION = "articles"
FIRESTORE_ENRICH_INTERVAL = 900     # seconds between enrichment passes
FIRESTORE_QUOTA_BACKOFF = 3600      # back off this long when the Firestore read quota is exhausted

# Market tickers
MARKET_INTERVAL = 300  # 5 minutes

# GitHub activity
GITHUB_INTERVAL = 300  # 5 minutes

# Google Calendar (set GOOGLE_CALENDAR_ICS env var)
GOOGLE_CALENDAR_ICS = os.environ.get("GOOGLE_CALENDAR_ICS", "")
CALENDAR_INTERVAL = 600  # 10 minutes

# Docker socket
DOCKER_SOCKET = "/var/run/docker.sock"

# Pi-hole
PIHOLE_INTERVAL = 300  # 5 minutes

# WireGuard
WIREGUARD_INTERVAL = 60  # 1 minute

# Service health
HEALTH_INTERVAL = 60  # 1 minute

# Speed test
SPEEDTEST_INTERVAL = 86400  # 24 hours

# Quick links
BOOKMARKS = [
    {"name": "Gitea", "url": "http://192.168.86.40:3300", "icon": "G"},
    {"name": "Pi-hole", "url": "http://192.168.86.40/admin", "icon": "P"},
    {"name": "Open WebUI", "url": "http://192.168.86.40:3000", "icon": "W"},
    {"name": "wg-easy", "url": "http://192.168.86.40:51821", "icon": "V"},
]

# Custom RSS feeds
CUSTOM_FEEDS = [
    ("Hacker News Best", "https://hnrss.org/best"),
]
CUSTOM_FEED_MAX = 10

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
