"""
Position sizing — vol targeting + capped Kelly + ERC.

The mandate from the user: "drawdown all can be maintained by capping means
buying n trailing." Translation: every position's notional is set so that
its dollar risk is capped, then trailing stops manage the exit.

Three sizing modes:

1. VOL_TARGET (default) — each position contributes equal annualized $-vol to
   the book. Notional_i = (target_book_vol * book_value * weight_i) / sigma_i

2. CAPPED_KELLY — Kelly-optimal sizing with a 1/4-Kelly cap (leverage safety).
   Requires win_prob and win/loss ratio inputs from the scorer.

3. EQUAL_RISK_CONTRIB — each position contributes equal portfolio variance.
   Closer to risk-parity; uses pairwise correlations from cluster_dedup.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class SizedPosition:
    ticker: str
    direction: str          # "long" / "short"
    target_notional: float
    target_shares: int
    target_pct_of_book: float
    realized_vol_annualized: float


def _realized_vols(tickers: list[str], lookback_days: int = 30) -> dict[str, float]:
    df = yf.download(tickers, period=f"{lookback_days + 10}d", interval="1d",
                     auto_adjust=True, progress=False, threads=True)
    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])
    rets = closes.pct_change().dropna(how="all").tail(lookback_days)
    vol = rets.std() * np.sqrt(252)
    return {tk: float(vol.get(tk, np.nan)) for tk in tickers if not np.isnan(vol.get(tk, np.nan))}


def _last_prices(tickers: list[str]) -> dict[str, float]:
    df = yf.download(tickers, period="5d", interval="1d", auto_adjust=True,
                     progress=False, threads=True)
    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])
    return {tk: float(closes[tk].dropna().iloc[-1]) for tk in tickers if tk in closes.columns}


def vol_target_sizing(
    candidates: list[tuple[str, str, float]],   # (ticker, direction, signal_score)
    book_value: float,
    target_book_vol_annual: float = 0.15,        # 15% target ann. vol
    max_position_pct: float = 0.15,
    max_gross_leverage: float = 1.5,
) -> list[SizedPosition]:
    if not candidates:
        return []
    tickers = [c[0] for c in candidates]
    vols = _realized_vols(tickers)
    prices = _last_prices(tickers)
    candidates = [c for c in candidates if c[0] in vols and c[0] in prices]
    if not candidates:
        return []

    # weight by signal_score, then risk-equalize via 1/sigma
    scores = np.array([c[2] for c in candidates], dtype=float)
    score_w = scores / scores.sum() if scores.sum() > 0 else np.ones_like(scores) / len(scores)
    inv_vol = np.array([1.0 / vols[c[0]] for c in candidates])
    raw_w = score_w * inv_vol
    raw_w = raw_w / raw_w.sum()

    # cap per-position
    raw_w = np.minimum(raw_w, max_position_pct)
    if raw_w.sum() < 1e-9:
        return []
    raw_w = raw_w / raw_w.sum()

    # vol-target: scale book exposure so portfolio realized vol ~ target
    portfolio_vol_proxy = float(np.sqrt(sum((raw_w[i] * vols[c[0]]) ** 2 for i, c in enumerate(candidates))))
    if portfolio_vol_proxy <= 0:
        return []
    leverage = min(max_gross_leverage, target_book_vol_annual / portfolio_vol_proxy)

    out: list[SizedPosition] = []
    for w, (tk, direction, _) in zip(raw_w, candidates):
        notional = w * leverage * book_value
        shares = int(notional / prices[tk])
        out.append(SizedPosition(
            ticker=tk,
            direction=direction,
            target_notional=float(notional if direction == "long" else -notional),
            target_shares=shares if direction == "long" else -shares,
            target_pct_of_book=float(w * leverage),
            realized_vol_annualized=vols[tk],
        ))
    return out


def capped_kelly(
    win_prob: float,
    win_loss_ratio: float,
    cap_fraction: float = 0.25,
) -> float:
    """f* = p - (1-p)/b, capped at cap_fraction of full Kelly."""
    if win_loss_ratio <= 0:
        return 0.0
    f_star = win_prob - (1 - win_prob) / win_loss_ratio
    return float(max(0.0, min(cap_fraction, f_star * cap_fraction)))


if __name__ == "__main__":
    test = [("EWY", "long", 75), ("SLV", "long", 72), ("SOXX", "long", 70), ("IGV", "long", 68)]
    sized = vol_target_sizing(test, book_value=100_000)
    for s in sized:
        print(f"{s.ticker:6s} {s.direction:5s} ${s.target_notional:>+10.0f}  {s.target_shares:>+5d} sh  "
              f"({s.target_pct_of_book:.1%} of book)  vol={s.realized_vol_annualized:.1%}")
