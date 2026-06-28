# stage_classifier.py
"""
Weinstein Stage Classification for ETFs (Stage 1-4).
Only Stage 2 is eligible for long positions.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional

def slope(series: pd.Series, lookback: int = 10) -> float:
    """Compute linear slope over the last `lookback` periods."""
    if len(series) < lookback:
        return 0.0
    y = series.iloc[-lookback:].values
    x = np.arange(len(y))
    return np.polyfit(x, y, 1)[0]

def classify_weinstein_stage(close: pd.Series) -> Tuple[int, str]:
    """
    Returns (stage, description).
    Stage 2 = Advancing (BUY)
    Stage 3 = Topping (AVOID)
    Stage 4 = Declining (AVOID)
    Stage 1 = Basing (WAIT)
    """
    if len(close) < 160:
        return (0, "Insufficient data")

    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()

    price = close.iloc[-1]
    last_sma50 = sma50.iloc[-1]
    last_sma150 = sma150.iloc[-1]
    slope50 = slope(sma50)
    slope150 = slope(sma150)

    # Stage 2: price > 50MA > 150MA, both rising
    if (price > last_sma50 > last_sma150) and (slope50 > 0) and (slope150 > 0):
        return (2, "Stage 2 – Advancing (BUY)")

    # Stage 4: price < 50MA < 150MA, both falling
    if (price < last_sma50 < last_sma150) and (slope50 < 0) and (slope150 < 0):
        return (4, "Stage 4 – Declining (AVOID)")

    # Stage 3: 150MA rolling over, or price below 150MA
    if (slope150 < 0) or (price < last_sma150):
        return (3, "Stage 3 – Topping/Distribution (AVOID)")

    # Everything else = Stage 1
    return (1, "Stage 1 – Basing (WAIT)")

def apply_stage_gate(close_df: pd.DataFrame, min_stage_allowed: int = 2) -> pd.Series:
    """
    For each ETF (column), returns a boolean mask: True if stage >= min_stage_allowed.
    For long-only, only Stage 2 should pass.
    """
    stages = {}
    for ticker in close_df.columns:
        stage, _ = classify_weinstein_stage(close_df[ticker])
        stages[ticker] = stage
    return pd.Series(stages) >= min_stage_allowed

def get_stage_map(close_df: pd.DataFrame) -> dict:
    """
    Returns a dict mapping ticker -> (stage, description) for all columns.
    Useful for dashboard display.
    """
    stage_map = {}
    for ticker in close_df.columns:
        stage, desc = classify_weinstein_stage(close_df[ticker])
        stage_map[ticker] = {"stage": stage, "description": desc}
    return stage_map
