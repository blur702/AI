# MCP Documentation Search Server

MCP server for semantic documentation search using Weaviate.

## Overview

This server provides a `search_documentation` tool that performs semantic similarity search over documentation stored in a Weaviate vector database. It's designed to be used with VS Code (via Claude Code) or Claude Desktop.

## Prerequisites

1. **Weaviate** running on localhost:8080 (or configured URL)
2. **Ollama** running with the `nomic-embed-text` model (or configured model)
3. **Documentation ingested** via `api_gateway/services/doc_ingestion.py`

## Installation

```bash
cd mcp_servers/documentation
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate HTTP endpoint |
| `WEAVIATE_GRPC_HOST` | `localhost` | Weaviate gRPC host |
| `WEAVIATE_GRPC_PORT` | `50051` | Weaviate gRPC port |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model name |
| `LOG_LEVEL` | `INFO` | Logging level |

## Running

### Direct execution

```bash
python -m mcp_servers.documentation.main
```

### VS Code / Claude Code

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "documentation": {
      "command": "python",
      "args": ["-m", "mcp_servers.documentation.main"],
      "cwd": "<path-to-your-AI-workspace>"
    }
  }
}
```

**Note:** Replace `<path-to-your-AI-workspace>` with the absolute path to your AI workspace directory (e.g., `/home/user/AI` on Linux/macOS or `C:\\Users\\user\\AI` on Windows).

### Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "documentation": {
      "command": "python",
      "args": ["-m", "mcp_servers.documentation.main"],
      "cwd": "<path-to-your-AI-workspace>"
    }
  }
}
```

**Note:** Replace `<path-to-your-AI-workspace>` with the absolute path to your AI workspace directory.

## Available Tools

### `search_documentation`

Search documentation using semantic similarity.

**Parameters:**
- `query` (string, required): Search query text
- `limit` (integer, optional, default: 10): Maximum number of results (1-100)

**Returns:**

On success, returns a list of matching documentation chunks:
```json
[
  {
    "title": "Getting Started",
    "content": "This guide explains how to...",
    "file_path": "docs/getting-started.md",
    "section": "h1"
  }
]
```

On error, returns an object with an `error` key:

| Error Code | Description |
|------------|-------------|
| `collection_not_found` | Documentation collection doesn't exist. Run `doc_ingestion` first. |
| `connection_failed` | Failed to connect to Weaviate. Includes `message` with details. |
| `query_failed` | Query execution error. Includes `message` with details. |
| `invalid_limit` | Limit parameter out of range (must be 1-100). Includes `message`. |

**Error Response Examples:**
```json
{"error": "collection_not_found"}
```
```json
{"error": "connection_failed", "message": "Connection refused"}
```
```json
{"error": "invalid_limit", "message": "limit must be an integer between 1 and 100, got -5"}
```

**Successful Request Example:**
```json
{
  "name": "search_documentation",
  "arguments": {
    "query": "how to start the dashboard",
    "limit": 5
  }
}
```

**Client Integration Notes:**

When integrating with this tool, clients should:
1. Check if the response is an array (success) or object with `error` key (failure)
2. Handle `collection_not_found` by prompting user to run documentation ingestion
3. Handle `connection_failed` by checking Weaviate service status
4. Handle `invalid_limit` by validating limit before calling (1-100 range)

## Ingesting Documentation

Before using this server, ingest documentation into Weaviate:

```bash
cd api_gateway
python -m api_gateway.services.doc_ingestion ingest --verbose
```

To check ingestion status:

```bash
python -m api_gateway.services.doc_ingestion status
```

## Architecture

```
VS Code/Claude Desktop
        |
        | STDIO (JSON-RPC)
        v
   MCP Server (main.py)
        |
        | near_text query
        v
    Weaviate DB
        |
        | embedding generation
        v
      Ollama
```

The server uses STDIO transport (FastMCP default) for communication. All logging goes to stderr to avoid corrupting JSON-RPC messages on stdout.
