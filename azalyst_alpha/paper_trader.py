"""
Paper trader — realistic frictions.

Slippage model: half-spread + market impact (square-root rule).
    fill_px = mid * (1 + sign * spread/2 + sign * impact_coef * sqrt(notional / ADV))

Persistence: SQLite at data/paper_trader.db with positions, trades, equity.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

import yfinance as yf


DB_PATH = Path("data/paper_trader.db")
SPREAD_BPS = 5
IMPACT_COEF = 0.10  # bp per sqrt(participation%)
INITIAL_BOOK = 100_000.0


@dataclass
class Trade:
    trade_date: str
    ticker: str
    action: str        # "BUY" / "SELL" / "COVER" / "SHORT"
    shares: int
    fill_price: float
    notional: float
    reason: str


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT, ticker TEXT, action TEXT, shares INTEGER,
            fill_price REAL, notional REAL, reason TEXT
        );
        CREATE TABLE IF NOT EXISTS positions (
            ticker TEXT PRIMARY KEY, shares INTEGER, avg_entry REAL,
            entry_date TEXT, peak_price REAL, atr_at_entry REAL
        );
        CREATE TABLE IF NOT EXISTS equity (
            equity_date TEXT PRIMARY KEY, value REAL
        );
        CREATE TABLE IF NOT EXISTS state (
            k TEXT PRIMARY KEY, v TEXT
        );
    """)
    return c


def _avg_volume(ticker: str) -> float:
    try:
        h = yf.Ticker(ticker).history(period="30d")
        return float(h["Volume"].mean())
    except Exception:
        return 1e6


def _slippage_fill(ticker: str, mid: float, shares: int) -> float:
    sign = 1 if shares > 0 else -1
    half_spread = mid * SPREAD_BPS / 1e4
    adv = _avg_volume(ticker)
    participation = abs(shares) / max(adv, 1)
    impact = mid * IMPACT_COEF * (participation ** 0.5) / 1e4
    return mid + sign * (half_spread + impact)


def _last_mid(ticker: str) -> float | None:
    try:
        h = yf.Ticker(ticker).history(period="2d")
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except Exception:
        return None


def book_value() -> float:
    c = _conn()
    cur = c.execute("SELECT v FROM state WHERE k = 'book_value'")
    row = cur.fetchone()
    if row is None:
        c.execute("INSERT INTO state(k, v) VALUES (?, ?)", ("book_value", str(INITIAL_BOOK)))
        c.commit()
        return INITIAL_BOOK
    return float(row[0])


def set_book_value(v: float) -> None:
    c = _conn()
    c.execute("INSERT OR REPLACE INTO state(k, v) VALUES (?, ?)", ("book_value", str(v)))
    c.commit()


def open_position(ticker: str, shares: int, reason: str = "") -> Trade | None:
    mid = _last_mid(ticker)
    if mid is None:
        return None
    fill = _slippage_fill(ticker, mid, shares)
    notional = fill * shares
    today = str(date.today())
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO positions(ticker, shares, avg_entry, entry_date, peak_price, atr_at_entry)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (ticker, shares, fill, today, fill, 0.0))
    action = "BUY" if shares > 0 else "SHORT"
    c.execute("""INSERT INTO trades(trade_date, ticker, action, shares, fill_price, notional, reason)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (today, ticker, action, shares, fill, notional, reason))
    c.commit()
    return Trade(today, ticker, action, shares, fill, notional, reason)


def close_position(ticker: str, reason: str = "EXIT") -> Trade | None:
    c = _conn()
    cur = c.execute("SELECT shares, avg_entry FROM positions WHERE ticker = ?", (ticker,))
    row = cur.fetchone()
    if row is None:
        return None
    shares, _ = row
    mid = _last_mid(ticker)
    if mid is None:
        return None
    fill = _slippage_fill(ticker, mid, -shares)
    notional = fill * -shares
    today = str(date.today())
    action = "SELL" if shares > 0 else "COVER"
    c.execute("""INSERT INTO trades(trade_date, ticker, action, shares, fill_price, notional, reason)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (today, ticker, action, -shares, fill, notional, reason))
    c.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
    c.commit()
    return Trade(today, ticker, action, -shares, fill, notional, reason)


def mark_to_market() -> float:
    c = _conn()
    cash = book_value()
    cur = c.execute("SELECT ticker, shares, avg_entry FROM positions")
    pnl_unreal = 0.0
    for ticker, shares, avg_entry in cur.fetchall():
        mid = _last_mid(ticker)
        if mid is None:
            continue
        pnl_unreal += (mid - avg_entry) * shares
    today = str(date.today())
    equity = cash + pnl_unreal
    c.execute("INSERT OR REPLACE INTO equity(equity_date, value) VALUES (?, ?)", (today, equity))
    c.commit()
    return equity


def positions() -> list[dict]:
    c = _conn()
    cur = c.execute("SELECT ticker, shares, avg_entry, entry_date FROM positions")
    return [{"ticker": t, "shares": s, "avg_entry": p, "entry_date": d}
            for t, s, p, d in cur.fetchall()]


def equity_curve() -> list[tuple[str, float]]:
    c = _conn()
    cur = c.execute("SELECT equity_date, value FROM equity ORDER BY equity_date")
    return cur.fetchall()
