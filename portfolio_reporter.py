"""
portfolio_reporter.py — AZALYST Daily Portfolio Briefing

Sends two types of Discord reports:

1. TRADE ENTRY NOTICE  — fired immediately when a position is opened
2. END OF DAY REPORT   — fired once daily at market close (scheduled)
   Shows full book: open positions with unrealised PnL, closed trades,
   cash balance, total return, win rate, track record.
"""

import logging
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional

log = logging.getLogger("azalyst.portfolio_reporter")

# Discord @mention policy:
# Only ping for actual paper-trade actions: buy entries and sell exits.
# Routine EOD/scan reports should stay quiet.
DISCORD_USER_ID = "1363959528194052118"

def _mention() -> str:
    """Return Discord mention prefix for paper-trade buy/sell alerts."""
    return f"<@{DISCORD_USER_ID}>"


def _sign(value: float) -> str:
    return f"+{value:,.2f}" if value >= 0 else f"{value:,.2f}"


def _sign_pct(value: float) -> str:
    return f"+{value:.2f}%" if value >= 0 else f"{value:.2f}%"


def _pnl_color(pnl: float) -> int:
    """Embed color based on PnL direction."""
    if pnl > 0:
        return 0x1E6B3C   # Green
    elif pnl < 0:
        return 0x922B21   # Red
    return 0x1A3A5C       # Neutral navy


