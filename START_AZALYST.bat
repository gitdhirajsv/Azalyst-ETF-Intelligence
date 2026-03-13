@echo off
setlocal enableextensions enabledelayedexpansion

title AZALYST ETF INTELLIGENCE - ENGINE

echo ------------------------------------------------------------
echo   AZALYST ETF INTELLIGENCE  |  Macro Fund Edition
echo   Engine launcher (keeps running even if Spyder is closed)
echo ------------------------------------------------------------
echo.

:: Ensure we run from repo root
cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.9+ not found on PATH. Install Python and retry.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo [1/3] Checking dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo [WARNING] Dependency install reported issues. You can rerun:
    echo          pip install -r requirements.txt
)

echo [2/3] Dependencies ready.
echo [3/3] Starting AZALYST engine...
echo.

:: Optional environment overrides
:: set WEBHOOK=https://discord.com/api/webhooks/YOUR_WEBHOOK
:: set AZALYST_THRESHOLD=62
:: set INTERVAL=30

python azalyst.py

if errorlevel 1 (
    echo.
    echo [ERROR] AZALYST crashed. Check azalyst.log for details.
    echo Press any key to exit...
    pause >nul
)

endlocal
