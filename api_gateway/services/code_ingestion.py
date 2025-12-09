"""
Code entity ingestion service for Weaviate.

Scans source code files in the workspace, parses them to extract code entities
(functions, classes, interfaces, types, variables, styles), and ingests them
into a `CodeEntity` collection in Weaviate using the `text2vec-ollama` vectorizer.

This enables semantic code search across the codebase.

CLI usage (from project root, with api_gateway on PYTHONPATH):

    python -m api_gateway.services.code_ingestion ingest --verbose
    python -m api_gateway.services.code_ingestion reindex
    python -m api_gateway.services.code_ingestion status
    python -m api_gateway.services.code_ingestion ingest --dry-run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import weaviate

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .code_entity_schema import (
    CodeEntity,
    create_code_entity_collection,
    get_collection_stats,
)
from .code_parsers import CodeParser
from .weaviate_connection import WeaviateConnection, CODE_ENTITY_COLLECTION_NAME


def get_entity_text_for_embedding(entity: CodeEntity) -> str:
    """
    Create text representation of entity for embedding.

    Combines key fields to create a semantically meaningful text for vectorization.
    """
    parts = [
        f"{entity.entity_type}: {entity.full_name}",
        entity.signature,
        entity.docstring,
    ]
    return " ".join(p for p in parts if p)


logger = get_logger("api_gateway.code_ingestion")


# Directories to exclude from scanning
EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    ".cache",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    "site-packages",
    "lib",
    "Lib",
    "Scripts",
    "bin",
    "eggs",
    ".eggs",
    # Conda and package-related
    "conda",
    "pkgs",
    "envs",
    "miniconda",
    "anaconda",
    # Documentation and test directories (for external projects)
    "docs",
    "doc",
    "examples",
    "example",
    "samples",
    "sample",
    # Other common build/output directories
    "output",
    "outputs",
    "logs",
    "tmp",
    "temp",
    ".tox",
    ".nox",
    # IDE and editor directories
    ".idea",
    ".vscode",
}

# File patterns to include
INCLUDE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".css"}

# AI service directory mappings: directory name -> service name
AI_SERVICE_DIRS: Dict[str, str] = {
    "alltalk_tts": "alltalk",
    "audiocraft": "audiocraft",
    "ComfyUI": "comfyui",
    "DiffRhythm": "diffrhythm",
    "MusicGPT": "musicgpt",
    "stable-audio-tools": "stable_audio",
    "Wan2GP": "wan2gp",
    "YuE": "yue",
}

# Virtual environment directories within AI services to exclude
AI_SERVICE_VENVS = {
    "audiocraft_env",
    "wan2gp_env",
    "yue_env",
    "alltalk_env",
    "alltalk_environment",  # Conda environment for alltalk
    "comfyui_env",
    "diffrhythm_env",
    "musicgpt_env",
    "stable_audio_env",
}


def _is_excluded(path: Path, extra_excludes: Optional[set[str]] = None) -> bool:
    """
    Check if any parent directory of the path is in excluded_dirs.

    Args:
        path: Path to check
        extra_excludes: Additional directory names to exclude (optional)

    Returns:
        True if path should be excluded, False otherwise
    """
    excluded = EXCLUDED_DIRS | (extra_excludes or set())
    for parent in path.resolve().parents:
        if parent.name in excluded:
            return True
    # Also check the file's immediate parent
    if path.parent.name in excluded:
        return True
    return False


def scan_source_files(service_name: Optional[str] = None) -> List[Path]:
    """
    Scan the workspace for source code files.

    Args:
        service_name: If provided, scan only that AI service's directory.
                     Use "core" for main project files (api_gateway, dashboard, etc.)
                     Use None to scan only core project files (same as "core").

    Includes:
    - Python files (.py)
    - TypeScript files (.ts, .tsx)
    - JavaScript files (.js, .jsx)
    - CSS files (.css)

    Excludes:
    - Common build/dependency directories (node_modules, .git, venvs, etc.)
    - AI service virtual environments
    """
    workspace_root = Path(__file__).resolve().parents[2]
    source_files: List[Path] = []

    if service_name is None or service_name == "core":
        # Scan core project directories
        scan_dirs = [
            workspace_root / "api_gateway",
            workspace_root / "dashboard",
            workspace_root / "mcp_servers",
            workspace_root / "tests",
        ]

        for scan_dir in scan_dirs:
            if not scan_dir.is_dir():
                continue

            for ext in INCLUDE_EXTENSIONS:
                for path in scan_dir.rglob(f"*{ext}"):
                    if not _is_excluded(path):
                        source_files.append(path)
    else:
        # Find the directory for this service
        service_dir = None
        for dir_name, svc_name in AI_SERVICE_DIRS.items():
            if svc_name == service_name:
                service_dir = workspace_root / dir_name
                break

        if service_dir is None:
            logger.error("Unknown service name: %s", service_name)
            return []

        if not service_dir.is_dir():
            logger.error("Service directory does not exist: %s", service_dir)
            return []

        # Scan the service directory, excluding its venvs
        for ext in INCLUDE_EXTENSIONS:
            for path in service_dir.rglob(f"*{ext}"):
                if not _is_excluded(path, AI_SERVICE_VENVS):
                    source_files.append(path)

    # Remove duplicates and sort
    unique_files = sorted({p.resolve() for p in source_files})

    logger.info("Found %d source files for ingestion (service=%s)", len(unique_files), service_name or "core")
    for p in unique_files:
        logger.debug("Source file: %s", p)

    return list(unique_files)


def scan_all_services() -> Dict[str, List[Path]]:
    """
    Scan all AI service directories and return files grouped by service.

    Returns:
        Dictionary mapping service_name to list of file paths.
    """
    workspace_root = Path(__file__).resolve().parents[2]
    result: Dict[str, List[Path]] = {}

    for dir_name, service_name in AI_SERVICE_DIRS.items():
        service_dir = workspace_root / dir_name
        if not service_dir.is_dir():
            logger.debug("Skipping non-existent service directory: %s", service_dir)
            continue

        files: List[Path] = []
        for ext in INCLUDE_EXTENSIONS:
            for path in service_dir.rglob(f"*{ext}"):
                if not _is_excluded(path, AI_SERVICE_VENVS):
                    files.append(path.resolve())

        if files:
            result[service_name] = sorted(files)
            logger.info("Found %d files for service '%s'", len(files), service_name)

    return result


def _batched(
    iterable: Iterable[CodeEntity], batch_size: int
) -> Iterable[List[CodeEntity]]:
    """Yield successive batches from an iterable."""
    batch: List[CodeEntity] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


ProgressCallback = Callable[[str, int, int, str], None]
CancelCheck = Callable[[], bool]
PauseCheck = Callable[[], bool]


def ingest_code_entities(
    client: weaviate.WeaviateClient,
    force_reindex: bool = False,
    dry_run: bool = False,
    service_name: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
    check_cancelled: Optional[CancelCheck] = None,
    check_paused: Optional[PauseCheck] = None,
) -> Dict[str, int]:
    """
    Ingest source files into Weaviate.

    Args:
        client: Connected Weaviate client
        force_reindex: If True, delete existing collection before creating
        dry_run: If True, scan and parse without inserting into Weaviate
        service_name: If provided, ingest only that service's code.
                     Use "core" for main project, "all" for all AI services,
                     or a specific service name (comfyui, alltalk, etc.)
        progress_callback: Optional callback(phase, current, total, message) for progress updates
        check_cancelled: Optional callback() -> bool to check if operation should be cancelled
        check_paused: Optional callback() -> bool to check if paused and wait. Returns True if cancelled.

    Returns:
        Statistics dict with keys:
        - files: Number of files processed
        - entities: Total number of code entities extracted
        - errors: Number of errors encountered
        - cancelled: (bool, only if cancelled)
    """
    code_parser = CodeParser()
    cancelled = False

    def emit_progress(phase: str, current: int, total: int, message: str) -> None:
        if progress_callback:
            try:
                progress_callback(phase, current, total, message)
            except Exception:  # noqa: BLE001
                pass  # Don't let callback errors stop ingestion

    def is_cancelled() -> bool:
        if check_cancelled:
            try:
                return check_cancelled()
            except Exception:  # noqa: BLE001
                return False
        return False

    def is_paused() -> bool:
        """Check if paused and wait. Returns True if cancelled during wait."""
        if check_paused:
            try:
                return check_paused()
            except Exception:  # noqa: BLE001
                return False
        return False

    # Determine which files to scan and their service names
    files_by_service: Dict[str, List[Path]] = {}

    emit_progress("scanning", 0, 0, "Scanning for source files...")

    if service_name == "all":
        # Scan all AI services (not core)
        files_by_service = scan_all_services()
    elif service_name is None or service_name == "core":
        # Scan core project only
        files_by_service["core"] = scan_source_files("core")
    else:
        # Scan specific service
        files = scan_source_files(service_name)
        if files:
            files_by_service[service_name] = files

    # Count total files for progress
    total_file_count = sum(len(files) for files in files_by_service.values())
    emit_progress("scanning", total_file_count, total_file_count, f"Found {total_file_count} source files")

    total_files = 0
    total_entities = 0
    errors = 0
    processed_files = 0

    def entity_stream() -> Iterable[CodeEntity]:
        nonlocal total_files, total_entities, errors, cancelled, processed_files
        for svc_name, files in files_by_service.items():
            for path in files:
                if is_cancelled():
                    cancelled = True
                    logger.info("Ingestion cancelled by user")
                    return

                # Check for pause and wait if paused
                if is_paused():
                    cancelled = True
                    logger.info("Ingestion cancelled during pause")
                    return

                try:
                    total_files += 1
                    processed_files += 1
                    entities = code_parser.parse_file(path)
                    total_entities += len(entities)
                    emit_progress(
                        "processing",
                        processed_files,
                        total_file_count,
                        f"Parsing {path.name} ({len(entities)} entities)"
                    )
                    logger.debug(
                        "Parsed %d entities from %s (service=%s)",
                        len(entities),
                        path.name,
                        svc_name,
                    )
                    for entity in entities:
                        # Override service_name for non-core services
                        if svc_name != "core":
                            entity.service_name = svc_name
                        yield entity
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    processed_files += 1
                    logger.exception("Failed to process %s: %s", path, exc)

    if dry_run:
        # In dry-run mode, never alter the collection (no delete/create, no inserts).
        for _entity in entity_stream():
            if cancelled:
                break
        logger.info(
            "Dry run complete: %d files, %d entities, %d errors (no data ingested)",
            total_files,
            total_entities,
            errors,
        )
        result = {"files": total_files, "entities": total_entities, "errors": errors}
        if cancelled:
            result["cancelled"] = True
        return result

    emit_progress("indexing", 0, total_file_count, "Creating/updating collection")
    create_code_entity_collection(client, force_reindex=force_reindex)
    collection = client.collections.get(CODE_ENTITY_COLLECTION_NAME)

    import time
    inserted = 0
    for entity in entity_stream():
        if cancelled:
            break

        retries = 3
        while retries > 0:
            if is_cancelled():
                cancelled = True
                break

            # Check for pause and wait if paused
            if is_paused():
                cancelled = True
                break

            try:
                # Compute embedding via Python (bypassing Weaviate's text2vec-ollama issues)
                text = get_entity_text_for_embedding(entity)
                vector = get_embedding(text)
                collection.data.insert(entity.to_properties(), vector=vector)
                inserted += 1
                if inserted % 50 == 0:
                    logger.info("Inserted %d entities so far...", inserted)
                    emit_progress(
                        "indexing",
                        processed_files,
                        total_file_count,
                        f"Indexed {inserted} entities"
                    )
                break
            except Exception as exc:  # noqa: BLE001
                retries -= 1
                if retries == 0:
                    errors += 1
                    logger.warning("Failed to insert entity %s after retries: %s", entity.full_name, exc)
                else:
                    time.sleep(1)  # Brief pause before retry

    if cancelled:
        emit_progress("cancelled", processed_files, total_file_count, "Ingestion cancelled")
    else:
        emit_progress("complete", processed_files, total_file_count, "Ingestion complete")

    logger.info(
        "Ingestion %s: %d files, %d entities, %d errors",
        "cancelled" if cancelled else "complete",
        total_files,
        total_entities,
        errors,
    )
    result = {"files": total_files, "entities": total_entities, "errors": errors}
    if cancelled:
        result["cancelled"] = True
    return result


def collection_status(client: weaviate.WeaviateClient) -> Dict[str, int]:
    """
    Return basic statistics for the CodeEntity collection.

    Returns:
        Dictionary with:
        - exists: Whether the collection exists
        - object_count: Total number of code entities
        - entity_counts: Breakdown by entity_type
    """
    return get_collection_stats(client)


def _configure_logging(verbose: bool) -> None:
    """
    Configure logging level based on verbosity flag.

    Args:
        verbose: If True, enable DEBUG logging; otherwise use settings.LOG_LEVEL
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    else:
        # Respect LOG_LEVEL from settings for the module logger
        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(level)


