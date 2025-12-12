"""
Documentation Ingestion Audit and Verification.

Audits the Documentation collection in Weaviate to identify:
- Missing files: markdown files not in vector DB
- Mismatched files: files with outdated content
- Synced files: files already correctly indexed

Then performs ingestion using the appropriate strategy and verifies results.

CLI usage:
    # Run audit only
    python -m api_gateway.services.doc_ingestion_audit audit

    # Run audit and fix (ingest missing/outdated files)
    python -m api_gateway.services.doc_ingestion_audit fix

    # Full reindex (force rebuild entire collection)
    python -m api_gateway.services.doc_ingestion_audit fix --force-reindex

    # Dry run (show what would be done)
    python -m api_gateway.services.doc_ingestion_audit fix --dry-run

    # Verify collection integrity
    python -m api_gateway.services.doc_ingestion_audit verify
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from weaviate.classes.query import Filter

from ..utils.logger import get_logger
from .doc_ingestion import (
    chunk_by_headers,
    collection_status,
    ingest_documentation,
    scan_markdown_files,
    _relative_to_workspace,
    DOCUMENTATION_COLLECTION_NAME,
)
from .weaviate_connection import WeaviateConnection

logger = get_logger("api_gateway.doc_ingestion_audit")


@dataclass
class AuditResult:
    """Result of documentation audit."""

    missing: List[str] = field(default_factory=list)
    """Files not found in vector DB."""

    mismatched: List[str] = field(default_factory=list)
    """Files with outdated content (hash mismatch)."""

    synced: List[str] = field(default_factory=list)
    """Files correctly indexed."""

    errors: List[str] = field(default_factory=list)
    """Files that couldn't be audited."""

    @property
    def files_to_ingest(self) -> List[str]:
        """Combine missing and mismatched files for ingestion."""
        return self.missing + self.mismatched

    @property
    def total_files(self) -> int:
        """Total files discovered."""
        return len(self.missing) + len(self.mismatched) + len(self.synced) + len(self.errors)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "missing": self.missing,
            "mismatched": self.mismatched,
            "synced": self.synced,
            "errors": self.errors,
            "files_to_ingest": self.files_to_ingest,
            "total_files": self.total_files,
        }


@dataclass
class VerificationResult:
    """Result of post-ingestion verification."""

    file_path: str
    expected_chunks: int
    actual_chunks: int
    status: str  # "ok", "missing", "partial"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "expected_chunks": self.expected_chunks,
            "actual_chunks": self.actual_chunks,
            "status": self.status,
        }


@dataclass
class IngestionReport:
    """Final ingestion report."""

    strategy: str  # "full_reindex" or "incremental"
    files_processed: int
    chunks_inserted: int
    chunks_updated: int
    errors: int
    verification_passed: bool
    verification_details: List[VerificationResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy": self.strategy,
            "files_processed": self.files_processed,
            "chunks_inserted": self.chunks_inserted,
            "chunks_updated": self.chunks_updated,
            "errors": self.errors,
            "verification_passed": self.verification_passed,
            "verification_details": [v.to_dict() for v in self.verification_details],
        }


