# LLM Integration Guide — Azalyst ETF Intelligence

> Integrating NVIDIA NIM's Mistral 7B Instruct for AI-powered ETF strategy optimization

---

## Overview

This guide covers the integration of **NVIDIA NIM** (Mistral 7B Instruct) into the Azalyst ETF Intelligence platform. The LLM integration provides:

- **Portfolio Performance Analysis**: Automated analysis of trading results with actionable improvement suggestions
- **Signal Enhancement**: LLM-evaluated trading signals with allocation recommendations
- **Macro Regime Detection**: Economic regime interpretation and sector rotation guidance
- **Trade Documentation**: Auto-generated rationales for compliance and review
- **Feedback Loop**: Continuous learning from trade outcomes

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Core LLM dependencies:
- `openai>=1.12.0` — NVIDIA NIM API client
- `langchain-nvidia-ai-endpoints>=0.1.0` — Optional LangChain integration
- `transformers>=4.38.0` — Optional local model deployment

### 2. Configure API Key

Get your NVIDIA API key from: https://build.nvidia.com/explore/discover

Add to `.env`:
```env
NVIDIA_API_KEY=nvapi-your_key_here
```

### 3. Configure LLM Settings

Add to `.env`:
```env
# LLM Integration Settings
LLM_MODEL=mistralai/mistral-7b-instruct-v0.3
LLM_TEMPERATURE=0.2
LLM_TOP_P=0.7
LLM_MAX_TOKENS=1024
LLM_ENABLED=true
LLM_ANALYSIS_INTERVAL=1440  # minutes (1440 = daily)
LLM_AUTO_APPLY=false
LLM_MIN_CONFIDENCE=75
```

### 4. Run with LLM Enabled

```bash
# Normal operation with LLM enhancement
python azalyst.py

# LLM analysis only mode
python azalyst.py --llm-analysis

# Test the optimizer directly
python llm_optimizer.py

# Test the analyzer directly
python llm_analyzer.py
```

---

## Architecture

### File Structure

```
.
|-- azalyst.py              # Main engine (LLM-enhanced)
|-- llm_optimizer.py        # NVIDIA NIM client & optimization logic
|-- llm_analyzer.py         # Analysis workflow integration
|-- llm_prompts.py          # Prompt templates
|-- config.py               # Configuration (includes LLM settings)
|-- .env                    # Environment variables (API keys)
|-- llm_feedback_log.json   # Trade outcome log for learning
+-- docs/
    +-- LLM_INTEGRATION.md  # This file
```

### Data Flow

```
┌─────────────────────┐
│  Portfolio Data     │
│  (azalyst_portfolio)│
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  Macro Indicators   │
│  (Yahoo Finance)    │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  LLM Optimizer      │
│  (NVIDIA NIM API)   │
│  Mistral 7B Instruct│
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  Analysis Results   │
│  - Suggestions      │
│  - Recommendations  │
│  - Rationale        │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  Feedback Log       │
│  (Trade Outcomes)   │
│  Continuous Learning│
└─────────────────────┘
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NVIDIA_API_KEY` | Required | Your NVIDIA NIM API key |
| `LLM_MODEL` | `mistralai/mistral-7b-instruct-v0.3` | Model to use |
| `LLM_TEMPERATURE` | `0.2` | Sampling temperature (0.0-1.0) |
| `LLM_TOP_P` | `0.7` | Nucleus sampling parameter |
| `LLM_MAX_TOKENS` | `1024` | Maximum response length |
| `LLM_ENABLED` | `true` | Enable/disable LLM features |
| `LLM_ANALYSIS_INTERVAL` | `1440` | Analysis frequency in minutes |
| `LLM_AUTO_APPLY` | `false` | Auto-apply safe suggestions |
| `LLM_MIN_CONFIDENCE` | `75` | Min confidence for auto-apply |

### Configuration via `config.py`

All LLM settings are accessible via the `Config` class:

```python
from config import Config

cfg = Config()
print(cfg.NVIDIA_API_KEY)
print(cfg.LLM_MODEL)
print(cfg.LLM_ENABLED)
```

---

## Features

### 1. Portfolio Performance Analysis

**What it does**: Analyzes your portfolio's performance metrics and provides specific recommendations for improvement.

**Input**:
- Portfolio metrics (win rate, drawdown, P&L)
- Open positions and closed trades
- Macroeconomic indicators

**Output**:
- Performance diagnosis
- Parameter adjustment suggestions
- Risk management improvements
- Strategy enhancements

**Example**:
```python
from llm_analyzer import LLMAnalyzer
from config import Config

cfg = Config()
analyzer = LLMAnalyzer(cfg)

result = analyzer.run_portfolio_analysis()
print(result['suggestions'])
```

