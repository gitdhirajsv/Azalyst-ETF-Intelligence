"""
Layer 7 — Correlation Cluster Dedup.

Stops SOXX + SMH + SOXL from being three independent positions.
Hierarchical clustering on 60-day return correlation, distance = sqrt(2*(1-rho)).

Use:
    clusters = build_clusters(universe)
    keep_one_per_cluster(signals, clusters)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from . import ETF_UNIVERSE


@dataclass(frozen=True)
class Cluster:
    cluster_id: int
    members: list[str]


def _correlation_matrix(tickers: list[str], lookback_days: int = 60) -> pd.DataFrame:
    px = yf.download(tickers, period=f"{lookback_days + 10}d", interval="1d",
                     auto_adjust=True, progress=False, threads=True)
    closes = px["Close"] if "Close" in px.columns.get_level_values(0) else px
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])
    rets = closes.pct_change().dropna(how="all").tail(lookback_days)
    rets = rets.dropna(axis=1, thresh=int(0.8 * lookback_days))
    return rets.corr().fillna(0)


def build_clusters(
    tickers: list[str] | None = None,
    n_clusters: int | None = None,
    distance_threshold: float = 0.5,
) -> list[Cluster]:
    tickers = tickers or ETF_UNIVERSE
    # scipy.linkage requires >=2 observations. With 0 or 1 candidates each
    # ticker is its own trivial cluster (no dedup needed anyway).
    if len(tickers) <= 1:
        return [Cluster(cluster_id=i, members=[t]) for i, t in enumerate(tickers)]
    corr = _correlation_matrix(tickers)
    if corr.empty or len(corr.columns) <= 1:
        return [Cluster(cluster_id=i, members=[t]) for i, t in enumerate(tickers)]
    dist = np.sqrt(np.clip(2 * (1 - corr.values), 0, None))
    np.fill_diagonal(dist, 0)
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method="average")
    if n_clusters is not None:
        labels = fcluster(Z, t=n_clusters, criterion="maxclust")
    else:
        labels = fcluster(Z, t=distance_threshold, criterion="distance")
    out: dict[int, list[str]] = {}
    for tk, lbl in zip(corr.columns, labels):
        out.setdefault(int(lbl), []).append(tk)
    return [Cluster(cluster_id=cid, members=members) for cid, members in sorted(out.items())]


def keep_one_per_cluster(
    candidates: list[tuple[str, float]],
    clusters: list[Cluster],
) -> list[tuple[str, float]]:
    """candidates = [(ticker, score), ...] sorted desc by score; we keep the
    highest-scoring ticker per cluster."""
    ticker_to_cluster = {tk: c.cluster_id for c in clusters for tk in c.members}
    seen: set[int] = set()
    out: list[tuple[str, float]] = []
    for tk, score in sorted(candidates, key=lambda x: -x[1]):
        cid = ticker_to_cluster.get(tk, -1)
        if cid in seen and cid != -1:
            continue
        seen.add(cid)
        out.append((tk, score))
    return out


if __name__ == "__main__":
    clusters = build_clusters()
    for c in clusters:
        if len(c.members) > 1:
            print(f"Cluster {c.cluster_id}: {c.members}")
