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

### Dashboard Persistence & Monitoring
The dashboard has a Task Scheduler-based persistence system that automatically restarts it if it becomes unresponsive.

**Scripts Location**: `D:\AI\scripts\`
- `dashboard-monitor.ps1` - Monitors port 80 every 30 seconds, restarts dashboard on failure
- `setup-task.ps1` - Creates Windows Task Scheduler task (run as Administrator)

**Setup (one-time, run as Administrator):**
```powershell
powershell -ExecutionPolicy Bypass -File D:\AI\scripts\setup-task.ps1
```

**How it works:**
1. Task Scheduler runs `dashboard-monitor.ps1` on user logon with SYSTEM privileges
2. Script checks port 80 connectivity every 30 seconds
3. If port is unresponsive (and no disable flag), executes `start_dashboard.bat`
4. Coexists with tray app auto-restart (both mechanisms can operate independently)

**Disable/Enable Monitoring:**
```powershell
# Disable (create flag file)
New-Item -ItemType File -Path "D:\AI\scripts\disable.flag" -Force

# Enable (remove flag file)
Remove-Item -Path "D:\AI\scripts\disable.flag" -Force

# Check status
Test-Path "D:\AI\scripts\disable.flag"
```

**Task Management:**
```powershell
# View task details
schtasks /query /tn "AI Dashboard Monitor" /v /fo list

# Delete task
schtasks /delete /tn "AI Dashboard Monitor" /f

# Run task manually
schtasks /run /tn "AI Dashboard Monitor"

# View logs: Event Viewer → Applications and Services Logs → Microsoft → Windows → TaskScheduler
```

## Architecture

### Single-Port Deployment
The dashboard uses a **single-port architecture** where Flask serves both the React frontend and API on port 80. This enables external access via domain without exposing multiple ports. Persistent monitoring via Task Scheduler ensures the dashboard auto-restarts if it becomes unresponsive.

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
```text
GET  /api/services                 # All service statuses
POST /api/services/<id>/start      # Start a service
POST /api/services/<id>/stop       # Stop a service
POST /api/services/<id>/pause      # Pause a running service
POST /api/services/<id>/resume     # Resume a paused service
GET  /api/vram/status              # GPU memory info
GET  /api/models/ollama/list       # All Ollama models
GET  /api/models/ollama/loaded     # Currently loaded models
POST /api/models/ollama/load       # Load model to GPU
POST /api/models/ollama/unload     # Unload model

# Ingestion Management
GET  /api/ingestion/status         # Ingestion status with collection counts
POST /api/ingestion/start          # Start ingestion (types[], reindex, options)
POST /api/ingestion/cancel         # Cancel running ingestion
POST /api/ingestion/pause          # Pause running ingestion
POST /api/ingestion/resume         # Resume paused ingestion
POST /api/ingestion/clean          # Delete collections (collections[])
POST /api/ingestion/reindex        # Force reindex (same params as start)

WebSocket Events:
- vram_update (every 2s)
- service_status, service_paused, service_resumed
- ingestion_progress, ingestion_paused, ingestion_resumed, ingestion_complete
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

### PostgreSQL Database
The API Gateway uses PostgreSQL with asyncpg for persistent storage.

**Tables:**
- `jobs` - Async job tracking (image/audio/video generation)
- `api_keys` - API key authentication
- `todos` - Task management
- `errors` - Error tracking and monitoring

**Configuration** (in `.env` or environment):
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=ai_gateway
POSTGRES_PASSWORD=your_password
POSTGRES_DB=ai_gateway
# Or set DATABASE_URL directly:
# DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db
```

**Migration Commands:**
```bash
# Migrate from SQLite to PostgreSQL
python -m api_gateway.scripts.migrate_to_postgres
python -m api_gateway.scripts.migrate_to_postgres --dry-run

# Test PostgreSQL connectivity and CRUD
python -m api_gateway.scripts.test_postgres_migration

