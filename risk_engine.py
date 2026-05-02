"""
risk_engine.py - AZALYST Institutional Risk Engine

Aladdin-grade portfolio risk analytics:
  1. Correlation / Covariance Analysis  (30-day rolling)
  2. Benchmark Tracking                 (SPY alpha from inception)
  3. Volatility-Adjusted Position Sizing (inverse-vol scaling)
  4. Systematic Rebalancing              (drift detection + auto-trim)
  5. Stress Testing / Scenario Analysis  (factor shocks)
"""

import json
import logging
import math
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np

log = logging.getLogger("azalyst.risk")

# ── Constants ────────────────────────────────────────────────────────────────

BENCHMARK_TICKER = "SPY"
TARGET_VOL = 0.15                   # 15% annualised — target portfolio vol
CORRELATION_BLOCK_THRESHOLD = 0.80  # block new entry if max corr > 0.80
CORRELATION_WARN_THRESHOLD  = 0.60  # warn on dashboard if > 0.60
REBALANCE_DRIFT_PCT = 5.0           # trigger rebalance if position drifts > 5% from target
ANNUALISE_FACTOR = math.sqrt(252)   # trading days per year

# Standard shock scenarios (BlackRock / Aladdin style)
STRESS_SCENARIOS = {
    "2008_GFC":        {"equities": -0.40, "bonds": +0.10, "gold": +0.25, "oil": -0.55, "crypto": -0.60},
    "2020_COVID":      {"equities": -0.34, "bonds": +0.05, "gold": +0.03, "oil": -0.65, "crypto": -0.40},
    "RATES_SHOCK_+2%": {"equities": -0.15, "bonds": -0.12, "gold": -0.05, "oil": -0.10, "crypto": -0.20},
    "USD_SPIKE_+10%":  {"equities": -0.08, "bonds": +0.02, "gold": -0.12, "oil": -0.15, "crypto": -0.10},
    "VIX_SPIKE_40":    {"equities": -0.18, "bonds": +0.04, "gold": +0.08, "oil": -0.20, "crypto": -0.25},
}

# ETF → factor sensitivity mapping (sector-based heuristic)
SECTOR_FACTOR_MAP = {
    "defense":              "equities",
    "defense_aerospace":    "equities",
    "india_equity":         "equities",
    "banking_financial":    "equities",
    "technology_ai":        "equities",
    "cybersecurity":        "equities",
    "emerging_markets":     "equities",
    "nuclear_uranium":      "equities",
    "gold_precious_metals": "gold",
    "energy_oil":           "oil",
    "commodities_mining":   "oil",
    "crypto_digital":       "crypto",
}

TICKER_FACTOR_MAP = {
    "AGG": "bonds",
    "BHARATBOND": "bonds",
    "BND": "bonds",
    "BOND": "bonds",
    "GLDM": "gold",
    "GDX": "gold",
    "GDXJ": "gold",
    "GOLDBEES": "gold",
    "HDFCGOLD": "gold",
    "IBIT": "crypto",
    "BITQ": "crypto",
    "TIP": "bonds",
    "TLT": "bonds",
    "USO": "oil",
    "IXC": "oil",
    "XLE": "oil",
}

# ── Yahoo Finance Helpers ────────────────────────────────────────────────────

def _fetch_chart_points(
    ticker: str,
    range_str: Optional[str] = "1mo",
    interval: str = "1d",
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
) -> Optional[List[Tuple[datetime, float]]]:
    """Fetch dated historical closes from Yahoo Finance."""
    try:
        if start_dt and end_dt:
            period1 = int((start_dt - timedelta(days=5)).timestamp())
            period2 = int((end_dt + timedelta(days=5)).timestamp())
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                f"?interval={interval}&period1={period1}&period2={period2}"
            )
        else:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                f"?interval={interval}&range={range_str}"
            )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        chart = result[0]
        closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        timestamps = chart.get("timestamp", [])
        output = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            output.append((datetime.fromtimestamp(ts, tz=timezone.utc), float(close)))
        return output
    except Exception as exc:
        log.warning("Chart fetch failed for %s: %s", ticker, exc)
        return None


