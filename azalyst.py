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

# ── NEW: Multi-engine alpha stack ────────────────────────────────────────────
try:
    from price_scanner        import PriceScanner, ETF_TO_SECTOR
    from constituent_analyzer import ConstituentAnalyzer
    from reverse_researcher   import ReverseResearcher
    from signal_fusion        import SignalFuser
    _MULTI_ENGINE_AVAILABLE = True
except Exception as _imp_err:
    _MULTI_ENGINE_AVAILABLE = False
    PriceScanner = ConstituentAnalyzer = ReverseResearcher = SignalFuser = None
    ETF_TO_SECTOR = {}

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

        # ── 5. FUSE signals across all 3 engines ────────────────────────────
        if signal_fuser is not None:
            fused = signal_fuser.fuse(
                news_signals_raw, price_signals, constituent_signals
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

        for signal in new_signals:
            etf_recs = mapper.get_etfs(signal["sectors"], signal)
            signal["etf_recommendations"] = etf_recs
            is_update = state.is_update(signal)

            reporter.send_report(signal, is_update=is_update)
            state.record_signal(signal)
            time.sleep(1)

            # Paper trade entry — HIGH/CRITICAL signals only
            if cfg.PAPER_TRADING_ENABLED and not is_update:
                severity   = signal.get("severity", "LOW")
                confidence = signal.get("confidence", 0)
                if severity in ("HIGH", "CRITICAL") or confidence >= 75:
                    etf, platform = _select_etf_for_trade(signal)
                    if etf and platform:
                        # QUANT BLOCKER: Check if the ETF is mathematically broken
                        ticker = etf.get("ticker")
                        if ticker and not quant_fetcher.check_trend_approval(ticker):
                            log.warning(f"Trade skipped: News is bullish, but {ticker} is structurally broken (Quant Blocker).")
                            continue

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

    for sector_key, record in state._state.items():
        confidence = record.get("confidence", 0)
        if confidence < 75:
            continue  # Only HIGH/CRITICAL confidence signals

        sector_label = record.get("sector_label", "Unknown")
        sectors      = sector_key.split("|")
        severity     = "CRITICAL" if confidence >= 80 else "HIGH"

        etf_recs = mapper.get_etfs(sectors, record)
        signal = {
            "sectors":              sectors,
            "sector_label":         sector_label,
            "confidence":           confidence,
            "severity":             severity,
            "top_headlines":        [f"Startup seed — {sector_label} (conf: {confidence})"],
            "etf_recommendations":  etf_recs,
        }

        etf, platform = _select_etf_for_trade(signal)
        if etf and platform:
            # FIX: Apply the same quant blocker used in run_intelligence_cycle.
            # Previously seed trades bypassed the 200-day MA trend check entirely.
            ticker = etf.get("ticker")
            if ticker and not quant_fetcher.check_trend_approval(ticker):
                log.warning(
                    f"Seed trade skipped: {ticker} is in a structural downtrend (Quant Blocker)."
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
        reverse_researcher   = ReverseResearcher(classifier)
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
