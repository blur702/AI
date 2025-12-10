"""
Documentation ingestion service for Weaviate.

Scans markdown files in the workspace, chunks them by headers for
semantic coherence, and ingests them into a `Documentation` collection
in Weaviate using manual vectorization via Ollama API
(bypasses Weaviate's text2vec-ollama to avoid connection issues).

CLI usage (from project root, with api_gateway on PYTHONPATH):

    python -m api_gateway.services.doc_ingestion ingest --verbose
    python -m api_gateway.services.doc_ingestion reindex
    python -m api_gateway.services.doc_ingestion status
    python -m api_gateway.services.doc_ingestion ingest --dry-run
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .weaviate_connection import WeaviateConnection, DOCUMENTATION_COLLECTION_NAME


logger = get_logger("api_gateway.doc_ingestion")


def get_doc_text_for_embedding(chunk: "DocChunk") -> str:
    """
    Build text representation for embedding computation.

    Args:
        chunk: DocChunk object containing title and content

    Returns:
        Concatenated string of title and content (first 1000 chars) for embedding
    """
    parts = []
    if chunk.title:
        parts.append(chunk.title)
    if chunk.content:
        parts.append(chunk.content[:1000])  # Limit content length
    return " ".join(parts)


@dataclass
class DocChunk:
  """
  Represents a chunk of documentation text.

  Attributes:
      title: Section heading or filename if no headers
      content: The text content of this section
      file_path: Workspace-relative file path
      section: Header level (h1, h2, etc.) or h0 for no header
  """
  title: str
  content: str
  file_path: str
  section: str

  def to_properties(self) -> Dict[str, str]:
    """
    Convert chunk to Weaviate property dictionary.

    Returns:
        Dictionary with title, content, file_path, and section keys
    """
    return {
      "title": self.title,
      "content": self.content,
      "file_path": self.file_path,
      "section": self.section,
    }


# AI service directory mappings (same as code_ingestion.py)
AI_SERVICE_DIRS = {
    "alltalk_tts": "alltalk",
    "audiocraft": "audiocraft",
    "ComfyUI": "comfyui",
    "DiffRhythm": "diffrhythm",
    "MusicGPT": "musicgpt",
    "stable-audio-tools": "stable_audio",
    "Wan2GP": "wan2gp",
    "YuE": "yue",
}


def scan_markdown_files(include_service_readmes: bool = True) -> List[Path]:
  """
  Scan the workspace for markdown files.

  - Includes all `.md` files under `docs/`
  - Includes `.md` files in the workspace root
  - Optionally includes README.md files from AI service directories
  - Excludes common large/irrelevant directories such as node_modules, .git, venvs.

  Args:
      include_service_readmes: If True, include README.md from AI service directories
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
    # AI service venvs
    "audiocraft_env",
    "wan2gp_env",
    "yue_env",
    "alltalk_env",
    "alltalk_environment",
    "comfyui_env",
    "diffrhythm_env",
    "musicgpt_env",
    "stable_audio_env",
  }

  def is_excluded(path: Path) -> bool:
    """Check if any parent directory of the path is in excluded_dirs."""
    for parent in path.resolve().parents:
      if parent.name in excluded_dirs:
        return True
    return False

  markdown_files: List[Path] = []

  # Include docs/ directory
  if docs_dir.is_dir():
    for path in docs_dir.rglob("*.md"):
      if not is_excluded(path):
        markdown_files.append(path)

  # Include root .md files
  for path in workspace_root.glob("*.md"):
    if not is_excluded(path):
      markdown_files.append(path)

  # Include AI service READMEs
  if include_service_readmes:
    for dir_name in AI_SERVICE_DIRS.keys():
      service_dir = workspace_root / dir_name
      if service_dir.is_dir():
        # Look for README.md (case-insensitive on Windows)
        for readme_name in ["README.md", "readme.md", "Readme.md"]:
          readme_path = service_dir / readme_name
          if readme_path.exists():
            markdown_files.append(readme_path)
            break
        # Also include docs folder within service if it exists
        service_docs = service_dir / "docs"
        if service_docs.is_dir():
          for path in service_docs.rglob("*.md"):
            if not is_excluded(path):
              markdown_files.append(path)

  # Remove duplicates if any
  unique_files = sorted({p.resolve() for p in markdown_files})

  logger.info("Found %d markdown files for ingestion", len(unique_files))
  for p in unique_files:
    logger.debug("Markdown file: %s", p)

  return list(unique_files)


