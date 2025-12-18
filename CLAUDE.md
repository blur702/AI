# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Local AI development workspace with integrated generation tools (audio, image, music, video, TTS, LLM) for RTX 3090 (24GB VRAM). Central dashboard orchestrates independent AI services.

**External access**: `https://ssdd.kevinalthaus.com` (HTTPS via nginx)

## IMPORTANT: Query the Vector Database FIRST

Before using `Glob`, `Grep`, or file searches, **always query Weaviate first** for coding questions. The database contains semantically indexed code and documentation that provides faster, more relevant results.

### Weaviate MCP Tools

```
search_code          - Find functions/classes/methods by description
search_documentation - Find docs by concept
search_codebase      - Search BOTH code AND docs (use for broad questions)
search_drupal_api    - Search Drupal 11.x API (16k+ PHP classes/functions/hooks)
search_congressional - Search House member press releases and voting records
search_mdn           - Search MDN JavaScript and Web API documentation
```

**Filters for search_code:**
- `entity_type`: function, method, class, struct, trait, enum, impl, style, animation
- `service_name`: core, alltalk, audiocraft, comfyui, diffrhythm, musicgpt, stable_audio, wan2gp, yue
- `language`: python, typescript, javascript, css, rust

**Filters for search_drupal_api:**
- `entity_type`: class, interface, trait, function, method, hook, constant

**Filters for search_congressional:**
- `state`: Two-letter state code (e.g., "CA", "TX")
- `party`: "Republican" or "Democrat"

**Filters for search_mdn:**
- `collection`: "javascript" or "webapi" (or omit for both)

**Embedding model check (do this BEFORE any Weaviate query):** Silently run `ollama ps` to check if `snowflake-arctic-embed:l` is loaded. If not, load it with `ollama run snowflake-arctic-embed:l ""` and inform user of loading progress.

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
| `DrupalModuleDocs` | Drupal module READMEs and documentation (from remote server) |
| `DrupalTwigTemplates` | Drupal Twig templates from core, contrib, and custom themes |
| `CongressionalData` | House member websites, press releases, voting records |

### Indexing

```bash
# Incremental (after merges)
python -m api_gateway.services.incremental_indexer --git-diff

# Full reindex
python -m api_gateway.services.code_ingestion reindex --service all
python -m api_gateway.services.doc_ingestion reindex

# Drupal module docs (fetches from remote server via SSH)
python -m api_gateway.services.drupal_doc_ingestion ingest --verbose
python -m api_gateway.services.drupal_doc_ingestion status

# Drupal Twig templates (fetches from remote server via SSH)
python -m api_gateway.services.drupal_twig_ingestion ingest --verbose
python -m api_gateway.services.drupal_twig_ingestion status
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

1. **Vector DB First**: ALWAYS use `search_code`/`search_codebase`/`search_documentation` BEFORE Glob/Grep. The semantic index is faster and more accurate.
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

## Secret Scanning Pipeline

Automated protection against committing secrets to the repository.

### Protection Layers

| Layer | File | Trigger |
|-------|------|---------|
| GitHub Actions | `.github/workflows/secret-scan.yml` | Every PR to master |
| Pre-commit hook | `.git/hooks/pre-commit` | Every local commit |
| Manual scanner | `scripts/check-env-secrets.py` | On-demand |

### What Gets Blocked

- Any `.env` file (only `.env.example` templates allowed)
- Files containing detected secrets:
  - API keys (OpenAI `sk-`, AWS `AKIA`, Stripe, GitHub, Slack)
  - Database URLs with embedded passwords
  - Private keys (RSA, PGP, SSH)
  - JWT/Auth secrets

### Safe Placeholders (Allowed)

```bash
API_KEY=your-api-key-here      # OK
PASSWORD=changeme              # OK
SECRET=${SECRET_KEY}           # OK (environment variable)
DATABASE_URL=localhost:5432    # OK (no credentials)
```

### Commands

```bash
# Run secret scanner manually
python scripts/check-env-secrets.py

# Run in CI mode (stricter)
python scripts/check-env-secrets.py --ci

# Show fix suggestions
python scripts/check-env-secrets.py --fix

# Install local pre-commit hook
.\scripts\install-hooks.ps1
```

### If Commit Is Blocked

1. Remove the secret from the file
2. Use a placeholder value instead
3. Store real secrets in local `.env` (not tracked)
4. Re-run `git commit`

**NEVER** use `git commit --no-verify` to bypass the hook.

## PostgreSQL Setup

```bash
# Config in .env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=ai_gateway
POSTGRES_DB=ai_gateway
```

Tables: `jobs`, `api_keys`, `todos`, `errors`, `ideas`

## Congressional Scraper

Parallel scraper system for House of Representatives member websites. Scrapes member pages, press releases, and voting records into Weaviate's `CongressionalData` collection.

### Architecture

- **Supervisor** (`congressional_parallel_supervisor.py`): Orchestrates 20 parallel workers
- **Workers** (`congressional_worker.py`): Each scrapes assigned subset of members
- **Scraper** (`congressional_scraper.py`): Core scraping logic with rate limiting

### Data Flow

```
House.gov JSON Feed → Supervisor divides 441 members among 20 workers
    ↓
Workers scrape member websites (max 5 pages each)
    ↓
Content + embeddings → Weaviate CongressionalData collection
```

### Commands

```bash
# Start parallel scrape (20 workers)
python -m api_gateway.services.congressional_parallel_supervisor start

# Check worker status
python -m api_gateway.services.congressional_parallel_supervisor status

# Stop all workers
python -m api_gateway.services.congressional_parallel_supervisor stop

# Single-threaded scrape (for testing)
python -m api_gateway.services.congressional_scraper scrape --limit 5

# Scrape voting records only
python -m api_gateway.services.congressional_scraper scrape --votes-only --max-votes 100

# Check collection stats
python -m api_gateway.services.congressional_scraper status
```

### File Locations

| Path | Purpose |
|------|---------|
| `data/scraper/congressional/` | Config, PID, work assignments |
| `data/scraper/congressional/heartbeats/` | Worker heartbeat files (health monitoring) |
| `data/scraper/congressional/checkpoints/` | Resume state for crashed workers |
| `logs/congressional_scraper/` | Per-worker log files |

### Configuration

`data/scraper/congressional/congressional_parallel_config.json`:

```json
{
  "supervisor": {
    "worker_count": 20,
    "heartbeat_timeout_seconds": 300,
    "max_restarts_per_worker": 3
  },
  "worker": {
    "request_delay": 2.0,
    "max_pages_per_member": 5,
    "checkpoint_interval": 5
  }
}
```

### Data Schema

CongressionalData collection fields:
- `member_name`, `state`, `district`, `party`, `chamber`
- `title`, `topic`, `content_text`, `url`
- `policy_topics` (auto-classified via Ollama)
- `scraped_at`, `content_hash`, `uuid`
