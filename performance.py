"""
performance.py — AZALYST ETF Intelligence Performance Analytics

CFA L3-aligned portfolio performance metrics and Minervini-style trade analytics.
Designed for the ETF paper-trading system, consuming equity curve snapshots and
closed trade history from PaperPortfolio.

References:
  - CFA L3 LM01: Portfolio Performance Evaluation (Sharpe, Sortino, IR, up/down capture)
  - CFA L1V9: Portfolio Management (VaR, CVaR, CAPM)
  - Minervini: "Think and Trade Like a Champion" Section 9 (R-multiples, expectancy)
  - Strachman: "Getting Started in Hedge Funds" (risk budgeting, drawdown)
"""

import math
import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger("azalyst.performance")

# Risk-free rate assumption (annualized). Use ~5% for current T-Bill environment.
RISK_FREE_RATE = 0.05
TRADING_DAYS_PER_YEAR = 252


# =====================================================================
#  EQUITY-CURVE METRICS (CFA L3 Portfolio Performance Evaluation)
# =====================================================================

def daily_returns(equity_series: List[float]) -> np.ndarray:
    """Compute daily simple returns from an equity time series."""
    eq = np.array(equity_series, dtype=float)
    return eq[1:] / eq[:-1] - 1.0


def sharpe_ratio(equity_series: List[float], risk_free: float = RISK_FREE_RATE) -> Optional[float]:
    """Annualized Sharpe Ratio = (R_p - R_f) / σ_p.

    CFA L3: "The Sharpe ratio is the most commonly used measure of
    risk-adjusted return."
    """
    if len(equity_series) < 3:
        return None
    rets = daily_returns(equity_series)
    daily_rf = (1 + risk_free) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess = rets - daily_rf
    if np.std(excess) == 0:
        return None
    return round(float(np.mean(excess) / np.std(excess) * math.sqrt(TRADING_DAYS_PER_YEAR)), 4)


def sortino_ratio(equity_series: List[float], risk_free: float = RISK_FREE_RATE) -> Optional[float]:
    """Sortino Ratio = (R_p - R_f) / σ_downside.

    Unlike Sharpe, penalizes only downside volatility — better for
    asymmetric return distributions typical of trend-following.
    """
    if len(equity_series) < 3:
        return None
    rets = daily_returns(equity_series)
    daily_rf = (1 + risk_free) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess = rets - daily_rf
    downside = excess[excess < 0]
    if len(downside) == 0:
        return None
    downside_std = np.std(downside)
    if downside_std == 0:
        return None
    return round(float(np.mean(excess) / downside_std * math.sqrt(TRADING_DAYS_PER_YEAR)), 4)


def information_ratio(
    portfolio_series: List[float],
    benchmark_series: List[float],
) -> Optional[float]:
    """Information Ratio = (R_p - R_b) / tracking_error.

    CFA L3: "The information ratio measures the active return per unit of
    active risk." Higher IR = more consistent alpha generation.
    """
    if len(portfolio_series) < 3 or len(benchmark_series) < 3:
        return None
    n = min(len(portfolio_series), len(benchmark_series))
    p_rets = daily_returns(portfolio_series[:n])
    b_rets = daily_returns(benchmark_series[:n])
    min_len = min(len(p_rets), len(b_rets))
    active = p_rets[:min_len] - b_rets[:min_len]
    te = np.std(active)
    if te == 0:
        return None
    return round(float(np.mean(active) / te * math.sqrt(TRADING_DAYS_PER_YEAR)), 4)


def calmar_ratio(equity_series: List[float]) -> Optional[float]:
    """Calmar Ratio = annualized_return / |max_drawdown|.

    High Calmar = attractive returns relative to worst-case loss.
    """
    if len(equity_series) < 3:
        return None
    rets = daily_returns(equity_series)
    ann_ret = float(np.mean(rets) * TRADING_DAYS_PER_YEAR)
    mdd = max_drawdown(equity_series)
    if mdd is None or mdd == 0:
        return None
    return round(ann_ret / abs(mdd), 4)


