# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **local AI development workspace** featuring an integrated ecosystem of AI generation tools (audio, image, music, video, text-to-speech, and LLM) designed for RTX 3090 (24GB VRAM). The architecture follows a **master-satellite pattern** where a central dashboard orchestrates independent AI services.

## Key Commands

### Dashboard & Monitoring
```bash
.\start_dashboard.bat              # Launch web dashboard (ports 80 + 5000)
.\start_n8n.bat                    # Launch N8N workflow automation (port 5678)
python vram_manager.py             # GPU VRAM monitoring CLI
.\vram.bat                         # Quick VRAM check
node test_services.js              # Health check all services (uses Playwright)
```

### Dashboard Backend Development
```bash
cd D:\AI\dashboard\backend
pip install -r requirements.txt
python app.py                      # Flask API on port 5000
```

### Ollama Model Management
```bash
ollama list                        # List available models
ollama ps                          # Show loaded models
ollama pull <model>                # Download model
ollama run <model>                 # Load and run
ollama stop <model>                # Unload from VRAM
```

## Architecture

### Service Port Allocation
| Port | Service |
|------|---------|
| 80 | Dashboard frontend |
| 5000 | Dashboard API (Flask + WebSocket) |
| 5678 | N8N workflow automation |
| 3000 | Open WebUI (LLM chat) |
| 8188 | ComfyUI (image generation) |
| 7851 | AllTalk TTS |
| 7860 | Wan2GP Video |
| 7870 | YuE Music |
| 7871 | DiffRhythm |
| 7872 | MusicGen |
| 7873 | Stable Audio |
| 11434 | Ollama API |

### Dashboard API Endpoints
```
GET  /api/vram/status              # GPU memory info
GET  /api/models/ollama/list       # All Ollama models
GET  /api/models/ollama/loaded     # Currently loaded models
POST /api/models/ollama/load       # Load model to GPU
POST /api/models/ollama/unload     # Unload model
POST /api/models/ollama/download   # Download new model

WebSocket Events: vram_update (every 2s), model_download_progress
```

### Project Structure
Each AI project (alltalk_tts, audiocraft, ComfyUI, DiffRhythm, local-talking-llm, stable-audio-tools, MusicGPT, Wan2GP, YuE) has:
- Its own git repository (excluded from root repo)
- Isolated Python virtual environment
- Independent dependencies

VSCode is configured to exclude subprojects from search/watch for performance.

## Critical Development Notes

1. **Virtual Environments**: Always activate the project-specific venv before running any AI tool
2. **VRAM Management**: Monitor constantly - combinations of services can exhaust 24GB
3. **Windows-Specific**: Uses PowerShell, batch scripts, and nvidia-smi
4. **Port Conflicts**: Check port availability before starting services
5. **Project Isolation**: Don't assume unified structure - each subproject is independent

## Documentation

See `docs/` directory for:
- `PROJECT_STRUCTURE.md` - Comprehensive directory and project guide
- `README_N8N.md` - N8N setup and troubleshooting
- `PLAN.md` - Setup guides and VRAM optimization
