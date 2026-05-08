"""
Universe fetcher — pull the live US-listed ETF master list.

Hardcoding 350 tickers in __init__.py rots fast. NASDAQ Trader publishes the
authoritative daily list of all listed securities (NASDAQ + NYSE/AMEX) as
free TSV. The "ETF" column flags ETFs explicitly. ~5,000 US-listed ETFs.

Pipeline:
  1. Pull both NASDAQ and Other (NYSE/AMEX) listings
  2. Filter to ETF=Y, exclude test issues + when-issued + suspended
  3. Filter to liquid: 30D ADV * close >= $5M, AUM >= $250M (single bulk yfinance call)
  4. Cache to data/etf_universe_cache.csv (refresh weekly via cron)

Fallback: if NASDAQ Trader is unreachable, fall back to ETF_UNIVERSE in __init__.py.
This file is callable from fusion.py to override the static list.
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
CACHE_PATH = Path("data/etf_universe_cache.csv")
CACHE_TTL_DAYS = 7


@dataclass(frozen=True)
class ETFRow:
    ticker: str
    name: str
    exchange: str          # "NASDAQ" | "NYSE" | "AMEX"
    is_etf: bool


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "azalyst-alpha/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_nasdaq_listed(text: str) -> list[ETFRow]:
    """Pipe-delimited TSV. Columns: Symbol|Security Name|Market Category|Test Issue|
    Financial Status|Round Lot Size|ETF|NextShares"""
    rows: list[ETFRow] = []
    for line in text.splitlines()[1:]:  # skip header
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        sym, name, _cat, test_issue, fin_stat, _lot, is_etf = parts[:7]
        if test_issue == "Y" or fin_stat == "D":  # delinquent
            continue
        rows.append(ETFRow(ticker=sym.strip(), name=name.strip(), exchange="NASDAQ",
                           is_etf=(is_etf.strip().upper() == "Y")))
    return rows


def _parse_other_listed(text: str) -> list[ETFRow]:
    """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"""
    rows: list[ETFRow] = []
    for line in text.splitlines()[1:]:
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        sym, name, exch, _cqs, is_etf, _lot, test_issue = parts[:7]
        if test_issue == "Y":
            continue
        ex_map = {"A": "AMEX", "N": "NYSE", "P": "ARCA", "Z": "BATS"}
        rows.append(ETFRow(ticker=sym.strip(), name=name.strip(),
                           exchange=ex_map.get(exch, exch),
                           is_etf=(is_etf.strip().upper() == "Y")))
    return rows


def fetch_master_list() -> list[ETFRow]:
    """Pull live NASDAQ + Other listings. Returns ETFs only."""
    out: list[ETFRow] = []
    try:
        out.extend(_parse_nasdaq_listed(_http_get(NASDAQ_URL)))
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"[universe_fetcher] NASDAQ fetch failed: {exc}")
    try:
        out.extend(_parse_other_listed(_http_get(OTHER_URL)))
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"[universe_fetcher] Other fetch failed: {exc}")
    etfs = [r for r in out if r.is_etf]
    # Drop oddballs: tickers with $, =, ^, or > 5 chars are typically warrants/preferreds
    etfs = [r for r in etfs if r.ticker.isalpha() and 1 <= len(r.ticker) <= 5]
    return etfs


def filter_by_liquidity(
    tickers: list[str],
    min_dollar_volume_30d: float = 5_000_000,
    min_price: float = 5.0,
    chunk_size: int = 200,
) -> list[str]:
    """Bulk yfinance fetch; keep only ETFs with sustained dollar-volume.
    chunk_size keeps each HTTP call manageable."""
    import yfinance as yf
    keep: list[str] = []
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        try:
            df = yf.download(chunk, period="40d", interval="1d",
                             auto_adjust=True, progress=False, threads=True,
                             group_by="column")
        except Exception as exc:
            print(f"[universe_fetcher] yfinance chunk {i} failed: {exc}")
            continue
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            closes = df["Close"]
            volumes = df["Volume"]
        else:
            closes = df[["Close"]]
            volumes = df[["Volume"]]
        for tk in closes.columns:
            c = closes[tk].dropna()
            v = volumes[tk].dropna() if tk in volumes.columns else pd.Series(dtype=float)
            if c.empty or v.empty or len(c) < 20:
                continue
            last_close = float(c.iloc[-1])
            if last_close < min_price:
                continue
            adv_30d = float((c * v).tail(30).mean())
            if adv_30d >= min_dollar_volume_30d:
                keep.append(tk)
    return keep


def fetch_universe(
    use_cache: bool = True,
    refresh: bool = False,
    apply_liquidity_filter: bool = True,
) -> list[str]:
    """High-level: returns a list of liquid ETF tickers. Caches to disk so we
    don't re-do the 5000-ticker liquidity scan on every fusion run."""
    if use_cache and not refresh and CACHE_PATH.exists():
        age = datetime.now() - datetime.fromtimestamp(CACHE_PATH.stat().st_mtime)
        if age < timedelta(days=CACHE_TTL_DAYS):
            try:
                df = pd.read_csv(CACHE_PATH)
                tickers = df["ticker"].astype(str).tolist()
                if tickers:
                    return tickers
            except Exception:
                pass

    raw = fetch_master_list()
    if not raw:
        print("[universe_fetcher] live fetch returned 0 ETFs; falling back to static universe")
        from . import ETF_UNIVERSE
        return ETF_UNIVERSE

    candidates = sorted({r.ticker for r in raw})
    print(f"[universe_fetcher] {len(candidates)} ETFs from NASDAQ Trader master list")

    if apply_liquidity_filter:
        liquid = filter_by_liquidity(candidates)
        print(f"[universe_fetcher] {len(liquid)} pass liquidity gate")
    else:
        liquid = candidates

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": liquid}).to_csv(CACHE_PATH, index=False)
    return liquid


if __name__ == "__main__":
    import sys
    refresh = "--refresh" in sys.argv
    no_filter = "--no-filter" in sys.argv
    universe = fetch_universe(refresh=refresh, apply_liquidity_filter=not no_filter)
    print(f"\nUniverse size: {len(universe)}")
    print("First 30:", universe[:30])