def _fetch_chart(ticker: str, range_str: str = "1mo", interval: str = "1d") -> Optional[List[float]]:
    """Fetch historical closing prices from Yahoo Finance."""
    points = _fetch_chart_points(ticker, range_str=range_str, interval=interval)
    if not points:
        return None
    return [close for _, close in points]


def fetch_historical_closes(tickers: List[str], range_str: str = "1mo") -> Dict[str, List[float]]:
    """Fetch 30-day closing prices for multiple tickers in parallel."""
    result: Dict[str, List[float]] = {}

    def _worker(ticker: str) -> Tuple[str, Optional[List[float]]]:
        closes = _fetch_chart(ticker, range_str)
        return ticker, closes

    with ThreadPoolExecutor(max_workers=min(len(tickers), 10)) as executor:
        futures = {executor.submit(_worker, t): t for t in tickers}
        for future in as_completed(futures):
            try:
                ticker, closes = future.result()
                if closes and len(closes) >= 5:
                    result[ticker] = closes
            except Exception:
                pass
    return result


# ── 1. Correlation / Covariance Analysis ─────────────────────────────────────

def _daily_returns(closes: List[float]) -> List[float]:
    """Compute daily log returns from a price series."""
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            returns.append(math.log(closes[i] / closes[i - 1]))
    return returns


def _pearson_correlation(x: List[float], y: List[float]) -> float:
    """Compute Pearson correlation between two return series using NumPy (VectorBT style)."""
    n = min(len(x), len(y))
    if n < 5:
        return 0.0
    arr_x = np.array(x[:n])
    arr_y = np.array(y[:n])
    std_x = np.std(arr_x)
    std_y = np.std(arr_y)
    if std_x == 0 or std_y == 0:
        return 0.0
    corr = np.corrcoef(arr_x, arr_y)[0, 1]
    return round(float(corr), 4)


def compute_correlation_matrix(closes_dict: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]:
    """Compute pairwise correlation matrix from historical closes."""
    tickers = sorted(closes_dict.keys())
    returns = {t: _daily_returns(closes_dict[t]) for t in tickers}
    matrix: Dict[str, Dict[str, float]] = {}
    for i, t1 in enumerate(tickers):
        matrix[t1] = {}
        for j, t2 in enumerate(tickers):
            if i == j:
                matrix[t1][t2] = 1.0
            elif j < i:
                matrix[t1][t2] = matrix[t2][t1]
            else:
                matrix[t1][t2] = _pearson_correlation(returns[t1], returns[t2])
    return matrix


def check_portfolio_correlation(
    existing_tickers: List[str],
    new_ticker: str,
    closes_dict: Optional[Dict[str, List[float]]] = None,
) -> Dict:
    """
    Check if adding new_ticker would create excessive correlation.
    Returns: {blocked: bool, max_corr: float, corr_with: str, all_corrs: dict}
    """
    all_tickers = list(set(existing_tickers + [new_ticker]))
    if closes_dict is None:
        closes_dict = fetch_historical_closes(all_tickers)

    if new_ticker not in closes_dict:
        return {"blocked": False, "max_corr": 0.0, "corr_with": "", "all_corrs": {}}

    new_returns = _daily_returns(closes_dict[new_ticker])
    max_positive_corr = 0.0
    corr_with = ""
    most_negative_corr = 0.0
    negative_with = ""
    all_corrs = {}

    for ticker in existing_tickers:
        if ticker == new_ticker or ticker not in closes_dict:
            continue
        existing_returns = _daily_returns(closes_dict[ticker])
        corr = _pearson_correlation(new_returns, existing_returns)
        all_corrs[ticker] = corr
        if corr > max_positive_corr:
            max_positive_corr = corr
            corr_with = ticker
        if corr < most_negative_corr:
            most_negative_corr = corr
            negative_with = ticker

    blocked = max_positive_corr > CORRELATION_BLOCK_THRESHOLD
    if blocked:
        log.warning(
            "CORRELATION BLOCK: %s has %.2f correlation with %s (threshold: %.2f)",
            new_ticker, max_positive_corr, corr_with, CORRELATION_BLOCK_THRESHOLD,
        )
    return {
        "blocked": blocked,
        "max_corr": round(max_positive_corr, 4),
        "corr_with": corr_with,
        "most_negative_corr": round(most_negative_corr, 4),
        "negative_corr_with": negative_with,
        "all_corrs": {k: round(v, 4) for k, v in all_corrs.items()},
    }


