# Windows System Tray Utility for AI Services

## Overview
Create a lightweight Windows system tray application that provides quick access to:
- Start/Stop AI services
- View and manage GPU VRAM usage
- Unload Ollama models to free VRAM

## Technology Choice: `pystray` + `requests`

**Why `pystray`:**
- Pure Python, lightweight (~50KB)
- Native Windows system tray integration
- Works with existing Python 3.14 installation
- No heavy GUI framework needed (no tkinter/PyQt/wxPython)
- Simple menu-based interface - perfect for quick actions

**Alternative considered:**
- `infi.systray` - similar but less maintained
- `wxPython` - overkill for a tray app
- Electron - too heavy

## Architecture

```
D:\AI\
├── tray_app/
│   ├── ai_tray.py          # Main tray application
│   ├── api_client.py       # HTTP client for dashboard API
│   ├── icons/
│   │   ├── ai_tray.ico     # Main tray icon
│   │   ├── ai_tray_busy.ico # Icon when service is starting
│   │   └── ai_tray_error.ico # Icon for error state
│   └── requirements.txt    # pystray, Pillow, requests
├── start_tray.bat          # Launch script
└── start_tray.vbs          # Silent launch for startup
```

## Features

### 1. Right-Click Menu Structure
```
AI Services Manager
├── Services ►
│   ├── AllTalk TTS      [Running] ►
│   │   ├── Stop
│   │   └── Open in Browser
│   ├── ComfyUI          [Stopped] ►
│   │   └── Start
│   ├── Wan2GP Video     [Stopped] ►
│   │   └── Start
│   ├── YuE Music        [Stopped] ►
│   │   └── Start
│   ├── DiffRhythm       [Stopped] ►
│   │   └── Start
│   ├── MusicGen         [Stopped] ►
│   │   └── Start
│   ├── Stable Audio     [Stopped] ►
│   │   └── Start
│   └── N8N              [Stopped] ►
│       └── Start
├── ─────────────
├── VRAM: 5.2 GB / 24 GB (21%)
├── Loaded Models ►
│   ├── qwen2.5:7b (4.5 GB)  ► Unload
│   └── nomic-embed-text     ► Unload
├── Unload All Models
├── ─────────────
├── Open Dashboard
├── ─────────────
└── Exit
```

### 2. Tooltip
Shows quick status: "AI Services: 2 running | VRAM: 5.2GB/24GB"

### 3. Left-Click Action
Opens the web dashboard in default browser

### 4. Background Polling
- Poll `/api/services` every 10 seconds for service status
- Poll `/api/resources/summary` every 10 seconds for VRAM/models
- Update menu and tooltip dynamically

## Implementation Steps

1. **Create `tray_app/api_client.py`**
   - `get_services()` - fetch all service statuses
   - `start_service(id)` - start a service
   - `stop_service(id)` - stop a service
   - `get_vram_status()` - get GPU info
   - `get_loaded_models()` - get Ollama models in VRAM
   - `unload_model(name)` - unload an Ollama model

2. **Create `tray_app/ai_tray.py`**
   - System tray icon using `pystray`
   - Dynamic menu generation based on API responses
   - Background thread for status polling
   - Notifications for service state changes (optional)

3. **Create icon files**
   - Simple .ico files (can be generated from emoji or simple shapes)

4. **Create launcher scripts**
   - `start_tray.bat` - visible launch
   - `start_tray.vbs` - silent launch for startup folder

5. **Update `dashboard_startup.vbs`**
   - Add tray app launch after dashboard starts

## Dependencies
```
pystray>=0.19.0
Pillow>=10.0.0
requests>=2.31.0
```

## API Endpoints Used
All endpoints already exist in the dashboard backend:
- `GET /api/services` - list services with status
- `POST /api/services/<id>/start` - start service
- `POST /api/services/<id>/stop` - stop service
- `GET /api/resources/summary` - GPU info + loaded models
- `POST /api/models/ollama/unload` - unload model

## Notes
- The tray app communicates with the existing dashboard backend on port 80
- If dashboard is not running, tray will show error state
- No duplicate logic - all operations go through the API
