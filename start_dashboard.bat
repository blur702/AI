@echo off
echo Starting AI Services Dashboard...
echo.

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0

REM Use environment variables if set, otherwise use defaults relative to script location
if "%PYTHON_EXE%"=="" set PYTHON_EXE=python

REM Check for required environment variables
if "%DASHBOARD_AUTH_USERNAME%"=="" (
    echo ERROR: DASHBOARD_AUTH_USERNAME environment variable is not set.
    echo Please set DASHBOARD_AUTH_USERNAME and DASHBOARD_AUTH_PASSWORD before starting.
    echo.
    echo Example:
    echo   set DASHBOARD_AUTH_USERNAME=admin
    echo   set DASHBOARD_AUTH_PASSWORD=yourpassword
    echo.
    echo Or create a .env file in dashboard\backend directory.
    pause
    exit /b 1
)

if "%DASHBOARD_AUTH_PASSWORD%"=="" (
    echo ERROR: DASHBOARD_AUTH_PASSWORD environment variable is not set.
    echo Please set DASHBOARD_AUTH_USERNAME and DASHBOARD_AUTH_PASSWORD before starting.
    echo.
    echo Example:
    echo   set DASHBOARD_AUTH_USERNAME=admin
    echo   set DASHBOARD_AUTH_PASSWORD=yourpassword
    echo.
    echo Or create a .env file in dashboard\backend directory.
    pause
    exit /b 1
)

REM Single-port deployment: Flask serves both frontend and API on port 80
echo Starting dashboard on port 80 (frontend + API)...
start /B cmd /c "cd /d %SCRIPT_DIR%dashboard\backend && %PYTHON_EXE% app.py"

REM Wait a moment for server to start
timeout /t 2 /nobreak > nul

REM Get network IP if not already set (optional environment variable)
if "%DASHBOARD_NETWORK_IP%"=="" (
    REM Try to detect local IP address (first IPv4 address from ipconfig)
    for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
        set DASHBOARD_NETWORK_IP=%%a
        goto :ip_found
    )
    :ip_found
    REM Trim leading spaces
    set DASHBOARD_NETWORK_IP=%DASHBOARD_NETWORK_IP: =%
)

REM External host is optional (set via DASHBOARD_EXTERNAL_HOST environment variable)
if not "%DASHBOARD_EXTERNAL_HOST%"=="" (
    set EXTERNAL_LINE=  External access: http://%DASHBOARD_EXTERNAL_HOST%
) else (
    set EXTERNAL_LINE=  External access: (set DASHBOARD_EXTERNAL_HOST to configure)
)

echo.
echo Dashboard started!
echo   Dashboard: http://localhost (port 80)
echo   API: http://localhost/api
if not "%DASHBOARD_NETWORK_IP%"=="" (
    echo   Network access: http://%DASHBOARD_NETWORK_IP%
)
echo %EXTERNAL_LINE%
echo.
echo To customize access URLs, set environment variables:
echo   DASHBOARD_NETWORK_IP - Network IP address (auto-detected: %DASHBOARD_NETWORK_IP%)
echo   DASHBOARD_EXTERNAL_HOST - External domain/IP if accessible from internet
echo.
echo Press any key to exit (services will continue running)...
pause > nul
