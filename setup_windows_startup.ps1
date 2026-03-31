# Azalyst ETF Intelligence - Auto-Startup Configuration
# This PowerShell script sets up Windows Task Scheduler to run Azalyst daily

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AZALYST - Windows Auto-Startup Configuration" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Get the current directory (Azalyst folder)
$azalystPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$batchFile = Join-Path $azalystPath "start_azalyst.bat"
$pythonScript = Join-Path $azalystPath "azalyst.py"

Write-Host "Azalyst Path: $azalystPath" -ForegroundColor Yellow
Write-Host "Batch File: $batchFile" -ForegroundColor Yellow
Write-Host ""

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")

if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please right-click on this file and select 'Run as Administrator'" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

Write-Host "Running as Administrator: YES" -ForegroundColor Green
Write-Host ""

# Define task name
$taskName = "Azalyst ETF Intelligence"
$taskDescription = "Automatically starts Azalyst ETF Intelligence with LLM analysis on user login. Runs portfolio analysis and monitors global news for trading signals."

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "Task '$taskName' already exists." -ForegroundColor Yellow
    $overwrite = Read-Host "Do you want to overwrite it? (Y/N)"
    if ($overwrite -ne 'Y' -and $overwrite -ne 'y') {
        Write-Host "Configuration cancelled." -ForegroundColor Yellow
        pause
        exit 0
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Existing task removed." -ForegroundColor Green
}

Write-Host ""
Write-Host "Creating scheduled task..." -ForegroundColor Cyan

# Create the scheduled task action
$action = New-ScheduledTaskAction -Execute $batchFile -WorkingDirectory $azalystPath

# Create triggers (run on user login)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 24)

# Create the principal (run with highest privileges)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Description $taskDescription `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -ErrorAction Stop
    
    Write-Host "✓ Task created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Details:" -ForegroundColor Cyan
    Write-Host "  Name: $taskName"
    Write-Host "  Trigger: On user login ($env:USERNAME)"
    Write-Host "  Action: Run $batchFile"
    Write-Host "  Working Directory: $azalystPath"
    Write-Host "  Settings: Restart on failure (3 attempts, 1 min interval)"
    Write-Host ""
    
} catch {
    Write-Host "ERROR: Failed to create task" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    pause
    exit 1
}

# Verify the task
Write-Host "Verifying task..." -ForegroundColor Cyan
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($task) {
    Write-Host "✓ Task verified successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  CONFIGURATION COMPLETE!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Azalyst will now start automatically when you log in." -ForegroundColor White
    Write-Host ""
    Write-Host "To manage the task:" -ForegroundColor Yellow
    Write-Host "  1. Open Task Scheduler (taskschd.msc)"
    Write-Host "  2. Find 'Azalyst ETF Intelligence' in the task list"
    Write-Host "  3. Right-click to Run, Disable, or Properties"
    Write-Host ""
    Write-Host "To test now:" -ForegroundColor Yellow
    Write-Host "  - Double-click: start_azalyst.bat"
    Write-Host ""
    Write-Host "Logs will be saved to:" -ForegroundColor Yellow
    Write-Host "  - $azalystPath\azalyst.log"
    Write-Host "  - $azalystPath\llm_feedback_log.json"
    Write-Host ""
} else {
    Write-Host "ERROR: Task verification failed" -ForegroundColor Red
}

pause