# ── 2. Benchmark Tracking ───────────────────────────────────────────────────

def fetch_benchmark_return(start_date: str, benchmark: str = BENCHMARK_TICKER) -> Dict:
    """
    Compute benchmark (SPY) total return from a start date.
    Returns: {benchmark_return_pct, benchmark_price_start, benchmark_price_now}
    """
    try:
        start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        points = _fetch_chart_points(
            benchmark,
            interval="1d",
            start_dt=start_dt,
            end_dt=now,
        )
        if not points or len(points) < 2:
            return {"benchmark_return_pct": 0.0, "benchmark_price_start": 0, "benchmark_price_now": 0}

        start_price = 0.0
        for ts, close in points:
            if ts.date() >= start_dt.date():
                start_price = close
                break
        if start_price <= 0:
            start_price = points[0][1]

        end_price = points[-1][1]
        ret_pct = round(((end_price - start_price) / start_price) * 100, 2) if start_price > 0 else 0.0

        return {
            "benchmark_return_pct": ret_pct,
            "benchmark_price_start": round(start_price, 2),
            "benchmark_price_now": round(end_price, 2),
            "benchmark_ticker": benchmark,
        }
    except Exception as exc:
        log.warning("Benchmark fetch failed: %s", exc)
        return {"benchmark_return_pct": 0.0, "benchmark_price_start": 0, "benchmark_price_now": 0}


def compute_alpha(portfolio_return_pct: float, benchmark_return_pct: float) -> float:
    """Simple alpha = portfolio return - benchmark return."""
    return round(portfolio_return_pct - benchmark_return_pct, 2)


# ── 3. Volatility-Adjusted Position Sizing ───────────────────────────────────

def compute_volatility(closes_dict: Dict[str, List[float]]) -> Dict[str, float]:
    """Compute annualised realised volatility for each ticker."""
    vol_map: Dict[str, float] = {}
    for ticker, closes in closes_dict.items():
        returns = _daily_returns(closes)
        if len(returns) < 5:
            vol_map[ticker] = TARGET_VOL  # default if insufficient data
            continue
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        daily_vol = math.sqrt(variance)
        annual_vol = round(daily_vol * ANNUALISE_FACTOR, 4)
        vol_map[ticker] = max(annual_vol, 0.01)  # floor at 1% to prevent division issues
    return vol_map


def vol_adjusted_sizing(kelly_fraction: float, ticker_vol: float) -> float:
    """
    Scale position size inversely with realised volatility.
    Higher vol → smaller position. Capped at 2x kelly to prevent oversizing low-vol ETFs.
    """
    if ticker_vol <= 0:
        ticker_vol = TARGET_VOL
    vol_scalar = TARGET_VOL / ticker_vol
    vol_scalar = min(max(vol_scalar, 0.3), 2.0)  # clamp between 0.3x and 2.0x
    adjusted = round(kelly_fraction * vol_scalar, 4)
    return adjusted


# ── 4. Systematic Rebalancing ────────────────────────────────────────────────

def compute_target_weights(positions: List[Dict], portfolio_value: float) -> Dict[str, float]:
    """
    Compute equal-weight target for each position.
    Target = 1/N across all positions, with the remainder as cash target.
    """
    n = len(positions)
    if n == 0 or portfolio_value <= 0:
        return {}
    # Equal-weight target (ex-cash)
    equity_target = 0.90  # 90% in positions, 10% cash target
    per_position = round(equity_target / n, 4)
    targets = {}
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker:
            targets[ticker] = per_position
    targets["CASH"] = round(1.0 - equity_target, 4)
    return targets


