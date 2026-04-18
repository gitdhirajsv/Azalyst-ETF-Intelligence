# Azalyst Global ETF - 90 Day Execution Plan

## North Star

Build a global, explainable ETF intelligence system that:

- ranks the best ETF candidates across the full tracked universe
- explains why each ETF is preferred now
- proves edge net of costs against benchmarks
- maintains accessible usability while delivering institutional-grade analytics

## What We Are Building

Azalyst is designed to operate as:
It should become:

- a global macro-event to ETF routing engine
- a transparent ETF selector with ranked alternatives
- a disciplined research and paper-trading platform with audit trails

## Current Priority Decisions

- Global-first product, not India-first
- Unified ETF ranking, not bucket-first routing
- Proof of edge before advanced AI upgrades
- Execution realism before marketing claims

## Success Criteria By Day 90

- Every signal produces a ranked ETF list with a documented selection reason
- Backtests run across multiple market regimes with transaction costs included
- Paper-trading reports compare performance against benchmark ETFs net of costs
- Position sizing uses observed edge or conservative risk budgets, not assumed Kelly math
- Dashboard and reports show top-ranked ETFs globally, with market-specific alternatives only as execution support

## Phase 0 - Already Underway

- Replace first-ETF selection with unified ranking
- Remove India-vs-global recommendation split from the primary selection path
- Update dashboard/report payloads to carry top-ranked ETFs and execution markets

## Phase 1 - Truth Machine (Days 1-21)

Goal: make every performance claim measurable.

Build:

- historical replay engine for stored signals
- benchmark suite by sector and by portfolio
- transaction-cost model
- slippage model by ETF liquidity bucket
- regime tagging: risk-on, inflation shock, crisis, easing cycle, commodity spike

Acceptance checks:

- replay one full year of signals end to end
- output gross return, net return, alpha, Sharpe, Sortino, max drawdown, hit rate, profit factor
- compare against at least `SPY`, `VT`, `AGG`, and a sector benchmark when relevant

## Phase 2 - Signal Quality Upgrade (Days 22-42)

Goal: stop treating text noise as conviction.

Build:

- directional sentiment for sector catalysts
- word-boundary keyword matching
- fuzzy dedup across paraphrased headlines
- full-text ingestion instead of title-only dependence
- source credibility tiers and recency decay smoothing

Acceptance checks:

- "oil surges" and "oil crashes" no longer score the same
- near-duplicate articles do not inflate conviction
- confidence components move smoothly instead of in step jumps

## Phase 3 - ETF Selection Engine (Days 43-63)

Goal: make ETF choice itself a source of edge.

Build:

- ETF ranking inputs: liquidity, spread proxy, cost, purity, diversification, stability
- market access alternatives separated from core ranking
- benchmark-aware ETF choice by sector
- fallback logic for thin or inaccessible ETFs

Acceptance checks:

- every recommendation has a primary ETF and at least one alternative when available
- ranking output explains the choice in plain language
- thin, tactical, or structurally noisy products stop dominating core recommendations

## Phase 4 - Risk And Execution Upgrade (Days 64-84)

Goal: make the book survivable in the real world.

Build:

- empirical sizing or capped risk-budget model
- signed correlation handling
- better factor mapping for commodities, gold, rates, crypto, and regional equity sleeves
- gap-risk aware stop logic
- time-based and drift-based rebalance rules

Acceptance checks:

- portfolio concentration, stress, and drawdown controls reflect actual exposure
- stop-loss assumptions acknowledge open-gap failure risk
- sizing falls back safely when edge is not yet measured

## Phase 5 - Product Hardening (Days 85-90)

Goal: package the engine as a credible product, not a code experiment.

Build:

- clear methodology page
- model limitations page
- benchmark and track-record page
- versioned change log for signal/scoring logic
- global positioning copy across dashboard and docs

Acceptance checks:

- a new user can understand what the model does, why it selected an ETF, and what it still does not know

## Metrics To Track Weekly

- signal-to-trade conversion rate
- win rate net of costs
- average return per trade net of costs
- max drawdown
- benchmark-relative alpha
- false-positive rate by sector
- recommendation turnover
- percent of signals with clear primary ETF explanation

## What Not To Do In The Next 90 Days

- maintain strict compliance regarding performance claims
- do not add heavy ML before validation exists
- ensure position sizing models rely strictly on empirical edge inputs
- do not optimize only for paper gains without spread/slippage
- do not overfit to India-specific flows if the goal is a global product

## Practical Build Order

1. Validation and benchmark layer
2. Cost and slippage model
3. Signal quality fixes
4. ETF ranking and execution routing
5. Risk and sizing rebuild
6. Documentation and positioning cleanup

## Definition Of Done

Azalyst becomes credible when it can say:

"Here is the signal, here is the best ETF globally, here is why it won, here is the realistic cost to trade it, and here is how the strategy has performed versus benchmarks across different regimes."
