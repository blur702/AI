"""
Service Registry Configuration.

Defines all AI services with their startup commands, ports, and health check settings.
Used by the service manager for on-demand service starting.

Key Components:
    SERVICES: Main service registry dictionary mapping service IDs to configuration
    GPU_INTENSIVE_SERVICES: List of service IDs that use significant VRAM
    DEFAULT_HOST: Default host for health checks (127.0.0.1)

Service Configuration Schema:
    name: Display name for the service
    port: Port number the service binds to
    icon: Emoji icon for UI display
    description: Short description of service functionality
    working_dir: Working directory for process execution
    command: Command list to start the service (None for external services)
    health_endpoint: HTTP endpoint for health checks
    startup_timeout: Max seconds to wait for service to become healthy
    gradio: Whether service uses Gradio interface
    external: Whether service is managed externally (not started by dashboard)
    auto_start_with: List of services to auto-start when this service comes online

Environment Variables:
    AI_ROOT_DIR: Override default AI root directory path
"""

import os
from pathlib import Path
from typing import Any

# Get AI root directory from environment or use platform-aware default
# Default: ~/AI on Linux/macOS, D:\AI on Windows
if os.environ.get("AI_ROOT_DIR"):
    AI_ROOT_PATH = Path(os.environ["AI_ROOT_DIR"])
else:
    if os.name == "nt":  # Windows
        AI_ROOT_PATH = Path(r"D:\AI")
    else:  # Linux/macOS
        AI_ROOT_PATH = Path.home() / "AI"


# Helper function to build platform-agnostic paths
def _build_path(*parts: str) -> str:
    """Build absolute path from AI root.

    Args:
        *parts: Path components to join (e.g., 'ComfyUI', 'venv')

    Returns:
        Absolute path string
    """
    return str(AI_ROOT_PATH.joinpath(*parts))


def _build_python_path(venv_dir: str, script_name: str | None = None) -> list[str]:
    """Build path to Python executable in virtual environment.

    Always returns a list to allow easy concatenation with additional arguments.

    Args:
        venv_dir: Virtual environment directory (e.g., 'ComfyUI/venv')
        script_name: Optional script name to append (e.g., 'main.py')

    Returns:
        List with Python executable path, optionally followed by script name
    """
    if os.name == "nt":  # Windows
        python_exe = _build_path(venv_dir, "Scripts", "python.exe")
    else:  # Linux/macOS
        python_exe = _build_path(venv_dir, "bin", "python")

    if script_name:
        return [python_exe, script_name]
    return [python_exe]


