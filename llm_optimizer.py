"""
llm_optimizer.py — AZALYST LLM Integration with NVIDIA NIM

Integrates Mistral 7B Instruct via NVIDIA NIM API for:
  - Backtest analysis and strategy optimization suggestions
  - Macroeconomic context interpretation
  - Risk management recommendations
  - Auto-generated documentation of strategy changes
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from openai import OpenAI

log = logging.getLogger("azalyst.llm")

# Default NVIDIA NIM configuration
DEFAULT_NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
DEFAULT_MODEL = "mistralai/mistral-7b-instruct-v0.3"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_P = 0.7
DEFAULT_MAX_TOKENS = 1024


class MistralETFOptimizer:
    """
    LLM-powered optimizer for ETF strategy analysis using NVIDIA NIM.
    
    Capabilities:
    - Analyze backtest results and suggest improvements
    - Interpret macroeconomic indicators for strategy adjustments
    - Generate risk management recommendations
    - Auto-document strategy change rationale
    """

    def __init__(
        self,
        api_key: str = DEFAULT_NVIDIA_API_KEY,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        """Initialize the Mistral optimizer with NVIDIA NIM client."""
        if not api_key:
            log.warning(
                "NVIDIA API key not configured. Set NVIDIA_API_KEY env var or in .env file. "
                "LLM features will be disabled."
            )
            self.client = None
            return

        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key,
        )
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        
        log.info(f"LLM Optimizer initialized with model: {model}")

    def _build_messages(self, system_prompt: str, user_prompt: str) -> List[Dict]:
        """Construct message list for chat completion."""
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call NVIDIA NIM API and return response."""
        if not self.client:
            return ""

        try:
            messages = self._build_messages(system_prompt, user_prompt)
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
            )
            
            response = completion.choices[0].message.content
            log.info(f"LLM response received ({len(response)} chars)")
            return response
            
        except Exception as e:
            log.error(f"LLM API call failed: {e}")
            return ""

    def analyze_backtest(
        self,
        portfolio_data: Dict,
        macro_context: Optional[Dict] = None,
        etf_fundamentals: Optional[Dict] = None,
    ) -> Dict:
        """
        Analyze portfolio/backtest results and generate optimization suggestions.
        
        Args:
            portfolio_data: Portfolio metrics (cash, positions, closed trades, etc.)
            macro_context: Macroeconomic indicators (CPI, rates, GDP, etc.)
            etf_fundamentals: ETF-specific data (holdings, expense ratios, etc.)
            
        Returns:
            Dict with analysis, suggestions, and code recommendations
        """
        if not self.client:
            return {"error": "LLM not configured", "suggestions": []}

        # Build structured prompt
        prompt_data = self._format_backtest_prompt(
            portfolio_data, macro_context, etf_fundamentals
        )
        
        system_prompt = """You are an expert quantitative analyst specializing in ETF strategy optimization.
Analyze the provided portfolio performance data and macroeconomic context.
Provide specific, actionable recommendations to improve risk-adjusted returns.
Focus on:
1. Identifying underperformance patterns
2. Suggesting parameter adjustments (position sizing, stop-loss, sector caps)
3. Recommending risk management improvements
4. Proposing new indicators or filters based on macro conditions

Be concise and specific. Avoid generic advice."""

        response = self._call_llm(system_prompt, prompt_data)
        
        # Parse response into structured output
        return self._parse_analysis_response(response, portfolio_data)

    def _format_backtest_prompt(
        self,
        portfolio_data: Dict,
        macro_context: Optional[Dict],
        etf_fundamentals: Optional[Dict],
    ) -> str:
        """Format portfolio and macro data into LLM prompt."""
        
        # Extract key metrics
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
        
        max_drawdown = portfolio_data.get("max_drawdown_pct", 0)
        
        # Build prompt
        prompt = f"""PORTFOLIO PERFORMANCE SUMMARY:

Total Capital Deposited: ₹{total_deposited:,.0f}
Current Portfolio Value: ₹{portfolio_value:,.2f}
Total Return: ₹{total_return:+,.2f} ({total_return_pct:+.2f}%)
Cash Available: ₹{cash:,.2f}

TRADING STATISTICS:
Total Closed Trades: {len(closed_trades)}
Win Rate: {win_rate:.1f}% ({win_count}W / {loss_count}L)
Average Win: ₹{avg_win:+,.2f}
Average Loss: ₹{avg_loss:+,.2f}
Profit Factor: {abs(avg_win / avg_loss) if avg_loss != 0 else 'N/A':.2f}
Max Drawdown: {max_drawdown:.2f}%

OPEN POSITIONS:
"""
        for pos in portfolio_data.get("open_positions", [])[:5]:
            pnl_pct = ((pos.get("current_price", 0) - pos.get("entry_price", 0)) / pos.get("entry_price", 1)) * 100
            prompt += f"- {pos.get('ticker')}: {pnl_pct:+.1f}% | Conf: {pos.get('confidence')}/100 | Days: {pos.get('days_held', 'N/A')}\n"

        if closed_trades:
            prompt += "\nRECENT CLOSED TRADES (Last 5):\n"
            for trade in closed_trades[-5:]:
                prompt += f"- {trade.get('ticker')}: {trade.get('realised_pnl_pct', 0):+.1f}% | {trade.get('exit_reason', 'N/A')}\n"

        if macro_context:
            prompt += f"\nMACROECONOMIC CONTEXT:\n"
            for key, value in macro_context.items():
                prompt += f"- {key}: {value}\n"

        if etf_fundamentals:
            prompt += f"\nETF FUNDAMENTALS:\n"
            for key, value in etf_fundamentals.items():
                prompt += f"- {key}: {value}\n"

        prompt += "\nBased on this data, provide 3-5 specific recommendations to improve portfolio performance."
        
        return prompt

    def _parse_analysis_response(
        self,
        response: str,
        portfolio_data: Dict,
    ) -> Dict:
        """Parse LLM response into structured analysis."""
        if not response:
            return {"error": "Empty response from LLM", "suggestions": []}

        # Extract structured suggestions
        suggestions = []
        lines = response.strip().split("\n")
        
        current_suggestion = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("PORTFOLIO") and not line.startswith("Based on"):
                current_suggestion.append(line)
        
        if current_suggestion:
            suggestions.append(" ".join(current_suggestion))

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "analysis_text": response,
            "suggestions": suggestions[:5],  # Top 5 suggestions
            "portfolio_snapshot": {
                "total_value": portfolio_data.get("cash_inr", 0) + sum(
                    pos.get("current_price", 0) * pos.get("units", 0)
                    for pos in portfolio_data.get("open_positions", [])
                ),
                "win_rate": self._calculate_win_rate(portfolio_data),
                "max_drawdown": portfolio_data.get("max_drawdown_pct", 0),
            },
        }

    def _calculate_win_rate(self, portfolio_data: Dict) -> float:
        """Calculate win rate from closed trades."""
        closed_trades = portfolio_data.get("closed_trades", [])
        if not closed_trades:
            return 0.0
        wins = sum(1 for t in closed_trades if t.get("realised_pnl", 0) > 0)
        return round(wins / len(closed_trades) * 100, 2)

    def suggest_strategy_adjustment(
        self,
        signal: Dict,
        current_allocation: Dict,
        market_regime: Optional[str] = None,
    ) -> Dict:
        """
        Generate strategy adjustment suggestions for a specific signal.
        
        Args:
            signal: Current signal with confidence, severity, sector info
            current_allocation: Current portfolio allocation by sector
            market_regime: Current market regime (e.g., "high_volatility", "risk_off")
            
        Returns:
            Dict with allocation suggestions and rationale
        """
        if not self.client:
            return {"error": "LLM not configured", "adjustment": None}

        prompt = f"""SIGNAL ANALYSIS REQUEST:

Signal Details:
- Sector: {signal.get('sector_label', 'Unknown')}
- Confidence: {signal.get('confidence', 0)}/100
- Severity: {signal.get('severity', 'LOW')}
- Article Count: {signal.get('article_count', 0)}

Current Portfolio Allocation:
{json.dumps(current_allocation, indent=2)}

Market Regime: {market_regime or 'Not specified'}

Provide a specific recommendation:
1. Should we enter/add to this position? (Yes/No with confidence level)
2. Suggested allocation percentage (0-40%)
3. Risk management parameters (stop-loss %, take-profit %)
4. Rationale (2-3 sentences)

Format response as JSON with keys: recommendation, allocation_pct, stop_loss_pct, take_profit_pct, rationale"""

        system_prompt = """You are a portfolio manager making allocation decisions.
Be decisive and specific. Use JSON format for easy parsing."""

        response = self._call_llm(system_prompt, prompt)
        
        # Try to parse JSON from response
        try:
            # Extract JSON block if present
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                adjustment = json.loads(json_match.group())
                adjustment["raw_response"] = response
                return adjustment
        except Exception as e:
            log.warning(f"Failed to parse JSON response: {e}")

        return {
            "raw_response": response,
            "adjustment": {
                "recommendation": "Review manually",
                "rationale": response[:200] if response else "No response",
            },
        }

    def generate_trade_rationale(
        self,
        entry_data: Dict,
        exit_data: Optional[Dict] = None,
    ) -> str:
        """
        Generate human-readable rationale for trade entry/exit.
        
        Args:
            entry_data: Trade entry details (signal, confidence, etc.)
            exit_data: Optional exit details (price, reason, P&L)
            
        Returns:
            Formatted rationale text
        """
        if not self.client:
            return self._generate_simple_rationale(entry_data, exit_data)

        prompt = f"""Generate a concise trade rationale for documentation:

ENTRY:
- Ticker: {entry_data.get('ticker', 'N/A')}
- Sector: {entry_data.get('sector', 'N/A')}
- Entry Price: ₹{entry_data.get('entry_price', 0):.2f}
- Confidence: {entry_data.get('confidence', 0)}/100
- Signal: {entry_data.get('signal_headline', 'N/A')[:100]}
"""

        if exit_data:
            pnl_pct = exit_data.get("realised_pnl_pct", 0)
            prompt += f"""
EXIT:
- Exit Price: ₹{exit_data.get('exit_price', 0):.2f}
- P&L: {pnl_pct:+.1f}%
- Reason: {exit_data.get('exit_reason', 'N/A')}
"""

        prompt += "\nWrite a 2-3 sentence rationale explaining the trade logic and outcome."

        system_prompt = """You are documenting trades for a performance review.
Be objective and focus on the decision-making process."""

        return self._call_llm(system_prompt, prompt) or self._generate_simple_rationale(entry_data, exit_data)

    def _generate_simple_rationale(
        self,
        entry_data: Dict,
        exit_data: Optional[Dict] = None,
    ) -> str:
        """Generate simple rationale without LLM."""
        ticker = entry_data.get("ticker", "N/A")
        sector = entry_data.get("sector", "Unknown")
        conf = entry_data.get("confidence", 0)
        
        rationale = f"Entered {ticker} ({sector}) on signal with {conf}/100 confidence."
        
        if exit_data:
            pnl = exit_data.get("realised_pnl_pct", 0)
            reason = exit_data.get("exit_reason", "N/A")
            rationale += f" Exited with {pnl:+.1f}% P&L. Reason: {reason}."
        
        return rationale

    def interpret_macro_indicators(
        self,
        indicators: Dict[str, Any],
    ) -> Dict:
        """
        Interpret macroeconomic indicators and suggest portfolio positioning.
        
        Args:
            indicators: Dict of macro indicators (CPI, rates, GDP, etc.)
            
        Returns:
            Dict with interpretation and positioning suggestions
        """
        if not self.client:
            return {"error": "LLM not configured", "interpretation": None}

        indicators_str = "\n".join(f"- {k}: {v}" for k, v in indicators.items())
        
        prompt = f"""MACROECONOMIC INDICATORS:

{indicators_str}

Provide:
1. Current economic regime assessment (expansion/recession/inflation/deflation)
2. Sector rotation implications (which sectors benefit/hurt)
3. Risk management adjustments (increase/decrease exposure, hedging needs)
4. Key risks to monitor

Be specific and actionable."""

        system_prompt = """You are a macro strategist advising a fund manager.
Provide clear, actionable insights based on the data."""

        response = self._call_llm(system_prompt, prompt)
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "indicators": indicators,
            "interpretation": response,
        }

    def validate_strategy_change(
        self,
        proposed_change: str,
        current_params: Dict,
    ) -> Dict:
        """
        Validate a proposed strategy change against risk constraints.
        
        Args:
            proposed_change: Description of proposed change
            current_params: Current strategy parameters
            
        Returns:
            Validation result with risk assessment
        """
        if not self.client:
            return {"valid": True, "warnings": [], "notes": ["LLM validation skipped"]}

        prompt = f"""PROPOSED STRATEGY CHANGE:

{proposed_change}

CURRENT PARAMETERS:
{json.dumps(current_params, indent=2)}

Evaluate:
1. Does this change violate any risk constraints? (position limits, sector caps, drawdown limits)
2. What are the potential unintended consequences?
3. Should this change be: (a) auto-applied, (b) flagged for review, or (c) rejected?
4. Provide brief rationale.

Respond in JSON format with keys: valid (bool), risk_level (low/medium/high), action (apply/review/reject), warnings (list), rationale (string)"""

        system_prompt = """You are a risk manager validating strategy changes.
Be conservative. Flag any concerns."""

        response = self._call_llm(system_prompt, prompt)
        
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                result["raw_response"] = response
                return result
        except Exception as e:
            log.warning(f"Failed to parse validation response: {e}")

        return {
            "valid": True,
            "risk_level": "medium",
            "action": "review",
            "warnings": ["Manual review recommended"],
            "rationale": response[:200] if response else "No response",
            "raw_response": response,
        }


