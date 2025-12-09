# Dashboard Monitor Script
# Monitors port 80 and restarts the dashboard if it becomes unresponsive.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File dashboard-monitor.ps1
#
# To disable monitoring temporarily:
#   New-Item -ItemType File -Path "D:\AI\scripts\disable.flag" -Force
#
# To re-enable monitoring:
#   Remove-Item -Path "D:\AI\scripts\disable.flag" -Force

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DisableFlag = Join-Path $ScriptDir "disable.flag"
$DashboardDir = "D:\AI"
$DashboardPort = 80
$CheckInterval = 30  # seconds

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $Message"
}

Write-Log "Dashboard monitor started"
Write-Log "Monitoring port $DashboardPort every $CheckInterval seconds"
Write-Log "Disable flag location: $DisableFlag"

while ($true) {
    try {
        # Check if monitoring is disabled
        if (Test-Path $DisableFlag) {
            Write-Log "Monitoring disabled (disable.flag present), skipping check"
            Start-Sleep -Seconds $CheckInterval
            continue
        }

        # Test port connectivity
        $portTest = Test-NetConnection -ComputerName localhost -Port $DashboardPort -InformationLevel Quiet -WarningAction SilentlyContinue

        if ($portTest) {
            # Dashboard is responding, no action needed
        } else {
            Write-Log "Dashboard unresponsive on port $DashboardPort, initiating restart..."

            try {
                # Execute start_dashboard.bat
                $batchPath = Join-Path $DashboardDir "start_dashboard.bat"

                if (Test-Path $batchPath) {
                    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $batchPath -WorkingDirectory $DashboardDir -NoNewWindow
                    Write-Log "Restart initiated via start_dashboard.bat"
                } else {
                    Write-Log "ERROR: start_dashboard.bat not found at $batchPath"
                }
            } catch {
                Write-Log "ERROR: Failed to restart dashboard: $_"
            }
        }
    } catch {
        Write-Log "ERROR: Port check failed: $_"
    }

    Start-Sleep -Seconds $CheckInterval
}
