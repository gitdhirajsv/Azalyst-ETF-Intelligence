# Azalyst ETF Intelligence — v2 Alpha Stack

> **A note from the desk.** This week I sat with the leaderboard open and watched
> EWY +9.95%, IGV +8.27%, SLV +7.41%, SOXX +6.70%, SMH +6.59% print over 5
> sessions — and Azalyst v1 surfaced none of them. I was taking those trades by
> eye while the engine I'd built told me nothing. So I called a board meeting,
> brought in the experts whose work I respect, took the CTO chair myself, and
> rebuilt the system from the ground up. This README is the public record of
> that rebuild.
>
> — *gitdhirajsv*

---

## What v1 was

Azalyst v1 was a news-driven sector-rotation platform: four engines (News,
Price, Constituents, COT) feeding a confidence scorer that gated publication at
62/100. On paper, an elegant multi-engine fusion. In practice, the scorer
allocated **88 of 100 points to news factors**, capped cross-engine confirmation
at 12, and `self_improve.py` retuned weights against past P&L on a nightly
cron. A clean tape-led move could not mathematically clear the gate without a
press release — and by the time the press arrived, the move was over.

That's what the leaderboard week proved.

## The board meeting

I didn't want to redesign this alone, so I assembled a virtual round table of
ten practitioners whose published work directly addresses every gap I'd
identified — Cliff Asness, Gary Antonacci, Meb Faber, Andrew Lo, Marcos López
de Prado, Ernest Chan, Eric Balchunas, Charlie McElligott, Cem Karsan, Wes
Gray. Each took a verdict and a concrete demand. The vote on the highest-leverage fix:

| Fix | Voters |
|---|---|
| Rebuild scorer so price/flow can clear gate without news | Asness, Faber, Chan, Lo (4) |
| Add ETF flows + options/dealer positioning | Balchunas, McElligott, Karsan (3) |
| Holdings-weighted (not equal-weight) constituent rotation | Gray, Antonacci (2) |
| Stop overfitting via `self_improve.py` until CV is in place | López de Prado (1) |

The room was unanimous on diagnosis: **v1 was a news-confirmation engine wearing
quant aesthetics.** The 62-point scorer with 88/100 budget on news was the
chokepoint.

## The CTO mandate

I took the CTO + Fund Manager chair and committed to delivery against this
spec, in writing, before any P&L exists to argue with:

> *Annualized return 25–40% gross, Sharpe > 1.4, max drawdown < 18%, deflated
> Sharpe > 0.5 on a 6-month rolling window. If realized DSR drops below 0.4
> over any 6-month window, the strategy auto-pauses pending re-validation.*

Hold me to it.

## What v2 actually is

A 7-layer alpha stack with regime-conditional weighting, a vol-targeted
portfolio constructor, capped-and-trailing risk overlay, and a López de Prado
validation gate. Free data only — no Bloomberg, no SpotGamma, no LiveVol — built
from yfinance EOD, issuer holdings JSONs, FRED, and Black-Scholes math on
public option chains.

| Layer | Module | What it does | Replaces (paid equiv.) |
|---|---|---|---|
| 1 | `cross_sectional_ranker.py` | Risk-adj rank across 120 ETFs, residualized vs. SPY — generates the leaderboard | — |
| 2 | `flow_engine.py` | ETF creation/redemption + AUM Δ proxy | Bloomberg ETF flows |
| 3a | `gex_engine.py` | Dealer GEX from Black-Scholes on yfinance chains, gamma flip level, call/put walls | SpotGamma ($500/mo) |
| 3b | `options_tape.py` | IV rank, 25Δ skew, sweep detector, C/P $-vol ratio | LiveVol ($300/mo) |
| 4 | `holdings_weighted_rotation.py` | Top-holding rotation **weighted by AUM share** (not equal-weight count) | — |
| 5 | `macro_overlay.py` | Per-ETF cross-asset regime fit (DXY, real yields, copper/gold, KRW…) | Refinitiv |
| 6 | News confirmation | Existing RSS ingestion, **downgraded to 10/100 max** | — |
| 7 | `cluster_dedup.py` | Hierarchical correlation clustering — kills SOXX+SMH double-count | — |
| Risk | `regime_engine.py` | Lo VIX-tercile weight matrix + Antonacci abs-momentum gate | — |
| Risk | `position_sizer.py` | Vol-target sizing, capped Kelly | — |
| Risk | `risk_manager.py` | ATR(14) chandelier trailing stop, –8% hard, –15% DD circuit breaker | — |
| Validation | `backtester.py` | Walk-forward + purged k-fold | — |
| Validation | `deflated_sharpe.py` | DSR ≥ 0.5 publication gate | — |
| Exec | `paper_trader.py` | SQLite paper trader with half-spread + √-rule market impact | — |
| Reporting | `report.py` | Daily markdown tearsheet | — |
| Orchestration | `fusion.py` | End-to-end daily runner | — |

### The new scorer (`scorer_v2.py`)

