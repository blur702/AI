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

from api_gateway.services.weaviate_connection import WeaviateConnection
from api_gateway.services.code_parsers import CodeParser
from api_gateway.services.code_ingestion import (
    CodeEntity,
    ensure_code_entity_collection,
    generate_entity_uuid,
)
from api_gateway.services.doc_ingestion import (
    ensure_documentation_collection,
    parse_markdown_sections,
    DocumentSection,
)
from api_gateway.utils.embeddings import get_embedding

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
                # Create CodeEntity object
                code_entity = CodeEntity(
                    entity_type=entity.get("type", "unknown"),
                    name=entity.get("name", ""),
                    full_name=entity.get("full_name", entity.get("name", "")),
                    signature=entity.get("signature", ""),
                    docstring=entity.get("docstring", ""),
                    source_code=entity.get("source", "")[:2000],  # Truncate
                    file_path=str(file_path),
                    line_number=entity.get("line", 0),
                    service_name=service_name,
                    language=_get_language(extension),
                )

                if dry_run:
                    logger.info(f"  [DRY RUN] Would index: {code_entity.full_name}")
                    stats["entities_added"] += 1
                    continue

                # Generate UUID for deduplication
                uuid = generate_entity_uuid(code_entity)

                # Build text for embedding
                text_parts = [code_entity.full_name]
                if code_entity.docstring:
                    text_parts.append(code_entity.docstring)
                if code_entity.signature:
                    text_parts.append(code_entity.signature)
                text = "\n\n".join(text_parts)

                # Get embedding
                vector = get_embedding(text)

                # Check if entity exists
                existing = collection.query.fetch_object_by_id(uuid)

                if existing:
                    # Update existing
                    collection.data.update(
                        uuid=uuid,
                        properties=code_entity.__dict__,
                        vector=vector,
                    )
                    stats["entities_updated"] += 1
                    logger.debug(f"  Updated: {code_entity.full_name}")
                else:
                    # Insert new
                    collection.data.insert(
                        uuid=uuid,
                        properties=code_entity.__dict__,
                        vector=vector,
                    )
                    stats["entities_added"] += 1
                    logger.debug(f"  Added: {code_entity.full_name}")

            except Exception as e:
                logger.error(f"  Error indexing entity {entity.get('name')}: {e}")
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
        content = file_path.read_text(encoding="utf-8")
        sections = parse_markdown_sections(content, str(file_path))

        for section in sections:
            try:
                if dry_run:
                    logger.info(f"  [DRY RUN] Would index section: {section.title}")
                    stats["sections_added"] += 1
                    continue

                # Build text for embedding
                text = f"{section.title}\n\n{section.content}"
                vector = get_embedding(text)

                # Generate UUID from file path + section title
                import hashlib
                uuid_str = f"{file_path}:{section.title}"
                uuid = hashlib.md5(uuid_str.encode()).hexdigest()

                properties = {
                    "title": section.title,
                    "content": section.content,
                    "file_path": str(file_path),
                    "section": section.header_level,
                }

                # Check if exists
                try:
                    existing = collection.query.fetch_object_by_id(uuid)
                    if existing:
                        collection.data.update(
                            uuid=uuid,
                            properties=properties,
                            vector=vector,
                        )
                        stats["sections_updated"] += 1
                        logger.debug(f"  Updated section: {section.title}")
                    else:
                        raise Exception("Not found")  # noqa: TRY301
                except Exception:
                    collection.data.insert(
                        uuid=uuid,
                        properties=properties,
                        vector=vector,
                    )
                    stats["sections_added"] += 1
                    logger.debug(f"  Added section: {section.title}")

            except Exception as e:
                logger.error(f"  Error indexing section {section.title}: {e}")
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
            ensure_code_entity_collection(client)
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
            ensure_documentation_collection(client)
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

    if not files:
        logger.error("No files specified. Use --files, --stdin, or --git-diff")
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
