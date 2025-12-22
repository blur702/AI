# Architecture Overview

Local AI development workspace for RTX 3090 (24GB VRAM). Central dashboard orchestrates independent AI services.

**External URL**: `https://ssdd.kevinalthaus.com`

---

## Directory Structure

```
D:\AI/
├── dashboard/           # Flask backend + React frontend (port 80)
│   ├── backend/         # Flask app, service management, WebSocket
│   └── frontend/        # React 18 + Vite + TypeScript
├── api_gateway/         # FastAPI external API (port 1301)
│   ├── routes/          # REST endpoints
│   ├── services/        # Business logic, scrapers, Weaviate
│   ├── middleware/      # Auth, response formatting
│   └── models/          # SQLAlchemy + Pydantic schemas
├── mcp_servers/         # Claude semantic search integration
├── tests/               # Playwright test suite
├── scripts/             # Automation, deployment, monitoring
├── nginx/               # HTTPS reverse proxy (port 443)
├── drupal_modules/      # Custom Drupal 11 modules
├── drupal_theme/        # React SPA for Drupal (build artifacts only)
├── docs/                # Documentation
├── logs/                # Service and ingestion logs
├── data/                # Runtime data, scraper cache
└── [AI Services]/       # alltalk_tts, ComfyUI, Wan2GP, etc.
```

---

## Port Allocation

| Port  | Service     | Purpose               |
| ----- | ----------- | --------------------- |
| 443   | Nginx       | HTTPS external access |
| 80    | Dashboard   | Flask + React UI      |
| 1301  | API Gateway | External REST API     |
| 5678  | N8N         | Workflow automation   |
| 7851  | AllTalk     | Text-to-speech        |
| 8080  | Weaviate    | Vector database       |
| 8188  | ComfyUI     | Image generation      |
| 11434 | Ollama      | LLM runtime           |

---

## Key Entry Points

| Service               | File                                                        | Command                            |
| --------------------- | ----------------------------------------------------------- | ---------------------------------- |
| Dashboard             | `dashboard/backend/app.py`                                  | `start_dashboard.bat`              |
| API Gateway           | `api_gateway/main.py`                                       | `start_gateway.bat`                |
| N8N                   | npm global                                                  | `start_n8n.bat`                    |
| Congressional Scraper | `api_gateway/services/congressional_parallel_supervisor.py` | `start_congressional_parallel.bat` |

---

## Dashboard Backend (`dashboard/backend/`)

**Stack**: Flask 3.0 + Flask-SocketIO + psutil

| File                   | Purpose                                                            |
| ---------------------- | ------------------------------------------------------------------ |
| `app.py`               | Main Flask app, WebSocket, auth, static serving                    |
| `service_manager.py`   | Service lifecycle (start/stop/pause), health checks, idle timeouts |
| `services_config.py`   | Service registry: ports, commands, health endpoints                |
| `ingestion_manager.py` | Weaviate indexing control and progress                             |
| `claude_manager.py`    | Claude Code WebSocket sessions                                     |

**Key Functions**:

- `ServiceManager.start_service(id)` - Launches AI service with VRAM check
- `ServiceManager.stop_service(id)` - Graceful shutdown with cleanup
- `IngestionManager.start_ingestion()` - Triggers Weaviate reindexing

---

## Dashboard Frontend (`dashboard/frontend/`)

**Stack**: React 18 + TypeScript + Vite + MUI

| Directory         | Contents                                                     |
| ----------------- | ------------------------------------------------------------ |
| `src/components/` | ServiceCard, ResourceManager, CongressionalChat, ClaudePanel |
| `src/hooks/`      | useSocket, useServices, useVram, useClaude, useCongressional |
| `src/config/`     | Service definitions for UI                                   |

**Build**: `npm run build` outputs to `dist/`, served by Flask.

---

## API Gateway (`api_gateway/`)

**Stack**: FastAPI + Uvicorn + SQLAlchemy (async) + Pydantic

### Routes (`routes/`)

| File               | Endpoints                                   |
| ------------------ | ------------------------------------------- |
| `generation.py`    | `POST /generate/image\|video\|audio\|music` |
| `llm.py`           | `POST /llm/generate`                        |
| `tts.py`           | `POST /tts`                                 |
| `jobs.py`          | `GET /jobs/{id}`, WebSocket updates         |
| `congressional.py` | Congressional data queries                  |
| `auth.py`          | API key management                          |
| `health.py`        | Health checks                               |

**Auth**: Requires `X-API-Key` header (validated in `middleware/auth.py`).

### Services (`services/`)

**Weaviate Integration**:
| File | Purpose |
|------|---------|
| `weaviate_connection.py` | Connection management, collection constants |
| `code_ingestion.py` | Index Python/TS/JS/CSS/Rust code |
| `doc_ingestion.py` | Index markdown documentation |
| `code_parsers.py` | Language-specific AST parsing |
| `incremental_indexer.py` | Post-merge partial reindexing |

