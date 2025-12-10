# Ollama Model Keep-Alive Script
# Pings the model periodically to prevent unloading
# Run in background: Start-Job -FilePath D:\AI\scripts\ollama-keepalive.ps1

param(
    [string]$Model = "qwen3-coder:30b",
    [int]$IntervalMinutes = 4,
    [string]$KeepAlive = "24h"
)

$OllamaUrl = "http://localhost:11434/api/generate"

Write-Host "Ollama Keep-Alive started for model: $Model"
Write-Host "Ping interval: $IntervalMinutes minutes"
Write-Host "Keep-alive duration: $KeepAlive"
Write-Host "Press Ctrl+C to stop"
Write-Host ""

while ($true) {
    try {
        $body = @{
            model = $Model
            prompt = ""
            keep_alive = $KeepAlive
        } | ConvertTo-Json

        $response = Invoke-RestMethod -Uri $OllamaUrl -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Host "[$timestamp] Pinged $Model - keep_alive set to $KeepAlive"
    }
    catch {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Host "[$timestamp] Error pinging model: $_" -ForegroundColor Yellow
    }

    Start-Sleep -Seconds ($IntervalMinutes * 60)
}
