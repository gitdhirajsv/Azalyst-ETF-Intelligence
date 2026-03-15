import json
import os
import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT          = Path(__file__).resolve().parent
PORTFOLIO_FILE = _ROOT / "azalyst_portfolio.json"
STATE_FILE     = _ROOT / "azalyst_state.json"
OUTPUT_FILE    = _ROOT / "status.json"

# ── Sector label cleanup ───────────────────────────────────────────────────────
SECTOR_LABELS = {
    "defense":               "Defense & Aerospace",
    "defense_aerospace":     "Defense & Aerospace",
    "india_equity":          "India Equity",
    "banking_financial":     "Banking & Finance",
    "gold_precious_metals":  "Precious Metals",
    "energy_oil":            "Energy & Oil",
    "commodities_mining":    "Commodities",
    "crypto_digital":        "Crypto & Digital",
    "technology_ai":         "Technology & AI",
    "nuclear_uranium":       "Nuclear & Uranium",
    "cybersecurity":         "Cybersecurity",
    "emerging_markets":      "Emerging Markets",
}

def clean_label(raw_key):
    key = raw_key.split("|")[0].strip().lower()
    return SECTOR_LABELS.get(key, raw_key.replace("_", " ").title())

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"⚠️  Could not parse {path}: {e}")
            return {}
        except Exception as e:
            print(f"⚠️  Unexpected error reading {path}: {e}")
            return {}
    print(f"⚠️  File not found: {path}")
    return {}

def calc_metrics(portfolio):
    positions    = portfolio.get("open_positions", [])
    total_inv    = sum(p["invested_inr"] for p in positions)
    market_val   = sum(p["current_price"] * p["units"] for p in positions)
    cash         = portfolio.get("cash_inr", 0)
    deposited    = portfolio.get("total_deposited_inr", total_inv + cash)
    total_assets = market_val + cash
    overall_pct  = ((total_assets - deposited) / deposited * 100) if deposited > 0 else 0
    sign         = "+" if overall_pct >= 0 else ""
    return dict(
        portfolio_value = round(total_assets, 2),
        total_deposited = round(deposited, 2),
        cash            = round(cash, 2),
        market_value    = round(market_val, 2),
        change          = f"{sign}{overall_pct:.2f}",
        closed_trades   = int(portfolio.get("closed_trades", 0)),
    )

def build_allocation(positions, cash):
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
    labels, values = [], []
    for p in positions:
        invested    = p.get("invested_inr", 0)
        current_val = p["current_price"] * p["units"]
        labels.append(p["ticker"])
        values.append(round(current_val - invested, 2))
    return {"labels": labels, "values": values}

def build_confidence(state):
    rows = []
    for key, sig in state.items():
        label = sig.get("sector_label") or clean_label(key)
        rows.append({
            "symbol": label,
            "score":  round(float(sig.get("confidence", 0)), 1),
        })
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows

def build_articles(state):
    articles = []
    for key, sig in state.items():
        conf  = float(sig.get("confidence", 0))
        label = sig.get("sector_label") or clean_label(key)
        etf   = sig.get("etf_ticker", "")
        count = sig.get("article_count", 0)

        if conf >= 80:
            tag, badge = "tag-bull", "Bullish"
        elif conf >= 65:
            tag, badge = "tag-neu",  "Neutral"
        else:
            tag, badge = "tag-bear", "Watch"

        text = f"{label} — {count} articles · {etf} confidence {conf:.0f}%" if etf else \
               f"{label} — {count} articles · confidence {conf:.0f}%"

        articles.append({"tag": tag, "label": badge, "text": text})

    articles.sort(key=lambda x: {"tag-bull": 0, "tag-neu": 1, "tag-bear": 2}[x["tag"]])
    return articles

def build_logs(portfolio, state):
    now  = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    logs = []
    logs.append(f"{now} [INFO] AZALYST — status.json generated")
    sig_count = len(state)
    if sig_count:
        logs.append(f"{now} [INFO] AZALYST — {sig_count} active signals in state")
    positions = portfolio.get("open_positions", [])
    if positions:
        tickers = ", ".join(p["ticker"] for p in positions)
        logs.append(f"{now} [INFO] AZALYST — Open positions: {tickers}")
    total_articles = sum(int(sig.get("article_count", 0)) for sig in state.values())
    if total_articles:
        logs.append(f"{now} [INFO] azalyst.classifier — Total articles: {total_articles}")
    for entry in portfolio.get("logs", [])[-15:]:
        logs.append(entry)
    return logs

# ── Main ──────────────────────────────────────────────────────────────────────
def generate_status():
    portfolio = load_json(PORTFOLIO_FILE)
    state     = load_json(STATE_FILE)

    # If azalyst.py found no articles/signals this cycle it won't write
    # state files — this happens on scheduled runs during quiet news windows.
    # Write a valid minimal status.json so downstream steps never crash.
    if not portfolio and not state:
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        print("⚠️  No data files found — writing minimal status.json")
        minimal = {
            "portfolio_value":    0,
            "total_deposited":    0,
            "cash":               0,
            "market_value":       0,
            "change":             "+0.00",
            "closed_trades":      0,
            "positions":          [],
            "confidence_threshold": 62,
            "allocation":         {"labels": [], "values": []},
            "pnl":                {"labels": [], "values": []},
            "confidence":         [],
            "articles":           [],
            "logs":               [f"{now} [WARN] AZALYST — No data available this cycle (quiet news window)"],
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(minimal, f, indent=2, ensure_ascii=False)
        print(f"✅  Minimal status.json written to {OUTPUT_FILE}")
        return

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
