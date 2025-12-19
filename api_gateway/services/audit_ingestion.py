"""
Audit-driven documentation ingestion orchestrator.

Uses a Phase 1 audit report to decide whether to perform a full
documentation reindex or a targeted incremental update, then verifies
the resulting Weaviate state.

The audit report is expected to be a JSON/dict with keys:
  - missing: list[str]  # files not present in vector DB
  - mismatched: list[str]  # files with content mismatch
  - synced: list[str]  # files already correctly indexed
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from weaviate.classes.query import Filter

from ..utils.logger import get_logger
from .doc_ingestion import (
    chunk_by_headers,
    collection_status,
    ingest_documentation,
    scan_markdown_files,
)
from .incremental_indexer import index_files
from .weaviate_connection import (
    DOCUMENTATION_COLLECTION_NAME,
    WeaviateConnection,
)

logger = get_logger("api_gateway.audit_ingestion")


def _relative_to_workspace(path: Path) -> str:
    """
    Convert absolute path to path relative to workspace root.

    Mirrors the behavior used in doc_ingestion._relative_to_workspace.
    """
    workspace_root = Path(__file__).resolve().parents[2]
    try:
        return str(path.resolve().relative_to(workspace_root))
    except ValueError:
        return str(path.resolve())


def _load_audit_report(path: Path) -> dict[str, list[str]]:
    """Load audit report JSON from disk."""
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = data.get("missing", []) or []
    mismatched = data.get("mismatched", []) or []
    synced = data.get("synced", []) or []
    return {
        "missing": list(missing),
        "mismatched": list(mismatched),
        "synced": list(synced),
    }


def _expected_chunks_for_files(files: Iterable[Path]) -> dict[str, int]:
    """
    Compute expected chunk count per file using chunk_by_headers.

    Returns:
        Dict mapping workspace-relative file_path -> expected chunk count.
    """
    counts: dict[str, int] = {}
    for path in files:
        try:
            chunks = chunk_by_headers(path)
            rel = _relative_to_workspace(path)
            counts[rel] = len(chunks)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to chunk %s for verification: %s", path, exc)
    return counts


def _verify_files(
    client,
    files_to_ingest: list[Path],
) -> list[dict[str, Any]]:
    """
    Verify that each file has the expected number of chunks in Weaviate.

    Returns:
        List of per-file verification dicts with keys:
        file_path, expected_chunks, actual_chunks, status.
    """
    collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)
    expected_counts = _expected_chunks_for_files(files_to_ingest)

    results: list[dict[str, Any]] = []

    for file_path in files_to_ingest:
        rel_path = _relative_to_workspace(file_path)
        expected = expected_counts.get(rel_path, 0)

        try:
            resp = collection.query.fetch_objects(
                filters=Filter.by_property("file_path").equal(rel_path),
                limit=1000,
            )
            actual = len(resp.objects or [])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Verification query failed for %s: %s", rel_path, exc)
            actual = 0

        if actual == 0:
            status = "missing"
        elif expected and actual != expected:
            status = "partial"
        else:
            status = "ok"

        results.append(
            {
                "file_path": rel_path,
                "expected_chunks": expected,
                "actual_chunks": actual,
                "status": status,
            }
        )

    return results


def run_audit_ingestion(audit: dict[str, list[str]]) -> dict[str, Any]:
    """
    Run documentation ingestion based on an audit report.

    Args:
        audit: Dict with keys missing, mismatched, synced (lists of file paths).

    Returns:
        Ingestion report dict with:
        - strategy: "full_reindex" | "incremental" | "noop"
        - files_processed
        - chunks_inserted
        - chunks_updated
        - errors
        - verification_passed
        - verification_details
        - collection_object_count
    """
    missing = audit.get("missing", []) or []
    mismatched = audit.get("mismatched", []) or []
    synced = audit.get("synced", []) or []

    files_to_ingest = sorted(set(missing) | set(mismatched))

    logger.info(
        "Audit report: %d missing, %d mismatched, %d synced. Total to ingest: %d",
        len(missing),
        len(mismatched),
        len(synced),
        len(files_to_ingest),
    )

    # Resolve to absolute Paths relative to workspace root
    workspace_root = Path(__file__).resolve().parents[2]
    files_to_ingest_paths = [workspace_root / f for f in files_to_ingest]

    # Determine strategy based on markdown file coverage
    all_markdown_files = scan_markdown_files()
    total_md_files = len(all_markdown_files)

    if total_md_files == 0:
        logger.warning("No markdown files discovered by scan_markdown_files()")

    coverage = len(files_to_ingest_paths) / total_md_files if total_md_files > 0 else 0.0

    logger.info(
        "Files to ingest cover %.1f%% of markdown corpus (%d of %d)",
        coverage * 100.0,
        len(files_to_ingest_paths),
        total_md_files,
    )

    strategy = "noop"
    chunks_inserted = 0
    chunks_updated = 0
    errors = 0

    # Choose strategy
    if not files_to_ingest_paths:
        logger.info("No files require ingestion. Skipping indexing.")
    elif coverage >= 0.5:
        # Full reindex via doc_ingestion.ingest_documentation(force_reindex=True)
        logger.info("Using full reindex strategy (coverage >= 50%%)")
        strategy = "full_reindex"
        with WeaviateConnection() as client:
            stats = ingest_documentation(
                client,
                force_reindex=True,
                dry_run=False,
            )
            # ingest_documentation returns files, chunks, errors
            chunks_inserted = int(stats.get("chunks", 0))
            errors = int(stats.get("errors", 0))
    else:
        # Incremental update via incremental_indexer.index_files
        logger.info("Using incremental strategy (coverage < 50%%)")
        strategy = "incremental"
        incremental_stats = index_files(files_to_ingest_paths, dry_run=False)
        chunks_inserted = int(incremental_stats.get("sections_added", 0))
        chunks_updated = int(incremental_stats.get("sections_updated", 0))
        errors = int(incremental_stats.get("errors", 0))

    # Verification
    verification_details: list[dict[str, Any]] = []
    verification_passed = True
    collection_object_count = 0

    if files_to_ingest_paths:
        with WeaviateConnection() as client:
            # Per-file verification
            verification_details = _verify_files(client, files_to_ingest_paths)
            for v in verification_details:
                if v["status"] != "ok":
                    verification_passed = False

            # Total collection object count
            status_dict = collection_status(client)
            collection_object_count = int(status_dict.get("object_count", 0))

    report: dict[str, Any] = {
        "strategy": strategy,
        "files_processed": len(files_to_ingest_paths),
        "chunks_inserted": chunks_inserted,
        "chunks_updated": chunks_updated,
        "errors": errors,
        "verification_passed": verification_passed,
        "verification_details": verification_details,
        "collection_object_count": collection_object_count,
    }

    return report


def main(argv: list[str] | None = None) -> None:
    """
    CLI entry point.

    Usage:
        python -m api_gateway.services.audit_ingestion path/to/audit_report.json
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Run documentation ingestion based on an audit report.",
    )
    parser.add_argument(
        "audit_report",
        help="Path to audit report JSON file with missing/mismatched/synced lists",
    )
    args = parser.parse_args(argv)

    report_path = Path(args.audit_report)
    if not report_path.is_file():
        logger.error("Audit report not found: %s", report_path)
        raise SystemExit(1)

    audit = _load_audit_report(report_path)
    report = run_audit_ingestion(audit)

    logging.getLogger(__name__).info("Ingestion report: %s", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
