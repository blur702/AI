import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv


load_dotenv()


class Settings:
    API_PORT: int = int(os.getenv("API_PORT", "1301"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./api_gateway.db")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    
    # VRAM Manager path - resolves relative paths to absolute
    @staticmethod
    def _resolve_vram_path() -> str:
        vram_path = os.getenv("VRAM_MANAGER_PATH", "./vram_manager.py")
        if not vram_path:
            vram_path = "./vram_manager.py"
        
        # Resolve relative paths relative to project root (parent of api_gateway)
        path = Path(vram_path)
        if not path.is_absolute():
            # Get project root (parent directory of api_gateway)
            project_root = Path(__file__).resolve().parent.parent
            path = (project_root / vram_path).resolve()
        
        return str(path)
    
    VRAM_MANAGER_PATH: str = _resolve_vram_path.__func__()

    # Weaviate Vector Database
    WEAVIATE_URL: str = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    WEAVIATE_GRPC_HOST: str = os.getenv("WEAVIATE_GRPC_HOST", "localhost")
    
    # Validate WEAVIATE_GRPC_PORT is a valid integer
    @staticmethod
    def _parse_grpc_port() -> int:
        port_str = os.getenv("WEAVIATE_GRPC_PORT", "50051")
        try:
            return int(port_str)
        except ValueError:
            import logging
            logging.warning(f"Invalid WEAVIATE_GRPC_PORT '{port_str}', using default 50051")
            return 50051
    
    WEAVIATE_GRPC_PORT: int = _parse_grpc_port.__func__()
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    # Ollama API endpoint for embeddings (from Weaviate's perspective)
    # Use host.docker.internal when Weaviate runs in Docker, localhost for native setup
    OLLAMA_API_ENDPOINT: str = os.getenv("OLLAMA_API_ENDPOINT", "http://127.0.0.1:11434")

    SERVICES: Dict[str, str] = {
        "comfyui": "http://localhost:8188",
        "alltalk": "http://localhost:7851",
        "ollama": "http://localhost:11434",
        "wan2gp": "http://localhost:7860",
        "yue": "http://localhost:7870",
        "diffrhythm": "http://localhost:7871",
        "stable_audio": "http://localhost:7873",
    }


settings = Settings()