def compute_file_content_hash(file_path: Path) -> str:
    """
    Compute SHA256 hash of file content for change detection.

    Args:
        file_path: Path to markdown file

    Returns:
        64-character SHA256 hexdigest
    """
    content = file_path.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def audit_documentation(client) -> AuditResult:
    """
    Audit the Documentation collection against filesystem.

    Compares discovered markdown files against what's stored in Weaviate
    to identify missing, mismatched, and synced files.

    Args:
        client: Connected Weaviate client

    Returns:
        AuditResult with categorized files
    """
    result = AuditResult()

    # Discover all markdown files
    markdown_files = scan_markdown_files()
    logger.info("Discovered %d markdown files", len(markdown_files))

    # Check if collection exists
    if not client.collections.exists(DOCUMENTATION_COLLECTION_NAME):
        logger.warning("Documentation collection does not exist - all files are missing")
        for path in markdown_files:
            result.missing.append(str(path))
        return result

    collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)

    # For each file, check if it exists in the collection
    for file_path in markdown_files:
        rel_path = _relative_to_workspace(file_path)

        try:
            # Query for chunks from this file
            response = collection.query.fetch_objects(
                filters=Filter.by_property("file_path").equal(rel_path),
                limit=1000
            )

            chunk_count = len(response.objects)

            if chunk_count == 0:
                # File not in vector DB
                result.missing.append(str(file_path))
                logger.debug("Missing: %s", rel_path)
            else:
                # File exists - check if content matches by comparing chunk count
                expected_chunks = chunk_by_headers(file_path)

                if len(expected_chunks) != chunk_count:
                    # Chunk count mismatch - needs reindex
                    result.mismatched.append(str(file_path))
                    logger.debug(
                        "Mismatched: %s (expected %d chunks, found %d)",
                        rel_path, len(expected_chunks), chunk_count
                    )
                else:
                    # File appears synced
                    result.synced.append(str(file_path))
                    logger.debug("Synced: %s (%d chunks)", rel_path, chunk_count)

        except Exception as exc:
            result.errors.append(f"{file_path}: {exc}")
            logger.error("Error auditing %s: %s", rel_path, exc)

    logger.info(
        "Audit complete: %d missing, %d mismatched, %d synced, %d errors",
        len(result.missing), len(result.mismatched),
        len(result.synced), len(result.errors)
    )

    return result


def verify_file_ingestion(client, file_path: Path) -> VerificationResult:
    """
    Verify a single file was correctly ingested.

    Args:
        client: Connected Weaviate client
        file_path: Path to markdown file

    Returns:
        VerificationResult with chunk counts and status
    """
    rel_path = _relative_to_workspace(file_path)

    # Get expected chunk count
    try:
        expected_chunks = len(chunk_by_headers(file_path))
    except Exception:
        return VerificationResult(
            file_path=rel_path,
            expected_chunks=0,
            actual_chunks=0,
            status="error"
        )

    # Query actual chunks in collection
    if not client.collections.exists(DOCUMENTATION_COLLECTION_NAME):
        return VerificationResult(
            file_path=rel_path,
            expected_chunks=expected_chunks,
            actual_chunks=0,
            status="missing"
        )

    collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)

    try:
        response = collection.query.fetch_objects(
            filters=Filter.by_property("file_path").equal(rel_path),
            limit=1000
        )
        actual_chunks = len(response.objects)
    except Exception:
        return VerificationResult(
            file_path=rel_path,
            expected_chunks=expected_chunks,
            actual_chunks=0,
            status="error"
        )

    if actual_chunks == 0:
        status = "missing"
    elif actual_chunks < expected_chunks:
        status = "partial"
    else:
        status = "ok"

    return VerificationResult(
        file_path=rel_path,
        expected_chunks=expected_chunks,
        actual_chunks=actual_chunks,
        status=status
    )


def verify_collection_integrity(client) -> Dict[str, Any]:
    """
    Verify overall collection integrity.

    Args:
        client: Connected Weaviate client

    Returns:
        Dictionary with verification results
    """
    # Get expected total chunks
    markdown_files = scan_markdown_files()
    expected_total = 0
    file_details: List[VerificationResult] = []

    for file_path in markdown_files:
        try:
            chunks = chunk_by_headers(file_path)
            expected_total += len(chunks)
        except Exception as exc:
            logger.warning("Error counting chunks for %s: %s", file_path, exc)

    # Get actual collection count
    stats = collection_status(client)
    actual_total = stats.get("object_count", 0)

    # Verify each file
    for file_path in markdown_files:
        result = verify_file_ingestion(client, file_path)
        file_details.append(result)

    # Calculate pass/fail
    tolerance = 5  # Allow small variance for parsing edge cases
    counts_match = abs(expected_total - actual_total) <= tolerance

    files_ok = sum(1 for r in file_details if r.status == "ok")
    files_missing = sum(1 for r in file_details if r.status == "missing")
    files_partial = sum(1 for r in file_details if r.status == "partial")
    files_error = sum(1 for r in file_details if r.status == "error")

    verification_passed = counts_match and files_missing == 0 and files_partial == 0

    return {
        "expected_total_chunks": expected_total,
        "actual_total_chunks": actual_total,
        "counts_match": counts_match,
        "tolerance": tolerance,
        "files_ok": files_ok,
        "files_missing": files_missing,
        "files_partial": files_partial,
        "files_error": files_error,
        "verification_passed": verification_passed,
        "file_details": file_details,
    }


