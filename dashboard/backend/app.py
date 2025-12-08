import logging
import os
import subprocess
import threading
import time

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from flask_socketio import SocketIO
import requests as http_requests

from service_manager import get_service_manager, ServiceStatus
from services_config import SERVICES
from ingestion_manager import get_ingestion_manager
from claude_manager import get_claude_manager

# Path to React build output
FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))

# Don't use Flask's built-in static serving - we'll handle it manually
app = Flask(__name__, static_folder=None)
CORS(app, resources={r"/*": {"origins": "*"}})

# Explicit async_mode for compatibility on Windows; threading works well here.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# Proxy configuration
MAX_PROXY_REQUEST_SIZE = int(os.environ.get("MAX_PROXY_REQUEST_SIZE", str(100 * 1024 * 1024)))  # 100MB default
PROXY_TIMEOUT_SECONDS = int(os.environ.get("PROXY_TIMEOUT_SECONDS", "30"))
PROXY_AUTH_ENABLED = os.environ.get("PROXY_AUTH_ENABLED", "false").lower() == "true"
PROXY_AUTH_TOKEN = os.environ.get("PROXY_AUTH_TOKEN", "").strip()

# Validate proxy authentication configuration
if PROXY_AUTH_ENABLED:
    if not PROXY_AUTH_TOKEN:
        logger.error(
            "FATAL: PROXY_AUTH_ENABLED is true but PROXY_AUTH_TOKEN is not set or empty. "
            "This would allow authentication with empty tokens, which is insecure. "
            "Please set a strong PROXY_AUTH_TOKEN environment variable or disable authentication."
        )
        raise SystemExit(1)
    logger.info("Proxy authentication enabled with configured token")
else:
    logger.info("Proxy authentication disabled")


vram_thread = None
vram_thread_lock = threading.Lock()
connected_clients = 0
vram_thread_stop = False
gpu_info_error = False


def emit_service_status(service_id: str, status: str, message: str = ""):
    """Callback for service manager to emit status updates via WebSocket."""
    socketio.emit(
        "service_status",
        {
            "service_id": service_id,
            "status": status,
            "message": message,
        },
    )


# Initialize service manager with WebSocket callback
service_manager = get_service_manager(emit_service_status)


def emit_ingestion_event(event_name: str, data: dict):
    """Callback for ingestion manager to emit events via WebSocket."""
    socketio.emit(event_name, data)


# Initialize ingestion manager with WebSocket callback
ingestion_manager = get_ingestion_manager(emit_ingestion_event)

# Initialize Claude manager with WebSocket callback
claude_manager = get_claude_manager(emit_ingestion_event, socketio.start_background_task)


