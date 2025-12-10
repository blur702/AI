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
import sys
import time
from datetime import datetime

from api_gateway.services.weaviate_connection import WeaviateConnection
from api_gateway.services.base_doc_scraper import ScraperConfig
from api_gateway.utils.logger import get_logger

# Import all scrapers
from api_gateway.services.pytorch_docs_scraper import PyTorchDocScraper
from api_gateway.services.tensorflow_docs_scraper import TensorFlowDocScraper
from api_gateway.services.sklearn_docs_scraper import ScikitLearnDocScraper
from api_gateway.services.web_framework_scrapers import (
    DjangoDocScraper,
    FlaskDocScraper,
    FastAPIDocScraper,
)
from api_gateway.services.image_lib_scrapers import (
    PillowDocScraper,
    OpenCVDocScraper,
)
from api_gateway.services.scraping_lib_scrapers import (
    BeautifulSoupDocScraper,
    ScrapyDocScraper,
)

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
}

# Grouped by category for display
SCRAPER_CATEGORIES = {
    "AI/ML": ["pytorch", "tensorflow", "sklearn"],
    "Web Frameworks": ["django", "flask", "fastapi"],
    "Image Processing": ["pillow", "opencv"],
    "Web Scraping": ["beautifulsoup", "scrapy"],
}


def run_scraper(
    name: str,
    scraper_class,
    config: ScraperConfig,
    resume: bool = True,
    dry_run: bool = False,
) -> dict:
    """Run a single scraper and return stats."""
    print(f"\n{'='*60}")
    print(f"  Scraping: {name.upper()}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    start_time = time.time()
    scraper = scraper_class(config=config)

    try:
        stats = scraper.scrape(resume=resume, dry_run=dry_run)
        elapsed = time.time() - start_time

        stats["elapsed_seconds"] = round(elapsed, 1)
        stats["status"] = "success"

        print(f"\n  Completed in {elapsed:.1f}s")
        print(f"  Pages scraped: {stats.get('pages_scraped', 0)}")
        print(f"  Pages skipped: {stats.get('pages_skipped', 0)}")
        print(f"  Pages failed: {stats.get('pages_failed', 0)}")

        return stats

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("Scraper %s failed: %s", name, e)
        print(f"\n  FAILED after {elapsed:.1f}s: {e}")
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
            scraper = scraper_class(ScraperConfig())
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

    print("\n" + "="*60)
    print("  DOCUMENTATION COLLECTIONS STATUS")
    print("="*60)

    total_docs = 0

    for category, scrapers in SCRAPER_CATEGORIES.items():
        print(f"\n  {category}:")
        for name in scrapers:
            info = status.get(name, {})
            count = info.get("count", 0)
            exists = info.get("exists", False)

            if exists:
                print(f"    {name:15} {count:>6} docs")
                total_docs += count
            else:
                print(f"    {name:15} {'(not created)':>12}")

    print(f"\n  {'TOTAL':15} {total_docs:>6} docs")
    print("="*60)


def clean_all():
    """Delete all collections."""
    print("\nDeleting all documentation collections...")

    with WeaviateConnection() as client:
        for name, scraper_class in ALL_SCRAPERS.items():
            scraper = scraper_class(ScraperConfig())
            collection_name = scraper.collection_name

            if client.collections.exists(collection_name):
                client.collections.delete(collection_name)
                print(f"  Deleted: {collection_name}")
            else:
                print(f"  Skipped: {collection_name} (does not exist)")

    print("\nDone!")


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
            print("Cancelled.")

    elif args.command == "list":
        print("\nAvailable scrapers:")
        for category, scrapers in SCRAPER_CATEGORIES.items():
            print(f"\n  {category}:")
            for name in scrapers:
                print(f"    - {name}")

    elif args.command == "scrape":
        # Determine which scrapers to run
        scrapers_to_run = args.scrapers or list(ALL_SCRAPERS.keys())

        print(f"\n{'#'*60}")
        print(f"  DOCUMENTATION SCRAPER RUNNER")
        print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Scrapers: {', '.join(scrapers_to_run)}")
        print(f"  Limit: {args.limit or 'unlimited'}")
        print(f"  Dry run: {args.dry_run}")
        print(f"{'#'*60}")

        # Build config
        config = ScraperConfig(max_pages=args.limit) if args.limit > 0 else None

        # Run scrapers
        all_stats = {}
        total_start = time.time()

        for name in scrapers_to_run:
            scraper_class = ALL_SCRAPERS[name]
            stats = run_scraper(
                name=name,
                scraper_class=scraper_class,
                config=config or ScraperConfig(),
                resume=not args.no_resume,
                dry_run=args.dry_run,
            )
            all_stats[name] = stats

        total_elapsed = time.time() - total_start

        # Print summary
        print(f"\n{'#'*60}")
        print(f"  FINAL SUMMARY")
        print(f"{'#'*60}")
        print(f"\n  Total time: {total_elapsed:.1f}s")
        print(f"\n  Results:")

        total_scraped = 0
        total_failed = 0
        for name, stats in all_stats.items():
            status = stats.get("status", "unknown")
            scraped = stats.get("pages_scraped", 0)
            elapsed = stats.get("elapsed_seconds", 0)

            if status == "success":
                print(f"    {name:15} SUCCESS  {scraped:>5} pages  ({elapsed:.1f}s)")
                total_scraped += scraped
            else:
                print(f"    {name:15} FAILED   {stats.get('error', 'unknown')[:30]}")
                total_failed += 1

        print(f"\n  Total pages scraped: {total_scraped}")
        if total_failed > 0:
            print(f"  Scrapers failed: {total_failed}")

        # Show final status
        if not args.dry_run:
            print_status()


if __name__ == "__main__":
    main()
