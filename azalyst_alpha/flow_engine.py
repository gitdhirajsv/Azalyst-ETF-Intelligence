"""
Layer 2 — ETF Flow Engine.

Free Bloomberg-flows replacement. yfinance does NOT expose reliable historical
shares-outstanding for ETFs (fast_info.shares returns None for most ETFs and is
point-in-time only). So instead of pretending we have AUM-delta data we don't,
we use the cleanest free proxy: **abnormal dollar volume**.

Signal:  flow_proxy_t = (close_t * volume_t)  -  rolling_median_20d(close * volume)
         flow_z5      = z-score of flow_proxy over the last 5 sessions

Why this is a good free proxy: ETF creation/redemption is settled by APs through
secondary-market dollar volume. Bursts of dollar volume that exceed 20-day
median, especially when persistent (5D z-score > 1.5), correlate strongly with
flow into / out of the fund.

Bulk download (one HTTP call for all tickers) so we don't hit the per-ticker
fast_info path that returns None.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class FlowRow:
    ticker: str
    price: float
    ret_1d: float
    dollar_volume_today: float    # close_t * volume_t
    median_dv_20d: float          # 20-day rolling median dollar volume
    flow_proxy_today: float       # dv_today - median_dv_20d
    flow_z5: float                # 5D z-score of flow_proxy
    score: float                  # 0-20 contribution to scorer_v2


def _bulk_history(tickers: list[str], period: str = "60d") -> pd.DataFrame:
    """One HTTP call for all tickers. Returns a DataFrame with MultiIndex
    columns (Field, Ticker) where Field includes Close, Volume."""
    df = yf.download(
        tickers, period=period, interval="1d",
        auto_adjust=True, progress=False, threads=True, group_by="column",
    )
    return df


def _flow_for_ticker(close: pd.Series, volume: pd.Series) -> tuple[float, float, float, float]:
    """Returns (dv_today, median_dv_20d, flow_proxy_today, flow_z5)."""
    close = close.dropna()
    volume = volume.dropna()
    if len(close) < 21 or len(volume) < 21:
        return 0.0, 0.0, 0.0, 0.0
    dv = (close * volume).dropna()
    median_dv = dv.rolling(20).median()
    flow_proxy = (dv - median_dv).fillna(0)
    today = float(flow_proxy.iloc[-1])
    last5 = flow_proxy.iloc[-6:-1]
    mu = float(last5.mean()) if len(last5) > 0 else 0.0
    sd = float(last5.std()) if len(last5) > 0 else 0.0
    sd = sd if sd > 0 else 1.0
    z5 = (today - mu) / sd
    return float(dv.iloc[-1]), float(median_dv.iloc[-1] or 0), today, z5


def compute_flows(tickers: list[str]) -> list[FlowRow]:
    if not tickers:
        return []
    raw = _bulk_history(tickers)
    if raw is None or len(raw) == 0:
        return []

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
        volumes = raw["Volume"]
    else:
        # single-ticker fallback
        closes = raw[["Close"]].rename(columns={"Close": tickers[0]})
        volumes = raw[["Volume"]].rename(columns={"Volume": tickers[0]})

    out: list[FlowRow] = []
    for tk in closes.columns:
        s_close = closes[tk]
        s_vol = volumes[tk] if tk in volumes.columns else pd.Series(dtype=float)
        if s_close.dropna().empty:
            continue
        dv_today, median_dv, flow_today, z5 = _flow_for_ticker(s_close, s_vol)
        if dv_today == 0:
            continue
        ret_1d = float(s_close.pct_change().iloc[-1]) if len(s_close.dropna()) >= 2 else 0.0
        price = float(s_close.dropna().iloc[-1])

        directional = np.sign(ret_1d) == np.sign(flow_today)
        # Score curve: linear in z5 up to z5=2 -> 20 pts; penalize counter-flow.
        base = max(0.0, 10 * z5 * (1.0 if directional else -0.3))
        kicker = 5.0 if z5 > 1.5 else 0.0
        score = float(np.clip(base + kicker, 0.0, 20.0))

        out.append(FlowRow(
            ticker=tk,
            price=price,
            ret_1d=ret_1d,
            dollar_volume_today=dv_today,
            median_dv_20d=median_dv,
            flow_proxy_today=flow_today,
            flow_z5=z5,
            score=score,
        ))
    return out


def to_dataframe(rows: list[FlowRow]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in rows])


if __name__ == "__main__":
    from . import ETF_UNIVERSE
    rows = compute_flows(ETF_UNIVERSE)
    df = to_dataframe(rows).sort_values("flow_z5", ascending=False)
    print(f"rows: {len(rows)} (universe: {len(ETF_UNIVERSE)})")
    print(df.head(20).to_string(index=False))
