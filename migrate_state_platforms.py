"""
migrate_state_platforms.py — Update existing state file with correct ETF platform info

This script fixes the hardcoded platform values in the state file's etf_recommendations
by looking up the correct platform from the etf_mapper database.

Run this once to update your existing azalyst_state.json file.
"""

import json
from pathlib import Path
from etf_mapper import ETF_DATABASE

STATE_FILE = Path(__file__).parent / "azalyst_state.json"

# Build a ticker -> ETF mapping from the ETF database
TICKER_TO_ETF = {}

for sector_name, sector_data in ETF_DATABASE.items():
    for region in ["india", "global"]:
        for etf in sector_data.get(region, []):
            ticker = etf.get("ticker")
            if ticker:
                # Store the full ETF info
                TICKER_TO_ETF[ticker.upper()] = etf


def migrate_etf_recommendations(etf_recs):
    """Update ETF recommendations with correct platform info."""
    updated = False
    
    for region in ["india", "global"]:
        etf_list = etf_recs.get(region, [])
        for i, etf in enumerate(etf_list):
            ticker = etf.get("ticker", "").upper()
            if ticker in TICKER_TO_ETF:
                correct_etf = TICKER_TO_ETF[ticker]
                # Update platform if different
                if etf.get("platform") != correct_etf.get("platform"):
                    old_platform = etf.get("platform", "")
                    etf["platform"] = correct_etf.get("platform")
                    print(f"    {ticker} ({region}): '{old_platform}' -> '{etf['platform']}'")
                    updated = True
                # Update exchange if different
                if etf.get("exchange") != correct_etf.get("exchange"):
                    old_exchange = etf.get("exchange", "")
                    etf["exchange"] = correct_etf.get("exchange")
                    print(f"    {ticker} ({region}): Exchange '{old_exchange}' -> '{etf['exchange']}'")
                    updated = True
                # Update other fields if missing
                if "risk" not in etf and "risk" in correct_etf:
                    etf["risk"] = correct_etf["risk"]
                if "timeframe" not in etf and "timeframe" in correct_etf:
                    etf["timeframe"] = correct_etf["timeframe"]
                if "thesis" not in etf and "thesis" in correct_etf:
                    etf["thesis"] = correct_etf["thesis"]
    
    return updated


def migrate_state():
    """Update state file with correct platform info in ETF recommendations."""
    if not STATE_FILE.exists():
        print(f"State file not found: {STATE_FILE}")
        return

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    print("=" * 60)
    print("AZALYST STATE FILE PLATFORM MIGRATION")
    print("=" * 60)
    
    total_signals = len(state)
    print(f"\nFound {total_signals} sector signals in state")
    print("\nUpdating ETF recommendation platform information...\n")

    updated_count = 0
    for sector_key, signal in state.items():
        etf_recs = signal.get("etf_recommendations")
        if etf_recs:
            print(f"  {sector_key}:")
            if migrate_etf_recommendations(etf_recs):
                updated_count += 1
            else:
                print(f"    ✓ Already up to date")

    if updated_count > 0:
        # Save updated state
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 60)
        print(f"✓ State file updated successfully!")
        print(f"  Updated {updated_count} sector signals")
        print(f"  File: {STATE_FILE}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✓ No updates needed - all platforms are already correct")
        print("=" * 60)


if __name__ == "__main__":
    migrate_state()
