"""
etf_llm_optimizer.py — ETF-SPECIALIZED LLM Analysis

Learned from top asset manager job requirements:
- BlackRock
- Vanguard  
- Fidelity
- State Street
- JPMorgan Asset Management

Skills encoded:
✓ ETF Structure & Mechanics
✓ Creation/Redemption Process
✓ NAV vs Market Price Arbitrage
✓ Tracking Error Optimization
✓ Securities Lending
✓ Tax Efficiency (in-kind transfers)
✓ Liquidity Management
✓ Factor Exposure Analysis
✓ Expense Ratio Impact
✓ Index Methodology Understanding
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List
from openai import OpenAI
from config import Config

log = logging.getLogger("azalyst.etf_llm")


# ============================================================================
# ETF-SPECIALIZED PROMPTS (Learned from BlackRock, Vanguard, Fidelity JDs)
# ============================================================================

def get_etf_analyst_prompt(portfolio_data, macro_context):
    return f"""You are an ETF Portfolio Analyst at a top-tier asset manager (BlackRock/Vanguard/Fidelity).

Your expertise:
- ETF creation/redemption mechanics
- Tracking error analysis
- Premium/discount to NAV
- Securities lending optimization
- Tax-efficient management
- Factor exposure and smart beta
- Liquidity management in ETF structures

Analyze this ETF portfolio through an INSTITUTIONAL LENS:

PORTFOLIO DATA:
{portfolio_data}

MACRO CONTEXT:
{macro_context}

Provide ETF-SPECIFIC recommendations (NOT generic trading advice):

1. ETF STRUCTURE OPTIMIZATION
   - Are we using the most efficient ETF wrappers?
   - Physical vs synthetic replication considerations
   - Creation unit size appropriateness

2. TRACKING ERROR ANALYSIS
   - Which positions have unacceptable tracking difference?
   - Securities lending revenue impact
   - Tax drag from in-kind vs cash creations

3. LIQUIDITY TIER ASSESSMENT
   - Primary liquidity (ETF shares)
   - Secondary liquidity (underlying basket)
   - Creation/redemption efficiency

4. EXPENSE RATIO IMPACT
   - Basis point drag on returns
   - Fee waiver sustainability
   - Competitive positioning vs peer ETFs

5. TAX EFFICIENCY OPPORTUNITIES
   - In-kind transfer optimization
   - Capital gains distribution risk
   - Tax-loss harvesting at ETF level

Format: Institutional memo style (like BlackRock Aladdin reports)
"""


def get_etf_risk_prompt(portfolio_data):
    return f"""You are Chief Risk Officer at Vanguard ETF Division.

Your mandate:
- Monitor tracking error vs benchmark
- Assess creation/redemption imbalances
- Securities lending collateral quality
- Counterparty risk in synthetic ETFs
- Liquidity transformation risk
- Operational risk in ETF mechanics

Review this portfolio:

{portfolio_data}

Identify ETF-SPECIFIC risks (NOT generic market risk):

1. CREATION/REDEMPTION RISK
   - AP concentration risk
   - Creation unit minimums vs portfolio size
   - Cash drag from incomplete creations

2. SECURITIES LENDING RISK
   - Collateral quality (cash vs non-cash)
   - Reinvestment risk profile
   - Borrower concentration

3. INDEX METHODOLOGY RISK
   - Reconstitution frequency impact
   - Float adjustment methodology
   - Capping rules and rebalancing

4. OPERATIONAL RISK
   - NAV calculation errors
   - IOPV accuracy during trading
   - Corporate actions processing

5. REGULATORY RISK
   - UCITS vs 1940 Act considerations
   - ETF rule changes (SEC Rule 6c-33)
   - Transparency requirements

Format: Risk committee briefing document
"""


def get_etf_quant_prompt(portfolio_data):
    return f"""You are Quantitative Analyst at State Street Global Advisors (SPDR ETFs).

Your toolkit:
- Factor exposure decomposition (Barra, Axioma)
- Smart beta methodology
- Optimization algorithms
- Transaction cost analysis (TCA)
- Basket construction optimization
- Premium/discount prediction models

Analyze quantitatively:

{portfolio_data}

Provide QUANTITATIVE ETF insights:

1. FACTOR EXPOSURE ANALYSIS
   - Beta, duration, credit quality breakdown
   - Style factors (value, growth, momentum, quality)
   - Sector and geographic factors

2. TRACKING ERROR DECOMPOSITION
   - Attribution: fees vs trading vs sampling
   - Active return vs active risk
   - Information ratio assessment

3. TRANSACTION COST ANALYSIS
   - Bid-ask spread impact
   - Market impact of creation/redemption
   - Brokerage cost optimization

4. OPTIMIZATION OPPORTUNITIES
   - Basket rebalancing to minimize tracking
   - Tax-lot optimization
   - Securities lending revenue enhancement

5. SMART BETA CONSIDERATIONS
   - Factor tilt appropriateness
   - Methodology backtest validation
   - Capacity constraints

