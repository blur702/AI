"""
Documentation ingestion service for Weaviate.

Scans markdown files in the workspace, chunks them by headers for
semantic coherence, and ingests them into a `Documentation` collection
in Weaviate using the `text2vec-ollama` vectorizer with the
`nomic-embed-text` model (or the model configured via settings).

CLI usage (from project root, with api_gateway on PYTHONPATH):

    python -m api_gateway.services.doc_ingestion ingest --verbose
    python -m api_gateway.services.doc_ingestion reindex
    python -m api_gateway.services.doc_ingestion status
    python -m api_gateway.services.doc_ingestion ingest --dry-run
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import weaviate
from weaviate.classes.config import Configure, DataType, Property

from ..config import settings
from ..utils.logger import get_logger
from .weaviate_connection import WeaviateConnection, DOCUMENTATION_COLLECTION_NAME


logger = get_logger("api_gateway.doc_ingestion")


@dataclass
class DocChunk:
  title: str
  content: str
  file_path: str
  section: str

  def to_properties(self) -> Dict[str, str]:
    return {
      "title": self.title,
      "content": self.content,
      "file_path": self.file_path,
      "section": self.section,
    }


def scan_markdown_files() -> List[Path]:
  """
  Scan the workspace for markdown files.

  - Includes all `.md` files under `docs/`
  - Includes `.md` files in the workspace root
  - Excludes common large/irrelevant directories such as node_modules, .git, venvs.
  """
  workspace_root = Path(__file__).resolve().parents[2]
  docs_dir = workspace_root / "docs"

  excluded_dirs = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
  }

  def is_excluded(path: Path) -> bool:
    """Check if any parent directory of the path is in excluded_dirs."""
    for parent in path.resolve().parents:
      if parent.name in excluded_dirs:
        return True
    return False

  markdown_files: List[Path] = []

  if docs_dir.is_dir():
    for path in docs_dir.rglob("*.md"):
      if not is_excluded(path):
        markdown_files.append(path)

  for path in workspace_root.glob("*.md"):
    if not is_excluded(path):
      markdown_files.append(path)

  # Remove duplicates if any
  unique_files = sorted({p.resolve() for p in markdown_files})

  logger.info("Found %d markdown files for ingestion", len(unique_files))
  for p in unique_files:
    logger.debug("Markdown file: %s", p)

  return list(unique_files)


def _relative_to_workspace(path: Path) -> str:
  workspace_root = Path(__file__).resolve().parents[2]
  try:
    return str(path.resolve().relative_to(workspace_root))
  except ValueError:
    return str(path.resolve())


def chunk_by_headers(file_path: Path) -> List[DocChunk]:
  """
  Chunk a markdown file by header hierarchy.

  Each chunk contains:
    - title: header text (or filename if no headers)
    - content: section text including any code blocks/formatting
    - file_path: path relative to workspace root
    - section: header level string (e.g., "h1", "h2")
  """
  text = file_path.read_text(encoding="utf-8")
  lines = text.splitlines()

  chunks: List[DocChunk] = []
  current_title: Optional[str] = None
  current_level: Optional[str] = None
  current_content: List[str] = []
  in_code_block = False

  def flush_chunk() -> None:
    nonlocal current_title, current_level, current_content
    if current_title is None and not current_content:
      return
    title = current_title or file_path.stem
    section = current_level or "h0"
    content = "\n".join(current_content).strip()
    if not content:
      return
    chunks.append(
      DocChunk(
        title=title,
        content=content,
        file_path=_relative_to_workspace(file_path),
        section=section,
      )
    )
    current_content = []

  for line in lines:
    stripped = line.lstrip()

    # Track fenced code blocks (``` or ~~~). Inside code blocks, do not treat
    # lines starting with '#' as headings.
    if stripped.startswith("```") or stripped.startswith("~~~"):
      in_code_block = not in_code_block
      current_content.append(line)
      continue

    if not in_code_block and stripped.startswith("#"):
      header_marks = stripped.split(" ", 1)[0]
      level = len(header_marks)
      header_text = stripped[level:].strip() or file_path.stem
      flush_chunk()
      current_title = header_text
      current_level = f"h{level}"
      continue

    current_content.append(line)

  flush_chunk()

  if not chunks:
    # File without headers, treat entire content as one chunk
    chunks.append(
      DocChunk(
        title=file_path.stem,
        content=text.strip(),
        file_path=_relative_to_workspace(file_path),
        section="h0",
      )
    )

  logger.info(
    "Created %d chunks from %s",
    len(chunks),
    _relative_to_workspace(file_path),
  )
  return chunks


def create_documentation_collection(
  client: weaviate.WeaviateClient, force_reindex: bool = False
) -> None:
  """
  Create (or recreate) the Documentation collection.

  When `force_reindex` is True, deletes any existing collection first.
  """
  exists = client.collections.exists(DOCUMENTATION_COLLECTION_NAME)
  if exists and force_reindex:
    logger.info(
      "Deleting existing collection '%s' for reindexing",
      DOCUMENTATION_COLLECTION_NAME,
    )
    client.collections.delete(DOCUMENTATION_COLLECTION_NAME)
    exists = False

  if not exists:
    logger.info("Creating collection '%s'", DOCUMENTATION_COLLECTION_NAME)
    client.collections.create(
      name=DOCUMENTATION_COLLECTION_NAME,
      vectorizer_config=Configure.Vectorizer.text2vec_ollama(
        api_endpoint=settings.OLLAMA_API_ENDPOINT,
        model=settings.OLLAMA_EMBEDDING_MODEL,
      ),
      properties=[
        Property(name="title", data_type=DataType.TEXT),
        Property(name="content", data_type=DataType.TEXT),
        Property(name="file_path", data_type=DataType.TEXT),
        Property(name="section", data_type=DataType.TEXT),
      ],
    )
  else:
    logger.info("Collection '%s' already exists", DOCUMENTATION_COLLECTION_NAME)


def _batched(iterable: Iterable[DocChunk], batch_size: int) -> Iterable[List[DocChunk]]:
  batch: List[DocChunk] = []
  for item in iterable:
    batch.append(item)
    if len(batch) >= batch_size:
      yield batch
      batch = []
  if batch:
    yield batch


def ingest_documentation(
  client: weaviate.WeaviateClient,
  force_reindex: bool = False,
  dry_run: bool = False,
) -> Dict[str, int]:
  """
  Ingest all discovered markdown files into Weaviate.

  Returns statistics dict with keys:
    - files
    - chunks
    - errors
  """
  files = scan_markdown_files()
  total_files = 0
  total_chunks = 0
  errors = 0
  collection = None

  def chunk_stream() -> Iterable[DocChunk]:
    nonlocal total_files, total_chunks, errors
    for path in files:
      try:
        total_files += 1
        chunks = chunk_by_headers(path)
        total_chunks += len(chunks)
        for chunk in chunks:
          yield chunk
      except Exception as exc:  # noqa: BLE001
        errors += 1
        logger.exception("Failed to process %s: %s", path, exc)

  if dry_run:
    # In dry-run mode, never alter the collection (no delete/create, no inserts).
    for _chunk in chunk_stream():
      pass
    logger.info(
      "Dry run complete: %d files, %d chunks, %d errors (no data ingested)",
      total_files,
      total_chunks,
      errors,
    )
    return {"files": total_files, "chunks": total_chunks, "errors": errors}

  create_documentation_collection(client, force_reindex=force_reindex)
  collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)

  for batch in _batched(chunk_stream(), batch_size=64):
    try:
      collection.data.insert_many(
        [chunk.to_properties() for chunk in batch],
      )
      logger.info("Inserted batch of %d chunks", len(batch))
    except Exception as exc:  # noqa: BLE001
      errors += len(batch)
      logger.exception("Failed to insert batch of %d chunks: %s", len(batch), exc)

  logger.info(
    "Ingestion complete: %d files, %d chunks, %d errors",
    total_files,
    total_chunks,
    errors,
  )
  return {"files": total_files, "chunks": total_chunks, "errors": errors}


def collection_status(client: weaviate.WeaviateClient) -> Dict[str, int]:
  """
  Return basic statistics for the Documentation collection.

  Currently returns:
    - object_count
  """
  if not client.collections.exists(DOCUMENTATION_COLLECTION_NAME):
    logger.info(
      "Collection '%s' does not exist",
      DOCUMENTATION_COLLECTION_NAME,
    )
    return {"object_count": 0}

  collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)
  agg = collection.aggregate.over_all(total_count=True)
  total = agg.total_count or 0
  logger.info("Collection '%s' total objects: %s", DOCUMENTATION_COLLECTION_NAME, total)
  return {"object_count": int(total)}


def _configure_logging(verbose: bool) -> None:
  if verbose:
    logging.getLogger().setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
  else:
    # Respect LOG_LEVEL from settings for the module logger
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)


def main(argv: Optional[List[str]] = None) -> None:
  parser = argparse.ArgumentParser(
    description="Documentation ingestion service for Weaviate.",
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
    help="Scan and chunk documents without ingesting into Weaviate.",
  )

  args = parser.parse_args(argv)
  _configure_logging(args.verbose)

  # Quick connectivity hint before opening connection
  logger.info("WEAVIATE_URL=%s", settings.WEAVIATE_URL)

  exit_code = 0

  try:
    with WeaviateConnection() as client:
      if args.command == "status":
        stats = collection_status(client)
        logger.info("Status: %s", stats)
      else:
        force = args.command == "reindex"
        stats = ingest_documentation(
          client,
          force_reindex=force,
          dry_run=args.dry_run,
        )
        logger.info("Ingestion stats: %s", stats)
  except Exception as exc:  # noqa: BLE001
    logger.exception("doc_ingestion command failed: %s", exc)
    exit_code = 1

  raise SystemExit(exit_code)


if __name__ == "__main__":
  main()
