"""
scorer.py — AZALYST Confidence Scoring Model

5-factor confidence model (institutional grade):

  Factor 1: Signal Strength       (0–25 pts) — weighted keyword score
  Factor 2: Volume Confirmation   (0–20 pts) — number of corroborating articles
  Factor 3: Source Diversity      (0–20 pts) — number of independent sources
  Factor 4: Recency               (0–20 pts) — how fresh is the news
  Factor 5: Geopolitical Severity (0–15 pts) — severity tag + region

Final score = sum of all factors, capped at 100.
Only signals >= threshold (default 62) are reported.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

log = logging.getLogger("azalyst.scorer")

# Source credibility tiers (higher tier = more weight in source diversity score)
SOURCE_TIERS = {
    "tier1": {
        "reuters", "bbc", "bloomberg", "wsj", "wall street journal",
        "financial times", "ft ", "ap ", "associated press", "nyt",
        "new york times", "economic times", "cnbc",
    },
    "tier2": {
        "sky news", "dw", "al jazeera", "cnbc", "the guardian", "axios",
        "defense news", "oilprice", "worldmonitor", "zero hedge",
    },
}

SEVERITY_WEIGHTS = {
    "CRITICAL": 15,
    "HIGH":     10,
    "MEDIUM":   6,
    "LOW":      3,
}

REGION_WEIGHTS = {
    "middle_east": 5,   # high geopolitical impact on commodities
    "europe":      4,
    "asia_pacific": 4,
    "americas":    3,
    "india":       2,
    "africa":      2,
    "global":      1,
}


class ConfidenceScorer:
    """
    Scores sector signals on a 0–100 scale.
    """

    def __init__(self, cfg):
        self.cfg = cfg

    def score(self, signal: Dict, all_articles: List[Dict]) -> int:
        """Compute final confidence score (0–100) for a signal."""
        f1 = self._factor_signal_strength(signal)
        f2 = self._factor_volume(signal)
        f3 = self._factor_source_diversity(signal)
        f4 = self._factor_recency(signal)
        f5 = self._factor_geopolitical_severity(signal)

        raw = f1 + f2 + f3 + f4 + f5
        return min(int(raw), 100)

    def breakdown(self, signal: Dict, all_articles: List[Dict]) -> Dict:
        """Return component breakdown for transparency in report."""
        return {
            "signal_strength":       round(self._factor_signal_strength(signal), 1),
            "volume_confirmation":   round(self._factor_volume(signal), 1),
            "source_diversity":      round(self._factor_source_diversity(signal), 1),
            "recency":               round(self._factor_recency(signal), 1),
            "geopolitical_severity": round(self._factor_geopolitical_severity(signal), 1),
        }

    # ── Factor 1: Signal Strength ─────────────────────────────────────────
    def _factor_signal_strength(self, signal: Dict) -> float:
        """
        Normalized from total keyword score.
        25 pts max.
        """
        ts = signal.get("total_score", 0)
        # Normalize: score of 80+ → full 25 pts
        return min(ts / 80 * 25, 25)

    # ── Factor 2: Volume Confirmation ─────────────────────────────────────
    def _factor_volume(self, signal: Dict) -> float:
        """
        More articles covering same theme = stronger signal.
        20 pts max.
        Scale: 2 articles → 5pts, 5 → 12pts, 10+ → 20pts
        """
        count = signal.get("article_count", 0)
        if count >= 10:
            return 20.0
        elif count >= 7:
            return 16.0
        elif count >= 5:
            return 12.0
        elif count >= 3:
            return 8.0
        elif count >= 2:
            return 5.0
        return 0.0

    # ── Factor 3: Source Diversity ────────────────────────────────────────
    def _factor_source_diversity(self, signal: Dict) -> float:
        """
        Independent source confirmation raises confidence.
        20 pts max. Tier-1 sources worth more.
        """
        sources = {s.lower() for s in signal.get("sources", [])}
        score = 0.0

        tier1_hits = 0
        tier2_hits = 0
        for src in sources:
            if any(t in src for t in SOURCE_TIERS["tier1"]):
                tier1_hits += 1
            elif any(t in src for t in SOURCE_TIERS["tier2"]):
                tier2_hits += 1

        score += tier1_hits * 5.0   # up to 4 tier1 sources = 20pts
        score += tier2_hits * 2.5

        return min(score, 20.0)

    # ── Factor 4: Recency ─────────────────────────────────────────────────
    def _factor_recency(self, signal: Dict) -> float:
        """
        How fresh is the most recent article?
        20 pts max.
        < 1hr  → 20pts
        < 3hr  → 15pts
        < 6hr  → 10pts
        < 12hr → 6pts
        < 24hr → 3pts
        older  → 0pts
        """
        try:
            latest = signal.get("latest_ts")
            if not latest:
                return 5.0
            now = datetime.now(timezone.utc)
            age = now - latest
            if age < timedelta(hours=1):
                return 20.0
            elif age < timedelta(hours=3):
                return 15.0
            elif age < timedelta(hours=6):
                return 10.0
            elif age < timedelta(hours=12):
                return 6.0
            elif age < timedelta(hours=24):
                return 3.0
            return 0.0
        except Exception:
            return 5.0

    # ── Factor 5: Geopolitical Severity ──────────────────────────────────
    def _factor_geopolitical_severity(self, signal: Dict) -> float:
        """
        Severity tag + region impact.
        15 pts max.
        """
        severity = signal.get("severity", "LOW")
        sev_score = SEVERITY_WEIGHTS.get(severity, 3)

        # Best region score from detected regions
        regions = signal.get("regions", ["global"])
        reg_score = max(
            (REGION_WEIGHTS.get(r, 1) for r in regions),
            default=1,
        )

        return min(sev_score + reg_score, 15.0)
