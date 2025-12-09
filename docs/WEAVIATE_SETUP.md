# Weaviate Vector Database Setup Guide

**Last Updated:** December 6, 2025
**Purpose:** Long-term memory and RAG capabilities for the API Gateway

---

## Overview

Weaviate is a vector database that provides semantic search and retrieval-augmented generation (RAG) capabilities. This setup uses Docker to run Weaviate with the `text2vec-ollama` module, enabling embedding generation via the locally running Ollama instance.

**Architecture:**
```
┌─────────────────────┐     ┌─────────────────────────────┐
│   API Gateway       │────▶│   Weaviate Container        │
│   (port 1301)       │     │   (port 8080 HTTP)          │
└─────────────────────┘     │   (port 50051 gRPC)         │
                            └──────────────┬──────────────┘
                                           │
                            ┌──────────────▼──────────────┐
                            │   Ollama (host)             │
                            │   (port 11434)              │
                            │   via host.docker.internal  │
                            └─────────────────────────────┘
```

---

## Prerequisites

### 1. Docker Desktop for Windows

**Installation:**
1. Download Docker Desktop from https://www.docker.com/products/docker-desktop/
2. Run the installer and follow the prompts
3. Restart your computer when prompted
4. Launch Docker Desktop and complete the initial setup

**Verify Installation:**
```powershell
docker --version
docker-compose --version
```

### 2. System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM for Weaviate | 4GB | 8GB |
| Disk Space | 10GB | 50GB+ (depends on data) |
| Docker Desktop | Latest stable | Latest stable |

### 3. Ollama with Embedding Model

Ollama should already be installed. Download the embedding model:

```powershell
ollama pull snowflake-arctic-embed:l
```

Verify Ollama is running:
```powershell
curl http://localhost:11434/api/tags
```

---

## Installation Steps

### Step 1: Start Weaviate

Navigate to the api_gateway directory from your project root and run the startup script:

**Windows:**
```powershell
# From project root (e.g., D:\AI or /path/to/AI)
cd api_gateway
.\start_weaviate.bat
```

**macOS/Linux:**
```bash
# From project root
cd api_gateway
docker-compose up -d
```

The script will:
1. Check if Docker Desktop is running
2. Warn if Ollama is not available (non-blocking)
3. Start the Weaviate container
4. Perform a health check

### Step 2: Verify Weaviate is Running

**Health Check:**
```powershell
curl http://localhost:8080/v1/.well-known/ready
```

Expected response:
```json
{}
```

**Check Weaviate Meta Info:**
```powershell
curl http://localhost:8080/v1/meta
```

### Step 3: Verify Ollama Connection

Test that Weaviate can reach Ollama for embeddings:

```powershell
curl http://localhost:8080/v1/modules
```

Look for `text2vec-ollama` in the response.

---

## Configuration

### Environment Variables

Add these to your `.env` file (copy from `.env.example`):

```
WEAVIATE_URL=http://localhost:8080
WEAVIATE_GRPC_HOST=localhost
WEAVIATE_GRPC_PORT=50051
OLLAMA_EMBEDDING_MODEL=snowflake-arctic-embed:l
```

| Variable | Description | Default |
|----------|-------------|---------|
| `WEAVIATE_URL` | HTTP endpoint for Weaviate | `http://localhost:8080` |
| `WEAVIATE_GRPC_HOST` | gRPC host for high-performance connections | `localhost` |
| `WEAVIATE_GRPC_PORT` | gRPC port | `50051` |
| `OLLAMA_EMBEDDING_MODEL` | Default embedding model | `snowflake-arctic-embed:l` |

### Customizing the Embedding Model

To use a different embedding model:

1. Pull the model in Ollama:
   ```powershell
   ollama pull mxbai-embed-large
   ```

2. Update your `.env` file:
   ```
   OLLAMA_EMBEDDING_MODEL=mxbai-embed-large
   ```

**Popular Embedding Models:**
- `snowflake-arctic-embed:l` - State-of-the-art retrieval quality, 1024 dims (recommended)
- `nomic-embed-text` - Good balance of speed and quality, 768 dims
- `mxbai-embed-large` - Higher quality, slower, 1024 dims
- `all-minilm` - Fast, smaller model

### Authentication

Currently, anonymous access is enabled for development. To enable authentication:

1. Edit `docker-compose.yml`:
   ```yaml
   AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'false'
   AUTHENTICATION_APIKEY_ENABLED: 'true'
   AUTHENTICATION_APIKEY_ALLOWED_KEYS: 'your-api-key-here'
   ```

2. Restart Weaviate:
   ```powershell
   docker-compose down
   docker-compose up -d
   ```

### Data Persistence

Data is persisted in the Docker volume `weaviate_data`. This survives container restarts.

**Backup:**
```powershell
docker run --rm -v weaviate_data:/data -v ${PWD}:/backup alpine tar czf /backup/weaviate_backup.tar.gz /data
```

