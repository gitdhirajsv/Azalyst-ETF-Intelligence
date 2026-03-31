# Azalyst Auto-Startup Guide

> Set up Azalyst to run automatically every day when you start your laptop

---

## 🚀 Quick Setup (2 Minutes)

### Option 1: Easy Installer (Recommended)

**Step 1:** Double-click this file:
```
install_autostart.bat
```

**Step 2:** That's it! ✅

Azalyst will now start automatically every time you log in to Windows.

---

### Option 2: Task Scheduler (Advanced)

**Step 1:** Right-click on this file → "Run as Administrator"
```
setup_windows_startup.ps1
```

**Step 2:** Follow the prompts

**Benefits:**
- More control over scheduling
- Can set specific times
- Better error handling
- Restart on failure

---

## 📋 What Gets Installed

### Files Created:

1. **`start_azalyst.bat`** - Startup script
   - Changes to Azalyst directory
   - Checks Python installation
   - Runs `azalyst.py` with LLM analysis

2. **Windows Startup Shortcut** (Option 1)
   - Location: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
   - Name: `Azalyst ETF Intelligence.lnk`
   - Target: `start_azalyst.bat`

3. **Scheduled Task** (Option 2)
   - Name: "Azalyst ETF Intelligence"
   - Trigger: On user login
   - Settings: Restart on failure (3 attempts)

---

## ⚙️ Configuration

### Current Settings (from `.env`):

```dotenv
# LLM Analysis
NVIDIA_API_KEY=nvapi-6RA7q1Z-...  ✓ Configured
LLM_ENABLED=true                   ✓ Enabled
LLM_ANALYSIS_INTERVAL=1440         # Daily analysis

# Trading Settings
AZALYST_THRESHOLD=62               # Confidence threshold
AZALYST_MIN_ARTICLES=2             # Minimum articles
PAPER_TRADING=true                 # Paper trading enabled
```

### What Happens on Startup:

1. **LLM Portfolio Analysis** (5-10 seconds)
   - Analyzes your current positions
   - Fetches macro indicators (VIX, yields, USD/INR)
   - Generates improvement suggestions
   - Logs to `azalyst.log`

2. **News Monitoring** (every 30 minutes)
   - Scans global news feeds
   - Classifies into sectors
   - Scores confidence (0-100)
   - Maps to ETFs

3. **Signal Evaluation** (per signal)
   - LLM evaluates high-confidence signals
   - Provides allocation recommendations
   - Logs rationale

4. **Paper Trading** (when signals fire)
   - Enters positions (confidence 75+)
   - Manages stop-losses
   - Tracks P&L

5. **Mark-to-Market** (every 60 minutes)
   - Updates live prices
   - Checks stop-losses
   - Calculates unrealized P&L

6. **EOD Report** (daily at 3:30 PM UTC / 9:00 PM IST)
   - Sends portfolio summary to Discord
   - Includes win rate, P&L, positions

---

## 📊 Daily Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  YOU LOG IN TO WINDOWS                                      │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  Azalyst Starts Automatically                               │
│  (Window opens, shows startup banner)                       │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  LLM Portfolio Analysis Runs                                │
│  • Loads your portfolio (azalyst_portfolio.json)            │
│  • Fetches macro data (VIX, yields, USD/INR)                │
│  • Calls NVIDIA NIM API (Mistral 7B)                        │
│  • Generates 3-5 recommendations                            │
│  • Logs to azalyst.log                                      │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  News Monitoring Starts (30-min cycle)                      │
│  • Fetches 50-100 articles                                  │
│  • Classifies into 11 sectors                               │
│  • Scores confidence                                        │
│  • Sends alerts to Discord (if 62+ confidence)              │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  Continuous Operation                                       │
│  • Every 30 min: News scan                                  │
│  • Every 60 min: Mark-to-market                             │
│  • Every 6 hours: LLM macro analysis                        │
│  • Daily 9 PM IST: EOD report                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Monitoring & Logs

### Log Files:

1. **`azalyst.log`** - Main system log
   ```
   2026-03-31 12:25:42 [INFO] LLM Optimizer initialized
   2026-03-31 12:26:01 [INFO] Running LLM portfolio analysis...
   2026-03-31 12:26:15 [INFO] LLM Suggestion #1: 1. Identify Underperformance...
   ```

2. **`llm_feedback_log.json`** - LLM analysis history
   ```json
   {
     "timestamp": "2026-03-31T12:26:15Z",
     "ticker": "XLE",
     "pnl_pct": 10.7,
     "llm_suggested": true,
     "llm_rationale": "..."
   }
   ```

3. **`azalyst_portfolio.json`** - Live portfolio state
   - Updated every trade
   - Includes open positions, closed trades
   - Can be viewed in dashboard

### View Logs:

**Option A:** Open in Notepad
```bash
notepad azalyst.log
```

**Option B:** Real-time monitoring
```bash
# PowerShell
Get-Content azalyst.log -Wait -Tail 50
```

