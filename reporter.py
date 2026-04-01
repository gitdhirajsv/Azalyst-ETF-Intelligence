"""
reporter.py — AZALYST Discord Report Generator

Institutional-grade macro briefing format.
No emojis. No decorative symbols. Clean, professional prose.
Formatted like a sell-side research note or hedge fund internal memo.
"""

import logging
import requests
from datetime import datetime, timezone
from typing import Dict, List

log = logging.getLogger("azalyst.reporter")

# ── Severity color palette — muted, professional ────────────────────────────
SEVERITY_COLORS = {
    "CRITICAL": 0xA93226,
    "HIGH":     0xCA6F1E,
    "MEDIUM":   0x1A5276,
    "LOW":      0x1E8449,
}

SEVERITY_LABEL = {
    "CRITICAL": "CRITICAL",
    "HIGH":     "HIGH",
    "MEDIUM":   "MEDIUM",
    "LOW":      "LOW",
}


def confidence_bar(score: int) -> str:
    filled = score // 10
    empty  = 10 - filled
    return f"[{'|' * filled}{'.' * empty}]  {score} / 100"


def build_etf_block(etf: Dict) -> str:
    """Build ETF display block using platform info from etf_mapper database."""
    note = f"\nNote     : {etf['note']}" if etf.get("note") else ""
    platform = etf.get("platform", "N/A")
    return (
        f"**{etf['name']}**  `{etf['ticker']}`\n"
        f"Platform : {platform}  |  Exchange : {etf['exchange']}\n"
        f"Risk     : {etf['risk']}  |  Horizon  : {etf['timeframe']}\n"
        f"Thesis   : {etf['thesis']}"
        + note
    )


