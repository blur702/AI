#!/bin/bash
# Deploy Playwright tests to VPS via SSH
# Usage: ./deploy-to-vps.sh [VPS_HOST] [VPS_USER] [SSH_KEY_PATH]
#
# Environment variables:
#   VPS_HOST          - Target VPS hostname (required if not passed as argument)
#   VPS_USER          - SSH user (default: root)
#   SSH_KEY_PATH      - Path to SSH private key (default: ~/.ssh/id_rsa)
#   REMOTE_TEST_DIR   - Remote directory for tests (default: /opt/ai-tests)
#   SYNC_DELETE       - Set to "true" to delete remote files not present locally (default: false)
#   SSH_KNOWN_HOSTS   - Path to known_hosts file (default: ~/.ssh/known_hosts)
#   SSH_SKIP_HOST_KEY - Set to "true" to skip host key verification (CI/automation only)
#
# Example with delete enabled:
#   SYNC_DELETE=true ./deploy-to-vps.sh myhost.com
#
# First-time setup (add host key to known_hosts):
#   ssh-keyscan -H myhost.com >> ~/.ssh/known_hosts
#
# CI/Automation mode (less secure, use only with ephemeral environments):
#   SSH_SKIP_HOST_KEY=true ./deploy-to-vps.sh myhost.com

set -e

# Configuration
VPS_HOST="${1:-${VPS_HOST:-}}"
VPS_USER="${2:-${VPS_USER:-root}}"
SSH_KEY="${3:-${SSH_KEY_PATH:-~/.ssh/id_rsa}}"
REMOTE_DIR="${REMOTE_TEST_DIR:-/opt/ai-tests}"

# Optional: Set SYNC_DELETE=true to remove remote files not present locally.
# WARNING: This can delete test reports and other artifacts on the remote server.
# By default, --delete is NOT used to preserve remote artifacts.
SYNC_DELETE="${SYNC_DELETE:-false}"

# SSH host key verification settings
SSH_KNOWN_HOSTS="${SSH_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
SSH_SKIP_HOST_KEY="${SSH_SKIP_HOST_KEY:-false}"

# Validate required parameters
if [ -z "$VPS_HOST" ]; then
    echo "Error: VPS_HOST is required"
    echo "Usage: $0 <VPS_HOST> [VPS_USER] [SSH_KEY_PATH]"
    echo "Or set VPS_HOST environment variable"
    exit 1
fi

# Build SSH options array with proper host key handling
SSH_OPTS=()

if [ "$SSH_SKIP_HOST_KEY" = "true" ]; then
    # CI/Automation mode: Skip host key verification
    # WARNING: This is vulnerable to MITM attacks. Only use in controlled environments.
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════════════════╗"
    echo "║  WARNING: SSH host key verification is DISABLED (SSH_SKIP_HOST_KEY=true)  ║"
    echo "║  This is vulnerable to man-in-the-middle attacks.                         ║"
    echo "║  Only use in CI/automation with ephemeral environments.                   ║"
    echo "╚═══════════════════════════════════════════════════════════════════════════╝"
    echo ""
    SSH_OPTS+=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
else
    # Secure mode: Use known_hosts file for host key verification
    if [ -f "$SSH_KNOWN_HOSTS" ]; then
        SSH_OPTS+=(-o UserKnownHostsFile="$SSH_KNOWN_HOSTS")
    fi

    # Check if host key exists in known_hosts
    if ! ssh-keygen -F "$VPS_HOST" -f "$SSH_KNOWN_HOSTS" >/dev/null 2>&1; then
        echo ""
        echo "Host key for '$VPS_HOST' not found in $SSH_KNOWN_HOSTS"
        echo ""
        echo "To add the host key, run one of:"
        echo "  ssh-keyscan -H $VPS_HOST >> $SSH_KNOWN_HOSTS"
        echo "  ssh $VPS_USER@$VPS_HOST  # (connect manually and accept the key)"
        echo ""
        echo "Or for CI/automation (less secure):"
        echo "  SSH_SKIP_HOST_KEY=true $0 $*"
        echo ""
        exit 1
    fi
fi

if [ -f "$SSH_KEY" ]; then
    SSH_OPTS+=(-i "$SSH_KEY")
fi

echo "=== VPS Test Deployment ==="
echo "Host: $VPS_USER@$VPS_HOST"
echo "Remote directory: $REMOTE_DIR"
echo ""

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Project root: $PROJECT_ROOT"

# Create remote directory
echo "[1/4] Creating remote directory..."
ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" "mkdir -p $REMOTE_DIR"

# Build rsync options
# --delete is only added if SYNC_DELETE=true to avoid accidentally removing remote artifacts
RSYNC_OPTS="-avz"
if [ "$SYNC_DELETE" = "true" ]; then
    echo "WARNING: SYNC_DELETE is enabled. Remote files not present locally will be deleted."
    RSYNC_OPTS="$RSYNC_OPTS --delete"
fi

# Rsync test files (exclude node_modules, reports, screenshots)
echo "[2/4] Syncing test files..."
rsync $RSYNC_OPTS \
    --exclude 'node_modules/' \
    --exclude 'playwright-report/' \
    --exclude 'test-results/' \
    --exclude 'tests/reports/' \
    --exclude 'tests/screenshots/' \
    --exclude '.git/' \
    --exclude '*.log' \
    -e "ssh ${SSH_OPTS[*]}" \
    "$PROJECT_ROOT/tests/" \
    "$VPS_USER@$VPS_HOST:$REMOTE_DIR/tests/"

# Sync package files
rsync -avz \
    -e "ssh ${SSH_OPTS[*]}" \
    "$PROJECT_ROOT/package.json" \
    "$PROJECT_ROOT/tsconfig.json" \
    "$VPS_USER@$VPS_HOST:$REMOTE_DIR/"

# Sync VPS environment file if exists
if [ -f "$PROJECT_ROOT/tests/.env.vps" ]; then
    echo "Syncing .env.vps..."
    rsync -avz \
        -e "ssh ${SSH_OPTS[*]}" \
        "$PROJECT_ROOT/tests/.env.vps" \
        "$VPS_USER@$VPS_HOST:$REMOTE_DIR/tests/.env"
fi

# Install dependencies on VPS
echo "[3/4] Installing dependencies on VPS..."
ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" << EOF
    cd $REMOTE_DIR

    # Check Node.js version
    if ! command -v node &> /dev/null; then
        echo "Node.js not found. Please install Node.js 18+ on the VPS."
        exit 1
    fi

    echo "Node version: \$(node --version)"
    echo "NPM version: \$(npm --version)"

    # Install npm dependencies
    npm install --production=false
EOF

# Install Playwright browsers
echo "[4/4] Installing Playwright browsers..."
ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" << EOF
    cd $REMOTE_DIR
    npx playwright install --with-deps chromium
EOF

echo ""
echo "=== Deployment Complete ==="
echo "Remote test directory: $VPS_USER@$VPS_HOST:$REMOTE_DIR"
echo ""
echo "To run tests:"
echo "  ssh ${SSH_OPTS[*]} $VPS_USER@$VPS_HOST 'cd $REMOTE_DIR && npm run test:vps'"
echo ""
echo "Or use: ./run-vps-tests.sh $VPS_HOST $VPS_USER $SSH_KEY"
