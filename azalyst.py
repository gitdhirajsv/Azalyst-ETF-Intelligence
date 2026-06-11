"""
AZALYST ETF INTELLIGENCE — CORE ENGINE
Macro hedge fund-grade global news + paper trading track record system
+ Aladdin-grade risk engine (correlation, benchmark, vol-sizing, rebalancing, stress testing)
"""

import time
import logging
import schedule
import traceback
from datetime import datetime, timezone

from news_fetcher       import NewsFetcher
from classifier         import SectorClassifier
from scorer             import ConfidenceScorer
from etf_mapper         import ETFMapper
from reporter           import DiscordReporter
from state              import SignalStateManager
from paper_trader       import PaperPortfolio
from portfolio_reporter import PortfolioReporter
from config             import Config
from quant_fetcher      import QuantFetcher

# ── Multi-engine alpha stack (legacy v1; v2 stack lives in azalyst_alpha/) ──
try:
    from price_scanner        import PriceScanner, ETF_TO_SECTOR
    from constituent_analyzer import ConstituentAnalyzer
    from signal_fusion        import SignalFuser
    _MULTI_ENGINE_AVAILABLE = True
except Exception as _imp_err:
    _MULTI_ENGINE_AVAILABLE = False
    PriceScanner = ConstituentAnalyzer = SignalFuser = None
    ETF_TO_SECTOR = {}
ReverseResearcher = None  # removed in cleanup; legacy "explain mover" feature

# ── REVIEW BOARD CHANGE: COT positioning engine ─────────────────────────────
try:
    from cot_fetcher import COTFetcher
    _COT_AVAILABLE = True
except ImportError:
    COTFetcher = None
    _COT_AVAILABLE = False

# ── REVIEW BOARD CHANGE: External shock circuit breaker ─────────────────────
try:
    from risk_engine import compute_trend_adjustment, external_shock_check, CIRCUIT_BREAKER_ACTIVE
    _RISK_ADVANCED = True
