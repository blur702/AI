@echo off
echo Starting Weaviate Vector Database...
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running. Please start Docker Desktop first.
    echo.
    pause
    exit /b 1
)

REM Check if Ollama is running
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo WARNING: Ollama does not appear to be running on port 11434.
    echo Weaviate will start but embeddings will not work until Ollama is available.
    echo.
)

REM Navigate to the script's directory
cd /d "%~dp0"

REM Check if docker-compose is available
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: docker-compose command not found. Please ensure Docker Compose is installed.
    echo.
    pause
    exit /b 1
)

REM Start Weaviate using docker-compose
echo Starting Weaviate container...
docker-compose up -d
if errorlevel 1 (
    echo ERROR: Failed to start Weaviate container. docker-compose exited with code %ERRORLEVEL%
    echo Check Docker Desktop is running and try: docker-compose logs
    echo.
    pause
    exit /b %ERRORLEVEL%
)

REM Wait for Weaviate to be ready
echo Waiting for Weaviate to be ready...
timeout /t 5 /nobreak >nul

REM Check Weaviate health
curl -s http://localhost:8080/v1/.well-known/ready >nul 2>&1
if errorlevel 1 (
    echo WARNING: Weaviate may not be ready yet. Check logs with: docker-compose logs -f
) else (
    echo.
    echo Weaviate is running!
    echo   API: http://localhost:8080
    echo   GraphQL: http://localhost:8080/v1/graphql
    echo   Health: http://localhost:8080/v1/.well-known/ready
)

echo.
echo To stop Weaviate: docker-compose down
echo To view logs: docker-compose logs -f
echo.
pause