def max_drawdown(equity_series: List[float]) -> Optional[float]:
    """Maximum peak-to-trough drawdown as a decimal (e.g., -0.12 = 12% loss)."""
    if len(equity_series) < 2:
        return None
    eq = np.array(equity_series)
    running_max = np.maximum.accumulate(eq)
    drawdowns = eq / running_max - 1.0
    return round(float(np.min(drawdowns)), 6)


def max_drawdown_duration(equity_series: List[float]) -> Optional[int]:
    """Longest drawdown duration in periods (days if daily data)."""
    if len(equity_series) < 2:
        return None
    eq = np.array(equity_series)
    running_max = np.maximum.accumulate(eq)
    in_drawdown = eq < running_max
    max_dur = 0
    current_dur = 0
    for is_dd in in_drawdown:
        if is_dd:
            current_dur += 1
            max_dur = max(max_dur, current_dur)
        else:
            current_dur = 0
    return max_dur


def up_down_capture(
    portfolio_series: List[float],
    benchmark_series: List[float],
) -> Optional[Dict[str, float]]:
    """Up/Down capture ratios — CFA L3 manager evaluation.

    Up capture > 100% and down capture < 100% = ideal asymmetry.
    """
    if len(portfolio_series) < 3 or len(benchmark_series) < 3:
        return None
    n = min(len(portfolio_series), len(benchmark_series))
    p_rets = daily_returns(portfolio_series[:n])
    b_rets = daily_returns(benchmark_series[:n])
    min_len = min(len(p_rets), len(b_rets))
    p_rets = p_rets[:min_len]
    b_rets = b_rets[:min_len]

    up_mask = b_rets > 0
    down_mask = b_rets < 0

    if np.sum(up_mask) == 0 or np.sum(down_mask) == 0:
        return None

    up_capture = float(np.mean(p_rets[up_mask]) / np.mean(b_rets[up_mask]) * 100)
    down_capture = float(np.mean(p_rets[down_mask]) / np.mean(b_rets[down_mask]) * 100)

    return {
        "up_capture_pct": round(up_capture, 2),
        "down_capture_pct": round(down_capture, 2),
    }


# =====================================================================
#  RISK METRICS (CFA L1V9 / L3 Risk Management)
# =====================================================================

def historical_var(equity_series: List[float], confidence: float = 0.95) -> Optional[float]:
    """Historical Value at Risk — CFA L1V9.

    Returns the daily loss threshold at the given confidence level.
    E.g., VaR(95%) = -2.1% means on 95% of days, the loss won't exceed 2.1%.
    """
    if len(equity_series) < 10:
        return None
    rets = daily_returns(equity_series)
    return round(float(np.percentile(rets, (1 - confidence) * 100)), 6)


def conditional_var(equity_series: List[float], confidence: float = 0.95) -> Optional[float]:
    """Conditional VaR (Expected Shortfall) — CFA L3 Risk Management.

    Average loss given that VaR has been breached. CVaR > VaR always;
    it captures tail risk better than VaR alone.
    """
    if len(equity_series) < 10:
        return None
    rets = daily_returns(equity_series)
    var_threshold = np.percentile(rets, (1 - confidence) * 100)
    tail = rets[rets <= var_threshold]
    if len(tail) == 0:
        return None
    return round(float(np.mean(tail)), 6)


def compute_beta(
    portfolio_series: List[float],
    benchmark_series: List[float],
) -> Optional[float]:
    """Portfolio beta via OLS regression against benchmark (CAPM).

    CFA L1V9: β = Cov(R_p, R_m) / Var(R_m).
    """
    if len(portfolio_series) < 10 or len(benchmark_series) < 10:
        return None
    n = min(len(portfolio_series), len(benchmark_series))
    p_rets = daily_returns(portfolio_series[:n])
    b_rets = daily_returns(benchmark_series[:n])
    min_len = min(len(p_rets), len(b_rets))
    p_rets = p_rets[:min_len]
    b_rets = b_rets[:min_len]
    cov = np.cov(p_rets, b_rets)[0, 1]
    var_b = np.var(b_rets)
    if var_b == 0:
        return None
    return round(float(cov / var_b), 4)


