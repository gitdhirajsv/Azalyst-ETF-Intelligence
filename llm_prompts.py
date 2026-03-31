"""
llm_prompts.py — AZALYST LLM Prompt Templates

Standardized prompt templates for:
  - Backtest analysis
  - Macroeconomic interpretation
  - Strategy optimization
  - Risk management recommendations
  - Trade documentation
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


class PromptTemplates:
    """Collection of prompt templates for LLM-powered analysis."""

    # ── System Prompts ───────────────────────────────────────────────────────

    SYSTEM_ANALYST = """You are an expert quantitative analyst specializing in ETF strategy optimization and risk management.
Your role is to:
1. Analyze portfolio performance data objectively
2. Identify patterns in winning and losing trades
3. Suggest specific, actionable improvements to strategy parameters
4. Recommend risk management adjustments based on market conditions
5. Provide clear rationale for all recommendations

Be concise, data-driven, and avoid generic advice. Focus on measurable improvements."""

    SYSTEM_MACRO_STRATEGIST = """You are a macro strategist advising a fund manager on asset allocation.
Your role is to:
1. Interpret economic indicators and identify the current economic regime
2. Recommend sector rotation strategies based on macro conditions
3. Identify risks and opportunities across asset classes
4. Suggest hedging strategies when appropriate

Be decisive and specific. Use historical precedents when relevant."""

    SYSTEM_RISK_MANAGER = """You are a risk manager for a quantitative ETF fund.
Your role is to:
1. Validate proposed strategy changes against risk constraints
2. Identify potential unintended consequences
3. Assess whether changes should be auto-applied, flagged for review, or rejected
4. Ensure compliance with position limits, sector caps, and drawdown guardrails

Be conservative. When in doubt, flag for human review."""

    SYSTEM_DOCUMENTATION = """You are documenting trades and strategy decisions for compliance and performance review.
Your role is to:
1. Write clear, objective trade rationales
2. Document the decision-making process
3. Link trades to specific signals and confidence levels
4. Record outcomes and lessons learned

Be factual and concise. Avoid hindsight bias."""

    # ── Backtest Analysis Prompts ────────────────────────────────────────────

    BACKTEST_ANALYSIS_PROMPT = """PORTFOLIO PERFORMANCE ANALYSIS REQUEST

=== PERFORMANCE METRICS ===
Total Capital Deposited: ₹{total_deposited:,.0f}
Current Portfolio Value: ₹{portfolio_value:,.2f}
Total Return: ₹{total_return:+,.2f} ({total_return_pct:+.2f}%)
Cash Available: ₹{cash:,.2f}

=== TRADING STATISTICS ===
Total Closed Trades: {total_trades}
Win Rate: {win_rate:.1f}% ({win_count}W / {loss_count}L)
Average Win: ₹{avg_win:+,.2f}
Average Loss: ₹{avg_loss:+,.2f}
Profit Factor: {profit_factor:.2f}
Max Drawdown: {max_drawdown:.2f}%

=== OPEN POSITIONS ===
{open_positions_text}

=== RECENT CLOSED TRADES ===
{closed_trades_text}

=== MACROECONOMIC CONTEXT ===
{macro_context}

=== ANALYSIS REQUEST ===
Based on the data above, provide:

1. **Performance Diagnosis** (2-3 sentences)
   - What is working well?
   - What are the main areas of underperformance?

2. **Parameter Adjustment Recommendations** (2-3 specific suggestions)
   - Position sizing adjustments
   - Stop-loss or take-profit modifications
   - Sector cap changes

3. **Risk Management Improvements** (1-2 suggestions)
   - New risk controls or guardrails
   - Hedging recommendations

4. **Strategy Enhancements** (1-2 ideas)
   - New indicators or filters to add
   - Market regime detection improvements

Be specific and actionable. Prioritize recommendations by expected impact."""

    # ── Signal Analysis Prompts ──────────────────────────────────────────────

    SIGNAL_ANALYSIS_PROMPT = """SIGNAL EVALUATION REQUEST

=== SIGNAL DETAILS ===
Sector: {sector}
Confidence Score: {confidence}/100
Severity: {severity}
Article Count: {article_count}
Sources: {sources}

=== CONFIDENCE BREAKDOWN ===
{confidence_breakdown}

