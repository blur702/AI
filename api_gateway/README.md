# API Gateway (Port 1301)

This service is a FastAPI-based unified API gateway that coordinates multiple GPU-backed AI services behind a single authenticated interface.

## Overview

- Runs on port `1301`
- Provides a unified job queue with REST and WebSocket access
- Manages GPU VRAM usage via the central VRAM manager
- Enforces API key authentication on all endpoints

## Authentication

All endpoints require an API key passed in the `X-API-Key` header.

### Create an API key

```bash
curl -X POST http://localhost:1301/auth/keys \
  -H "Content-Type: application/json" \
  -d '{"name": "mobile-app"}'
```

Response:

```json
{
  "success": true,
  "data": {
    "key": "generated-key",
    "name": "mobile-app",
    "created_at": "..."
  },
  "error": null,
  "timestamp": "..."
}
```

Use the returned `key` value as:

```bash
-H \"X-API-Key: generated-key\"
```

## Job Queue

- Create jobs via generation / TTS / LLM endpoints.
- Poll job status using `GET /jobs/{job_id}`.
- Subscribe to live updates via `GET /ws/jobs/{job_id}` WebSocket.

Example polling:

```bash
curl -X GET http://localhost:1301/jobs/<job_id> \
  -H \"X-API-Key: YOUR_KEY\"
```

WebSocket example (JavaScript):

```js
const ws = new WebSocket(\"ws://localhost:1301/jobs/ws/jobs/\" + jobId);
ws.onmessage = (event) => {
  console.log(\"Job update:\", JSON.parse(event.data));
};
```

## Endpoints

- `POST /generate/image` – Image generation (ComfyUI)
- `POST /generate/video` – Video generation (Wan2GP)
- `POST /generate/audio` – Audio generation (Stable Audio / AudioCraft)
- `POST /generate/music` – Music generation (YuE / DiffRhythm / MusicGPT)
- `POST /tts` – Text-to-speech (AllTalk)
- `POST /llm/generate` – LLM text generation (Ollama)
- `GET /llm/models` – List Ollama models
- `GET /jobs/{job_id}` – Get job status
- `GET /jobs` – List recent jobs
- `DELETE /jobs/{job_id}` – Cancel job
- `GET /ws/jobs/{job_id}` – WebSocket job updates
- `GET /health` – Health check

All responses follow a unified format:

```json
{
  \"success\": true,
  \"data\": { \"job_id\": \"uuid\", \"status\": \"pending\" },
  \"error\": null,
  \"timestamp\": \"...\"
}
```

Error example:

```json
{
  \"success\": false,
  \"data\": null,
  \"error\": {
    \"code\": \"SERVICE_UNAVAILABLE\",
    \"message\": \"ComfyUI service is not responding\"
  },
  \"timestamp\": \"...\"
}
```

## Vector Database

The API Gateway integrates with Weaviate for long-term memory and RAG capabilities:

- **Weaviate:** `http://localhost:8080` (Docker container)
- **Embedding Model:** snowflake-arctic-embed:l (via Ollama)
- **Features:** Conversation history, document RAG, semantic search

### Starting Weaviate

**Windows:**
```cmd
cd api_gateway
start_weaviate.bat
```

**macOS/Linux:**
```bash
cd api_gateway
docker-compose up -d
```

**Platform-agnostic (recommended):**
```bash
# From project root, navigate to api_gateway
cd api_gateway
docker-compose up -d
```

### Verifying Weaviate

```bash
curl http://localhost:8080/v1/.well-known/ready
```

See `docs/WEAVIATE_SETUP.md` for detailed setup and configuration.

## Backend Services

The gateway routes to the following services:

- ComfyUI: `http://localhost:8188`
- AllTalk: `http://localhost:7851`
- Ollama: `http://localhost:11434`
- Wan2GP: `http://localhost:7860`
- YuE: `http://localhost:7870`
- DiffRhythm: `http://localhost:7871`
- Stable Audio: `http://localhost:7873`

## VRAM Management

The gateway calls into `vram_manager.py` to:

- Inspect GPU usage and processes
- Inspect and stop Ollama models to free VRAM
- Ensure only one GPU-intensive service runs at a time

## Mobile App Integration

Mobile or web clients:

- Obtain an API key via `/auth/keys`
- Submit generation / TTS / LLM requests
- Poll via `/jobs/{job_id}` or subscribe via WebSocket `/ws/jobs/{job_id}` for status updates

