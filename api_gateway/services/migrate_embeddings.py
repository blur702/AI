"""
Embedding model migration script for Weaviate.

This script handles migration when changing embedding models (e.g., from
nomic-embed-text to snowflake-arctic-embed:l). Since embedding dimensions
differ between models, all collections must be re-indexed.

IMPORTANT: Different embedding models produce vectors of different dimensions
and semantics. You CANNOT mix embeddings from different models. This migration
deletes all existing collections and re-ingests all data with the new model.

CLI usage (from project root):
    python -m api_gateway.services.migrate_embeddings check
    python -m api_gateway.services.migrate_embeddings migrate --dry-run
    python -m api_gateway.services.migrate_embeddings migrate
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional

import httpx

from ..config import settings
from ..utils.logger import get_logger
from .weaviate_connection import (
    WeaviateConnection,
    DOCUMENTATION_COLLECTION_NAME,
    CODE_ENTITY_COLLECTION_NAME,
    DRUPAL_API_COLLECTION_NAME,
)

logger = get_logger("api_gateway.migrate_embeddings")

# Import embedding models from centralized config
EMBEDDING_MODELS = settings.EMBEDDING_MODEL_DIMENSIONS

ALL_COLLECTIONS = [
    DOCUMENTATION_COLLECTION_NAME,
    CODE_ENTITY_COLLECTION_NAME,
    DRUPAL_API_COLLECTION_NAME,
]


def get_ollama_models() -> List[str]:
    """
    Get list of models available in Ollama.

    Returns:
        List of model name strings from Ollama /api/tags endpoint,
        or empty list on error
    """
    try:
        response = httpx.get(
            f"{settings.OLLAMA_API_ENDPOINT}/api/tags",
            timeout=30.0,
        )
        response.raise_for_status()
        models = response.json().get("models", [])
        return [m["name"] for m in models]
    except Exception as e:
        logger.warning("Failed to get Ollama models: %s", e)
        return []


def check_model_available(model_name: str) -> bool:
    """
    Check if a model is available in Ollama by trying to generate an embedding.

    First attempts a direct embedding test (most reliable), then falls back
    to checking the model list with tag variation handling.

    Args:
        model_name: Model identifier (e.g., "snowflake-arctic-embed:l")

    Returns:
        True if model is available and can generate embeddings, False otherwise
    """
    # First try direct embedding test - most reliable
    try:
        response = httpx.post(
            f"{settings.OLLAMA_API_ENDPOINT}/api/embeddings",
            json={"model": model_name, "prompt": "test"},
            timeout=60.0,
        )
        if response.status_code == 200:
            return True
    except Exception as e:
        logger.debug("Embedding test failed: %s", e)

    # Fall back to model list check
    models = get_ollama_models()
    # Handle both exact match and tag variations
    return any(
        m == model_name or m.startswith(f"{model_name}:") or model_name.startswith(f"{m}:")
        for m in models
    )


def get_embedding_dimension(model_name: str) -> Optional[int]:
    """
    Get embedding dimension for a model, or None if unknown.

    Args:
        model_name: Model identifier

    Returns:
        Expected embedding vector dimension, or None if model is not in known list
    """
    return EMBEDDING_MODELS.get(model_name)


def check_status() -> Dict[str, Any]:
    """
    Check current configuration and collection status.

    Queries Ollama for model availability and Weaviate for collection counts.

    Returns:
        Dict with keys:
            - configured_model (str): Current model in settings
            - model_available (bool): Whether model is available in Ollama
            - model_dimensions (int|None): Expected embedding dimensions
            - collections (dict): Collection name -> object count (or None if not exists)
    """
    model = settings.OLLAMA_EMBEDDING_MODEL
    available = check_model_available(model)
    dimensions = get_embedding_dimension(model)

    collections = {}
    try:
        with WeaviateConnection() as client:
            for coll_name in ALL_COLLECTIONS:
                if client.collections.exists(coll_name):
                    coll = client.collections.get(coll_name)
                    agg = coll.aggregate.over_all(total_count=True)
                    collections[coll_name] = agg.total_count or 0
                else:
                    collections[coll_name] = None  # Does not exist
    except Exception as e:
        logger.warning("Failed to connect to Weaviate: %s", e)

    return {
        "configured_model": model,
        "model_available": available,
        "model_dimensions": dimensions,
        "collections": collections,
    }


def migrate(dry_run: bool = False) -> Dict[str, Any]:
    """
    Perform full migration: delete all collections and re-ingest.

    Deletes all Weaviate collections (Documentation, CodeEntity, DrupalAPIEntity)
    and re-indexes Documentation and CodeEntity with new embedding model. DrupalAPIEntity
    collection is recreated empty (requires re-running scraper).

    Args:
        dry_run: If True, only report what would be done without making changes

    Returns:
        Dict with migration results:
            - success (bool): Whether migration succeeded
            - model (str): Model used for migration
            - dry_run (bool): Whether this was a dry run
            - collections_deleted (list): List of deleted collection names
            - collections_reindexed (dict): Collection -> reindex stats
            - error (str, optional): Error message if failed
    """
    # Import ingestion services here to avoid circular imports
    from .doc_ingestion import ingest_documentation
    from .code_ingestion import ingest_code_entities

    model = settings.OLLAMA_EMBEDDING_MODEL

    # Pre-flight checks
    if not check_model_available(model):
        return {
            "success": False,
            "error": f"Model '{model}' not available in Ollama. Run: ollama pull {model}",
        }

    results = {
        "model": model,
        "dry_run": dry_run,
        "collections_deleted": [],
        "collections_reindexed": {},
    }

    try:
        with WeaviateConnection() as client:
            # Step 1: Delete all collections
            for coll_name in ALL_COLLECTIONS:
                if client.collections.exists(coll_name):
                    if dry_run:
                        logger.info("[DRY RUN] Would delete collection: %s", coll_name)
                    else:
                        logger.info("Deleting collection: %s", coll_name)
                        client.collections.delete(coll_name)
                    results["collections_deleted"].append(coll_name)

            if dry_run:
                logger.info("[DRY RUN] Would re-ingest all data with model: %s", model)
                results["success"] = True
                return results

            # Step 2: Re-ingest Documentation
            logger.info("Re-indexing Documentation collection...")
            doc_stats = ingest_documentation(client, force_reindex=True)
            results["collections_reindexed"]["Documentation"] = doc_stats

            # Step 3: Re-ingest CodeEntity
            logger.info("Re-indexing CodeEntity collection...")
            code_stats = ingest_code_entities(client, force_reindex=True)
            results["collections_reindexed"]["CodeEntity"] = code_stats

            # Step 4: Re-ingest DrupalAPI (if we have data)
            # Note: Drupal data comes from scraping, so we just recreate the collection
            # and note that the scraper needs to be re-run
            logger.info("Creating empty DrupalAPIEntity collection (requires re-scraping)...")
            try:
                from .drupal_api_schema import create_drupal_api_collection
                create_drupal_api_collection(client, force_reindex=True)
                results["collections_reindexed"]["DrupalAPIEntity"] = {
                    "note": "Collection created. Run scraper to re-populate.",
                    "command": "python -m api_gateway.services.drupal_scraper scrape",
                }
            except ImportError as e:
                logger.error("Could not import drupal_api_schema module: %s", e)
                results["collections_reindexed"]["DrupalAPIEntity"] = {
                    "error": f"Import error: {e}"
                }
            except Exception as e:
                logger.warning("Could not create DrupalAPIEntity collection: %s", e)
                results["collections_reindexed"]["DrupalAPIEntity"] = {"error": str(e)}

            results["success"] = True

    except Exception as e:
        logger.exception("Migration failed")
        results["success"] = False
        results["error"] = str(e)

    return results


def _configure_logging(verbose: bool) -> None:
    """
    Configure logging level based on verbosity flag.

    Args:
        verbose: If True, enable DEBUG logging for all loggers;
                 otherwise use settings.LOG_LEVEL
    """
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(level)


def main(argv: Optional[List[str]] = None) -> None:
    """
    CLI entry point for embedding model migration.

    Args:
        argv: Optional command line arguments (for testing)

    Raises:
        SystemExit: On error or when model is not available
    """
    parser = argparse.ArgumentParser(
        description="Embedding model migration for Weaviate collections.",
        epilog="""
