# Congressional Query Module

Query LLM about congressional members with voting records via SSH tunnel to remote Ollama and Weaviate services.

## Features

- **Query Form**: Simple form to submit questions about congressional members
- **Chat Interface**: Multi-turn conversation interface with message history
- **Source Citations**: Display source documents with member information and party affiliation
- **Member Filtering**: Filter results by specific congressional members
- **Connection Status Block**: Real-time status monitoring for SSH, Ollama, and Weaviate
- **Admin Dashboard**: Query statistics, logs, and system status overview
- **REST API**: External API endpoints for query and chat functionality

## Requirements

- Drupal 9, 10, or 11
- PHP 8.1+
- Composer
- Remote server with:
  - Ollama LLM service (port 11434)
  - Weaviate vector database (port 8080)
  - SSH access

## Installation

1. Copy the module to your Drupal modules directory:
   ```bash
   cp -r congressional_query /path/to/drupal/modules/custom/
   ```

2. Install PHP dependencies:
   ```bash
   cd /path/to/drupal/modules/custom/congressional_query
   composer install
   ```

3. Enable the module:
   ```bash
   drush en congressional_query
   ```

4. Configure the module at `/admin/config/services/congressional-query`

## Configuration

### SSH Settings

| Setting | Description |
|---------|-------------|
| SSH Host | Remote server hostname or IP |
| SSH Port | SSH port (default: 22) |
| SSH Username | SSH login username |
| SSH Password | SSH password (optional if using key) |
| Private Key Path | Path to SSH private key file |

### Ollama Settings

