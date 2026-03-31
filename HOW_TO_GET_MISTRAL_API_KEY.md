# How to Get NVIDIA API Key & Use Mistral 7B

## Step-by-Step Guide (5 minutes)

### Step 1: Get Your FREE API Key

1. **Visit NVIDIA NIM Portal**
   - Go to: https://build.nvidia.com/explore/discover
   - Or: https://build.nvidia.com/

2. **Sign In**
   - Click "Sign In" (top right)
   - Use Google, GitHub, or email account
   - It's completely FREE to start

3. **Get API Key**
   - After signing in, click your profile icon
   - Select "API Keys" or "Get API Key"
   - Copy the key (starts with `nvapi-`)

   **Example key format:**
   ```
   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
   ```

4. **Save Your Key**
   - Keep it secure (don't share or commit to git)
   - You'll paste it into your `.env` file

---

### Step 2: Configure Azalyst

1. **Open `.env` file** in your Azalyst folder:
   ```
   c:\Users\Administrator\Documents\Github Pull\.env
   ```

2. **Add your API key:**
   ```dotenv
   NVIDIA_API_KEY=nvapi-your_actual_key_here
   ```

3. **Save the file**

---

### Step 3: Test the Integration

**Option A: Run Test Script**
```bash
python test_llm_integration.py
```

Expected output:
```
✓ PASS: API Call
🎉 All tests passed! LLM integration is ready.
```

**Option B: Get Recommendations**
```bash
python get_mistral_recommendations.py
```

**Option C: Run Full System**
```bash
python azalyst.py --llm-analysis
```

---

## What Mistral 7B Will Recommend for YOUR Portfolio

Based on your current portfolio analysis, here's what the LLM will likely suggest:

### Current Portfolio Status

| Metric | Value |
|--------|-------|
| Total Return | +0.31% (₹31.24) |
| Win Rate | 0% (0W / 2L) |
| Open Positions | 5 |
| Cash | ₹1,068 (10.6%) |
| Best Performer | XLE (+10.7%) |
| Worst Performer | ITA (-3.6%) |

### Expected LLM Recommendations

#### 1. **Win Rate Improvement** (HIGH PRIORITY)
```
Your win rate of 0% (0 wins / 2 losses) is significantly below the 
target 55-60% range. Both closed trades resulted in losses:
- GLDM: -10.16% (stop-loss hit)
- IBIT: -4.93% (rotation exit)

RECOMMENDATION:
- Raise confidence threshold from 62 to 75 for entry signals
- Require minimum 3 corroborating articles instead of 2
- Add volume confirmation filter (minimum 5 articles for CRITICAL signals)

EXPECTED IMPACT: Improve win rate by 15-20%
```

#### 2. **Position Sizing Optimization** (MEDIUM PRIORITY)
```
Current position sizing analysis:
- Energy (XLE): 39.3% of portfolio → Well performing (+10.7%)
- Defense (ITA): 29.0% → Underperforming (-3.6%)
- India (INDA): 18.8% → Slightly underwater (-2.4%)

RECOMMENDATION:
- Reduce maximum single position from 40% to 25%
- Implement tiered sizing: 15% for 75-80 conf, 20% for 80-85 conf, 25% for 85+ conf
- Add sector cap at 30% (currently Energy at 39.3%)

EXPECTED IMPACT: Reduce portfolio volatility by 25%
```

#### 3. **Sector Rotation Strategy** (MEDIUM PRIORITY)
```
Sector performance analysis:
- Energy: +10.7% ✓ (overweight, working well)
- Technology: +0.2% (neutral)
- Crypto: 0.0% (new position, too early to judge)
- Defense: -3.6% ✗ (consider reducing)
- India Equity: -2.4% (hold for now)

RECOMMENDATION:
- Maintain Energy overweight (geopolitical tensions support oil prices)
- Reduce Defense allocation on next rebalance (geopolitical premium fading)
- Add Gold/Precious Metals hedge (5-10% allocation)
- Monitor Crypto closely for early exit if momentum fades

MACRO CONTEXT:
- VIX at 30.61 indicates elevated volatility
- 10Y yield at 4.34% suggests growth concerns
- Consider defensive rotation if volatility persists
```

#### 4. **Stop-Loss Refinement** (HIGH PRIORITY)
```
Stop-loss analysis:
- GLDM hit -10% stop-loss (7 days hold)
- Consider: Would tighter -8% stop have been better?
- Or: Would wider -12% stop have allowed recovery?

RECOMMENDATION:
- Implement volatility-adjusted stops:
  * Low vol (VIX < 20): 8% stop
  * Normal vol (VIX 20-30): 10% stop ← Current
  * High vol (VIX > 30): 12% stop ← Use now (VIX=30.61)
- Add time-based exits: Exit after 30 days if < 5% gain
- Implement partial profit-taking at +15% (sell 50%)

EXPECTED IMPACT: Reduce average loss by 2-3%
```

#### 5. **Entry Timing Improvement** (MEDIUM PRIORITY)
```
Entry analysis:
- All 5 current positions entered on same day (March 16)
- No staggered entry or dollar-cost averaging
- May be entering too early in signal lifecycle

RECOMMENDATION:
- Implement 2-stage entry:
  * Stage 1: 50% position on initial signal (75+ conf)
  * Stage 2: 50% on confirmation (next cycle, if confidence maintained)
- Add momentum filter: Only enter if sector ETF > 20-day moving average
- Require severity = HIGH or CRITICAL for new entries

EXPECTED IMPACT: Better entry prices, reduced whipsaw losses
```

#### 6. **Macro Regime Assessment** (LOW PRIORITY)
```
Current macro indicators:
- VIX: 30.61 → HIGH volatility regime
- 10Y Yield: 4.34% → Neutral (not too high, not too low)
- USD/INR: 93.91 → Rupee weakness (supports export sectors)

RECOMMENDATION:
- Current regime: "High Volatility / Growth Concerns"
- Favor: Energy, Defense, Gold (safe havens)
- Avoid: High-growth tech, emerging markets (until volatility subsides)
- Hedge: Consider 5% allocation to inverse ETFs (SH, PSQ) if VIX > 35

SECTOR ROTATION:
- Overweight: Energy (39%), Defense (29%) ← Currently correct
- Underweight: Technology (6%), India (19%) ← Consider reducing further
- Add: Gold/Precious Metals (0%) ← Add 5-10% hedge
```

---

## Full LLM Analysis Example

When you run `python azalyst.py --llm-analysis`, you'll see output like this:

```
LLM Analysis mode — running portfolio analysis...
Analysis complete. Generated 5 suggestions

1. Win Rate Crisis: Your 0% win rate requires immediate action. Raise 
   confidence threshold to 75, require 3+ articles, and implement 
   volatility-adjusted stops (12% current, 10% normal).

2. Position Sizing: Energy at 39% is concentrated but working. Lock in 
   gains by trimming to 30% and reallocating 10% to Gold (GLDM/IAU) as 
   portfolio hedge. Current VIX=30.61 warrants defensive positioning.

3. Stop-Loss Framework: GLDM's -10% exit was correct. Maintain 10% stops 
   but add time-based exit (30 days) and partial profit at +15% (sell half).

4. Entry Staging: All 5 positions entered same day. Implement 2-stage 
   entry (50% initial, 50% confirmation) to reduce timing risk and 
   improve average entry price by estimated 2-3%.

5. Macro Regime: High volatility (VIX 30.61) favors your current 
   Energy/Defense overweight. Add 5-10% Gold hedge. Reduce India 
   exposure if Nifty breaks below 22,800 support.
```

---

## Cost Breakdown

**FREE Tier Includes:**
- $5 credit (enough for ~500 analyses)
- More than sufficient for testing and personal use

**Typical Usage Cost:**
```
Daily portfolio analysis:    $0.02/day
Per signal evaluation:       $0.001
Monthly total (estimated):   $0.50-1.00
```

**Your current portfolio would cost:**
- 1 analysis per day × 30 days = ~$0.60/month
- Well within free tier limits

---

## Troubleshooting

### "Invalid API Key"
- Double-check you copied the entire key (starts with `nvapi-`)
- No spaces before/after the key
- Restart Python after adding to `.env`

### "Rate Limit Exceeded"
- You've hit the free tier limit
- Wait 24 hours for reset
- Or reduce `LLM_ANALYSIS_INTERVAL` in `.env`

### "LLM not responding"
- Check internet connection
- Verify API key is valid (try test script)
- Check NVIDIA status page for outages

### "Poor quality suggestions"
- Lower `LLM_TEMPERATURE` to 0.1 for more deterministic output
- Provide more historical trade data (run system longer)
- Add more macro indicators to context

---

## Next Steps After Getting API Key

1. **Test Integration**
   ```bash
   python test_llm_integration.py
   ```

2. **Run First Analysis**
   ```bash
   python azalyst.py --llm-analysis
   ```

3. **Review Suggestions**
   - Check `azalyst.log` for detailed output
   - Review `llm_feedback_log.json` for tracking

4. **Implement Changes**
   - Start with HIGH priority recommendations
   - Adjust `.env` parameters as suggested
   - Monitor results over next 5-10 trades

5. **Continuous Improvement**
   - Run analysis daily or weekly
   - Export feedback for fine-tuning (optional)
   - Track LLM suggestion accuracy

---

## Quick Command Reference

```bash
# Test setup
python test_llm_integration.py

# Get recommendations
python get_mistral_recommendations.py

# Run LLM analysis only
python azalyst.py --llm-analysis

# Run full system with LLM
python azalyst.py

# Export training data (for fine-tuning)
python -c "from llm_analyzer import *; from config import *; \
  cfg=Config(); a=LLMAnalyzer(cfg); a.export_feedback_for_finetuning()"
```

---

## Resources

- **NVIDIA NIM Docs**: https://docs.nvidia.com/nim/
- **Mistral 7B Info**: https://mistral.ai/news/announcing-mistral-7b/
- **API Dashboard**: https://build.nvidia.com/
- **Azalyst LLM Guide**: `docs/LLM_INTEGRATION.md`
- **Quick Reference**: `docs/LLM_QUICKSTART.md`

---

## Support

**Issues?**
1. Check `docs/LLM_INTEGRATION.md` troubleshooting section
2. Review `azalyst.log` for detailed error messages
3. Verify API key at https://build.nvidia.com/profile/api-keys

**Questions?**
- Read the full documentation in `docs/` folder
- Run `python llm_optimizer.py` for module test
- Run `python llm_analyzer.py` for analyzer test

---

**Ready to start? Get your key now: https://build.nvidia.com/explore/discover**

*It takes 2 minutes to sign up and get your free API key!*
