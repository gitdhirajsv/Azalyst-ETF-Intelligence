"""
Daily fusion runner v2 — end-to-end pipeline.

  Signal layers
       |
       v
  Regime-conditional scoring (scorer_v2 + regime_engine weight matrix)
       |
       v
  Publish gate (60-pt threshold)
       |
       v
  Cluster dedup
       |
       v
  Antonacci absolute-momentum gate (RISK_OFF -> defensives only)
       |
       v
  Vol-target sizing
       |
       v
  Risk overlay (trailing stops, circuit breaker)
       |
       v
  Paper trader execution + tearsheet

Run:
    python -m azalyst_alpha.fusion
"""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from . import (
    ETF_UNIVERSE, cross_sectional_ranker, flow_engine, gex_engine,
    holdings_weighted_rotation, macro_overlay, options_tape,
    portfolio_constructor, regime_engine, report, scorer_v2,
    universe_fetcher,
)


GEX_TARGETS = ["SPY", "QQQ", "IWM", "SOXX", "SMH", "IGV", "XLK", "XLF", "XLE",
               "GLD", "SLV", "EWY", "GDX", "ITA"]


# Map v1 sector_id -> list of v2 ETF tickers. Used to translate the per-sector
# news confidence (written to azalyst_state.json by the legacy news engine)
# into per-ETF news_score for the v2 scorer (capped at 10/100).
SECTOR_TO_ETFS: dict[str, list[str]] = {
    "technology_ai":          ["SOXX", "SMH", "SOXL", "IGV", "XLK", "VGT", "FDN", "ARKK", "ARKW", "QQQ"],
    "energy_oil":             ["XLE", "USO", "UNG", "BNO"],
    "gold_precious_metals":   ["GLD", "IAU", "SLV", "GDX", "GDXJ", "SIL", "PPLT"],
    "defense_aerospace":      ["ITA", "PPA", "XAR", "DFEN"],
    "nuclear_uranium":        ["URA", "URNM", "NLR"],
    "cybersecurity":          ["HACK", "CIBR", "BUG"],
    "india_equity":           ["INDA", "EPI", "INDY", "SMIN"],
    "crypto_digital":         ["BITO", "IBIT", "FBTC", "ETHE"],
    "banking_financial":      ["KBE", "KRE", "XLF", "IYG"],
    "commodities_mining":     ["DBC", "GSG", "COPX", "PICK", "REMX", "LIT"],
    "emerging_markets":       ["EEM", "VWO", "EWZ", "EWY", "EWT", "FXI", "MCHI", "ASHR", "INDA"],
    "asia_pacific":           ["EWY", "EWT", "EWJ", "FXI", "MCHI", "ASHR"],
    "europe_equity":          ["EWG", "EWU", "EWQ", "EWI", "EWP"],
    "healthcare_pharma":      ["XBI", "IBB", "ARKG", "IHI"],
    "clean_energy_renewables":["ICLN", "TAN", "FAN", "PBW"],
    "real_estate_reit":       ["VNQ", "IYR", "REM"],
    "bonds_fixed_income":     ["TLT", "IEF", "SHY", "HYG", "LQD", "TIP", "AGG"],
}


def _load_news_scores() -> dict[str, float]:
    """Read v1 sector confidence from azalyst_state.json and project to per-ETF
    news_score capped at 10. Confidence is 0-100; we scale by 0.1 -> 0-10.

    Also fires Discord news alerts (no @-mention) for HIGH/CRITICAL sectors
    that haven't been alerted in the last 6 hours."""
    import json
    from datetime import datetime, timezone
    from pathlib import Path
    state_path = Path("azalyst_state.json")
    if not state_path.exists():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(state, dict):
        return {}

    # Sentinel tracks last news-alert timestamp per sector to throttle pings
    alert_sentinel = Path("data/.last_news_alert.json")
    try:
        alert_log = json.loads(alert_sentinel.read_text(encoding="utf-8"))
    except Exception:
        alert_log = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    alert_changed = False

    out: dict[str, float] = {}
    for sector_id, record in state.items():
        if not isinstance(record, dict):
            continue
        conf = record.get("confidence")
        if not isinstance(conf, (int, float)):
            continue
        sev = str(record.get("severity", "")).upper()
        sev_mult = {"CRITICAL": 1.0, "HIGH": 0.8, "MEDIUM": 0.6, "LOW": 0.4}.get(sev, 0.5)
        score = float(conf) / 10.0 * sev_mult
        for etf in SECTOR_TO_ETFS.get(sector_id, []):
            out[etf] = max(out.get(etf, 0.0), score)

        # Discord news alert: fire on HIGH/CRITICAL sectors, max once per 6h
        if sev in ("HIGH", "CRITICAL") and conf >= 70:
            last = alert_log.get(sector_id)
            should_fire = True
            if last:
                try:
                    age_hours = (datetime.now(timezone.utc) -
                                 datetime.fromisoformat(last)).total_seconds() / 3600
                    should_fire = age_hours >= 6
                except Exception:
                    pass
            if should_fire:
                try:
                    from . import discord_notify
                    headlines = record.get("top_headlines") or []
                    sector_label = record.get("sector_label", sector_id.replace("_", " ").title())
                    discord_notify.notify_news_alert(
                        sector=sector_label,
                        confidence=float(conf),
                        severity=sev,
                        headlines=headlines if isinstance(headlines, list) else [],
                        etfs=SECTOR_TO_ETFS.get(sector_id, [])[:6],
                    )
                    alert_log[sector_id] = now_iso
                    alert_changed = True
                except Exception:
                    pass

    if alert_changed:
        try:
            alert_sentinel.parent.mkdir(parents=True, exist_ok=True)
            alert_sentinel.write_text(json.dumps(alert_log), encoding="utf-8")
        except Exception:
            pass
    return out