**Option C:** GitHub Dashboard
- Visit: https://gitdhirajsv.github.io/Azalyst-ETF-Intelligence/
- Updated every 30 minutes

---

## 🛑 How to Stop/Disable

### Temporary Stop:

**Close the window:**
- Click X on the Azalyst console window
- Azalyst stops, but will restart next login

### Disable Auto-Start (Option 1 - Shortcut):

**Step 1:** Press `Win+R`

**Step 2:** Type:
```
shell:startup
```

**Step 3:** Delete `Azalyst ETF Intelligence.lnk`

### Disable Auto-Start (Option 2 - Task Scheduler):

**Step 1:** Press `Win+R`

**Step 2:** Type:
```
taskschd.msc
```

**Step 3:** Find "Azalyst ETF Intelligence"

**Step 4:** Right-click → Disable (or Delete)

---

## 🎯 Customization

### Change Analysis Frequency:

Edit `.env`:
```dotenv
# Run LLM analysis every 6 hours instead of daily
LLM_ANALYSIS_INTERVAL=360
```

### Change Confidence Threshold:

Edit `.env`:
```dotenv
# Only take highest confidence signals
AZALYST_THRESHOLD=75
```

### Change News Scan Interval:

Edit `.env`:
```dotenv
# Scan every 15 minutes instead of 30
INTERVAL=15
```

### Disable Paper Trading:

Edit `.env`:
```dotenv
# Monitor only, no trades
PAPER_TRADING=false
```

---

## 📅 Scheduled Tasks Summary

| Task | Frequency | Time |
|------|-----------|------|
| **News Scan** | Every 30 min | All day |
| **LLM Signal Evaluation** | Per signal | When 75+ confidence |
| **Mark-to-Market** | Every 60 min | All day |
| **LLM Macro Analysis** | Every 6 hours | 00:00, 06:00, 12:00, 18:00 |
| **LLM Portfolio Analysis** | Daily | On startup |
| **EOD Report** | Daily | 9:00 PM IST |

---

## 🔧 Troubleshooting

### Azalyst Doesn't Start on Login:

**Check 1:** Verify shortcut exists
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```
Should contain: `Azalyst ETF Intelligence.lnk`

**Check 2:** Manually test
```bash
cd "c:\Users\Administrator\Documents\Github Pull"
start_azalyst.bat
```

**Check 3:** Check logs
```bash
notepad azalyst.log
```

### Python Not Found Error:

**Solution:** Install Python 3.9+
- Download: https://www.python.org/downloads/
- During install: ✓ Add Python to PATH

### API Key Error:

**Check `.env` file:**
```dotenv
NVIDIA_API_KEY=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
```

**Test API:**
```bash
python test_llm_integration.py
```

### High CPU Usage:

**Solution:** Reduce scan frequency
```dotenv
INTERVAL=60  # Scan every 60 min instead of 30
```

---

## 💡 Tips & Best Practices

### 1. Check Logs Daily
```bash
# First thing in morning
notepad azalyst.log
```

### 2. Review LLM Suggestions Weekly
```bash
# Run manual analysis
python azalyst.py --llm-analysis
```

### 3. Monitor Portfolio Performance
- Visit dashboard: https://gitdhirajsv.github.io/Azalyst-ETF-Intelligence/
- Check `azalyst_portfolio.json`

### 4. Adjust Parameters Monthly
Based on win rate:
- **Win rate < 40%**: Raise threshold (62→75)
- **Win rate > 60%**: Can lower threshold slightly
- **Too many trades**: Raise MIN_ARTICLES
- **Too few trades**: Lower THRESHOLD

### 5. Keep API Key Secure
- Never commit `.env` to git
- Rotate key every 3-6 months
- Monitor usage at: https://build.nvidia.com/profile/api-usage

---

## 📞 Quick Commands

```bash
# Start manually
start_azalyst.bat

# Run LLM analysis only
python azalyst.py --llm-analysis

# Test integration
python test_llm_integration.py

# Get recommendations
python get_mistral_recommendations.py

# View logs (PowerShell)
Get-Content azalyst.log -Wait -Tail 50

# View feedback stats
python -c "from llm_analyzer import *; from config import *; cfg=Config(); a=LLMAnalyzer(cfg); print(a.get_feedback_statistics())"
```

---

## ✅ Setup Checklist

- [ ] Run `install_autostart.bat`
- [ ] Verify shortcut in Startup folder
- [ ] Test with `start_azalyst.bat`
- [ ] Check `azalyst.log` for errors
- [ ] Verify API key in `.env`
- [ ] Run `test_llm_integration.py`
- [ ] Check Discord webhook (if using)
- [ ] Review initial LLM recommendations

---

**That's it! Azalyst will now run automatically every day.** 🎉

Just start your laptop and Azalyst will:
1. ✅ Start automatically
2. ✅ Run LLM analysis
3. ✅ Monitor news 24/7
4. ✅ Send alerts to Discord
5. ✅ Track your portfolio

---

*For more details, see `docs/LLM_INTEGRATION.md`*
