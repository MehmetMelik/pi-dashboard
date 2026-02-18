"""News fetching: RSS feeds + Hacker News JSON API."""

import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from app.config import (
    FINANCE_FEEDS,
    TECH_FEEDS,
    HN_TOP_URL,
    HN_ITEM_URL,
    HN_MAX_STORIES,
    ARTICLES_PER_CATEGORY,
)
from app.database import save_articles, load_articles


def _parse_date(entry) -> str | None:
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                return dt.isoformat()
            except Exception:
                return raw
    return None


def _clean_summary(entry) -> str | None:
    summary = entry.get("summary", "")
    if not summary:
        return None
    clean = re.sub(r"<[^>]+>", "", summary)
    clean = clean.strip()
    if len(clean) > 300:
        clean = clean[:297] + "..."
    return clean if clean else None


def _extract_image(entry) -> str | None:
    """Extract image URL from RSS entry using various feed formats."""
    # 1. media:thumbnail (common in many feeds)
    thumbnails = entry.get("media_thumbnail", [])
    if thumbnails and isinstance(thumbnails, list):
        url = thumbnails[0].get("url", "")
        if url:
            return url

    # 2. media:content with type image
    media = entry.get("media_content", [])
    if media and isinstance(media, list):
        for m in media:
            mtype = m.get("medium", "") or m.get("type", "")
            url = m.get("url", "")
            if url and ("image" in mtype or url.endswith((".jpg", ".jpeg", ".png", ".webp"))):
                return url
        # Fallback: first media_content with a url
        if media[0].get("url"):
            return media[0]["url"]

    # 3. enclosure with image type
    enclosures = entry.get("enclosures", [])
    if enclosures:
        for enc in enclosures:
            etype = enc.get("type", "")
            url = enc.get("href", "") or enc.get("url", "")
            if url and "image" in etype:
                return url

    # 4. Try to find image in summary/content HTML
    for field in ("summary", "content"):
        html = ""
        val = entry.get(field, "")
        if isinstance(val, list) and val:
            html = val[0].get("value", "")
        elif isinstance(val, str):
            html = val
        if html:
            match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
            if match:
                img_url = match.group(1)
                if img_url.startswith("http") and not "tracking" in img_url.lower() and not "pixel" in img_url.lower():
                    return img_url

    return None


async def _fetch_og_image(url: str, client: httpx.AsyncClient) -> str | None:
    """Fetch og:image from a URL's HTML head."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=8)
        if resp.status_code != 200:
            return None
        # Only parse first 20KB to find og:image quickly
        text = resp.text[:20000]
        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', text, re.IGNORECASE)
        if not match:
            match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', text, re.IGNORECASE)
        if match:
            img = match.group(1)
            if img.startswith("http"):
                return img
    except Exception:
        pass
    return None


def fetch_rss_feeds(feeds: list[tuple]) -> list[dict]:
    articles = []
    for source, url, category in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue
                articles.append({
                    "source": source,
                    "category": category,
                    "title": title,
                    "url": link,
                    "published": _parse_date(entry),
                    "summary": _clean_summary(entry),
                    "image_url": _extract_image(entry),
                    "score": 0,
                })
        except Exception as e:
            print(f"[news] RSS error for {source}: {e}")
    return articles


async def fetch_hacker_news() -> list[dict]:
    articles = []
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "PiDashboard/1.0"}) as client:
            resp = await client.get(HN_TOP_URL)
            resp.raise_for_status()
            story_ids = resp.json()[:HN_MAX_STORIES]

            for i, sid in enumerate(story_ids):
                try:
                    r = await client.get(HN_ITEM_URL.format(sid))
                    r.raise_for_status()
                    item = r.json()
                    if not item or item.get("type") != "story":
                        continue
                    title = item.get("title", "").strip()
                    url = item.get("url", f"https://news.ycombinator.com/item?id={sid}")

                    # Fetch og:image for top 5 stories that have external URLs
                    image_url = None
                    if i < 5 and item.get("url"):
                        image_url = await _fetch_og_image(item["url"], client)

                    articles.append({
                        "source": "Hacker News",
                        "category": "tech",
                        "title": title,
                        "url": url,
                        "published": datetime.fromtimestamp(item.get("time", 0)).isoformat() if item.get("time") else None,
                        "summary": None,
                        "image_url": image_url,
                        "score": item.get("score", 0),
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"[news] HN error: {e}")
    return articles


async def fetch_all_news():
    finance = fetch_rss_feeds(FINANCE_FEEDS)
    tech = fetch_rss_feeds(TECH_FEEDS)
    hn = await fetch_hacker_news()

    # For finance articles without images, try og:image for top ones
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "PiDashboard/1.0"}) as client:
        no_img = [a for a in finance if not a.get("image_url")]
        for a in no_img[:5]:
            img = await _fetch_og_image(a["url"], client)
            if img:
                a["image_url"] = img
        no_img_tech = [a for a in tech if not a.get("image_url")]
        for a in no_img_tech[:5]:
            img = await _fetch_og_image(a["url"], client)
            if img:
                a["image_url"] = img

    all_articles = finance + tech + hn
    if all_articles:
        save_articles(all_articles)
    img_count = sum(1 for a in all_articles if a.get("image_url"))
    print(f"[news] saved {len(all_articles)} articles ({img_count} with images)")


def get_finance_articles() -> list[dict]:
    return load_articles("finance", ARTICLES_PER_CATEGORY)


def get_tech_articles() -> list[dict]:
    return load_articles("tech", ARTICLES_PER_CATEGORY)
