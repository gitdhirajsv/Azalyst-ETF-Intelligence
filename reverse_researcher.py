"""
reverse_researcher.py — AZALYST Unexplained-Mover Investigator

When the price scanner flags a 5-sigma move but the news engine produced no
matching sector signal, that is a known-unknown — there is a story behind
the price action that our RSS feeds didn't surface.

This module is triggered ONLY for those unexplained movers. It:

  1. Pulls the most recent headlines for the moving ticker from yfinance's
     news endpoint (uses Yahoo Finance's public news graph).
  2. Pulls headlines for known catalyst tickers in the same sector
     (e.g. NVDA + TSM + AVGO when SOXX moves).
  3. Feeds those headlines back into the SectorClassifier, this time at
     a lower MIN_ARTICLES threshold (1 instead of 2) since price has
     already confirmed the signal.
  4. If keywords still don't match, returns the raw headlines as
     "unknown_catalyst" evidence so the analyst can investigate manually
     or feed them to the daily LLM self-improver.

This closes the loop: price-led discovery + news-confirmed conviction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import yfinance as yf

log = logging.getLogger("azalyst.reverse_researcher")


# Sector → catalyst tickers used to seed the news search.
# When XLE moves, also pull headlines for XOM, CVX, the OPEC tag etc.
SECTOR_CATALYST_TICKERS: Dict[str, List[str]] = {
    "energy_oil": ["XOM", "CVX", "COP", "SLB", "USO", "XLE"],
    "defense": ["RTX", "LMT", "NOC", "GD", "BA", "ITA"],
    "gold_precious_metals": ["GLD", "GDX", "NEM", "GOLD", "AEM"],
    "technology_ai": ["NVDA", "TSM", "AVGO", "ASML", "AMD", "MU", "SOXX", "SMH"],
    "nuclear_uranium": ["CCJ", "URA", "URNM", "NXE", "UEC"],
    "cybersecurity": ["CRWD", "PANW", "FTNT", "ZS", "HACK"],
    "india_equity": ["INDA", "INFY", "HDB", "RELIANCE.NS"],
    "crypto_digital": ["BTC-USD", "ETH-USD", "COIN", "MSTR", "IBIT"],
    "banking_financial": ["JPM", "BAC", "WFC", "GS", "XLF"],
    "commodities_mining": ["FCX", "BHP", "RIO", "DBC", "COPX"],
    "emerging_markets": ["EEM", "FXI", "BABA", "TSM", "EWZ"],
    "healthcare_pharma": ["LLY", "UNH", "JNJ", "ABBV", "XLV"],
    "clean_energy_renewables": ["FSLR", "ENPH", "TSLA", "ICLN", "TAN"],
    "real_estate_reit": ["VNQ", "AMT", "PLD", "EQIX", "O"],
    "bonds_fixed_income": ["TLT", "AGG", "TIP", "LQD", "HYG"],
    "asia_pacific": ["EWJ", "EWY", "EWT", "TM", "SSNLF"],
    "europe_equity": ["VGK", "EWG", "EWU", "ASML", "NESN.SW"],
}


@dataclass
class HeadlineEvidence:
    ticker: str
    title: str
    publisher: str
    url: str
    published_at: datetime
    related_tickers: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Researcher
# ─────────────────────────────────────────────────────────────────────────────
class ReverseResearcher:
    """
    For each unexplained price-action signal, fetch fresh headlines and
    re-feed them through the classifier with a relaxed threshold.
    """

    MAX_HEADLINES_PER_TICKER = 8
    MAX_AGE_HOURS = 72   # ignore stale news

    def __init__(self, classifier, max_seed_tickers: int = 4):
        """
        classifier : a SectorClassifier instance (the existing one).
        max_seed_tickers : how many sector-catalyst tickers to pull headlines
                           for, in addition to the moving ETF itself.
        """
        self.classifier = classifier
        self.max_seed_tickers = max_seed_tickers

    def _fetch_headlines(self, ticker: str) -> List[HeadlineEvidence]:
        """yfinance exposes Yahoo's news graph for any ticker via .news."""
        out: List[HeadlineEvidence] = []
        try:
            t = yf.Ticker(ticker)
            news = t.news or []
        except Exception as exc:
            log.debug("yfinance news fetch failed for %s: %s", ticker, exc)
            return out

        now = datetime.now(timezone.utc)
        for item in news[: self.MAX_HEADLINES_PER_TICKER * 2]:
            content = item.get("content", item)  # yfinance API variants
            title = (content.get("title") or "").strip()
            pub = (content.get("provider") or {}).get("displayName") or content.get("publisher", "")
            url = (content.get("clickThroughUrl") or {}).get("url") or content.get("link", "")

            ts_raw = (
                content.get("pubDate")
                or content.get("displayTime")
                or content.get("providerPublishTime")
            )
            if isinstance(ts_raw, (int, float)):
                published = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            elif isinstance(ts_raw, str):
                try:
                    published = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except Exception:
                    published = now
            else:
                published = now

            age_hours = (now - published).total_seconds() / 3600
            if age_hours > self.MAX_AGE_HOURS:
                continue
            if not title:
                continue

            related = []
            for sub in (content.get("finance", {}).get("stockTickers", []) or []):
                sym = sub.get("symbol")
                if sym:
                    related.append(sym)

            out.append(HeadlineEvidence(
                ticker=ticker,
                title=title,
                publisher=str(pub),
                url=str(url),
                published_at=published,
                related_tickers=related,
            ))
            if len(out) >= self.MAX_HEADLINES_PER_TICKER:
                break
        return out

    def _build_synthetic_articles(self,
                                  evidences: List[HeadlineEvidence],
                                  sector_id: str) -> List[Dict]:
        """Wrap headlines in the article-dict shape the classifier expects."""
        articles: List[Dict] = []
        for i, e in enumerate(evidences):
            articles.append({
                "id": f"rev_{sector_id}_{i}_{e.ticker}",
                "title": e.title,
                "description": e.title,                  # yfinance has no body
                "raw_text": e.title,
                "published": e.published_at,
                "source": e.publisher or "yahoo_finance",
                "region": "global",
                "url": e.url,
                "via": "reverse_researcher",
                "seed_ticker": e.ticker,
            })
        return articles

    def explain(self, unexplained_price_signals: List[Dict]) -> List[Dict]:
        """
        For each input price-derived signal that has no news counterpart,
        fetch fresh headlines and try to classify them.

        Returns enriched signals with one of three outcomes:
          - ``news_confirmed``  : reverse-fetched news matched the sector
          - ``news_orthogonal`` : headlines came back but didn't match
          - ``no_news_found``   : no recent headlines retrieved
        """
        enriched: List[Dict] = []
        for sig in unexplained_price_signals:
            sector_id = sig.get("sector_id")
            if not sector_id:
                continue
            seed_tickers: List[str] = []
            driver = sig.get("ticker_driver")
            if driver:
                seed_tickers.append(driver)
            # Add sector catalyst tickers (limit to keep API calls bounded)
            for tk in SECTOR_CATALYST_TICKERS.get(sector_id, []):
                if tk not in seed_tickers:
                    seed_tickers.append(tk)
                if len(seed_tickers) >= self.max_seed_tickers + 1:
                    break

            evidences: List[HeadlineEvidence] = []
            for tk in seed_tickers:
                evidences.extend(self._fetch_headlines(tk))

            # Dedup by title
            seen: Set[str] = set()
            unique: List[HeadlineEvidence] = []
            for e in evidences:
                key = e.title.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(e)

            if not unique:
                sig["reverse_research"] = {
                    "outcome": "no_news_found",
                    "seeds": seed_tickers,
                    "headlines": [],
                }
                enriched.append(sig)
                continue

            # Build synthetic article batch and re-classify
            synth = self._build_synthetic_articles(unique, sector_id)

            # Lower threshold since price already confirmed the signal:
            # we accept a single matching article as evidence here.
            original_min = getattr(self.classifier, "min_articles", 2)
            try:
                self.classifier.min_articles = 1
                sub_signals = self.classifier.classify_articles(synth)
            finally:
                self.classifier.min_articles = original_min

            sector_match = next(
                (s for s in sub_signals if sector_id in s.get("sectors", [])),
                None,
            )

            if sector_match:
                sig["reverse_research"] = {
                    "outcome": "news_confirmed",
                    "seeds": seed_tickers,
                    "matched_sector_score": sector_match.get("total_score", 0),
                    "matched_direction": sector_match.get("direction"),
                    "headlines": [
                        {"ticker": e.ticker, "title": e.title,
                         "publisher": e.publisher, "url": e.url,
                         "published": e.published_at.isoformat()}
                        for e in unique[:6]
                    ],
                }
                # Boost the price signal with the news confirmation
                sig["news_confirmed"] = True
                sig["total_score"] = sig.get("total_score", 0) + sector_match.get("total_score", 0) * 0.4
                sig.setdefault("articles", []).extend(synth[:5])
                sig["article_count"] = sig.get("article_count", 0) + len(synth[:5])
            else:
                sig["reverse_research"] = {
                    "outcome": "news_orthogonal",
                    "seeds": seed_tickers,
                    "headlines": [
                        {"ticker": e.ticker, "title": e.title,
                         "publisher": e.publisher, "url": e.url,
                         "published": e.published_at.isoformat()}
                        for e in unique[:6]
                    ],
                    "note": "Price moved meaningfully but reverse-fetched "
                            "headlines did not match the sector keyword model. "
                            "Likely a missing keyword — feed to self_improve.",
                }
            enriched.append(sig)

        return enriched