except ImportError:
    compute_trend_adjustment = external_shock_check = None
    CIRCUIT_BREAKER_ACTIVE = False
    _RISK_ADVANCED = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("azalyst.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("AZALYST")

BANNER = """
+--------------------------------------------------------------+
|   AZALYST  ETF INTELLIGENCE + PAPER TRADING SYSTEM          |
|   Macro Fund Edition  .  Track Record Engine                 |
|   + Aladdin Risk Engine (Institutional Analytics)             |
+--------------------------------------------------------------+
"""


def _get_5d_return(ticker: str):
    """Return the 5-session price return for ticker, or None on failure."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="15d")
        if hist.empty:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 6:
            return None
        return float(closes.iloc[-1] / closes.iloc[-6] - 1)
    except Exception:
        return None


# Volatility regime thresholds (live VIX). Below ELEVATED = trade normally.
# ELEVATED = only highest-conviction longs allowed (the market is shaky).
# EXTREME  = no new longs at all; only inverse/bearish entries make sense.
VIX_ELEVATED = 25.0
VIX_EXTREME  = 30.0

# Cold-start seeder: max positions to open in one startup pass. Staging by
# conviction beats dumping every stored signal into the book simultaneously.
MAX_SEED_POSITIONS = 2


def _market_regime():
    """Return (vix_level, regime) where regime is NORMAL / ELEVATED / EXTREME.

    A long book has no business adding risk into a spiking-VIX, risk-off tape.
    This is the regime awareness the entry path was missing — the 6 startup-seed
    longs were opened straight into a falling market with VIX ramping."""
    vix = 20.0
    try:
        if _RISK_ADVANCED and external_shock_check is not None:
            vix = float(external_shock_check().get("indicators", {}).get("vix", 20.0))
    except Exception:
        vix = 20.0
    if vix >= VIX_EXTREME:
        return vix, "EXTREME"
    if vix >= VIX_ELEVATED:
        return vix, "ELEVATED"
    return vix, "NORMAL"


def _regime_size_multiplier(regime: str) -> float:
    """Scale long size to the volatility regime instead of blocking the entry.

    This is the VOLATILITY dampener — distinct from the DIRECTION filter below.
    When the market is volatile but NOT falling, longs are still OK, just smaller:
    NORMAL = full size, ELEVATED = 0.6x, EXTREME = 0.4x. Bearish signals route to
    inverse ETFs separately and are unaffected by this."""
    if regime == "EXTREME":
        return 0.4
    if regime == "ELEVATED":
        return 0.6
    return 1.0


def _market_downturn():
    """Return (in_downturn: bool, detail: str) for the broad market (SPY).

    DIRECTION filter, separate from the VIX volatility dampener. A downturn is a
    falling market — SPY below its 50-day MA (sustained downtrend) OR SPY down
    >3% over the last 5 sessions (sharp drop). When the market is in a downturn
    it is NOT ok to open longs: capital should go to inverse ETFs (the short
    side), not long ETFs. High volatility alone is not a downturn."""
    try:
        import yfinance as yf
        closes = yf.Ticker("SPY").history(period="3mo")["Close"].dropna()
        if len(closes) < 50:
            return False, "insufficient SPY history — longs allowed"
        last = float(closes.iloc[-1])
        ma50 = float(closes.rolling(50).mean().iloc[-1])
        ret5 = float(closes.iloc[-1] / closes.iloc[-6] - 1) if len(closes) >= 6 else 0.0
        below_ma   = last < ma50
        sharp_drop = ret5 <= -0.03
        if below_ma or sharp_drop:
            why = []
            if below_ma:
                why.append(f"SPY {last:.0f} < 50dMA {ma50:.0f}")
            if sharp_drop:
                why.append(f"SPY 5d {ret5 * 100:+.1f}%")
            return True, "; ".join(why)
        return False, f"SPY {last:.0f} >= 50dMA {ma50:.0f}, 5d {ret5 * 100:+.1f}%"
    except Exception as exc:
        # Fail open — a data hiccup should not silently halt all long entries.
        return False, f"downturn check failed ({exc}) — longs allowed"


def _select_etf_for_trade(signal: dict) -> tuple:
    """Pick the highest-ranked ETF from the unified recommendation set."""
    etf_recs = signal.get("etf_recommendations", {})

    primary = etf_recs.get("primary")
    if primary:
        return primary, primary.get("platform", "Broker")

    ranked = etf_recs.get("ranked", [])
    if ranked:
        etf = ranked[0]
        return etf, etf.get("platform", "Broker")

    # Legacy fallback for older state records.
    global_etfs = etf_recs.get("global", [])
    india_etfs = etf_recs.get("india", [])
    if global_etfs:
        etf = global_etfs[0]
        return etf, etf.get("platform", "Global Broker")
    if india_etfs:
        etf = india_etfs[0]
        return etf, etf.get("platform", "Indian Broker")
    return None, None


def run_intelligence_cycle(
    fetcher, classifier, scorer, mapper,
    reporter, state, portfolio, port_reporter, quant_fetcher, cfg,
    price_scanner=None, constituent_analyzer=None,
    reverse_researcher=None, signal_fuser=None,
):
    log.info("--- Intelligence cycle starting ---")
    try:
        # ── 1. NEWS engine (lagging, deep narrative) ─────────────────────────
        articles = fetcher.fetch_all()
        log.info(f"Fetched {len(articles)} articles")

        news_signals_raw = classifier.classify_articles(articles) if articles else []
        # Pre-score so signal_fusion can use confidence
        for s in news_signals_raw:
            s["confidence"] = scorer.score(s, articles)
            s["confidence_breakdown"] = scorer.breakdown(s, articles)

        # ── 2. PRICE engine (leading, momentum/breakouts) ────────────────────
        price_signals: list = []
        if price_scanner is not None:
            try:
                raw = price_scanner.scan()
                price_signals = price_scanner.aggregate_by_sector(raw)
                log.info("Price engine: %d sector-level signals", len(price_signals))
            except Exception as exc:
                log.warning("Price engine failed: %s", exc)

        # ── 3. CONSTITUENT engine (top holdings rotation) ────────────────────
        constituent_signals: list = []
        if constituent_analyzer is not None:
            try:
                rots = constituent_analyzer.scan()
                constituent_signals = [r.to_signal_dict() for r in rots]
                log.info("Constituent engine: %d rotation signals", len(constituent_signals))
            except Exception as exc:
                log.warning("Constituent engine failed: %s", exc)

        # ── 4. Reverse research for unexplained price movers ────────────────
        if reverse_researcher is not None and price_signals:
            news_sectors = {s["sector_id"] for s in news_signals_raw}
            unexplained = [p for p in price_signals if p["sector_id"] not in news_sectors]
            if unexplained:
                log.info("Reverse-researching %d unexplained price movers...", len(unexplained))
                try:
                    reverse_researcher.explain(unexplained)
                except Exception as exc:
                    log.warning("Reverse researcher failed: %s", exc)

        # ── 3.5 COT engine (institutional positioning) ─────────────────────
        # REVIEW BOARD CHANGE: 9-0 vote to add COT as 4th engine
        cot_signals: list = []
        if _COT_AVAILABLE:
            try:
                cot = COTFetcher(enabled=True)
                cot_results = cot.scan_all()
                cot_signals = [cot.to_azalyst_signal(r) for r in cot_results]
                log.info("COT engine: %d positioning signals", len(cot_signals))
            except Exception as exc:
                log.warning("COT engine failed: %s", exc)

        # ── 5. FUSE signals across all 4 engines ────────────────────────────
        if signal_fuser is not None:
            fused = signal_fuser.fuse(
                news_signals_raw, price_signals, constituent_signals, cot_signals
            )
            log.info(
                "Fused: %d signals (TierA=%d TierB=%d TierC=%d divergent=%d)",
                len(fused),
                sum(1 for f in fused if f.consensus_tier == "A"),
                sum(1 for f in fused if f.consensus_tier == "B"),
                sum(1 for f in fused if f.consensus_tier == "C"),
                sum(1 for f in fused if f.divergent),
            )
            sector_signals = [f.to_dict() for f in fused]
        else:
            sector_signals = news_signals_raw

        # ── 6. Score (now multi-engine aware via Factor 6) ──────────────────
        scored_signals = []
        for signal in sector_signals:
            score = scorer.score(signal, articles)
            signal["confidence"] = score
            signal["confidence_breakdown"] = scorer.breakdown(signal, articles)
            if score >= cfg.CONFIDENCE_THRESHOLD:
                scored_signals.append(signal)

        new_signals = state.filter_new_or_updated(scored_signals)
        log.info(f"{len(new_signals)} new/updated signals after multi-engine scoring")

        # Volatility regime (size dampener) + market direction (downturn = no longs).
        # Both computed once per cycle and applied to every long entry below.
        cycle_vix, cycle_regime = _market_regime()
        cycle_downturn, cycle_downturn_detail = _market_downturn()
        log.info("Market regime: VIX %.1f → %s", cycle_vix, cycle_regime)
        log.info(
            "Market direction: %s (%s)",
            "DOWNTURN — longs off, shorts only" if cycle_downturn else "not a downturn — longs allowed",
            cycle_downturn_detail,
        )

        for signal in new_signals:
            etf_recs = mapper.get_etfs(signal["sectors"], signal)
            signal["etf_recommendations"] = etf_recs
            is_update = state.is_update(signal)

            reporter.send_report(signal, is_update=is_update)
            state.record_signal(signal)
            time.sleep(1)

            # ======== REVIEW BOARD CHANGE: Graduated trend adjustment ========
            # Replaces binary Quant Blocker with confidence/size multipliers
            # and adds external shock circuit breaker check
            if cfg.PAPER_TRADING_ENABLED and not is_update:
                severity   = signal.get("severity", "LOW")
                confidence = signal.get("confidence", 0)
                direction  = signal.get("direction", "BULLISH")

                # External shock check — don't trade if cross-asset stress is extreme
                if _RISK_ADVANCED and CIRCUIT_BREAKER_ACTIVE:
                    log.warning("Trade skipped — external shock circuit breaker active")
                    continue

                if severity in ("HIGH", "CRITICAL") or confidence >= 75:

                    # DIRECTION GATE: BEARISH signals must route to inverse ETFs, never long
                    if direction == "BEARISH":
                        if severity in ("HIGH", "CRITICAL"):
                            bearish_recs = mapper.get_etfs(["bearish_macro"], signal)
                            b_etf = bearish_recs.get("primary")
                            b_platform = b_etf.get("platform", "Broker") if b_etf else None
                            if b_etf and b_platform:
                                log.info(
                                    "BEARISH signal -> inverse ETF entry: %s (sector=%s conf=%d)",
                                    b_etf.get("ticker"), signal.get("sector_label"), confidence,
                                )
                                b_entry = portfolio.enter_position(signal, b_etf, b_platform, is_hedge=True)
                                if b_entry and not b_entry.get("is_topup"):
                                    port_reporter.send_trade_entry(b_entry, signal)
                        else:
                            log.info(
                                "BEARISH signal skipped — not HIGH/CRITICAL: %s (conf=%d)",
                                signal.get("sector_label"), confidence,
                            )
                        continue

                    # DIRECTION FILTER: if the broad market is in a downturn it is
                    # not ok to open longs — the short side (inverse ETFs, routed
                    # above from bearish signals) is how we participate. Block the
                    # long here.
                    if cycle_downturn:
                        log.info(
                            "Long entry blocked — market in downturn (%s); %s long skipped (%s)",
                            cycle_downturn_detail, severity, signal.get("sector_label"),
                        )
                        continue

                    # REGIME SIZING: outside a downturn, don't skip longs in a dip —
                    # assess and invest, just size down when volatility is high.
                    regime_mult = _regime_size_multiplier(cycle_regime)
                    if regime_mult < 1.0:
                        signal["_regime_size_mult"] = regime_mult
                        log.info(
                            "VIX %.1f %s — sizing %s long to %.0f%% (%s)",
                            cycle_vix, cycle_regime, severity, regime_mult * 100,
                            signal.get("sector_label"),
                        )

                    etf, platform = _select_etf_for_trade(signal)
                    if etf and platform:
                        ticker = etf.get("ticker")

                        # SCOPE GATE: India-domestic signals must not buy globally-traded ETFs.
                        # Example: Sensex falling or India gold import duty should not
                        # trigger INDA/GLD/XLE — those respond to global events, not
                        # domestic India policy. India-domestic signals are restricted to
                        # India-listed ETFs only.
                        signal_scope = signal.get("signal_scope", "global")
                        etf_scope    = etf.get("market_scope", "International-listed")
                        if signal_scope == "india_domestic" and etf_scope != "India-listed":
                            log.info(
                                "Trade skipped — India-domestic signal (%s, %.0f%% India articles) "
                                "cannot enter global ETF %s",
                                signal.get("sector_label"),
                                signal.get("india_article_ratio", 0) * 100,
                                ticker,
                            )
                            continue

                        # PRICE-DIVERGENCE GATE: news says BULLISH but price already falling
                        if ticker:
                            ret_5d = _get_5d_return(ticker)
                            if ret_5d is not None and ret_5d < -0.02:
                                log.warning(
                                    "Trade skipped — news BULLISH but %s price down %.1f%% over 5 days",
                                    ticker, ret_5d * 100,
                                )
                                continue

                        # ── Graduated trend adjustment (replaces binary Quant Blocker) ──
                        if ticker and _RISK_ADVANCED:
                            try:
                                current = __import__("paper_trader", fromlist=["get_current_price_inr"]).get_current_price_inr(
                                    ticker, etf.get("exchange", "NYSE")
                                )
                                if current:
                                    import yfinance as yf
                                    hist = yf.Ticker(ticker).history(period="1y")
                                    if not hist.empty and len(hist) >= 200:
                                        ma_200 = float(hist["Close"].rolling(window=200).mean().iloc[-1])
                                        adj = compute_trend_adjustment(current, ma_200, ticker)
                                        conf_mult = adj["confidence_multiplier"]
                                        
                                        if conf_mult < 1.0:
                                            original_conf = signal["confidence"]
                                            signal["confidence"] = int(original_conf * conf_mult)
                                            signal["_trend_adjusted"] = True
                                            signal["_original_confidence"] = original_conf
                                            signal["_confidence_multiplier"] = conf_mult
                                            
                                            # Alert if adjustment > 15%
                                            if conf_mult < 0.85:
                                                log.warning(
                                                    "Trend adjustment: %s confidence %d → %d (mult=%.2f)",
                                                    ticker, original_conf, signal["confidence"], conf_mult
                                                )
                                                reporter.send_quant_block_alert(signal, etf, ticker)
                                            
                                            # Skip if adjusted below threshold
                                            if signal["confidence"] < cfg.CONFIDENCE_THRESHOLD:
                                                log.info(
                                                    "Trade skipped — adjusted confidence %d below threshold %d",
                                                    signal["confidence"], cfg.CONFIDENCE_THRESHOLD
                                                )
                                                continue
                            except Exception as exc:
                                log.warning("Trend adjustment failed for %s: %s", ticker, exc)
                        
                        entry = portfolio.enter_position(signal, etf, platform)
                        if entry:
                            rotation_exits = entry.get("rotation_exits") or []
                            if rotation_exits:
                                port_reporter.send_trade_exits(rotation_exits)
                            if not entry.get("is_topup"):
                                port_reporter.send_trade_entry(entry, signal)
                            log.info(f"Paper trade {'topped up' if entry.get('is_topup') else 'entered'}: {entry['ticker']}")

        # ── Always send 30-min digest (even if 0 new signals) ────────────────
        for sig in scored_signals:
            if "etf_recommendations" not in sig:
                sig["etf_recommendations"] = mapper.get_etfs(sig["sectors"], sig)
        reporter.send_cycle_digest(scored_signals, new_count=len(new_signals))

        log.info("--- Cycle complete ---\n")

    except Exception as e:
        log.error(f"Cycle error: {e}")
        log.debug(traceback.format_exc())
        try:
            reporter.send_error_alert(str(e))
        except Exception:
            pass


def run_mtm_cycle(portfolio, port_reporter):
    log.info("--- Mark-to-market ---")
    try:
        exits = portfolio.mark_to_market()
        if exits:
            port_reporter.send_trade_exits(exits)
    except Exception as e:
        log.error(f"MTM error: {e}")


def run_eod_report(portfolio, port_reporter):
    log.info("--- EOD report ---")
    try:
        portfolio.mark_to_market()
        summary = portfolio.get_summary()
        port_reporter.send_eod_report(summary)
    except Exception as e:
        log.error(f"EOD report error: {e}")


# FIX: Added quant_fetcher parameter so seed trades go through the same
# trend-approval gate as live intelligence cycle trades.
def seed_startup_trades(state, mapper, portfolio, port_reporter, quant_fetcher, cfg):
    """
    On startup, enter paper trades for any HIGH/CRITICAL signals already in state
    that don't yet have open positions. Fixes the cold-start problem where all
    signals are in cooldown and no trades would fire otherwise.
    """
    if not cfg.PAPER_TRADING_ENABLED:
        return
    if len(portfolio.open_positions) > 0:
        log.info(f"Startup trade seed skipped — {len(portfolio.open_positions)} positions already open")
        return

    log.info("Startup trade seeder running — checking existing signals for entry...")
    seeded = 0

    # Regime (size) + direction (downturn) for the cold-start seeder too — never
    # seed a fresh long book into a falling market (the exact failure that opened
    # 6 sinking longs). Both computed once here.
    seed_vix, seed_regime = _market_regime()
    seed_downturn, seed_downturn_detail = _market_downturn()
    log.info("Seed-time market regime: VIX %.1f → %s", seed_vix, seed_regime)
    log.info(
        "Seed-time market direction: %s (%s)",
        "DOWNTURN — long seeds off" if seed_downturn else "not a downturn",
        seed_downturn_detail,
    )

    # Stage entries by conviction instead of dumping every stored signal at once.
    # The original seeder opened all 6 positions in the same minute with zero
    # diversification across time — cap it and take only the highest-conviction.
    ranked_records = sorted(
        state._state.items(),
        key=lambda kv: kv[1].get("confidence", 0),
        reverse=True,
    )

    for sector_key, record in ranked_records:
        if seeded >= MAX_SEED_POSITIONS:
            log.info(
                "Seed cap reached (%d) — remaining signals deferred to live cycles",
                MAX_SEED_POSITIONS,
            )
            break

        confidence = record.get("confidence", 0)
        if confidence < 75:
            continue  # Only HIGH/CRITICAL confidence signals

        direction    = record.get("direction", "NEUTRAL")
        signal_scope = record.get("signal_scope", "global")
        sector_label = record.get("sector_label", "Unknown")
        sectors      = sector_key.split("|")
        severity     = "CRITICAL" if confidence >= 80 else "HIGH"

        # DIRECTION GATE: never seed a long position from a stored BEARISH signal
        if direction == "BEARISH":
            log.info(
                "Seed skipped — stored direction is BEARISH for %s (conf=%d)",
                sector_label, confidence,
            )
            continue

        # DIRECTION FILTER: no long seeds while the market is in a downturn.
        if seed_downturn:
            log.info(
                "Seed skipped — market in downturn (%s); long seed off for %s",
                seed_downturn_detail, sector_label,
            )
            continue

        # REGIME SIZING: outside a downturn, don't skip seeds in a dip — invest,
        # just size down when volatility is high.
        regime_mult = _regime_size_multiplier(seed_regime)

        etf_recs = mapper.get_etfs(sectors, record)
        signal = {
            "sectors":              sectors,
            "sector_label":         sector_label,
            "confidence":           confidence,
            "severity":             severity,
            "direction":            direction,
            "direction_score":      record.get("direction_score", 2.0),
            "signal_scope":         signal_scope,
            "india_article_ratio":  record.get("india_article_ratio", 0.0),
            "_regime_size_mult":    regime_mult,
            "top_headlines":        [f"Startup seed — {sector_label} (conf: {confidence})"],
            "etf_recommendations":  etf_recs,
        }
        if regime_mult < 1.0:
            log.info(
                "VIX %.1f %s — sizing seed %s to %.0f%% (%s)",
                seed_vix, seed_regime, severity, regime_mult * 100, sector_label,
            )

        etf, platform = _select_etf_for_trade(signal)
        if etf and platform:
            seed_ticker = etf.get("ticker")
            etf_scope   = etf.get("market_scope", "International-listed")

            # SCOPE GATE: India-domestic stored signals must not seed global ETFs
            if signal_scope == "india_domestic" and etf_scope != "India-listed":
                log.info(
                    "Seed skipped — India-domestic signal (%s) cannot seed global ETF %s",
                    sector_label, seed_ticker,
                )
                continue

            # PRICE-DIVERGENCE GATE: price already falling despite bullish signal in state
            if seed_ticker:
                ret_5d = _get_5d_return(seed_ticker)
                if ret_5d is not None and ret_5d < -0.02:
                    log.warning(
                        "Seed skipped — %s price down %.1f%% over 5 days despite stored bullish signal",
                        seed_ticker, ret_5d * 100,
                    )
                    continue
            ticker = etf.get("ticker")
            if ticker:
                if _RISK_ADVANCED:
                    try:
                        from paper_trader import get_current_price_inr
                        current = get_current_price_inr(ticker, etf.get("exchange", "NYSE"))
                        if current:
                            import yfinance as yf
                            hist = yf.Ticker(ticker).history(period="1y")
                            if not hist.empty and len(hist) >= 200:
                                ma_200 = float(hist["Close"].rolling(window=200).mean().iloc[-1])
                                adj = compute_trend_adjustment(current, ma_200, ticker)
                                conf_mult = adj["confidence_multiplier"]
                                if conf_mult < 1.0:
                                    signal["confidence"] = int(signal["confidence"] * conf_mult)
                                    if signal["confidence"] < cfg.CONFIDENCE_THRESHOLD:
                                        log.info(
                                            "Seed trade skipped -- adjusted confidence %d below threshold %d",
                                            signal["confidence"], cfg.CONFIDENCE_THRESHOLD,
                                        )
                                        continue
                    except Exception as exc:
                        log.warning("Trend adjustment failed for seed %s: %s", ticker, exc)
                elif not quant_fetcher.check_trend_approval(ticker):
                    log.warning(
                        "Seed trade skipped: %s is in a structural downtrend (Quant Blocker).", ticker
                    )
                    continue

            entry = portfolio.enter_position(signal, etf, platform)
            if entry:
                rotation_exits = entry.get("rotation_exits") or []
                if rotation_exits:
                    port_reporter.send_trade_exits(rotation_exits)
                if not entry.get("is_topup"):
                    port_reporter.send_trade_entry(entry, signal)
                log.info(f"Startup trade seeded: {entry['ticker']} | {sector_label} | conf {confidence}")
                seeded += 1
                time.sleep(1)

    if seeded == 0:
        log.info("Startup trade seed — no new positions opened (cash low or all below threshold)")
    else:
        log.info(f"Startup trade seed complete — {seeded} positions opened")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single intelligence cycle then exit (used by GitHub Actions)",
    )
    args = parser.parse_args()

    print(BANNER)
    cfg = Config()

    fetcher       = NewsFetcher(cfg)
    classifier    = SectorClassifier(cfg)
    scorer        = ConfidenceScorer(cfg)
    mapper        = ETFMapper()
    reporter      = DiscordReporter(cfg)
    state         = SignalStateManager(cfg)
    portfolio     = PaperPortfolio(cfg.PORTFOLIO_FILE)
    port_reporter = PortfolioReporter(cfg)
    quant_fetcher = QuantFetcher()

    # ── NEW: Multi-engine alpha stack ──────────────────────────────────────
    if _MULTI_ENGINE_AVAILABLE:
        price_scanner        = PriceScanner()
        constituent_analyzer = ConstituentAnalyzer(ETF_TO_SECTOR)
        reverse_researcher   = None  # ReverseResearcher removed; legacy feature
        signal_fuser         = SignalFuser()
        log.info("Multi-engine stack ENABLED (price + constituents + fusion)")
    else:
        price_scanner = constituent_analyzer = reverse_researcher = signal_fuser = None
        log.warning("Multi-engine stack DISABLED — running news-only mode")

    log.info(f"Ready. Interval: {cfg.POLL_INTERVAL_MINUTES}m | Paper trading: {'ON' if cfg.PAPER_TRADING_ENABLED else 'OFF'}")

    reporter.send_startup_message()

    # FIX: Pass quant_fetcher so seeded trades go through trend-approval gate.
    seed_startup_trades(state, mapper, portfolio, port_reporter, quant_fetcher, cfg)

    run_intelligence_cycle(
        fetcher, classifier, scorer, mapper,
        reporter, state, portfolio, port_reporter, quant_fetcher, cfg,
        price_scanner=price_scanner,
        constituent_analyzer=constituent_analyzer,
        reverse_researcher=reverse_researcher,
        signal_fuser=signal_fuser,
    )

    if args.once:
        log.info("Single-cycle mode — running mark-to-market...")
        run_mtm_cycle(portfolio, port_reporter)
        log.info("Single-cycle mode — sending EOD report...")
        run_eod_report(portfolio, port_reporter)
        log.info("Single-cycle mode complete. Exiting.")
        return

    schedule.every(cfg.POLL_INTERVAL_MINUTES).minutes.do(
        run_intelligence_cycle,
        fetcher, classifier, scorer, mapper,
        reporter, state, portfolio, port_reporter, quant_fetcher, cfg,
        price_scanner, constituent_analyzer, reverse_researcher, signal_fuser,
    )
    schedule.every(cfg.MTM_INTERVAL_MINUTES).minutes.do(
        run_mtm_cycle, portfolio, port_reporter
    )
    eod_time = f"{cfg.EOD_REPORT_HOUR:02d}:{cfg.EOD_REPORT_MINUTE:02d}"
    schedule.every().day.at(eod_time).do(
        run_eod_report, portfolio, port_reporter
    )
    log.info(f"EOD report scheduled at {eod_time} UTC (8:30 PM IST)")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