SERVICES: dict[str, dict[str, Any]] = {
    "alltalk": {
        "name": "AllTalk TTS",
        "section": "Music",
        "port": 7851,
        "icon": "🗣️",
        "description": "Text-to-Speech synthesis",
        "working_dir": _build_path("alltalk_tts"),
        "command": _build_python_path("alltalk_tts/alltalk_environment/env", "script.py"),
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": False,
    },
    "comfyui": {
        "name": "ComfyUI",
        "section": "Image",
        "port": 8188,
        "icon": "🎨",
        "description": "Image generation workflows",
        "working_dir": _build_path("ComfyUI"),
        "command": _build_python_path("ComfyUI/venv") + ["main.py", "--listen", "0.0.0.0"],
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": False,
    },
    "wan2gp": {
        "name": "Wan2GP Video",
        "section": "Image",
        "port": 7860,
        "icon": "🎬",
        "description": "Video generation",
        "working_dir": _build_path("Wan2GP"),
        "command": _build_python_path("Wan2GP/wan2gp_env", "wgp.py") + ["--listen"],
        "health_endpoint": "/",
        "startup_timeout": 180,
        "gradio": True,
    },
    "yue": {
        "name": "YuE Music",
        "section": "Music",
        "port": 7870,
        "icon": "🎵",
        "description": "AI music generation",
        "working_dir": _build_path("YuE"),
        "command": _build_python_path("YuE/yue_env", "run_ui.py"),
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": True,
    },
    "diffrhythm": {
        "name": "DiffRhythm",
        "section": "Music",
        "port": 7871,
        "icon": "🥁",
        "description": "Rhythm-based music generation",
        "working_dir": _build_path("DiffRhythm"),
        "command": _build_python_path("DiffRhythm/diffrhythm_env", "run_ui.py"),
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": True,
    },
    "musicgen": {
        "name": "MusicGen",
        "section": "Music",
        "port": 7872,
        "icon": "🎹",
        "description": "Meta's music generation model",
        "working_dir": _build_path("audiocraft"),
        "command": _build_python_path("audiocraft/audiocraft_env")
        + ["demos/musicgen_app.py", "--listen", "0.0.0.0", "--server_port", "7872"],
        "health_endpoint": "/",
        "startup_timeout": 600,  # MusicGen loads large models - needs 10 minutes
        "gradio": True,
    },
    "stable_audio": {
        "name": "Stable Audio",
        "section": "Music",
        "port": 7873,
        "icon": "🔊",
        "description": "Stability AI audio generation",
        "working_dir": _build_path("stable-audio-tools"),
        "command": _build_python_path("stable-audio-tools/stable_audio_env", "run_ui.py"),
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": True,
    },
    "openwebui": {
        "name": "Open WebUI",
        "section": "Main",
        "port": 3000,
        "icon": "💬",
        "description": "LLM chat interface",
        "working_dir": _build_path("open-webui"),
        "command": None,  # Managed separately (Docker or standalone)
        "health_endpoint": "/",
        "startup_timeout": 60,
        "gradio": False,
        "external": True,  # Not managed by service manager
    },
    "n8n": {
        "name": "N8N",
        "section": "Main",
        "port": 5678,
        "icon": "🔄",
        "description": "Workflow automation",
        "working_dir": str(AI_ROOT_PATH),
        # Uses cmd.exe/sh to find n8n in PATH; requires: npm install n8n -g
        "command": [
            "cmd.exe" if os.name == "nt" else "sh",
            "/c" if os.name == "nt" else "-c",
            "n8n start",
        ],
        "health_endpoint": "/",
        "startup_timeout": 60,
        "gradio": False,
    },
    "ollama": {
        "name": "Ollama",
        "section": "Main",
        "port": 11434,
        "icon": "🦙",
        "description": "Local LLM API",
        "working_dir": None,
        "command": None,  # System service
        "health_endpoint": "/api/tags",
        "startup_timeout": 30,
        "gradio": False,
        "external": True,  # Managed as Windows service
        "auto_start_with": ["weaviate", "n8n"],  # Start these when Ollama comes online
    },
    "weaviate": {
        "name": "Weaviate Console",
        "section": "Main",
        "port": 8081,
        "icon": "🧠",
        "description": "Vector database explorer for RAG and memory",
        "working_dir": _build_path("api_gateway"),
        "command": ["docker-compose", "up", "-d"],
        "health_endpoint": "/",
        "startup_timeout": 60,
        "gradio": False,
        "external": False,  # Managed via docker-compose from dashboard
    },
    "a1111": {
        "name": "A1111 WebUI",
        "section": "Image",
        "port": 7861,
        "icon": "🖼️",
        "description": "AUTOMATIC1111 Stable Diffusion Web UI",
        "working_dir": _build_path("stability-matrix/Packages/Stable Diffusion WebUI"),
        "command": _build_python_path("stability-matrix/Packages/Stable Diffusion WebUI/venv")
        + ["launch.py", "--listen", "--port", "7861", "--api"],
        "health_endpoint": "/",
        "startup_timeout": 180,
        "gradio": True,
    },
    "forge": {
        "name": "SD Forge",
        "section": "Image",
        "port": 7862,
        "icon": "⚒️",
        "description": "Stable Diffusion WebUI Forge",
        "working_dir": _build_path("stability-matrix/Packages/stable-diffusion-webui-forge"),
        "command": _build_python_path("stability-matrix/Packages/stable-diffusion-webui-forge/venv")
        + ["launch.py", "--listen", "--port", "7862"],
        "health_endpoint": "/",
        "startup_timeout": 180,
        "gradio": True,
    },
    "fooocus": {
        "name": "Fooocus",
        "section": "Image",
        "port": 7865,
        "icon": "🎯",
        "description": "Simplified Stable Diffusion interface",
        "working_dir": _build_path("stability-matrix/Packages/Fooocus"),
        "command": _build_python_path("stability-matrix/Packages/Fooocus/venv")
        + ["launch.py", "--listen", "0.0.0.0", "--port", "7865"],
        "health_endpoint": "/",
        "startup_timeout": 180,
        "gradio": True,
    },
}

# Services that use significant GPU VRAM
GPU_INTENSIVE_SERVICES: list[str] = [
    "wan2gp",
    "yue",
    "diffrhythm",
    "musicgen",
    "stable_audio",
    "comfyui",
    "alltalk",
    "a1111",
    "forge",
    "fooocus",
]

# Default host for health checks
DEFAULT_HOST = "127.0.0.1"
