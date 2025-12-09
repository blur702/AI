# Deploy Playwright tests to VPS via SSH (PowerShell/Windows)
# Usage: .\deploy-to-vps.ps1 -VpsHost <host> [-VpsUser <user>] [-SshKeyPath <path>]
#
# Parameters:
#   -VpsHost          Target VPS hostname (required, or set VPS_HOST env var)
#   -VpsUser          SSH user (default: root)
#   -SshKeyPath       Path to SSH private key (default: ~/.ssh/id_rsa)
#   -RemoteDir        Remote directory for tests (default: /opt/ai-tests)
#   -SshKnownHosts    Path to known_hosts file (default: ~/.ssh/known_hosts)
#   -SkipHostKeyCheck Skip SSH host key verification (CI/automation only)
#
# First-time setup (add host key):
#   ssh-keyscan -H myhost.com >> $env:USERPROFILE\.ssh\known_hosts
#
# CI/Automation mode (less secure):
#   .\deploy-to-vps.ps1 -VpsHost myhost.com -SkipHostKeyCheck

param(
    [Parameter(Mandatory=$false)]
    [string]$VpsHost = $env:VPS_HOST,

    [Parameter(Mandatory=$false)]
    [string]$VpsUser = $(if ($env:VPS_USER) { $env:VPS_USER } else { "root" }),

    [Parameter(Mandatory=$false)]
    [string]$SshKeyPath = $(if ($env:SSH_KEY_PATH) { $env:SSH_KEY_PATH } else { "$env:USERPROFILE\.ssh\id_rsa" }),

    [Parameter(Mandatory=$false)]
    [string]$RemoteDir = $(if ($env:REMOTE_TEST_DIR) { $env:REMOTE_TEST_DIR } else { "/opt/ai-tests" }),

    [Parameter(Mandatory=$false)]
    [string]$SshKnownHosts = $(if ($env:SSH_KNOWN_HOSTS) { $env:SSH_KNOWN_HOSTS } else { "$env:USERPROFILE\.ssh\known_hosts" }),

    [Parameter(Mandatory=$false)]
    [switch]$SkipHostKeyCheck = $(if ($env:SSH_SKIP_HOST_KEY -eq "true") { $true } else { $false })
)

$ErrorActionPreference = "Stop"

# Helper function to check command exit code
function Test-LastExitCode {
    param(
        [string]$Operation,
        [switch]$AllowContinue
    )
    if ($LASTEXITCODE -ne 0) {
        $message = "Failed: $Operation (exit code: $LASTEXITCODE)"
        if ($AllowContinue) {
            Write-Warning $message
            return $false
        } else {
            Write-Error $message
            exit 1
        }
    }
    return $true
}

# Validate required parameters
if ([string]::IsNullOrEmpty($VpsHost)) {
    Write-Error "VPS_HOST is required. Use -VpsHost parameter or set VPS_HOST environment variable."
    exit 1
}

# Build SSH options with proper host key handling
$SshOpts = @()

if ($SkipHostKeyCheck) {
    # CI/Automation mode: Skip host key verification
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Red
    Write-Host "║  WARNING: SSH host key verification is DISABLED (-SkipHostKeyCheck)       ║" -ForegroundColor Red
    Write-Host "║  This is vulnerable to man-in-the-middle attacks.                         ║" -ForegroundColor Red
    Write-Host "║  Only use in CI/automation with ephemeral environments.                   ║" -ForegroundColor Red
    Write-Host "╚═══════════════════════════════════════════════════════════════════════════╝" -ForegroundColor Red
    Write-Host ""
    $SshOpts += @("-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null")
} else {
    # Secure mode: Use known_hosts file for host key verification
    if (Test-Path $SshKnownHosts) {
        $SshOpts += @("-o", "UserKnownHostsFile=$SshKnownHosts")
    }

    # Check if host key exists in known_hosts (using ssh-keygen -F)
    $hostKeyCheck = & ssh-keygen -F $VpsHost -f $SshKnownHosts 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($hostKeyCheck)) {
        Write-Host ""
        Write-Host "Host key for '$VpsHost' not found in $SshKnownHosts" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To add the host key, run one of:" -ForegroundColor Cyan
        Write-Host "  ssh-keyscan -H $VpsHost >> $SshKnownHosts"
        Write-Host "  ssh ${VpsUser}@${VpsHost}  # (connect manually and accept the key)"
        Write-Host ""
        Write-Host "Or for CI/automation (less secure):" -ForegroundColor Cyan
        Write-Host "  .\deploy-to-vps.ps1 -VpsHost $VpsHost -SkipHostKeyCheck"
        Write-Host ""
        exit 1
    }
}

if (Test-Path $SshKeyPath) {
    $SshOpts += @("-i", $SshKeyPath)
}

$SshTarget = "${VpsUser}@${VpsHost}"

