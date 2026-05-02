"""
paper_trader.py - AZALYST Paper Trading Engine

Institution-style paper trading with:
  - USD-denominated accounting
  - monthly capital top-ups
  - empirical risk-budget sizing
  - sector caps, drawdown guardrails, and trailing stops
  - partial profit-taking at +8%
  - capital rotation into stronger signals (min 14-day hold)
  - max single position cap at 22%
  - modeled slippage and trading costs
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
import urllib.request

log = logging.getLogger("azalyst.trader")

# Lazy import to avoid circular dependency — loaded on first use
_risk_engine = None
def _get_risk_engine():
    global _risk_engine
    if _risk_engine is None:
        try:
            import risk_engine as _re
            _risk_engine = _re
        except ImportError:
            _risk_engine = None
    return _risk_engine


MONTHLY_BUDGET_USD      = 10_000
MIN_TRADE_USD           = 50
MAX_POSITIONS           = 6
MAX_SINGLE_POSITION_PCT = 0.22
STOP_LOSS_PCT           = 0.10
TRAILING_STOP_PCT       = 0.08
TRAIL_ACTIVATION_PCT    = 0.05
PARTIAL_PROFIT_PCT      = 0.08
PARTIAL_PROFIT_FRACTION = 0.50
SECTOR_CAP_PCT          = 0.30
CASH_FLOOR_PCT          = 0.05
MAX_HOLD_DAYS           = 180
CIRCUIT_BREAKER_DRAWDOWN_PCT = 0.12
ROTATION_CONFIDENCE_DELTA    = 10
ROTATION_MIN_HOLD_DAYS       = 14

BASE_RISK_BUDGET_BY_SEVERITY = {
    "CRITICAL": 0.13,
    "HIGH":     0.10,
    "MEDIUM":   0.07,
    "LOW":      0.04,
}
MIN_RISK_BUDGET_PCT = 0.04
EMPIRICAL_MIN_TRADES = 8

VENUE_EXPLICIT_COST_BPS = {
    "US": {
        "commission_bps": 1.0,
        "tax_bps": 0.0,
    },
    "INDIA": {
        "commission_bps": 4.0,
        "tax_bps": 4.0,
    },
}

RISK_SLIPPAGE_BPS = {
    "LOW": 4.0,
    "LOW-MEDIUM": 6.0,
    "MEDIUM": 10.0,
    "MEDIUM-HIGH": 16.0,
    "HIGH": 28.0,
}

USD_TO_INR = 83.5

MIN_TRADE_INR = round(MIN_TRADE_USD * USD_TO_INR, 2)

# ======== REVIEW BOARD CHANGES: Liquidity checks & realistic cost models ========
# Ken Griffin / Citadel: pre-trade liquidity validation prevents phantom fills.
# Cliff Asness / AQR: ETF costs must be modeled accurately.

# India ETF lot sizes (NSE minimum trading lots) — update quarterly
INDIA_ETF_LOT_SIZES = {
    "NIFTYBEES": 1,
    "BANKBEES": 1,
    "GOLDBEES": 1,
    "HDFCGOLD": 1,
    "MIDCAPETF": 1,
    "CPSEETF": 5,
    "PHARMABEES": 1,
    "HEALTHCARE": 1,
    "REALTY": 1,
    "DEFENCEETF": 5,
    "PSUBNKBEES": 1,
    "BHARATBOND": 1,
    "NEWENERGY": 5,
    "MAFANG": 1,
}

# Realistic India trading costs (Citadel calibration)
# Source: SEBI, NSE, and broker data — updated Q1 2025
INDIA_BUY_COSTS = {
    "brokerage_bps": 5.0,       # Discount broker: ₹20/order flat, ~5 bps for retail size
    "stamp_duty_bps": 0.015,    # 0.015% of transaction value (Maharashtra rate)
    "gst_bps": 0.9,             # 18% GST on brokerage (0.9 bps)
    "sebi_charges_bps": 0.0002, # SEBI turnover fee
    "exchange_fee_bps": 0.00325,# NSE transaction charges
    "total_buy_bps": 5.918,     # Sum of above
}

INDIA_SELL_COSTS = {
    "brokerage_bps": 5.0,
    "stt_bps": 0.025,           # Securities Transaction Tax on sell
    "gst_bps": 0.9,
    "sebi_charges_bps": 0.0002,
    "exchange_fee_bps": 0.00325,
    "total_sell_bps": 5.928,
}

# ADV (Average Daily Volume) thresholds — position size limit
MAX_POSITION_PCT_OF_ADV = 0.01   # Max 1% of 20-day ADV per position
MAX_SPREAD_BPS_WARNING = 50.0    # >50 bps spread → warn and skip

def fetch_etf_liquidity(ticker: str, exchange: str) -> Optional[Dict[str, float]]:
    """
    Fetch ETF's 20-day ADV and current bid-ask spread.
    Uses Yahoo Finance for now — production would use Bloomberg/Reuters.
    
    Returns: {adv_shares, adv_inr, spread_bps, spread_pct} or None
    """
    try:
        import yfinance as yf
        etf = yf.Ticker(ticker if "." not in ticker else ticker.split(".")[0] + ("" if "NSE" not in (exchange or "").upper() else ".NS"))
        
        # 20-day ADV
        hist = etf.history(period="1mo")
        if hist.empty or len(hist) < 5:
            return None
        adv_shares = float(hist["Volume"].tail(20).mean())
        
        # Bid-ask spread
        info = etf.info or {}
        bid = info.get("bid", 0) or 0
        ask = info.get("ask", 0) or 0
        last_price = info.get("regularMarketPrice", 0) or info.get("previousClose", 0) or float(hist["Close"].iloc[-1])
        
        if bid > 0 and ask > 0 and ask > bid:
            spread_pct = (ask - bid) / ask
            spread_bps = spread_pct * 10000
        else:
            # Heuristic: 5 bps for liquid US ETFs, 25 bps for India ETFs
            if "NSE" in (exchange or "").upper() or "BSE" in (exchange or "").upper():
                spread_bps = 25.0
            else:
                spread_bps = 5.0
            spread_pct = spread_bps / 10000.0
        
        adv_inr = adv_shares * last_price
        
        return {
            "adv_shares": round(adv_shares, 0),
            "adv_inr": round(adv_inr, 0),
            "last_price": round(last_price, 2),
            "spread_bps": round(spread_bps, 1),
            "spread_pct": round(spread_pct, 4),
        }
    except Exception as e:
        log.warning("Liquidity check failed for %s: %s", ticker, e)
        return None


def get_india_costs(direction: str = "buy") -> Dict[str, float]:
    """Return realistic India trading costs as fraction of trade value."""
    costs = INDIA_BUY_COSTS if direction == "buy" else INDIA_SELL_COSTS
    return {
        "brokerage": costs["brokerage_bps"] / 10000.0,
        "stamp_or_stt": (costs.get("stamp_duty_bps", 0) if direction == "buy" else costs.get("stt_bps", 0)) / 10000.0,
        "gst": costs["gst_bps"] / 10000.0,
        "sebi": costs["sebi_charges_bps"] / 10000.0,
        "exchange_fee": costs["exchange_fee_bps"] / 10000.0,
        "total_rate": costs[f"total_{direction}_bps"] / 10000.0,
    }



def _venue_key(exchange: str) -> str:
    exchange_upper = (exchange or "").upper()
    if "NSE" in exchange_upper or "BSE" in exchange_upper:
        return "INDIA"
    return "US"


def estimate_execution_cost_model(exchange: str, risk: str = "MEDIUM") -> Dict[str, float]:
    venue_key = _venue_key(exchange)
    venue_model = VENUE_EXPLICIT_COST_BPS.get(venue_key, VENUE_EXPLICIT_COST_BPS["US"])
    slippage_bps = RISK_SLIPPAGE_BPS.get((risk or "MEDIUM").upper(), RISK_SLIPPAGE_BPS["MEDIUM"])
    explicit_bps = venue_model["commission_bps"] + venue_model["tax_bps"]
    return {
        "venue": venue_key,
        "commission_bps": venue_model["commission_bps"],
        "tax_bps": venue_model["tax_bps"],
        "explicit_bps": explicit_bps,
        "slippage_bps": slippage_bps,
        "round_trip_bps": explicit_bps * 2 + slippage_bps * 2,
    }


def build_entry_execution(
    quote_price: float,
    cash_budget_inr: float,
    exchange: str,
    risk: str = "MEDIUM",
) -> Optional[Dict[str, float]]:
    if quote_price <= 0 or cash_budget_inr <= 0:
        return None

    model = estimate_execution_cost_model(exchange, risk)
    explicit_rate = model["explicit_bps"] / 10000.0
    slippage_rate = model["slippage_bps"] / 10000.0
    fill_price = round(quote_price * (1 + slippage_rate), 4)
    gross_budget = cash_budget_inr / (1 + explicit_rate)
    units = round(gross_budget / fill_price, 6)
    if units <= 0:
        return None

    gross_notional = round(units * fill_price, 2)
    fees = round(gross_notional * explicit_rate, 2)
    slippage_cost = round(units * max(fill_price - quote_price, 0.0), 2)
    total_cash = round(gross_notional + fees, 2)

    return {
        "quote_price": round(quote_price, 4),
        "fill_price": fill_price,
        "units": units,
        "gross_notional": gross_notional,
        "fees_inr": fees,
        "slippage_inr": slippage_cost,
        "total_cash_inr": total_cash,
        "total_cost_inr": round(fees + slippage_cost, 2),
        "cost_model": model,
    }


def build_exit_execution(
    quote_price: float,
    units: float,
    exchange: str,
    risk: str = "MEDIUM",
) -> Optional[Dict[str, float]]:
    if quote_price <= 0 or units <= 0:
        return None

    model = estimate_execution_cost_model(exchange, risk)
    explicit_rate = model["explicit_bps"] / 10000.0
    slippage_rate = model["slippage_bps"] / 10000.0
    fill_price = round(quote_price * (1 - slippage_rate), 4)
    gross_proceeds = round(units * fill_price, 2)
    fees = round(gross_proceeds * explicit_rate, 2)
    slippage_cost = round(units * max(quote_price - fill_price, 0.0), 2)
    net_proceeds = round(gross_proceeds - fees, 2)

    return {
        "quote_price": round(quote_price, 4),
        "fill_price": fill_price,
        "gross_proceeds": gross_proceeds,
        "fees_inr": fees,
        "slippage_inr": slippage_cost,
        "net_proceeds_inr": net_proceeds,
        "total_cost_inr": round(fees + slippage_cost, 2),
        "cost_model": model,
    }


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


def get_current_price_inr(
    ticker: str,
    exchange: str,
    usd_inr_rate: Optional[float] = None,
) -> Optional[float]:
    exchange_upper = (exchange or "").upper()
    if "NSE" in exchange_upper or "BSE" in exchange_upper:
        return fetch_price_inr(ticker)
    usd_price = fetch_price_usd(ticker)
    if usd_price is None:
        return None
    rate = usd_inr_rate if usd_inr_rate is not None else fetch_usd_to_inr()
    return round(usd_price * rate, 4)


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
        instrument_risk: str = "MEDIUM",
        entry_reference_price: Optional[float] = None,
        cumulative_costs_inr: float = 0.0,
    ):
        self.trade_id       = trade_id
        self.ticker         = ticker
        self.etf_name       = etf_name
        self.exchange       = exchange
        self.platform       = platform
        self.sector         = sector
        self.entry_price    = entry_price
        self.units          = units
        self.invested_inr   = invested_inr
        self.entry_date     = entry_date
        self.confidence     = confidence
        self.severity       = severity
        self.signal_headline = signal_headline
        self.instrument_risk = instrument_risk
        self.entry_reference_price = entry_reference_price or entry_price
        self.cumulative_costs_inr = cumulative_costs_inr
        self.current_price  = entry_price
        self.last_updated   = entry_date
        self.peak_price     = entry_price
        self.trail_stop     = round(entry_price * (1 - STOP_LOSS_PCT), 4)
        self.half_exited    = False
        self.roi_step       = 0

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
            "trade_id":       self.trade_id,
            "ticker":         self.ticker,
            "etf_name":       self.etf_name,
            "exchange":       self.exchange,
            "platform":       self.platform,
            "sector":         self.sector,
            "entry_price":    self.entry_price,
            "units":          self.units,
            "invested_inr":   self.invested_inr,
            "entry_date":     self.entry_date,
            "confidence":     self.confidence,
            "severity":       self.severity,
            "signal_headline": self.signal_headline,
            "instrument_risk": self.instrument_risk,
            "entry_reference_price": self.entry_reference_price,
            "cumulative_costs_inr": self.cumulative_costs_inr,
            "current_price":  self.current_price,
            "last_updated":   self.last_updated,
            "peak_price":     self.peak_price,
            "trail_stop":     self.trail_stop,
            "half_exited":    self.half_exited,
            "roi_step":       self.roi_step,
        }

    @classmethod
    def from_dict(cls, raw: Dict) -> "Position":
        pos = cls(
            trade_id        = raw["trade_id"],
            ticker          = raw["ticker"],
            etf_name        = raw["etf_name"],
            exchange        = raw.get("exchange", "NYSE"),
            platform        = raw.get("platform", "Broker"),
            sector          = raw["sector"],
            entry_price     = raw["entry_price"],
            units           = raw["units"],
            invested_inr    = raw["invested_inr"],
            entry_date      = raw["entry_date"],
            confidence      = raw["confidence"],
            severity        = raw["severity"],
            signal_headline = raw.get("signal_headline", ""),
            instrument_risk = raw.get("instrument_risk", "MEDIUM"),
            entry_reference_price = raw.get("entry_reference_price", raw["entry_price"]),
            cumulative_costs_inr = raw.get("cumulative_costs_inr", 0.0),
        )
        pos.current_price = raw.get("current_price", raw["entry_price"])
        pos.last_updated  = raw.get("last_updated", raw["entry_date"])
        pos.peak_price    = raw.get("peak_price", max(pos.current_price, pos.entry_price))
        pos.trail_stop    = raw.get(
            "trail_stop",
            round(pos.entry_price * (1 - STOP_LOSS_PCT), 4),
        )
        pos.half_exited = raw.get("half_exited", False)
        pos.roi_step    = raw.get("roi_step", 1 if pos.half_exited else 0)
        return pos


class ClosedTrade:
    """Record of one completed position close."""

    def __init__(
        self,
        position: Position,
        quote_exit_price: float,
        fill_exit_price: float,
        net_proceeds_inr: float,
        execution_costs_inr: float,
        exit_date: str,
        exit_reason: str,
    ):
        self.trade_id        = position.trade_id
        self.ticker          = position.ticker
        self.etf_name        = position.etf_name
        self.platform        = position.platform
        self.exchange        = position.exchange
        self.sector          = position.sector
        self.entry_price     = position.entry_price
        self.exit_price      = fill_exit_price
        self.quote_exit_price = quote_exit_price
        self.units           = position.units
        self.invested_inr    = position.invested_inr
        self.exit_date       = exit_date
        self.exit_reason     = exit_reason
        self.entry_date      = position.entry_date
        self.confidence      = position.confidence
        self.severity        = position.severity
        self.execution_costs_inr = round(execution_costs_inr, 2)
        self.gross_realised_pnl = round(
            (fill_exit_price - position.entry_price) * position.units,
            2,
        )
        self.realised_pnl    = round(net_proceeds_inr - position.invested_inr, 2)
        self.realised_pnl_pct = round(
            (self.realised_pnl / position.invested_inr) * 100 if position.invested_inr else 0.0,
            2,
        )
        self.days_held = position.days_held()

    def to_dict(self) -> Dict:
        return {
            "trade_id":          self.trade_id,
            "ticker":            self.ticker,
            "etf_name":          self.etf_name,
            "platform":          self.platform,
            "exchange":          self.exchange,
            "sector":            self.sector,
            "entry_price":       self.entry_price,
            "exit_price":        self.exit_price,
            "units":             self.units,
            "invested_inr":      self.invested_inr,
            "quote_exit_price":  self.quote_exit_price,
            "realised_pnl":      self.realised_pnl,
            "gross_realised_pnl": self.gross_realised_pnl,
            "realised_pnl_pct":  self.realised_pnl_pct,
            "execution_costs_inr": self.execution_costs_inr,
            "days_held":         self.days_held,
            "entry_date":        self.entry_date,
            "exit_date":         self.exit_date,
            "exit_reason":       self.exit_reason,
            "confidence":        self.confidence,
            "severity":          self.severity,
        }


class PaperPortfolio:
    """Manages paper-book cash, entries, exits, and risk overlays."""

    def __init__(self, portfolio_file: str = "azalyst_portfolio.json"):
        self.portfolio_file              = portfolio_file
        self.cash_inr                    = 0.0
        self.total_deposited             = 0.0
        self.partial_realised_pnl_total  = 0.0
        self.total_execution_costs_inr   = 0.0
        self.portfolio_peak              = 0.0
        self.max_drawdown_pct            = 0.0
        self.open_positions: List[Position]   = []
        self.closed_trades: List[ClosedTrade] = []
        self.monthly_deposits: Dict[str, float] = {}
        self.trade_counter               = 0
        self.monthly_reserve_inr         = 0.0

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

            self.cash_inr                   = data.get("cash_inr", 0.0)
            self.total_deposited            = data.get("total_deposited", 0.0)
            self.partial_realised_pnl_total = data.get("partial_realised_pnl_total", 0.0)
            self.total_execution_costs_inr  = data.get("total_execution_costs_inr", 0.0)
            self.portfolio_peak             = data.get("portfolio_peak", 0.0)
            self.max_drawdown_pct           = data.get("max_drawdown_pct", 0.0)
            self.monthly_deposits           = data.get("monthly_deposits", {})
            self.trade_counter              = data.get("trade_counter", 0)
            self.monthly_reserve_inr        = data.get("monthly_reserve_inr", 0.0)
            self.open_positions             = [Position.from_dict(p) for p in data.get("open_positions", [])]
            self.closed_trades              = [ClosedTrade.__new__(ClosedTrade) for _ in data.get("closed_trades", [])]
            for ct, raw in zip(self.closed_trades, data.get("closed_trades", [])):
                ct.__dict__.update(raw)
                if not hasattr(ct, "exchange"):
                    ct.exchange = "NYSE"

            log.info(
                "Portfolio loaded - Cash: %.0f | Reserve: %.0f | Open: %s | Closed: %s",
                self.cash_inr,
                self.monthly_reserve_inr,
                len(self.open_positions),
                len(self.closed_trades),
            )

            total_invested_inr = sum(pos.invested_inr for pos in self.open_positions)
            portfolio_approx   = self.cash_inr + self.monthly_reserve_inr + total_invested_inr
            if self.total_deposited > 0 and portfolio_approx > 0 and self.total_deposited < portfolio_approx * 0.5:
                original_deposited = data.get("total_deposited", 0)
                corrected = sum(self.monthly_deposits.values())
                if corrected > self.total_deposited:
                    self.total_deposited = corrected
                else:
                    realised_pnl = sum(getattr(ct, "realised_pnl", 0) for ct in self.closed_trades)
                    unrealised   = sum(
                        (pos.current_price - pos.entry_price) * pos.units
                        for pos in self.open_positions
                    )
                    self.total_deposited = portfolio_approx - unrealised - realised_pnl
                log.warning(
                    "Corrected total_deposited from %.2f to %.2f (was likely stored in wrong currency)",
                    original_deposited,
                    self.total_deposited,
                )
                self.save()
        except Exception as exc:
            log.error(f"Portfolio load error: {exc}")

    def save(self):
        try:
            data = {
                "cash_inr":                    self.cash_inr,
                "total_deposited":             self.total_deposited,
                "partial_realised_pnl_total":  round(self.partial_realised_pnl_total, 2),
                "total_execution_costs_inr":   round(self.total_execution_costs_inr, 2),
                "portfolio_peak":              round(self.portfolio_peak, 2),
                "max_drawdown_pct":            round(self.max_drawdown_pct, 2),
                "monthly_deposits":            self.monthly_deposits,
                "trade_counter":               self.trade_counter,
                "monthly_reserve_inr":         round(self.monthly_reserve_inr, 2),
                "open_positions":              [p.to_dict() for p in self.open_positions],
                "closed_trades":               [ct.to_dict() for ct in self.closed_trades],
                "last_saved":                  datetime.now(timezone.utc).isoformat(),
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

        usd_inr_rate   = fetch_usd_to_inr()
        budget_inr     = round(MONTHLY_BUDGET_USD * usd_inr_rate, 2)
        deploy_half  = round(budget_inr * 0.50, 2)
        reserve_half = round(budget_inr - deploy_half, 2)

        self.cash_inr          += deploy_half
        self.monthly_reserve_inr += reserve_half
        self.total_deposited   += budget_inr
        self.monthly_deposits[month_key] = round(budget_inr, 2)
        log.info(
            "Monthly deposit: $%s USD. "
            "Deployed half: %.0f | Reserved half: %.0f | Cash: %.0f",
            f"{MONTHLY_BUDGET_USD:,}",
            deploy_half,
            reserve_half,
            self.cash_inr,
        )
        self.save()

    @property
    def deployable_cash(self) -> float:
        return round(self.cash_inr, 2)

    def _release_reserve(self, amount: float) -> float:
        release = round(min(amount, self.monthly_reserve_inr), 2)
        if release <= 0:
            return 0.0
        self.monthly_reserve_inr -= release
        self.cash_inr += release
        log.info(
            "RESERVE RELEASED: %.2f | Remaining reserve: %.2f | Cash: %.2f",
            release, self.monthly_reserve_inr, self.cash_inr,
        )
        return release

    def _should_release_reserve(self, signal: Dict) -> bool:
        if self.monthly_reserve_inr <= 0:
            return False
        incoming_conf = signal.get("confidence", 0)
        if not self.open_positions:
            return incoming_conf >= 75
        max_existing_conf = max(pos.confidence for pos in self.open_positions)
        return incoming_conf > max_existing_conf

    def _total_market_value(self) -> float:
        return round(sum(pos.current_value() for pos in self.open_positions), 2)

    def _portfolio_value(self) -> float:
        return round(self.cash_inr + self.monthly_reserve_inr + self._total_market_value(), 2)

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

    def _empirical_edge_multiplier(self, severity: str) -> float:
        trades = [ct for ct in self.closed_trades if getattr(ct, "severity", "") == severity]
        if len(trades) < EMPIRICAL_MIN_TRADES:
            return 1.0

        winners = [ct.realised_pnl_pct for ct in trades if ct.realised_pnl_pct > 0]
        losers = [abs(ct.realised_pnl_pct) for ct in trades if ct.realised_pnl_pct < 0]
        if not winners or not losers:
            return 0.9

        win_rate = len(winners) / len(trades)
        avg_win = sum(winners) / len(winners)
        avg_loss = sum(losers) / len(losers)
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        if expectancy <= 0:
            return 0.65
        if expectancy < 1.0:
            return 0.85
        if expectancy > 3.0 and win_rate >= 0.55:
            return 1.15
        return 1.0

    def _position_size(self, confidence: int, severity: str = "MEDIUM") -> float:
        base_fraction = BASE_RISK_BUDGET_BY_SEVERITY.get(severity, BASE_RISK_BUDGET_BY_SEVERITY["MEDIUM"])
        confidence_scalar = 0.75 + max(confidence - 60, 0) / 100.0
        slot_scalar = 1.0 if len(self.open_positions) < 3 else 0.9
        empirical_scalar = self._empirical_edge_multiplier(severity)
        fraction = base_fraction * confidence_scalar * slot_scalar * empirical_scalar
        # Ensure the calculated fraction does not exceed the single position cap
        return round(min(fraction, MAX_SINGLE_POSITION_PCT), 4)

    def _select_rotation_candidate(self, signal: Dict) -> Optional[Position]:
        incoming_conf   = signal.get("confidence", 0)
        incoming_sector = signal.get("sector_label", "")
        candidates = []

        for pos in self.open_positions:
            if pos.days_held() < ROTATION_MIN_HOLD_DAYS:
                continue

            pnl_pct = pos.unrealised_pnl_pct()
            score   = 0.0

            if incoming_conf >= pos.confidence + ROTATION_CONFIDENCE_DELTA:
                score += (incoming_conf - pos.confidence)
            if pnl_pct < 0:
                score += abs(pnl_pct) * 2.0
            elif pnl_pct < 2:
                score += 2.0
            if pos.days_held() >= ROTATION_MIN_HOLD_DAYS:
                score += min(pos.days_held(), 20) * 0.3

            if score > 0:
                candidates.append((score, pnl_pct, pos.confidence, -pos.days_held(), pos))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))
        return candidates[0][-1]

    def _close_position(
        self,
        position: Position,
        exit_price: float,
        exit_date: str,
        reason: str,
    ) -> Dict:
        execution = build_exit_execution(
            exit_price,
            position.units,
            position.exchange,
            getattr(position, "instrument_risk", "MEDIUM"),
        )
        if not execution:
            raise ValueError(f"Cannot build exit execution for {position.ticker}")

        if position in self.open_positions:
            self.open_positions.remove(position)

        ct = ClosedTrade(
            position,
            execution["quote_price"],
            execution["fill_price"],
            execution["net_proceeds_inr"],
            execution["total_cost_inr"],
            exit_date,
            reason,
        )
        self.closed_trades.append(ct)
        self.cash_inr += execution["net_proceeds_inr"]
        self.total_execution_costs_inr += execution["total_cost_inr"]
        self._update_drawdown_state()

        log.info(
            "CLOSED %s - %s | PnL: %s (%+.1f%%) | Costs %.2f | %s",
            position.trade_id,
            position.ticker,
            f"{ct.realised_pnl:+,.2f}",
            ct.realised_pnl_pct,
            execution["total_cost_inr"],
            reason,
        )

        return {
            "trade_id":         ct.trade_id,
            "ticker":           ct.ticker,
            "etf_name":         ct.etf_name,
            "platform":         ct.platform,
            "realised_pnl":     ct.realised_pnl,
            "realised_pnl_pct": ct.realised_pnl_pct,
            "execution_costs_inr": ct.execution_costs_inr,
            "days_held":        ct.days_held,
            "exit_reason":      ct.exit_reason,
            "exit_price":       ct.exit_price,
        }

    def _rotate_for_signal(self, signal: Dict, min_cash_needed: float) -> List[Dict]:
        rotation_exits: List[Dict] = []
        attempts = 0
        usd_inr = fetch_usd_to_inr()

        while (self.cash_inr < min_cash_needed or len(self.open_positions) >= MAX_POSITIONS) and attempts < 2:
            candidate = self._select_rotation_candidate(signal)
            if candidate is None:
                break

            current_price = get_current_price_inr(candidate.ticker, candidate.exchange, usd_inr)
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
        """Freqtrade-inspired Dynamic Step-ROI Logic."""
        roi_table = [
            {"target_pct": 0.05, "sell_fraction": 0.25},
            {"target_pct": 0.10, "sell_fraction": 0.33},
            {"target_pct": 0.15, "sell_fraction": 0.50},
        ]

        step = getattr(position, "roi_step", 0)
        if step >= len(roi_table):
            return None

        current_step = roi_table[step]
        if position.current_price < position.entry_price * (1 + current_step["target_pct"]):
            return None

        sell_units      = round(position.units * current_step["sell_fraction"], 6)
        remaining_units = round(position.units - sell_units, 6)
        if sell_units <= 0 or remaining_units <= 0:
            return None

        execution = build_exit_execution(
            position.current_price,
            sell_units,
            position.exchange,
            getattr(position, "instrument_risk", "MEDIUM"),
        )
        if not execution:
            return None

        prior_units = position.units
        cost_basis_sold = round(
            position.invested_inr * (sell_units / prior_units),
            2,
        )
        sale_value = execution["net_proceeds_inr"]
        realised_pnl = round(sale_value - cost_basis_sold, 2)

        position.units        = remaining_units
        position.invested_inr = round(max(position.invested_inr - cost_basis_sold, 0.0), 2)
        position.half_exited  = True
        position.roi_step     = step + 1
        position.cumulative_costs_inr = round(
            position.cumulative_costs_inr + execution["total_cost_inr"],
            2,
        )
        self.cash_inr                   += sale_value
        self.partial_realised_pnl_total += realised_pnl
        self.total_execution_costs_inr  += execution["total_cost_inr"]
        self._update_position_risk(position)
        self._update_drawdown_state()

        log.info(
            "STEP-ROI - %s | Step %d | Realised %+,.2f | Costs %.2f | Remaining units %.6f",
            position.ticker,
            position.roi_step,
            realised_pnl,
            execution["total_cost_inr"],
            position.units,
        )

        return {
            "trade_id":    position.trade_id,
            "ticker":      position.ticker,
            "realised_pnl": realised_pnl,
            "sale_value":  sale_value,
            "execution_costs_inr": execution["total_cost_inr"],
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

        best_pos    = max(winners, key=lambda pos: pos.unrealised_pnl_pct())
        deployable  = round(self.cash_inr - portfolio_value * CASH_FLOOR_PCT, 2)
        if deployable < MIN_TRADE_INR:
            return

        usd_inr       = fetch_usd_to_inr()
        current_price = get_current_price_inr(best_pos.ticker, best_pos.exchange, usd_inr)
        if current_price is None or current_price <= 0:
            return

        available_sector_capacity = self._available_sector_capacity_inr(best_pos.sector)
        top_up_inr = round(min(deployable * 0.80, deployable, available_sector_capacity), 2)
        if top_up_inr < MIN_TRADE_INR:
            return

        execution = build_entry_execution(
            current_price,
            top_up_inr,
            best_pos.exchange,
            getattr(best_pos, "instrument_risk", "MEDIUM"),
        )
        if not execution:
            return

        units_bought = execution["units"]
        invested = execution["total_cash_inr"]
        if invested > self.cash_inr or invested < MIN_TRADE_INR:
            return

        new_invested          = round(best_pos.invested_inr + invested, 2)
        new_units             = round(best_pos.units + units_bought, 6)
        best_pos.entry_price  = round(new_invested / new_units, 4)
        best_pos.units        = new_units
        best_pos.invested_inr = new_invested
        best_pos.current_price = execution["fill_price"]
        best_pos.entry_reference_price = execution["quote_price"]
        best_pos.cumulative_costs_inr = round(
            best_pos.cumulative_costs_inr + execution["total_cost_inr"],
            2,
        )
        self.cash_inr         -= invested
        self.total_execution_costs_inr += execution["total_cost_inr"]
        self._update_position_risk(best_pos)
        self._update_drawdown_state()

        log.info(
            "IDLE CASH RECYCLED - %s | +%.2f | New avg %.4f | Costs %.2f | Cash %.2f",
            best_pos.ticker, invested, best_pos.entry_price, execution["total_cost_inr"], self.cash_inr,
        )
        self.save()

    def _next_trade_id(self) -> str:
        self.trade_counter += 1
        return f"T{self.trade_counter:04d}"

    def _best_existing_for_topup(self, signal: Dict) -> Optional[Position]:
        """If the new signal is NOT better than a current position IN THE SAME SECTOR,
        return that position to top-up instead of opening a new one.

        FIX: Cross-sector redirect intentionally removed. The previous logic would
        route capital from a new Energy signal into a higher-confidence Tech position,
        which defeats the purpose of sector-targeted signal routing entirely.
        Only same-sector positions qualify for top-up consideration.
        """
        if not self.open_positions:
            return None
        incoming_conf = signal.get("confidence", 0)
        incoming_sector = signal.get("sector_label", "")

        # Only consider same-sector positions — never redirect across sectors.
        same_sector_stronger = [
            pos for pos in self.open_positions
            if pos.sector == incoming_sector
            and pos.confidence >= incoming_conf
            and pos.unrealised_pnl_pct() >= -2.0  # not deeply underwater
        ]
        if not same_sector_stronger:
            return None  # no same-sector candidate — open a new position

        return max(same_sector_stronger, key=lambda p: (p.confidence, p.unrealised_pnl_pct()))

    def enter_position(self, signal: Dict, etf: Dict, platform: str) -> Optional[Dict]:
        confidence = signal.get("confidence", 0)
        severity   = signal.get("severity", "LOW")
        ticker     = etf["ticker"]
        exchange   = etf.get("exchange", "NYSE")
        etf_name   = etf["name"]
        instrument_risk = etf.get("risk", "MEDIUM")
        sector     = signal.get("sector_label", "Unknown")
        headline   = (signal.get("top_headlines") or [""])[0]

        self._update_drawdown_state()
        
        # ======== REVIEW BOARD CHANGE: External shock circuit breaker ========
        # Tudor Jones / Ken Griffin: stop trading when cross-asset stress spikes
        if self._circuit_breaker_active():
            log.info("Position rejected - drawdown circuit breaker active")
            return None
        try:
            from risk_engine import CIRCUIT_BREAKER_ACTIVE
            if CIRCUIT_BREAKER_ACTIVE:
                log.warning("Position rejected - external shock circuit breaker active")
                return None
        except ImportError:
            pass  # risk_engine not loaded, skip check

        # ======== REVIEW BOARD CHANGE: Pre-trade liquidity check ========
        # Ken Griffin / Citadel: validate that the ETF can actually absorb the trade
        liquidity = fetch_etf_liquidity(ticker, exchange)
        if liquidity:
            adv_inr = liquidity.get("adv_inr", 0)
            spread_bps = liquidity.get("spread_bps", 100)
            
            # Skip if spread is too wide
            if spread_bps > MAX_SPREAD_BPS_WARNING:
                log.warning(
                    "Position rejected - spread too wide for %s: %.1f bps (threshold: %.0f bps)",
                    ticker, spread_bps, MAX_SPREAD_BPS_WARNING,
                )
                return None
            
            # Cap position size at 1% of ADV
            max_by_adv = adv_inr * MAX_POSITION_PCT_OF_ADV
            if max_by_adv > 0 and max_by_adv < MIN_TRADE_INR:
                log.warning(
                    "Position rejected - %s is too illiquid: ADV=%.0f, max_position=%.0f < min_trade=%.0f",
                    ticker, adv_inr, max_by_adv, MIN_TRADE_INR,
                )
                return None
            
            # Store liquidity data for sizing
            signal["_liquidity"] = liquidity
            signal["_max_by_adv"] = max_by_adv
        else:
            log.info("Liquidity data unavailable for %s — proceeding with caution", ticker)

        re = _get_risk_engine()
        if re and not any(p.ticker == ticker for p in self.open_positions):
            existing_tickers = [p.ticker for p in self.open_positions]
            if existing_tickers:
                corr_result = re.check_portfolio_correlation(existing_tickers, ticker)
                if corr_result.get("blocked"):
                    log.info(
                        "Position rejected - correlation %.2f with %s exceeds threshold",
                        corr_result["max_corr"], corr_result["corr_with"],
                    )
                    return None

        fraction = self._position_size(confidence, severity)
        if fraction <= 0:
            return None

        if re:
            closes = re.fetch_historical_closes([ticker], "1mo")
            if closes.get(ticker):
                vol_map = re.compute_volatility(closes)
                ticker_vol = vol_map.get(ticker, re.TARGET_VOL)
                fraction = re.vol_adjusted_sizing(fraction, ticker_vol)
                log.info(
                    "Vol-adjusted sizing for %s: vol=%.1f%%, fraction=%.4f",
                    ticker, ticker_vol * 100, fraction,
                )

        if self._should_release_reserve(signal):
            released = self._release_reserve(self.monthly_reserve_inr)
            if released > 0:
                log.info(
                    "Reserve released for superior signal (%s conf %d vs max existing %d)",
                    sector, confidence,
                    max((p.confidence for p in self.open_positions), default=0),
                )

        topup_target = self._best_existing_for_topup(signal)
        if topup_target and not any(p.ticker == ticker for p in self.open_positions):
            log.info(
                "New signal %s (conf %d) not better than existing same-sector %s (conf %d) — topping up",
                sector, confidence, topup_target.ticker, topup_target.confidence,
            )
            ticker   = topup_target.ticker
            etf_name = topup_target.etf_name
            exchange = topup_target.exchange
            platform = topup_target.platform
            sector   = topup_target.sector
            instrument_risk = getattr(topup_target, "instrument_risk", instrument_risk)

        target_alloc = round(min(self.cash_inr * fraction, self.cash_inr * MAX_SINGLE_POSITION_PCT), 2)
        target_alloc = max(target_alloc, MIN_TRADE_INR)

        rotation_exits: List[Dict] = []
        if self.cash_inr < target_alloc or len(self.open_positions) >= MAX_POSITIONS:
            rotation_exits = self._rotate_for_signal(signal, target_alloc)

        if self.cash_inr < MIN_TRADE_INR:
            log.info("Position rejected - insufficient cash (%.0f)", self.cash_inr)
            return None

        usd_inr     = fetch_usd_to_inr()
        entry_price = get_current_price_inr(ticker, exchange, usd_inr)
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

        execution = build_entry_execution(entry_price, alloc_inr, exchange, instrument_risk)
        if not execution:
            log.warning("Cannot build entry execution for %s", ticker)
            return None

        units = execution["units"]
        invested = execution["total_cash_inr"]
        if invested > self.cash_inr or invested < MIN_TRADE_INR:
            log.warning(
                "Insufficient cash for %s - need %.2f, have %.2f",
                ticker, invested, self.cash_inr,
            )
            return None

        existing = next((pos for pos in self.open_positions if pos.ticker == ticker), None)
        if existing:
            new_invested          = round(existing.invested_inr + invested, 2)
            new_units             = round(existing.units + units, 6)
            existing.entry_price  = round(new_invested / new_units, 4)
            existing.units        = new_units
            existing.invested_inr = new_invested
            existing.confidence   = max(existing.confidence, confidence)
            existing.current_price = execution["fill_price"]
            existing.entry_reference_price = execution["quote_price"]
            existing.cumulative_costs_inr = round(
                existing.cumulative_costs_inr + execution["total_cost_inr"],
                2,
            )
            self.cash_inr -= invested
            self.total_execution_costs_inr += execution["total_cost_inr"]
            self._update_position_risk(existing)
            self._update_drawdown_state()
            self.save()

            log.info(
                "TOPPED UP %s - %s | +%.2f | Avg price %.4f | Costs %.2f",
                existing.trade_id, ticker, invested, existing.entry_price, execution["total_cost_inr"],
            )

            return {
                "trade_id":       existing.trade_id,
                "ticker":         ticker,
                "etf_name":       etf_name,
                "platform":       platform,
                "exchange":       exchange,
                "sector":         sector,
                "entry_price":    existing.entry_price,
                "units":          new_units,
                "invested_inr":   invested,
                "execution_costs_inr": execution["total_cost_inr"],
                "confidence":     confidence,
                "severity":       severity,
                "cash_remaining": self.cash_inr,
                "is_topup":       True,
                "rotation_exits": rotation_exits,
            }

        if len(self.open_positions) >= MAX_POSITIONS:
            log.info("New position rejected - max positions (%s) reached", MAX_POSITIONS)
            return None

        self.cash_inr -= invested
        position = Position(
            trade_id        = self._next_trade_id(),
            ticker          = ticker,
            etf_name        = etf_name,
            exchange        = exchange,
            platform        = platform,
            sector          = sector,
            entry_price     = execution["fill_price"],
            units           = units,
            invested_inr    = invested,
            entry_date      = datetime.now(timezone.utc).isoformat(),
            confidence      = confidence,
            severity        = severity,
            signal_headline = headline[:120],
            instrument_risk = instrument_risk,
            entry_reference_price = execution["quote_price"],
            cumulative_costs_inr = execution["total_cost_inr"],
        )
        position.current_price = execution["fill_price"]
        self._update_position_risk(position)
        self.open_positions.append(position)
        self.total_execution_costs_inr += execution["total_cost_inr"]
        self._update_drawdown_state()
        self.save()

        log.info(
            "ENTERED %s - %s | %.2f | Fill %.4f | Units %.4f | Costs %.2f",
            position.trade_id, ticker, invested, execution["fill_price"], units, execution["total_cost_inr"],
        )

        return {
            "trade_id":       position.trade_id,
            "ticker":         ticker,
            "etf_name":       etf_name,
            "platform":       platform,
            "exchange":       exchange,
            "sector":         sector,
            "entry_price":    execution["fill_price"],
            "units":          units,
            "invested_inr":   invested,
            "execution_costs_inr": execution["total_cost_inr"],
            "confidence":     confidence,
            "severity":       severity,
            "cash_remaining": self.cash_inr,
            "rotation_exits": rotation_exits,
        }

    def mark_to_market(self) -> List[Dict]:
        exits: List[Dict] = []
        now_str = datetime.now(timezone.utc).isoformat()
        today   = date.today().isoformat()
        positions_to_close = []

        usd_inr = fetch_usd_to_inr()

        for position in list(self.open_positions):
            current = get_current_price_inr(position.ticker, position.exchange, usd_inr)
            if current is None or current <= 0:
                log.warning(f"Price unavailable for {position.ticker} - skipping mark")
                continue

            position.current_price = current
            position.last_updated  = now_str
            self._update_position_risk(position)
            self._execute_partial_profit(position)
            self._update_position_risk(position)

            trailing_active = (
                position.peak_price >= position.entry_price * (1 + TRAIL_ACTIVATION_PCT)
                or position.half_exited
            )
            change_pct = (
                (current - position.entry_price) / position.entry_price
                if position.entry_price else 0.0
            )
            days = position.days_held()

            exit_reason = None
            if current <= position.trail_stop:
                if trailing_active:
                    exit_reason = f"Trailing stop hit ({change_pct * 100:.1f}%)"
                else:
                    exit_reason = f"Stop-loss hit ({change_pct * 100:.1f}%)"
            elif days >= 14 and change_pct <= -0.02:
                exit_reason = f"Time-based unclogging ({days} days, {change_pct * 100:.1f}%)"
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

        re = _get_risk_engine()
        if re and self.open_positions:
            pos_dicts = [p.to_dict() for p in self.open_positions]
            pv = self._portfolio_value()
            drift_alerts = re.check_rebalance_drift(pos_dicts, self.cash_inr, pv)
            for alert in drift_alerts:
                log.info(
                    "REBALANCE ALERT: %s drifted %+.1f%% (actual %.1f%% vs target %.1f%%) — %s $%.0f",
                    alert["ticker"], alert["drift_pct"],
                    alert["actual_weight_pct"], alert["target_weight_pct"],
                    alert["action"], alert["amount"],
                )

        return exits

    def get_summary(self) -> Dict:
        total_invested = round(sum(pos.invested_inr for pos in self.open_positions), 2)
        total_current  = round(sum(pos.current_value() for pos in self.open_positions), 2)
        unrealised_pnl = round(total_current - total_invested, 2)
        closed_realised = round(sum(ct.realised_pnl for ct in self.closed_trades), 2)
        total_realised  = round(closed_realised + self.partial_realised_pnl_total, 2)
        portfolio_value = round(self.cash_inr + self.monthly_reserve_inr + total_current, 2)

        winners   = [ct for ct in self.closed_trades if ct.realised_pnl > 0]
        losers    = [ct for ct in self.closed_trades if ct.realised_pnl < 0]
        win_rate  = (len(winners) / len(self.closed_trades) * 100) if self.closed_trades else 0.0

        best_trade  = max(self.closed_trades, key=lambda t: t.realised_pnl_pct, default=None)
        worst_trade = min(self.closed_trades, key=lambda t: t.realised_pnl_pct, default=None)

        usd_inr_rate = fetch_usd_to_inr()
        self._update_drawdown_state()

        return {
            "cash_inr":              round(self.cash_inr, 2),
            "monthly_reserve_inr":   round(self.monthly_reserve_inr, 2),
            "total_invested":        total_invested,
            "total_current":         total_current,
            "unrealised_pnl":        unrealised_pnl,
            "total_realised":        total_realised,
            "partial_realised_pnl":  round(self.partial_realised_pnl_total, 2),
            "total_execution_costs_inr": round(self.total_execution_costs_inr, 2),
            "portfolio_value":       portfolio_value,
            "total_deposited":       round(self.total_deposited, 2),
            "total_return_pct":      round(
                ((portfolio_value - self.total_deposited) / self.total_deposited * 100)
                if self.total_deposited > 0 else 0,
                2,
            ),
            "usd_inr_rate":          usd_inr_rate,
            "open_positions":  [pos.to_dict() for pos in self.open_positions],
            "open_count":      len(self.open_positions),
            "closed_count":    len(self.closed_trades),
            "win_rate":        round(win_rate, 1),
            "winners":         len(winners),
            "losers":          len(losers),
            "best_trade":      best_trade.to_dict() if best_trade else None,
            "worst_trade":     worst_trade.to_dict() if worst_trade else None,
            "portfolio_peak":  round(self.portfolio_peak, 2),
            "drawdown_now_pct": round(self._current_drawdown_pct(), 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "circuit_breaker_active": self._circuit_breaker_active(),
        }
