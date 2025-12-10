from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict


APP_NAME = "DashboardApp"


def get_config_dir() -> Path:
    """Return the directory where the app stores its config and logs."""
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".config"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    """Return the full path to the JSON config file."""
    return get_config_dir() / "config.json"


@dataclass
class AppConfig:
    """Persistent configuration for the desktop dashboard app."""

    window_width: int = 1200
    window_height: int = 800
    window_x: int | None = None
    window_y: int | None = None
    last_tab: str = "dashboard"
    theme: str = "dark"

    # Resource panel
    resource_panel_expanded: bool = True

    # Auto-stop
    autostop_enabled: bool = False
    autostop_timeout_minutes: int = 30

    # Polling intervals (seconds)
    poll_services_interval: int = 5
    poll_vram_interval: int = 3
    poll_models_interval: int = 10

    # Service auto-start preferences (service_id -> bool)
    service_autostart: Dict[str, bool] | None = None


def load_config() -> AppConfig:
    """Load configuration from disk, falling back to defaults on error."""
    path = get_config_path()
    if not path.exists():
        return AppConfig()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return AppConfig()

    cfg = AppConfig()
    for field in asdict(cfg).keys():
        if field in raw:
            setattr(cfg, field, raw[field])
    return cfg


def save_config(config: AppConfig) -> None:
    """Persist configuration to disk."""
    path = get_config_path()
    try:
        path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    except OSError:
        # Best-effort: failure to save config should not crash the app.
        pass
