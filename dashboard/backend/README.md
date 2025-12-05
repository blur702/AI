# Dashboard Backend API

## Overview
Flask REST API server for GPU VRAM monitoring and Ollama model management. Provides real-time WebSocket updates for VRAM status.

## Prerequisites
- Python 3.10+
- NVIDIA GPU with nvidia-smi installed
- Ollama installed and running on localhost:11434

## Installation
```bash
cd d:/AI/dashboard/backend
pip install -r requirements.txt
```

## Running the Server
```bash
python app.py
```

Server runs on `http://localhost:5000`

## API Endpoints

1. **GET /api/vram/status** - Get current GPU memory status  
   Response:
   ```json
   {
     "gpu": {
       "name": "...",
       "total_mb": 0,
       "used_mb": 0,
       "free_mb": 0,
       "utilization": 0
     },
     "processes": []
   }
   ```

2. **GET /api/models/ollama/list** - List all available Ollama models  
   Response:
   ```json
   {
     "models": [
       {
         "name": "...",
         "id": "...",
         "size": "..."
       }
     ],
     "count": 0
   }
   ```

3. **GET /api/models/ollama/loaded** - List currently loaded models  
   Response:
   ```json
   {
     "models": [
       {
         "name": "...",
         "id": "...",
         "size": "...",
         "processor": "..."
       }
     ],
     "count": 0
   }
   ```

4. **POST /api/models/ollama/load** - Load a model into memory  
   Request:
   ```json
   {
     "model_name": "llama2"
   }
   ```
   Response:
   ```json
   {
     "success": true,
     "message": "...",
     "model_name": "llama2"
   }
   ```

5. **POST /api/models/ollama/unload** - Unload a model from memory  
   Request:
   ```json
   {
     "model_name": "llama2"
   }
   ```
   Response:
   ```json
   {
     "success": true,
     "message": "...",
     "model_name": "llama2"
   }
   ```

6. **POST /api/models/ollama/download** - Download a new model  
   Request:
   ```json
   {
     "model_name": "llama2"
   }
   ```
   Response:
   ```json
   {
     "success": true,
     "message": "Download started",
     "model_name": "llama2"
   }
   ```
   Progress updates are sent via WebSocket.

## WebSocket Events

- **vram_update** (receive) - Real-time GPU status updates every 2 seconds  
  Payload:
  ```json
  {
    "gpu": {
      "name": "...",
      "total_mb": 0,
      "used_mb": 0,
      "free_mb": 0,
      "utilization": 0
    },
    "processes": [],
    "timestamp": 0
  }
  ```

- **model_download_progress** (receive) - Model download progress  
  Payload:
  ```json
  {
    "model_name": "llama2",
    "progress": "...",
    "status": "downloading/complete/error"
  }
  ```

## Testing
Use curl or Postman to test endpoints:
```bash
curl http://localhost:5000/api/vram/status
curl -X POST http://localhost:5000/api/models/ollama/load -H "Content-Type: application/json" -d '{"model_name":"llama2"}'
```

## Architecture
Reuses logic from `d:/AI/vram_manager.py` for GPU monitoring and Ollama CLI operations. Extends with WebSocket support for real-time updates.
