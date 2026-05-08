# Azalyst-ETF-Alpha — Strategy Document

**Version:** 1.0
**Author:** CTO / PM
**Status:** Production-ready, paper-traded prior to capital deployment
**Investment universe:** ~120 US-listed sector / thematic / regional / fixed-income ETFs

---

## 1. Investment Thesis

ETF leaderboards (5D / 20D / 3M risk-adjusted return rankings) telegraph
sector rotation 1–3 sessions before the move is consensus. The market does not
adequately price (a) **dealer gamma positioning**, (b) **ETF primary-market flows**,
or (c) **cross-asset macro confirmation** into single-name sector ETFs. A
multi-factor overlay on the leaderboard, gated by regime, sized to vol-target,
and protected by trailing stops, captures persistent excess return over SPY.

This is **not** a news-driven strategy. The previous Azalyst architecture
weighted news factors at 88/100 in its publication scorer. We have rebalanced
to make news a *confirmation* (max 10 pts), not a gate.

---

## 2. Signal Architecture

### Six factor layers, regime-conditional weighting

| # | Factor | Pts (mid-vol) | Source | Captures |
|---|---|---|---|---|
| 1 | Cross-Sectional Rank | 25 | yfinance EOD | Universe leadership; risk-adj 5D/20D/60D |
| 2 | ETF Flow | 20 | yfinance + ETF.com | Primary-market creations/redemptions |
| 3 | Options Tape + GEX | 20 | yfinance chains + BS | Dealer gamma, IV rank, skew, sweeps |
| 4 | Holdings-Weighted Rotation | 15 | Issuer pages | Top-holding consensus weighted by AUM |
| 5 | Macro Fit | 10 | yfinance + FRED | Cross-asset regime confirmation |
| 6 | News Confirmation | 10 | RSS / GDELT | Bonus only — not gating |
| **Total** | | **100** | | |

**Publish threshold:** 60 pts. Any 3 of {rank, flow, options, rotation} can clear
the gate independently. News alone cannot.

### Regime-conditional re-weighting (Lo)

| Regime | Trigger | Rebalanced budget |
|---|---|---|
| LOW_VOL | VIX < 33%ile 1Y | Rank 30, Flow 22, Options 18, Rotation 15, Macro 8, News 7 |
| MID_VOL | 33–67%ile | Default (above) |
| HIGH_VOL | VIX > 67%ile | Rank 18, Flow 18, Options 28, Rotation 12, Macro 12, News 12 |

Rationale: in trending tape (LOW_VOL), cross-sectional momentum is dominant.
In dispersion / panic (HIGH_VOL), options and dealer flows lead; momentum
mean-reverts.

---

## 3. Risk Architecture (the user's mandate)

> "Risk factor drawdown all can be maintained by capping means buying n trailing"

Three layers, applied in this order at every bar:

### 3.1 Position-level
- **Vol-target sizing** — each position contributes equal annualized vol to the
  book. Notional ∝ 1/σ. Max 15% of book per position.
- **Capped Kelly** option for high-confidence signals — 1/4-Kelly cap.
- **ATR(14) chandelier trailing stop** at 2.5× ATR from peak.
- **Hard stop** at −8% from entry.

### 3.2 Book-level
- **Max gross leverage:** 1.5×
- **Max net long:** 1.0×
- **Max single-cluster weight:** 1 position per correlation cluster (kills SOXX+SMH double-count)
- **Max positions:** 8

### 3.3 Portfolio-level
- **Drawdown circuit breaker** at −15% from equity peak: flatten everything
  except defensives, 7-day cool-down before new longs.
- **Vol-target rebalance:** if 20D realized vol > 1.4× target → deleverage; if < 0.7× → re-leverage.
- **Antonacci absolute-momentum gate:** in RISK_OFF regime (SPY < 200MA AND
  SPY 3M return < 3M T-bill), only defensives (TLT, GLD, SHV, AGG, TIP) can
  publish long signals.

---

## 4. Validation (López de Prado discipline)

Every change to weights, thresholds, or new signal layers must pass:

1. **Walk-forward backtest** over ≥ 3 years. No look-ahead. Train on rolling
   252-day window, test on next 63 days, roll forward.
2. **Purged k-fold CV** (k=5, embargo=5 days) — checks regime stability of edge.
3. **Deflated Sharpe Ratio** ≥ 0.5 — adjusted for trial inflation, return skew,
   excess kurtosis. Below this threshold, a "discovered edge" is statistically
   indistinguishable from the maximum noise Sharpe across all backtests we ran.

**Hard rule: no parameter changes via LLM-driven optimization against past PnL.**
The upstream `self_improve.py` is deprecated for this reason — it is, in the
words of board member López de Prado, "p-hacking with a feedback loop." All
parameter changes go through the validation pipeline above and a code review.

---

## 5. Execution

