"""
signal_fusion.py — AZALYST Multi-Engine Signal Fusion

Three independent signal engines now exist:

    NEWS engine          (lagging)  — RSS + keyword classifier
    PRICE engine         (leading)  — yfinance momentum / breakouts
    CONSTITUENT engine   (leading)  — top holdings rotation

This module merges them per-sector and outputs a single ranked signal list
with a "consensus tier" tag that downstream code (scorer, paper trader,
reporter) uses to size conviction:

    TIER A — all 3 engines agree on the same direction (rare, highest alpha)
    TIER B — 2 engines agree, third silent (typical strong setup)
    TIER C — 1 engine only (noisy; reduce position size or skip)

Direction conflicts (e.g. news bullish but price bearish) are NOT auto-merged;
they're flagged as "divergent" and routed for manual review since they often
mean the news has already been priced in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("azalyst.fusion")


@dataclass
class FusedSignal:
    sector_id: str
    sector_label: str
    direction: str                          # BULLISH / BEARISH
    consensus_tier: str                     # A / B / C
    engines: List[str] = field(default_factory=list)
    news_signal: Optional[Dict] = None
    price_signal: Optional[Dict] = None
    constituent_signal: Optional[Dict] = None
    divergent: bool = False
    fused_score: float = 0.0                # composite 0-100
    explanation: str = ""

    def to_dict(self) -> Dict:
        """Return the merged signal in the shape downstream code expects."""
        # Pick the "primary" payload — prefer news (richest payload), then
        # price, then constituents. Then patch in cross-engine evidence.
        primary = self.news_signal or self.price_signal or self.constituent_signal or {}
        out = dict(primary)
        out.update({
            "sector_id": self.sector_id,
            "sectors": [self.sector_id],
            "sector_label": self.sector_label,
            "direction": self.direction,
            "fused_score": self.fused_score,
            "consensus_tier": self.consensus_tier,
            "engines": self.engines,
            "divergent": self.divergent,
            "fusion_explanation": self.explanation,
            "evidence": {
                "news":         self.news_signal,
                "price":        self.price_signal,
                "constituents": self.constituent_signal,
            },
        })
        return out


class SignalFuser:
    """Fuse signals across the three engines."""

    # Weights for the composite fused_score (sum to 1.0)
    W_NEWS = 0.45
    W_PRICE = 0.35
    W_CONSTITUENTS = 0.20

    def fuse(self,
             news_signals: List[Dict],
             price_signals: List[Dict],
             constituent_signals: List[Dict]) -> List[FusedSignal]:

        # Index every input by sector_id
        idx_news: Dict[str, Dict] = {s["sector_id"]: s for s in news_signals if s.get("sector_id")}
        idx_price: Dict[str, Dict] = {s["sector_id"]: s for s in price_signals if s.get("sector_id")}
        idx_const: Dict[str, Dict] = {s["sector_id"]: s for s in constituent_signals if s.get("sector_id")}

        all_sectors = set(idx_news) | set(idx_price) | set(idx_const)
        fused: List[FusedSignal] = []

        for sec in all_sectors:
            n = idx_news.get(sec)
            p = idx_price.get(sec)
            c = idx_const.get(sec)

            engines = [tag for tag, x in
                       [("NEWS", n), ("PRICE", p), ("CONSTITUENTS", c)] if x]

            # Direction vote
            dirs: List[Tuple[str, str]] = []
            if n: dirs.append(("NEWS", n.get("direction", "NEUTRAL")))
            if p: dirs.append(("PRICE", p.get("direction", "NEUTRAL")))
            if c: dirs.append(("CONSTITUENTS", c.get("direction", "NEUTRAL")))

            bull_votes = [e for e, d in dirs if d == "BULLISH"]
            bear_votes = [e for e, d in dirs if d == "BEARISH"]

            if not bull_votes and not bear_votes:
                continue   # all neutral, nothing to act on

            if bull_votes and bear_votes:
                # Conflict — flag divergent, pick the engine with more weight
                divergent = True
                direction = "BULLISH" if len(bull_votes) >= len(bear_votes) else "BEARISH"
            else:
                divergent = False
                direction = "BULLISH" if bull_votes else "BEARISH"

            # Consensus tier
            agree_count = max(len(bull_votes), len(bear_votes))
            if agree_count >= 3:
                tier = "A"
            elif agree_count == 2:
                tier = "B"
            else:
                tier = "C"

            # Fused score (0-100)
            news_pts = self._news_pts(n) if n else 0
            price_pts = self._price_pts(p) if p else 0
            const_pts = self._const_pts(c) if c else 0
            fused_score = round(
                news_pts * self.W_NEWS
                + price_pts * self.W_PRICE
                + const_pts * self.W_CONSTITUENTS,
                1,
            )
            # Tier A bonus, Tier C penalty for being thin
            if tier == "A": fused_score = min(fused_score * 1.15, 100)
            if tier == "C": fused_score *= 0.85
            if divergent:   fused_score *= 0.7

            # Explanation string for the reporter
            parts = []
            if n: parts.append(
                f"news conf={n.get('confidence', '?')}, dir={n.get('direction')}, "
                f"articles={n.get('article_count', 0)}"
            )
            if p:
                ps = p.get("price_signal", {})
                parts.append(
                    f"price 5D={ps.get('ret_5d', 0):+.2f}% z={ps.get('z_5d', 0):+.2f}σ "
                    f"({p.get('ticker_driver','?')} {p.get('direction')})"
                )
            if c:
                ce = c.get("constituent_evidence", {})
                parts.append(
                    f"constituents {ce.get('bullish_count','?')}↑/"
                    f"{ce.get('bearish_count','?')}↓ ({c.get('direction')})"
                )
            explanation = " | ".join(parts)
            if divergent:
                explanation = "[DIVERGENT] " + explanation

            sector_label = (n or p or c).get("sector_label") or sec

            fused.append(FusedSignal(
                sector_id=sec,
                sector_label=sector_label,
                direction=direction,
                consensus_tier=tier,
                engines=engines,
                news_signal=n,
                price_signal=p,
                constituent_signal=c,
                divergent=divergent,
                fused_score=fused_score,
                explanation=explanation,
            ))

        # Rank: tier A first, then by fused_score
        tier_order = {"A": 0, "B": 1, "C": 2}
        fused.sort(key=lambda f: (tier_order[f.consensus_tier], -f.fused_score))
        return fused

    # ── per-engine point converters (each on 0-100) ─────────────────────────
    @staticmethod
    def _news_pts(s: Dict) -> float:
        return float(s.get("confidence", 0) or 0)

    @staticmethod
    def _price_pts(s: Dict) -> float:
        ps = s.get("price_signal") or {}
        return float(ps.get("strength", 0) or 0)

    @staticmethod
    def _const_pts(s: Dict) -> float:
        ev = s.get("constituent_evidence") or {}
        return float(ev.get("conviction", 0) or 0)
