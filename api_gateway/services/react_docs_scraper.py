"""
React Ecosystem Documentation Scraper.

Scrapes documentation from React and popular React ecosystem libraries:

- React (react.dev)
- React Router (reactrouter.com)
- Redux (redux.js.org)
- Redux Toolkit (redux-toolkit.js.org)
- TanStack Query (tanstack.com/query)
- Next.js (nextjs.org/docs)
- Zustand (docs.pmnd.rs/zustand)
- React Hook Form (react-hook-form.com)

Usage:
    # Scrape all React ecosystem docs
    python -m api_gateway.services.react_docs_scraper scrape

    # Scrape specific library
    python -m api_gateway.services.react_docs_scraper scrape --library react
    python -m api_gateway.services.react_docs_scraper scrape --library nextjs

    # Dry run (parse only, no storage)
    python -m api_gateway.services.react_docs_scraper scrape --dry-run

    # Limit pages per library
    python -m api_gateway.services.react_docs_scraper scrape --limit 100

    # Check status
    python -m api_gateway.services.react_docs_scraper status

    # Force reindex
    python -m api_gateway.services.react_docs_scraper reindex
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
from .react_docs_schema import (
    REACT_ECOSYSTEM_COLLECTION_NAME,
    create_react_ecosystem_collection,
    get_react_ecosystem_stats,
)
from .weaviate_connection import WeaviateConnection

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Library Configurations
# -----------------------------------------------------------------------------

REACT_LIBRARIES = {
    "react": {
        "name": "React",
        "base_url": "https://react.dev",
        "seed_urls": [
            "https://react.dev/learn",
            "https://react.dev/reference/react",
            "https://react.dev/reference/react-dom",
        ],
        "url_patterns": [
            r"/learn/",
            r"/reference/",
        ],
    },
    "react-router": {
        "name": "React Router",
        "base_url": "https://reactrouter.com",
        "seed_urls": [
            "https://reactrouter.com/en/main",
            "https://reactrouter.com/en/main/start/tutorial",
            "https://reactrouter.com/en/main/router-components/browser-router",
        ],
        "url_patterns": [
            r"/en/main/",
        ],
    },
    "redux": {
        "name": "Redux",
        "base_url": "https://redux.js.org",
        "seed_urls": [
            "https://redux.js.org/introduction/getting-started",
            "https://redux.js.org/tutorials/essentials/part-1-overview-concepts",
            "https://redux.js.org/api/api-reference",
        ],
        "url_patterns": [
            r"/introduction/",
            r"/tutorials/",
            r"/api/",
            r"/style-guide/",
            r"/usage/",
            r"/faq/",
        ],
    },
    "redux-toolkit": {
        "name": "Redux Toolkit",
        "base_url": "https://redux-toolkit.js.org",
        "seed_urls": [
            "https://redux-toolkit.js.org/introduction/getting-started",
            "https://redux-toolkit.js.org/tutorials/quick-start",
            "https://redux-toolkit.js.org/api/configureStore",
        ],
        "url_patterns": [
            r"/introduction/",
            r"/tutorials/",
            r"/api/",
            r"/usage/",
            r"/rtk-query/",
        ],
    },
    "tanstack-query": {
        "name": "TanStack Query",
        "base_url": "https://tanstack.com",
        "seed_urls": [
            "https://tanstack.com/query/latest/docs/framework/react/overview",
            "https://tanstack.com/query/latest/docs/framework/react/quick-start",
            "https://tanstack.com/query/latest/docs/framework/react/guides/queries",
        ],
        "url_patterns": [
            r"/query/latest/docs/",
        ],
    },
    "nextjs": {
        "name": "Next.js",
        "base_url": "https://nextjs.org",
        "seed_urls": [
            "https://nextjs.org/docs",
            "https://nextjs.org/docs/getting-started/installation",
            "https://nextjs.org/docs/app/building-your-application/routing",
            "https://nextjs.org/docs/app/api-reference",
        ],
        "url_patterns": [
            r"/docs/",
        ],
    },
    "zustand": {
        "name": "Zustand",
        "base_url": "https://docs.pmnd.rs",
        "seed_urls": [
            "https://docs.pmnd.rs/zustand/getting-started/introduction",
            "https://docs.pmnd.rs/zustand/guides/updating-state",
            "https://docs.pmnd.rs/zustand/recipes/recipes",
        ],
        "url_patterns": [
            r"/zustand/",
        ],
    },
    "react-hook-form": {
        "name": "React Hook Form",
        "base_url": "https://react-hook-form.com",
        "seed_urls": [
            "https://react-hook-form.com/get-started",
            "https://react-hook-form.com/docs/useform",
            "https://react-hook-form.com/docs/useformcontext",
        ],
        "url_patterns": [
            r"/get-started",
            r"/docs/",
            r"/faqs",
            r"/ts",
            r"/advanced-usage",
        ],
    },
}


class ReactEcosystemScraper(BaseDocScraper):
    """
    Scraper for React ecosystem documentation.

    Supports multiple React libraries with library-specific URL patterns
    and parsing logic.
    """

    def __init__(
        self,
        library: str | None = None,
        config: ScraperConfig | None = None,
    ):
        """
        Initialize the React ecosystem scraper.

        Args:
            library: Specific library to scrape (None = all)
            config: Scraper configuration
        """
        self.library = library
        self._current_library: str | None = None

        # Use more conservative rate limiting for React sites
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
            name="react_ecosystem",
            base_url="https://react.dev",  # Default, will be overridden
            collection_name=REACT_ECOSYSTEM_COLLECTION_NAME,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        """Get seed URLs for all or specified libraries."""
        urls = []
        libraries = [self.library] if self.library else list(REACT_LIBRARIES.keys())

        for lib_key in libraries:
            if lib_key in REACT_LIBRARIES:
                lib = REACT_LIBRARIES[lib_key]
                urls.extend(lib["seed_urls"])
                logger.info("Added %d seed URLs for %s", len(lib["seed_urls"]), lib["name"])

        return urls

    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be scraped based on library patterns."""
        parsed = urlparse(url)

        # Find matching library for this URL
        for _lib_key, lib in REACT_LIBRARIES.items():
            lib_parsed = urlparse(lib["base_url"])
            if parsed.netloc == lib_parsed.netloc:
                # Check if URL matches any pattern for this library
                for pattern in lib["url_patterns"]:
                    if re.search(pattern, url):
                        return True
                return False

        return False

    def _detect_library(self, url: str) -> str:
        """Detect which library a URL belongs to."""
        parsed = urlparse(url)

        for lib_key, lib in REACT_LIBRARIES.items():
            lib_parsed = urlparse(lib["base_url"])
            if parsed.netloc == lib_parsed.netloc:
                return lib_key

        return "unknown"

    def parse_page(self, url: str, html: str) -> DocPage | None:
        """Parse a React ecosystem documentation page."""
        soup = BeautifulSoup(html, "html.parser")

        # Detect library
        package = self._detect_library(url)

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
            "script",
            "style",
            "noscript",
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

        if not title:
            return None

        # Get main content
        main_content = None
        for selector in ["main", "article", "[role='main']", ".content", ".docs-content"]:
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

        # Determine section type
        section = "reference"
        url_lower = url.lower()
        if "/learn" in url_lower or "/tutorial" in url_lower or "/getting-started" in url_lower:
            section = "tutorial"
        elif "/guide" in url_lower:
            section = "guide"
        elif "/api" in url_lower or "/reference" in url_lower or "/docs/" in url_lower:
            section = "reference"

        # Get breadcrumb
        breadcrumb = ""
        breadcrumb_elem = soup.select_one("[aria-label='breadcrumb']")
        if breadcrumb_elem:
            breadcrumb = " > ".join(
                [li.get_text(strip=True) for li in breadcrumb_elem.select("li, a")]
            )

        return DocPage(
            url=url,
            title=title,
            content=content,
            section=section,
            package=package,
            breadcrumb=breadcrumb,
            code_examples=code_examples,
        )

    def create_collection(self, client: weaviate.WeaviateClient) -> None:
        """Create the ReactEcosystem collection."""
        create_react_ecosystem_collection(client)