def run_command(command):
    """Run a system command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except FileNotFoundError as exc:
        msg = f"Command not found: {command[0]} ({exc})"
        logger.error(msg)
        return False, "", msg
    except Exception as exc:  # noqa: BLE001
        msg = f"Error running command {command}: {exc}"
        logger.error(msg)
        return False, "", msg


def get_gpu_info():
    """Get GPU memory information using nvidia-smi.

    Reuses logic from vram_manager.get_gpu_info().
    """
    try:
        success, stdout, stderr = run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ]
        )
        if not success:
            if stderr:
                logger.error("Error getting GPU info: %s", stderr.strip())
            return None

        line = stdout.strip()
        if not line:
            return None

        parts = line.split(", ")
        if len(parts) < 5:
            return None

        return {
            "name": parts[0],
            "total_mb": int(parts[1]),
            "used_mb": int(parts[2]),
            "free_mb": int(parts[3]),
            "utilization": int(parts[4]),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting GPU info: %s", exc)
        return None


def get_gpu_processes():
    """Get processes using the GPU via nvidia-smi.

    Reuses logic from vram_manager.get_gpu_processes().
    """
    try:
        success, stdout, stderr = run_command(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader",
            ]
        )
        if not success:
            if stderr:
                logger.error("Error getting GPU processes: %s", stderr.strip())
            return []

        processes = []
        for line in stdout.strip().splitlines():
            if not line:
                continue
            if "Insufficient Permissions" in line or "[N/A]" in line:
                continue
            parts = line.split(", ")
            if len(parts) < 3:
                continue
            processes.append(
                {
                    "pid": parts[0].strip(),
                    "name": parts[1].strip(),
                    "memory": parts[2].strip(),
                }
            )
        return processes
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting GPU processes: %s", exc)
        return []


def get_available_ollama_models():
    """Get list of all available Ollama models.

    Reuses logic from vram_manager.get_available_ollama_models().
    """
    try:
        success, stdout, stderr = run_command(["ollama", "list"])
        if not success:
            if stderr:
                logger.error("Error listing Ollama models: %s", stderr.strip())
            return []

        lines = stdout.strip().splitlines()
        if not lines:
            return []

        models = []
        for line in lines[1:]:
            parts = line.split()
            if not parts:
                continue
            models.append(
                {
                    "name": parts[0],
                    "id": parts[1] if len(parts) > 1 else "",
                    "size": parts[2] if len(parts) > 2 else "",
                }
            )
        return models
    except Exception as exc:  # noqa: BLE001
        logger.error("Error listing Ollama models: %s", exc)
        return []


def get_loaded_ollama_models():
    """Get list of models currently loaded in Ollama.

    Reuses logic from vram_manager.get_ollama_models().
    """
    try:
        success, stdout, stderr = run_command(["ollama", "ps"])
        if not success:
            if stderr:
                logger.error("Error getting loaded Ollama models: %s", stderr.strip())
            return []

        lines = stdout.strip().splitlines()
        if not lines:
            return []

        models = []
        for line in lines[1:]:
            parts = line.split()
            if not parts:
                continue
            models.append(
                {
                    "name": parts[0],
                    "id": parts[1] if len(parts) > 1 else "",
                    "size": parts[2] if len(parts) > 2 else "",
                    "processor": parts[3] if len(parts) > 3 else "",
                }
            )
        return models
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting loaded Ollama models: %s", exc)
        return []


def classify_ollama_error(stderr_text):
    """Classify Ollama stderr into a stable error code."""
    text = (stderr_text or "").lower()
    if "no such model" in text or "model not found" in text:
        return "MODEL_NOT_FOUND"
    if (
        "connection refused" in text
        or "failed to connect" in text
        or "connection error" in text
    ):
        return "OLLAMA_UNAVAILABLE"
    if (
        "command not found" in text
        or "is not recognized as an internal or external command" in text
    ):
        return "OLLAMA_CLI_NOT_FOUND"
    return "UNKNOWN_ERROR"


def stop_ollama_model(model_name):
    """Stop/unload an Ollama model from memory.

    Reuses logic from vram_manager.stop_ollama_model().
    Returns (success, message, error_code).
    """
    try:
        success, _stdout, stderr = run_command(["ollama", "stop", model_name])
        if not success:
            stderr_text = (stderr or "").strip()
            code = classify_ollama_error(stderr_text)
            message = stderr_text or "Failed to stop model."
            logger.error("Error stopping Ollama model '%s': %s", model_name, message)
            return False, message, code
        return True, "", None
    except Exception as exc:  # noqa: BLE001
        message = f"Error stopping Ollama model '{model_name}': {exc}"
        logger.error(message)
        return False, message, "UNKNOWN_ERROR"


def load_ollama_model(model_name):
    """Load an Ollama model into memory.

    Executes: `ollama run <model_name> --keepalive 0`.
    Returns (success, message, error_code).
    """
    command = ["ollama", "run", model_name, "--keepalive", "0"]
    try:
        success, _stdout, stderr = run_command(command)
        if not success:
            stderr_text = (stderr or "").strip()
            code = classify_ollama_error(stderr_text)
            message = stderr_text or "Failed to load model."
            logger.error("Error loading Ollama model '%s': %s", model_name, message)
            return False, message, code
        return True, "", None
    except Exception as exc:  # noqa: BLE001
        message = f"Error loading Ollama model '{model_name}': {exc}"
        logger.error(message)
        return False, message, "UNKNOWN_ERROR"


def pull_ollama_model(model_name):
    """Download an Ollama model and emit progress via WebSocket.

    Emits `model_download_progress` events with payload:
    { "model_name": "...", "progress": "...", "status": "downloading|complete|error" }.
    """
    command = ["ollama", "pull", model_name]

    socketio.emit(
        "model_download_progress",
        {
            "model_name": model_name,
            "progress": "starting",
            "status": "downloading",
        },
    )

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            socketio.emit(
                "model_download_progress",
                {
                    "model_name": model_name,
                    "progress": line,
                    "status": "downloading",
                },
                    )

        process.wait()
        if process.returncode == 0:
            socketio.emit(
                "model_download_progress",
                {
                    "model_name": model_name,
                    "progress": "complete",
                    "status": "complete",
                },
                    )
        else:
            socketio.emit(
                "model_download_progress",
                {
                    "model_name": model_name,
                    "progress": "error",
                    "status": "error",
                },
                    )
            logger.error(
                "Error pulling Ollama model '%s', return code %s",
                model_name,
                process.returncode,
            )
    except FileNotFoundError as exc:
        msg = f"Ollama command not found: {exc}"
        logger.error(msg)
        socketio.emit(
            "model_download_progress",
            {
                "model_name": model_name,
                "progress": msg,
                "status": "error",
            },
            )
    except Exception as exc:  # noqa: BLE001
        msg = f"Error pulling Ollama model '{model_name}': {exc}"
        logger.error(msg)
        socketio.emit(
            "model_download_progress",
            {
                "model_name": model_name,
                "progress": msg,
                "status": "error",
            },
            )


@app.route("/api/vram/status", methods=["GET"])
def api_vram_status():
    gpu = get_gpu_info()
    processes = get_gpu_processes()

    if gpu is None:
        return (
            jsonify(
                {
                    "error": "Unable to retrieve GPU information.",
                    "gpu": None,
                    "processes": processes,
                }
            ),
            500,
        )

    return jsonify(
        {
            "gpu": gpu,
            "processes": processes,
        }
    )


@app.route("/api/models/ollama/list", methods=["GET"])
def api_list_ollama_models():
    models = get_available_ollama_models()
    return jsonify(
        {
            "models": models,
            "count": len(models),
        }
    )


@app.route("/api/models/ollama/loaded", methods=["GET"])
def api_loaded_ollama_models():
    models = get_loaded_ollama_models()
    return jsonify(
        {
            "models": models,
            "count": len(models),
        }
    )


@app.route("/api/models/ollama/load", methods=["POST"])
def api_load_ollama_model():
    if not request.is_json:
        return jsonify({"success": False, "message": "Expected JSON body."}), 400

    data = request.get_json(silent=True) or {}
    model_name = data.get("model_name")
    if not model_name or not isinstance(model_name, str):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Field 'model_name' is required.",
                    "model_name": model_name,
                }
            ),
            400,
        )

    success, message, error_code = load_ollama_model(model_name)
    status_code = 200 if success else 500

    body = {
        "success": success,
        "message": message or "Model loaded successfully.",
        "model_name": model_name,
    }
    if not success:
        body["error"] = {
            "code": error_code or "UNKNOWN_ERROR",
            "details": message,
        }

    return jsonify(body), status_code


@app.route("/api/models/ollama/unload", methods=["POST"])
def api_unload_ollama_model():
    if not request.is_json:
        return jsonify({"success": False, "message": "Expected JSON body."}), 400

    data = request.get_json(silent=True) or {}
    model_name = data.get("model_name")
    if not model_name or not isinstance(model_name, str):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Field 'model_name' is required.",
                    "model_name": model_name,
                }
            ),
            400,
        )

    success, message, error_code = stop_ollama_model(model_name)
    status_code = 200 if success else 500

    body = {
        "success": success,
        "message": message or "Model unloaded successfully.",
        "model_name": model_name,
    }
    if not success:
        body["error"] = {
            "code": error_code or "UNKNOWN_ERROR",
            "details": message,
        }

    return jsonify(body), status_code


@app.route("/api/models/ollama/download", methods=["POST"])
def api_download_ollama_model():
    if not request.is_json:
        return jsonify({"success": False, "message": "Expected JSON body."}), 400

    data = request.get_json(silent=True) or {}
    model_name = data.get("model_name")
    if not model_name or not isinstance(model_name, str):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Field 'model_name' is required.",
                    "model_name": model_name,
                }
            ),
            400,
        )

    socketio.start_background_task(pull_ollama_model, model_name)

    return jsonify(
        {
            "success": True,
            "message": "Download started",
            "model_name": model_name,
        }
    )


# =============================================================================
# Service Management Endpoints
# =============================================================================


@app.route("/api/services", methods=["GET"])
def api_list_services():
    """Get list of all services with their current status."""
    statuses = service_manager.get_all_status()
    return jsonify(
        {
            "services": statuses,
            "count": len(statuses),
        }
    )


@app.route("/api/services/<service_id>", methods=["GET"])
def api_get_service(service_id):
    """Get status of a specific service."""
    status = service_manager.get_status(service_id)
    if "error" in status:
        return jsonify(status), 404
    return jsonify(status)


@app.route("/api/services/<service_id>/start", methods=["POST"])
def api_start_service(service_id):
    """Start a service."""
    result = service_manager.start_service(service_id)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/services/<service_id>/stop", methods=["POST"])
def api_stop_service(service_id):
    """Stop a service."""
    result = service_manager.stop_service(service_id)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/services/<service_id>/restart", methods=["POST"])
def api_restart_service(service_id):
    """Restart a service."""
    result = service_manager.restart_service(service_id)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/services/<service_id>/touch", methods=["POST"])
def api_touch_service(service_id):
    """Update last activity timestamp for a service."""
    if service_id not in SERVICES:
        return jsonify({"error": "Service not found"}), 404
    service_manager.touch_activity(service_id)
    return jsonify({"success": True, "message": "Activity updated"})


@app.route("/api/test/services/<service_id>/force-error", methods=["POST"])
def api_test_force_error(service_id):
    """Test-only endpoint to force a service into startup error mode."""
    if not os.environ.get("DASHBOARD_TEST_MODE"):
        return jsonify({"error": "Test mode not enabled"}), 403
    if service_id not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    service_manager.set_test_error_mode(service_id, True)
    return jsonify({"success": True, "message": "Test error mode enabled"})


@app.route("/api/test/services/<service_id>/clear-error", methods=["POST"])
def api_test_clear_error(service_id):
    """Test-only endpoint to clear forced error mode for a service."""
    if not os.environ.get("DASHBOARD_TEST_MODE"):
        return jsonify({"error": "Test mode not enabled"}), 403
    if service_id not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    service_manager.set_test_error_mode(service_id, False)
    return jsonify({"success": True, "message": "Test error mode disabled"})


# =============================================================================
# Resource Management Endpoints
# =============================================================================


@app.route("/api/resources/summary", methods=["GET"])
def api_resource_summary():
    """Get summary of resource usage across all services."""
    gpu = get_gpu_info()
    processes = get_gpu_processes()
    ollama_models = get_loaded_ollama_models()
    service_summary = service_manager.get_resource_summary()

    return jsonify({
        "gpu": gpu,
        "gpu_processes": processes,
        "ollama_models": ollama_models,
        "services": service_summary,
    })


@app.route("/api/resources/settings", methods=["GET"])
def api_resource_settings():
    """Get current resource management settings."""
    return jsonify({
        "auto_stop_enabled": service_manager.is_auto_stop_enabled(),
        "idle_timeout_seconds": service_manager.get_idle_timeout(),
        "idle_timeout_minutes": service_manager.get_idle_timeout() // 60,
    })


@app.route("/api/resources/settings", methods=["POST"])
def api_update_resource_settings():
    """Update resource management settings."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Expected JSON body."}), 400

    data = request.get_json(silent=True) or {}

    if "auto_stop_enabled" in data:
        service_manager.enable_auto_stop(bool(data["auto_stop_enabled"]))

    if "idle_timeout_minutes" in data:
        try:
            minutes = int(data["idle_timeout_minutes"])
            service_manager.set_idle_timeout(minutes * 60)
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "message": "idle_timeout_minutes must be an integer"
            }), 400

    return jsonify({
        "success": True,
        "auto_stop_enabled": service_manager.is_auto_stop_enabled(),
        "idle_timeout_seconds": service_manager.get_idle_timeout(),
        "idle_timeout_minutes": service_manager.get_idle_timeout() // 60,
    })