**Restore:**
```powershell
docker run --rm -v weaviate_data:/data -v ${PWD}:/backup alpine tar xzf /backup/weaviate_backup.tar.gz -C /
```

---

## Architecture Details

### Container → Host Communication

On Windows with Docker Desktop, containers access host services via `host.docker.internal`. The docker-compose.yml configures:

```yaml
OLLAMA_API_ENDPOINT: 'http://host.docker.internal:11434'
```

This allows the Weaviate container to reach Ollama running natively on the Windows host.

### Port Mappings

| Port | Protocol | Purpose |
|------|----------|---------|
| 8080 | HTTP | REST API, GraphQL endpoint |
| 50051 | gRPC | High-performance client connections |

### Data Flow for Embedding Generation

1. Client sends text to Weaviate
2. Weaviate calls Ollama via `host.docker.internal:11434`
3. Ollama generates embedding using configured model (default: `snowflake-arctic-embed:l`)
4. Weaviate stores the text + embedding vector
5. Future queries use vector similarity for semantic search

---

## Troubleshooting

### Docker Not Running

**Error:** `ERROR: Docker is not running. Please start Docker Desktop first.`

**Solution:**
1. Open Docker Desktop application
2. Wait for Docker to fully start (whale icon in system tray is stable)
3. Run `start_weaviate.bat` again

### Ollama Not Accessible

**Error:** `WARNING: Ollama does not appear to be running on port 11434.`

**Solution:**
1. Start Ollama if not running
2. Verify with: `curl http://localhost:11434/api/tags`
3. Weaviate will work once Ollama is available

### Port Conflicts

**Error:** Port 8080 or 50051 already in use

**Solution:**
1. Check what's using the port:
   ```powershell
   netstat -ano | findstr :8080
   ```
2. Either stop the conflicting service or modify `docker-compose.yml`:
   ```yaml
   ports:
     - "8081:8080"  # Change host port
   ```

### Embedding Generation Fails

**Symptoms:** Weaviate returns errors when adding objects with vectorizer

**Checks:**
1. Verify Ollama is running: `ollama ps`
2. Verify the embedding model is available: `ollama list`
3. Check Weaviate logs: `docker-compose logs -f`

### Data Persistence Issues

**Reset Everything:**
```powershell
docker-compose down -v  # -v removes volumes
docker-compose up -d
```

### View Container Logs

```powershell
docker-compose logs -f
```

### Restart Weaviate

```powershell
docker-compose restart
```

---

## Testing the Setup

### Python Test Script

```python
import weaviate
from weaviate.classes.config import Configure, Property, DataType

# Connect to Weaviate
client = weaviate.connect_to_local()

try:
    # Check if connected
    print(f"Weaviate is ready: {client.is_ready()}")

    # Create a test collection with Ollama vectorizer
    if not client.collections.exists("TestCollection"):
        client.collections.create(
            name="TestCollection",
            vectorizer_config=Configure.Vectorizer.text2vec_ollama(
                api_endpoint="http://host.docker.internal:11434",
                model="snowflake-arctic-embed:l"
            ),
            properties=[
                Property(name="text", data_type=DataType.TEXT),
            ]
        )
        print("Created TestCollection")

    # Get the collection
    collection = client.collections.get("TestCollection")

    # Add a test object
    uuid = collection.data.insert({
        "text": "This is a test document for semantic search."
    })
    print(f"Inserted object with UUID: {uuid}")

    # Perform a semantic search
    response = collection.query.near_text(
        query="search query",
        limit=1
    )
    print(f"Search results: {response.objects}")

    # Cleanup
    collection.data.delete_many(where=None)
    client.collections.delete("TestCollection")
    print("Cleanup completed")

finally:
    client.close()
```

### Curl Test

**Create a collection:**
```powershell
curl -X POST http://localhost:8080/v1/schema -H "Content-Type: application/json" -d '{
  "class": "Article",
  "vectorizer": "text2vec-ollama",
  "moduleConfig": {
    "text2vec-ollama": {
      "apiEndpoint": "http://host.docker.internal:11434",
      "model": "snowflake-arctic-embed:l"
    }
  },
  "properties": [
    {"name": "title", "dataType": ["text"]},
    {"name": "content", "dataType": ["text"]}
  ]
}'
```

**Add an object:**
```powershell
curl -X POST http://localhost:8080/v1/objects -H "Content-Type: application/json" -d '{
  "class": "Article",
  "properties": {
    "title": "Hello World",
    "content": "This is a test article about AI and machine learning."
  }
}'
```

**Query with GraphQL:**
```powershell
curl -X POST http://localhost:8080/v1/graphql -H "Content-Type: application/json" -d '{
  "query": "{ Get { Article(nearText: {concepts: [\"artificial intelligence\"]}) { title content } } }"
}'
```

---

## Next Steps

### Phase 2: API Gateway Integration