def _relative_to_workspace(path: Path) -> str:
  """
  Convert absolute path to path relative to workspace root.

  Args:
      path: Absolute file path

  Returns:
      Relative path string, or absolute path if not within workspace
  """
  workspace_root = Path(__file__).resolve().parents[2]
  try:
    return str(path.resolve().relative_to(workspace_root))
  except ValueError:
    return str(path.resolve())


def chunk_by_headers(file_path: Path) -> List[DocChunk]:
  """
  Chunk a markdown file by header hierarchy.

  Splits markdown files into semantic chunks at header boundaries while
  preserving code blocks. Each chunk contains content between consecutive
  headers.

  Args:
      file_path: Path to markdown file to chunk

  Returns:
      List of DocChunk objects, one per header section. If no headers exist,
      returns single chunk with entire file content.

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
    """Finalize current chunk and append to chunks list if non-empty."""
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

  Sets up the Weaviate collection schema with manual vectorization (no
  text2vec-ollama) to avoid connection issues. Uses COSINE distance metric.

  Args:
      client: Connected Weaviate client
      force_reindex: If True, deletes any existing collection first

  Collection schema:
      - title (TEXT): Section heading
      - content (TEXT): Section text
      - file_path (TEXT): Workspace-relative path
      - section (TEXT): Header level (h1, h2, etc.)
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
    # Use manual vectorization (none) to avoid Weaviate's text2vec-ollama connection issues
    # We compute embeddings via Python and pass them on insert
    client.collections.create(
      name=DOCUMENTATION_COLLECTION_NAME,
      vectorizer_config=Configure.Vectorizer.none(),
      vector_index_config=Configure.VectorIndex.hnsw(
        distance_metric=VectorDistances.COSINE,
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
  """
  Yield successive batches from an iterable.

  Args:
      iterable: Iterable of DocChunk objects
      batch_size: Maximum number of items per batch

  Yields:
      Lists of up to batch_size items
  """
  batch: List[DocChunk] = []
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


def ingest_documentation(
  client: weaviate.WeaviateClient,
  force_reindex: bool = False,
  dry_run: bool = False,
  progress_callback: Optional[ProgressCallback] = None,
  check_cancelled: Optional[CancelCheck] = None,
  check_paused: Optional[PauseCheck] = None,
) -> Dict[str, int]:
  """
  Ingest all discovered markdown files into Weaviate.

  Args:
    client: Weaviate client connection
    force_reindex: If True, delete and recreate the collection
    dry_run: If True, scan files without ingesting
    progress_callback: Optional callback(phase, current, total, message) for progress updates
    check_cancelled: Optional callback() -> bool to check if operation should be cancelled
    check_paused: Optional callback() -> bool to check if paused and wait. Returns True if cancelled.

  Returns statistics dict with keys:
    - files
    - chunks
    - errors
    - cancelled (bool, only if cancelled)
  """
  files = scan_markdown_files()
  total_files = len(files)
  processed_files = 0
  total_chunks = 0
  errors = 0
  collection = None
  cancelled = False

  def emit_progress(phase: str, current: int, total: int, message: str) -> None:
    """Call progress_callback if provided, suppressing any errors."""
    if progress_callback:
      try:
        progress_callback(phase, current, total, message)
      except Exception:  # noqa: BLE001
        pass  # Don't let callback errors stop ingestion

  def is_cancelled() -> bool:
    """Check if operation should be cancelled, suppressing callback errors."""
    if check_cancelled:
      try:
        return check_cancelled()
      except Exception:  # noqa: BLE001
        return False
    return False

  def is_paused() -> bool:
    """
    Check if paused and wait. Returns True if cancelled during wait.

    Returns:
        True if operation was cancelled during pause, False otherwise
    """
    if check_paused:
      try:
        return check_paused()
      except Exception:  # noqa: BLE001
        return False
    return False

  emit_progress("scanning", 0, total_files, f"Found {total_files} markdown files")

  def chunk_stream() -> Iterable[DocChunk]:
    """
    Stream DocChunks from all markdown files, respecting cancel/pause callbacks.

    Yields:
        DocChunk objects for each section of each file
    """
    nonlocal processed_files, total_chunks, errors, cancelled
    for idx, path in enumerate(files):
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
        chunks = chunk_by_headers(path)
        total_chunks += len(chunks)
        processed_files += 1
        emit_progress(
          "processing",
          idx + 1,
          total_files,
          f"Processing {_relative_to_workspace(path)}"
        )
        for chunk in chunks:
          yield chunk
      except Exception as exc:  # noqa: BLE001
        errors += 1
        processed_files += 1
        logger.exception("Failed to process %s: %s", path, exc)

  if dry_run:
    # In dry-run mode, never alter the collection (no delete/create, no inserts).
    for _chunk in chunk_stream():
      if cancelled:
        break
    logger.info(
      "Dry run complete: %d files, %d chunks, %d errors (no data ingested)",
      processed_files,
      total_chunks,
      errors,
    )
    result = {"files": processed_files, "chunks": total_chunks, "errors": errors}
    if cancelled:
      result["cancelled"] = True
    return result

  emit_progress("indexing", 0, total_files, "Creating/updating collection")
  create_documentation_collection(client, force_reindex=force_reindex)
  collection = client.collections.get(DOCUMENTATION_COLLECTION_NAME)

  inserted_count = 0
  for chunk in chunk_stream():
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
        text = get_doc_text_for_embedding(chunk)
        vector = get_embedding(text)
        collection.data.insert(chunk.to_properties(), vector=vector)
        inserted_count += 1
        if inserted_count % 50 == 0:
          logger.info("Inserted %d chunks so far...", inserted_count)
          emit_progress(
            "indexing",
            processed_files,
            total_files,
            f"Indexed {inserted_count} chunks"
          )
        break
      except Exception as exc:  # noqa: BLE001
        retries -= 1
        if retries == 0:
          errors += 1
          logger.warning("Failed to insert chunk '%s' after retries: %s", chunk.title[:50], exc)
        else:
          time.sleep(1)  # Brief pause before retry

  if cancelled:
    emit_progress("cancelled", processed_files, total_files, "Ingestion cancelled")
  else:
    emit_progress("complete", processed_files, total_files, "Ingestion complete")

  logger.info(
    "Ingestion %s: %d files, %d chunks, %d errors",
    "cancelled" if cancelled else "complete",
    processed_files,
    total_chunks,
    errors,
  )
  result = {"files": processed_files, "chunks": total_chunks, "errors": errors}
  if cancelled:
    result["cancelled"] = True
  return result


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
  """
  Configure logging level based on verbosity flag.

  Args:
      verbose: If True, enable DEBUG logging; otherwise use settings.LOG_LEVEL
  """
  if verbose:
    logger.setLevel(logging.DEBUG)
  else:
    # Respect LOG_LEVEL from settings for the module logger
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)


def main(argv: Optional[List[str]] = None) -> None:
  """
  CLI entry point for documentation ingestion.

  Args:
      argv: Optional command line arguments (for testing)

  Raises:
      SystemExit: On command failure
  """
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