# =============================================================================
# Ingestion Management Endpoints
# =============================================================================


@app.route("/api/ingestion/status", methods=["GET"])
def api_ingestion_status():
    """Get current ingestion status and collection statistics."""
    status = ingestion_manager.get_status()
    return jsonify(status)


@app.route("/api/ingestion/start", methods=["POST"])
def api_ingestion_start():
    """Start ingestion in the background."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Expected JSON body."}), 400

    data = request.get_json(silent=True) or {}

    # Validate types
    types = data.get("types", [])
    if not types or not isinstance(types, list):
        return jsonify({
            "success": False,
            "message": "Field 'types' is required and must be a list.",
        }), 400

    valid_types = {"documentation", "code"}
    for t in types:
        if t not in valid_types:
            return jsonify({
                "success": False,
                "message": f"Invalid type '{t}'. Valid types: {valid_types}",
            }), 400

    reindex = bool(data.get("reindex", False))
    code_service = data.get("code_service", "core")

    result = ingestion_manager.start_ingestion(types, reindex, code_service)

    if not result.get("success"):
        return jsonify(result), 409  # Conflict - already running

    # Start the actual ingestion in background
    socketio.start_background_task(
        ingestion_manager.run_ingestion,
        types,
        reindex,
        code_service,
    )

    return jsonify(result)


@app.route("/api/ingestion/cancel", methods=["POST"])
def api_ingestion_cancel():
    """Cancel the current ingestion."""
    result = ingestion_manager.cancel_ingestion()
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


# =============================================================================
# Claude Code Execution Endpoints
# =============================================================================


@app.route("/api/claude/execute", methods=["POST"])
def api_claude_execute():
    """Execute Claude CLI in normal mode."""
    if not request.is_json:
        return jsonify({"success": False, "error": "Expected JSON body"}), 400

    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt")

    if not prompt or not isinstance(prompt, str):
        return jsonify({
            "success": False,
            "error": "Field 'prompt' is required and must be a string",
        }), 400

    result = claude_manager.execute_claude(prompt, "normal")

    if not result.get("success"):
        return jsonify(result), 400

    return jsonify(result)


@app.route("/api/claude/execute-yolo", methods=["POST"])
def api_claude_execute_yolo():
    """Execute Claude CLI in YOLO mode (skips permission prompts)."""
    if not request.is_json:
        return jsonify({"success": False, "error": "Expected JSON body"}), 400

    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt")

    if not prompt or not isinstance(prompt, str):
        return jsonify({
            "success": False,
            "error": "Field 'prompt' is required and must be a string",
        }), 400

    result = claude_manager.execute_claude(prompt, "yolo")

    if not result.get("success"):
        return jsonify(result), 400

    return jsonify(result)


@app.route("/api/claude/sessions", methods=["GET"])
def api_claude_sessions():
    """Get list of all Claude execution sessions."""
    sessions = claude_manager.get_sessions()
    return jsonify({
        "sessions": sessions,
        "count": len(sessions),
    })


@app.route("/api/claude/sessions/<session_id>", methods=["GET"])
def api_claude_session(session_id):
    """Get details for a specific Claude execution session."""
    include_output = request.args.get("include_output", "false").lower() == "true"
    result = claude_manager.get_session(session_id, include_output=include_output)

    if "error" in result:
        return jsonify(result), 404

    return jsonify(result)


@app.route("/api/claude/sessions/<session_id>/cancel", methods=["POST"])
def api_claude_cancel(session_id):
    """Cancel a running Claude execution session."""
    result = claude_manager.cancel_session(session_id)

    if not result.get("success"):
        if "not found" in result.get("error", "").lower():
            return jsonify(result), 404
        return jsonify(result), 400

    return jsonify(result)


def vram_background_thread():
    """Background thread that periodically emits VRAM status updates."""
    global vram_thread_stop, gpu_info_error

    logger.info("VRAM monitoring background thread started.")
    while not vram_thread_stop:
        gpu = get_gpu_info()
        processes = get_gpu_processes()

        if gpu is None:
            payload = {
                "gpu": None,
                "processes": processes,
                "timestamp": time.time(),
                "error": "Unable to retrieve GPU information",
            }
            if not gpu_info_error:
                logger.warning(
                    "Unable to retrieve GPU information; emitting error updates over WebSocket.",
                )
                gpu_info_error = True
            socketio.emit("vram_update", payload)
            socketio.sleep(5)
            continue

        if gpu_info_error:
            logger.info("GPU information retrieval recovered; resuming normal updates.")
            gpu_info_error = False

        payload = {
            "gpu": gpu,
            "processes": processes,
            "timestamp": time.time(),
        }
        socketio.emit("vram_update", payload)
        socketio.sleep(2)

    logger.info("VRAM monitoring background thread stopping.")


@socketio.on("connect")
def handle_connect():
    global vram_thread, connected_clients, vram_thread_stop
    with vram_thread_lock:
        connected_clients += 1
        logger.info("Client connected. Total clients: %s", connected_clients)
        if vram_thread is None or not vram_thread.is_alive():
            vram_thread_stop = False
            vram_thread = socketio.start_background_task(vram_background_thread)


@socketio.on("disconnect")
def handle_disconnect():
    global connected_clients, vram_thread_stop
    with vram_thread_lock:
        connected_clients = max(0, connected_clients - 1)
        logger.info("Client disconnected. Total clients: %s", connected_clients)
        if connected_clients == 0:
            vram_thread_stop = True


# =============================================================================
# Reverse Proxy for Services
# =============================================================================

# Map URL prefixes to service ports
SERVICE_PROXY_MAP = {
    "n8n": 5678,
    "comfyui": 8188,
    "openwebui": 3000,
    "alltalk": 7851,
    "wan2gp": 7860,
    "yue": 7870,
    "diffrhythm": 7871,
    "musicgen": 7872,
    "stable-audio": 7873,
    "ollama": 11434,
    "weaviate": 8080,
    "a1111": 7861,
    "forge": 7862,
    "fooocus": 7865,
}

EXCLUDED_HEADERS = [
    'content-encoding', 'content-length', 'transfer-encoding', 'connection',
    'host', 'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-host'
]


def check_proxy_auth():
    """
    Check if request is authorized to use the proxy.
    Returns (authorized: bool, error_response: tuple or None).
    """
    if not PROXY_AUTH_ENABLED:
        return True, None
    
    # Check for Authorization header with Bearer token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning("Proxy request rejected: Missing or invalid Authorization header")
        return False, (jsonify({"error": "Unauthorized: Missing or invalid token"}), 401)
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    if token != PROXY_AUTH_TOKEN:
        logger.warning("Proxy request rejected: Invalid token")
        return False, (jsonify({"error": "Forbidden: Invalid token"}), 403)
    
    return True, None


def proxy_request(target_url):
    """
    Proxy a request to the target URL and return the response.
    
    Security features:
    - Optional token-based authentication
    - Request size limiting
    - Configurable timeout
    """
    # Authentication check
    authorized, error_response = check_proxy_auth()
    if not authorized:
        return error_response
    
    # Check request size
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            size = int(content_length)
            if size > MAX_PROXY_REQUEST_SIZE:
                logger.warning(
                    f"Proxy request rejected: Body size {size} exceeds limit {MAX_PROXY_REQUEST_SIZE}"
                )
                return jsonify({
                    "error": f"Request body too large (max {MAX_PROXY_REQUEST_SIZE // (1024 * 1024)}MB)"
                }), 413
        except ValueError:
            logger.warning("Proxy request with invalid Content-Length header")
            return jsonify({"error": "Invalid Content-Length header"}), 400
    
    try:
        # Stream request body to avoid loading large payloads into memory
        if request.method in ["POST", "PUT", "PATCH"]:
            # Use request.stream for body streaming
            request_data = request.stream
        else:
            request_data = None
        
        # Forward the request with configurable timeout
        resp = http_requests.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers if k.lower() not in EXCLUDED_HEADERS},
            data=request_data,
            cookies=request.cookies,
            allow_redirects=False,
            stream=True,
            timeout=PROXY_TIMEOUT_SECONDS,
        )

        # Build response headers, excluding hop-by-hop headers
        headers = [(k, v) for k, v in resp.raw.headers.items()
                   if k.lower() not in EXCLUDED_HEADERS]

        return Response(
            resp.iter_content(chunk_size=8192),
            status=resp.status_code,
            headers=headers,
            content_type=resp.headers.get('content-type'),
        )
    except http_requests.exceptions.ConnectionError:
        logger.error(f"Proxy connection error to {target_url}")
        return jsonify({"error": "Service not available"}), 503
    except http_requests.exceptions.Timeout:
        logger.error(f"Proxy timeout to {target_url} (timeout={PROXY_TIMEOUT_SECONDS}s)")
        return jsonify({"error": "Service timeout"}), 504
    except Exception as e:
        logger.error(f"Proxy error to {target_url}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/proxy/<service_id>/", defaults={"path": ""})
@app.route("/proxy/<service_id>/<path:path>")
def proxy_service(service_id, path):
    """Reverse proxy requests to backend services."""
    if service_id not in SERVICE_PROXY_MAP:
        return jsonify({"error": f"Unknown service: {service_id}"}), 404

    port = SERVICE_PROXY_MAP[service_id]
    target_url = f"http://127.0.0.1:{port}/{path}"

    # Preserve query string
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"

    return proxy_request(target_url)


# =============================================================================
# Static File Serving (React Frontend)
# =============================================================================


@app.route("/")
def serve_index():
    """Serve the React app index.html."""
    return send_from_directory(FRONTEND_DIST, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    """Serve static files, fall back to index.html for SPA routing."""
    from werkzeug.security import safe_join
    
    # Don't catch API routes
    if path.startswith("api/") or path.startswith("socket.io/"):
        return jsonify({"error": "Not found"}), 404
    
    # Safely check if file exists (prevents path traversal)
    safe_path = safe_join(FRONTEND_DIST, path)
    if safe_path and os.path.isfile(safe_path):
        return send_from_directory(FRONTEND_DIST, path)
    
    # Otherwise, serve index.html for SPA routing
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    # Run on port 80 for single-port deployment
    # debug=False to avoid the reloader spawning multiple processes
    socketio.run(app, host="0.0.0.0", port=80, debug=False)
