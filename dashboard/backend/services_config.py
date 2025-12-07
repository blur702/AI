"""
Service Registry Configuration

Defines all AI services with their startup commands, ports, and health check settings.
Used by the service manager for on-demand service starting.
"""

import os
from pathlib import Path

# Get AI root directory from environment or use platform-aware default
# Default: ~/AI on Linux/macOS, D:\AI on Windows
if os.environ.get('AI_ROOT_DIR'):
    AI_ROOT_PATH = Path(os.environ['AI_ROOT_DIR'])
else:
    if os.name == 'nt':  # Windows
        AI_ROOT_PATH = Path(r'D:\AI')
    else:  # Linux/macOS
        AI_ROOT_PATH = Path.home() / 'AI'

# Helper function to build platform-agnostic paths
def _build_path(*parts):
    """Build absolute path from AI root."""
    return str(AI_ROOT_PATH.joinpath(*parts))

def _build_python_path(venv_dir, script_name=None):
    """Build path to Python executable in virtual environment."""
    if os.name == 'nt':  # Windows
        python_exe = _build_path(venv_dir, 'Scripts', 'python.exe')
    else:  # Linux/macOS
        python_exe = _build_path(venv_dir, 'bin', 'python')
    
    if script_name:
        return [python_exe, script_name]
    return python_exe

SERVICES = {
    "alltalk": {
        "name": "AllTalk TTS",
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
        "port": 7872,
        "icon": "🎹",
        "description": "Meta's music generation model",
        "working_dir": _build_path("audiocraft"),
        "command": _build_python_path("audiocraft/audiocraft_env") + [
            "demos/musicgen_app.py",
            "--listen", "0.0.0.0",
            "--server_port", "7872"
        ],
        "health_endpoint": "/",
        "startup_timeout": 600,  # MusicGen loads large models - needs 10 minutes
        "gradio": True,
    },
    "stable_audio": {
        "name": "Stable Audio",
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
        "port": 5678,
        "icon": "🔄",
        "description": "Workflow automation",
        "working_dir": str(AI_ROOT_PATH),
        # Uses cmd.exe/sh to find n8n in PATH; requires: npm install n8n -g
        "command": ["cmd.exe" if os.name == 'nt' else "sh", "/c" if os.name == 'nt' else "-c", "n8n start"],
        "health_endpoint": "/",
        "startup_timeout": 60,
        "gradio": False,
    },
    "ollama": {
        "name": "Ollama",
        "port": 11434,
        "icon": "🦙",
        "description": "Local LLM API",
        "working_dir": None,
        "command": None,  # System service
        "health_endpoint": "/api/tags",
        "startup_timeout": 30,
        "gradio": False,
        "external": True,  # Managed as Windows service
    },
    "weaviate": {
        "name": "Weaviate",
        "port": 8080,
        "icon": "🧠",
        "description": "Vector database for RAG and memory",
        "working_dir": _build_path("api_gateway"),
        "command": ["docker-compose", "up", "-d"],
        "health_endpoint": "/v1/.well-known/ready",
        "startup_timeout": 60,
        "gradio": False,
        "external": True,  # Docker container
    },
}

# Services that use significant GPU VRAM
GPU_INTENSIVE_SERVICES = [
    "wan2gp",
    "yue",
    "diffrhythm",
    "musicgen",
    "stable_audio",
    "comfyui",
    "alltalk",
]

# Default host for health checks
DEFAULT_HOST = "127.0.0.1"  
