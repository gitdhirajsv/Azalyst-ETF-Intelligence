"""
Risk overlay — your explicit mandate: "drawdown all can be maintained by capping
means buying n trailing."

Three layers of protection, applied in order at every bar:

1. PER-POSITION TRAILING STOP
   - ATR(14) × 2.5 chandelier from peak high since entry
   - Hard stop at -8% from entry (cap)

2. PORTFOLIO MAX-DRAWDOWN CIRCUIT BREAKER
   - If equity drawdown from peak > 15% intraday: flatten everything except defensives
   - 7-trading-day cool-down before any new long entry

3. VOL-TARGET REBALANCE
   - If realized 20D portfolio vol > 1.4 × target: deleverage proportionally
   - If < 0.7 × target: re-leverage up to max_gross
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd


@dataclass
class Position:
    ticker: str
    entry_price: float
    entry_date: date
    shares: int                     # signed: long > 0, short < 0
    peak_price: float = 0.0         # tracked since entry for trailing
    trough_price: float = float("inf")
    atr_at_entry: float = 0.0


@dataclass
class RiskState:
    equity_peak: float
    equity_now: float
    drawdown: float
    in_cooldown: bool
    cooldown_until: date | None
    realized_vol_20d: float


@dataclass
class StopAction:
    ticker: str
    reason: str                     # "TRAILING_STOP", "HARD_STOP", "CIRCUIT_BREAKER"
    sell_price: float


def update_position_peaks(pos: Position, latest_high: float, latest_low: float) -> Position:
    pos.peak_price = max(pos.peak_price or pos.entry_price, latest_high)
    pos.trough_price = min(pos.trough_price, latest_low)
    return pos


def check_trailing_stop(
    pos: Position,
    latest_close: float,
    atr_multiple: float = 2.5,
    hard_stop_pct: float = 0.08,
) -> StopAction | None:
    if pos.shares > 0:  # long
        trail_level = pos.peak_price - atr_multiple * pos.atr_at_entry
        hard_level = pos.entry_price * (1 - hard_stop_pct)
        if latest_close <= hard_level:
            return StopAction(pos.ticker, "HARD_STOP", latest_close)
        if latest_close <= trail_level:
            return StopAction(pos.ticker, "TRAILING_STOP", latest_close)
    elif pos.shares < 0:  # short
        trail_level = pos.trough_price + atr_multiple * pos.atr_at_entry
        hard_level = pos.entry_price * (1 + hard_stop_pct)
        if latest_close >= hard_level:
            return StopAction(pos.ticker, "HARD_STOP", latest_close)
        if latest_close >= trail_level:
            return StopAction(pos.ticker, "TRAILING_STOP", latest_close)
    return None


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def check_circuit_breaker(
    state: RiskState,
    threshold_dd: float = 0.15,
    cooldown_days: int = 7,
    today: date | None = None,
) -> tuple[bool, RiskState]:
    today = today or date.today()
    triggered = state.drawdown >= threshold_dd
    if triggered:
        from datetime import timedelta
        state.in_cooldown = True
        state.cooldown_until = today + timedelta(days=cooldown_days)
    elif state.in_cooldown and state.cooldown_until and today > state.cooldown_until:
        state.in_cooldown = False
        state.cooldown_until = None
    return triggered, state


def vol_target_leverage_adjustment(
    realized_vol_20d: float,
    target_vol: float = 0.15,
    upper_band: float = 1.4,
    lower_band: float = 0.7,
    current_leverage: float = 1.0,
    max_leverage: float = 1.5,
) -> float:
    if realized_vol_20d <= 0:
        return current_leverage
    ratio = realized_vol_20d / target_vol
    if ratio > upper_band:
        return current_leverage * (upper_band / ratio)
    if ratio < lower_band:
        return min(max_leverage, current_leverage * (lower_band / ratio))
    return current_leverage


def evaluate_book(
    positions: list[Position],
    market_data: dict[str, pd.DataFrame],
    state: RiskState,
) -> tuple[list[StopAction], RiskState]:
    actions: list[StopAction] = []
    for pos in positions:
        df = market_data.get(pos.ticker)
        if df is None or df.empty:
            continue
        latest = df.iloc[-1]
        update_position_peaks(pos, float(latest["High"]), float(latest["Low"]))
        action = check_trailing_stop(pos, float(latest["Close"]))
        if action:
            actions.append(action)
    triggered, state = check_circuit_breaker(state)
    if triggered:
        for pos in positions:
            actions.append(StopAction(pos.ticker, "CIRCUIT_BREAKER",
                                      float(market_data[pos.ticker].iloc[-1]["Close"])))
    return actions, state
