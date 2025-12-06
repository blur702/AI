"""
Service Registry Configuration

Defines all AI services with their startup commands, ports, and health check settings.
Used by the service manager for on-demand service starting.
"""

SERVICES = {
    "alltalk": {
        "name": "AllTalk TTS",
        "port": 7851,
        "icon": "🗣️",
        "description": "Text-to-Speech synthesis",
        "working_dir": "D:\\AI\\alltalk_tts",
        "command": [
            "D:\\AI\\alltalk_tts\\alltalk_environment\\env\\python.exe",
            "script.py"
        ],
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": False,
    },
    "comfyui": {
        "name": "ComfyUI",
        "port": 8188,
        "icon": "🎨",
        "description": "Image generation workflows",
        "working_dir": "D:\\AI\\ComfyUI",
        "command": [
            "D:\\AI\\ComfyUI\\venv\\Scripts\\python.exe",
            "main.py",
            "--listen", "0.0.0.0"
        ],
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": False,
    },
    "wan2gp": {
        "name": "Wan2GP Video",
        "port": 7860,
        "icon": "🎬",
        "description": "Video generation",
        "working_dir": "D:\\AI\\Wan2GP",
        "command": [
            "D:\\AI\\Wan2GP\\wan2gp_env\\python.exe",
            "wgp.py",
            "--listen"
        ],
        "health_endpoint": "/",
        "startup_timeout": 180,
        "gradio": True,
    },
    "yue": {
        "name": "YuE Music",
        "port": 7870,
        "icon": "🎵",
        "description": "AI music generation",
        "working_dir": "D:\\AI\\YuE",
        "command": [
            "D:\\AI\\YuE\\yue_env\\Scripts\\python.exe",
            "run_ui.py"
        ],
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": True,
    },
    "diffrhythm": {
        "name": "DiffRhythm",
        "port": 7871,
        "icon": "🥁",
        "description": "Rhythm-based music generation",
        "working_dir": "D:\\AI\\DiffRhythm",
        "command": [
            "D:\\AI\\DiffRhythm\\diffrhythm_env\\Scripts\\python.exe",
            "run_ui.py"
        ],
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": True,
    },
    "musicgen": {
        "name": "MusicGen",
        "port": 7872,
        "icon": "🎹",
        "description": "Meta's music generation model",
        "working_dir": "D:\\AI\\audiocraft",
        "command": [
            "D:\\AI\\audiocraft\\audiocraft_env\\Scripts\\python.exe",
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
        "working_dir": "D:\\AI\\stable-audio-tools",
        "command": [
            "D:\\AI\\stable-audio-tools\\stable_audio_env\\Scripts\\python.exe",
            "run_ui.py"
        ],
        "health_endpoint": "/",
        "startup_timeout": 120,
        "gradio": True,
    },
    "openwebui": {
        "name": "Open WebUI",
        "port": 3000,
        "icon": "💬",
        "description": "LLM chat interface",
        "working_dir": "D:\\AI\\open-webui",
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
        "working_dir": "D:\\AI",
        # Uses cmd.exe to find n8n in PATH; requires: npm install n8n -g
        "command": ["cmd.exe", "/c", "n8n", "start"],
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
