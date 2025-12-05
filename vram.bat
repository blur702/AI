@echo off
REM VRAM Model Manager - Quick access batch file
REM Usage:
REM   vram          - Show status
REM   vram -s       - Show status
REM   vram --stop MODEL   - Unload a specific model
REM   vram --stop-all     - Unload all models
REM   vram -l       - List available models
REM   vram -j       - Output as JSON

python "%~dp0vram_manager.py" %*
