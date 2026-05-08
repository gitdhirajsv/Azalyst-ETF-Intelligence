"""
Layer 3a — Dealer Gamma Exposure (GEX).

Free SpotGamma equivalent. Math is from Squeeze Metrics' "The Implied Order Book"
(2017) and Charlie McElligott's standard convention.

For every option strike on an ETF:
    gamma_per_contract = N'(d1) / (S * sigma * sqrt(T)) * 100   (per share, x100 = per contract)
    dealer_gamma_$       = gamma_per_contract * OI * 100 * S^2 * 0.01

Sign convention (Squeeze Metrics standard):
    Calls:   dealers are SHORT  -> negative gamma  (multiplier = -1)
    Puts:    dealers are LONG   -> positive gamma  (multiplier = +1)

Total dealer GEX($) = sum over strikes.
    Negative GEX  -> dealers chase moves (selling low, buying high) -> volatility
    Positive GEX  -> dealers fade moves  (buying low, selling high) -> compression

Zero-gamma flip level (the "gamma flip") is the strike at which cumulative
dealer GEX crosses zero. Below it -> regime change to volatile.

Data: yfinance option chains (free, EOD-quality). For ETFs we care about the
top-liquidity sector ETFs: SPY, QQQ, IWM, SOXX, SMH, IGV, XLK, XLE, XLF, GLD, SLV, etc.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm


RISK_FREE_RATE = 0.05  # close enough for GEX; we don't need to be precise


@dataclass(frozen=True)
class GexRow:
    ticker: str
    spot: float
    total_gex_usd: float          # net dealer gamma, $
    gamma_flip: float | None      # strike where cumulative GEX = 0
    largest_call_wall: float      # strike with most positive call OI*gamma
    largest_put_wall: float       # strike with most negative put OI*gamma
    pct_distance_to_flip: float   # (spot - flip) / spot
    score: float                  # 0-20 contribution to scorer_v2


def _bs_gamma(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return norm.pdf(d1) / (S * sigma * math.sqrt(T))


def _years_to_expiry(expiry: str) -> float:
    exp = datetime.strptime(expiry, "%Y-%m-%d")
    days = (exp - datetime.utcnow()).days
    return max(days, 1) / 365.0


def compute_gex(ticker: str, max_expiries: int = 6) -> GexRow | None:
    try:
        t = yf.Ticker(ticker)
        spot = float(t.history(period="1d")["Close"].iloc[-1])
        expiries = list(t.options)[:max_expiries]
    except Exception:
        return None
    if not expiries:
        return None

    rows: list[dict] = []
    for exp in expiries:
        try:
            chain = t.option_chain(exp)
        except Exception:
            continue
        T = _years_to_expiry(exp)
        for kind, df, sign in (("C", chain.calls, -1), ("P", chain.puts, +1)):
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                K = float(row["strike"])
                iv = float(row.get("impliedVolatility") or 0.0)
                oi = float(row.get("openInterest") or 0.0)
                if oi <= 0 or iv <= 0 or K <= 0:
                    continue
                g = _bs_gamma(spot, K, T, iv)
                # dollar gamma per 1% move: gamma * OI * 100 * spot^2 * 0.01
                gex_dollar = sign * g * oi * 100 * (spot ** 2) * 0.01
                rows.append({"K": K, "kind": kind, "gex": gex_dollar})

    if not rows:
        return None
    df = pd.DataFrame(rows)
    by_strike = df.groupby("K")["gex"].sum().sort_index()
    total_gex = float(by_strike.sum())

    cum = by_strike.cumsum()
    flip_strike: float | None = None
    if (cum.iloc[0] < 0 < cum.iloc[-1]) or (cum.iloc[0] > 0 > cum.iloc[-1]):
        sign_change = (np.sign(cum.values[:-1]) * np.sign(cum.values[1:])) < 0
        idx = int(np.argmax(sign_change)) if sign_change.any() else None
        if idx is not None:
            flip_strike = float(by_strike.index[idx])

    calls_only = df[df["kind"] == "C"].groupby("K")["gex"].sum()
    puts_only = df[df["kind"] == "P"].groupby("K")["gex"].sum()
    call_wall = float(calls_only.idxmin()) if not calls_only.empty else float("nan")  # most negative = biggest call wall
    put_wall = float(puts_only.idxmax()) if not puts_only.empty else float("nan")     # most positive = biggest put wall

    pct_to_flip = (spot - flip_strike) / spot if flip_strike else 0.0

    # Score: negative GEX = explosive regime = high alpha.
    # Spot below flip = regime change imminent.
    norm_gex = -total_gex / max(abs(total_gex), 1e9) * 10  # negative GEX -> +10
    flip_bonus = 5 if flip_strike and abs(pct_to_flip) < 0.01 else 0  # within 1% of flip
    wall_bonus = 5 if not math.isnan(call_wall) and abs(call_wall - spot) / spot < 0.02 else 0
    score = max(0.0, min(20.0, norm_gex + flip_bonus + wall_bonus))

    return GexRow(
        ticker=ticker,
        spot=spot,
        total_gex_usd=total_gex,
        gamma_flip=flip_strike,
        largest_call_wall=call_wall,
        largest_put_wall=put_wall,
        pct_distance_to_flip=pct_to_flip,
        score=score,
    )


def compute_gex_universe(tickers: list[str]) -> list[GexRow]:
    out: list[GexRow] = []
    for tk in tickers:
        row = compute_gex(tk)
        if row is not None:
            out.append(row)
    return out


def to_dataframe(rows: list[GexRow]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in rows])


if __name__ == "__main__":
    targets = ["SPY", "QQQ", "IWM", "SOXX", "SMH", "IGV", "XLK", "XLF", "XLE", "GLD", "SLV", "EWY"]
    rows = compute_gex_universe(targets)
    print(to_dataframe(rows).to_string(index=False))
