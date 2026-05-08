"""
Layer 4 — Holdings-Weighted Rotation.

Rebuilds upstream constituent_analyzer.py. Two changes vs. upstream:
  1. Holdings are weighted by AUM share, not equal-weighted (Wes Gray fix).
     Conviction = sum(weight_i * sign(ret_5d_i) * |ret_5d_i|).
  2. Threshold expressed as fraction of weight, not fraction of count.
     Default 0.30 of weight (vs. upstream 0.40 of count).

Free holdings sources:
  - iShares: per-fund daily holdings JSON
  - VanEck:  per-fund daily holdings CSV
  - SSGA:    per-fund daily holdings CSV
  - Fallback: hardcoded top-10 + estimated weights for the most-trafficked ETFs

This module ships with a curated weights table for the top sector ETFs so it
runs out of the box; upgrade path is to plug live issuer fetchers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf


# Curated weights (approximate; refresh quarterly from issuer pages).
# Format: ETF -> [(ticker, weight_pct), ...]
WEIGHTED_HOLDINGS: dict[str, list[tuple[str, float]]] = {
    "SOXX": [("NVDA", 0.095), ("AVGO", 0.085), ("AMD", 0.075), ("TSM", 0.070),
             ("QCOM", 0.060), ("TXN", 0.055), ("AMAT", 0.045), ("MU", 0.045),
             ("LRCX", 0.040), ("INTC", 0.030)],
    "SMH":  [("NVDA", 0.215), ("TSM", 0.115), ("AVGO", 0.075), ("AMD", 0.055),
             ("ASML", 0.050), ("AMAT", 0.045), ("LRCX", 0.040), ("QCOM", 0.040),
             ("MU", 0.040), ("INTC", 0.030)],
    "IGV":  [("MSFT", 0.085), ("ORCL", 0.080), ("CRM", 0.075), ("PANW", 0.065),
             ("NOW", 0.060), ("ADBE", 0.055), ("INTU", 0.050), ("CRWD", 0.045),
             ("FTNT", 0.040), ("WDAY", 0.040)],
    "XLK":  [("AAPL", 0.180), ("MSFT", 0.170), ("NVDA", 0.140), ("AVGO", 0.045),
             ("CRM", 0.030), ("ORCL", 0.030), ("ADBE", 0.025), ("CSCO", 0.025),
             ("ACN", 0.025), ("AMD", 0.025)],
    "XLF":  [("BRK-B", 0.130), ("JPM", 0.110), ("V", 0.075), ("MA", 0.070),
             ("BAC", 0.045), ("WFC", 0.040), ("GS", 0.035), ("SPGI", 0.035),
             ("MS", 0.030), ("AXP", 0.030)],
    "XLE":  [("XOM", 0.230), ("CVX", 0.165), ("COP", 0.080), ("EOG", 0.045),
             ("WMB", 0.045), ("SLB", 0.040), ("MPC", 0.040), ("PSX", 0.035),
             ("OXY", 0.035), ("VLO", 0.030)],
    "EWY":  [("005930.KS", 0.230), ("000660.KS", 0.090), ("207940.KS", 0.040),
             ("005380.KS", 0.035), ("373220.KS", 0.030), ("035420.KS", 0.030),
             ("000270.KS", 0.025), ("068270.KS", 0.020), ("005490.KS", 0.020),
             ("105560.KS", 0.020)],
    "ITA":  [("RTX", 0.175), ("BA", 0.155), ("LMT", 0.080), ("NOC", 0.050),
             ("GD", 0.045), ("HII", 0.040), ("LHX", 0.040), ("TXT", 0.035),
             ("HEI", 0.030), ("AXON", 0.030)],
    "GDX":  [("NEM", 0.130), ("AEM", 0.090), ("WPM", 0.075), ("GOLD", 0.060),
             ("FNV", 0.060), ("KGC", 0.045), ("PAAS", 0.035), ("AU", 0.035),
             ("HMY", 0.030), ("ZIJ", 0.030)],
}


@dataclass(frozen=True)
class RotationRow:
    etf: str
    n_holdings: int
    coverage_weight: float       # sum of weights we have data for
    weighted_ret_5d: float       # weighted average 5d return of constituents
    bullish_weight: float        # sum of weights with positive 5d return
    bearish_weight: float
    conviction: float            # max(bullish, bearish) - threshold
    direction: str               # "long" / "short" / "neutral"
    score: float                 # 0-15 contribution to scorer_v2


def _bulk_returns(tickers: list[str], lookback: int = 5) -> dict[str, float]:
    if not tickers:
        return {}
    df = yf.download(tickers, period="20d", interval="1d",
                     auto_adjust=True, progress=False, threads=True)
    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])
    rets: dict[str, float] = {}
    for tk in closes.columns:
        s = closes[tk].dropna()
        if len(s) < lookback + 1:
            continue
        rets[tk] = float(s.iloc[-1] / s.iloc[-lookback - 1] - 1)
    return rets


def compute_rotation(etf: str, threshold: float = 0.30) -> RotationRow | None:
    holdings = WEIGHTED_HOLDINGS.get(etf)
    if not holdings:
        return None
    tickers = [t for t, _ in holdings]
    weights = {t: w for t, w in holdings}
    rets = _bulk_returns(tickers)
    covered = {t: weights[t] for t in rets}
    coverage_weight = sum(covered.values())
    if coverage_weight < 0.3:
        return None

    weighted_ret = sum(weights[t] * rets[t] for t in rets) / coverage_weight
    bullish = sum(weights[t] for t in rets if rets[t] > 0)
    bearish = sum(weights[t] for t in rets if rets[t] < 0)
    bullish_norm = bullish / coverage_weight
    bearish_norm = bearish / coverage_weight

    if bullish_norm >= threshold and bullish_norm > bearish_norm:
        direction = "long"
        conviction = bullish_norm - threshold
    elif bearish_norm >= threshold and bearish_norm > bullish_norm:
        direction = "short"
        conviction = bearish_norm - threshold
    else:
        direction = "neutral"
        conviction = 0.0

    score = float(np.clip(
        15 * conviction / (1 - threshold) + 8 * abs(weighted_ret) * 100,
        0, 15,
    )) if direction != "neutral" else 0.0

    return RotationRow(
        etf=etf,
        n_holdings=len(rets),
        coverage_weight=coverage_weight,
        weighted_ret_5d=weighted_ret,
        bullish_weight=bullish_norm,
        bearish_weight=bearish_norm,
        conviction=conviction,
        direction=direction,
        score=score,
    )


def compute_universe(etfs: list[str] | None = None) -> list[RotationRow]:
    targets = etfs or list(WEIGHTED_HOLDINGS.keys())
    out: list[RotationRow] = []
    for etf in targets:
        r = compute_rotation(etf)
        if r is not None:
            out.append(r)
        time.sleep(0.05)
    return out


def to_dataframe(rows: list[RotationRow]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in rows])


if __name__ == "__main__":
    rows = compute_universe()
    print(to_dataframe(rows).sort_values("score", ascending=False).to_string(index=False))
