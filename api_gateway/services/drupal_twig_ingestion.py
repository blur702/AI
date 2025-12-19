"""
Drupal Twig template ingestion service for Weaviate.

Fetches .html.twig template files from a remote Drupal server via SSH,
and ingests them into Weaviate using manual vectorization via Ollama.

CLI usage:
    python -m api_gateway.services.drupal_twig_ingestion ingest --verbose
    python -m api_gateway.services.drupal_twig_ingestion reindex
    python -m api_gateway.services.drupal_twig_ingestion status
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .drupal_ssh import SSHCommandError, run_drupal_ssh
from .weaviate_connection import WeaviateConnection

logger = get_logger("api_gateway.drupal_twig_ingestion")

# Weaviate collection name
DRUPAL_TWIG_COLLECTION = "DrupalTwigTemplates"
DRUPAL_WEB_ROOT = settings.DRUPAL_WEB_ROOT


@dataclass
class TwigTemplate:
    """Represents a Drupal Twig template."""

    template_name: str
    content: str
    file_path: str
    source_type: str  # 'core_theme', 'core_module', 'contrib_module', 'custom_theme'
    source_name: str  # theme or module name
    template_type: str  # 'page', 'node', 'block', 'field', 'views', 'form', 'other'
    description: str  # extracted from comments

    def to_properties(self) -> dict[str, str]:
        return {
            "template_name": self.template_name,
            "content": self.content,
            "file_path": self.file_path,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "template_type": self.template_type,
            "description": self.description,
        }


def get_text_for_embedding(template: TwigTemplate) -> str:
    """Build text representation for embedding computation."""
    parts = [template.template_name, template.source_name]
    if template.description:
        parts.append(template.description)
    if template.template_type != "other":
        parts.append(template.template_type)
    # Include a snippet of the template content
    content_snippet = template.content[:800] if template.content else ""
    if content_snippet:
        parts.append(content_snippet)
    return " ".join(parts)


def run_ssh_command(command: str, timeout: int = 120) -> str:
    """Execute command via the shared Drupal SSH helper."""
    result = run_drupal_ssh(command, timeout=timeout)
    return result.stdout


def determine_template_type(filename: str, content: str) -> str:
    """Determine the type of template based on filename and content."""
    name_lower = filename.lower()

    if name_lower.startswith("page"):
        return "page"
    elif name_lower.startswith("node"):
        return "node"
    elif name_lower.startswith("block"):
        return "block"
    elif name_lower.startswith("field"):
        return "field"
    elif name_lower.startswith("views"):
        return "views"
    elif name_lower.startswith("form"):
        return "form"
    elif name_lower.startswith("comment"):
        return "comment"
    elif name_lower.startswith("user"):
        return "user"
    elif name_lower.startswith("taxonomy"):
        return "taxonomy"
    elif name_lower.startswith("menu"):
        return "menu"
    elif name_lower.startswith("region"):
        return "region"
    elif name_lower.startswith("html"):
        return "html"
    elif name_lower.startswith("maintenance"):
        return "maintenance"
    elif name_lower.startswith("status"):
        return "status"
    elif name_lower.startswith("input"):
        return "form"
    elif name_lower.startswith("table"):
        return "table"
    elif name_lower.startswith("pager"):
        return "pager"
    elif name_lower.startswith("image"):
        return "media"
    elif name_lower.startswith("media"):
        return "media"
    else:
        return "other"


def extract_description(content: str) -> str:
    """Extract description from Twig template comments."""
    # Look for docblock-style comments at the top
    # {# ... #} or multiline {#\n...\n#}

    # Try to find the first comment block
    match = re.search(r"\{#\s*(.*?)\s*#\}", content, re.DOTALL)
    if match:
        comment = match.group(1).strip()
        # Clean up the comment
        lines = comment.split("\n")
        # Take first few meaningful lines
        desc_lines = []
        for line in lines[:5]:
            line = line.strip().strip("*").strip("-").strip()
            if line and not line.startswith("@") and not line.startswith("Available variables"):
                desc_lines.append(line)
        if desc_lines:
            return " ".join(desc_lines)[:500]

    return ""


def fetch_twig_files() -> list[dict[str, str]]:
    """Fetch list of Twig template files from Drupal server."""
    # Find all .html.twig files in themes and modules
    command = f"""find {DRUPAL_WEB_ROOT}/core/themes {DRUPAL_WEB_ROOT}/core/modules {DRUPAL_WEB_ROOT}/modules/contrib {DRUPAL_WEB_ROOT}/themes/custom -name '*.html.twig' -type f 2>/dev/null"""

    output = run_ssh_command(command)
    files = []

    for line in output.strip().split("\n"):
        if not line:
            continue
        path = line.strip()

        # Determine source type and name
        if "/core/themes/" in path:
            source_type = "core_theme"
            parts = path.split("/core/themes/")[1].split("/")
            source_name = parts[0]
        elif "/core/modules/" in path:
            source_type = "core_module"
            parts = path.split("/core/modules/")[1].split("/")
            source_name = parts[0]
        elif "/modules/contrib/" in path:
            source_type = "contrib_module"
            parts = path.split("/modules/contrib/")[1].split("/")
            source_name = parts[0]
        elif "/themes/custom/" in path:
            source_type = "custom_theme"
            parts = path.split("/themes/custom/")[1].split("/")
            source_name = parts[0]
        else:
            source_type = "other"
            source_name = "unknown"

        template_name = Path(path).name

        files.append(
            {
                "path": path,
                "template_name": template_name,
                "source_type": source_type,
                "source_name": source_name,
            }
        )

    logger.info("Found %d Twig template files on Drupal server", len(files))
    return files


def fetch_file_content(remote_path: str) -> str:
    """Fetch content of a single file from Drupal server."""
    command = f"cat '{remote_path}'"
    return run_ssh_command(command)


def process_templates(file_list: list[dict[str, str]]) -> list[TwigTemplate]:
    """Fetch and process all template files."""
    templates: list[TwigTemplate] = []

    for file_info in file_list:
        logger.debug("Processing: %s", file_info["path"])
        content = fetch_file_content(file_info["path"])

        if not content or len(content.strip()) < 10:
            continue

        template_type = determine_template_type(file_info["template_name"], content)
        description = extract_description(content)

        templates.append(
            TwigTemplate(
                template_name=file_info["template_name"],
                content=content[:10000],  # Limit content size
                file_path=file_info["path"],
                source_type=file_info["source_type"],
                source_name=file_info["source_name"],
                template_type=template_type,
                description=description,
            )
        )

    return templates


def ensure_collection(client: weaviate.WeaviateClient) -> None:
    """Ensure the DrupalTwigTemplates collection exists."""
    if client.collections.exists(DRUPAL_TWIG_COLLECTION):
        logger.info("Collection %s already exists", DRUPAL_TWIG_COLLECTION)
        return

    client.collections.create(
        name=DRUPAL_TWIG_COLLECTION,
        description="Drupal Twig templates",
        vectorizer_config=Configure.Vectorizer.none(),
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
        ),
        properties=[
            Property(name="template_name", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="file_path", data_type=DataType.TEXT),
            Property(name="source_type", data_type=DataType.TEXT),
            Property(name="source_name", data_type=DataType.TEXT),
            Property(name="template_type", data_type=DataType.TEXT),
            Property(name="description", data_type=DataType.TEXT),
        ],
    )
    logger.info("Created collection %s", DRUPAL_TWIG_COLLECTION)


def ingest_templates(dry_run: bool = False, verbose: bool = False) -> int:
    """Ingest Drupal Twig templates into Weaviate."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Fetch file list from Drupal server
    twig_files = fetch_twig_files()

    if not twig_files:
        logger.warning("No Twig template files found")
        return 0

    # Process templates
    templates = process_templates(twig_files)
    logger.info("Processed %d templates", len(templates))

    if dry_run:
        logger.info("Dry run - would ingest %d templates", len(templates))
        for t in templates[:5]:
            logger.info(
                "  [%s/%s] %s: %s",
                t.source_type,
                t.source_name,
                t.template_name,
                t.description[:50] if t.description else "(no desc)",
            )
        return len(templates)

    # Connect to Weaviate and ingest
    with WeaviateConnection() as client:
        ensure_collection(client)
        collection = client.collections.get(DRUPAL_TWIG_COLLECTION)

        ingested = 0
        for template in templates:
            try:
                text = get_text_for_embedding(template)
                vector = get_embedding(text)
                collection.data.insert(
                    properties=template.to_properties(),
                    vector=vector,
                )
                ingested += 1
                if ingested % 50 == 0:
                    logger.info("Ingested %d/%d templates", ingested, len(templates))
            except Exception as e:
                logger.error("Failed to ingest template %s: %s", template.template_name, e)

        logger.info("Successfully ingested %d templates", ingested)
        return ingested


