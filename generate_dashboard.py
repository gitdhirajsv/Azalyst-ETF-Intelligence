import json
import os
import datetime
import urllib.request
import urllib.error
from pathlib import Path

_ROOT          = Path(__file__).resolve().parent
PORTFOLIO_FILE = _ROOT / "azalyst_portfolio.json"
STATE_FILE     = _ROOT / "azalyst_state.json"
OUTPUT_FILE    = _ROOT / "status.json"

SECTOR_LABELS = {
    "defense": "Defense & Aerospace", "defense_aerospace": "Defense & Aerospace",
    "india_equity": "India Equity", "banking_financial": "Banking & Finance",
    "gold_precious_metals": "Precious Metals", "energy_oil": "Energy & Oil",
    "commodities_mining": "Commodities", "crypto_digital": "Crypto & Digital",
    "technology_ai": "Technology & AI", "nuclear_uranium": "Nuclear & Uranium",
    "cybersecurity": "Cybersecurity", "emerging_markets": "Emerging Markets",
}

def clean_label(k):
    k = k.split("|")[0].strip().lower()
    return SECTOR_LABELS.get(k, k.replace("_", " ").title())

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except Exception as e:
            print(f"⚠️ {path}: {e}"); return {}
    print(f"⚠️ Not found: {path}"); return {}

def sign(v):     return f"+{v:,.2f}" if v >= 0 else f"{v:,.2f}"
def signp(v):    return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"

def calc_metrics(pf):
    pos       = pf.get("open_positions", [])
    inv       = sum(p["invested_inr"] for p in pos)
    mktval    = sum(p["current_price"] * p["units"] for p in pos)
    cash      = pf.get("cash_inr", 0)
    deposited = pf.get("total_deposited", pf.get("total_deposited_inr", inv + cash))
    total     = mktval + cash
    unreal    = mktval - inv
    realised  = sum(ct.get("realised_pnl", 0) for ct in pf.get("closed_trades", []))
    ret_pct   = ((total - deposited) / deposited * 100) if deposited > 0 else 0
    return {
        "portfolio_value":   round(total, 2),
        "total_deposited":   round(deposited, 2),
        "cash":              round(cash, 2),
        "market_value":      round(mktval, 2),
        "total_invested":    round(inv, 2),
        "unrealised_pnl":    round(unreal, 2),
        "unrealised_str":    sign(unreal),
        "realised_pnl":      round(realised, 2),
        "realised_str":      sign(realised),
        "change":            signp(ret_pct),
        "change_raw":        round(ret_pct, 2),
        "closed_trades":     len(pf.get("closed_trades", [])),
    }

def build_positions(pos):
    rows = []
    for p in pos:
        e, c, u = p.get("entry_price",0), p.get("current_price", p.get("entry_price",0)), p.get("units",0)
        inv = p.get("invested_inr", 0)
        pnl = round((c - e) * u, 2)
        pct = round((c - e) / e * 100, 2) if e else 0
        rows.append({
            "trade_id": p.get("trade_id",""), "ticker": p.get("ticker",""),
            "etf_name": p.get("etf_name",""), "sector": p.get("sector",""),
            "platform": p.get("platform",""),
            "entry": round(e,2), "current": round(c,2),
            "units": round(u,6), "invested": round(inv,2),
            "pnl": pnl, "pnl_str": sign(pnl),
            "pnl_pct": pct, "pnl_pct_str": signp(pct),
            "confidence": p.get("confidence",0), "severity": p.get("severity",""),
        })
    return rows

def build_closed(closed):
    rows = []
    for ct in closed:
        pnl = ct.get("realised_pnl", 0)
        pct = ct.get("realised_pnl_pct", 0)
        rows.append({
            "trade_id": ct.get("trade_id",""), "ticker": ct.get("ticker",""),
            "etf_name": ct.get("etf_name",""),
            "entry": round(ct.get("entry_price",0),2), "exit": round(ct.get("exit_price",0),2),
            "pnl": round(pnl,2), "pnl_str": sign(pnl),
            "pnl_pct": round(pct,2), "pnl_pct_str": signp(pct),
            "days_held": ct.get("days_held",0), "exit_reason": ct.get("exit_reason",""),
            "winner": pnl > 0,
        })
    return rows

