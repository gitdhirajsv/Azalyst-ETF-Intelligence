@echo off
REM Azalyst ETF Intelligence - Auto Startup Script

echo ============================================================
echo   AZALYST ETF INTELLIGENCE - STARTING
echo   Aladdin Risk Engine + Paper Trading
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

REM Start Azalyst continuous monitoring
echo [%DATE% %TIME%] Starting Continuous Monitoring...
echo ============================================================
echo Azalyst is now running.
echo - News scanning every 30 minutes
echo - Signal evaluation active
echo - Paper trading enabled
echo - Mark-to-market every 60 minutes
echo.
echo Logs: azalyst.log
echo Portfolio: azalyst_portfolio.json
echo.

REM Run Azalyst
python azalyst.py

REM If the script exits, pause to show any error messages
if errorlevel 1 (
    echo.
    echo ERROR: Azalyst exited with an error.
    echo Check azalyst.log for details.
    pause
)