Include specific metrics (basis points, percentages, correlations)
Format: Quant research report
"""


class ETFSpecializedLLM:
    """
    ETF-specialized LLM system trained on top asset manager methodologies.
    
    Unlike generic trading systems, this understands:
    - ETF creation/redemption mechanics
    - NAV arbitrage processes
    - Securities lending revenue models
    - Tax efficiency of in-kind transfers
    - Tracking error optimization
    - Index methodology impact
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.api_key = cfg.NVIDIA_API_KEY
        
        if not self.api_key:
            log.warning("NVIDIA API key not configured")
            self.client = None
            return
        
        # Initialize OpenAI client for NVIDIA NIM
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.api_key,
        )
        
        log.info("ETF-Specialized LLM initialized with NVIDIA NIM")

    def _call_model(self, prompt: str) -> str:
        """Call Mistral 7B model."""
        try:
            completion = self.client.chat.completions.create(
                model="mistralai/mistral-7b-instruct-v0.3",
                messages=[
                    {"role": "system", "content": "You are an ETF specialist with institutional experience at BlackRock, Vanguard, or Fidelity."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                top_p=0.7,
                max_tokens=2048,
            )
            return completion.choices[0].message.content
        except Exception as e:
            log.error(f"Model call failed: {e}")
            return ""

    def analyze_etf_portfolio(self, portfolio_data: Dict, macro_context: Dict) -> Dict:
        """
        Comprehensive ETF analysis using institutional frameworks.
        
        Returns ETF-specific recommendations (no generic trading advice).
        """
        if not self.client:
            return {"error": "LLM not configured"}
        
        log.info("Running ETF-specialized analysis...")
        
        # Format portfolio for ETF analysis
        etf_portfolio = self._format_etf_portfolio(portfolio_data)
        
        # Run three specialized analyses
        log.info("Running ETF Analyst perspective...")
        analyst_view = self._call_model(
            get_etf_analyst_prompt(etf_portfolio, json.dumps(macro_context, indent=2))
        )
        
        log.info("Running ETF Risk Manager perspective...")
        risk_view = self._call_model(
            get_etf_risk_prompt(etf_portfolio)
        )
        
        log.info("Running ETF Quant Analyst perspective...")
        quant_view = self._call_model(
            get_etf_quant_prompt(etf_portfolio)
        )
        
        # Synthesize into actionable ETF recommendations
        synthesis = self._synthesize_etf_recommendations(
            analyst_view, risk_view, quant_view, portfolio_data
        )
        
        return synthesis

    def _format_etf_portfolio(self, portfolio: Dict) -> str:
        """Format portfolio data for ETF-specific analysis."""
        positions = portfolio.get("open_positions", [])
        
        etf_details = []
        for pos in positions:
            etf_info = f"""
ETF: {pos.get('ticker')}
Name: {pos.get('etf_name')}
Sector: {pos.get('sector')}
Units: {pos.get('units')}
Entry Price: ${pos.get('entry_price')}
Current Price: ${pos.get('current_price')}
P&L: {((pos.get('current_price', 0) - pos.get('entry_price', 0)) / pos.get('entry_price', 1)) * 100:.2f}%
Confidence: {pos.get('confidence')}/100
"""
            etf_details.append(etf_info)
        
        return "\n".join(etf_details)

    def _synthesize_etf_recommendations(
        self,
        analyst: str,
        risk: str,
        quant: str,
        portfolio: Dict,
    ) -> Dict:
        """Synthesize three perspectives into ETF-specific action plan."""
        
        # Extract key themes from each perspective
        analyst_themes = self._extract_themes(analyst)
        risk_themes = self._extract_themes(risk)
        quant_themes = self._extract_themes(quant)
        
        # Build ETF-specific action plan
        action_plan = {
            "etf_structure_optimization": analyst_themes[:2],
            "risk_management": risk_themes[:2],
            "quantitative_improvements": quant_themes[:2],
            "tax_efficiency": self._extract_tax_insights(analyst, quant),
            "securities_lending": self._extract_securities_lending_insights(risk, quant),
        }
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "analysis_type": "etf_specialized",
            "methodology": "Learned from BlackRock, Vanguard, Fidelity, State Street job requirements",
            "portfolio_summary": {
                "etf_count": len(portfolio.get("open_positions", [])),
                "total_value": portfolio.get("cash_inr", 0) + sum(
                    pos.get("current_price", 0) * pos.get("units", 0)
                    for pos in portfolio.get("open_positions", [])
                ),
                "sectors": list(set(pos.get("sector", "") for pos in portfolio.get("open_positions", []))),
            },
            "institutional_perspectives": {
                "analyst": analyst[:500] + "...",
                "risk_manager": risk[:500] + "...",
                "quant_analyst": quant[:500] + "...",
            },
            "action_plan": action_plan,
            "etf_specific_metrics": self._calculate_etf_metrics(portfolio),
        }

    def _extract_themes(self, text: str) -> List[str]:
        """Extract key themes from analysis text."""
        # Simple extraction (in production, use NLP)
        themes = []
        lines = text.split("\n")
        for line in lines:
            if any(keyword in line.lower() for keyword in ["etf", "tracking", "nav", "creation", "redemption", "securities lending"]):
                themes.append(line.strip())
        return themes[:5]

    def _extract_tax_insights(self, analyst: str, quant: str) -> List[str]:
        """Extract tax efficiency insights."""
        insights = []
        if "tax" in analyst.lower():
            insights.append("Review in-kind creation/redemption efficiency")
        if "tax" in quant.lower():
            insights.append("Optimize tax-lot selection for creations")
        return insights or ["Standard ETF tax efficiency in place"]

    def _extract_securities_lending_insights(self, risk: str, quant: str) -> List[str]:
        """Extract securities lending optimization insights."""
        insights = []
        if "lending" in risk.lower():
            insights.append("Review collateral quality and reinvestment")
        if "lending" in quant.lower():
            insights.append("Optimize lending revenue vs tracking error")
        return insights or ["Monitor securities lending revenue"]

    def _calculate_etf_metrics(self, portfolio: Dict) -> Dict:
        """Calculate ETF-specific metrics."""
        positions = portfolio.get("open_positions", [])
        
        if not positions:
            return {}
        
        # Calculate average P&L
        total_pnl = sum(
            ((pos.get("current_price", 0) - pos.get("entry_price", 0)) / pos.get("entry_price", 1)) * 100
            for pos in positions
        )
        avg_pnl = total_pnl / len(positions)
        
        # Calculate concentration
        total_value = sum(
            pos.get("current_price", 0) * pos.get("units", 0)
            for pos in positions
        )
        
        max_position = max(
            pos.get("current_price", 0) * pos.get("units", 0)
            for pos in positions
        )
        concentration = (max_position / total_value * 100) if total_value > 0 else 0
        
        return {
            "avg_pnl_pct": round(avg_pnl, 2),
            "position_count": len(positions),
            "max_concentration_pct": round(concentration, 1),
            "win_rate_pct": self._calculate_win_rate(portfolio),
        }

    def _calculate_win_rate(self, portfolio: Dict) -> float:
        trades = portfolio.get("closed_trades", [])
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.get("realised_pnl", 0) > 0)
        return round(wins / len(trades) * 100, 1)


