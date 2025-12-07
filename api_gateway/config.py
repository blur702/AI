import os
from typing import Dict, List

from dotenv import load_dotenv


load_dotenv()


class Settings:
    API_PORT: int = int(os.getenv("API_PORT", "1301"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./api_gateway.db")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    VRAM_MANAGER_PATH: str = os.getenv("VRAM_MANAGER_PATH", "D:/AI/vram_manager.py")

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

