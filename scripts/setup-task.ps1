<#
.SYNOPSIS
    Task Scheduler Setup Script - Creates a scheduled task to run the dashboard monitor on user logon.
.DESCRIPTION
    This script creates a Windows scheduled task that runs the dashboard monitor script automatically
    when the system starts or a user logs on. Requires Administrator privileges.
.PARAMETER TaskName
    The name of the scheduled task. Defaults to "AI Dashboard Monitor".
.PARAMETER RunAsUser
    The user account to run the task as. Defaults to SYSTEM for maximum reliability.
.PARAMETER TriggerType
    When to trigger the task. Valid values: OnLogon, OnStartup. Defaults to OnLogon.
.PARAMETER Force
    If specified, will replace existing task without prompting.
.EXAMPLE
    .\setup-task.ps1
    Create task with default settings (SYSTEM account, OnLogon trigger)
.EXAMPLE
    .\setup-task.ps1 -RunAsUser "DOMAIN\User" -TriggerType OnStartup -Force
    Create task for specific user with startup trigger, replace if exists
.NOTES
    Requires Administrator privileges to create scheduled tasks.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateNotNullOrEmpty()]
    [string]$TaskName = "AI Dashboard Monitor",

    [Parameter()]
    [ValidateNotNullOrEmpty()]
    [string]$RunAsUser = "SYSTEM",

    [Parameter()]
    [ValidateSet('OnLogon', 'OnStartup')]
    [string]$TriggerType = "OnLogon",

    [Parameter()]
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# Derive script path from this script's location for portability
$ScriptPath = Join-Path $PSScriptRoot "dashboard-monitor.ps1"

function Write-Header {
    <#
    .SYNOPSIS
        Write a formatted header message
    #>
    param([Parameter(Mandatory)][string]$Message)

    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host ""
}

function Test-AdministratorPrivileges {
    <#
    .SYNOPSIS
        Check if the current PowerShell session is running as Administrator
    .OUTPUTS
        Boolean - True if running as Administrator, False otherwise
    #>
    try {
        $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    }
    catch {
        Write-Error "Failed to check administrator privileges: $_"
        return $false
    }
}

function Test-TaskExists {
    <#
    .SYNOPSIS
        Check if a scheduled task exists
    .PARAMETER TaskName
        The name of the task to check
    .OUTPUTS
        Boolean - True if task exists, False otherwise
    #>
    param([Parameter(Mandatory)][string]$TaskName)

    try {
        $null = schtasks /query /tn $TaskName 2>$null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

Write-Header "AI Dashboard Monitor Task Setup"

# Validate that the monitor script exists before proceeding
if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: dashboard-monitor.ps1 not found at expected location:" -ForegroundColor Red
    Write-Host "       $ScriptPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please ensure dashboard-monitor.ps1 exists in the same directory as this script." -ForegroundColor Yellow
    exit 1
}

Write-Host "Monitor script validated: $ScriptPath" -ForegroundColor Green
Write-Host ""

# Check if running as Administrator
if (-not (Test-AdministratorPrivileges)) {
    Write-Host "ERROR: This script must be run as Administrator." -ForegroundColor Red
    Write-Host ""
    Write-Host "To run as Administrator:" -ForegroundColor Yellow
    Write-Host "  1. Right-click PowerShell" -ForegroundColor Yellow
    Write-Host "  2. Select 'Run as Administrator'" -ForegroundColor Yellow
    Write-Host "  3. Re-run this script" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# Check if task already exists
if (Test-TaskExists -TaskName $TaskName) {
    Write-Host "Task '$TaskName' already exists." -ForegroundColor Yellow

    if (-not $Force) {
        $response = Read-Host "Replace existing task? (Y/N)"
        if ($response -notmatch '^[Yy]') {
            Write-Host "Operation cancelled by user." -ForegroundColor Yellow
            exit 0
        }
    }

    Write-Host "Task will be replaced." -ForegroundColor Yellow
    Write-Host ""
}

# Build task command
$TaskCommand = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""

# Create the scheduled task
Write-Host "Creating scheduled task '$TaskName'..." -ForegroundColor Cyan
Write-Host "  Run as: $RunAsUser" -ForegroundColor Gray
Write-Host "  Trigger: $TriggerType" -ForegroundColor Gray
Write-Host "  Command: $TaskCommand" -ForegroundColor Gray
Write-Host ""

try {
    # Map trigger type to schtasks parameter
    $triggerParam = switch ($TriggerType) {
        'OnLogon' { 'onlogon' }
        'OnStartup' { 'onstart' }
        default { 'onlogon' }
    }

    $schtasksArgs = @(
        "/create"
        "/tn", "`"$TaskName`""
        "/tr", "`"$TaskCommand`""
        "/sc", $triggerParam
        "/ru", $RunAsUser
        "/rl", "highest"
        "/f"
    )

    $process = Start-Process -FilePath "schtasks" -ArgumentList $schtasksArgs -Wait -NoNewWindow -PassThru -ErrorAction Stop

    if ($process.ExitCode -eq 0) {
        Write-Host ""
        Write-Host "SUCCESS: Task '$TaskName' created successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Task Details:" -ForegroundColor Cyan
        Write-Host "-------------" -ForegroundColor Cyan

        $taskDetails = schtasks /query /tn $TaskName /fo list | Select-String -Pattern "TaskName|Status|Next Run|Last Run"
        $taskDetails | ForEach-Object { Write-Host $_ -ForegroundColor Gray }

        Write-Host ""
        Write-Host "The monitor will start automatically on next $TriggerType." -ForegroundColor Green
        Write-Host "To start it now, run: schtasks /run /tn `"$TaskName`"" -ForegroundColor Yellow
        Write-Host ""

        # Show management commands
        Write-Header "Task Management Commands"
        Write-Host "View task:   " -NoNewline -ForegroundColor Cyan
        Write-Host "schtasks /query /tn `"$TaskName`" /v /fo list" -ForegroundColor Gray
        Write-Host "Delete task: " -NoNewline -ForegroundColor Cyan
        Write-Host "schtasks /delete /tn `"$TaskName`" /f" -ForegroundColor Gray
        Write-Host "Run task:    " -NoNewline -ForegroundColor Cyan
        Write-Host "schtasks /run /tn `"$TaskName`"" -ForegroundColor Gray

        $DisableFlagPath = Join-Path $PSScriptRoot "disable.flag"
        Write-Host ""
        Write-Host "Disable/Enable Monitoring:" -ForegroundColor Cyan
        Write-Host "--------------------------" -ForegroundColor Cyan
        Write-Host "Disable: " -NoNewline -ForegroundColor Cyan
        Write-Host "New-Item -ItemType File -Path `"$DisableFlagPath`" -Force" -ForegroundColor Gray
        Write-Host "Enable:  " -NoNewline -ForegroundColor Cyan
        Write-Host "Remove-Item -Path `"$DisableFlagPath`" -Force" -ForegroundColor Gray
        Write-Host "Status:  " -NoNewline -ForegroundColor Cyan
        Write-Host "Test-Path `"$DisableFlagPath`"" -ForegroundColor Gray
        Write-Host ""

        exit 0
    }
    else {
        Write-Host ""
        Write-Host "ERROR: Failed to create task. Exit code: $($process.ExitCode)" -ForegroundColor Red
        Write-Host "Make sure you're running this script as Administrator." -ForegroundColor Yellow
        exit 1
    }
}
catch {
    Write-Host ""
    Write-Host "ERROR: Failed to create scheduled task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Stack trace:" -ForegroundColor Yellow
    Write-Host $_.ScriptStackTrace -ForegroundColor Gray
    exit 1
}
