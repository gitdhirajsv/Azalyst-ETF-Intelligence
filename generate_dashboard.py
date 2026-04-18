import datetime
import json
import math
import os
import statistics
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Aladdin-grade risk engine
try:
    import risk_engine
except ImportError:
    risk_engine = None

ROOT = Path(__file__).resolve().parent
PORTFOLIO_FILE = ROOT / "azalyst_portfolio.json"
STATE_FILE     = ROOT / "azalyst_state.json"
OUTPUT_FILE    = ROOT / "status.json"

TRAIL_ACTIVATION_PCT        = 0.05
TRAILING_STOP_PCT           = 0.08
HARD_STOP_PCT               = 0.10
PARTIAL_PROFIT_PCT          = 0.08
SECTOR_CAP_PCT              = 30
CIRCUIT_BREAKER_DRAWDOWN_PCT = 12

SECTOR_LABELS = {
    "defense":                "Defense & Aerospace",
    "defense_aerospace":      "Defense & Aerospace",
    "india_equity":           "India Equity",
    "banking_financial":      "Banking & Finance",
    "gold_precious_metals":   "Precious Metals",
    "energy_oil":             "Energy & Oil",
    "commodities_mining":     "Commodities",
    "crypto_digital":         "Crypto & Digital",
    "technology_ai":          "Technology & AI",
    "nuclear_uranium":        "Nuclear & Uranium",
    "cybersecurity":          "Cybersecurity",
    "emerging_markets":       "Emerging Markets",
    "healthcare_pharma":      "Healthcare & Pharma",
    "clean_energy_renewables": "Clean Energy",
    "real_estate_reit":       "Real Estate & REITs",
    "bonds_fixed_income":     "Bonds & Fixed Income",
    "asia_pacific":           "Asia Pacific",
    "europe_equity":          "Europe Equity",
}

MARKET_TICKERS = [
    ("^GSPC",    "S&P 500",    "US"),
    ("^IXIC",    "NASDAQ",     "US"),
    ("^DJI",     "Dow Jones",  "US"),
    ("^FTSE",    "FTSE 100",   "UK"),
    ("^GDAXI",   "DAX",        "EU"),
    ("^N225",    "Nikkei 225", "JP"),
    ("^HSI",     "Hang Seng",  "HK"),
    ("^NSEI",    "Nifty 50",   "IN"),
    ("GC=F",     "Gold",       "COMMOD"),
    ("CL=F",     "Crude Oil",  "COMMOD"),
    ("BTC-USD",  "Bitcoin",    "CRYPTO"),
    ("DX-Y.NYB", "USD Index",  "FX"),
    ("^VIX",     "VIX",        "VOL"),
]


def clean_label(raw_key: str) -> str:
    key = raw_key.split("|")[0].strip().lower()
    return SECTOR_LABELS.get(key, key.replace("_", " ").title())


def load_json(path: Path) -> Dict:
    if not os.path.exists(path):
        print(f"WARNING: not found: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"WARNING: could not load {path}: {exc}")
        return {}


def parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def format_timestamp(value) -> str:
    dt = parse_timestamp(value)
    if not dt:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).strftime("%d %b %Y %H:%M UTC")


def sign(value: float) -> str:
    return f"+{value:,.2f}" if value >= 0 else f"{value:,.2f}"


def sign_pct(value: float) -> str:
    return f"+{value:.2f}%" if value >= 0 else f"{value:.2f}%"


def safe_round(value, digits=2):
    try:
        return round(float(value), digits)
    except Exception:
        return 0.0


# ── Market snapshot (parallelized) ───────────────────────────────────────────