def main(argv: Optional[List[str]] = None) -> None:
    """
    CLI entry point for code ingestion.

    Args:
        argv: Optional command line arguments (for testing)

    Raises:
        SystemExit: On command failure
    """
    # Build service choices dynamically
    service_choices = ["core", "all"] + sorted(AI_SERVICE_DIRS.values())

    parser = argparse.ArgumentParser(
        description="Code entity ingestion service for Weaviate.",
    )
    parser.add_argument(
        "command",
        choices=["ingest", "reindex", "status"],
        nargs="?",
        default="ingest",
        help="Operation to perform (default: ingest).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and parse files without ingesting into Weaviate.",
    )
    parser.add_argument(
        "--service",
        "-s",
        choices=service_choices,
        default="all",
        help="Service to ingest: 'all' (default, all AI services), 'core', or specific service name.",
    )

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    # Quick connectivity hint before opening connection
    logger.info("WEAVIATE_URL=%s", settings.WEAVIATE_URL)
    logger.info("Service target: %s", args.service)

    exit_code = 0

    try:
        with WeaviateConnection() as client:
            if args.command == "status":
                stats = collection_status(client)
                logger.info("Status: %s", stats)
            else:
                force = args.command == "reindex"
                stats = ingest_code_entities(
                    client,
                    force_reindex=force,
                    dry_run=args.dry_run,
                    service_name=args.service,
                )
                logger.info("Ingestion stats: %s", stats)
    except Exception as exc:  # noqa: BLE001
        logger.exception("code_ingestion command failed: %s", exc)
        exit_code = 1

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
