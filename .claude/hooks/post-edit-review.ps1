# Post-Edit Review Hook
# Runs after Edit/Write operations to lint code and optionally run CodeRabbit
# Also stores errors in PostgreSQL for tracking and resolution
#
# Environment variables provided by Claude Code:
#   $env:CLAUDE_FILE_PATH - The file that was edited
#   $env:CLAUDE_PROJECT_DIR - The project root directory

param(
    [switch]$SkipCodeRabbit,  # Skip CodeRabbit review (for quick iterations)
    [switch]$SkipErrorDb      # Skip storing errors in database
)

$filePath = $env:CLAUDE_FILE_PATH
$projectDir = $env:CLAUDE_PROJECT_DIR

# Use api_gateway venv for error tracking
$pythonExe = "D:\AI\api_gateway\venv\Scripts\python.exe"

if (-not $filePath) {
    Write-Host "No file path provided"
    exit 0
}

$extension = [System.IO.Path]::GetExtension($filePath).ToLower()
$issues = @()
$errorDetails = @()  # Collect structured error info for DB

# Determine service name from path
function Get-ServiceName {
    param([string]$path)

    if ($path -match "dashboard[/\\]frontend") { return "dashboard/frontend" }
    if ($path -match "dashboard[/\\]backend") { return "dashboard/backend" }
    if ($path -match "api_gateway") { return "api_gateway" }
    if ($path -match "tests") { return "tests" }
    if ($path -match "alltalk") { return "alltalk_tts" }
    if ($path -match "audiocraft") { return "audiocraft" }
    if ($path -match "ComfyUI") { return "comfyui" }
    if ($path -match "DiffRhythm") { return "diffrhythm" }
    if ($path -match "MusicGPT") { return "musicgpt" }
    if ($path -match "stable-audio") { return "stable_audio" }
    if ($path -match "Wan2GP") { return "wan2gp" }
    if ($path -match "YuE") { return "yue" }
    return "core"
}

$serviceName = Get-ServiceName -path $filePath

# ============================================
# LINTING
# ============================================

# Python files - run ruff
if ($extension -eq ".py") {
    Write-Host "Running ruff check on $filePath..." -ForegroundColor Cyan
    $ruffOutput = & ruff check $filePath --output-format=json 2>&1
    $ruffExitCode = $LASTEXITCODE

    if ($ruffExitCode -ne 0) {
        # Also get human-readable output
        $ruffReadable = & ruff check $filePath 2>&1
        $issues += "=== Ruff Linting Issues ==="
        $issues += $ruffReadable

        # Parse JSON for structured error info
        try {
            $ruffErrors = $ruffOutput | ConvertFrom-Json
            foreach ($err in $ruffErrors) {
                $errorDetails += @{
                    service = $serviceName
                    file = $err.filename
                    line = $err.location.row
                    message = "$($err.code): $($err.message)"
                    severity = "error"
                }
            }
        } catch {
            # Fallback if JSON parsing fails
            $errorDetails += @{
                service = $serviceName
                file = $filePath
                line = 0
                message = ($ruffReadable -join "`n")
                severity = "error"
            }
        }
    } else {
        Write-Host "  Ruff: OK" -ForegroundColor Green
    }
}

# TypeScript/JavaScript files - run eslint
if ($extension -in @(".ts", ".tsx", ".js", ".jsx")) {
    Write-Host "Running eslint on $filePath..." -ForegroundColor Cyan
    $eslintOutput = & npx eslint $filePath --format=json 2>&1
    $eslintExitCode = $LASTEXITCODE

    if ($eslintExitCode -ne 0) {
        # Also get human-readable output
        $eslintReadable = & npx eslint $filePath 2>&1
        $issues += "=== ESLint Issues ==="
        $issues += $eslintReadable

        # Parse JSON for structured error info
        try {
            $eslintResults = $eslintOutput | ConvertFrom-Json
            foreach ($result in $eslintResults) {
                foreach ($msg in $result.messages) {
                    $severity = if ($msg.severity -eq 2) { "error" } else { "warning" }
                    $errorDetails += @{
                        service = $serviceName
                        file = $result.filePath
                        line = $msg.line
                        message = "$($msg.ruleId): $($msg.message)"
                        severity = $severity
                    }
                }
            }
        } catch {
            # Fallback if JSON parsing fails
            $errorDetails += @{
                service = $serviceName
                file = $filePath
                line = 0
                message = ($eslintReadable -join "`n")
                severity = "error"
            }
        }
    } else {
        Write-Host "  ESLint: OK" -ForegroundColor Green
    }
}

