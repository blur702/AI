# MCP Servers

Model Context Protocol (MCP) servers that provide AI assistants with access to the codebase's semantic search capabilities.

## Available Servers

### Documentation Search Server

Provides semantic search over code and documentation stored in Weaviate.

**Location:** `mcp_servers/documentation/`

**Tools Provided:**

| Tool | Description |
|------|-------------|
| `search_documentation` | Search markdown docs by semantic similarity |
| `search_code` | Search code entities (functions, classes, etc.) with filters |
| `search_codebase` | Combined search across docs and code |

## Quick Start

### Prerequisites

1. **Weaviate** running on `http://localhost:8080`
2. **Ollama** running on `http://127.0.0.1:11434` with embedding model
3. **Python** with dependencies from `api_gateway/requirements.txt`

### Manual Testing

```bash
# Start the server manually (for testing)
D:\AI\mcp_servers\start_mcp_server.bat
```

## Integration with AI Assistants

### Claude Code (CLI)

The MCP server is automatically available when Claude Code is run from `D:\AI`. The configuration is in `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": ["mcp__documentation__search_code"]
  }
}
```

### Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "documentation": {
      "command": "python",
      "args": ["-m", "mcp_servers.documentation.main"],
      "cwd": "D:\\AI"
    }
  }
}
```

## Tool Reference

### search_documentation

Search markdown documentation by semantic similarity.

**Parameters:**
- `query` (string, required): Search query text
- `limit` (int, optional): Max results 1-100 (default: 10)

**Returns:**
```json
[
  {
    "title": "Section Title",
    "content": "Section content...",
    "file_path": "docs/guide.md",
    "section": "h2"
  }
]
```

### search_code

Search code entities (functions, classes, methods, etc.) with optional filters.

**Parameters:**
- `query` (string, required): Natural language description
- `limit` (int, optional): Max results 1-100 (default: 10)
- `entity_type` (string, optional): Filter by type
  - Values: `function`, `method`, `class`, `variable`, `interface`, `type`, `style`, `animation`, `struct`, `trait`, `enum`, `impl`, `constant`, `static`
- `service_name` (string, optional): Filter by service
  - Values: `core`, `alltalk`, `audiocraft`, `comfyui`, `diffrhythm`, `musicgpt`, `stable_audio`, `wan2gp`, `yue`
- `language` (string, optional): Filter by language
  - Values: `python`, `typescript`, `javascript`, `css`, `rust`

**Returns:**
```json
[
  {
    "entity_type": "function",
    "name": "search_code",
    "full_name": "mcp_servers.documentation.main::search_code",
    "signature": "def search_code(query: str, limit: int = 10, ...) -> SearchResponse",
    "file_path": "mcp_servers/documentation/main.py:158",
    "docstring": "Search code entities using semantic similarity...",
    "source_code": "def search_code(...",
    "service_name": "core"
  }
]
```

### search_codebase

Combined search across both documentation and code.

**Parameters:**
- `query` (string, required): Search query text
- `limit` (int, optional): Total max results (split between docs and code)

**Returns:**
```json
[
  {
    "source": "documentation",
    "title": "...",
    "content": "..."
  },
  {
    "source": "code",
    "entity_type": "function",
    "name": "..."
  }
]
```

## Example Queries

```
# Find authentication-related code
search_code("user authentication login")

# Find React components in the dashboard
search_code("react component", language="typescript", service_name="core")

# Find documentation about VRAM management
search_documentation("GPU VRAM memory management")

# Understand how a feature works (docs + code)
search_codebase("how does the scraper supervisor work")
```

## Configuration

Environment variables (set in `.env` or shell):

| Variable | Default | Description |
|----------|---------|-------------|
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate HTTP endpoint |
| `WEAVIATE_GRPC_HOST` | `localhost` | Weaviate gRPC host |
| `WEAVIATE_GRPC_PORT` | `50051` | Weaviate gRPC port |
| `OLLAMA_API_ENDPOINT` | `http://127.0.0.1:11434` | Ollama API for embeddings |
| `OLLAMA_EMBEDDING_MODEL` | `snowflake-arctic-embed:l` | Embedding model |
| `LOG_LEVEL` | `INFO` | Logging level |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   AI Assistant  │     │   MCP Server    │     │    Weaviate     │
│     (Claude)     │────▶│  (STDIO/JSON)   │────▶│  (Vector DB)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │     Ollama      │
                        │  (Embeddings)   │
                        └─────────────────┘
```

## Troubleshooting

### "collection_not_found" error

Run the ingestion scripts to populate Weaviate:

```bash
python -m api_gateway.services.doc_ingestion reindex
python -m api_gateway.services.code_ingestion reindex --service all
```

### "connection_failed" error

Ensure Weaviate is running:

```bash
# Check Weaviate health
curl http://localhost:8080/v1/.well-known/ready
```

### "embedding_failed" error

Ensure Ollama is running with the embedding model:

```bash
ollama list  # Should show snowflake-arctic-embed:l
ollama pull snowflake-arctic-embed:l  # If not present
```

## Development

### Running Tests

```bash
cd D:\AI
python -m pytest mcp_servers/documentation/tests/ -v
```

### Adding New Tools

1. Add a new function decorated with `@mcp.tool()` in `main.py`
2. Follow the existing patterns for error handling and logging
3. Update this README with the new tool documentation
