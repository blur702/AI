# AI Dashboard - Build & Distribution Guide

## Overview

This guide covers building the AI Dashboard as a standalone Windows executable using PyInstaller.

## System Requirements

### Build Machine

- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.10 or higher (ideally in a dedicated virtual environment)
- **RAM**: 4GB minimum
- **Disk**: 2GB free space

### Runtime Dependencies (Required on Target Machine)

The executable requires these external tools to be installed:

1. **NVIDIA Drivers** (for GPU monitoring)
   - Download: https://www.nvidia.com/Download/index.aspx
   - Provides `nvidia-smi` command
   - Required for VRAM monitoring and GPU process tracking

2. **Ollama** (for LLM model management)
   - Download: https://ollama.ai/download
   - Provides `ollama` command
   - Required for loading/unloading models

3. **Docker Desktop** (for Weaviate service, optional)
   - Download: https://www.docker.com/products/docker-desktop
   - Provides `docker` and `docker-compose` commands
   - Required only if using Weaviate vector database

4. **AI Services** (optional, as needed)
   - ComfyUI, Wan2GP, YuE, MusicGen, etc.
   - See `dashboard/backend/services_config.py` for full list
   - Each service must be installed at the configured path

---

## Building the Executable

### Step 1: Prepare Environment

```bash
cd d:\AI\dashboard_app

# (Recommended) Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate
```

### Step 2: Run Build Script

```bash
build_exe.bat
```

The script will:

1. Check Python installation
2. Install/update dependencies into the currently active Python environment
3. Validate external tools (nvidia-smi, ollama, docker)
4. Build the executable using PyInstaller and `dashboard_app.spec`
5. Output to `dist\AI Dashboard.exe`

**Build time**: ~2-5 minutes depending on system

### Step 3: Verify Build

Check that the executable was created:

```bash
dir dist\"AI Dashboard.exe"
```

Expected size: ~15-25 MB (compressed with UPX)

---

## Testing the Executable

### Local Testing

1. Run the executable:

   ```bash
   dist\"AI Dashboard.exe"
   ```

2. Check logs:

   ```
   %APPDATA%\DashboardApp\dashboard_app.log
   ```

3. Verify functionality:
   - Window opens with Dashboard, Models, and Settings tabs
   - Resource panel shows GPU stats (if `nvidia-smi` available)
   - Service cards display with start/stop buttons
   - Models tab lists Ollama models (if Ollama running)

### Clean System Testing

Test on a machine without Python installed:

1. Copy `dist\AI Dashboard.exe` to test machine
2. Install runtime dependencies (NVIDIA drivers, Ollama, Docker)
3. Run the executable
4. Verify all features work

**Common issues**:

- `"nvidia-smi" not found`: Install NVIDIA drivers
- `"ollama" not found`: Install Ollama
- Services won't start: Check service paths in `services_config.py`

---

## Distribution

### Option 1: Standalone Executable

Distribute just the `.exe` file.

**Pros**:

- Single file, easy to share
- No installer required

**Cons**:

- Users must install runtime dependencies separately
- Service paths must match configuration

**Instructions for users**:

1. Download `AI Dashboard.exe`
2. Install NVIDIA drivers, Ollama, Docker
3. Run the executable

### Option 2: Installer Package

Create an installer with Inno Setup or NSIS.

**Include**:

- `AI Dashboard.exe`
- `DISTRIBUTION_README.txt` with setup instructions
- Links to download runtime dependencies

**Pros**:

- Professional installation experience
- Can set up shortcuts and registry entries

**Cons**:

- More complex to create
- Larger download size

### Option 3: Portable Package

Create a ZIP:

```text
AI-Dashboard-Portable/
├── AI Dashboard.exe
├── DISTRIBUTION_README.txt
└── logs/ (optional)
```

**Pros**:

- No installation needed
- Can run from USB drive

**Cons**:

- Users must manually install dependencies

---

## Configuration

### Application Config

Stored at: `%APPDATA%\DashboardApp\config.json`

**Settings**:

- Window size and position
- Last selected tab
- Theme (dark/light)
- Polling intervals
- Auto-stop configuration

**Reset config**: Delete `config.json` to restore defaults.

### Service Paths

Defined in: `dashboard/backend/services_config.py`

To customize:

1. Edit `services_config.py` before building
2. Or set `AI_ROOT_DIR` environment variable at runtime:

   ```bash
   set AI_ROOT_DIR=E:\MyAI
   "AI Dashboard.exe"
   ```

---

## Troubleshooting

### Build Errors

- **"Module not found"**:
  - Add it to `hiddenimports` in `dashboard_app.spec`
  - Rebuild with `--clean`

- **"Icon file not found"**:
  - Verify `assets\icon.ico` exists
  - Check `icon` path in spec file

### Runtime Errors

- **"Failed to execute script"**:
  - Run from command prompt to see error details:

    ```bash
    "AI Dashboard.exe"
    ```

  - Check logs at `%APPDATA%\DashboardApp\dashboard_app.log`

- **Service won't start**:
  - Verify service path exists
  - Check working directory in `services_config.py`
  - Ensure Python venv exists for the service

- **GPU stats not showing**:
  - Install NVIDIA drivers
  - Run `nvidia-smi` in a command prompt to verify

---

## File Structure

```text
dashboard_app/
├── main.py                 # Entry point
├── dashboard_app.spec      # PyInstaller spec file
├── build_exe.bat           # Build script
├── requirements.txt        # Python dependencies
├── BUILD_GUIDE.md          # This file
├── assets/
│   └── icon.ico           # Application icon
├── controllers/
├── views/
├── utils/
└── config.py
```

Build artifacts (generated):

```text
build/                      # Temporary build files (can delete)
dist/
└── AI Dashboard.exe        # Final executable
```

---

## Maintenance

### Updating the Executable

1. Make code changes
2. Run `build_exe.bat`
3. Test the new executable
4. Distribute updated `.exe`

### Dependency Updates

Update `requirements.txt`:

```bash
pip install --upgrade requests psutil pyinstaller
pip freeze > requirements.txt
```

Rebuild to include updated dependencies.

---

## Support

- Core Python dependencies such as `requests` and `psutil` are managed via
  `requirements.txt` and are bundled into the executable by PyInstaller.

- Logs: `%APPDATA%\DashboardApp\dashboard_app.log`
- Config: `%APPDATA%\DashboardApp\config.json`

Common paths:

- `%APPDATA%` = `C:\Users\<username>\AppData\Roaming`
- `%LOCALAPPDATA%` = `C:\Users\<username>\AppData\Local`