def reindex() -> int:
    """Delete collection and re-ingest all templates."""
    with WeaviateConnection() as client:
        if client.collections.exists(DRUPAL_TWIG_COLLECTION):
            client.collections.delete(DRUPAL_TWIG_COLLECTION)
            logger.info("Deleted collection %s", DRUPAL_TWIG_COLLECTION)

    return ingest_templates()


def status() -> None:
    """Show current ingestion status."""
    with WeaviateConnection() as client:
        if not client.collections.exists(DRUPAL_TWIG_COLLECTION):
            print(f"Collection {DRUPAL_TWIG_COLLECTION} does not exist")
            return

        collection = client.collections.get(DRUPAL_TWIG_COLLECTION)
        count = collection.aggregate.over_all(total_count=True).total_count
        print(f"Collection: {DRUPAL_TWIG_COLLECTION}")
        print(f"Total templates: {count}")


def main():
    parser = argparse.ArgumentParser(description="Drupal Twig template ingestion")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest templates")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Don't actually ingest")
    ingest_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    subparsers.add_parser("reindex", help="Delete and re-ingest all templates")
    subparsers.add_parser("status", help="Show ingestion status")

    args = parser.parse_args()

    try:
        if args.command == "ingest":
            ingest_templates(dry_run=args.dry_run, verbose=args.verbose)
        elif args.command == "reindex":
            reindex()
        elif args.command == "status":
            status()
    except SSHCommandError as exc:
        logger.error("SSH command failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