# Rollback to SQLite (if needed)
python -m api_gateway.scripts.rollback_to_sqlite
python -m api_gateway.scripts.rollback_to_sqlite --export-data
```

**PostgreSQL Setup (Windows):**
```bash
# Install PostgreSQL (via installer or scoop)
scoop install postgresql

# Initialize and start
initdb -D D:\AI\data\postgres
pg_ctl -D D:\AI\data\postgres start

# Create database and user
psql -U postgres
-- ⚠️  IMPORTANT: Replace with a strong, unique password (use environment variables or secret manager)
CREATE USER ai_gateway WITH PASSWORD 'REPLACE_WITH_SECURE_PASSWORD';
CREATE DATABASE ai_gateway OWNER ai_gateway;
GRANT ALL PRIVILEGES ON DATABASE ai_gateway TO ai_gateway;
```

### PostgreSQL Storage for LLMs (Errors & Todos)

The PostgreSQL database stores structured data that should NOT be vectorized - things like errors, todos, and job tracking. Use this for:
- **Errors**: Exception tracking with service, severity, stack traces, resolution status
- **Todos**: Task management with status, priority, due dates, tags
- **Jobs**: Async job tracking for long-running operations

**Schema (api_gateway/models/database.py):**
```python
# Error tracking
class Error(Base):
    id: str            # UUID
    service: str       # Service that raised the error
    severity: Enum     # info, warning, error, critical
    message: str       # Error message
    stack_trace: str   # Full traceback
    context: JSON      # Additional context (file paths, inputs)
    job_id: str        # Related job if any
    created_at: datetime
    resolved: bool
    resolved_at: datetime

# Task management
class Todo(Base):
    id: str            # UUID
    title: str         # Short description
    description: str   # Detailed description
    status: Enum       # pending, in_progress, completed
    priority: int      # 0=low, higher=more urgent
    due_date: datetime
    tags: JSON         # ["feature", "bug", "docs"]
    created_at: datetime
    completed_at: datetime
```

**Python API for LLMs:**
```python
from api_gateway.models.database import AsyncSessionLocal, Error, Todo, ErrorSeverity, TodoStatus
from datetime import datetime, timezone

# Store an error
async with AsyncSessionLocal() as session:
    error = Error(
        service="code_ingestion",
        severity=ErrorSeverity.error,
        message="Failed to parse file",
        stack_trace=traceback.format_exc(),
        context={"file": "path/to/file.py", "line": 42},
    )
    session.add(error)
    await session.commit()

# Create a todo
async with AsyncSessionLocal() as session:
    todo = Todo(
        title="Fix authentication bug",
        description="Users are getting logged out unexpectedly",
        status=TodoStatus.pending,
        priority=2,
        tags=["bug", "auth"],
    )
    session.add(todo)
    await session.commit()

# Query errors
async with AsyncSessionLocal() as session:
    result = await session.execute(
        select(Error).where(Error.resolved == False).order_by(Error.created_at.desc())
    )
    unresolved_errors = result.scalars().all()

# Query todos
async with AsyncSessionLocal() as session:
    result = await session.execute(
        select(Todo).where(Todo.status != TodoStatus.completed)
    )
    active_todos = result.scalars().all()
