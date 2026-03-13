"""
paper_trader.py — AZALYST Paper Trading Engine

Simulates a real fund manager making allocation decisions based on signals.

Rules:
  - 10,000 INR added to cash at the start of each calendar month
  - Cash never expires — undeployed cash carries forward
  - Position sizing based on confidence score and severity
  - Maximum single position: 40% of available cash
  - Maximum concurrent open positions: 6
  - Positions are closed when a defined exit condition is met:
      * Target hit (+15% for HIGH/CRITICAL, +10% for MEDIUM)
      * Stop-loss hit (-8% for all positions)
      * Max hold period reached (60 days)
  - All prices fetched via Yahoo Finance (yfinance) for US ETFs
    and NSE data for Indian ETFs
  - Full trade log persisted to JSON

Position sizing model:
  Confidence 90-100  →  35% of available cash
  Confidence 80-89   →  28% of available cash
  Confidence 70-79   →  22% of available cash
  Confidence 62-69   →  15% of available cash
"""

import json
import logging
import os
from datetime import datetime, timezone, date, timedelta
from typing import Dict, List, Optional, Tuple
import urllib.request
import urllib.error

log = logging.getLogger("azalyst.trader")

# ── Constants ─────────────────────────────────────────────────────────────────
MONTHLY_BUDGET_INR  = 10_000
MAX_POSITIONS       = 6
STOP_LOSS_PCT       = 0.10     # -10% hard exit
MAX_HOLD_DAYS       = 180      # 6 months safety net — no profit target, let winners run

# Position size as fraction of available cash
SIZING = {
    (90, 100): 0.35,
    (80,  89): 0.28,
    (70,  79): 0.22,
    (62,  69): 0.15,
}

USD_TO_INR = 83.5   # Fallback rate if live fetch fails


# ── Price Fetching ────────────────────────────────────────────────────────────

