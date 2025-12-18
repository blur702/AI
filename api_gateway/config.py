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
    """
    Application configuration settings loaded from environment variables.

    Centralizes all configuration values with sensible defaults. Loads from .env file
    and environment variables, with file values taking precedence (override=True).

    Attributes:
        API_PORT: Port for API gateway server (default: 1301)
        POSTGRES_HOST: PostgreSQL server hostname
        POSTGRES_PORT: PostgreSQL server port
        POSTGRES_USER: PostgreSQL username
        POSTGRES_PASSWORD: PostgreSQL password
        POSTGRES_DB: PostgreSQL database name
        DATABASE_URL: Full PostgreSQL connection URL (auto-built from components)
        DB_POOL_SIZE: Connection pool size for database
        DB_MAX_OVERFLOW: Maximum overflow connections beyond pool size
        DB_POOL_RECYCLE: Connection recycle time in seconds
        LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
        CORS_ORIGINS: Allowed CORS origins (comma-separated)
        VRAM_MANAGER_PATH: Absolute path to vram_manager.py
        WEAVIATE_URL: Weaviate HTTP endpoint URL
        WEAVIATE_GRPC_HOST: Weaviate gRPC hostname
        WEAVIATE_GRPC_PORT: Weaviate gRPC port
        OLLAMA_EMBEDDING_MODEL: Ollama model name for embeddings
        OLLAMA_API_ENDPOINT: Ollama API base URL
        SERVICES: Dictionary of service names to endpoint URLs
    """
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
        """
        Construct PostgreSQL connection URL from environment variables.

        Uses explicit DATABASE_URL if set, otherwise builds URL from component
        settings (POSTGRES_HOST, PORT, USER, PASSWORD, DB). Automatically URL-encodes
        password to handle special characters.

        Returns:
            PostgreSQL asyncpg connection URL
        """
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
        """
        Resolve VRAM manager path to absolute filesystem path.

        Converts relative paths (like ./vram_manager.py) to absolute paths
        relative to the project root directory (parent of api_gateway).

        Returns:
            Absolute path to vram_manager.py as string
        """
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
        """
        Parse and validate Weaviate gRPC port from environment variable.

        Attempts to parse WEAVIATE_GRPC_PORT as integer. Falls back to default
        50051 with warning if parsing fails.

        Returns:
            Valid port number as integer
        """
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

    # Known embedding models and their vector dimensions
    # Used by migrate_embeddings and collection schemas
    EMBEDDING_MODEL_DIMENSIONS: Dict[str, int] = {
        "nomic-embed-text": 768,
        "snowflake-arctic-embed:l": 1024,
        "mxbai-embed-large": 1024,
        "all-minilm": 384,
    }

    @classmethod
    def get_embedding_dimension(cls) -> int:
        """
        Get the vector dimension for the configured embedding model.

        Returns:
            Dimension for the current OLLAMA_EMBEDDING_MODEL, or 1024 as default
        """
        return cls.EMBEDDING_MODEL_DIMENSIONS.get(cls.OLLAMA_EMBEDDING_MODEL, 1024)

    SERVICES: Dict[str, str] = {
        "comfyui": "http://localhost:8188",
        "alltalk": "http://localhost:7851",
        "ollama": "http://localhost:11434",
        "wan2gp": "http://localhost:7860",
        "yue": "http://localhost:7870",
        "diffrhythm": "http://localhost:7871",
        "stable_audio": "http://localhost:7873",
    }

    # SSH and Drupal integration configuration.
    DRUPAL_SSH_HOST: str = os.getenv("DRUPAL_SSH_HOST", "65.181.112.77")
    DRUPAL_SSH_USER: str = os.getenv("DRUPAL_SSH_USER", "root")
    DRUPAL_SSH_PASSWORD: str = os.getenv("DRUPAL_SSH_PASSWORD", "T917nY9ILYmJGtUq")
    DRUPAL_WEB_ROOT: str = os.getenv("DRUPAL_WEB_ROOT", "/var/www/drupal/web")
    PLINK_PATH: str = os.getenv("PLINK_PATH", r"C:\Program Files\PuTTY\plink.exe")
    PSCP_PATH: str = os.getenv("PSCP_PATH", r"C:\Program Files\PuTTY\pscp.exe")
    DRUPAL_HOSTKEY: str = os.getenv(
        "DRUPAL_HOSTKEY",
        "ssh-ed25519 255 SHA256:EnWadrWQBKWVjQ8UV9ynQuSJbAjEuaMimajwlXoZecw",
    )


settings = Settings()
