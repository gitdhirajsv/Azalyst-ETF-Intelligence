"""Azalyst-Alpha-Free — drop-in alpha layer for Azalyst-ETF-Intelligence."""

__version__ = "0.2.0"

# Universe = ETFs the cross-sectional ranker scores. IBKR-tradeable, liquid.
# Final list deduplicated below via dict.fromkeys.
ETF_UNIVERSE = [
    # ─────────── BROAD MARKET ───────────
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "IVV", "ITOT",
    "VV", "SCHB", "SCHX", "SCHM", "SCHA",
    "RSP", "OEF",  # equal-weight S&P, S&P 100

    # ─────────── FACTORS / SMART BETA ───────────
    "MTUM", "QUAL", "USMV", "VLUE", "SIZE",
    "SPLV", "SPHB", "SPHQ", "SPMO",
    "SCHG", "SCHD", "VYM", "VIG", "DGRO", "NOBL", "SDY", "DVY", "HDV",
    "AVUV", "AVDV", "AVUS", "AVDE", "AVEM",  # Avantis active-factor
    "DGRW", "REGL",
    "JEPI", "JEPQ", "DIVO",  # covered call income

    # ─────────── ESG / SUSTAINABLE ───────────
    "ESGV", "USSG", "ESGU", "SUSL", "DSI",

    # ─────────── US SECTORS (Select Sector SPDRs + alternatives) ───────────
    "XLE", "XLF", "XLK", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC",
    "VDE", "VGT", "VFH", "VHT", "VIS", "VCR", "VDC", "VPU", "VAW", "VOX", "VNQ",
    "FTEC", "FNCL", "FHLC", "FUTY", "FIDU", "FSTA", "FENY", "FREL",
    "IYW", "IYH", "IYE", "IYF", "IYG", "IYR", "IYJ", "IYK", "IYZ", "IYM", "IDU", "ITB",

    # ─────────── TECH / SOFTWARE / SEMIS / AI ───────────
    "SOXX", "SMH", "SOXL", "SOXS", "USD", "TQQQ", "QLD", "FNGS", "FNGU",
    "IGV", "FDN", "WCLD", "CLOU", "SKYY",
    "ARKK", "ARKW", "ARKQ", "ARKF", "ARKG", "ARKX",
    "AIQ", "ROBO", "BOTZ", "KOMP", "GNOM", "PRNT",
    "XSD", "PSI", "FTXL", "CHIP", "QTUM",
    "BLOK", "DAPP", "WTAI", "IRBO",

    # ─────────── CYBERSECURITY ───────────
    "HACK", "CIBR", "BUG", "WCBR", "IHAK",

    # ─────────── DEFENSE & AEROSPACE ───────────
    "ITA", "PPA", "XAR", "DFEN", "SHLD",

    # ─────────── NUCLEAR & URANIUM ───────────
    "URA", "URNM", "URNJ", "NLR",

    # ─────────── GOLD & PRECIOUS METALS ───────────
    "GLD", "IAU", "GLDM", "SGOL", "BAR", "PHYS", "AAAU", "OUNZ", "IAUM",
    "SLV", "PSLV", "SIVR",
    "GDX", "GDXJ", "RING", "GOEX", "SGDM",
    "SIL", "SILJ",
    "PPLT", "PALL", "GLTR", "DBP",

    # ─────────── ENERGY / OIL & GAS ───────────
    "XLE", "VDE", "IYE", "IXC", "FILL", "ENRG",
    "XOP", "OIH", "IEO", "FCG", "CRAK", "PXJ", "XES",
    "USO", "USL", "DBO", "BNO", "UCO", "SCO", "OILK",
    "UNG", "UNL", "BOIL", "KOLD", "FCG",
    "AMLP", "MLPA", "MLPX", "AMJ", "MLPB",

    # ─────────── COMMODITIES & MINING ───────────
    "DBC", "GSG", "DJP", "PDBC", "COMT", "FTGC",
    "COPX", "CPER", "JJC", "JJM", "JJN", "JJP",
    "PICK", "REMX", "LIT", "BATT", "SLX", "WIRE",
    "DBA", "WEAT", "CORN", "SOYB", "CANE", "JO", "NIB", "SGG",
    "KRBN", "GRN", "KSET",  # carbon

    # ─────────── CRYPTO / DIGITAL ───────────
    "BITO", "BITI", "BTF", "BTCO", "EZBC", "FBTC", "IBIT", "ARKB", "HODL", "BRRR", "DEFI",
    "ETHE", "ETHA", "ETH", "ETHV", "ETHW", "GBTC",
    "BITQ", "DAPP", "BLOK", "BITW", "SATO", "BKCH",

    # ─────────── BANKING & FINANCIALS ───────────
    "KBE", "KRE", "KBWB", "KBWP", "KBWR", "DPST", "FAS", "FAZ",
    "XLF", "VFH", "FNCL", "IYF", "IYG", "FXO", "RYF",

    # ─────────── HEALTHCARE / BIOTECH / PHARMA ───────────
    "XLV", "VHT", "IYH", "FHLC", "RYH",
    "XBI", "IBB", "LABU", "LABD", "SBIO", "BBC", "BBP", "PBE", "GNOM", "ARKG",
    "IHI", "IHE", "IHF", "PILL", "CURE", "CNCR", "RXL",

    # ─────────── CLEAN ENERGY / EV / RENEWABLE ───────────
    "ICLN", "QCLN", "PBW", "SMOG", "TAN", "KWT", "FAN", "GRID", "ACES", "RNRG",
    "DRIV", "KARS", "IDRV", "HAIL", "MOTO",
    "HDRO", "HYDR", "LIT", "BATT", "REMX",
    "URA", "URNM", "NLR",  # already in nuclear but fits clean-energy

    # ─────────── REAL ESTATE / REITs ───────────
    "VNQ", "VNQI", "IYR", "XLRE", "SCHH", "RWR", "USRT", "FREL", "REM", "REZ", "MORT", "ROOF", "PSR",
    "INDS",  # industrial REIT

    # ─────────── FIXED INCOME / BONDS ───────────
    "AGG", "BND", "SCHZ", "IUSB", "FBND",
    "TLT", "TBT", "TMV", "TMF", "EDV", "ZROZ",
    "IEF", "VGIT", "VGLT", "VGSH", "GOVT", "SCHQ", "SCHO",
    "SHY", "BIL", "SHV", "SGOV",
    "TIP", "VTIP", "STIP", "SCHP", "TIPX", "TDTT",
    "MBB", "MUB", "VTEB", "TFI",
    "HYG", "JNK", "SHYG", "USHY", "HYS",
    "LQD", "VCSH", "VCIT", "VCLT", "VCRB",
    "BNDX", "IGOV", "BWX", "EMB", "EMLC", "VWOB", "PCY",
    "FLOT", "BKLN", "SRLN",  # floating rate
    "PFF", "PFFD", "PGX",  # preferred

    # ─────────── ASIA-PACIFIC ───────────
    "FXI", "MCHI", "ASHR", "ASHS", "KBA", "CXSE", "KWEB", "CWEB", "YINN", "YANG",
    "CQQQ", "KURE", "CHIE", "CHII", "CHIQ", "CHIK", "CHIM",
    "EWY", "EWT", "EWJ", "DXJ", "HEWJ", "JPXN", "DBJP",
    "EWA", "EWS", "EWM", "VNM", "EIDO", "THD", "EPHE", "ENZL",

    # ─────────── EMERGING MARKETS (broad + single-country) ───────────
    "EEM", "VWO", "IEMG", "SCHE", "SPEM", "EMQQ", "DEM", "EWX", "EDC", "EDZ",
    "FRN", "FM",  # frontier
    "EWZ", "FLBR", "BRZU",  # Brazil
    "EWW", "MEXX",  # Mexico
    "EZA",  # South Africa
    "TUR",  # Turkey
    "GREK",  # Greece
    "RSXJ",  # Russia smallcap
    "ARGT",  # Argentina
    "EGPT",  # Egypt
    "QAT", "UAE",  # GCC
    "KSA",  # Saudi
    "FLKR",  # Korea
    "FLCH",  # China
    "INDA", "EPI", "INDY",  # India (folded under EM, not a separate sector)

    # ─────────── EUROPE ───────────
    "VGK", "IEUR", "FEZ", "HEDJ", "EZU", "FLEE",
    "EWG", "DAX", "HEWG",
    "EWU", "FLGB",
    "EWQ", "EWI", "EWP", "EWN", "EWO", "EWD", "EWL", "EWK",
    "EWQ",

    # ─────────── THEMATIC ───────────
    "JETS", "XRT", "ITB", "XHB", "PEJ", "BJK",
    "MJ", "MSOS", "YOLO",  # cannabis
    "ESPO", "HERO", "GAMR",  # gaming
    "PAVE", "IFRA", "GII",  # infrastructure
    "MOO",  # agribusiness
    "SLX",  # steel
    "FIVG",  # 5G
    "GENY", "MILN",  # millennial themes
    "HLAL", "SPUS",  # halal
    "IPAY",  # payments

    # ─────────── DIVIDEND / INCOME ───────────
    "SCHD", "VYM", "VIG", "DGRO", "DGRW", "NOBL", "SDY", "DVY", "HDV", "REGL",
    "JEPI", "JEPQ", "DIVO", "QYLD", "RYLD", "XYLD",  # covered call

    # ─────────── VOLATILITY ───────────
    "VIXY", "UVXY", "SVXY", "VXX", "VIXM",

    # ─────────── INVERSE / SHORT ───────────
    "SH", "SDS", "SPXU", "PSQ", "QID", "RWM", "SBB",

    # ─────────── LEVERAGED LONG (selected liquid) ───────────
    "TQQQ", "QLD", "UPRO", "SSO", "TNA", "URTY", "DDM",
]
# Dedupe while preserving first-occurrence order
ETF_UNIVERSE = list(dict.fromkeys(ETF_UNIVERSE))


MACRO_TICKERS = ["DX-Y.NYB", "^TNX", "^FVX", "^VIX", "GC=F", "SI=F", "HG=F", "CL=F", "BTC-USD"]
