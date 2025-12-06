# Create a startup shortcut for the AI Tray application
$ScriptDir = $PSScriptRoot
$VbsPath = Join-Path $ScriptDir "start_tray.vbs"

# Validate that start_tray.vbs exists
if (-not (Test-Path $VbsPath)) {
    Write-Error "start_tray.vbs not found at: $VbsPath"
    exit 1
}

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $StartupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
    $ShortcutPath = "$StartupPath\AI Tray.lnk"

    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $VbsPath
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description = "AI Services System Tray Utility"
    $Shortcut.Save()

    Write-Host "Shortcut created at: $ShortcutPath"
}
catch {
    Write-Error "Failed to create shortcut: $_"
    exit 1
}
