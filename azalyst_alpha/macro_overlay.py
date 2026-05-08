"""
Layer 5 — Macro & Cross-Asset Overlay.

Per-ETF regime fit. The signal isn't "SLV is up 7%" alone — it's
"SLV is up 7% WHILE DXY is down + real yields are falling + gold/silver
ratio breaking" — that's a confirmed regime, not a one-off pop.

For every signal candidate, we compute a regime-fit score in [-1, +1]
based on whether its expected macro tailwinds are aligned today.

Free data: yfinance for proxies (DXY via "DX-Y.NYB", US10Y via "^TNX",
TIPS via "TIP", VIX via "^VIX", gold "GC=F", silver "SI=F", copper "HG=F",
oil "CL=F", BTC "BTC-USD"). FRED API key (free) is optional but adds real
yields and inflation expectations precisely.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from . import MACRO_TICKERS


# Tailwind map: ETF -> list of (macro_ticker, sign, weight)
# sign = +1 means: macro_ticker UP supports ETF UP. -1 means inverse.
ETF_TAILWINDS: dict[str, list[tuple[str, int, float]]] = {
    "SLV":  [("DX-Y.NYB", -1, 0.4), ("^TNX", -1, 0.3), ("GC=F", +1, 0.3)],
    "GLD":  [("DX-Y.NYB", -1, 0.4), ("^TNX", -1, 0.3), ("^VIX", +1, 0.3)],
    "GDX":  [("GC=F", +1, 0.5), ("DX-Y.NYB", -1, 0.3), ("^TNX", -1, 0.2)],
    "GDXJ": [("GC=F", +1, 0.5), ("DX-Y.NYB", -1, 0.3), ("^TNX", -1, 0.2)],
    "SOXX": [("^TNX", -1, 0.3), ("^VIX", -1, 0.3), ("DX-Y.NYB", -1, 0.4)],
    "SMH":  [("^TNX", -1, 0.3), ("^VIX", -1, 0.3), ("DX-Y.NYB", -1, 0.4)],
    "IGV":  [("^TNX", -1, 0.5), ("^VIX", -1, 0.3), ("DX-Y.NYB", -1, 0.2)],
    "XLK":  [("^TNX", -1, 0.5), ("^VIX", -1, 0.3), ("DX-Y.NYB", -1, 0.2)],
    "ARKK": [("^TNX", -1, 0.6), ("^VIX", -1, 0.4)],
    "XLE":  [("CL=F", +1, 0.6), ("DX-Y.NYB", -1, 0.2), ("^TNX", +1, 0.2)],
    "USO":  [("CL=F", +1, 0.8), ("DX-Y.NYB", -1, 0.2)],
    "XLF":  [("^TNX", +1, 0.5), ("^VIX", -1, 0.5)],
    "KBE":  [("^TNX", +1, 0.5), ("^VIX", -1, 0.5)],
    "TLT":  [("^TNX", -1, 0.7), ("^VIX", +1, 0.3)],
    "EWY":  [("DX-Y.NYB", -1, 0.4), ("HG=F", +1, 0.3), ("^VIX", -1, 0.3)],
    "INDA": [("DX-Y.NYB", -1, 0.4), ("CL=F", -1, 0.3), ("^VIX", -1, 0.3)],
    "EWZ":  [("DX-Y.NYB", -1, 0.4), ("HG=F", +1, 0.3), ("CL=F", +1, 0.3)],
    "FXI":  [("DX-Y.NYB", -1, 0.4), ("HG=F", +1, 0.4), ("^VIX", -1, 0.2)],
    "COPX": [("HG=F", +1, 0.7), ("DX-Y.NYB", -1, 0.3)],
    "URA":  [("CL=F", +1, 0.4), ("^TNX", -1, 0.3), ("^VIX", -1, 0.3)],
    "BITO": [("BTC-USD", +1, 0.7), ("^VIX", -1, 0.3)],
    "IBIT": [("BTC-USD", +1, 0.8), ("DX-Y.NYB", -1, 0.2)],
}


@dataclass(frozen=True)
class MacroFit:
    etf: str
    fit_score: float       # in [-1, +1]
    contributors: dict[str, float]
    score: float           # 0-10 contribution to scorer_v2


def _macro_5d_changes() -> dict[str, float]:
    df = yf.download(MACRO_TICKERS, period="15d", interval="1d",
                     auto_adjust=True, progress=False, threads=True)
    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=MACRO_TICKERS[0])
    out: dict[str, float] = {}
    for tk in closes.columns:
        s = closes[tk].dropna()
        if len(s) < 6:
            continue
        out[tk] = float(s.iloc[-1] / s.iloc[-6] - 1)
    return out


def compute_macro_fit(etf: str, macro_changes: dict[str, float] | None = None) -> MacroFit | None:
    macro_changes = macro_changes or _macro_5d_changes()
    tw = ETF_TAILWINDS.get(etf)
    if not tw:
        return MacroFit(etf=etf, fit_score=0.0, contributors={}, score=0.0)
    contributions: dict[str, float] = {}
    fit = 0.0
    total_w = 0.0
    for macro_tk, sign, w in tw:
        chg = macro_changes.get(macro_tk)
        if chg is None:
            continue
        # Tanh-squash so a +1% macro move doesn't blow up
        contrib = sign * np.tanh(chg * 50) * w
        contributions[macro_tk] = float(contrib)
        fit += contrib
        total_w += w
    if total_w == 0:
        return MacroFit(etf=etf, fit_score=0.0, contributors=contributions, score=0.0)
    fit_score = float(np.clip(fit / total_w, -1, 1))
    score = float(np.clip(10 * max(fit_score, 0), 0, 10))
    return MacroFit(etf=etf, fit_score=fit_score, contributors=contributions, score=score)


def compute_universe(etfs: list[str] | None = None) -> list[MacroFit]:
    macro = _macro_5d_changes()
    targets = etfs or list(ETF_TAILWINDS.keys())
    return [m for m in (compute_macro_fit(e, macro) for e in targets) if m is not None]


if __name__ == "__main__":
    for m in sorted(compute_universe(), key=lambda x: -x.score):
        print(f"{m.etf:6s}  fit={m.fit_score:+.2f}  score={m.score:5.2f}  {m.contributors}")