def _fetch_one_quote(ticker: str, label: str, region: str) -> Optional[Dict]:
    """Fetch a single Yahoo Finance quote. Returns None on any failure."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(ticker)}?interval=1d&range=5d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read())
    except Exception:
        return None

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return None

    chart = result[0]
    meta  = chart.get("meta") or {}
    indicator_rows = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    closes = [v for v in indicator_rows.get("close", []) if v is not None]

    price = meta.get("regularMarketPrice")
    if price is None and closes:
        price = closes[-1]
    prev = meta.get("previousClose")
    if prev is None and len(closes) >= 2:
        prev = closes[-2]
    elif prev is None and closes:
        prev = closes[-1]

    return {"price": price, "previous_close": prev, "currency": meta.get("currency", "")}


def fetch_market_snapshot() -> List[Dict]:
    """
    FIX: Parallelized with ThreadPoolExecutor (was sequential).
    On a cold CI runner sequential calls took 30-50 s and occasionally timed out.
    Concurrent execution reduces wall-clock time to ~max(individual_timeout).
    """
    rows: List[Dict] = []

    def _worker(args: Tuple) -> Optional[Dict]:
        ticker, label, region = args
        quote = _fetch_one_quote(ticker, label, region)
        if not quote:
            return None
        price = quote.get("price")
        prev  = quote.get("previous_close") or price
        chg   = (price - prev) if price is not None and prev is not None else 0.0
        chg_pct = ((chg / prev) * 100) if prev else 0.0
        return {
            "label":      label,
            "ticker":     ticker,
            "region":     region,
            "price":      safe_round(price),
            "currency":   quote.get("currency", ""),
            "change":     safe_round(chg),
            "change_pct": safe_round(chg_pct),
            "change_str": sign_pct(safe_round(chg_pct)),
            "direction":  "up" if safe_round(chg_pct) >= 0 else "down",
        }

    with ThreadPoolExecutor(max_workers=len(MARKET_TICKERS)) as executor:
        futures = {executor.submit(_worker, t): t for t in MARKET_TICKERS}
        # Preserve original ticker ordering in the output
        ordered: Dict[str, Optional[Dict]] = {}
        for future in as_completed(futures):
            ticker, label, region = futures[future]
            try:
                ordered[ticker] = future.result()
            except Exception:
                ordered[ticker] = None

    for ticker, label, region in MARKET_TICKERS:
        result = ordered.get(ticker)
        if result:
            rows.append(result)

    return rows


def infer_vix_regime(vix_value):
    if vix_value is None:
        return "Unknown"
    if vix_value < 15:
        return "NORMAL"
    if vix_value < 25:
        return "ELEVATED"
    if vix_value < 35:
        return "HIGH"
    return "EXTREME"


def calc_metrics(portfolio, usd_inr_rate=83.5):
    """Compute portfolio metrics and output everything in USD."""
    positions     = portfolio.get("open_positions", [])
    total_invested = sum(pos.get("invested_inr", 0) for pos in positions)
    market_value  = sum(
        pos.get("current_price", pos.get("entry_price", 0)) * pos.get("units", 0)
        for pos in positions
    )
    cash      = portfolio.get("cash_inr", 0)
    reserve   = portfolio.get("monthly_reserve_inr", 0)
    deposited = portfolio.get("total_deposited", portfolio.get("total_deposited_inr", total_invested + cash))
    total     = market_value + cash + reserve
    unrealised = market_value - total_invested
    closed_realised = sum(trade.get("realised_pnl", 0) for trade in portfolio.get("closed_trades", []))
    partial_realised = portfolio.get("partial_realised_pnl_total", 0)
    realised  = closed_realised + partial_realised

    # Sanity check: total_deposited should be roughly (total - unrealised - realised).
    # If it is far below that figure it was almost certainly stored in the wrong currency
    # (e.g. raw USD instead of INR), so recompute it from the actual portfolio data.
    expected_deposited = total - unrealised - realised
    if deposited > 0 and expected_deposited > 0 and deposited < expected_deposited * 0.5:
        deposited = expected_deposited

    change_raw = ((total - deposited) / deposited * 100) if deposited > 0 else 0

    portfolio_peak = portfolio.get("portfolio_peak", total)
    if portfolio_peak < total:
        portfolio_peak = total
    drawdown_now = ((portfolio_peak - total) / portfolio_peak * 100) if portfolio_peak else 0
    max_drawdown = max(portfolio.get("max_drawdown_pct", 0), drawdown_now)

    r = usd_inr_rate  # convert all monetary values from INR to USD
    return {
        "portfolio_value":   safe_round(total / r),
        "total_deposited":   safe_round(deposited / r),
        "cash":              safe_round(cash / r),
        "monthly_reserve":   safe_round(reserve / r),
        "market_value":      safe_round(market_value / r),
        "total_invested":    safe_round(total_invested / r),
        "unrealised_pnl":    safe_round(unrealised / r),
        "unrealised_str":    sign(unrealised / r),
        "realised_pnl":      safe_round(realised / r),
        "realised_str":      sign(realised / r),
        "change":            sign_pct(change_raw),
        "change_raw":        safe_round(change_raw),
        "closed_trades":     len(portfolio.get("closed_trades", [])),
        "partial_realised_pnl": safe_round(partial_realised / r),
        "portfolio_peak":    safe_round(portfolio_peak / r),
        "drawdown_now_pct":  safe_round(drawdown_now),
        "max_drawdown_pct":  safe_round(max_drawdown),
    }


def days_held(entry_date) -> int:
    dt = parse_timestamp(entry_date)
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return max((datetime.datetime.now(datetime.timezone.utc) - dt).days, 0)


def build_positions(positions, usd_inr_rate=83.5):
    """Build position rows with all monetary values in USD."""
    r = usd_inr_rate
    rows = []
    for pos in positions:
        entry   = safe_round(pos.get("entry_price", 0), 4)
        current = safe_round(pos.get("current_price", pos.get("entry_price", 0)), 4)
        units   = safe_round(pos.get("units", 0), 6)
        invested = safe_round(pos.get("invested_inr", entry * units))
        pnl     = safe_round((current - entry) * units)
        pnl_pct = safe_round(((current - entry) / entry) * 100) if entry else 0.0
        peak_price = safe_round(pos.get("peak_price", max(current, entry)), 4)
        hard_stop  = entry * (1 - HARD_STOP_PCT)
        trailing_active = (
            peak_price >= entry * (1 + TRAIL_ACTIVATION_PCT) or pos.get("half_exited", False)
        )
        trail_stop = pos.get("trail_stop")
        if trail_stop is None:
            trail_stop = max(hard_stop, peak_price * (1 - TRAILING_STOP_PCT)) if trailing_active else hard_stop
        trail_stop  = safe_round(trail_stop, 4)
        dist_to_trail = safe_round(((current - trail_stop) / current) * 100) if current else 0.0

        rows.append({
            "trade_id":          pos.get("trade_id", ""),
            "ticker":            pos.get("ticker", ""),
            "etf_name":          pos.get("etf_name", ""),
            "sector":            pos.get("sector", ""),
            "platform":          pos.get("platform", ""),
            "exchange":          pos.get("exchange", ""),
            "entry":             safe_round(entry / r),
            "current":           safe_round(current / r),
            "peak_price":        safe_round(peak_price / r),
            "trail_stop":        safe_round(trail_stop / r),
            "dist_to_trail_pct": safe_round(dist_to_trail),
            "units":             safe_round(units, 6),
            "invested":          safe_round(invested / r),
            "pnl":               safe_round(pnl / r),
            "pnl_str":           sign(pnl / r),
            "pnl_pct":           pnl_pct,
            "pnl_pct_str":       sign_pct(pnl_pct),
            "confidence":        pos.get("confidence", 0),
            "severity":          pos.get("severity", ""),
            "days_held":         days_held(pos.get("entry_date")),
            "half_exited":       bool(pos.get("half_exited", False)),
        })
    return rows


def build_closed(closed_trades, usd_inr_rate=83.5):
    """Build closed trade rows with all monetary values in USD."""
    r = usd_inr_rate
    rows = []
    for trade in closed_trades:
        pnl = safe_round(trade.get("realised_pnl", 0) / r)
        pct = safe_round(trade.get("realised_pnl_pct", 0))
        rows.append({
            "trade_id":    trade.get("trade_id", ""),
            "ticker":      trade.get("ticker", ""),
            "etf_name":    trade.get("etf_name", ""),
            "platform":    trade.get("platform", ""),
            "exchange":    trade.get("exchange", ""),
            "entry":       safe_round(trade.get("entry_price", 0) / r),
            "exit":        safe_round(trade.get("exit_price", 0) / r),
            "pnl":         pnl,
            "pnl_str":     sign(pnl),
            "pnl_pct":     pct,
            "pnl_pct_str": sign_pct(pct),
            "days_held":   trade.get("days_held", 0),
            "exit_reason": trade.get("exit_reason", ""),
            "winner":      pnl > 0,
        })
    return rows


def summarise_trade(trade):
    if trade is None:
        return None
    pct = safe_round(trade.get("realised_pnl_pct", 0))
    return {
        "ticker":      trade.get("ticker", "-"),
        "etf_name":    trade.get("etf_name", "-"),
        "pnl_pct":     pct,
        "pnl_pct_str": sign_pct(pct),
        "exit_reason": trade.get("exit_reason", "-"),
        "days_held":   trade.get("days_held", 0),
    }


def build_track(portfolio):
    closed  = portfolio.get("closed_trades", [])
    winners = [t for t in closed if t.get("realised_pnl", 0) > 0]
    losers  = [t for t in closed if t.get("realised_pnl", 0) < 0]
    returns = [safe_round(t.get("realised_pnl_pct", 0)) for t in closed]

    avg_win  = safe_round(sum(t.get("realised_pnl_pct", 0) for t in winners) / len(winners)) if winners else 0.0
    avg_loss = safe_round(sum(t.get("realised_pnl_pct", 0) for t in losers) / len(losers)) if losers else 0.0

    profit_sum = sum(t.get("realised_pnl", 0) for t in winners)
    loss_sum   = abs(sum(t.get("realised_pnl", 0) for t in losers))
    if profit_sum > 0 and loss_sum == 0:
        profit_factor = 99.0
    elif loss_sum > 0:
        profit_factor = profit_sum / loss_sum
    else:
        profit_factor = 0.0

    expectancy = safe_round(sum(returns) / len(returns)) if returns else 0.0
    if len(returns) >= 2:
        std_dev      = statistics.pstdev(returns)
        sharpe_proxy = (statistics.mean(returns) / std_dev) if std_dev else 0.0
    else:
        sharpe_proxy = 0.0

    best  = max(closed, key=lambda t: t.get("realised_pnl_pct", 0), default=None)
    worst = min(closed, key=lambda t: t.get("realised_pnl_pct", 0), default=None)

    return {
        "total_trades":  len(closed),
        "winners":       len(winners),
        "losers":        len(losers),
        "win_rate":      safe_round((len(winners) / len(closed) * 100) if closed else 0.0, 1),
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "profit_factor": safe_round(profit_factor),
        "expectancy":    expectancy,
        "sharpe_proxy":  safe_round(sharpe_proxy),
        "best":          summarise_trade(best),
        "worst":         summarise_trade(worst),
    }


def build_alloc(positions, cash):
    total = sum(pos["current"] * pos["units"] for pos in positions) + cash
    if total <= 0:
        return {"labels": [], "values": []}
    labels = [pos["ticker"] for pos in positions] + ["CASH"]
    values = [safe_round(pos["current"] * pos["units"] / total * 100, 1) for pos in positions]
    values.append(safe_round(cash / total * 100, 1))
    return {"labels": labels, "values": values}


def build_pnl(positions):
    return {
        "labels": [pos["ticker"] for pos in positions],
        "values": [safe_round(pos["pnl"]) for pos in positions],
    }


def build_conf(state):
    rows = []
    for key, signal in state.items():
        rows.append({
            "symbol": signal.get("sector_label") or clean_label(key),
            "score":  safe_round(signal.get("confidence", 0), 1),
        })
    return sorted(rows, key=lambda item: item["score"], reverse=True)


def extract_tickers(bucket):
    tickers = []
    for item in bucket or []:
        ticker = item.get("ticker")
        if ticker:
            tickers.append(ticker)
    return tickers


def extract_ranked_tickers(recs: Dict, limit: int = 4) -> List[str]:
    ranked = recs.get("top_etfs") or recs.get("ranked") or []
    if ranked:
        return extract_tickers(ranked)[:limit]

    combined = []
    combined.extend(recs.get("global", []))
    combined.extend(recs.get("india", []))
    return extract_tickers(combined)[:limit]


def extract_primary_ticker(recs: Dict) -> str:
    primary = recs.get("primary") or {}
    ticker = primary.get("ticker")
    if ticker:
        return ticker
    ranked = extract_ranked_tickers(recs, limit=1)
    return ranked[0] if ranked else ""


def extract_market_labels(recs: Dict) -> List[str]:
    labels = list((recs.get("regional_alternatives") or {}).keys())
    if labels:
        return labels[:3]

    fallback = []
    if recs.get("global"):
        fallback.append("International-listed")
    if recs.get("india"):
        fallback.append("India-listed")
    return fallback[:3]


def _breakdown_has_data(breakdown: Dict) -> bool:
    """Return True if the breakdown contains at least one non-zero component."""
    return any(v != 0 for v in breakdown.values())


def build_signal_cards(state):
    """
    FIX: legacy state records (recorded before breakdown tracking was added)
    have all-zero score components.  We now mark these explicitly so the
    dashboard can display a 'legacy record' notice instead of zeroed bars,
    which previously looked like a broken signal.
    """
    cards = []
    for key, signal in state.items():
        label      = signal.get("sector_label") or clean_label(key)
        confidence = safe_round(signal.get("confidence", 0))
        severity   = signal.get("severity") or (
            "CRITICAL" if confidence >= 80 else
            "HIGH"     if confidence >= 72 else
            "MEDIUM"
        )
        headlines  = signal.get("top_headlines") or []
        regions    = signal.get("regions") or []
        sources    = signal.get("sources") or []
        breakdown  = signal.get("confidence_breakdown") or {}
        recs       = signal.get("etf_recommendations") or {
            "selection_method": "global-ranked",
            "primary": None,
            "ranked": [],
            "regional_alternatives": {},
            "india": [],
            "global": [],
        }
        is_legacy  = not _breakdown_has_data(breakdown)

        cards.append({
            "sector_key":    key,
            "sector_label":  label,
            "confidence":    confidence,
            "severity":      severity,
            "direction":     signal.get("direction", "NEUTRAL"),
            "direction_score": safe_round(signal.get("direction_score", 0), 2),
            "ml_sentiment_label": signal.get("ml_sentiment_label", "NEUTRAL"),
            "ml_sentiment_score": safe_round(signal.get("ml_sentiment_score", 0), 4),
            "ml_sentiment_mode": signal.get("ml_sentiment_mode", "rules-only"),
            "article_count": signal.get("article_count", 0),
            "latest_at":     format_timestamp(signal.get("latest_ts") or signal.get("sent_at")),
            "headline":      (
                headlines[0] if headlines
                else f"{label} — active signal (legacy record, no headline stored)"
                if is_legacy
                else f"{label} remains active in the signal book."
            ),
            "regions":       regions[:4],
            "sources":       sources[:4],
            "primary_etf":   extract_primary_ticker(recs),
            "top_etfs":      extract_ranked_tickers(recs)[:4],
            "access_markets": extract_market_labels(recs),
            "india_etfs":    extract_tickers(recs.get("india"))[:3],
            "global_etfs":   extract_tickers(recs.get("global"))[:4],
            "is_legacy":     is_legacy,
            "breakdown": {
                "signal_strength":       safe_round(breakdown.get("signal_strength", 0), 1),
                "volume_confirmation":   safe_round(breakdown.get("volume_confirmation", 0), 1),
                "source_diversity":      safe_round(breakdown.get("source_diversity", 0), 1),
                "recency":               safe_round(breakdown.get("recency", 0), 1),
                "geopolitical_severity": safe_round(breakdown.get("geopolitical_severity", 0), 1),
            },
        })

    return sorted(cards, key=lambda item: item["confidence"], reverse=True)


def build_articles(signal_cards):
    items = []
    for signal in signal_cards:
        direction = signal.get("direction", "NEUTRAL")
        if direction == "BULLISH":
            tag = "tag-bull"
            badge = "Bullish"
        elif direction == "BEARISH":
            tag = "tag-bear"
            badge = "Bearish"
        else:
            tag = "tag-neu"
            badge = "Neutral"
        legacy_note = " [legacy]" if signal.get("is_legacy") else ""
        items.append({
            "tag":   tag,
            "label": badge,
            "text": (
                f"{signal['sector_label']} - {signal['article_count']} articles - "
                f"{signal['severity']} / {direction}{legacy_note} - {signal['headline']}"
            ),
        })
    return items


def _convert_aladdin_to_usd(aladdin_risk, usd_inr_rate):
    """Convert Aladdin risk engine monetary outputs from INR to USD."""
    r = usd_inr_rate
    # Stress test scenario impacts
    for scenario_data in (aladdin_risk.get("stress_test", {}).get("scenarios", {}) or {}).values():
        if "total_impact" in scenario_data:
            scenario_data["total_impact"] = safe_round(scenario_data["total_impact"] / r)
        for pi in scenario_data.get("position_impacts", []):
            if "impact" in pi:
                pi["impact"] = safe_round(pi["impact"] / r)
    # Rebalance alert amounts
    for alert in (aladdin_risk.get("rebalance", {}).get("alerts", []) or []):
        if "amount" in alert:
            alert["amount"] = safe_round(alert["amount"] / r)


def build_risk_controls(metrics, positions, market_snapshot):
    vix_row   = next((row for row in market_snapshot if row["ticker"] == "^VIX"), None)
    vix_value = vix_row["price"] if vix_row else None

    sector_rows  = []
    portfolio_value = metrics["portfolio_value"]
    for pos in positions:
        current_value = pos["current"] * pos["units"]
        sector_rows.append((pos["sector"], current_value))

    sector_totals: Dict[str, float] = {}
    for sector, value in sector_rows:
        sector_totals[sector] = sector_totals.get(sector, 0.0) + value

    concentration = []
    for sector, value in sorted(sector_totals.items(), key=lambda item: item[1], reverse=True):
        weight = safe_round((value / portfolio_value) * 100 if portfolio_value else 0.0, 1)
        concentration.append({
            "sector": sector,
            "weight": weight,
            "at_cap": weight >= SECTOR_CAP_PCT,
        })

    drawdown = metrics.get("drawdown_now_pct", 0.0)
    return {
        "circuit_breaker_active":  drawdown >= CIRCUIT_BREAKER_DRAWDOWN_PCT,
        "drawdown_from_peak_pct":  safe_round(drawdown),
        "portfolio_peak":          metrics.get("portfolio_peak", 0.0),
        "vix":                     safe_round(vix_value) if vix_value is not None else None,
        "vix_regime":              infer_vix_regime(vix_value),
        "sector_concentration":    concentration,
        "max_drawdown_pct":        metrics.get("max_drawdown_pct", 0.0),
        "sector_cap_pct":          SECTOR_CAP_PCT,
        "trailing_stop_pct":       int(TRAILING_STOP_PCT * 100),
        "hard_stop_pct":           int(HARD_STOP_PCT * 100),
        "partial_profit_pct":      int(PARTIAL_PROFIT_PCT * 100),
    }


def build_logs(portfolio, state, metrics):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    logs = [f"{now} [INFO] AZALYST - status.json generated"]
    logs.append(
        f"{now} [INFO] PORTFOLIO - NAV USD {metrics['portfolio_value']:,.2f} | "
        f"Return {metrics['change']}"
    )
    if state:
        logs.append(f"{now} [INFO] SIGNALS - {len(state)} active signal buckets in state")
    positions = portfolio.get("open_positions", [])
    if positions:
        logs.append(f"{now} [INFO] TRADER - Open positions: {', '.join(p['ticker'] for p in positions)}")
    closed = portfolio.get("closed_trades", [])
    if closed:
        logs.append(f"{now} [INFO] TRADER - Closed trades: {len(closed)}")
    if portfolio.get("partial_realised_pnl_total", 0):
        logs.append(
            f"{now} [INFO] RISK - Partial profits realised: USD "
            f"{portfolio.get('partial_realised_pnl_total', 0):,.2f}"
        )
    if metrics.get("drawdown_now_pct", 0) >= CIRCUIT_BREAKER_DRAWDOWN_PCT:
        logs.append(f"{now} [WARN] RISK - Circuit breaker threshold reached")
    return logs


def minimal_status(now_str):
    return {
        "portfolio_value":  0,
        "total_deposited":  0,
        "cash":             0,
        "monthly_reserve":  0,
        "market_value":     0,
        "total_invested":   0,
        "unrealised_pnl":   0,
        "unrealised_str":   "+0.00",
        "realised_pnl":     0,
        "realised_str":     "+0.00",
        "change":           "+0.00%",
        "change_raw":       0,
        "closed_trades":    0,
        "usd_inr_rate":     83.5,
        "positions":        [],
        "closed_trades_list": [],
        "track_record": {
            "total_trades": 0, "winners": 0, "losers": 0, "win_rate": 0,
            "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
            "expectancy": 0, "sharpe_proxy": 0, "best": None, "worst": None,
        },
        "confidence_threshold": 62,
        "allocation":    {"labels": [], "values": []},
        "pnl":           {"labels": [], "values": []},
        "confidence":    [],
        "signals":       [],
        "articles":      [],
        "market_snapshot": [],
        "risk_controls": {
            "circuit_breaker_active": False,
            "drawdown_from_peak_pct": 0,
            "portfolio_peak":         0,
            "vix":                    None,
            "vix_regime":             "Unknown",
            "sector_concentration":   [],
            "max_drawdown_pct":       0,
            "sector_cap_pct":         SECTOR_CAP_PCT,
            "trailing_stop_pct":      int(TRAILING_STOP_PCT * 100),
            "hard_stop_pct":          int(HARD_STOP_PCT * 100),
            "partial_profit_pct":     int(PARTIAL_PROFIT_PCT * 100),
        },
        "aladdin_risk": {
            "correlation": {"matrix": {}, "tickers": [], "max_corr": 0, "max_corr_pair": [], "status": "OK"},
            "volatility": {"per_ticker": {}, "portfolio_avg_vol_pct": 0, "target_vol_pct": 15},
            "benchmark": {"benchmark_return_pct": 0, "benchmark_price_start": 0, "benchmark_price_now": 0, "benchmark_ticker": "SPY", "portfolio_return_pct": 0, "alpha": 0},
            "rebalance": {"alerts": [], "drift_threshold_pct": 5, "needs_rebalance": False},
            "stress_test": {"scenarios": {}, "worst_scenario": "", "worst_loss_pct": 0},
        },
        "logs":          [f"{now_str} [WARN] No data available"],
        "generated_at":  now_str,
    }


def generate_status():
    portfolio = load_json(PORTFOLIO_FILE)
    state     = load_json(STATE_FILE)
    now_str   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    if not portfolio and not state:
        output = minimal_status(now_str)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2)
        print(f"Written minimal dashboard status -> {OUTPUT_FILE}")
        return

    # Fetch live USD/INR rate FIRST — needed for INR→USD conversion
    usd_inr_rate = None
    try:
        from paper_trader import fetch_usd_to_inr
        usd_inr_rate = fetch_usd_to_inr()
    except Exception:
        usd_inr_rate = 83.5  # fallback

    market_snapshot = fetch_market_snapshot()
    metrics         = calc_metrics(portfolio, usd_inr_rate)
    positions       = build_positions(portfolio.get("open_positions", []), usd_inr_rate)
    signal_cards    = build_signal_cards(state)

    # ── Aladdin Risk Engine ──────────────────────────────────────────────
    aladdin_risk = {}
    if risk_engine:
        try:
            portfolio_return_pct = metrics.get("change_raw", 0.0)
            aladdin_risk = risk_engine.generate_risk_report(
                portfolio,
                metrics["portfolio_value"] * usd_inr_rate,  # engine expects INR
                portfolio_return_pct,
            )
            # Convert Aladdin monetary outputs from INR to USD
            _convert_aladdin_to_usd(aladdin_risk, usd_inr_rate)
        except Exception as exc:
            print(f"WARNING: risk_engine failed: {exc}")
            aladdin_risk = risk_engine._empty_report() if risk_engine else {}

    status = {
        **metrics,
        "usd_inr_rate":       safe_round(usd_inr_rate, 4),
        "positions":          positions,
        "closed_trades_list": build_closed(portfolio.get("closed_trades", []), usd_inr_rate),
        "track_record":       build_track(portfolio),
        "confidence_threshold": 62,
        "allocation":  build_alloc(positions, metrics["cash"] + metrics.get("monthly_reserve", 0)),
        "pnl":         build_pnl(positions),
        "confidence":  build_conf(state),
        "signals":     signal_cards,
        "articles":    build_articles(signal_cards),
        "market_snapshot": market_snapshot,
        "risk_controls":   build_risk_controls(metrics, positions, market_snapshot),
        "aladdin_risk":    aladdin_risk,
        "logs":            build_logs(portfolio, state, metrics),
        "generated_at":    now_str,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2)

    print(f"status.json written -> {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_status()
