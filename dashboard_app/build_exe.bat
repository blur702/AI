@echo off
setlocal enabledelayedexpansion

REM NOTE: This script installs packages into the currently active Python
REM environment. It is strongly recommended to run it inside a dedicated
REM virtual environment to avoid polluting your global Python installation.

echo ============================================
echo AI Dashboard - Windows Executable Builder
echo ============================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

echo [1/5] Checking dependencies...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install "pyinstaller>=6.0.0"
)

echo.
echo [2/5] Installing requirements into the current Python environment...
pip install -r requirements.txt

echo.
echo [3/5] Validating external dependencies...
REM Check nvidia-smi
nvidia-smi --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] nvidia-smi not found. GPU monitoring will not work.
    echo Install NVIDIA drivers from: https://www.nvidia.com/Download/index.aspx
)

REM Check ollama
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama not found. Model management will not work.
    echo Install Ollama from: https://ollama.ai/download
)

REM Check docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Docker not found. Weaviate service will not work.
    echo Install Docker Desktop from: https://www.docker.com/products/docker-desktop
)

echo.
echo [4/5] Building executable with PyInstaller...
pyinstaller dashboard_app.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check the output above for errors.
    pause
    exit /b 1
)

echo.
echo [5/5] Build complete!
echo.
echo Executable location: dist\AI Dashboard.exe
echo.
echo ============================================
echo Next Steps:
echo 1. Test the executable: dist\"AI Dashboard.exe"
echo 2. Check logs at: %%APPDATA%%\DashboardApp\dashboard_app.log
echo 3. See BUILD_GUIDE.md for distribution instructions
echo ============================================
echo.
pause
