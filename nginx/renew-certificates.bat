@echo off
REM Auto-renewal script for Let's Encrypt certificates
echo [%date% %time%] Starting certificate renewal check...
certbot renew --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] ERROR: certbot renew failed with exit code %ERRORLEVEL%
    exit /b 1
)

REM Verify source certificate files exist before copying
set CERT_SRC=C:\Certbot\live\ssdd.kevinalthaus.com\fullchain.pem
set KEY_SRC=C:\Certbot\live\ssdd.kevinalthaus.com\privkey.pem

if not exist "%CERT_SRC%" (
    echo [%date% %time%] ERROR: Source certificate not found: %CERT_SRC%
    exit /b 1
)

if not exist "%KEY_SRC%" (
    echo [%date% %time%] ERROR: Source private key not found: %KEY_SRC%
    exit /b 1
)

REM Copy renewed certificates to nginx
echo [%date% %time%] Copying certificate...
copy /Y "%CERT_SRC%" "D:\AI\nginx\ssl\ssdd.kevinalthaus.com.crt" >nul
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] ERROR: Failed to copy certificate file
    exit /b 1
)

echo [%date% %time%] Copying private key...
copy /Y "%KEY_SRC%" "D:\AI\nginx\ssl\ssdd.kevinalthaus.com.key" >nul
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] ERROR: Failed to copy private key file
    exit /b 1
)

REM Verify destination files exist before reloading nginx
if not exist "D:\AI\nginx\ssl\ssdd.kevinalthaus.com.crt" (
    echo [%date% %time%] ERROR: Destination certificate missing after copy
    exit /b 1
)

if not exist "D:\AI\nginx\ssl\ssdd.kevinalthaus.com.key" (
    echo [%date% %time%] ERROR: Destination private key missing after copy
    exit /b 1
)

REM Both certificates copied successfully, reload nginx
echo [%date% %time%] Certificates copied successfully, reloading nginx...
call "D:\AI\nginx\reload-nginx.bat"
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] ERROR: Failed to reload nginx
    exit /b 1
)

echo [%date% %time%] Certificate renewal completed successfully