=== CURRENT PORTFOLIO CONTEXT ===
Open Positions: {open_positions_count}
Cash Available: ₹{cash:,.2f}
Sector Exposure: {sector_exposure}

=== MARKET REGIME ===
{market_regime}

=== DECISION REQUEST ===
Provide a clear allocation recommendation:

1. **Action**: Enter / Add / Wait / Skip
2. **Confidence in Recommendation**: High / Medium / Low
3. **Suggested Allocation**: 0-40% of available capital
4. **Risk Parameters**:
   - Stop-loss: __%
   - Take-profit: __%
   - Max hold period: __ days

5. **Rationale** (2-3 sentences explaining the decision)

Format response as JSON with keys:
{{
  "action": "enter|add|wait|skip",
  "confidence": "high|medium|low",
  "allocation_pct": 0-40,
  "stop_loss_pct": number,
  "take_profit_pct": number,
  "max_hold_days": number,
  "rationale": "string"
}}"""

    # ── Macro Interpretation Prompts ─────────────────────────────────────────

    MACRO_INTERPRETATION_PROMPT = """MACROECONOMIC INDICATOR INTERPRETATION

=== CURRENT INDICATORS ===
{indicators_text}

=== ANALYSIS REQUEST ===
Provide a comprehensive macro assessment:

1. **Economic Regime Identification**
   - Current phase: Expansion / Slowdown / Recession / Recovery
   - Inflation regime: Rising / Peak / Declining
   - Growth outlook: Accelerating / Stable / Decelerating

2. **Sector Rotation Implications**
   - Sectors to OVERWEIGHT (2-3)
   - Sectors to UNDERWEIGHT (2-3)
   - Sectors to AVOID (1-2)

3. **Risk Management Adjustments**
   - Overall exposure: Increase / Maintain / Reduce
   - Hedging needs: Yes/No (specify instruments if yes)
   - Key risk indicators to monitor

4. **Tactical Recommendations** (next 1-3 months)
   - Specific ETF opportunities
   - Suggested position sizing adjustments
   - Time horizon considerations

Be specific and reference historical precedents where applicable."""

    # ── Risk Validation Prompts ──────────────────────────────────────────────

    RISK_VALIDATION_PROMPT = """STRATEGY CHANGE RISK VALIDATION

=== PROPOSED CHANGE ===
{proposed_change}

=== CURRENT PARAMETERS ===
{current_params}

=== RISK CONSTRAINTS ===
- Maximum single position: 40%
- Maximum sector exposure: 30%
- Maximum portfolio drawdown: 12%
- Maximum positions: 8
- Minimum cash buffer: 5%
- Stop-loss requirement: 10%

=== VALIDATION REQUEST ===
Evaluate the proposed change:

1. **Constraint Compliance**: Does this violate any risk constraints listed above?
2. **Risk Assessment**: Low / Medium / High risk change
3. **Unintended Consequences**: What could go wrong?
4. **Recommendation**: Auto-apply / Flag for review / Reject
5. **Rationale**: Brief explanation

Respond in JSON format:
{{
  "valid": boolean,
  "risk_level": "low|medium|high",
  "action": "apply|review|reject",
  "warnings": ["list of concerns"],
  "rationale": "string"
}}"""

    # ── Trade Documentation Prompts ──────────────────────────────────────────

    TRADE_RATIONALE_PROMPT = """TRADE DOCUMENTATION REQUEST

=== ENTRY DETAILS ===
Ticker: {ticker}
Sector: {sector}
Entry Price: ₹{entry_price:.2f}
Units: {units}
Investment: ₹{invested:.2f}
Entry Date: {entry_date}
Signal Confidence: {confidence}/100
Signal Severity: {severity}
Trigger Headline: {headline}

=== EXIT DETAILS ===
{exit_details}

=== DOCUMENTATION REQUEST ===
Write a concise trade rationale (3-5 sentences) covering:

1. **Investment Thesis**: Why was this trade entered?
2. **Signal Context**: What macro development triggered the entry?
3. **Outcome** (if exited): What was the result and key lesson?

Be objective and avoid hindsight bias. Focus on the decision-making process at the time of entry."""

    # ── Strategy Optimization Prompts ────────────────────────────────────────

    STRATEGY_OPTIMIZATION_PROMPT = """STRATEGY OPTIMIZATION ANALYSIS

