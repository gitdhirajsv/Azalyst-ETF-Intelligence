# 📅 DAILY AUTOMATED WORKFLOW

> Everything runs automatically when you log in!

---

## ⏰ What Happens Every Day

### When You Log In to Windows:

```
┌─────────────────────────────────────────────────────────────┐
│  1. YOU LOG IN TO WINDOWS                                   │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  2. AZALYST STARTS AUTOMATICALLY                            │
│     (Window opens in background)                            │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  3. ETF-SPECIALIZED LLM ANALYSIS RUNS FIRST                 │
│     Powered by BlackRock/Vanguard/Fidelity methodology      │
│                                                             │
│     • ETF structure optimization                            │
│     • Securities lending analysis                           │
│     • Tax efficiency recommendations                        │
│     • Tracking error assessment                             │
│     • Creation/redemption efficiency                        │
│     • Factor exposure decomposition                         │
│                                                             │
│     Duration: 10-15 seconds                                 │
│     Output: azalyst.log                                     │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  4. STANDARD LLM PORTFOLIO ANALYSIS                         │
│     Powered by Mistral 7B                                   │
│                                                             │
│     • Win rate analysis                                     │
│     • Risk management recommendations                       │
│     • Position sizing optimization                          │
│     • Sector concentration review                           │
│     • Macro regime assessment                               │
│                                                             │
│     Duration: 5-10 seconds                                  │
│     Output: azalyst.log                                     │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  5. CONTINUOUS MONITORING STARTS                            │
│                                                             │
│     EVERY 30 MINUTES:                                       │
│     • Global news scanning (50-100 articles)                │
│     • Sector classification                                 │
│     • Confidence scoring (0-100)                            │
│     • LLM signal evaluation (75+ confidence)                │
│     • Discord alerts (if configured)                        │
│                                                             │
│     EVERY 60 MINUTES:                                       │
│     • Mark-to-market (live price updates)                   │
│     • Stop-loss checks                                      │
│     • P&L calculations                                      │
│     • Trailing stop adjustments                             │
│                                                             │
│     EVERY 6 HOURS:                                          │
│     • LLM macro regime analysis                             │
│     • Sector rotation recommendations                       │
│                                                             │
│     DAILY AT 9:00 PM IST:                                   │
│     • EOD portfolio report                                  │
│     • Win rate summary                                      │
│     • P&L statement                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Daily Timeline

| Time | Activity | Duration |
|------|----------|----------|
| **On Login** | ETF-specialized LLM analysis | 10-15 sec |
| **On Login** | Standard LLM portfolio analysis | 5-10 sec |
| **Every 30 min** | News scan + signal detection | 2-3 sec |
| **Every 60 min** | Mark-to-market updates | 1-2 sec |
| **Every 6 hours** | LLM macro analysis | 5 sec |
| **9:00 PM IST** | EOD report to Discord | 2 sec |

---

## 📁 What Gets Generated Daily

### Log Files:

1. **`azalyst.log`** - Main system log
   ```
   2026-03-31 12:00:00 [INFO] Running ETF-specialized analysis...
   2026-03-31 12:00:10 [INFO] ETF Analyst perspective complete
   2026-03-31 12:00:15 [INFO] ETF Risk Manager perspective complete
   2026-03-31 12:00:20 [INFO] ETF Quant Analyst perspective complete
   2026-03-31 12:00:25 [INFO] Running standard LLM portfolio analysis...
   2026-03-31 12:00:30 [INFO] LLM Suggestion #1: Win rate improvement...
   ```

2. **`llm_feedback_log.json`** - LLM suggestions & outcomes
   ```json
   {
     "timestamp": "2026-03-31T12:00:25Z",
     "analysis_type": "portfolio_analysis",
     "recommendations": [...],
     "confidence": 68.0
   }
   ```

3. **`azalyst_portfolio.json`** - Live portfolio state
   - Updated every trade
   - Includes open positions, closed trades
   - Real-time P&L

---

## 🎯 Your Daily Routine (2 Minutes)

### Morning (After Login):

```bash
# 1. Check what ran automatically
notepad azalyst.log

# 2. Review ETF-specialized recommendations
# Look for sections like:
# - "ETF STRUCTURE OPTIMIZATION"
# - "RISK MANAGEMENT"
# - "QUANTITATIVE IMPROVEMENTS"
# - "TAX EFFICIENCY"
# - "SECURITIES LENDING"