def _regime_weighted_composite(
    ticker: str,
    rank_score: float,
    flow_score: float,
    options_tape_score: float,
    gex_score: float,
    rotation_score: float,
    macro_score: float,
    news_score: float,
    direction: str,
    weight_matrix: dict[str, float],
) -> scorer_v2.CompositeScore:
    """Apply regime-conditional weights (scale max per factor) to scorer_v2."""
    rank = rank_score * (weight_matrix["rank"] / 25.0)
    flow = flow_score * (weight_matrix["flow"] / 20.0)
    opt = (options_tape_score + 0.5 * gex_score) * (weight_matrix["options"] / 20.0)
    rot = rotation_score * (weight_matrix["rotation"] / 15.0)
    macro = macro_score * (weight_matrix["macro"] / 10.0)
    news = news_score * (weight_matrix["news"] / 10.0)
    total = rank + flow + opt + rot + macro + news
    return scorer_v2.CompositeScore(
        ticker=ticker,
        rank_score=rank,
        flow_score=flow,
        options_score=opt,
        rotation_score=rot,
        macro_score=macro,
        news_score=news,
        total=total,
        publish=total >= scorer_v2.PUBLISH_THRESHOLD,
        direction=direction,
    )


def run(book_value: float = 100_000, verbose: bool = True) -> dict:
    if verbose: print("[regime] detecting...")
    regime = regime_engine.detect_regime()
    if verbose: print(f"  -> {regime.risk_state} / {regime.vol_regime} / VIX {regime.vix_level:.1f}")

    # Live universe via NASDAQ Trader; falls back to ETF_UNIVERSE if fetch fails.
    try:
        universe = universe_fetcher.fetch_universe()
        if verbose: print(f"[universe] {len(universe)} liquid ETFs (cache or live fetch)")
    except Exception as exc:
        if verbose: print(f"[universe] live fetch failed ({exc}); using static ETF_UNIVERSE")
        universe = ETF_UNIVERSE

    if verbose: print("[1/6] cross-sectional rank")
    rank_rows = cross_sectional_ranker.rank_universe(tickers=universe)
    rank_map = {r.ticker: r for r in rank_rows}

    if verbose: print("[2/6] ETF flows")
    flow_rows = flow_engine.compute_flows(universe)
    flow_map = {r.ticker: r for r in flow_rows}

    if verbose: print("[3a/6] dealer GEX")
    gex_rows = gex_engine.compute_gex_universe(GEX_TARGETS)
    gex_map = {r.ticker: r for r in gex_rows}

    if verbose: print("[3b/6] options tape")
    opt_rows = options_tape.compute_options_universe(GEX_TARGETS)
    opt_map = {r.ticker: r for r in opt_rows}

    if verbose: print("[4/6] holdings-weighted rotation")
    rot_rows = holdings_weighted_rotation.compute_universe()
    rot_map = {r.etf: r for r in rot_rows}

    if verbose: print("[5/6] macro overlay")
    macro_rows = macro_overlay.compute_universe()
    macro_map = {r.etf: r for r in macro_rows}

    if verbose: print("[6/6] regime-weighted composite scoring")
    news_map = _load_news_scores()
    if verbose: print(f"[news] {len(news_map)} ETFs with news_score from azalyst_state.json")
    composite: list[scorer_v2.CompositeScore] = []
    score_universe = {*rank_map, *flow_map, *gex_map, *opt_map, *rot_map, *macro_map, *news_map}
    for tk in score_universe:
        cs = _regime_weighted_composite(
            ticker=tk,
            rank_score=rank_map[tk].score if tk in rank_map else 0,
            flow_score=flow_map[tk].score if tk in flow_map else 0,
            options_tape_score=opt_map[tk].score if tk in opt_map else 0,
            gex_score=gex_map[tk].score if tk in gex_map else 0,
            rotation_score=rot_map[tk].score if tk in rot_map else 0,
            macro_score=macro_map[tk].score if tk in macro_map else 0,
            news_score=news_map.get(tk, 0),
            direction=(rot_map[tk].direction if tk in rot_map else "long"),
            weight_matrix=regime.weight_matrix,
        )
        composite.append(cs)

    if verbose: print("[portfolio] regime gate -> dedup -> sizing")
    book, _ = portfolio_constructor.build_book(composite, book_value=book_value)

    leaderboard = pd.DataFrame([asdict(c) for c in composite]).sort_values("total", ascending=False)
    book_df = portfolio_constructor.to_dataframe(book)

    # Always write the CSV — generate_dashboard.py reads this for top_signal payload.
    from pathlib import Path
    Path("data").mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv("data/leaderboard_latest.csv", index=False)
    if verbose: print(f"[csv] data/leaderboard_latest.csv written ({len(leaderboard)} rows)")

    if verbose: print("[report] writing tearsheet -> data/tearsheet.md")
    try:
        out = report.write_report(leaderboard, book_df, regime)
    except ImportError as exc:
        # tabulate not installed -> fall back to plain text tearsheet
        if verbose: print(f"[report] markdown rendering unavailable ({exc}); writing plain-text tearsheet")
        Path("data/tearsheet.md").write_text(
            f"# Azalyst Tearsheet — {regime.risk_state} / {regime.vol_regime}\n\n"
            f"VIX {regime.vix_level:.1f} ({regime.vix_percentile_1y:.0%}ile)\n\n"
            f"## Top 25\n```\n{leaderboard.head(25).to_string(index=False)}\n```\n\n"
            f"## Published Book\n```\n{book_df.to_string(index=False) if not book_df.empty else '(empty)'}\n```\n",
            encoding="utf-8",
        )
        out = "data/tearsheet.md"

    # Discord cycle digest -- post regime + top 5 + news leaders + book size.
    # Throttled by content fingerprint so identical cycles don't spam: only
    # post when (a) regime changed, (b) top signal changed, (c) published count
    # changed, OR (d) >= 4 hours since last digest.
    try:
        _push_cycle_digest_if_changed(leaderboard, book_df, regime, verbose=verbose)
    except Exception as exc:
        if verbose: print(f"[discord] cycle digest skipped: {exc}")

    return {"leaderboard": leaderboard, "book": book_df, "regime": regime, "tearsheet": out}


