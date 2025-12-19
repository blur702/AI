# AI Dashboard - Testing Checklist

## Pre-Build Testing

- [ ] All Python files have no syntax errors.
- [ ] `main.py` runs successfully with `python main.py`.
- [ ] All imports resolve correctly from project root.
- [ ] Config file is created at `%APPDATA%\DashboardApp\config.json`.
- [ ] Logs are written to `%APPDATA%\DashboardApp\dashboard_app.log`.

## Build Testing

- [ ] `build_exe.bat` completes without errors.
- [ ] Executable is created at `dist\AI Dashboard.exe`.
- [ ] Executable size is reasonable (~15–25 MB).
- [ ] No "module not found" warnings in build output.

## Functional Testing (With Python Installed)

### Window & UI

- [ ] Application window opens.
- [ ] Window title is "AI Dashboard".
- [ ] Icon displays correctly in the taskbar.
- [ ] Tabs: Dashboard, Models, Settings are visible.
- [ ] Window is resizable.
- [ ] Window position/size persists across restarts.

### Dashboard Tab

- [ ] Resource panel displays.
- [ ] GPU stats show (if `nvidia-smi` available).
- [ ] Service cards display grouped by section.
- [ ] Service icons and names display correctly.
- [ ] Start/Stop buttons are functional.
- [ ] Open button launches browser to service URL.
- [ ] Service status updates in near real time.

### Models Tab

- [ ] Ollama models list displays (if Ollama running).
- [ ] Load operations succeed for unloaded models.
- [ ] Unload operations succeed for loaded models.
- [ ] Model status updates after load/unload.
- [ ] VRAM usage responds to model load/unload.

### Settings Tab

- [ ] Auto-stop toggle reflects current configuration.
- [ ] Timeout dropdown shows options (5, 15, 30, 60, 120 min).
- [ ] Auto-stop settings persist across restarts.

### Resource Panel

- [ ] Expand/collapse works.
- [ ] GPU name / summary displays.
- [ ] VRAM bar shows usage percentage.
- [ ] Loaded models list updates.
- [ ] GPU processes list updates.
- [ ] Unload button works for selected loaded model.
- [ ] Auto-stop controls reflect and update config.

### Logging

- [ ] Log file is created.
- [ ] Service start/stop events are logged.
- [ ] Auto-stop actions are logged.
- [ ] Errors include stack traces where applicable.
- [ ] Log rotation works around the 10MB limit.

## Clean System Testing (Without Python)

### Prerequisites

- [ ] Test machine has no Python in PATH.
- [ ] NVIDIA drivers installed and `nvidia-smi` works.
- [ ] Ollama installed and running.
- [ ] Docker Desktop installed (if testing Weaviate).

### Basic Functionality

- [ ] Executable runs without errors.
- [ ] No "Python not found" errors.
- [ ] No "Module not found" errors.
- [ ] UI behaves as expected.

### Service Management

- [ ] Can start at least one service.
- [ ] Health checks change status appropriately.
- [ ] Can stop running services.
- [ ] Port conflict detection works.

### GPU Monitoring

- [ ] Multi-GPU systems show aggregate VRAM stats.
- [ ] Single-GPU systems show correct VRAM usage.
- [ ] GPU process list lists active compute processes.

### Ollama Integration

- [ ] Ollama API is reachable.
- [ ] Models tab lists available models.
- [ ] Load operations work for selected models.
- [ ] Unload operations free VRAM and update status.

## Performance Testing

- [ ] Application starts in under 5 seconds.
- [ ] UI remains responsive while services start/stop.
- [ ] Polling intervals do not cause noticeable lag.
- [ ] Idle CPU usage stays low (< 5%).
- [ ] Memory usage is reasonable (< 200MB idle).

## Error Handling

- [ ] Graceful handling when `nvidia-smi` is missing.
- [ ] Graceful handling when Ollama is not running.
- [ ] Graceful handling when Docker is not available.
- [ ] Service startup failures show user-friendly messages.
- [ ] Port conflicts are logged and surfaced in UI.

## Edge Cases

- [ ] Works with no GPU (VRAM panel shows appropriate warning).
- [ ] Works with Ollama disabled (Models tab degrades gracefully).
- [ ] Works with Docker disabled (Weaviate-related controls degrade gracefully).
- [ ] Handles service crash during startup.
- [ ] Handles service crash while running.

## Cleanup Testing

- [ ] Closing app stops managed subprocesses when appropriate.
- [ ] Config is saved on close.
- [ ] No orphaned processes remain after exit.

## Distribution Testing

- [ ] Executable works when copied to a different directory.
- [ ] Executable works on a fresh Windows machine.
- [ ] Executable runs from a USB drive.
- [ ] Executable runs from a network share (if applicable).

## Documentation Testing

- [ ] `BUILD_GUIDE.md` matches actual build behavior.
- [ ] `DISTRIBUTION_README.txt` is accurate and clear.
- [ ] All links in documentation are valid.

---

## Test Results Template

```text
Test Date: _______________
Tester: _______________
Build Version: _______________
Test Machine: _______________

Passed: ___ / ___
Failed: ___ / ___

Failed Tests:
1. _______________
2. _______________

Notes:
_______________
_______________
```
