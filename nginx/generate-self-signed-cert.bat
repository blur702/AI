@echo off
REM Generate Self-Signed SSL Certificate for ssdd.kevinalthaus.com
REM For testing/development purposes only

echo ============================================
echo Self-Signed Certificate Generator
echo Domain: ssdd.kevinalthaus.com
echo ============================================
echo.
echo WARNING: Self-signed certificates will show browser warnings.
echo Use Let's Encrypt for production (setup-letsencrypt.bat)
echo.

REM Check if OpenSSL is installed
where openssl >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: OpenSSL is not installed or not in PATH.
    echo.
    echo Please install OpenSSL for Windows:
    echo 1. Download from: https://slproweb.com/products/Win32OpenSSL.html
    echo 2. Install and add to PATH
    echo 3. Re-run this script
    echo.
    pause
    exit /b 1
)

set SSL_DIR=%~dp0ssl

REM Ensure SSL directory exists
if not exist "%SSL_DIR%" (
    echo Creating SSL directory: %SSL_DIR%
    mkdir "%SSL_DIR%"
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Failed to create SSL directory.
        pause
        exit /b 1
    )
)

cd /d "%SSL_DIR%"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to change to SSL directory: %SSL_DIR%
    pause
    exit /b 1
)

echo Generating self-signed certificate...
echo.

openssl req -x509 -nodes -days 365 -newkey rsa:2048 ^
    -keyout ssdd.kevinalthaus.com.key ^
    -out ssdd.kevinalthaus.com.crt ^
    -subj "/CN=ssdd.kevinalthaus.com/O=Local Development/C=US"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Certificate generation failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo Certificate generated successfully!
echo.
echo Files created:
echo   - %SSL_DIR%\ssdd.kevinalthaus.com.crt
echo   - %SSL_DIR%\ssdd.kevinalthaus.com.key
echo.
echo NEXT STEPS:
echo 1. Start nginx: start-nginx.bat
echo 2. Accept the browser security warning when accessing the site
echo ============================================
pause