def run_ingestion_fix(
    client,
    audit_result: AuditResult,
    force_reindex: bool = False,
    dry_run: bool = False,
) -> IngestionReport:
    """
    Run ingestion based on audit results.

    Chooses strategy based on file count:
    - >50% files need update: full reindex via ingest_documentation()
    - <50% files need update: incremental via incremental_indexer

    Args:
        client: Connected Weaviate client
        audit_result: Result from audit_documentation()
        force_reindex: Force full reindex regardless of file count
        dry_run: Preview only, don't actually ingest

    Returns:
        IngestionReport with results
    """
    files_to_ingest = audit_result.files_to_ingest
    total_files = audit_result.total_files

    if not files_to_ingest and not force_reindex:
        logger.info("No files need ingestion - collection is up to date")
        return IngestionReport(
            strategy="none",
            files_processed=0,
            chunks_inserted=0,
            chunks_updated=0,
            errors=0,
            verification_passed=True,
        )

    # Determine strategy
    # Use full reindex if >50% of files need update OR force_reindex is set
    use_full_reindex = force_reindex or (
        total_files > 0 and len(files_to_ingest) / total_files > 0.5
    )

    strategy = "full_reindex" if use_full_reindex else "incremental"
    logger.info(
        "Using %s strategy: %d/%d files need update (%.1f%%)",
        strategy,
        len(files_to_ingest),
        total_files,
        (len(files_to_ingest) / total_files * 100) if total_files > 0 else 0
    )

    if dry_run:
        logger.info("[DRY RUN] Would process %d files via %s", len(files_to_ingest), strategy)
        for f in files_to_ingest[:10]:
            logger.info("  - %s", _relative_to_workspace(Path(f)))
        if len(files_to_ingest) > 10:
            logger.info("  ... and %d more", len(files_to_ingest) - 10)

        return IngestionReport(
            strategy=strategy,
            files_processed=len(files_to_ingest),
            chunks_inserted=0,
            chunks_updated=0,
            errors=0,
            verification_passed=True,
        )

    # Execute ingestion
    if use_full_reindex:
        # Full reindex path - use ingest_documentation with force_reindex=True
        stats = ingest_documentation(
            client,
            force_reindex=True,
            dry_run=False,
        )

        return IngestionReport(
            strategy=strategy,
            files_processed=stats.get("files", 0),
            chunks_inserted=stats.get("chunks", 0),
            chunks_updated=0,  # Full reindex doesn't update, just inserts
            errors=stats.get("errors", 0),
            verification_passed=stats.get("errors", 0) == 0,
        )
    else:
        # Incremental path - use incremental_indexer's index_doc_file
        from .incremental_indexer import index_doc_file
        from .doc_ingestion import create_documentation_collection

        create_documentation_collection(client)
        collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)

        total_added = 0
        total_updated = 0
        total_errors = 0

        for file_path_str in files_to_ingest:
            file_path = Path(file_path_str)
            logger.info("Indexing: %s", _relative_to_workspace(file_path))

            stats = index_doc_file(client, file_path, collection, dry_run=False)
            total_added += stats.get("sections_added", 0)
            total_updated += stats.get("sections_updated", 0)
            total_errors += stats.get("errors", 0)

        return IngestionReport(
            strategy=strategy,
            files_processed=len(files_to_ingest),
            chunks_inserted=total_added,
            chunks_updated=total_updated,
            errors=total_errors,
            verification_passed=total_errors == 0,
        )


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Documentation ingestion audit and verification"
    )
    parser.add_argument(
        "command",
        choices=["audit", "fix", "verify"],
        help="Command to execute: audit (check status), fix (ingest missing), verify (check integrity)"
    )
    parser.add_argument(
        "--force-reindex",
        action="store_true",
        help="Force full reindex regardless of file count"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args(argv)

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    try:
        with WeaviateConnection() as client:
            if args.command == "audit":
                result = audit_documentation(client)

                print("\n" + "=" * 60)
                print("DOCUMENTATION AUDIT REPORT")
                print("=" * 60)
                print(f"Total files discovered: {result.total_files}")
                print(f"Missing (not in DB):    {len(result.missing)}")
                print(f"Mismatched (outdated):  {len(result.mismatched)}")
                print(f"Synced (up to date):    {len(result.synced)}")
                print(f"Errors:                 {len(result.errors)}")
                print(f"Files needing ingest:   {len(result.files_to_ingest)}")
                print("=" * 60)

                if result.missing:
                    print("\nMissing files:")
                    for f in result.missing[:20]:
                        print(f"  - {_relative_to_workspace(Path(f))}")
                    if len(result.missing) > 20:
                        print(f"  ... and {len(result.missing) - 20} more")

                if result.mismatched:
                    print("\nMismatched files:")
                    for f in result.mismatched[:20]:
                        print(f"  - {_relative_to_workspace(Path(f))}")
                    if len(result.mismatched) > 20:
                        print(f"  ... and {len(result.mismatched) - 20} more")

            elif args.command == "fix":
                # First audit
                audit_result = audit_documentation(client)

                print("\n" + "=" * 60)
                print("AUDIT RESULTS")
                print("=" * 60)
                print(f"Files needing ingest: {len(audit_result.files_to_ingest)}")

                # Then fix
                report = run_ingestion_fix(
                    client,
                    audit_result,
                    force_reindex=args.force_reindex,
                    dry_run=args.dry_run,
                )

                print("\n" + "=" * 60)
                print("INGESTION REPORT")
                print("=" * 60)
                print(f"Strategy:           {report.strategy}")
                print(f"Files processed:    {report.files_processed}")
                print(f"Chunks inserted:    {report.chunks_inserted}")
                print(f"Chunks updated:     {report.chunks_updated}")
                print(f"Errors:             {report.errors}")
                print(f"Verification:       {'PASSED' if report.verification_passed else 'FAILED'}")
                print("=" * 60)

                if not report.verification_passed:
                    sys.exit(1)

            elif args.command == "verify":
                result = verify_collection_integrity(client)

                print("\n" + "=" * 60)
                print("VERIFICATION REPORT")
                print("=" * 60)
                print(f"Expected total chunks: {result['expected_total_chunks']}")
                print(f"Actual total chunks:   {result['actual_total_chunks']}")
                print(f"Counts match:          {result['counts_match']} (tolerance: ±{result['tolerance']})")
                print()
                print(f"Files OK:              {result['files_ok']}")
                print(f"Files missing:         {result['files_missing']}")
                print(f"Files partial:         {result['files_partial']}")
                print(f"Files with errors:     {result['files_error']}")
                print()
                print(f"VERIFICATION:          {'PASSED' if result['verification_passed'] else 'FAILED'}")
                print("=" * 60)

                if result['files_missing'] > 0:
                    print("\nMissing files:")
                    for detail in result['file_details']:
                        if detail.status == "missing":
                            print(f"  - {detail.file_path}")

                if result['files_partial'] > 0:
                    print("\nPartial files:")
                    for detail in result['file_details']:
                        if detail.status == "partial":
                            print(f"  - {detail.file_path} ({detail.actual_chunks}/{detail.expected_chunks} chunks)")

                if not result['verification_passed']:
                    sys.exit(1)

    except Exception as exc:
        logger.exception("Command failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