Examples:
  # Check current status
  python -m api_gateway.services.migrate_embeddings check

  # Preview migration (no changes)
  python -m api_gateway.services.migrate_embeddings migrate --dry-run

  # Perform full migration
  python -m api_gateway.services.migrate_embeddings migrate
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        choices=["check", "migrate"],
        help="check: Show current status. migrate: Delete and re-index all collections.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="For migrate: show what would be done without making changes.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.command == "check":
        status = check_status()
        logger.info("Embedding migration status: %s", status)
        print("\n=== Embedding Migration Status ===\n")
        print(f"Configured model:    {status['configured_model']}")
        print(f"Model available:     {'[OK] Yes' if status['model_available'] else '[X] No'}")
        print(f"Embedding dimensions: {status['model_dimensions'] or 'Unknown'}")
        print("\nCollections:")
        for coll, count in status["collections"].items():
            if count is None:
                print(f"  {coll}: Does not exist")
            else:
                print(f"  {coll}: {count} objects")

        if not status["model_available"]:
            logger.error("Model '%s' is not available in Ollama", status['configured_model'])
            print(f"\n[!] Model not available. Run: ollama pull {status['configured_model']}")
            sys.exit(1)

    elif args.command == "migrate":
        print("\n=== Embedding Migration ===\n")

        if not args.dry_run:
            logger.warning("About to DELETE all Weaviate collections and re-ingest data")
            print("[!] WARNING: This will DELETE all Weaviate collections and re-ingest data.")
            print("   - Documentation: Will be re-indexed from markdown files")
            print("   - CodeEntity: Will be re-indexed from source code")
            print("   - DrupalAPIEntity: Collection recreated (requires re-running scraper)")
            print("")
            try:
                confirm = input("Type 'yes' to proceed: ")
            except (EOFError, KeyboardInterrupt):
                print("\nMigration cancelled.")
                logger.info("Migration cancelled by user")
                sys.exit(0)

            if confirm.lower() != "yes":
                print("Migration cancelled.")
                logger.info("Migration cancelled by user (incorrect confirmation)")
                sys.exit(0)

        results = migrate(dry_run=args.dry_run)

        if args.dry_run:
            print("\n[DRY RUN] Migration preview:")
            print(f"  Model: {results['model']}")
            print(f"  Would delete: {', '.join(results['collections_deleted']) or 'None'}")
            print("  Would re-ingest: Documentation, CodeEntity")
            print("  Would create: DrupalAPIEntity (empty)")
        else:
            if results.get("success"):
                print("\n[OK] Migration completed successfully!")
                print(f"\nDeleted: {', '.join(results['collections_deleted'])}")
                print("\nRe-indexed:")
                for coll, stats in results.get("collections_reindexed", {}).items():
                    if isinstance(stats, dict) and "files" in stats:
                        print(f"  {coll}: {stats.get('chunks', 0)} chunks from {stats.get('files', 0)} files")
                    elif isinstance(stats, dict) and "entities" in stats:
                        print(f"  {coll}: {stats.get('entities', 0)} entities")
                    else:
                        print(f"  {coll}: {stats}")

                # Remind about Drupal scraper
                print("\n[!] Note: DrupalAPIEntity collection is empty.")
                print("   To re-populate, run: python -m api_gateway.services.drupal_scraper scrape")
            else:
                print(f"\n[FAIL] Migration failed: {results.get('error', 'Unknown error')}")
                sys.exit(1)


if __name__ == "__main__":
    main()
