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
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("azalyst.classifier")

# ── Keyword Expansion Merge ───────────────────────────────────────────────────
# Pull additional keywords from keyword_expansions.py (created separately so
# the LLM self-improver can edit them without touching this file's structure).
try:
    from keyword_expansions import KEYWORD_EXPANSIONS as _EXP
except ImportError:
    _EXP = {}


def _merge_keyword_expansions():
    """Idempotent merge: only adds keywords that aren't already present."""
    added = 0
    for sector_id, extra_kws in _EXP.items():
        if sector_id not in SECTOR_DEFINITIONS:
            continue
        existing = {kw for kw, _ in SECTOR_DEFINITIONS[sector_id]["keywords"]}
        for kw, weight in extra_kws:
            if kw not in existing:
                SECTOR_DEFINITIONS[sector_id]["keywords"].append((kw, weight))
                existing.add(kw)
                added += 1
    return added


# Sector definitions are populated below; the merge runs after they are defined.
def _post_definitions_setup():
    n = _merge_keyword_expansions()
    if n:
        logging.getLogger("azalyst.classifier").info(
            "Loaded %d additional keywords from keyword_expansions.py", n
        )

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
            ("artificial intelligence", 6), ("ai", 4), ("machine learning", 5),
            ("semiconductor", 6), ("chip", 5), ("nvidia", 5), ("tsmc", 5),
            ("intel", 3), ("amd", 3), ("broadcom", 3), ("qualcomm", 3),
            ("data center", 4), ("cloud computing", 4), ("tech", 2),
            ("technology", 2), ("silicon", 3), ("fab", 3), ("foundry", 3),
            ("export control", 4), ("chip ban", 6), ("chip restriction", 5),
            ("quantum computing", 5), ("robotics", 4), ("automation", 3),
            ("5g", 4), ("6g", 4), ("semiconductor supply chain", 6),
            ("taiwan", 4), ("chip war", 6), ("tech stock", 4),
            ("gpu", 4), ("cpu", 3), ("processor", 3),
            # ── NEW: Company coverage ──────────────────────────────────────
            ("asml", 6), ("micron", 5), ("sk hynix", 5), ("samsung electronics", 4),
            ("arm holdings", 4), ("lam research", 4), ("applied materials", 4),
            ("kla", 3), ("marvell", 3), ("on semiconductor", 3),
            ("analog devices", 3), ("texas instruments", 3), ("infineon", 3),
            ("microchip technology", 3), ("smic", 4), ("umc", 3),
            # ── NEW: Product / technical terms ────────────────────────────
            ("wafer", 4), ("chipmaker", 5), ("chip sales", 5),
            ("chip earnings", 5), ("chip revenue", 5), ("chip capacity", 4),
            ("hbm", 5), ("high bandwidth memory", 5), ("ai chip", 6),
            ("ai accelerator", 5), ("advanced packaging", 4),
            ("memory chip", 4), ("logic chip", 4), ("nand", 4), ("dram", 4),
            # ── NEW: Trade / tariff policy terms ──────────────────────────
            ("chip tariff", 6), ("semiconductor tariff", 6),
            ("chip exemption", 6), ("tariff exemption tech", 6),
            ("chip export ban", 6), ("semiconductor export ban", 6),
            ("chip export eased", 6), ("trade deal tech", 5),
            ("semiconductor deal", 5), ("tech tariff", 5),
        ],
        "negators": [],
        "geopolitical_boost": ["china", "taiwan", "usa", "export restriction",
                               "chip ban", "tariff", "trade deal"],
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

    "healthcare_pharma": {
        "label": "Healthcare & Pharma",
        "emoji": "💊",
        "keywords": [
            ("pharma", 4), ("pharmaceutical", 4), ("drug", 3), ("fda", 6),
            ("clinical trial", 5), ("vaccine", 5), ("biotech", 5), ("biopharmaceutical", 4),
            ("healthcare", 3), ("hospital", 3), ("medical device", 4), ("health insurance", 3),
            ("drug approval", 7), ("drug patent", 5), ("generic drug", 4),
            ("pandemic", 6), ("epidemic", 5), ("outbreak", 5), ("who", 3),
            ("cancer treatment", 5), ("gene therapy", 5), ("mrna", 5),
            ("medicare", 4), ("medicaid", 4), ("health reform", 4),
            ("drug pricing", 5), ("obesity drug", 6), ("glp-1", 6),
            ("novo nordisk", 5), ("eli lilly", 5), ("pfizer", 4), ("moderna", 4),
        ],
        "negators": [],
        "geopolitical_boost": ["pandemic", "outbreak", "health crisis"],
    },

    "clean_energy_renewables": {
        "label": "Clean Energy & Renewables",
        "emoji": "🌱",
        "keywords": [
            ("solar", 5), ("wind energy", 5), ("renewable", 4), ("clean energy", 5),
            ("ev", 4), ("electric vehicle", 5), ("battery", 4), ("lithium battery", 5),
            ("hydrogen", 5), ("green hydrogen", 6), ("fuel cell", 5),
            ("carbon neutral", 4), ("net zero", 5), ("carbon credit", 5),
            ("climate", 3), ("paris agreement", 4), ("carbon tax", 5),
            ("wind farm", 5), ("solar panel", 4), ("photovoltaic", 4),
            ("energy storage", 5), ("grid storage", 4), ("offshore wind", 5),
            ("tesla", 3), ("charging station", 3), ("decarbonization", 4),
            ("ira", 4), ("inflation reduction act", 6), ("green subsidy", 5),
        ],
        "negators": ["oil", "coal", "natural gas"],
        "geopolitical_boost": ["climate summit", "cop", "subsidy", "mandate"],
    },

    "real_estate_reit": {
        "label": "Real Estate & REITs",
        "emoji": "🏠",
        "keywords": [
            ("real estate", 5), ("reit", 6), ("property", 3), ("housing", 4),
            ("mortgage", 5), ("mortgage rate", 6), ("home price", 5),
            ("commercial real estate", 6), ("office vacancy", 5), ("rent", 3),
            ("housing market", 5), ("home sales", 4), ("construction", 3),
            ("housing bubble", 6), ("foreclosure", 5), ("landlord", 3),
            ("data center reit", 6), ("industrial reit", 5), ("warehouse", 3),
            ("zoning", 3), ("housing starts", 4), ("building permits", 4),
        ],
        "negators": [],
        "geopolitical_boost": ["rate cut", "rate hike", "fed", "mortgage crisis"],
    },

    # FIX: Added bonds_fixed_income to SECTOR_DEFINITIONS.
    # Previously this sector existed in etf_mapper.py (BND, TLT, TIP, BHARATBOND)
    # and in SECTOR_DIRECTION_TERMS below, but was missing here — so bond/rate
    # headlines were being misclassified into banking_financial and routed to
    # bank ETFs (XLF) instead of the correct fixed-income ETFs.
    "bonds_fixed_income": {
        "label": "Bonds & Fixed Income",
        "emoji": "📈",
        "keywords": [
            ("bond", 4), ("treasury", 5), ("yield", 4), ("fixed income", 5),
            ("10-year", 5), ("2-year", 4), ("30-year", 4), ("yield curve", 6),
            ("inversion", 5), ("bond auction", 5), ("coupon", 3),
            ("corporate bond", 5), ("high yield", 5), ("junk bond", 5),
            ("credit spread", 5), ("investment grade", 4), ("sovereign bond", 5),
            ("tips", 4), ("inflation-linked", 4), ("duration", 3),
            ("fed funds rate", 6), ("rate decision", 5), ("pivot", 4),
            ("quantitative tightening", 5), ("balance sheet", 3),
            ("debt issuance", 4), ("bond market", 5), ("private credit", 5),
            ("bnd", 4), ("tlt", 4), ("treasury bond", 5),
        ],
        "negators": [],
        "geopolitical_boost": ["fed", "ecb", "boj", "rbi", "recession", "default"],
    },

    "asia_pacific": {
        "label": "Asia Pacific Equity",
        "emoji": "🌏",
        "keywords": [
            ("japan", 4), ("nikkei", 6), ("boj", 5), ("yen", 4),
            ("south korea", 4), ("kospi", 5), ("samsung", 3),
            ("australia", 3), ("asx", 4), ("new zealand", 2),
            ("asean", 4), ("asia pacific", 5), ("pacific rim", 3),
            ("japan stimulus", 5), ("yen weakness", 5), ("carry trade", 5),
            ("abenomics", 4), ("japan rate", 5), ("ycc", 5),
            ("hong kong", 3), ("hang seng", 5), ("shanghai", 3),
            ("china gdp", 4), ("china stimulus", 5), ("china property", 5),
        ],
        "negators": [],
        "geopolitical_boost": ["taiwan", "south china sea", "boj", "pboc"],
    },

    "europe_equity": {
        "label": "Europe Equity",
        "emoji": "🇪🇺",
        "keywords": [
            ("europe", 3), ("eurozone", 5), ("ecb", 5), ("euro", 3),
            ("dax", 5), ("ftse", 4), ("cac", 4), ("stoxx", 5),
            ("germany", 3), ("france", 3), ("uk", 2), ("britain", 3),
            ("european central bank", 5), ("ecb rate", 6), ("eu fiscal", 4),
            ("eu regulation", 4), ("eu tariff", 5), ("brexit", 4),
            ("european defense", 5), ("eu spending", 4), ("eu gdp", 4),
            ("bank of england", 4), ("boe", 4), ("gilt", 4),
        ],
        "negators": [],
        "geopolitical_boost": ["ukraine", "russia", "ecb", "nato", "energy crisis"],
    },
}

