"""
Daily fusion runner v2 — end-to-end pipeline.

  Signal layers
       |
       v
  Regime-conditional scoring (scorer_v2 + regime_engine weight matrix)
       |
       v
  Publish gate (60-pt threshold)
       |
       v
  Cluster dedup
       |
       v
  Antonacci absolute-momentum gate (RISK_OFF -> defensives only)
       |
       v
  Vol-target sizing
       |
       v
  Risk overlay (trailing stops, circuit breaker)
       |
       v
  Paper trader execution + tearsheet

Run:
    python -m azalyst_alpha.fusion
"""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from . import (
    ETF_UNIVERSE, cross_sectional_ranker, flow_engine, gex_engine,
    holdings_weighted_rotation, macro_overlay, options_tape,
    portfolio_constructor, regime_engine, report, scorer_v2,
)


GEX_TARGETS = ["SPY", "QQQ", "IWM", "SOXX", "SMH", "IGV", "XLK", "XLF", "XLE",
               "GLD", "SLV", "EWY", "GDX", "ITA"]


def _regime_weighted_composite(
    ticker: str,
    rank_score: float,
    flow_score: float,
    options_tape_score: float,
    gex_score: float,
    rotation_score: float,
    macro_score: float,
    news_score: float,
    direction: str,
    weight_matrix: dict[str, float],
) -> scorer_v2.CompositeScore:
    """Apply regime-conditional weights (scale max per factor) to scorer_v2."""
    rank = rank_score * (weight_matrix["rank"] / 25.0)
    flow = flow_score * (weight_matrix["flow"] / 20.0)
    opt = (options_tape_score + 0.5 * gex_score) * (weight_matrix["options"] / 20.0)
    rot = rotation_score * (weight_matrix["rotation"] / 15.0)
    macro = macro_score * (weight_matrix["macro"] / 10.0)
    news = news_score * (weight_matrix["news"] / 10.0)
    total = rank + flow + opt + rot + macro + news
    return scorer_v2.CompositeScore(
        ticker=ticker,
        rank_score=rank,
        flow_score=flow,
        options_score=opt,
        rotation_score=rot,
        macro_score=macro,
        news_score=news,
        total=total,
        publish=total >= scorer_v2.PUBLISH_THRESHOLD,
        direction=direction,
    )


def run(book_value: float = 100_000, verbose: bool = True) -> dict:
    if verbose: print("[regime] detecting...")
    regime = regime_engine.detect_regime()
    if verbose: print(f"  -> {regime.risk_state} / {regime.vol_regime} / VIX {regime.vix_level:.1f}")

    if verbose: print("[1/6] cross-sectional rank")
    rank_rows = cross_sectional_ranker.rank_universe()
    rank_map = {r.ticker: r for r in rank_rows}

    if verbose: print("[2/6] ETF flows")
    flow_rows = flow_engine.compute_flows(ETF_UNIVERSE)
    flow_map = {r.ticker: r for r in flow_rows}

    if verbose: print("[3a/6] dealer GEX")
    gex_rows = gex_engine.compute_gex_universe(GEX_TARGETS)
    gex_map = {r.ticker: r for r in gex_rows}

    if verbose: print("[3b/6] options tape")
    opt_rows = options_tape.compute_options_universe(GEX_TARGETS)
    opt_map = {r.ticker: r for r in opt_rows}

    if verbose: print("[4/6] holdings-weighted rotation")
    rot_rows = holdings_weighted_rotation.compute_universe()
    rot_map = {r.etf: r for r in rot_rows}

    if verbose: print("[5/6] macro overlay")
    macro_rows = macro_overlay.compute_universe()
    macro_map = {r.etf: r for r in macro_rows}

    if verbose: print("[6/6] regime-weighted composite scoring")
    composite: list[scorer_v2.CompositeScore] = []
    universe = {*rank_map, *flow_map, *gex_map, *opt_map, *rot_map, *macro_map}
    for tk in universe:
        cs = _regime_weighted_composite(
            ticker=tk,
            rank_score=rank_map[tk].score if tk in rank_map else 0,
            flow_score=flow_map[tk].score if tk in flow_map else 0,
            options_tape_score=opt_map[tk].score if tk in opt_map else 0,
            gex_score=gex_map[tk].score if tk in gex_map else 0,
            rotation_score=rot_map[tk].score if tk in rot_map else 0,
            macro_score=macro_map[tk].score if tk in macro_map else 0,
            news_score=0,
            direction=(rot_map[tk].direction if tk in rot_map else "long"),
            weight_matrix=regime.weight_matrix,
        )
        composite.append(cs)

    if verbose: print("[portfolio] regime gate -> dedup -> sizing")
    book, _ = portfolio_constructor.build_book(composite, book_value=book_value)

    leaderboard = pd.DataFrame([asdict(c) for c in composite]).sort_values("total", ascending=False)
    book_df = portfolio_constructor.to_dataframe(book)

    # Always write the CSV — generate_dashboard.py reads this for top_signal payload.
    from pathlib import Path
    Path("data").mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv("data/leaderboard_latest.csv", index=False)
    if verbose: print(f"[csv] data/leaderboard_latest.csv written ({len(leaderboard)} rows)")

    if verbose: print("[report] writing tearsheet -> data/tearsheet.md")
    try:
        out = report.write_report(leaderboard, book_df, regime)
    except ImportError as exc:
        # tabulate not installed -> fall back to plain text tearsheet
        if verbose: print(f"[report] markdown rendering unavailable ({exc}); writing plain-text tearsheet")
        Path("data/tearsheet.md").write_text(
            f"# Azalyst Tearsheet — {regime.risk_state} / {regime.vol_regime}\n\n"
            f"VIX {regime.vix_level:.1f} ({regime.vix_percentile_1y:.0%}ile)\n\n"
            f"## Top 25\n```\n{leaderboard.head(25).to_string(index=False)}\n```\n\n"
            f"## Published Book\n```\n{book_df.to_string(index=False) if not book_df.empty else '(empty)'}\n```\n",
            encoding="utf-8",
        )
        out = "data/tearsheet.md"

    return {"leaderboard": leaderboard, "book": book_df, "regime": regime, "tearsheet": out}


if __name__ == "__main__":
    out = run()
    print("\n=== TOP 15 ===")
    print(out["leaderboard"].head(15).to_string(index=False))
    print("\n=== PUBLISHED BOOK ===")
    if out["book"].empty:
        print("(empty — regime gate or no signal cleared 60-pt threshold)")
    else:
        print(out["book"].to_string(index=False))
    print(f"\nTearsheet -> {out['tearsheet']}")
