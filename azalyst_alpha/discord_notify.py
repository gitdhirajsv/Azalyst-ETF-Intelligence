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


def _mention() -> str:
    return f"<@{DISCORD_USER_ID}>"


def _post(payload: dict) -> None:
    url = os.environ.get(WEBHOOK_ENV)
    if not url:
        print(f"[discord] WARNING: {WEBHOOK_ENV} not set - skipping notification")
        return
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[discord] POST success (status {resp.status})")
    except urllib.error.HTTPError as e:
        print(f"[discord] POST FAILED - HTTP {e.code}: {e.reason}")
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
            print(f"[discord]   response body: {body}")
        except Exception:
            pass
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[discord] POST FAILED - {type(e).__name__}: {e}")


def notify_entry(
    ticker: str,
    shares: int,
    fill_price: float,
    notional: float,
    score: float,
    regime_state: str,
    vol_regime: str,
    factor_breakdown: dict[str, float] | None = None,
    pct_of_book: float = 0.0,
    book_value: float = 0.0,
) -> None:
    """Tag the user — this is a real entry. Shows BOTH dollar notional AND
    percentage of book so the user can translate to any real-account size
    (10k / 50k / 100k all use same %)."""
    fb = factor_breakdown or {}
    fb_line = " | ".join(
        f"{k}={v:.0f}" for k, v in fb.items() if v
    ) or "(no breakdown)"
    pct_str = f"{pct_of_book * 100:.1f}%" if pct_of_book else "—"
    notional_str = f"${notional:,.0f}  ·  **{pct_str} of book**"
    embed = {
        "title": f"📈 ENTRY — {ticker}",
        "color": 0x00FF41,
        "fields": [
            {"name": "Shares", "value": f"{shares:,}", "inline": True},
            {"name": "Fill", "value": f"${fill_price:,.2f}", "inline": True},
            {"name": "Notional", "value": notional_str, "inline": True},
            {"name": "Composite Score", "value": f"{score:.1f} / 100", "inline": True},
            {"name": "Regime", "value": f"{regime_state} / {vol_regime}", "inline": True},
            {"name": "Book Reference", "value": f"${book_value:,.0f}" if book_value else "—", "inline": True},
            {"name": "Factor Breakdown", "value": fb_line, "inline": False},
            {"name": "Real-account translation", "value":
                f"`$10k → ${(pct_of_book * 10_000):,.0f}` · `$50k → ${(pct_of_book * 50_000):,.0f}` · `$100k → ${(pct_of_book * 100_000):,.0f}`",
                "inline": False},
        ],
        "footer": {"text": "Paper trade · simulated only · scale by your account"},
    }
    _post({"content": f"{_mention()}  **ENTRY** {ticker}  ({pct_str})", "embeds": [embed]})


def notify_exit(
    ticker: str,
    shares: int,
    fill_price: float,
    notional: float,
    pnl_usd: float,
    pnl_pct: float,
    reason: str,
    hold_days: int,
    pct_of_book_at_entry: float = 0.0,
    book_value: float = 0.0,
) -> None:
    """Tag the user — real exit. Shows P&L in $ AND % of book contribution."""
    color = 0x00FF41 if pnl_pct >= 0 else 0xFF3333
    emoji = "✅" if pnl_pct >= 0 else "🔻"
    book_contrib_pct = pct_of_book_at_entry * pnl_pct if pct_of_book_at_entry else 0.0
    pct_str = f"{pct_of_book_at_entry * 100:.1f}%" if pct_of_book_at_entry else "—"
    pnl_str = (f"${pnl_usd:+,.2f}  ·  position **{pnl_pct:+.2%}**  "
               f"·  book **{book_contrib_pct:+.3%}**")
    embed = {
        "title": f"{emoji} EXIT — {ticker}  ({pnl_pct:+.2%})",
        "color": color,
        "fields": [
            {"name": "Shares", "value": f"{shares:,}", "inline": True},
            {"name": "Fill", "value": f"${fill_price:,.2f}", "inline": True},
            {"name": "Notional", "value": f"${notional:,.0f}  ·  was {pct_str} of book", "inline": True},
            {"name": "P&L", "value": pnl_str, "inline": False},
            {"name": "Reason", "value": reason, "inline": True},
            {"name": "Hold", "value": f"{hold_days}d", "inline": True},
            {"name": "Real-account P&L", "value":
                f"`$10k acct → ${(book_contrib_pct * 10_000):+,.2f}` · `$50k → ${(book_contrib_pct * 50_000):+,.2f}` · `$100k → ${(book_contrib_pct * 100_000):+,.2f}`",
                "inline": False},
        ],
        "footer": {"text": "Paper trade · simulated only · scale by your account"},
    }
    _post({"content": f"{_mention()}  **EXIT** {ticker}  {pnl_pct:+.2%} ({pct_str} pos)", "embeds": [embed]})


