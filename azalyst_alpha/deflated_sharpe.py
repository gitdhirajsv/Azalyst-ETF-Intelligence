"""
Deflated Sharpe Ratio (López de Prado, 2014).

Why we need this gate: with N parametrizations of a strategy backtested
against history, the *expected* maximum Sharpe under the null hypothesis
(no real edge) grows as ~sqrt(2 ln N). The DSR adjusts the realized Sharpe
for (a) trial inflation, (b) skew, (c) kurtosis of returns.

If DSR < 0.5 (i.e. <70% probability the edge is real): do not deploy.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm


def deflated_sharpe(
    realized_sharpe: float,
    n_observations: int,
    n_trials: int = 1,
    skew: float = 0.0,
    excess_kurtosis: float = 0.0,
    benchmark_sharpe: float | None = None,
) -> dict[str, float]:
    """
    Returns a dict with:
      - sr0: expected max Sharpe under null with n_trials backtests (Bailey & Lopez de Prado)
      - dsr: probabilistic Sharpe ratio after deflation
      - p_real: probability the strategy has true Sharpe > 0
    """
    if benchmark_sharpe is None:
        # Expected max Sharpe under the null with n_trials independent backtests
        gamma = 0.5772156649  # Euler-Mascheroni
        if n_trials > 1:
            sr0 = (1 - gamma) * norm.ppf(1 - 1.0 / n_trials) + gamma * norm.ppf(1 - 1.0 / (n_trials * math.e))
            sr0 = sr0 / math.sqrt(252)  # annualize-> per-period
        else:
            sr0 = 0.0
    else:
        sr0 = benchmark_sharpe

    sr = realized_sharpe / math.sqrt(252)  # convert to per-period
    if n_observations <= 1:
        return {"sr0": sr0, "dsr": 0.0, "p_real": 0.0}

    sigma_sr = math.sqrt(
        (1 - skew * sr + ((excess_kurtosis - 1) / 4) * sr ** 2) / (n_observations - 1)
    )
    if sigma_sr <= 0:
        return {"sr0": sr0, "dsr": 0.0, "p_real": 0.0}

    dsr = norm.cdf((sr - sr0) / sigma_sr)
    p_real = norm.cdf(sr / (math.sqrt((1 + 0.5 * sr ** 2) / (n_observations - 1)) or 1))
    return {"sr0": sr0 * math.sqrt(252), "dsr": float(dsr), "p_real": float(p_real)}


def gate(
    realized_sharpe: float,
    returns: pd.Series,
    n_trials: int = 1,
    min_dsr: float = 0.5,
) -> tuple[bool, dict[str, float]]:
    skew = float(returns.skew()) if len(returns) > 2 else 0.0
    kurt = float(returns.kurt()) if len(returns) > 2 else 0.0
    metrics = deflated_sharpe(
        realized_sharpe=realized_sharpe,
        n_observations=len(returns),
        n_trials=n_trials,
        skew=skew,
        excess_kurtosis=kurt,
    )
    return metrics["dsr"] >= min_dsr, metrics


if __name__ == "__main__":
    np.random.seed(42)
    rets = pd.Series(np.random.normal(0.0008, 0.012, 500))
    sharpe = rets.mean() / rets.std() * np.sqrt(252)
    passed, m = gate(sharpe, rets, n_trials=50)
    print(f"Realized Sharpe: {sharpe:.2f}")
    print(f"Expected null max Sharpe (50 trials): {m['sr0']:.2f}")
    print(f"DSR: {m['dsr']:.2%}  P(real edge): {m['p_real']:.2%}  -> {'DEPLOY' if passed else 'REJECT'}")
