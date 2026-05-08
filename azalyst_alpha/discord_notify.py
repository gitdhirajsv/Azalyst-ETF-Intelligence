"""
Discord notifications for v2 paper trader.

Policy (from v1 portfolio_reporter, retained for v2):
  - @mention only on actual paper-trade buy/sell events.
  - Cycle digests, leaderboard updates, and informational pings post WITHOUT mention.

Webhook URL from DISCORD_WEBHOOK_URL env var. No-op if unset.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


DISCORD_USER_ID = "1363959528194052118"  # owner
WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


def _post(payload: dict) -> None:
    url = os.environ.get(WEBHOOK_ENV)
    if not url:
        return
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except (urllib.error.URLError, TimeoutError):
        pass


def _mention() -> str:
    return f"<@{DISCORD_USER_ID}>"


def notify_entry(
    ticker: str,
    shares: int,
    fill_price: float,
    notional: float,
    score: float,
    regime_state: str,
    vol_regime: str,
    factor_breakdown: dict[str, float] | None = None,
) -> None:
    """Tag the user — this is a real entry."""
    fb = factor_breakdown or {}
    fb_line = " | ".join(
        f"{k}={v:.0f}" for k, v in fb.items() if v
    ) or "(no breakdown)"
    embed = {
        "title": f"📈 ENTRY — {ticker}",
        "color": 0x00FF41,  # green
        "fields": [
            {"name": "Shares", "value": f"{shares:,}", "inline": True},
            {"name": "Fill", "value": f"${fill_price:,.2f}", "inline": True},
            {"name": "Notional", "value": f"${notional:,.0f}", "inline": True},
            {"name": "Composite Score", "value": f"{score:.1f} / 100", "inline": True},
            {"name": "Regime", "value": f"{regime_state} / {vol_regime}", "inline": True},
            {"name": "Factor Breakdown", "value": fb_line, "inline": False},
        ],
        "footer": {"text": "Azalyst v2 · paper trade · simulated only"},
    }
    _post({"content": f"{_mention()}  **ENTRY** {ticker}", "embeds": [embed]})


def notify_exit(
    ticker: str,
    shares: int,
    fill_price: float,
    notional: float,
    pnl_usd: float,
    pnl_pct: float,
    reason: str,
    hold_days: int,
) -> None:
    """Tag the user — this is a real exit."""
    color = 0x00FF41 if pnl_pct >= 0 else 0xFF3333
    emoji = "✅" if pnl_pct >= 0 else "🔻"
    embed = {
        "title": f"{emoji} EXIT — {ticker}  ({pnl_pct:+.2%})",
        "color": color,
        "fields": [
            {"name": "Shares", "value": f"{shares:,}", "inline": True},
            {"name": "Fill", "value": f"${fill_price:,.2f}", "inline": True},
            {"name": "P&L", "value": f"${pnl_usd:+,.2f}", "inline": True},
            {"name": "Reason", "value": reason, "inline": True},
            {"name": "Hold", "value": f"{hold_days}d", "inline": True},
        ],
        "footer": {"text": "Azalyst v2 · paper trade · simulated only"},
    }
    _post({"content": f"{_mention()}  **EXIT** {ticker}  {pnl_pct:+.2%}", "embeds": [embed]})


def notify_cycle_digest(
    regime_state: str,
    vol_regime: str,
    vix_level: float,
    leaderboard_top: list[tuple[str, float]],
    book_size: int,
) -> None:
    """No mention — informational only."""
    top = "\n".join(f"`{i+1:>2}` **{tk}** — {sc:.1f}" for i, (tk, sc) in enumerate(leaderboard_top[:5]))
    embed = {
        "title": "Azalyst v2 — cycle digest",
        "description": f"Regime: **{regime_state}** / **{vol_regime}**  ·  VIX {vix_level:.1f}\n\n"
                       f"**Top 5 leaderboard**\n{top}\n\n"
                       f"Live book: {book_size} positions",
        "color": 0xFF6600,
        "footer": {"text": "Azalyst v2 · informational · no action"},
    }
    _post({"embeds": [embed]})
