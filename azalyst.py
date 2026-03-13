"""
AZALYST ETF INTELLIGENCE — CORE ENGINE
Macro hedge fund-grade global news + paper trading track record system
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
    """Pick best ETF from signal recommendations. Global first, then India."""
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
    reporter, state, portfolio, port_reporter, cfg
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
                            if not entry.get("is_topup"):
                                port_reporter.send_trade_entry(entry, signal)
                            log.info(f"Paper trade entered: {entry['ticker']}")

        # ── Cycle digest (reporter may suppress to reduce Discord noise) ─────
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

    log.info(f"Ready. Interval: {cfg.POLL_INTERVAL_MINUTES}m | Paper trading: {'ON' if cfg.PAPER_TRADING_ENABLED else 'OFF'}")

    reporter.send_startup_message()

    # Seed paper trades from existing state signals (fixes cold-start / restart)
    seed_startup_trades(state, mapper, portfolio, port_reporter, cfg)

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
    log.info(f"EOD report scheduled at {eod_time} UTC (8:30 PM IST)")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
