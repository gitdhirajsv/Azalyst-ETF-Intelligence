"""
get_mistral_recommendations.py — Get LLM Recommendations for Your Portfolio

This script analyzes your current portfolio and shows what Mistral 7B recommends.

Requirements:
1. NVIDIA API key in .env file
2. Existing portfolio data (azalyst_portfolio.json)

Usage:
    python get_mistral_recommendations.py
"""

import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("RECOMMENDATIONS")


def load_portfolio():
    """Load current portfolio data."""
    try:
        with open("azalyst_portfolio.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.error("Portfolio file not found. Run azalyst.py first.")
        return None
    except Exception as e:
        log.error(f"Error loading portfolio: {e}")
        return None


def analyze_portfolio_manually(portfolio):
    """
    Analyze portfolio without LLM to show what insights we can extract.
    This demonstrates what the LLM would analyze.
    """
    print("\n" + "=" * 70)
    print("PORTFOLIO ANALYSIS (Pre-LLM Insights)")
    print("=" * 70)
    
    # Basic metrics
    cash = portfolio.get("cash_inr", 0)
    total_deposited = portfolio.get("total_deposited", 0)
    
    positions = portfolio.get("open_positions", [])
    closed_trades = portfolio.get("closed_trades", [])
    
    # Calculate portfolio value
    positions_value = sum(
        pos.get("current_price", 0) * pos.get("units", 0)
        for pos in positions
    )
    portfolio_value = cash + positions_value
    total_return = portfolio_value - total_deposited
    total_return_pct = (total_return / total_deposited * 100) if total_deposited > 0 else 0
    
    print(f"\n📊 PORTFOLIO SUMMARY")
    print(f"   Total Deposited:    ₹{total_deposited:,.0f}")
    print(f"   Current Value:      ₹{portfolio_value:,.2f}")
    print(f"   Total Return:       ₹{total_return:+,.2f} ({total_return_pct:+.2f}%)")
    print(f"   Cash Available:     ₹{cash:,.2f}")
    print(f"   Invested:           ₹{positions_value:,.2f}")
    
    # Win/Loss analysis
    wins = [t for t in closed_trades if t.get("realised_pnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("realised_pnl", 0) <= 0]
    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0
    
    print(f"\n📈 TRADING STATISTICS")
    print(f"   Total Trades:       {len(closed_trades)}")
    print(f"   Winners:            {len(wins)}")
    print(f"   Losers:             {len(losses)}")
    print(f"   Win Rate:           {win_rate:.1f}%")
    
    if wins:
        avg_win = sum(t.get("realised_pnl", 0) for t in wins) / len(wins)
        print(f"   Average Win:        ₹{avg_win:+,.2f}")
    
    if losses:
        avg_loss = sum(t.get("realised_pnl", 0) for t in losses) / len(losses)
        print(f"   Average Loss:       ₹{avg_loss:+,.2f}")
    
    # Open positions analysis
    print(f"\n📋 OPEN POSITIONS ({len(positions)})")
    for pos in positions:
        pnl_pct = ((pos.get("current_price", 0) - pos.get("entry_price", 0)) / pos.get("entry_price", 1)) * 100
        days_held = (datetime.now() - datetime.fromisoformat(pos.get("entry_date", '').replace('+00:00', ''))).days if pos.get('entry_date') else 0
        print(f"   • {pos.get('ticker'):6} | {pnl_pct:+6.1f}% | Conf: {pos.get('confidence'):3}/100 | Days: {days_held:3} | {pos.get('sector', 'N/A')[:30]}")
    
    # Sector exposure
    sector_exposure = {}
    for pos in positions:
        sector = pos.get('sector', 'Unknown')
        value = pos.get('current_price', 0) * pos.get('units', 0)
        sector_exposure[sector] = sector_exposure.get(sector, 0) + value
    
    print(f"\n🎯 SECTOR EXPOSURE")
    for sector, value in sorted(sector_exposure.items(), key=lambda x: -x[1]):
        pct = (value / positions_value * 100) if positions_value > 0 else 0
        print(f"   • {sector:35} {pct:5.1f}% (₹{value:,.0f})")
    
    # Generate manual recommendations based on rules
    print(f"\n💡 RULE-BASED RECOMMENDATIONS")
    recommendations = []
    
    # Win rate check
    if win_rate < 50 and closed_trades:
        recommendations.append({
            "priority": "HIGH",
            "issue": f"Win rate ({win_rate:.1f}%) is below 50% target",
            "recommendation": "Consider raising confidence threshold from 62 to 70-75 to filter lower-quality signals",
            "expected_impact": "Could improve win rate by 10-15%"
        })
    
    # Position sizing check
    if positions:
        avg_position = positions_value / len(positions)
        if avg_position > total_deposited * 0.25:
            recommendations.append({
                "priority": "MEDIUM",
                "issue": f"Average position size (₹{avg_position:,.0f}) may be too large",
                "recommendation": "Reduce position sizing to 15-20% per trade for better diversification",
                "expected_impact": "Reduce portfolio volatility and drawdown risk"
            })
    
    # Sector concentration check
    if sector_exposure:
        max_sector_pct = max(sector_exposure.values()) / positions_value * 100 if positions_value > 0 else 0
        if max_sector_pct > 40:
            max_sector = max(sector_exposure.items(), key=lambda x: x[1])[0]
            recommendations.append({
                "priority": "MEDIUM",
                "issue": f"High concentration in {max_sector} ({max_sector_pct:.1f}%)",
                "recommendation": "Diversify across more sectors to reduce single-sector risk",
                "expected_impact": "Lower correlation and portfolio volatility"
            })
    
    # Cash utilization check
    cash_ratio = cash / portfolio_value * 100 if portfolio_value > 0 else 0
    if cash_ratio > 30:
        recommendations.append({
            "priority": "LOW",
            "issue": f"High cash allocation ({cash_ratio:.1f}%)",
            "recommendation": "Consider deploying idle cash into high-conviction signals (75+ confidence)",
            "expected_impact": "Improved capital efficiency and returns"
        })
    elif cash_ratio < 10:
        recommendations.append({
            "priority": "MEDIUM",
            "issue": f"Low cash buffer ({cash_ratio:.1f}%)",
            "recommendation": "Maintain at least 10-15% cash for new opportunities and risk management",
            "expected_impact": "Better ability to capitalize on new signals without forced exits"
        })
    
    # Stop-loss analysis
    if losses:
        stop_loss_trades = [t for t in losses if 'stop-loss' in t.get('exit_reason', '').lower()]
        if len(stop_loss_trades) > len(losses) * 0.5:
            recommendations.append({
                "priority": "HIGH",
                "issue": f"High proportion of stop-loss exits ({len(stop_loss_trades)}/{len(losses)})",
                "recommendation": "Review entry criteria - may be entering too late or at wrong confidence levels",
                "expected_impact": "Fewer stop-loss hits and better risk-adjusted returns"
            })
    
    # Drawdown check
    max_drawdown = portfolio.get("max_drawdown_pct", 0)
    if max_drawdown > 8:
        recommendations.append({
            "priority": "HIGH",
            "issue": f"Maximum drawdown ({max_drawdown:.1f}%) approaching 12% limit",
            "recommendation": "Reduce position sizing by 25% until drawdown improves",
            "expected_impact": "Better risk control and capital preservation"
        })
    
    # Display recommendations
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"\n   [{rec['priority']}] Recommendation #{i}:")
            print(f"   Issue: {rec['issue']}")
            print(f"   → {rec['recommendation']}")
            print(f"   Expected Impact: {rec['expected_impact']}")
    else:
        print("   ✓ No major issues detected based on rule-based analysis")
    
    print("\n" + "=" * 70)
    print("TO GET LLM-POWERED RECOMMENDATIONS:")
    print("=" * 70)
    print("""
1. Get your FREE NVIDIA API key:
   → Visit: https://build.nvidia.com/explore/discover
   → Sign in (Google/GitHub account)
   → Click "Get API Key"

2. Add to your .env file:
   → NVIDIA_API_KEY=nvapi-your_key_here

3. Run this script again:
   → python get_mistral_recommendations.py

4. Or run the full system:
   → python azalyst.py --llm-analysis

The LLM will provide:
  ✓ 3-5 specific portfolio improvement suggestions
  ✓ Macro regime analysis and sector rotation guidance
  ✓ Signal evaluation with allocation recommendations
  ✓ Trade documentation and rationale generation
  ✓ Continuous learning from your trade outcomes
    """)
    
    return recommendations


def main():
    print("\n" + "=" * 70)
    print("  AZALYST PORTFOLIO ANALYZER")
    print("  Powered by NVIDIA NIM (Mistral 7B)")
    print("=" * 70)
    
    # Load portfolio
    portfolio = load_portfolio()
    if not portfolio:
        return 1
    
    # Check if API key is configured
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("NVIDIA_API_KEY", "")
    
    if not api_key:
        print("\n⚠️  NVIDIA_API_KEY not configured")
        print("\nRunning rule-based analysis (LLM features disabled)...")
        analyze_portfolio_manually(portfolio)
        return 0
    
    # If API key is available, use LLM
    print("\n✓ NVIDIA API key detected - Running LLM analysis...")
    
    try:
        from llm_analyzer import LLMAnalyzer
        from config import Config
        from llm_optimizer import fetch_macro_indicators
        
        cfg = Config()
        analyzer = LLMAnalyzer(cfg)
        
        if not analyzer.optimizer or not analyzer.optimizer.client:
            print("⚠️  LLM client initialization failed. Running rule-based analysis...")
            analyze_portfolio_manually(portfolio)
            return 0
        
        # Fetch macro indicators
        print("\n📡 Fetching macro indicators...")
        macro = fetch_macro_indicators()
        
        # Run LLM analysis
        print("🧠 Running LLM portfolio analysis (this may take 5-10 seconds)...")
        result = analyzer.run_portfolio_analysis()
        
        if "error" in result:
            print(f"❌ LLM analysis failed: {result['error']}")
            print("\nFalling back to rule-based analysis...")
            analyze_portfolio_manually(portfolio)
            return 0
        
        # Display results
        print("\n" + "=" * 70)
        print("  LLM ANALYSIS RESULTS")
        print("=" * 70)
        
        snapshot = result.get("portfolio_snapshot", {})
        print(f"\n📊 PORTFOLIO SNAPSHOT")
        print(f"   Total Value:    ₹{snapshot.get('total_value', 0):,.2f}")
        print(f"   Win Rate:       {snapshot.get('win_rate', 0):.1f}%")
        print(f"   Max Drawdown:   {snapshot.get('max_drawdown', 0):.2f}%")
        
        suggestions = result.get("suggestions", [])
        if suggestions:
            print(f"\n💡 LLM RECOMMENDATIONS ({len(suggestions)} suggestions)")
            for i, suggestion in enumerate(suggestions, 1):
                print(f"\n   #{i}: {suggestion}")
        else:
            print("\n⚠️  No suggestions generated")
        
        # Show analysis text if available
        analysis_text = result.get("analysis_text", "")
        if analysis_text and len(analysis_text) > 50:
            print("\n📝 DETAILED ANALYSIS")
            print("-" * 70)
            # Print first 1000 chars of analysis
            print(analysis_text[:1000])
            if len(analysis_text) > 1000:
                print("... (truncated)")
        
        print("\n" + "=" * 70)
        print("✅ LLM Analysis Complete!")
        print("=" * 70)
        
        return 0
        
    except ImportError as e:
        print(f"⚠️  Import error: {e}")
        print("\nRunning rule-based analysis instead...")
        analyze_portfolio_manually(portfolio)
        return 0
    
    except Exception as e:
        print(f"❌ Error during LLM analysis: {e}")
        log.exception("Detailed error:")
        print("\nRunning rule-based analysis instead...")
        analyze_portfolio_manually(portfolio)
        return 0


if __name__ == "__main__":
    exit(main())