- **Cadence:** end-of-day signal generation, next-open execution.
- **Slippage model:** half-spread (5 bps default) + market impact 0.10 ×
  √(notional / 30D ADV).
- **Capital model:** $100k starting equity (paper). Production: scaled but
  same architecture.
- **Position log:** SQLite at `data/paper_trader.db`. Trades, positions, equity.

---

## 6. Performance Targets

These are explicit goals, not promises. Track against them weekly.

| Metric | Target | Unacceptable |
|---|---|---|
| Annualized return | 25–40% (gross of fees) | < 12% |
| Sharpe (after fees) | > 1.4 | < 0.8 |
| Max drawdown | < 18% | > 25% |
| Win rate | 55–65% | < 50% |
| Profit factor | > 1.6 | < 1.3 |
| Turnover | 4–8x annually | > 12x (over-trading) |

If realized DSR drops below 0.4 over any 6-month rolling window, **strategy is
paused** pending a full re-validation.

---

## 7. What Is Explicitly Out of Scope

- Single-name equity selection
- Crypto / FX / rates outright (only via ETFs in universe)
- Intraday execution (signals are EOD; cron schedule reflects this)
- Options structures (we use options data as a signal; we trade the underlying ETF)
- Discretionary overrides — every signal published is acted on or none are

---

## 8. Operational Runbook

```powershell
# Daily run (post-close)
cd C:\Users\Administrator\Documents\Azalyst-Alpha-Free
python -m azalyst_alpha.fusion

# Walk-forward validation (run before deploying any change)
python -m azalyst_alpha.backtester

# DSR gate on a new strategy variant
python -m azalyst_alpha.deflated_sharpe

# Smoke test: did we catch the user's leaderboard movers?
python tests\smoke_test.py
```

Output: `data/tearsheet.md` (markdown daily report), `data/leaderboard_latest.csv`,
`data/paper_trader.db`.

---

## 9. Module Inventory

| Module | Role |
|---|---|
| `cross_sectional_ranker.py` | Layer 1 — universe ranking |
| `flow_engine.py` | Layer 2 — ETF flow proxy |
| `gex_engine.py` | Layer 3a — dealer gamma (SpotGamma replacement) |
| `options_tape.py` | Layer 3b — unusual options activity |
| `holdings_weighted_rotation.py` | Layer 4 — weighted constituent rotation |
| `macro_overlay.py` | Layer 5 — cross-asset regime fit |
| `cluster_dedup.py` | Layer 7 — correlation clustering |
| `regime_engine.py` | Lo + Antonacci regime gate |
| `scorer_v2.py` | Replaces upstream news-heavy scorer |
| `position_sizer.py` | Vol-target + Kelly + ERC |
| `risk_manager.py` | Trailing stops + circuit breakers |
| `portfolio_constructor.py` | End-to-end signal → book |
| `backtester.py` | Walk-forward + purged k-fold |
| `deflated_sharpe.py` | DSR gate (López de Prado) |
| `paper_trader.py` | SQLite paper exec with frictions |
| `report.py` | Daily tearsheet |
| `fusion.py` | Daily orchestrator |

---

## 10. Honest Risks

1. **yfinance is unofficial.** Yahoo can rate-limit or break the endpoint.
   Mitigation: Stooq + Tiingo fallback (one-line swap in download helpers).
2. **Free options chains are EOD-quality.** We miss intraday GEX flips.
   Acceptable for an EOD strategy; would matter for intraday.
3. **News layer is genuinely thin** vs. paid Bloomberg. We've explicitly
   downgraded news to 10 pts to reflect this.
4. **Overfitting risk.** This document is itself a backtest set. Every
   parameter above must be validated walk-forward; the DSR gate exists
   precisely because we know we'd otherwise self-deceive.
5. **Regime-shift risk.** If the macro tape regime-shifts faster than our
   weight matrix updates (e.g. rate shock), the LOW_VOL/HIGH_VOL bands may
   misclassify briefly. The trailing-stop layer is the backstop.

---

## 11. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| v1.0 | Replace upstream scorer (88-pt news, 12-pt cross-engine) | Mathematically blocks tape-led movers |
| v1.0 | Add VIX-regime weight matrix (Lo) | Static weights ignore regime-conditional signal efficacy |
| v1.0 | Add absolute-momentum gate (Antonacci) | Long-only relative momentum has no defense in 2022-style drawdowns |
| v1.0 | Holdings weighted by AUM, not equal-weight (Gray) | Concentrated ETFs (IGV, SOXX) require weight-aware conviction |
| v1.0 | Deprecate `self_improve.py` (López de Prado) | LLM-driven PnL optimization = automated p-hacking |
| v1.0 | Cluster dedup before sizing (McElligott implicit) | SOXX/SMH/SOXL = one bet, not three |
| v1.0 | DSR ≥ 0.5 gate before deploying any variant | Prevents trial-inflation false positives |
