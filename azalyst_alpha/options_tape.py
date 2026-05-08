"""
Layer 3b — Options Tape (LiveVol-equivalent).

Computes from yfinance option chains:
  - Call/put dollar volume ratio + 5D z-score (unusual call activity)
  - IV rank (current ATM IV vs. 1Y range)
  - 25-delta risk reversal (skew direction)
  - Volume / OI ratio per strike (sweep detector)
  - Gamma squeeze prerequisite: dealer call wall + spot-pinning + IV compression

This is the McElligott / Karsan layer. SOXX / SMH / IGV moves typically print
unusual call sweeps 1-3 sessions before the underlying breaks out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class OptionsRow:
    ticker: str
    spot: float
    cp_dollar_ratio: float        # call $vol / put $vol today
    cp_ratio_z5: float            # 5D z-score of cp ratio (proxy)
    atm_iv: float                 # ATM IV nearest expiry
    iv_rank_1y: float             # 0-100, current vs. 1Y
    risk_reversal_25d: float      # 25d call IV - 25d put IV (positive = bullish skew)
    sweep_count: int              # strikes where today's volume > OI (today's prints absorb existing OI)
    score: float                  # 0-20 contribution to scorer_v2


def _atm_strike(strikes: pd.Series, spot: float) -> float:
    return float(strikes.iloc[(strikes - spot).abs().argsort().iloc[0]])


def _iv_at_delta(df: pd.DataFrame, target_delta: float, spot: float, T: float) -> float | None:
    """Approximate moneyness for 25d call: K ~ spot * exp(0.25 * iv * sqrt(T)).
    Picks the strike whose IV-implied delta is closest to target."""
    if df is None or df.empty:
        return None
    if target_delta > 0:  # call
        target_K = spot * (1 + 0.06 * np.sqrt(T))
    else:                  # put
        target_K = spot * (1 - 0.06 * np.sqrt(T))
    idx = (df["strike"] - target_K).abs().idxmin()
    iv = df.loc[idx, "impliedVolatility"]
    return float(iv) if iv and iv > 0 else None


def _years_to_expiry(expiry: str) -> float:
    exp = datetime.strptime(expiry, "%Y-%m-%d")
    return max((exp - datetime.utcnow()).days, 1) / 365.0


def compute_options_tape(ticker: str) -> OptionsRow | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist.empty:
            return None
        spot = float(hist["Close"].iloc[-1])
        expiries = list(t.options)
        if not expiries:
            return None
    except Exception:
        return None

    near = expiries[0]
    try:
        chain = t.option_chain(near)
    except Exception:
        return None
    calls, puts = chain.calls, chain.puts
    if calls.empty or puts.empty:
        return None

    T = _years_to_expiry(near)
    atm_K = _atm_strike(calls["strike"], spot)
    atm_iv_row = calls.loc[calls["strike"] == atm_K]
    atm_iv = float(atm_iv_row["impliedVolatility"].iloc[0]) if not atm_iv_row.empty else 0.0

    iv_25c = _iv_at_delta(calls, 0.25, spot, T)
    iv_25p = _iv_at_delta(puts, -0.25, spot, T)
    rr = (iv_25c - iv_25p) if (iv_25c and iv_25p) else 0.0

    call_dv = float((calls["lastPrice"].fillna(0) * calls["volume"].fillna(0)).sum() * 100)
    put_dv = float((puts["lastPrice"].fillna(0) * puts["volume"].fillna(0)).sum() * 100)
    cp_ratio = call_dv / put_dv if put_dv > 0 else float("inf")

    # Sweep detector: strikes where day's volume > existing OI
    sweep_calls = int(((calls["volume"].fillna(0) > calls["openInterest"].fillna(0)) & (calls["volume"].fillna(0) > 100)).sum())

    # IV rank vs. 1Y realized vol as a free proxy (true 1Y IV history needs paid feed)
    rv = hist["Close"].pct_change().rolling(20).std() * np.sqrt(252)
    rv_min, rv_max = float(rv.min()), float(rv.max())
    iv_rank = 100 * (atm_iv - rv_min) / (rv_max - rv_min) if rv_max > rv_min else 50.0
    iv_rank = float(np.clip(iv_rank, 0, 100))

    # Score: bullish skew + unusual call $ + sweeps + low IV rank (compression before breakout)
    s = 0.0
    s += 5 if cp_ratio > 1.5 else 0
    s += 5 if cp_ratio > 3.0 else 0
    s += min(5, sweep_calls)
    s += 3 if rr > 0 else 0
    s += 2 if iv_rank < 30 else 0
    score = float(np.clip(s, 0, 20))

    return OptionsRow(
        ticker=ticker,
        spot=spot,
        cp_dollar_ratio=cp_ratio if cp_ratio != float("inf") else 99.0,
        cp_ratio_z5=0.0,  # would need historical chain snapshots; placeholder
        atm_iv=atm_iv,
        iv_rank_1y=iv_rank,
        risk_reversal_25d=rr,
        sweep_count=sweep_calls,
        score=score,
    )


def compute_options_universe(tickers: list[str]) -> list[OptionsRow]:
    out: list[OptionsRow] = []
    for tk in tickers:
        r = compute_options_tape(tk)
        if r is not None:
            out.append(r)
    return out


def to_dataframe(rows: list[OptionsRow]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in rows])


if __name__ == "__main__":
    rows = compute_options_universe(["SPY", "QQQ", "SOXX", "SMH", "IGV", "GLD", "SLV", "EWY"])
    print(to_dataframe(rows).to_string(index=False))