def check_rebalance_drift(
    positions: List[Dict],
    cash: float,
    portfolio_value: float,
) -> List[Dict]:
    """
    Identify positions that have drifted beyond REBALANCE_DRIFT_PCT from target.
    Returns list of drift alerts with recommended action.
    """
    if portfolio_value <= 0 or not positions:
        return []

    targets = compute_target_weights(positions, portfolio_value)
    alerts = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        current_value = pos.get("current_price", pos.get("entry_price", 0)) * pos.get("units", 0)
        actual_weight = (current_value / portfolio_value) * 100
        target_weight = targets.get(ticker, 0) * 100
        drift = actual_weight - target_weight

        if abs(drift) > REBALANCE_DRIFT_PCT:
            action = "TRIM" if drift > 0 else "ADD"
            trim_amount = round(abs(drift) / 100 * portfolio_value, 2)
            alerts.append({
                "ticker": ticker,
                "actual_weight_pct": round(actual_weight, 2),
                "target_weight_pct": round(target_weight, 2),
                "drift_pct": round(drift, 2),
                "action": action,
                "amount": trim_amount,
                "etf_name": pos.get("etf_name", ""),
            })

    # Check cash drift
    cash_weight = (cash / portfolio_value) * 100
    cash_target = targets.get("CASH", 0.10) * 100
    cash_drift = cash_weight - cash_target
    if abs(cash_drift) > REBALANCE_DRIFT_PCT:
        alerts.append({
            "ticker": "CASH",
            "actual_weight_pct": round(cash_weight, 2),
            "target_weight_pct": round(cash_target, 2),
            "drift_pct": round(cash_drift, 2),
            "action": "DEPLOY" if cash_drift > 0 else "RAISE",
            "amount": round(abs(cash_drift) / 100 * portfolio_value, 2),
            "etf_name": "Cash Reserve",
        })

    return sorted(alerts, key=lambda a: abs(a["drift_pct"]), reverse=True)


# ── 5. Review Board Change: Trend-Based Confidence & Size Adjustment ────────────────────
# Replaces the binary quant blocker with a graduated adjustment.
# 9-0 panel decision: don't block trades outright — adjust conviction & size.

def compute_trend_adjustment(
    current_price: float,
    ma_200: float,
    ticker: str = "",
) -> Dict[str, float]:
    """
    Return confidence and size multipliers based on 200-day MA relationship.

    - Above MA: no adjustment (multiplier 1.0, size multiplier 1.0)
    - Below MA: confidence multiplier = 1.0 - (distance_in_stddev * 0.3), clamped [0.4, 1.0]
                size multiplier = 0.6 (position is reduced but not eliminated)

    Returns: {"confidence_multiplier": float, "size_multiplier": float, "blocked": False}
    """
    if ma_200 <= 0 or current_price <= 0:
        return {"confidence_multiplier": 1.0, "size_multiplier": 1.0, "blocked": False}

    if current_price >= ma_200:
        return {"confidence_multiplier": 1.0, "size_multiplier": 1.0, "blocked": False}

    # Distance below MA as a fraction of MA
    distance_pct = (ma_200 - current_price) / ma_200
    # Scale: 5% below = 0.2σ → ~0.94 multiplier; 15% below = ~0.6σ → ~0.82 multiplier
    distance_in_stddev = distance_pct * 4.0  # heuristic: 5% ≈ 0.2σ of daily returns

    confidence_multiplier = 1.0 - (distance_in_stddev * 0.3)
    confidence_multiplier = max(min(confidence_multiplier, 1.0), 0.4)
    size_multiplier = 0.6

    log.info(
        "Trend adjustment for %s: price=%.2f, MA200=%.2f, dist=%.1f%% → "
        "conf_mult=%.2f, size_mult=%.2f",
        ticker, current_price, ma_200, distance_pct * 100,
        confidence_multiplier, size_multiplier,
    )

    return {
        "confidence_multiplier": round(confidence_multiplier, 3),
        "size_multiplier": round(size_multiplier, 3),
        "blocked": False,  # Never hard-block; let the human decide
    }


# ── 5. Stress Testing / Scenario Analysis ────────────────────────────────────