def build_track(pf):
    closed  = pf.get("closed_trades", [])
    winners = [ct for ct in closed if ct.get("realised_pnl", 0) > 0]
    losers  = [ct for ct in closed if ct.get("realised_pnl", 0) <= 0]
    wr      = round(len(winners) / len(closed) * 100, 1) if closed else 0
    best    = max(closed, key=lambda x: x.get("realised_pnl_pct", 0), default=None)
    worst   = min(closed, key=lambda x: x.get("realised_pnl_pct", 0), default=None)

    def _summary(ct):
        if ct is None:
            return None
        pct = float(ct.get("realised_pnl_pct", 0) or 0)
        return {
            "ticker":      ct.get("ticker", "–"),
            "etf_name":    ct.get("etf_name", "–"),
            "pnl_pct":     round(pct, 2),
            "pnl_pct_str": signp(pct),
            "exit_reason": ct.get("exit_reason", "–"),
            "days_held":   ct.get("days_held", 0),
        }

    return {
        "total_trades": len(closed),
        "winners":      len(winners),
        "losers":       len(losers),
        "win_rate":     wr,
        "avg_win":      round(sum(ct.get("realised_pnl_pct", 0) for ct in winners) / len(winners), 2) if winners else 0,
        "avg_loss":     round(sum(ct.get("realised_pnl_pct", 0) for ct in losers)  / len(losers),  2) if losers  else 0,
        "best":         _summary(best),
        "worst":        _summary(worst),
    }

def build_alloc(pos, cash):
    total = sum(p["current_price"]*p["units"] for p in pos) + cash
    if not total: return {"labels":[], "values":[]}
    labels = [p["ticker"] for p in pos] + ["CASH"]
    values = [round(p["current_price"]*p["units"]/total*100,1) for p in pos] + [round(cash/total*100,1)]
    return {"labels": labels, "values": values}

def build_pnl(pos):
    return {
        "labels": [p["ticker"] for p in pos],
        "values": [round((p["current_price"]-p["entry_price"])*p["units"],2) for p in pos],
    }

def build_conf(state):
    rows = [{"symbol": s.get("sector_label") or clean_label(k),
             "score": round(float(s.get("confidence",0)),1)} for k,s in state.items()]
    return sorted(rows, key=lambda x: x["score"], reverse=True)

def build_articles(state):
    out = []
    for k, s in state.items():
        conf  = float(s.get("confidence",0))
        label = s.get("sector_label") or clean_label(k)
        count = s.get("article_count",0)
        tag   = "tag-bull" if conf>=80 else "tag-neu" if conf>=65 else "tag-bear"
        badge = "Bullish"  if conf>=80 else "Neutral" if conf>=65 else "Watch"
        out.append({"tag":tag,"label":badge,"text":f"{label} — {count} articles · confidence {conf:.0f}%"})
    return sorted(out, key=lambda x: {"tag-bull":0,"tag-neu":1,"tag-bear":2}[x["tag"]])


# ── Market snapshot (Yahoo Finance — free, no key required) ───────────────────
_MARKET_TICKERS = [
    ("^GSPC",   "S&P 500",     "US"),
    ("^IXIC",   "NASDAQ",      "US"),
    ("^DJI",    "Dow Jones",   "US"),
    ("^FTSE",   "FTSE 100",    "UK"),
    ("^GDAXI",  "DAX",         "EU"),
    ("^N225",   "Nikkei 225",  "JP"),
    ("^HSI",    "Hang Seng",   "HK"),
    ("^NSEI",   "Nifty 50",    "IN"),
    ("GC=F",    "Gold",        "COMMOD"),
    ("CL=F",    "Crude Oil",   "COMMOD"),
    ("BTC-USD", "Bitcoin",     "CRYPTO"),
    ("DX-Y.NYB","USD Index",   "FX"),
]