A `vector_service.py` will be created to integrate Weaviate with the API Gateway, providing:

- Conversation history storage with semantic search
- Document/knowledge base for RAG
- User-specific memory isolation

### Phase 3: Documentation Ingestion Service

The API Gateway includes a standalone documentation ingestion service that:

- Scans markdown files in the workspace (`docs/` and selected root `.md` files)
- Chunks content by markdown headers for semantic coherence
- Ingests chunks into a `Documentation` collection in Weaviate using `text2vec-ollama` with the configured embedding model (default: `snowflake-arctic-embed:l`)

**Service Location**

- Module: `api_gateway/services/doc_ingestion.py`
- Collection name: `Documentation`

**CLI Usage (from project root)**

```powershell
cd api_gateway

# Run initial ingestion
python -m api_gateway.services.doc_ingestion ingest --verbose

# Force reindex (delete and recreate collection, then ingest)
python -m api_gateway.services.doc_ingestion reindex --verbose

# Check collection status (object count)
python -m api_gateway.services.doc_ingestion status

# Dry run (scan and chunk without ingesting)
python -m api_gateway.services.doc_ingestion ingest --dry-run --verbose
```

**Expected Output (example)**

```text
[INFO] Connecting to Weaviate at http://localhost:8080 (gRPC localhost:50051)
[INFO] Found 16 markdown files for ingestion
[INFO] Created 8 chunks from docs/WEAVIATE_SETUP.md
[INFO] Created 12 chunks from docs/PROJECT_STRUCTURE.md
...
[INFO] Ingestion complete: 16 files, 127 chunks, 0 errors
```

**Status Command**

The `status` command reports basic statistics for the `Documentation` collection:

- Total object count via `collection.aggregate.over_all(total_count=True)`

Use this to quickly verify that documents have been ingested.

**Troubleshooting**

- Ensure Weaviate is running (`start_weaviate.bat` / `docker-compose up -d`)
- Ensure Ollama is running with the configured embedding model:
  - `ollama pull snowflake-arctic-embed:l`
  - `ollama ps` / `ollama list`
- Check `api_gateway.log` for detailed ingestion and connection logs

### Useful Resources

- **Weaviate Documentation:** https://weaviate.io/developers/weaviate
- **Python Client:** https://weaviate.io/developers/weaviate/client-libraries/python
- **Ollama Embedding Models:** https://ollama.ai/library?category=embedding
- **text2vec-ollama Module:** https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-ollama

---

## Embedding Model Migration

When changing embedding models (e.g., from `nomic-embed-text` to `snowflake-arctic-embed:l`), you **must re-embed the entire corpus**. Different models produce vectors with different dimensions and semantics that cannot be mixed.

### Why Migration is Required

| Model | Dimensions | Context |
|-------|-----------|---------|
| nomic-embed-text | 768 | 8192 |
| snowflake-arctic-embed:l | 1024 | 512 |
| mxbai-embed-large | 1024 | 512 |

Vectors from different models are incompatible - you cannot query embeddings created by one model using vectors from another.

### Migration Steps

1. **Verify the new model is available:**
   ```powershell
   ollama pull snowflake-arctic-embed:l
   ollama list
   ```

2. **Update environment configuration:**
   ```powershell
   # Edit .env (both root and api_gateway/.env)
   OLLAMA_EMBEDDING_MODEL=snowflake-arctic-embed:l
   ```

3. **Check current status:**
   ```powershell
   python -m api_gateway.services.migrate_embeddings check
   ```

4. **Preview migration (dry run):**
   ```powershell
   python -m api_gateway.services.migrate_embeddings migrate --dry-run
   ```

5. **Perform full migration:**
   ```powershell
   python -m api_gateway.services.migrate_embeddings migrate
   ```

   This will:
   - Delete all existing collections (Documentation, CodeEntity, DrupalAPIEntity)
   - Re-ingest Documentation from markdown files
   - Re-ingest CodeEntity from source code
   - Create empty DrupalAPIEntity collection

6. **Re-populate Drupal data (if needed):**
   ```powershell
   python -m api_gateway.services.drupal_scraper scrape
   ```

### Migration Script Reference

| Command | Description |
|---------|-------------|
| `migrate_embeddings check` | Show configured model and collection status |
| `migrate_embeddings migrate --dry-run` | Preview what would be deleted/re-indexed |
| `migrate_embeddings migrate` | Perform full migration (interactive confirmation) |

---

## Management Commands

| Command | Description |
|---------|-------------|
| `docker-compose up -d` | Start Weaviate in background |
| `docker-compose down` | Stop Weaviate |
| `docker-compose down -v` | Stop and remove data |
| `docker-compose logs -f` | View live logs |
| `docker-compose restart` | Restart Weaviate |
| `docker-compose ps` | Check container status |

---

*This document is part of the AI Workspace documentation. See `PROJECT_STRUCTURE.md` for the full system overview.*
