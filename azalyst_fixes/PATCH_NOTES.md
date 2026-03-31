# Azalyst ETF Intelligence — Patch Notes

## Files Changed

Replace the following files in the repository root with the versions in this folder:

| File | Status |
|---|---|
| `llm_analyzer.py` | **NEW** — was missing, caused ImportError on startup |
| `config.py` | Updated — added LLM config vars |
| `state.py` | Fixed — `latest_ts` now deserialized from JSON |
| `scorer.py` | Fixed — source tier matching + recency default |
| `news_fetcher.py` | Fixed — article age filter added |
| `classifier.py` | Fixed — `latest_ts` preserved in merged signals |
| `paper_trader.py` | Fixed — MAX_POSITIONS=6, single USD/INR fetch |
| `generate_dashboard.py` | Fixed — parallel market fetch, legacy breakdown display |
| `.env.example` | Updated — added LLM and MAX_ARTICLE_AGE_DAYS vars |

---

## Fix Summary

### 🔴 Correctness

**1. `llm_analyzer.py` — missing module (startup crash)**
- `azalyst.py` imported `from llm_analyzer import LLMAnalyzer, create_llm_analyzer`
- Module did not exist → `ImportError` on every run
- Created full stub: disabled by default, activates when `NVIDIA_API_KEY` is set

**2. `state.py` — `latest_ts` not deserialized**
- `_load()` only converted `sent_at` back to `datetime`; `latest_ts` remained a string
- `scorer.py` `_factor_recency()` called `now - latest_ts` → `TypeError` on loaded signals
- The broad `except` masked the bug and returned `5.0` free points
- Fix: `_parse_dt()` helper now deserializes both fields on load

**3. `classifier.py` — merged signals lost `latest_ts`**
- `_merge_correlated_signals()` only kept `latest_ts` from the first signal
- If the second constituent was more recent, the merged signal scored stale recency
- Fix: `_max_ts()` helper takes the latest timestamp across both signals

**4. `paper_trader.py` — `MAX_POSITIONS` was 8, spec says 6**
- README, system prompt, and paper trading rules all specify max 6 open positions
- Code had `MAX_POSITIONS = 8` — corrected to 6

### 🟡 Signal Quality

**5. `scorer.py` — source tier matching was fragile**
- `"ap "` (trailing space) missed `"AP News"`, `"Associated Press"`
- `"ft "` could false-positive on unrelated sources
- Fix: replaced with regex word-boundary matching via `_source_in_tier()`

**6. `scorer.py` — recency default was `5.0` for missing timestamps**
- Signals with no `latest_ts` received free recency points
- Fix: default changed to `0.0`

**7. `news_fetcher.py` — stale evergreen articles inflated signals**
- Articles from 2022/2023 (e.g. "LimeWire AI Studio Review 2023") were being
  classified and counted toward signal confidence
- Fix: articles older than `MAX_ARTICLE_AGE_DAYS` (default 7) are dropped
  before classification. Configurable via `.env`

### 🟠 Performance

**8. `generate_dashboard.py` — market snapshot was sequential**
- 13 Yahoo Finance API calls in a loop → 30–50 s on cold CI runners
- Fix: `ThreadPoolExecutor` parallelizes all 13 calls; wall-clock time ≈ single timeout

**9. `paper_trader.py` — USD/INR fetched once per position in MTM**
- `get_current_price_inr` called `fetch_usd_to_inr()` inside the position loop
- Fix: rate fetched once before the loop; passed as optional arg to `get_current_price_inr`

### 🔵 UX

**10. `generate_dashboard.py` — legacy signal cards showed zeroed score bars**
- State records saved before breakdown tracking showed all-zero components
- Dashboard looked broken for these entries
- Fix: `_breakdown_has_data()` detects legacy records; headline and label updated accordingly

---

## Suggested Commit Message

```
fix: 10 correctness/quality/perf fixes (llm stub, state ts, MAX_POSITIONS, source tiers, age filter, parallel dash)

- Add llm_analyzer.py stub — fixes ImportError on startup
- config.py: add LLM_ENABLED, LLM_MODEL, NVIDIA_API_KEY, LLM_ANALYSIS_INTERVAL
- state.py: deserialize latest_ts from JSON (was causing silent TypeError in recency scoring)
- classifier.py: preserve latest_ts across merged signals (_max_ts helper)
- scorer.py: fix source tier regex matching; recency default 5→0
- news_fetcher.py: drop articles older than MAX_ARTICLE_AGE_DAYS (default 7d)
- paper_trader.py: MAX_POSITIONS 8→6; single USD/INR fetch per MTM cycle
- generate_dashboard.py: parallel market snapshot; legacy breakdown label
- .env.example: add LLM + MAX_ARTICLE_AGE_DAYS vars
```
