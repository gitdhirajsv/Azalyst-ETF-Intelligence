"""ETF-05 regression: USD/INR fetch failures must fall back to the
persisted last-known-good rate, not a stale hardcoded constant.

Forensic audit (2026-07-28): fetch_usd_to_inr() fell back to a static
USD_TO_INR = 83.5 constant on any fetch failure. As of this book's July
2026 deposits the live rate is ~94.7 -- a single failed fetch during
mark-to-market could misprice the entire USD book by ~12% in one cycle,
potentially tripping every trailing stop simultaneously.
"""

from __future__ import annotations

from unittest.mock import patch

import paper_trader
from paper_trader import PaperPortfolio, USD_TO_INR, fetch_usd_to_inr


def _bare_portfolio() -> PaperPortfolio:
    pf = PaperPortfolio.__new__(PaperPortfolio)
    pf.last_good_usd_inr_rate = None
    return pf


# ── module-level free function ──────────────────────────────────────────────

def test_fetch_usd_to_inr_returns_live_rate_when_available():
    with patch("paper_trader._yahoo_chart_price", return_value=94.73):
        rate = fetch_usd_to_inr(fallback=80.0)
    assert rate == 94.73


def test_fetch_usd_to_inr_uses_supplied_fallback_on_failure_not_static_constant():
    with patch("paper_trader._yahoo_chart_price", return_value=None):
        rate = fetch_usd_to_inr(fallback=94.73)
    assert rate == 94.73
    assert rate != USD_TO_INR


def test_fetch_usd_to_inr_uses_static_constant_only_when_no_fallback_given():
    with patch("paper_trader._yahoo_chart_price", return_value=None):
        rate = fetch_usd_to_inr(fallback=None)
    assert rate == USD_TO_INR


# ── PaperPortfolio._fetch_usd_inr (persisted last-known-good) ──────────────

def test_fetch_usd_inr_persists_rate_on_success():
    pf = _bare_portfolio()
    with patch("paper_trader._yahoo_chart_price", return_value=94.73):
        rate = pf._fetch_usd_inr()
    assert rate == 94.73
    assert pf.last_good_usd_inr_rate == 94.73


def test_fetch_usd_inr_falls_back_to_persisted_rate_on_outage():
    pf = _bare_portfolio()
    # A prior successful cycle recorded the real rate.
    pf.last_good_usd_inr_rate = 94.73

    with patch("paper_trader._yahoo_chart_price", return_value=None):
        rate = pf._fetch_usd_inr()

    assert rate == 94.73, (
        "a live-fetch outage must fall back to the last real observed rate, "
        "not the stale static constant"
    )
    assert rate != USD_TO_INR


def test_fetch_usd_inr_falls_back_to_static_constant_only_on_a_brand_new_book():
    pf = _bare_portfolio()  # last_good_usd_inr_rate is None -- nothing persisted yet
    with patch("paper_trader._yahoo_chart_price", return_value=None):
        rate = pf._fetch_usd_inr()
    assert rate == USD_TO_INR


def test_fetch_usd_inr_recovers_after_an_outage():
    """Persisted rate must update again once the feed comes back, not stay
    pinned to whatever the outage-time fallback was."""
    pf = _bare_portfolio()
    pf.last_good_usd_inr_rate = 90.0

    with patch("paper_trader._yahoo_chart_price", return_value=None):
        assert pf._fetch_usd_inr() == 90.0

    with patch("paper_trader._yahoo_chart_price", return_value=95.5):
        assert pf._fetch_usd_inr() == 95.5

    assert pf.last_good_usd_inr_rate == 95.5
