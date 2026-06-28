--- distribution_tracker.py (原始)


+++ distribution_tracker.py (修改后)
# distribution_tracker.py
"""
Institutional selling (distribution days) on SPY.
Count over trailing 25 days. 5+ days = defensive mode.
"""

import pandas as pd
import numpy as np
from typing import Tuple

def count_distribution_days(close: pd.Series, volume: pd.Series,
                            lookback: int = 25,
                            min_pct_down: float = 0.2) -> Tuple[int, float, bool]:
    """
    Returns (count, ratio, is_high_risk).
    A distribution day: close down >0.2%, volume > previous day,
    volume > 50-day average.
    """
    if len(close) < 50 + lookback:
        return (0, 0.0, False)

    ret = close.pct_change() * 100
    vol_ma50 = volume.rolling(50).mean()

    # Conditions
    down = ret < -min_pct_down
    vol_up = volume > volume.shift(1)
    vol_high = volume > vol_ma50

    dist = down & vol_up & vol_high

    # Count over last `lookback` days (excluding today)
    count = dist.iloc[-lookback:-1].sum() if lookback > 1 else 0
    ratio = count / min(lookback, len(close))
    is_high_risk = count >= 5

    return (count, ratio, is_high_risk)

def get_spy_risk_multiplier(spy_data: pd.DataFrame) -> dict:
    """Return a dict with multiplier and regime."""
    close = spy_data['Close']
    volume = spy_data['Volume']
    count, _, high_risk = count_distribution_days(close, volume)
    return {
        'distribution_count': int(count),
        'risk_multiplier': 0.5 if high_risk else 1.0,
        'regime': 'DEFENSIVE' if high_risk else 'NORMAL'
    }