@echo off
echo Starting AI Services Dashboard...
echo.

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0

REM Use environment variables if set, otherwise use defaults relative to script location
if "%PYTHON_EXE%"=="" set PYTHON_EXE=python

REM Check for required environment variables
REM If not set, try to load from .env file in dashboard\backend
if "%DASHBOARD_AUTH_USERNAME%"=="" (
    set ENV_FILE=%SCRIPT_DIR%dashboard\backend\.env
    if exist "%SCRIPT_DIR%dashboard\backend\.env" (
        echo Loading credentials from .env file...
        for /f "usebackq tokens=1,* delims==" %%a in ("%SCRIPT_DIR%dashboard\backend\.env") do (
            if "%%a"=="DASHBOARD_AUTH_USERNAME" set DASHBOARD_AUTH_USERNAME=%%b
            if "%%a"=="DASHBOARD_AUTH_PASSWORD" set DASHBOARD_AUTH_PASSWORD=%%b
        )
    )
)

REM Final check - if still not set, show error
if "%DASHBOARD_AUTH_USERNAME%"=="" (
    echo ERROR: DASHBOARD_AUTH_USERNAME not found in environment or .env file.
    echo Please set DASHBOARD_AUTH_USERNAME and DASHBOARD_AUTH_PASSWORD.
    echo.
    echo Option 1 - Environment variables:
    echo   set DASHBOARD_AUTH_USERNAME=admin
    echo   set DASHBOARD_AUTH_PASSWORD=yourpassword
    echo.
    echo Option 2 - Create .env file in dashboard\backend:
    echo   DASHBOARD_AUTH_USERNAME=admin
    echo   DASHBOARD_AUTH_PASSWORD=yourpassword
    pause
    exit /b 1
)

if "%DASHBOARD_AUTH_PASSWORD%"=="" (
    echo ERROR: DASHBOARD_AUTH_PASSWORD not found in environment or .env file.
    echo Please set DASHBOARD_AUTH_USERNAME and DASHBOARD_AUTH_PASSWORD.
    echo.
    echo Option 1 - Environment variables:
    echo   set DASHBOARD_AUTH_USERNAME=admin
    echo   set DASHBOARD_AUTH_PASSWORD=yourpassword
    echo.
    echo Option 2 - Create .env file in dashboard\backend:
    echo   DASHBOARD_AUTH_USERNAME=admin
    echo   DASHBOARD_AUTH_PASSWORD=yourpassword
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
