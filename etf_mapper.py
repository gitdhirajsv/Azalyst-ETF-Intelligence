"""
etf_mapper.py — AZALYST ETF Mapping Engine

Maps detected sectors to specific ETF recommendations.
Covers both Indian ETFs (Dhan App) and Global ETFs (INDmoney / Vested).

Each ETF entry includes:
  - name, ticker, platform, exchange
  - thesis: why it captures the sector signal
  - timeframe: typical trade horizon
  - risk: Low / Medium / High
"""

from typing import List, Dict


# ── Master ETF Database ───────────────────────────────────────────────────────
ETF_DATABASE = {

    "energy_oil": {
        "india": [
            {
                "name":      "Nippon India ETF Nifty PSU Bank BeES",
                "ticker":    "PSUBNKBEES",
                "note":      "PSU banks benefit from energy sector capex",
                "platform":  "Dhan App",
                "exchange":  "NSE/BSE",
                "risk":      "Medium",
                "timeframe": "1–6 months",
                "thesis":    "Indian PSU energy companies (ONGC, IOC) drive PSU bank credit. Energy capex cycle benefits.",
            },
            {
                "name":      "CPSE ETF",
                "ticker":    "CPSEETF",
                "note":      "Direct PSU energy exposure — ONGC, NTPC, Coal India",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "1–6 months",
                "thesis":    "CPSE ETF holds ONGC, Coal India, NTPC, BHEL. Direct play on India's energy sector.",
            },
        ],
        "global": [
            {
                "name":      "Energy Select Sector SPDR",
                "ticker":    "XLE",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "1–3 months",
                "thesis":    "Largest US energy ETF. Holds Exxon, Chevron, ConocoPhillips. Direct oil price leverage.",
            },
            {
                "name":      "United States Oil Fund",
                "ticker":    "USO",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "1–4 weeks",
                "thesis":    "Direct WTI crude oil futures exposure. Short-term geopolitical supply-shock play.",
            },
            {
                "name":      "iShares Global Energy ETF",
                "ticker":    "IXC",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "1–6 months",
                "thesis":    "Global energy diversification — Shell, BP, TotalEnergies, Saudi Aramco. Less US-centric.",
            },
        ],
    },

    "defense": {
        "india": [
            {
                "name":      "CPSE ETF",
                "ticker":    "CPSEETF",
                "note":      "BEL, HAL, BHEL included — India defense capex beneficiaries",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "India's defense indigenization (Make in India) drives HAL, BEL, Hindustan Aeronautics revenue.",
            },
            {
                "name":      "Mirae Asset Nifty India Defence ETF",
                "ticker":    "DEFENCEETF",
                "note":      "Pure-play India defense ETF",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium-High",
                "timeframe": "3–12 months",
                "thesis":    "India's ₹6+ lakh crore defense budget. HAL, BEL, DRDO suppliers benefit directly.",
            },
        ],
        "global": [
            {
                "name":      "iShares U.S. Aerospace & Defense ETF",
                "ticker":    "ITA",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "$16B fund. RTX, GE Aerospace, Boeing, L3Harris. NATO rearmament cycle locked in for years.",
            },
            {
                "name":      "SPDR S&P Aerospace & Defense ETF",
                "ticker":    "XAR",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Equal-weighted defense ETF — less concentration risk than ITA. Good diversification.",
            },
            {
                "name":      "Invesco Aerospace & Defense ETF",
                "ticker":    "PPA",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Broader definition includes cyber + space. Lockheed, Northrop, Raytheon core holdings.",
            },
        ],
    },

    "gold_precious_metals": {
        "india": [
            {
                "name":      "Nippon India Gold BeES",
                "ticker":    "GOLDBEES",
                "note":      "Largest Indian gold ETF by AUM",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Low-Medium",
                "timeframe": "3–18 months",
                "thesis":    "Tracks physical gold in INR. Double benefit: gold price rise + potential INR depreciation.",
            },
            {
                "name":      "HDFC Gold ETF",
                "ticker":    "HDFCGOLD",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Low-Medium",
                "timeframe": "3–18 months",
                "thesis":    "Physical gold backed. Very liquid. Safe haven in geopolitical or inflation-driven scenarios.",
            },
        ],
        "global": [
            {
                "name":      "SPDR Gold MiniShares Trust",
                "ticker":    "GLDM",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Low-Medium",
                "timeframe": "3–18 months",
                "thesis":    "Lowest-cost physical gold ETF (0.10% ER). JPMorgan targets $5,000/oz by Q4 2026.",
            },
            {
                "name":      "VanEck Gold Miners ETF",
                "ticker":    "GDX",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium-High",
                "timeframe": "3–9 months",
                "thesis":    "Gold miners offer 2–3x leverage to gold price. If gold surges, miners typically outperform.",
            },
            {
                "name":      "VanEck Junior Gold Miners ETF",
                "ticker":    "GDXJ",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "2–6 months",
                "thesis":    "Smaller miners — highest leverage to gold. High risk/reward. Use only for strong conviction.",
            },
        ],
    },

    "technology_ai": {
        "india": [
            {
                "name":      "Mirae Asset Nifty IT ETF",
                "ticker":    "MAFANG",
                "note":      "India IT sector ETF — TCS, Infosys, Wipro, HCL",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Indian IT majors benefit from global AI spend. USD-earning companies — rupee hedge embedded.",
            },
            {
                "name":      "Nippon India Nifty IT ETF",
                "ticker":    "NIFTYBEES",
                "note":      "Broad Nifty 50 — tech-heavy index",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Low-Medium",
                "timeframe": "6–18 months",
                "thesis":    "Nifty 50 is ~14% IT. Indirect India tech exposure with large-cap safety.",
            },
        ],
        "global": [
            {
                "name":      "iShares Semiconductor ETF",
                "ticker":    "SOXX",
                "platform":  "INDmoney / Vested",
                "exchange":  "NASDAQ",
                "risk":      "Medium-High",
                "timeframe": "3–12 months",
                "thesis":    "The semiconductor cycle. Nvidia, Broadcom, AMD, TSMC ADR. AI infrastructure backbone.",
            },
            {
                "name":      "Invesco QQQ Trust",
                "ticker":    "QQQ",
                "platform":  "INDmoney / Vested",
                "exchange":  "NASDAQ",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Top 100 NASDAQ companies. 50%+ tech. Diversified AI exposure with lower volatility than SOXX.",
            },
            {
                "name":      "Global X AI & Technology ETF",
                "ticker":    "AIQ",
                "platform":  "INDmoney / Vested",
                "exchange":  "NASDAQ",
                "risk":      "Medium-High",
                "timeframe": "3–12 months",
                "thesis":    "AI applications layer — includes software, cloud, robotics alongside chips.",
            },
        ],
    },

    "nuclear_uranium": {
        "india": [
            {
                "name":      "CPSE ETF",
                "ticker":    "CPSEETF",
                "note":      "NTPC (nuclear expansion) + BHEL included",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "6–24 months",
                "thesis":    "NTPC is building India's first fleet of small modular reactors. CPSE ETF captures this.",
            },
        ],
        "global": [
            {
                "name":      "Sprott Uranium Miners ETF",
                "ticker":    "URNM",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "6–24 months",
                "thesis":    "Physical uranium + major miners. Uranium in structural deficit through 2040. Early-cycle.",
            },
            {
                "name":      "Global X Uranium ETF",
                "ticker":    "URA",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "6–24 months",
                "thesis":    "Broader uranium + nuclear supply chain. Cameco, Kazatomprom. Lower concentration than URNM.",
            },
            {
                "name":      "Sprott Physical Uranium Trust",
                "ticker":    "SRUUF",
                "platform":  "INDmoney / Vested",
                "exchange":  "OTC",
                "risk":      "High",
                "timeframe": "12–36 months",
                "thesis":    "Holds physical uranium. Longer-term hold. Acts like gold but for nuclear fuel cycle.",
            },
        ],
    },

    "cybersecurity": {
        "india": [],
        "global": [
            {
                "name":      "ETFMG Prime Cyber Security ETF",
                "ticker":    "HACK",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Palo Alto, CrowdStrike, Fortinet core holdings. Non-cyclical growth. Every geopolitical event drives demand.",
            },
            {
                "name":      "First Trust Nasdaq CEA Cybersecurity ETF",
                "ticker":    "CIBR",
                "platform":  "INDmoney / Vested",
                "exchange":  "NASDAQ",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Larger, more diversified cyber ETF. Cisco, Broadcom's security arm, Palo Alto, Zscaler.",
            },
        ],
    },

    "india_equity": {
        "india": [
            {
                "name":      "Nippon India Nifty 50 BeES",
                "ticker":    "NIFTYBEES",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Low-Medium",
                "timeframe": "6–18 months",
                "thesis":    "Broadest India equity exposure. Liquid, low cost. Core India macro play.",
            },
            {
                "name":      "Mirae Asset Nifty Midcap 150 ETF",
                "ticker":    "MIDCAPETF",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium-High",
                "timeframe": "6–18 months",
                "thesis":    "India mid-cap growth. Higher beta than Nifty 50. Better for India growth thesis.",
            },
        ],
        "global": [
            {
                "name":      "iShares MSCI India ETF",
                "ticker":    "INDA",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "US-listed India equity ETF. USD-denominated India large-cap exposure.",
            },
        ],
    },

    "crypto_digital": {
        "india": [],
        "global": [
            {
                "name":      "iShares Bitcoin Trust ETF",
                "ticker":    "IBIT",
                "platform":  "INDmoney / Vested",
                "exchange":  "NASDAQ",
                "risk":      "High",
                "timeframe": "1–6 months",
                "thesis":    "Spot Bitcoin ETF — regulated, institutional-grade BTC exposure. BlackRock backed.",
            },
            {
                "name":      "Bitwise Crypto Industry Innovators ETF",
                "ticker":    "BITQ",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "1–6 months",
                "thesis":    "Crypto ecosystem companies — Coinbase, miners, blockchain infrastructure.",
            },
        ],
    },

    "banking_financial": {
        "india": [
            {
                "name":      "Nippon India ETF Bank BeES",
                "ticker":    "BANKBEES",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "1–6 months",
                "thesis":    "Top Indian private and PSU banks. Rate cut cycle could re-rate banking sector.",
            },
        ],
        "global": [
            {
                "name":      "Financial Select Sector SPDR",
                "ticker":    "XLF",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "1–6 months",
                "thesis":    "US financials ETF. JPMorgan, BofA, Wells Fargo. Rate and credit cycle play.",
            },
            {
                "name":      "SPDR Gold MiniShares Trust",
                "ticker":    "GLDM",
                "note":      "Flight to safety during banking stress",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Low-Medium",
                "timeframe": "1–3 months",
                "thesis":    "Banking crisis → gold safe haven. GLDM benefits from systemic financial stress.",
            },
        ],
    },

    "commodities_mining": {
        "india": [
            {
                "name":      "CPSE ETF",
                "ticker":    "CPSEETF",
                "note":      "NMDC, Coal India — commodity exposure",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "3–9 months",
                "thesis":    "NMDC (iron ore), Coal India in CPSE basket. India infrastructure demand driver.",
            },
        ],
        "global": [
            {
                "name":      "Invesco DB Commodity Index Tracking Fund",
                "ticker":    "DBC",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–9 months",
                "thesis":    "Diversified commodity basket — energy, metals, agriculture. Broad commodity cycle play.",
            },
            {
                "name":      "Sprott Physical Copper Trust",
                "ticker":    "COPP",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium-High",
                "timeframe": "3–12 months",
                "thesis":    "Copper is the backbone of electrification and AI infrastructure. Structural demand growth.",
            },
        ],
    },

    "emerging_markets": {
        "india": [
            {
                "name":      "Nippon India Nifty 50 BeES",
                "ticker":    "NIFTYBEES",
                "note":      "India as EM leader",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Low-Medium",
                "timeframe": "6–18 months",
                "thesis":    "India is the premier EM destination. Capital inflows support Nifty re-rating.",
            },
        ],
        "global": [
            {
                "name":      "iShares MSCI Emerging Markets ETF",
                "ticker":    "EEM",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Broad EM exposure. China, India, Taiwan, Brazil. EM rotation play vs US equities.",
            },
            {
                "name":      "SPDR Portfolio Emerging Markets ETF",
                "ticker":    "SPEM",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Lower cost EM alternative (0.07% ER). Similar coverage to EEM.",
            },
        ],
    },

    # ── NEW GLOBAL SECTORS ────────────────────────────────────────────────────

    "healthcare_pharma": {
        "india": [
            {
                "name":      "Mirae Asset Nifty Healthcare ETF",
                "ticker":    "HEALTHCARE",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "India pharma majors — Sun Pharma, Dr Reddy's, Cipla. Generic drug exports + domestic demand.",
            },
            {
                "name":      "Nippon India Nifty Pharma ETF",
                "ticker":    "PHARMABEES",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Pure Indian pharma play. Secular demand story — ageing population, US generics market.",
            },
        ],
        "global": [
            {
                "name":      "Health Care Select Sector SPDR",
                "ticker":    "XLV",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Low-Medium",
                "timeframe": "6–18 months",
                "thesis":    "UnitedHealth, J&J, Eli Lilly, AbbVie. Defensive growth — non-cyclical demand driver.",
            },
            {
                "name":      "iShares Global Healthcare ETF",
                "ticker":    "IXJ",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Low-Medium",
                "timeframe": "6–18 months",
                "thesis":    "Global diversification — Roche, Novartis, Novo Nordisk (GLP-1 supercycle). Less US-centric.",
            },
            {
                "name":      "SPDR S&P Biotech ETF",
                "ticker":    "XBI",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "3–12 months",
                "thesis":    "Equal-weighted biotech. High risk/reward. FDA catalyst-driven. For strong macro health signals.",
            },
        ],
    },

    "real_estate_reit": {
        "india": [
            {
                "name":      "Kotak Nifty Realty ETF",
                "ticker":    "REALTY",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium-High",
                "timeframe": "6–24 months",
                "thesis":    "India real estate cycle — DLF, Godrej Properties, Prestige. Rate cut tailwind.",
            },
        ],
        "global": [
            {
                "name":      "Vanguard Real Estate ETF",
                "ticker":    "VNQ",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Largest US REIT ETF. 160+ REITs. Rate-sensitive: rallies when Fed cuts. Dividend yield ~4%.",
            },
            {
                "name":      "iShares Global REIT ETF",
                "ticker":    "REET",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Global real estate — US, Japan, Australia, UK. Diversified property exposure with income.",
            },
        ],
    },

    "clean_energy_renewables": {
        "india": [
            {
                "name":      "Nippon India Nifty India New Energy ETF",
                "ticker":    "NEWENERGY",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "6–24 months",
                "thesis":    "India's energy transition — NTPC Green, Adani Green, solar/wind value chain. 500 GW target by 2030.",
            },
        ],
        "global": [
            {
                "name":      "iShares Global Clean Energy ETF",
                "ticker":    "ICLN",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NASDAQ",
                "risk":      "Medium-High",
                "timeframe": "6–24 months",
                "thesis":    "Solar, wind, renewable utilities globally. Policy tailwind from IRA + EU Green Deal.",
            },
            {
                "name":      "First Trust NASDAQ Clean Edge Green Energy ETF",
                "ticker":    "QCLN",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NASDAQ",
                "risk":      "Medium-High",
                "timeframe": "6–18 months",
                "thesis":    "EV + clean energy blend — Tesla, ON Semi, Enphase. Captures the electrification megatrend.",
            },
            {
                "name":      "Invesco WilderHill Clean Energy ETF",
                "ticker":    "PBW",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "3–12 months",
                "thesis":    "Pure-play clean energy innovators. High conviction play on renewable energy policy cycle.",
            },
        ],
    },

    "europe_equity": {
        "india": [],
        "global": [
            {
                "name":      "Vanguard FTSE Europe ETF",
                "ticker":    "VGK",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Broad European equities — UK, France, Germany, Switzerland. Cheap vs US on P/E basis.",
            },
            {
                "name":      "iShares MSCI Germany ETF",
                "ticker":    "EWG",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "German re-industrialisation + defence spending surge. DAX is undervalued vs US peers.",
            },
            {
                "name":      "iShares MSCI United Kingdom ETF",
                "ticker":    "EWU",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "FTSE-heavy: energy, financials, consumer staples. Value play — FTSE 100 is deeply discounted.",
            },
            {
                "name":      "iShares Europe ETF",
                "ticker":    "IEV",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "350+ European large/mid caps. Diversified vs single-country risk. ECB rate cut tailwind.",
            },
        ],
    },

    "asia_pacific": {
        "india": [],
        "global": [
            {
                "name":      "iShares MSCI Japan ETF",
                "ticker":    "EWJ",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Japan corporate reform + Nikkei record highs. BoJ normalisation adds FX tailwind for USD investors.",
            },
            {
                "name":      "iShares MSCI South Korea ETF",
                "ticker":    "EWY",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium-High",
                "timeframe": "3–12 months",
                "thesis":    "Korea: Samsung, SK Hynix, POSCO. Memory chip & EV battery cycle play. Korea discount narrowing.",
            },
            {
                "name":      "Franklin FTSE Asia ex Japan ETF",
                "ticker":    "FLAX",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Asia ex-Japan — India, China, Taiwan, Korea, ASEAN. Catch-up trade vs US equities.",
            },
            {
                "name":      "iShares China Large-Cap ETF",
                "ticker":    "FXI",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "1–6 months",
                "thesis":    "China stimulus-driven re-rating potential. Alibaba, Tencent, BYD. High geopolitical risk.",
            },
        ],
    },

    "bonds_fixed_income": {
        "india": [
            {
                "name":      "Bharat Bond ETF — April 2025",
                "ticker":    "BHARATBOND",
                "platform":  "Dhan App",
                "exchange":  "NSE",
                "risk":      "Low",
                "timeframe": "3–12 months",
                "thesis":    "AAA PSU bonds. Safe haven when equities sell off. Capital preservation with 7%+ yield.",
            },
        ],
        "global": [
            {
                "name":      "iShares 20+ Year Treasury Bond ETF",
                "ticker":    "TLT",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NASDAQ",
                "risk":      "Medium",
                "timeframe": "3–18 months",
                "thesis":    "Long-duration US Treasuries. Rallies hard when Fed cuts rates or risk-off hits. Classic safe haven.",
            },
            {
                "name":      "Vanguard Total Bond Market ETF",
                "ticker":    "BND",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NASDAQ",
                "risk":      "Low",
                "timeframe": "6–24 months",
                "thesis":    "Broad US bond market. Capital preservation with income. Low correlation to equities.",
            },
            {
                "name":      "iShares TIPS Bond ETF",
                "ticker":    "TIP",
                "platform":  "INDmoney / Vested / IBKR",
                "exchange":  "NYSE",
                "risk":      "Low-Medium",
                "timeframe": "6–24 months",
                "thesis":    "Inflation-protected US bonds. Outperforms nominal bonds when CPI surprises to the upside.",
            },
        ],
    },
}

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


