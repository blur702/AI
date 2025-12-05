@echo off
cd /d D:\AI\api_gateway
if not exist venv (
  echo Virtual environment not found. Please run setup_gateway.bat first.
  exit /b 1
)
call venv\Scripts\activate.bat
python -m api_gateway.main

