@echo off
REM Start Nginx reverse proxy for ssdd.kevinalthaus.com

echo ============================================
echo Starting Nginx Reverse Proxy
echo ============================================

cd /d %~dp0

REM Check if nginx is already running
tasklist /fi "imagename eq nginx.exe" 2>nul | find /i "nginx.exe" >nul
if %ERRORLEVEL% EQU 0 (
    echo WARNING: Nginx is already running.
    echo Use reload-nginx.bat to reload configuration.
    echo Use stop-nginx.bat to stop the server.
    pause
    exit /b 0
)

REM Check if SSL certificate file exists
if not exist "ssl\ssdd.kevinalthaus.com.crt" (
    echo ERROR: SSL certificate file not found!
    echo.
    echo Missing: ssl\ssdd.kevinalthaus.com.crt
    echo.
    echo Please run one of the following first:
    echo   - setup-letsencrypt.bat (for production)
    echo   - generate-self-signed-cert.bat (for testing)
    echo.
    pause
    exit /b 1
)

REM Check if SSL private key file exists
if not exist "ssl\ssdd.kevinalthaus.com.key" (
    echo ERROR: SSL private key file not found!
    echo.
    echo Missing: ssl\ssdd.kevinalthaus.com.key
    echo.
    echo Please run one of the following first:
    echo   - setup-letsencrypt.bat (for production)
    echo   - generate-self-signed-cert.bat (for testing)
    echo.
    pause
    exit /b 1
)

echo SSL certificates found.

REM Test configuration before starting
echo Testing configuration...
nginx.exe -t -c "%~dp0nginx.conf"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Configuration test failed. Fix errors before starting.
    pause
    exit /b 1
)

echo.
echo Starting nginx...
start "" nginx.exe -c "%~dp0nginx.conf"

REM Wait a moment and verify it started
timeout /t 2 /nobreak >nul

tasklist /fi "imagename eq nginx.exe" 2>nul | find /i "nginx.exe" >nul
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================
    echo Nginx started successfully!
    echo.
    echo HTTPS: https://ssdd.kevinalthaus.com/
    echo HTTP:  http://ssdd.kevinalthaus.com/ (redirects to HTTPS)
    echo.
    echo Logs: %~dp0logs\
    echo ============================================
) else (
    echo.
    echo ERROR: Nginx failed to start. Check logs\error.log for details.
)

pause
