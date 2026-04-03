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
   - Runs `azalyst.py`

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
# Trading Settings
AZALYST_THRESHOLD=62               # Confidence threshold
AZALYST_MIN_ARTICLES=2             # Minimum articles
PAPER_TRADING=true                 # Paper trading enabled
```

### What Happens on Startup:

1. **News Monitoring** (every 30 minutes)
   - Scans global news feeds
   - Classifies into sectors
   - Scores confidence (0-100)
   - Maps to ETFs

3. **Signal Evaluation** (per signal)
   - Evaluates high-confidence signals
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
│  • Daily 9 PM IST: EOD report                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Monitoring & Logs

### Log Files:

1. **`azalyst.log`** - Main system log

2. **`azalyst_portfolio.json`** - Live portfolio state
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
| **Mark-to-Market** | Every 60 min | All day |
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
Ensure your Discord webhook is correctly set.

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

### 2. Monitor Portfolio Performance
- Visit dashboard: https://gitdhirajsv.github.io/Azalyst-ETF-Intelligence/
- Check `azalyst_portfolio.json`

### 4. Adjust Parameters Monthly
Based on win rate:
- **Win rate < 40%**: Raise threshold (62→75)
- **Win rate > 60%**: Can lower threshold slightly
- **Too many trades**: Raise MIN_ARTICLES
- **Too few trades**: Lower THRESHOLD

---