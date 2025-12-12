@echo off
REM Congressional Parallel Scraper Launcher
REM Starts 20 parallel workers to scrape House member websites

setlocal EnableDelayedExpansion

echo ==========================================
echo Congressional Parallel Scraper
echo ==========================================
echo.

cd /d D:\AI

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    pause
    exit /b 1
)

REM Check command argument
if "%1"=="" goto start
if /i "%1"=="start" goto start
if /i "%1"=="check" goto check
if /i "%1"=="status" goto status
if /i "%1"=="stop" goto stop
if /i "%1"=="install-task" goto install_task
if /i "%1"=="help" goto help

echo Unknown command: %1
goto help

:start
echo Starting parallel scraper with 20 workers...
echo.
python -m api_gateway.services.congressional_parallel_supervisor start
goto end

:check
echo Running health check...
python -m api_gateway.services.congressional_parallel_supervisor check
goto end

:status
echo Getting status...
python -m api_gateway.services.congressional_parallel_supervisor status
goto end

:stop
echo Stopping all workers...
python -m api_gateway.services.congressional_parallel_supervisor stop
goto end

:install_task
echo Installing Windows Task Scheduler task...
python -m api_gateway.services.congressional_parallel_supervisor install-task --interval 5
goto end

:help
echo.
echo Usage: start_congressional_parallel.bat [command]
echo.
echo Commands:
echo   start        Start all parallel workers (default)
echo   check        Run health check on workers
echo   status       Show status of all workers
echo   stop         Stop all workers
echo   install-task Install Windows scheduled task
echo   help         Show this help message
echo.
goto end

:end
endlocal
