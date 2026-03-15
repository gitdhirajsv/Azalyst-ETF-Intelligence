"""
AZALYST ETF INTELLIGENCE — CORE ENGINE
Macro hedge fund-grade global news + paper trading track record system
"""

import time
import logging
import schedule
import traceback
import os
import sys
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
+------------------------------------------------------+
|   AZALYST  ETF INTELLIGENCE + PAPER TRADING SYSTEM  |
|   Macro Fund Edition  .  Track Record Engine         |
+------------------------------------------------------+
"""


def _select_etf_for_trade(signal: dict) -> tuple:
    etf_recs    = signal.get("etf_recommendations", {})
    global_etfs = etf_recs.get("global", [])
    india_etfs  = etf_recs.get("india",  [])

    if global_etfs:
        return global_etfs[0], "INDmoney / Vested"
    elif india_etfs:
        return india_etfs[0], "Dhan App"

    return None, None


def run_intelligence_cycle(
    fetcher, classifier, scorer, mapper,
    reporter, state, portfolio, port_reporter, cfg,
    raise_on_error=False,
):
    log.info("--- Intelligence cycle starting ---")

    try:
        articles = fetcher.fetch_all()
        log.info(f"Fetched {len(articles)} articles")

        if not articles:
            log.warning("No articles fetched — skipping cycle")
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

        for signal in new_signals:
            etf_recs = mapper.get_etfs(signal["sectors"])
            signal["etf_recommendations"] = etf_recs

            is_update = state.is_update(signal)

            reporter.send_report(signal, is_update=is_update)

            state.record_signal(signal)

            time.sleep(1)

            if cfg.PAPER_TRADING_ENABLED and not is_update:
                severity   = signal.get("severity", "LOW")
                confidence = signal.get("confidence", 0)

                if severity in ("HIGH", "CRITICAL") or confidence >= 75:
                    etf, platform = _select_etf_for_trade(signal)

                    if etf and platform:
                        entry = portfolio.enter_position(signal, etf, platform)

                        if entry:
                            if not entry.get("is_topup"):
                                port_reporter.send_trade_entry(entry, signal)
                            log.info(f"Paper trade entered: {entry['ticker']}")

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

        # In GitHub Actions, re-raise so the step fails visibly
        # instead of silently succeeding with no output files written.
        if raise_on_error:
            raise


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


def seed_startup_trades(state, mapper, portfolio, port_reporter, cfg):
    if not cfg.PAPER_TRADING_ENABLED:
        return

    if len(portfolio.open_positions) > 0:
        log.info("Startup trade seed skipped — positions already open")
        return

    log.info("Startup trade seeder running")

    # Use public API instead of private _state attribute
    all_signals = state.get_all_signals() if hasattr(state, "get_all_signals") else state._state

    for sector_key, record in all_signals.items():
        confidence = record.get("confidence", 0)

        if confidence < 75:
            continue

        sector_label = record.get("sector_label", "Unknown")
        sectors      = sector_key.split("|")
        etf_recs     = mapper.get_etfs(sectors)

        signal = {
            "sectors":             sectors,
            "sector_label":        sector_label,
            "confidence":          confidence,
            "severity":            "HIGH",
            "top_headlines":       [f"Startup seed — {sector_label}"],
            "etf_recommendations": etf_recs,
        }

        etf, platform = _select_etf_for_trade(signal)

        if etf and platform:
            entry = portfolio.enter_position(signal, etf, platform)

            if entry:
                if not entry.get("is_topup"):
                    port_reporter.send_trade_entry(entry, signal)
                log.info(f"Startup trade seeded: {entry['ticker']}")
                time.sleep(1)


def main():
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

    log.info(
        f"Ready. Interval: {cfg.POLL_INTERVAL_MINUTES}m | "
        f"Paper trading: {'ON' if cfg.PAPER_TRADING_ENABLED else 'OFF'}"
    )

    reporter.send_startup_message()

    seed_startup_trades(state, mapper, portfolio, port_reporter, cfg)

    # ── GitHub Actions: single cycle, fail hard on error ─────────────────────
    if os.getenv("GITHUB_ACTIONS") == "true":
        log.info("GitHub Actions detected — running single cycle only")

        try:
            run_intelligence_cycle(
                fetcher, classifier, scorer, mapper,
                reporter, state, portfolio, port_reporter, cfg,
                raise_on_error=True,
            )
        except Exception as e:
            log.error(f"Fatal cycle error in Actions: {e}")
            sys.exit(1)   # Makes the workflow step go red — no more silent failures

        log.info("Single cycle done — exiting cleanly")
        sys.exit(0)

    # ── Local / server: continuous scheduling loop ────────────────────────────
    log.info("Running continuous engine (local mode)")

    # Run one cycle immediately on startup, then hand off to scheduler
    run_intelligence_cycle(
        fetcher, classifier, scorer, mapper,
        reporter, state, portfolio, port_reporter, cfg
    )

    schedule.every(cfg.POLL_INTERVAL_MINUTES).minutes.do(
        run_intelligence_cycle,
        fetcher, classifier, scorer, mapper,
        reporter, state, portfolio, port_reporter, cfg
    )

    schedule.every(cfg.MTM_INTERVAL_MINUTES).minutes.do(
        run_mtm_cycle, portfolio, port_reporter
    )

    eod_time = f"{cfg.EOD_REPORT_HOUR:02d}:{cfg.EOD_REPORT_MINUTE:02d}"
    schedule.every().day.at(eod_time).do(
        run_eod_report, portfolio, port_reporter
    )

    log.info(f"EOD report scheduled at {eod_time} UTC")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
