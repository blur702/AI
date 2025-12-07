# Run this script as Administrator
# Right-click PowerShell -> Run as Administrator, then run this script

$rules = @(
    @{Name="AI A1111 WebUI"; Port=7861},
    @{Name="AI SD Forge"; Port=7862},
    @{Name="AI Fooocus"; Port=7865},
    @{Name="AI Weaviate"; Port=8080}
)

foreach ($rule in $rules) {
    $existing = netsh advfirewall firewall show rule name="$($rule.Name)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Rule '$($rule.Name)' already exists, skipping..." -ForegroundColor Yellow
    } else {
        netsh advfirewall firewall add rule name="$($rule.Name)" dir=in action=allow protocol=TCP localport=$($rule.Port)
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Added rule '$($rule.Name)' for port $($rule.Port)" -ForegroundColor Green
        } else {
            Write-Host "Failed to add rule '$($rule.Name)'" -ForegroundColor Red
        }
    }
}

Write-Host "`nDone! Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
