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

import re
from collections import defaultdict
from typing import Dict, List


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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "SPDR by State Street — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "1–3 months",
                "thesis":    "Largest US energy ETF. Holds Exxon, Chevron, ConocoPhillips. Direct oil price leverage.",
            },
            {
                "name":      "United States Oil Fund",
                "ticker":    "USO",
                "platform":  "USCF — IBKR / Schwab",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "1–4 weeks",
                "thesis":    "Direct WTI crude oil futures exposure. Short-term geopolitical supply-shock play.",
            },
            {
                "name":      "iShares Global Energy ETF",
                "ticker":    "IXC",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "$16B fund. RTX, GE Aerospace, Boeing, L3Harris. NATO rearmament cycle locked in for years.",
            },
            {
                "name":      "SPDR S&P Aerospace & Defense ETF",
                "ticker":    "XAR",
                "platform":  "SPDR by State Street — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Equal-weighted defense ETF — less concentration risk than ITA. Good diversification.",
            },
            {
                "name":      "Invesco Aerospace & Defense ETF",
                "ticker":    "PPA",
                "platform":  "Invesco — IBKR / Schwab / Fidelity",
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
                "platform":  "SPDR by State Street — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Low-Medium",
                "timeframe": "3–18 months",
                "thesis":    "Lowest-cost physical gold ETF (0.10% ER). JPMorgan targets $5,000/oz by Q4 2026.",
            },
            {
                "name":      "VanEck Gold Miners ETF",
                "ticker":    "GDX",
                "platform":  "VanEck — IBKR / Schwab",
                "exchange":  "NYSE",
                "risk":      "Medium-High",
                "timeframe": "3–9 months",
                "thesis":    "Gold miners offer 2–3x leverage to gold price. If gold surges, miners typically outperform.",
            },
            {
                "name":      "VanEck Junior Gold Miners ETF",
                "ticker":    "GDXJ",
                "platform":  "VanEck — IBKR / Schwab",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NASDAQ",
                "risk":      "Medium-High",
                "timeframe": "3–12 months",
                "thesis":    "The semiconductor cycle. Nvidia, Broadcom, AMD, TSMC ADR. AI infrastructure backbone.",
            },
            {
                "name":      "Invesco QQQ Trust",
                "ticker":    "QQQ",
                "platform":  "Invesco — IBKR / Schwab / Fidelity",
                "exchange":  "NASDAQ",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Top 100 NASDAQ companies. 50%+ tech. Diversified AI exposure with lower volatility than SOXX.",
            },
            {
                "name":      "Global X AI & Technology ETF",
                "ticker":    "AIQ",
                "platform":  "Global X — IBKR / Schwab",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "Sprott — IBKR / Schwab",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "6–24 months",
                "thesis":    "Physical uranium + major miners. Uranium in structural deficit through 2040. Early-cycle.",
            },
            {
                "name":      "Global X Uranium ETF",
                "ticker":    "URA",
                "platform":  "VanEck — IBKR / Schwab",
                "exchange":  "NYSE",
                "risk":      "High",
                "timeframe": "6–24 months",
                "thesis":    "Broader uranium + nuclear supply chain. Cameco, Kazatomprom. Lower concentration than URNM.",
            },
            {
                "name":      "Sprott Physical Uranium Trust",
                "ticker":    "SRUUF",
                "platform":  "Sprott — IBKR",
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
                "platform":  "ETFMG — IBKR / Schwab",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Palo Alto, CrowdStrike, Fortinet core holdings. Non-cyclical growth. Every geopolitical event drives demand.",
            },
            {
                "name":      "First Trust Nasdaq CEA Cybersecurity ETF",
                "ticker":    "CIBR",
                "platform":  "First Trust — IBKR / Schwab",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
                "exchange":  "NSE",
                "risk":      "Low-Medium",
                "timeframe": "6–18 months",
                "thesis":    "Broadest India equity exposure. Liquid, low cost. Core India macro play.",
            },
            {
                "name":      "Mirae Asset Nifty Midcap 150 ETF",
                "ticker":    "MIDCAPETF",
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
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
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NASDAQ",
                "risk":      "High",
                "timeframe": "1–6 months",
                "thesis":    "Spot Bitcoin ETF — regulated, institutional-grade BTC exposure. BlackRock backed.",
            },
            {
                "name":      "Bitwise Crypto Industry Innovators ETF",
                "ticker":    "BITQ",
                "platform":  "Bitwise — IBKR / Coinbase / Schwab",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "SPDR by State Street — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "1–6 months",
                "thesis":    "US financials ETF. JPMorgan, BofA, Wells Fargo. Rate and credit cycle play.",
            },
            {
                "name":      "SPDR Gold MiniShares Trust",
                "ticker":    "GLDM",
                "note":      "Flight to safety during banking stress",
                "platform":  "SPDR by State Street — IBKR / Schwab / Fidelity",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "Invesco — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–9 months",
                "thesis":    "Diversified commodity basket — energy, metals, agriculture. Broad commodity cycle play.",
            },
            {
                "name":      "Sprott Physical Copper Trust",
                "ticker":    "COPP",
                "platform":  "Sprott — IBKR / Schwab",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Broad EM exposure. China, India, Taiwan, Brazil. EM rotation play vs US equities.",
            },
            {
                "name":      "SPDR Portfolio Emerging Markets ETF",
                "ticker":    "SPEM",
                "platform":  "SPDR by State Street — IBKR / Schwab / Fidelity",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
                "exchange":  "NSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "India pharma majors — Sun Pharma, Dr Reddy's, Cipla. Generic drug exports + domestic demand.",
            },
            {
                "name":      "Nippon India Nifty Pharma ETF",
                "ticker":    "PHARMABEES",
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "SPDR by State Street — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Low-Medium",
                "timeframe": "6–18 months",
                "thesis":    "UnitedHealth, J&J, Eli Lilly, AbbVie. Defensive growth — non-cyclical demand driver.",
            },
            {
                "name":      "iShares Global Healthcare ETF",
                "ticker":    "IXJ",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Low-Medium",
                "timeframe": "6–18 months",
                "thesis":    "Global diversification — Roche, Novartis, Novo Nordisk (GLP-1 supercycle). Less US-centric.",
            },
            {
                "name":      "SPDR S&P Biotech ETF",
                "ticker":    "XBI",
                "platform":  "SPDR by State Street — IBKR / Schwab / Fidelity",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "Vanguard — IBKR / Fidelity / Schwab",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Largest US REIT ETF. 160+ REITs. Rate-sensitive: rallies when Fed cuts. Dividend yield ~4%.",
            },
            {
                "name":      "iShares Global REIT ETF",
                "ticker":    "REET",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NASDAQ",
                "risk":      "Medium-High",
                "timeframe": "6–24 months",
                "thesis":    "Solar, wind, renewable utilities globally. Policy tailwind from IRA + EU Green Deal.",
            },
            {
                "name":      "First Trust NASDAQ Clean Edge Green Energy ETF",
                "ticker":    "QCLN",
                "platform":  "First Trust — IBKR / Schwab",
                "exchange":  "NASDAQ",
                "risk":      "Medium-High",
                "timeframe": "6–18 months",
                "thesis":    "EV + clean energy blend — Tesla, ON Semi, Enphase. Captures the electrification megatrend.",
            },
            {
                "name":      "Invesco WilderHill Clean Energy ETF",
                "ticker":    "PBW",
                "platform":  "Invesco — IBKR / Schwab / Fidelity",
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
                "platform":  "Vanguard — IBKR / Fidelity / Schwab",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Broad European equities — UK, France, Germany, Switzerland. Cheap vs US on P/E basis.",
            },
            {
                "name":      "iShares MSCI Germany ETF",
                "ticker":    "EWG",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "German re-industrialisation + defence spending surge. DAX is undervalued vs US peers.",
            },
            {
                "name":      "iShares MSCI United Kingdom ETF",
                "ticker":    "EWU",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "FTSE-heavy: energy, financials, consumer staples. Value play — FTSE 100 is deeply discounted.",
            },
            {
                "name":      "iShares Europe ETF",
                "ticker":    "IEV",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
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
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Japan corporate reform + Nikkei record highs. BoJ normalisation adds FX tailwind for USD investors.",
            },
            {
                "name":      "iShares MSCI South Korea ETF",
                "ticker":    "EWY",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NYSE",
                "risk":      "Medium-High",
                "timeframe": "3–12 months",
                "thesis":    "Korea: Samsung, SK Hynix, POSCO. Memory chip & EV battery cycle play. Korea discount narrowing.",
            },
            {
                "name":      "Franklin FTSE Asia ex Japan ETF",
                "ticker":    "FLAX",
                "platform":  "Franklin Templeton — IBKR / Schwab",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "6–18 months",
                "thesis":    "Asia ex-Japan — India, China, Taiwan, Korea, ASEAN. Catch-up trade vs US equities.",
            },
            {
                "name":      "iShares China Large-Cap ETF",
                "ticker":    "FXI",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
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
                "platform":  "NSE/BSE listed — Zerodha / Dhan / Groww",
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
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
                "exchange":  "NASDAQ",
                "risk":      "Medium",
                "timeframe": "3–18 months",
                "thesis":    "Long-duration US Treasuries. Rallies hard when Fed cuts rates or risk-off hits. Classic safe haven.",
            },
            {
                "name":      "Vanguard Total Bond Market ETF",
                "ticker":    "BND",
                "platform":  "Vanguard — IBKR / Fidelity / Schwab",
                "exchange":  "NASDAQ",
                "risk":      "Low",
                "timeframe": "6–24 months",
                "thesis":    "Broad US bond market. Capital preservation with income. Low correlation to equities.",
            },
            {
                "name":      "iShares TIPS Bond ETF",
                "ticker":    "TIP",
                "platform":  "iShares by BlackRock — IBKR / Schwab / Fidelity",
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
