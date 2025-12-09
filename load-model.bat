@echo off
REM Quick launcher for Ollama Model Loader
REM
REM Usage:
REM   load-model                           Interactive menu
REM   load-model qwen3-coder:30b           Load specific model (1 hour keep-alive)
REM   load-model qwen3-coder:30b 7200      Load with custom keep-alive (seconds)
REM   load-model -status                   Show loaded models and VRAM
REM   load-model -list                     List available models
REM   load-model -unload qwen3-coder:30b   Unload a model

setlocal

set "SCRIPT_PATH=%~dp0scripts\ollama-model-loader.ps1"

if "%1"=="-status" (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" -Status
    goto :end
)

if "%1"=="-list" (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" -List
    goto :end
)

if "%1"=="-unload" (
    if "%2"=="" (
        echo Error: missing model name.
        echo Usage: load-model -unload ^<model^>
        exit /b 1
    )
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" -Unload -Model "%2"
    goto :end
)

if "%1"=="" (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_PATH%"
    goto :end
)

REM Load specific model with optional keep-alive
if "%2"=="" (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" -Model "%1"
) else (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" -Model "%1" -KeepAlive %2
)

:end
endlocal
