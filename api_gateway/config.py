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

