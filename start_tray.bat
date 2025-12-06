@echo off
REM AI Services System Tray Utility
REM Starts the tray application for managing AI services and VRAM

cd /d "%~dp0tray_app"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to change directory to tray_app 1>&2
    echo The tray_app folder may not exist at: %~dp0tray_app 1>&2
    pause
    exit /b 1
)

REM Check if Python is available
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python not found in PATH
    pause
    exit /b 1
)

REM Check if dependencies are installed
python -c "import pystray, PIL, requests" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing dependencies...
    
    REM Verify requirements.txt exists
    if not exist "requirements.txt" (
        echo ERROR: requirements.txt not found in %CD%
        pause
        exit /b 1
    )
    
    REM Check if pip is available
    python -m pip --version >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: pip is not available. Please install pip or use 'python -m ensurepip'
        pause
        exit /b 1
    )
    
    REM Install dependencies and capture exit code
    python -m pip install -r requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Failed to install dependencies from requirements.txt
        echo Please check the error messages above and resolve any issues
        pause
        exit /b 1
    )
    
    echo Dependencies installed successfully
)

REM Start the tray application
python ai_tray.py
