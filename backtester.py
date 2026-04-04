"""
backtester.py - AZALYST Historical Signal Replay

Historical replay is different from paper trading:
  - paper trading tests signals going forward from today
  - backtesting replays dated historical signals against historical prices

Input:
  JSON or JSONL file containing dated signal events. Each event should include:
    {
      "timestamp": "2025-01-15T10:30:00Z",
      "sectors": ["technology_ai"],
      "sector_label": "Technology & AI / Semiconductors",
      "confidence": 78,
      "severity": "HIGH"
    }

Usage:
  python backtester.py --signals data/backtest_events.sample.jsonl
"""

import argparse
import bisect
import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from etf_mapper import ETFMapper
from paper_trader import (
    BASE_RISK_BUDGET_BY_SEVERITY,
    MAX_HOLD_DAYS,
    MAX_POSITIONS,
    MAX_SINGLE_POSITION_PCT,
    MIN_RISK_BUDGET_PCT,
    MIN_TRADE_USD,
    PARTIAL_PROFIT_FRACTION,
    PARTIAL_PROFIT_PCT,
    SECTOR_CAP_PCT,
    STOP_LOSS_PCT,
    TRAIL_ACTIVATION_PCT,
    TRAILING_STOP_PCT,
    USD_TO_INR,
    build_entry_execution,
    build_exit_execution,
)

log = logging.getLogger("azalyst.backtester")
ROOT = Path(__file__).resolve().parent


