"""
Unified Documentation Scraper Runner.

Runs all documentation scrapers sequentially or in parallel.
Tracks overall progress and reports status for all collections.

Usage:
    # Run all scrapers sequentially
    python -m api_gateway.services.run_all_scrapers scrape

    # Run specific scrapers
    python -m api_gateway.services.run_all_scrapers scrape --scrapers pytorch tensorflow

    # Check status of all collections
    python -m api_gateway.services.run_all_scrapers status

    # Dry run (parse but don't store)
    python -m api_gateway.services.run_all_scrapers scrape --dry-run --limit 10

    # Clean all collections
    python -m api_gateway.services.run_all_scrapers clean
"""

import argparse
import time
from datetime import datetime

from api_gateway.services.image_lib_scrapers import (
    OpenCVDocScraper,
    PillowDocScraper,
)

# Import all scrapers
from api_gateway.services.pytorch_docs_scraper import PyTorchDocScraper
from api_gateway.services.scraping_lib_scrapers import (
    BeautifulSoupDocScraper,
    ScrapyDocScraper,
)
from api_gateway.services.sklearn_docs_scraper import ScikitLearnDocScraper
from api_gateway.services.tensorflow_docs_scraper import TensorFlowDocScraper
from api_gateway.services.vscode_docs_scraper import VSCodeDocScraper
from api_gateway.services.weaviate_connection import WeaviateConnection
from api_gateway.services.web_framework_scrapers import (
    DjangoDocScraper,
    FastAPIDocScraper,
    FlaskDocScraper,
)
from api_gateway.utils.logger import get_logger

logger = get_logger(__name__)

# All available scrapers
ALL_SCRAPERS = {
    # AI/ML
    "pytorch": PyTorchDocScraper,
    "tensorflow": TensorFlowDocScraper,
    "sklearn": ScikitLearnDocScraper,
    # Web frameworks
    "django": DjangoDocScraper,
    "flask": FlaskDocScraper,
    "fastapi": FastAPIDocScraper,
    # Image processing
    "pillow": PillowDocScraper,
    "opencv": OpenCVDocScraper,
    # Web scraping
    "beautifulsoup": BeautifulSoupDocScraper,
    "scrapy": ScrapyDocScraper,
    # IDEs/Editors
    "vscode": VSCodeDocScraper,
}

# Grouped by category for display
SCRAPER_CATEGORIES = {
    "AI/ML": ["pytorch", "tensorflow", "sklearn"],
    "Web Frameworks": ["django", "flask", "fastapi"],
    "Image Processing": ["pillow", "opencv"],
    "Web Scraping": ["beautifulsoup", "scrapy"],
    "IDEs/Editors": ["vscode"],
}


