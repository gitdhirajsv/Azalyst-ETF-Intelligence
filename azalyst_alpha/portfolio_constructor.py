"""
Portfolio constructor — turns a list of CompositeScores into a sized,
deduped, regime-gated, risk-managed book of positions.

Pipeline:
    raw composite scores
      -> regime gate (Antonacci absolute momentum / Lo VIX regime)
      -> publish threshold from scorer_v2 (60 pts, regime-conditional)
      -> cluster dedup (keep best ticker per correlation cluster)
      -> max N positions
      -> vol-target sizing (position_sizer)
      -> trailing-stop attachment (risk_manager)
      -> book = list[SizedPosition]
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import cluster_dedup, position_sizer, regime_engine, scorer_v2


@dataclass(frozen=True)
class BookEntry:
    ticker: str
    direction: str
    composite_score: float
    target_notional: float
    target_shares: int
    target_pct_of_book: float
    realized_vol: float
    regime_state: str
    vol_regime: str


def build_book(
    composite_scores: list[scorer_v2.CompositeScore],
    book_value: float,
    target_book_vol: float = 0.15,
    max_positions: int = 8,
    max_position_pct: float = 0.15,
    max_gross_leverage: float = 1.5,
) -> tuple[list[BookEntry], regime_engine.RegimeState]:
    regime = regime_engine.detect_regime()

    eligible: list[scorer_v2.CompositeScore] = []
    for cs in composite_scores:
        if not cs.publish:
            continue
        if regime.risk_state == "RISK_OFF" and cs.ticker not in regime_engine.DEFENSIVE_TICKERS:
            continue
        if regime.risk_state == "RISK_OFF" and cs.direction == "long" and cs.ticker not in regime_engine.DEFENSIVE_TICKERS:
            continue
        eligible.append(cs)

    if not eligible:
        return [], regime

    candidate_pairs = [(cs.ticker, cs.total) for cs in eligible]
    clusters = cluster_dedup.build_clusters([cs.ticker for cs in eligible])
    deduped = cluster_dedup.keep_one_per_cluster(candidate_pairs, clusters)
    deduped_set = {tk for tk, _ in deduped}
    eligible = [cs for cs in eligible if cs.ticker in deduped_set]

    eligible.sort(key=lambda c: -c.total)
    eligible = eligible[:max_positions]

    sizing_input = [(cs.ticker, cs.direction, cs.total) for cs in eligible]
    sized = position_sizer.vol_target_sizing(
        sizing_input,
        book_value=book_value,
        target_book_vol_annual=target_book_vol,
        max_position_pct=max_position_pct,
        max_gross_leverage=max_gross_leverage,
    )

    score_map = {cs.ticker: cs.total for cs in eligible}
    book = [
        BookEntry(
            ticker=s.ticker,
            direction=s.direction,
            composite_score=score_map.get(s.ticker, 0),
            target_notional=s.target_notional,
            target_shares=s.target_shares,
            target_pct_of_book=s.target_pct_of_book,
            realized_vol=s.realized_vol_annualized,
            regime_state=regime.risk_state,
            vol_regime=regime.vol_regime,
        )
        for s in sized
    ]
    return book, regime


def to_dataframe(book: list[BookEntry]) -> pd.DataFrame:
    return pd.DataFrame([b.__dict__ for b in book])
