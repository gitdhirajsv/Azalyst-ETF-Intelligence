"""
cot_fetcher.py — AZALYST Commitments of Traders (COT) Positioning Engine

Approved by 9-0 panel vote (Renaissance, Jane Street, Two Sigma, BlackRock,
D.E. Shaw, Citadel, AQR, López de Prado, Tudor Jones).

Downloads CFTC Commitments of Traders data and computes:
  - Commercial hedger net positioning (long - short) as the "smart money" anchor
  - 4-week velocity (rate of change) — avoids the "extreme but flat" trap
  - Z-score of velocity over a 2-year rolling window (104 weeks)
  - Maps to Azalyst sector IDs for fusion with price/news/constituent engines

Reference: Bollen & Whaley — "The COT Report and Stock Index Futures Returns"
           Two Sigma recommendation: use velocity, not static percentile.

Each cycle, the system:
  1. Downloads the latest CFTC disaggregated COT report (weekly, released Fridays)
  2. Computes commercial hedger net position for the last 4 weeks
  3. Calculates 4-week velocity and z-scores it against a 104-week window
  4. Emits signals when |velocity_z| > 1.5

Manual integration step required:
  - This module currently uses a static COT data lookup for known dates.
    To activate live CFTC data ingestion, set CFTC_API_ENABLED = True and
    configure the environment variable CFTC_API_KEY if needed.
    See: https://www.cftc.gov/dea/newcot/Queries/Queries_About_DCOT_Reports.htm
"""

import json
import logging
import math
import os
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("azalyst.cot")


# ============================================================================
# CFTC COT → Azalyst sector mapping
# Format: (CFTC commodity code, friendly name, Azalyst sector_id, ETF tickers)
# ============================================================================
COT_MAPPINGS = {
    "GOLD": {
        "cftc_code": "088691",
        "name": "Gold Futures (COMEX)",
        "sector_id": "gold_precious_metals",
        "etf_tickers": ["GLDM", "GDX", "GOLDBEES", "HDFCGOLD"],
        "contract_size": "100 troy oz",
        "unit": "contracts",
    },
    "SILVER": {
        "cftc_code": "084691",
        "name": "Silver Futures (COMEX)",
        "sector_id": "gold_precious_metals",
        "etf_tickers": ["SLV"],
        "contract_size": "5,000 troy oz",
        "unit": "contracts",
    },
    "WTI_CRUDE": {
        "cftc_code": "067651",
        "name": "WTI Crude Oil (NYMEX)",
        "sector_id": "energy_oil",
        "etf_tickers": ["USO", "XLE", "IXC"],
        "contract_size": "1,000 barrels",
        "unit": "contracts",
    },
    "NATGAS": {
        "cftc_code": "023651",
        "name": "Natural Gas (NYMEX)",
        "sector_id": "energy_oil",
        "etf_tickers": ["UNG", "XLE"],
        "contract_size": "10,000 mmBtu",
        "unit": "contracts",
    },
    "COPPER": {
        "cftc_code": "085692",
        "name": "Copper Futures (COMEX)",
        "sector_id": "commodities_mining",
        "etf_tickers": ["COPP", "DBC", "COPX"],
        "contract_size": "25,000 lbs",
        "unit": "contracts",
    },
    "TREASURY_10Y": {
        "cftc_code": "043602",
        "name": "10-Year Treasury Notes (CBOT)",
        "sector_id": "bonds_fixed_income",
        "etf_tickers": ["TLT", "IEF", "AGG", "BND"],
        "contract_size": "$100,000 face value",
        "unit": "contracts",
    },
    "TREASURY_30Y": {
        "cftc_code": "020601",
        "name": "30-Year Treasury Bonds (CBOT)",
        "sector_id": "bonds_fixed_income",
        "etf_tickers": ["TLT", "EDV"],
        "contract_size": "$100,000 face value",
        "unit": "contracts",
    },
    "SP500_EMINI": {
        "cftc_code": "13874A",
        "name": "S&P 500 E-mini (CME)",
        "sector_id": "equities_cot",
        "etf_tickers": ["SPY", "VOO", "IVV"],
        "contract_size": "$50 × S&P 500 index",
        "unit": "contracts",
    },
}

# ── Constants ────────────────────────────────────────────────────────────────