def treynor_ratio(
    portfolio_series: List[float],
    benchmark_series: List[float],
    risk_free: float = RISK_FREE_RATE,
) -> Optional[float]:
    """Treynor Ratio = (R_p - R_f) / β.

    CFA L3: Risk-adjusted return per unit of systematic (market) risk.
    """
    beta = compute_beta(portfolio_series, benchmark_series)
    if beta is None or beta == 0:
        return None
    p_rets = daily_returns(portfolio_series)
    ann_ret = float(np.mean(p_rets) * TRADING_DAYS_PER_YEAR)
    return round((ann_ret - risk_free) / beta, 4)


def jensens_alpha(
    portfolio_series: List[float],
    benchmark_series: List[float],
    risk_free: float = RISK_FREE_RATE,
) -> Optional[float]:
    """Jensen's Alpha = R_p - [R_f + β(R_m - R_f)].

    CFA L3: True risk-adjusted excess return accounting for systematic risk.
    Positive = outperformance after adjusting for beta exposure.
    """
    beta = compute_beta(portfolio_series, benchmark_series)
    if beta is None:
        return None
    p_rets = daily_returns(portfolio_series)
    b_rets = daily_returns(benchmark_series)
    n = min(len(p_rets), len(b_rets))
    ann_p = float(np.mean(p_rets[:n]) * TRADING_DAYS_PER_YEAR)
    ann_b = float(np.mean(b_rets[:n]) * TRADING_DAYS_PER_YEAR)
    return round(ann_p - (risk_free + beta * (ann_b - risk_free)), 4)


# =====================================================================
#  TRADE-LEVEL METRICS (Minervini / Trading Skill)
# =====================================================================

def trade_analytics(closed_trades: List[Dict]) -> Dict:
    """Minervini-style trade analytics from closed trade history.

    Computes win rate, profit factor, expectancy, average R-multiple,
    and average holding period. Includes partial profit events if available.

    References:
      - "Think and Trade Like a Champion" Section 9
      - "Trade Like a Stock Market Wizard" Chapter on trade review
    """
    if not closed_trades:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "expectancy_per_trade": 0.0,
            "avg_r_multiple": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "avg_hold_days": 0,
            "largest_win_pct": 0.0,
            "largest_loss_pct": 0.0,
        }

    winners = [t for t in closed_trades if t.get("realised_pnl", 0) > 0]
    losers = [t for t in closed_trades if t.get("realised_pnl", 0) < 0]
    flat = [t for t in closed_trades if t.get("realised_pnl", 0) == 0]

    total = len(closed_trades)
    win_rate = len(winners) / total * 100 if total else 0.0

    gross_wins = sum(t.get("realised_pnl", 0) for t in winners)
    gross_losses = abs(sum(t.get("realised_pnl", 0) for t in losers))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf") if gross_wins > 0 else 0.0

    total_pnl = sum(t.get("realised_pnl", 0) for t in closed_trades)
    expectancy = total_pnl / total if total else 0.0

    # R-multiples: PnL / initial risk (entry - stop)
    r_multiples = []
    for t in closed_trades:
        entry = t.get("entry_price", 0) or t.get("entry_price_inr", 0)
        stop = t.get("hard_stop", 0) or t.get("stop_loss", 0)
        pnl_pct = t.get("realised_pnl_pct", 0) or 0
        if entry > 0 and stop > 0 and entry != stop:
            risk_pct = abs(entry - stop) / entry
            r = pnl_pct / 100.0 / risk_pct if risk_pct > 0 else 0
            r_multiples.append(r)

    avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0

    avg_win_pct = (
        sum(t.get("realised_pnl_pct", 0) for t in winners) / len(winners)
        if winners else 0.0
    )
    avg_loss_pct = (
        sum(t.get("realised_pnl_pct", 0) for t in losers) / len(losers)
        if losers else 0.0
    )

    # Hold period
    hold_days = []
    for t in closed_trades:
        hd = t.get("days_held", 0)
        if hd:
            hold_days.append(hd)
    avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0

    pnl_pcts = [t.get("realised_pnl_pct", 0) for t in closed_trades]

    return {
        "total_trades": total,
        "winners": len(winners),
        "losers": len(losers),
        "flat": len(flat),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "∞",
        "expectancy_per_trade": round(expectancy, 2),
        "avg_r_multiple": round(avg_r, 2),
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "avg_hold_days": round(avg_hold, 1),
        "largest_win_pct": round(max(pnl_pcts), 2) if pnl_pcts else 0.0,
        "largest_loss_pct": round(min(pnl_pcts), 2) if pnl_pcts else 0.0,
    }