=== CURRENT STRATEGY PARAMETERS ===
{strategy_params}

=== PERFORMANCE ATTRIBUTION ===
{performance_attribution}

=== MARKET ENVIRONMENT ===
{market_environment}

=== OPTIMIZATION REQUEST ===
Identify specific parameter adjustments to improve risk-adjusted returns:

1. **Position Sizing**
   - Current Kelly fraction: {kelly_fraction}
   - Suggested adjustment: __
   - Rationale: __

2. **Risk Parameters**
   - Current stop-loss: {stop_loss}%
   - Current trailing stop: {trailing_stop}%
   - Suggested adjustments: __

3. **Entry Criteria**
   - Current confidence threshold: {confidence_threshold}
   - Suggested adjustments: __

4. **Exit Rules**
   - Current partial profit: {partial_profit}%
   - Current max hold: {max_hold} days
   - Suggested adjustments: __

5. **New Features**
   - Suggested indicators or filters to add
   - Market regime detection improvements

Prioritize by expected impact on Sharpe ratio and maximum drawdown."""

    # ── Helper Methods ──────────────────────────────────────────────────────

    @classmethod
    def format_backtest_prompt(
        cls,
        portfolio_data: Dict,
        macro_context: Optional[Dict] = None,
    ) -> str:
        """Format portfolio data into backtest analysis prompt."""
        # Calculate metrics
        cash = portfolio_data.get("cash_inr", 0)
        total_deposited = portfolio_data.get("total_deposited", 0)
        
        portfolio_value = cash + sum(
            pos.get("current_price", 0) * pos.get("units", 0)
            for pos in portfolio_data.get("open_positions", [])
        )
        total_return = portfolio_value - total_deposited
        total_return_pct = (total_return / total_deposited * 100) if total_deposited > 0 else 0
        
        closed_trades = portfolio_data.get("closed_trades", [])
        win_count = sum(1 for t in closed_trades if t.get("realised_pnl", 0) > 0)
        loss_count = sum(1 for t in closed_trades if t.get("realised_pnl", 0) <= 0)
        win_rate = (win_count / len(closed_trades) * 100) if closed_trades else 0
        
        avg_win = sum(t.get("realised_pnl", 0) for t in closed_trades if t.get("realised_pnl", 0) > 0) / win_count if win_count > 0 else 0
        avg_loss = sum(t.get("realised_pnl", 0) for t in closed_trades if t.get("realised_pnl", 0) < 0) / loss_count if loss_count > 0 else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        # Format open positions
        open_positions_lines = []
        for pos in portfolio_data.get("open_positions", [])[:5]:
            pnl_pct = ((pos.get("current_price", 0) - pos.get("entry_price", 0)) / pos.get("entry_price", 1)) * 100
            days = pos.get("days_held", "N/A")
            open_positions_lines.append(
                f"- {pos.get('ticker')}: {pnl_pct:+.1f}% | Conf: {pos.get('confidence')}/100 | Days: {days}"
            )
        open_positions_text = "\n".join(open_positions_lines) if open_positions_lines else "No open positions"
        
        # Format closed trades
        closed_trades_lines = []
        for trade in closed_trades[-5:]:
            pnl_pct = trade.get("realised_pnl_pct", 0)
            reason = trade.get("exit_reason", "N/A")
            closed_trades_lines.append(
                f"- {trade.get('ticker')}: {pnl_pct:+.1f}% | {reason}"
            )
        closed_trades_text = "\n".join(closed_trades_lines) if closed_trades_lines else "No closed trades yet"
        
        # Format macro context
        macro_text = "No macro data provided"
        if macro_context:
            macro_lines = [f"- {k}: {v}" for k, v in macro_context.items()]
            macro_text = "\n".join(macro_lines)
        
        return cls.BACKTEST_ANALYSIS_PROMPT.format(
            total_deposited=total_deposited,
            portfolio_value=portfolio_value,
            total_return=total_return,
            total_return_pct=total_return_pct,
            cash=cash,
            total_trades=len(closed_trades),
            win_rate=win_rate,
            win_count=win_count,
            loss_count=loss_count,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=portfolio_data.get("max_drawdown_pct", 0),
            open_positions_text=open_positions_text,
            closed_trades_text=closed_trades_text,
            macro_context=macro_text,
        )

    @classmethod
    def format_signal_prompt(
        cls,
        signal: Dict,
        portfolio_context: Dict,
        market_regime: Optional[str] = None,
    ) -> str:
        """Format signal data into analysis prompt."""
        # Format confidence breakdown
        breakdown = signal.get("confidence_breakdown", {})
        breakdown_lines = []
        for key, value in breakdown.items():
            formatted_key = key.replace("_", " ").title()
            breakdown_lines.append(f"- {formatted_key}: {value}")
        breakdown_text = "\n".join(breakdown_lines) if breakdown else "Not available"
        
        # Format sector exposure
        sector = signal.get("sector_label", "Unknown")
        sector_exposure = portfolio_context.get("sector_exposure", {}).get(sector, "0%")
        
        return cls.SIGNAL_ANALYSIS_PROMPT.format(
            sector=sector,
            confidence=signal.get("confidence", 0),
            severity=signal.get("severity", "LOW"),
            article_count=signal.get("article_count", 0),
            sources=", ".join(signal.get("sources", [])[:5]),
            confidence_breakdown=breakdown_text,
            open_positions_count=portfolio_context.get("open_positions_count", 0),
            cash=portfolio_context.get("cash", 0),
            sector_exposure=sector_exposure,
            market_regime=market_regime or "Not specified",
        )

    @classmethod
    def format_macro_prompt(cls, indicators: Dict[str, Any]) -> str:
        """Format macro indicators into interpretation prompt."""
        indicators_lines = [f"- {k}: {v}" for k, v in indicators.items()]
        return cls.MACRO_INTERPRETATION_PROMPT.format(
            indicators_text="\n".join(indicators_lines)
        )

    @classmethod
    def format_risk_validation_prompt(
        cls,
        proposed_change: str,
        current_params: Dict,
    ) -> str:
        """Format risk validation prompt."""
        params_text = "\n".join(f"- {k}: {v}" for k, v in current_params.items())
        return cls.RISK_VALIDATION_PROMPT.format(
            proposed_change=proposed_change,
            current_params=params_text,
        )

    @classmethod
    def format_trade_rationale_prompt(
        cls,
        entry_data: Dict,
        exit_data: Optional[Dict] = None,
    ) -> str:
        """Format trade documentation prompt."""
        exit_details = "Trade still open"
        if exit_data:
            exit_details = f"""Exit Price: ₹{exit_data.get('exit_price', 0):.2f}
