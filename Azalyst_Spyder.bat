@echo off
setlocal enableextensions enabledelayedexpansion

title Azalyst ETF Intelligence - Spyder Launcher

:: Always run from the repo root
cd /d "%~dp0"

:: Use an isolated Spyder config directory (keeps this project independent)
set "SPYDER_PROFILE=%~dp0.spyder_azalyst_etf"

:: Resolve a Python executable for prepare_spyder_profile.py
set "PYTHON_EXE=python"
where %PYTHON_EXE% >nul 2>nul
if errorlevel 1 (
    set "PYTHON_EXE=py"
)
where %PYTHON_EXE% >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Python was not found on PATH.
    echo Install Python 3.9+ and ensure it is available as 'python' or 'py'.
    echo.
    pause
    exit /b 1
)

:: Locate Spyder (standalone install path, then PATH lookup)
if not defined SPYDER_EXE (
    set "SPYDER_EXE="

    if exist "C:\ProgramData\spyder-6\envs\spyder-runtime\Scripts\spyder.exe" (
        set "SPYDER_EXE=C:\ProgramData\spyder-6\envs\spyder-runtime\Scripts\spyder.exe"
    )

    if not defined SPYDER_EXE if exist "%USERPROFILE%\anaconda3\Scripts\spyder.exe" (
        set "SPYDER_EXE=%USERPROFILE%\anaconda3\Scripts\spyder.exe"
    )
    if not defined SPYDER_EXE if exist "%USERPROFILE%\miniconda3\Scripts\spyder.exe" (
        set "SPYDER_EXE=%USERPROFILE%\miniconda3\Scripts\spyder.exe"
    )

    if not defined SPYDER_EXE (
        for /d %%D in ("%USERPROFILE%\anaconda3\envs\*") do (
            if not defined SPYDER_EXE if exist "%%D\Scripts\spyder.exe" set "SPYDER_EXE=%%D\Scripts\spyder.exe"
        )
    )
    if not defined SPYDER_EXE (
        for /d %%D in ("%USERPROFILE%\miniconda3\envs\*") do (
            if not defined SPYDER_EXE if exist "%%D\Scripts\spyder.exe" set "SPYDER_EXE=%%D\Scripts\spyder.exe"
        )
    )

    if not defined SPYDER_EXE (
        for /f "delims=" %%I in ('where spyder 2^>nul') do (
            if not defined SPYDER_EXE set "SPYDER_EXE=%%I"
        )
    )
)

echo.
echo [1/3] Preparing Spyder profile...
%PYTHON_EXE% prepare_spyder_profile.py
if errorlevel 1 (
    echo [WARNING] Spyder profile preparation failed. Spyder may not auto-run the monitor.
)

echo.
echo [2/3] Launching Spyder live monitor...
if defined SPYDER_EXE (
    echo Spyder: %SPYDER_EXE%
    start "Spyder Monitor" /D "%~dp0" "%SPYDER_EXE%" --new-instance --conf-dir "%SPYDER_PROFILE%" -w "%~dp0" --window-title "Azalyst ETF Intelligence - Monitor" "%~dp0spyder_live_monitor.py"
) else (
    echo [ERROR] Spyder was not found.
    echo Install Spyder via Anaconda, or launch Spyder manually and open spyder_live_monitor.py.
    echo.
    set /p "CONTINUE_WITHOUT_SPYDER=Run the Azalyst engine anyway without Spyder? [Y/N]: "
    if /i not "!CONTINUE_WITHOUT_SPYDER!"=="Y" (
        echo.
        echo Exiting. Install Spyder first, then re-run this launcher.
        pause
        exit /b 0
    )
    echo Continuing without Spyder...
)

echo.
echo [3/3] Starting Azalyst engine...
if "%AZALYST_SPYDER_SKIP_ENGINE%"=="1" (
    echo Skipping engine start because AZALYST_SPYDER_SKIP_ENGINE=1.
) else (
    start "Azalyst Engine" /min cmd /c "call \"%~dp0START_AZALYST.bat\""
)

echo.
echo Launcher complete.
