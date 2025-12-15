# VRAM Monitor & Ollama Manager

A lightweight VS Code extension that surfaces NVIDIA GPU VRAM usage, Ollama model status, and resource controls by delegating telemetry to `vram_manager.py` and integrating with the Ollama API.

## Features

- **Real-time VRAM monitoring** every 3 seconds via `vram_manager.py --json`
- **Status bar indicator** with color-coded VRAM (green/yellow/red thresholds)
- **Interactive dashboard** (sidebar WebView) with collapsible sections for GPU usage, loaded/available models, and processes
- **Ollama model management**: load/unload models via QuickPick, dashboard buttons, or commands
- **Configurable visibility**: toggles to show or hide individual stats and sections
- **Diagnostics commands** that reveal poll/activity logs and Ollama connectivity status
- **Graceful degradation**: works when Ollama is offline or no GPU is detected

## Requirements

1. Python 3.x (`python` or custom path) with access to `vram_manager.py`
2. NVIDIA GPU and `nvidia-smi` available on the system `PATH`
3. Ollama CLI installed and running (`ollama serve`) for model management features
4. VS Code 1.85.0 or newer

## Installation

### From a VSIX
1. Run `npm run package` to create `vscode-vram-monitor-0.1.0.vsix`
2. Open Extensions view (`Ctrl+Shift+X`), click the ellipsis menu, choose **Install from VSIX...**, and select the package

### From Source
```bash
cd vscode-vram-monitor
npm install
npm run compile
# Launch the Extension Development Host with F5
```

## Usage

### Status Bar
- Displays `GPU: used / total (util%)` with colors (green <50%, yellow 50-80%, red >=80%)
- Clicking the status bar opens the VRAM Monitor dashboard sidebar
- Toggle visibility with `VRAM Monitor: Toggle Status Bar`

### Commands

| Command | Description |
| --- | --- |
| `VRAM Monitor: Show Dashboard` | Open the dashboard sidebar |
| `VRAM Monitor: Refresh Stats` | Force an immediate poll |
| `VRAM Monitor: Load Ollama Model` | Choose from available models to load |
| `VRAM Monitor: Unload All Ollama Models` | Evict every loaded model from Ollama VRAM |
| `VRAM Monitor: Toggle Status Bar` | Show or hide the status bar badge |
| `VRAM Monitor: Show Ollama Diagnostics` | Display Ollama health, models, and errors |
| `VRAM Monitor: Show Output` | Reveal the output channel for polling logs |
| `VRAM Monitor: Show Diagnostics` | Dump VRAM Monitor diagnostics and cached data |

### Dashboard
- **GPU Stats**: Progress bar + stats row powered by GPU utilization
- **Loaded Models**: List current models with unload buttons
- **Available Models**: Filterable list with load buttons
- **GPU Processes**: Table of active GPU processes
- **Refresh**: Trigger manual update via toolbar button

## Configuration

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| `vramMonitor.pythonPath` | string | `python` | Python interpreter path |
| `vramMonitor.vramManagerPath` | string | `${workspaceFolder}/vram_manager.py` | Path to VRAM telemetry script |
| `vramMonitor.pollInterval` | number | `3000` | Polling interval (ms, min 1000) |
| `vramMonitor.ollamaUrl` | string | `http://localhost:11434` | Ollama HTTP API URL |
| `vramMonitor.ollamaLoadTimeout` | number | `60000` | Model loading timeout (ms) |
| `vramMonitor.ollamaHealthCheckTimeout` | number | `5000` | Health check timeout (ms) |
| `vramMonitor.showTotalVRAM` | boolean | `true` | Show total VRAM |
| `vramMonitor.showUsedVRAM` | boolean | `true` | Show used VRAM |
| `vramMonitor.showFreeVRAM` | boolean | `true` | Show free VRAM |
| `vramMonitor.showUtilization` | boolean | `true` | Show GPU utilization |
| `vramMonitor.showLoadedModels` | boolean | `true` | Show loaded model count |
| `vramMonitor.showGPUProcesses` | boolean | `true` | Show GPU process table |
| `vramMonitor.showGPUName` | boolean | `true` | Show GPU name |
| `vramMonitor.showProgressBar` | boolean | `true` | Show VRAM progress bar |

## Development

- Build: `npm run compile`
- Watch: `npm run watch`
- Package: `npm run package`
- Debug: Press F5 in VS Code to launch the Extension Development Host

## License

Released under the [MIT License](LICENSE).
