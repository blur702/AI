# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **local AI development workspace** featuring an integrated ecosystem of AI generation tools (audio, image, music, video, text-to-speech, and LLM) designed for RTX 3090 (24GB VRAM). The architecture follows a **master-satellite pattern** where a central dashboard orchestrates independent AI services.

**External access**: `https://ssdd.kevinalthaus.com` (HTTPS via nginx reverse proxy)

## Key Commands

### Dashboard & Monitoring
```bash
.\start_dashboard.bat              # Launch dashboard (single-port on 80)
.\start_n8n.bat                    # Launch N8N workflow automation (port 5678)
python vram_manager.py             # GPU VRAM monitoring CLI
.\vram.bat                         # Quick VRAM check
```

### Nginx Reverse Proxy (HTTPS)
```bash
cd D:\AI\nginx
.\start-nginx.bat                  # Start nginx (HTTPS on 443)
.\stop-nginx.bat                   # Stop nginx
.\reload-nginx.bat                 # Reload config without restart
.\test-nginx.bat                   # Test configuration syntax
.\setup-letsencrypt.bat            # Get Let's Encrypt certificate
.\generate-self-signed-cert.bat    # Create self-signed cert (testing)
```

### Dashboard Frontend (React + TypeScript + Vite)
```bash
cd D:\AI\dashboard\frontend
npm install                        # Install dependencies
npm run dev                        # Dev server with HMR
npm run build                      # Production build (must rebuild after changes)
```

### Dashboard Backend (Flask + Socket.IO)
```bash
cd D:\AI\dashboard\backend
pip install -r requirements.txt
python app.py                      # Serves frontend + API on port 80
```

### API Gateway (FastAPI)
```bash
cd D:\AI\api_gateway
pip install -r requirements.txt
.\start_gateway.bat                # Start on port 1301
python -m api_gateway.main         # Or run directly
```

### Playwright Tests
```bash
npm install                        # From project root
npx playwright install             # One-time: download browser binaries (Chromium/Firefox/WebKit)
npm test                           # All tests (headless)
npm run test:headed                # All tests (headed)
npm run test:api                   # API tests only
npm run test:ui                    # UI tests only
npm run test:smoke                 # Smoke tests
npm run test:debug                 # Debug with inspector
npm run test:ui-mode               # Interactive UI mode
npm run test:report                # Open HTML report
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

### Single-Port Deployment
The dashboard uses a **single-port architecture** where Flask serves both the React frontend and API on port 80. This enables external access via domain without exposing multiple ports.

- Frontend: `http://localhost/` (React SPA from `frontend/dist/`)
- API: `http://localhost/api/*`
- WebSocket: `http://localhost/socket.io/`

### Service Port Allocation
| Port | Service |
|------|---------|
| 443 | Nginx HTTPS reverse proxy (external entry point) |
| 80 | Dashboard (Flask serves React + API + WebSocket) |
| 1301 | API Gateway (FastAPI) |
| 5678 | N8N workflow automation |
| 3000 | Open WebUI (LLM chat) |
| 8080 | Weaviate (vector database HTTP) |
| 50051 | Weaviate (gRPC) |
| 8188 | ComfyUI (image generation) |
| 7851 | AllTalk TTS |
| 7860 | Wan2GP Video |
| 7870 | YuE Music |
| 7871 | DiffRhythm |
| 7872 | MusicGen |
| 7873 | Stable Audio |
| 11434 | Ollama API |

### Nginx Path-Based Routing
External HTTPS URLs via `https://ssdd.kevinalthaus.com`:
| Path | Service | Backend Port |
|------|---------|--------------|
| `/` | Dashboard | 80 |
| `/api/` | Dashboard API | 80 |
| `/socket.io/` | WebSocket | 80 |
| `/comfyui/` | ComfyUI | 8188 |
| `/n8n/` | N8N | 5678 |
| `/openwebui/` | Open WebUI | 3000 |
| `/alltalk/` | AllTalk TTS | 7851 |
| `/wan2gp/` | Wan2GP | 7860 |
| `/yue/` | YuE Music | 7870 |
| `/diffrhythm/` | DiffRhythm | 7871 |
| `/musicgen/` | MusicGen | 7872 |
| `/stable-audio/` | Stable Audio | 7873 |
| `/ollama/` | Ollama API | 11434 |
| `/weaviate/` | Weaviate | 8080 |

