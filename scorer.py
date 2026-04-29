"""
scorer.py — AZALYST Confidence Scoring Model (6-factor, multi-engine aware)

  Factor 1: Signal Strength         (0–22 pts) — weighted keyword score
  Factor 2: Volume Confirmation     (0–18 pts) — corroborating articles
  Factor 3: Source Diversity        (0–18 pts) — independent sources
  Factor 4: Recency                 (0–17 pts) — freshness
  Factor 5: Geopolitical Severity   (0–13 pts) — severity tag + region
  Factor 6: Cross-Engine Confirmation (0–12 pts) — price-action / constituents
                                                   agree with the news signal

Total caps at 100. Threshold = 62 (configurable).

Factor 6 is the alpha-generating factor: it rewards signals where the news
narrative is corroborated by independent price action and stock-rotation
data. A news-only signal can still reach 88; only multi-engine consensus
can reach 100.
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
        f6 = self._factor_cross_engine_confirmation(signal)

        raw = f1 + f2 + f3 + f4 + f5 + f6
        return min(int(raw), 100)

    def breakdown(self, signal: Dict, all_articles: List[Dict]) -> Dict:
        """Return component breakdown for transparency in report."""
        return {
            "signal_strength":            round(self._factor_signal_strength(signal), 1),
            "volume_confirmation":        round(self._factor_volume(signal), 1),
            "source_diversity":           round(self._factor_source_diversity(signal), 1),
            "recency":                    round(self._factor_recency(signal), 1),
            "geopolitical_severity":      round(self._factor_geopolitical_severity(signal), 1),
            "cross_engine_confirmation":  round(self._factor_cross_engine_confirmation(signal), 1),
        }

    # ── Factor 1: Signal Strength ─────────────────────────────────────────
    def _factor_signal_strength(self, signal: Dict) -> float:
        """Smoothly saturating score from total keyword intensity. 22 pts max."""
        total_score = max(float(signal.get("total_score", 0) or 0), 0.0)
        avg_score = max(float(signal.get("avg_article_score", 0) or 0), 0.0)
        if total_score <= 0:
            return 0.0
        score = 22.0 * (1 - math.exp(-total_score / 55.0))
        if avg_score > 0:
            score += min(avg_score / 15.0, 1.0) * 1.8
        return min(score, 22.0)

    # ── Factor 2: Volume Confirmation ─────────────────────────────────────
    def _factor_volume(self, signal: Dict) -> float:
        """Diminishing returns from corroborating article count. 18 pts max."""
        count = signal.get("article_count", 0)
        if count < 2:
            return 0.0
        normalized = math.log1p(max(count - 1, 0)) / math.log1p(12)
        return min(max(normalized, 0.0) * 18.0, 18.0)

    # ── Factor 3: Source Diversity ────────────────────────────────────────
    def _factor_source_diversity(self, signal: Dict) -> float:
        """Independent source confirmation. 18 pts max. Tiered by quality."""
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
                is_crypto_source = any(crypto_term in src for crypto_term in
                                        ["cointelegraph", "coinbase", "crypto", "bitcoin"])
                is_crypto_sector = ("crypto" in signal.get("sector_label", "").lower()
                                    or "crypto" in "".join(signal.get("sectors", [])).lower())
                if is_crypto_source and not is_crypto_sector:
                    tier3_hits += 0.1
                else:
                    tier3_hits += 1

        weighted_sources = tier1_hits * 1.6 + tier2_hits * 1.0 + tier3_hits * 0.6
        return min(18.0 * (1 - math.exp(-weighted_sources / 4.0)), 18.0)

    # ── Factor 4: Recency ─────────────────────────────────────────────────
    def _factor_recency(self, signal: Dict) -> float:
        """Exponential time decay. 17 pts max."""
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
            if age_hours > 48:
                return max(17.0 * math.exp(-age_hours / 3.0) * 0.3, 0.0)
            return min(17.0 * math.exp(-age_hours / 10.0), 17.0)
        except Exception:
            return 0.0

    # ── Factor 5: Geopolitical Severity ──────────────────────────────────
    def _factor_geopolitical_severity(self, signal: Dict) -> float:
        """Event intensity + region impact. 13 pts max."""
        severity = signal.get("severity", "LOW")
        sev_score = SEVERITY_WEIGHTS.get(severity, 3)
        event_intensity = float(signal.get("event_intensity", 0.0) or 0.0)

        regions = signal.get("regions", ["global"])
        max_region = max(
            (REGION_WEIGHTS.get(r, 1) for r in regions),
            default=1,
        )
        cross_region_bonus = min(max(len(set(regions)) - 1, 0), 2) * 0.65
        intensity_component = min(event_intensity / 2.0, 7.5)
        severity_component = min(sev_score * 0.22, 2.6)
        region_component = min(max_region * 0.65, 3.0)

        return min(intensity_component + severity_component + region_component + cross_region_bonus, 13.0)

    # ── Factor 6: Cross-Engine Confirmation ──────────────────────────────
    def _factor_cross_engine_confirmation(self, signal: Dict) -> float:
        """
        Reward signals confirmed by INDEPENDENT engines (price action +
        constituent rotation). 12 pts max.

        Lookups:
          signal["evidence"]["price"]        → from signal_fusion.SignalFuser
          signal["evidence"]["constituents"]
          signal["fused_score"]              → composite from fusion
          signal["consensus_tier"]           → A/B/C from fusion
          signal["engines"]                  → list of contributing engines

        The factor rewards:
          - Multiple engines agree (≥2)
          - Direction agreement (no divergence penalty)
          - Strong individual price/constituent metrics
        """
        evidence = signal.get("evidence") or {}
        engines = signal.get("engines") or []
        tier = signal.get("consensus_tier")
        divergent = signal.get("divergent", False)

        # If fusion never ran, fall back to checking embedded price/constituent
        # data on the signal itself (single-engine signals enriched in-place
        # by the price scanner or reverse_researcher).
        price_evidence = evidence.get("price") or signal.get("price_signal")
        const_evidence = evidence.get("constituents") or signal.get("constituent_evidence")
        news_confirmed = signal.get("news_confirmed", False)

        score = 0.0

        # Tier-based base reward
        if tier == "A":
            score += 7.0
        elif tier == "B":
            score += 4.0
        elif len(engines) == 1 and news_confirmed:
            # News+price reverse-confirmed but only fed as one signal
            score += 3.0

        # Price-action quality boost (independent of news)
        if price_evidence:
            # `price_evidence` may be a dict (engine output) with embedded
            # PriceSignal asdict() under "price_signal", or directly a
            # PriceSignal-asdict.
            ps = (price_evidence.get("price_signal") if isinstance(price_evidence, dict) else None) or price_evidence
            if isinstance(ps, dict):
                z5 = abs(float(ps.get("z_5d", 0) or 0))
                strength = float(ps.get("strength", 0) or 0)
                # Reward big abnormal moves and breakouts
                score += min(z5 * 0.8, 2.5)
                score += min(strength / 60.0, 1.5)
                if ps.get("breakout_20d_high") or ps.get("breakdown_20d_low"):
                    score += 0.8

        # Constituent rotation boost
        if const_evidence:
            ev = (const_evidence.get("constituent_evidence")
                  if isinstance(const_evidence, dict) and "constituent_evidence" in const_evidence
                  else const_evidence)
            if isinstance(ev, dict):
                conv = float(ev.get("conviction", 0) or 0)
                score += min(conv / 30.0, 2.0)

        # Divergence penalty
        if divergent:
            score *= 0.5

        return min(score, 12.0)
