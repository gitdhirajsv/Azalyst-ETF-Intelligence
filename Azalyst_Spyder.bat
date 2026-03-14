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
echo [3/3] Launching dashboard window...
set "AZALYST_MONITOR_INLINE=0"
set "AZALYST_MONITOR_BACKEND=TkAgg"
set "PYTHONW_EXE=pythonw"
where %PYTHONW_EXE% >nul 2>nul
if errorlevel 1 (
    set "PYTHONW_EXE=python"
)
start "Azalyst Monitor" /D "%~dp0" "%PYTHONW_EXE%" spyder_live_monitor.py

echo.
echo Opening Spyder (optional)...
python prepare_spyder_profile.py >nul 2>&1
set "AZALYST_MONITOR_INLINE=0"
set "AZALYST_MONITOR_BACKEND=TkAgg"

if not defined SPYDER_EXE (
    if exist "C:\ProgramData\spyder-6\envs\spyder-runtime\Scripts\spyder.exe" set "SPYDER_EXE=C:\ProgramData\spyder-6\envs\spyder-runtime\Scripts\spyder.exe"
    if not defined SPYDER_EXE if exist "%USERPROFILE%\anaconda3\Scripts\spyder.exe" set "SPYDER_EXE=%USERPROFILE%\anaconda3\Scripts\spyder.exe"
    if not defined SPYDER_EXE if exist "%USERPROFILE%\miniconda3\Scripts\spyder.exe" set "SPYDER_EXE=%USERPROFILE%\miniconda3\Scripts\spyder.exe"
    for /f "delims=" %%I in ('where spyder 2^>nul') do if not defined SPYDER_EXE set "SPYDER_EXE=%%I"
)

if defined SPYDER_EXE (
    start "Spyder Monitor" /D "%~dp0" "%SPYDER_EXE%" --new-instance --conf-dir "%~dp0.spyder_azalyst_etf" -w "%~dp0" --window-title "Azalyst ETF Intelligence - Monitor" "%~dp0spyder_live_monitor.py"
) else (
    echo [INFO] Spyder not found; engine continues headless. Open Spyder manually and run spyder_live_monitor.py if needed.
)

echo.
echo Done. Press any key to close this window...
pause >nul

endlocal
