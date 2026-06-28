--- bottom_detector.py (原始)


+++ bottom_detector.py (修改后)
# bottom_detector.py
"""
Follow-Through Day (FTD) detection for early bullish confirmation.
"""

import pandas as pd
import numpy as np
from typing import Optional
from datetime import datetime

def detect_follow_through_day(spy_close: pd.Series, spy_volume: pd.Series,
                              min_gain_pct: float = 1.7,
                              lookback_low: int = 20,
                              min_days_after_low: int = 4) -> Optional[datetime]:
    """
    Returns date of the most recent FTD, or None.
    FTD: gain >=1.7% on higher volume, occurring at least 4 days after
    the 20-day low.
    """
    if len(spy_close) < lookback_low + min_days_after_low + 1:
        return None

    # Find the lowest close in the lookback period
    low_idx = spy_close.iloc[-lookback_low:].idxmin()
    low_pos = spy_close.index.get_loc(low_idx)

    for i in range(low_pos + min_days_after_low, len(spy_close)):
        date = spy_close.index[i]
        ret = (spy_close.iloc[i] / spy_close.iloc[i-1] - 1) * 100
        if ret >= min_gain_pct:
            vol_today = spy_volume.iloc[i]
            vol_yest = spy_volume.iloc[i-1]
            if vol_today > vol_yest:
                return date
    return None

def get_bottom_signal(spy_data: pd.DataFrame) -> dict:
    """Return dict with FTD date and confidence."""
    close = spy_data['Close']
    volume = spy_data['Volume']
    ftd = detect_follow_through_day(close, volume)
    return {
        'ftd_date': ftd,
        'ftd_active': ftd is not None,
        'aggressive_multiplier': 1.2 if ftd is not None else 1.0
    }