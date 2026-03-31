"""
classifier.py — AZALYST Sector Classification Engine

Multi-pass keyword classification with:
  - Weighted keyword scoring per sector
  - Negation handling (e.g. "ceasefire" reduces conflict score)
  - Multi-sector support (one article can trigger multiple sectors)
  - Article clustering by sector theme
  - Severity tagging (CRITICAL / HIGH / MEDIUM / LOW)
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Optional

log = logging.getLogger("azalyst.classifier")

# ── Sector Definitions ────────────────────────────────────────────────────────
# Format: { sector_id: { "label": str, "keywords": [(word, weight)], "negators": [word] } }

SECTOR_DEFINITIONS = {

    "energy_oil": {
        "label": "Energy / Oil & Gas",
        "emoji": "🛢️",
        "keywords": [
            ("oil", 3), ("crude", 4), ("petroleum", 3), ("brent", 4),
            ("wti", 4), ("opec", 5), ("opec+", 5), ("barrel", 3),
            ("energy", 2), ("gas", 2), ("natural gas", 4), ("lng", 4),
            ("pipeline", 3), ("refinery", 3), ("fuel", 2), ("gasoline", 2),
            ("oil supply", 5), ("oil price", 5), ("oil production", 4),
            ("shipping lane", 4), ("strait of hormuz", 8), ("red sea", 5),
            ("suez canal", 6), ("oil embargo", 7), ("energy crisis", 5),
            ("petrodollar", 4), ("oil sanctions", 6), ("drilling", 2),
            ("shale", 3), ("fracking", 3), ("energy security", 4),
        ],
        "negators": ["electric", "renewable", "solar", "wind energy", "ev charging"],
        "geopolitical_boost": ["iran", "saudi", "gulf", "middle east", "russia",
                               "venezuela", "libya", "nigeria"],
    },

    "defense": {
        "label": "Defense & Aerospace",
        "emoji": "🛡️",
        "keywords": [
            ("war", 4), ("military", 4), ("airstrike", 7), ("missile", 6),
            ("bomb", 4), ("attack", 3), ("conflict", 3), ("invasion", 7),
            ("troops", 4), ("army", 3), ("navy", 3), ("air force", 3),
            ("nato", 5), ("defense spending", 6), ("defense budget", 6),
            ("weapons", 4), ("arms", 3), ("ammunition", 4), ("drone", 4),
            ("fighter jet", 5), ("warship", 5), ("aircraft carrier", 6),
            ("ballistic", 5), ("hypersonic", 5), ("nuclear weapon", 7),
            ("rearmament", 6), ("defense contract", 5), ("pentagon", 5),
            ("military aid", 5), ("weapon supply", 5), ("warfare", 4),
            ("ceasefire", -3), ("peace deal", -4), ("disarmament", -5),
            ("artillery", 4), ("sanctions", 3), ("blockade", 4),
            ("geopolitical tension", 4), ("escalation", 5),
        ],
        "negators": [],
        "geopolitical_boost": ["ukraine", "russia", "israel", "iran", "taiwan",
                               "china", "north korea", "nato"],
    },

    "gold_precious_metals": {
        "label": "Gold & Precious Metals",
        "emoji": "🥇",
        "keywords": [
            ("gold", 5), ("silver", 3), ("precious metal", 5), ("bullion", 5),
            ("inflation", 4), ("hyperinflation", 6), ("stagflation", 5),
            ("interest rate", 3), ("fed rate", 4), ("rate hike", 4),
            ("rate cut", 4), ("dollar weakness", 5), ("usd weakness", 5),
            ("safe haven", 6), ("flight to safety", 7), ("risk off", 5),
            ("banking crisis", 6), ("bank collapse", 7), ("bank run", 6),
            ("currency debasement", 5), ("debt crisis", 5), ("default", 4),
            ("central bank gold", 6), ("gold reserve", 5), ("gold price", 5),
            ("platinum", 3), ("palladium", 3), ("xau", 5),
            ("federal reserve", 3), ("monetary policy", 3), ("quantitative easing", 4),
        ],
        "negators": ["cryptocurrency", "bitcoin gold"],
        "geopolitical_boost": ["war", "conflict", "crisis", "uncertainty",
                               "geopolitical", "recession", "inflation"],
    },

    "technology_ai": {
        "label": "Technology & AI / Semiconductors",
        "emoji": "💻",
        "keywords": [
            ("artificial intelligence", 6), ("ai ", 4), ("machine learning", 5),
            ("semiconductor", 6), ("chip", 5), ("nvidia", 5), ("tsmc", 5),
            ("intel", 3), ("amd", 3), ("broadcom", 3), ("qualcomm", 3),
            ("data center", 4), ("cloud computing", 4), ("tech", 2),
            ("technology", 2), ("silicon", 3), ("fab", 3), ("foundry", 3),
            ("export control", 4), ("chip ban", 6), ("chip restriction", 5),
            ("quantum computing", 5), ("robotics", 4), ("automation", 3),
            ("5g", 4), ("6g", 4), ("semiconductor supply chain", 6),
            ("taiwan", 4), ("chip war", 6), ("tech stock", 4),
            ("gpu", 4), ("cpu", 3), ("processor", 3),
        ],
        "negators": [],
        "geopolitical_boost": ["china", "taiwan", "usa", "export restriction",
                               "chip ban"],
    },

    "nuclear_uranium": {
        "label": "Nuclear Energy & Uranium",
        "emoji": "⚛️",
        "keywords": [
            ("nuclear", 4), ("uranium", 6), ("reactor", 5), ("enrichment", 5),
            ("nuclear plant", 5), ("nuclear energy", 5), ("nuclear power", 5),
            ("atomic", 3), ("radioactive", 3), ("fission", 4), ("fusion", 4),
            ("small modular reactor", 6), ("smr", 5), ("thorium", 4),
            ("nuclear deal", 5), ("iran nuclear", 7), ("nuclear weapon", 5),
            ("nonproliferation", 4), ("iaea", 5), ("uranium mine", 6),
            ("kazatomprom", 5), ("cameco", 5), ("yellow cake", 5),
            ("nuclear fuel", 5), ("energy transition", 3),
        ],
        "negators": [],
        "geopolitical_boost": ["iran", "north korea", "russia", "kazakhstan"],
    },

    "cybersecurity": {
        "label": "Cybersecurity",
        "emoji": "🔐",
        "keywords": [
            ("cyberattack", 7), ("cyber attack", 7), ("hacking", 5), ("hack", 4),
            ("ransomware", 7), ("malware", 6), ("data breach", 6),
            ("cybersecurity", 5), ("cyber threat", 5), ("cyber war", 7),
            ("critical infrastructure attack", 8), ("phishing", 4),
            ("zero-day", 6), ("vulnerability", 4), ("cve", 4),
            ("ddos", 5), ("espionage", 5), ("nation-state hack", 7),
            ("cyber espionage", 7), ("information warfare", 5),
            ("cisa", 4), ("nist", 3),
        ],
        "negators": [],
        "geopolitical_boost": ["russia", "china", "north korea", "iran", "government"],
    },

    "india_equity": {
        "label": "India Equity Markets",
        "emoji": "🇮🇳",
        "keywords": [
            ("india", 4), ("nifty", 6), ("sensex", 6), ("rbi", 5),
            ("sebi", 4), ("bse", 4), ("nse", 4), ("indian market", 5),
            ("indian economy", 4), ("india gdp", 4), ("rupee", 4),
            ("modi", 3), ("indian government", 3), ("india budget", 5),
            ("fii", 4), ("foreign investment india", 4), ("make in india", 3),
            ("india manufacturing", 3), ("india inflation", 4),
            ("india interest rate", 4), ("india growth", 3),
        ],
        "negators": [],
        "geopolitical_boost": ["india", "rbi", "sebi"],
    },

    "crypto_digital": {
        "label": "Crypto & Digital Assets",
        "emoji": "₿",
        "keywords": [
            ("bitcoin", 6), ("crypto", 5), ("ethereum", 5), ("blockchain", 4),
            ("defi", 4), ("stablecoin", 5), ("cbdc", 5), ("crypto regulation", 6),
            ("crypto ban", 6), ("sec crypto", 5), ("btc", 5), ("eth", 4),
            ("digital asset", 4), ("crypto exchange", 4), ("binance", 4),
            ("coinbase", 4), ("altcoin", 3), ("nft", 3), ("web3", 3),
            ("crypto etf", 6), ("spot bitcoin etf", 7),
        ],
        "negators": [],
        "geopolitical_boost": [],
    },

    "banking_financial": {
        "label": "Banking & Financial Sector",
        "emoji": "🏦",
        "keywords": [
            ("bank", 3), ("banking", 3), ("federal reserve", 4), ("ecb", 4),
            ("interest rate", 4), ("rate decision", 5), ("rate hike", 5),
            ("rate cut", 5), ("monetary policy", 4), ("credit crisis", 6),
            ("bank failure", 7), ("bank collapse", 7), ("credit default", 6),
            ("financial crisis", 7), ("recession", 5), ("yield curve", 5),
            ("bond yield", 4), ("treasury yield", 4), ("10-year yield", 4),
            ("debt ceiling", 5), ("sovereign debt", 5), ("imf", 4),
            ("basel", 3), ("stress test", 4), ("npl", 3), ("bad loan", 4),
        ],
        "negators": [],
        "geopolitical_boost": ["crisis", "collapse", "default", "panic"],
    },

    "commodities_mining": {
        "label": "Commodities & Mining",
        "emoji": "⛏️",
        "keywords": [
            ("copper", 5), ("iron ore", 5), ("lithium", 5), ("cobalt", 5),
            ("rare earth", 6), ("critical mineral", 6), ("nickel", 4),
            ("aluminum", 3), ("zinc", 3), ("commodity", 3), ("mining", 4),
            ("supply chain", 4), ("supply disruption", 5), ("tariff", 4),
            ("trade war", 5), ("commodity price", 4), ("raw material", 3),
            ("steel", 3), ("iron", 3), ("resource nationalism", 5),
            ("chile", 3), ("congo", 3), ("indonesia ban", 4),
        ],
        "negators": [],
        "geopolitical_boost": ["china", "trade war", "sanctions"],
    },

    "emerging_markets": {
        "label": "Emerging Markets",
        "emoji": "🌏",
        "keywords": [
            ("emerging market", 5), ("developing economy", 4), ("brics", 5),
            ("china", 3), ("brazil", 3), ("indonesia", 3), ("south africa", 3),
            ("vietnam", 3), ("thailand", 2), ("malaysia", 2), ("em equity", 5),
            ("em bond", 4), ("capital flow", 4), ("em currency", 4),
            ("dollar strength", 4), ("em outflow", 5), ("em inflow", 5),
        ],
        "negators": [],
        "geopolitical_boost": ["fed", "dollar", "rate"],
    },
}


def _score_text(text: str, keywords: List, negators: List, geo_boost: List) -> float:
    """Score a piece of text against a sector's keyword list."""
    score = 0.0
    text_lower = text.lower()

    for kw, weight in keywords:
        if kw in text_lower:
            score += weight

    # Apply negation dampening
    for neg in negators:
        if neg in text_lower:
            score *= 0.6

    # Geopolitical context boost
    for gk in geo_boost:
        if gk in text_lower:
            score += 2.0
            break  # One boost per article max

    return score


