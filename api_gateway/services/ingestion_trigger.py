"""
Unified CLI for triggering Weaviate ingestion.

Provides a single entry point for ingesting documentation and/or code
into Weaviate collections. Supports both full ingestion and incremental
updates from git hooks.

CLI usage (from project root):

    # Full ingestion
    python -m api_gateway.services.ingestion_trigger all          # Doc + Code (core)
    python -m api_gateway.services.ingestion_trigger doc          # Documentation only
    python -m api_gateway.services.ingestion_trigger code         # Code only (core)
    python -m api_gateway.services.ingestion_trigger code --service comfyui
    python -m api_gateway.services.ingestion_trigger all --reindex
    python -m api_gateway.services.ingestion_trigger status
    python -m api_gateway.services.ingestion_trigger all --dry-run

    # Incremental update (for git hooks)
    python -m api_gateway.services.ingestion_trigger --files "path/to/file1.py path/to/file2.md"
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

from ..config import settings
from ..utils.logger import get_logger
from .weaviate_connection import WeaviateConnection, CODE_ENTITY_COLLECTION_NAME, DOCUMENTATION_COLLECTION_NAME
from .doc_ingestion import (
    ingest_documentation,
    collection_status as doc_collection_status,
    chunk_by_headers,
)
from .code_ingestion import (
    ingest_code_entities,
    collection_status as code_collection_status,
    AI_SERVICE_DIRS,
    get_embedding,
)
from .code_parsers import CodeParser


logger = get_logger("api_gateway.ingestion_trigger")


def print_progress(
    ingestion_type: str,
    phase: str,
    current: int,
    total: int,
    message: str,
) -> None:
    """Print progress update to console."""
    if total > 0:
        pct = (current / total) * 100
        print(f"[{ingestion_type}] {phase}: {current}/{total} ({pct:.1f}%) - {message}")
    else:
        print(f"[{ingestion_type}] {phase}: {message}")


# File extensions that trigger code vs documentation ingestion
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".css"}
DOC_EXTENSIONS = {".md"}


def _relative_to_workspace(path: Path) -> str:
    """Convert path to workspace-relative string."""
    workspace_root = Path(__file__).resolve().parents[2]
    try:
        return str(path.resolve().relative_to(workspace_root))
    except ValueError:
        return str(path.resolve())


def run_incremental(file_paths: List[str], dry_run: bool = False) -> int:
    """
    Run incremental ingestion for specific files.

    This is designed to be called from git hooks to update only the
    changed files instead of reindexing everything.

    Args:
        file_paths: List of file paths (relative to workspace root)
        dry_run: If True, only show what would be done

    Returns:
        Exit code (0 for success, 1 for errors)
    """
    workspace_root = Path(__file__).resolve().parents[2]
    code_parser = CodeParser()

    # Categorize files
    code_files: List[Path] = []
    doc_files: List[Path] = []
    skipped_files: List[str] = []

    for file_path_str in file_paths:
        file_path = workspace_root / file_path_str
        if not file_path.exists():
            skipped_files.append(f"{file_path_str} (deleted or not found)")
            continue

        suffix = file_path.suffix.lower()
        if suffix in CODE_EXTENSIONS:
            code_files.append(file_path)
        elif suffix in DOC_EXTENSIONS:
            doc_files.append(file_path)
        else:
            skipped_files.append(f"{file_path_str} (unsupported type)")

    print(f"Incremental ingestion for {len(file_paths)} files:")
    print(f"  Code files: {len(code_files)}")
    print(f"  Doc files: {len(doc_files)}")
    print(f"  Skipped: {len(skipped_files)}")
    if skipped_files:
        for s in skipped_files:
            print(f"    - {s}")
    print()

    if dry_run:
        print("[DRY RUN] Would process:")
        for f in code_files:
            print(f"  [code] {_relative_to_workspace(f)}")
        for f in doc_files:
            print(f"  [doc] {_relative_to_workspace(f)}")
        return 0

    errors = 0

    try:
        with WeaviateConnection() as client:
            # Process documentation files
            if doc_files and client.collections.exists(DOCUMENTATION_COLLECTION_NAME):
                doc_collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)
                print("Processing documentation files...")

                for file_path in doc_files:
                    rel_path = _relative_to_workspace(file_path)
                    try:
                        # Delete existing chunks for this file
                        from weaviate.classes.query import Filter
                        doc_collection.data.delete_many(
                            where=Filter.by_property("file_path").equal(rel_path)
                        )

                        # Parse and insert new chunks
                        chunks = chunk_by_headers(file_path)
                        for chunk in chunks:
                            doc_collection.data.insert(chunk.to_properties())

                        print(f"  [doc] {rel_path}: {len(chunks)} chunks")
                    except Exception as exc:
                        print(f"  [doc] {rel_path}: ERROR - {exc}")
                        errors += 1

            # Process code files
            if code_files and client.collections.exists(CODE_ENTITY_COLLECTION_NAME):
                code_collection = client.collections.get(CODE_ENTITY_COLLECTION_NAME)
                print("Processing code files...")

                for file_path in code_files:
                    rel_path = _relative_to_workspace(file_path)
                    try:
                        # Delete existing entities for this file
                        from weaviate.classes.query import Filter
                        code_collection.data.delete_many(
                            where=Filter.by_property("file_path").equal(rel_path)
                        )

                        # Parse and insert new entities
                        entities = code_parser.parse_file(file_path)
                        for entity in entities:
                            # Compute embedding
                            text = f"{entity.entity_type}: {entity.full_name} {entity.signature} {entity.docstring}"
                            vector = get_embedding(text)
                            code_collection.data.insert(
                                entity.to_properties(),
                                vector=vector
                            )

                        print(f"  [code] {rel_path}: {len(entities)} entities")
                    except Exception as exc:
                        print(f"  [code] {rel_path}: ERROR - {exc}")
                        errors += 1

    except Exception as exc:
        print(f"Connection error: {exc}")
        return 1

    print()
    print(f"Incremental ingestion complete. Errors: {errors}")
    return 1 if errors > 0 else 0


def run_status() -> int:
    """Show status of all collections."""
    print(f"Weaviate URL: {settings.WEAVIATE_URL}")
    print()

    try:
        with WeaviateConnection() as client:
            # Documentation collection
            doc_stats = doc_collection_status(client)
            print("Documentation Collection:")
            print(f"  Objects: {doc_stats.get('object_count', 0)}")
            print()

            # Code collection
            code_stats = code_collection_status(client)
            print("Code Entity Collection:")
            print(f"  Exists: {code_stats.get('exists', False)}")
            print(f"  Objects: {code_stats.get('object_count', 0)}")
            if code_stats.get("entity_counts"):
                print("  Entity Types:")
                for entity_type, count in code_stats["entity_counts"].items():
                    print(f"    {entity_type}: {count}")
            print()

        return 0

    except Exception as exc:
        logger.exception("Failed to get status: %s", exc)
        return 1


def run_ingestion(
    targets: List[str],
    reindex: bool,
    dry_run: bool,
    code_service: str,
    verbose: bool,
) -> int:
    """Run ingestion for specified targets."""
    print(f"Weaviate URL: {settings.WEAVIATE_URL}")
    print(f"Targets: {', '.join(targets)}")
    print(f"Reindex: {reindex}")
    print(f"Dry run: {dry_run}")
    if "code" in targets:
        print(f"Code service: {code_service}")
    print()

    start_time = time.time()
    all_stats = {}
    exit_code = 0

    try:
        with WeaviateConnection() as client:
            # Documentation ingestion
            if "doc" in targets or "all" in targets:
                print("=" * 60)
                print("Starting documentation ingestion...")
                print("=" * 60)

                doc_stats = ingest_documentation(
                    client,
                    force_reindex=reindex,
                    dry_run=dry_run,
                    progress_callback=lambda phase, cur, tot, msg: print_progress(
                        "doc", phase, cur, tot, msg
                    ),
                )
                all_stats["documentation"] = doc_stats

                print()
                print(f"Documentation complete: {doc_stats.get('files', 0)} files, "
                      f"{doc_stats.get('chunks', 0)} chunks, "
                      f"{doc_stats.get('errors', 0)} errors")
                print()

                if doc_stats.get("errors", 0) > 0:
                    exit_code = 1

            # Code ingestion
            if "code" in targets or "all" in targets:
                print("=" * 60)
                print(f"Starting code ingestion (service: {code_service})...")
                print("=" * 60)

                code_stats = ingest_code_entities(
                    client,
                    force_reindex=reindex,
                    dry_run=dry_run,
                    service_name=code_service,
                    progress_callback=lambda phase, cur, tot, msg: print_progress(
                        "code", phase, cur, tot, msg
                    ),
                )
                all_stats["code"] = code_stats

                print()
                print(f"Code complete: {code_stats.get('files', 0)} files, "
                      f"{code_stats.get('entities', 0)} entities, "
                      f"{code_stats.get('errors', 0)} errors")
                print()

                if code_stats.get("errors", 0) > 0:
                    exit_code = 1

    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        return 1

    duration = time.time() - start_time
    print("=" * 60)
    print(f"Ingestion finished in {duration:.2f} seconds")
    print("=" * 60)

    return exit_code


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point."""
    # Build service choices dynamically
    service_choices = ["core", "all"] + sorted(AI_SERVICE_DIRS.values())

    parser = argparse.ArgumentParser(
        description="Unified Weaviate ingestion trigger for documentation and code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full ingestion
  python -m api_gateway.services.ingestion_trigger all
  python -m api_gateway.services.ingestion_trigger doc --reindex
  python -m api_gateway.services.ingestion_trigger code --service comfyui
  python -m api_gateway.services.ingestion_trigger status

  # Incremental update (for git hooks)
  python -m api_gateway.services.ingestion_trigger --files "api_gateway/app.py docs/README.md"
        """,
    )

    parser.add_argument(
        "target",
        choices=["all", "doc", "code", "status"],
        nargs="?",
        default=None,
        help="What to ingest: 'all' (doc + code), 'doc', 'code', or 'status' check",
    )

    parser.add_argument(
        "--files",
        type=str,
        default=None,
        help="Space-separated list of file paths for incremental update (from git hooks)",
    )

    parser.add_argument(
        "--service", "-s",
        choices=service_choices,
        default="all",
        help="For code ingestion: 'all' (default, all AI services), 'core', "
             "or a specific service name.",
    )

    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Delete existing collections and recreate before ingesting.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and parse files without actually ingesting into Weaviate.",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )

    args = parser.parse_args(argv)

    # Configure logging
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )

    # Handle incremental update mode
    if args.files:
        file_paths = args.files.split()
        exit_code = run_incremental(file_paths, dry_run=args.dry_run)
        sys.exit(exit_code)

    # Require target for full ingestion
    if not args.target:
        parser.error("target is required unless --files is specified")

    # Execute command
    if args.target == "status":
        exit_code = run_status()
    else:
        targets = [args.target] if args.target != "all" else ["doc", "code"]
        exit_code = run_ingestion(
            targets=targets,
            reindex=args.reindex,
            dry_run=args.dry_run,
            code_service=args.service,
            verbose=args.verbose,
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