```

**When to use PostgreSQL vs Weaviate:**
| Data Type | Storage | Why |
|-----------|---------|-----|
| Errors | PostgreSQL | Structured, filterable, no semantic search needed |
| Todos | PostgreSQL | Structured, status tracking, no semantic search |
| Jobs | PostgreSQL | Tracking state, not content-based queries |
| Conversations | Weaviate | Semantic search over past conversations |
| Documentation | Weaviate | Semantic search by concept |
| Code entities | Weaviate | Find similar functions/classes |

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

scripts/               # System monitoring and automation
├── dashboard-monitor.ps1  # Port 80 monitor with auto-restart
├── setup-task.ps1         # Task Scheduler setup script
└── disable.flag           # Create to disable monitoring (on demand)

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
| `ClaudeConversation` | Claude Code session history | Hook captures prompts |
| `ConversationMemory` | Talking head chat history | Talking head system |

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

### Claude Conversation Storage

Claude Code conversations are automatically stored in Weaviate via a hook that triggers on user prompts. This enables semantic search over past conversations.

**Automatic Storage (Hook):**
A `UserPromptSubmit` hook in `.claude/settings.json` captures each user prompt and stores it in the `ClaudeConversation` collection:
```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": ".*",
      "hooks": [{
        "type": "command",
        "command": "powershell -ExecutionPolicy Bypass -File \"$CLAUDE_PROJECT_DIR/.claude/hooks/post-message-store.ps1\""
      }]
    }]
  }
}
```

**Manual Storage:**
```bash
# Store a conversation turn
python -m api_gateway.services.claude_conversation_schema store \
    --session-id "session-123" \
    --user-message "How do I add a new service?" \
    --assistant-response "To add a new service, you need to..."

# Store from stdin (JSON)
echo '{"session_id":"abc","user_message":"hello","assistant_response":"Hi!"}' | \
    python -m api_gateway.services.claude_conversation_schema store-stdin
```

**Search Past Conversations:**
```bash
# Semantic search
python -m api_gateway.services.claude_conversation_schema search \
    --query "adding new services"

# Filter by session
python -m api_gateway.services.claude_conversation_schema search \
    --query "error handling" \
    --session-id "session-123"
```

**Python API for Retrieval:**
```python
from api_gateway.services.claude_conversation_schema import (
    search_conversations,
    ClaudeConversationTurn,
    insert_conversation_turn,
)
from api_gateway.services.weaviate_connection import WeaviateConnection

with WeaviateConnection() as client:
    # Search for similar conversations
    results = search_conversations(
        client,
        query="How do I configure VRAM?",
        limit=5,
    )
    for r in results:
        print(f"User: {r['user_message'][:50]}...")
        print(f"Response: {r['assistant_response'][:50]}...")
        print(f"Similarity: {1 - r['distance']:.2f}")

    # Store a new conversation
    turn = ClaudeConversationTurn(
        session_id="my-session",
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_message="What is vectorization?",
        assistant_response="Vectorization is the process of...",
    )
    uuid = insert_conversation_turn(client, turn)
```

**Collection Stats:**
```bash
python -m api_gateway.services.claude_conversation_schema stats
```

### Storing Custom Data in Weaviate

For any semantic content that needs search, use manual vectorization with the shared embedding utility:

```python
from api_gateway.utils.embeddings import get_embedding
from api_gateway.services.weaviate_connection import WeaviateConnection

with WeaviateConnection() as client:
    collection = client.collections.get("YourCollection")

    # Build text representation
    text = f"{title}\n\n{content}"

    # Get embedding vector
    vector = get_embedding(text)

    # Insert with vector
    uuid = collection.data.insert(
        properties={"title": title, "content": content},
        vector=vector,
    )