# ============================================
# CODERABBIT CLI (via WSL if available)
# ============================================

if (-not $SkipCodeRabbit) {
    # Check if WSL Ubuntu is available
    $wslDistros = wsl --list --quiet 2>$null
    if ($wslDistros -match "Ubuntu") {
        # Check if coderabbit CLI is installed in WSL
        $crCheck = wsl -d Ubuntu which coderabbit 2>$null
        if ($crCheck) {
            Write-Host "Running CodeRabbit review..." -ForegroundColor Cyan

            # Convert Windows path to WSL path
            $wslPath = $filePath -replace '\\', '/' -replace '^([A-Za-z]):', '/mnt/$1'.ToLower()

            # Run CodeRabbit on the specific file
            $crOutput = wsl -d Ubuntu coderabbit review --plain --files $wslPath 2>&1

            if ($crOutput -and $crOutput -notmatch "No issues found") {
                $issues += "=== CodeRabbit AI Review ==="
                $issues += $crOutput

                # Store CodeRabbit findings as warnings
                $errorDetails += @{
                    service = $serviceName
                    file = $filePath
                    line = 0
                    message = "CodeRabbit: $($crOutput -join ' ')"
                    severity = "warning"
                }
            } else {
                Write-Host "  CodeRabbit: OK" -ForegroundColor Green
            }
        }
    }
}

# ============================================
# STORE ERRORS IN DATABASE
# ============================================

if (-not $SkipErrorDb) {
    if ($errorDetails.Count -gt 0) {
        # Store each error in the database
        Write-Host "Storing $($errorDetails.Count) error(s) in database..." -ForegroundColor Cyan

        foreach ($err in $errorDetails) {
            try {
                $storeArgs = @(
                    "-m", "api_gateway.services.error_tracker", "store",
                    "--service", $err.service,
                    "--message", $err.message,
                    "--severity", $err.severity
                )
                if ($err.file) {
                    $storeArgs += "--file"
                    $storeArgs += $err.file
                }
                if ($err.line -and $err.line -gt 0) {
                    $storeArgs += "--line"
                    $storeArgs += $err.line
                }

                & $pythonExe @storeArgs 2>&1 | Out-Null
            } catch {
                # Silently continue - don't block on DB errors
            }
        }
        Write-Host "  Errors logged to database" -ForegroundColor Yellow
    } else {
        # No errors found - mark any existing errors for this file as resolved
        try {
            $resolveOutput = & $pythonExe -m api_gateway.services.error_tracker resolve `
                --file $filePath `
                --resolution "Fixed: Linting passed after edit" 2>&1

            if ($resolveOutput -match "Resolved (\d+) errors") {
                $count = $Matches[1]
                if ([int]$count -gt 0) {
                    Write-Host "  Resolved $count previous error(s) for this file" -ForegroundColor Green
                }
            }
        } catch {
            # Silently continue
        }
    }
}

# ============================================
# OUTPUT ISSUES
# ============================================

if ($issues.Count -gt 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "ISSUES FOUND - Please fix before commit" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""
    foreach ($issue in $issues) {
        Write-Host $issue -ForegroundColor Red
    }
    Write-Host ""
    # Return non-zero to signal issues (Claude will see this)
    exit 1
}

exit 0