SECTOR_DIRECTION_TERMS = {
    "energy_oil": {
        "bullish": [
            ("surge", 2.0), ("spike", 2.0), ("jump", 1.5), ("rally", 1.5),
            ("shortage", 2.0), ("supply disruption", 2.5), ("production cuts", 2.0),
            ("embargo", 2.0), ("sanctions", 1.5),
        ],
        "bearish": [
            ("fall", 2.0), ("drop", 2.0), ("slump", 2.0), ("decline", 1.5),
            ("oversupply", 2.0), ("glut", 2.0), ("ceasefire", 1.5),
            ("production increase", 2.0), ("supply recovery", 1.5),
        ],
    },
    "gold_precious_metals": {
        "bullish": [
            ("safe haven", 2.0), ("flight to safety", 2.0), ("inflation surge", 2.0),
            ("rate cut", 1.5), ("dollar weakness", 2.0), ("banking stress", 2.0),
        ],
        "bearish": [
            ("rate hike", 2.0), ("dollar strength", 2.0), ("real yields rise", 2.0),
            ("risk appetite", 1.5), ("disinflation", 1.5),
        ],
    },
    "technology_ai": {
        "bullish": [
            ("beat estimates", 2.0), ("capex increase", 2.0), ("ai demand", 2.0),
            ("chip demand", 2.0), ("orders surge", 1.5), ("investment boom", 1.5),
            # ── NEW: Trade / tariff relief ─────────────────────────────────
            ("tariff exemption", 2.5), ("tariff relief", 2.5), ("tariff pause", 2.5),
            ("trade deal", 2.0), ("ban lifted", 2.5), ("restrictions eased", 2.0),
            ("export ban eased", 2.5), ("chip export allowed", 2.5),
            # ── NEW: Financial outperformance ──────────────────────────────
            ("earnings beat", 2.0), ("revenue beat", 2.0), ("guidance raised", 2.5),
            ("record revenue", 2.0), ("record shipments", 2.0),
            ("strong chip demand", 2.5), ("chip sales surge", 2.5),
            ("wafer demand", 2.0), ("memory recovery", 2.0),
            ("hbm demand", 2.5), ("ai chip orders", 2.5),
        ],
        "bearish": [
            ("export controls tighten", 2.0), ("guidance cut", 2.0), ("slowdown", 1.5),
            ("inventory glut", 2.0), ("demand weakness", 2.0), ("chip restrictions", 2.0),
            ("chip ban tightened", 2.5), ("tariff escalation tech", 2.5),
            ("revenue miss", 2.0), ("guidance lowered", 2.0),
        ],
    },
    "nuclear_uranium": {
        "bullish": [
            ("reactor approval", 2.0), ("supply deficit", 2.0), ("contracting cycle", 1.5),
            ("buildout", 1.5), ("energy security", 1.5),
        ],
        "bearish": [
            ("mine restart", 1.5), ("oversupply", 2.0), ("project delay", 1.5),
            ("shutdown", 2.0),
        ],
    },
    "cybersecurity": {
        "bullish": [
            ("breach", 2.0), ("cyberattack", 2.0), ("ransomware", 2.0),
            ("security spending", 1.5), ("nation-state", 1.5),
        ],
        "bearish": [
            ("budget cuts", 2.0), ("spending slowdown", 1.5), ("deal cancellation", 1.5),
        ],
    },
    "india_equity": {
        "bullish": [
            ("rate cut", 1.5), ("inflows", 2.0), ("gdp growth", 1.5),
            ("budget boost", 1.5), ("manufacturing expansion", 1.5),
        ],
        "bearish": [
            ("outflows", 2.0), ("inflation spike", 1.5), ("rate hike", 1.5),
            ("rupee weakness", 1.5), ("earnings miss", 1.5),
        ],
    },
    "crypto_digital": {
        "bullish": [
            ("etf inflows", 2.0), ("approval", 1.5), ("adoption", 1.5),
            ("halving", 1.5), ("institutional buying", 2.0),
        ],
        "bearish": [
            ("ban", 2.0), ("hack", 2.0), ("liquidation", 1.5),
            ("outflows", 1.5), ("enforcement action", 2.0),
        ],
    },
    "banking_financial": {
        "bullish": [
            ("rate cuts", 1.5), ("soft landing", 1.5), ("credit growth", 1.5),
            ("capital return", 1.5), ("deposit growth", 1.5),
        ],
        "bearish": [
            ("bank run", 2.0), ("defaults rise", 2.0), ("credit stress", 2.0),
            ("yield curve inversion", 1.5), ("funding stress", 2.0),
        ],
    },
    "commodities_mining": {
        "bullish": [
            ("supply disruption", 2.0), ("inventory draw", 1.5), ("demand surge", 1.5),
            ("export restrictions", 2.0),
        ],
        "bearish": [
            ("oversupply", 2.0), ("inventory build", 1.5), ("demand slowdown", 2.0),
            ("price collapse", 2.0),
        ],
    },
    "emerging_markets": {
        "bullish": [
            ("inflows", 2.0), ("dollar weakness", 2.0), ("rate cuts", 1.5),
            ("growth acceleration", 1.5),
        ],
        "bearish": [
            ("outflows", 2.0), ("dollar strength", 2.0), ("devaluation", 2.0),
            ("capital flight", 2.0),
        ],
    },
    "healthcare_pharma": {
        "bullish": [
            ("fda approval", 2.0), ("drug approval", 2.0), ("breakthrough", 1.5),
            ("clinical success", 2.0), ("patent", 1.5), ("obesity drug demand", 2.0),
        ],
        "bearish": [
            ("drug recall", 2.0), ("trial failure", 2.0), ("patent cliff", 2.0),
            ("pricing regulation", 1.5), ("fda rejection", 2.0),
        ],
    },
    "clean_energy_renewables": {
        "bullish": [
            ("subsidy", 2.0), ("mandate", 1.5), ("investment boom", 2.0),
            ("capacity expansion", 1.5), ("cost reduction", 1.5),
        ],
        "bearish": [
            ("subsidy cut", 2.0), ("tariff", 2.0), ("overcapacity", 1.5),
            ("policy reversal", 2.0), ("funding pulled", 1.5),
        ],
    },
    "real_estate_reit": {
        "bullish": [
            ("rate cut", 2.0), ("housing demand", 1.5), ("rent growth", 1.5),
            ("occupancy", 1.5), ("construction boom", 1.5),
        ],
        "bearish": [
            ("rate hike", 2.0), ("vacancy", 2.0), ("foreclosure", 2.0),
            ("office downturn", 2.0), ("mortgage stress", 2.0),
        ],
    },
    "bonds_fixed_income": {
        "bullish": [
            ("rate cut", 2.0), ("pivot", 2.0), ("flight to safety", 2.0),
            ("dovish", 1.5), ("recession fear", 1.5),
        ],
        "bearish": [
            ("rate hike", 2.0), ("hawkish", 1.5), ("inflation surprise", 2.0),
            ("bond selloff", 2.0), ("yield surge", 2.0),
        ],
    },
    "asia_pacific": {
        "bullish": [
            ("stimulus", 2.0), ("yen weakness", 1.5), ("reform", 1.5),
            ("earnings beat", 1.5), ("inflows", 2.0),
        ],
        "bearish": [
            ("yen strength", 2.0), ("china slowdown", 2.0), ("outflows", 2.0),
            ("property crisis", 2.0), ("deflation", 1.5),
        ],
    },
    "europe_equity": {
        "bullish": [
            ("ecb cut", 2.0), ("fiscal stimulus", 2.0), ("defense spending", 1.5),
            ("growth surprise", 1.5), ("inflows", 2.0),
        ],
        "bearish": [
            ("energy crisis", 2.0), ("recession", 2.0), ("fragmentation", 1.5),
            ("ecb hike", 2.0), ("political crisis", 1.5),
        ],
    },
}

