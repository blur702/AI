# Create Windows Startup Shortcut for AI Dashboard
# Optional parameter: specify custom target path
param(
    [string]$TargetScript = ""
)

# Compute script directory and resolve target path
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($TargetScript)) {
    $TargetScript = Join-Path $ScriptDir "dashboard_startup.vbs"
}

# Validate that target exists
if (-not (Test-Path $TargetScript)) {
    Write-Host "ERROR: Target script not found: $TargetScript" -ForegroundColor Red
    Write-Host "Please ensure dashboard_startup.vbs exists or specify a valid path." -ForegroundColor Red
    exit 1
}

# Resolve to absolute path
$TargetScript = Resolve-Path $TargetScript

$WshShell = New-Object -ComObject WScript.Shell
$StartupPath = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupPath "AI Dashboard.lnk"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetScript
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = "AI Services Dashboard - Auto-start on login"
$Shortcut.Save()

Write-Host "Startup shortcut created at: $ShortcutPath" -ForegroundColor Green
Write-Host "Target: $TargetScript" -ForegroundColor Cyan
