@echo off
REM Let's Encrypt SSL Certificate Setup for ssdd.kevinalthaus.com
REM Requires Certbot to be installed (https://certbot.eff.org/instructions?ws=other&os=windows)

echo ============================================
echo Let's Encrypt Certificate Setup
echo Domain: ssdd.kevinalthaus.com
echo ============================================
echo.

REM Check if certbot is installed
where certbot >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Certbot is not installed or not in PATH.
    echo.
    echo Please install Certbot for Windows:
    echo 1. Download from: https://dl.eff.org/certbot-beta-installer-win_amd64.exe
    echo 2. Run the installer
    echo 3. Re-run this script
    echo.
    pause
    exit /b 1
)

echo Certbot found. Starting certificate request...
echo.
echo IMPORTANT: This will temporarily start a webserver on port 80.
echo Make sure no other service is using port 80 (stop Flask dashboard first).
echo.
pause

REM Request certificate using standalone mode
certbot certonly --standalone -d ssdd.kevinalthaus.com --agree-tos --no-eff-email

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Certificate request failed.
    echo Check the error message above for details.
    pause
    exit /b 1
)

echo.
echo Certificate obtained successfully!
echo.

REM Copy certificates to nginx ssl directory
set CERT_PATH=C:\Certbot\live\ssdd.kevinalthaus.com
set SSL_DIR=%~dp0ssl

echo Copying certificates to %SSL_DIR%...

if exist "%CERT_PATH%\fullchain.pem" (
    copy "%CERT_PATH%\fullchain.pem" "%SSL_DIR%\ssdd.kevinalthaus.com.crt"
    copy "%CERT_PATH%\privkey.pem" "%SSL_DIR%\ssdd.kevinalthaus.com.key"
    echo Certificates copied successfully!
) else (
    echo WARNING: Could not find certificates at %CERT_PATH%
    echo You may need to manually copy them.
)

echo.
echo ============================================
echo NEXT STEPS:
echo 1. Start nginx: start-nginx.bat
echo 2. Set up auto-renewal task (see setup-renewal-task.bat)
echo ============================================
pause
