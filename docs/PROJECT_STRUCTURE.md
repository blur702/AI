# AI Workspace Project Structure Guide

**Last Updated:** December 5, 2025  
**For:** New LLM Agents/Instances  
**Purpose:** Understanding this integrated AI development workspace

---

## Overview

This workspace (`D:\AI\`) is a comprehensive AI development environment containing multiple specialized AI projects for audio generation, image generation, text-to-speech, and voice assistants. All projects are configured with separate Python virtual environments and are ready to use.

**System Specifications:**
- **GPU:** NVIDIA RTX 3090 (24GB VRAM)
- **OS:** Windows
- **Shell:** PowerShell 5.1

---

## Directory Structure

```
D:\AI\
├── docs/                          # Documentation hub (you are here)
├── alltalk_tts/                   # Text-to-Speech system
├── audiocraft/                    # Audio/music generation (Meta)
├── ComfyUI/                       # Visual AI workflow engine
├── DiffRhythm/                    # Rhythm/music generation
├── local-talking-llm/             # Voice assistant with LLM
├── stable-audio-tools/            # Audio generation tools
├── Wan2GP/                        # Wan to GP conversion
├── YuE/                          # YuE project
├── MusicGPT/                     # Music generation
├── ollama-models/                # Local LLM models storage
├── stability-matrix/             # Package manager for Stable Diffusion
├── dashboard/                    # Service monitoring dashboard
├── screenshots/                  # Project screenshots
├── test-results/                 # Test output files
└── node_modules/                 # Node.js dependencies

Root Files:
├── package.json                  # Node.js project config
├── vram_manager.py              # VRAM monitoring utility
├── vram.bat                     # VRAM check batch script
├── start_dashboard.bat          # Launch monitoring dashboard
├── start_n8n.bat               # Launch n8n workflow automation
├── test_services.js            # Service health checks
└── index.html                  # Main entry point (if web-based)
```

---

## Core Projects

### 1. **alltalk_tts** 
**Purpose:** Advanced Text-to-Speech system with voice cloning  
**Technology:** XTTSv2, Coqui TTS  
**Environment:** `alltalk_tts/alltalk_environment/env/`  
**Python Version:** 3.11  
**Status:** ✅ All dependencies installed, no issues

**Key Features:**
- Voice cloning and fine-tuning
- DeepSpeed acceleration (2-3x performance boost)
- Low VRAM mode for GPU memory management
- Bulk TTS generation
- API server for integration with other tools
- Narrator mode with multiple voices

**Entry Points:**
- `start_alltalk.bat` - Launch TTS server
- `start_environment.bat` - Activate environment
- `tts_server.py` - Main server script
- `script.py` - CLI interface

**Documentation:** Extensive built-in docs available in project

---

### 2. **audiocraft**
**Purpose:** AI audio and music generation (Meta's AudioCraft)  
**Technology:** MusicGen, AudioGen  
**Environment:** `audiocraft/audiocraft_env/`  
**Python Version:** 3.10  
**Status:** ⚠️ Minor version mismatch (av 16.0.1 vs 11.0.0) - tested and functional

**Key Features:**
- High-quality music generation
- Audio generation from text
- Melody conditioning
- Stereo audio support
- Pre-trained models included

**Entry Points:**
- `run_musicgen_ui.py` - Launch Gradio UI
- Command line demos in `demos/`

**Known Issues:** av library version preference (16.0.1 installed, 11.0.0 preferred) - doesn't affect functionality

---

### 3. **ComfyUI**
**Purpose:** Visual node-based workflow engine for Stable Diffusion and AI image generation  
**Technology:** PyTorch, Stable Diffusion, ControlNet  
**Environment:** `ComfyUI/venv/`  
**Python Version:** Python 3.x  
**Status:** ✅ All dependencies installed, no issues

**Key Features:**
- Node-based visual workflow builder
- Supports multiple AI models (SD, SDXL, etc.)
- Custom nodes and extensions via `custom_nodes/`
- API server for automation
- Model management system

**Entry Points:**
- `main.py` - Launch ComfyUI server
- `run_network.bat` - Network-accessible mode
- `server.py` - API server

**Important Directories:**
- `models/` - AI model storage
- `custom_nodes/` - Extensions and plugins
- `input/` - Input images
- `output/` - Generated images
- `temp/` - Temporary files

---

### 4. **DiffRhythm**
**Purpose:** Rhythm and music generation with diffusion models  
**Environment:** `DiffRhythm/diffrhythm_env/`  
**Python Version:** 3.x  
**Status:** ✅ All dependencies installed, no issues (huggingface-hub updated to 0.36.0)

**Entry Points:**
- `run_ui.py` - Launch UI

**Key Directories:**
- `model/` - Model weights
- `dataset/` - Training data
- `config/` - Configuration files

---

### 5. **local-talking-llm**
**Purpose:** Local voice assistant combining Speech-to-Text, LLM, and TTS  
**Technology:** OpenAI Whisper, Ollama, ChatterBox TTS  
**Environment:** `local-talking-llm/venv/`  
**Python Version:** 3.12  
**Status:** ⚠️ Minor PyTorch version mismatch (2.5.1 vs 2.6.0) - functional

**Key Features:**
- Real-time speech recognition (Whisper)
- Local LLM integration (Ollama)
- Voice synthesis with cloning
- Low-latency conversation
- Optimized for RTX 3090

**Entry Points:**
- `app.py` - Main application
- `tts.py` - TTS module

**Hardware Notes:**
- Whisper large-v3: ~3GB VRAM
- ChatterBox TTS: ~2-3GB VRAM
- Total with LLM: ~22-24GB (fits RTX 3090)

---

### 6. **stable-audio-tools**
**Purpose:** Audio generation and manipulation tools  
**Environment:** `stable-audio-tools/stable_audio_env/`  
**Python Version:** 3.10  
**Status:** ⚠️ Minor numpy version conflict (1.24.0, laion-clap prefers 1.23.5) - functional

**Entry Points:**
- `run_gradio.py` - Gradio interface
- `run_ui.py` - Main UI
- `train.py` - Model training

**Key Scripts:**
- `pre_encode.py` - Data preprocessing
- `unwrap_model.py` - Model utilities

---

### 7. **Wan2GP** & **YuE**
**Purpose:** Specialized conversion/generation tools  
**Environments:** Separate Python environments in each directory  
**Status:** Environment present (YuE has `yue_env/`)

---

## Vector Database (Weaviate)

**Purpose:** Long-term memory and RAG for LLM applications
**Technology:** Weaviate with text2vec-ollama module
**Deployment:** Docker container (port 8080 HTTP, 50051 gRPC)
**Embedding Model:** snowflake-arctic-embed:l via Ollama
**Status:** ✅ Configured and ready for integration

**Key Features:**
- Conversation history storage with semantic search
- Document/knowledge base for RAG
- User-specific memory isolation
- GraphQL API for advanced queries
- Persistent storage via Docker volumes

**Entry Points:**
- `api_gateway/start_weaviate.bat` - Launch Weaviate container
- `api_gateway/docker-compose.yml` - Container configuration
- API: http://localhost:8080
- GraphQL: http://localhost:8080/v1/graphql

**Integration:**
- Connects to Ollama at localhost:11434 for embeddings (via host.docker.internal)
- Will be integrated into API Gateway via vector_service.py (Phase 2)
- Supports conversation history, document RAG, and semantic search

**Documentation:** See `docs/WEAVIATE_SETUP.md` for detailed setup instructions

---

## Supporting Infrastructure

### Node.js Components

**Package:** `package.json`
- **playwright** ^1.57.0 - Browser automation for testing
- **n8n** - Workflow automation (installed globally)

**Scripts:**
- `test_services.js` - Health check for all services
- `start_dashboard.bat` - Launch monitoring dashboard
- `start_n8n.bat` - Launch n8n automation platform

### Utilities

**vram_manager.py**
- Monitor GPU VRAM usage
- Track memory allocation across projects
- Helps prevent OOM errors when running multiple services

**vram.bat**
- Quick VRAM check batch script
- Windows-friendly wrapper for vram_manager.py

---

## Documentation Files

Located in `docs/` directory:

1. **DEPENDENCY_CHECK_REPORT.md** - Latest dependency audit results
2. **LLM_Query_Process_Example.md** - Example workflows
3. **PLAN.md** - Setup plans and configuration guides
4. **README_N8N.md** - n8n workflow automation guide
5. **SERVICE_STATUS_REPORT.md** - Service health status
6. **PROJECT_STRUCTURE.md** - This document

---

## Python Environment Management

Each project uses isolated Python virtual environments:

| Project | Environment Path | Python Version | Status |
|---------|-----------------|----------------|--------|
| alltalk_tts | `alltalk_tts/alltalk_environment/env/` | 3.11 | ✅ Clean |
| audiocraft | `audiocraft/audiocraft_env/` | 3.10 | ⚠️ av version |
| ComfyUI | `ComfyUI/venv/` | 3.x | ✅ Clean |
| DiffRhythm | `DiffRhythm/diffrhythm_env/` | 3.x | ✅ Clean |
| local-talking-llm | `local-talking-llm/venv/` | 3.12 | ⚠️ torch version |
| stable-audio-tools | `stable-audio-tools/stable_audio_env/` | 3.10 | ⚠️ numpy conflict |
| YuE | `YuE/yue_env/` | 3.x | Not checked |

### Activating Environments

**PowerShell:**
```powershell
# Example for ComfyUI
.\ComfyUI\venv\Scripts\Activate.ps1

# Example for audiocraft
.\audiocraft\audiocraft_env\Scripts\Activate.ps1
```

**Verify Installation:**
```powershell
python -m pip check
```

---

## Common Workflows

### Starting Services

**Text-to-Speech (AllTalk):**
```powershell
cd D:\AI\alltalk_tts
.\start_alltalk.bat
```

**ComfyUI (Image Generation):**
```powershell
cd D:\AI\ComfyUI
python main.py
```

**AudioCraft (Music Generation):**
```powershell
cd D:\AI\audiocraft
.\audiocraft_env\Scripts\Activate.ps1
python run_musicgen_ui.py
```

**Voice Assistant:**
```powershell
cd D:\AI\local-talking-llm
.\venv\Scripts\Activate.ps1
python app.py
```

### Monitoring

**Check VRAM Usage:**
```powershell
python vram_manager.py
# or
.\vram.bat
```

**Service Health Check:**
```powershell
node test_services.js
```

**Launch Dashboard:**
```powershell
.\start_dashboard.bat
```

---

## Integration Notes

### Cross-Project Integration

Many projects can work together:

1. **ComfyUI + alltalk_tts** - Generate images with TTS narration
2. **local-talking-llm + alltalk_tts** - Voice assistant with custom voices
3. **audiocraft + stable-audio-tools** - Music generation pipeline
4. **n8n** - Automate workflows between all services

### API Endpoints

Most services expose REST APIs for integration:
- **alltalk_tts** - TTS API server
- **ComfyUI** - Workflow execution API
- **n8n** - Workflow automation webhooks

---

## Troubleshooting

### Common Issues

**1. VRAM Exhaustion**
- Check with `python vram_manager.py`
- Close unused services
- Use low VRAM modes where available (alltalk_tts has this)

**2. Port Conflicts**
- ComfyUI default: 8188
- alltalk_tts default: 7851
- n8n default: 5678
- Check `SERVICE_STATUS_REPORT.md` for current assignments

**3. Python Environment Issues**
- Ensure correct environment is activated
- Run `pip check` to verify dependencies
- See `DEPENDENCY_CHECK_REPORT.md` for known issues

**4. CUDA/PyTorch Issues**
- Verify CUDA installation: `nvidia-smi`
- Check PyTorch CUDA: `python -c "import torch; print(torch.cuda.is_available())"`

---

## Best Practices for LLM Agents

### When Working in This Workspace:

1. **Always check which project you're working in** - paths matter
2. **Activate the correct Python environment** before running commands
3. **Monitor VRAM** when running multiple GPU-intensive services
4. **Check existing documentation** in `docs/` before asking questions
5. **Use absolute paths** when uncertain about working directory
6. **Verify service status** before attempting to start services

### Before Making Changes:

1. Check `DEPENDENCY_CHECK_REPORT.md` for known issues
2. Backup any configuration files you modify
3. Test in isolated environments when possible
4. Document any new workflows or fixes

### File Operations:

- **Project files** stay in their project directories
- **Documentation** goes in `docs/`
- **Test outputs** go in `test-results/`
- **Screenshots** go in `screenshots/`

---

## Quick Reference

### Important Commands

```powershell
# Check Python version in environment
python --version

# List installed packages
pip list

# Check for dependency issues
pip check

# Monitor GPU
nvidia-smi

# Check VRAM usage
python vram_manager.py

# Test service health
node test_services.js
```

### Important Paths

- **Models Storage:** Various (check each project's `models/` directory)
- **Ollama Models:** `D:\AI\ollama-models\`
- **ComfyUI Models:** `D:\AI\ComfyUI\models\`
- **Output Files:** Project-specific `output/` directories
- **Documentation:** `D:\AI\docs\`

---

## Project Maturity & Maintenance

| Project | Maturity | Active Development | Maintenance Status |
|---------|----------|-------------------|-------------------|
| ComfyUI | Production | ✅ Active | Regular updates |
| alltalk_tts | Production | ✅ Active | Version 2 available |
| audiocraft | Stable | ⚠️ Slower | Meta research project |
| local-talking-llm | Beta | ✅ Active | Community maintained |
| stable-audio-tools | Beta | ✅ Active | Stability AI project |
| DiffRhythm | Research | ⚠️ Varies | Academic project |

---

## External Resources

- **Ollama:** Local LLM runtime (installed globally)
- **n8n:** Workflow automation (installed globally via npm)
- **stability-matrix:** Package manager for Stable Diffusion models

---

## Summary for New LLM Instances

This is a **production-ready AI development workspace** with:
- ✅ All major dependencies installed and verified
- ✅ 6+ specialized AI projects ready to use
- ✅ Comprehensive monitoring and testing infrastructure
- ⚠️ 3 projects with minor version preferences (all functional)
- 🔧 GPU optimized for RTX 3090 (24GB VRAM)
- 📚 Full documentation in `docs/` directory

**Start Here:**
1. Read `DEPENDENCY_CHECK_REPORT.md` for current status
2. Check `PLAN.md` for setup guides
3. Use `vram_manager.py` to monitor GPU usage
4. Activate project-specific environments before working

**Need Help?**
- Check project README files in each directory
- Review `docs/` for guides and reports
- Test services with `node test_services.js`
- Monitor with `start_dashboard.bat`

---

*This document is maintained as the authoritative guide to the workspace structure. Update when adding new projects or making significant changes.*