Write-Host "=== VPS Test Deployment ===" -ForegroundColor Cyan
Write-Host "Host: $SshTarget"
Write-Host "Remote directory: $RemoteDir"
Write-Host ""

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

Write-Host "Project root: $ProjectRoot"

# Check for required tools
$requiredTools = @("ssh", "scp")
foreach ($tool in $requiredTools) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Error "$tool is not available. Please install OpenSSH or use Git Bash."
        exit 1
    }
}

# Create remote directory
Write-Host "[1/4] Creating remote directory..." -ForegroundColor Yellow
& ssh @SshOpts $SshTarget "mkdir -p $RemoteDir/tests"
Test-LastExitCode -Operation "Create remote directory"

# Files and directories to copy
$filesToCopy = @(
    @{ Source = "$ProjectRoot\package.json"; Dest = "$RemoteDir/" },
    @{ Source = "$ProjectRoot\tsconfig.json"; Dest = "$RemoteDir/" }
)

$dirsToSync = @(
    @{
        Source = "$ProjectRoot\tests";
        Dest = "$RemoteDir/";
        Exclude = @("node_modules", "playwright-report", "test-results", "reports", "screenshots")
    }
)

# Copy individual files
Write-Host "[2/4] Syncing test files..." -ForegroundColor Yellow

foreach ($file in $filesToCopy) {
    if (Test-Path $file.Source) {
        Write-Host "  Copying $($file.Source)..."
        & scp @SshOpts "$($file.Source)" "${SshTarget}:$($file.Dest)"
        Test-LastExitCode -Operation "Copy $($file.Source)"
    }
}

# Sync directories (using scp -r for simplicity on Windows)
foreach ($dir in $dirsToSync) {
    if (Test-Path $dir.Source) {
        Write-Host "  Syncing $($dir.Source)..."

        # Create a temp directory with filtered content
        $tempDir = Join-Path $env:TEMP "vps-deploy-$(Get-Random)"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        # Copy files excluding specified patterns
        Get-ChildItem -Path $dir.Source -Recurse | Where-Object {
            $relativePath = $_.FullName.Substring($dir.Source.Length)
            $excluded = $false
            foreach ($pattern in $dir.Exclude) {
                if ($relativePath -match [regex]::Escape($pattern)) {
                    $excluded = $true
                    break
                }
            }
            -not $excluded
        } | ForEach-Object {
            $targetPath = Join-Path $tempDir $_.FullName.Substring($dir.Source.Length)
            $targetDir = Split-Path -Parent $targetPath
            if (-not (Test-Path $targetDir)) {
                New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
            }
            if (-not $_.PSIsContainer) {
                Copy-Item $_.FullName -Destination $targetPath -Force
            }
        }

        # Upload to VPS
        & scp -r @SshOpts "$tempDir\*" "${SshTarget}:$RemoteDir/tests/"
        $scpResult = Test-LastExitCode -Operation "Sync $($dir.Source)" -AllowContinue

        # Cleanup temp directory
        Remove-Item -Recurse -Force $tempDir

        if (-not $scpResult) {
            Write-Error "Failed to sync directory $($dir.Source)"
            exit 1
        }
    }
}

# Copy VPS environment file if exists
$envVpsPath = "$ProjectRoot\tests\.env.vps"
if (Test-Path $envVpsPath) {
    Write-Host "  Syncing .env.vps..."
    & scp @SshOpts $envVpsPath "${SshTarget}:$RemoteDir/tests/.env"
    Test-LastExitCode -Operation "Copy .env.vps"
}

# Install dependencies on VPS
Write-Host "[3/4] Installing dependencies on VPS..." -ForegroundColor Yellow
$installScript = @"
cd $RemoteDir

# Check Node.js version
if ! command -v node &> /dev/null; then
    echo 'Node.js not found. Please install Node.js 18+ on the VPS.'
    exit 1
fi

echo "Node version: `$(node --version)"
echo "NPM version: `$(npm --version)"

# Install npm dependencies
npm install --production=false
"@

$installScript | & ssh @SshOpts $SshTarget "bash -s"
Test-LastExitCode -Operation "Install npm dependencies"

# Install Playwright browsers
Write-Host "[4/4] Installing Playwright browsers..." -ForegroundColor Yellow
$playwrightScript = @"
cd $RemoteDir
npx playwright install --with-deps chromium
"@

$playwrightScript | & ssh @SshOpts $SshTarget "bash -s"
Test-LastExitCode -Operation "Install Playwright browsers"

Write-Host ""
Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host "Remote test directory: ${SshTarget}:$RemoteDir"
Write-Host ""
Write-Host "To run tests:"
Write-Host "  ssh $SshTarget 'cd $RemoteDir && npm run test:vps'"
Write-Host ""
Write-Host "Or use: .\run-vps-tests.ps1 -VpsHost $VpsHost -VpsUser $VpsUser"