| Factor | Pts (mid-vol) | Source |
|---|---|---|
| Cross-Sectional Rank | 25 | Layer 1 |
| Flow | 20 | Layer 2 |
| Options + GEX | 20 | Layers 3a + 3b |
| Holdings-Weighted Rotation | 15 | Layer 4 |
| Macro Fit | 10 | Layer 5 |
| News Confirmation | 10 | (downgraded from 88) |
| **Threshold** | **60** | — |

**Any 3 of {rank, flow, options, rotation} can clear the gate independently.
News alone cannot.** That is the architectural delta.

### Regime-conditional weighting (Lo)

Static factor weights ignore that momentum half-life and signal efficacy
change with the volatility regime. `regime_engine.py` classifies VIX into
LOW / MID / HIGH terciles vs. trailing 1Y and applies a regime-specific
weight matrix on top of the scorer.

| Regime | Trigger | Tilt |
|---|---|---|
| LOW_VOL | VIX < 33%ile | Lean into momentum: Rank 30, Flow 22 |
| MID_VOL | 33–67%ile | Default budget |
| HIGH_VOL | VIX > 67%ile | Lean into options/dealer flow: Options 28, Macro 12 |

Plus the Antonacci absolute-momentum gate: in `RISK_OFF` (SPY < 200MA AND
SPY 3M return < 3M T-bill), **only defensives** (TLT, GLD, SHV, AGG, TIP)
can publish long signals.

## What v1 modules are deprecated

See [DEPRECATION_NOTICE.md](DEPRECATION_NOTICE.md) for the full list. Headlines:

- **`self_improve.py` — disabled.** This was an LLM-driven loop that proposed
  weight tweaks against historical P&L and "auto-rolled back if PnL drops
  > 2pp." That's automated p-hacking. Replacement: every parameter change
  passes `walk_forward()` + `deflated_sharpe.gate()`.
- **`scorer.py` — replaced** by `scorer_v2.py`.
- **`signal_fusion.py` — replaced** by `azalyst_alpha/fusion.py`.
- **`price_scanner.py` — replaced** by `cross_sectional_ranker.py`.
- **`constituent_analyzer.py` — replaced** by `holdings_weighted_rotation.py`.
- **`news_fetcher.py` — kept**, but its output is capped at 10/100 in scoring.

## How to run

```powershell
# install
pip install -r requirements.txt

# detect today's regime
python -m azalyst_alpha.regime_engine

# full daily pipeline (regime -> 6 layers -> scoring -> dedup -> sizing -> tearsheet)
python -m azalyst_alpha.fusion

# walk-forward validation (run before any parameter change)
python -m azalyst_alpha.backtester

# DSR gate
python -m azalyst_alpha.deflated_sharpe
```

Output lands in `data/tearsheet.md`, `data/leaderboard_latest.csv`, and
`data/paper_trader.db`.

## Dashboard

The GitHub Pages dashboard at <https://gitdhirajsv.github.io/Azalyst-ETF-Intelligence/>
now shows:

- **Regime banner** — risk state, vol regime, VIX percentile, SPY vs 200MA, 3M
  excess vs T-bill, active weight matrix.
- **Factor Breakdown panel** — for the top published signal: per-layer points
  (Rank/25, Flow/20, Options+GEX/20, Rotation/15, Macro/10, News/10) and
  whether the signal cleared the 60-pt v2 gate.
- **v2 Threshold** — 60/100 (down from v1's 62, with rebalanced budget).

## Performance targets

Stated up front so they can be enforced.

| Metric | Target | Pause floor |
|---|---|---|
| Annualized return (gross) | 25–40% | < 12% |
| Sharpe (after fees) | > 1.4 | < 0.8 |
| Max drawdown | < 18% | > 25% |
| Win rate | 55–65% | < 50% |
| Deflated Sharpe (rolling 6M) | > 0.5 | < 0.4 |

If DSR drops below 0.4 over any 6-month rolling window, **the strategy
auto-pauses** pending re-validation. This is non-negotiable.

## What's still honest about the limits

- yfinance is unofficial. Yahoo can rate-limit or break it; mitigation is a
  one-line swap to Stooq or Tiingo free tier.
- Free option chains are EOD-quality. Intraday GEX flips are missed — fine
  for an EOD strategy, would matter for intraday.
- News depth on free tier is genuinely thin vs. paid Bloomberg. That's why
  it's downgraded to a 10-point confirmation, not a gate.

## Documents

- [STRATEGY.md](STRATEGY.md) — formal strategy document, investor-letter
  format. The contract.
- [DEPRECATION_NOTICE.md](DEPRECATION_NOTICE.md) — what to remove from v1.

## Acknowledgments

The v1 architecture concepts (multi-engine fusion, COT integration,
dashboard scaffolding) are kept. The board members above informed every v2
design decision, even where the room disagreed (López de Prado vs. an
LLM-driven self-improvement loop — López de Prado won, decisively).

Open-source dependencies: yfinance, pandas, numpy, scipy. That is the entire
production stack. Total monthly data cost: **$0**.

---

**Status:** v2 alpha stack shipped. Paper-trading gate active prior to live
capital. Hold the targets above to me in writing.

*License: MIT.*
