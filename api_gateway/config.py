"""
API Gateway Configuration Module.

Centralized configuration management using environment variables with sensible
defaults. Loads configuration from .env file and provides a Settings class
with all configurable options.

Configuration Categories:
    - API Server: Port, CORS origins, log level
    - PostgreSQL: Database connection settings
    - Weaviate: Vector database connection
    - Ollama: LLM and embedding model settings
    - Service Endpoints: AI service URLs

Environment Variables:
    API_PORT: API gateway port (default: 1301)
    DATABASE_URL: Full PostgreSQL URL (overrides component settings)
    POSTGRES_HOST/PORT/USER/PASSWORD/DB: PostgreSQL components
    WEAVIATE_URL: Weaviate HTTP endpoint
    WEAVIATE_GRPC_PORT: Weaviate gRPC port
    OLLAMA_API_ENDPOINT: Ollama API base URL
    OLLAMA_EMBEDDING_MODEL: Model for embeddings

Usage:
    from api_gateway.config import settings
    print(settings.API_PORT)
    print(settings.WEAVIATE_URL)
"""
import os
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote_plus

from dotenv import load_dotenv


# Load .env with override to ensure file values take precedence
load_dotenv(override=True)


class Settings:
    API_PORT: int = int(os.getenv("API_PORT", "1301"))

    # PostgreSQL configuration
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "ai_gateway")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "ai_gateway")

    # Build DATABASE_URL from components if not explicitly set
    @staticmethod
    def _build_database_url() -> str:
        explicit_url = os.getenv("DATABASE_URL")
        if explicit_url:
            return explicit_url

        # Build PostgreSQL URL from components
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "ai_gateway")
        password = os.getenv("POSTGRES_PASSWORD", "")
        db = os.getenv("POSTGRES_DB", "ai_gateway")

        if password:
            # URL-encode password to handle special characters like @, /, %
            encoded_password = quote_plus(password)
            return f"postgresql+asyncpg://{user}:{encoded_password}@{host}:{port}/{db}"
        return f"postgresql+asyncpg://{user}@{host}:{port}/{db}"

    DATABASE_URL: str = _build_database_url.__func__()

    # Database connection pool settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))

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
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "snowflake-arctic-embed:l")
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

