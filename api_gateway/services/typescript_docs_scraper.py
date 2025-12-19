"""
TypeScript Documentation Scraper.

Scrapes documentation from the official TypeScript website:
- typescriptlang.org/docs/handbook
- typescriptlang.org/docs/handbook/2 (updated handbook)
- typescriptlang.org/docs/handbook/declaration-files
- typescriptlang.org/docs/handbook/release-notes
- typescriptlang.org/tsconfig

Usage:
    # Scrape all TypeScript docs
    python -m api_gateway.services.typescript_docs_scraper scrape

    # Dry run (parse only, no storage)
    python -m api_gateway.services.typescript_docs_scraper scrape --dry-run

    # Limit pages
    python -m api_gateway.services.typescript_docs_scraper scrape --limit 100

    # Check status
    python -m api_gateway.services.typescript_docs_scraper status

    # Force reindex
    python -m api_gateway.services.typescript_docs_scraper reindex
"""

from __future__ import annotations

import argparse
import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    import weaviate

from ..utils.logger import get_logger
from .base_doc_scraper import BaseDocScraper, DocPage, ScraperConfig
from .typescript_docs_schema import (
    TYPESCRIPT_DOCS_COLLECTION_NAME,
    create_typescript_docs_collection,
    get_typescript_docs_stats,
)
from .weaviate_connection import WeaviateConnection

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# TypeScript Documentation Sections
# -----------------------------------------------------------------------------

TYPESCRIPT_SECTIONS = {
    "handbook": {
        "name": "Handbook",
        "seed_urls": [
            "https://www.typescriptlang.org/docs/handbook/intro.html",
            "https://www.typescriptlang.org/docs/handbook/2/basic-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/everyday-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/narrowing.html",
            "https://www.typescriptlang.org/docs/handbook/2/functions.html",
            "https://www.typescriptlang.org/docs/handbook/2/objects.html",
            "https://www.typescriptlang.org/docs/handbook/2/types-from-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/generics.html",
            "https://www.typescriptlang.org/docs/handbook/2/keyof-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/typeof-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/indexed-access-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/conditional-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/mapped-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/template-literal-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/classes.html",
            "https://www.typescriptlang.org/docs/handbook/2/modules.html",
        ],
        "url_patterns": [
            r"/docs/handbook/",
        ],
    },
    "reference": {
        "name": "Reference",
        "seed_urls": [
            "https://www.typescriptlang.org/docs/handbook/utility-types.html",
            "https://www.typescriptlang.org/docs/handbook/decorators.html",
            "https://www.typescriptlang.org/docs/handbook/declaration-merging.html",
            "https://www.typescriptlang.org/docs/handbook/enums.html",
            "https://www.typescriptlang.org/docs/handbook/iterators-and-generators.html",
            "https://www.typescriptlang.org/docs/handbook/jsx.html",
            "https://www.typescriptlang.org/docs/handbook/mixins.html",
            "https://www.typescriptlang.org/docs/handbook/namespaces.html",
            "https://www.typescriptlang.org/docs/handbook/namespaces-and-modules.html",
            "https://www.typescriptlang.org/docs/handbook/symbols.html",
            "https://www.typescriptlang.org/docs/handbook/triple-slash-directives.html",
            "https://www.typescriptlang.org/docs/handbook/type-compatibility.html",
            "https://www.typescriptlang.org/docs/handbook/type-inference.html",
            "https://www.typescriptlang.org/docs/handbook/variable-declarations.html",
        ],
        "url_patterns": [
            r"/docs/handbook/utility-types",
            r"/docs/handbook/decorators",
            r"/docs/handbook/declaration-merging",
            r"/docs/handbook/enums",
            r"/docs/handbook/iterators",
            r"/docs/handbook/jsx",
            r"/docs/handbook/mixins",
            r"/docs/handbook/namespaces",
            r"/docs/handbook/symbols",
            r"/docs/handbook/triple-slash",
            r"/docs/handbook/type-compatibility",
            r"/docs/handbook/type-inference",
            r"/docs/handbook/variable-declarations",
        ],
    },
    "declaration-files": {
        "name": "Declaration Files",
        "seed_urls": [
            "https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html",
            "https://www.typescriptlang.org/docs/handbook/declaration-files/by-example.html",
            "https://www.typescriptlang.org/docs/handbook/declaration-files/library-structures.html",
            "https://www.typescriptlang.org/docs/handbook/declaration-files/templates.html",
            "https://www.typescriptlang.org/docs/handbook/declaration-files/do-s-and-don-ts.html",
            "https://www.typescriptlang.org/docs/handbook/declaration-files/deep-dive.html",
            "https://www.typescriptlang.org/docs/handbook/declaration-files/publishing.html",
            "https://www.typescriptlang.org/docs/handbook/declaration-files/consumption.html",
        ],
        "url_patterns": [
            r"/docs/handbook/declaration-files/",
        ],
    },
    "project-config": {
        "name": "Project Configuration",
        "seed_urls": [
            "https://www.typescriptlang.org/tsconfig",
            "https://www.typescriptlang.org/docs/handbook/tsconfig-json.html",
            "https://www.typescriptlang.org/docs/handbook/compiler-options.html",
            "https://www.typescriptlang.org/docs/handbook/project-references.html",
            "https://www.typescriptlang.org/docs/handbook/integrating-with-build-tools.html",
            "https://www.typescriptlang.org/docs/handbook/configuring-watch.html",
            "https://www.typescriptlang.org/docs/handbook/nightly-builds.html",
        ],
        "url_patterns": [
            r"/tsconfig",
            r"/docs/handbook/tsconfig",
            r"/docs/handbook/compiler-options",
            r"/docs/handbook/project-references",
            r"/docs/handbook/integrating-with-build",
            r"/docs/handbook/configuring-watch",
            r"/docs/handbook/nightly-builds",
        ],
    },
}


