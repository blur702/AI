"""
Helper utilities for running SSH commands against the Drupal server.

Provides a centralized way to load PuTTY credentials, build sanitized command
lines, and execute commands with retries and masked logging. Used by ingestion
services and the new deployment workflow.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import settings

LOGGER = logging.getLogger("api_gateway.drupal_ssh")


class SSHCommandError(RuntimeError):
    """Raised when an SSH command exits with a non-zero status."""


@dataclass(frozen=True)
class SSHConfig:
    plink: str
    pscp: str
    host: str
    user: str
    password: str
    hostkey: str


def load_mcp_config() -> dict[str, str]:
    """Parse .mcp.json to extract PuTTY credentials, if available."""
    config_path = Path(".mcp.json")
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        LOGGER.warning("Failed to parse %s", config_path)
        return {}

    servers = data.get("mcpServers", {})
    server = servers.get("drupal-remote") or next(iter(servers.values()), {})
    return {
        "command": server.get("command", settings.PLINK_PATH),
        "args": server.get("args", []),
    }


def get_ssh_config() -> SSHConfig:
    """Build the SSH configuration using env vars, .mcp.json, or defaults."""
    mcp = load_mcp_config()
    plink = mcp.get("command", settings.PLINK_PATH)
    pscp = settings.PSCP_PATH
    host = settings.DRUPAL_SSH_HOST
    user = settings.DRUPAL_SSH_USER
    password = settings.DRUPAL_SSH_PASSWORD
    hostkey = settings.DRUPAL_HOSTKEY

    return SSHConfig(
        plink=plink,
        pscp=pscp,
        host=host,
        user=user,
        password=password,
        hostkey=hostkey,
    )


def _sanitize_command(cmd: list[str], password: str) -> str:
    """Mask password when logging the full command."""
    sanitized = ["***" if part == password else part for part in cmd]
    return " ".join(sanitized)


def run_drupal_ssh(
    command: str, timeout: int = 60, retries: int = 3
) -> subprocess.CompletedProcess:
    """Execute an SSH command with retry logic."""
    cfg = get_ssh_config()
    base_cmd = [
        cfg.plink,
        "-ssh",
        "-pw",
        cfg.password,
        "-hostkey",
        cfg.hostkey,
        f"{cfg.user}@{cfg.host}",
        command,
    ]

    last_exc: SSHCommandError | None = None
    for attempt in range(1, retries + 1):
        safe_cmd = _sanitize_command(base_cmd, cfg.password)
        LOGGER.debug("Running SSH command (%d/%d): %s", attempt, retries, safe_cmd)
        proc = subprocess.run(base_cmd, capture_output=True, text=True, timeout=timeout)
        LOGGER.debug("SSH stdout: %s", proc.stdout.strip())
        LOGGER.debug("SSH stderr: %s", proc.stderr.strip())
        if proc.returncode == 0:
            return proc
        last_exc = SSHCommandError(
            f"SSH command failed (exit {proc.returncode}): {command}; stderr: {proc.stderr.strip()}"
        )
        if attempt < retries:
            sleep_time = 2**attempt
            LOGGER.warning("Retrying SSH command in %ds", sleep_time)
            time.sleep(sleep_time)

    raise last_exc or SSHCommandError("SSH command failed without output.")


def build_pscp_command(local: Path, remote: str) -> list[str]:
    """Build PSCP upload command."""
    cfg = get_ssh_config()
    cmd = [
        cfg.pscp,
        "-r",
        "-pw",
        cfg.password,
        "-hostkey",
        cfg.hostkey,
        str(local),
        f"{cfg.user}@{cfg.host}:{remote}",
    ]
    LOGGER.debug("Built PSCP command: %s", _sanitize_command(cmd, cfg.password))
    return cmd
