"""
news_fetcher.py — AZALYST Multi-Source News Ingestion

Fetches from:
  1. worldmonitor.app RSS proxy API (primary — geopolitical filtered)
  2. Direct RSS feeds (financial, energy, defense, tech, India)

Returns normalized article dicts:
  {
    "id":          str (sha256 hash of url/title),
    "title":       str,
    "description": str,
    "url":         str,
    "source":      str,
    "published":   datetime,
    "region":      str,   # inferred
    "raw_text":    str,   # title + description concatenated for classification
  }
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from typing import List, Dict

import feedparser
import requests

log = logging.getLogger("azalyst.fetcher")

# ── Region keyword classifier ────────────────────────────────────────────────
REGION_KEYWORDS = {
    "middle_east":   ["israel", "iran", "gaza", "hamas", "hezbollah", "yemen",
                      "saudi", "riyadh", "tehran", "beirut", "lebanon", "jordan",
                      "iraq", "baghdad", "persian gulf", "red sea", "hormuz"],
    "europe":        ["ukraine", "russia", "nato", "eu ", "european", "germany",
                      "france", "uk ", "britain", "london", "berlin", "paris",
                      "poland", "baltic", "kremlin", "moscow", "kyiv"],
    "asia_pacific":  ["china", "taiwan", "south china sea", "japan", "korea",
                      "beijing", "tokyo", "seoul", "philippines", "india",
                      "pakistan", "myanmar", "vietnam", "asean"],
    "americas":      ["usa", "united states", "fed ", "federal reserve", "wall street",
                      "washington", "canada", "mexico", "brazil", "latin america",
                      "venezuela", "colombia"],
    "africa":        ["africa", "nigeria", "kenya", "ethiopia", "egypt", "sudan",
                      "sahel", "congo"],
    "global":        ["global", "world", "international", "imf", "world bank",
                      "wto", "opec", "g7", "g20", "united nations"],
    "india":         ["india", "rbi", "nifty", "sensex", "sebi", "modi",
                      "mumbai", "delhi", "rupee", "bse", "nse"],
}


def infer_region(text: str) -> str:
    text_lower = text.lower()
    for region, keywords in REGION_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return region
    return "global"


def parse_date(entry) -> datetime:
    """Parse RSS date fields into UTC datetime."""
    for field in ("published", "updated", "created"):
        val = getattr(entry, field, None) or entry.get(field)
        if val:
            try:
                return parsedate_to_datetime(val).astimezone(timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def hash_id(url: str, title: str) -> str:
    key = (url or "") + "|" + (title or "")
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def fetch_feed(url: str, timeout: int, source_name: str = None) -> List[Dict]:
    """Fetch and parse a single RSS/Atom feed. Returns list of article dicts."""
    articles = []
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; AzalystBot/1.0; "
                "+https://github.com/azalyst) feedparser/6.0"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }

        # Use requests for fetching (better timeout handling than feedparser)
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        source = source_name or (
            feed.feed.get("title", "") or url.split("/")[2]
        )

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            desc  = entry.get("summary", entry.get("description", "")).strip()
            # Strip HTML tags from description
            desc = re.sub(r"<[^>]+>", " ", desc)
            desc = re.sub(r"\s+", " ", desc).strip()
            link  = entry.get("link", "")

            if not title:
                continue

            raw_text = f"{title} {desc}"
            published = parse_date(entry)
            region = infer_region(raw_text)

            articles.append({
                "id":          hash_id(link, title),
                "title":       title,
                "description": desc[:500],
                "url":         link,
                "source":      source,
                "published":   published,
                "region":      region,
                "raw_text":    raw_text.lower(),
            })

    except requests.exceptions.Timeout:
        log.debug(f"Timeout fetching: {url[:80]}")
    except requests.exceptions.HTTPError as e:
        log.debug(f"HTTP {e.response.status_code} fetching: {url[:80]}")
    except Exception as e:
        log.debug(f"Error fetching {url[:80]}: {e}")

    return articles


class NewsFetcher:
    """
    Concurrent multi-source news fetcher.
    Deduplicates by article ID across all sources.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self._seen_ids = set()   # Cross-session dedup within a cycle

    def fetch_all(self) -> List[Dict]:
        all_articles: List[Dict] = []
        seen_this_cycle: set = set()

        # Combine worldmonitor proxy feeds + direct feeds
        all_feeds = []
        for url in self.cfg.WORLDMONITOR_RSS_FEEDS:
            all_feeds.append((url, "WorldMonitor"))
        for url in self.cfg.DIRECT_RSS_FEEDS:
            all_feeds.append((url, None))

        log.info(f"Fetching {len(all_feeds)} news sources concurrently...")

        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {
                executor.submit(fetch_feed, url, self.cfg.FETCH_TIMEOUT, name): url
                for url, name in all_feeds
            }
            for future in as_completed(futures):
                url = futures[future]
                try:
                    articles = future.result()
                    for art in articles:
                        if art["id"] not in seen_this_cycle:
                            seen_this_cycle.add(art["id"])
                            all_articles.append(art)
                    if articles:
                        log.debug(f"  ✓ {len(articles)} articles — {url[:60]}")
                except Exception as e:
                    log.debug(f"  ✗ Error from {url[:60]}: {e}")

        # Sort by recency
        all_articles.sort(key=lambda x: x["published"], reverse=True)

        # Cap at max articles for performance
        all_articles = all_articles[: self.cfg.MAX_ARTICLES_PER_CYCLE]

        log.info(
            f"Total articles after dedup: {len(all_articles)} "
            f"(from {len(seen_this_cycle)} unique)"
        )
        return all_articles