**Sample Output**:
```
1. Your win rate of 45% is below the target 55%. Consider raising the confidence threshold from 62 to 70 to filter lower-quality signals.

2. Maximum drawdown of 8.2% is approaching the 12% limit. Reduce position sizing from 20% to 15% per trade.

3. Energy sector trades show 65% win rate vs 35% for tech. Consider overweighting energy signals and underweighting technology.
```

---

### 2. Signal Enhancement

**What it does**: Evaluates individual trading signals and provides allocation recommendations.

**When**: Runs automatically for each new signal when LLM is enabled.

**Output**:
- Action recommendation (Enter/Add/Wait/Skip)
- Suggested allocation percentage
- Risk parameters (stop-loss, take-profit)
- Rationale

**Integration**:
```python
# In azalyst.py, automatically called for each signal
llm_rec = llm_analyzer.evaluate_signal(signal, portfolio_context)
signal["llm_recommendation"] = llm_rec
```

**Sample Response**:
```json
{
  "action": "enter",
  "confidence": "high",
  "allocation_pct": 15,
  "stop_loss_pct": 8,
  "take_profit_pct": 20,
  "max_hold_days": 30,
  "rationale": "Energy sector showing strong momentum with 87/100 confidence. Multiple tier-1 sources confirm supply disruption."
}
```

---

### 3. Macro Regime Detection

**What it does**: Interprets macroeconomic indicators to identify the current economic regime and suggest sector rotations.

**Indicators Tracked**:
- US 10Y Treasury Yield
- VIX (Volatility Index)
- USD/INR Rate
- (Extensible to CPI, GDP, etc.)

**Regime Labels**:
- `expansion` — Growth accelerating
- `slowdown` — Growth decelerating
- `recession` — Economic contraction
- `recovery` — Post-recession rebound
- `high_inflation` — Inflationary pressure
- `high_volatility` — Risk-off environment

**Usage**:
```python
regime_result = analyzer.interpret_macro_regime()
print(f"Current regime: {regime_result['regime']}")
print(regime_result['interpretation'])
```

**Sample Output**:
```
Current regime: high_inflation

The economy is experiencing inflationary pressure with the 10Y yield at 4.5% 
and elevated commodity prices. This favors:
- OVERWEIGHT: Energy, Materials, Real Estate
- UNDERWEIGHT: Technology, Growth stocks
- Hedge with: TIPS, Commodities
```

---

### 4. Trade Documentation

**What it does**: Auto-generates human-readable rationales for trades.

**When**: Called automatically when trades are exited.

**Output**: Concise 2-3 sentence rationale explaining the trade logic and outcome.

**Example**:
```python
rationale = analyzer.generate_trade_documentation(
    entry_data={
        "ticker": "XLE",
        "sector": "Energy",
        "entry_price": 95.0,
        "confidence": 85,
        "signal_headline": "Oil prices surge on supply disruption",
    },
    exit_data={
        "exit_price": 105.0,
        "pnl_pct": 10.5,
        "exit_reason": "Target hit",
    }
)
```

**Sample Output**:
```
"Entered XLE (Energy) on signal with 85/100 confidence, driven by oil supply 
disruption concerns. The trade achieved a +10.5% return as prices rallied on 
tightening supply expectations. Exit triggered at the pre-defined profit target, 
validating the momentum thesis."
```

---

### 5. Feedback Loop

**What it does**: Logs all trade outcomes for continuous learning and model improvement.

**Logged Data**:
- Trade entry/exit details
- P&L outcome
- Whether LLM suggested the trade
- LLM's original rationale

**Feedback Log Location**: `llm_feedback_log.json`

**Export for Fine-tuning**:
```python
analyzer.export_feedback_for_finetuning("training_data.jsonl")
```

**Output Format** (JSONL):
```json
{"instruction": "Analyze this ETF trade...", "input": "", "output": "This trade was successful..."}
```

**Feedback Statistics**:
```python
stats = analyzer.get_feedback_statistics()
print(f"LLM Win Rate: {stats['llm_win_rate']}%")
print(f"LLM Avg P&L: {stats['llm_avg_pnl_pct']}%")
```

---

## Usage Examples

### Example 1: Run LLM Analysis Only

```bash
python azalyst.py --llm-analysis
```

**Output**:
```
LLM Analysis mode — running portfolio analysis...
Analysis complete. Generated 5 suggestions

1. Your win rate of 45% is below target. Consider raising confidence threshold to 70.

2. Maximum drawdown approaching limit. Reduce position sizing to 15%.

3. Energy sector outperforming. Consider overweighting energy signals.

4. Add volatility filter (VIX > 30) to avoid choppy market whipsaws.

5. Implement trailing stop at 8% to capture more upside in trending markets.
```

---

### Example 2: Programmatic Analysis

