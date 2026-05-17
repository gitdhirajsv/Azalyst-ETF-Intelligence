"""Tests for scorer factor caps — sanity checks + zero-signal behaviour."""

from __future__ import annotations

import pytest

from config import Config
from scorer import ConfidenceScorer


def test_sum_of_factor_caps_is_100():
    """The six factor caps must total exactly 100 — the score range."""
    total = (
        Config.SCORER_CAP_SIGNAL_STRENGTH
        + Config.SCORER_CAP_VOLUME_CONFIRMATION
        + Config.SCORER_CAP_SOURCE_DIVERSITY
        + Config.SCORER_CAP_RECENCY
        + Config.SCORER_CAP_GEOPOLITICAL_SEVERITY
        + Config.SCORER_CAP_CROSS_ENGINE_CONFIRMATION
    )
    assert total == 100, f"factor caps must sum to 100, got {total}"


def test_zero_signal_returns_score_under_20():
    """An empty signal must not produce meaningful confidence."""
    scorer = ConfidenceScorer(Config)
    empty_signal = {
        "total_score": 0,
        "avg_article_score": 0,
        "article_count": 0,
        "sources": [],
        "latest_ts": None,
        "severity": "LOW",
        "event_intensity": 0,
        "regions": [],
        "engines": [],
        "consensus_tier": None,
        "evidence": {},
    }
    score = scorer.score(empty_signal, all_articles=[])
    assert score < 20, f"zero-signal input must score < 20, got {score}"


def test_breakdown_returns_all_factor_keys():
    scorer = ConfidenceScorer(Config)
    signal = {
        "total_score": 0,
        "article_count": 0,
        "sources": [],
        "severity": "LOW",
        "regions": ["global"],
    }
    bd = scorer.breakdown(signal, all_articles=[])
    expected = {
        "signal_strength",
        "volume_confirmation",
        "source_diversity",
        "recency",
        "geopolitical_severity",
        "cross_engine_confirmation",
    }
    assert set(bd.keys()) == expected


def test_caps_are_config_driven(monkeypatch):
    """Changing a config cap must propagate to the scorer instance."""

    class StubCfg:
        SCORER_CAP_SIGNAL_STRENGTH = 30
        SCORER_CAP_VOLUME_CONFIRMATION = 18
        SCORER_CAP_SOURCE_DIVERSITY = 18
        SCORER_CAP_RECENCY = 11
        SCORER_CAP_GEOPOLITICAL_SEVERITY = 13
        SCORER_CAP_CROSS_ENGINE_CONFIRMATION = 10

    scorer = ConfidenceScorer(StubCfg)
    assert scorer._caps["signal_strength"] == 30
    assert scorer._caps["recency"] == 11


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
