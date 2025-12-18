# Install git hooks for secret scanning
# Run this once: .\scripts\install-hooks.ps1

$ErrorActionPreference = "Stop"

$hookPath = ".git\hooks\pre-commit"
$scriptPath = "scripts\check-env-secrets.py"

# Check if we're in a git repo
if (-not (Test-Path ".git")) {
    Write-Error "Not in a git repository root"
    exit 1
}

# Create the pre-commit hook content
$hookContent = @'
#!/bin/sh
#
# Pre-commit hook to scan for secrets in .env files

echo "Running secret scan..."

# Run the secret scanner
python scripts/check-env-secrets.py --ci 2>/dev/null || python3 scripts/check-env-secrets.py --ci

if [ $? -ne 0 ]; then
    echo ""
    echo "COMMIT BLOCKED: Secrets detected!"
    echo "Remove the secrets and try again."
    exit 1
fi

# Check if any .env files (non-example) are staged
STAGED_ENV=$(git diff --cached --name-only | grep -E '\.env$|\.env\.local$' | grep -v '\.example' || true)

if [ -n "$STAGED_ENV" ]; then
    echo ""
    echo "COMMIT BLOCKED: .env file staged!"
    echo "Only .env.example files should be committed."
    echo "Staged files: $STAGED_ENV"
    exit 1
fi

echo "Secret scan passed"
exit 0
'@

# Write the hook
Set-Content -Path $hookPath -Value $hookContent -NoNewline

Write-Host "Git pre-commit hook installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "The hook will now scan for secrets before each commit."
Write-Host "To bypass (not recommended): git commit --no-verify"
