# Azalyst ETF Intelligence

> An institutional-style quantitative research platform built as a personal project. Not a hedge fund. Not a financial product. Just a passion for systematic research.

---

## Overview

Azalyst ETF Intelligence is a research infrastructure project for monitoring global news, classifying macro developments into investable sectors, and routing only the highest-conviction observations into a structured alert workflow. It is designed as a disciplined research system rather than a financial product, broker integration layer, or automated trading stack.

At a high level, the platform scans global news feeds, deduplicates and clusters related articles, applies a lightweight NLP-style sector classifier, computes a transparent five-factor confidence score, maps validated sector signals to ETFs across India and global markets, and delivers structured reports to Discord. Every cycle is logged locally, and signal state is persisted so the system can enforce cooldowns, detect stronger updates, and maintain an audit trail across runs.

The project exists for a simple reason: global macro events move faster than discretionary monitoring can reliably keep up with, yet most headline streams are too noisy to act on directly. Azalyst attempts to bridge that gap with disciplined filtering. The system is opinionated about what should qualify as a signal, conservative about what deserves distribution, and explicit about why a given alert cleared the bar.

## Dashboard Preview

Live monitor output (generated from the current portfolio/state artifacts):

![Azalyst ETF Intelligence Dashboard](docs/dashboard_12pct.png)

Core capabilities:

- Global news scanning through **[WorldMonitor](https://github.com/koala73/worldmonitor)** and direct RSS feeds.
- Sector classification across 11 research buckets using weighted keyword rules, negation handling, and article clustering.
- Five-factor confidence scoring with transparent component breakdowns.
- ETF opportunity mapping for India and global markets.
- Structured Discord delivery via **[Discord Webhooks](https://discord.com/developers/docs/resources/webhook)**.
- Local state persistence and log-based auditability.

Research controls:

- Conservative delivery threshold: `62+` confidence.
- Minimum corroboration requirement: `2+` relevant articles.
- Cooldown mechanism: `4` hours per tracked signal basket.
- Update logic: stronger signals can re-issue before cooldown expiry if confidence improves materially.
- Audit trail logging through `azalyst.log` and persisted sector state in `azalyst_state.json`.

Primary dependencies:

- **[Python 3.9+](https://www.python.org/downloads/)**
- **[WorldMonitor](https://github.com/koala73/worldmonitor)**
- **[requests](https://pypi.org/project/requests/)**
- **[feedparser](https://pypi.org/project/feedparser/)**
- **[schedule](https://pypi.org/project/schedule/)**
- **[python-dateutil](https://pypi.org/project/python-dateutil/)**
- **[python-dotenv](https://pypi.org/project/python-dotenv/)**

---

## Live Track Record — Public & Verifiable

This project runs a fully transparent, forward-tested paper trading experiment on GitHub Actions.

Every 30 minutes, the system automatically:
- Scans global news and detects macro signals
- Enters paper trades based on those signals
- Marks all open positions to market with live prices
- Commits every update back to this repository with a timestamp

**No data is hidden, adjusted, or cherry-picked.** Every trade entry, price update, stop-loss exit, and P&L change is permanently recorded in `azalyst_portfolio.json` with a full git history. Anyone can click **History** on that file and verify every single transaction from day one.

| | |
|---|---|
| **Experiment started** | March 2026 |
| **Monthly capital** | ₹10,000 / month (auto-credited) |
| **Total after 6 months** | ₹60,000 deposited |
| **Stop-loss** | −10% per position |
| **Max hold period** | 180 days |
| **Max open positions** | 6 at a time |

**Live dashboard (updates every 30 min):**
👉 https://gitdhirajsv.github.io/Azalyst-ETF-Intelligence/

The dashboard shows current portfolio value, open positions with live P&L, closed trade history, win rate, and overall return vs capital deposited.

**The goal:** After 6 months, does this system outperform a simple Nifty 50 index fund? If yes, the signal model has demonstrated real edge and real capital deployment becomes worth considering. If not, the experiment saved real money and identified what needs improvement  which is exactly what paper trading is for.

---

## System Flow

```mermaid
flowchart LR
    A["Global News"] --> B["Deduplication"]
    B --> C["NLP Classification"]
    C --> D["5-Factor Scoring"]
    D --> E["Statistical Validation"]
    E --> F["ETF Mapping"]
    F --> G["Discord Delivery"]
    G --> H["State Persistence"]
```

`Statistical Validation` in this context refers to corroboration counts, source diversity checks, recency decay, severity weighting, threshold enforcement, and cooldown-aware update logic. The objective is to suppress noise rather than maximize alert volume.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/Azalyst-ETF-Intelligence.git
cd Azalyst-ETF-Intelligence
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure `.env`

Copy the example file and set your Discord webhook:

```bash
cp .env.example .env
```

```dotenv
WEBHOOK=https://discord.com/api/webhooks/your_webhook_here
INTERVAL=30
THRESHOLD=62
COOLDOWN_HOURS=4
MIN_ARTICLES=2
```

### 4. Run the system

```bash
python azalyst.py
```

### Windows Launcher

```bat
Azalyst_Spyder.bat
```

This is the single launcher for the project. It starts the engine in a command prompt and optionally opens Spyder with the live monitor. If the Spyder window is closed, the engine keeps running.

## Configuration

| Parameter | Default | Type | Description |
|---|---:|---|---|
| `WEBHOOK` | Required | `string` | Discord webhook for structured report delivery. Also supports `AZALYST_DISCORD_WEBHOOK`. |
| `INTERVAL` | `30` | `integer` | Scan interval in minutes. Also supports `AZALYST_INTERVAL`. |
| `THRESHOLD` | `62` | `integer` | Minimum confidence score before a signal is delivered. Also supports `AZALYST_THRESHOLD`. |
| `COOLDOWN_HOURS` | `4` | `integer` | Minimum hours between alerts on the same sector. Also supports `AZALYST_COOLDOWN_HOURS`. |
| `MIN_ARTICLES` | `2` | `integer` | Minimum corroborating articles to form a signal. Also supports `AZALYST_MIN_ARTICLES`. |

See `.env.example` for the full template including advanced controls.

## Confidence Score Model

Each signal is assigned a score from `0` to `100` as the sum of five deterministic components. No hidden weighting or opaque model calibration is used.

| Factor | Max Points | Description |
|---|---:|---|
| Signal Strength | `25` | Weighted keyword relevance across clustered articles. |
| Volume Confirmation | `20` | Number of corroborating articles supporting the same theme. |
| Source Diversity | `20` | Independent source confirmation, tiered by outlet credibility. |
| Recency | `20` | Freshness of the most recent supporting article. |
| Geopolitical Severity | `15` | Event severity and regional macro impact. |

Example: `Strait of Hormuz airstrike = 92/100`

| Factor | Score | Rationale |
|---|---:|---|
| Signal Strength | `23/25` | Strong keyword density around airstrike, oil supply, shipping lanes. |
| Volume Confirmation | `16/20` | Seven corroborating articles across the event cluster. |
| Source Diversity | `18/20` | Multiple independent sources including top-tier international outlets. |
| Recency | `20/20` | Latest article published within the last hour. |
| Geopolitical Severity | `15/15` | Critical event in a high-impact energy corridor. |
| **Total** | **`92/100`** | High-conviction signal. |

## Sector Coverage

| Sector | India (Dhan/Kite) | Global (INDmoney/Vested) |
|---|---|---|
| Energy & Oil | `CPSEETF`, `PSUBNKBEES` | `XLE`, `USO`, `IXC` |
| Defense & Aerospace | `DEFENCEETF`, `CPSEETF` | `ITA`, `XAR`, `PPA` |
| Precious Metals | `GOLDBEES`, `HDFCGOLD` | `GLDM`, `GDX`, `GDXJ` |
| Technology & AI | `MAFANG`, `NIFTYBEES` | `SOXX`, `QQQ`, `AIQ` |
| Nuclear & Uranium | `CPSEETF` | `URNM`, `URA`, `SRUUF` |
| Cybersecurity | `—` | `HACK`, `CIBR` |
| Broad India Equity | `NIFTYBEES`, `MIDCAPETF` | `INDA` |
| Banking & Finance | `BANKBEES` | `XLF`, `GLDM` |
| Commodities | `CPSEETF` | `DBC`, `COPP` |
| Emerging Markets | `NIFTYBEES` | `EEM`, `SPEM` |
| Cryptocurrencies | `—` | `IBIT`, `BITQ` |

## File Structure

```text
.
|-- azalyst.py
|-- Azalyst_Spyder.bat
|-- config.py
|-- prepare_spyder_profile.py
|-- news_fetcher.py
|-- classifier.py
|-- scorer.py
|-- etf_mapper.py
|-- reporter.py
|-- state.py
|-- spyder_live_monitor.py
|-- requirements.txt
|-- docs/
|-- paper_trader.py
|-- portfolio_reporter.py
`-- generate_dashboard.py
```

Runtime artifacts (`azalyst.log`, `azalyst_state.json`, `azalyst_portfolio.json`, `status.json`) are generated automatically and should not be treated as source files.

## Usage Examples

```bash
python azalyst.py                          # run continuously (local)
python azalyst.py --once                   # single cycle then exit (GitHub Actions)
AZALYST_THRESHOLD=70 python azalyst.py     # custom confidence threshold
AZALYST_COOLDOWN_HOURS=8 python azalyst.py # extended cooldown
```

## Troubleshooting

- **No alerts firing:** confirm `WEBHOOK` is set, inspect `azalyst.log`, temporarily lower threshold to 50 to test end-to-end delivery.
- **Too many alerts:** raise `THRESHOLD`, increase `COOLDOWN_HOURS`.
- **News not loading:** check internet, try without VPN, inspect feed errors in `azalyst.log`.

## Architecture Notes

### Design principles

The system is built around transparent research mechanics. Classification is rule-based and inspectable. Scoring is additive and deterministic. Thresholds are explicit. State persistence is local and human-readable. Every alert is explainable after the fact.

The platform is signal-first rather than price-first. It does not predict intraday microstructure, route orders, or construct a portfolio frontier. Its role is upstream: identifying macro developments early, framing them consistently, and presenting a disciplined starting point for human review.

### Known limitations

- Feed quality and timing are constrained by upstream sources.
- The classifier is robust for obvious macro themes but subtle context remains a hard problem for rule-based systems.
- ETF mapping is a research convenience layer, not a guarantee of availability or suitability.
- The system does not backtest signal efficacy or model transaction costs.

## Attribution

**[WorldMonitor](https://github.com/koala73/worldmonitor)** by [@koala73](https://github.com/koala73) provides the foundation for global news aggregation.

## License

Released under the **MIT License**. See `LICENSE`.

## Disclaimer

This is a personal research and learning project. Azalyst is not a financial service, investment advisor, or trading algorithm. Nothing here is financial advice. Use entirely at your own risk. Past signal performance does not guarantee future results. Consult a qualified financial advisor before making investment decisions.

Built by **Azalyst** | Azalyst Quant Research
