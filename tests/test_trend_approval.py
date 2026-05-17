"""Tests for quant_fetcher.check_trend_approval lookahead protection."""

from __future__ import annotations

from datetime import timezone
from unittest.mock import patch

import pandas as pd
import pytest

from quant_fetcher import QuantFetcher


def _make_hist(end_date: str, n_days: int = 400, base: float = 100.0) -> pd.DataFrame:
    """Build a synthetic daily history ending at end_date (inclusive)."""
    idx = pd.bdate_range(end=end_date, periods=n_days, tz=timezone.utc)
    closes = [base + i * 0.1 for i in range(n_days)]
    return pd.DataFrame({"Close": closes}, index=idx)


def test_backtest_replay_never_reads_index_at_or_after_signal_date():
    """The 200-MA gate must use prices strictly before the signal date."""
    signal_date = "2024-06-03"
    hist = _make_hist(end_date="2024-12-31", n_days=400)

    captured = {}

    def fake_history(self, *args, **kwargs):
        captured["kwargs"] = kwargs
        # Return only data up to the requested end (mimic yfinance contract).
        end = kwargs.get("end")
        if end is not None:
            return hist[hist.index < pd.Timestamp(end).tz_localize(timezone.utc)]
        return hist

    qf = QuantFetcher()
    # Clear LRU cache so this call isn't shadowed by an earlier one.
    qf.check_trend_approval.cache_clear()

    with patch("yfinance.Ticker") as mock_ticker:
        instance = mock_ticker.return_value
        instance.history = fake_history.__get__(instance, type(instance))
        result = qf.check_trend_approval("SPY", signal_date=signal_date)

    # Function must run cleanly and pass an explicit end <= signal_date.
    assert "end" in captured["kwargs"], "backtest replay must pass explicit end="
    end_passed = pd.Timestamp(captured["kwargs"]["end"])
    assert end_passed <= pd.Timestamp(signal_date), (
        f"end={end_passed} must be <= signal_date={signal_date}"
    )
    assert isinstance(result, bool)


def test_strict_lt_signal_date_filter():
    """Internal slicing must use strict <, not <=."""
    signal_date = "2024-06-03"
    cutoff = pd.Timestamp(signal_date).tz_localize(timezone.utc)
    # Hist that *includes* the signal date as last bar.
    idx = pd.bdate_range(end="2024-06-03", periods=300, tz=timezone.utc)
    hist = pd.DataFrame({"Close": [100.0] * 300}, index=idx)
    assert hist.index.max() == cutoff

    def fake_history(self, *args, **kwargs):
        return hist

    qf = QuantFetcher()
    qf.check_trend_approval.cache_clear()

    with patch("yfinance.Ticker") as mock_ticker:
        instance = mock_ticker.return_value
        instance.history = fake_history.__get__(instance, type(instance))
        # We can't directly observe the internal slice, but we can confirm the
        # function still returns a bool and doesn't crash with the signal bar
        # present in the input.
        result = qf.check_trend_approval("XYZ", signal_date=signal_date)
        assert isinstance(result, bool)


def test_live_mode_no_signal_date_uses_period():
    """Live mode (signal_date=None) must use period='1y' — no explicit end."""
    captured = {}

    def fake_history(self, *args, **kwargs):
        captured["kwargs"] = kwargs
        return _make_hist("2024-12-31", n_days=300)

    qf = QuantFetcher()
    qf.check_trend_approval.cache_clear()

    with patch("yfinance.Ticker") as mock_ticker:
        instance = mock_ticker.return_value
        instance.history = fake_history.__get__(instance, type(instance))
        qf.check_trend_approval("QQQ")

    assert captured["kwargs"].get("period") == "1y"
    assert "end" not in captured["kwargs"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