def load_portfolio_for_analysis(portfolio_file: str = "azalyst_portfolio.json") -> Dict:
    """Load portfolio data for LLM analysis."""
    import json
    import os
    
    if not os.path.exists(portfolio_file):
        log.warning(f"Portfolio file not found: {portfolio_file}")
        return {}
    
    try:
        with open(portfolio_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load portfolio: {e}")
        return {}


def fetch_macro_indicators() -> Dict:
    """
    Fetch current macroeconomic indicators for LLM context.
    
    Returns:
        Dict of key macro indicators
    """
    import urllib.request
    import json as json_lib
    
    indicators = {}
    
    # US 10-Year Treasury Yield (proxy via Yahoo Finance)
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json_lib.loads(resp.read())
        yield_val = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        indicators["US 10Y Treasury Yield"] = f"{yield_val:.2f}%"
    except Exception:
        indicators["US 10Y Treasury Yield"] = "N/A"
    
    # VIX (Volatility Index)
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json_lib.loads(resp.read())
        vix_val = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        indicators["VIX (Volatility Index)"] = f"{vix_val:.2f}"
    except Exception:
        indicators["VIX (Volatility Index)"] = "N/A"
    
    # USD/INR
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json_lib.loads(resp.read())
        usdinr = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        indicators["USD/INR Rate"] = f"{usdinr:.2f}"
    except Exception:
        indicators["USD/INR Rate"] = "N/A"
    
    # Add timestamp
    indicators["As of"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    return indicators


if __name__ == "__main__":
    # Test the optimizer
    logging.basicConfig(level=logging.INFO)
    
    optimizer = MistralETFOptimizer()
    
    if optimizer.client:
        print("LLM Optimizer initialized successfully")
        
        # Load portfolio
        portfolio = load_portfolio_for_analysis()
        
        # Fetch macro indicators
        macro = fetch_macro_indicators()
        
        # Run analysis
        result = optimizer.analyze_backtest(portfolio, macro)
        
        print("\n=== ANALYSIS RESULTS ===")
        print(f"Timestamp: {result.get('timestamp', 'N/A')}")
        print(f"Suggestions: {len(result.get('suggestions', []))}")
        
        for i, suggestion in enumerate(result.get("suggestions", []), 1):
            print(f"\n{i}. {suggestion}")
    else:
        print("LLM Optimizer not configured. Set NVIDIA_API_KEY in .env file.")