class DiscordReporter:
    """Sends structured macro intelligence reports to Discord."""

    def __init__(self, cfg):
        self.webhook_url = cfg.DISCORD_WEBHOOK_URL
        self._missing_webhook_warned = False
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _post(self, payload: Dict) -> bool:
        if not self.webhook_url:
            if not self._missing_webhook_warned:
                log.warning(
                    "Discord webhook not configured. Set WEBHOOK or "
                    "AZALYST_DISCORD_WEBHOOK in .env to enable delivery."
                )
                self._missing_webhook_warned = True
            return False
        try:
            resp = self.session.post(self.webhook_url, json=payload, timeout=15)
            if resp.status_code in (200, 204):
                return True
            log.error(f"Discord returned {resp.status_code}: {resp.text[:200]}")
            return False
        except requests.exceptions.Timeout:
            log.error("Discord webhook request timed out")
            return False
        except Exception as e:
            log.error(f"Discord webhook error: {e}")
            return False

    # ── System Messages ───────────────────────────────────────────────────────

    def send_startup_message(self):
        payload = {
            "embeds": [{
                "title": "AZALYST ETF INTELLIGENCE  —  SYSTEM ACTIVE",
                "description": (
                    "The macro monitoring system has initialised and is running.\n\n"
                    "```\n"
                    "Scan interval    : Every 30 minutes\n"
                    "Sectors covered  : Energy, Defense, Gold, Technology,\n"
                    "                   Uranium, Cybersecurity, Banking,\n"
                    "                   India Equity, Commodities, Crypto, EM\n"
                    "Confidence floor : 62 / 100\n"
                    "Capital plan     : $10,000 USD / month (50% deploy, 50% reserve)\n"
                    "Exchanges        : NYSE, NASDAQ, NSE, BSE\n"
                    "Access via       : IBKR, Schwab, Fidelity, INDmoney,\n"
                    "                   Vested, Dhan, Groww, Zerodha\n"
                    "```\n\n"
                    "Alerts are issued only when a confirmed macro event meets the "
                    "confidence threshold. No output is generated for noise."
                ),
                "color": 0x1A252F,
                "footer": {"text": "Azalyst ETF Intelligence  |  For informational use only"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }
        self._post(payload)
        log.info("Startup message dispatched to Discord")

    def send_error_alert(self, error_msg: str):
        payload = {
            "embeds": [{
                "title": "AZALYST  —  SYSTEM NOTICE",
                "description": (
                    "An error was encountered during the current intelligence cycle. "
                    "The system will continue running and retry on the next interval.\n\n"
                    f"```{error_msg[:500]}```"
                ),
                "color": 0x7B241C,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "Azalyst ETF Intelligence"},
            }]
        }
        self._post(payload)

    # ── Main Intelligence Report ──────────────────────────────────────────────

    def send_report(self, signal: Dict, is_update: bool = False):
        """
        Dispatch a full macro intelligence report to Discord.

        Embed 1  —  Report classification header and signal metadata
        Embed 2  —  Supporting headlines
        Embed 3  —  India ETF recommendations  (NSE / BSE brokers)
        Embed 4  —  Global ETF recommendations  (International brokers)
        Embed 5  —  Macro thesis, suggested posture, confidence score
        """
        confidence    = signal.get("confidence", 0)
        severity      = signal.get("severity", "MEDIUM")
        sector_label  = signal.get("sector_label", "Unclassified Sector")
        headlines     = signal.get("top_headlines", [])
        regions       = signal.get("regions", [])
        article_count = signal.get("article_count", 0)
        sources       = signal.get("sources", [])
        etf_recs      = signal.get("etf_recommendations", {"india": [], "global": []})
        breakdown     = signal.get("confidence_breakdown", {})
        latest_ts     = signal.get("latest_ts")
        ts_str        = latest_ts.strftime("%d %b %Y  %H:%M UTC") if latest_ts else "—"

        color        = SEVERITY_COLORS.get(severity, 0x1A5276)
        sev_label    = SEVERITY_LABEL.get(severity, "MEDIUM")
        report_type  = "SIGNAL UPDATE" if is_update else "NEW SIGNAL"
        region_str   = ",  ".join(r.replace("_", " ").upper() for r in regions[:3]) or "GLOBAL"
        source_str   = "  |  ".join(sources[:4]) or "Multiple Sources"

        # ── Embed 1: Classification Header ───────────────────────────────
        prev_line = ""
        if is_update:
            prev = signal.get("_prev_confidence", 0)
            prev_line = f"Previous Confidence  : {prev}\n"

        embed1 = {
            "title": "AZALYST ETF INTELLIGENCE",
            "description": (
                f"```\n"
                f"Report Type          : {report_type}\n"
                f"Severity             : {sev_label}\n"
                f"Sector               : {sector_label.upper()}\n"
                f"Region               : {region_str}\n"
                f"Articles Detected    : {article_count}\n"
                f"Sources              : {source_str}\n"
                f"Signal Timestamp     : {ts_str}\n"
                f"{prev_line}"
                f"```"
            ),
            "color": color,
        }

        # ── Embed 2: Supporting Headlines ─────────────────────────────────
        if headlines:
            headline_lines = "\n".join(
                f"  {i+1}.  {h}" for i, h in enumerate(headlines[:5])
            )
        else:
            headline_lines = "  No headlines available."

        embed2 = {
            "title": "SUPPORTING INTELLIGENCE",
            "description": (
                "The following headlines contributed to this signal classification:\n\n"
                f"```\n{headline_lines}\n```"
            ),
            "color": color,
        }

        # ── Embed 3: India ETF Allocation ─────────────────────────────────
        india_etfs = etf_recs.get("india", [])
        if india_etfs:
            india_blocks = [build_etf_block(e) for e in india_etfs[:3]]
            india_body   = ("\n" + "─" * 44 + "\n").join(india_blocks)
        else:
            india_body = (
                "No India ETF is mapped for this sector classification. "
                "Refer to the global instruments below."
            )

        embed3 = {
            "title": "INDIA ETF ALLOCATION  —  NSE / BSE (via INDmoney, Vested, Groww, Zerodha)",
            "description": india_body,
            "color": 0x1B3A5C,
        }

        # ── Embed 4: Global ETF Allocation ────────────────────────────────
        global_etfs = etf_recs.get("global", [])
        if global_etfs:
            global_blocks = [build_etf_block(e) for e in global_etfs[:4]]
            global_body   = ("\n" + "─" * 44 + "\n").join(global_blocks)
        else:
            global_body = "No global ETF is mapped for this sector classification."

        embed4 = {
            "title": "GLOBAL ETF ALLOCATION  —  NYSE / NASDAQ (via IBKR, Schwab, Fidelity)",
            "description": global_body,
            "color": 0x1B3A5C,
        }

        # ── Embed 5: Thesis, Posture, Confidence ──────────────────────────
        thesis  = self._generate_thesis(signal)
        posture = self._generate_posture(signal)
        bd      = breakdown

        score_detail = ""
        if bd:
            score_detail = (
                "\n\n**Score Breakdown**\n"
                "```\n"
                f"Signal Strength         {bd.get('signal_strength', 0):5.1f}  /  25\n"
                f"Volume Confirmation     {bd.get('volume_confirmation', 0):5.1f}  /  20\n"
                f"Source Diversity        {bd.get('source_diversity', 0):5.1f}  /  20\n"
                f"Recency                 {bd.get('recency', 0):5.1f}  /  20\n"
                f"Geopolitical Severity   {bd.get('geopolitical_severity', 0):5.1f}  /  15\n"
                f"{'─' * 38}\n"
                f"Confidence Score        {confidence:5d}  / 100\n"
                "```"
            )

        embed5 = {
            "title": "MACRO THESIS  &  SUGGESTED POSTURE",
            "description": (
                f"**Thesis**\n{thesis}\n\n"
                f"─────────────────────────────────────────────\n\n"
                f"**Suggested Posture**\n{posture}"
                f"\n\n─────────────────────────────────────────────\n\n"
                f"**Confidence Score**\n`{confidence_bar(confidence)}`"
                f"{score_detail}"
            ),
            "color": color,
            "footer": {
                "text": (
                    "Azalyst ETF Intelligence  |  For informational use only.  "
                    "Not financial advice. Verify ETF availability before executing."
                )
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        payload = {
            "content": (
                f"**AZALYST  |  {report_type}  |  {sector_label.upper()}  "
                f"|  CONFIDENCE: {confidence}  |  {sev_label}**"
            ),
            "embeds": [embed1, embed2, embed3, embed4, embed5],
        }

        success = self._post(payload)
        if success:
            log.info(
                f"Report dispatched — {sector_label} | "
                f"Confidence: {confidence} | Severity: {severity}"
            )
        else:
            log.error(f"Failed to dispatch report for {sector_label}")

    # ── Thesis Templates ──────────────────────────────────────────────────────

    THESIS_TEMPLATES = {
        "energy_oil": (
            "Geopolitical disruption or supply chain stress is generating upward pressure on "
            "energy prices. Conflict escalation in the Middle East, shipping lane disruption "
            "through the Strait of Hormuz or Red Sea, or an unexpected OPEC+ production decision "
            "can each tighten supply materially within days. Energy sector ETFs have historically "
            "delivered their strongest short-term returns during conflict-driven supply shocks, "
            "typically in the first two to six weeks following an escalation event."
        ),
        "defense": (
            "Geopolitical escalation is reinforcing a multi-year defense spending cycle that is "
            "already structurally locked in. NATO members have committed to 5% of GDP in defense "
            "expenditure by 2035. The US defense budget exceeds $900 billion annually. Defense "
            "prime contractors operate on long-dated government contracts, providing revenue "
            "visibility that makes the sector independent of the broader economic cycle. "
            "This is not a short-term trade — it is a structural allocation to "
            "government-guaranteed revenue growth for the next several years."
        ),
        "gold_precious_metals": (
            "Safe-haven demand is being activated by rising uncertainty across markets. Gold "
            "performs best in environments characterised by financial stress, inflation above "
            "target, currency debasement, or unresolved geopolitical risk. Central bank gold "
            "purchases have been running at near-record levels, providing structural support. "
            "Both JPMorgan and Goldman Sachs have published targets of $4,900 to $5,000 per "
            "ounce by the end of 2026. Gold mining equities typically offer 2–3x leverage to "
            "the underlying metal price once sentiment turns constructive."
        ),
        "technology_ai": (
            "A development in semiconductor policy, AI infrastructure investment, or export "
            "controls is creating directional momentum in technology equities. The structural "
            "driver is clear: AI model training and inference at scale requires chip capacity "
            "that is growing faster than fabrication supply can meet. The US-Taiwan chip "
            "partnership and domestic CHIPS Act spending are reinforcing this dynamic. "
            "Bank of America forecasts 30% year-on-year growth in global semiconductor "
            "revenues through 2026, which underpins the fundamental case."
        ),
        "nuclear_uranium": (
            "Nuclear energy demand is being driven by the power requirements of AI data centres "
            "and the global net-zero transition. Uranium is in a structural supply deficit — "
            "reactor requirements are expected to outpace mine supply by 197 million pounds "
            "through 2040. Governments across the US, France, Japan, and South Korea are "
            "actively accelerating both large-scale and small modular reactor programmes. "
            "This is an early-to-mid cycle commodity trade with a multi-year fundamental "
            "thesis that is becoming increasingly consensus among institutional energy investors."
        ),
        "cybersecurity": (
            "Elevated cyber attack activity is translating directly into budget acceleration "
            "across both government and enterprise security programmes. Every major kinetic "
            "conflict carries a parallel cyber dimension, and nation-state threat actors "
            "represent the primary vector. Cybersecurity is a non-discretionary spending "
            "category — organisations cannot defer security investment without accepting "
            "material operational risk. This characteristic makes the sector largely "
            "recession-resistant and insulated from the economic cycle."
        ),
        "india_equity": (
            "India-specific macro developments are creating a directional catalyst for domestic "
            "equity markets. India remains the world's fastest-growing major economy, with "
            "structural tailwinds from demographics, manufacturing relocations under the "
            "China-plus-one framework, and public infrastructure investment. RBI policy, FII "
            "flow data, and government budget execution are the key near-term variables. "
            "India has become the preferred emerging market allocation for global institutional "
            "investors seeking growth with improving governance."
        ),
        "banking_financial": (
            "A monetary policy development or financial sector stress event is generating "
            "directional implications for banking equities and safe-haven assets. Rate "
            "decisions by the Federal Reserve, ECB, or RBI directly determine net interest "
            "margins for banks and the discount rate applied to equity valuations. A rate-cut "
            "cycle is typically constructive for bank valuations. Banking stress events, by "
            "contrast, accelerate rotation into gold, short-duration bonds, and defensive "
            "sectors. The key question is whether this is an isolated event or a "
            "potential contagion catalyst."
        ),
        "commodities_mining": (
            "Industrial commodity markets are experiencing disruption from supply chain "
            "friction, trade policy, or resource nationalism. Copper remains the primary "
            "bellwether for global industrial activity and is a critical input for both "
            "the energy transition and AI infrastructure build-out. Lithium and rare earth "
            "elements are subject to increasing Chinese export restrictions and western "
            "supply chain diversification efforts. Commodity price disruption of this "
            "nature typically sustains across a three to nine month horizon before "
            "supply-side adjustments re-establish equilibrium."
        ),
        "crypto_digital": (
            "A regulatory development, macroeconomic event, or institutional flow is "
            "driving directional momentum in digital asset markets. The approval of spot "
            "Bitcoin ETFs has institutionalised BTC as an allocatable asset class. Bitcoin "
            "now correlates meaningfully with broad risk appetite and moves inversely to "
            "dollar strength during risk-off periods. Regulatory clarity typically provides "
            "a sustained positive catalyst; enforcement actions create sharp but often "
            "short-lived dislocations. Position sizing should reflect the high volatility "
            "characteristics of the asset class."
        ),
        "emerging_markets": (
            "Capital flow dynamics are shifting across emerging market allocations. The "
            "primary drivers are Federal Reserve rate expectations, US dollar direction, "
            "and relative growth differentials between emerging and developed markets. "
            "India and Southeast Asia continue to attract manufacturing investment under "
            "the China-plus-one framework. Monitor for currency risk, capital controls, "
            "and political transition risk in individual country exposures within "
            "broad EM index ETFs."
        ),
    }

    POSTURE_TEMPLATES = {
        "CRITICAL": (
            "Signal strength and confirmation are at institutional conviction levels. "
            "If capital is available, this represents a deployment opportunity consistent "
            "with the macro thesis above. Events of this severity have historically produced "
            "meaningful ETF price movement within 24 to 72 hours. Consider a defined position "
            "with a stop-loss in the 8–10% range and a two-week review horizon."
        ),
        "HIGH": (
            "The signal meets the quality bar for capital deployment. Consider allocating "
            "your planned monthly ETF budget to this sector. Geopolitical events of this "
            "nature typically sustain momentum for two to eight weeks before the market "
            "fully discounts the development. A partial initial position with a plan to "
            "add on confirmation is the appropriate approach."
        ),
        "MEDIUM": (
            "The signal is forming but not yet confirmed at high conviction. Add this "
            "sector to your active watchlist. A small starter position is acceptable if "
            "the macro thesis aligns with your existing view, but avoid over-allocating "
            "until the next one or two intelligence cycles provide further confirmation."
        ),
        "LOW": (
            "This is an early-stage signal for informational awareness only. "
            "No capital deployment is suggested at this confidence level. "
            "Monitor for follow-on developments that may strengthen the signal "
            "in the coming days."
        ),
    }

    # ── 30-Minute Cycle Digest ────────────────────────────────────────────────

    def send_cycle_digest(self, scored_signals: List[Dict], new_count: int = 0):
        """
        Lightweight 30-minute cycle summary.
        Sent every cycle — shows active signal dashboard + whether anything new fired.
        Suppresses Discord post if 0 new signals (no new information to deliver),
        but always logs locally.
        """
        now_str = datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M UTC")

        if not scored_signals:
            # Nothing above threshold — log only, no Discord noise
            log.info("Cycle digest — 0 active signals, nothing dispatched")
            return

        # Build signal table rows
        rows = []
        for sig in sorted(scored_signals, key=lambda x: x.get("confidence", 0), reverse=True):
            label      = sig.get("sector_label", "Unknown")[:32]
            conf       = sig.get("confidence", 0)
            severity   = sig.get("severity", "—")[:8]
            art_count  = sig.get("article_count", 0)
            rows.append(
                f"  {label:<34}  Conf: {conf:>3}  {severity:<8}  {art_count:>3} articles"
            )

        table = "\n".join(rows)
        new_label = f"{new_count} NEW signal(s) fired this cycle" if new_count > 0 else "No new signals — all within cooldown"

        # Only post the digest to Discord when something actually changed
        if new_count == 0:
            log.info(f"Cycle digest — {len(scored_signals)} active signals, 0 new, digest suppressed")
            return

        payload = {
            "embeds": [{
                "title": "AZALYST  —  CYCLE DIGEST",
                "description": (
                    f"```\n"
                    f"Timestamp        : {now_str}\n"
                    f"Active Signals   : {len(scored_signals)}\n"
                    f"New This Cycle   : {new_count}\n"
                    f"Status           : {new_label}\n"
                    f"{'─' * 60}\n"
                    f"  {'SECTOR':<34}  {'CONF':>4}  {'SEVERITY':<8}  ARTICLES\n"
                    f"  {'─' * 57}\n"
                    f"{table}\n"
                    f"```"
                ),
                "color": 0xCA6F1E,
                "footer": {"text": "Azalyst ETF Intelligence  |  Next scan in 30 minutes"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }
        self._post(payload)
        log.info(f"Cycle digest dispatched — {len(scored_signals)} active signals, {new_count} new")

    def _generate_thesis(self, signal: Dict) -> str:
        sectors = signal.get("sectors", [])
        primary = sectors[0] if sectors else ""
        return self.THESIS_TEMPLATES.get(
            primary,
            (
                "A macro development has been detected with potential directional implications "
                "for the identified sector. Monitor for follow-through confirmation and "
                "cross-sector corroboration before committing capital."
            ),
        )

    def _generate_posture(self, signal: Dict) -> str:
        severity = signal.get("severity", "LOW")
        etf_recs = signal.get("etf_recommendations", {})
        base     = self.POSTURE_TEMPLATES.get(severity, self.POSTURE_TEMPLATES["LOW"])

        best_global = (etf_recs.get("global") or [{}])[0].get("ticker", "")
        best_india  = (etf_recs.get("india")  or [{}])[0].get("ticker", "")
        
        # Get platform info from ETF data
        best_global_platform = (etf_recs.get("global") or [{}])[0].get("platform", "")
        best_india_platform  = (etf_recs.get("india")  or [{}])[0].get("platform", "")
        
        # Extract broker names from platform string (e.g. "iShares by BlackRock — IBKR / Schwab" -> "IBKR / Schwab")
        global_brokers = ""
        india_brokers = ""
        if best_global_platform and "—" in best_global_platform:
            global_brokers = best_global_platform.split("—")[-1].strip()
        if best_india_platform and "—" in best_india_platform:
            india_brokers = best_india_platform.split("—")[-1].strip()
        elif best_india_platform:
            india_brokers = best_india_platform

        if best_global and best_india:
            if global_brokers and india_brokers:
                suffix = (
                    f" Primary instruments: **{best_india}** via {india_brokers} "
                    f"and **{best_global}** via {global_brokers}."
                )
            elif best_global:
                suffix = (
                    f" Primary instruments: **{best_india}** (India) "
                    f"and **{best_global}** (Global)."
                )
            else:
                suffix = ""
        elif best_global:
            if global_brokers:
                suffix = f" Primary instrument: **{best_global}** via {global_brokers}."
            else:
                suffix = f" Primary instrument: **{best_global}** (Global)."
        elif best_india:
            if india_brokers:
                suffix = f" Primary instrument: **{best_india}** via {india_brokers}."
            else:
                suffix = f" Primary instrument: **{best_india}** (India)."
        else:
            suffix = ""

        return base + suffix