```

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
10. **Dashboard Auto-Restart**: Stopping the dashboard manually will trigger auto-restart within 30 seconds unless monitoring is disabled. To disable during maintenance: `New-Item -ItemType File -Path "D:\AI\scripts\disable.flag" -Force`
11. **Dashboard Context**: When started by Task Scheduler monitor, dashboard runs as SYSTEM. When started manually via `start_dashboard.bat`, it runs in user context.
12. **Auto Code Review**: A PostToolUse hook runs linters (ruff for Python, ESLint for TypeScript) after every file edit. Issues are displayed for immediate fixing. See `.claude/hooks/post-edit-review.ps1`.
13. **MANDATORY CodeRabbit Review**: All code changes MUST be verified through CodeRabbit before a task is considered complete. See "CodeRabbit Verification Workflow" section below.

## Automatic Code Review (Claude Code Hooks)

This project has automatic code review configured via Claude Code hooks. After every `Edit` or `Write` operation, linters run automatically.

### Current Setup

**Hook Location**: `.claude/hooks/post-edit-review.ps1`
**Configuration**: `.claude/settings.json`

**What runs automatically:**
- **Python files (*.py)**: `ruff check` for linting
- **TypeScript/JavaScript (*.ts, *.tsx, *.js, *.jsx)**: `eslint` for linting

### Adding CodeRabbit CLI (Future Enhancement)

CodeRabbit CLI provides AI-powered code reviews but requires Linux/macOS (or WSL with Ubuntu).

**To install when WSL Ubuntu is available:**
```bash
# In WSL Ubuntu
curl -fsSL https://cli.coderabbit.ai/install.sh | sh
source ~/.bashrc
coderabbit auth login
```

**Then update the hook** (`.claude/hooks/post-edit-review.ps1`):
```powershell
# Add CodeRabbit review for comprehensive AI analysis
$wslPath = $filePath -replace '\\', '/' -replace '^D:', '/mnt/d'
$crOutput = wsl -d Ubuntu coderabbit review --plain --type uncommitted 2>&1
if ($crOutput) {
    $issues += "=== CodeRabbit AI Review ==="
    $issues += $crOutput
}
```

### Manual Review Commands

```bash
# Python linting
ruff check <file.py>
ruff check <file.py> --fix  # Auto-fix

# TypeScript/JavaScript linting
npx eslint <file.ts>
npx eslint <file.ts> --fix  # Auto-fix

# Format all code
npm run format
npm run lint:fix
```

## CodeRabbit Integration

This project has full CodeRabbit integration for automated code review and fix application.

### Configuration Files

| File | Purpose |
|------|---------|
| `.coderabbit.yaml` | Main CodeRabbit configuration (review profile, tools, path rules) |
| `.github/workflows/coderabbit-autofix.yml` | GitHub Actions workflow for auto-applying fixes |
| `.github/scripts/coderabbit_autofix.py` | Python script that parses and applies CodeRabbit suggestions |

### How CodeRabbit Review Works

1. **Create a PR**: Push changes to a branch and create a Pull Request
2. **Automatic Review**: CodeRabbit automatically reviews the PR (configured in `.coderabbit.yaml`)
3. **Auto-Fix Workflow**: The GitHub Actions workflow runs automatically:
   - Parses CodeRabbit review comments
   - Extracts code suggestions (diff blocks, before/after patterns)
   - Applies fixes automatically
   - Runs linters (ruff, black, isort, prettier, eslint)
   - Commits and pushes fixes
   - Posts a summary comment on the PR

### Configuration Details

**Review Profile**: `assertive` (detailed feedback)
**Auto-Review**: Enabled for `master` and `main` branches
**Tools Enabled**:
- `ast_grep` - AST-based code analysis
- `shellcheck` - Bash script linting
- `ruff` - Python linting
- `eslint` - JavaScript/TypeScript linting
- `biome` - JavaScript/TypeScript formatting

**Path-Specific Rules**:
- Python (`**/*.py`): Type hints, logging, exceptions, security, subprocess calls
- TypeScript (`**/*.ts`): Proper types, async/await, error handling
- React (`**/*.tsx`): React patterns, hooks, typed props
- Tests (`tests/**/*`): Meaningful tests, proper assertions, isolation

### GitHub CLI

GitHub CLI (`gh`) is installed at `C:\Program Files\GitHub CLI\gh.exe`. If `gh` is not in PATH, use the full path:
```bash
"C:\Program Files\GitHub CLI\gh.exe" pr create --title "Title" --body "Body"
"C:\Program Files\GitHub CLI\gh.exe" pr view 123
```

### Running CodeRabbit Verification

**Option 1: Via Pull Request (Recommended)**
```bash
# Create a branch and push changes
git checkout -b feature/my-changes
git add -A
git commit -m "feat: Description of changes"
git push -u origin feature/my-changes

