"""
Daily tearsheet — what a fund manager would actually read at the end of day.

Sections:
  1. Regime banner (risk state, vol regime, weight matrix)
  2. Top-25 leaderboard (composite scores)
  3. Published book (post regime gate + dedup + sizing)
  4. Position-level PnL since entry (from paper_trader)
  5. Risk dashboard (gross/net exposure, realized vol, drawdown)
  6. Factor attribution (which signal layers drove published positions)
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

import pandas as pd

from . import paper_trader, regime_engine


def render_markdown(
    leaderboard: pd.DataFrame,
    book: pd.DataFrame,
    regime: regime_engine.RegimeState,
) -> str:
    today = date.today().isoformat()
    eq = paper_trader.equity_curve()
    equity_value = paper_trader.mark_to_market()
    pos = paper_trader.positions()

    md: list[str] = []
    md.append(f"# Azalyst Daily Tearsheet — {today}\n")
    md.append("## 1. Regime\n")
    md.append(f"- **Risk state:** {regime.risk_state}")
    md.append(f"- **Vol regime:** {regime.vol_regime}  (VIX {regime.vix_level:.1f}, {regime.vix_percentile_1y:.0%}ile 1Y)")
    md.append(f"- **SPY > 200MA:** {regime.spy_above_200ma}")
    md.append(f"- **SPY 3M excess vs T-bill:** {regime.spy_excess_vs_tbill_3m:+.2%}")
    md.append(f"- **Active weights:** {regime.weight_matrix}\n")

    md.append("## 2. Top-25 Leaderboard\n")
    md.append(leaderboard.head(25).to_markdown(index=False, floatfmt=".2f"))
    md.append("")

    md.append("## 3. Published Book\n")
    if book.empty:
        md.append("_No published positions today (regime gate active or no signal cleared 60-pt threshold)._\n")
    else:
        md.append(book.to_markdown(index=False, floatfmt=".2f"))
        gross = book["target_notional"].abs().sum()
        net = book["target_notional"].sum()
        md.append(f"\n- **Gross exposure:** ${gross:,.0f}  ({gross/max(equity_value,1):.0%} of equity)")
        md.append(f"- **Net exposure:** ${net:,.0f}  ({net/max(equity_value,1):.0%} of equity)\n")

    md.append("## 4. Live Positions (paper)\n")
    if not pos:
        md.append("_No live positions._\n")
    else:
        df = pd.DataFrame(pos)
        md.append(df.to_markdown(index=False))
        md.append("")

    md.append("## 5. Equity\n")
    md.append(f"- **Current equity:** ${equity_value:,.0f}")
    if len(eq) >= 2:
        first = eq[0][1]
        prev = eq[-2][1]
        md.append(f"- **PnL since inception:** {equity_value/first - 1:+.2%}")
        md.append(f"- **PnL today:** {equity_value/prev - 1:+.2%}")

    return "\n".join(md)


def write_report(
    leaderboard: pd.DataFrame,
    book: pd.DataFrame,
    regime: regime_engine.RegimeState,
    out_path: str = "data/tearsheet.md",
) -> str:
    md = render_markdown(leaderboard, book, regime)
    from pathlib import Path
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(md, encoding="utf-8")
    return out_path
