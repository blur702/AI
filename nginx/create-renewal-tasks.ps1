# Create Certbot renewal scheduled tasks
# Run as current user

$TaskName = "CertbotRenewal"
$TaskNamePM = "CertbotRenewal_PM"
$ScriptPath = "D:\AI\nginx\renew-certificates.bat"

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
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $TriggerAM -Settings $Settings -Description "Let's Encrypt certificate renewal (3:00 AM)"
Write-Host "Created task: $TaskName"

# Register PM task (as current user, no elevation)
Register-ScheduledTask -TaskName $TaskNamePM -Action $Action -Trigger $TriggerPM -Settings $Settings -Description "Let's Encrypt certificate renewal (3:00 PM)"
Write-Host "Created task: $TaskNamePM"

# Verify
Write-Host "`nVerifying tasks:"
Get-ScheduledTask -TaskName "CertbotRenewal*" | Format-Table TaskName, State -AutoSize
