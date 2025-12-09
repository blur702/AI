# PowerShell Script to Configure Windows Firewall for Nginx Reverse Proxy
# Run as Administrator: powershell -ExecutionPolicy Bypass -File configure-firewall.ps1

#Requires -RunAsAdministrator

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Configuring Windows Firewall for Nginx" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Define rule names prefix
$rulePrefix = "AI_Nginx"

# Define ports to expose externally (via nginx)
$externalPorts = @(
    @{ Port = 443; Name = "HTTPS"; Description = "Nginx HTTPS reverse proxy" },
    @{ Port = 80;  Name = "HTTP";  Description = "Nginx HTTP (redirect to HTTPS)" }
)

# Define service ports to block external access (nginx handles these internally)
$internalPorts = @(
    @{ Port = 3000;  Name = "OpenWebUI" },
    @{ Port = 5678;  Name = "N8N" },
    @{ Port = 7851;  Name = "AllTalk" },
    @{ Port = 7860;  Name = "Wan2GP" },
    @{ Port = 7861;  Name = "A1111" },
    @{ Port = 7862;  Name = "SDForge" },
    @{ Port = 7865;  Name = "Fooocus" },
    @{ Port = 7870;  Name = "YuE" },
    @{ Port = 7871;  Name = "DiffRhythm" },
    @{ Port = 7872;  Name = "MusicGen" },
    @{ Port = 7873;  Name = "StableAudio" },
    @{ Port = 8080;  Name = "Weaviate" },
    @{ Port = 8081;  Name = "WeaviateConsole" },
    @{ Port = 8188;  Name = "ComfyUI" },
    @{ Port = 11434; Name = "Ollama" }
)

# Remove existing rules with our prefix
Write-Host "Removing existing firewall rules..." -ForegroundColor Yellow
Get-NetFirewallRule -DisplayName "$rulePrefix*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

Write-Host ""
Write-Host "Creating firewall rules..." -ForegroundColor Green
Write-Host ""

# Allow external access to nginx ports (443 and 80)
foreach ($port in $externalPorts) {
    $ruleName = "${rulePrefix}_Allow_$($port.Name)_$($port.Port)"
    Write-Host "  Allowing inbound TCP $($port.Port) ($($port.Name))..." -ForegroundColor White

    New-NetFirewallRule -DisplayName $ruleName `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $port.Port `
        -Action Allow `
        -Profile Any `
        -Description $port.Description `
        -ErrorAction Stop | Out-Null
}

Write-Host ""

# Configure service ports: allow localhost, block all other remote addresses
# Windows Firewall processes rules by specificity, so we create both allow and block rules
foreach ($port in $internalPorts) {
    $allowRuleName = "${rulePrefix}_Allow_Localhost_$($port.Name)_$($port.Port)"
    $blockRuleName = "${rulePrefix}_Block_External_$($port.Name)_$($port.Port)"

    Write-Host "  Configuring TCP $($port.Port) ($($port.Name))..." -ForegroundColor White

    # First: Allow localhost access (127.0.0.1 and ::1)
    Write-Host "    - Allowing localhost access..." -ForegroundColor Gray
    New-NetFirewallRule -DisplayName $allowRuleName `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $port.Port `
        -RemoteAddress "127.0.0.1","::1" `
        -Action Allow `
        -Profile Any `
        -Description "Allow localhost access to $($port.Name) for nginx proxy" `
        -ErrorAction Stop | Out-Null

    # Second: Block all other remote addresses
    Write-Host "    - Blocking external access..." -ForegroundColor Gray
    New-NetFirewallRule -DisplayName $blockRuleName `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $port.Port `
        -Action Block `
        -Profile Public,Private `
        -Description "Block external access to $($port.Name) - use nginx proxy instead" `
        -ErrorAction Stop | Out-Null
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Firewall Configuration Complete" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "External Access Allowed:" -ForegroundColor Green
foreach ($port in $externalPorts) {
    Write-Host "  - Port $($port.Port) ($($port.Name))" -ForegroundColor White
}
Write-Host ""
Write-Host "External Access Blocked (localhost only):" -ForegroundColor Yellow
foreach ($port in $internalPorts) {
    Write-Host "  - Port $($port.Port) ($($port.Name))" -ForegroundColor White
}
Write-Host ""
Write-Host "To view rules: Get-NetFirewallRule -DisplayName '$rulePrefix*'" -ForegroundColor Cyan
Write-Host "To remove rules: Get-NetFirewallRule -DisplayName '$rulePrefix*' | Remove-NetFirewallRule" -ForegroundColor Cyan
Write-Host ""

# Summary verification
Write-Host "Verifying rules..." -ForegroundColor Yellow
$rules = Get-NetFirewallRule -DisplayName "$rulePrefix*" | Select-Object DisplayName, Enabled, Direction, Action
$rules | Format-Table -AutoSize

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
