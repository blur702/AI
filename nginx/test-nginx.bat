@echo off
REM Test Nginx configuration for syntax errors

echo ============================================
echo Testing Nginx Configuration
echo ============================================

cd /d %~dp0

nginx.exe -t -c "%~dp0nginx.conf"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Configuration test PASSED.
) else (
    echo.
    echo Configuration test FAILED. Fix the errors above.
)

pause