ML_DIRECTION_ALIGNMENTS = {
    "asia_pacific": 1.0,
    "banking_financial": 1.0,
    "bonds_fixed_income": 1.0,
    "clean_energy_renewables": 1.0,
    "crypto_digital": 1.0,
    "emerging_markets": 1.0,
    "europe_equity": 1.0,
    "healthcare_pharma": 1.0,
    "india_equity": 1.0,
    "real_estate_reit": 1.0,
    "technology_ai": 1.0,
}

# ── Run the expansion merge now that SECTOR_DEFINITIONS exists ────────────────
_post_definitions_setup()

ML_HYBRID_DIRECTION_WEIGHT = 2.5


class FinancialSentimentModel:
    """Optional finance-tuned sentiment layer with graceful fallback."""

    def __init__(self, cfg):
        self.enabled = bool(getattr(cfg, "ML_SENTIMENT_ENABLED", False))
        self.mode = getattr(cfg, "ML_SENTIMENT_MODE", "shadow")
        self.model_name = getattr(cfg, "ML_SENTIMENT_MODEL", "ProsusAI/finbert")
        self.min_confidence = float(getattr(cfg, "ML_SENTIMENT_MIN_CONFIDENCE", 0.58))
        self._pipeline = None
        self._disabled_reason = ""
        self._cache: Dict[str, Dict] = {}

    def _ensure_pipeline(self):
        if not self.enabled:
            return None
        if self._pipeline is not None:
            return self._pipeline
        if self._disabled_reason:
            return None
        try:
            from transformers import pipeline
            self._pipeline = pipeline(
                "text-classification",
                model=self.model_name,
                tokenizer=self.model_name,
            )
        except Exception as exc:
            self._disabled_reason = str(exc)
            log.warning("ML sentiment disabled, using rules-only fallback: %s", exc)
            return None
        return self._pipeline

    def analyze(self, text: str) -> Dict:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())[:1000]
        if not cleaned:
            return {
                "enabled": False,
                "available": False,
                "model": self.model_name,
                "label": "NEUTRAL",
                "confidence": 0.0,
                "signed_score": 0.0,
            }
        if cleaned in self._cache:
            return dict(self._cache[cleaned])

        pipe = self._ensure_pipeline()
        if not pipe:
            result = {
                "enabled": self.enabled,
                "available": False,
                "model": self.model_name,
                "label": "NEUTRAL",
                "confidence": 0.0,
                "signed_score": 0.0,
            }
            self._cache[cleaned] = result
            return dict(result)

        try:
            raw = pipe(cleaned, truncation=True)[0]
            label_raw = str(raw.get("label", "neutral")).upper()
            confidence = float(raw.get("score", 0.0) or 0.0)
        except Exception as exc:
            log.warning("ML sentiment inference failed, reverting to rules-only: %s", exc)
            self._disabled_reason = str(exc)
            result = {
                "enabled": self.enabled,
                "available": False,
                "model": self.model_name,
                "label": "NEUTRAL",
                "confidence": 0.0,
                "signed_score": 0.0,
            }
            self._cache[cleaned] = result
            return dict(result)

        if "POS" in label_raw:
            label = "POSITIVE"
            sign = 1.0
        elif "NEG" in label_raw:
            label = "NEGATIVE"
            sign = -1.0
        else:
            label = "NEUTRAL"
            sign = 0.0

        signed_score = sign * confidence if confidence >= self.min_confidence else 0.0
        if signed_score == 0.0:
            label = "NEUTRAL"

        result = {
            "enabled": True,
            "available": True,
            "model": self.model_name,
            "label": label,
            "confidence": round(confidence, 4),
            "signed_score": round(signed_score, 4),
        }
        self._cache[cleaned] = result
        return dict(result)

    def directional_bias(self, sector_id: str, analysis: Dict) -> float:
        if self.mode != "hybrid":
            return 0.0
        alignment = ML_DIRECTION_ALIGNMENTS.get(sector_id, 0.0)
        if alignment == 0.0:
            return 0.0
        return round(float(analysis.get("signed_score", 0.0) or 0.0) * ML_HYBRID_DIRECTION_WEIGHT * alignment, 2)


