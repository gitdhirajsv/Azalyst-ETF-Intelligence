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
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Broad EM exposure. China, India, Taiwan, Brazil. EM rotation play vs US equities.",
            },
            {
                "name":      "SPDR Portfolio Emerging Markets ETF",
                "ticker":    "SPEM",
                "platform":  "INDmoney / Vested",
                "exchange":  "NYSE",
                "risk":      "Medium",
                "timeframe": "3–12 months",
                "thesis":    "Lower cost EM alternative (0.07% ER). Similar coverage to EEM.",
            },
        ],
    },
}


class ETFMapper:
    """Maps sector signals to specific ETF recommendations."""

    def get_etfs(self, sectors: List[str]) -> Dict:
        """
        Get ETF recommendations for a list of sectors.
        Returns merged India + Global ETF lists.
        """
        india_etfs = []
        global_etfs = []
        seen_tickers = set()

        for sector_id in sectors:
            mapping = ETF_DATABASE.get(sector_id, {})

            for etf in mapping.get("india", []):
                if etf["ticker"] not in seen_tickers:
                    seen_tickers.add(etf["ticker"])
                    india_etfs.append(etf)

            for etf in mapping.get("global", []):
                if etf["ticker"] not in seen_tickers:
                    seen_tickers.add(etf["ticker"])
                    global_etfs.append(etf)

        return {
            "india":  india_etfs[:4],   # Cap to avoid overly long reports
            "global": global_etfs[:5],
        }