class ETFMapper:
    """
    Maps sector signals to specific ETF recommendations.
    Supports global ETF database with sector aliasing.
    """

    @staticmethod
    def _resolve(sector_id: str) -> str:
        """Resolve a raw sector key to the canonical database key."""
        key = sector_id.lower().strip().split("|")[0].strip()
        return _SECTOR_ALIASES.get(key, key)

    def get_etfs(self, sectors: List[str]) -> Dict:
        """
        Get ETF recommendations for a list of sectors.
        Returns deduplicated India + Global ETF lists.
        Unknown sector keys are silently ignored.
        """
        india_etfs:  List[Dict] = []
        global_etfs: List[Dict] = []
        seen_tickers: set       = set()

        for raw_sector in sectors:
            canonical = self._resolve(raw_sector)
            mapping   = ETF_DATABASE.get(canonical, {})

            for etf in mapping.get("india", []):
                if etf["ticker"] not in seen_tickers:
                    seen_tickers.add(etf["ticker"])
                    india_etfs.append(etf)

            for etf in mapping.get("global", []):
                if etf["ticker"] not in seen_tickers:
                    seen_tickers.add(etf["ticker"])
                    global_etfs.append(etf)

        return {
            "india":  india_etfs[:4],   # Cap per report to keep Discord messages readable
            "global": global_etfs[:5],
        }

    def list_all_tickers(self) -> List[str]:
        """Return all known tickers across the entire database."""
        tickers = []
        for sector_data in ETF_DATABASE.values():
            for bucket in ("india", "global"):
                for etf in sector_data.get(bucket, []):
                    tickers.append(etf["ticker"])
        return list(dict.fromkeys(tickers))  # preserve insertion order, deduplicate