**Congressional Scraper** (parallel architecture):
| File | Purpose |
|------|---------|
| `congressional_parallel_supervisor.py` | Orchestrates 20 workers |
| `congressional_worker.py` | Scrapes assigned House members |
| `congressional_scraper.py` | Core scraping with rate limiting |
| `congressional_schema.py` | Weaviate schema, UUID5 generation |

**Drupal Integration**:
| File | Purpose |
|------|---------|
| `drupal_doc_ingestion.py` | Fetch module docs via SSH |
| `drupal_twig_ingestion.py` | Fetch Twig templates via SSH |
| `drupal_ssh.py` | SSH connection handling |

**Utilities**:
| File | Purpose |
|------|---------|
| `job_queue.py` | Async job management (SQLite) |
| `vram_service.py` | GPU memory monitoring |
| `error_tracker.py` | PostgreSQL error logging |
| `topic_classifier.py` | Ollama-based content classification |

---

## Weaviate Collections

| Collection            | Contents                    | Source           |
| --------------------- | --------------------------- | ---------------- |
| `CodeEntity`          | Functions, classes, methods | Local codebase   |
| `Documentation`       | Markdown docs               | Local + scraped  |
| `DrupalAPI`           | 16k+ Drupal classes/hooks   | Remote scrape    |
| `DrupalModuleDocs`    | Module READMEs              | Remote SSH       |
| `DrupalTwigTemplates` | Twig templates              | Remote SSH       |
| `CongressionalData`   | House member data           | Parallel scraper |
| `MDNJavaScript`       | MDN JS docs                 | Web scrape       |
| `MDNWebAPIs`          | MDN Web API docs            | Web scrape       |

**Embedding Model**: `snowflake-arctic-embed:l` (1024 dimensions) via Ollama.

---

## MCP Servers (`mcp_servers/`)

Enables Claude to query Weaviate via semantic search:

```
search_code          - Find functions/classes by description
search_documentation - Find docs by concept
search_codebase      - Search both code AND docs
search_drupal_api    - Search Drupal 11.x API
search_congressional - Search House member data
search_mdn           - Search MDN documentation
```

**Config**: `.mcp.json` at project root.

---

## Testing (`tests/`)

**Stack**: Playwright + TypeScript

```bash
npm test              # All tests
npm run test:api      # API tests
npm run test:ui       # UI tests
npm run test:smoke    # Quick health checks
```

| Directory       | Purpose               |
| --------------- | --------------------- |
| `tests/api/`    | API endpoint tests    |
| `tests/ui/`     | Dashboard UI tests    |
| `tests/smoke/`  | Service health checks |
| `tests/drupal/` | Drupal integration    |

---

## Databases

| DB         | Purpose                       | Connection                         |
| ---------- | ----------------------------- | ---------------------------------- |
| PostgreSQL | Jobs, API keys, errors, todos | `localhost:5432`, db: `ai_gateway` |
| SQLite     | API Gateway job queue         | `api_gateway.db`                   |
| Weaviate   | Vector embeddings             | `localhost:8080`                   |

---

## Startup Scripts

| Script                             | Purpose                  |
| ---------------------------------- | ------------------------ |
| `start_dashboard.bat`              | Dashboard on port 80     |
| `start_gateway.bat`                | API Gateway on port 1301 |
| `start_n8n.bat`                    | N8N on port 5678         |
| `vram.bat`                         | Quick VRAM check         |
| `start_congressional_parallel.bat` | Congressional scraper    |

---

## Anomalies & Notes

1. **Dual Server Architecture**: Dashboard (Flask:80) and API Gateway (FastAPI:1301) are separate processes. Dashboard is for local UI; Gateway is for external API clients.

2. **Windows-Specific Paths**: Hardcoded `D:\AI` paths in service_manager.py and startup scripts.

3. **SSH Credentials**: `.mcp.json` contains cleartext SSH password for Drupal remote server.

4. **Per-Service Venvs**: Each AI service has its own virtual environment (e.g., `ComfyUI/venv`, `alltalk_tts/venv`).

5. **Branch Protection**: PRs required for master. CodeRabbit auto-reviews.

6. **Auto-Restart**: Dashboard auto-restarts via Windows Task Scheduler. Disable with `New-Item D:\AI\scripts\disable.flag`.

7. **VRAM Management**: Services auto-pause after idle timeout to free GPU memory. Monitor with `vram.bat`.

8. **Embedding Model**: Must load `snowflake-arctic-embed:l` in Ollama before Weaviate queries: `ollama run snowflake-arctic-embed:l ""`.

9. **Rate Limiting**: Nginx limits Ollama endpoints to 10 req/min per IP.

10. **drupal_theme/**: Contains only build artifacts (dist/, node_modules/). Source code is elsewhere or was a temporary build.

---

## Quick Reference

```bash
# Start services
.\start_dashboard.bat          # Dashboard UI
.\start_gateway.bat            # External API

# Check status
.\vram.bat                     # GPU memory
curl localhost/api/services    # Service status

# Indexing
python -m api_gateway.services.incremental_indexer --git-diff
python -m api_gateway.services.code_ingestion reindex --service all

# Linting
ruff check <file.py> --fix
npx eslint <file.ts> --fix

# Testing
npm test
```