def _parse_ts(value: str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _venue_symbol(ticker: str, exchange: str) -> str:
    exchange_upper = (exchange or "").upper()
    if ("NSE" in exchange_upper or "BSE" in exchange_upper) and not ticker.endswith(".NS"):
        return f"{ticker}.NS"
    return ticker


def _fetch_daily_closes(ticker: str, exchange: str, start_dt: datetime, end_dt: datetime) -> Dict[date, float]:
    symbol = _venue_symbol(ticker, exchange)
    period1 = int(start_dt.timestamp())
    period2 = int((end_dt + timedelta(days=1)).timestamp())
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?period1={period1}&period2={period2}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return {}

    chart = result[0]
    timestamps = chart.get("timestamp") or []
    closes = (((chart.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    rows: Dict[date, float] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        rows[datetime.fromtimestamp(ts, tz=timezone.utc).date()] = round(float(close) * USD_TO_INR, 4)
    return rows


def _load_events(path: Path) -> List[Dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        raw = [json.loads(line) for line in text.splitlines() if line.strip()]

    events = []
    mapper = ETFMapper()
    for item in raw:
        event = dict(item)
        event["timestamp"] = _parse_ts(event["timestamp"])
        event.setdefault("sectors", [])
        event.setdefault("sector_label", "Unknown")
        event.setdefault("confidence", 0)
        event.setdefault("severity", "MEDIUM")
        event["etf_recommendations"] = event.get("etf_recommendations") or mapper.get_etfs(
            event["sectors"],
            event,
        )
        primary = event["etf_recommendations"].get("primary")
        if not primary:
            continue
        event["ticker"] = primary["ticker"]
        event["exchange"] = primary.get("exchange", "NYSE")
        event["etf_name"] = primary.get("name", primary["ticker"])
        event["instrument_risk"] = primary.get("risk", "MEDIUM")
        events.append(event)
    return sorted(events, key=lambda item: item["timestamp"])


def _next_price_date(ordered_dates: List[date], target: date) -> Optional[date]:
    index = bisect.bisect_left(ordered_dates, target)
    if index >= len(ordered_dates):
        return None
    return ordered_dates[index]


def _price_on_or_before(history: Dict[date, float], ordered_dates: List[date], target: date) -> Optional[float]:
    index = bisect.bisect_right(ordered_dates, target) - 1
    if index < 0:
        return None
    return history.get(ordered_dates[index])


def _size_fraction(confidence: int, severity: str) -> float:
    base = BASE_RISK_BUDGET_BY_SEVERITY.get(severity, BASE_RISK_BUDGET_BY_SEVERITY["MEDIUM"])
    confidence_scalar = 0.75 + max(confidence - 60, 0) / 100.0
    return max(MIN_RISK_BUDGET_PCT, min(base * confidence_scalar, MAX_SINGLE_POSITION_PCT))


@dataclass
class SimPosition:
    ticker: str
    exchange: str
    sector: str
    risk: str
    units: float
    invested_inr: float
    entry_price: float
    entry_date: date
    confidence: int
    severity: str
    peak_price: float
    trail_stop: float
    half_exited: bool = False

    def days_held(self, current_day: date) -> int:
        return (current_day - self.entry_date).days

    def current_value(self, price: float) -> float:
        return round(self.units * price, 2)


class HistoricalReplay:
    def __init__(self, events: List[Dict], initial_capital_usd: float = 10000.0):
        self.events = events
        self.initial_capital_inr = round(initial_capital_usd * USD_TO_INR, 2)
        self.cash_inr = self.initial_capital_inr
        self.open_positions: List[SimPosition] = []
        self.closed_trades: List[Dict] = []
        self.total_execution_costs_inr = 0.0
        self.daily_equity: List[Dict] = []
        self.price_cache: Dict[str, Dict[date, float]] = {}
        self.price_dates: Dict[str, List[date]] = {}

    def _prepare_prices(self):
        if not self.events:
            return
        start_dt = min(event["timestamp"] for event in self.events) - timedelta(days=10)
        end_dt = max(event["timestamp"] for event in self.events) + timedelta(days=MAX_HOLD_DAYS + 10)
        tickers = {(event["ticker"], event["exchange"]) for event in self.events}
        tickers.update({("SPY", "NYSE"), ("VT", "NYSE"), ("AGG", "NYSE")})

        for ticker, exchange in sorted(tickers):
            try:
                history = _fetch_daily_closes(ticker, exchange, start_dt, end_dt)
                if history:
                    self.price_cache[ticker] = history
                    self.price_dates[ticker] = sorted(history.keys())
            except Exception as exc:
                log.warning("Price history fetch failed for %s: %s", ticker, exc)

    def _portfolio_value(self, current_day: date) -> float:
        total = self.cash_inr
        for pos in self.open_positions:
            history = self.price_cache.get(pos.ticker, {})
            dates = self.price_dates.get(pos.ticker, [])
            mark = _price_on_or_before(history, dates, current_day)
            if mark:
                total += pos.current_value(mark)
        return round(total, 2)

    def _sector_exposure(self, sector: str, current_day: date) -> float:
        exposure = 0.0
        for pos in self.open_positions:
            if pos.sector != sector:
                continue
            history = self.price_cache.get(pos.ticker, {})
            dates = self.price_dates.get(pos.ticker, [])
            mark = _price_on_or_before(history, dates, current_day)
            if mark:
                exposure += pos.current_value(mark)
        return round(exposure, 2)

    def _mark_to_market(self, current_day: date):
        survivors: List[SimPosition] = []
        for pos in self.open_positions:
            history = self.price_cache.get(pos.ticker, {})
            dates = self.price_dates.get(pos.ticker, [])
            mark = _price_on_or_before(history, dates, current_day)
            if mark is None:
                survivors.append(pos)
                continue

            pos.peak_price = max(pos.peak_price, mark)
            trailing_active = pos.peak_price >= pos.entry_price * (1 + TRAIL_ACTIVATION_PCT) or pos.half_exited
            hard_stop = pos.entry_price * (1 - STOP_LOSS_PCT)
            pos.trail_stop = max(hard_stop, pos.peak_price * (1 - TRAILING_STOP_PCT)) if trailing_active else hard_stop

            if (not pos.half_exited) and mark >= pos.entry_price * (1 + PARTIAL_PROFIT_PCT):
                sell_units = round(pos.units * PARTIAL_PROFIT_FRACTION, 6)
                execution = build_exit_execution(mark, sell_units, pos.exchange, pos.risk)
                if execution:
                    cost_basis_sold = round(pos.invested_inr * (sell_units / pos.units), 2)
                    net_proceeds = execution["net_proceeds_inr"]
                    self.cash_inr += net_proceeds
                    self.total_execution_costs_inr += execution["total_cost_inr"]
                    pos.invested_inr = round(pos.invested_inr - cost_basis_sold, 2)
                    pos.units = round(pos.units - sell_units, 6)
                    pos.half_exited = True

            exit_reason = None
            if mark <= pos.trail_stop:
                exit_reason = "Trailing/stop exit"
            elif pos.days_held(current_day) >= MAX_HOLD_DAYS:
                exit_reason = "Max hold exit"

            if exit_reason:
                execution = build_exit_execution(mark, pos.units, pos.exchange, pos.risk)
                if execution:
                    self.cash_inr += execution["net_proceeds_inr"]
                    self.total_execution_costs_inr += execution["total_cost_inr"]
                    realised_pnl = round(execution["net_proceeds_inr"] - pos.invested_inr, 2)
                    self.closed_trades.append({
                        "ticker": pos.ticker,
                        "sector": pos.sector,
                        "entry_date": pos.entry_date.isoformat(),
                        "exit_date": current_day.isoformat(),
                        "entry_price": pos.entry_price,
                        "exit_price": execution["fill_price"],
                        "realised_pnl": realised_pnl,
                        "realised_pnl_pct": round((realised_pnl / pos.invested_inr) * 100 if pos.invested_inr else 0.0, 2),
                        "execution_costs_inr": execution["total_cost_inr"],
                        "confidence": pos.confidence,
                        "severity": pos.severity,
                        "exit_reason": exit_reason,
                    })
                continue

            survivors.append(pos)

        self.open_positions = survivors

    def _enter_signal(self, event: Dict, current_day: date):
        if len(self.open_positions) >= MAX_POSITIONS:
            return
        if any(pos.ticker == event["ticker"] for pos in self.open_positions):
            return

        history = self.price_cache.get(event["ticker"], {})
        dates = self.price_dates.get(event["ticker"], [])
        mark = _price_on_or_before(history, dates, current_day)
        if mark is None:
            return

        portfolio_value = self._portfolio_value(current_day)
        sector_cap = portfolio_value * SECTOR_CAP_PCT
        sector_remaining = max(sector_cap - self._sector_exposure(event["sector_label"], current_day), 0.0)
        if sector_remaining <= 0:
            return

        fraction = _size_fraction(event["confidence"], event["severity"])
        budget = min(self.cash_inr * fraction, self.cash_inr * MAX_SINGLE_POSITION_PCT, sector_remaining)
        if budget < MIN_TRADE_USD * USD_TO_INR:
            return

        execution = build_entry_execution(mark, budget, event["exchange"], event["instrument_risk"])
        if not execution or execution["total_cash_inr"] > self.cash_inr:
            return

        self.cash_inr -= execution["total_cash_inr"]
        self.total_execution_costs_inr += execution["total_cost_inr"]
        self.open_positions.append(
            SimPosition(
                ticker=event["ticker"],
                exchange=event["exchange"],
                sector=event["sector_label"],
                risk=event["instrument_risk"],
                units=execution["units"],
                invested_inr=execution["total_cash_inr"],
                entry_price=execution["fill_price"],
                entry_date=current_day,
                confidence=event["confidence"],
                severity=event["severity"],
                peak_price=execution["fill_price"],
                trail_stop=execution["fill_price"] * (1 - STOP_LOSS_PCT),
            )
        )

    def _benchmarks(self, start_day: date, end_day: date) -> Dict[str, float]:
        output = {}
        for ticker in ("SPY", "VT", "AGG"):
            history = self.price_cache.get(ticker, {})
            dates = self.price_dates.get(ticker, [])
            start_price = _price_on_or_before(history, dates, start_day)
            end_price = _price_on_or_before(history, dates, end_day)
            if start_price and end_price:
                output[ticker] = round(((end_price - start_price) / start_price) * 100, 2)
        return output

    def run(self) -> Dict:
        if not self.events:
            return {"error": "No events supplied"}

        self._prepare_prices()
        entry_schedule: Dict[date, List[Dict]] = {}
        all_days = set()

        for event in self.events:
            dates = self.price_dates.get(event["ticker"], [])
            if not dates:
                continue
            entry_day = _next_price_date(dates, event["timestamp"].date())
            if entry_day is None:
                continue
            entry_schedule.setdefault(entry_day, []).append(event)
            all_days.update(self.price_cache.get(event["ticker"], {}).keys())

        for ticker in ("SPY", "VT", "AGG"):
            all_days.update(self.price_cache.get(ticker, {}).keys())

        ordered_days = sorted(day for day in all_days if day >= min(entry_schedule) and day <= max(all_days))
        if not ordered_days:
            return {"error": "No overlapping market data for supplied events"}

        for current_day in ordered_days:
            self._mark_to_market(current_day)
            for event in sorted(entry_schedule.get(current_day, []), key=lambda item: item["confidence"], reverse=True):
                self._enter_signal(event, current_day)

            self.daily_equity.append({
                "date": current_day.isoformat(),
                "equity_inr": self._portfolio_value(current_day),
            })

        final_day = ordered_days[-1]
        self._mark_to_market(final_day)
        final_value = self._portfolio_value(final_day)
        peak = 0.0
        max_drawdown = 0.0
        for row in self.daily_equity:
            equity = row["equity_inr"]
            peak = max(peak, equity)
            if peak > 0:
                drawdown = ((peak - equity) / peak) * 100
                max_drawdown = max(max_drawdown, drawdown)

        winners = [trade for trade in self.closed_trades if trade["realised_pnl"] > 0]
        losers = [trade for trade in self.closed_trades if trade["realised_pnl"] < 0]
        avg_win = sum(t["realised_pnl_pct"] for t in winners) / len(winners) if winners else 0.0
        avg_loss = sum(t["realised_pnl_pct"] for t in losers) / len(losers) if losers else 0.0
        win_rate = (len(winners) / len(self.closed_trades) * 100) if self.closed_trades else 0.0

        return {
            "initial_capital_usd": round(self.initial_capital_inr / USD_TO_INR, 2),
            "final_value_usd": round(final_value / USD_TO_INR, 2),
            "total_return_pct": round(((final_value - self.initial_capital_inr) / self.initial_capital_inr) * 100, 2),
            "cash_usd": round(self.cash_inr / USD_TO_INR, 2),
            "open_positions": len(self.open_positions),
            "closed_trades": len(self.closed_trades),
            "win_rate": round(win_rate, 2),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "execution_costs_usd": round(self.total_execution_costs_inr / USD_TO_INR, 2),
            "benchmarks": self._benchmarks(ordered_days[0], final_day),
            "trades": self.closed_trades,
            "daily_equity": self.daily_equity,
        }


def run_walk_forward(events: List[Dict], splits: int, initial_capital_usd: float) -> List[Dict]:
    """Run simple chronological rolling test windows over the supplied events."""
    if splits <= 1 or len(events) < 4:
        return []

    ordered = sorted(events, key=lambda item: item["timestamp"])
    chunk_size = max(len(ordered) // splits, 1)
    windows = []

    for start in range(0, len(ordered), chunk_size):
        stop = min(start + chunk_size, len(ordered))
        window_events = ordered[start:stop]
        if len(window_events) < 2:
            continue
        replay = HistoricalReplay(window_events, initial_capital_usd=initial_capital_usd)
        summary = replay.run()
        if summary.get("error"):
            continue
        windows.append({
            "window": len(windows) + 1,
            "from": window_events[0]["timestamp"].date().isoformat(),
            "to": window_events[-1]["timestamp"].date().isoformat(),
            "events": len(window_events),
            "total_return_pct": summary["total_return_pct"],
            "max_drawdown_pct": summary["max_drawdown_pct"],
            "win_rate": summary["win_rate"],
            "benchmarks": summary["benchmarks"],
        })

    return windows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--signals", required=True, help="Path to JSON or JSONL historical signal file")
    parser.add_argument("--initial-capital-usd", type=float, default=10000.0)
    parser.add_argument("--walk-forward-splits", type=int, default=0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    signal_path = Path(args.signals)
    events = _load_events(signal_path)
    result = HistoricalReplay(events, initial_capital_usd=args.initial_capital_usd).run()
    if not result.get("error") and args.walk_forward_splits > 1:
        result["walk_forward"] = run_walk_forward(
            events,
            splits=args.walk_forward_splits,
            initial_capital_usd=args.initial_capital_usd,
        )
    output = json.dumps(result, indent=2)
    print(output)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
