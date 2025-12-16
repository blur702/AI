"""
Drupal module documentation ingestion service for Weaviate.

Fetches documentation files from a remote Drupal server via SSH,
chunks them by headers, and ingests them into Weaviate using
manual vectorization via Ollama.

CLI usage:
    python -m api_gateway.services.drupal_doc_ingestion ingest --verbose
    python -m api_gateway.services.drupal_doc_ingestion reindex
    python -m api_gateway.services.drupal_doc_ingestion status
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .drupal_ssh import SSHCommandError, run_drupal_ssh
from .weaviate_connection import WeaviateConnection

logger = get_logger("api_gateway.drupal_doc_ingestion")

# Weaviate collection name
DRUPAL_DOCS_COLLECTION = "DrupalModuleDocs"
DRUPAL_WEB_ROOT = settings.DRUPAL_WEB_ROOT


@dataclass
class DrupalDocChunk:
    """Represents a chunk of Drupal module documentation."""
    title: str
    content: str
    file_path: str
    section: str
    module_name: str
    module_type: str  # 'contrib', 'core', or 'custom'

    def to_properties(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "content": self.content,
            "file_path": self.file_path,
            "section": self.section,
            "module_name": self.module_name,
            "module_type": self.module_type,
        }


def get_doc_text_for_embedding(chunk: DrupalDocChunk) -> str:
    """Build text representation for embedding computation."""
    parts = [chunk.module_name]
    if chunk.title:
        parts.append(chunk.title)
    if chunk.content:
        parts.append(chunk.content[:1000])
    return " ".join(parts)


def run_ssh_command(command: str) -> str:
    """Execute command via the shared Drupal SSH helper."""
    result = run_drupal_ssh(command)
    return result.stdout


def fetch_doc_files() -> List[Dict[str, str]]:
    """Fetch list of documentation files from Drupal server."""
    # Find all README and markdown files in modules
    command = f"""find {DRUPAL_WEB_ROOT}/modules/contrib {DRUPAL_WEB_ROOT}/core/modules -type f \\( -name 'README*' -o -name '*.md' -o -name 'INSTALL*' -o -name 'CHANGELOG*' \\) 2>/dev/null"""

    output = run_ssh_command(command)
    files = []

    for line in output.strip().split('\n'):
        if not line:
            continue
        path = line.strip()

        # Determine module type and name
        if '/modules/contrib/' in path:
            module_type = 'contrib'
            # Extract module name from path
            parts = path.split('/modules/contrib/')[1].split('/')
            module_name = parts[0]
        elif '/core/modules/' in path:
            module_type = 'core'
            parts = path.split('/core/modules/')[1].split('/')
            module_name = parts[0]
        else:
            module_type = 'custom'
            module_name = 'unknown'

        files.append({
            'path': path,
            'module_name': module_name,
            'module_type': module_type,
        })

    logger.info("Found %d documentation files on Drupal server", len(files))
    return files


def fetch_file_content(remote_path: str) -> str:
    """Fetch content of a single file from Drupal server."""
    command = f"cat '{remote_path}'"
    return run_ssh_command(command)


def chunk_by_headers(content: str, file_info: Dict[str, str]) -> List[DrupalDocChunk]:
    """Chunk markdown content by header hierarchy."""
    lines = content.splitlines()
    chunks: List[DrupalDocChunk] = []

    current_title: Optional[str] = None
    current_level: Optional[str] = None
    current_content: List[str] = []
    in_code_block = False

    def flush_chunk() -> None:
        nonlocal current_title, current_level, current_content
        if current_title is None and not current_content:
            return
        title = current_title or Path(file_info['path']).stem
        section = current_level or "h0"
        chunk_content = "\n".join(current_content).strip()
        if not chunk_content:
            return
        chunks.append(DrupalDocChunk(
            title=title,
            content=chunk_content,
            file_path=file_info['path'],
            section=section,
            module_name=file_info['module_name'],
            module_type=file_info['module_type'],
        ))
        current_content = []

    for line in lines:
        # Track code blocks
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            current_content.append(line)
            continue

        if in_code_block:
            current_content.append(line)
            continue

        # Check for headers
        if line.startswith('#'):
            flush_chunk()
            level = len(line) - len(line.lstrip('#'))
            current_level = f"h{level}"
            current_title = line.lstrip('#').strip()
            continue

        current_content.append(line)

    flush_chunk()

    # If no chunks created, create one for entire content
    if not chunks and content.strip():
        chunks.append(DrupalDocChunk(
            title=Path(file_info['path']).stem,
            content=content.strip()[:5000],
            file_path=file_info['path'],
            section="h0",
            module_name=file_info['module_name'],
            module_type=file_info['module_type'],
        ))

    return chunks


def ensure_collection(client: weaviate.WeaviateClient) -> None:
    """Ensure the DrupalModuleDocs collection exists."""
    if client.collections.exists(DRUPAL_DOCS_COLLECTION):
        logger.info("Collection %s already exists", DRUPAL_DOCS_COLLECTION)
        return

    client.collections.create(
        name=DRUPAL_DOCS_COLLECTION,
        description="Drupal module documentation",
        vectorizer_config=Configure.Vectorizer.none(),
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
        ),
        properties=[
            Property(name="title", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="file_path", data_type=DataType.TEXT),
            Property(name="section", data_type=DataType.TEXT),
            Property(name="module_name", data_type=DataType.TEXT),
            Property(name="module_type", data_type=DataType.TEXT),
        ],
    )
    logger.info("Created collection %s", DRUPAL_DOCS_COLLECTION)


def ingest_docs(dry_run: bool = False, verbose: bool = False) -> int:
    """Ingest Drupal module documentation into Weaviate."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Fetch file list from Drupal server
    doc_files = fetch_doc_files()

    if not doc_files:
        logger.warning("No documentation files found")
        return 0

    all_chunks: List[DrupalDocChunk] = []

    # Fetch and chunk each file
    for file_info in doc_files:
        logger.debug("Processing: %s", file_info['path'])
        content = fetch_file_content(file_info['path'])
        if content:
            chunks = chunk_by_headers(content, file_info)
            all_chunks.extend(chunks)
            logger.debug("  -> %d chunks", len(chunks))

    logger.info("Total chunks: %d", len(all_chunks))

    if dry_run:
        logger.info("Dry run - would ingest %d chunks", len(all_chunks))
        for chunk in all_chunks[:5]:
            logger.info("  [%s] %s: %s...", chunk.module_name, chunk.title, chunk.content[:50])
        return len(all_chunks)

    # Connect to Weaviate and ingest
    with WeaviateConnection() as client:
        ensure_collection(client)
        collection = client.collections.get(DRUPAL_DOCS_COLLECTION)

        ingested = 0
        for chunk in all_chunks:
            try:
                text = get_doc_text_for_embedding(chunk)
                vector = get_embedding(text)
                collection.data.insert(
                    properties=chunk.to_properties(),
                    vector=vector,
                )
                ingested += 1
                if ingested % 10 == 0:
                    logger.info("Ingested %d/%d chunks", ingested, len(all_chunks))
            except Exception as e:
                logger.error("Failed to ingest chunk %s: %s", chunk.title, e)

        logger.info("Successfully ingested %d chunks", ingested)
        return ingested