@lru_cache(maxsize=512)
def _compile_term_pattern(term: str) -> re.Pattern:
    escaped = re.escape(term.strip().lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


def _contains_term(text_lower: str, term: str) -> bool:
    return bool(_compile_term_pattern(term).search(text_lower))


def _directional_score(text: str, sector_id: str) -> float:
    text_lower = text.lower()
    terms = SECTOR_DIRECTION_TERMS.get(sector_id, {})
    bullish = sum(weight for term, weight in terms.get("bullish", []) if _contains_term(text_lower, term))
    bearish = sum(weight for term, weight in terms.get("bearish", []) if _contains_term(text_lower, term))
    return round(bullish - bearish, 2)


def _direction_label(score: float) -> str:
    if score >= 2.0:
        return "BULLISH"
    if score <= -2.0:
        return "BEARISH"
    return "NEUTRAL"


def _sentiment_label(score: float) -> str:
    if score >= 0.15:
        return "POSITIVE"
    if score <= -0.15:
        return "NEGATIVE"
    return "NEUTRAL"


def _score_text(text: str, keywords: List, negators: List, geo_boost: List) -> float:
    """Score a piece of text against a sector's keyword list."""
    score = 0.0
    text_lower = text.lower()

    for kw, weight in keywords:
        if _contains_term(text_lower, kw):
            score += weight

    for neg in negators:
        if _contains_term(text_lower, neg):
            score *= 0.6

    for gk in geo_boost:
        if _contains_term(text_lower, gk):
            score += 2.0
            break

    return score


def _max_ts(*timestamps) -> Optional[datetime]:
    """Return the latest non-None datetime from an arbitrary list."""
    valid = [ts for ts in timestamps if ts is not None]
    if not valid:
        return None
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
        self.sentiment_model = FinancialSentimentModel(cfg)

    def classify_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        Main classification pass.
        Returns list of sector signal clusters.
        """
        sector_scores: Dict[str, List] = defaultdict(list)

        for art in articles:
            text = art["raw_text"]
            sentiment = self.sentiment_model.analyze(
                f"{art.get('title', '')}. {art.get('description', '')}"
            )
            for sector_id, defn in SECTOR_DEFINITIONS.items():
                score = _score_text(
                    text,
                    defn["keywords"],
                    defn.get("negators", []),
                    defn.get("geopolitical_boost", []),
                )
                rule_direction_score = _directional_score(text, sector_id)
                ml_direction_score = self.sentiment_model.directional_bias(sector_id, sentiment)
                direction_score = round(rule_direction_score + ml_direction_score, 2)
                if score >= 4.0:
                    sector_scores[sector_id].append({
                        "article": art,
                        "relevance_score": score,
                        "rule_direction_score": rule_direction_score,
                        "ml_direction_score": ml_direction_score,
                        "direction_score": direction_score,
                        "ml_sentiment_label": sentiment.get("label", "NEUTRAL"),
                        "ml_sentiment_confidence": sentiment.get("confidence", 0.0),
                        "ml_sentiment_score": sentiment.get("signed_score", 0.0),
                    })

        signals = []
        for sector_id, scored_arts in sector_scores.items():
            if len(scored_arts) < self.min_articles:
                continue

            scored_arts.sort(key=lambda x: x["relevance_score"], reverse=True)

            top_articles = [s["article"] for s in scored_arts[:8]]
            total_score = sum(s["relevance_score"] for s in scored_arts)
            avg_article_score = round(total_score / max(len(scored_arts), 1), 2)
            direction_score = round(sum(s.get("direction_score", 0.0) for s in scored_arts), 2)
            ml_sentiment_score = round(
                sum(s.get("ml_sentiment_score", 0.0) for s in scored_arts) / max(len(scored_arts), 1),
                4,
            )

            defn = SECTOR_DEFINITIONS[sector_id]
            severity, event_intensity = self._determine_severity(scored_arts, direction_score)

            signals.append({
                "sector_id":     sector_id,
                "sector_label":  defn["label"],
                "sector_emoji":  defn["emoji"],
                "sectors":       [sector_id],
                "articles":      top_articles,
                "article_count": len(scored_arts),
                "total_score":   total_score,
                "avg_article_score": avg_article_score,
                "direction_score": direction_score,
                "direction":     _direction_label(direction_score),
                "severity":      severity,
                "event_intensity": event_intensity,
                "ml_sentiment_label": _sentiment_label(ml_sentiment_score),
                "ml_sentiment_score": ml_sentiment_score,
                "ml_sentiment_model": self.sentiment_model.model_name,
                "ml_sentiment_mode": self.sentiment_model.mode,
                "top_headlines": [a["title"] for a in top_articles[:5]],
                "regions":       list({s["article"]["region"] for s in scored_arts}),
                "sources":       list({s["article"]["source"] for s in scored_arts}),
                "latest_ts":     max(a["published"] for a in top_articles),
            })

        signals = self._merge_correlated_signals(signals)
        signals.sort(key=lambda x: x["total_score"], reverse=True)

        log.info(
            f"Classified {len(articles)} articles into {len(signals)} sector signals"
        )
        return signals

    @staticmethod
    def _severity_from_intensity(intensity: float) -> str:
        if intensity >= 20:
            return "CRITICAL"
        elif intensity >= 13:
            return "HIGH"
        elif intensity >= 7:
            return "MEDIUM"
        return "LOW"

    def _determine_severity(self, scored_arts: List[Dict], direction_score: float) -> Tuple[str, float]:
        if not scored_arts:
            return "LOW", 0.0

        relevance_scores = [float(item.get("relevance_score", 0.0) or 0.0) for item in scored_arts]
        avg_score = sum(relevance_scores) / len(relevance_scores)
        regions = {
            item.get("article", {}).get("region", "global")
            for item in scored_arts
            if item.get("article", {}).get("region")
        }
        non_global_regions = {region for region in regions if region != "global"}
        high_conviction_ratio = (
            sum(1 for score in relevance_scores if score >= 10.0) / len(relevance_scores)
        )
        avg_direction_strength = abs(direction_score) / len(scored_arts)
        intensity = (
            avg_score * 1.35
            + min(len(non_global_regions), 4) * 1.5
            + min(avg_direction_strength, 4.0) * 1.1
            + high_conviction_ratio * 4.0
        )
        intensity = round(intensity, 2)
        return self._severity_from_intensity(intensity), intensity

    def _merge_correlated_signals(self, signals: List[Dict]) -> List[Dict]:
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
                    original_count = max(combined.get("article_count", 1), 1)
                    other_count = max(sig_b.get("article_count", 1), 1)
                    combined["sectors"].extend(sig_b["sectors"])
                    combined["sector_label"] += f" + {sig_b['sector_label']}"
                    combined["sector_emoji"] += sig_b["sector_emoji"]
                    combined["total_score"] += sig_b["total_score"] * 0.5
                    combined["direction_score"] = round(
                        combined.get("direction_score", 0.0) + sig_b.get("direction_score", 0.0),
                        2,
                    )
                    combined["direction"] = _direction_label(combined["direction_score"])
                    combined_articles = list(combined.get("articles", []))
                    combined_articles.extend(
                        article for article in sig_b.get("articles", [])
                        if article.get("id") not in combined_ids_a
                    )
                    combined["articles"] = combined_articles[:12]
                    combined_ids_a |= ids_b
                    combined["article_count"] = len(combined_articles)
                    combined["avg_article_score"] = round(
                        combined["total_score"] / max(combined["article_count"], 1),
                        2,
                    )
                    weighted_ml = (
                        combined.get("ml_sentiment_score", 0.0) * original_count
                        + sig_b.get("ml_sentiment_score", 0.0) * other_count
                    ) / max(original_count + other_count, 1)
                    combined["ml_sentiment_score"] = round(weighted_ml, 4)
                    combined["ml_sentiment_label"] = _sentiment_label(combined["ml_sentiment_score"])
                    combined["event_intensity"] = round(
                        max(combined.get("event_intensity", 0.0), sig_b.get("event_intensity", 0.0)) + 1.0,
                        2,
                    )
                    combined["severity"] = self._severity_from_intensity(combined["event_intensity"])
                    combined["top_headlines"] = list(
                        dict.fromkeys(
                            combined["top_headlines"] + sig_b["top_headlines"]
                        )
                    )[:6]
                    combined["regions"] = list(dict.fromkeys(combined["regions"] + sig_b["regions"]))
                    combined["sources"] = list(dict.fromkeys(combined.get("sources", []) + sig_b.get("sources", [])))
                    combined["latest_ts"] = _max_ts(
                        combined.get("latest_ts"),
                        sig_b.get("latest_ts"),
                    )
                    used.add(j)

            merged.append(combined)
            used.add(i)

        return merged
