@echo off
REM Start Ollama keep-alive script in background
REM Keeps qwen3-coder:30b loaded for 24 hours

start "Ollama Keep-Alive" /min powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\AI\scripts\ollama-keepalive.ps1"
echo Ollama keep-alive started in background
