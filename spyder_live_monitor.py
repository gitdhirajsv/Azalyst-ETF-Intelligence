"""
spyder_live_monitor.py

Institutional-grade live dashboard for Azalyst ETF Intelligence.
Runs inside Spyder with zero external dependencies beyond matplotlib.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

def _choose_backend() -> str:
    env_backend = os.environ.get("AZALYST_MONITOR_BACKEND")
    force_inline = os.environ.get("AZALYST_MONITOR_INLINE", "").strip() == "1"
    default_backend = "TkAgg"  # windowed and responsive for Spyder
    if force_inline:
        backend = "module://matplotlib_inline.backend_inline"
    else:
        backend = env_backend or default_backend
    try:
        matplotlib.use(backend, force=False)
        return matplotlib.get_backend()
    except Exception:
        matplotlib.use("Agg")
        return "Agg"

BACKEND = _choose_backend().lower()

import matplotlib.pyplot as plt
if "agg" not in BACKEND:
    plt.ion()
from IPython.display import clear_output

# Ensure UTF-8 output even on Windows consoles
import sys
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "azalyst.log"
STATE_PATH = ROOT / "azalyst_state.json"
PORTFOLIO_PATH = ROOT / "azalyst_portfolio.json"

DEFAULT_INTERVAL = 30
DEFAULT_THRESHOLD = 62
DEFAULT_COOLDOWN_HOURS = 4
REFRESH_SECONDS = int(os.environ.get("AZALYST_MONITOR_REFRESH", "300"))  # default 5 minutes
CONSOLE_WIDTH = 90
LOG_LINES = 15
FIG = None
PRICE_CACHE: Dict[str, Tuple[float, float]] = {}  # symbol -> (price_in_inr, timestamp)
PRICE_TTL = 120  # seconds
ORANGE = "#f97316"
BLUE = "#2563eb"
GREEN = "#22c55e"
RED = "#ef4444"
GRAY_DARK = "#111827"
GRAY_LIGHT = "#e5e7eb"

matplotlib.rcParams.update(
    {
        "toolbar": "None",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.edgecolor": GRAY_LIGHT,
        "axes.labelcolor": GRAY_DARK,
        "axes.titleweight": "bold",
        "axes.titlesize": 12,
        "figure.titlesize": 14,
        "grid.color": GRAY_LIGHT,
        "grid.alpha": 0.6,
        "xtick.color": GRAY_DARK,
        "ytick.color": GRAY_DARK,
        "text.color": GRAY_DARK,
        "font.family": "monospace",
    }
)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------
def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def tail_lines(path: Path, count: int) -> List[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-count:]
    except Exception:
        return []


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fmt_inr(value: float) -> str:
    try:
        return f"INR {value:,.0f}"
    except Exception:
        return "INR 0"


def fmt_pct(value: float) -> str:
    try:
        return f"{value:+.2f}%"
    except Exception:
        return "0.00%"


def bar(value: float, max_value: float, length: int) -> str:
    if max_value <= 0:
        return "░" * length
    ratio = max(0.0, min(1.0, value / max_value))
    filled = min(length, max(0, int(round(ratio * length))))
    return "█" * filled + "░" * (length - filled)


def short(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def fetch_json(url: str, timeout: float = 6.0) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def fetch_usd_inr(previous: Optional[float]) -> Optional[float]:
    data = fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X?range=1d&interval=5m")
    if not data:
        return previous
    try:
        result = data["chart"]["result"][0]
        price = result["meta"].get("regularMarketPrice")
        if price:
            return float(price)
    except Exception:
        pass
    return previous


def ticker_symbol(ticker: str, exchange: Optional[str]) -> str:
    upper = (ticker or "").upper()
    if upper.endswith((".NS", ".BO")):
        return upper
    if exchange and exchange.upper().startswith(("NSE", "BSE")):
        return upper + ".NS"
    return upper


def fetch_price_in_inr(ticker: str, exchange: Optional[str], usd_inr: Optional[float], fallback: Optional[float]) -> Optional[float]:
    symbol = ticker_symbol(ticker, exchange)
    now = time.time()
    if symbol in PRICE_CACHE:
        cached_price, ts = PRICE_CACHE[symbol]
        if now - ts < PRICE_TTL:
            return cached_price

    data = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=5m")
    price: Optional[float] = None
    if data:
        try:
            result = data["chart"]["result"][0]
            meta = result["meta"]
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
        except Exception:
            price = None

    if price is None:
        return fallback

    if symbol.endswith((".NS", ".BO")):
        val = float(price)
    else:
        val = float(price) * float(usd_inr) if usd_inr else float(price)

    PRICE_CACHE[symbol] = (val, now)
    return val


# ---------------------------------------------------------------------------
# Data classes for clarity
# ---------------------------------------------------------------------------
@dataclass
class PositionView:
    trade_id: str
    ticker: str
    sector: str
    entry_price: float
    live_price: float
    units: float
    invested_inr: float
    unrealised_pnl: float
    return_pct: float
    confidence: float


@dataclass
class PortfolioSnapshot:
    portfolio_value: float
    total_deposited: float
    overall_return_pct: float
    cash: float
    capital_deployed: float
    market_value: float
    unrealised_pnl: float
    realised_pnl: float
    open_count: int
    closed_count: int
    positions: List[PositionView]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def build_portfolio_snapshot(portfolio: Dict[str, Any], usd_inr: Optional[float]) -> PortfolioSnapshot:
    open_positions = portfolio.get("open_positions") or []
    closed_trades = portfolio.get("closed_trades") or []

    positions: List[PositionView] = []
    market_value = 0.0
    unrealised_pnl = 0.0
    capital_deployed = 0.0

    price_cache: Dict[str, float] = {}

    for pos in open_positions:
        ticker = pos.get("ticker", "").strip()
        exchange = pos.get("exchange")
        units = float(pos.get("units", 0) or 0)
        entry_price = float(pos.get("entry_price", 0) or 0)
        invested = float(pos.get("invested_inr", entry_price * units))
        capital_deployed += invested

        cache_key = ticker_symbol(ticker, exchange)
        live_price = price_cache.get(cache_key)
        if live_price is None:
            live_price = fetch_price_in_inr(
                ticker=ticker,
                exchange=exchange,
                usd_inr=usd_inr,
                fallback=pos.get("current_price"),
            )
            if live_price is not None:
                price_cache[cache_key] = live_price

        if live_price is None:
            live_price = entry_price

        market_val = live_price * units
        pnl = (live_price - entry_price) * units
        pnl_pct = (pnl / invested * 100) if invested else 0.0

        market_value += market_val
        unrealised_pnl += pnl

        positions.append(
            PositionView(
                trade_id=str(pos.get("trade_id", "")),
                ticker=ticker,
                sector=pos.get("sector", "") or pos.get("etf_name", ""),
                entry_price=entry_price,
                live_price=live_price,
                units=units,
                invested_inr=invested,
                unrealised_pnl=pnl,
                return_pct=pnl_pct,
                confidence=float(pos.get("confidence", 0) or 0),
            )
        )

    realised_pnl = sum(float(ct.get("realised_pnl", 0) or 0) for ct in closed_trades)
    cash = float(portfolio.get("cash_inr", 0) or 0)
    total_deposited = float(portfolio.get("total_deposited", 0) or 0)

    portfolio_value = cash + market_value
    overall_return_pct = (
        ((portfolio_value + realised_pnl) - total_deposited) / total_deposited * 100
        if total_deposited
        else 0.0
    )

    return PortfolioSnapshot(
        portfolio_value=portfolio_value,
        total_deposited=total_deposited,
        overall_return_pct=overall_return_pct,
        cash=cash,
        capital_deployed=capital_deployed,
        market_value=market_value,
        unrealised_pnl=unrealised_pnl,
        realised_pnl=realised_pnl,
        open_count=len(open_positions),
        closed_count=len(closed_trades),
        positions=positions,
    )


def build_sector_rows(state: Dict[str, Any], cooldown_hours: int, threshold: float) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for key, entry in (state or {}).items():
        confidence = float(entry.get("confidence", 0) or 0)
        label = entry.get("sector_label") or key.replace("_", " ").title()
        article_count = int(entry.get("article_count", 0) or 0)
        sent_at = parse_dt(entry.get("sent_at"))
        status = "ACTIVE"
        if sent_at:
            age_hours = (now - sent_at).total_seconds() / 3600
            if age_hours < cooldown_hours:
                remaining = max(0.0, cooldown_hours - age_hours)
                status = f"COOLDOWN ({remaining:.1f}h)"
        if confidence < threshold:
            status = "COOLDOWN" if status.startswith("COOLDOWN") else "BELOW THRESH"

        rows.append(
            {
                "label": label,
                "confidence": confidence,
                "status": status,
                "articles": article_count,
            }
        )

    rows.sort(key=lambda r: r["confidence"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def render_console(snapshot: PortfolioSnapshot, sectors: List[Dict[str, Any]], logs: List[str], threshold: float) -> None:
    lines: List[str] = []
    divider = "─" * CONSOLE_WIDTH

    # Portfolio overview
    overview_items = [
        ("Portfolio Value", fmt_inr(snapshot.portfolio_value)),
        ("Total Deposited", fmt_inr(snapshot.total_deposited)),
        ("Overall Return", fmt_pct(snapshot.overall_return_pct)),
        ("Cash Available", fmt_inr(snapshot.cash)),
        ("Capital Deployed", fmt_inr(snapshot.capital_deployed)),
        ("Market Value", fmt_inr(snapshot.market_value)),
        ("Unrealised P&L", fmt_inr(snapshot.unrealised_pnl)),
        ("Realised P&L", fmt_inr(snapshot.realised_pnl)),
        ("Open Positions", str(snapshot.open_count)),
        ("Closed Trades", str(snapshot.closed_count)),
    ]
    lines.append("PORTFOLIO OVERVIEW".ljust(CONSOLE_WIDTH))
    col_width = CONSOLE_WIDTH // 3
    for i in range(0, len(overview_items), 3):
        row = overview_items[i : i + 3]
        formatted = [f"{label}: {value}" for label, value in row]
        padded = [short(text, col_width - 1).ljust(col_width) for text in formatted]
        lines.append("".join(padded))

    # Open positions
    lines.append(divider)
    lines.append(
        f"{'ID':<5} {'Ticker':<7} {'Sector':<22} {'Entry':>10} {'Live':>10} {'PnL':>10} {'Ret%':>7} {'Conf':<10}"
    )
    lines.append(divider)
    if snapshot.positions:
        for pos in snapshot.positions:
            lines.append(
                f"{short(pos.trade_id,4):<5} "
                f"{short(pos.ticker,6):<7} "
                f"{short(pos.sector,22):<22} "
                f"{pos.entry_price:>10.2f} "
                f"{pos.live_price:>10.2f} "
                f"{pos.unrealised_pnl:>10.2f} "
                f"{pos.return_pct:>7.2f} "
                f"{bar(pos.confidence, 100, 10)}"
            )
    else:
        lines.append("No open positions.".ljust(CONSOLE_WIDTH))

    # Signals intelligence
    lines.append(divider)
    lines.append(
        f"{'Sector':<32} {'Conf':>6} {'Status':<18} {'Articles':>8} {'Bar':<15}"
    )
    lines.append(divider)
    if sectors:
        for row in sectors:
            lines.append(
                f"{short(row['label'],32):<32} "
                f"{row['confidence']:>6.1f} "
                f"{short(row['status'],18):<18} "
                f"{row['articles']:>8d} "
                f"{bar(row['confidence'], 100, 15)}"
            )
    else:
        lines.append("No sector signals loaded.".ljust(CONSOLE_WIDTH))

    # Logs
    lines.append(divider)
    lines.append("RECENT LOGS".ljust(CONSOLE_WIDTH))
    lines.append(divider)
    if logs:
        for line in logs[-LOG_LINES:]:
            lines.append(short(line.strip(), CONSOLE_WIDTH))
    else:
        lines.append("Log file not found or empty.".ljust(CONSOLE_WIDTH))

    print("\n".join(lines))


def build_dashboard_figure(
    snapshot: PortfolioSnapshot,
    usd_inr: Optional[float],
    threshold: float,
    log_lines: List[str],
) -> "matplotlib.figure.Figure":
    global FIG
    if FIG is None or not plt.fignum_exists(FIG.number):
        FIG = plt.figure(figsize=(12, 7))
    else:
        FIG.clf()
    fig = FIG
    gs = fig.add_gridspec(2, 3, width_ratios=[1, 1, 1], height_ratios=[1, 1], wspace=0.45, hspace=0.4)

    # KPI cards (top left)
    ax_kpi = fig.add_subplot(gs[0, 0])
    ax_kpi.axis("off")
    kpis = [
        ("Portfolio Value", fmt_inr(snapshot.portfolio_value)),
        ("Total Deposited", fmt_inr(snapshot.total_deposited)),
        ("Overall Return", fmt_pct(snapshot.overall_return_pct)),
        ("Unrealised P&L", fmt_inr(snapshot.unrealised_pnl)),
        ("Cash Available", fmt_inr(snapshot.cash)),
        ("Market Value", fmt_inr(snapshot.market_value)),
        ("Open Positions", str(snapshot.open_count)),
        ("Closed Trades", str(snapshot.closed_count)),
    ]
    for idx, (label, value) in enumerate(kpis):
        y = 1 - (idx * 0.11)
        ax_kpi.text(0.02, y, label, fontsize=9, color="#94a3b8", transform=ax_kpi.transAxes)
        ax_kpi.text(0.55, y, value, fontsize=11, fontweight="bold", transform=ax_kpi.transAxes)

    # Allocation pie (top middle)
    ax_pie = fig.add_subplot(gs[0, 1])
    values = [p.live_price * p.units for p in snapshot.positions]
    labels = [p.ticker for p in snapshot.positions]
    if snapshot.cash > 0:
        values.append(snapshot.cash)
        labels.append("CASH")
    if values and sum(values) > 0:
        colors = [ORANGE, BLUE, "#0ea5e9", "#fcd34d", "#a855f7", "#10b981", "#f97316", "#94a3b8"]
        ax_pie.pie(values, labels=labels, autopct="%1.0f%%", colors=colors[: len(values)], textprops={"color": GRAY_DARK})
    ax_pie.set_title("Allocation", pad=10)

    # Confidence per ticker (top right)
    ax_conf = fig.add_subplot(gs[0, 2])
    confs = [p.confidence for p in snapshot.positions] or [0]
    conf_labels = [p.ticker for p in snapshot.positions] or ["-"]
    ax_conf.barh(conf_labels, confs, color=ORANGE)
    ax_conf.axvline(threshold, color="#9ca3af", linestyle="--", linewidth=1, label=f"Threshold {threshold}")
    ax_conf.set_xlim(0, 100)
    ax_conf.set_xlabel("Confidence")
    ax_conf.set_title("Position Confidence")
    ax_conf.legend(loc="lower right", fontsize=8)
    for i, v in enumerate(confs):
        ax_conf.text(v + 1, i, f"{v:.1f}", va="center", fontsize=8)

    # Unrealised P&L per position (bottom left, span 1 col)
    ax_pnl = fig.add_subplot(gs[1, 0])
    tickers = [p.ticker for p in snapshot.positions] or ["-"]
    pnls = [p.unrealised_pnl for p in snapshot.positions] or [0]
    colors = [GREEN if v > 0 else RED if v < 0 else GRAY_LIGHT for v in pnls]
    ax_pnl.bar(tickers, pnls, color=colors)
    ax_pnl.set_title("Unrealised P&L per Position (INR)")
    ax_pnl.axhline(0, color="#334155", linewidth=1)
    for x, val in enumerate(pnls):
        ax_pnl.text(x, val, f"{val:.0f}", ha="center", va="bottom" if val >= 0 else "top", fontsize=8)

    # Status panel (bottom middle)
    ax_status = fig.add_subplot(gs[1, 1])
    ax_status.axis("off")
    status_lines = [
        f"Run state: RUNNING",
        f"Portfolio value: {fmt_inr(snapshot.portfolio_value)}",
        f"Deposited: {fmt_inr(snapshot.total_deposited)}",
        f"Market value: {fmt_inr(snapshot.market_value)}",
        f"Cash: {fmt_inr(snapshot.cash)}",
        f"Unrealised P&L: {fmt_inr(snapshot.unrealised_pnl)}",
        f"Realised P&L: {fmt_inr(snapshot.realised_pnl)}",
        f"Open positions: {snapshot.open_count}",
        f"Closed trades: {snapshot.closed_count}",
        f"USD/INR: {usd_inr:.2f}" if usd_inr else "USD/INR: n/a",
    ]
    for i, line in enumerate(status_lines):
        ax_status.text(0.02, 1 - i * 0.11, line, fontsize=9, transform=ax_status.transAxes)

    # Log tail panel (bottom right)
    ax_log = fig.add_subplot(gs[1, 2])
    ax_log.axis("off")
    log_title = "Recent Log Tail"
    ax_log.text(0.02, 1.02, log_title, fontsize=10, fontweight="bold", transform=ax_log.transAxes)
    if log_lines:
        for i, line in enumerate(log_lines[-12:]):
            ax_log.text(0.02, 0.9 - i * 0.075, short(line, 90), fontsize=8, transform=ax_log.transAxes)
    else:
        ax_log.text(0.02, 0.8, "No log entries yet (waiting for first cycle)", fontsize=9, color="#9ca3af", transform=ax_log.transAxes)

    fig.suptitle("Azalyst ETF Intelligence - Live Monitor", fontweight="bold", color=GRAY_DARK, y=0.98)
    try:
        plt.tight_layout(rect=[0.02, 0.02, 0.98, 0.96])
    except Exception:
        plt.tight_layout()
    return fig


def render_charts(snapshot: PortfolioSnapshot, sectors: List[Dict[str, Any]], usd_inr: Optional[float], threshold: float) -> None:
    log_lines = tail_lines(LOG_PATH, LOG_LINES)
    fig = build_dashboard_figure(snapshot, usd_inr, threshold, log_lines)
    if "inline" in BACKEND:
        plt.show()
        plt.close(fig)
        return
    if "agg" not in BACKEND:
        fig.canvas.draw_idle()
        fig.canvas.flush_events()
        plt.pause(0.05)
    else:
        plt.close(fig)


def save_dashboard_image(output_path: str) -> str:
    _, threshold, _ = load_config()
    usd_inr = fetch_usd_inr(None)
    portfolio = load_json(PORTFOLIO_PATH)
    snapshot = build_portfolio_snapshot(portfolio, usd_inr)
    log_lines = tail_lines(LOG_PATH, LOG_LINES)
    fig = build_dashboard_figure(snapshot, usd_inr, threshold, log_lines)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def load_config() -> Tuple[int, float, int]:
    interval = DEFAULT_INTERVAL
    threshold = DEFAULT_THRESHOLD
    cooldown = DEFAULT_COOLDOWN_HOURS
    try:
        import config  # type: ignore

        interval = int(getattr(config, "INTERVAL", interval))
        threshold = float(getattr(config, "THRESHOLD", threshold))
        cooldown = int(getattr(config, "COOLDOWN_HOURS", cooldown))
    except Exception:
        pass
    return interval, threshold, cooldown


def main() -> None:
    _, threshold, cooldown_hours = load_config()
    usd_inr: Optional[float] = None

    while True:
        start = time.time()
        try:
            usd_inr = fetch_usd_inr(usd_inr)
            portfolio = load_json(PORTFOLIO_PATH)
            state = load_json(STATE_PATH)
            logs = tail_lines(LOG_PATH, LOG_LINES)

            snapshot = build_portfolio_snapshot(portfolio, usd_inr)
            sectors = build_sector_rows(state, cooldown_hours, threshold)

            clear_output(wait=True)
            render_console(snapshot, sectors, logs, threshold)
            render_charts(snapshot, sectors, usd_inr, threshold)
        except Exception as exc:
            clear_output(wait=True)
            print(f"Spyder monitor encountered an error: {exc}")

        elapsed = time.time() - start
        sleep_for = max(5.0, REFRESH_SECONDS - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
