# Create Certbot renewal scheduled tasks
# Run as current user

$TaskName = "CertbotRenewal"
$TaskNamePM = "CertbotRenewal_PM"
# Derive script path relative to this script's location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $ScriptDir "renew-certificates.bat"

# Remove existing tasks if they exist
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskNamePM -Confirm:$false -ErrorAction SilentlyContinue

# Create action
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$ScriptPath`""

# Create triggers - 3:00 AM and 3:00 PM daily
$TriggerAM = New-ScheduledTaskTrigger -Daily -At 3:00AM
$TriggerPM = New-ScheduledTaskTrigger -Daily -At 3:00PM

# Create settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register AM task (as current user, no elevation)
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $TriggerAM -Settings $Settings -Description "Let's Encrypt certificate renewal (3:00 AM)" -ErrorAction Stop | Out-Null
    Write-Host "Created task: $TaskName"
} catch {
    Write-Host "Failed to create task ${TaskName}: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Register PM task (as current user, no elevation)
try {
    Register-ScheduledTask -TaskName $TaskNamePM -Action $Action -Trigger $TriggerPM -Settings $Settings -Description "Let's Encrypt certificate renewal (3:00 PM)" -ErrorAction Stop | Out-Null
    Write-Host "Created task: $TaskNamePM"
} catch {
    Write-Host "Failed to create task ${TaskNamePM}: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Verify
Write-Host "`nVerifying tasks:"
Get-ScheduledTask -TaskName "CertbotRenewal*" | Format-Table TaskName, State -AutoSize
