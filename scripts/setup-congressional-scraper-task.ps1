<#
.SYNOPSIS
    Sets up Windows Task Scheduler task for Congressional Scraper Supervisor.

.DESCRIPTION
    Creates a scheduled task that runs health checks on the parallel congressional
    scraper workers every N minutes. The task monitors worker processes and
    automatically restarts any that have crashed or become unresponsive.

.PARAMETER IntervalMinutes
    How often to run health checks (default: 5 minutes)

.PARAMETER TaskName
    Name of the scheduled task (default: CongressionalScraperSupervisor)

.PARAMETER Force
    Overwrite existing task without prompting

.PARAMETER Uninstall
    Remove the scheduled task

.EXAMPLE
    .\setup-congressional-scraper-task.ps1

.EXAMPLE
    .\setup-congressional-scraper-task.ps1 -IntervalMinutes 10

.EXAMPLE
    .\setup-congressional-scraper-task.ps1 -Uninstall
#>

param(
    [int]$IntervalMinutes = 5,
    [string]$TaskName = "CongressionalScraperSupervisor",
    [switch]$Force,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ScriptDir = "D:\AI"
$PythonExe = "python"

# Check for admin rights
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Warning "This script should be run as Administrator for best results."
    Write-Warning "The task may not run properly without elevated privileges."
}

if ($Uninstall) {
    Write-Host "Uninstalling task '$TaskName'..." -ForegroundColor Yellow

    try {
        schtasks /delete /tn $TaskName /f 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Task '$TaskName' uninstalled successfully." -ForegroundColor Green
        } else {
            Write-Host "Task '$TaskName' not found or already removed." -ForegroundColor Yellow
        }
    } catch {
        Write-Error "Failed to uninstall task: $_"
        exit 1
    }
    exit 0
}

# Build the command
$TaskCommand = "cd /d `"$ScriptDir`" && $PythonExe -m api_gateway.services.congressional_parallel_supervisor check"

Write-Host "Setting up Congressional Scraper Supervisor Task" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Task Name: $TaskName"
Write-Host "Interval: Every $IntervalMinutes minutes"
Write-Host "Command: $TaskCommand"
Write-Host ""

# Check if task already exists
$existingTask = schtasks /query /tn $TaskName 2>$null
if ($LASTEXITCODE -eq 0 -and -not $Force) {
    Write-Warning "Task '$TaskName' already exists. Use -Force to overwrite."
    exit 1
}

# Build schtasks arguments
$schtasksArgs = @(
    "/create"
    "/tn", $TaskName
    "/tr", "cmd /c `"$TaskCommand`""
    "/sc", "MINUTE"
    "/mo", $IntervalMinutes
    "/ru", "SYSTEM"
    "/rl", "HIGHEST"
)

if ($Force) {
    $schtasksArgs += "/f"
}

Write-Host "Creating scheduled task..." -ForegroundColor Yellow

try {
    $result = & schtasks @schtasksArgs 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Task '$TaskName' created successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "The supervisor will check worker health every $IntervalMinutes minutes."
        Write-Host ""
        Write-Host "Management commands:" -ForegroundColor Cyan
        Write-Host "  View task:     schtasks /query /tn $TaskName /v"
        Write-Host "  Run now:       schtasks /run /tn $TaskName"
        Write-Host "  Delete task:   schtasks /delete /tn $TaskName /f"
        Write-Host ""
        Write-Host "Supervisor commands:" -ForegroundColor Cyan
        Write-Host "  Start workers: python -m api_gateway.services.congressional_parallel_supervisor start"
        Write-Host "  Check health:  python -m api_gateway.services.congressional_parallel_supervisor check"
        Write-Host "  View status:   python -m api_gateway.services.congressional_parallel_supervisor status"
        Write-Host "  Stop workers:  python -m api_gateway.services.congressional_parallel_supervisor stop"
    } else {
        Write-Error "Failed to create task: $result"
        exit 1
    }
} catch {
    Write-Error "Failed to create task: $_"
    exit 1
}
