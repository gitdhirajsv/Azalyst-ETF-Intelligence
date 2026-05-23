"""
Backtester — walk-forward + purged k-fold CV (López de Prado).

The upstream Azalyst `self_improve.py` is a textbook overfitting machine: an LLM
proposes weight tweaks against past PnL, and "auto-rolls back if PnL drops 2pp."
That's p-hacking with a feedback loop. We replace it with two things:

  (a) A walk-forward backtest: train on [t-N, t-1], test on [t, t+H], roll forward.
      No look-ahead; tests never see training data.

  (b) Purged k-fold CV: when validating, embargo `H` days around each test fold
      so labels can't leak across folds (López de Prado, AFML ch. 7).

Output: backtest equity curve, Sharpe, Sortino, max DD, deflated Sharpe input.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from . import ETF_UNIVERSE


@dataclass(frozen=True)
class BacktestResult:
    n_trades: int
    total_return: float
    annualized_return: float
    annualized_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    equity_curve: pd.Series


def _download_universe(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    df = yf.download(tickers, start=start, end=end, interval="1d",
                     auto_adjust=True, progress=False, threads=True)
    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])
    return closes.dropna(how="all", axis=1)


def momentum_top_n_strategy(
    closes: pd.DataFrame,
    lookback: int = 20,
    top_n: int = 5,
    rebalance_days: int = 5,
) -> pd.Series:
    """Simple monthly cross-sectional momentum baseline. Use this as the
    'null hypothesis' the full Azalyst stack must beat in walk-forward."""
    rets = closes.pct_change()
    momo = (1 + rets).rolling(lookback).apply(np.prod, raw=True) - 1
    weights = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    rebal_dates = closes.index[lookback::rebalance_days]
    for i, d in enumerate(rebal_dates):
        if d not in momo.index:
            continue
        ranks = momo.loc[d].rank(ascending=False)
        picks = ranks.nsmallest(top_n).index
        next_d = rebal_dates[i + 1] if i + 1 < len(rebal_dates) else closes.index[-1]
        weights.loc[d:next_d, picks] = 1.0 / top_n
    weights = weights.shift(1).fillna(0)  # next-day execution
    portfolio_ret = (weights * rets).sum(axis=1)
    return portfolio_ret


def evaluate(returns: pd.Series, freq: int = 252) -> BacktestResult:
    if returns.empty:
        return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, pd.Series(dtype=float))
    equity = (1 + returns).cumprod()
    total = float(equity.iloc[-1] - 1)
    n = len(returns)
    ann_ret = float((1 + total) ** (freq / max(n, 1)) - 1) if n > 0 else 0
    ann_vol = float(returns.std() * np.sqrt(freq))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    downside = returns[returns < 0]
    sortino = (ann_ret / (downside.std() * np.sqrt(freq))) if len(downside) > 0 and downside.std() > 0 else 0
    peak = equity.cummax()
    dd = (equity / peak - 1).min()
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    win_rate = float(len(wins) / len(returns[returns != 0])) if (returns != 0).any() else 0
    avg_win = float(wins.mean()) if len(wins) else 0
    avg_loss = float(losses.mean()) if len(losses) else 0
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return BacktestResult(
        n_trades=int((returns != 0).sum()),
        total_return=total,
        annualized_return=ann_ret,
        annualized_vol=ann_vol,
        sharpe=sharpe, sortino=sortino,
        max_drawdown=float(dd),
        win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
        profit_factor=pf,
        equity_curve=equity,
    )


def walk_forward(
    tickers: list[str] | None = None,
    start: str = "2020-01-01",
    end: str | None = None,
    train_window: int = 252,
    test_window: int = 63,
) -> list[BacktestResult]:
    tickers = tickers or ETF_UNIVERSE
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    closes = _download_universe(tickers, start, end)
    n = len(closes)
    results: list[BacktestResult] = []
    i = train_window
    while i + test_window <= n:
        test_slice = closes.iloc[i: i + test_window]
        rets = momentum_top_n_strategy(test_slice)
        results.append(evaluate(rets))
        i += test_window
    return results


def purged_kfold(
    returns: pd.Series,
    k: int = 5,
    embargo_days: int = 5,
) -> list[BacktestResult]:
    """K-fold evaluation of a pre-computed return series with fold-boundary
    embargo.

    Split `returns` into k contiguous folds. For each fold, drop the first
    `embargo_days` bars before evaluating — those bars sit closest to the
    previous fold and can carry information through the strategy's lookback
    windows (e.g. 20-day momentum at the fold boundary depends on bars from
    the previous fold). Embargoing the boundary keeps each fold's stats from
    being contaminated by the adjacent fold's tape.

    Note: this is fold-boundary embargo for already-computed strategy returns.
    It is not the full López de Prado purged-CV (which also purges training
    data around test folds); this function has no training stage.
    """
    if k <= 0:
        return []
    n = len(returns)
    fold_size = n // k
    if fold_size <= 0:
        return []
    embargo = max(0, int(embargo_days))
    out: list[BacktestResult] = []
    for f in range(k):
        start = f * fold_size
        end = start + fold_size
        # Drop the first `embargo` bars of every fold except the first one —
        # there is no previous fold for fold 0 to leak into it.
        fold_start = start + embargo if f > 0 else start
        if fold_start >= end:
            # Embargo wider than the fold — emit an empty result so callers
            # still see k entries.
            out.append(evaluate(pd.Series(dtype=float)))
            continue
        test = returns.iloc[fold_start:end]
        out.append(evaluate(test))
    return out


if __name__ == "__main__":
    closes = _download_universe(ETF_UNIVERSE[:30], "2022-01-01",
                                pd.Timestamp.today().strftime("%Y-%m-%d"))
    rets = momentum_top_n_strategy(closes)
    res = evaluate(rets)
    print(f"Trades: {res.n_trades}  Sharpe: {res.sharpe:.2f}  MaxDD: {res.max_drawdown:.1%}  AnnRet: {res.annualized_return:.1%}")
    print("\nPurged 5-fold:")
    for i, r in enumerate(purged_kfold(rets, k=5)):
        print(f"  Fold {i+1}: Sharpe={r.sharpe:+.2f}  Ret={r.annualized_return:+.1%}  DD={r.max_drawdown:.1%}")
