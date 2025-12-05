import logging
import subprocess
import threading
import time

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Explicit async_mode for compatibility on Windows; threading works well here.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


vram_thread = None
vram_thread_lock = threading.Lock()
connected_clients = 0
vram_thread_stop = False
gpu_info_error = False


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
        broadcast=True,
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
                broadcast=True,
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
                broadcast=True,
            )
        else:
            socketio.emit(
                "model_download_progress",
                {
                    "model_name": model_name,
                    "progress": "error",
                    "status": "error",
                },
                broadcast=True,
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
            broadcast=True,
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
            broadcast=True,
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
            socketio.emit("vram_update", payload, broadcast=True)
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
        socketio.emit("vram_update", payload, broadcast=True)
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


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
