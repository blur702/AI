# AI Dashboard Setup and Configuration

This document summarizes the setup, configuration, and automation features implemented for the AI Services Dashboard.

## Overview

The AI Dashboard is a unified control center for managing multiple AI generation services (audio, image, music, video, text-to-speech, and LLM) designed for an RTX 3090 (24GB VRAM). The architecture follows a master-satellite pattern where a central dashboard orchestrates independent AI services.

---

## 1. Single-Port Architecture

The dashboard uses a **single-port deployment** where Flask serves both the React frontend and API on port 80.

### Benefits
- External access via domain without exposing multiple ports
- Simplified firewall configuration
- Single entry point for all dashboard functionality

### Structure
- **Frontend**: `http://localhost/` (React SPA from `frontend/dist/`)
- **API**: `http://localhost/api/*`
- **WebSocket**: `http://localhost/socket.io/`

---

## 2. Resource Manager

A collapsible panel in the dashboard UI that displays real-time GPU and service information.

### Features
- **GPU VRAM Display**: Shows total, used, and free VRAM with visual bar
- **Loaded LLM Models**: Lists Ollama models currently in VRAM with unload buttons
- **GPU Processes**: Shows all processes using GPU memory
- **Running Services**: Displays active services with idle time tracking
- **Auto-Stop Settings**: Configure automatic shutdown of idle GPU-intensive services

### Files
- `dashboard/frontend/src/components/ResourceManager.tsx`
- `dashboard/frontend/src/components/ResourceManager.css`
- `dashboard/frontend/src/types/index.ts` (types for GPU, processes, models)

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/resources/summary` | GET | GPU info, loaded models, processes, services |
| `/api/resources/settings` | GET/POST | Auto-stop configuration |
| `/api/services/<id>/touch` | POST | Update service activity timestamp |

---

## 3. Idle Service Auto-Stop

Automatically stops GPU-intensive services after a configurable idle period.

### Configuration Options
- **Enable/Disable**: Toggle auto-stop functionality
- **Timeout Values**: 5, 15, 30, 60, or 120 minutes

### Implementation
- Service activity is tracked via `last_activity` timestamp
- Background thread checks idle times periodically
- Only GPU-intensive services are auto-stopped

### Files
- `dashboard/backend/service_manager.py` - Idle tracking and auto-stop logic

---

## 4. Windows Auto-Start

The dashboard automatically starts on Windows boot.

### Components

#### Startup Script (`dashboard_startup.vbs`)
VBScript that runs silently on Windows startup:
1. Starts Docker Desktop if not running
2. Waits for Docker to initialize
3. Starts the `open-webui` container
4. Starts the Ollama service
5. Launches the Flask dashboard backend

#### Shortcut Creator (`create_startup_shortcut.ps1`)
PowerShell script that creates a shortcut in the Windows Startup folder:
```powershell
.\create_startup_shortcut.ps1
```

### Location
Shortcut installed at: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AI Dashboard.lnk`

---


## 6. Firewall Configuration

Windows Firewall rules for all AI service ports.

### Script (`configure_firewall.ps1`)
Run as Administrator to create inbound rules:
```powershell
# Right-click PowerShell > Run as Administrator
.\configure_firewall.ps1
```

### Configured Ports

| Port | Service | Description |
|------|---------|-------------|
| 80 | Dashboard | Flask serves React + API + WebSocket |
| 1301 | API Gateway | FastAPI unified API |
| 3000 | Open WebUI | LLM chat interface |
| 5678 | N8N | Workflow automation |
| 7851 | AllTalk TTS | Text-to-speech |
| 7860 | Wan2GP | Video generation |
| 7870 | YuE | Music generation |
| 7871 | DiffRhythm | Rhythm music |
| 7872 | MusicGen | Meta AudioCraft |
| 7873 | Stable Audio | Audio generation |
| 8188 | ComfyUI | Image generation |
| 11434 | Ollama | Local LLM API |

### Verify Rules
```powershell
Get-NetFirewallRule -DisplayName 'AI *' | Select-Object DisplayName, Enabled
```

---

## 7. Test Suite

Comprehensive Playwright test suite with 129+ tests.

### Run Tests
```bash
npm test                 # All tests (headless)
npm run test:headed      # All tests (headed)
npm run test:api         # API tests only
npm run test:ui          # UI tests only
npm run test:smoke       # Smoke tests
```

### Test Categories
- **API Tests**: Gateway health, generation endpoints, job management
- **UI Tests**: Dashboard display, service navigation, model management
- **Integration Tests**: Cross-service workflows, model switching
- **Service Tests**: Individual service start/stop/generation

---

## 7. File Summary

### Configuration Scripts
| File | Purpose |
|------|---------|
| `configure_firewall.ps1` | Windows Firewall rules (run as admin) |
| `create_startup_shortcut.ps1` | Create dashboard Windows Startup shortcut |
| `dashboard_startup.vbs` | Silent dashboard startup script |
| `start_dashboard.bat` | Manual dashboard launcher |
| `dashboard/backend/app.py` | Flask app with API routes |
| `dashboard/backend/service_manager.py` | Service lifecycle + idle tracking |
| `dashboard/backend/services_config.py` | Service definitions |

### Frontend
| File | Purpose |
|------|---------|
| `dashboard/frontend/src/App.tsx` | Main app with ResourceManager |
| `dashboard/frontend/src/components/ResourceManager.tsx` | GPU/model panel |
| `dashboard/frontend/src/config/services.ts` | API base URL config |
| `dashboard/frontend/src/types/index.ts` | TypeScript interfaces |

---

## 9. Quick Start
### First-Time Setup
1. Configure firewall (as Administrator):
   ```powershell
   .\configure_firewall.ps1
   ```

2. Create dashboard startup shortcut:
   ```powershell
   .\create_startup_shortcut.ps1
   ```

3. Build frontend:
   ```bash
   cd dashboard/frontend
   npm install
   npm run build
   ```

4. (reserved for future use)

### Access
- **Local**: http://localhost
- **External**: http://your-domain.com (port 80 only)

---

## 10. Known Fixes
### MusicGen Compatibility
MusicGen requires `accelerate==0.24.1` due to compatibility issues with newer versions:
```bash
cd D:\AI\audiocraft
audiocraft_env\Scripts\pip install accelerate==0.24.1
```

---

*Last updated: December 2025*
