# Task Scheduler Setup Script
# Creates a scheduled task to run the dashboard monitor on user logon.
#
# Usage (run as Administrator):
#   powershell -ExecutionPolicy Bypass -File setup-task.ps1
#
# Task Management Commands:
#   View task:   schtasks /query /tn "AI Dashboard Monitor" /v /fo list
#   Delete task: schtasks /delete /tn "AI Dashboard Monitor" /f
#   Run task:    schtasks /run /tn "AI Dashboard Monitor"

$TaskName = "AI Dashboard Monitor"
# Derive script path from this script's location for portability
$ScriptPath = Join-Path $PSScriptRoot "dashboard-monitor.ps1"

Write-Host "=================================="
Write-Host "AI Dashboard Monitor Task Setup"
Write-Host "=================================="
Write-Host ""

# Validate that the monitor script exists before proceeding
if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: dashboard-monitor.ps1 not found at expected location:"
    Write-Host "       $ScriptPath"
    Write-Host ""
    Write-Host "Please ensure dashboard-monitor.ps1 exists in the same directory as this script."
    exit 1
}

Write-Host "Monitor script validated: $ScriptPath"
Write-Host ""

$TaskCommand = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "WARNING: This script should be run as Administrator for best results."
    Write-Host "The task may not have full privileges without admin rights."
    Write-Host ""
}

# Check if task already exists
$existingTask = schtasks /query /tn $TaskName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Task '$TaskName' already exists. It will be replaced."
    Write-Host ""
}

# Create the scheduled task
Write-Host "Creating scheduled task '$TaskName'..."
Write-Host "Command: $TaskCommand"
Write-Host ""

$schtasksArgs = @(
    "/create"
    "/tn", "`"$TaskName`""
    "/tr", "`"$TaskCommand`""
    "/sc", "onlogon"
    "/ru", "SYSTEM"
    "/rl", "highest"
    "/f"
)

$process = Start-Process -FilePath "schtasks" -ArgumentList $schtasksArgs -Wait -NoNewWindow -PassThru

if ($process.ExitCode -eq 0) {
    Write-Host ""
    Write-Host "SUCCESS: Task '$TaskName' created successfully!"
    Write-Host ""
    Write-Host "Task Details:"
    Write-Host "-------------"
    schtasks /query /tn $TaskName /fo list | Select-String -Pattern "TaskName|Status|Next Run|Last Run"
    Write-Host ""
    Write-Host "The monitor will start automatically on next logon."
    Write-Host "To start it now, run: schtasks /run /tn `"$TaskName`""
} else {
    Write-Host ""
    Write-Host "ERROR: Failed to create task. Exit code: $($process.ExitCode)"
    Write-Host "Make sure you're running this script as Administrator."
}

Write-Host ""
Write-Host "=================================="
Write-Host "Task Management Commands:"
Write-Host "=================================="
Write-Host "View task:   schtasks /query /tn `"$TaskName`" /v /fo list"
Write-Host "Delete task: schtasks /delete /tn `"$TaskName`" /f"
Write-Host "Run task:    schtasks /run /tn `"$TaskName`""
$DisableFlagPath = Join-Path $PSScriptRoot "disable.flag"
Write-Host ""
Write-Host "Disable/Enable Monitoring:"
Write-Host "--------------------------"
Write-Host "Disable: New-Item -ItemType File -Path `"$DisableFlagPath`" -Force"
Write-Host "Enable:  Remove-Item -Path `"$DisableFlagPath`" -Force"
Write-Host "Status:  Test-Path `"$DisableFlagPath`""
Write-Host ""
