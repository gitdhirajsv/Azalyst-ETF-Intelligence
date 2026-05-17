"""Tests for cot_fetcher: last_updated_at presence + honest-failure semantics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import cot_fetcher
from cot_fetcher import COTFetcher, COT_MAPPINGS


def _synthetic_records(weeks: int = 130) -> dict:
    """Build synthetic CFTC records spanning ``weeks`` Fridays."""
    start = datetime(2022, 1, 7, tzinfo=timezone.utc)
    out = {}
    for i in range(weeks):
        d = (start + timedelta(weeks=i)).date().isoformat()
        out[d] = {
            "commercial_long": 100000 + i * 50,
            "commercial_short": 80000 + i * 30,
        }
    return out


def test_to_azalyst_signal_includes_last_updated_at():
    """to_azalyst_signal must propagate last_updated_at."""
    fetcher = COTFetcher(enabled=True)
    cot_result = {
        "commodity": "GOLD",
        "sector_id": "gold_precious_metals",
        "velocity": 0.05,
        "velocity_z_score": 1.8,
        "commercial_net": 20000,
        "direction": "BULLISH",
        "latest_date": "2024-12-13",
        "etf_tickers": ["GLDM"],
        "last_updated_at": "2024-12-16T10:00:00+00:00",
        "data_source": "cftc_live",
    }
    signal = fetcher.to_azalyst_signal(cot_result)
    assert "last_updated_at" in signal
    assert signal["last_updated_at"] == "2024-12-16T10:00:00+00:00"
    assert signal["cot_evidence"]["last_updated_at"] == "2024-12-16T10:00:00+00:00"
    assert signal["cot_evidence"]["data_source"] == "cftc_live"


def test_fetch_cot_velocity_returns_none_on_failure(tmp_path, monkeypatch):
    """When CFTC fetch fails AND no cache exists, fetch_cot_velocity returns None."""
    monkeypatch.setattr(cot_fetcher, "COT_CACHE_DIR", tmp_path)
    fetcher = COTFetcher(enabled=True)
    with patch.object(fetcher, "_fetch_cftc_api", return_value=None):
        result = fetcher.fetch_cot_velocity("GOLD")
    assert result is None, "must emit no signal when live fetch fails and no cache"


def test_fetch_cot_velocity_stamps_last_updated_at(tmp_path, monkeypatch):
    """On successful live fetch, result carries a last_updated_at timestamp."""
    monkeypatch.setattr(cot_fetcher, "COT_CACHE_DIR", tmp_path)
    fetcher = COTFetcher(enabled=True)
    records = _synthetic_records(130)
    with patch.object(fetcher, "_fetch_cftc_api", return_value=records):
        result = fetcher.fetch_cot_velocity("GOLD")
    assert result is not None
    assert "last_updated_at" in result
    # Parse it — must be ISO 8601.
    datetime.fromisoformat(result["last_updated_at"])
    assert result.get("data_source") == "cftc_live"


def test_cache_round_trip(tmp_path, monkeypatch):
    """Fresh cache should serve subsequent calls without re-fetching."""
    monkeypatch.setattr(cot_fetcher, "COT_CACHE_DIR", tmp_path)
    fetcher = COTFetcher(enabled=True)
    records = _synthetic_records(130)
    call_count = {"n": 0}

    def fake_fetch(code):
        call_count["n"] += 1
        return records

    with patch.object(fetcher, "_fetch_cftc_api", side_effect=fake_fetch):
        fetcher.fetch_cot_velocity("GOLD")
        fetcher.fetch_cot_velocity("GOLD")
    assert call_count["n"] == 1, "second call within TTL should hit cache"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