Exit Date: {exit_data.get('exit_date', 'N/A')}
P&L: {exit_data.get('realised_pnl_pct', 0):+.1f}%
Exit Reason: {exit_data.get('exit_reason', 'N/A')}"""
        
        return cls.TRADE_RATIONALE_PROMPT.format(
            ticker=entry_data.get("ticker", "N/A"),
            sector=entry_data.get("sector", "N/A"),
            entry_price=entry_data.get("entry_price", 0),
            units=entry_data.get("units", 0),
            invested=entry_data.get("invested_inr", 0),
            entry_date=entry_data.get("entry_date", "N/A"),
            confidence=entry_data.get("confidence", 0),
            severity=entry_data.get("severity", "LOW"),
            headline=entry_data.get("signal_headline", "N/A")[:100],
            exit_details=exit_details,
        )


if __name__ == "__main__":
    # Test prompt formatting
    test_portfolio = {
        "cash_inr": 5000,
        "total_deposited": 20000,
        "open_positions": [
            {
                "ticker": "XLE",
                "current_price": 100,
                "entry_price": 95,
                "units": 10,
                "confidence": 85,
                "days_held": 5,
            }
        ],
        "closed_trades": [
            {
                "ticker": "ITA",
                "realised_pnl": 500,
                "realised_pnl_pct": 5.0,
                "exit_reason": "Target hit",
            },
            {
                "ticker": "GLDM",
                "realised_pnl": -300,
                "realised_pnl_pct": -3.0,
                "exit_reason": "Stop-loss",
            },
        ],
    }
    
    prompt = PromptTemplates.format_backtest_prompt(test_portfolio)
    print("=== GENERATED PROMPT ===")
    print(prompt)