def _max_ts(*timestamps) -> Optional[datetime]:
    """Return the latest non-None datetime from an arbitrary list."""
    valid = [ts for ts in timestamps if ts is not None]
    if not valid:
        return None
    # Normalize all to UTC-aware before comparing
    aware = []
    for ts in valid:
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            aware.append(ts)
    return max(aware) if aware else None


class SectorClassifier:
    """
    Classifies articles into sector signals.
    Returns clusters: list of {sector, articles, top_headlines, severity}
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.min_articles = cfg.MIN_ARTICLES_FOR_SIGNAL

    def classify_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        Main classification pass.
        Returns list of sector signal clusters.
        """
        # Score every article against every sector
        sector_scores: Dict[str, List] = defaultdict(list)

        for art in articles:
            text = art["raw_text"]
            for sector_id, defn in SECTOR_DEFINITIONS.items():
                score = _score_text(
                    text,
                    defn["keywords"],
                    defn.get("negators", []),
                    defn.get("geopolitical_boost", []),
                )
                if score >= 4.0:   # Minimum relevance threshold
                    sector_scores[sector_id].append({
                        "article": art,
                        "relevance_score": score,
                    })

        # Build signal clusters
        signals = []
        for sector_id, scored_arts in sector_scores.items():
            if len(scored_arts) < self.min_articles:
                continue

            # Sort articles by relevance
            scored_arts.sort(key=lambda x: x["relevance_score"], reverse=True)

            # Top headlines (highest relevance)
            top_articles = [s["article"] for s in scored_arts[:8]]
            total_score   = sum(s["relevance_score"] for s in scored_arts)

            defn     = SECTOR_DEFINITIONS[sector_id]
            severity = self._determine_severity(total_score, len(scored_arts))

            signals.append({
                "sector_id":     sector_id,
                "sector_label":  defn["label"],
                "sector_emoji":  defn["emoji"],
                "sectors":       [sector_id],
                "articles":      top_articles,
                "article_count": len(scored_arts),
                "total_score":   total_score,
                "severity":      severity,
                "top_headlines": [a["title"] for a in top_articles[:5]],
                "regions":       list({a["region"] for a in top_articles}),
                "sources":       list({a["source"] for a in top_articles[:5]}),
                "latest_ts":     max(a["published"] for a in top_articles),
            })

        # Merge overlapping sector signals (e.g. war → defense + oil)
        signals = self._merge_correlated_signals(signals)

        # Sort by total score descending
        signals.sort(key=lambda x: x["total_score"], reverse=True)

        log.info(
            f"Classified {len(articles)} articles into {len(signals)} sector signals"
        )
        return signals

    def _determine_severity(self, total_score: float, article_count: int) -> str:
        """Severity based on aggregate score + volume."""
        adjusted = total_score * (1 + min(article_count, 20) / 20)
        if adjusted >= 150:
            return "CRITICAL"
        elif adjusted >= 80:
            return "HIGH"
        elif adjusted >= 40:
            return "MEDIUM"
        else:
            return "LOW"

    def _merge_correlated_signals(self, signals: List[Dict]) -> List[Dict]:
        """
        Combine correlated signals into multi-sector alerts.
        E.g. if defense AND energy both triggered from Middle East news,
        merge them into one combined signal.
        """
        merged = []
        used = set()

        for i, sig_a in enumerate(signals):
            if i in used:
                continue

            combined = dict(sig_a)
            combined_ids_a = {a["id"] for a in sig_a["articles"]}

            for j, sig_b in enumerate(signals):
                if j <= i or j in used:
                    continue

                ids_b = {a["id"] for a in sig_b["articles"]}
                overlap = len(combined_ids_a & ids_b) / max(len(combined_ids_a), 1)

                if overlap >= 0.35:
                    # Merge
                    combined["sectors"].extend(sig_b["sectors"])
                    combined["sector_label"] += f" + {sig_b['sector_label']}"
                    combined["sector_emoji"] += sig_b["sector_emoji"]
                    combined["total_score"]   += sig_b["total_score"] * 0.5
                    combined["article_count"] += sig_b["article_count"]
                    combined["top_headlines"] = list(
                        dict.fromkeys(
                            combined["top_headlines"] + sig_b["top_headlines"]
                        )
                    )[:6]
                    combined["regions"] = list(
                        set(combined["regions"]) | set(sig_b["regions"])
                    )
                    # FIX: take the latest timestamp across both signals.
                    # Previously only sig_a's latest_ts was kept, meaning a merged
                    # signal whose more-recent constituent was sig_b would score
                    # stale recency points.
                    combined["latest_ts"] = _max_ts(
                        combined.get("latest_ts"),
                        sig_b.get("latest_ts"),
                    )
                    used.add(j)

            merged.append(combined)
            used.add(i)

        return merged
