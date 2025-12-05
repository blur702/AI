@echo off
echo Starting AI Services Dashboard on port 80...
echo.
echo Access from this machine: http://localhost
echo Access from network: http://10.0.0.138
echo.
echo Press Ctrl+C to stop the server.
echo.
cd /D "D:\AI"
python -m http.server 80 --bind 0.0.0.0
