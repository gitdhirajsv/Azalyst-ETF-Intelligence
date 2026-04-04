"""
config.py - AZALYST runtime configuration.

Environment variables are loaded from a local .env file when python-dotenv is
available. Both the short README-friendly names (for example WEBHOOK) and the
existing AZALYST_* variables are supported.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional until dependencies are installed
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parent

if load_dotenv:
    load_dotenv(ROOT_DIR / ".env", override=False)


def _get_env(*names, default=None):
    """Return the first non-empty environment variable value from names."""
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return default


class Config:
    # Discord delivery
    DISCORD_WEBHOOK_URL = _get_env(
        "AZALYST_DISCORD_WEBHOOK",
        "DISCORD_WEBHOOK_URL",
        "WEBHOOK",
        default="",
    )

    # Polling
    POLL_INTERVAL_MINUTES = int(_get_env("AZALYST_INTERVAL", "INTERVAL", default="30"))

    # Signal thresholds
    CONFIDENCE_THRESHOLD = int(_get_env("AZALYST_THRESHOLD", "THRESHOLD", default="62"))
    MIN_ARTICLES_FOR_SIGNAL = int(
        _get_env("AZALYST_MIN_ARTICLES", "MIN_ARTICLES", default="2")
    )

    # Deduplication and update logic
    SIGNAL_COOLDOWN_HOURS = int(
        _get_env("AZALYST_COOLDOWN_HOURS", "COOLDOWN_HOURS", default="4")
    )
    UPDATE_THRESHOLD_HOURS = int(
        _get_env("AZALYST_UPDATE_HOURS", "UPDATE_HOURS", default="2")
    )
    UPDATE_CONFIDENCE_DELTA = int(
        _get_env("AZALYST_UPDATE_DELTA", "UPDATE_DELTA", default="10")
    )

    # State persistence
    STATE_FILE = _get_env("AZALYST_STATE_FILE", "STATE_FILE", default="azalyst_state.json")
    PORTFOLIO_FILE = _get_env(
        "AZALYST_PORTFOLIO_FILE",
        "PORTFOLIO_FILE",
        default="azalyst_portfolio.json",
    )

    # Paper-trading utilities
    PAPER_TRADING_ENABLED = (
        _get_env("AZALYST_PAPER_TRADING", "PAPER_TRADING", default="true").lower()
        == "true"
    )
    EOD_REPORT_HOUR = int(
        _get_env("AZALYST_EOD_HOUR", "EOD_REPORT_HOUR", default="15")
    )
    EOD_REPORT_MINUTE = int(
        _get_env("AZALYST_EOD_MINUTE", "EOD_REPORT_MINUTE", default="30")
    )
    MTM_INTERVAL_MINUTES = int(
        _get_env("AZALYST_MTM_INTERVAL", "MTM_INTERVAL", default="60")
    )

    # News sources
    WORLDMONITOR_RSS_FEEDS = [
        "https://api.worldmonitor.app/api/rss?url=https://feeds.reuters.com/reuters/topNews",
        "https://api.worldmonitor.app/api/rss?url=https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://api.worldmonitor.app/api/rss?url=https://rss.dw.com/rdf/rss-en-world",
        "https://api.worldmonitor.app/api/rss?url=https://feeds.skynews.com/feeds/rss/world.xml",
    ]

    DIRECT_RSS_FEEDS = [
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://a.dj.com/rss/RSSWorldNews.xml",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "https://oilprice.com/rss/main",
        "https://feeds.feedburner.com/TechCrunch",
        "https://www.theverge.com/rss/index.xml",
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://feeds.feedburner.com/ndtvnews-business",
        "https://www.defensenews.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://www.zerohedge.com/fullrss2.xml",
    ]

    FETCH_TIMEOUT = int(_get_env("AZALYST_TIMEOUT", "TIMEOUT", default="12"))
    MAX_ARTICLES_PER_CYCLE = int(
        _get_env("AZALYST_MAX_ARTICLES", "MAX_ARTICLES", default="300")
    )
    # Drop articles older than this many days before classification (0 = no filter)
    MAX_ARTICLE_AGE_DAYS = int(
        _get_env("AZALYST_MAX_ARTICLE_AGE", "MAX_ARTICLE_AGE_DAYS", default="7")
    )
    FUZZY_TITLE_DEDUP_THRESHOLD = float(
        _get_env(
            "AZALYST_FUZZY_TITLE_DEDUP_THRESHOLD",
            "FUZZY_TITLE_DEDUP_THRESHOLD",
            default="0.92",
        )
    )

    # Optional ML sentiment layer
    ML_SENTIMENT_ENABLED = (
        _get_env("AZALYST_ML_SENTIMENT_ENABLED", "ML_SENTIMENT_ENABLED", default="true").lower()
        == "true"
    )
    ML_SENTIMENT_MODE = _get_env(
        "AZALYST_ML_SENTIMENT_MODE",
        "ML_SENTIMENT_MODE",
        default="shadow",
    ).lower()
    ML_SENTIMENT_MODEL = _get_env(
        "AZALYST_ML_SENTIMENT_MODEL",
        "ML_SENTIMENT_MODEL",
        default="ProsusAI/finbert",
    )
    ML_SENTIMENT_MIN_CONFIDENCE = float(
        _get_env(
            "AZALYST_ML_SENTIMENT_MIN_CONFIDENCE",
            "ML_SENTIMENT_MIN_CONFIDENCE",
            default="0.58",
        )
    )
    LOG_LEVEL = _get_env("AZALYST_LOG_LEVEL", "LOG_LEVEL", default="INFO")
