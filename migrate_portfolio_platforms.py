"""
migrate_portfolio_platforms.py — Update existing portfolio with correct ETF platform info

This script fixes the hardcoded "INDmoney / Vested" platform values in the portfolio file
by looking up the correct platform from the etf_mapper database.

Run this once to update your existing azalyst_portfolio.json file.
"""

import json
from pathlib import Path
from etf_mapper import ETFMapper, ETF_DATABASE

PORTFOLIO_FILE = Path(__file__).parent / "azalyst_portfolio.json"

# Build a ticker -> platform mapping from the ETF database
TICKER_TO_PLATFORM = {}

for sector_name, sector_data in ETF_DATABASE.items():
    for region in ["india", "global"]:
        for etf in sector_data.get(region, []):
            ticker = etf.get("ticker")
            platform = etf.get("platform")
            if ticker and platform:
                TICKER_TO_PLATFORM[ticker.upper()] = platform

# Also add exchange info
TICKER_TO_EXCHANGE = {}
for sector_name, sector_data in ETF_DATABASE.items():
    for region in ["india", "global"]:
        for etf in sector_data.get(region, []):
            ticker = etf.get("ticker")
            exchange = etf.get("exchange", "NYSE" if region == "global" else "NSE")
            if ticker:
                TICKER_TO_EXCHANGE[ticker.upper()] = exchange


def migrate_portfolio():
    """Update portfolio file with correct platform and exchange info."""
    if not PORTFOLIO_FILE.exists():
        print(f"Portfolio file not found: {PORTFOLIO_FILE}")
        return

    with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
        portfolio = json.load(f)

    updated = False
    positions = portfolio.get("open_positions", [])
    closed_trades = portfolio.get("closed_trades", [])

    print("=" * 60)
    print("AZALYST PORTFOLIO PLATFORM MIGRATION")
    print("=" * 60)
    print(f"\nFound {len(positions)} open positions and {len(closed_trades)} closed trades")
    print("\nUpdating platform information from ETF database...\n")

    # Update open positions
    for pos in positions:
        ticker = pos.get("ticker", "").upper()
        old_platform = pos.get("platform", "")
        old_exchange = pos.get("exchange", "")

        # Look up correct platform
        correct_platform = TICKER_TO_PLATFORM.get(ticker)
        correct_exchange = TICKER_TO_EXCHANGE.get(ticker)

        if correct_platform and old_platform != correct_platform:
            print(f"  {ticker}: '{old_platform}' -> '{correct_platform}'")
            pos["platform"] = correct_platform
            updated = True

        if correct_exchange and old_exchange != correct_exchange:
            print(f"  {ticker}: Exchange '{old_exchange}' -> '{correct_exchange}'")
            pos["exchange"] = correct_exchange
            updated = True

    # Update closed trades
    for trade in closed_trades:
        ticker = trade.get("ticker", "").upper()
        old_platform = trade.get("platform", "")
        old_exchange = trade.get("exchange", "")

        correct_platform = TICKER_TO_PLATFORM.get(ticker)
        correct_exchange = TICKER_TO_EXCHANGE.get(ticker)

        if correct_platform and old_platform != correct_platform:
            print(f"  {ticker} (closed): '{old_platform}' -> '{correct_platform}'")
            trade["platform"] = correct_platform
            updated = True

        if correct_exchange and old_exchange != correct_exchange:
            print(f"  {ticker} (closed): Exchange '{old_exchange}' -> '{correct_exchange}'")
            trade["exchange"] = correct_exchange
            updated = True

    if updated:
        # Save updated portfolio
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 60)
        print("✓ Portfolio updated successfully!")
        print(f"  File: {PORTFOLIO_FILE}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✓ No updates needed - all platforms are already correct")
        print("=" * 60)


if __name__ == "__main__":
    migrate_portfolio()
