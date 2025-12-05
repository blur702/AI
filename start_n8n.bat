@echo off
REM ============================================================
REM  N8N Workflow Automation - Startup Script
REM ============================================================
REM Prerequisites:
REM   - Node.js version 20.19.x to 24.x (recommended for n8n)
REM   - Check Node.js version:  node --version
REM   - Install n8n globally:   npm install n8n -g
REM   - Verify n8n installation: n8n --version
REM
REM Notes:
REM   - n8n is installed globally (not as a local project dependency).
REM   - For advanced configuration, see the official n8n docs:
REM       https://docs.n8n.io/
REM   - n8n can be configured via environment variables for:
REM       * Data folder location
REM       * Webhook URL / public URL
REM       * Authentication and security
REM   - On first launch, you will be guided through creating
REM     an account in the n8n web interface.
REM ============================================================

echo Starting N8N Workflow Automation on port 5678...
echo.
echo Access from this machine: http://localhost:5678
echo Access from network:     http://10.0.0.138:5678
echo.
echo Press Ctrl+C to stop the N8N service.
echo.

cd /D "D:\AI"

REM Quick check to ensure n8n is installed and on PATH
n8n --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] n8n does not appear to be installed globally or is not on PATH.
    echo         Please run: npm install n8n -g
    echo         After installation, close and reopen your terminal so PATH updates take effect.
    echo.
    echo Exiting without starting N8N.
    goto :EOF
)

REM Launch n8n with default configuration.
REM By default, n8n will:
REM   - Listen on port 5678
REM   - Use its default data directory
REM   - Expose the web UI at / on the configured host/port
n8n start