class TypeScriptDocsScraper(BaseDocScraper):
    """
    Scraper for TypeScript documentation.

    Supports multiple documentation sections with section-specific URL patterns
    and parsing logic.
    """

    def __init__(
        self,
        config: ScraperConfig | None = None,
    ):
        """
        Initialize the TypeScript docs scraper.

        Args:
            config: Scraper configuration
        """
        # Use conservative rate limiting
        if config is None:
            config = ScraperConfig(
                min_delay=1.5,
                max_delay=4.0,
                batch_size=8,
                batch_pause_min=10.0,
                batch_pause_max=20.0,
                max_depth=8,
            )

        super().__init__(
            name="typescript_docs",
            base_url="https://www.typescriptlang.org",
            collection_name=TYPESCRIPT_DOCS_COLLECTION_NAME,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        """Get seed URLs for all TypeScript documentation sections."""
        urls = []
        for section_key, section in TYPESCRIPT_SECTIONS.items():
            urls.extend(section["seed_urls"])
            logger.info("Added %d seed URLs for %s", len(section["seed_urls"]), section["name"])
        return urls

    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be scraped based on section patterns."""
        parsed = urlparse(url)

        # Must be typescriptlang.org
        if parsed.netloc not in ("www.typescriptlang.org", "typescriptlang.org"):
            return False

        # Check if URL matches any section pattern
        for section in TYPESCRIPT_SECTIONS.values():
            for pattern in section["url_patterns"]:
                if re.search(pattern, url):
                    return True

        # Also allow general handbook pages
        if "/docs/handbook/" in url:
            return True

        return False

    def _detect_section(self, url: str) -> str:
        """Detect which documentation section a URL belongs to."""
        url_lower = url.lower()

        if "/declaration-files/" in url_lower:
            return "declaration-files"
        elif "/tsconfig" in url_lower or "compiler-options" in url_lower:
            return "project-config"
        elif "/docs/handbook/2/" in url_lower:
            return "handbook"
        elif any(
            term in url_lower
            for term in [
                "utility-types",
                "decorators",
                "enums",
                "jsx",
                "mixins",
                "namespaces",
                "symbols",
            ]
        ):
            return "reference"
        else:
            return "handbook"

    def _detect_subsection(self, url: str, title: str) -> str:  # noqa: ARG002
        """Detect more specific subsection based on URL and title."""
        url_lower = url.lower()

        # Type manipulation
        if any(
            term in url_lower
            for term in [
                "generics",
                "keyof",
                "typeof",
                "indexed-access",
                "conditional-types",
                "mapped-types",
                "template-literal",
            ]
        ):
            return "type-manipulation"

        # Classes and objects
        if any(term in url_lower for term in ["classes", "objects"]):
            return "classes-objects"

        # Functions
        if "functions" in url_lower:
            return "functions"

        # Modules
        if "modules" in url_lower or "namespaces" in url_lower:
            return "modules"

        # Types
        if any(term in url_lower for term in ["types", "narrowing", "everyday"]):
            return "types"

        # Configuration
        if any(term in url_lower for term in ["tsconfig", "compiler", "project-references"]):
            return "configuration"

        return "general"

    def parse_page(self, url: str, html: str) -> DocPage | None:
        """Parse a TypeScript documentation page."""
        soup = BeautifulSoup(html, "html.parser")

        # Detect section
        section = self._detect_section(url)

        # Remove navigation, footer, etc.
        for selector in [
            "nav",
            "footer",
            "header",
            "aside",
            "[role='navigation']",
            "[role='banner']",
            ".sidebar",
            ".toc",
            ".nav",
            ".footer",
            ".header",
            ".site-nav",
            ".page-nav",
            ".doc-nav",
            "script",
            "style",
            "noscript",
            ".playground-button",  # TypeScript playground buttons
        ]:
            for elem in soup.select(selector):
                elem.decompose()

        # Get title
        title = ""
        title_elem = soup.find("h1")
        if title_elem:
            title = title_elem.get_text(strip=True)
        elif soup.title:
            title = soup.title.get_text(strip=True)
            # Clean up title
            if " - " in title:
                title = title.split(" - ")[0].strip()

        if not title:
            return None

        # Detect subsection
        subsection = self._detect_subsection(url, title)

        # Get main content
        main_content = None
        for selector in [
            "main",
            "article",
            "[role='main']",
            ".content",
            ".docs-content",
            ".markdown",
            "#handbook-content",
        ]:
            main_content = soup.select_one(selector)
            if main_content:
                break

        if not main_content:
            main_content = soup.body

        if not main_content:
            return None

        # Extract text content
        content = main_content.get_text(separator="\n", strip=True)
        if len(content) < 100:
            return None  # Skip pages with too little content

        # Extract code examples
        code_examples = []
        for code in main_content.select("pre code, pre"):
            code_text = code.get_text(strip=True)
            if code_text and len(code_text) > 20:
                code_examples.append(code_text[:1000])

        # Get breadcrumb
        breadcrumb = ""
        breadcrumb_elem = soup.select_one("[aria-label='breadcrumb'], .breadcrumb, .breadcrumbs")
        if breadcrumb_elem:
            breadcrumb = " > ".join(
                [li.get_text(strip=True) for li in breadcrumb_elem.select("li, a")]
            )

        return DocPage(
            url=url,
            title=title,
            content=content,
            section=section,
            package=subsection,  # Using package field for subsection
            breadcrumb=breadcrumb,
            code_examples=code_examples,
        )

    def create_collection(self, client: weaviate.WeaviateClient) -> None:
        """Create the TypeScriptDocs collection."""
        create_typescript_docs_collection(client)


def scrape_typescript_docs(
    max_pages: int = 0,
    dry_run: bool = False,
    resume: bool = True,
) -> dict:
    """
    Scrape TypeScript documentation.

    Args:
        max_pages: Maximum pages to scrape (0 = unlimited)
        dry_run: Parse only, don't store
        resume: Resume from checkpoint

    Returns:
        Statistics dict
    """
    config = ScraperConfig(
        min_delay=1.5,
        max_delay=4.0,
        batch_size=8,
        batch_pause_min=10.0,
        batch_pause_max=20.0,
        max_pages=max_pages,
    )

    scraper = TypeScriptDocsScraper(config=config)
    return scraper.scrape(resume=resume, dry_run=dry_run)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Scrape TypeScript documentation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape documentation")
    scrape_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum pages to scrape (default: unlimited)",
    )
    scrape_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse only, don't store",
    )
    scrape_parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh, don't resume from checkpoint",
    )

    # status command
    subparsers.add_parser("status", help="Show collection status")

    # reindex command
    subparsers.add_parser("reindex", help="Force reindex")

    args = parser.parse_args()

    if args.command == "scrape":
        logger.info("Starting TypeScript docs scrape")

        stats = scrape_typescript_docs(
            max_pages=args.limit,
            dry_run=args.dry_run,
            resume=not args.no_resume,
        )

        print("\n" + "=" * 50)
        print("TYPESCRIPT DOCS SCRAPE SUMMARY")
        print("=" * 50)
        for key, value in stats.items():
            print(f"  {key}: {value}")
        print("=" * 50)

    elif args.command == "status":
        with WeaviateConnection() as client:
            stats = get_typescript_docs_stats(client)

            print("\n" + "=" * 50)
            print("TYPESCRIPT DOCS COLLECTION STATUS")
            print("=" * 50)
            print(f"Exists: {stats['exists']}")
            print(f"Total objects: {stats['object_count']}")
            if stats["section_counts"]:
                print("\nBy section:")
                for section, count in sorted(stats["section_counts"].items()):
                    print(f"  {section}: {count}")
            print("=" * 50)

    elif args.command == "reindex":
        with WeaviateConnection() as client:
            create_typescript_docs_collection(client, force_reindex=True)

        logger.info("Reindexing TypeScript docs...")
        stats = scrape_typescript_docs(resume=False)

        print("\n" + "=" * 50)
        print("REINDEX COMPLETE")
        print("=" * 50)
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
