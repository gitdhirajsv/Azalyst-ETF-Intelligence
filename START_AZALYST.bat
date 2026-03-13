@echo off
:: ============================================================
:: AZALYST ETF INTELLIGENCE — Windows Launcher
:: Double-click this file to start the system
:: ============================================================

title AZALYST ETF Intelligence System

echo.
echo  ╔═══════════════════════════════════════════╗
echo  ║   AZALYST ETF INTELLIGENCE SYSTEM         ║
echo  ║   Macro Fund Edition — Starting...        ║
echo  ╚═══════════════════════════════════════════╝
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Please install Python 3.9+ from python.org
    echo  Press any key to exit...
    pause >nul
    exit /b 1
)

:: Navigate to script directory
cd /d "%~dp0"

:: Install / upgrade dependencies silently
echo  [1/3] Checking dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [WARNING] Some dependencies may not have installed correctly.
    echo  Try running: pip install -r requirements.txt
)

echo  [2/3] Dependencies ready.
echo  [3/3] Starting AZALYST...
echo.

:: The application auto-loads a local .env file when present.
:: You can also override settings here if needed.
:: set WEBHOOK=https://discord.com/api/webhooks/YOUR_WEBHOOK

:: Optional: Adjust polling interval (default 30 minutes)
:: set INTERVAL=30

:: Optional: Adjust confidence threshold (default 62)
:: set AZALYST_THRESHOLD=62

:: Run the main script
python azalyst.py

:: If it crashes, show error and pause
if errorlevel 1 (
    echo.
    echo  [ERROR] AZALYST crashed. Check azalyst.log for details.
    echo  Press any key to exit...
    pause >nul
)