def reindex() -> int:
    """Delete collection and re-ingest all documentation."""
    with WeaviateConnection() as client:
        if client.collections.exists(DRUPAL_DOCS_COLLECTION):
            client.collections.delete(DRUPAL_DOCS_COLLECTION)
            logger.info("Deleted collection %s", DRUPAL_DOCS_COLLECTION)

    return ingest_docs()


def status() -> None:
    """Show current ingestion status."""
    with WeaviateConnection() as client:
        if not client.collections.exists(DRUPAL_DOCS_COLLECTION):
            print(f"Collection {DRUPAL_DOCS_COLLECTION} does not exist")
            return

        collection = client.collections.get(DRUPAL_DOCS_COLLECTION)
        count = collection.aggregate.over_all(total_count=True).total_count
        print(f"Collection: {DRUPAL_DOCS_COLLECTION}")
        print(f"Total documents: {count}")

        # Show module breakdown
        # (simplified - would need groupby for full breakdown)


def main():
    parser = argparse.ArgumentParser(description="Drupal module documentation ingestion")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest documentation")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Don't actually ingest")
    ingest_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    subparsers.add_parser("reindex", help="Delete and re-ingest all docs")
    subparsers.add_parser("status", help="Show ingestion status")

    args = parser.parse_args()

    try:
        if args.command == "ingest":
            ingest_docs(dry_run=args.dry_run, verbose=args.verbose)
        elif args.command == "reindex":
            reindex()
        elif args.command == "status":
            status()
    except SSHCommandError as exc:
        logger.error("SSH command failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