def fetch_usd_to_inr() -> float:
    """Fetch live USD/INR rate from Yahoo Finance."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return float(price)
    except Exception:
        return USD_TO_INR


def fetch_price_usd(ticker: str) -> Optional[float]:
    """
    Fetch current price for a US-listed ETF from Yahoo Finance.
    Returns price in USD, or None if unavailable.
    """
    try:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?interval=1d&range=1d"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return float(price)
    except Exception as e:
        log.warning(f"Price fetch failed for {ticker}: {e}")
        return None


def fetch_price_inr(ticker: str) -> Optional[float]:
    """
    Fetch current price for an NSE-listed ETF.
    Yahoo Finance uses .NS suffix for NSE instruments.
    Returns price in INR, or None if unavailable.
    """
    try:
        yf_ticker = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_ticker}"
            f"?interval=1d&range=1d"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return float(price)
    except Exception as e:
        log.warning(f"NSE price fetch failed for {ticker}: {e}")
        return None


def get_current_price_inr(ticker: str, exchange: str) -> Optional[float]:
    """
    Unified price fetch. Returns price in INR regardless of exchange.
    """
    exchange_upper = exchange.upper()

    if "NSE" in exchange_upper or "BSE" in exchange_upper:
        return fetch_price_inr(ticker)
    else:
        # US ETF — fetch in USD, convert to INR
        usd_price = fetch_price_usd(ticker)
        if usd_price is None:
            return None
        fx = fetch_usd_to_inr()
        return round(usd_price * fx, 4)


# ── Portfolio State ───────────────────────────────────────────────────────────

class Position:
    """Represents a single open paper trade position."""

    def __init__(
        self,
        trade_id:       str,
        ticker:         str,
        etf_name:       str,
        exchange:       str,
        platform:       str,
        sector:         str,
        entry_price:    float,       # INR
        units:          float,
        invested_inr:   float,
        entry_date:     str,
        confidence:     int,
        severity:       str,
        signal_headline: str,
    ):
        self.trade_id        = trade_id
        self.ticker          = ticker
        self.etf_name        = etf_name
        self.exchange        = exchange
        self.platform        = platform
        self.sector          = sector
        self.entry_price     = entry_price
        self.units           = units
        self.invested_inr    = invested_inr
        self.entry_date      = entry_date
        self.confidence      = confidence
        self.severity        = severity
        self.signal_headline = signal_headline
        self.current_price   = entry_price
        self.last_updated    = entry_date

    def current_value(self) -> float:
        return round(self.units * self.current_price, 2)

    def unrealised_pnl(self) -> float:
        return round(self.current_value() - self.invested_inr, 2)

    def unrealised_pnl_pct(self) -> float:
        if self.invested_inr == 0:
            return 0.0
        return round((self.unrealised_pnl() / self.invested_inr) * 100, 2)

    def days_held(self) -> int:
        try:
            entry = datetime.fromisoformat(self.entry_date).date()
            return (date.today() - entry).days
        except Exception:
            return 0

    def to_dict(self) -> Dict:
        return {
            "trade_id":        self.trade_id,
            "ticker":          self.ticker,
            "etf_name":        self.etf_name,
            "exchange":        self.exchange,
            "platform":        self.platform,
            "sector":          self.sector,
            "entry_price":     self.entry_price,
            "units":           self.units,
            "invested_inr":    self.invested_inr,
            "entry_date":      self.entry_date,
            "confidence":      self.confidence,
            "severity":        self.severity,
            "signal_headline": self.signal_headline,
            "current_price":   self.current_price,
            "last_updated":    self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Position":
        p = cls(
            trade_id        = d["trade_id"],
            ticker          = d["ticker"],
            etf_name        = d["etf_name"],
            exchange        = d.get("exchange", "NYSE"),
            platform        = d.get("platform", "INDmoney / Vested"),
            sector          = d["sector"],
            entry_price     = d["entry_price"],
            units           = d["units"],
            invested_inr    = d["invested_inr"],
            entry_date      = d["entry_date"],
            confidence      = d["confidence"],
            severity        = d["severity"],
            signal_headline = d.get("signal_headline", ""),
        )
        p.current_price = d.get("current_price", d["entry_price"])
        p.last_updated  = d.get("last_updated", d["entry_date"])
        return p


class ClosedTrade:
    """Record of a completed trade."""

    def __init__(
        self,
        position:     Position,
        exit_price:   float,
        exit_date:    str,
        exit_reason:  str,
    ):
        self.trade_id       = position.trade_id
        self.ticker         = position.ticker
        self.etf_name       = position.etf_name
        self.platform       = position.platform
        self.sector         = position.sector
        self.entry_price    = position.entry_price
        self.exit_price     = exit_price
        self.units          = position.units
        self.invested_inr   = position.invested_inr
        self.exit_date      = exit_date
        self.exit_reason    = exit_reason
        self.entry_date     = position.entry_date
        self.confidence     = position.confidence
        self.severity       = position.severity

        self.realised_pnl     = round((exit_price - position.entry_price) * position.units, 2)
        self.realised_pnl_pct = round(
            ((exit_price - position.entry_price) / position.entry_price) * 100, 2
        )
        self.days_held = position.days_held()

    def to_dict(self) -> Dict:
        return {
            "trade_id":         self.trade_id,
            "ticker":           self.ticker,
            "etf_name":         self.etf_name,
            "platform":         self.platform,
            "sector":           self.sector,
            "entry_price":      self.entry_price,
            "exit_price":       self.exit_price,
            "units":            self.units,
            "invested_inr":     self.invested_inr,
            "realised_pnl":     self.realised_pnl,
            "realised_pnl_pct": self.realised_pnl_pct,
            "days_held":        self.days_held,
            "entry_date":       self.entry_date,
            "exit_date":        self.exit_date,
            "exit_reason":      self.exit_reason,
            "confidence":       self.confidence,
            "severity":         self.severity,
        }


# ── Portfolio Manager ─────────────────────────────────────────────────────────

class PaperPortfolio:
    """
    Manages the paper trading book.
    Handles cash, position sizing, entry/exit, PnL marking.
    """

    def __init__(self, portfolio_file: str = "azalyst_portfolio.json"):
        self.portfolio_file    = portfolio_file
        self.cash_inr          = 0.0
        self.total_deposited   = 0.0
        self.open_positions:   List[Position]    = []
        self.closed_trades:    List[ClosedTrade] = []
        self.monthly_deposits: Dict[str, float]  = {}
        self.trade_counter     = 0

        self._load()
        self._process_monthly_deposit()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self):
        if not os.path.exists(self.portfolio_file):
            log.info("No portfolio file found — starting fresh book")
            return
        try:
            with open(self.portfolio_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.cash_inr          = data.get("cash_inr", 0.0)
            self.total_deposited   = data.get("total_deposited", 0.0)
            self.monthly_deposits  = data.get("monthly_deposits", {})
            self.trade_counter     = data.get("trade_counter", 0)
            self.open_positions    = [Position.from_dict(p) for p in data.get("open_positions", [])]
            self.closed_trades     = [ClosedTrade.__new__(ClosedTrade) for _ in data.get("closed_trades", [])]
            for ct, raw in zip(self.closed_trades, data.get("closed_trades", [])):
                ct.__dict__.update(raw)

            log.info(
                f"Portfolio loaded — Cash: INR {self.cash_inr:,.0f} | "
                f"Open: {len(self.open_positions)} | Closed: {len(self.closed_trades)}"
            )
        except Exception as e:
            log.error(f"Portfolio load error: {e}")

    def save(self):
        try:
            data = {
                "cash_inr":         self.cash_inr,
                "total_deposited":  self.total_deposited,
                "monthly_deposits": self.monthly_deposits,
                "trade_counter":    self.trade_counter,
                "open_positions":   [p.to_dict() for p in self.open_positions],
                "closed_trades":    [ct.to_dict() for ct in self.closed_trades],
                "last_saved":       datetime.now(timezone.utc).isoformat(),
            }
            with open(self.portfolio_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"Portfolio save error: {e}")

    # ── Monthly Deposit ───────────────────────────────────────────────────

    def _process_monthly_deposit(self):
        """Credit 10,000 INR at the start of each calendar month if not already done."""
        month_key = date.today().strftime("%Y-%m")
        if month_key not in self.monthly_deposits:
            self.cash_inr         += MONTHLY_BUDGET_INR
            self.total_deposited  += MONTHLY_BUDGET_INR
            self.monthly_deposits[month_key] = MONTHLY_BUDGET_INR
            log.info(f"Monthly deposit: INR {MONTHLY_BUDGET_INR:,} credited. Cash: INR {self.cash_inr:,.0f}")
            self.save()
        else:
            log.info(f"Monthly deposit already credited for {month_key}")

    # ── Position Sizing ───────────────────────────────────────────────────

    def _position_size(self, confidence: int) -> float:
        """Return fraction of available cash to deploy for a given confidence score."""
        for (lo, hi), fraction in SIZING.items():
            if lo <= confidence <= hi:
                return fraction
        return 0.0

    def _next_trade_id(self) -> str:
        self.trade_counter += 1
        return f"T{self.trade_counter:04d}"

    # ── Trade Entry ───────────────────────────────────────────────────────

    def enter_position(
        self,
        signal:    Dict,
        etf:       Dict,
        platform:  str,
    ) -> Optional[Dict]:
        """
        Attempt to enter a paper position based on a signal and selected ETF.
        Returns entry summary dict, or None if rejected.
        """
        confidence  = signal.get("confidence", 0)
        severity    = signal.get("severity", "LOW")
        ticker      = etf["ticker"]
        exchange    = etf.get("exchange", "NYSE")
        etf_name    = etf["name"]
        sector      = signal.get("sector_label", "Unknown")
        headline    = (signal.get("top_headlines") or [""])[0]

        # ── Guards ──────────────────────────────────────────────────────
        if self.cash_inr < 500:
            log.info(f"Position rejected — insufficient cash (INR {self.cash_inr:.0f})")
            return None

        # ── Sizing ──────────────────────────────────────────────────────
        fraction    = self._position_size(confidence)
        if fraction == 0:
            return None

        alloc_inr   = round(min(self.cash_inr * fraction, self.cash_inr * 0.40), 2)
        alloc_inr   = max(alloc_inr, 500)

        # ── Fetch current price ──────────────────────────────────────────
        entry_price = get_current_price_inr(ticker, exchange)
        if entry_price is None or entry_price <= 0:
            log.warning(f"Cannot enter {ticker} — price unavailable")
            return None

        units    = round(alloc_inr / entry_price, 6)
        invested = round(units * entry_price, 2)

        if invested > self.cash_inr:
            log.warning(f"Insufficient cash for {ticker} — need {invested}, have {self.cash_inr:.2f}")
            return None

        # ── Top-up if already holding this ETF ───────────────────────────
        existing = next((p for p in self.open_positions if p.ticker == ticker), None)
        if existing:
            total_invested       = existing.invested_inr + invested
            total_units          = existing.units + units
            avg_price            = round(total_invested / total_units, 4)
            existing.entry_price  = avg_price
            existing.units        = total_units
            existing.invested_inr = total_invested
            existing.confidence   = max(existing.confidence, confidence)
            self.cash_inr        -= invested
            self.save()
            log.info(f"TOPPED UP {existing.trade_id} — {ticker} | +INR {invested:,.2f} | Avg price {avg_price:.4f}")
            return {
                "trade_id":       existing.trade_id,
                "ticker":         ticker,
                "etf_name":       etf_name,
                "platform":       platform,
                "exchange":       exchange,
                "sector":         sector,
                "entry_price":    avg_price,
                "units":          total_units,
                "invested_inr":   invested,
                "confidence":     confidence,
                "severity":       severity,
                "cash_remaining": self.cash_inr,
                "is_topup":       True,
            }

        # ── New position — check max cap ─────────────────────────────────
        if len(self.open_positions) >= MAX_POSITIONS:
            log.info(f"New position rejected — max positions ({MAX_POSITIONS}) reached")
            return None

        # ── Execute ──────────────────────────────────────────────────────
        self.cash_inr -= invested
        trade_id = self._next_trade_id()

        position = Position(
            trade_id        = trade_id,
            ticker          = ticker,
            etf_name        = etf_name,
            exchange        = exchange,
            platform        = platform,
            sector          = sector,
            entry_price     = entry_price,
            units           = units,
            invested_inr    = invested,
            entry_date      = datetime.now(timezone.utc).isoformat(),
            confidence      = confidence,
            severity        = severity,
            signal_headline = headline[:120],
        )
        self.open_positions.append(position)
        self.save()

        log.info(
            f"ENTERED {trade_id} — {ticker} | "
            f"INR {invested:,.2f} | Price {entry_price:.4f} | Units {units:.4f}"
        )

        return {
            "trade_id":     trade_id,
            "ticker":       ticker,
            "etf_name":     etf_name,
            "platform":     platform,
            "exchange":     exchange,
            "sector":       sector,
            "entry_price":  entry_price,
            "units":        units,
            "invested_inr": invested,
            "confidence":   confidence,
            "severity":     severity,
            "cash_remaining": self.cash_inr,
        }

    # ── Mark to Market ────────────────────────────────────────────────────

    def mark_to_market(self) -> List[Dict]:
        """
        Update all open positions with current market prices.
        Check exit conditions. Returns list of closed trade summaries.
        """
        exits = []
        now_str = datetime.now(timezone.utc).isoformat()
        today   = date.today().isoformat()

        positions_to_close = []

        for pos in self.open_positions:
            current = get_current_price_inr(pos.ticker, pos.exchange)
            if current is None:
                log.warning(f"Price unavailable for {pos.ticker} — skipping mark")
                continue

            pos.current_price = current
            pos.last_updated  = now_str

            change_pct  = (current - pos.entry_price) / pos.entry_price
            days        = pos.days_held()

            exit_reason = None
            if change_pct <= -STOP_LOSS_PCT:
                exit_reason = f"Stop-loss hit ({change_pct*100:.1f}%)"
            # No profit target — let winners run
            # exit_reason = "Target" — removed
            elif days >= MAX_HOLD_DAYS:
                exit_reason = f"Max hold period ({days} days)"

            if exit_reason:
                positions_to_close.append((pos, current, today, exit_reason))

        for pos, exit_price, exit_date, reason in positions_to_close:
            self.open_positions.remove(pos)
            ct = ClosedTrade(pos, exit_price, exit_date, reason)
            self.closed_trades.append(ct)
            self.cash_inr += ct.invested_inr + ct.realised_pnl

            log.info(
                f"CLOSED {pos.trade_id} — {pos.ticker} | "
                f"PnL: INR {ct.realised_pnl:+,.2f} ({ct.realised_pnl_pct:+.1f}%) | {reason}"
            )

            exits.append({
                "trade_id":        ct.trade_id,
                "ticker":          ct.ticker,
                "etf_name":        ct.etf_name,
                "platform":        ct.platform,
                "realised_pnl":    ct.realised_pnl,
                "realised_pnl_pct": ct.realised_pnl_pct,
                "days_held":       ct.days_held,
                "exit_reason":     ct.exit_reason,
                "exit_price":      ct.exit_price,
            })

        self.save()
        return exits

    # ── Portfolio Summary ─────────────────────────────────────────────────

    def get_summary(self) -> Dict:
        """Return full portfolio snapshot for reporting."""
        total_invested   = sum(p.invested_inr   for p in self.open_positions)
        total_current    = sum(p.current_value() for p in self.open_positions)
        unrealised_pnl   = total_current - total_invested
        total_realised   = sum(ct.realised_pnl   for ct in self.closed_trades)
        portfolio_value  = self.cash_inr + total_current

        winners = [ct for ct in self.closed_trades if ct.realised_pnl > 0]
        losers  = [ct for ct in self.closed_trades if ct.realised_pnl < 0]
        win_rate = (len(winners) / len(self.closed_trades) * 100) if self.closed_trades else 0

        best_trade  = max(self.closed_trades, key=lambda x: x.realised_pnl_pct, default=None)
        worst_trade = min(self.closed_trades, key=lambda x: x.realised_pnl_pct, default=None)

        return {
            "cash_inr":          round(self.cash_inr, 2),
            "total_invested":    round(total_invested, 2),
            "total_current":     round(total_current, 2),
            "unrealised_pnl":    round(unrealised_pnl, 2),
            "total_realised":    round(total_realised, 2),
            "portfolio_value":   round(portfolio_value, 2),
            "total_deposited":   round(self.total_deposited, 2),
            "total_return_pct":  round(
                ((portfolio_value - self.total_deposited) / self.total_deposited * 100)
                if self.total_deposited > 0 else 0, 2
            ),
            "open_positions":    [p.to_dict() for p in self.open_positions],
            "open_count":        len(self.open_positions),
            "closed_count":      len(self.closed_trades),
            "win_rate":          round(win_rate, 1),
            "winners":           len(winners),
            "losers":            len(losers),
            "best_trade":        best_trade.to_dict() if best_trade else None,
            "worst_trade":       worst_trade.to_dict() if worst_trade else None,
        }
