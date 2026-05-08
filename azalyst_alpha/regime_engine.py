"""
Regime Engine — Lo (adaptive markets) + Antonacci (dual momentum).

Two outputs that gate the entire signal stack:

1. RISK_ON / RISK_OFF / NEUTRAL — absolute momentum gate (Antonacci).
   SPY return > 3M T-bill return AND SPY > 200D MA  -> RISK_ON
   Otherwise                                         -> RISK_OFF
   In RISK_OFF, only defensive ETFs (TLT, GLD, SHV, SHY) can be longed.

2. VOL_REGIME = LOW / MID / HIGH — VIX terciles (1Y rolling).
   Each regime maps to a different factor-weight matrix because momentum
   half-life and signal efficacy differ by regime (Lo).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf


DEFENSIVE_TICKERS = {"TLT", "IEF", "SHY", "SHV", "GLD", "IAU", "BIL", "AGG", "TIP"}


@dataclass(frozen=True)
class RegimeState:
    risk_state: str         # "RISK_ON" / "RISK_OFF" / "NEUTRAL"
    vol_regime: str         # "LOW_VOL" / "MID_VOL" / "HIGH_VOL"
    spy_above_200ma: bool
    spy_excess_vs_tbill_3m: float
    vix_level: float
    vix_percentile_1y: float
    weight_matrix: dict[str, float]


# Regime-conditional weight matrices for scorer_v2.
# Sum to 100 in each regime; reweight factor budget to what works in that tape.
WEIGHT_MATRICES: dict[str, dict[str, float]] = {
    "LOW_VOL": {       # trending, momentum dominates
        "rank": 30, "flow": 22, "options": 18, "rotation": 15, "macro": 8, "news": 7,
    },
    "MID_VOL": {       # base case
        "rank": 25, "flow": 20, "options": 20, "rotation": 15, "macro": 10, "news": 10,
    },
    "HIGH_VOL": {      # dispersion + dealer flows dominate; momentum unreliable
        "rank": 18, "flow": 18, "options": 28, "rotation": 12, "macro": 12, "news": 12,
    },
}


def _spy_close(period: str = "2y") -> pd.Series:
    return yf.download("SPY", period=period, interval="1d",
                       auto_adjust=True, progress=False)["Close"].dropna()


def _vix_close(period: str = "2y") -> pd.Series:
    return yf.download("^VIX", period=period, interval="1d",
                       progress=False)["Close"].dropna()


def _tbill_3m_yield() -> float:
    """3-month T-bill yield via ^IRX (CBOE 13-week rate quoted as %)."""
    try:
        irx = yf.download("^IRX", period="10d", interval="1d", progress=False)["Close"].dropna()
        return float(irx.iloc[-1]) / 100.0
    except Exception:
        return 0.05


def detect_regime() -> RegimeState:
    spy = _spy_close()
    vix = _vix_close()
    if spy.empty or vix.empty:
        return RegimeState(
            risk_state="NEUTRAL", vol_regime="MID_VOL",
            spy_above_200ma=True, spy_excess_vs_tbill_3m=0.0,
            vix_level=20.0, vix_percentile_1y=0.5,
            weight_matrix=WEIGHT_MATRICES["MID_VOL"],
        )

    spy_now = float(spy.iloc[-1])
    spy_200ma = float(spy.rolling(200).mean().iloc[-1])
    above_200 = spy_now > spy_200ma

    spy_3m_ret = float(spy.iloc[-1] / spy.iloc[-63] - 1) if len(spy) >= 63 else 0.0
    tbill_3m = _tbill_3m_yield() / 4
    excess = spy_3m_ret - tbill_3m

    if above_200 and excess > 0:
        risk_state = "RISK_ON"
    elif (not above_200) and excess < 0:
        risk_state = "RISK_OFF"
    else:
        risk_state = "NEUTRAL"

    vix_now = float(vix.iloc[-1])
    vix_1y = vix.iloc[-252:] if len(vix) >= 252 else vix
    vix_pct = float((vix_1y < vix_now).mean())

    if vix_pct < 0.33:
        vol_regime = "LOW_VOL"
    elif vix_pct > 0.67:
        vol_regime = "HIGH_VOL"
    else:
        vol_regime = "MID_VOL"

    return RegimeState(
        risk_state=risk_state,
        vol_regime=vol_regime,
        spy_above_200ma=above_200,
        spy_excess_vs_tbill_3m=excess,
        vix_level=vix_now,
        vix_percentile_1y=vix_pct,
        weight_matrix=WEIGHT_MATRICES[vol_regime],
    )


def passes_absolute_momentum(ticker: str, ret_3m: float, regime: RegimeState) -> bool:
    """Antonacci gate: in RISK_OFF, only defensive ETFs can publish long signals."""
    if regime.risk_state == "RISK_ON":
        return ret_3m > 0
    if regime.risk_state == "RISK_OFF":
        return ticker in DEFENSIVE_TICKERS
    return ret_3m > 0


if __name__ == "__main__":
    r = detect_regime()
    print(f"Risk state:        {r.risk_state}")
    print(f"Vol regime:        {r.vol_regime}")
    print(f"SPY > 200MA:       {r.spy_above_200ma}")
    print(f"SPY 3M excess:     {r.spy_excess_vs_tbill_3m:+.2%}")
    print(f"VIX:               {r.vix_level:.2f} ({r.vix_percentile_1y:.0%}ile)")
    print(f"Weights:           {r.weight_matrix}")
