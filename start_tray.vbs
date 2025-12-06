' AI Services System Tray Utility - Silent Launch
' This script starts the tray application without showing a console window
' Place a shortcut to this file in the Windows Startup folder for auto-start

Dim WshShell, scriptDir, trayDir, FSO
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located
scriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
trayDir = scriptDir & "\tray_app"

' Change to the tray app directory and run
If Not FSO.FolderExists(trayDir) Then
    MsgBox "Error: tray_app folder not found at " & trayDir, vbCritical, "Tray Launcher Error"
    WScript.Quit 1
End If

WshShell.CurrentDirectory = trayDir

If Not FSO.FileExists("ai_tray.py") Then
    MsgBox "Error: ai_tray.py not found in " & trayDir, vbCritical, "Tray Launcher Error"
    WScript.Quit 1
End If

' Run Python with the tray app (0 = hidden window)
On Error Resume Next
WshShell.Run "python ai_tray.py", 0, False
If Err.Number <> 0 Then
    MsgBox "Error launching tray app: " & Err.Description & vbCrLf & vbCrLf & "Make sure Python is installed and in PATH.", vbCritical, "Tray Launcher Error"
    WScript.Quit 1
End If
On Error Goto 0

Set WshShell = Nothing