def run_scraper(
    name: str,
    scraper_class,
    max_pages: int = 0,
    resume: bool = True,
    dry_run: bool = False,
) -> dict:
    """Run a single scraper and return stats."""
    logger.info("=" * 60)
    logger.info("  Scraping: %s", name.upper())
    logger.info("  Started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    start_time = time.time()
    # Create scraper with its own defaults, then override max_pages if needed
    scraper = scraper_class()
    if max_pages > 0:
        scraper.config.max_pages = max_pages

    try:
        stats = scraper.scrape(resume=resume, dry_run=dry_run)
        elapsed = time.time() - start_time

        stats["elapsed_seconds"] = round(elapsed, 1)
        stats["status"] = "success"

        logger.info("  Completed in %.1fs", elapsed)
        logger.info("  Pages scraped: %d", stats.get("pages_scraped", 0))
        logger.info("  Pages skipped: %d", stats.get("pages_skipped", 0))
        logger.info("  Pages failed: %d", stats.get("pages_failed", 0))

        return stats

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("Scraper %s failed: %s", name, e)
        logger.error("  FAILED after %.1fs: %s", elapsed, e)
        return {
            "status": "failed",
            "error": str(e),
            "elapsed_seconds": round(elapsed, 1),
        }


def get_all_status() -> dict:
    """Get status of all collections."""
    status = {}

    with WeaviateConnection() as client:
        for name, scraper_class in ALL_SCRAPERS.items():
            # Create scraper with defaults to get collection_name
            scraper = scraper_class()
            collection_name = scraper.collection_name

            if client.collections.exists(collection_name):
                collection = client.collections.get(collection_name)
                response = collection.aggregate.over_all(total_count=True)
                status[name] = {
                    "collection": collection_name,
                    "count": response.total_count,
                    "exists": True,
                }
            else:
                status[name] = {
                    "collection": collection_name,
                    "count": 0,
                    "exists": False,
                }

    return status


def print_status():
    """Print status of all collections in a formatted table."""
    status = get_all_status()

    logger.info("=" * 60)
    logger.info("  DOCUMENTATION COLLECTIONS STATUS")
    logger.info("=" * 60)

    total_docs = 0

    for category, scrapers in SCRAPER_CATEGORIES.items():
        logger.info("  %s:", category)
        for name in scrapers:
            info = status.get(name, {})
            count = info.get("count", 0)
            exists = info.get("exists", False)

            if exists:
                logger.info("    %s %6d docs", name.ljust(15), count)
                total_docs += count
            else:
                logger.info("    %s %s", name.ljust(15), "(not created)")

    logger.info("  %s %6d docs", "TOTAL".ljust(15), total_docs)
    logger.info("=" * 60)


def clean_all():
    """Delete all collections."""
    logger.info("Deleting all documentation collections...")

    with WeaviateConnection() as client:
        for _name, scraper_class in ALL_SCRAPERS.items():
            # Create scraper with defaults to get collection_name
            scraper = scraper_class()
            collection_name = scraper.collection_name

            if client.collections.exists(collection_name):
                client.collections.delete(collection_name)
                logger.info("  Deleted: %s", collection_name)
            else:
                logger.info("  Skipped: %s (does not exist)", collection_name)

    logger.info("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Unified Documentation Scraper Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all scrapers
  python -m api_gateway.services.run_all_scrapers scrape

  # Run specific scrapers
  python -m api_gateway.services.run_all_scrapers scrape --scrapers pytorch tensorflow

  # Check status
  python -m api_gateway.services.run_all_scrapers status

  # Dry run with limit
  python -m api_gateway.services.run_all_scrapers scrape --dry-run --limit 10
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Run documentation scrapers")
    scrape_parser.add_argument(
        "--scrapers",
        nargs="+",
        choices=list(ALL_SCRAPERS.keys()),
        help="Specific scrapers to run (default: all)",
    )
    scrape_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum pages per scraper (0=unlimited)",
    )
    scrape_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse pages without storing to database",
    )
    scrape_parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh, ignore checkpoints",
    )

    # Status command
    subparsers.add_parser("status", help="Show status of all collections")

    # Clean command
    subparsers.add_parser("clean", help="Delete all collections")

    # List command
    subparsers.add_parser("list", help="List available scrapers")

    args = parser.parse_args()

    if args.command == "status":
        print_status()

    elif args.command == "clean":
        confirm = input("Delete ALL documentation collections? (yes/no): ")
        if confirm.lower() == "yes":
            clean_all()
        else:
            logger.info("Cancelled.")

    elif args.command == "list":
        logger.info("Available scrapers:")
        for category, scrapers in SCRAPER_CATEGORIES.items():
            logger.info("  %s:", category)
            for name in scrapers:
                logger.info("    - %s", name)

    elif args.command == "scrape":
        # Determine which scrapers to run
        scrapers_to_run = args.scrapers or list(ALL_SCRAPERS.keys())

        logger.info("#" * 60)
        logger.info("  DOCUMENTATION SCRAPER RUNNER")
        logger.info("  Started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("  Scrapers: %s", ", ".join(scrapers_to_run))
        logger.info("  Limit: %s", args.limit or "unlimited")
        logger.info("  Dry run: %s", args.dry_run)
        logger.info("#" * 60)

        # Run scrapers
        all_stats = {}
        total_start = time.time()

        for name in scrapers_to_run:
            scraper_class = ALL_SCRAPERS[name]
            stats = run_scraper(
                name=name,
                scraper_class=scraper_class,
                max_pages=args.limit,
                resume=not args.no_resume,
                dry_run=args.dry_run,
            )
            all_stats[name] = stats

        total_elapsed = time.time() - total_start

        # Log summary
        logger.info("#" * 60)
        logger.info("  FINAL SUMMARY")
        logger.info("#" * 60)
        logger.info("  Total time: %.1fs", total_elapsed)
        logger.info("  Results:")

        total_scraped = 0
        total_failed = 0
        for name, stats in all_stats.items():
            status = stats.get("status", "unknown")
            scraped = stats.get("pages_scraped", 0)
            elapsed = stats.get("elapsed_seconds", 0)

            if status == "success":
                logger.info("    %s SUCCESS  %5d pages  (%.1fs)", name.ljust(15), scraped, elapsed)
                total_scraped += scraped
            else:
                logger.info(
                    "    %s FAILED   %s", name.ljust(15), stats.get("error", "unknown")[:30]
                )
                total_failed += 1

        logger.info("  Total pages scraped: %d", total_scraped)
        if total_failed > 0:
            logger.info("  Scrapers failed: %d", total_failed)

        # Show final status
        if not args.dry_run:
            print_status()


if __name__ == "__main__":
    main()
