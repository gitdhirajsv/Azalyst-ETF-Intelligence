"""
etf_mapper.py - AZALYST ETF Mapping Engine

Maps detected sectors to specific ETF recommendations.
Supports a global ETF universe with market-aware alternatives across
international and India-listed venues.

Each ETF entry includes:
  - name, ticker, platform, exchange
  - thesis: why it captures the sector signal
  - timeframe: typical trade horizon
  - risk: Low / Medium / High
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

# ── Master ETF Database ───────────────────────────────────────────────────────
def load_etf_database() -> Dict:
    path = Path("data") / "etf_universe.json"
    if not path.exists():
        log.warning("ETF universe file missing at %s — using empty database", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("Failed to load ETF universe: %s", exc)
        return {}

ETF_DATABASE = load_etf_database()

# ── Sector aliases — map classifier output keys to database keys ──────────────
_SECTOR_ALIASES: Dict[str, str] = {
    "defense_aerospace":        "defense",
    "gold":                     "gold_precious_metals",
    "precious_metals":          "gold_precious_metals",
    "tech":                     "technology_ai",
    "ai":                       "technology_ai",
    "nuclear":                  "nuclear_uranium",
    "uranium":                  "nuclear_uranium",
    "cyber":                    "cybersecurity",
    "india":                    "india_equity",
    "crypto":                   "crypto_digital",
    "digital_assets":           "crypto_digital",
    "banking":                  "banking_financial",
    "financials":               "banking_financial",
    "commodities":              "commodities_mining",
    "mining":                   "commodities_mining",
    "em":                       "emerging_markets",
    "healthcare":               "healthcare_pharma",
    "pharma":                   "healthcare_pharma",
    "biotech":                  "healthcare_pharma",
    "real_estate":              "real_estate_reit",
    "reit":                     "real_estate_reit",
    "clean_energy":             "clean_energy_renewables",
    "renewables":               "clean_energy_renewables",
    "europe":                   "europe_equity",
    "european_equity":          "europe_equity",
    "asia":                     "asia_pacific",
    "japan":                    "asia_pacific",
    "china":                    "asia_pacific",
    "bonds":                    "bonds_fixed_income",
    "fixed_income":             "bonds_fixed_income",
    "rates":                    "bonds_fixed_income",
    "energy":                   "energy_oil",
    "oil":                      "energy_oil",
    "oil_gas":                  "energy_oil",
}

_DEFAULT_SELECTION_PROFILE = {
    "cost": 3,
    "liquidity": 3,
    "purity": 3,
    "diversification": 3,
    "access": 3,
    "stability": 3,
}

# Internal qualitative selector weights. These are heuristic quality tiers,
# not live market data or broker quotes.
_SELECTION_PROFILES: Dict[str, Dict[str, int]] = {
    "AIQ":        {"purity": 4, "access": 4, "stability": 2},
    "BANKBEES":   {"purity": 4, "access": 2, "stability": 3},
    "BHARATBOND": {"cost": 4, "purity": 5, "stability": 5, "access": 2},
    "BITQ":       {"cost": 2, "liquidity": 3, "purity": 4, "diversification": 2, "access": 4, "stability": 1},
    "BND":        {"cost": 5, "liquidity": 5, "purity": 5, "diversification": 5, "access": 5, "stability": 5},
    "CIBR":       {"cost": 4, "liquidity": 4, "purity": 5, "diversification": 4, "access": 5, "stability": 4},
    "COPP":       {"cost": 2, "liquidity": 2, "purity": 5, "diversification": 1, "access": 3, "stability": 2},
    "CPSEETF":    {"cost": 3, "liquidity": 2, "purity": 2, "diversification": 3, "access": 2, "stability": 3},
    "DBC":        {"cost": 4, "liquidity": 4, "purity": 5, "diversification": 4, "access": 5, "stability": 4},
    "DEFENCEETF": {"cost": 2, "liquidity": 2, "purity": 5, "diversification": 2, "access": 2, "stability": 2},
    "EEM":        {"cost": 3, "liquidity": 5, "purity": 5, "diversification": 5, "access": 5, "stability": 4},
    "EWG":        {"cost": 4, "liquidity": 4, "purity": 4, "diversification": 3, "access": 5, "stability": 4},
    "EWJ":        {"cost": 4, "liquidity": 4, "purity": 4, "diversification": 3, "access": 5, "stability": 4},
    "EWU":        {"cost": 4, "liquidity": 4, "purity": 4, "diversification": 3, "access": 5, "stability": 4},
    "EWY":        {"cost": 4, "liquidity": 4, "purity": 4, "diversification": 3, "access": 5, "stability": 3},
    "FLAX":       {"cost": 3, "liquidity": 2, "purity": 4, "diversification": 5, "access": 4, "stability": 3},
    "FXI":        {"cost": 4, "liquidity": 4, "purity": 4, "diversification": 3, "access": 5, "stability": 2},
    "GDX":        {"cost": 3, "liquidity": 4, "purity": 4, "diversification": 3, "access": 4, "stability": 3},
    "GDXJ":       {"cost": 2, "liquidity": 3, "purity": 5, "diversification": 1, "access": 4, "stability": 1},
    "GLDM":       {"cost": 5, "liquidity": 5, "purity": 5, "diversification": 4, "access": 5, "stability": 5},
    "GOLDBEES":   {"cost": 3, "liquidity": 3, "purity": 5, "diversification": 4, "access": 2, "stability": 4},
    "HACK":       {"cost": 3, "liquidity": 3, "purity": 4, "diversification": 4, "access": 4, "stability": 3},
    "HDFCGOLD":   {"cost": 3, "liquidity": 2, "purity": 5, "diversification": 4, "access": 2, "stability": 4},
    "HEALTHCARE": {"cost": 3, "liquidity": 2, "purity": 5, "diversification": 3, "access": 2, "stability": 3},
    "IBIT":       {"cost": 4, "liquidity": 5, "purity": 5, "diversification": 1, "access": 5, "stability": 3},
    "ICLN":       {"cost": 4, "liquidity": 4, "purity": 5, "diversification": 4, "access": 5, "stability": 3},
    "IEV":        {"cost": 4, "liquidity": 4, "purity": 4, "diversification": 5, "access": 5, "stability": 4},
    "INDA":       {"cost": 4, "liquidity": 4, "purity": 5, "diversification": 5, "access": 5, "stability": 4},
    "ITA":        {"cost": 4, "liquidity": 4, "purity": 5, "diversification": 4, "access": 5, "stability": 4},
    "IXC":        {"cost": 4, "liquidity": 4, "purity": 4, "diversification": 5, "access": 5, "stability": 4},
    "IXJ":        {"cost": 4, "liquidity": 4, "purity": 4, "diversification": 5, "access": 5, "stability": 4},
    "MAFANG":     {"cost": 2, "liquidity": 2, "purity": 3, "diversification": 3, "access": 2, "stability": 3},
    "MIDCAPETF":  {"cost": 2, "liquidity": 2, "purity": 4, "diversification": 2, "access": 2, "stability": 2},
    "NEWENERGY":  {"cost": 2, "liquidity": 1, "purity": 4, "diversification": 2, "access": 2, "stability": 1},
    "NIFTYBEES":  {"cost": 4, "liquidity": 4, "purity": 3, "diversification": 5, "access": 2, "stability": 4},
    "PBW":        {"cost": 1, "liquidity": 3, "purity": 5, "diversification": 3, "access": 4, "stability": 1},
    "PHARMABEES": {"cost": 3, "liquidity": 2, "purity": 4, "diversification": 3, "access": 2, "stability": 3},
    "PPA":        {"cost": 3, "liquidity": 3, "purity": 4, "diversification": 4, "access": 4, "stability": 4},
    "PSUBNKBEES": {"cost": 2, "liquidity": 1, "purity": 1, "diversification": 2, "access": 2, "stability": 2},
    "QCLN":       {"cost": 2, "liquidity": 3, "purity": 5, "diversification": 3, "access": 4, "stability": 2},
    "QQQ":        {"cost": 4, "liquidity": 5, "purity": 3, "diversification": 5, "access": 5, "stability": 5},
    "REALTY":     {"cost": 2, "liquidity": 2, "purity": 4, "diversification": 2, "access": 2, "stability": 2},
    "REET":       {"cost": 3, "liquidity": 3, "purity": 4, "diversification": 5, "access": 4, "stability": 4},
    "SOXX":       {"cost": 3, "liquidity": 4, "purity": 5, "diversification": 3, "access": 5, "stability": 4},
    "SPEM":       {"cost": 4, "liquidity": 3, "purity": 5, "diversification": 5, "access": 4, "stability": 4},
    "SRUUF":      {"cost": 1, "liquidity": 1, "purity": 4, "diversification": 2, "access": 1, "stability": 4},
    "TIP":        {"cost": 4, "liquidity": 4, "purity": 5, "diversification": 4, "access": 5, "stability": 4},
    "TLT":        {"cost": 4, "liquidity": 5, "purity": 5, "diversification": 4, "access": 5, "stability": 4},
    "URA":        {"cost": 3, "liquidity": 4, "purity": 4, "diversification": 3, "access": 5, "stability": 3},
    "URNM":       {"cost": 2, "liquidity": 3, "purity": 5, "diversification": 2, "access": 4, "stability": 2},
    "USO":        {"cost": 1, "liquidity": 4, "purity": 5, "diversification": 1, "access": 4, "stability": 1},
    "VGK":        {"cost": 5, "liquidity": 4, "purity": 5, "diversification": 5, "access": 5, "stability": 5},
    "VNQ":        {"cost": 5, "liquidity": 5, "purity": 5, "diversification": 5, "access": 5, "stability": 5},
    "XAR":        {"cost": 3, "liquidity": 3, "purity": 4, "diversification": 5, "access": 4, "stability": 4},
    "XBI":        {"cost": 2, "liquidity": 4, "purity": 5, "diversification": 3, "access": 5, "stability": 2},
    "XLE":        {"cost": 5, "liquidity": 5, "purity": 4, "diversification": 4, "access": 5, "stability": 5},
    "XLF":        {"cost": 5, "liquidity": 5, "purity": 5, "diversification": 5, "access": 5, "stability": 5},
    "XLV":        {"cost": 5, "liquidity": 5, "purity": 5, "diversification": 5, "access": 5, "stability": 5},
}

_SELECTION_WEIGHTS = {
    "cost": 4.0,
    "liquidity": 5.0,
    "purity": 4.5,
    "diversification": 3.5,
    "access": 3.0,
    "stability": 4.0,
}

_RISK_ADJUSTMENTS = {
    "LOW": 6.0,
    "LOW-MEDIUM": 5.0,
    "MEDIUM": 3.0,
    "MEDIUM-HIGH": 0.0,
    "HIGH": -5.0,
}


class ETFMapper:
    """
    Maps sector signals to globally ranked ETF recommendations while keeping
    market-specific alternatives available for execution and reporting.
    """

    @staticmethod
    def _resolve(sector_id: str) -> str:
        """Resolve a raw sector key to the canonical database key."""
        key = sector_id.lower().strip().split("|")[0].strip()
        return _SECTOR_ALIASES.get(key, key)

    @staticmethod
    def _merge_profile(ticker: str) -> Dict[str, int]:
        profile = dict(_DEFAULT_SELECTION_PROFILE)
        profile.update(_SELECTION_PROFILES.get(ticker, {}))
        return profile

    @staticmethod
    def _score_timeframe(timeframe: str) -> float:
        text = (timeframe or "").lower()
        numbers = [float(num) for num in re.findall(r"\d+(?:\.\d+)?", text)]
        if not numbers:
            return 0.0
        if "week" in text:
            numbers = [num / 4.0 for num in numbers]
        if "day" in text:
            numbers = [num / 30.0 for num in numbers]
        midpoint = numbers[0] if len(numbers) == 1 else sum(numbers[:2]) / 2.0
        if midpoint < 1.5:
            return -4.0
        if midpoint < 4.0:
            return 1.0
        if midpoint <= 18.0:
            return 4.0
        return 2.0

    @staticmethod
    def _score_listing(exchange: str, market_bucket: str) -> float:
        exchange_upper = (exchange or "").upper()
        if "NASDAQ" in exchange_upper or "NYSE" in exchange_upper:
            return 4.0
        if "NSE" in exchange_upper or "BSE" in exchange_upper:
            return 2.5
        if market_bucket == "global":
            return 2.0
        return 1.0

    @staticmethod
    def _text_adjustments(etf: Dict) -> tuple:
        text = " ".join(
            [
                etf.get("name", ""),
                etf.get("note", ""),
                etf.get("thesis", ""),
            ]
        ).lower()
        score = 0.0
        reasons = []

        positive_checks = (
            ("largest", 2.0, "institutional depth"),
            ("broad", 1.5, "broad exposure"),
            ("diversified", 1.5, "diversified exposure"),
            ("low-cost", 2.0, "cost-aware implementation"),
            ("lowest-cost", 2.5, "cost-aware implementation"),
            ("very liquid", 2.0, "strong trading liquidity"),
            ("capital preservation", 1.5, "defensive profile"),
            ("safe haven", 1.5, "defensive profile"),
            ("equal-weighted", 1.0, "reduced single-name concentration"),
        )
        for keyword, boost, reason in positive_checks:
            if keyword in text:
                score += boost
                reasons.append(reason)

        negative_checks = (
            ("futures exposure", -5.0, "futures roll-cost risk"),
            ("highest leverage", -4.0, "very high beta"),
            ("2-3x leverage", -4.0, "levered miner sensitivity"),
            ("high risk/reward", -3.0, "narrow tactical profile"),
            ("use only for strong conviction", -3.0, "best used tactically"),
            ("high geopolitical risk", -2.0, "elevated geopolitical risk"),
            ("short-term", -2.0, "short holding window"),
        )
        for keyword, penalty, reason in negative_checks:
            if keyword in text:
                score += penalty
                reasons.append(reason)

        return score, reasons

    @staticmethod
    def _signal_market_boost(signal: Dict, market_bucket: str) -> tuple:
        if not signal:
            return 0.0, []

        regions = {str(region).lower() for region in signal.get("regions", [])}
        score = 0.0
        reasons = []

        if regions.intersection({"india", "south_asia"}) and market_bucket == "india":
            score += 3.0
            reasons.append("matches India-listed access")
        elif regions.intersection(
            {"global", "united_states", "us", "north_america", "europe", "asia_pacific"}
        ) and market_bucket == "global":
            score += 2.0
            reasons.append("matches international access")

        return score, reasons

    def _enrich_candidate(self, etf: Dict, canonical_sector: str, market_bucket: str, signal: Dict = None) -> Dict:
        candidate = dict(etf)
        profile = self._merge_profile(candidate["ticker"])

        base_score = sum(
            profile[dimension] * _SELECTION_WEIGHTS[dimension]
            for dimension in _SELECTION_WEIGHTS
        )
        risk_adjustment = _RISK_ADJUSTMENTS.get(
            (candidate.get("risk") or "").upper(),
            0.0,
        )
        timeframe_adjustment = self._score_timeframe(candidate.get("timeframe", ""))
        listing_adjustment = self._score_listing(candidate.get("exchange", ""), market_bucket)
        text_adjustment, text_reasons = self._text_adjustments(candidate)
        signal_adjustment, signal_reasons = self._signal_market_boost(signal or {}, market_bucket)

        score = (
            base_score
            + risk_adjustment
            + timeframe_adjustment
            + listing_adjustment
            + text_adjustment
            + signal_adjustment
        )

        reasons = []
        if profile["liquidity"] >= 5:
            reasons.append("deep liquidity")
        if profile["cost"] >= 5:
            reasons.append("strong cost profile")
        if profile["purity"] >= 5:
            reasons.append("clean thematic exposure")
        if profile["diversification"] >= 5:
            reasons.append("broad diversification")
        if profile["stability"] >= 5:
            reasons.append("high implementation stability")
        reasons.extend(text_reasons)
        reasons.extend(signal_reasons)

        unique_reasons = []
        for reason in reasons:
            if reason not in unique_reasons:
                unique_reasons.append(reason)

        candidate["sector_key"] = canonical_sector
        candidate["market_bucket"] = market_bucket
        candidate["market_scope"] = "India-listed" if market_bucket == "india" else "International-listed"
        candidate["selection_score"] = round(score, 1)
        candidate["selection_notes"] = unique_reasons[:3]
        return candidate

    def get_etfs(self, sectors: List[str], signal: Dict = None) -> Dict:
        """
        Get ETF recommendations for a list of sectors.
        Returns a unified ranked ETF list across every mapped market, while
        retaining legacy India/global buckets for backward compatibility.
        Unknown sector keys are silently ignored.
        """
        india_etfs: List[Dict] = []
        global_etfs: List[Dict] = []
        ranked_candidates: List[Dict] = []
        by_market: Dict[str, List[Dict]] = defaultdict(list)
        seen_tickers: set = set()

        for raw_sector in sectors:
            canonical = self._resolve(raw_sector)
            mapping = ETF_DATABASE.get(canonical, {})

            for etf in mapping.get("india", []):
                if etf["ticker"] not in seen_tickers:
                    seen_tickers.add(etf["ticker"])
                    candidate = self._enrich_candidate(etf, canonical, "india", signal)
                    india_etfs.append(candidate)
                    ranked_candidates.append(candidate)
                    by_market[candidate["market_scope"]].append(candidate)

            for etf in mapping.get("global", []):
                if etf["ticker"] not in seen_tickers:
                    seen_tickers.add(etf["ticker"])
                    candidate = self._enrich_candidate(etf, canonical, "global", signal)
                    global_etfs.append(candidate)
                    ranked_candidates.append(candidate)
                    by_market[candidate["market_scope"]].append(candidate)

        ranked = sorted(
            ranked_candidates,
            key=lambda etf: (etf.get("selection_score", 0), etf.get("ticker", "")),
            reverse=True,
        )
        primary = ranked[0] if ranked else None

        return {
            "selection_method": "global-ranked",
            "primary": primary,
            "ranked": ranked[:6],
            "top_etfs": ranked[:3],
            "regional_alternatives": {
                market: sorted(
                    candidates,
                    key=lambda etf: (etf.get("selection_score", 0), etf.get("ticker", "")),
                    reverse=True,
                )[:3]
                for market, candidates in by_market.items()
            },
            "india": sorted(
                india_etfs,
                key=lambda etf: (etf.get("selection_score", 0), etf.get("ticker", "")),
                reverse=True,
            )[:4],
            "global": sorted(
                global_etfs,
                key=lambda etf: (etf.get("selection_score", 0), etf.get("ticker", "")),
                reverse=True,
            )[:5],
        }

    def list_all_tickers(self) -> List[str]:
        """Return all known tickers across the entire database."""
        tickers = []
        for sector_data in ETF_DATABASE.values():
            for bucket in ("india", "global"):
                for etf in sector_data.get(bucket, []):
                    tickers.append(etf["ticker"])
        return list(dict.fromkeys(tickers))  # preserve insertion order, deduplicate