def scrape_react_ecosystem(
    library: str | None = None,
    max_pages: int = 0,
    dry_run: bool = False,
    resume: bool = True,
) -> dict:
    """
    Scrape React ecosystem documentation.

    Args:
        library: Specific library to scrape (None = all)
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

    scraper = ReactEcosystemScraper(library=library, config=config)
    return scraper.scrape(resume=resume, dry_run=dry_run)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Scrape React ecosystem documentation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape documentation")
    scrape_parser.add_argument(
        "--library",
        "-l",
        choices=list(REACT_LIBRARIES.keys()),
        help="Specific library to scrape (default: all)",
    )
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
    reindex_parser = subparsers.add_parser("reindex", help="Force reindex")
    reindex_parser.add_argument(
        "--library",
        "-l",
        choices=list(REACT_LIBRARIES.keys()),
        help="Specific library to reindex",
    )

    args = parser.parse_args()

    if args.command == "scrape":
        logger.info("Starting React ecosystem scrape")
        if args.library:
            logger.info("Scraping library: %s", args.library)

        stats = scrape_react_ecosystem(
            library=args.library,
            max_pages=args.limit,
            dry_run=args.dry_run,
            resume=not args.no_resume,
        )

        print("\n" + "=" * 50)
        print("REACT ECOSYSTEM SCRAPE SUMMARY")
        print("=" * 50)
        for key, value in stats.items():
            print(f"  {key}: {value}")
        print("=" * 50)

    elif args.command == "status":
        with WeaviateConnection() as client:
            stats = get_react_ecosystem_stats(client)

            print("\n" + "=" * 50)
            print("REACT ECOSYSTEM COLLECTION STATUS")
            print("=" * 50)
            print(f"Exists: {stats['exists']}")
            print(f"Total objects: {stats['object_count']}")
            if stats["package_counts"]:
                print("\nBy package:")
                for pkg, count in sorted(stats["package_counts"].items()):
                    print(f"  {pkg}: {count}")
            print("=" * 50)

    elif args.command == "reindex":
        with WeaviateConnection() as client:
            create_react_ecosystem_collection(client, force_reindex=True)

        logger.info("Reindexing React ecosystem docs...")
        stats = scrape_react_ecosystem(
            library=args.library if hasattr(args, "library") else None,
            resume=False,
        )

        print("\n" + "=" * 50)
        print("REINDEX COMPLETE")
        print("=" * 50)
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