### Dashboard API (port 80)
```
GET  /api/services                 # All service statuses
POST /api/services/<id>/start      # Start a service
POST /api/services/<id>/stop       # Stop a service
GET  /api/vram/status              # GPU memory info
GET  /api/models/ollama/list       # All Ollama models
GET  /api/models/ollama/loaded     # Currently loaded models
POST /api/models/ollama/load       # Load model to GPU
POST /api/models/ollama/unload     # Unload model

WebSocket Events: vram_update (every 2s)
```

### API Gateway (port 1301)
Unified REST/WebSocket interface for external clients (mobile apps, etc). Requires API key auth via `X-API-Key` header.
```
POST /generate/image               # ComfyUI image generation
POST /generate/video               # Wan2GP video generation
POST /generate/audio               # Stable Audio / AudioCraft
POST /generate/music               # YuE / DiffRhythm / MusicGPT
POST /tts                          # AllTalk text-to-speech
POST /llm/generate                 # Ollama text generation
GET  /jobs/{job_id}                # Poll job status
GET  /ws/jobs/{job_id}             # WebSocket job updates
```

### Core Components (this repo)
```
dashboard/
├── frontend/          # React + TypeScript + Vite
│   ├── src/
│   │   ├── components/   # ServiceCard, VramDisplay
│   │   ├── hooks/        # useSocket (Socket.IO client)
│   │   ├── config/       # services.ts (service definitions, getApiBase)
│   │   └── types/        # TypeScript interfaces
│   └── dist/          # Production build (served by Flask)
└── backend/           # Flask + Socket.IO (port 80)
    ├── app.py            # Main app, serves frontend + API
    ├── service_manager.py # Service lifecycle management
    └── services_config.py # Service registry

api_gateway/           # FastAPI unified API (port 1301)
├── routes/            # Endpoint handlers
├── services/          # Backend service clients
└── models/            # Pydantic models

nginx/                 # Nginx reverse proxy configuration
├── nginx.conf         # Main configuration
├── conf.d/
│   └── ssdd.conf      # Site-specific config (HTTPS, routing)
├── ssl/               # SSL certificates
├── logs/              # Access and error logs
└── *.bat              # Management scripts

tests/                 # Playwright test suite
├── fixtures/          # Base and service fixtures
├── page-objects/      # POM classes
├── api-clients/       # HTTP/WebSocket clients
└── tests/             # API, UI, smoke specs
```

### AI Service Projects (independent repos)
Each AI project (alltalk_tts, audiocraft, ComfyUI, DiffRhythm, stable-audio-tools, Wan2GP, YuE) has:
- Its own git repository (excluded from root repo)
- Isolated Python virtual environment (e.g., `audiocraft_env/Scripts/python.exe`)
- Independent dependencies

## Weaviate Vector Database

This project maintains a semantic index of documentation, code, and external API references in Weaviate. **Query the vector DB BEFORE using Glob/Grep** for faster, more accurate results.

### Collections

| Collection | Contents | Source |
|------------|----------|--------|
| `Documentation` | Markdown docs, READMEs | Local `docs/`, `.md` files |
| `CodeEntity` | Functions, classes, methods, styles | Local Python/TS/JS/CSS |
| `DrupalAPI` | Drupal 11.x API reference | Scraped from api.drupal.org |

### MCP Tools Available

| Tool | Use Case | Example Query |
|------|----------|---------------|
| `search_code` | Find functions, classes, methods, styles | "function that starts a service" |
| `search_documentation` | Find docs by concept | "how to configure VRAM monitoring" |
| `search_codebase` | Combined search (docs + code) | "how does authentication work" |

### search_code Filters

- `entity_type`: function, method, class, variable, interface, type, style, animation
- `service_name`: core, alltalk, audiocraft, comfyui, diffrhythm, musicgpt, stable_audio, wan2gp, yue
- `language`: python, typescript, javascript, css

### When to Use

1. **"Where is X defined?"** → `search_code(query="X", entity_type="function")`
2. **"How does X work?"** → `search_codebase(query="X")` (gets both docs and implementation)
3. **"What does the README say about X?"** → `search_documentation(query="X")`
4. **"Find all CSS for buttons"** → `search_code(query="button styles", entity_type="style")`

