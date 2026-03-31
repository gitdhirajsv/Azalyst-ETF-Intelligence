# LLM Quick Reference — Azalyst ETF Intelligence

> Quick start guide for NVIDIA NIM (Mistral 7B) integration

---

## 1-Minute Setup

```bash
# 1. Get API key from https://build.nvidia.com/explore/discover

# 2. Add to .env
echo "NVIDIA_API_KEY=nvapi-your_key_here" >> .env

# 3. Run
python azalyst.py
```

---

## Commands

```bash
# Normal operation with LLM
python azalyst.py

# LLM analysis only
python azalyst.py --llm-analysis

# Test optimizer
python llm_optimizer.py

# Test analyzer
python llm_analyzer.py
```

---

## Configuration

```dotenv
# Required for LLM
NVIDIA_API_KEY=nvapi-your_key_here

# Optional tuning
LLM_MODEL=mistralai/mistral-7b-instruct-v0.3
LLM_TEMPERATURE=0.2        # Lower = more deterministic
LLM_MAX_TOKENS=1024        # Response length
LLM_ANALYSIS_INTERVAL=1440 # Minutes (1440 = daily)
LLM_AUTO_APPLY=false       # Manual review first
```

---

## Features

| Feature | What It Does |
|---------|--------------|
| **Portfolio Analysis** | Analyzes performance, suggests improvements |
| **Signal Enhancement** | Evaluates signals, recommends allocation |
| **Macro Regime Detection** | Interprets economic indicators |
| **Trade Documentation** | Auto-generates trade rationales |
| **Feedback Loop** | Learns from trade outcomes |

---

## Sample Output

```
LLM Analysis mode — running portfolio analysis...
Analysis complete. Generated 5 suggestions

1. Your win rate of 45% is below target. Consider raising confidence threshold to 70.

2. Maximum drawdown of 8.2% is approaching the 12% limit. Reduce position sizing to 15%.

3. Energy sector trades show 65% win rate vs 35% for tech. Overweight energy signals.

4. Add volatility filter (VIX > 30) to avoid choppy market whipsaws.

5. Implement trailing stop at 8% to capture more upside in trending markets.
```

---

## API Reference

### Portfolio Analysis

```python
from llm_analyzer import LLMAnalyzer
from config import Config

cfg = Config()
analyzer = LLMAnalyzer(cfg)

result = analyzer.run_portfolio_analysis()
print(result['suggestions'])
```

### Signal Evaluation

```python
rec = analyzer.evaluate_signal(signal, portfolio_context)
print(f"Action: {rec['action']}")
print(f"Allocation: {rec['allocation_pct']}%")
```

### Macro Regime

```python
regime = analyzer.interpret_macro_regime()
print(f"Regime: {regime['regime']}")
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "API key not set" | Add `NVIDIA_API_KEY` to `.env` |
| Poor suggestions | Lower `LLM_TEMPERATURE` to 0.1 |
| Rate limits | Increase `LLM_ANALYSIS_INTERVAL` |
| High cost | Reduce analysis frequency |

---

## Cost Estimate

- **Typical usage**: $0.50-1.00/month
- **Per analysis**: ~$0.01
- **Per signal**: ~$0.001

---

## Next Steps

1. **Run analysis**: `python azalyst.py --llm-analysis`
2. **Review suggestions**: Check `azalyst.log`
3. **Adjust parameters**: Edit `.env` as needed
4. **Read full guide**: `docs/LLM_INTEGRATION.md`

---

**Questions?** See `docs/LLM_INTEGRATION.md` for complete documentation.
