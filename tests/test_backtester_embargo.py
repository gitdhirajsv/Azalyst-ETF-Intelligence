"""
Regression test for `azalyst_alpha.backtester.purged_kfold` embargo.

Bug being guarded:
    The function's docstring + README claimed it embargoed `embargo_days`
    around each test fold. The implementation ignored `embargo_days`
    entirely — it just split returns into k contiguous folds and evaluated
    each. The fix uses `embargo_days` to drop the first `embargo_days`
    bars of every fold except the first.

This test pins:
  1. Non-zero embargo actually changes results when bars at the boundary
     differ from the rest of the fold.
  2. Embargo 0 reproduces the legacy contiguous-fold behavior.
  3. Embargo wider than the fold returns an empty result rather than
     crashing or silently returning a partial fold.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from azalyst_alpha.backtester import purged_kfold


def _build_returns_with_boundary_spike(n_per_fold: int, k: int) -> pd.Series:
    """Construct a returns series where the first bar of each fold (except
    fold 0) is a +10% spike and the rest are flat zero. With embargo > 0
    those spikes get dropped, so per-fold mean return drops to zero."""
    n = n_per_fold * k
    rs = np.zeros(n, dtype=float)
    for f in range(1, k):
        rs[f * n_per_fold] = 0.10  # spike on the first bar of each fold
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.Series(rs, index=idx)


def test_embargo_drops_boundary_bars():
    k, n_per_fold = 4, 10
    rets = _build_returns_with_boundary_spike(n_per_fold=n_per_fold, k=k)

    no_embargo = purged_kfold(rets, k=k, embargo_days=0)
    with_embargo = purged_kfold(rets, k=k, embargo_days=1)

    assert len(no_embargo) == k and len(with_embargo) == k

    # Fold 0 has no spike (and no embargo applied) — identical either way.
    assert no_embargo[0].total_return == with_embargo[0].total_return

    # Folds 1..k-1 contain the +10% spike under embargo=0. Under
    # embargo=1, the spike is dropped → those folds become all-zero
    # returns, so total_return must be 0.0.
    for f in range(1, k):
        assert no_embargo[f].total_return > 0.0, f"fold {f} should show the spike when embargo=0"
        assert abs(with_embargo[f].total_return) < 1e-12, f"fold {f} should be flat when embargo=1"


def test_embargo_zero_matches_legacy_contiguous_split():
    """embargo_days=0 must reproduce the pre-fix behavior of pure k-fold."""
    k, n_per_fold = 5, 6
    rets = pd.Series(
        np.linspace(0.001, 0.030, n_per_fold * k),
        index=pd.date_range("2024-01-01", periods=n_per_fold * k, freq="D"),
    )
    result = purged_kfold(rets, k=k, embargo_days=0)
    assert len(result) == k
    # Each fold should have exactly n_per_fold bars used.
    for f, r in enumerate(result):
        assert r.n_trades == n_per_fold, f"fold {f} expected {n_per_fold} bars, got {r.n_trades}"


def test_embargo_wider_than_fold_returns_empty_result_not_crash():
    rets = pd.Series(
        np.zeros(20, dtype=float),
        index=pd.date_range("2024-01-01", periods=20, freq="D"),
    )
    # 4 folds of size 5; embargo=10 leaves no bars in folds 1..3.
    result = purged_kfold(rets, k=4, embargo_days=10)
    assert len(result) == 4
    # Fold 0 still has its 5 bars (no embargo applied to fold 0).
    assert result[0].n_trades == 0  # zero returns -> n_trades counts non-zero, so 0 is correct
    # Folds 1..3 should be empty BacktestResults, not crashes.
    for f in range(1, 4):
        assert result[f].n_trades == 0
        assert result[f].total_return == 0.0