# 3. Review standard LLM recommendations
# Look for:
# - "TOP RECOMMENDATIONS"
# - "IMPLEMENTATION ROADMAP"
```

### Throughout the Day:

- **Passive monitoring** - Azalyst scans news every 30 min
- **Discord alerts** - If 62+ confidence signals detected
- **Paper trades** - Automatically entered (75+ confidence)

### Evening (Optional):

```bash
# Check daily performance
# Visit dashboard: https://gitdhirajsv.github.io/Azalyst-ETF-Intelligence/

# Or view portfolio
notepad azalyst_portfolio.json
```

---

## ✅ What's Automated

### ✅ Daily Analysis
- [x] ETF-specialized LLM (BlackRock methodology)
- [x] Standard portfolio LLM (Mistral 7B)
- [x] Macro regime assessment
- [x] Risk management review

### ✅ Continuous Monitoring
- [x] News scanning (every 30 min)
- [x] Signal detection (11 sectors)
- [x] Confidence scoring (0-100)
- [x] LLM signal evaluation (75+ confidence)

### ✅ Trading Operations
- [x] Paper trade entry (automatic)
- [x] Stop-loss management
- [x] Mark-to-market updates
- [x] P&L tracking

### ✅ Reporting
- [x] Log file updates
- [x] Discord alerts (if configured)
- [x] EOD reports (9 PM IST)
- [x] Dashboard updates

---

## 🛑 How to Stop/Modify

### Skip ETF Analysis for a Day:

Edit `start_azalyst.bat` - comment out this line:
```batch
REM python etf_llm_optimizer.py
```

### Disable Auto-Start Completely:

1. Press `Win+R`
2. Type: `shell:startup`
3. Delete `Azalyst ETF Intelligence.lnk`

---

## 📈 Weekly Summary (Every Monday)

On Monday mornings, you'll see:

```
WEEKLY ETF ANALYSIS SUMMARY
============================

Portfolio Value: ₹XX,XXX
Week Change: +X.XX%
Win Rate: XX%

TOP ETF INSIGHTS:
1. [Structure optimization]
2. [Risk management]
3. [Quantitative improvements]
4. [Tax efficiency]
5. [Securities lending]

ACTION ITEMS FOR THE WEEK:
• [High priority tasks]
• [Medium priority tasks]
• [Ongoing monitoring]
```

---

## 🎯 Performance Tracking

### Metrics Tracked Daily:

1. **ETF-Specific Metrics**:
   - Tracking error (bps)
   - Securities lending revenue
   - Tax efficiency (in-kind ratio)
   - Expense ratio drag
   - Creation/redemption efficiency

2. **Portfolio Metrics**:
   - Total return (%)
   - Win rate (%)
   - Average win/loss
   - Max drawdown
   - Sharpe ratio

3. **LLM Performance**:
   - Suggestion accuracy
   - Confidence calibration
   - Win rate on LLM-suggested trades

### Where to Find:

- **Daily**: `azalyst.log`
- **Weekly**: Dashboard (https://gitdhirajsv.github.io/Azalyst-ETF-Intelligence/)
- **Monthly**: Export from `azalyst_portfolio.json`

---

## 💡 Pro Tips

### 1. Review Logs Weekly
```bash
# Every Monday morning
notepad azalyst.log
```

### 2. Track ETF-Specific Improvements
Look for these in logs:
- "Securities lending revenue" - Should increase
- "Tracking error" - Should decrease
- "Tax efficiency" - Should improve

### 3. Compare Recommendations vs Actions
```bash
# What LLM recommended vs what you implemented
# Check if suggestions were actionable
```

### 4. Monthly Optimization Review
Once a month:
- Review all ETF recommendations
- Implement structural changes
- Adjust parameters based on performance

---

## 🚀 You're All Set!

**Everything runs automatically every day!**

Just log in to Windows and let Azalyst do the work:
1. ✅ ETF-specialized LLM analysis
2. ✅ Standard portfolio LLM analysis
3. ✅ Continuous news monitoring
4. ✅ Paper trading
5. ✅ Performance tracking

**Your only job**: Check `azalyst.log` occasionally and implement high-priority recommendations!

---

*For more details, see `ETF_SPECIALIZED_LLM.md` and `START_HERE.md`*
