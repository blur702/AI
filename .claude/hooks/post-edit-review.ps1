# Post-Edit Review Hook for Claude Code
# Runs linters on edited files and outputs issues for Claude to fix
#
# Input: JSON from stdin with tool_input.file_path
# Output: Lint errors to stdout (Claude will see and fix them)

param(
    [Parameter(ValueFromPipeline=$true)]
    [string]$InputJson
)

# Parse the JSON input to get file path
try {
    $data = $InputJson | ConvertFrom-Json
    $filePath = $data.tool_input.file_path
} catch {
    exit 0  # No file path, skip
}

if (-not $filePath -or -not (Test-Path $filePath)) {
    exit 0
}

$extension = [System.IO.Path]::GetExtension($filePath).ToLower()
$issues = @()

# Python files - run ruff
if ($extension -eq ".py") {
    $ruffPath = Get-Command ruff -ErrorAction SilentlyContinue
    if ($ruffPath) {
        $ruffOutput = & ruff check $filePath --output-format=text 2>&1
        if ($LASTEXITCODE -ne 0 -and $ruffOutput) {
            $issues += "=== Ruff (Python) Issues ==="
            $issues += $ruffOutput
        }
    }
}

# TypeScript/JavaScript files - run ESLint
if ($extension -in ".ts", ".tsx", ".js", ".jsx") {
    $eslintPath = Get-Command npx -ErrorAction SilentlyContinue
    if ($eslintPath) {
        $eslintOutput = & npx eslint $filePath --format stylish 2>&1
        if ($LASTEXITCODE -ne 0 -and $eslintOutput) {
            $issues += "=== ESLint (TypeScript/JavaScript) Issues ==="
            $issues += $eslintOutput
        }
    }
}

# Output issues if any were found
if ($issues.Count -gt 0) {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════╗"
    Write-Host "║  CODE REVIEW ISSUES FOUND - Please fix before continuing     ║"
    Write-Host "╚══════════════════════════════════════════════════════════════╝"
    Write-Host ""
    foreach ($issue in $issues) {
        Write-Host $issue
    }
    Write-Host ""
    # Exit 0 to not block, but output will be visible to Claude
}

exit 0
