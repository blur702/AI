' AI Dashboard Startup Script
' Runs the dashboard and required services silently on Windows startup

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Compute backend path relative to script location
' Script is in D:\AI, backend is in D:\AI\dashboard\backend
ScriptPath = FSO.GetParentFolderName(WScript.ScriptFullName)
BackendPath = FSO.BuildPath(ScriptPath, "dashboard\backend")

' Resolve Python executable from environment or PATH
PythonExe = WshShell.ExpandEnvironmentStrings("%PYTHON_HOME%")
If PythonExe = "%PYTHON_HOME%" Or PythonExe = "" Then
    ' PYTHON_HOME not set, try AI_DASHBOARD_PYTHON or fall back to PATH
    PythonExe = WshShell.ExpandEnvironmentStrings("%AI_DASHBOARD_PYTHON%")
    If PythonExe = "%AI_DASHBOARD_PYTHON%" Or PythonExe = "" Then
        PythonExe = "python"
    End If
Else
    ' PYTHON_HOME is set, append python.exe
    PythonExe = FSO.BuildPath(PythonExe, "python.exe")
End If

' Resolve Docker Desktop path (allow override via DOCKER_DESKTOP_EXE)
Dim DockerDesktopPath, dockerInstallDir
DockerDesktopPath = WshShell.ExpandEnvironmentStrings("%DOCKER_DESKTOP_EXE%")
If DockerDesktopPath = "%DOCKER_DESKTOP_EXE%" Or DockerDesktopPath = "" Then
    ' Try to read Docker install location from registry
    On Error Resume Next
    dockerInstallDir = WshShell.RegRead("HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop\InstallLocation")
    If Err.Number <> 0 Then
        Err.Clear
        dockerInstallDir = ""
    End If
    On Error GoTo 0

    If dockerInstallDir <> "" Then
        DockerDesktopPath = FSO.BuildPath(dockerInstallDir, "Docker Desktop.exe")
    End If
End If

If DockerDesktopPath = "%DOCKER_DESKTOP_EXE%" Or DockerDesktopPath = "" Then
    ' Fallback to default installation path
    DockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
End If

' Track whether Docker is available
Dim DockerAvailable
DockerAvailable = False

' Start Ollama service if not running (can run without Docker)
WshShell.Run "cmd /c sc query Ollama | find ""RUNNING"" >nul || net start Ollama", 0, False

' Start the dashboard backend FIRST (Flask on port 80) - critical service
' This ensures dashboard starts even if Docker/Ollama have issues
' IMPORTANT: Requires DASHBOARD_AUTH_USERNAME and DASHBOARD_AUTH_PASSWORD environment variables
' Set these via System Properties > Environment Variables or in a .env file in dashboard\backend
' Use quoted paths to handle spaces
WshShell.Run "cmd /c cd /d """ & BackendPath & """ && """ & PythonExe & """ app.py", 0, False

' Wait a moment for dashboard to initialize
WScript.Sleep 2000

' Load Ollama model with error logging
' Attempts to load the model and logs any failures
Dim OllamaLogPath, OllamaCmd
OllamaLogPath = FSO.BuildPath(ScriptPath, "logs\ollama_startup.log")
OllamaCmd = "cmd /c (ollama run qwen3-coder:30b --keepalive 24h ""exit"" 2>&1 || (echo %date% %time% - Failed to load model >> """ & OllamaLogPath & """ && ollama pull qwen3-coder:30b >> """ & OllamaLogPath & """ 2>&1))"
WshShell.Run OllamaCmd, 0, False

' --- Docker Services (optional, non-blocking) ---
' These are started AFTER the dashboard to ensure dashboard always starts

' Check if Docker Desktop exists before trying to start it
If FSO.FileExists(DockerDesktopPath) Then
    ' Start Docker Desktop if not already running
    WshShell.Run "cmd /c docker info >nul 2>&1 || start """" """ & DockerDesktopPath & """", 0, False

    ' Wait for Docker in background (up to 60 seconds)
    Dim attempts
    For attempts = 1 To 12
        WScript.Sleep 5000
        If WshShell.Run("cmd /c docker info >nul 2>&1", 0, True) = 0 Then
            DockerAvailable = True
            Exit For
        End If
    Next

    ' Start Docker-dependent services if Docker is available
    If DockerAvailable Then
        ' Start the Open WebUI container if it exists but is stopped
        WshShell.Run "cmd /c docker start open-webui 2>nul", 0, False
    End If
End If

' Optional: Open browser after a delay
' WScript.Sleep 3000
' WshShell.Run "http://localhost", 1, False
