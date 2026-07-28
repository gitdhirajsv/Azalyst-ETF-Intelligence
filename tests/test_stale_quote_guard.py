"""ETF-05 regression: a stale quote (e.g. Friday's last close, read from a
weekend/holiday cron run) must be treated as unavailable, not as a live,
tradeable price.

Forensic audit (2026-07-28): the paper-trading control timezone check
(is_weekday_trade_session, IST) does not stop a UTC weekend cron from
calling into price/mark/exit logic; the only thing that could catch a
stale Friday close was the price fetch itself, and it previously accepted
whatever quote Yahoo returned regardless of age. A quote older than
_MAX_QUOTE_AGE_HOURS is now rejected exactly like a fetch failure -- every
call site already fails safe (skip the open/close/mark) on None.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from unittest.mock import patch

import paper_trader
from paper_trader import _yahoo_chart_price, _MAX_QUOTE_AGE_HOURS


def _fake_urlopen(payload: dict):
    body = json.dumps(payload).encode("utf-8")

    @contextmanager
    def _opener(req, timeout=8):
        class _Resp:
            def read(self_inner):
                return body
        yield _Resp()

    return _opener


def _chart_payload(*, regular_market_time=None, timestamps=None, price=100.0):
    result = {
        "meta": {"regularMarketPrice": price},
        "indicators": {"quote": [{"close": [price]}]},
    }
    if regular_market_time is not None:
        result["meta"]["regularMarketTime"] = regular_market_time
    if timestamps is not None:
        result["timestamp"] = timestamps
    return {"chart": {"result": [result]}}


def test_fresh_quote_is_accepted():
    payload = _chart_payload(regular_market_time=time.time() - 60)  # 1 minute old
    with patch("paper_trader.urllib.request.urlopen", side_effect=_fake_urlopen(payload)):
        price = _yahoo_chart_price("GLD")
    assert price == 100.0


def test_quote_older_than_max_age_is_rejected():
    stale_time = time.time() - (25 * 3600)  # 25 hours old
    payload = _chart_payload(regular_market_time=stale_time)
    with patch("paper_trader.urllib.request.urlopen", side_effect=_fake_urlopen(payload)):
        price = _yahoo_chart_price("GLD")
    assert price is None, (
        "a 25-hour-old quote must be treated as unavailable, not as a "
        "tradeable price -- this is exactly the Friday-close-on-Sunday case"
    )


def test_quote_just_under_max_age_is_accepted():
    fresh_time = time.time() - (23 * 3600)  # 23 hours old
    payload = _chart_payload(regular_market_time=fresh_time)
    with patch("paper_trader.urllib.request.urlopen", side_effect=_fake_urlopen(payload)):
        price = _yahoo_chart_price("GLD")
    assert price == 100.0


def test_falls_back_to_timestamp_array_when_regular_market_time_missing():
    stale_time = time.time() - (48 * 3600)
    payload = _chart_payload(timestamps=[stale_time])
    with patch("paper_trader.urllib.request.urlopen", side_effect=_fake_urlopen(payload)):
        price = _yahoo_chart_price("GLD")
    assert price is None


def test_no_timestamp_info_at_all_does_not_block_a_price():
    """If Yahoo's payload carries no timestamp at all, don't invent
    staleness that isn't there -- fall through to the existing price logic."""
    payload = _chart_payload()
    with patch("paper_trader.urllib.request.urlopen", side_effect=_fake_urlopen(payload)):
        price = _yahoo_chart_price("GLD")
    assert price == 100.0


def test_weekend_style_staleness_blocks_a_position_open():
    """Integration-shaped check: get_current_price_inr (used by open/close/
    mark call sites) must return None when the underlying quote is stale,
    exactly as it does on a genuine fetch failure."""
    stale_time = time.time() - (60 * 3600)  # 2.5 days old -- a long weekend
    payload = _chart_payload(regular_market_time=stale_time, price=250.0)
    with patch("paper_trader.urllib.request.urlopen", side_effect=_fake_urlopen(payload)):
        price = paper_trader.get_current_price_inr("SPY", "NYSE", usd_inr_rate=90.0)
    assert price is None
