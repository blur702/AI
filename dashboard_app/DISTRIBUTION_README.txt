================================================================================
                          AI Dashboard for Windows
================================================================================

A desktop application for managing AI services, monitoring GPU resources, and
controlling Ollama models.

FEATURES
--------
- Start/stop AI services (ComfyUI, Ollama, Weaviate, etc.)
- Real-time GPU VRAM monitoring
- Load/unload Ollama models
- Auto-stop idle GPU-intensive services
- Dark/light theme support

SYSTEM REQUIREMENTS
-------------------
- Windows 10/11 (64-bit)
- NVIDIA GPU with drivers installed
- 8GB RAM minimum (16GB recommended)
- 24GB VRAM recommended for AI services

REQUIRED DEPENDENCIES
---------------------
Before running AI Dashboard, install these tools:

1. NVIDIA Drivers
   Download: https://www.nvidia.com/Download/index.aspx
   Required for GPU monitoring (`nvidia-smi`)

2. Ollama (for LLM models)
   Download: https://ollama.ai/download
   Required for model management

3. Docker Desktop (optional, for Weaviate)
   Download: https://www.docker.com/products/docker-desktop
   Required only if using Weaviate vector database

INSTALLATION
------------
1. Install the required dependencies above.
2. Run `AI Dashboard.exe`.
3. The application will start and show the dashboard.

FIRST RUN
---------
On first run, the application will:
- Create a config file at: %APPDATA%\DashboardApp\config.json
- Create a log file at: %APPDATA%\DashboardApp\dashboard_app.log
- Scan for available services based on configuration.

USAGE
-----
Dashboard Tab:
  - View all services grouped by category.
  - Click "Start" to launch a service.
  - Click "Stop" to shut down a service.
  - Click "Open" to open a service in your browser.
  - Expand the "Resources" panel to see GPU stats and processes.

Models Tab:
  - View all Ollama models.
  - Load models into VRAM using Ollama.
  - Unload models to free VRAM.

Settings Tab:
  - Configure auto-stop for idle GPU-intensive services.
  - Set idle timeout (5–120 minutes).

CONFIGURATION
-------------
Config file: %APPDATA%\DashboardApp\config.json

To reset settings, delete the config file and restart the app.

LOGS
----
Log file: %APPDATA%\DashboardApp\dashboard_app.log

Check logs if services fail to start or errors occur.

TROUBLESHOOTING
---------------
Q: Services won't start  
A: Check that service paths exist and Python environments for services are installed.

Q: GPU stats not showing  
A: Install NVIDIA drivers and verify `nvidia-smi` works in a command prompt.

Q: Ollama models not listed  
A: Ensure Ollama is installed and its service is running (http://localhost:11434).

Q: Application won't start  
A: Check logs at %APPDATA%\DashboardApp\dashboard_app.log.

SUPPORT
-------
Common paths:
- Config: %APPDATA%\DashboardApp\config.json
- Logs: %APPDATA%\DashboardApp\dashboard_app.log

================================================================================

