@echo off
REM Azalyst ETF Intelligence - Auto Startup Script
REM This script starts Azalyst with LLM analysis enabled

echo ============================================================
echo   AZALYST ETF INTELLIGENCE - STARTING
echo   LLM-Powered Portfolio Analysis
echo ============================================================
echo.

REM Change to Azalyst directory
cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

echo [%DATE% %TIME%] Starting Azalyst...
echo.

REM Step 1: Run ETF-specialized LLM analysis FIRST (institutional insights)
echo [%DATE% %TIME%] Running ETF-Specialized LLM Analysis...
echo ============================================================
python etf_llm_optimizer.py
echo.

REM Step 2: Run standard LLM portfolio analysis
echo [%DATE% %TIME%] Running Standard LLM Portfolio Analysis...
echo ============================================================
python azalyst.py --llm-analysis
echo.

REM Step 3: Continue with normal Azalyst operation
echo [%DATE% %TIME%] Starting Continuous Monitoring...
echo ============================================================
echo Azalyst is now running in the background.
echo - News scanning every 30 minutes
echo - LLM signal evaluation active
echo - Paper trading enabled
echo - Mark-to-market every 60 minutes
echo.
echo Logs: azalyst.log
echo Portfolio: azalyst_portfolio.json
echo.

REM Run Azalyst with LLM analysis
REM --llm-analysis runs portfolio analysis first, then continues normal operation
python azalyst.py

REM If the script exits, pause to show any error messages
if errorlevel 1 (
    echo.
    echo ERROR: Azalyst exited with an error.
    echo Check azalyst.log for details.
    pause
)
