# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is the **AI Services System Tray Application** - a Windows system tray utility for managing AI services and VRAM from the taskbar. It communicates with the main AI Dashboard backend (Flask on port 80) to display service status and control services.

## Quick Start

**Windows:**
```cmd
# Install dependencies
pip install -r requirements.txt

# Run the tray app directly
python ai_tray.py

# Or use launcher scripts from parent directory
..\start_tray.bat                  # Run with visible console
..\start_tray.vbs                  # Run silently (no console)
```

**Linux/macOS:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run the tray app directly
python ai_tray.py

# Or use launcher script from parent directory
../start_tray.sh                   # Run in background
```

**Portable Configuration:**
Set environment variables to specify installation location:
```bash
# Windows
set TRAY_APP_HOME=C:\path\to\AI\tray_app
cd %TRAY_APP_HOME%
python ai_tray.py

# Linux/macOS
export TRAY_APP_HOME=/path/to/AI/tray_app
cd $TRAY_APP_HOME
python ai_tray.py
```

## Architecture

```
tray_app/
├── ai_tray.py        # Main app using pystray - icon, menu, polling loop
├── api_client.py     # HTTP client wrapping Dashboard REST API
├── requirements.txt  # pystray, Pillow, requests
└── icons/            # Tray icon files (optional)
```

### Components

**AITrayApp** (`ai_tray.py`)
- Creates system tray icon with dynamic color (green=connected, red=offline)
- Builds hierarchical menu: Services → VRAM → Loaded Models → Actions
- Polls dashboard API every 10 seconds in background thread
- Left-click opens dashboard in browser

**DashboardAPI** (`api_client.py`)
- Wraps all Dashboard REST endpoints used by tray
- 5-second timeout for requests
- Returns `None` or empty lists on failure (graceful degradation)

### Dashboard API Endpoints Used

**GET /api/services**
- Returns: `List[{id: str, name: str, status: str, gpu_intensive: bool, port: int, ...}]`
- Status codes: 200 (success), 500 (server error)
- Example response:
  ```json
  [
    {"id": "comfyui", "name": "ComfyUI", "status": "running", "gpu_intensive": true, "port": 8188},
    {"id": "ollama", "name": "Ollama", "status": "stopped", "gpu_intensive": true, "port": 11434}
  ]
  ```

**POST /api/services/<id>/start**
- Returns: `{success: bool, message: str}`
- Status codes: 200 (success), 400 (bad request), 500 (start failed)
- Example response: `{"success": true, "message": "Service started"}`

**POST /api/services/<id>/stop**
- Returns: `{success: bool, message: str}`
- Status codes: 200 (success), 400 (bad request), 500 (stop failed)
- Example response: `{"success": true, "message": "Service stopped"}`

**GET /api/vram/status**
- Returns: `{total_gb: float, used_gb: float, free_gb: float, utilization_percent: float, name: str}`
- Units: Memory values in gigabytes (GB), utilization as percentage (0-100)
- Status codes: 200 (success), 500 (GPU query failed)
- Example response:
  ```json
  {
    "total_gb": 24.0,
    "used_gb": 8.5,
    "free_gb": 15.5,
    "utilization_percent": 35.4,
    "name": "NVIDIA GeForce RTX 4090"
  }
  ```

**GET /api/models/ollama/loaded**
- Returns: `List[{name: str, vram_gb: float, size: str}]`
- Units: vram_gb in gigabytes, size as human-readable string
- Status codes: 200 (success), 500 (Ollama unreachable)
- Example response:
  ```json
  [
    {"name": "llama3.2:3b", "vram_gb": 2.1, "size": "2.1 GB"},
    {"name": "mistral:7b", "vram_gb": 4.8, "size": "4.8 GB"}
  ]
  ```

**POST /api/models/ollama/unload**
- Request body: `{model_name: str}`
- Returns: `{success: bool, message: str}`
- Status codes: 200 (success), 400 (invalid model name), 404 (model not loaded), 500 (unload failed)
- Example response: `{"success": true, "message": "Model unloaded"}`

## Key Configuration

In `ai_tray.py`:
```python
DASHBOARD_URL = "http://localhost"  # Dashboard backend URL
POLL_INTERVAL = 10                  # Seconds between API polls
ICON_SIZE = 64                      # Tray icon dimensions
```

## Dependencies

- **pystray**: System tray icon and menu
- **Pillow**: Icon image generation
- **requests**: HTTP client for Dashboard API

## Development Notes

1. **Dashboard Required**: The tray app depends on the Dashboard backend running on port 80. Start it with `start_dashboard.bat` from `D:\AI\`.

2. **Thread Safety**: Uses `threading.Lock` to protect shared state accessed by both poll thread and menu callbacks.

3. **Graceful Degradation**: If dashboard is unreachable, icon turns red and menu shows limited options.

4. **Windows-Specific**: Uses pystray which has platform-specific behavior. On Windows, left-click opens dashboard; right-click shows menu.

5. **Icon Generation**: Icons are generated dynamically using Pillow (no external icon files required).
