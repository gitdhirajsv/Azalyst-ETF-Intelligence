@echo off
setlocal enableextensions enabledelayedexpansion

title Azalyst ETF Intelligence - Launcher
cd /d "%~dp0"

set "SPYDER_PROFILE=%~dp0.spyder_azalyst_etf"

echo [1/3] Checking dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo [WARNING] Dependency install reported issues. You can rerun: pip install -r requirements.txt
)

echo.
echo [2/3] Starting engine in separate console...
start "Azalyst Engine" /D "%~dp0" cmd /k "python -u azalyst.py"
echo Engine is running; it will stay alive even if you close Spyder.

echo.
echo [3/3] Launching monitor (optional)...
start "Azalyst Monitor" /D "%~dp0" cmd /k "set AZALYST_MONITOR_BACKEND=TkAgg && python -u spyder_live_monitor.py"

echo.
echo Done. Press any key to close this window...
pause >nul

endlocal
