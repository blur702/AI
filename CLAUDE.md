# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Local AI development workspace with integrated generation tools (audio, image, music, video, TTS, LLM) for RTX 3090 (24GB VRAM). Central dashboard orchestrates independent AI services.

**External access**: `https://ssdd.kevinalthaus.com` (HTTPS via nginx)

## Database Quick Reference

| Database | Port | Contents | When to Use |
|----------|------|----------|-------------|
| **Weaviate** | 8080 | Code, docs, conversations | "How does X work?", "Find code that does Y" |
| **PostgreSQL** | 5432 | Errors, todos, jobs | "What errors occurred?", "What tasks are pending?" |

### Weaviate MCP Tools

```
search_code          - Find functions/classes by description
search_documentation - Find docs by concept
search_codebase      - Search both code and docs
```

**Filters for search_code:**
- `entity_type`: function, method, class, struct, trait, enum, impl, style, animation
- `service_name`: core, alltalk, audiocraft, comfyui, diffrhythm, musicgpt, stable_audio, wan2gp, yue
- `language`: python, typescript, javascript, css, rust

### PostgreSQL CLI

```bash
python -m api_gateway.services.error_tracker stats   # Error statistics
python -m api_gateway.services.error_tracker list    # Unresolved errors
python -m api_gateway.services.error_tracker find --service "api_gateway"
```

## Key Commands

```bash
# Dashboard & Services
.\start_dashboard.bat              # Launch dashboard (port 80)
.\start_n8n.bat                    # N8N workflow (port 5678)
.\vram.bat                         # Quick VRAM check

# Frontend (after changes)
cd dashboard\frontend && npm run build

# API Gateway
.\start_gateway.bat                # Start on port 1301

# Linting
ruff check <file.py> --fix         # Python
npx eslint <file.ts> --fix         # TypeScript

# Tests
npm test                           # All Playwright tests
```

## Architecture

### Port Allocation

| Port | Service |
|------|---------|
| 443 | Nginx HTTPS (external) |
| 80 | Dashboard (Flask + React) |
| 1301 | API Gateway (FastAPI) |
| 5678 | N8N |
| 8080 | Weaviate |
| 8188 | ComfyUI |
| 7851 | AllTalk TTS |
| 7860-7873 | Music/Video services |
| 11434 | Ollama |

### Dashboard API (port 80)

```
GET  /api/services                 # Service statuses
POST /api/services/<id>/start|stop # Control services
GET  /api/vram/status              # GPU memory
GET  /api/ingestion/status         # Weaviate status
POST /api/ingestion/start          # Start indexing
```

### API Gateway (port 1301)

Requires `X-API-Key` header.

```
POST /generate/image|video|audio|music
POST /tts
POST /llm/generate
GET  /jobs/{job_id}
```

## Weaviate Collections

| Collection | Contents |
|------------|----------|
| `CodeEntity` | Functions, classes, methods (Python/TS/JS/CSS/Rust) |
| `Documentation` | Markdown docs |
| `ClaudeConversation` | Past Claude sessions |
| `DrupalAPI` | Drupal 11.x API reference |

### Indexing

```bash
# Incremental (after merges)
python -m api_gateway.services.incremental_indexer --git-diff

# Full reindex
python -m api_gateway.services.code_ingestion reindex --service all
python -m api_gateway.services.doc_ingestion reindex
```

## Project Structure

```
dashboard/
├── frontend/          # React + TypeScript + Vite
└── backend/           # Flask + Socket.IO

api_gateway/           # FastAPI (port 1301)
├── routes/
├── services/
└── models/

.claude/hooks/         # Post-edit linting, conversation storage
nginx/                 # HTTPS reverse proxy
scripts/               # Monitoring, git hooks
tests/                 # Playwright tests
```

## Critical Notes

1. **Vector DB First**: Use `search_code`/`search_codebase` before Glob/Grep
2. **Single-Port**: Flask serves React + API on port 80. Run `npm run build` after frontend changes
3. **VRAM**: Monitor constantly - services can exhaust 24GB
4. **Virtual Envs**: Each AI service has its own venv
5. **Auto-Restart**: Dashboard auto-restarts via Task Scheduler. Disable with `New-Item D:\AI\scripts\disable.flag`
6. **Linting**: Post-edit hook runs ruff/eslint automatically
7. **Branch Protection**: PRs required for master, CodeRabbit reviews automatically

## Code Review Workflow

1. Create branch, make changes
2. Run linters: `ruff check . --fix` and `npx eslint . --fix`
3. Commit and push, create PR
4. CodeRabbit reviews automatically
5. Address review comments
6. Merge when approved

### GitHub CLI

```bash
"C:\Program Files\GitHub CLI\gh.exe" pr create --title "Title" --body "Body"
"C:\Program Files\GitHub CLI\gh.exe" pr view 123
```

## Error Tracking

Errors auto-tracked in PostgreSQL via post-edit hook.

```bash
python -m api_gateway.services.error_tracker list      # View errors
python -m api_gateway.services.error_tracker stats     # Statistics
python -m api_gateway.services.error_tracker resolve --error-id "uuid" --resolution "Fixed by..."
```

## PostgreSQL Setup

```bash
# Config in .env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=ai_gateway
POSTGRES_DB=ai_gateway
```

Tables: `jobs`, `api_keys`, `todos`, `errors`, `ideas`
