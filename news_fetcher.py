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
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
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
    now = datetime.now(timezone.utc)
    for field in ("published", "updated", "created"):
        val = getattr(entry, field, None) or entry.get(field)
        if val:
            try:
                parsed = parsedate_to_datetime(val).astimezone(timezone.utc)
                if parsed > now + timedelta(days=1):
                    return now
                if parsed.year < 2000:
                    return now
                return parsed
            except Exception:
                pass
    return now


def hash_id(url: str, title: str) -> str:
    key = (url or "") + "|" + (title or "")
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _normalise_title(title: str) -> str:
    text = re.sub(r"<[^>]+>", " ", title or "")
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _titles_too_similar(title_a: str, title_b: str, threshold: float) -> bool:
    if not title_a or not title_b:
        return False
    if title_a == title_b:
        return True
    if len(title_a) < 18 or len(title_b) < 18:
        return False
    return SequenceMatcher(None, title_a, title_b).ratio() >= threshold


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

            raw_text  = f"{title} {desc}"
            published = parse_date(entry)
            region    = infer_region(raw_text)

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
    Filters out articles older than MAX_ARTICLE_AGE_DAYS to prevent
    stale evergreen content (e.g. 2022/2023 how-to articles) from
    inflating signal scores.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self._seen_ids = set()   # Cross-session dedup within a cycle
        # FIX: age filter — drop articles older than configured threshold
        self._max_age_days: int = getattr(cfg, "MAX_ARTICLE_AGE_DAYS", 7)
        self._title_similarity_threshold: float = max(
            0.80,
            min(float(getattr(cfg, "FUZZY_TITLE_DEDUP_THRESHOLD", 0.92)), 0.99),
        )

    def fetch_all(self) -> List[Dict]:
        all_articles: List[Dict] = []
        seen_this_cycle: set = set()
        seen_titles: List[str] = []
        cutoff: datetime = (
            datetime.now(timezone.utc) - timedelta(days=self._max_age_days)
            if self._max_age_days > 0
            else None
        )

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
                        if art["id"] in seen_this_cycle:
                            continue
                        norm_title = _normalise_title(art.get("title", ""))
                        if norm_title and any(
                            _titles_too_similar(norm_title, prior, self._title_similarity_threshold)
                            for prior in seen_titles
                        ):
                            continue
                        # FIX: drop articles older than the age cutoff.
                        # This prevents evergreen "best of 2022" style articles
                        # from scoring as fresh signals.
                        if cutoff is not None:
                            pub = art["published"]
                            if pub.tzinfo is None:
                                pub = pub.replace(tzinfo=timezone.utc)
                            if pub < cutoff:
                                continue
                        seen_this_cycle.add(art["id"])
                        if norm_title:
                            seen_titles.append(norm_title)
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
            f"Total articles after dedup + age filter: {len(all_articles)} "
            f"(from {len(seen_this_cycle)} unique)"
        )
        return all_articles
