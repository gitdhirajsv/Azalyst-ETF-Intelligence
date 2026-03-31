"""
paper_trader.py - AZALYST Paper Trading Engine

Institution-style paper trading with:
  - INR-denominated accounting
  - monthly capital top-ups
  - half-Kelly sizing
  - sector caps, drawdown guardrails, and trailing stops
  - partial profit-taking
  - capital rotation into stronger signals when cash is trapped
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
import urllib.request

log = logging.getLogger("azalyst.trader")


MONTHLY_BUDGET_INR = 10_000
MIN_TRADE_INR = 500
MAX_POSITIONS = 8
MAX_SINGLE_POSITION_PCT = 0.40
STOP_LOSS_PCT = 0.10
TRAILING_STOP_PCT = 0.08
TRAIL_ACTIVATION_PCT = 0.05
PARTIAL_PROFIT_PCT = 0.15
PARTIAL_PROFIT_FRACTION = 0.50
SECTOR_CAP_PCT = 0.30
CASH_FLOOR_PCT = 0.05
MAX_HOLD_DAYS = 180
CIRCUIT_BREAKER_DRAWDOWN_PCT = 0.12
ROTATION_CONFIDENCE_DELTA = 6
ROTATION_MIN_HOLD_DAYS = 3

AVG_WIN_BY_SEVERITY = {
    "CRITICAL": 0.20,
    "HIGH": 0.15,
    "MEDIUM": 0.12,
    "LOW": 0.08,
}

USD_TO_INR = 83.5


def fetch_usd_to_inr() -> float:
    """Fetch live USD/INR rate from Yahoo Finance."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        return USD_TO_INR


