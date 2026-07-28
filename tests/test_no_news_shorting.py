"""ETF-01 regression: a bearish news signal must never open a position.

Forensic audit (2026-07-28) found that any HIGH/CRITICAL-severity bearish
headline -- from any sector -- routed straight into an inverse ETF
(SH/PSQ/SDS/SQQQ) via ``is_hedge=True``, bypassing every long-side gate.
11 of 19 closed trades in the live track record were SH entered this way.
This test locks in the fix: BEARISH signals are now informational only.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import azalyst


def _make_cfg():
    cfg = MagicMock()
    cfg.CONFIDENCE_THRESHOLD = 60
    cfg.PAPER_TRADING_ENABLED = True
    return cfg


def _make_bearish_signal():
    return {
        "sector_id": "gold",
        "sector_label": "Gold & Precious Metals",
        "sectors": ["gold"],
        "direction": "BEARISH",
        "severity": "CRITICAL",
        "best_headline": "Gold prices fall as dollar rallies",
    }


def _run_cycle_with_signal(raw_signal):
    """Drive run_intelligence_cycle with one pre-built raw signal and fully
    faked collaborators, patching out every network-touching call so the
    test is hermetic and fast."""
    fetcher = MagicMock()
    # Must be non-empty: azalyst.py only calls classifier.classify_articles()
    # `if articles` -- an empty list short-circuits straight to "0 signals"
    # and the whole cycle no-ops (which would make this test pass for the
    # wrong reason, since the outer function swallows all exceptions).
    fetcher.fetch_all.return_value = [
        {"title": "Gold prices fall as dollar rallies", "link": "http://example.com/1", "source": "test-wire"}
    ]

    classifier = MagicMock()
    classifier.classify_articles.return_value = [dict(raw_signal)]

    scorer = MagicMock()
    scorer.score.return_value = 90
    scorer.breakdown.return_value = {}

    mapper = MagicMock()
    mapper.get_etfs.return_value = {"primary": {"ticker": "GLD", "platform": "Broker"}}

    reporter = MagicMock()

    state = MagicMock()
    state.is_update.return_value = False
    state.filter_new_or_updated.side_effect = lambda signals: signals

    portfolio = MagicMock()
    port_reporter = MagicMock()
    quant_fetcher = MagicMock()
    cfg = _make_cfg()

    with patch("azalyst._market_regime", return_value=(20.0, "NORMAL")), \
         patch("azalyst._market_downturn", return_value=(False, "no downturn")), \
         patch("azalyst._get_jlaw_risk", return_value={
             "distribution_count": 0, "risk_multiplier": 1.0, "regime": "NORMAL",
             "ftd_date": None, "ftd_active": False, "aggressive_multiplier": 1.0,
         }), \
         patch("azalyst.COTFetcher", None), \
         patch("azalyst._COT_AVAILABLE", False), \
         patch("forex_fetcher.ForexFactoryFetcher") as MockForex:
        MockForex.return_value.fetch_events.return_value = []
        azalyst.run_intelligence_cycle(
            fetcher, classifier, scorer, mapper,
            reporter, state, portfolio, port_reporter, quant_fetcher, cfg,
        )

    return mapper, portfolio


def test_critical_bearish_signal_opens_zero_positions():
    mapper, portfolio = _run_cycle_with_signal(_make_bearish_signal())

    portfolio.enter_position.assert_not_called()

    for call in mapper.get_etfs.call_args_list:
        sectors_arg = call.args[0] if call.args else call.kwargs.get("sectors")
        assert sectors_arg != ["bearish_macro"], (
            "mapper.get_etfs must never be called with the bearish_macro bucket "
            "-- news-driven shorting must be fully disabled"
        )


def test_high_severity_bearish_signal_also_opens_zero_positions():
    signal = _make_bearish_signal()
    signal["severity"] = "HIGH"
    mapper, portfolio = _run_cycle_with_signal(signal)

    portfolio.enter_position.assert_not_called()
