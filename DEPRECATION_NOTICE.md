# Deprecation Notice — Upstream Modules to Disable

When integrating Azalyst-Alpha-Free into the upstream `Azalyst-ETF-Intelligence`
repo, the following modules must be disabled or replaced:

## 1. `self_improve.py` — DELETE / DISABLE

**Why:** This is an LLM-driven loop that proposes weight tweaks against
historical PnL, applies them, and "auto-rolls back if PnL drops > 2pp."

This is automated p-hacking. With sufficient trials it will inevitably find
parameter sets that look profitable in-sample and fail out-of-sample. The
2pp rollback rule does not protect against this — it just selects for noise
that hasn't yet expired.

**Replacement:** Parameter changes go through `backtester.walk_forward()` +
`deflated_sharpe.gate()`. Any change that does not pass DSR ≥ 0.5 is rejected.
No automated edits to live config.

**Action:**
```python
# In daily_improve.yml or equivalent:
# Remove the schedule. Or:
# Replace the script body with: print("self_improve.py is deprecated; see STRATEGY.md §4")
```

## 2. `scorer.py` — REPLACE with `scorer_v2.py`

**Why:** The upstream scorer allocates 88/100 to news factors and caps
cross-engine input at 12 pts. A pure tape-led move cannot mathematically
clear the 62-pt publication threshold without press coverage. By the time
press coverage arrives, the move is over.

**Replacement:** `azalyst_alpha.scorer_v2` (Rank 25 / Flow 20 / Options+GEX 20
/ Rotation 15 / Macro 10 / News 10, threshold 60).

## 3. `news_fetcher.py` + RSS classifier — DOWNGRADE, don't delete

**Why:** News still has confirmation value (max 10 pts in v2). But it is no
longer a gate, and the seven-RSS-feeds-per-sector + ~1,030-keywords machinery
is now over-engineered for its budget.

**Action:** Keep RSS ingestion, disable the bursty alert path. Pipe its
output as `news_score` into `fusion.run()` keyword arg.

## 4. `signal_fusion.py` — REPLACE with `fusion.py`

**Why:** Upstream fusion uses static 0.40/0.25/0.20/0.15 weights and only
redistributes when COT is missing. v2 uses regime-conditional weight matrix
(LOW_VOL / MID_VOL / HIGH_VOL) and routes through the publish gate, dedup,
absolute-momentum gate, and sizing pipeline.

## 5. `price_scanner.py` — REPLACE with `cross_sectional_ranker.py`

**Why:** Upstream uses per-asset z-score with `Z_THRESHOLD = 1.8`. v2 uses
universe-wide rank residualized vs. SPY. The former lags by 2–3 days; the
latter generates the leaderboard view directly.

## 6. `constituent_analyzer.py` — REPLACE with `holdings_weighted_rotation.py`

**Why:** Equal-weights top-10 holdings. Misses concentrated mega-cap-driven
moves on IGV (MSFT/ORCL ~16%) and SOXX (NVDA/AVGO ~18%). v2 weights by AUM
share and uses fraction-of-weight (not fraction-of-count) thresholds.

## 7. `paper_trader.py` (upstream) — REPLACE with v2

**Why:** Upstream simulates fills without spread/impact and without
persistence. v2 adds half-spread + sqrt-rule market impact and SQLite trade log.

---

## Modules to Keep

- `cot_fetcher.py` — keep, useful for commodity ETFs (SLV, GLD, USO, UNG).
  Just feed its output into v2 fusion as `gex_score`-equivalent for COT-eligible
  ETFs.
- `etf_mapper.py` — keep, but extend the holdings table per `holdings_weighted_rotation.py`.
- `backtester.py` (upstream) — replace with v2; v2 includes purged k-fold.
- `risk_engine.py` (upstream Fama-French attribution) — keep as post-trade analysis.
