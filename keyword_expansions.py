"""
keyword_expansions.py — AZALYST Sector Keyword Expansions

Drop-in additions for classifier.SECTOR_DEFINITIONS. Imported once at startup
and merged into the main keyword DB. Keeping these in a separate module makes
the classifier file readable and lets the LLM self-improver target additions
here without touching the main classifier.

Coverage:
  - Macro themes (Fed/ECB/BOJ/PBOC/RBI dates, ISM, NFP, CPI, PCE, GDP)
  - Asset-class jargon (yield curve, basis, repo stress, swap spreads)
  - Sector catalysts (FDA approvals, M&A, downgrades, guidance, earnings)
  - Company tickers + alias names
  - Trade policy (tariff, exemption, retaliation, subsidy)
"""

# Each entry merges into the existing SECTOR_DEFINITIONS[sector_id]["keywords"] list.
KEYWORD_EXPANSIONS = {

    "energy_oil": [
        # Companies
        ("exxon", 4), ("chevron", 4), ("conocophillips", 4), ("schlumberger", 3),
        ("halliburton", 3), ("baker hughes", 3), ("aramco", 5), ("petrobras", 4),
        ("shell", 4), ("bp ", 3), ("totalenergies", 4), ("eog resources", 3),
        # OPEC / supply mechanics
        ("opec meeting", 6), ("oil inventories", 5), ("crude inventory", 5),
        ("eia report", 4), ("rig count", 4), ("spr release", 6),
        ("strategic petroleum reserve", 6), ("global oil demand", 5),
        ("iea forecast", 4), ("driving season", 3),
        # Geopolitics
        ("houthi", 5), ("yemen attack", 6), ("tanker", 4), ("israel iran", 6),
        ("ukraine pipeline", 5), ("nord stream", 5), ("russia oil cap", 6),
        ("price cap", 4), ("gulf tension", 5),
        # Demand-side
        ("china oil demand", 5), ("india fuel demand", 4), ("aviation fuel", 3),
        ("jet fuel", 3), ("diesel demand", 3), ("heating oil", 3),
    ],

    "defense": [
        # Programs & contracts
        ("lockheed martin", 4), ("raytheon", 4), ("northrop", 4), ("general dynamics", 4),
        ("boeing defense", 4), ("bae systems", 4), ("rheinmetall", 5),
        ("leonardo", 3), ("saab", 3), ("dassault", 4), ("thales", 3),
        ("hensoldt", 3), ("kongsberg", 3), ("hanwha aerospace", 4),
        ("hindustan aeronautics", 4), ("hal share", 4), ("bel share", 3),
        # Weapons systems
        ("javelin", 4), ("stinger", 4), ("patriot system", 5), ("thaad", 5),
        ("aegis", 4), ("f-35", 5), ("f-16", 4), ("himars", 5),
        ("excalibur", 4), ("storm shadow", 4), ("iron dome", 5),
        ("tomahawk", 4), ("aukus", 5), ("nato summit", 5),
        # Conflicts / hot zones
        ("gaza", 4), ("hezbollah", 4), ("hamas", 4), ("kursk", 4),
        ("zaporizhzhia", 4), ("south china sea", 5), ("strait of taiwan", 5),
        ("dprk", 4), ("baltic incursion", 5),
        # Procurement language
        ("multi-year contract", 5), ("fms approval", 5), ("foreign military sale", 5),
        ("munitions stockpile", 5), ("artillery shell production", 5),
        ("defense supplemental", 6), ("ndaa", 5), ("nato 2 percent", 5),
    ],

    "gold_precious_metals": [
        # Macro drivers
        ("real yield", 5), ("real interest rate", 5), ("dxy", 4),
        ("dollar index", 4), ("tips yield", 4), ("breakeven inflation", 4),
        ("cpi report", 5), ("pce inflation", 5), ("core pce", 5),
        ("fomc minutes", 5), ("fed pivot", 5), ("dovish fed", 4),
        ("hawkish fed", 4), ("wage growth", 3), ("nfp", 3), ("jobs report", 3),
        # Central bank buying
        ("pboc gold", 6), ("rbi gold", 6), ("central bank buying", 5),
        ("gold reserves added", 5), ("dedollarization", 5),
        # Mining companies
        ("newmont", 4), ("barrick", 4), ("agnico", 3), ("franco-nevada", 3),
        ("wheaton", 3), ("kinross", 3), ("hindustan zinc", 3),
        # Crisis triggers
        ("treasury sell-off", 5), ("debt downgrade", 6), ("fitch downgrade", 5),
        ("moody's downgrade", 5), ("flight to quality", 5),
    ],

    "technology_ai": [
        # Mega-cap tech
        ("apple", 3), ("microsoft", 3), ("alphabet", 3), ("google", 3),
        ("meta", 3), ("amazon", 3), ("netflix", 2), ("oracle", 3),
        ("salesforce", 3), ("tesla", 3),
        # AI infra & frontier labs
        ("openai", 5), ("anthropic", 5), ("xai", 4), ("deepmind", 4),
        ("perplexity", 3), ("mistral", 3), ("hugging face", 3),
        ("foundation model", 5), ("llm", 5), ("large language model", 5),
        ("gpt", 4), ("claude", 4), ("gemini", 4), ("llama", 4),
        ("inference", 4), ("training run", 4), ("ai capex", 5),
        ("hyperscaler capex", 6), ("ai infrastructure", 5),
        # Cloud
        ("aws", 4), ("azure", 4), ("gcp", 4), ("cloud growth", 4),
        ("oracle cloud", 4), ("cloud capex", 5), ("ai cloud", 5),
        # Semis ecosystem
        ("euv lithography", 5), ("euv tool", 5), ("dram price", 5),
        ("nand price", 5), ("memory cycle", 5), ("foundry capacity", 5),
        ("chips act", 6), ("chip subsidy", 6), ("foundry buildout", 5),
        ("3nm node", 5), ("2nm node", 5), ("gate-all-around", 4),
        ("co-packaged optics", 4), ("liquid cooling", 4),
        # Trade policy
        ("entity list", 6), ("commerce department", 4), ("bis ruling", 5),
        ("export license", 5), ("section 232", 5), ("section 301", 5),
        ("china retaliation tech", 5), ("rare earth export", 4),
    ],

    "nuclear_uranium": [
        ("cameco", 5), ("kazatomprom", 5), ("constellation energy", 5),
        ("vistra energy", 4), ("oklo", 4), ("nuscale", 4), ("centrus", 4),
        ("nano nuclear", 4),
        ("haleu", 5), ("low enriched uranium", 5), ("conversion price", 5),
        ("u3o8", 5), ("spot uranium price", 6),
        ("hyperscaler nuclear ppa", 6), ("microsoft nuclear", 5),
        ("amazon nuclear", 5), ("data center nuclear", 6),
        ("doe nuclear loan", 5), ("nrc approval", 5),
        ("japan reactor restart", 5), ("germany nuclear", 4),
        ("france nuclear", 4), ("uk smr", 5),
    ],

    "cybersecurity": [
        # Vendors
        ("crowdstrike", 5), ("palo alto", 5), ("fortinet", 5), ("zscaler", 5),
        ("okta", 4), ("sentinelone", 4), ("cloudflare", 3),
        ("datadog security", 3), ("splunk", 4), ("rapid7", 3), ("qualys", 3),
        # Incidents
        ("solarwinds", 5), ("kaseya", 5), ("colonial pipeline", 6),
        ("change healthcare", 6), ("snowflake breach", 5), ("microsoft breach", 5),
        ("citrix bleed", 5), ("log4j", 5), ("solarwinds-style", 5),
        # Regulatory
        ("sec cyber rule", 5), ("nis2", 5), ("cisa directive", 5),
        ("breach disclosure", 5), ("cyber insurance", 4),
        # Threat actors
        ("apt29", 5), ("lazarus", 5), ("salt typhoon", 6), ("volt typhoon", 6),
        ("scattered spider", 5),
    ],

    "india_equity": [
        # Indices & Securities
        ("bank nifty", 5), ("nifty it", 5), ("nifty pharma", 4), ("nifty auto", 4),
        ("nifty fmcg", 4), ("nifty psu bank", 5), ("nifty metal", 4),
        # Macro
        ("rbi mpc", 5), ("rbi rate", 5), ("crr cut", 5), ("repo rate india", 5),
        ("india cpi", 5), ("india wpi", 4), ("india pmi", 4),
        ("union budget", 6), ("fiscal deficit india", 5),
        ("fii flows", 5), ("dii flows", 4), ("fpi outflow", 4),
        # Companies
        ("reliance", 4), ("tcs", 4), ("infosys", 4), ("hdfc bank", 4),
        ("icici bank", 4), ("bharti airtel", 3), ("itc share", 3), ("adani", 4),
        ("tata motors", 3), ("bajaj finance", 3), ("zomato", 3), ("paytm", 3),
        ("ipo india", 4),
        # Themes
        ("china plus one", 5), ("pli scheme", 5), ("semicon india", 5),
        ("railways capex", 4), ("defence indigenisation", 5),
    ],

    "crypto_digital": [
        ("etf flows", 5), ("spot ether etf", 6), ("solana etf", 5),
        ("blackrock crypto", 5), ("fidelity crypto", 5), ("grayscale", 4),
        ("microstrategy", 5), ("strategy", 3), ("coinbase earnings", 5),
        ("kraken", 4), ("circle ipo", 5), ("usdc", 4), ("tether", 4),
        ("stablecoin bill", 6), ("genius act", 5), ("clarity act", 5),
        ("sec lawsuit", 5), ("gensler", 4), ("new sec chair", 5),
        ("trump crypto", 5), ("bitcoin treasury", 5), ("strategic bitcoin reserve", 6),
        ("layer 2", 3), ("restaking", 3), ("eigenlayer", 3),
        ("sol", 3), ("xrp etf", 5), ("doge", 3),
    ],

    "banking_financial": [
        # Vendors and banks
        ("jpmorgan", 4), ("goldman sachs", 4), ("morgan stanley", 4),
        ("bank of america", 4), ("citigroup", 4), ("wells fargo", 4),
        ("regional banks", 5), ("svb", 6), ("first republic", 6),
        ("new york community bancorp", 5), ("nycb", 5),
        # Regulators
        ("basel iii", 4), ("basel iii endgame", 5), ("g-sib buffer", 4),
        ("liquidity coverage ratio", 4), ("lcr", 3),
        # Macro plumbing
        ("repo rate", 4), ("sofr", 4), ("bank reserves", 4),
        ("discount window", 5), ("standing repo facility", 5),
        ("fed balance sheet", 5), ("qt taper", 5), ("end of qt", 6),
        # Credit stress
        ("credit card delinquency", 5), ("auto loan delinquency", 4),
        ("commercial real estate stress", 6), ("cre exposure", 5),
        ("private credit", 5), ("blackstone private credit", 4),
        ("bdc", 4), ("apollo", 3), ("kkr", 3), ("ares", 3),
    ],

    "commodities_mining": [
        # Major miners
        ("freeport-mcmoran", 4), ("freeport mcmoran", 4), ("bhp group", 4),
        ("rio tinto", 4), ("vale", 4), ("glencore", 4), ("anglo american", 4),
        ("teck resources", 3), ("first quantum", 4), ("antofagasta", 3),
        # Demand themes
        ("ev battery demand", 5), ("grid copper", 5), ("ai data center copper", 6),
        ("electrification", 4), ("transmission lines", 4),
        # Trade controls
        ("china rare earth ban", 6), ("germanium export", 5),
        ("gallium export", 5), ("antimony ban", 5), ("graphite export", 5),
        ("indonesia nickel ban", 5), ("dr congo cobalt", 4),
        # Steel / aluminum
        ("steel tariff", 5), ("aluminum tariff", 5), ("section 232 steel", 5),
        ("china steel exports", 5), ("baosteel", 3),
    ],

    "emerging_markets": [
        ("em equity inflows", 5), ("em local debt", 5), ("em fx", 4),
        ("em debt restructuring", 5), ("brl", 3), ("mxn", 3), ("zar", 3),
        ("turkey lira", 4), ("argentina peso", 4), ("argentina dollarization", 5),
        ("milei", 4), ("lula", 3), ("amlo", 3), ("erdogan rate", 4),
        ("china stimulus package", 6), ("pboc rrr", 5), ("china rrr cut", 5),
        ("china property rescue", 6), ("evergrande", 4), ("country garden", 4),
    ],

    "healthcare_pharma": [
        # Mega caps
        ("eli lilly", 5), ("novo nordisk", 5), ("pfizer", 4), ("merck", 4),
        ("johnson and johnson", 4), ("abbvie", 4), ("amgen", 4),
        ("astrazeneca", 4), ("sanofi", 4), ("gilead", 4), ("regeneron", 4),
        ("vertex", 4), ("biogen", 3), ("moderna", 3),
        # GLP-1 theme
        ("zepbound", 5), ("wegovy", 5), ("ozempic", 5), ("mounjaro", 5),
        ("retatrutide", 5), ("orforglipron", 5),
        # Catalyst language
        ("pdufa date", 6), ("phase 3 readout", 6), ("phase 2 data", 5),
        ("mid-stage data", 4), ("topline results", 5), ("breakthrough designation", 5),
        ("fast track", 4), ("orphan drug", 4),
        # Policy
        ("medicare negotiation", 5), ("ira drug pricing", 5),
        ("most favored nation", 5), ("340b", 4), ("pbm reform", 5),
        # India pharma
        ("dr reddy", 3), ("sun pharma", 3), ("cipla", 3), ("lupin", 3),
        ("aurobindo", 3),
    ],

    "clean_energy_renewables": [
        ("first solar", 5), ("enphase", 5), ("solaredge", 4), ("plug power", 4),
        ("bloom energy", 4), ("nextera energy", 4), ("ge vernova", 5),
        ("vestas", 4), ("orsted", 4), ("siemens energy", 4),
        ("itc credit", 5), ("ptc credit", 5), ("45x credit", 5),
        ("section 45v", 5), ("hydrogen tax credit", 5),
        ("ira repeal", 6), ("trump ira rollback", 6), ("methane fee", 4),
        ("offshore wind cancel", 5), ("auction undersubscribed", 4),
        ("byd", 4), ("nio", 3), ("xpeng", 3), ("li auto", 3),
        ("ev tariff", 5), ("ev incentive", 4), ("china ev export", 5),
    ],

    "real_estate_reit": [
        ("prologis", 4), ("public storage", 4), ("digital realty", 5),
        ("equinix", 5), ("simon property", 4), ("realty income", 4),
        ("vici properties", 4), ("welltower", 4), ("avalonbay", 3),
        ("data center reit", 6), ("ai data center reit", 6),
        ("cre default", 6), ("office cre", 5), ("multifamily delinquency", 5),
        ("cmbs spread", 5), ("starwood redemption", 5),
        ("blackstone breit", 5), ("private reit redemption", 5),
        ("nahb confidence", 4), ("existing home sales", 4),
        ("pending home sales", 4), ("housing starts", 4),
    ],

    "bonds_fixed_income": [
        ("term premium", 5), ("real yields", 5), ("nominal yields", 4),
        ("convexity", 4), ("mbs spread", 4), ("mortgage spread", 4),
        ("credit spread widening", 6), ("credit spread tightening", 5),
        ("hy spread", 4), ("ig spread", 4),
        ("fed dot plot", 6), ("sep release", 5), ("dot plot", 5),
        ("powell speech", 4), ("jackson hole", 5), ("fed minutes", 4),
        ("ecb cut", 5), ("ecb hold", 4), ("boj rate hike", 6),
        ("boj jgb", 5), ("yen intervention", 5), ("ycc end", 6),
        ("rbi liquidity", 4), ("rbi rate cut", 5), ("rbi rate hike", 5),
        ("auction tail", 5), ("auction strong demand", 4),
        ("primary dealer", 3), ("indirect bidder", 3),
    ],

    "asia_pacific": [
        # Japan
        ("japan cpi", 4), ("nikkei record", 5), ("japan wage", 4),
        ("toyota", 3), ("sony", 3), ("nintendo", 3), ("softbank", 4),
        ("mitsubishi ufj", 4), ("nomura", 3),
        # Korea
        ("samsung", 4), ("sk hynix", 5), ("hyundai", 3), ("lg energy", 4),
        ("naver", 3), ("kakao", 3), ("kospi reform", 5),
        # Australia
        ("rba rate", 4), ("aud", 3), ("commonwealth bank", 3),
        # China
        ("china pmi", 5), ("china exports", 5), ("china deflation", 5),
        ("china yuan", 4), ("usd cnh", 4), ("politburo", 5),
        ("third plenum", 5), ("nppc", 4),
    ],

    "europe_equity": [
        ("dax record", 5), ("cac record", 5), ("stoxx 600", 5),
        ("ecb minutes", 5), ("lagarde", 4), ("bundesbank", 4),
        # Companies
        ("lvmh", 4), ("hermes", 3), ("kering", 3), ("nestle", 4),
        ("novartis", 4), ("roche", 4), ("siemens", 4), ("airbus", 5),
        ("safran", 4), ("schneider electric", 4), ("asml earnings", 5),
        # Macro
        ("german ifo", 4), ("zew survey", 4), ("eurozone pmi", 5),
        ("uk inflation", 4), ("gilt yield", 4), ("uk gdp", 4),
        ("french budget", 4), ("italy spread", 4), ("btp bund spread", 5),
        ("eu defense fund", 5), ("rearmament europe", 6),
    ],
}