def fetch_market_snapshot() -> list:
    """
    Pull price + 1-day change for major global indices, commodities, crypto.
    Uses Yahoo Finance public v8 API — no API key required.
    Gracefully skips any ticker that fails.
    """
    results = []
    for ticker, label, region in _MARKET_TICKERS:
        try:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                f"?interval=1d&range=2d"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read())
            meta      = data["chart"]["result"][0]["meta"]
            price     = float(meta.get("regularMarketPrice") or 0)
            prev      = float(meta.get("previousClose") or price)
            chg       = price - prev
            chg_pct   = (chg / prev * 100) if prev else 0
            currency  = meta.get("currency", "")
            results.append({
                "label":      label,
                "ticker":     ticker,
                "region":     region,
                "price":      round(price, 2),
                "currency":   currency,
                "change":     round(chg, 2),
                "change_pct": round(chg_pct, 2),
                "change_str": f"+{chg_pct:.2f}%" if chg_pct >= 0 else f"{chg_pct:.2f}%",
                "direction":  "up" if chg_pct >= 0 else "down",
            })
        except Exception:
            continue
    return results


def build_logs(pf, state):
    from datetime import timezone as _tz
    now = datetime.datetime.now(_tz.utc).strftime("%Y-%m-%d %H:%M:%S")
    logs = [f"{now} [INFO] AZALYST — status.json generated"]
    if state:
        logs.append(f"{now} [INFO] AZALYST — {len(state)} active signals in state")
    pos = pf.get("open_positions", [])
    if pos:
        logs.append(f"{now} [INFO] AZALYST — Open positions: {', '.join(p['ticker'] for p in pos)}")
    closed = pf.get("closed_trades", [])
    if closed:
        logs.append(f"{now} [INFO] AZALYST — Closed trades: {len(closed)}")
    total_articles = sum(s.get("article_count", 0) for s in state.values()) if state else 0
    if total_articles:
        logs.append(f"{now} [INFO] azalyst.classifier — Total articles: {total_articles}")
    return logs

def generate_status():
    pf    = load_json(PORTFOLIO_FILE)
    state = load_json(STATE_FILE)
    now   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    if not pf and not state:
        print("⚠️  No data — writing minimal status.json")
        out = {
            "portfolio_value":0,"total_deposited":0,"cash":0,"market_value":0,
            "total_invested":0,"unrealised_pnl":0,"unrealised_str":"+0.00",
            "realised_pnl":0,"realised_str":"+0.00","change":"+0.00%","change_raw":0,
            "closed_trades":0,"positions":[],"closed_trades_list":[],
            "track_record":{"total_trades":0,"winners":0,"losers":0,"win_rate":0,"best":None,"worst":None},
            "confidence_threshold":62,"allocation":{"labels":[],"values":[]},
            "pnl":{"labels":[],"values":[]},"confidence":[],"articles":[],
            "logs":[f"{now} [WARN] No data available"],"generated_at":now,
        }
        with open(OUTPUT_FILE,"w") as f: json.dump(out,f,indent=2)
        print(f"✅ Written: {OUTPUT_FILE}"); return

    pos  = pf.get("open_positions",[])
    cash = pf.get("cash_inr",0)

    status = {
        **calc_metrics(pf),
        "positions":          build_positions(pos),
        "closed_trades_list": build_closed(pf.get("closed_trades",[])),
        "track_record":       build_track(pf),
        "confidence_threshold": 62,
        "allocation":         build_alloc(pos, cash),
        "pnl":                build_pnl(pos),
        "confidence":         build_conf(state),
        "articles":           build_articles(state),
        "market_snapshot":    fetch_market_snapshot(),
        "logs":               build_logs(pf, state),
        "generated_at":       now,
    }

    with open(OUTPUT_FILE,"w") as f: json.dump(status,f,indent=2)
    print(f"✅ status.json written → {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_status()