def _push_cycle_digest_if_changed(leaderboard, book_df, regime, verbose=True):
    """Smart throttle: only post when something meaningful changed since last cycle."""
    import json
    from datetime import datetime, timezone, timedelta
    from pathlib import Path
    from . import discord_notify

    sentinel = Path("data/.last_cycle_digest")
    top1_ticker = leaderboard["ticker"].iloc[0] if not leaderboard.empty else None
    top1_score  = float(leaderboard["total"].iloc[0]) if not leaderboard.empty else 0.0
    published_count = int(leaderboard["publish"].sum()) if "publish" in leaderboard.columns else 0
    book_count = len(book_df)
    fingerprint = {
        "regime": f"{regime.risk_state}/{regime.vol_regime}",
        "top1": top1_ticker,
        "published_count": published_count,
        "book_count": book_count,
    }
    now = datetime.now(timezone.utc)
    last = None
    if sentinel.exists():
        try:
            last = json.loads(sentinel.read_text(encoding="utf-8"))
        except Exception:
            last = None
    same = last and last.get("fingerprint") == fingerprint
    age_hours = float("inf")
    if last and last.get("ts"):
        try:
            age_hours = (now - datetime.fromisoformat(last["ts"])).total_seconds() / 3600
        except Exception:
            pass
    if same and age_hours < 4:
        if verbose: print(f"[discord] digest skipped (no change, last fired {age_hours:.1f}h ago)")
        return

    # Read v1 sector news for the digest
    try:
        state = json.loads(Path("azalyst_state.json").read_text(encoding="utf-8"))
    except Exception:
        state = {}
    news_top = sorted(
        [(s, float(r.get("confidence", 0)), str(r.get("severity", ""))) for s, r in state.items()
         if isinstance(r, dict) and isinstance(r.get("confidence"), (int, float))],
        key=lambda x: -x[1],
    )

    discord_notify.notify_cycle_digest(
        regime_state=regime.risk_state,
        vol_regime=regime.vol_regime,
        vix_level=regime.vix_level,
        leaderboard_top=[(r.ticker, float(r.total)) for r in leaderboard.head(5).itertuples()],
        book_size=book_count,
        news_top=news_top,
        published_count=published_count,
    )
    if verbose: print(f"[discord] cycle digest posted (regime={fingerprint['regime']}, top1={top1_ticker} {top1_score:.1f}, published={published_count})")

    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(json.dumps({"fingerprint": fingerprint, "ts": now.isoformat()}), encoding="utf-8")


