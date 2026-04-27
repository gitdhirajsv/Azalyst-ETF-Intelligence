import json
from etf_mapper import ETF_DATABASE

with open("data/etf_universe.json", "w", encoding="utf-8") as f:
    json.dump(ETF_DATABASE, f, indent=2)
print("ETF_DATABASE exported to data/etf_universe.json")
