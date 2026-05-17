"""
quant_fetcher.py — AZALYST Quantitative Data Integration

Uses yfinance to fetch market fundamentals, technicals, and macro volatility.
Acts as the Phase 2 risk-confirmation layer before executing news-driven trades.
"""

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import pandas as pd
import yfinance as yf

log = logging.getLogger("azalyst.quant")

class QuantFetcher:
    def __init__(self):
        self.enabled = True

    @lru_cache(maxsize=32)
    def check_trend_approval(self, ticker: str, signal_date: Optional[str] = None) -> bool:
        """
        Check if the ETF is in a bullish/neutral technical trend at ``signal_date``.

        Returns False ONLY if the ETF was actively trading >5% below its 200-day MA
        as of the signal date. If yfinance fails, defaults to True (fails open).

        Lookahead protection
        --------------------
        - In live use (``signal_date=None``) the function uses prices up to "today",
          which is the only history available at decision time — this is not
          lookahead, it's the standard walk-forward setup.
        - In backtest replay, callers MUST pass ``signal_date`` (ISO string, UTC).
          The function then fetches history with an explicit ``end=signal_date``
          and strictly slices the frame to dates < ``signal_date`` before computing
          the 200-MA, so no price at or after the signal can leak into the gate.
        """
        try:
            ticker_obj = yf.Ticker(ticker)

            if signal_date is None:
                # Live mode: use all data up to now. yfinance returns history up
                # to the latest available bar at call time — that is t-by-t data,
                # not future data.
                hist = ticker_obj.history(period="1y")
                cutoff = None
            else:
                # Backtest mode: bound the request and slice strictly < signal_date.
                cutoff = pd.Timestamp(signal_date)
                if cutoff.tzinfo is None:
                    cutoff = cutoff.tz_localize(timezone.utc)
                # Pull ~14 months ending at signal_date so we have 200 trading days
                # of *prior* history available after slicing strictly < cutoff.
                start = (cutoff - timedelta(days=425)).date().isoformat()
                end = cutoff.date().isoformat()
                hist = ticker_obj.history(start=start, end=end)

            if hist.empty:
                return True  # Not enough data, fail open

            # Normalize index timezone for safe comparison.
            if hist.index.tz is None:
                hist.index = hist.index.tz_localize(timezone.utc)
            else:
                hist.index = hist.index.tz_convert(timezone.utc)

            if cutoff is not None:
                # Strict <: never include the signal-date bar in the 200-MA gate.
                hist = hist[hist.index < cutoff]

            if len(hist) < 200:
                return True  # Not enough prior history, fail open

            window = hist['Close'].tail(200)
            current_price = float(window.iloc[-1])
            ma_200 = float(window.mean())

            # Structural-downtrend blocker: >5% below 200-day MA.
            if current_price < (ma_200 * 0.95):
                log.warning(
                    f"QUANT BLOCKER: {ticker} is in a structural downtrend "
                    f"(Price: {current_price:.2f}, 200MA: {ma_200:.2f})"
                )
                return False

            return True
        except Exception as e:
            log.warning(f"yfinance failed to fetch {ticker}: {e}. Failsafe: Approving trend.")
            return True

    @lru_cache(maxsize=1)
    def get_market_volatility(self) -> float:
        """
        Fetch the current ^VIX value to adjust global portfolio risk limits.
        """
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="5d")
            if not hist.empty:
                return round(float(hist['Close'].iloc[-1]), 2)
            return 15.0 # Default to normal vol if data missing
        except Exception:
            return 15.0