def notify_cycle_digest(
    regime_state: str,
    vol_regime: str,
    vix_level: float,
    leaderboard_top: list[tuple[str, float]],
    book_size: int,
    news_top: list[tuple[str, float, str]] | None = None,
    published_count: int = 0,
) -> None:
    """No mention — informational digest after each fusion cycle."""
    top = "\n".join(
        f"`{i+1:>2}` **{tk}** — {sc:.1f}"
        for i, (tk, sc) in enumerate(leaderboard_top[:5])
    )
    description = (
        f"Regime: **{regime_state}** · **{vol_regime.replace('_',' ')}** · VIX {vix_level:.1f}\n\n"
        f"**Top 5 by composite score**\n{top}\n\n"
    )
    if news_top:
        nl = "\n".join(
            f"`{sev[:4]:>4}` **{sector}** — {conf:.0f}/100"
            for sector, conf, sev in news_top[:5]
        )
        description += f"**News leaders**\n{nl}\n\n"
    description += f"Published (cleared 60-pt gate): **{published_count}** · Live book: **{book_size}** positions"

    embed = {
        "title": "Azalyst — cycle digest",
        "description": description,
        "color": 0xFF6600,
        "footer": {"text": "Informational · no action"},
    }
    _post({"embeds": [embed]})


def notify_new_signal(ticker: str, score: float, factor_breakdown: dict[str, float] | None = None) -> None:
    """No mention — fired when a ticker enters the published-book set
    (cleared the gate AND survived dedup) but BEFORE commit_book opens it."""
    fb = factor_breakdown or {}
    fb_line = " | ".join(f"{k}={v:.0f}" for k, v in fb.items() if v) or "(no breakdown)"
    embed = {
        "title": f"📡 SIGNAL — {ticker}",
        "description": f"Composite score **{score:.1f} / 100** · cleared gate\n\n{fb_line}",
        "color": 0xFFAA00,
        "footer": {"text": "Signal published · execution decided by commit_book"},
    }
    _post({"embeds": [embed]})


def notify_news_alert(sector: str, confidence: float, severity: str, headlines: list[str], etfs: list[str]) -> None:
    """No mention — high-confidence sector news alert (independent of trades)."""
    head_block = "\n".join(f"• {h[:120]}" for h in headlines[:3]) if headlines else "_(no headlines captured)_"
    etfs_line = ", ".join(etfs[:6]) if etfs else "_(no mapping)_"
    color = 0xFF3333 if severity == "CRITICAL" else 0xFFAA00 if severity == "HIGH" else 0x888888
    embed = {
        "title": f"📰 NEWS — {sector}  ({severity})",
        "description": (
            f"Confidence **{confidence:.0f} / 100**\n\n"
            f"**Top headlines**\n{head_block}\n\n"
            f"**Related ETFs:** {etfs_line}"
        ),
        "color": color,
        "footer": {"text": "News signal · feeds news_score factor at next cycle"},
    }
    _post({"embeds": [embed]})
