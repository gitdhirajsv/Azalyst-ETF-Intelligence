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
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List

log = logging.getLogger("azalyst.scorer")

# Source credibility tiers (higher tier = more weight in source diversity score).
#
# FIX: Replaced exact-substring matching (e.g. "ap ", "ft ") with a set of
# normalised tokens that are matched against the lowercased source name after
# stripping punctuation.  The old approach had two failure modes:
#   1. "ap " missed "AP News", "Associated Press", "AP/" variants.
#   2. "ft " false-positived on any source containing "ft " (e.g. "left ").
# Now each entry is a standalone word/phrase that must appear as a word boundary
# inside the source name, handled by _source_in_tier().
SOURCE_TIERS = {
    "tier1": {
        "reuters", "bbc", "bloomberg", "wsj", "wall street journal",
        "financial times", "associated press", "ap news",
        "new york times", "nyt", "economic times", "cnbc",
    },
    "tier2": {
        "sky news", "dw", "al jazeera", "the guardian", "axios",
        "defense news", "oilprice", "worldmonitor", "zero hedge",
        "zerohedge",
    },
}

SEVERITY_WEIGHTS = {
    "CRITICAL": 15,
    "HIGH":     10,
    "MEDIUM":   6,
    "LOW":      3,
}

REGION_WEIGHTS = {
    "middle_east":  5,   # high geopolitical impact on commodities
    "europe":       4,
    "asia_pacific": 4,
    "americas":     3,
    "india":        2,
    "africa":       2,
    "global":       1,
}


def _source_in_tier(source_lower: str, tier_tokens: set) -> bool:
    """
    Return True if any tier token appears as a meaningful substring in
    the source name (lowercased).  Uses word-boundary logic: the token
    must either start the string, end it, or be surrounded by
    non-alphanumeric characters.
    """
    import re
    for token in tier_tokens:
        # Escape for regex, then wrap in word-boundary-like assertion
        pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
        if re.search(pattern, source_lower):
            return True
    return False


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
        Smoothly saturating score from total keyword intensity.
        25 pts max.
        """
        total_score = max(float(signal.get("total_score", 0) or 0), 0.0)
        avg_score = max(float(signal.get("avg_article_score", 0) or 0), 0.0)
        if total_score <= 0:
            return 0.0
        score = 25.0 * (1 - math.exp(-total_score / 55.0))
        if avg_score > 0:
            score += min(avg_score / 15.0, 1.0) * 2.0
        return min(score, 25.0)

    # ── Factor 2: Volume Confirmation ─────────────────────────────────────
    def _factor_volume(self, signal: Dict) -> float:
        """
        More corroborating articles help, but with diminishing returns.
        20 pts max.
        """
        count = signal.get("article_count", 0)
        if count < 2:
            return 0.0
        normalized = math.log1p(max(count - 1, 0)) / math.log1p(12)
        return min(max(normalized, 0.0) * 20.0, 20.0)

    # ── Factor 3: Source Diversity ────────────────────────────────────────
    def _factor_source_diversity(self, signal: Dict) -> float:
        """
        Independent source confirmation raises confidence.
        20 pts max. Higher-quality sources count more, but breadth matters too.
        """
        sources = {s.lower() for s in signal.get("sources", [])}
        tier1_hits = 0
        tier2_hits = 0
        tier3_hits = 0

        for src in sources:
            if _source_in_tier(src, SOURCE_TIERS["tier1"]):
                tier1_hits += 1
            elif _source_in_tier(src, SOURCE_TIERS["tier2"]):
                tier2_hits += 1
            elif src:
                # Penalize crypto sources in non-crypto sectors
                is_crypto_source = any(crypto_term in src for crypto_term in ["cointelegraph", "coinbase", "crypto", "bitcoin"])
                is_crypto_sector = "crypto" in signal.get("sector_label", "").lower() or "crypto" in "".join(signal.get("sectors", [])).lower()
                if is_crypto_source and not is_crypto_sector:
                    tier3_hits += 0.1  # Minimal weight for irrelevant crypto sources
                else:
                    tier3_hits += 1    # Normal weight

        weighted_sources = tier1_hits * 1.6 + tier2_hits * 1.0 + tier3_hits * 0.6
        return min(20.0 * (1 - math.exp(-weighted_sources / 4.0)), 20.0)

    # ── Factor 4: Recency ─────────────────────────────────────────────────
    def _factor_recency(self, signal: Dict) -> float:
        """
        Exponential time decay from the latest supporting article.
        """
        try:
            latest = signal.get("latest_ts")
            if not latest:
                return 0.0
            now = datetime.now(timezone.utc)
            if isinstance(latest, datetime) and latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            age = now - latest
            age_hours = max(age.total_seconds() / 3600.0, 0.0)
            if age_hours > 24 * 7:
                return 0.0
            return min(20.0 * math.exp(-age_hours / 10.0), 20.0)
        except Exception:
            return 0.0

    # ── Factor 5: Geopolitical Severity ──────────────────────────────────
    def _factor_geopolitical_severity(self, signal: Dict) -> float:
        """
        Event intensity + region impact.
        15 pts max.
        """
        severity = signal.get("severity", "LOW")
        sev_score = SEVERITY_WEIGHTS.get(severity, 3)
        event_intensity = float(signal.get("event_intensity", 0.0) or 0.0)

        regions = signal.get("regions", ["global"])
        max_region = max(
            (REGION_WEIGHTS.get(r, 1) for r in regions),
            default=1,
        )
        cross_region_bonus = min(max(len(set(regions)) - 1, 0), 2) * 0.75
        intensity_component = min(event_intensity / 2.0, 8.5)
        severity_component = min(sev_score * 0.25, 3.0)
        region_component = min(max_region * 0.75, 3.5)

        return min(intensity_component + severity_component + region_component + cross_region_bonus, 15.0)
