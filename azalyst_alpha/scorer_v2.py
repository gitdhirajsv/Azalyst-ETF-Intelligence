"""
Replacement for upstream Azalyst scorer.py.

Upstream allocated 88/100 to news factors and 12/100 to cross-engine. Result:
a clean tape-led mover (EWY, IGV, SLV, SOXX, SMH on the leaderboard) cannot
clear the 62-point gate without a press release.

This scorer rebalances:
    Cross-Sectional Rank        25  (Layer 1)
    Flow                        20  (Layer 2)
    Options Tape + GEX          20  (Layer 3a + 3b)
    Holdings-Weighted Rotation  15  (Layer 4)
    Macro Fit                   10  (Layer 5)
    News Confirmation           10  (Layer 6, downgraded)
    -------------------------------
    Total                      100

Threshold = 60. Now any 3 of {rank, flow, options, rotation} can publish a
signal independently. News is a bonus, not a gate.
"""

from __future__ import annotations

from dataclasses import dataclass


PUBLISH_THRESHOLD = 60.0
MAX_NEWS = 10.0


@dataclass(frozen=True)
class CompositeScore:
    ticker: str
    rank_score: float
    flow_score: float
    options_score: float        # = options_tape + 0.5 * gex (capped at 20)
    rotation_score: float
    macro_score: float
    news_score: float
    total: float
    publish: bool
    direction: str              # "long" / "short" / "neutral"


def composite_score(
    ticker: str,
    rank_score: float = 0.0,
    flow_score: float = 0.0,
    options_tape_score: float = 0.0,
    gex_score: float = 0.0,
    rotation_score: float = 0.0,
    macro_score: float = 0.0,
    news_score: float = 0.0,
    direction: str = "long",
) -> CompositeScore:
    rank = max(0.0, min(25.0, rank_score))
    flow = max(0.0, min(20.0, flow_score))
    opt = max(0.0, min(20.0, options_tape_score + 0.5 * gex_score))
    rot = max(0.0, min(15.0, rotation_score))
    macro = max(0.0, min(10.0, macro_score))
    news = max(0.0, min(MAX_NEWS, news_score))
    total = rank + flow + opt + rot + macro + news
    return CompositeScore(
        ticker=ticker,
        rank_score=rank,
        flow_score=flow,
        options_score=opt,
        rotation_score=rot,
        macro_score=macro,
        news_score=news,
        total=total,
        publish=total >= PUBLISH_THRESHOLD,
        direction=direction,
    )
