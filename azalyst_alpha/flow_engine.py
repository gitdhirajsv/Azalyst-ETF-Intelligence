"""
Layer 2 — ETF Flow Engine.

Replaces the Bloomberg ETF flow terminal. Issuers publish daily holdings + shares
outstanding in plain JSON/CSV — diffing shares-outstanding day-over-day gives
creation/redemption units (= flow).

Free sources:
  - iShares  (BlackRock):  https://www.ishares.com/us/products/<id>/<slug>/1467271812596.ajax?fileType=json
                           (ticker -> product page exposes a JSON/CSV endpoint with shares outstanding)
  - VanEck:                https://www.vaneck.com/api/etf/<ticker>/dailyholdings/
  - State Street SPDR:     ssga.com per-fund daily PDF/CSV
  - Invesco:               invesco.com/qqq/holdings exposes JSON
  - ETF.com daily flows:   public table, scrapable

The cleanest cross-issuer source is `yfinance.Ticker(t).info` which exposes
`sharesOutstanding` and `totalAssets` daily. Combined with adjusted close,
flow = AUM_t  -  AUM_{t-1} * (1 + return_t).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class FlowRow:
    ticker: str
    aum: float
    shares_out: float
    price: float
    ret_1d: float
    flow_usd_est: float       # USD created/redeemed today (estimate)
    flow_pct_aum: float       # flow as % of AUM
    flow_z5: float            # 5D z-score of flow
    score: float              # 0-20 contribution to scorer_v2


def _fetch_daily_state(ticker: str) -> dict | None:
    """Pull current AUM, shares outstanding, last price."""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        hist = t.history(period="30d", auto_adjust=True)
        if hist.empty:
            return None
        return {
            "ticker": ticker,
            "price": float(hist["Close"].iloc[-1]),
            "shares_out": float(getattr(info, "shares", float("nan"))),
            "aum": float(getattr(info, "shares", float("nan"))) * float(hist["Close"].iloc[-1]),
            "hist": hist[["Close", "Volume"]],
        }
    except Exception:
        return None


def _estimate_flow_history(hist: pd.DataFrame, current_shares: float) -> pd.Series:
    """
    Estimate daily flow as USD-equivalent from historical OHLCV. We don't have
    historical shares-outstanding free, so we proxy flow with:
        flow_proxy = (volume * close) - (20D median dollar volume)
    This isn't true creation/redemption, but it tracks abnormal dollar
    volume which is a strong flow correlate for ETFs.
    """
    dv = hist["Close"] * hist["Volume"]
    median_dv = dv.rolling(20).median()
    return (dv - median_dv).fillna(0)


def compute_flows(tickers: list[str], throttle: float = 0.05) -> list[FlowRow]:
    out: list[FlowRow] = []
    for tk in tickers:
        st = _fetch_daily_state(tk)
        if st is None:
            continue
        hist = st["hist"]
        if len(hist) < 6:
            continue
        ret_1d = float(hist["Close"].pct_change().iloc[-1])
        flow_proxy = _estimate_flow_history(hist, st["shares_out"])
        flow_today = float(flow_proxy.iloc[-1])
        last5 = flow_proxy.iloc[-6:-1]
        mu, sd = float(last5.mean()), float(last5.std() or 1.0)
        z5 = (flow_today - mu) / sd if sd else 0.0
        flow_pct_aum = flow_today / st["aum"] if st["aum"] else 0.0

        # Score: positive flow z-score + price up = highest. Divergence
        # (price up, flow z negative) is a fade signal -> lower score.
        directional = np.sign(ret_1d) == np.sign(flow_today)
        score = max(0.0, min(20.0, 10 * z5 * (1 if directional else -0.3) + 5 * (z5 > 1.5)))
        out.append(FlowRow(
            ticker=tk,
            aum=st["aum"],
            shares_out=st["shares_out"],
            price=st["price"],
            ret_1d=ret_1d,
            flow_usd_est=flow_today,
            flow_pct_aum=flow_pct_aum,
            flow_z5=z5,
            score=score,
        ))
        time.sleep(throttle)
    return out


def to_dataframe(rows: list[FlowRow]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in rows])


if __name__ == "__main__":
    from . import ETF_UNIVERSE
    rows = compute_flows(ETF_UNIVERSE[:25])
    df = to_dataframe(rows).sort_values("flow_z5", ascending=False)
    print(df.head(15).to_string(index=False))
