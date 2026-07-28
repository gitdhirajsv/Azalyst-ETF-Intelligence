"""ETF-04 regression: the SPY benchmark comparison must use the book's true
funding inception (earliest monthly deposit), not the earliest still-OPEN
position's entry date.

Forensic audit (2026-07-28): risk_engine.generate_risk_report used
`min(entry_dates)` across currently-open positions as the benchmark start
date. If the oldest open position happened to be 5 days old, "portfolio vs
SPY" silently meant SPY's trailing 5-day return, not the true multi-month
money-weighted record -- a benchmark that shrinks every time an old position
closes and a new one opens.
"""

from __future__ import annotations

from unittest.mock import patch

import risk_engine


def _base_portfolio(**overrides):
    portfolio = {
        "open_positions": [
            {"ticker": "GLD", "entry_date": "2026-07-20T00:00:00+00:00"},
        ],
        "cash_inr": 1000.0,
        "monthly_deposits": {"2026-04": 100000.0, "2026-05": 100000.0},
    }
    portfolio.update(overrides)
    return portfolio


def test_inception_uses_earliest_monthly_deposit_not_position_entry_date():
    captured = {}

    def fake_fetch_benchmark_return(start_date, benchmark=risk_engine.BENCHMARK_TICKER):
        captured["start_date"] = start_date
        return {"benchmark_return_pct": 0.0, "benchmark_price_start": 0, "benchmark_price_now": 0}

    portfolio = _base_portfolio()

    with patch("risk_engine.fetch_historical_closes", return_value={}), \
         patch("risk_engine.compute_volatility", return_value={}), \
         patch("risk_engine.check_rebalance_drift", return_value=[]), \
         patch("risk_engine.stress_test_portfolio", return_value={}), \
         patch("risk_engine.fetch_benchmark_return", side_effect=fake_fetch_benchmark_return):
        risk_engine.generate_risk_report(portfolio, portfolio_value=101000.0, portfolio_return_pct=1.0)

    assert captured["start_date"] == "2026-04-01", (
        "inception should be the earliest funded month (2026-04), not the "
        "open position's entry_date (2026-07-20) -- a multi-month record "
        "must not be benchmarked over a handful of trailing days"
    )


def test_falls_back_to_entry_date_when_no_deposit_history():
    captured = {}

    def fake_fetch_benchmark_return(start_date, benchmark=risk_engine.BENCHMARK_TICKER):
        captured["start_date"] = start_date
        return {"benchmark_return_pct": 0.0, "benchmark_price_start": 0, "benchmark_price_now": 0}

    portfolio = _base_portfolio(monthly_deposits={})

    with patch("risk_engine.fetch_historical_closes", return_value={}), \
         patch("risk_engine.compute_volatility", return_value={}), \
         patch("risk_engine.check_rebalance_drift", return_value=[]), \
         patch("risk_engine.stress_test_portfolio", return_value={}), \
         patch("risk_engine.fetch_benchmark_return", side_effect=fake_fetch_benchmark_return):
        risk_engine.generate_risk_report(portfolio, portfolio_value=101000.0, portfolio_return_pct=1.0)

    assert captured["start_date"] == "2026-07-20T00:00:00+00:00"
