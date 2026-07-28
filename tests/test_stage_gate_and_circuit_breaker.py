"""ETF-06 regression: the Stage-2 gate must actually be reachable, and the
external-shock circuit breaker must actually block trades when active.

Forensic audit (2026-07-28) found two dead risk controls:

1. The Stage-2 gate fetched `period="6mo"` (~126 trading-day rows) then
   required `len(hist) >= 160` before calling classify_weinstein_stage --
   a threshold 6 months of daily bars can never reach, so "only Stage 2
   allowed" never filtered a single trade.

2. `from risk_engine import CIRCUIT_BREAKER_ACTIVE` bound a snapshot of
   the value at import time (False). risk_engine later rebinding its own
   module-level global via `global CIRCUIT_BREAKER_ACTIVE` never
   propagates to azalyst's separately-bound name, so the breaker check
   permanently read a stale False regardless of live shock conditions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

import azalyst


# ── (1) Stage-2 gate fetches enough history to actually run ────────────────

def test_stage_gate_no_longer_uses_the_unreachable_6mo_160bar_pattern():
    """Static guard against the exact bug: fetching a per-ticker history
    immediately followed by a `len(hist) >= 160` gate (classify_weinstein_
    stage's floor) using a period that can never satisfy it. This does not
    touch _get_jlaw_risk's own unrelated 6mo SPY fetch (different purpose,
    different requirement), nor the trend-adjustment block's unrelated
    `len(hist) >= 200` check -- only the two classify_weinstein_stage call
    sites, identified by pairing each `history(period=...)` line with the
    very next `len(hist) >= 160` line."""
    import inspect
    import re

    source = inspect.getsource(azalyst)
    # Pair each history() fetch with the len(hist) >= 160 check on the next
    # non-blank line, capturing the requested period.
    pattern = re.compile(
        r'history\(period="([^"]+)"\)\s*\n\s*if not hist\.empty and len\(hist\) >= 160:'
    )
    matches = pattern.findall(source)

    assert len(matches) == 2, (
        f"expected exactly 2 classify_weinstein_stage call sites "
        f"(run_intelligence_cycle, seed_startup_trades), found {len(matches)}"
    )
    assert all(period == "1y" for period in matches), (
        f"every classify_weinstein_stage call site must fetch enough "
        f"history to reach the >=160-bar floor -- found periods {matches}, "
        f"and period='6mo' (~126 trading-day rows) can never satisfy it"
    )


def _declining_history(n=200, start=200.0, step=0.4):
    """A strictly declining daily-close series: price < SMA50 < SMA150,
    both slopes negative -- unambiguously Weinstein Stage 4."""
    idx = pd.bdate_range(end="2026-07-28", periods=n)
    closes = [start - i * step for i in range(n)]
    return pd.DataFrame({"Close": closes}, index=idx)


def test_stage_gate_actually_reachable_and_blocks_a_stage4_ticker():
    """Behavioral proof, not just a period string: feed a real 200-bar
    declining series (Stage 4) through the live entry path and confirm the
    gate fires. Under the pre-fix period="6mo" this could never happen --
    len(hist) was always < 160 so the whole gate body was unreachable."""
    fetcher = MagicMock()
    fetcher.fetch_all.return_value = [
        {"title": "Gold surges", "link": "http://example.com/1", "source": "test-wire"}
    ]
    classifier = MagicMock()
    classifier.classify_articles.return_value = [{
        "sector_id": "gold", "sector_label": "Gold & Precious Metals",
        "sectors": ["gold"], "direction": "BULLISH", "severity": "CRITICAL",
        "best_headline": "Gold surges on safe-haven demand",
    }]
    scorer = MagicMock()
    scorer.score.return_value = 100
    scorer.breakdown.return_value = {}
    mapper = MagicMock()
    mapper.get_etfs.return_value = {"primary": {"ticker": "GLD", "platform": "Broker"}}
    reporter = MagicMock()
    state = MagicMock()
    state.is_update.return_value = False
    state.filter_new_or_updated.side_effect = lambda signals: signals
    portfolio = MagicMock()
    portfolio.enter_position.return_value = {"is_topup": False}
    port_reporter = MagicMock()
    quant_fetcher = MagicMock()
    cfg = MagicMock()
    cfg.CONFIDENCE_THRESHOLD = 60
    cfg.PAPER_TRADING_ENABLED = True

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, period=None):
            # The 200MA trend-adjustment check (a different, unrelated
            # gate) also calls yf.Ticker(...).history(period="1y") earlier
            # in the same code path -- return the same declining series
            # for any period request so both see consistent data.
            return _declining_history()

    with patch("azalyst._market_regime", return_value=(20.0, "NORMAL", False)), \
         patch("azalyst._market_downturn", return_value=(False, "no downturn")), \
         patch("azalyst._get_jlaw_risk", return_value={
             "distribution_count": 0, "risk_multiplier": 1.0, "regime": "NORMAL",
             "ftd_date": None, "ftd_active": False, "aggressive_multiplier": 1.0,
         }), \
         patch("azalyst.COTFetcher", None), \
         patch("azalyst._COT_AVAILABLE", False), \
         patch("azalyst._get_5d_return", return_value=0.01), \
         patch("azalyst._price_confirms_signal", return_value=True), \
         patch("paper_trader.get_current_price_inr", return_value=None), \
         patch("yfinance.Ticker", FakeTicker), \
         patch("forex_fetcher.ForexFactoryFetcher") as MockForex:
        MockForex.return_value.fetch_events.return_value = []
        azalyst.run_intelligence_cycle(
            fetcher, classifier, scorer, mapper,
            reporter, state, portfolio, port_reporter, quant_fetcher, cfg,
        )

    portfolio.enter_position.assert_not_called()


# ── (2) circuit breaker actually blocks trades ──────────────────────────────

def _rising_history(n=200, start=100.0, step=0.4):
    """A strictly rising daily-close series: price > SMA50 > SMA150, both
    slopes positive -- unambiguously Weinstein Stage 2, so the circuit-
    breaker tests below aren't accidentally gated by an unrelated Stage
    rejection."""
    idx = pd.bdate_range(end="2026-07-28", periods=n)
    closes = [start + i * step for i in range(n)]
    return pd.DataFrame({"Close": closes}, index=idx)


class _StageTwoTicker:
    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, period=None):
        return _rising_history()


def _make_bullish_signal():
    return {
        "sector_id": "gold",
        "sector_label": "Gold & Precious Metals",
        "sectors": ["gold"],
        "direction": "BULLISH",
        "severity": "CRITICAL",
        "best_headline": "Gold surges on safe-haven demand",
    }


def _run_cycle(breaker_active):
    fetcher = MagicMock()
    fetcher.fetch_all.return_value = [
        {"title": "Gold surges", "link": "http://example.com/1", "source": "test-wire"}
    ]
    classifier = MagicMock()
    classifier.classify_articles.return_value = [_make_bullish_signal()]

    scorer = MagicMock()
    scorer.score.return_value = 100
    scorer.breakdown.return_value = {}

    mapper = MagicMock()
    mapper.get_etfs.return_value = {"primary": {"ticker": "GLD", "platform": "Broker"}}

    reporter = MagicMock()
    state = MagicMock()
    state.is_update.return_value = False
    state.filter_new_or_updated.side_effect = lambda signals: signals

    portfolio = MagicMock()
    portfolio.enter_position.return_value = {"is_topup": False}
    port_reporter = MagicMock()
    quant_fetcher = MagicMock()
    cfg = MagicMock()
    cfg.CONFIDENCE_THRESHOLD = 60
    cfg.PAPER_TRADING_ENABLED = True

    with patch("azalyst._market_downturn", return_value=(False, "no downturn")), \
         patch("azalyst._get_jlaw_risk", return_value={
             "distribution_count": 0, "risk_multiplier": 1.0, "regime": "NORMAL",
             "ftd_date": None, "ftd_active": False, "aggressive_multiplier": 1.0,
         }), \
         patch("azalyst.COTFetcher", None), \
         patch("azalyst._COT_AVAILABLE", False), \
         patch("azalyst._get_5d_return", return_value=0.01), \
         patch("azalyst._price_confirms_signal", return_value=True), \
         patch("azalyst.external_shock_check", return_value={
             "circuit_breaker_active": breaker_active,
             "indicators": {"vix": 20.0},
             "warnings": [],
         }), \
         patch("azalyst._RISK_ADVANCED", True), \
         patch("paper_trader.get_current_price_inr", return_value=None), \
         patch("yfinance.Ticker", _StageTwoTicker), \
         patch("forex_fetcher.ForexFactoryFetcher") as MockForex:
        MockForex.return_value.fetch_events.return_value = []
        azalyst.run_intelligence_cycle(
            fetcher, classifier, scorer, mapper,
            reporter, state, portfolio, port_reporter, quant_fetcher, cfg,
        )

    return portfolio


def test_circuit_breaker_active_blocks_entry():
    portfolio = _run_cycle(breaker_active=True)
    portfolio.enter_position.assert_not_called()


def test_circuit_breaker_inactive_allows_entry():
    portfolio = _run_cycle(breaker_active=False)
    portfolio.enter_position.assert_called_once()


def test_seeder_blocks_all_seeding_when_circuit_breaker_active():
    state = MagicMock()
    state._state = {
        "gold|precious_metals": {
            "confidence": 95, "direction": "BULLISH", "signal_scope": "global",
            "sector_label": "Gold & Precious Metals",
        },
    }
    mapper = MagicMock()
    portfolio = MagicMock()
    portfolio.open_positions = []
    port_reporter = MagicMock()
    quant_fetcher = MagicMock()
    cfg = MagicMock()
    cfg.PAPER_TRADING_ENABLED = True

    with patch("azalyst._market_regime", return_value=(20.0, "NORMAL", True)), \
         patch("azalyst._market_downturn", return_value=(False, "no downturn")), \
         patch("azalyst._get_jlaw_risk", return_value={
             "distribution_count": 0, "risk_multiplier": 1.0, "regime": "NORMAL",
             "ftd_date": None, "ftd_active": False, "aggressive_multiplier": 1.0,
         }):
        azalyst.seed_startup_trades(state, mapper, portfolio, port_reporter, quant_fetcher, cfg)

    mapper.get_etfs.assert_not_called()
    portfolio.enter_position.assert_not_called()