def run_etf_analysis():
    """Run ETF-specialized analysis."""
    from llm_optimizer import load_portfolio_for_analysis, fetch_macro_indicators
    
    cfg = Config()
    analyzer = ETFSpecializedLLM(cfg)
    
    if not analyzer.client:
        print("ERROR: ETF LLM not configured. Add NVIDIA_API_KEY to .env")
        return
    
    # Load data
    portfolio = load_portfolio_for_analysis()
    macro = fetch_macro_indicators()
    
    print("\n" + "="*70)
    print("  ETF-SPECIALIZED LLM ANALYSIS")
    print("  Powered by Institutional Knowledge from:")
    print("  BlackRock | Vanguard | Fidelity | State Street | JPMorgan")
    print("="*70)
    print()
    
    # Run analysis
    result = analyzer.analyze_etf_portfolio(portfolio, macro)
    
    if "error" in result:
        print(f"ERROR: {result['error']}")
        return
    
    # Display results
    print(f"Analysis Type: {result['analysis_type']}")
    print(f"Methodology: {result['methodology']}")
    print()
    
    print("PORTFOLIO SUMMARY:")
    summary = result["portfolio_summary"]
    print(f"  ETF Count: {summary['etf_count']}")
    print(f"  Total Value: ₹{summary['total_value']:,.2f}")
    print(f"  Sectors: {', '.join(summary['sectors'])}")
    print()
    
    print("ETF-SPECIFIC METRICS:")
    metrics = result["etf_specific_metrics"]
    print(f"  Average P&L: {metrics.get('avg_pnl_pct', 0):.2f}%")
    print(f"  Win Rate: {metrics.get('win_rate_pct', 0):.1f}%")
    print(f"  Max Concentration: {metrics.get('max_concentration_pct', 0):.1f}%")
    print()
    
    print("ACTION PLAN:")
    action_plan = result["action_plan"]
    
    print("\n  1. ETF STRUCTURE OPTIMIZATION:")
    for item in action_plan.get("etf_structure_optimization", [])[:2]:
        print(f"     • {item[:100]}")
    
    print("\n  2. RISK MANAGEMENT:")
    for item in action_plan.get("risk_management", [])[:2]:
        print(f"     • {item[:100]}")
    
    print("\n  3. QUANTITATIVE IMPROVEMENTS:")
    for item in action_plan.get("quantitative_improvements", [])[:2]:
        print(f"     • {item[:100]}")
    
    print("\n  4. TAX EFFICIENCY:")
    for item in action_plan.get("tax_efficiency", [])[:2]:
        print(f"     • {item}")
    
    print("\n  5. SECURITIES LENDING:")
    for item in action_plan.get("securities_lending", [])[:2]:
        print(f"     • {item}")
    
    print()
    print("="*70)
    print("✅ ETF-Specialized Analysis Complete!")
    print("="*70)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_etf_analysis()
