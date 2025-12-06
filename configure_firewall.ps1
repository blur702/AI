# AI Services Firewall Configuration
# Run as Administrator

$rules = @(
    @{Name="AI Dashboard (HTTP)"; Port=80; Description="Dashboard + API"},
    @{Name="AI API Gateway"; Port=1301; Description="FastAPI Gateway"},
    @{Name="AI Open WebUI"; Port=3000; Description="LLM Chat Interface"},
    @{Name="AI N8N Workflows"; Port=5678; Description="Workflow Automation"},
    @{Name="AI AllTalk TTS"; Port=7851; Description="Text-to-Speech"},
    @{Name="AI Wan2GP Video"; Port=7860; Description="Video Generation"},
    @{Name="AI YuE Music"; Port=7870; Description="Music Generation"},
    @{Name="AI DiffRhythm"; Port=7871; Description="Rhythm Music"},
    @{Name="AI MusicGen"; Port=7872; Description="Meta AudioCraft"},
    @{Name="AI Stable Audio"; Port=7873; Description="Audio Generation"},
    @{Name="AI ComfyUI"; Port=8188; Description="Image Generation"},
    @{Name="AI Ollama API"; Port=11434; Description="Local LLM API"}
)

Write-Host "Configuring Windows Firewall for AI Services..." -ForegroundColor Cyan
Write-Host ""

foreach ($rule in $rules) {
    $existingRule = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue

    if ($existingRule) {
        Write-Host "[EXISTS] $($rule.Name) (Port $($rule.Port))" -ForegroundColor Yellow
    } else {
        try {
            New-NetFirewallRule -DisplayName $rule.Name `
                -Direction Inbound `
                -Protocol TCP `
                -LocalPort $rule.Port `
                -Action Allow `
                -Description $rule.Description `
                -Profile Domain,Private `
                -ErrorAction Stop | Out-Null
            Write-Host "[ADDED]  $($rule.Name) (Port $($rule.Port))" -ForegroundColor Green
        } catch {
            Write-Host "[FAILED] $($rule.Name) (Port $($rule.Port)) - $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "Firewall configuration complete!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Ports now open:" -ForegroundColor White
foreach ($rule in $rules) {
    Write-Host "  $($rule.Port.ToString().PadRight(6)) - $($rule.Description)"
}
