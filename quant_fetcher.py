"""
quant_fetcher.py — AZALYST Quantitative Data Integration

Uses yfinance to fetch market fundamentals, technicals, and macro volatility.
Acts as the Phase 2 risk-confirmation layer before executing news-driven trades.
"""

import logging
import yfinance as yf
from functools import lru_cache

log = logging.getLogger("azalyst.quant")

class QuantFetcher:
    def __init__(self):
        self.enabled = True

    @lru_cache(maxsize=32)
    def check_trend_approval(self, ticker: str) -> bool:
        """
        Check if the ETF is currently in a bullish/neutral technical trend.
        Returns False ONLY if the ETF is actively crashing below its 200-day MA.
        If yfinance fails, defaults to True (fails open) so news engine isn't blocked.
        """
        try:
            ticker_obj = yf.Ticker(ticker)
            # Fetch 1 year of daily history
            hist = ticker_obj.history(period="1y")
            if hist.empty or len(hist) < 200:
                return True # Not enough data, fail open
                
            current_price = hist['Close'].iloc[-1]
            ma_200 = hist['Close'].rolling(window=200).mean().iloc[-1]
            
            # Simple blocker: If price is > 5% below its 200-day MA, it's a structural downtrend.
            # Don't buy the dip purely on news if the asset is fundamentally broken.
            if current_price < (ma_200 * 0.95):
                log.warning(f"QUANT BLOCKER: {ticker} is in a structural downtrend (Price: {current_price:.2f}, 200MA: {ma_200:.2f})")
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
