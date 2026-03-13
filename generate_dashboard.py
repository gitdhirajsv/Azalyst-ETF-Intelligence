import json
import datetime
import os

# Paths
PORTFOLIO_FILE = r"d:\Personal Files\Azalyst-ETF-Intelligence\azalyst_portfolio.json"
STATE_FILE = r"d:\Personal Files\Azalyst-ETF-Intelligence\azalyst_state.json"
OUTPUT_FILE = r"d:\Personal Files\Azalyst-ETF-Intelligence\dashboard.html"

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def format_currency(value):
    return f"₹{value:,.2f}"

def format_pct(value):
    color = "#10b981" if value >= 0 else "#ef4444"
    sign = "+" if value >= 0 else ""
    return f'<span style="color: {color}; font-weight: 600;">{sign}{value:.2f}%</span>'

def calculate_portfolio_metrics(portfolio):
    total_invested = sum(pos['invested_inr'] for pos in portfolio.get('open_positions', []))
    current_value = sum(pos['current_price'] * pos['units'] for pos in portfolio.get('open_positions', []))
    cash = portfolio.get('cash_inr', 0)
    total_assets = current_value + cash
    pnl = current_value - total_invested
    pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0
    
    return {
        "invested": total_invested,
        "current": current_value,
        "cash": cash,
        "total": total_assets,
        "pnl": pnl,
        "pnl_pct": pnl_pct
    }

def generate_html():
    portfolio = load_json(PORTFOLIO_FILE)
    state = load_json(STATE_FILE)
    metrics = calculate_portfolio_metrics(portfolio)
    
    # Sort signals by recency
    signals = []
    for key, data in state.items():
        signals.append(data)
    signals.sort(key=lambda x: x.get('sent_at', ''), reverse=True)

    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Azalyst ETF Intelligence Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --accent: #3b82f6;
            --text-main: #f8fafc;
            --text-dim: #94a3b8;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Inter', sans-serif; 
            background: var(--bg); 
            color: var(--text-main);
            line-height: 1.5;
            padding: 2rem;
        }}

        .container {{ max-width: 1200px; margin: 0 auto; }}
        
        header {{ margin-bottom: 2.5rem; border-bottom: 1px solid #334155; padding-bottom: 1.5rem; }}
        h1 {{ font-size: 2rem; font-weight: 700; letter-spacing: -0.025em; }}
        .timestamp {{ color: var(--text-dim); font-size: 0.875rem; }}

        .metrics-grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); 
            gap: 1.5rem; 
            margin-bottom: 2.5rem;
        }}

        .card {{ 
            background: var(--card-bg); 
            padding: 1.5rem; 
            border-radius: 1rem; 
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            border: 1px solid #334155;
            transition: transform 0.2s;
        }}
        .card:hover {{ transform: translateY(-2px); }}

        .metric-label {{ font-size: 0.875rem; color: var(--text-dim); margin-bottom: 0.5rem; }}
        .metric-value {{ font-size: 1.75rem; font-weight: 700; }}
        
        .section-title {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 1.25rem; display: flex; align-items: center; gap: 0.5rem; }}

        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th {{ text-align: left; padding: 1rem; color: var(--text-dim); font-weight: 500; font-size: 0.875rem; border-bottom: 1px solid #334155; }}
        td {{ padding: 1rem; border-bottom: 1px solid #334155; font-size: 0.9375rem; }}
        
        .badge {{ 
            padding: 0.25rem 0.625rem; 
            border-radius: 9999px; 
            font-size: 0.75rem; 
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge-high {{ background: rgba(245, 158, 11, 0.1); color: var(--warning); }}
        .badge-critical {{ background: rgba(239, 68, 68, 0.1); color: var(--danger); }}
        .badge-normal {{ background: rgba(59, 130, 246, 0.1); color: var(--accent); }}

        .signal-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1rem;
        }}
        
        .signal-card {{
            background: rgba(30, 41, 59, 0.5);
            border: 1px solid #334155;
            border-radius: 0.75rem;
            padding: 1.25rem;
        }}
        .signal-header {{ display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem; }}
        .signal-sector {{ font-weight: 600; color: var(--accent); }}
        .signal-meta {{ font-size: 0.8125rem; color: var(--text-dim); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏦 Azalyst Intelligence Dashboard</h1>
            <p class="timestamp">Last Updated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </header>

        <section>
            <h2 class="section-title">📊 Portfolio Overview</h2>
            <div class="metrics-grid">
                <div class="card">
                    <div class="metric-label">Total Assets</div>
                    <div class="metric-value">{format_currency(metrics['total'])}</div>
                </div>
                <div class="card">
                    <div class="metric-label">Portfolio P&L</div>
                    <div class="metric-value">{format_currency(metrics['pnl'])} ({format_pct(metrics['pnl_pct'])})</div>
                </div>
                <div class="card">
                    <div class="metric-label">Available Cash</div>
                    <div class="metric-value">{format_currency(metrics['cash'])}</div>
                </div>
                <div class="card">
                    <div class="metric-label">Active Positions</div>
                    <div class="metric-value">{len(portfolio.get('open_positions', []))}</div>
                </div>
            </div>
        </section>

        <section style="margin-bottom: 3rem;">
            <h2 class="section-title">💼 Open Positions</h2>
            <div class="card" style="padding: 0;">
                <table>
                    <thead>
                        <tr>
                            <th>ETF Ticker</th>
                            <th>Sector</th>
                            <th>Units</th>
                            <th>Invested</th>
                            <th>Current Value</th>
                            <th>Returns</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join([f'''
                        <tr>
                            <td><strong>{pos['ticker']}</strong><br><small style="color:var(--text-dim)">{pos['etf_name']}</small></td>
                            <td>{pos['sector']}</td>
                            <td>{pos['units']:.4f}</td>
                            <td>{format_currency(pos['invested_inr'])}</td>
                            <td>{format_currency(pos['current_price'] * pos['units'])}</td>
                            <td>{format_pct(((pos['current_price'] * pos['units']) - pos['invested_inr']) / pos['invested_inr'] * 100)}</td>
                        </tr>
                        ''' for pos in portfolio.get('open_positions', [])])}
                    </tbody>
                </table>
            </div>
        </section>

        <section>
            <h2 class="section-title">🔔 Recent Signals</h2>
            <div class="signal-grid">
                {"".join([f'''
                <div class="signal-card">
                    <div class="signal-header">
                        <div class="signal-sector">{sig['sector_label']}</div>
                        <div class="badge badge-{"critical" if sig['confidence'] >= 85 else "high" if sig['confidence'] >= 75 else "normal"}">
                            {sig['confidence']}% Conf
                        </div>
                    </div>
                    <div class="signal-meta">
                        <div>📅 {sig['sent_at'][:19].replace('T', ' ')}</div>
                        <div>📰 {sig['article_count']} articles analyzed</div>
                    </div>
                </div>
                ''' for sig in signals[:12]])}
            </div>
        </section>
    </div>
</body>
</html>
    """
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"Dashboard generated successfully at {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_html()