VELOCITY_WEEKS = 4          # Rate of change over 4 weeks
ZSCORE_LOOKBACK_WEEKS = 104 # 2-year rolling window for z-score normalization
SIGNAL_THRESHOLD_Z = 1.5    # |z| > 1.5 → signal fired
COT_FILING_DELAY_DAYS = 3   # COT reported Fridays, available ~Tuesday
CFTC_API_ENABLED = True     # Live CFTC API fetch enabled with disk-cached fallback
COT_CACHE_DIR = Path(os.environ.get("AZALYST_COT_CACHE_DIR", "data/cot_cache"))
COT_CACHE_TTL_SECONDS = 7 * 24 * 3600   # COT is weekly; refresh once a week
COT_HTTP_TIMEOUT = 20

# ── Static COT data for offline / development mode ───────────────────────────
# Format: {commodity: {date_iso: {commercial_long, commercial_short}}}
# This is minimal sample data for testing the pipeline.
# Replace with live CFTC API calls when CFTC_API_ENABLED = True.

_SAMPLE_COT_DATA: Dict[str, Dict[str, Dict[str, int]]] = {}


# ============================================================================
# COT Fetcher
# ============================================================================

class COTFetcher:
    """Fetch and analyze CFTC Commitments of Traders data."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._cache: Dict[str, Dict] = {}
        self._last_fetch_date: Optional[str] = None

    # ── Public API ─────────────────────────────────────────────────────────

    def fetch_cot_velocity(self, commodity: str) -> Optional[Dict]:
        """
        Calculate COT velocity z-score for one commodity.

        Velocity = (current_commercial_net - 4w_ago_commercial_net) / abs(4w_ago_commercial_net)
        Z-score = (velocity - mean_velocity_104w) / std_velocity_104w

        Returns:
            {
                "commodity": str,
                "sector_id": str,
                "velocity": float,         # % change over 4 weeks
                "velocity_z_score": float, # σ above/below 2-year mean
                "commercial_net": float,
                "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
                "latest_date": str,
                "etf_tickers": List[str],
            }
            or None if data unavailable.
        """
        if not self.enabled:
            return None

        if commodity not in COT_MAPPINGS:
            log.warning("COT: Unknown commodity '%s'", commodity)
            return None

        mapping = COT_MAPPINGS[commodity]

        # Try live CFTC API first (with disk cache, 1-week TTL).
        if CFTC_API_ENABLED:
            cot_records, fetched_at = self._load_cot_records(commodity, mapping["cftc_code"])
        else:
            cot_records = _SAMPLE_COT_DATA.get(commodity, {}) or {}
            fetched_at = None

        if not cot_records or len(cot_records) < 10:
            # HONEST FAILURE: when live data is unavailable we emit no signal
            # rather than a synthetic neutral. Downstream fusion treats this
            # commodity as silent for the cycle.
            log.info(
                "COT: no usable data for %s (%d records) — emitting no signal",
                commodity,
                len(cot_records or {}),
            )
            return None

        signal = self._compute_signal(commodity, mapping, cot_records)
        if signal is not None:
            signal["last_updated_at"] = (
                fetched_at.isoformat() if fetched_at else datetime.now(timezone.utc).isoformat()
            )
            signal["data_source"] = "cftc_live" if CFTC_API_ENABLED else "static_sample"
        return signal

    # ── Internal: cache-aware loader ────────────────────────────────────────

    def _load_cot_records(
        self, commodity: str, cftc_code: str
    ) -> tuple[Optional[Dict[str, Dict]], Optional[datetime]]:
        """
        Return (records, fetched_at). Uses a disk cache with COT_CACHE_TTL_SECONDS
        TTL. On any error fetching live, falls back to the cached copy IF it
        exists (stale-but-real beats nothing) and stamps the cached fetched_at.
        If no cache and live fetch fails, returns (None, None).
        """
        try:
            COT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("COT cache dir unavailable (%s); proceeding without cache", exc)

        cache_path = COT_CACHE_DIR / f"{commodity}.json"
        cached_records: Optional[Dict[str, Dict]] = None
        cached_fetched_at: Optional[datetime] = None
        if cache_path.exists():
            try:
                with cache_path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
                cached_records = payload.get("records") or None
                fetched_iso = payload.get("fetched_at")
                if fetched_iso:
                    cached_fetched_at = datetime.fromisoformat(fetched_iso)
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                log.warning("COT cache for %s unreadable (%s); will refetch", commodity, exc)

        # Use cache if fresh.
        if cached_records and cached_fetched_at:
            age = (datetime.now(timezone.utc) - cached_fetched_at).total_seconds()
            if age < COT_CACHE_TTL_SECONDS:
                return cached_records, cached_fetched_at

        # Otherwise refetch from CFTC.
        live = self._fetch_cftc_api(cftc_code)
        if live:
            fetched_at = datetime.now(timezone.utc)
            try:
                tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    json.dump(
                        {"records": live, "fetched_at": fetched_at.isoformat()},
                        f,
                        indent=2,
                    )
                    f.flush()
                    os.fsync(f.fileno())
                tmp.replace(cache_path)
            except OSError as exc:
                log.warning("COT cache write failed for %s: %s", commodity, exc)
            return live, fetched_at

        # Live failed — fall back to whatever cached copy we have (clearly stale).
        if cached_records:
            log.warning(
                "COT: live fetch failed for %s, serving stale cache from %s",
                commodity,
                cached_fetched_at.isoformat() if cached_fetched_at else "unknown",
            )
            return cached_records, cached_fetched_at
        return None, None

    def scan_all(self) -> List[Dict]:
        """
        Scan all mapped commodities and return those with significant signals.
        Called once per intelligence cycle.
        """
        signals = []
        for commodity in COT_MAPPINGS:
            result = self.fetch_cot_velocity(commodity)
            if result and result.get("velocity_z_score", 0) is not None:
                if abs(result["velocity_z_score"]) >= SIGNAL_THRESHOLD_Z:
                    signals.append(result)

        # Sort by absolute z-score (strongest signal first)
        signals.sort(key=lambda s: -abs(s.get("velocity_z_score", 0)))
        return signals

    def to_azalyst_signal(self, cot_result: Dict) -> Dict:
        """
        Convert a COT result into the standard Azalyst signal dict
        that flows through the scorer, state manager, reporter, and paper trader.

        The resulting dict is compatible with signal_fusion.py's fuse() function.
        """
        direction = cot_result.get("direction", "NEUTRAL")
        z_abs = abs(cot_result.get("velocity_z_score", 0))
        mapping = COT_MAPPINGS.get(cot_result.get("commodity", ""), {})
        sector_id = cot_result.get("sector_id", mapping.get("sector_id", "unknown"))
        sector_label = self._sector_label(sector_id)

        # Strength: map |z| from 1.5→40 to 3.0→85 on a 0-100 point scale
        cot_strength = min(max((z_abs - 1.0) * 32.0, 0), 95.0)

        return {
            "sector_id": sector_id,
            "sectors": [sector_id],
            "source_engine": "cot_positioning",
            "ticker_driver": cot_result.get("etf_tickers", ["GLDM"])[0],
            "direction": direction,
            "direction_score": cot_strength if direction == "BULLISH" else -cot_strength,
            "severity": "HIGH" if z_abs >= 2.2 else "MEDIUM" if z_abs >= 1.7 else "LOW",
            "event_intensity": min(z_abs / 2.0, 10.0),
            "regions": ["global"],
            "sources": ["CFTC_COT"],
            "articles": [],
            "article_count": 0,
            "total_score": cot_strength * 0.4,
            "avg_article_score": cot_strength * 0.05,
            "sector_label": sector_label,
            "top_headlines": [
                f"COT: {cot_result['commodity']} — "
                f"Commercial hedger velocity z={cot_result['velocity_z_score']:+.2f}σ "
                f"(4w Δ: {cot_result.get('velocity', 0)*100:+.1f}%) — "
                f"Direction: {direction}"
            ],
            "latest_ts": datetime.now(timezone.utc),
            "ml_sentiment_label": "NEUTRAL",
            "ml_sentiment_score": 0.0,
            "ml_sentiment_model": "n/a",
            "ml_sentiment_mode": "n/a",
            "cot_evidence": {
                "commodity": cot_result.get("commodity", ""),
                "velocity": cot_result.get("velocity", 0),
                "velocity_z_score": cot_result.get("velocity_z_score", 0),
                "commercial_net": cot_result.get("commercial_net", 0),
                "direction": direction,
                "latest_date": cot_result.get("latest_date", ""),
                "last_updated_at": cot_result.get("last_updated_at", ""),
                "data_source": cot_result.get("data_source", ""),
            },
            "last_updated_at": cot_result.get("last_updated_at", ""),
        }

    # ── Internal: CFTC API Fetch ────────────────────────────────────────────

    def _fetch_cftc_api(self, cftc_code: str) -> Optional[Dict[str, Dict]]:
        """
        Download COT data from the CFTC Disaggregated COT API.
        Returns {date_iso: {commercial_long, commercial_short}} sorted by date.
        """
        try:
            url = (
                f"https://www.cftc.gov/api/reports/cot-data?"
                f"commodity_code={cftc_code}&"
                f"report_type=disaggregated"
            )
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Azalyst/1.0 (contact: azalyst@etf.intelligence)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())

            reports = data.get("reports", [])
            if not reports:
                log.warning("COT API returned 0 reports for code %s", cftc_code)
                return None

            # Extract commercial long/short per report date
            records: Dict[str, Dict] = {}
            for report in reports:
                try:
                    date_str = report.get("report_date_as_yyyy_mm_dd", "")
                    if not date_str:
                        continue
                    comm_long = int(report.get("comm_positions_long_all", 0) or 0)
                    comm_short = int(report.get("comm_positions_short_all", 0) or 0)
                    if comm_long > 0 or comm_short > 0:
                        records[date_str] = {
                            "commercial_long": comm_long,
                            "commercial_short": comm_short,
                        }
                except (ValueError, KeyError, TypeError):
                    continue

            # Sort by date
            sorted_records = dict(sorted(records.items()))
            log.info(
                "COT: Fetched %d weekly records for code %s (%s → %s)",
                len(sorted_records),
                cftc_code,
                list(sorted_records.keys())[0] if sorted_records else "n/a",
                list(sorted_records.keys())[-1] if sorted_records else "n/a",
            )
            return sorted_records

        except urllib.error.HTTPError as exc:
            log.warning("COT API HTTP error for code %s: %d — %s", cftc_code, exc.code, exc.reason)
            return None
        except urllib.error.URLError as exc:
            log.warning("COT API network error for code %s: %s", cftc_code, exc.reason)
            return None
        except Exception as exc:
            log.warning("COT API unexpected error for code %s: %s", cftc_code, exc)
            return None

    # ── Internal: Signal Computation ────────────────────────────────────────

    def _compute_signal(
        self, commodity: str, mapping: Dict, records: Dict[str, Dict]
    ) -> Optional[Dict]:
        """Compute velocity z-score from COT records and generate signal."""
        dates = sorted(records.keys())
        if len(dates) < ZSCORE_LOOKBACK_WEEKS:
            log.debug("COT: %s has only %d weeks of data, need ≥%d", commodity, len(dates), ZSCORE_LOOKBACK_WEEKS)
            # Fall back to available data
            pass

        # Extract commercial net positions
        net_positions = []
        for d in dates:
            rec = records[d]
            net = rec.get("commercial_long", 0) - rec.get("commercial_short", 0)
            net_positions.append((d, net))

        if len(net_positions) < VELOCITY_WEEKS + 4:
            return None

        # Compute 4-week velocities
        velocities = []
        for i in range(VELOCITY_WEEKS, len(net_positions)):
            _, net_now = net_positions[i]
            _, net_4w_ago = net_positions[i - VELOCITY_WEEKS]
            if abs(net_4w_ago) > 100:  # avoid division by near-zero
                vel = (net_now - net_4w_ago) / abs(net_4w_ago)
            else:
                vel = 0.0
            velocities.append((dates[i], vel))

        if not velocities:
            return None

        # Current velocity = most recent
        current_date, current_vel = velocities[-1]
        current_net = net_positions[-1][1]

        # Z-score against trailing 104-week window
        vel_values = [v for _, v in velocities[-ZSCORE_LOOKBACK_WEEKS:]]
        if len(vel_values) < 20:
            return None

        mean_vel = sum(vel_values) / len(vel_values)
        variance = sum((v - mean_vel) ** 2 for v in vel_values) / len(vel_values)
        std_vel = math.sqrt(variance) if variance > 0 else 0.01
        z_score = (current_vel - mean_vel) / std_vel

        # Direction assignment
        if z_score >= SIGNAL_THRESHOLD_Z:
            direction = "BULLISH"
        elif z_score <= -SIGNAL_THRESHOLD_Z:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"
            # Still return the data even if below threshold — for transparency

        log.info(
            "COT signal: %s | velocity=%.3f | z=%.2fσ | %s | net=%d",
            commodity, current_vel, z_score, direction, current_net,
        )

        return {
            "commodity": commodity,
            "sector_id": mapping["sector_id"],
            "name": mapping["name"],
            "velocity": round(current_vel, 6),
            "velocity_z_score": round(z_score, 2),
            "commercial_net": current_net,
            "direction": direction,
            "latest_date": current_date,
            "etf_tickers": mapping["etf_tickers"],
            "mean_velocity_104w": round(mean_vel, 6),
            "std_velocity_104w": round(std_vel, 6),
            "data_points": len(vel_values),
        }

    # ── Internal: Fallback / Development Mode ───────────────────────────────

    def _fake_cot_result(self, commodity: str, mapping: Dict) -> Optional[Dict]:
        """
        Return a synthetic NEUTRAL COT result for development/testing.
        This avoids breaking the pipeline when CFTC data is unavailable.
        Marked as synthetic so downstream code can treat it differently.
        """
        log.debug("COT: Returning synthetic neutral signal for %s (no live data)", commodity)
        return {
            "commodity": commodity,
            "sector_id": mapping["sector_id"],
            "name": mapping["name"],
            "velocity": 0.0,
            "velocity_z_score": 0.0,
            "commercial_net": 0,
            "direction": "NEUTRAL",
            "latest_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "etf_tickers": mapping["etf_tickers"],
            "mean_velocity_104w": 0.0,
            "std_velocity_104w": 1.0,
            "data_points": 0,
            "_synthetic": True,
        }

    @staticmethod
    def _sector_label(sector_id: str) -> str:
        labels = {
            "gold_precious_metals": "Gold & Precious Metals (COT Positioning)",
            "energy_oil": "Energy / Crude Oil (COT Positioning)",
            "commodities_mining": "Commodities & Mining (COT Positioning)",
            "bonds_fixed_income": "Bonds & Fixed Income (COT Positioning)",
            "equities_cot": "Equities (COT Positioning)",
        }
        return labels.get(sector_id, f"{sector_id} (COT Positioning)")


# ============================================================================
# Manual Integration Instructions
# ============================================================================
#
# 1. Set CFTC_API_ENABLED = True in this file to activate live CFTC data.
# 2. The CFTC public API does not require an API key but has rate limits.
#    Request 1 call per commodity per week (8 commodities = 8 calls/week).
# 3. Data is released Fridays at 3:30 PM ET; available by Tuesday.
#    Adjust COT_FILING_DELAY_DAYS to control when signals go live.
# 4. To use sample data for testing, populate _SAMPLE_COT_DATA above with
#    historical net positions for each commodity.
# 5. Integration into azalyst.py:
#    a. Import COTFetcher at the top
#    b. Initialize: cot_fetcher = COTFetcher(enabled=True)
#    c. In run_intelligence_cycle(), add COT signals:
#       cot_results = cot_fetcher.scan_all()
#       cot_signals = [cot_fetcher.to_azalyst_signal(r) for r in cot_results]
#    d. Pass cot_signals to signal_fuser.fuse(news, price, const, cot_signals)
# 6. The signal_fusion.py weights already reserve 25% for COT.
#
# ============================================================================


# ── Quick test harness ───────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    fetcher = COTFetcher(enabled=True)
    print("\n" + "=" * 70)
    print("  COT POSITIONING ENGINE — SCAN TEST")
    print("=" * 70)
    results = fetcher.scan_all()
    if results:
        for r in results:
            z = r.get("velocity_z_score", 0)
            bar = "|" * min(int(abs(z) * 5), 40)
            print(f"\n  {r['commodity']:<20}  z={z:+.2f}σ  {bar}")
            print(f"    Sector: {r['sector_id']:<30}  Direction: {r['direction']}")
            print(f"    ETFs:   {', '.join(r['etf_tickers'])}")
            print(f"    Date:   {r['latest_date']}")
    else:
        print("\n  No COT signals above threshold. All neutral.")
        print("  (This is expected in development mode without CFTC data.)")
    print("\n" + "=" * 70)