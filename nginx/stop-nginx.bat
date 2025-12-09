@echo off
REM Stop Nginx reverse proxy

echo ============================================
echo Stopping Nginx
echo ============================================

cd /d %~dp0

REM Check if nginx is running
tasklist /fi "imagename eq nginx.exe" 2>nul | find /i "nginx.exe" >nul
if %ERRORLEVEL% NEQ 0 (
    echo Nginx is not running.
    pause
    exit /b 0
)

echo Sending stop signal...
nginx.exe -s stop

REM Wait for nginx to stop
timeout /t 2 /nobreak >nul

tasklist /fi "imagename eq nginx.exe" 2>nul | find /i "nginx.exe" >nul
if %ERRORLEVEL% EQU 0 (
    echo WARNING: Nginx did not stop gracefully. Force killing...
    taskkill /f /im nginx.exe >nul 2>&1
)

echo.
echo Nginx stopped.
pause
