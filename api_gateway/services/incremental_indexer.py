"""
Incremental Indexer for Weaviate Vector Database.

Indexes only specific changed files to the appropriate Weaviate collections.
Used by post-merge GitHub Actions and can be called manually.

Usage:
    # Index specific files
    python -m api_gateway.services.incremental_indexer --files file1.py file2.ts

    # Index from stdin (newline-separated file paths)
    echo -e "file1.py\nfile2.ts" | python -m api_gateway.services.incremental_indexer --stdin

    # Dry run (no actual indexing)
    python -m api_gateway.services.incremental_indexer --files file1.py --dry-run

    # Index git diff (changed files since last commit)
    python -m api_gateway.services.incremental_indexer --git-diff

    # Index git diff against specific branch
    python -m api_gateway.services.incremental_indexer --git-diff --base-branch master
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import hashlib
import uuid as uuid_module

from api_gateway.services.weaviate_connection import WeaviateConnection
from api_gateway.services.code_parsers import CodeParser
from api_gateway.services.code_entity_schema import (
    CodeEntity,
    create_code_entity_collection,
)
from api_gateway.services.doc_ingestion import (
    create_documentation_collection,
    chunk_by_headers,
    DocChunk,
)
from api_gateway.utils.embeddings import get_embedding


def generate_entity_uuid(entity: CodeEntity) -> str:
    """Generate a stable UUID for a code entity based on its identifying properties."""
    key = f"{entity.file_path}:{entity.full_name}:{entity.line_start}"
    return str(uuid_module.UUID(hashlib.md5(key.encode()).hexdigest()))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# File extensions we index
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".css"}
DOC_EXTENSIONS = {".md"}

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent


def get_service_name(file_path: Path) -> str:
    """Determine service name from file path."""
    try:
        rel_path = file_path.relative_to(PROJECT_ROOT)
        parts = rel_path.parts

        # Check if it's in an AI service directory
        ai_services = [
            "alltalk_tts", "audiocraft", "ComfyUI", "DiffRhythm",
            "MusicGPT", "stable-audio-tools", "Wan2GP", "YuE"
        ]
        for service in ai_services:
            if service in parts:
                return service.lower().replace("-", "_")

        # Default to core
        return "core"
    except ValueError:
        return "core"


def index_code_file(
    client,
    file_path: Path,
    collection,
    code_parser: CodeParser,
    dry_run: bool = False,
) -> dict:
    """
    Index a single code file to Weaviate.

    Returns:
        dict with keys: entities_added, entities_updated, errors
    """
    stats = {"entities_added": 0, "entities_updated": 0, "errors": 0}

    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        stats["errors"] += 1
        return stats

    service_name = get_service_name(file_path)
    extension = file_path.suffix.lower()

    try:
        # Parse the file
        entities = code_parser.parse_file(file_path)

        for entity in entities:
            try:
                # entity is already a CodeEntity object from the parser
                # Update service_name if not set
                if entity.service_name == "core":
                    entity.service_name = service_name

                if dry_run:
                    logger.info(f"  [DRY RUN] Would index: {entity.full_name}")
                    stats["entities_added"] += 1
                    continue

                # Generate UUID for deduplication
                uuid = generate_entity_uuid(entity)

                # Build text for embedding
                text_parts = [entity.full_name]
                if entity.docstring:
                    text_parts.append(entity.docstring)
                if entity.signature:
                    text_parts.append(entity.signature)
                text = "\n\n".join(text_parts)

                # Get embedding
                vector = get_embedding(text)

                # Check if entity exists
                existing = collection.query.fetch_object_by_id(uuid)

                if existing:
                    # Update existing
                    collection.data.update(
                        uuid=uuid,
                        properties=entity.to_properties(),
                        vector=vector,
                    )
                    stats["entities_updated"] += 1
                    logger.debug(f"  Updated: {entity.full_name}")
                else:
                    # Insert new
                    collection.data.insert(
                        uuid=uuid,
                        properties=entity.to_properties(),
                        vector=vector,
                    )
                    stats["entities_added"] += 1
                    logger.debug(f"  Added: {entity.full_name}")

            except Exception as e:
                logger.error(f"  Error indexing entity {entity.name}: {e}")
                stats["errors"] += 1

    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")
        stats["errors"] += 1

    return stats


def index_doc_file(
    client,
    file_path: Path,
    collection,
    dry_run: bool = False,
) -> dict:
    """
    Index a single documentation file to Weaviate.

    Returns:
        dict with keys: sections_added, sections_updated, errors
    """
    stats = {"sections_added": 0, "sections_updated": 0, "errors": 0}

    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        stats["errors"] += 1
        return stats

    try:
        # chunk_by_headers takes a file path and returns DocChunk objects
        chunks = chunk_by_headers(file_path)

        for chunk in chunks:
            try:
                if dry_run:
                    logger.info(f"  [DRY RUN] Would index section: {chunk.title}")
                    stats["sections_added"] += 1
                    continue

                # Build text for embedding
                text = f"{chunk.title}\n\n{chunk.content}"
                vector = get_embedding(text)

                # Generate UUID from file path + section title
                uuid_str = f"{file_path}:{chunk.title}"
                uuid_hash = hashlib.md5(uuid_str.encode()).hexdigest()

                properties = {
                    "title": chunk.title,
                    "content": chunk.content,
                    "file_path": str(file_path),
                    "section": chunk.section,
                }

                # Check if exists
                try:
                    existing = collection.query.fetch_object_by_id(uuid_hash)
                    if existing:
                        collection.data.update(
                            uuid=uuid_hash,
                            properties=properties,
                            vector=vector,
                        )
                        stats["sections_updated"] += 1
                        logger.debug(f"  Updated section: {chunk.title}")
                    else:
                        raise Exception("Not found")  # noqa: TRY301
                except Exception:
                    collection.data.insert(
                        uuid=uuid_hash,
                        properties=properties,
                        vector=vector,
                    )
                    stats["sections_added"] += 1
                    logger.debug(f"  Added section: {chunk.title}")

            except Exception as e:
                logger.error(f"  Error indexing section {chunk.title}: {e}")
                stats["errors"] += 1

    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")
        stats["errors"] += 1

    return stats


def _get_language(extension: str) -> str:
    """Map file extension to language name."""
    mapping = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".css": "css",
    }
    return mapping.get(extension, "unknown")


def get_git_changed_files(base_branch: str = "master") -> list[Path]:
    """Get list of changed files from git diff."""
    try:
        # Get changed files compared to base branch
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=PROJECT_ROOT,
        )
        files = [
            PROJECT_ROOT / f.strip()
            for f in result.stdout.strip().split("\n")
            if f.strip()
        ]
        return files
    except subprocess.CalledProcessError as e:
        logger.error(f"Git diff failed: {e}")
        return []


def get_files_changed_since(ref: str) -> list[Path]:
    """Get list of changed files since a git ref (e.g., HEAD~5, commit hash)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=PROJECT_ROOT,
        )
        files = [
            PROJECT_ROOT / f.strip()
            for f in result.stdout.strip().split("\n")
            if f.strip()
        ]
        return files
    except subprocess.CalledProcessError as e:
        logger.error(f"Git diff failed: {e}")
        return []


