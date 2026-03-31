@echo off
REM Azalyst - Easy Auto-Startup Installer
REM This creates a shortcut in your Windows Startup folder

echo ============================================================
echo   AZALYST - Auto-Startup Installer
echo ============================================================
echo.

REM Get the current directory
set AZALYST_PATH=%~dp0

REM Remove trailing backslash
set AZALYST_PATH=%AZALYST_PATH:~0,-1%

echo Azalyst Path: %AZALYST_PATH%
echo.

REM Get Startup folder path
set STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

echo Startup Folder: %STARTUP_FOLDER%
echo.

REM Create shortcut
echo Creating startup shortcut...
powershell -Command "$WScriptShell = New-Object -ComObject WScript.Shell; $Shortcut = $WScriptShell.CreateShortcut('%STARTUP_FOLDER%\Azalyst ETF Intelligence.lnk'); $Shortcut.TargetPath = '%AZALYST_PATH%\start_azalyst.bat'; $Shortcut.WorkingDirectory = '%AZALYST_PATH%'; $Shortcut.Description = 'Azalyst ETF Intelligence - Auto-start with ETF-specialized LLM analysis'; $Shortcut.Save()"

if errorlevel 1 (
    echo ERROR: Failed to create shortcut
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   SUCCESS! Auto-startup configured.
echo ============================================================
echo.
echo Azalyst will now start automatically when you log in to Windows.
echo.
echo What will happen EVERY DAY when you log in:
echo   1. You log in to Windows
echo   2. Azalyst starts automatically
echo   3. ETF-Specialized LLM Analysis runs (BlackRock/Vanguard methodology)
echo      - ETF structure optimization
echo      - Securities lending analysis
echo      - Tax efficiency recommendations
echo      - Tracking error assessment
echo   4. Standard LLM Portfolio Analysis runs
echo      - Win rate analysis
echo      - Risk management recommendations
echo   5. Continuous monitoring starts
echo      - News scanning every 30 minutes
echo      - Signal evaluation with LLM
echo      - Paper trading active
echo      - Mark-to-market every 60 minutes
echo   6. All results logged to azalyst.log
echo.
echo To disable auto-start:
echo   1. Press Win+R
echo   2. Type: shell:startup
echo   3. Delete "Azalyst ETF Intelligence.lnk"
echo.
echo To run manually anytime:
echo   - Double-click: start_azalyst.bat
echo   - Or: python etf_llm_optimizer.py (ETF analysis only)
echo.
echo Logs location:
echo   - %AZALYST_PATH%\azalyst.log
echo   - %AZALYST_PATH%\llm_feedback_log.json
echo   - %AZALYST_PATH%\etf_analysis.log
echo.
pause
