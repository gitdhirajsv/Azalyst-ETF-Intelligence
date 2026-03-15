import json
import os
import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT          = Path(__file__).resolve().parent
PORTFOLIO_FILE = _ROOT / "azalyst_portfolio.json"
STATE_FILE     = _ROOT / "azalyst_state.json"
OUTPUT_FILE    = _ROOT / "status.json"          # ← was dashboard.html

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def calc_metrics(portfolio):
    positions    = portfolio.get("open_positions", [])
    total_inv    = sum(p["invested_inr"] for p in positions)
    market_val   = sum(p["current_price"] * p["units"] for p in positions)
    cash         = portfolio.get("cash_inr", 0)
    deposited    = portfolio.get("total_deposited_inr", total_inv + cash)
    total_assets = market_val + cash
    pnl          = market_val - total_inv
    overall_pct  = ((total_assets - deposited) / deposited * 100) if deposited > 0 else 0
    return dict(
        portfolio_value = round(total_assets, 2),
        total_deposited = round(deposited, 2),
        cash            = round(cash, 2),
        market_value    = round(market_val, 2),
        change          = f"{overall_pct:+.2f}",
        closed_trades   = portfolio.get("closed_trades", 0),
    )

def build_allocation(positions, cash):
    """Pie chart: each position as % of total assets."""
    total = sum(p["current_price"] * p["units"] for p in positions) + cash
    if total == 0:
        return {"labels": [], "values": []}
    labels, values = [], []
    for p in positions:
        val = p["current_price"] * p["units"]
        labels.append(p["ticker"])
        values.append(round(val / total * 100, 1))
    labels.append("CASH")
    values.append(round(cash / total * 100, 1))
    return {"labels": labels, "values": values}

def build_pnl(positions):
    """Bar chart: unrealised P&L per position in INR."""
    labels, values = [], []
    for p in positions:
        pnl = round(p["current_price"] * p["units"] - p["invested_inr"], 2)
        labels.append(p["ticker"])
        values.append(pnl)
    return {"labels": labels, "values": values}

def build_confidence(state):
    """Confidence bars from azalyst_state.json signals."""
    rows = []
    for key, sig in state.items():
        rows.append({
            "symbol": sig.get("etf_ticker", key),
            "score":  round(float(sig.get("confidence", 0)), 1),
        })
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows

def build_articles(state):
    """Article update cards from signals."""
    articles = []
    for key, sig in state.items():
        conf  = float(sig.get("confidence", 0))
        label = sig.get("sector_label", key)
        etf   = sig.get("etf_ticker", key)
        count = sig.get("article_count", 0)

        if conf >= 80:
            tag, badge = "tag-bull", "Bullish"
        elif conf >= 65:
            tag, badge = "tag-neu", "Neutral"
        else:
            tag, badge = "tag-bear", "Watch"

        articles.append({
            "tag":   tag,
            "label": badge,
            "text":  f"{label} — {count} articles · {etf} confidence {conf:.0f}%",
        })

    articles.sort(key=lambda x: {"tag-bull": 0, "tag-neu": 1, "tag-bear": 2}[x["tag"]])
    return articles

def build_logs(portfolio, state):
    """Reconstruct a log tail from available data."""
    now  = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    logs = []

    logs.append(f"{now} [INFO] AZALYST — Dashboard status.json generated")

    sig_count = len(state)
    if sig_count:
        logs.append(f"{now} [INFO] AZALYST — {sig_count} active signals in state")

    positions = portfolio.get("open_positions", [])
    if positions:
        tickers = ", ".join(p["ticker"] for p in positions)
        logs.append(f"{now} [INFO] AZALYST — Open positions: {tickers}")

    total_articles = sum(
        int(sig.get("article_count", 0)) for sig in state.values()
    )
    if total_articles:
        logs.append(f"{now} [INFO] azalyst.classifier — Total articles across signals: {total_articles}")

    # Append any existing logs stored in portfolio file
    for entry in portfolio.get("logs", [])[-15:]:
        logs.append(entry)

    return logs

# ── Main ──────────────────────────────────────────────────────────────────────
def generate_status():
    portfolio = load_json(PORTFOLIO_FILE)
    state     = load_json(STATE_FILE)
    positions = portfolio.get("open_positions", [])
    cash      = portfolio.get("cash_inr", 0)

    status = {
        **calc_metrics(portfolio),
        "positions":            [{"symbol": p["ticker"]} for p in positions],
        "confidence_threshold": 62,
        "allocation":           build_allocation(positions, cash),
        "pnl":                  build_pnl(positions),
        "confidence":           build_confidence(state),
        "articles":             build_articles(state),
        "logs":                 build_logs(portfolio, state),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)

    print(f"✅  status.json written to {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_status()
