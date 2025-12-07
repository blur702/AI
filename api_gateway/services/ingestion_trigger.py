"""
Unified CLI for triggering Weaviate ingestion.

Provides a single entry point for ingesting documentation and/or code
into Weaviate collections.

CLI usage (from project root):

    python -m api_gateway.services.ingestion_trigger all          # Doc + Code (core)
    python -m api_gateway.services.ingestion_trigger doc          # Documentation only
    python -m api_gateway.services.ingestion_trigger code         # Code only (core)
    python -m api_gateway.services.ingestion_trigger code --service comfyui
    python -m api_gateway.services.ingestion_trigger all --reindex
    python -m api_gateway.services.ingestion_trigger status
    python -m api_gateway.services.ingestion_trigger all --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import List, Optional

from ..config import settings
from ..utils.logger import get_logger
from .weaviate_connection import WeaviateConnection
from .doc_ingestion import (
    ingest_documentation,
    collection_status as doc_collection_status,
)
from .code_ingestion import (
    ingest_code_entities,
    collection_status as code_collection_status,
    AI_SERVICE_DIRS,
)


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
  python -m api_gateway.services.ingestion_trigger all
  python -m api_gateway.services.ingestion_trigger doc --reindex
  python -m api_gateway.services.ingestion_trigger code --service comfyui
  python -m api_gateway.services.ingestion_trigger status
        """,
    )

    parser.add_argument(
        "target",
        choices=["all", "doc", "code", "status"],
        help="What to ingest: 'all' (doc + code), 'doc', 'code', or 'status' check",
    )

    parser.add_argument(
        "--service", "-s",
        choices=service_choices,
        default="core",
        help="For code ingestion: 'core' (default), 'all' (all AI services), "
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
