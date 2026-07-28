"""ETF-03 regression: a max-confidence news signal must not open a trade on
a flat or declining chart, and must be allowed to trade when price confirms.

Forensic audit (2026-07-28): live confidence is ~88% derived from RSS
news-article statistics (scorer.py), while price/flow evidence is capped
at 12 points -- well under the ~60-62 point publish threshold. That meant
a pure tape signal could never open a trade, but a pure news signal
always could, regardless of what the ticker's own chart was doing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import azalyst


# ── Unit tests: _price_confirms_signal in isolation ─────────────────────────

def _make_closes(values):
    idx = pd.bdate_range(end="2026-07-28", periods=len(values))
    return pd.DataFrame({"Close": values}, index=idx)


def test_price_confirms_when_above_50ma_and_positive_20d_return():
    # Rising 70-bar series: last close is above its own 50-bar mean and well
    # above the close 21 bars back.
    closes = [100.0 + i * 0.5 for i in range(70)]
    hist = _make_closes(closes)
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = hist
        result = azalyst._price_confirms_signal("GLD")
    assert result is True


def test_does_not_confirm_on_flat_tape():
    # Perfectly flat: last == its own 50-bar mean (not strictly greater) and
    # 20d return is exactly 0 -- this must NOT count as confirmation.
    closes = [100.0] * 70
    hist = _make_closes(closes)
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = hist
        result = azalyst._price_confirms_signal("GLD")
    assert result is False


def test_does_not_confirm_on_declining_tape():
    closes = [100.0 - i * 0.5 for i in range(70)]
    hist = _make_closes(closes)
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = hist
        result = azalyst._price_confirms_signal("GLD")
    assert result is False


def test_fails_open_to_none_on_insufficient_history():
    hist = _make_closes([100.0] * 10)
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = hist
        result = azalyst._price_confirms_signal("GLD")
    assert result is None


def test_fails_open_to_none_on_fetch_error():
    with patch("yfinance.Ticker", side_effect=RuntimeError("network down")):
        result = azalyst._price_confirms_signal("GLD")
    assert result is None


# ── Integration test: the gate inside run_intelligence_cycle ────────────────

def _rising_history(n=200, start=100.0, step=0.4):
    """A strictly rising daily-close series: price > SMA50 > SMA150, both
    slopes positive -- unambiguously Weinstein Stage 2. Used to keep the
    (now-reachable, see ETF-06) Stage-2 gate from rejecting these
    ETF-03-focused tests on real, non-deterministic network data."""
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


def _run_cycle(price_confirms_return):
    fetcher = MagicMock()
    fetcher.fetch_all.return_value = [
        {"title": "Gold surges", "link": "http://example.com/1", "source": "test-wire"}
    ]
    classifier = MagicMock()
    classifier.classify_articles.return_value = [_make_bullish_signal()]

    scorer = MagicMock()
    scorer.score.return_value = 100  # max-confidence news signal
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

    with patch("azalyst._market_regime", return_value=(20.0, "NORMAL", False)), \
         patch("azalyst._market_downturn", return_value=(False, "no downturn")), \
         patch("azalyst._get_jlaw_risk", return_value={
             "distribution_count": 0, "risk_multiplier": 1.0, "regime": "NORMAL",
             "ftd_date": None, "ftd_active": False, "aggressive_multiplier": 1.0,
         }), \
         patch("azalyst.COTFetcher", None), \
         patch("azalyst._COT_AVAILABLE", False), \
         patch("azalyst._get_5d_return", return_value=0.01), \
         patch("azalyst._price_confirms_signal", return_value=price_confirms_return), \
         patch("paper_trader.get_current_price_inr", return_value=None), \
         patch("yfinance.Ticker", _StageTwoTicker), \
         patch("forex_fetcher.ForexFactoryFetcher") as MockForex:
        MockForex.return_value.fetch_events.return_value = []
        azalyst.run_intelligence_cycle(
            fetcher, classifier, scorer, mapper,
            reporter, state, portfolio, port_reporter, quant_fetcher, cfg,
        )

    return portfolio


def test_max_news_signal_blocked_when_price_does_not_confirm():
    portfolio = _run_cycle(price_confirms_return=False)
    portfolio.enter_position.assert_not_called()


def test_signal_proceeds_when_price_confirms():
    portfolio = _run_cycle(price_confirms_return=True)
    portfolio.enter_position.assert_called_once()


def test_signal_proceeds_on_data_outage_fail_open():
    """A yfinance outage (None) must not silently halt every trade."""
    portfolio = _run_cycle(price_confirms_return=None)
    portfolio.enter_position.assert_called_once()