def commit_book(
    book_df: "pd.DataFrame",
    regime: regime_engine.RegimeState,
    leaderboard: "pd.DataFrame | None" = None,
    verbose: bool = True,
) -> dict[str, list[str]]:
    """
    Reconcile recommended book against live paper positions. Idempotent:
      - tickers in book but not in positions    -> open_position()  + Discord ENTRY
      - tickers in positions but not in book    -> close_position() + Discord EXIT (REASON='regime_exit')
      - tickers in both, share counts unchanged -> no action
      - tickers in both, share counts differ    -> close + reopen with new size

    Returns {"opened": [...], "closed": [...]}.
    """
    from . import paper_trader

    opened: list[str] = []
    closed: list[str] = []

    # Normalize current positions
    live = {p["ticker"]: p for p in paper_trader.positions()}
    target = {row["ticker"]: row for _, row in book_df.iterrows()} if not book_df.empty else {}

    leaderboard_map: dict[str, dict] = {}
    if leaderboard is not None and not leaderboard.empty:
        for _, r in leaderboard.iterrows():
            leaderboard_map[r["ticker"]] = r.to_dict()

    # Closes: in live, not in target
    for tk in list(live.keys()):
        if tk not in target:
            paper_trader.close_position(tk, reason="regime_exit_or_signal_drop", notify=True)
            closed.append(tk)
            if verbose: print(f"[commit] CLOSE {tk}")

    # Opens / resizes
    for tk, row in target.items():
        target_shares = int(row.get("target_shares") or 0)
        if target_shares == 0:
            continue
        live_shares = int(live[tk]["shares"]) if tk in live else 0
        if live_shares == target_shares:
            continue
        if live_shares != 0:
            paper_trader.close_position(tk, reason="resize", notify=True)
            closed.append(tk)
        fb = leaderboard_map.get(tk, {})
        breakdown = {
            "Rank":  float(fb.get("rank_score", 0)),
            "Flow":  float(fb.get("flow_score", 0)),
            "Opt":   float(fb.get("options_score", 0)),
            "Rot":   float(fb.get("rotation_score", 0)),
            "Macro": float(fb.get("macro_score", 0)),
            "News":  float(fb.get("news_score", 0)),
        }
        paper_trader.open_position(
            ticker=tk,
            shares=target_shares,
            reason=f"fusion publish (score {row.get('composite_score', 0):.1f})",
            score=float(row.get("composite_score", 0)),
            regime_state=regime.risk_state,
            vol_regime=regime.vol_regime,
            factor_breakdown=breakdown,
            pct_of_book=float(row.get("target_pct_of_book", 0) or 0),
            notify=True,
        )
        opened.append(tk)
        if verbose: print(f"[commit] OPEN {tk} {target_shares} sh @ score {row.get('composite_score', 0):.1f}")

    # Mark to market once at the end
    eq = paper_trader.mark_to_market()
    if verbose: print(f"[commit] equity (mtm): ${eq:,.2f}  ({len(opened)} opens, {len(closed)} closes)")

    return {"opened": opened, "closed": closed, "equity": eq}


if __name__ == "__main__":
    import os
    import sys
    out = run()
    print("\n=== TOP 15 ===")
    print(out["leaderboard"].head(15).to_string(index=False))
    print("\n=== PUBLISHED BOOK ===")
    if out["book"].empty:
        print("(empty — regime gate or no signal cleared 60-pt threshold)")
    else:
        print(out["book"].to_string(index=False))
    print(f"\nTearsheet -> {out['tearsheet']}")

    # Commit the book to paper-trader + fire Discord ENTRY/EXIT alerts
    # only when explicitly requested. Default ON in CI (GitHub Actions),
    # default OFF locally so a developer running fusion.py for inspection
    # doesn't accidentally trigger a paper trade + Discord ping.
    is_ci = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    want_commit = is_ci or "--commit" in sys.argv
    no_commit = "--no-commit" in sys.argv
    if want_commit and not no_commit:
        print("\n=== COMMITTING BOOK -> paper trader + Discord ===")
        commit_book(out["book"], out["regime"], leaderboard=out["leaderboard"])
    else:
        print("\n(skipping commit_book; pass --commit to execute paper trades + Discord)")
