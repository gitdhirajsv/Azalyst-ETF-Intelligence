@echo off
setlocal enableextensions enabledelayedexpansion

title Azalyst ETF Intelligence - Launcher

:: Run from repo root
cd /d "%~dp0"

echo [1/3] Starting Azalyst engine (separate console)...
start "Azalyst Engine" "%~dp0START_AZALYST.bat"

echo [2/3] Detecting Spyder...
if not defined SPYDER_EXE (
    if exist "C:\ProgramData\spyder-6\envs\spyder-runtime\Scripts\spyder.exe" set "SPYDER_EXE=C:\ProgramData\spyder-6\envs\spyder-runtime\Scripts\spyder.exe"
    if not defined SPYDER_EXE if exist "%USERPROFILE%\anaconda3\Scripts\spyder.exe" set "SPYDER_EXE=%USERPROFILE%\anaconda3\Scripts\spyder.exe"
    if not defined SPYDER_EXE if exist "%USERPROFILE%\miniconda3\Scripts\spyder.exe" set "SPYDER_EXE=%USERPROFILE%\miniconda3\Scripts\spyder.exe"
    for /f "delims=" %%I in ('where spyder 2^>nul') do if not defined SPYDER_EXE set "SPYDER_EXE=%%I"
)

echo [3/3] Launching Spyder monitor...
if defined SPYDER_EXE (
    echo Spyder: %SPYDER_EXE%
    start "Spyder Monitor" /D "%~dp0" "%SPYDER_EXE%" --new-instance --conf-dir "%~dp0.spyder_azalyst_etf" -w "%~dp0" --window-title "Azalyst ETF Intelligence - Monitor" "%~dp0spyder_live_monitor.py"
) else (
    echo [WARNING] Spyder not found. Engine is running; open Spyder manually and run spyder_live_monitor.py if needed.
)

echo.
echo Launcher complete. Engine console stays running even if you close Spyder.
echo Press any key to close this window...
pause >nul

endlocal
