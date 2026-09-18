"""Custom RSS feed aggregator."""

import httpx
import feedparser
from datetime import datetime
from app.config import CUSTOM_FEEDS, CUSTOM_FEED_MAX

_cache: list[dict] = []


async def refresh_custom_feeds():
    global _cache
    items = []
    # hnrss.org connects slowly and unevenly from the Pi (1–6s), so give it a
    # generous timeout and one retry; a single blip shouldn't blank the panel.
    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; PiDashboard/1.0)"},
    ) as client:
        for name, url in CUSTOM_FEEDS:
            for attempt in range(2):
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:CUSTOM_FEED_MAX]:
                        pub = ""
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            pub = datetime(*entry.published_parsed[:6]).strftime("%d %b")
                        items.append({
                            "title": entry.get("title", ""),
                            "url": entry.get("link", ""),
                            "source": name,
                            "published": pub,
                        })
                    break  # success — stop retrying this feed
                except Exception as e:
                    if attempt == 0:
                        continue  # transient — retry once
                    # type name matters: timeout exceptions have an empty str(e)
                    print(f"[customfeed] error fetching {name}: {type(e).__name__}: {e}")

    # Keep the last good cache on a fully-failed refresh instead of blanking it.
    if items:
        _cache = items[:CUSTOM_FEED_MAX * 2]
        print(f"[customfeed] refreshed {len(_cache)} items")
    else:
        print(f"[customfeed] refresh failed; keeping {len(_cache)} cached items")


def get_custom_feeds() -> list[dict]:
    return _cache
