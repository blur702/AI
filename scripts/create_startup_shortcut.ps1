$startupPath = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupPath "CongressionalScraperSupervisor.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "D:\AI\start_congressional_parallel.bat"
$shortcut.Arguments = "start"
$shortcut.WorkingDirectory = "D:\AI"
$shortcut.Description = "Start Congressional Scraper Supervisor"
$shortcut.Save()

Write-Host "Startup shortcut created at: $shortcutPath" -ForegroundColor Green
Write-Host "The scraper supervisor will start when you log in." -ForegroundColor Cyan
