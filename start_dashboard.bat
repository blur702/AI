@echo off
echo Starting AI Services Dashboard...
echo.

REM Single-port deployment: Flask serves both frontend and API on port 80
echo Starting dashboard on port 80 (frontend + API)...
start /B cmd /c "cd /d D:\AI\dashboard\backend && C:\Python314\python.exe app.py"

REM Wait a moment for server to start
timeout /t 2 /nobreak > nul

echo.
echo Dashboard started!
echo   Dashboard: http://localhost (port 80)
echo   API: http://localhost/api
echo   Access from network: http://10.0.0.138
echo   External access: http://ssdd.kevinalthaus.com
echo.
echo Press any key to exit (services will continue running)...
pause > nul