class PortfolioReporter:
    """Sends portfolio status reports to Discord."""

    def __init__(self, cfg):
        self.webhook_url = cfg.DISCORD_WEBHOOK_URL
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _post(self, payload: Dict) -> bool:
        try:
            resp = self.session.post(self.webhook_url, json=payload, timeout=15)
            if resp.status_code in (200, 204):
                return True
            log.error(f"Discord returned {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            log.error(f"Discord post error: {e}")
            return False

    # ── Trade Entry Notice ────────────────────────────────────────────────────

    def send_trade_entry(self, entry: Dict, signal: Dict):
        """
        Sent immediately when a new paper position is opened.
        Clean, factual — like a trade confirmation slip.
        """
        ticker      = entry["ticker"]
        etf_name    = entry["etf_name"]
        platform    = entry["platform"]
        exchange    = entry.get("exchange", "—")
        sector      = entry["sector"]
        invested    = entry["invested_inr"]
        price       = entry["entry_price"]
        units       = entry["units"]
        confidence  = entry["confidence"]
        severity    = entry["severity"]
        trade_id    = entry["trade_id"]
        cash_left   = entry["cash_remaining"]
        headline    = (signal.get("top_headlines") or ["—"])[0]
        rate        = entry.get("usd_inr_rate", 83.5)
        price_usd   = price / rate
        invested_usd = invested / rate
        cash_usd    = cash_left / rate

        embed = {
            "title": "AZALYST PAPER PORTFOLIO  —  TRADE ENTRY",
            "description": (
                f"```\n"
                f"Trade ID         : {trade_id}\n"
                f"ETF              : {etf_name}  ({ticker})\n"
                f"Exchange         : {exchange}\n"
                f"Platform         : {platform}\n"
                f"Sector           : {sector}\n"
                f"{'─' * 44}\n"
                f"Entry Price      : ${price_usd:,.4f}\n"
                f"Units            : {units:.4f}\n"
                f"Capital Deployed : ${invested_usd:,.2f}\n"
                f"Cash Remaining   : ${cash_usd:,.2f}\n"
                f"{'─' * 44}\n"
                f"Signal Confidence: {confidence} / 100\n"
                f"Severity         : {severity}\n"
                f"Signal Driver    : {headline[:80]}\n"
                f"```\n\n"
                f"This is a simulated paper trade. No real capital has been deployed."
            ),
            "color": 0x1B3A5C,
            "footer": {"text": "Azalyst Paper Trading  |  Simulated positions only"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # ======== REVIEW BOARD CHANGE: @mention added for trade entry ========
        self._post({
            "content": (
                f"{_mention()}  **ENTRY  |  {ticker}**  |  "
                f"{sector}  |  Confidence: {confidence}/100  |  "
                f"Risk: ${invested_usd:,.0f}"
            ),
            "embeds": [embed],
        })

    # ── Trade Exit Notice ─────────────────────────────────────────────────────

    def send_trade_exits(self, exits: List[Dict]):
        """Sent when one or more positions are closed."""
        if not exits:
            return

        for ex in exits:
            pnl     = ex["realised_pnl"]
            pnl_pct = ex["realised_pnl_pct"]
            color   = _pnl_color(pnl)
            rate    = ex.get("usd_inr_rate", 83.5)
            pnl_usd = pnl / rate
            exit_usd = ex["exit_price"] / rate
            exchange = ex.get("exchange", "—")

            embed = {
                "title": "AZALYST PAPER PORTFOLIO  —  POSITION CLOSED",
                "description": (
                    f"```\n"
                    f"Trade ID         : {ex['trade_id']}\n"
                    f"ETF              : {ex['etf_name']}  ({ex['ticker']})\n"
                    f"Exchange         : {exchange}\n"
                    f"Platform         : {ex['platform']}\n"
                    f"{'─' * 44}\n"
                    f"Exit Price       : ${exit_usd:,.4f}\n"
                    f"Days Held        : {ex['days_held']}\n"
                    f"Exit Reason      : {ex['exit_reason']}\n"
                    f"{'─' * 44}\n"
                    f"Realised PnL     : ${_sign(pnl_usd)}\n"
                    f"Return           : {_sign_pct(pnl_pct)}\n"
                    f"```"
                ),
                "color": color,
                "footer": {"text": "Azalyst Paper Trading  |  Simulated positions only"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # ======== REVIEW BOARD CHANGE: @mention added for trade exit ========
            pnl_emoji = "🟢" if pnl > 0 else "🔴"
            self._post({
                "content": (
                    f"{_mention()}  {pnl_emoji} **EXIT  |  {ex['ticker']}**  |  "
                    f"PnL: ${_sign(pnl_usd)} ({_sign_pct(pnl_pct)})  |  "
                    f"Reason: {ex['exit_reason']}"
                ),
                "embeds": [embed],
            })

    # ── End of Day Portfolio Report ───────────────────────────────────────────

    def send_eod_report(self, summary: Dict):
        """
        Daily end-of-day briefing — the full book.
        Sent once per day at configured time.
        """
        cash          = summary["cash_inr"]
        invested      = summary["total_invested"]
        current_val   = summary["total_current"]
        unrealised    = summary["unrealised_pnl"]
        realised      = summary["total_realised"]
        port_value    = summary["portfolio_value"]
        deposited     = summary["total_deposited"]
        total_ret_pct = summary["total_return_pct"]
        open_count    = summary["open_count"]
        closed_count  = summary["closed_count"]
        win_rate      = summary["win_rate"]
        winners       = summary["winners"]
        losers        = summary["losers"]
        positions     = summary["open_positions"]
        best          = summary.get("best_trade")
        worst         = summary.get("worst_trade")
        rate          = summary.get("usd_inr_rate", 83.5)

        today_str = datetime.now(timezone.utc).strftime("%d %b %Y")
        color     = _pnl_color(unrealised + realised)

        # USD equivalents
        pv_usd    = port_value / rate
        dep_usd   = deposited / rate
        cash_usd  = cash / rate
        inv_usd   = invested / rate
        cur_usd   = current_val / rate
        unr_usd   = unrealised / rate
        rel_usd   = realised / rate

        # ── Embed 1: Portfolio Overview ───────────────────────────────────
        embed1 = {
            "title": "AZALYST PAPER PORTFOLIO  —  END OF DAY REPORT",
            "description": (
                f"**{today_str}**\n\n"
                f"```\n"
                f"Portfolio Value      : ${pv_usd:>12,.2f}\n"
                f"Total Deposited      : ${dep_usd:>12,.2f}\n"
                f"Overall Return       : {_sign_pct(total_ret_pct):>12}\n"
                f"{'─' * 56}\n"
                f"Cash Available       : ${cash_usd:>12,.2f}\n"
                f"Capital Deployed     : ${inv_usd:>12,.2f}\n"
                f"Current Market Value : ${cur_usd:>12,.2f}\n"
                f"Unrealised PnL       : ${_sign(unr_usd):>12}\n"
                f"Realised PnL (total) : ${_sign(rel_usd):>12}\n"
                f"{'─' * 56}\n"
                f"Open Positions       : {open_count:>12}\n"
                f"Closed Trades        : {closed_count:>12}\n"
                f"Win Rate             : {win_rate:>11.1f}%\n"
                f"Winners / Losers     : {winners} / {losers}\n"
                f"```"
            ),
            "color": color,
        }

        # ── Embed 2: Open Positions ───────────────────────────────────────
        if positions:
            rows = []
            for p in positions:
                pnl     = round((p["current_price"] - p["entry_price"]) * p["units"], 2)
                pnl_pct = round(
                    (p["current_price"] - p["entry_price"]) / p["entry_price"] * 100, 2
                )
                days = 0
                try:
                    from datetime import date as _date
                    entry_d = datetime.fromisoformat(p["entry_date"]).date()
                    days = (_date.today() - entry_d).days
                except Exception:
                    pass

                rows.append(
                    f"  {p['trade_id']}  {p['ticker']:<12}"
                    f"  Entry: {p['entry_price']:>9,.2f}"
                    f"  Now: {p['current_price']:>9,.2f}"
                    f"  PnL: {_sign(pnl):>10}"
                    f"  ({_sign_pct(pnl_pct):>8})"
                    f"  {days}d"
                )

            positions_block = "\n".join(rows)
            embed2 = {
                "title": "OPEN POSITIONS",
                "description": f"```\n{'  ID      TICKER        ENTRY PRICE     NOW PRICE     UNREALISED PnL       DAYS':}\n{'  ' + '─' * 78}\n{positions_block}\n```",
                "color": 0x1B3A5C,
            }
        else:
            embed2 = {
                "title": "OPEN POSITIONS",
                "description": "```\nNo open positions. All cash is undeployed.\n```",
                "color": 0x1B3A5C,
            }

        # ── Embed 3: Track Record ─────────────────────────────────────────
        track_lines = []
        if best:
            track_lines.append(
                f"  Best Trade   : {best['ticker']:<10}  "
                f"{_sign_pct(best['realised_pnl_pct'])}  "
                f"({best['exit_reason']})"
            )
        if worst:
            track_lines.append(
                f"  Worst Trade  : {worst['ticker']:<10}  "
                f"{_sign_pct(worst['realised_pnl_pct'])}  "
                f"({worst['exit_reason']})"
            )

        if closed_count > 0:
            recent = sorted(
                summary.get("open_positions", []),
                key=lambda x: x.get("entry_date", ""),
                reverse=True,
            )[:3]

            track_block = "\n".join(track_lines) if track_lines else "  No closed trades yet."
            embed3 = {
                "title": "TRACK RECORD",
                "description": (
                    f"```\n"
                    f"  Total Closed Trades  : {closed_count}\n"
                    f"  Win Rate             : {win_rate:.1f}%\n"
                    f"  Total Realised PnL   : ${_sign(realised / rate)}\n"
                    f"  {'─' * 46}\n"
                    f"{track_block}\n"
                    f"```"
                ),
                "color": _pnl_color(realised),
                "footer": {
                    "text": (
                        "Azalyst Paper Trading  |  Simulated positions only.  "
                        "Not financial advice."
                    )
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            embed3 = {
                "title": "TRACK RECORD",
                "description": (
                    "```\n"
                    "  No completed trades yet. Building track record.\n"
                    "  Positions will close when target, stop-loss, or\n"
                    "  maximum hold period is reached.\n"
                    "```"
                ),
                "color": 0x1B3A5C,
                "footer": {
                    "text": (
                        "Azalyst Paper Trading  |  Simulated positions only.  "
                        "Not financial advice."
                    )
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        self._post({
            "content": (
                f"**EOD REPORT  |  {today_str}**  "
                f"|  Portfolio: ${pv_usd:,.0f}  "
                f"|  Return: {_sign_pct(total_ret_pct)}"
            ),
            "embeds": [embed1, embed2, embed3],
        })

        log.info(f"EOD report sent — Portfolio: ${pv_usd:,.2f} | Return: {total_ret_pct:+.2f}%")
