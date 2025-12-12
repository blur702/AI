@echo off
REM Start MCP Documentation Search Server
REM This server provides semantic search over code and documentation via Weaviate

echo ============================================
echo Starting MCP Documentation Search Server
echo ============================================

cd /d D:\AI

REM Activate the api_gateway venv (contains required dependencies)
call api_gateway\venv\Scripts\activate.bat

REM Set environment variables
set WEAVIATE_URL=http://localhost:8080
set OLLAMA_API_ENDPOINT=http://127.0.0.1:11434
set OLLAMA_EMBEDDING_MODEL=snowflake-arctic-embed:l
set LOG_LEVEL=INFO

echo.
echo Environment:
echo   WEAVIATE_URL=%WEAVIATE_URL%
echo   OLLAMA_API_ENDPOINT=%OLLAMA_API_ENDPOINT%
echo   OLLAMA_EMBEDDING_MODEL=%OLLAMA_EMBEDDING_MODEL%
echo.

REM Start the MCP server (STDIO mode)
python -m mcp_servers.documentation.main

pause
