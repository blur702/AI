# N8N Startup Script with Owner Pre-configured
# Skip the owner setup screen by pre-configuring credentials

$env:N8N_ENCRYPTION_KEY = "your-32-char-encryption-key-here"

# Pre-configure the owner account (skips setup wizard)
$env:N8N_AUTH_EMAIL = "admin@local.host"
$env:N8N_AUTH_PASSWORD = "admin123"

# Disable telemetry for local dev
$env:N8N_DIAGNOSTICS_ENABLED = "false"

Set-Location "D:\AI"
Write-Host "Starting N8N..."
Write-Host "Access: http://localhost:5678"
Write-Host "Login: admin@local.host / admin123"
Write-Host ""

n8n start
