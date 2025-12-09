#!/bin/bash
# Run Playwright tests on VPS via SSH and download reports
# Usage: ./run-vps-tests.sh [VPS_HOST] [VPS_USER] [SSH_KEY_PATH] [TEST_ARGS...]
#
# Environment variables:
#   VPS_HOST          - Target VPS hostname (required if not passed as argument)
#   VPS_USER          - SSH user (default: root)
#   SSH_KEY_PATH      - Path to SSH private key (default: ~/.ssh/id_rsa)
#   REMOTE_TEST_DIR   - Remote directory for tests (default: /opt/ai-tests)
#   SSH_KNOWN_HOSTS   - Path to known_hosts file (default: ~/.ssh/known_hosts)
#   SSH_SKIP_HOST_KEY - Set to "true" to skip host key verification (CI only)

set -e

# Configuration
VPS_HOST="${1:-${VPS_HOST:-}}"
VPS_USER="${2:-${VPS_USER:-root}}"
SSH_KEY="${3:-${SSH_KEY_PATH:-~/.ssh/id_rsa}}"
REMOTE_DIR="${REMOTE_TEST_DIR:-/opt/ai-tests}"

# SSH host key verification settings
SSH_KNOWN_HOSTS="${SSH_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
SSH_SKIP_HOST_KEY="${SSH_SKIP_HOST_KEY:-false}"

# Shift first 3 args if they look like config (not test args)
if [[ "$1" != --* ]] && [[ "$1" != -* ]] && [ -n "$1" ]; then
    shift
    if [[ "$1" != --* ]] && [[ "$1" != -* ]] && [ -n "$1" ]; then
        shift
        if [[ "$1" != --* ]] && [[ "$1" != -* ]] && [ -n "$1" ]; then
            shift
        fi
    fi
fi

# Remaining args are passed to test command (as array to preserve spaces/special chars)
TEST_ARGS=("$@")

# Validate required parameters
if [ -z "$VPS_HOST" ]; then
    echo "Error: VPS_HOST is required"
    echo "Usage: $0 <VPS_HOST> [VPS_USER] [SSH_KEY_PATH] [TEST_ARGS...]"
    echo "Or set VPS_HOST environment variable"
    exit 1
fi

# Build SSH options array with proper host key handling
SSH_OPTS=()

if [ "$SSH_SKIP_HOST_KEY" = "true" ]; then
    # CI/Automation mode: Skip host key verification
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

# Get local project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_REPORTS_DIR="$PROJECT_ROOT/tests/reports"
LOCAL_PLAYWRIGHT_REPORT="$PROJECT_ROOT/playwright-report"

echo "=== VPS Test Runner ==="
echo "Host: $VPS_USER@$VPS_HOST"
echo "Remote directory: $REMOTE_DIR"
echo "Test arguments: ${TEST_ARGS[*]:-<none>}"
echo ""

# Run tests on VPS
echo "[1/3] Running tests on VPS..."
echo "---"

# Build the remote test command with properly quoted arguments
# We need to escape the test args for remote execution
TEST_ARGS_ESCAPED=""
if [ ${#TEST_ARGS[@]} -gt 0 ]; then
    # Quote each argument to preserve spaces/special chars over SSH
    for arg in "${TEST_ARGS[@]}"; do
        # Escape single quotes and wrap in single quotes
        escaped_arg="'${arg//\'/\'\\\'\'}'"
        TEST_ARGS_ESCAPED="$TEST_ARGS_ESCAPED $escaped_arg"
    done
fi

# Stream test output in real-time
TEST_EXIT_CODE=0
ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" "cd $REMOTE_DIR && TEST_ENVIRONMENT=vps npm run test:vps --$TEST_ARGS_ESCAPED" || TEST_EXIT_CODE=$?

echo "---"
echo "Test execution completed with exit code: $TEST_EXIT_CODE"
echo ""

# Download reports
echo "[2/3] Downloading test reports..."

# Create local report directories
mkdir -p "$LOCAL_REPORTS_DIR"
mkdir -p "$LOCAL_PLAYWRIGHT_REPORT"

# Download JSON/JUnit reports
rsync -avz \
    -e "ssh ${SSH_OPTS[*]}" \
    "$VPS_USER@$VPS_HOST:$REMOTE_DIR/tests/reports/" \
    "$LOCAL_REPORTS_DIR/" 2>/dev/null || echo "No test reports to download"

# Download Playwright HTML report
rsync -avz \
    -e "ssh ${SSH_OPTS[*]}" \
    "$VPS_USER@$VPS_HOST:$REMOTE_DIR/playwright-report/" \
    "$LOCAL_PLAYWRIGHT_REPORT/" 2>/dev/null || echo "No Playwright report to download"

# Download test results (traces, screenshots, videos)
if ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" "test -d $REMOTE_DIR/test-results"; then
    echo "Downloading test artifacts..."
    rsync -avz \
        -e "ssh ${SSH_OPTS[*]}" \
        "$VPS_USER@$VPS_HOST:$REMOTE_DIR/test-results/" \
        "$PROJECT_ROOT/test-results/" 2>/dev/null || true
fi

echo ""
echo "[3/3] Cleanup (optional)..."
# Optionally clean up remote reports after download
# ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" "rm -rf $REMOTE_DIR/playwright-report $REMOTE_DIR/test-results $REMOTE_DIR/tests/reports"

echo ""
echo "=== Test Run Complete ==="
echo ""
echo "Results:"
echo "  - JSON Report: $LOCAL_REPORTS_DIR/report.json"
echo "  - JUnit Report: $LOCAL_REPORTS_DIR/junit-report.xml"
echo "  - HTML Report: $LOCAL_PLAYWRIGHT_REPORT/index.html"
echo ""
echo "To view the HTML report:"
echo "  npx playwright show-report"
echo ""

exit $TEST_EXIT_CODE
