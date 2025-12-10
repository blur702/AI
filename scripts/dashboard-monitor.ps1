<#
.SYNOPSIS
    Dashboard Monitor Script - Monitors port 80 and restarts the dashboard if it becomes unresponsive.
.DESCRIPTION
    This script continuously monitors the dashboard on port 80 and automatically restarts it if it becomes unresponsive.
    Monitoring can be temporarily disabled by creating a disable.flag file in the scripts directory.
.PARAMETER Port
    The port to monitor. Defaults to 80.
.PARAMETER CheckInterval
    The interval in seconds between checks. Defaults to 30.
.PARAMETER DashboardDir
    The directory containing start_dashboard.bat. Defaults to D:\AI.
.PARAMETER LogFile
    Path to the log file. If specified, logs will be written to this file in addition to console.
.EXAMPLE
    .\dashboard-monitor.ps1
    Run with default settings (port 80, 30s interval)
.EXAMPLE
    .\dashboard-monitor.ps1 -Port 8080 -CheckInterval 60
    Monitor port 8080 with 60 second intervals
.NOTES
    To disable monitoring temporarily:
      New-Item -ItemType File -Path "D:\AI\scripts\disable.flag" -Force
    To re-enable monitoring:
      Remove-Item -Path "D:\AI\scripts\disable.flag" -Force
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateRange(1, 65535)]
    [int]$Port = 80,

    [Parameter()]
    [ValidateRange(1, 3600)]
    [int]$CheckInterval = 30,

    [Parameter()]
    [ValidateScript({ Test-Path $_ -PathType Container })]
    [string]$DashboardDir = "D:\AI",

    [Parameter()]
    [string]$LogFile
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DisableFlag = Join-Path $ScriptDir "disable.flag"

function Write-Log {
    <#
    .SYNOPSIS
        Write a timestamped log message
    .PARAMETER Message
        The message to log
    .PARAMETER Level
        The log level (INFO, WARNING, ERROR)
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Message,

        [Parameter()]
        [ValidateSet('INFO', 'WARNING', 'ERROR')]
        [string]$Level = 'INFO'
    )

    try {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $logMessage = "[$timestamp] [$Level] $Message"
        Write-Host $logMessage

        if ($script:LogFile) {
            Add-Content -Path $script:LogFile -Value $logMessage -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-Error "Failed to write log: $_"
    }
}

function Test-PortConnectivity {
    <#
    .SYNOPSIS
        Test if a port is accessible
    .PARAMETER ComputerName
        The computer name to test
    .PARAMETER Port
        The port number to test
    #>
    param(
        [Parameter(Mandatory)]
        [string]$ComputerName,

        [Parameter(Mandatory)]
        [int]$Port
    )

    try {
        $result = Test-NetConnection -ComputerName $ComputerName -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction Stop
        return $result
    }
    catch {
        Write-Log "Port connectivity test failed: $_" -Level ERROR
        return $false
    }
}

function Start-DashboardRestart {
    <#
    .SYNOPSIS
        Restart the dashboard by executing start_dashboard.bat
    .PARAMETER DashboardDir
        The directory containing start_dashboard.bat
    #>
    param(
        [Parameter(Mandatory)]
        [string]$DashboardDir
    )

    try {
        $batchPath = Join-Path $DashboardDir "start_dashboard.bat"

        if (-not (Test-Path $batchPath)) {
            Write-Log "start_dashboard.bat not found at $batchPath" -Level ERROR
            return $false
        }

        Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$batchPath`"" -WorkingDirectory $DashboardDir -NoNewWindow -ErrorAction Stop
        Write-Log "Restart initiated via start_dashboard.bat" -Level INFO
        return $true
    }
    catch {
        Write-Log "Failed to restart dashboard: $_" -Level ERROR
        return $false
    }
}

# Main monitoring loop
try {
    Write-Log "Dashboard monitor started" -Level INFO
    Write-Log "Monitoring port $Port every $CheckInterval seconds" -Level INFO
    Write-Log "Disable flag location: $DisableFlag" -Level INFO
    Write-Log "Dashboard directory: $DashboardDir" -Level INFO

    while ($true) {
        try {
            # Check if monitoring is disabled
            if (Test-Path $DisableFlag) {
                Write-Log "Monitoring disabled (disable.flag present), skipping check" -Level WARNING
                Start-Sleep -Seconds $CheckInterval
                continue
            }

            # Test port connectivity
            $isResponsive = Test-PortConnectivity -ComputerName localhost -Port $Port

            if ($isResponsive) {
                # Dashboard is responding, no action needed
                Write-Verbose "Port $Port is responsive"
            }
            else {
                Write-Log "Dashboard unresponsive on port $Port, initiating restart..." -Level WARNING

                $restartSuccess = Start-DashboardRestart -DashboardDir $DashboardDir
                if (-not $restartSuccess) {
                    Write-Log "Restart attempt failed, will retry on next check" -Level ERROR
                }
            }
        }
        catch {
            Write-Log "Error during monitoring cycle: $_" -Level ERROR
            Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level ERROR
        }

        Start-Sleep -Seconds $CheckInterval
    }
}
catch {
    Write-Log "Fatal error in monitoring loop: $_" -Level ERROR
    Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level ERROR
    exit 1
}
finally {
    Write-Log "Monitor shutting down" -Level INFO
}