def index_files(
    files: list[Path],
    dry_run: bool = False,
) -> dict:
    """
    Index multiple files to Weaviate.

    Returns:
        dict with aggregated statistics
    """
    stats = {
        "code_files": 0,
        "doc_files": 0,
        "entities_added": 0,
        "entities_updated": 0,
        "sections_added": 0,
        "sections_updated": 0,
        "errors": 0,
        "skipped": 0,
    }

    # Filter to indexable files
    code_files = [f for f in files if f.suffix.lower() in CODE_EXTENSIONS]
    doc_files = [f for f in files if f.suffix.lower() in DOC_EXTENSIONS]
    skipped = len(files) - len(code_files) - len(doc_files)
    stats["skipped"] = skipped

    if not code_files and not doc_files:
        logger.info("No indexable files found")
        return stats

    logger.info(f"Found {len(code_files)} code files, {len(doc_files)} doc files to index")

    with WeaviateConnection() as client:
        code_parser = CodeParser()

        # Index code files
        if code_files:
            create_code_entity_collection(client)
            collection = client.collections.get("CodeEntity")

            for file_path in code_files:
                logger.info(f"Indexing code: {file_path}")
                file_stats = index_code_file(
                    client, file_path, collection, code_parser, dry_run
                )
                stats["code_files"] += 1
                stats["entities_added"] += file_stats["entities_added"]
                stats["entities_updated"] += file_stats["entities_updated"]
                stats["errors"] += file_stats["errors"]

        # Index doc files
        if doc_files:
            create_documentation_collection(client)
            collection = client.collections.get("Documentation")

            for file_path in doc_files:
                logger.info(f"Indexing docs: {file_path}")
                file_stats = index_doc_file(client, file_path, collection, dry_run)
                stats["doc_files"] += 1
                stats["sections_added"] += file_stats["sections_added"]
                stats["sections_updated"] += file_stats["sections_updated"]
                stats["errors"] += file_stats["errors"]

    return stats


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Incrementally index changed files to Weaviate"
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="Files to index",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read file paths from stdin (newline-separated)",
    )
    parser.add_argument(
        "--git-diff",
        action="store_true",
        help="Index files changed in git (compared to base branch)",
    )
    parser.add_argument(
        "--base-branch",
        default="master",
        help="Base branch for git diff (default: master)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files but don't actually index",
    )
    parser.add_argument(
        "--changed-since",
        metavar="REF",
        help="Index files changed since git ref (e.g., HEAD~5, abc123)",
    )

    args = parser.parse_args()

    # Collect files to index
    files: list[Path] = []

    if args.files:
        files.extend(Path(f) for f in args.files)

    if args.stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:
                files.append(Path(line))

    if args.git_diff:
        files.extend(get_git_changed_files(args.base_branch))

    if args.changed_since:
        files.extend(get_files_changed_since(args.changed_since))

    if not files:
        logger.error("No files specified. Use --files, --stdin, --git-diff, or --changed-since")
        sys.exit(1)

    # Make paths absolute
    files = [f if f.is_absolute() else PROJECT_ROOT / f for f in files]

    # Index
    stats = index_files(files, dry_run=args.dry_run)

    # Print summary
    print("\n" + "=" * 50)
    print("INDEXING SUMMARY")
    print("=" * 50)
    print(f"Code files processed: {stats['code_files']}")
    print(f"Doc files processed:  {stats['doc_files']}")
    print(f"Files skipped:        {stats['skipped']}")
    print(f"Entities added:       {stats['entities_added']}")
    print(f"Entities updated:     {stats['entities_updated']}")
    print(f"Doc sections added:   {stats['sections_added']}")
    print(f"Doc sections updated: {stats['sections_updated']}")
    print(f"Errors:               {stats['errors']}")
    print("=" * 50)

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