```python
from llm_optimizer import MistralETFOptimizer, load_portfolio_for_analysis, fetch_macro_indicators

# Initialize optimizer
optimizer = MistralETFOptimizer(api_key="nvapi-your_key")

# Load data
portfolio = load_portfolio_for_analysis()
macro = fetch_macro_indicators()

# Run analysis
result = optimizer.analyze_backtest(portfolio, macro)

# Print suggestions
for i, suggestion in enumerate(result['suggestions'], 1):
    print(f"{i}. {suggestion}")
```

---

### Example 3: Signal Evaluation

```python
from llm_analyzer import LLMAnalyzer
from config import Config

cfg = Config()
analyzer = LLMAnalyzer(cfg)

signal = {
    "sector_label": "Energy / Oil & Gas",
    "confidence": 87,
    "severity": "CRITICAL",
    "article_count": 12,
    "sources": ["Reuters", "Bloomberg", "WSJ"],
}

portfolio_context = {
    "cash": 5000,
    "open_positions_count": 3,
    "sector_exposure": {"Energy": "15%"},
}

rec = analyzer.evaluate_signal(signal, portfolio_context)
print(f"Action: {rec['action']}")
print(f"Allocation: {rec['allocation_pct']}%")
print(f"Rationale: {rec['rationale']}")
```

---

### Example 4: Macro Regime Interpretation

```python
from llm_analyzer import LLMAnalyzer
from config import Config

cfg = Config()
analyzer = LLMAnalyzer(cfg)

regime = analyzer.interpret_macro_regime()
print(f"Regime: {regime['regime']}")
print(f"Interpretation:\n{regime['interpretation']}")
```

---

## Fine-tuning (Optional)

### Why Fine-tune?

While the base Mistral 7B Instruct model works well out-of-box, fine-tuning on your specific trading data can:

- Improve suggestion relevance to your strategy
- Learn from your historical wins/losses
- Adapt to your risk tolerance
- Capture your decision-making style

### Prepare Training Data

```python
from llm_analyzer import LLMAnalyzer
from config import Config

cfg = Config()
analyzer = LLMAnalyzer(cfg)

# Export feedback log as training data
analyzer.export_feedback_for_finetuning("training_data.jsonl")
```

### Fine-tune with LoRA

```python
# See: llm_fine_tune.py (optional module)
# Uses PEFT + LoRA for efficient fine-tuning

from transformers import TrainingArguments
from peft import LoraConfig

# Configure LoRA
lora_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q_proj", "v_proj"],
)

# Train on your data
# (Full implementation available on request)
```

### Deploy Fine-tuned Model

1. Upload fine-tuned model to Hugging Face
2. Update `.env`:
   ```env
   LLM_MODEL=your-hf-username/azalyst-mistral-7b-finetuned
   ```
3. Restart Azalyst

---

## Troubleshooting

### LLM Not Working

**Symptom**: "LLM Analyzer disabled: NVIDIA_API_KEY not set"

**Solution**:
1. Get API key from https://build.nvidia.com/explore/discover
2. Add to `.env`:
   ```env
   NVIDIA_API_KEY=nvapi-your_key_here
   ```
3. Restart Azalyst

---

### API Rate Limits

**Symptom**: "Rate limit exceeded" errors

**Solutions**:
1. Increase `LLM_ANALYSIS_INTERVAL` (default: 1440 minutes = daily)
2. Reduce `LLM_MAX_TOKENS` (default: 1024)
3. Upgrade NVIDIA API tier for higher limits

---

### Poor Quality Suggestions

**Symptom**: Generic or irrelevant recommendations

**Solutions**:
1. Lower `LLM_TEMPERATURE` (try 0.1 for more deterministic output)
2. Provide more historical data in portfolio
3. Add more macro indicators
4. Consider fine-tuning on your strategy

---

### JSON Parsing Errors

**Symptom**: "Failed to parse JSON response"

**Cause**: LLM response not perfectly formatted JSON

**Solution**: Already handled gracefully with fallback parsing. Check logs for details.

---

## Best Practices

### 1. Start Conservative

```env
LLM_AUTO_APPLY=false  # Manual review first
LLM_ANALYSIS_INTERVAL=1440  # Daily analysis
```

### 2. Monitor Performance

```python
stats = analyzer.get_feedback_statistics()
print(f"LLM Win Rate: {stats['llm_win_rate']}%")
```

Compare LLM-suggested trades vs non-LLM trades.

### 3. Iterate on Prompts

Edit `llm_prompts.py` to customize analysis focus:
- Add your specific risk constraints
- Emphasize metrics you care about
- Include strategy-specific rules

### 4. Use as Decision Support

LLM suggestions are **advisory**, not prescriptive. Always apply human judgment.

### 5. Log Everything

Keep `llm_feedback_log.json` for:
- Performance tracking
- Fine-tuning data
- Compliance documentation

---

## API Reference

