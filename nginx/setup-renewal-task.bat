@echo off
REM Set up Windows Scheduled Task for Let's Encrypt certificate auto-renewal
REM Runs twice daily as recommended by Let's Encrypt

echo ============================================
echo Let's Encrypt Auto-Renewal Task Setup
echo ============================================
echo.

REM Check for administrator privileges
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: This script requires administrator privileges.
    echo Please right-click and "Run as administrator"
    pause
    exit /b 1
)

set TASK_NAME=CertbotRenewal
set NGINX_DIR=%~dp0

REM Create the renewal script
echo Creating renewal script...
(
echo @echo off
echo REM Auto-renewal script for Let's Encrypt certificates
echo echo [%%date%% %%time%%] Starting certificate renewal check...
echo certbot renew --quiet
echo if %%ERRORLEVEL%% NEQ 0 ^(
echo     echo [%%date%% %%time%%] ERROR: certbot renew failed with exit code %%ERRORLEVEL%%
echo     exit /b 1
echo ^)
echo.
echo REM Verify source certificate files exist before copying
echo set CERT_SRC=C:\Certbot\live\ssdd.kevinalthaus.com\fullchain.pem
echo set KEY_SRC=C:\Certbot\live\ssdd.kevinalthaus.com\privkey.pem
echo.
echo if not exist "%%CERT_SRC%%" ^(
echo     echo [%%date%% %%time%%] ERROR: Source certificate not found: %%CERT_SRC%%
echo     exit /b 1
echo ^)
echo.
echo if not exist "%%KEY_SRC%%" ^(
echo     echo [%%date%% %%time%%] ERROR: Source private key not found: %%KEY_SRC%%
echo     exit /b 1
echo ^)
echo.
echo REM Copy renewed certificates to nginx
echo echo [%%date%% %%time%%] Copying certificate...
echo copy /Y "%%CERT_SRC%%" "%NGINX_DIR%ssl\ssdd.kevinalthaus.com.crt" ^>nul
echo if %%ERRORLEVEL%% NEQ 0 ^(
echo     echo [%%date%% %%time%%] ERROR: Failed to copy certificate file
echo     exit /b 1
echo ^)
echo.
echo echo [%%date%% %%time%%] Copying private key...
echo copy /Y "%%KEY_SRC%%" "%NGINX_DIR%ssl\ssdd.kevinalthaus.com.key" ^>nul
echo if %%ERRORLEVEL%% NEQ 0 ^(
echo     echo [%%date%% %%time%%] ERROR: Failed to copy private key file
echo     exit /b 1
echo ^)
echo.
echo REM Verify destination files exist before reloading nginx
echo if not exist "%NGINX_DIR%ssl\ssdd.kevinalthaus.com.crt" ^(
echo     echo [%%date%% %%time%%] ERROR: Destination certificate missing after copy
echo     exit /b 1
echo ^)
echo.
echo if not exist "%NGINX_DIR%ssl\ssdd.kevinalthaus.com.key" ^(
echo     echo [%%date%% %%time%%] ERROR: Destination private key missing after copy
echo     exit /b 1
echo ^)
echo.
echo REM Both certificates copied successfully, reload nginx
echo echo [%%date%% %%time%%] Certificates copied successfully, reloading nginx...
echo call "%NGINX_DIR%reload-nginx.bat"
echo if %%ERRORLEVEL%% NEQ 0 ^(
echo     echo [%%date%% %%time%%] ERROR: Failed to reload nginx
echo     exit /b 1
echo ^)
echo.
echo echo [%%date%% %%time%%] Certificate renewal completed successfully
) > "%NGINX_DIR%renew-certificates.bat"

echo Created: %NGINX_DIR%renew-certificates.bat
echo.

REM Delete existing task if it exists
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM Create scheduled task to run twice daily (at 3:00 AM and 3:00 PM)
echo Creating scheduled task (twice daily)...
schtasks /create /tn "%TASK_NAME%" /tr "\"%NGINX_DIR%renew-certificates.bat\"" /sc daily /st 03:00 /ru SYSTEM /rl HIGHEST

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create scheduled task.
    pause
    exit /b 1
)

REM Delete existing PM task if it exists
schtasks /delete /tn "%TASK_NAME%_PM" /f >nul 2>&1

REM Add second trigger for 3:00 PM
schtasks /create /tn "%TASK_NAME%_PM" /tr "\"%NGINX_DIR%renew-certificates.bat\"" /sc daily /st 15:00 /ru SYSTEM /rl HIGHEST

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create second scheduled task trigger.
    pause
    exit /b 1
)

echo.
echo ============================================
echo Auto-renewal task created successfully!
echo.
echo Task Names: %TASK_NAME% (AM), %TASK_NAME%_PM (PM)
echo Schedule: Twice daily at 3:00 AM and 3:00 PM
echo.
echo To verify: schtasks /query /tn "%TASK_NAME%"
echo            schtasks /query /tn "%TASK_NAME%_PM"
echo To remove: schtasks /delete /tn "%TASK_NAME%" /f
echo            schtasks /delete /tn "%TASK_NAME%_PM" /f
echo ============================================
pause
