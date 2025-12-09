@echo off
REM Reload Nginx configuration without stopping

echo ============================================
echo Reloading Nginx Configuration
echo ============================================

cd /d %~dp0

REM Check if nginx is running
tasklist /fi "imagename eq nginx.exe" 2>nul | find /i "nginx.exe" >nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Nginx is not running. Use start-nginx.bat to start it.
    pause
    exit /b 1
)

REM Test configuration before reloading
echo Testing configuration...
nginx.exe -t -c "%~dp0nginx.conf"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Configuration test failed. Configuration not reloaded.
    pause
    exit /b 1
)

echo.
echo Reloading...
nginx.exe -s reload

echo.
echo Nginx configuration reloaded successfully.
pause