### `MistralETFOptimizer`

**Main class for NVIDIA NIM interaction.**

```python
from llm_optimizer import MistralETFOptimizer

optimizer = MistralETFOptimizer(
    api_key="nvapi-key",
    model="mistralai/mistral-7b-instruct-v0.3",
    temperature=0.2,
    top_p=0.7,
    max_tokens=1024,
)
```

**Methods**:
- `analyze_backtest(portfolio_data, macro_context, etf_fundamentals)` → Dict
- `suggest_strategy_adjustment(signal, current_allocation, market_regime)` → Dict
- `generate_trade_rationale(entry_data, exit_data)` → str
- `interpret_macro_indicators(indicators)` → Dict
- `validate_strategy_change(proposed_change, current_params)` → Dict

---

### `LLMAnalyzer`

**Integration layer for Azalyst workflow.**

```python
from llm_analyzer import LLMAnalyzer
from config import Config

cfg = Config()
analyzer = LLMAnalyzer(cfg)
```

**Methods**:
- `run_portfolio_analysis()` → Dict
- `evaluate_signal(signal, portfolio_context, market_regime)` → Dict
- `interpret_macro_regime()` → Dict
- `generate_trade_documentation(entry_data, exit_data)` → str
- `log_trade_outcome(trade_data)` → None
- `get_feedback_statistics()` → Dict
- `export_feedback_for_finetuning(output_file)` → None

---

### `PromptTemplates`

**Standardized prompt templates.**

```python
from llm_prompts import PromptTemplates

# Format backtest analysis prompt
prompt = PromptTemplates.format_backtest_prompt(portfolio_data, macro_context)

# Format signal evaluation prompt
prompt = PromptTemplates.format_signal_prompt(signal, portfolio_context)

# Format macro interpretation prompt
prompt = PromptTemplates.format_macro_prompt(indicators)
```

---

## Performance Benchmarks

### Latency

| Operation | Typical Time |
|-----------|--------------|
| Portfolio Analysis | 3-5 seconds |
| Signal Evaluation | 2-3 seconds |
| Macro Interpretation | 3-4 seconds |
| Trade Documentation | 2-3 seconds |

### Token Usage

| Operation | Avg Tokens |
|-----------|------------|
| Portfolio Analysis | ~800 tokens |
| Signal Evaluation | ~400 tokens |
| Macro Interpretation | ~600 tokens |
| Trade Documentation | ~200 tokens |

**Cost Estimate** (at current NVIDIA NIM pricing):
- Daily analysis: ~$0.02/day
- Per signal: ~$0.001
- Monthly total: ~$0.50-1.00

---

## Security

### API Key Management

- **Never commit** `.env` to git
- Store keys in environment variables for production
- Rotate keys periodically
- Use separate keys for dev/prod

### Data Privacy

- Portfolio data sent to NVIDIA NIM API
- No personally identifiable information (PII) included
- Trade data anonymized in prompts
- Feedback log stored locally only

---

## Roadmap

### Planned Enhancements

1. **Auto-Apply Engine**: Automatically implement safe parameter adjustments
2. **Multi-Model Support**: Compare suggestions from multiple LLMs
3. **Local Deployment**: Run Mistral locally via Ollama for zero API costs
4. **RAG Integration**: Retrieve historical similar scenarios for context
5. **Discord Reports**: Send LLM analysis summaries to Discord
6. **Backtest Integration**: Test LLM suggestions on historical data

### Experimental Features

- Fine-tuning pipeline
- Ensemble voting (multiple LLMs)
- Confidence calibration
- Suggestion explainability

---

## Contributing

Contributions welcome! Areas of focus:

1. **Prompt Engineering**: Improve template quality
2. **Fine-tuning**: Develop domain-specific models
3. **Evaluation**: Rigorous backtesting of LLM suggestions
4. **Local Deployment**: Ollama/LM Studio integration
5. **Cost Optimization**: Caching, batching, compression

---

## Support

- **Issues**: GitHub Issues
- **Discord**: [Link to community]
- **Documentation**: `docs/` folder
- **Examples**: `llm_optimizer.py`, `llm_analyzer.py` (run with `--help`)

---

## Disclaimer

This LLM integration is for **research and educational purposes only**. 

- LLM suggestions are **not financial advice**
- Always apply human judgment
- Past performance does not guarantee future results
- LLM can make mistakes (hallucinations)
- Verify all recommendations independently

The LLM is a **decision support tool**, not an autonomous trading system.

---

## Attribution

- **Mistral 7B**: Mistral AI (https://mistral.ai)
- **NVIDIA NIM**: NVIDIA Corporation (https://build.nvidia.com)
- **Azalyst ETF Intelligence**: Azalyst Quant Research

---

**Built with ❤️ by Azalyst Quant Research**

*For informational use only. Not financial advice.*
