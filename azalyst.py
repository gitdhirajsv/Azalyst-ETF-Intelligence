"""
AZALYST ETF INTELLIGENCE — CORE ENGINE
Macro hedge fund-grade global news + paper trading track record system
+ LLM-powered optimization with NVIDIA NIM (Mistral 7B)
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
from llm_analyzer       import LLMAnalyzer, create_llm_analyzer

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
|   + LLM Optimization (NVIDIA NIM / Mistral 7B)               |
+--------------------------------------------------------------+
"""


def _select_etf_for_trade(signal: dict) -> tuple:
    """Pick best ETF from signal recommendations. Global first, then India."""
    etf_recs    = signal.get("etf_recommendations", {})
    global_etfs = etf_recs.get("global", [])
    india_etfs  = etf_recs.get("india",  [])
    
    # Return ETF with its platform info from the database
    if global_etfs:
        etf = global_etfs[0]
        platform = etf.get("platform", "Global Broker")
        return etf, platform
    elif india_etfs:
        etf = india_etfs[0]
        platform = etf.get("platform", "Indian Broker")
        return etf, platform
    return None, None


def run_intelligence_cycle(
    fetcher, classifier, scorer, mapper,
    reporter, state, portfolio, port_reporter, cfg, llm_analyzer=None
):
    log.info("--- Intelligence cycle starting ---")
    try:
        articles = fetcher.fetch_all()
        log.info(f"Fetched {len(articles)} articles")
        if not articles:
            return

        sector_signals = classifier.classify_articles(articles)
        scored_signals = []
        for signal in sector_signals:
            score = scorer.score(signal, articles)
            signal["confidence"] = score
            signal["confidence_breakdown"] = scorer.breakdown(signal, articles)
            if score >= cfg.CONFIDENCE_THRESHOLD:
                scored_signals.append(signal)

        new_signals = state.filter_new_or_updated(scored_signals)
        log.info(f"{len(new_signals)} new/updated signals")

        # LLM-enhanced signal evaluation (if enabled)
        if llm_analyzer and llm_analyzer.enabled:
            log.info("LLM enhancement enabled for signal evaluation")
            for signal in new_signals:
                portfolio_context = {
                    "cash": portfolio.cash_inr,
                    "open_positions_count": len(portfolio.open_positions),
                    "sector_exposure": {},
                }
                llm_rec = llm_analyzer.evaluate_signal(signal, portfolio_context)
                signal["llm_recommendation"] = llm_rec
                log.info(f"LLM recommendation for {signal.get('sector_label')}: {llm_rec.get('action', 'N/A')}")

        for signal in new_signals:
            etf_recs = mapper.get_etfs(signal["sectors"])
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
                        entry = portfolio.enter_position(signal, etf, platform)
                        if entry:
                            rotation_exits = entry.get("rotation_exits") or []
                            if rotation_exits:
                                port_reporter.send_trade_exits(rotation_exits)
                            if not entry.get("is_topup"):
                                port_reporter.send_trade_entry(entry, signal)
                            log.info(f"Paper trade {'topped up' if entry.get('is_topup') else 'entered'}: {entry['ticker']}")

        # ── Always send 30-min digest (even if 0 new signals) ────────────────
        # Attach ETF recs to scored signals for digest context
        for sig in scored_signals:
            if "etf_recommendations" not in sig:
                sig["etf_recommendations"] = mapper.get_etfs(sig["sectors"])
        reporter.send_cycle_digest(scored_signals, new_count=len(new_signals))

        log.info("--- Cycle complete ---\n")

    except Exception as e:
        log.error(f"Cycle error: {e}")
        log.debug(traceback.format_exc())
        try:
            reporter.send_error_alert(str(e))
        except Exception:
            pass


def run_mtm_cycle(portfolio, port_reporter, llm_analyzer=None):
    log.info("--- Mark-to-market ---")
    try:
        exits = portfolio.mark_to_market()
        if exits:
            port_reporter.send_trade_exits(exits)
            
            # Log trade outcomes for LLM feedback
            if llm_analyzer and llm_analyzer.enabled:
                for exit_data in exits:
                    llm_analyzer.log_trade_outcome(exit_data)
    except Exception as e:
        log.error(f"MTM error: {e}")