def _normalise_sector_tokens(sector: str) -> List[str]:
    raw = (sector or "").lower()
    for token in ("+", "|", ","):
        raw = raw.replace(token, "/")
    raw = raw.replace("&", " ")
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    tokens = []
    for part in parts:
        token = re.sub(r"[^a-z0-9]+", "_", part).strip("_")
        if token:
            tokens.append(token)
    return tokens


def _get_factor(sector: str, ticker: str = "") -> str:
    """Map a position to its primary factor for stress testing."""
    ticker_key = (ticker or "").upper()
    if ticker_key in TICKER_FACTOR_MAP:
        return TICKER_FACTOR_MAP[ticker_key]

    factor_votes: Dict[str, int] = {}
    for token in _normalise_sector_tokens(sector):
        for key, factor in SECTOR_FACTOR_MAP.items():
            if key in token or token in key:
                factor_votes[factor] = factor_votes.get(factor, 0) + 1

    if factor_votes:
        return sorted(
            factor_votes.items(),
            key=lambda item: (item[1], item[0] != "equities"),
            reverse=True,
        )[0][0]
    return "equities"


def stress_test_portfolio(positions: List[Dict], portfolio_value: float) -> Dict:
    """
    Run all stress scenarios against the current portfolio.
    Returns scenario-level P&L impact.
    """
    if not positions or portfolio_value <= 0:
        return {"scenarios": {}, "worst_scenario": "", "worst_loss_pct": 0.0}

    results = {}
    worst_scenario = ""
    worst_loss = 0.0

    for scenario_name, shocks in STRESS_SCENARIOS.items():
        total_impact = 0.0
        position_impacts = []

        for pos in positions:
            current_value = pos.get("current_price", pos.get("entry_price", 0)) * pos.get("units", 0)
            factor = _get_factor(pos.get("sector", ""), pos.get("ticker", ""))
            shock = shocks.get(factor, -0.10)
            impact = round(current_value * shock, 2)
            total_impact += impact
            position_impacts.append({
                "ticker": pos.get("ticker", ""),
                "factor": factor,
                "shock_pct": round(shock * 100, 1),
                "impact": impact,
            })

        loss_pct = round((total_impact / portfolio_value) * 100, 2) if portfolio_value > 0 else 0.0
        results[scenario_name] = {
            "total_impact": round(total_impact, 2),
            "portfolio_loss_pct": loss_pct,
            "position_impacts": position_impacts,
        }

        if loss_pct < worst_loss:
            worst_loss = loss_pct
            worst_scenario = scenario_name

    return {
        "scenarios": results,
        "worst_scenario": worst_scenario,
        "worst_loss_pct": worst_loss,
    }


# ── Full Risk Report (combines all 5 features) ──────────────────────────────

# ── 6. Review Board Change: External Shock Circuit Breaker ────────────────
# Tudor Jones recommendation: don't trade when cross-asset stress indicators spike.
# This stub monitors swap spreads, EM FX vol, and gold/equity correlation.

# Circuit breaker flag — checked by paper_trader before entry
CIRCUIT_BREAKER_ACTIVE = False