# Create PR via GitHub CLI
gh pr create --title "My changes" --body "Description"

# CodeRabbit will automatically review the PR
# Auto-fix workflow will apply suggestions and re-run
```

**Option 2: Manual Trigger**
```bash
# Trigger the auto-fix workflow manually for an existing PR
gh workflow run coderabbit-autofix.yml -f pr_number=123 -f max_iterations=3
```

**Option 3: Local Linting (Pre-PR Check)**
```bash
# Run the same linters CodeRabbit uses locally
# Python
ruff check . --fix
black .
isort .

# TypeScript/JavaScript
npx eslint . --ext .ts,.tsx,.js,.jsx --fix
npx prettier --write .
```

### Auto-Fix Script Usage

The auto-fix script can be run locally (requires GITHUB_TOKEN):
```bash
# Set GitHub token
export GITHUB_TOKEN=your_token

# Run auto-fix for a specific PR
python .github/scripts/coderabbit_autofix.py \
    --repo owner/repo \
    --pr 123 \
    --max-iterations 3 \
    --output-summary summary.md
```

The script:
- Fetches CodeRabbit review comments via GitHub API
- Parses suggestions using regex patterns (diff, before/after, inline)
- Categorizes fixes: security, performance, bug, typing, style, improvement
- Applies fixes via exact matching or fuzzy line-based replacement
- Runs linters for additional auto-fixes
- Generates markdown summary

## CodeRabbit Verification Workflow (MANDATORY)

**CRITICAL: All code changes MUST be verified through CodeRabbit before a task is considered complete.** This is a non-negotiable requirement for code quality.

### How It Works

1. **User provides verification comments**: After reviewing changes (either manually or via CodeRabbit PR review), the user provides numbered verification comments with specific issues to fix.

2. **Comments format**: Each comment includes:
   - A title describing the issue
   - Specific instructions on what to change
   - File paths and code references
   - Expected behavior after the fix

3. **Implementation**: Claude must implement ALL verification comments exactly as specified, following the instructions verbatim.

4. **Build verification**: After implementing fixes, run the build to ensure no errors:
   ```bash
   # Frontend
   cd D:\AI\dashboard\frontend && npm run build

   # Python (if applicable)
   ruff check <modified_files>
   python -m py_compile <file.py>
   ```

5. **Task completion**: A task is ONLY complete when:
   - All verification comments have been addressed
   - The build passes without errors
   - No new issues are introduced

### Example Verification Comment Format

```markdown
## Comment 1: [Issue Title]

In `path/to/file.ext`, [description of the issue].

[Specific instructions on what to change, step by step]

After making these changes, verify [expected behavior].

### Referred Files
- path/to/file.ext
```

### Workflow Summary

```text
┌─────────────────────────────────────────────────────────────┐
│  1. Claude implements feature/fix                           │
│  2. Changes pushed to branch, PR created                    │
│  3. CodeRabbit automatically reviews PR                     │
│  4. Auto-fix workflow applies suggestions                   │
│  5. User reviews remaining issues, provides comments        │
│  6. Claude implements ALL comments verbatim                 │
│  7. Claude runs build to verify                             │
│  8. If build fails → fix and rebuild                        │
│  9. Task complete only when all comments fixed + build pass │
└─────────────────────────────────────────────────────────────┘
```

### Important Notes

- **Never skip verification**: Even if changes seem correct, wait for user verification comments
- **Follow instructions exactly**: Implement comments verbatim, not interpretively
- **Fix ALL comments**: Do not mark task complete until every comment is addressed
- **Build must pass**: A failing build means the task is not complete
- **Report blockers**: If a verification comment cannot be implemented as written, explain why and ask for clarification