def fetch_price_usd(ticker: str) -> Optional[float]:
    """Fetch a US-listed ETF price in USD."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception as exc:
        log.warning(f"Price fetch failed for {ticker}: {exc}")
        return None


def fetch_price_inr(ticker: str) -> Optional[float]:
    """Fetch an NSE-listed ETF price in INR."""
    try:
        yf_ticker = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_ticker}?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception as exc:
        log.warning(f"NSE price fetch failed for {ticker}: {exc}")
        return None


def get_current_price_inr(ticker: str, exchange: str) -> Optional[float]:
    """Return the latest ETF price in INR regardless of listing venue."""
    exchange_upper = (exchange or "").upper()
    if "NSE" in exchange_upper or "BSE" in exchange_upper:
        return fetch_price_inr(ticker)
    usd_price = fetch_price_usd(ticker)
    if usd_price is None:
        return None
    return round(usd_price * fetch_usd_to_inr(), 4)


class Position:
    """Represents one live paper position."""

    def __init__(
        self,
        trade_id: str,
        ticker: str,
        etf_name: str,
        exchange: str,
        platform: str,
        sector: str,
        entry_price: float,
        units: float,
        invested_inr: float,
        entry_date: str,
        confidence: int,
        severity: str,
        signal_headline: str,
    ):
        self.trade_id = trade_id
        self.ticker = ticker
        self.etf_name = etf_name
        self.exchange = exchange
        self.platform = platform
        self.sector = sector
        self.entry_price = entry_price
        self.units = units
        self.invested_inr = invested_inr
        self.entry_date = entry_date
        self.confidence = confidence
        self.severity = severity
        self.signal_headline = signal_headline
        self.current_price = entry_price
        self.last_updated = entry_date
        self.peak_price = entry_price
        self.trail_stop = round(entry_price * (1 - STOP_LOSS_PCT), 4)
        self.half_exited = False

    def current_value(self) -> float:
        return round(self.units * self.current_price, 2)

    def unrealised_pnl(self) -> float:
        return round(self.current_value() - self.invested_inr, 2)

    def unrealised_pnl_pct(self) -> float:
        if self.invested_inr <= 0:
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
            "trade_id": self.trade_id,
            "ticker": self.ticker,
            "etf_name": self.etf_name,
            "exchange": self.exchange,
            "platform": self.platform,
            "sector": self.sector,
            "entry_price": self.entry_price,
            "units": self.units,
            "invested_inr": self.invested_inr,
            "entry_date": self.entry_date,
            "confidence": self.confidence,
            "severity": self.severity,
            "signal_headline": self.signal_headline,
            "current_price": self.current_price,
            "last_updated": self.last_updated,
            "peak_price": self.peak_price,
            "trail_stop": self.trail_stop,
            "half_exited": self.half_exited,
        }

    @classmethod
    def from_dict(cls, raw: Dict) -> "Position":
        pos = cls(
            trade_id=raw["trade_id"],
            ticker=raw["ticker"],
            etf_name=raw["etf_name"],
            exchange=raw.get("exchange", "NYSE"),
            platform=raw.get("platform", "Broker"),
            sector=raw["sector"],
            entry_price=raw["entry_price"],
            units=raw["units"],
            invested_inr=raw["invested_inr"],
            entry_date=raw["entry_date"],
            confidence=raw["confidence"],
            severity=raw["severity"],
            signal_headline=raw.get("signal_headline", ""),
        )
        pos.current_price = raw.get("current_price", raw["entry_price"])
        pos.last_updated = raw.get("last_updated", raw["entry_date"])
        pos.peak_price = raw.get("peak_price", max(pos.current_price, pos.entry_price))
        pos.trail_stop = raw.get(
            "trail_stop",
            round(pos.entry_price * (1 - STOP_LOSS_PCT), 4),
        )
        pos.half_exited = raw.get("half_exited", False)
        return pos


class ClosedTrade:
    """Record of one completed position close."""

    def __init__(self, position: Position, exit_price: float, exit_date: str, exit_reason: str):
        self.trade_id = position.trade_id
        self.ticker = position.ticker
        self.etf_name = position.etf_name
        self.platform = position.platform
        self.sector = position.sector
        self.entry_price = position.entry_price
        self.exit_price = exit_price
        self.units = position.units
        self.invested_inr = position.invested_inr
        self.exit_date = exit_date
        self.exit_reason = exit_reason
        self.entry_date = position.entry_date
        self.confidence = position.confidence
        self.severity = position.severity
        self.realised_pnl = round((exit_price - position.entry_price) * position.units, 2)
        self.realised_pnl_pct = round(
            ((exit_price - position.entry_price) / position.entry_price) * 100,
            2,
        )
        self.days_held = position.days_held()

    def to_dict(self) -> Dict:
        return {
            "trade_id": self.trade_id,
            "ticker": self.ticker,
            "etf_name": self.etf_name,
            "platform": self.platform,
            "sector": self.sector,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "units": self.units,
            "invested_inr": self.invested_inr,
            "realised_pnl": self.realised_pnl,
            "realised_pnl_pct": self.realised_pnl_pct,
            "days_held": self.days_held,
            "entry_date": self.entry_date,
            "exit_date": self.exit_date,
            "exit_reason": self.exit_reason,
            "confidence": self.confidence,
            "severity": self.severity,
        }


class PaperPortfolio:
    """Manages paper-book cash, entries, exits, and risk overlays."""

    def __init__(self, portfolio_file: str = "azalyst_portfolio.json"):
        self.portfolio_file = portfolio_file
        self.cash_inr = 0.0
        self.total_deposited = 0.0
        self.partial_realised_pnl_total = 0.0
        self.portfolio_peak = 0.0
        self.max_drawdown_pct = 0.0
        self.open_positions: List[Position] = []
        self.closed_trades: List[ClosedTrade] = []
        self.monthly_deposits: Dict[str, float] = {}
        self.trade_counter = 0

        self._load()
        self._process_monthly_deposit()
        for pos in self.open_positions:
            self._update_position_risk(pos)
        self._update_drawdown_state()

    def _load(self):
        if not os.path.exists(self.portfolio_file):
            log.info("No portfolio file found - starting fresh book")
            return

        try:
            with open(self.portfolio_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            self.cash_inr = data.get("cash_inr", 0.0)
            self.total_deposited = data.get("total_deposited", 0.0)
            self.partial_realised_pnl_total = data.get("partial_realised_pnl_total", 0.0)
            self.portfolio_peak = data.get("portfolio_peak", 0.0)
            self.max_drawdown_pct = data.get("max_drawdown_pct", 0.0)
            self.monthly_deposits = data.get("monthly_deposits", {})
            self.trade_counter = data.get("trade_counter", 0)
            self.open_positions = [Position.from_dict(p) for p in data.get("open_positions", [])]
            self.closed_trades = [ClosedTrade.__new__(ClosedTrade) for _ in data.get("closed_trades", [])]
            for closed_trade, raw in zip(self.closed_trades, data.get("closed_trades", [])):
                closed_trade.__dict__.update(raw)

            log.info(
                "Portfolio loaded - Cash: INR %.0f | Open: %s | Closed: %s",
                self.cash_inr,
                len(self.open_positions),
                len(self.closed_trades),
            )
        except Exception as exc:
            log.error(f"Portfolio load error: {exc}")

    def save(self):
        try:
            data = {
                "cash_inr": self.cash_inr,
                "total_deposited": self.total_deposited,
                "partial_realised_pnl_total": round(self.partial_realised_pnl_total, 2),
                "portfolio_peak": round(self.portfolio_peak, 2),
                "max_drawdown_pct": round(self.max_drawdown_pct, 2),
                "monthly_deposits": self.monthly_deposits,
                "trade_counter": self.trade_counter,
                "open_positions": [p.to_dict() for p in self.open_positions],
                "closed_trades": [ct.to_dict() for ct in self.closed_trades],
                "last_saved": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.portfolio_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except Exception as exc:
            log.error(f"Portfolio save error: {exc}")

    def _process_monthly_deposit(self):
        month_key = date.today().strftime("%Y-%m")
        if month_key in self.monthly_deposits:
            log.info(f"Monthly deposit already credited for {month_key}")
            return

        self.cash_inr += MONTHLY_BUDGET_INR
        self.total_deposited += MONTHLY_BUDGET_INR
        self.monthly_deposits[month_key] = MONTHLY_BUDGET_INR
        log.info(
            "Monthly deposit: INR %s credited. Cash: INR %.0f",
            f"{MONTHLY_BUDGET_INR:,}",
            self.cash_inr,
        )
        self.save()

    def _total_market_value(self) -> float:
        return round(sum(pos.current_value() for pos in self.open_positions), 2)

    def _portfolio_value(self) -> float:
        return round(self.cash_inr + self._total_market_value(), 2)

    def _current_drawdown_pct(self) -> float:
        if self.portfolio_peak <= 0:
            return 0.0
        value = self._portfolio_value()
        return round(((self.portfolio_peak - value) / self.portfolio_peak) * 100, 2)

    def _update_drawdown_state(self):
        value = self._portfolio_value()
        if value <= 0:
            return
        if value > self.portfolio_peak:
            self.portfolio_peak = value
        drawdown = self._current_drawdown_pct()
        if drawdown > self.max_drawdown_pct:
            self.max_drawdown_pct = drawdown

    def _circuit_breaker_active(self) -> bool:
        return self._current_drawdown_pct() >= CIRCUIT_BREAKER_DRAWDOWN_PCT * 100

    def _sector_market_value(self, sector: str) -> float:
        return round(
            sum(pos.current_value() for pos in self.open_positions if pos.sector == sector),
            2,
        )

    def _available_sector_capacity_inr(self, sector: str) -> float:
        portfolio_value = self._portfolio_value()
        if portfolio_value <= 0:
            return 0.0
        cap_value = portfolio_value * SECTOR_CAP_PCT
        return round(max(cap_value - self._sector_market_value(sector), 0.0), 2)

    def _update_position_risk(self, position: Position):
        position.peak_price = max(position.peak_price or 0.0, position.current_price, position.entry_price)
        hard_stop = position.entry_price * (1 - STOP_LOSS_PCT)
        trailing_active = (
            position.peak_price >= position.entry_price * (1 + TRAIL_ACTIVATION_PCT)
            or position.half_exited
        )
        if trailing_active:
            position.trail_stop = round(max(hard_stop, position.peak_price * (1 - TRAILING_STOP_PCT)), 4)
        else:
            position.trail_stop = round(hard_stop, 4)

    def _kelly_fraction(self, confidence: int, severity: str) -> float:
        p = min(confidence / 100.0, 0.99)
        q = 1.0 - p
        avg_win = AVG_WIN_BY_SEVERITY.get(severity, 0.12)
        b = avg_win / STOP_LOSS_PCT
        kelly = (b * p - q) / b
        return round(min(max(kelly * 0.5, 0.05), MAX_SINGLE_POSITION_PCT), 4)

    def _position_size(self, confidence: int, severity: str = "MEDIUM") -> float:
        return self._kelly_fraction(confidence, severity)

    def _select_rotation_candidate(self, signal: Dict) -> Optional[Position]:
        incoming_conf = signal.get("confidence", 0)
        incoming_sector = signal.get("sector_label", "")
        candidates = []

        for pos in self.open_positions:
            pnl_pct = pos.unrealised_pnl_pct()
            score = 0.0

            if incoming_conf >= pos.confidence + ROTATION_CONFIDENCE_DELTA:
                score += (incoming_conf - pos.confidence)
            if pnl_pct < 0:
                score += abs(pnl_pct) * 2.0
            elif pnl_pct < 2:
                score += 2.0
            if pos.days_held() >= ROTATION_MIN_HOLD_DAYS:
                score += min(pos.days_held(), 20) * 0.3
            if pos.sector == incoming_sector:
                score += 1.5

            if score > 0:
                candidates.append((score, pnl_pct, pos.confidence, -pos.days_held(), pos))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))
        return candidates[0][-1]

    def _close_position(self, position: Position, exit_price: float, exit_date: str, reason: str) -> Dict:
        if position in self.open_positions:
            self.open_positions.remove(position)

        closed_trade = ClosedTrade(position, exit_price, exit_date, reason)
        self.closed_trades.append(closed_trade)
        self.cash_inr += round(exit_price * position.units, 2)
        self._update_drawdown_state()

        log.info(
            "CLOSED %s - %s | PnL: INR %s (%+.1f%%) | %s",
            position.trade_id,
            position.ticker,
            f"{closed_trade.realised_pnl:+,.2f}",
            closed_trade.realised_pnl_pct,
            reason,
        )

        return {
            "trade_id": closed_trade.trade_id,
            "ticker": closed_trade.ticker,
            "etf_name": closed_trade.etf_name,
            "platform": closed_trade.platform,
            "realised_pnl": closed_trade.realised_pnl,
            "realised_pnl_pct": closed_trade.realised_pnl_pct,
            "days_held": closed_trade.days_held,
            "exit_reason": closed_trade.exit_reason,
            "exit_price": closed_trade.exit_price,
        }

    def _rotate_for_signal(self, signal: Dict, min_cash_needed: float) -> List[Dict]:
        rotation_exits: List[Dict] = []
        attempts = 0

        while (self.cash_inr < min_cash_needed or len(self.open_positions) >= MAX_POSITIONS) and attempts < 2:
            candidate = self._select_rotation_candidate(signal)
            if candidate is None:
                break

            current_price = get_current_price_inr(candidate.ticker, candidate.exchange)
            if current_price is None or current_price <= 0:
                break

            exit_reason = (
                f"Capital rotation to stronger {signal.get('sector_label', 'signal')} "
                f"({signal.get('confidence', 0)}/100)"
            )
            candidate.current_price = current_price
            self._update_position_risk(candidate)
            rotation_exits.append(
                self._close_position(candidate, current_price, date.today().isoformat(), exit_reason)
            )
            attempts += 1

        if rotation_exits:
            self.save()
        return rotation_exits

    def _execute_partial_profit(self, position: Position) -> Optional[Dict]:
        if position.half_exited:
            return None
        if position.current_price < position.entry_price * (1 + PARTIAL_PROFIT_PCT):
            return None

        sell_units = round(position.units * PARTIAL_PROFIT_FRACTION, 6)
        remaining_units = round(position.units - sell_units, 6)
        if sell_units <= 0 or remaining_units <= 0:
            return None

        sale_value = round(sell_units * position.current_price, 2)
        cost_basis_sold = round(sell_units * position.entry_price, 2)
        realised_pnl = round(sale_value - cost_basis_sold, 2)

        position.units = remaining_units
        position.invested_inr = round(max(position.invested_inr - cost_basis_sold, 0.0), 2)
        position.half_exited = True
        self.cash_inr += sale_value
        self.partial_realised_pnl_total += realised_pnl
        self._update_position_risk(position)
        self._update_drawdown_state()

        log.info(
            "PARTIAL PROFIT - %s | Sold 50%% | Realised INR %+,.2f | Remaining units %.6f",
            position.ticker,
            realised_pnl,
            position.units,
        )

        return {
            "trade_id": position.trade_id,
            "ticker": position.ticker,
            "realised_pnl": realised_pnl,
            "sale_value": sale_value,
        }

    def _recycle_idle_cash(self):
        if not self.open_positions:
            return

        portfolio_value = self._portfolio_value()
        if portfolio_value <= 0:
            return

        cash_ratio = self.cash_inr / portfolio_value
        if cash_ratio < 0.15:
            return

        winners = [pos for pos in self.open_positions if pos.unrealised_pnl_pct() > 0]
        if not winners:
            return

        best_pos = max(winners, key=lambda pos: pos.unrealised_pnl_pct())
        deployable = round(self.cash_inr - portfolio_value * CASH_FLOOR_PCT, 2)
        if deployable < MIN_TRADE_INR:
            return

        current_price = get_current_price_inr(best_pos.ticker, best_pos.exchange)
        if current_price is None or current_price <= 0:
            return

        available_sector_capacity = self._available_sector_capacity_inr(best_pos.sector)
        top_up_inr = round(min(deployable * 0.80, deployable, available_sector_capacity), 2)
        if top_up_inr < MIN_TRADE_INR:
            return

        units_bought = round(top_up_inr / current_price, 6)
        invested = round(units_bought * current_price, 2)
        if invested > self.cash_inr or invested < MIN_TRADE_INR:
            return

        new_invested = round(best_pos.invested_inr + invested, 2)
        new_units = round(best_pos.units + units_bought, 6)
        best_pos.entry_price = round(new_invested / new_units, 4)
        best_pos.units = new_units
        best_pos.invested_inr = new_invested
        best_pos.current_price = current_price
        self.cash_inr -= invested
        self._update_position_risk(best_pos)
        self._update_drawdown_state()

        log.info(
            "IDLE CASH RECYCLED - %s | +INR %.2f | New avg %.4f | Cash INR %.2f",
            best_pos.ticker,
            invested,
            best_pos.entry_price,
            self.cash_inr,
        )
        self.save()

    def _next_trade_id(self) -> str:
        self.trade_counter += 1
        return f"T{self.trade_counter:04d}"

    def enter_position(self, signal: Dict, etf: Dict, platform: str) -> Optional[Dict]:
        confidence = signal.get("confidence", 0)
        severity = signal.get("severity", "LOW")
        ticker = etf["ticker"]
        exchange = etf.get("exchange", "NYSE")
        etf_name = etf["name"]
        sector = signal.get("sector_label", "Unknown")
        headline = (signal.get("top_headlines") or [""])[0]

        self._update_drawdown_state()
        if self._circuit_breaker_active():
            log.info("Position rejected - circuit breaker active")
            return None

        fraction = self._position_size(confidence, severity)
        if fraction <= 0:
            return None

        target_alloc = round(min(self.cash_inr * fraction, self.cash_inr * MAX_SINGLE_POSITION_PCT), 2)
        target_alloc = max(target_alloc, MIN_TRADE_INR)

        rotation_exits: List[Dict] = []
        if self.cash_inr < target_alloc or len(self.open_positions) >= MAX_POSITIONS:
            rotation_exits = self._rotate_for_signal(signal, target_alloc)

        if self.cash_inr < MIN_TRADE_INR:
            log.info("Position rejected - insufficient cash (INR %.0f)", self.cash_inr)
            return None

        entry_price = get_current_price_inr(ticker, exchange)
        if entry_price is None or entry_price <= 0:
            log.warning(f"Cannot enter {ticker} - price unavailable")
            return None

        alloc_inr = round(min(self.cash_inr * fraction, self.cash_inr * MAX_SINGLE_POSITION_PCT), 2)
        alloc_inr = max(alloc_inr, MIN_TRADE_INR)

        sector_capacity = self._available_sector_capacity_inr(sector)
        alloc_inr = round(min(alloc_inr, sector_capacity, self.cash_inr), 2)
        if alloc_inr < MIN_TRADE_INR:
            log.info("Position rejected - sector cap reached for %s", sector)
            return None

        units = round(alloc_inr / entry_price, 6)
        invested = round(units * entry_price, 2)
        if invested > self.cash_inr or invested < MIN_TRADE_INR:
            log.warning(
                "Insufficient cash for %s - need %.2f, have %.2f",
                ticker,
                invested,
                self.cash_inr,
            )
            return None

        existing = next((pos for pos in self.open_positions if pos.ticker == ticker), None)
        if existing:
            new_invested = round(existing.invested_inr + invested, 2)
            new_units = round(existing.units + units, 6)
            existing.entry_price = round(new_invested / new_units, 4)
            existing.units = new_units
            existing.invested_inr = new_invested
            existing.confidence = max(existing.confidence, confidence)
            existing.current_price = entry_price
            self.cash_inr -= invested
            self._update_position_risk(existing)
            self._update_drawdown_state()
            self.save()

            log.info(
                "TOPPED UP %s - %s | +INR %.2f | Avg price %.4f",
                existing.trade_id,
                ticker,
                invested,
                existing.entry_price,
            )

            return {
                "trade_id": existing.trade_id,
                "ticker": ticker,
                "etf_name": etf_name,
                "platform": platform,
                "exchange": exchange,
                "sector": sector,
                "entry_price": existing.entry_price,
                "units": new_units,
                "invested_inr": invested,
                "confidence": confidence,
                "severity": severity,
                "cash_remaining": self.cash_inr,
                "is_topup": True,
                "rotation_exits": rotation_exits,
            }

        if len(self.open_positions) >= MAX_POSITIONS:
            log.info("New position rejected - max positions (%s) reached", MAX_POSITIONS)
            return None

        self.cash_inr -= invested
        position = Position(
            trade_id=self._next_trade_id(),
            ticker=ticker,
            etf_name=etf_name,
            exchange=exchange,
            platform=platform,
            sector=sector,
            entry_price=entry_price,
            units=units,
            invested_inr=invested,
            entry_date=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
            severity=severity,
            signal_headline=headline[:120],
        )
        position.current_price = entry_price
        self._update_position_risk(position)
        self.open_positions.append(position)
        self._update_drawdown_state()
        self.save()

        log.info(
            "ENTERED %s - %s | INR %.2f | Price %.4f | Units %.4f",
            position.trade_id,
            ticker,
            invested,
            entry_price,
            units,
        )

        return {
            "trade_id": position.trade_id,
            "ticker": ticker,
            "etf_name": etf_name,
            "platform": platform,
            "exchange": exchange,
            "sector": sector,
            "entry_price": entry_price,
            "units": units,
            "invested_inr": invested,
            "confidence": confidence,
            "severity": severity,
            "cash_remaining": self.cash_inr,
            "rotation_exits": rotation_exits,
        }

    def mark_to_market(self) -> List[Dict]:
        exits: List[Dict] = []
        now_str = datetime.now(timezone.utc).isoformat()
        today = date.today().isoformat()
        positions_to_close = []

        for position in list(self.open_positions):
            current = get_current_price_inr(position.ticker, position.exchange)
            if current is None or current <= 0:
                log.warning(f"Price unavailable for {position.ticker} - skipping mark")
                continue

            position.current_price = current
            position.last_updated = now_str
            self._update_position_risk(position)
            self._execute_partial_profit(position)
            self._update_position_risk(position)

            trailing_active = (
                position.peak_price >= position.entry_price * (1 + TRAIL_ACTIVATION_PCT)
                or position.half_exited
            )
            change_pct = ((current - position.entry_price) / position.entry_price) if position.entry_price else 0.0
            days = position.days_held()

            exit_reason = None
            if current <= position.trail_stop:
                if trailing_active:
                    exit_reason = f"Trailing stop hit ({change_pct * 100:.1f}%)"
                else:
                    exit_reason = f"Stop-loss hit ({change_pct * 100:.1f}%)"
            elif days >= MAX_HOLD_DAYS:
                exit_reason = f"Max hold period ({days} days)"

            if exit_reason:
                positions_to_close.append((position, current, today, exit_reason))

        for position, exit_price, exit_date, reason in positions_to_close:
            exits.append(self._close_position(position, exit_price, exit_date, reason))

        self._update_drawdown_state()
        self.save()

        if exits:
            self._recycle_idle_cash()

        return exits

    def get_summary(self) -> Dict:
        total_invested = round(sum(pos.invested_inr for pos in self.open_positions), 2)
        total_current = round(sum(pos.current_value() for pos in self.open_positions), 2)
        unrealised_pnl = round(total_current - total_invested, 2)
        closed_realised = round(sum(ct.realised_pnl for ct in self.closed_trades), 2)
        total_realised = round(closed_realised + self.partial_realised_pnl_total, 2)
        portfolio_value = round(self.cash_inr + total_current, 2)

        winners = [ct for ct in self.closed_trades if ct.realised_pnl > 0]
        losers = [ct for ct in self.closed_trades if ct.realised_pnl < 0]
        win_rate = (len(winners) / len(self.closed_trades) * 100) if self.closed_trades else 0.0

        best_trade = max(self.closed_trades, key=lambda trade: trade.realised_pnl_pct, default=None)
        worst_trade = min(self.closed_trades, key=lambda trade: trade.realised_pnl_pct, default=None)

        self._update_drawdown_state()

        return {
            "cash_inr": round(self.cash_inr, 2),
            "total_invested": total_invested,
            "total_current": total_current,
            "unrealised_pnl": unrealised_pnl,
            "total_realised": total_realised,
            "partial_realised_pnl": round(self.partial_realised_pnl_total, 2),
            "portfolio_value": portfolio_value,
            "total_deposited": round(self.total_deposited, 2),
            "total_return_pct": round(
                ((portfolio_value - self.total_deposited) / self.total_deposited * 100)
                if self.total_deposited > 0
                else 0,
                2,
            ),
            "open_positions": [pos.to_dict() for pos in self.open_positions],
            "open_count": len(self.open_positions),
            "closed_count": len(self.closed_trades),
            "win_rate": round(win_rate, 1),
            "winners": len(winners),
            "losers": len(losers),
            "best_trade": best_trade.to_dict() if best_trade else None,
            "worst_trade": worst_trade.to_dict() if worst_trade else None,
            "portfolio_peak": round(self.portfolio_peak, 2),
            "drawdown_now_pct": round(self._current_drawdown_pct(), 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "circuit_breaker_active": self._circuit_breaker_active(),
        }