def run_eod_report(portfolio, port_reporter, llm_analyzer=None):
    log.info("--- EOD report ---")
    try:
        portfolio.mark_to_market()
        summary = portfolio.get_summary()
        port_reporter.send_eod_report(summary)
        
        # Run LLM analysis periodically (e.g., daily)
        if llm_analyzer and llm_analyzer.enabled and llm_analyzer.should_run_analysis():
            log.info("Running scheduled LLM portfolio analysis...")
            analysis_result = llm_analyzer.run_portfolio_analysis()
            
            # Log analysis results
            if "suggestions" in analysis_result:
                log.info(f"LLM generated {len(analysis_result['suggestions'])} suggestions")
                for i, suggestion in enumerate(analysis_result["suggestions"][:3], 1):
                    log.info(f"  Suggestion #{i}: {suggestion[:150]}...")
    except Exception as e:
        log.error(f"EOD report error: {e}")


def run_llm_macro_analysis(llm_analyzer, reporter):
    """Run LLM macro regime analysis and send to Discord."""
    if not llm_analyzer or not llm_analyzer.enabled:
        return
    
    try:
        log.info("Running LLM macro regime analysis...")
        regime_result = llm_analyzer.interpret_macro_regime()
        
        if "interpretation" in regime_result and regime_result["interpretation"]:
            log.info(f"Macro regime: {regime_result.get('regime', 'unknown')}")
            # Could send to Discord if desired
            # reporter.send_macro_analysis(regime_result)
    except Exception as e:
        log.error(f"LLM macro analysis error: {e}")


def seed_startup_trades(state, mapper, portfolio, port_reporter, cfg):
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

        # Build minimal signal dict from state record
        etf_recs = mapper.get_etfs(sectors)
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
    parser.add_argument(
        "--llm-analysis",
        action="store_true",
        help="Run LLM portfolio analysis immediately then exit",
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
    
    # Initialize LLM analyzer
    llm_analyzer = create_llm_analyzer(cfg) if cfg.LLM_ENABLED else None
    
    if llm_analyzer:
        log.info(f"LLM Analyzer: ENABLED (Model: {cfg.LLM_MODEL})")
    else:
        log.info("LLM Analyzer: DISABLED (Set NVIDIA_API_KEY in .env to enable)")

    log.info(f"Ready. Interval: {cfg.POLL_INTERVAL_MINUTES}m | Paper trading: {'ON' if cfg.PAPER_TRADING_ENABLED else 'OFF'} | LLM: {'ON' if llm_analyzer else 'OFF'}")

    reporter.send_startup_message()

    # Seed paper trades from existing state signals (fixes cold-start / restart)
    seed_startup_trades(state, mapper, portfolio, port_reporter, cfg)

    # --llm-analysis: run LLM analysis only mode
    if args.llm_analysis:
        if not llm_analyzer:
            log.error("LLM Analyzer not configured. Set NVIDIA_API_KEY in .env")
            return
        log.info("LLM Analysis mode — running portfolio analysis...")
        result = llm_analyzer.run_portfolio_analysis()
        log.info(f"Analysis complete. Generated {len(result.get('suggestions', []))} suggestions")
        for i, suggestion in enumerate(result.get("suggestions", []), 1):
            print(f"\n{i}. {suggestion}")
        return

    run_intelligence_cycle(
        fetcher, classifier, scorer, mapper,
        reporter, state, portfolio, port_reporter, cfg, llm_analyzer
    )

    # --once: single cycle mode for GitHub Actions
    # Run MTM to update live prices, check exits, then send EOD report to Discord
    if args.once:
        log.info("Single-cycle mode — running mark-to-market...")
        run_mtm_cycle(portfolio, port_reporter, llm_analyzer)
        log.info("Single-cycle mode — sending EOD report...")
        run_eod_report(portfolio, port_reporter, llm_analyzer)
        log.info("Single-cycle mode complete. Exiting.")
        return

    schedule.every(cfg.POLL_INTERVAL_MINUTES).minutes.do(
        run_intelligence_cycle,
        fetcher, classifier, scorer, mapper,
        reporter, state, portfolio, port_reporter, cfg, llm_analyzer
    )
    schedule.every(cfg.MTM_INTERVAL_MINUTES).minutes.do(
        run_mtm_cycle, portfolio, port_reporter, llm_analyzer
    )
    eod_time = f"{cfg.EOD_REPORT_HOUR:02d}:{cfg.EOD_REPORT_MINUTE:02d}"
    schedule.every().day.at(eod_time).do(
        run_eod_report, portfolio, port_reporter, llm_analyzer
    )
    log.info(f"EOD report scheduled at {eod_time} UTC (8:30 PM IST)")
    
    # Optional: Schedule LLM macro analysis (e.g., every 6 hours)
    if llm_analyzer and cfg.LLM_ANALYSIS_INTERVAL > 0:
        schedule.every(6).hours.do(
            run_llm_macro_analysis, llm_analyzer, reporter
        )
        log.info(f"LLM macro analysis scheduled every 6 hours")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