def external_shock_check() -> Dict:
    """
    Monitor cross-asset stress indicators and set circuit breaker flag.
    Currently uses placeholder thresholds — will be calibrated with live data.

    Indicators:
        - TED spread proxy (LIBOR-Fed Funds spread equivalent)
        - VIX level (fear gauge)
        - Gold/SPY correlation flip (safe-haven rush)
        - EM currency volatility

    Returns: {circuit_breaker_active, indicators, warnings}
    """
    global CIRCUIT_BREAKER_ACTIVE
    warnings = []
    indicators = {}

    # TODO: Fetch live TED spread from FRED (series: TEDRATE)
    ted_spread = 0.15  # placeholder: normal range 0.10-0.25, stress > 0.50
    indicators["ted_spread"] = ted_spread
    if ted_spread > 0.50:
        warnings.append(f"TED spread spike: {ted_spread:.2f}% — credit stress detected")

    # TODO: Fetch VIX from Yahoo Finance
    vix = 15.0  # placeholder
    indicators["vix"] = vix
    if vix > 35.0:
        warnings.append(f"VIX > 35 ({vix:.1f}) — extreme fear regime")

    # TODO: Compute gold/equity correlation rolling 20-day
    gold_equity_corr = -0.25  # placeholder: typically negative
    indicators["gold_equity_corr"] = gold_equity_corr
    if gold_equity_corr > 0.3:
        warnings.append(f"Gold/Equity correlation positive ({gold_equity_corr:.2f}) — safe-haven bid")

    # TODO: Monitor EM FX vol (JP Morgan EM-VXY or similar)
    em_fx_vol = 0.08  # placeholder: typical 6-10%, stress > 15%
    indicators["em_fx_vol"] = em_fx_vol
    if em_fx_vol > 0.15:
        warnings.append(f"EM FX vol spike: {em_fx_vol:.1%} — carry unwind risk")

    # Set circuit breaker if ≥2 warnings or VIX > 40
    CIRCUIT_BREAKER_ACTIVE = (len(warnings) >= 2) or (vix > 40.0)

    if CIRCUIT_BREAKER_ACTIVE:
        log.warning(
            "EXTERNAL SHOCK CIRCUIT BREAKER ACTIVE — %d warnings: %s",
            len(warnings), "; ".join(warnings),
        )

    return {
        "circuit_breaker_active": CIRCUIT_BREAKER_ACTIVE,
        "indicators": indicators,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ── 7. Review Board Change: Multi-Asset Benchmark ────────────────────────────
# Cliff Asness recommendation: compare against a composite benchmark, not just SPY.

DEFAULT_BENCHMARK_WEIGHTS = {
    "SPY": 0.40,   # Equities
    "GLD": 0.30,   # Gold
    "AGG": 0.20,   # Bonds
    "INDA": 0.10,  # India Equity
}


def fetch_multi_asset_benchmark_return(
    start_date: str,
    weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Compute composite benchmark return from inception.
    Weighted portfolio of SPY + GLD + AGG + INDA by default.

    Returns: {composite_return_pct, per_ticker, weights_used}
    """
    w = weights or DEFAULT_BENCHMARK_WEIGHTS
    per_ticker = {}
    composite_return = 0.0

    for ticker, weight in w.items():
        try:
            bench = fetch_benchmark_return(start_date, ticker)
            ret = bench.get("benchmark_return_pct", 0.0)
            per_ticker[ticker] = {
                "weight": weight,
                "return_pct": ret,
                "contribution": round(ret * weight, 2),
            }
            composite_return += ret * weight
        except Exception as exc:
            log.warning("Multi-asset benchmark: failed for %s: %s", ticker, exc)
            per_ticker[ticker] = {"weight": weight, "return_pct": 0.0, "contribution": 0.0}

    return {
        "composite_return_pct": round(composite_return, 2),
        "per_ticker": per_ticker,
        "weights_used": w,
        "benchmark_name": "Multi-Asset Composite (SPY 40/GLD 30/AGG 20/INDA 10)",
    }


def compute_composite_alpha(
    portfolio_return_pct: float,
    start_date: str,
    weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Compute alpha vs both SPY and the multi-asset composite benchmark.
    """
    spy_bench = fetch_benchmark_return(start_date, "SPY")
    composite_bench = fetch_multi_asset_benchmark_return(start_date, weights)

    return {
        "portfolio_return_pct": portfolio_return_pct,
        "spy_return_pct": spy_bench.get("benchmark_return_pct", 0.0),
        "alpha_vs_spy": round(portfolio_return_pct - spy_bench.get("benchmark_return_pct", 0.0), 2),
        "composite_return_pct": composite_bench["composite_return_pct"],
        "alpha_vs_composite": round(portfolio_return_pct - composite_bench["composite_return_pct"], 2),
        "composite_benchmark_name": composite_bench["benchmark_name"],
    }


# ── 8. Review Board Change: Factor Attribution ─────────────────────────────
# López de Prado / AQR recommendation: regress returns against Fama-French factors.

def factor_attribution(
    portfolio_returns: List[float],
    dates: List[str],
    factor_returns: Optional[Dict[str, List[float]]] = None,
) -> Dict:
    """
    Run a multi-factor regression of portfolio returns against Fama-French
    5-factor + momentum. Uses pre-loaded CSV data (manual step required).

    Args:
        portfolio_returns: list of daily returns (same length as dates)
        dates: list of date strings (YYYY-MM-DD)
        factor_returns: dict of {factor_name: [returns]} — if None, prints guidance

    Returns:
        {alpha_annualized, factor_loadings, r_squared, alpha_t_stat, warning}

    Manual step:
        Download Fama-French 5-factor + momentum CSV from:
        https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
        Place it as data/ff5_factors.csv with columns: date, Mkt-RF, SMB, HML, RMW, CMA, Mom
    """
    if factor_returns is None:
        log.warning(
            "Factor attribution requires Fama-French factor data. "
            "Place CSV at data/ff5_factors.csv. See docstring for instructions."
        )
        return {
            "status": "SKIPPED",
            "reason": "No factor data provided. Download Fama-French 5-factor CSV.",
            "alpha_annualized": 0.0,
            "factor_loadings": {},
            "r_squared": 0.0,
            "alpha_t_stat": 0.0,
            "warning": "MANUAL STEP: Download ff5_factors.csv to data/ folder",
        }

    try:
        import numpy as np
        port_arr = np.array(portfolio_returns)

        # Align factor arrays with portfolio
        factor_names = list(factor_returns.keys())
        X_list = []
        for fn in factor_names:
            factor_arr = np.array(factor_returns[fn])
            min_len = min(len(port_arr), len(factor_arr))
            X_list.append(factor_arr[:min_len])

        min_len = min(len(port_arr), min(len(x) for x in X_list)) if X_list else len(port_arr)
        y = port_arr[:min_len]
        X = np.column_stack([x[:min_len] for x in X_list])
        X = np.column_stack([np.ones(min_len), X])  # add intercept

        # OLS regression: (X'X)^-1 X'y
        XtX_inv = np.linalg.inv(X.T @ X)
        beta = XtX_inv @ X.T @ y
        y_pred = X @ beta
        residuals = y - y_pred

        # R-squared
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Standard errors
        sigma_sq = ss_res / (min_len - len(beta))
        se = np.sqrt(np.diag(sigma_sq * XtX_inv))
        t_stats = beta / se

        alpha_annualized = beta[0] * 252  # annualize daily alpha
        alpha_t_stat = t_stats[0]

        loadings = {"alpha": round(beta[0], 6)}
        for i, fn in enumerate(factor_names):
            loadings[fn] = round(beta[i + 1], 6)

        warning = ""
        if abs(alpha_t_stat) < 1.5:
            warning = (
                f"Alpha t-stat = {alpha_t_stat:.2f} (< 1.5) — "
                f"insufficient evidence of genuine alpha. "
                f"Returns may be explained by factor exposures."
            )

        return {
            "status": "COMPLETE",
            "alpha_annualized": round(alpha_annualized, 4),
            "alpha_daily": round(beta[0], 6),
            "factor_loadings": loadings,
            "r_squared": round(r_squared, 4),
            "alpha_t_stat": round(alpha_t_stat, 2),
            "observations": min_len,
            "warning": warning,
        }

    except Exception as exc:
        log.error("Factor attribution failed: %s", exc)
        return {
            "status": "ERROR",
            "reason": str(exc),
            "alpha_annualized": 0.0,
            "factor_loadings": {},
            "r_squared": 0.0,
            "alpha_t_stat": 0.0,
            "warning": "Factor attribution computation failed.",
        }


def generate_risk_report(
    portfolio: Dict,
    portfolio_value: float,
    portfolio_return_pct: float,
) -> Dict:
    """
    Generate a comprehensive institutional-grade risk report.
    Called by generate_dashboard.py to populate status.json.
    """
    positions = portfolio.get("open_positions", [])
    cash = portfolio.get("cash_inr", 0)

    # Extract tickers
    tickers = [pos.get("ticker", "") for pos in positions if pos.get("ticker")]
    if not tickers:
        return _empty_report()

    # 1. Fetch historical prices (single parallel call for all tickers + benchmark)
    all_tickers = list(set(tickers + [BENCHMARK_TICKER]))
    closes_dict = fetch_historical_closes(all_tickers, "1mo")

    # 2. Correlation matrix
    portfolio_closes = {t: closes_dict[t] for t in tickers if t in closes_dict}
    corr_matrix = compute_correlation_matrix(portfolio_closes) if len(portfolio_closes) >= 2 else {}

    # Find max off-diagonal correlation
    max_corr = 0.0
    max_corr_pair = ("", "")
    most_negative_corr = 0.0
    most_negative_pair = ("", "")
    corr_tickers = sorted(corr_matrix.keys())
    for i, t1 in enumerate(corr_tickers):
        for j, t2 in enumerate(corr_tickers):
            if i < j:
                c = corr_matrix.get(t1, {}).get(t2, 0)
                if c > max_corr:
                    max_corr = c
                    max_corr_pair = (t1, t2)
                if c < most_negative_corr:
                    most_negative_corr = c
                    most_negative_pair = (t1, t2)

    # 3. Volatility
    vol_map = compute_volatility(portfolio_closes) if portfolio_closes else {}
    portfolio_avg_vol = round(
        sum(vol_map.values()) / len(vol_map), 4
    ) if vol_map else 0.0

    # 4. Benchmark tracking
    # Use earliest position entry date as inception
    entry_dates = [pos.get("entry_date", "") for pos in positions if pos.get("entry_date")]
    inception = min(entry_dates) if entry_dates else datetime.now(timezone.utc).isoformat()
    benchmark_data = fetch_benchmark_return(inception)
    alpha = compute_alpha(portfolio_return_pct, benchmark_data.get("benchmark_return_pct", 0))

    # 5. Rebalancing drift
    drift_alerts = check_rebalance_drift(positions, cash, portfolio_value)

    # 6. Stress testing
    stress_results = stress_test_portfolio(positions, portfolio_value)

    # Serialize correlation matrix for JSON (convert nested dict)
    corr_serializable = {}
    for t1 in corr_matrix:
        corr_serializable[t1] = {t2: round(v, 3) for t2, v in corr_matrix[t1].items()}

    return {
        "correlation": {
            "matrix": corr_serializable,
            "tickers": corr_tickers,
            "max_corr": round(max_corr, 3),
            "max_corr_pair": list(max_corr_pair),
            "most_negative_corr": round(most_negative_corr, 3),
            "most_negative_pair": list(most_negative_pair),
            "status": "HIGH" if max_corr > CORRELATION_WARN_THRESHOLD else "OK",
        },
        "volatility": {
            "per_ticker": {k: round(v * 100, 2) for k, v in vol_map.items()},
            "portfolio_avg_vol_pct": round(portfolio_avg_vol * 100, 2),
            "target_vol_pct": round(TARGET_VOL * 100, 2),
        },
        "benchmark": {
            **benchmark_data,
            "portfolio_return_pct": portfolio_return_pct,
            "alpha": alpha,
        },
        "rebalance": {
            "alerts": drift_alerts,
            "drift_threshold_pct": REBALANCE_DRIFT_PCT,
            "needs_rebalance": len(drift_alerts) > 0,
        },
        "stress_test": stress_results,
    }


def _empty_report() -> Dict:
    """Return empty risk report when no positions exist."""
    return {
        "correlation": {
            "matrix": {},
            "tickers": [],
            "max_corr": 0.0,
            "max_corr_pair": [],
            "most_negative_corr": 0.0,
            "most_negative_pair": [],
            "status": "OK",
        },
        "volatility": {
            "per_ticker": {},
            "portfolio_avg_vol_pct": 0.0,
            "target_vol_pct": round(TARGET_VOL * 100, 2),
        },
        "benchmark": {
            "benchmark_return_pct": 0.0,
            "benchmark_price_start": 0,
            "benchmark_price_now": 0,
            "benchmark_ticker": BENCHMARK_TICKER,
            "portfolio_return_pct": 0.0,
            "alpha": 0.0,
        },
        "rebalance": {
            "alerts": [],
            "drift_threshold_pct": REBALANCE_DRIFT_PCT,
            "needs_rebalance": False,
        },
        "stress_test": {
            "scenarios": {},
            "worst_scenario": "",
            "worst_loss_pct": 0.0,
        },
    }