### Database Contents

- **Documentation**: All markdown files from `docs/`, root `.md` files, service READMEs
- **CodeEntity**: Functions, classes, methods, variables, interfaces, types, CSS styles, animations
  - Languages: Python, TypeScript, JavaScript, CSS
  - Services: core (dashboard, api_gateway, tests) + all AI services
- **DrupalAPI**: Classes, interfaces, functions, hooks, constants, namespaces from Drupal 11.x
  - Scraped from api.drupal.org with rate limiting
  - Includes signatures, parameters, descriptions, deprecation notices

### Ingestion Commands
```bash
# Check status
curl http://localhost/api/ingestion/status

# Reindex via dashboard UI (Settings panel)
# Or via CLI:
python -m api_gateway.services.doc_ingestion reindex
python -m api_gateway.services.code_ingestion reindex --service core
python -m api_gateway.services.code_ingestion reindex --service all

# Drupal API scraper
python -m api_gateway.services.drupal_scraper status
python -m api_gateway.services.drupal_scraper scrape --limit 100
python -m api_gateway.services.drupal_scraper reindex

# Embedding model migration (when changing models)
python -m api_gateway.services.migrate_embeddings check
python -m api_gateway.services.migrate_embeddings migrate --dry-run
python -m api_gateway.services.migrate_embeddings migrate
```

### Embedding Model
The default embedding model is `snowflake-arctic-embed:l` (1024 dimensions). When changing models, ALL collections must be re-indexed since different models produce incompatible vectors.

## Scraper Supervisor

Long-running scraping jobs are managed by the supervisor system with automatic restart and resume capabilities.

### Features
- **Checkpoint/Resume**: Saves progress every 10 entities, resumes from last checkpoint on restart
- **Deduplication**: Skips already-scraped entities via stable UUID comparison
- **Health Monitoring**: Detects crashed processes and heartbeat timeouts
- **Auto-Restart**: Automatically restarts failed jobs (up to 3 retries)
- **Windows Scheduled Task**: Runs health checks every 5 minutes

### Supervisor Commands
```bash
# Check status of all scraping jobs
python -m api_gateway.services.scraper_supervisor status

# Start a new scraping job
python -m api_gateway.services.scraper_supervisor start drupal
python -m api_gateway.services.scraper_supervisor start drupal --limit 1000
python -m api_gateway.services.scraper_supervisor start drupal -f  # foreground

# Resume a failed/stopped job
python -m api_gateway.services.scraper_supervisor resume drupal -f

# Run supervisor daemon (continuous monitoring)
python -m api_gateway.services.scraper_supervisor run

# Single health check pass
python -m api_gateway.services.scraper_supervisor check

# Windows scheduled task management
python -m api_gateway.services.scraper_supervisor install-task --interval 5
python -m api_gateway.services.scraper_supervisor uninstall-task
```

### Data Locations
- Jobs registry: `D:\AI\data\scraper\jobs.json`
- Checkpoints: `D:\AI\data\scraper\checkpoints\`
- Logs: `D:\AI\data\scraper\drupal_stderr.log`

## Critical Development Notes

1. **Nginx HTTPS Proxy**: External access via `https://ssdd.kevinalthaus.com` is handled by nginx (port 443). Flask binds to `127.0.0.1:80` and only accepts connections from localhost/nginx.
2. **Single-Port Architecture**: Flask on port 80 serves both `frontend/dist/` and `/api/*` routes. After frontend changes, run `npm run build` in `dashboard/frontend/`.
3. **Frontend API Config**: `dashboard/frontend/src/config/services.ts` uses `window.location.origin` for API base URL (same-origin requests).
4. **Virtual Environments**: Always activate the project-specific venv before running any AI tool.
5. **VRAM Management**: Monitor constantly - combinations of services can exhaust 24GB.
6. **Windows-Specific**: Uses PowerShell, batch scripts, and nvidia-smi.
7. **Port Conflicts**: Check port availability before starting services.
8. **Vector DB First**: Query `search_code`/`search_codebase` before using Glob/Grep to find code.
9. **SSL Certificates**: Let's Encrypt certificates expire after 90 days. Use `nginx/setup-renewal-task.bat` for auto-renewal.