| Setting | Description |
|---------|-------------|
| Ollama Endpoint | API endpoint (default: http://localhost:11434) |
| LLM Model | Model for answer generation (default: qwen3-coder-roo:latest) |
| Embedding Model | Model for embeddings (default: snowflake-arctic-embed:l) |
| Temperature | Generation temperature 0.0-2.0 (default: 0.3) |

### Weaviate Settings

| Setting | Description |
|---------|-------------|
| Weaviate URL | HTTP endpoint (default: http://localhost:8080) |
| gRPC Port | gRPC port (default: 50051) |
| Collection | Collection name (default: CongressionalData) |

### Query Settings

| Setting | Description |
|---------|-------------|
| Default Num Sources | Sources to retrieve per query (default: 8) |
| Max Context Length | Max characters per source (default: 1500) |
| Log Retention Days | Days to keep query logs (default: 90) |
| Session Timeout Hours | Conversation session timeout (default: 24) |

## Usage

### Query Form

Access at `/congressional/query`

1. Enter your question about congressional members
2. Optionally filter by member name
3. Adjust number of sources if needed
4. Submit to receive an answer with source citations

### Chat Interface

Access at `/congressional/chat`

1. Type questions in the input field
2. View responses with expandable source citations
3. Continue conversation with follow-up questions
4. Click example questions to get started

### Connection Status Block

Add the "Congressional Query Connection Status" block to any region to monitor:
- SSH tunnel status
- Ollama LLM connectivity
- Weaviate database status

Configure auto-refresh interval and detail display in block settings.

### Admin Dashboard

Access at `/admin/reports/congressional-query`

View:
- Total queries and daily/weekly stats
- Average response times
- Top member filters used
- Recent query history
- System status overview

## REST API

### Query Endpoint

```
POST /api/congressional/query
Content-Type: application/json

{
  "question": "What are the policy priorities for Texas representatives?",
  "member_filter": "Greene",
  "num_sources": 8
}
```

Response:
```json
{
  "query_id": 123,
  "answer": "Based on the sources...",
  "sources": [...],
  "model": "qwen3-coder-roo:latest",
  "response_time_ms": 2500
}
```

### Chat Endpoint

Send message:
```
POST /api/congressional/chat
Content-Type: application/json

{
  "message": "Tell me about recent votes on infrastructure",
  "conversation_id": "abc-123-def",
  "member_filter": null
}
```

Get conversation history:
```
GET /api/congressional/chat/{conversation_id}
```

## Permissions

| Permission | Description |
|------------|-------------|
| Use Congressional Query | Access query forms and chat interface |
| Administer Congressional Query | Configure SSH, Ollama, and Weaviate settings |
| View Query Logs | Access query history and statistics |

## Architecture

```
User Request
    |
    v
[Drupal] --SSH--> [Remote Server]
    |                   |
    |              [Ollama LLM]
    |                   |
    |              [Weaviate DB]
    |                   |
    v                   v
Generate Embedding --> Vector Search
    |                   |
    v                   v
Format Context <-- Retrieve Sources
    |
    v
Generate Answer
    |
    v
Display with Citations
```

## Troubleshooting

### SSH Connection Failed

1. Verify SSH credentials in configuration
2. Check if remote server is accessible
3. Ensure SSH key permissions are correct (600)
4. Test connection manually: `ssh user@host`

### Ollama Not Responding

1. Verify Ollama is running on remote server
2. Check endpoint configuration
3. Ensure required models are loaded
4. Test via curl: `curl http://localhost:11434/api/tags`

### Weaviate Connection Error

1. Verify Weaviate is running on remote server
2. Check URL configuration
3. Verify CongressionalData collection exists
4. Test via curl: `curl http://localhost:8080/v1/meta`

### Slow Response Times

1. Check network latency to remote server
2. Reduce number of sources retrieved
3. Ensure embedding model is loaded in Ollama
4. Consider caching frequently asked questions

## Drupal Core Updates

For instructions on updating Drupal core to version 11.3.0 or higher, see the [Drupal Core Update Guide](../../docs/DRUPAL_CORE_UPDATE.md).

**Important**: Keeping Drupal core updated is essential for continued security coverage. Drupal 11.2.x will reach end-of-life when Drupal 11.4.0 is released.

The Congressional Query module is compatible with Drupal 11.3.0 and has been tested with:
- Drupal 9.x, 10.x, and 11.x
- PHP 8.1 through 8.4
- Drush 12.x and 13.x

## Related Documentation

| Document | Description |
|----------|-------------|
| [Drupal Core Update Guide](../../docs/DRUPAL_CORE_UPDATE.md) | Update Drupal core to 11.3.0 |
| [Webform Libraries Installation](../WEBFORM_LIBRARIES_INSTALLATION.md) | Install external libraries for Webform module |
| [Webform Libraries Quick Start](../WEBFORM_LIBRARIES_QUICKSTART.md) | Quick reference for library installation |

**Note**: If using Webform elements in forms that interact with this module, ensure the Webform external libraries are installed locally for optimal performance. See the Webform Libraries documentation for details.

## Development

### File Structure

```
congressional_query/
├── congressional_query.info.yml
├── congressional_query.install
├── congressional_query.module
├── congressional_query.permissions.yml
├── congressional_query.routing.yml
├── congressional_query.services.yml
├── congressional_query.libraries.yml
├── composer.json
├── config/
│   ├── install/
│   │   └── congressional_query.settings.yml
│   └── schema/
│       └── congressional_query.schema.yml
├── src/
│   ├── Controller/
│   │   ├── CongressionalAdminController.php
│   │   ├── CongressionalChatController.php
│   │   ├── CongressionalHealthController.php
│   │   └── CongressionalQueryController.php
│   ├── Form/
│   │   ├── CongressionalConfigForm.php
│   │   └── CongressionalQueryForm.php
│   ├── Plugin/
│   │   ├── Block/
│   │   │   └── ConnectionStatusBlock.php
│   │   └── rest/
│   │       └── resource/
│   │           ├── CongressionalChatResource.php
│   │           └── CongressionalQueryResource.php
│   └── Service/
│       ├── ConversationManager.php
│       ├── OllamaLLMService.php
│       ├── SSHTunnelService.php
│       └── WeaviateClientService.php
├── templates/
│   ├── congressional-admin-dashboard.html.twig
│   ├── congressional-query-chat.html.twig
│   ├── congressional-query-form.html.twig
│   ├── congressional-query-results.html.twig
│   ├── congressional-query-source.html.twig
│   └── connection-status-block.html.twig
├── js/
│   ├── congressional-chat.js
│   └── connection-status.js
├── css/
│   └── congressional-query.css
└── README.md
```

## License

GPL-2.0-or-later
