"""
Store errors and solutions from the dashboard startup fix session.

This script logs the errors discovered during the debugging session and
their solutions to the PostgreSQL database for future reference.
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from api_gateway.models.database import (  # noqa: E402
    AsyncSessionLocal,
    Error,
    ErrorSeverity,
    init_db,
)

ERRORS_AND_SOLUTIONS = [
    {
        "service": "dashboard_startup",
        "severity": ErrorSeverity.error,
        "message": "Dashboard not starting after system reboot",
        "context": {
            "cause": "start_dashboard.bat checked for environment variables but they don't persist after reboot",
            "solution": "Modified start_dashboard.bat to load credentials from .env file when environment variables not set",
            "file_modified": "start_dashboard.bat",
        },
    },
    {
        "service": "dashboard_startup",
        "severity": ErrorSeverity.warning,
        "message": "Missing Python dependencies: psutil, beautifulsoup4, lxml",
        "context": {
            "cause": "Dependencies not installed for Python 3.14",
            "solution": "Ran pip install psutil beautifulsoup4 lxml",
        },
    },
    {
        "service": "dashboard_startup",
        "severity": ErrorSeverity.error,
        "message": "Dashboard startup blocked by Docker Desktop startup wait",
        "context": {
            "cause": "dashboard_startup.vbs waited for Docker (up to 30s) and exited if it failed",
            "solution": "Reordered dashboard_startup.vbs to start dashboard FIRST, Docker services after",
            "file_modified": "dashboard_startup.vbs",
        },
    },
    {
        "service": "n8n",
        "severity": ErrorSeverity.error,
        "message": "N8N owner creation spinner - form submission hangs indefinitely",
        "context": {
            "cause": "N8N trying to send verification email without SMTP configured",
            "solution": "Created owner user directly in SQLite database with Python script using bcrypt password hashing",
            "files_created": [
                "scripts/create_n8n_owner.py",
                "scripts/set_n8n_owner_role.py",
            ],
        },
    },
    {
        "service": "n8n",
        "severity": ErrorSeverity.warning,
        "message": "N8N_USER_MANAGEMENT_DISABLED environment variable deprecated",
        "context": {
            "cause": "Newer N8N versions require owner setup through web UI or direct database insertion",
            "solution": "Created database scripts to bypass web form; documented API key in .secrets/n8n_api_key.txt",
        },
    },
    {
        "service": "coderabbit",
        "severity": ErrorSeverity.warning,
        "message": "Docstring coverage at 74.93% (threshold 80%)",
        "context": {
            "cause": "Many Python modules missing module docstrings and function docstrings",
            "solution": "Added comprehensive docstrings to all API Gateway and dashboard backend files",
            "files_modified": [
                "api_gateway/config.py",
                "api_gateway/main.py",
                "api_gateway/middleware/auth.py",
                "api_gateway/middleware/response.py",
                "api_gateway/models/database.py",
                "api_gateway/models/schemas.py",
                "api_gateway/routes/health.py",
                "api_gateway/services/job_queue.py",
                "api_gateway/services/vram_service.py",
                "api_gateway/utils/exceptions.py",
                "api_gateway/utils/logger.py",
                "dashboard/backend/app.py",
                "scripts/set_n8n_owner_role.py",
            ],
        },
    },
]


async def store_errors() -> None:
    """Store all errors and solutions to the database."""
    print("Initializing database...")
    await init_db()

    print(f"Storing {len(ERRORS_AND_SOLUTIONS)} errors to database...")
    async with AsyncSessionLocal() as session:
        for error_data in ERRORS_AND_SOLUTIONS:
            error = Error(
                service=error_data["service"],
                severity=error_data["severity"],
                message=error_data["message"],
                context=error_data["context"],
                resolved=True,
                resolved_at=datetime.now(UTC),
            )
            session.add(error)
            print(f"  - {error_data['service']}: {error_data['message'][:50]}...")

        await session.commit()
        print("Done! All errors stored and marked as resolved.")


if __name__ == "__main__":
    asyncio.run(store_errors())
