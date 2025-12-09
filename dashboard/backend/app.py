import logging
import os
import subprocess
import threading
import time
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from flask_socketio import SocketIO
import psutil
import requests as http_requests

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not required if using system environment variables
    pass

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

# Track app start time for uptime calculation
APP_START_TIME = time.time()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# HTTP Basic Authentication
# =============================================================================

# Load authentication credentials from environment variables
BASIC_AUTH_USERNAME = os.environ.get("DASHBOARD_AUTH_USERNAME", "").strip()
BASIC_AUTH_PASSWORD = os.environ.get("DASHBOARD_AUTH_PASSWORD", "").strip()

# Validate required authentication configuration at startup
if not BASIC_AUTH_USERNAME or not BASIC_AUTH_PASSWORD:
    logger.error(
        "FATAL: DASHBOARD_AUTH_USERNAME and DASHBOARD_AUTH_PASSWORD environment variables must be set. "
        "Authentication cannot be enabled with missing credentials. "
        "Please set these environment variables before starting the dashboard."
    )
    raise SystemExit(1)

logger.info(f"Dashboard authentication enabled for user: {BASIC_AUTH_USERNAME}")


def check_auth(username, password):
    """Check if the provided credentials are valid."""
    return username == BASIC_AUTH_USERNAME and password == BASIC_AUTH_PASSWORD


# Session management with secure random tokens
import secrets
from datetime import datetime, timedelta

# In-memory session storage (use Redis/database in production)
# Structure: {token: {"username": str, "created_at": datetime, "expires_at": datetime}}
_session_store = {}
_session_lock = threading.Lock()

# Session configuration
SESSION_EXPIRY_HOURS = int(os.environ.get("SESSION_EXPIRY_HOURS", "24"))


def _cleanup_expired_sessions():
    """Remove expired sessions from storage (called during validation)."""
    now = datetime.utcnow()
    expired_tokens = [
        token for token, data in _session_store.items()
        if data["expires_at"] <= now
    ]
    for token in expired_tokens:
        del _session_store[token]
    if expired_tokens:
        logger.debug("Cleaned up %d expired sessions", len(expired_tokens))


def generate_session_token(username, password):
    """Generate a secure session token after validating credentials.
    
    Returns token string if credentials valid, None otherwise.
    Creates a cryptographically secure random token and stores session metadata.
    """
    # Verify credentials first
    if not check_auth(username, password):
        return None
    
    # Generate secure random token
    token = secrets.token_urlsafe(32)  # 256 bits of entropy
    
    # Set expiration
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=SESSION_EXPIRY_HOURS)
    
    # Store session
    with _session_lock:
        _session_store[token] = {
            "username": username,
            "created_at": now,
            "expires_at": expires_at,
        }
    
    logger.info("Session created for user: %s (expires in %d hours)", username, SESSION_EXPIRY_HOURS)
    return token


def validate_session_token(token):
    """Validate a session token and return whether it's valid.
    
    Returns True if token is valid and not expired, False otherwise.
    Automatically cleans up expired sessions during validation.
    """
    if not token:
        return False
    
    with _session_lock:
        # Cleanup expired sessions
        _cleanup_expired_sessions()
        
        # Check if token exists
        session = _session_store.get(token)
        if not session:
            return False
        
        # Check expiration (redundant after cleanup, but explicit)
        if session["expires_at"] <= datetime.utcnow():
            del _session_store[token]
            return False
        
        return True


def revoke_session_token(token):
    """Revoke a session token, removing it from storage.
    
    Returns True if token was found and revoked, False otherwise.
    """
    if not token:
        return False
    
    with _session_lock:
        if token in _session_store:
            del _session_store[token]
            logger.info("Session revoked")
            return True
        return False


def authenticate():
    """Return a 401 JSON response that prompts for Basic Auth credentials."""
    response = jsonify({"error": "Authentication required"})
    response.status_code = 401
    response.headers["WWW-Authenticate"] = 'Basic realm="Dashboard"'
    return response