# =====================================================================
#  FULL REPORT GENERATOR
# =====================================================================

def generate_performance_report(
    equity_curve: List[float],
    benchmark_curve: Optional[List[float]] = None,
    closed_trades: Optional[List[Dict]] = None,
    partial_pnl_events: Optional[List[Dict]] = None,
) -> Dict:
    """Generate a comprehensive performance report.

    Combines equity-curve metrics, risk analytics, and trade-level stats
    into a single dict suitable for logging, dashboards, or Discord reports.
    """
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "has_data": len(equity_curve) >= 3,
    }

    if len(equity_curve) >= 3:
        report["equity_metrics"] = {
            "sharpe_ratio": sharpe_ratio(equity_curve),
            "sortino_ratio": sortino_ratio(equity_curve),
            "calmar_ratio": calmar_ratio(equity_curve),
            "max_drawdown_pct": round(max_drawdown(equity_curve) * 100, 2) if max_drawdown(equity_curve) else None,
            "max_drawdown_duration_days": max_drawdown_duration(equity_curve),
            "total_return_pct": round((equity_curve[-1] / equity_curve[0] - 1) * 100, 2),
            "annualized_return_pct": round(
                float(np.mean(daily_returns(equity_curve)) * TRADING_DAYS_PER_YEAR * 100), 2
            ),
        }

        report["risk_metrics"] = {
            "var_95_daily_pct": round(historical_var(equity_curve, 0.95) * 100, 2) if historical_var(equity_curve, 0.95) else None,
            "var_99_daily_pct": round(historical_var(equity_curve, 0.99) * 100, 2) if historical_var(equity_curve, 0.99) else None,
            "cvar_95_daily_pct": round(conditional_var(equity_curve, 0.95) * 100, 2) if conditional_var(equity_curve, 0.95) else None,
        }

        if benchmark_curve and len(benchmark_curve) >= 3:
            beta = compute_beta(equity_curve, benchmark_curve)
            report["benchmark_metrics"] = {
                "beta": beta,
                "treynor_ratio": treynor_ratio(equity_curve, benchmark_curve),
                "jensens_alpha": jensens_alpha(equity_curve, benchmark_curve),
                "information_ratio": information_ratio(equity_curve, benchmark_curve),
            }
            cap = up_down_capture(equity_curve, benchmark_curve)
            if cap:
                report["benchmark_metrics"].update(cap)

    if closed_trades is not None:
        report["trade_metrics"] = trade_analytics(closed_trades)
        # Include partial profit events in the aggregate stats if available
        if partial_pnl_events:
            report["trade_metrics"]["partial_profit_events"] = len(partial_pnl_events)
            report["trade_metrics"]["partial_profit_total"] = round(
                sum(e.get("pnl", 0) for e in partial_pnl_events), 2
            )

    return report

