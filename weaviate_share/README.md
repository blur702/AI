# Weaviate Knowledge Base - Portable Setup

A pre-indexed vector database with 52,000+ searchable entries across:
- **CodeEntity** (28k) - Python/TypeScript/JavaScript/CSS/Rust code
- **Documentation** (1k) - Markdown docs
- **DrupalAPI** (16k) - Drupal 11.x API reference
- **CongressionalData** (8k) - US House member press releases
- **MDN Docs** (6k) - JavaScript and Web API documentation

## Prerequisites

- **Docker Desktop** (Windows/Mac) or Docker (Linux)
- **Ollama** with `snowflake-arctic-embed:l` model for embeddings
- **Python 3.10+** with pip
- **Claude Code** or another MCP-compatible client

## Quick Start (15 minutes)

### Step 1: Install Ollama and Embedding Model

```bash
# Install Ollama from https://ollama.ai
# Then pull the embedding model:
ollama pull snowflake-arctic-embed:l
```

### Step 2: Start Weaviate with Docker

```bash
# Create docker-compose.yml (or use the one in config/)
docker-compose -f config/docker-compose.yml up -d
```

Or create a minimal docker-compose.yml:

```yaml
version: '3.8'
services:
  weaviate:
    image: semitechnologies/weaviate:1.28.4
    ports:
      - "8080:8080"
      - "50051:50051"
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'
      PERSISTENCE_DATA_PATH: '/var/lib/weaviate'
      DEFAULT_VECTORIZER_MODULE: 'none'
      ENABLE_MODULES: ''
      CLUSTER_HOSTNAME: 'node1'
    volumes:
      - weaviate_data:/var/lib/weaviate
    restart: unless-stopped

volumes:
  weaviate_data:
```

### Step 3: Restore the Database

```bash
# Stop Weaviate first
docker-compose down

# Extract backup into the Docker volume
docker run --rm \
  -v weaviate_data:/data \
  -v $(pwd)/data:/backup \
  alpine sh -c "cd /data && tar xzf /backup/weaviate_data.tar.gz"

# Start Weaviate again
docker-compose up -d
```

### Step 4: Verify It Works

```bash
# Check Weaviate is healthy
curl http://localhost:8080/v1/.well-known/ready

# Check collections exist
curl http://localhost:8080/v1/schema | python -m json.tool
```

### Step 5: Install MCP Server Dependencies

```bash
cd mcp_server
pip install -r requirements.txt
pip install fastmcp weaviate-client httpx
```

### Step 6: Configure Claude Code

Add to your Claude Code MCP settings (`~/.claude/mcp_settings.json` or VS Code settings):

```json
{
  "mcpServers": {
    "documentation": {
      "command": "python",
      "args": ["-m", "mcp_server.main"],
      "cwd": "/path/to/weaviate_share"
    }
  }
}
```

### Step 7: Test the MCP Tools

Restart Claude Code, then try:

```
Search for "entity storage interface" in Drupal API
```

## Available Search Tools

| Tool | What it searches | Example query |
|------|------------------|---------------|
| `search_code` | Functions, classes, methods | "authentication middleware" |
| `search_documentation` | Markdown docs | "how to start services" |
| `search_codebase` | Both code and docs | "how does VRAM monitoring work" |
| `search_drupal_api` | Drupal 11.x PHP API | "entity interface" |
| `search_congressional` | House member content | "infrastructure bill" |
| `search_mdn` | JavaScript/Web APIs | "fetch API promise" |

## Filters

### search_code filters:
- `entity_type`: function, method, class, interface, style, animation
- `service_name`: core, alltalk, audiocraft, comfyui, etc.
- `language`: python, typescript, javascript, css, rust

### search_drupal_api filters:
- `entity_type`: class, interface, trait, function, method, hook

### search_congressional filters:
- `state`: Two-letter code (CA, TX, NY, etc.)
- `party`: Republican, Democrat

### search_mdn filters:
- `collection`: javascript, webapi

## Troubleshooting

### "Connection refused" error
- Make sure Weaviate is running: `docker ps`
- Check port 8080 is not in use: `netstat -an | grep 8080`

### "Embedding failed" error
- Make sure Ollama is running: `ollama list`
- Load the embedding model: `ollama run snowflake-arctic-embed:l ""`

### "Collection not found" error
- The backup may not have restored correctly
- Check collections: `curl http://localhost:8080/v1/schema`

### Slow first query
- Normal! First query loads the embedding model into VRAM
- Subsequent queries will be fast

## File Structure

```
weaviate_share/
├── README.md              # This file
├── data/
│   └── weaviate_data.tar.gz  # Database backup (369MB)
├── mcp_server/
│   ├── main.py            # MCP server with all search tools
│   ├── requirements.txt   # Python dependencies
│   └── README.md          # MCP server documentation
└── config/
    ├── docker-compose.yml # Weaviate Docker config
    ├── weaviate_connection.py  # Connection utilities
    └── mcp_settings.py    # MCP server settings
```

## Updating the Database

To add new content, you'll need the ingestion scripts from the original project:
- `code_ingestion.py` - Index source code
- `doc_ingestion.py` - Index markdown files
- `drupal_scraper.py` - Scrape Drupal API
- `congressional_scraper.py` - Scrape congressional data

## Credits

Built with:
- [Weaviate](https://weaviate.io/) - Vector database
- [Ollama](https://ollama.ai/) - Local embedding model
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