def require_auth(f):
    """Decorator that requires HTTP Basic Authentication for a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


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


# =============================================================================
# Model Capabilities Database
# =============================================================================

MODEL_CAPABILITIES = {
    "qwen": "Multilingual LLM with strong coding and reasoning. Supports 128K context.",
    "qwen2": "Qwen 2nd generation with improved multilingual and coding capabilities.",
    "qwen2.5": "Latest Qwen with enhanced instruction following and extended context.",
    "llama": "Meta's open-source foundation model. Excellent for chat and instruction following.",
    "llama2": "Meta's Llama 2 with improved safety and helpfulness.",
    "llama3": "Meta's Llama 3 with state-of-the-art performance across benchmarks.",
    "llama3.1": "Meta's Llama 3.1 with 128K context and improved capabilities.",
    "llama3.2": "Meta's Llama 3.2 with multimodal vision capabilities.",
    "mistral": "Efficient model with strong performance. Good for general tasks.",
    "mixtral": "Mixture of Experts model with 8x7B parameters. High quality, efficient inference.",
    "codellama": "Meta's code-specialized Llama. Optimized for code generation and completion.",
    "deepseek": "DeepSeek's foundation model with strong coding abilities.",
    "deepseek-coder": "DeepSeek model optimized specifically for code tasks.",
    "phi": "Microsoft's small but capable model. Efficient for constrained environments.",
    "phi3": "Microsoft's Phi-3 with improved reasoning in a small package.",
    "gemma": "Google's lightweight open model. Good balance of quality and efficiency.",
    "gemma2": "Google's Gemma 2 with improved performance and safety.",
    "starcoder": "BigCode's model trained on permissive code. Great for code completion.",
    "starcoder2": "Updated StarCoder with better performance on coding benchmarks.",
    "wizardcoder": "Code-focused model with strong instruction following.",
    "codestral": "Mistral AI's code-specialized model with excellent completion.",
    "command-r": "Cohere's Command model optimized for RAG and tool use.",
    "yi": "01.AI's bilingual model with strong Chinese and English support.",
    "solar": "Upstage's high-quality model with strong reasoning abilities.",
    "dolphin": "Fine-tuned uncensored model for unrestricted assistance.",
    "nous-hermes": "Nous Research model fine-tuned for helpful responses.",
    "openhermes": "Community model known for high quality general assistance.",
    "neural-chat": "Intel's optimized chat model for consumer hardware.",
    "orca-mini": "Microsoft research model with reasoning capabilities.",
    "vicuna": "LMSYS model fine-tuned on conversation data.",
    "zephyr": "HuggingFace model with strong chat capabilities.",
    "openchat": "Community-trained chat model with good performance.",
    "tinyllama": "Compact 1.1B model. Very fast, good for simple tasks.",
    "stable-lm": "Stability AI's language model for general use.",
    "falcon": "TII's efficient large language model.",
    "mpt": "MosaicML's pretrained transformer with strong performance.",
    "nomic-embed-text": "Text embedding model for semantic search.",
    "snowflake-arctic-embed": "Snowflake's embedding model with high accuracy.",
    "all-minilm": "Sentence transformer for fast embeddings.",
    "bge": "BAAI General Embedding model for semantic similarity.",
    "llava": "Large Language and Vision Assistant for image understanding.",
    "bakllava": "BakLLaVA multimodal model based on Mistral.",
}

# Cache for model info (TTL: 5 minutes)
_model_info_cache = {}
_model_info_cache_lock = threading.Lock()
MODEL_INFO_CACHE_TTL = 300  # 5 minutes


def estimate_model_vram(size_gb: float, quantization: str) -> int:
    """Estimate VRAM usage in MB based on model size and quantization.

    Uses heuristics:
    - Q4: ~60% of model size
    - Q5: ~70% of model size
    - Q6: ~80% of model size
    - Q8: ~90% of model size
    - FP16: ~100% of model size
    - FP32: ~200% of model size

    Add ~500MB overhead for context and KV cache.
    """
    quant_lower = quantization.lower()

    if "q4" in quant_lower or "q3" in quant_lower:
        factor = 0.6
    elif "q5" in quant_lower:
        factor = 0.7
    elif "q6" in quant_lower:
        factor = 0.8
    elif "q8" in quant_lower:
        factor = 0.9
    elif "fp16" in quant_lower or "f16" in quant_lower:
        factor = 1.0
    elif "fp32" in quant_lower or "f32" in quant_lower:
        factor = 2.0
    else:
        # Default to Q4 assumption for unknown quantization
        factor = 0.6

    vram_mb = int(size_gb * 1024 * factor) + 500  # Add 500MB overhead
    return vram_mb


def parse_model_size(size_str: str) -> float:
    """Parse model size string (e.g., '19GB', '4.7G') to float GB."""
    if not size_str:
        return 0.0

    size_str = size_str.strip().upper()

    try:
        if size_str.endswith("GB"):
            return float(size_str[:-2])
        elif size_str.endswith("G"):
            return float(size_str[:-1])
        elif size_str.endswith("MB"):
            return float(size_str[:-2]) / 1024
        elif size_str.endswith("M"):
            return float(size_str[:-1]) / 1024
        else:
            return float(size_str)
    except ValueError:
        return 0.0


def get_model_family(model_name: str) -> str:
    """Extract model family from model name."""
    # Remove tag (e.g., ':latest', ':32b-instruct-q4_K_M')
    base_name = model_name.split(":")[0].lower()

    # Common family patterns
    families = [
        "qwen2.5", "qwen2", "qwen",
        "llama3.2", "llama3.1", "llama3", "llama2", "llama",
        "mistral", "mixtral",
        "codellama", "deepseek-coder", "deepseek",
        "phi3", "phi",
        "gemma2", "gemma",
        "starcoder2", "starcoder",
        "wizardcoder", "codestral",
        "command-r",
        "yi", "solar",
        "dolphin", "nous-hermes", "openhermes",
        "neural-chat", "orca-mini",
        "vicuna", "zephyr", "openchat",
        "tinyllama", "stable-lm",
        "falcon", "mpt",
        "nomic-embed-text", "snowflake-arctic-embed",
        "all-minilm", "bge",
        "llava", "bakllava",
    ]

    for family in families:
        if family in base_name:
            return family

    # Return base name if no family matched
    return base_name.split("-")[0]


def _parse_ollama_verbose_output(stdout: str) -> dict:
    """Parse the structured output from `ollama show --verbose`.

    The verbose output has clearly defined sections:
    - Model: architecture, parameters, context length, embedding length, quantization
    - Capabilities: completion, tools, embedding, etc.
    - Parameters: top_k, top_p, temperature, etc.
    - Metadata: detailed key-value pairs

    Returns dict with extracted fields.
    """
    result = {
        "parameters": "",
        "quantization": "",
        "format": "",
        "architecture": "",
        "context_length": 0,
    }

    current_section = None
    lines = stdout.strip().splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect section headers (lines without leading whitespace that end with known section names)
        if not line.startswith(" ") and not line.startswith("\t"):
            section_lower = stripped.lower()
            if section_lower in ("model", "capabilities", "parameters", "metadata", "tensors", "license"):
                current_section = section_lower
                continue

        # Parse key-value pairs within sections
        # Format: "    key    value" (indented, with spaces/tabs between key and value)
        if current_section and (line.startswith(" ") or line.startswith("\t")):
            # Split on multiple spaces or tabs
            parts = stripped.split()
            if len(parts) >= 2:
                key = parts[0].lower()
                value = " ".join(parts[1:])

                if current_section == "model":
                    if key == "parameters":
                        result["parameters"] = value
                    elif key == "quantization":
                        result["quantization"] = value
                    elif key == "architecture":
                        result["architecture"] = value
                    elif key == "context" and len(parts) >= 3:
                        # "context length    40960"
                        try:
                            result["context_length"] = int(parts[2])
                        except (ValueError, IndexError):
                            pass

    return result


def get_ollama_model_info(model_name: str) -> dict:
    """Get detailed model information via `ollama show --verbose`.

    Uses the structured verbose output format which provides consistent
    key-value pairs organized by section (Model, Capabilities, Parameters, etc.).

    Returns dict with: name, family, parameters, quantization, size_gb,
    format, template, estimated_vram_mb, capability_description.

    Logs warnings when expected keys are missing to help detect
    regressions in future Ollama versions.
    """
    # Check cache
    cache_key = model_name
    with _model_info_cache_lock:
        if cache_key in _model_info_cache:
            cached, timestamp = _model_info_cache[cache_key]
            if time.time() - timestamp < MODEL_INFO_CACHE_TTL:
                return cached

    info = {
        "name": model_name,
        "family": get_model_family(model_name),
        "parameters": "",
        "quantization": "",
        "size_gb": 0.0,
        "format": "",
        "template": "",
        "estimated_vram_mb": 0,
        "capability_description": "",
    }

    try:
        # Use --verbose flag for structured output
        success, stdout, stderr = run_command(["ollama", "show", model_name, "--verbose"])
        if not success:
            logger.warning("Failed to get model info for %s: %s", model_name, stderr)
            # Still return basic info
            info["capability_description"] = MODEL_CAPABILITIES.get(info["family"], "")
            return info

        # Parse the structured verbose output
        parsed = _parse_ollama_verbose_output(stdout)

        # Apply parsed values
        if parsed.get("parameters"):
            info["parameters"] = parsed["parameters"]
        else:
            logger.debug("Model %s: 'parameters' not found in ollama show output", model_name)

        if parsed.get("quantization"):
            info["quantization"] = parsed["quantization"]
        else:
            logger.debug("Model %s: 'quantization' not found in ollama show output", model_name)

        if parsed.get("architecture"):
            info["format"] = parsed["architecture"]

        # Get size from ollama list
        models = get_available_ollama_models()
        for m in models:
            if m["name"] == model_name:
                info["size_gb"] = parse_model_size(m.get("size", ""))
                break

        # Estimate VRAM
        if info["size_gb"] > 0:
            info["estimated_vram_mb"] = estimate_model_vram(
                info["size_gb"],
                info["quantization"] or "q4"
            )

        # Get capability description
        info["capability_description"] = MODEL_CAPABILITIES.get(info["family"], "")

        # Cache result
        with _model_info_cache_lock:
            _model_info_cache[cache_key] = (info, time.time())

        return info

    except Exception as exc:
        logger.error("Error getting model info for %s: %s", model_name, exc)
        info["capability_description"] = MODEL_CAPABILITIES.get(info["family"], "")
        return info


def remove_ollama_model(model_name: str) -> tuple:
    """Remove an Ollama model from disk.

    Returns (success, message, error_code).
    """
    try:
        success, _stdout, stderr = run_command(["ollama", "rm", model_name])
        if not success:
            stderr_text = (stderr or "").strip()
            code = classify_ollama_error(stderr_text)
            message = stderr_text or "Failed to remove model."
            logger.error("Error removing Ollama model '%s': %s", model_name, message)
            return False, message, code

        # Invalidate cache
        with _model_info_cache_lock:
            if model_name in _model_info_cache:
                del _model_info_cache[model_name]

        return True, "", None
    except Exception as exc:
        message = f"Error removing Ollama model '{model_name}': {exc}"
        logger.error(message)
        return False, message, "UNKNOWN_ERROR"


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


# =============================================================================
# Authentication Check Endpoint
# =============================================================================


@app.route("/api/auth/check", methods=["GET"])
def api_auth_check():
    """Verify authentication status."""
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()
    return jsonify({"authenticated": True, "username": BASIC_AUTH_USERNAME})


@app.route("/api/auth/token", methods=["GET"])
def api_auth_token():
    """Generate a session token for Socket.IO authentication."""
    auth = request.authorization
    if not auth:
        return authenticate()
    
    token = generate_session_token(auth.username, auth.password)
    if not token:
        return authenticate()
    
    return jsonify({"token": token, "username": auth.username})


@app.route("/api/auth/revoke", methods=["POST"])
def api_auth_revoke():
    """Revoke the current session token."""
    # Extract token from Authorization header (if sent as Bearer token)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if revoke_session_token(token):
            return jsonify({"success": True, "message": "Session revoked"})

    return jsonify({"success": False, "message": "No valid session to revoke"}), 400


@app.route("/api/health", methods=["GET"])
@require_auth
def api_health():
    """Get dashboard health status including uptime, CPU, memory, and services."""
    # Calculate uptime
    uptime_seconds = time.time() - APP_START_TIME

    # Get CPU usage
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # Get memory info
    memory = psutil.virtual_memory()

    # Get services count
    statuses = service_manager.get_all_status()
    running_count = len([s for s in statuses.values() if s.get('status') == 'running'])

    # Determine status based on thresholds
    if cpu_percent < 80 and memory.percent < 85:
        status = 'healthy'
    elif cpu_percent < 90 or memory.percent < 90:
        status = 'warning'
    else:
        status = 'error'

    return jsonify({
        "status": status,
        "uptime_seconds": uptime_seconds,
        "cpu": {
            "percent": cpu_percent,
            "count": psutil.cpu_count()
        },
        "memory": {
            "percent": memory.percent,
            "used_mb": memory.used // (1024 * 1024),
            "total_mb": memory.total // (1024 * 1024)
        },
        "services": {
            "total": len(statuses),
            "running": running_count
        }
    })


@app.route("/api/vram/status", methods=["GET"])
@require_auth
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
@require_auth
def api_list_ollama_models():
    """Get list of all available Ollama models.

    Query Parameters:
        detailed (bool): If true, returns detailed model information including
            parameters, quantization, VRAM estimates, and capability descriptions.
            Default is false for backward compatibility.
        limit (int): When detailed=true, limits the number of models to fetch
            full details for. Remaining models return basic info only.

    Returns:
        Basic response (detailed=false):
            {"models": [...], "count": N}

        Detailed response (detailed=true):
            {"models": [...], "count": N, "loaded_count": N}
    """
    detailed = request.args.get("detailed", "").lower() in ("true", "1", "yes")

    if detailed:
        # Return detailed response matching /api/models/ollama/detailed
        limit = request.args.get("limit", type=int)
        models = get_available_ollama_models()
        loaded = get_loaded_ollama_models()
        loaded_names = {m["name"] for m in loaded}

        detailed_models = []
        for i, model in enumerate(models):
            if limit and i >= limit:
                # For remaining models, just return basic info
                detailed_models.append({
                    **model,
                    "family": get_model_family(model["name"]),
                    "is_loaded": model["name"] in loaded_names,
                    "detailed": False,
                })
                continue

            info = get_ollama_model_info(model["name"])
            detailed_models.append({
                **model,
                **info,
                "is_loaded": model["name"] in loaded_names,
                "detailed": True,
            })

        return jsonify({
            "models": detailed_models,
            "count": len(detailed_models),
            "loaded_count": len(loaded_names),
        })

    # Default: return basic model list
    models = get_available_ollama_models()
    return jsonify(
        {
            "models": models,
            "count": len(models),
        }
    )


@app.route("/api/models/ollama/loaded", methods=["GET"])
@require_auth
def api_loaded_ollama_models():
    models = get_loaded_ollama_models()
    return jsonify(
        {
            "models": models,
            "count": len(models),
        }
    )


@app.route("/api/models/ollama/load", methods=["POST"])
@require_auth
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
@require_auth
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
@require_auth
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


@app.route("/api/models/ollama/info/<path:model_name>", methods=["GET"])
@require_auth
def api_ollama_model_info(model_name):
    """Get detailed information about a specific Ollama model."""
    info = get_ollama_model_info(model_name)
    return jsonify(info)


@app.route("/api/models/ollama/detailed", methods=["GET"])
@require_auth
def api_ollama_models_detailed():
    """Get list of all Ollama models with detailed information.

    This endpoint fetches detailed info for each model which may be slower.
    Consider using ?limit=N to limit the number of models to fetch details for.
    """
    limit = request.args.get("limit", type=int)
    models = get_available_ollama_models()
    loaded = get_loaded_ollama_models()
    loaded_names = {m["name"] for m in loaded}

    detailed_models = []
    for i, model in enumerate(models):
        if limit and i >= limit:
            # For remaining models, just return basic info
            detailed_models.append({
                **model,
                "family": get_model_family(model["name"]),
                "is_loaded": model["name"] in loaded_names,
                "detailed": False,
            })
            continue

        info = get_ollama_model_info(model["name"])
        detailed_models.append({
            **model,
            **info,
            "is_loaded": model["name"] in loaded_names,
            "detailed": True,
        })

    return jsonify({
        "models": detailed_models,
        "count": len(detailed_models),
        "loaded_count": len(loaded_names),
    })


@app.route("/api/models/ollama/remove", methods=["POST"])
@require_auth
def api_remove_ollama_model():
    """Remove an Ollama model from disk.

    Requires confirmation: {"model_name": "...", "confirm": true}
    """
    if not request.is_json:
        return jsonify({"success": False, "message": "Expected JSON body."}), 400

    data = request.get_json(silent=True) or {}
    model_name = data.get("model_name")
    confirm = data.get("confirm", False)

    if not model_name or not isinstance(model_name, str):
        return jsonify({
            "success": False,
            "message": "Field 'model_name' is required.",
        }), 400

    if not confirm:
        return jsonify({
            "success": False,
            "message": "Field 'confirm' must be true to remove model.",
        }), 400

    success, message, error_code = remove_ollama_model(model_name)
    status_code = 200 if success else 500

    body = {
        "success": success,
        "message": message or "Model removed successfully.",
        "model_name": model_name,
    }
    if not success:
        body["error"] = {
            "code": error_code or "UNKNOWN_ERROR",
            "details": message,
        }

    return jsonify(body), status_code


@app.route("/api/models/ollama/<path:model_name>/services", methods=["GET"])
@require_auth
def api_model_services(model_name):
    """Get list of LLM-capable services that could potentially use the specified model.

    NOTE: This endpoint returns services that are LLM-capable and currently running,
    NOT services that are definitively using the specified model. True model-level
    attribution is not yet available. The frontend should treat this as
    "Services that can use this model" rather than "Services actively using this model".

    When model-level attribution becomes available, this endpoint will be extended
    to filter by actual model usage while maintaining backward compatibility.

    Args:
        model_name: The Ollama model name (included in response for reference)

    Returns:
        {
            "model_name": "...",
            "services": [
                {
                    "id": "...",
                    "name": "...",
                    "status": "running",
                    "usage": "potential"  # Indicates this is a potential association
                }
            ],
            "count": N,
            "note": "Services shown are LLM-capable and running, not necessarily using this specific model."
        }
    """
    # Services that can use Ollama models
    llm_services = ["openwebui", "ollama"]

    # Get running services
    statuses = service_manager.get_all_status()
    running_services = []

    for service_id, status in statuses.items():
        if service_id in llm_services and status.get("status") == "running":
            running_services.append({
                "id": service_id,
                "name": status.get("name", service_id),
                "status": status.get("status"),
                "usage": "potential",  # Indicates coarse association, not active binding
            })

    return jsonify({
        "model_name": model_name,
        "services": running_services,
        "count": len(running_services),
        "note": "Services shown are LLM-capable and running, not necessarily using this specific model.",
    })


# =============================================================================
# Service Management Endpoints
# =============================================================================


@app.route("/api/services", methods=["GET"])
@require_auth
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
@require_auth
def api_get_service(service_id):
    """Get status of a specific service."""
    status = service_manager.get_status(service_id)
    if "error" in status:
        return jsonify(status), 404
    return jsonify(status)


@app.route("/api/services/<service_id>/start", methods=["POST"])
@require_auth
def api_start_service(service_id):
    """Start a service."""
    result = service_manager.start_service(service_id)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/services/<service_id>/stop", methods=["POST"])
@require_auth
def api_stop_service(service_id):
    """Stop a service."""
    result = service_manager.stop_service(service_id)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/services/<service_id>/restart", methods=["POST"])
@require_auth
def api_restart_service(service_id):
    """Restart a service."""
    result = service_manager.restart_service(service_id)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/services/<service_id>/pause", methods=["POST"])
@require_auth
def api_pause_service(service_id):
    """Pause a running service."""
    result = service_manager.pause_service(service_id)
    status_code = 200 if result.get("success") else 400
    if result.get("success"):
        socketio.emit("service_paused", {
            "service_id": service_id,
            "status": "paused",
            "message": result.get("message", "Service paused"),
        })
    return jsonify(result), status_code


@app.route("/api/services/<service_id>/resume", methods=["POST"])
@require_auth
def api_resume_service(service_id):
    """Resume a paused service."""
    result = service_manager.resume_service(service_id)
    status_code = 200 if result.get("success") else 400
    if result.get("success"):
        socketio.emit("service_resumed", {
            "service_id": service_id,
            "status": "running",
            "message": result.get("message", "Service resumed"),
        })
    return jsonify(result), status_code


@app.route("/api/services/<service_id>/touch", methods=["POST"])
@require_auth
def api_touch_service(service_id):
    """Update last activity timestamp for a service."""
    if service_id not in SERVICES:
        return jsonify({"error": "Service not found"}), 404
    service_manager.touch_activity(service_id)
    return jsonify({"success": True, "message": "Activity updated"})


@app.route("/api/test/services/<service_id>/force-error", methods=["POST"])
@require_auth
def api_test_force_error(service_id):
    """Test-only endpoint to force a service into startup error mode."""
    if not os.environ.get("DASHBOARD_TEST_MODE"):
        return jsonify({"error": "Test mode not enabled"}), 403
    if service_id not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    service_manager.set_test_error_mode(service_id, True)
    return jsonify({"success": True, "message": "Test error mode enabled"})


@app.route("/api/test/services/<service_id>/clear-error", methods=["POST"])
@require_auth
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
@require_auth
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
@require_auth
def api_resource_settings():
    """Get current resource management settings."""
    return jsonify({
        "auto_stop_enabled": service_manager.is_auto_stop_enabled(),
        "idle_timeout_seconds": service_manager.get_idle_timeout(),
        "idle_timeout_minutes": service_manager.get_idle_timeout() // 60,
    })


@app.route("/api/resources/settings", methods=["POST"])
@require_auth
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
@require_auth
def api_ingestion_status():
    """Get current ingestion status and collection statistics."""
    status = ingestion_manager.get_status()
    return jsonify(status)


@app.route("/api/ingestion/start", methods=["POST"])
@require_auth
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

    valid_types = {"documentation", "code", "drupal", "mdn_javascript", "mdn_webapis"}
    for t in types:
        if t not in valid_types:
            return jsonify({
                "success": False,
                "message": f"Invalid type '{t}'. Valid types: {valid_types}",
            }), 400

    reindex = bool(data.get("reindex", False))
    code_service = data.get("code_service", "core")
    drupal_limit = data.get("drupal_limit")  # Optional: max entities for Drupal
    mdn_limit = data.get("mdn_limit")  # Optional: max documents for MDN
    mdn_section = data.get("mdn_section")  # Optional: section filter for mdn_webapis

    result = ingestion_manager.start_ingestion(
        types, reindex, code_service, drupal_limit, mdn_limit, mdn_section
    )

    if not result.get("success"):
        return jsonify(result), 409  # Conflict - already running

    # Start the actual ingestion in background
    socketio.start_background_task(
        ingestion_manager.run_ingestion,
        types,
        reindex,
        code_service,
        drupal_limit,
        mdn_limit,
        mdn_section,
    )

    return jsonify(result)


@app.route("/api/ingestion/cancel", methods=["POST"])
@require_auth
def api_ingestion_cancel():
    """Cancel the current ingestion."""
    result = ingestion_manager.cancel_ingestion()
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/ingestion/pause", methods=["POST"])
@require_auth
def api_ingestion_pause():
    """Pause the current ingestion."""
    result = ingestion_manager.pause_ingestion()
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/ingestion/resume", methods=["POST"])
@require_auth
def api_ingestion_resume():
    """Resume a paused ingestion."""
    result = ingestion_manager.resume_ingestion()
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/api/ingestion/clean", methods=["POST"])
@require_auth
def api_ingestion_clean():
    """Delete specified Weaviate collections."""
    import sys
    from pathlib import Path

    # Add project root to path for imports
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from api_gateway.services.weaviate_connection import (
        WeaviateConnection,
        DOCUMENTATION_COLLECTION_NAME,
        CODE_ENTITY_COLLECTION_NAME,
        DRUPAL_API_COLLECTION_NAME,
        MDN_JAVASCRIPT_COLLECTION_NAME,
        MDN_WEBAPIS_COLLECTION_NAME,
    )

    if not request.is_json:
        return jsonify({"success": False, "message": "Expected JSON body."}), 400

    data = request.get_json(silent=True) or {}
    collections = data.get("collections", [])

    if not collections or not isinstance(collections, list):
        return jsonify({
            "success": False,
            "message": "Field 'collections' is required and must be a list.",
        }), 400

    # Map collection names to Weaviate collection names
    collection_map = {
        "documentation": DOCUMENTATION_COLLECTION_NAME,
        "code_entity": CODE_ENTITY_COLLECTION_NAME,
        "drupal_api": DRUPAL_API_COLLECTION_NAME,
        "mdn_javascript": MDN_JAVASCRIPT_COLLECTION_NAME,
        "mdn_webapis": MDN_WEBAPIS_COLLECTION_NAME,
    }

    deleted = []
    errors = []

    try:
        with WeaviateConnection() as client:
            for collection_name in collections:
                if collection_name not in collection_map:
                    errors.append(f"Unknown collection: {collection_name}")
                    continue

                weaviate_name = collection_map[collection_name]
                try:
                    if client.collections.exists(weaviate_name):
                        client.collections.delete(weaviate_name)
                        deleted.append(collection_name)
                        logger.info(f"Deleted collection: {weaviate_name}")
                    else:
                        deleted.append(collection_name)  # Already doesn't exist
                except Exception as e:
                    errors.append(f"Error deleting {collection_name}: {str(e)}")
                    logger.error(f"Error deleting collection {weaviate_name}: {e}")

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to connect to Weaviate: {str(e)}",
        }), 500

    return jsonify({
        "success": len(errors) == 0,
        "deleted": deleted,
        "errors": errors if errors else None,
    })


@app.route("/api/ingestion/reindex", methods=["POST"])
@require_auth
def api_ingestion_reindex():
    """Start ingestion with forced reindex (delete and recreate collections)."""
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

    valid_types = {"documentation", "code", "drupal", "mdn_javascript", "mdn_webapis"}
    for t in types:
        if t not in valid_types:
            return jsonify({
                "success": False,
                "message": f"Invalid type '{t}'. Valid types: {valid_types}",
            }), 400

    # Force reindex=True
    code_service = data.get("code_service", "core")
    drupal_limit = data.get("drupal_limit")
    mdn_limit = data.get("mdn_limit")
    mdn_section = data.get("mdn_section")

    result = ingestion_manager.start_ingestion(
        types, reindex=True, code_service=code_service,
        drupal_limit=drupal_limit, mdn_limit=mdn_limit, mdn_section=mdn_section
    )

    if not result.get("success"):
        return jsonify(result), 409  # Conflict - already running

    # Start the actual ingestion in background
    socketio.start_background_task(
        ingestion_manager.run_ingestion,
        types,
        True,  # reindex=True
        code_service,
        drupal_limit,
        mdn_limit,
        mdn_section,
    )

    return jsonify(result)


# =============================================================================
# Claude Code Execution Endpoints
# =============================================================================


@app.route("/api/claude/execute", methods=["POST"])
@require_auth
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
@require_auth
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
@require_auth
def api_claude_sessions():
    """Get list of all Claude execution sessions."""
    sessions = claude_manager.get_sessions()
    return jsonify({
        "sessions": sessions,
        "count": len(sessions),
    })


@app.route("/api/claude/sessions/<session_id>", methods=["GET"])
@require_auth
def api_claude_session(session_id):
    """Get details for a specific Claude execution session."""
    include_output = request.args.get("include_output", "false").lower() == "true"
    result = claude_manager.get_session(session_id, include_output=include_output)

    if "error" in result:
        return jsonify(result), 404

    return jsonify(result)


@app.route("/api/claude/sessions/<session_id>/cancel", methods=["POST"])
@require_auth
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
def handle_connect(auth):
    global vram_thread, connected_clients, vram_thread_stop

    # Check authentication for WebSocket connections using Socket.IO auth payload
    # Clients must send a session token in the auth payload: { auth: { token: "..." } }
    token = None
    if auth and isinstance(auth, dict):
        token = auth.get('token')
    
    if not validate_session_token(token):
        logger.warning("WebSocket connection rejected: Invalid or missing auth token")
        return False  # Reject the connection
    
    logger.info("WebSocket connection accepted: Valid auth token")

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
    "weaviate-console": 8081,
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
@require_auth
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
@require_auth
def serve_index():
    """Serve the React app index.html."""
    return send_from_directory(FRONTEND_DIST, "index.html")


@app.route("/<path:path>")
@require_auth
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
    # Bind to 127.0.0.1 since nginx handles external traffic (HTTPS on 443)
    # debug=False to avoid the reloader spawning multiple processes
    socketio.run(app, host="127.0.0.1", port=80, debug=False)
