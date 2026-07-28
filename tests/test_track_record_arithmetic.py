"""ETF-04 regression: the published track record must not silently exclude
real realized P&L, silently launder a corrupted deposit figure, or hide
prior reset eras.

Forensic audit (2026-07-28) found:
  1. Partial profit-taking (Step-ROI) exits were entirely invisible to
     win/loss/expectancy stats -- only the running scalar
     partial_realised_pnl_total reflected them.
  2. calc_metrics silently substituted a recomputed `deposited` figure
     whenever it looked "too low" vs current holdings, with no trace in
     the output -- laundering a potential data bug into a plausible number.
  3. The public dashboard only ever showed the CURRENT era's stats; two
     earlier, worse-performing books existed and were archived without
     being surfaced anywhere on the live dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path

import generate_dashboard as gd


# ── (1) partial profit-taking events folded into track_record stats ────────

def test_partial_profit_events_count_as_winning_trades():
    portfolio = {
        "closed_trades": [
            {"ticker": "XLE", "realised_pnl": -100.0, "realised_pnl_pct": -2.0},
        ],
        "partial_realised_pnl_total": 500.0,
        "partial_realised_pnl_events": [
            {
                "ticker": "GLD", "etf_name": "SPDR Gold", "realised_pnl": 500.0,
                "realised_pnl_pct": 8.0, "roi_step": 1, "days_held": 12,
            },
        ],
    }
    track = gd.build_track(portfolio)

    assert track["total_trades"] == 2, "the partial exit must count as a trade"
    assert track["winners"] == 1
    assert track["losers"] == 1
    assert track["win_rate"] == 50.0, (
        "excluding the partial win understated win rate as 0% instead of 50%"
    )
    assert track["legacy_partial_pnl_not_itemized"] == 0.0, (
        "the itemized event fully accounts for partial_realised_pnl_total here"
    )


def test_legacy_partial_pnl_disclosed_when_no_itemized_events_exist():
    """Simulates the real live-book state: an aggregate scalar with no
    itemized events (money realized before this field existed)."""
    portfolio = {
        "closed_trades": [],
        "partial_realised_pnl_total": 15016.61,
        "partial_realised_pnl_events": [],
    }
    track = gd.build_track(portfolio)

    assert track["total_trades"] == 0
    assert track["legacy_partial_pnl_not_itemized"] == 15016.61, (
        "pre-existing aggregate partial P&L must be disclosed, not silently dropped"
    )


def test_build_track_with_no_partials_matches_prior_behaviour():
    portfolio = {
        "closed_trades": [
            {"ticker": "XLV", "realised_pnl": 50.0, "realised_pnl_pct": 1.5},
            {"ticker": "QQQ", "realised_pnl": -30.0, "realised_pnl_pct": -1.0},
        ],
    }
    track = gd.build_track(portfolio)
    assert track["total_trades"] == 2
    assert track["winners"] == 1
    assert track["losers"] == 1


# ── (2) deposited-figure anomaly is disclosed, not silently substituted ────

def test_deposited_is_published_as_is_with_anomaly_flag_when_suspect():
    # deposited (10) is far below expected_deposited (total - unrealised -
    # realised = 100 - 0 - 0 = 100) -- the old code silently replaced 10
    # with 100. It must now be published unmodified, with the flag set.
    portfolio = {
        "open_positions": [{"invested_inr": 50.0, "current_price": 1.0, "units": 100.0}],
        "open_hedge_positions": [],
        "cash_inr": 50.0,
        "monthly_reserve_inr": 0.0,
        "total_deposited": 10.0,
        "closed_trades": [],
        "partial_realised_pnl_total": 0.0,
        "portfolio_peak": 0.0,
        "max_drawdown_pct": 0.0,
    }
    metrics = gd.calc_metrics(portfolio, usd_inr_rate=1.0)

    assert metrics["total_deposited"] == 10.0, (
        "the on-file deposited value must be published unmodified, not "
        "silently replaced by a recomputed figure"
    )
    assert metrics["deposited_anomaly"] is True


def test_deposited_anomaly_false_for_a_consistent_book():
    portfolio = {
        "open_positions": [{"invested_inr": 100.0, "current_price": 1.0, "units": 100.0}],
        "open_hedge_positions": [],
        "cash_inr": 0.0,
        "monthly_reserve_inr": 0.0,
        "total_deposited": 100.0,
        "closed_trades": [],
        "partial_realised_pnl_total": 0.0,
        "portfolio_peak": 0.0,
        "max_drawdown_pct": 0.0,
    }
    metrics = gd.calc_metrics(portfolio, usd_inr_rate=1.0)
    assert metrics["deposited_anomaly"] is False
    assert metrics["total_deposited"] == 100.0


# ── (3) all-eras summary sums archived books + current ─────────────────────

def _write_era(archive_dir: Path, name: str, *, deposited, value, realised, trades, winners, losers):
    era_dir = archive_dir / name
    era_dir.mkdir(parents=True)
    status = {
        "total_deposited": deposited,
        "portfolio_value": value,
        "realised_pnl": realised,
        "change": "+0.00%",
        "track_record": {
            "total_trades": trades, "winners": winners, "losers": losers,
            "win_rate": safe_div(winners, trades), "profit_factor": 0,
        },
    }
    with open(era_dir / "status.json", "w", encoding="utf-8") as fh:
        json.dump(status, fh)


def safe_div(a, b):
    return round(a / b * 100, 1) if b else 0.0


def test_all_eras_summary_combines_archives_with_current(tmp_path, monkeypatch):
    monkeypatch.setattr(gd, "ROOT", tmp_path)
    archive_dir = tmp_path / "archive"
    _write_era(archive_dir, "v1_paper_track_record_2026-05-08",
               deposited=10043.4, value=10035.64, realised=5.68, trades=0, winners=0, losers=0)
    _write_era(archive_dir, "v2_paper_track_record_2026-06-25",
               deposited=10158.88, value=10050.65, realised=-93.17, trades=12, winners=1, losers=11)

    current_metrics = {"total_deposited": 19753.49, "portfolio_value": 19865.65,
                        "realised_pnl": -3.81, "change": "+0.57%"}
    current_track = {"total_trades": 19, "winners": 5, "losers": 14, "win_rate": 26.3, "profit_factor": 0.48}

    summary = gd.build_all_eras_summary(current_metrics, current_track)

    assert summary["era_count"] == 3
    assert summary["reset_count"] == 2
    assert summary["combined_total_trades"] == 0 + 12 + 19
    assert summary["combined_win_rate"] == round((0 + 1 + 5) / 31 * 100, 1)
    assert summary["combined_realised_pnl"] == round(5.68 + (-93.17) + (-3.81), 2)
    era_names = [e["era"] for e in summary["eras"]]
    assert era_names == [
        "v1_paper_track_record_2026-05-08",
        "v2_paper_track_record_2026-06-25",
        "current",
    ]


def test_all_eras_summary_with_no_archive_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(gd, "ROOT", tmp_path)  # no "archive" subdir created
    current_metrics = {"total_deposited": 100.0, "portfolio_value": 105.0, "realised_pnl": 0.0, "change": "+5.00%"}
    current_track = {"total_trades": 1, "winners": 1, "losers": 0, "win_rate": 100.0, "profit_factor": 99.0}

    summary = gd.build_all_eras_summary(current_metrics, current_track)

    assert summary["era_count"] == 1
    assert summary["reset_count"] == 0
    assert summary["eras"][0]["era"] == "current"
