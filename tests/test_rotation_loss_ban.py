"""ETF-02 regression: rotation must never realize a loss or roundtrip a sector.

Forensic audit (2026-07-28) found the rotation engine had regressed twice:

1. A same-sector veto (XLE -> XLE, -4.62%, 2026-06-14) was fixed in commit
   50e969e (2026-06-25) -- that fix is still correct and this test does not
   touch it.
2. But that same commit silently replaced an older hard rule -- "never
   rotate out at a loss" (commit 0c28054, 2026-04-18: ``if pnl_pct < 0:
   continue``) -- with a "cut losers early" bonus (+10 score for
   pnl_pct < -2.0) that did the opposite: it turned rotation into a
   loss-realization machine chasing whatever sector had the loudest news
   that cycle.

This test locks in the restored hard loss-ban and the raised (3 -> 10 day)
minimum hold, both applied directly to paper_trader.PaperPortfolio's real
rotation-candidate selection -- not a reimplementation of it.
"""

from __future__ import annotations

from datetime import date, timedelta

import paper_trader
from paper_trader import PaperPortfolio, Position, ROTATION_MIN_HOLD_DAYS


def _bare_portfolio() -> PaperPortfolio:
    """A PaperPortfolio with no file I/O, network calls, or deposit logic --
    __init__ is bypassed entirely since _select_rotation_candidate only
    reads self.open_positions."""
    pf = PaperPortfolio.__new__(PaperPortfolio)
    pf.open_positions = []
    pf.open_hedge_positions = []
    return pf


def _make_position(
    ticker: str,
    sector: str,
    confidence: int,
    days_ago: int,
    pnl_pct: float,
) -> Position:
    entry_date = (date.today() - timedelta(days=days_ago)).isoformat()
    entry_price = 100.0
    # unrealised_pnl_pct() = (current_value - invested) / invested * 100
    # with units=1, invested_inr=entry_price: pnl_pct == (current_price - entry_price)/entry_price*100
    current_price = entry_price * (1 + pnl_pct / 100.0)
    pos = Position(
        trade_id=f"T-{ticker}",
        ticker=ticker,
        etf_name=ticker,
        exchange="NYSE",
        platform="Broker",
        sector=sector,
        entry_price=entry_price,
        units=1.0,
        invested_inr=entry_price,
        entry_date=entry_date,
        confidence=confidence,
        severity="MEDIUM",
        signal_headline="synthetic",
    )
    pos.current_price = current_price
    return pos


INCOMING_SIGNAL = {
    "confidence": 95,
    "consensus_tier": "A",
    "sector_label": "Energy / Oil & Gas",
}


def test_losing_position_is_never_a_rotation_candidate():
    pf = _bare_portfolio()
    losing = _make_position(
        "XLE", sector="Energy / Oil & Gas", confidence=70,
        days_ago=ROTATION_MIN_HOLD_DAYS + 5, pnl_pct=-4.62,
    )
    # Different sector than the incoming signal so the same-sector veto
    # cannot be the reason it's excluded -- isolate the loss-ban itself.
    losing.sector = "Banking & Financial Sector"
    pf.open_positions = [losing]

    candidate = pf._select_rotation_candidate(INCOMING_SIGNAL)

    assert candidate is None, (
        "a position with negative unrealized P&L must never be selected for "
        "rotation eviction, regardless of how much stronger the incoming "
        "signal is"
    )


def test_flat_to_small_winner_below_protection_band_still_rotates():
    """Sanity check the ban is loss-specific, not a rotation-disable switch:
    a modest winner (0% < pnl <= 3%) in a DIFFERENT sector, held long enough,
    must remain rotation-eligible."""
    pf = _bare_portfolio()
    modest_winner = _make_position(
        "XLV", sector="Health Care", confidence=70,
        days_ago=ROTATION_MIN_HOLD_DAYS + 1, pnl_pct=1.92,
    )
    pf.open_positions = [modest_winner]

    candidate = pf._select_rotation_candidate(INCOMING_SIGNAL)

    assert candidate is modest_winner


def test_minimum_hold_blocks_rotation_before_ten_days():
    pf = _bare_portfolio()
    too_fresh = _make_position(
        "XLV", sector="Health Care", confidence=70,
        days_ago=ROTATION_MIN_HOLD_DAYS - 1, pnl_pct=1.5,
    )
    pf.open_positions = [too_fresh]

    candidate = pf._select_rotation_candidate(INCOMING_SIGNAL)

    assert candidate is None, (
        f"a position held fewer than {ROTATION_MIN_HOLD_DAYS} days must not "
        "be rotation-eligible"
    )


def test_same_sector_veto_still_holds():
    """Regression guard for the earlier (already-fixed) XLE -> XLE bug --
    make sure this remediation didn't accidentally weaken it."""
    pf = _bare_portfolio()
    same_sector = _make_position(
        "XLE", sector="Energy / Oil & Gas", confidence=70,
        days_ago=ROTATION_MIN_HOLD_DAYS + 5, pnl_pct=1.0,
    )
    pf.open_positions = [same_sector]

    candidate = pf._select_rotation_candidate(INCOMING_SIGNAL)

    assert candidate is None
