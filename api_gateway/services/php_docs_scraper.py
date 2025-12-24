"""
PHP Documentation Scraper.

Scrapes documentation from the official PHP website:
- php.net/manual/en/langref.php (Language Reference)
- php.net/manual/en/funcref.php (Function Reference)
- php.net/manual/en/features.php (Features)
- php.net/manual/en/security.php (Security)
- php.net/manual/en/faq.php (FAQ)

Usage:
    # Scrape all PHP docs
    python -m api_gateway.services.php_docs_scraper scrape

    # Dry run (parse only, no storage)
    python -m api_gateway.services.php_docs_scraper scrape --dry-run

    # Limit pages
    python -m api_gateway.services.php_docs_scraper scrape --limit 100

    # Check status
    python -m api_gateway.services.php_docs_scraper status

    # Force reindex
    python -m api_gateway.services.php_docs_scraper reindex
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
from .php_docs_schema import (
    PHP_DOCS_COLLECTION_NAME,
    create_php_docs_collection,
    get_php_docs_stats,
)
from .weaviate_connection import WeaviateConnection

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# PHP Documentation Sections
# -----------------------------------------------------------------------------

PHP_SECTIONS = {
    "langref": {
        "name": "Language Reference",
        "seed_urls": [
            "https://www.php.net/manual/en/langref.php",
            "https://www.php.net/manual/en/language.basic-syntax.php",
            "https://www.php.net/manual/en/language.types.php",
            "https://www.php.net/manual/en/language.variables.php",
            "https://www.php.net/manual/en/language.constants.php",
            "https://www.php.net/manual/en/language.expressions.php",
            "https://www.php.net/manual/en/language.operators.php",
            "https://www.php.net/manual/en/language.control-structures.php",
            "https://www.php.net/manual/en/language.functions.php",
            "https://www.php.net/manual/en/language.oop5.php",
            "https://www.php.net/manual/en/language.namespaces.php",
            "https://www.php.net/manual/en/language.enumerations.php",
            "https://www.php.net/manual/en/language.errors.php",
            "https://www.php.net/manual/en/language.exceptions.php",
            "https://www.php.net/manual/en/language.fibers.php",
            "https://www.php.net/manual/en/language.generators.php",
            "https://www.php.net/manual/en/language.attributes.php",
            "https://www.php.net/manual/en/language.references.php",
            "https://www.php.net/manual/en/reserved.variables.php",
            "https://www.php.net/manual/en/reserved.interfaces.php",
        ],
        "url_patterns": [
            r"/manual/en/language\.",
            r"/manual/en/reserved\.",
        ],
    },
    "funcref": {
        "name": "Function Reference",
        "seed_urls": [
            "https://www.php.net/manual/en/funcref.php",
            "https://www.php.net/manual/en/refs.basic.vartype.php",
            "https://www.php.net/manual/en/refs.basic.text.php",
            "https://www.php.net/manual/en/refs.math.php",
            "https://www.php.net/manual/en/refs.basic.date.php",
            "https://www.php.net/manual/en/refs.fileprocess.file.php",
            "https://www.php.net/manual/en/refs.database.php",
            "https://www.php.net/manual/en/refs.remote.php",
            "https://www.php.net/manual/en/refs.utilspec.cmdline.php",
            "https://www.php.net/manual/en/refs.compression.php",
            "https://www.php.net/manual/en/refs.crypto.php",
            "https://www.php.net/manual/en/refs.xml.php",
            "https://www.php.net/manual/en/book.array.php",
            "https://www.php.net/manual/en/book.strings.php",
            "https://www.php.net/manual/en/book.datetime.php",
            "https://www.php.net/manual/en/book.json.php",
            "https://www.php.net/manual/en/book.pdo.php",
            "https://www.php.net/manual/en/book.curl.php",
            "https://www.php.net/manual/en/book.filesystem.php",
            "https://www.php.net/manual/en/book.pcre.php",
        ],
        "url_patterns": [
            r"/manual/en/refs\.",
            r"/manual/en/book\.",
            r"/manual/en/function\.",
            r"/manual/en/class\.",
        ],
    },
    "features": {
        "name": "Features",
        "seed_urls": [
            "https://www.php.net/manual/en/features.php",
            "https://www.php.net/manual/en/features.http-auth.php",
            "https://www.php.net/manual/en/features.cookies.php",
            "https://www.php.net/manual/en/features.sessions.php",
            "https://www.php.net/manual/en/features.file-upload.php",
            "https://www.php.net/manual/en/features.commandline.php",
            "https://www.php.net/manual/en/features.gc.php",
            "https://www.php.net/manual/en/features.dtrace.php",
        ],
        "url_patterns": [
            r"/manual/en/features\.",
        ],
    },
    "security": {
        "name": "Security",
        "seed_urls": [
            "https://www.php.net/manual/en/security.php",
            "https://www.php.net/manual/en/security.intro.php",
            "https://www.php.net/manual/en/security.general.php",
            "https://www.php.net/manual/en/security.cgi-bin.php",
            "https://www.php.net/manual/en/security.apache.php",
            "https://www.php.net/manual/en/security.filesystem.php",
            "https://www.php.net/manual/en/security.database.php",
            "https://www.php.net/manual/en/security.errors.php",
            "https://www.php.net/manual/en/security.variables.php",
            "https://www.php.net/manual/en/security.hiding.php",
            "https://www.php.net/manual/en/security.current.php",
        ],
        "url_patterns": [
            r"/manual/en/security\.",
        ],
    },
    "faq": {
        "name": "FAQ",
        "seed_urls": [
            "https://www.php.net/manual/en/faq.php",
            "https://www.php.net/manual/en/faq.general.php",
            "https://www.php.net/manual/en/faq.mailinglist.php",
            "https://www.php.net/manual/en/faq.obtaining.php",
            "https://www.php.net/manual/en/faq.databases.php",
            "https://www.php.net/manual/en/faq.installation.php",
            "https://www.php.net/manual/en/faq.build.php",
            "https://www.php.net/manual/en/faq.using.php",
            "https://www.php.net/manual/en/faq.passwords.php",
            "https://www.php.net/manual/en/faq.html.php",
            "https://www.php.net/manual/en/faq.com.php",
            "https://www.php.net/manual/en/faq.misc.php",
        ],
        "url_patterns": [
            r"/manual/en/faq\.",
        ],
    },
    "appendices": {
        "name": "Appendices",
        "seed_urls": [
            "https://www.php.net/manual/en/appendices.php",
            "https://www.php.net/manual/en/history.php",
            "https://www.php.net/manual/en/migration83.php",
            "https://www.php.net/manual/en/migration82.php",
            "https://www.php.net/manual/en/migration81.php",
            "https://www.php.net/manual/en/migration80.php",
            "https://www.php.net/manual/en/debugger.php",
            "https://www.php.net/manual/en/configuration.php",
            "https://www.php.net/manual/en/ini.php",
        ],
        "url_patterns": [
            r"/manual/en/appendices\.",
            r"/manual/en/history\.",
            r"/manual/en/migration\d+\.",
            r"/manual/en/configuration\.",
            r"/manual/en/ini\.",
        ],
    },
}


class PHPDocsScraper(BaseDocScraper):
    """
    Scraper for PHP documentation.

    Supports multiple documentation sections with section-specific URL patterns
    and parsing logic.
    """

    def __init__(
        self,
        config: ScraperConfig | None = None,
    ):
        """
        Initialize the PHP docs scraper.

        Args:
            config: Scraper configuration
        """
        # Use conservative rate limiting (php.net is strict)
        if config is None:
            config = ScraperConfig(
                min_delay=2.0,
                max_delay=5.0,
                batch_size=6,
                batch_pause_min=15.0,
                batch_pause_max=30.0,
                max_depth=10,
            )

        super().__init__(
            name="php_docs",
            base_url="https://www.php.net",
            collection_name=PHP_DOCS_COLLECTION_NAME,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        """Get seed URLs for all PHP documentation sections."""
        urls = []
        for _section_key, section in PHP_SECTIONS.items():
            urls.extend(section["seed_urls"])
            logger.info("Added %d seed URLs for %s", len(section["seed_urls"]), section["name"])
        return urls

    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be scraped based on section patterns."""
        parsed = urlparse(url)

        # Must be php.net
        if parsed.netloc not in ("www.php.net", "php.net"):
            return False

        # Must be English manual
        if "/manual/en/" not in url:
            return False

        # Skip non-documentation pages
        skip_patterns = [
            r"/manual/en/about\.",
            r"/manual/en/copyright\.",
            r"/manual/en/credits\.",
            r"/manual/en/help\.",
            r"\.vote",
            r"\.comments",
            r"#",  # Skip anchor links
        ]
        for pattern in skip_patterns:
            if re.search(pattern, url):
                return False

        # Check if URL matches any section pattern
        for section in PHP_SECTIONS.values():
            for pattern in section["url_patterns"]:
                if re.search(pattern, url):
                    return True

        # Also allow general manual pages
        if "/manual/en/" in url and url.endswith(".php"):
            return True

        return False

    def _detect_section(self, url: str) -> str:
        """Detect which documentation section a URL belongs to."""
        url_lower = url.lower()

        if "/language." in url_lower or "/reserved." in url_lower:
            return "langref"
        elif any(p in url_lower for p in ["/refs.", "/book.", "/function.", "/class."]):
            return "funcref"
        elif "/features." in url_lower:
            return "features"
        elif "/security." in url_lower:
            return "security"
        elif "/faq." in url_lower:
            return "faq"
        elif any(
            p in url_lower
            for p in ["/appendices.", "/history.", "/migration", "/configuration.", "/ini."]
        ):
            return "appendices"
        else:
            return "general"

    def _detect_subsection(self, url: str, title: str) -> str:
        """Detect more specific subsection based on URL and title."""
        url_lower = url.lower()

        # Language reference subsections
        if "/language.types" in url_lower:
            return "types"
        if "/language.variables" in url_lower:
            return "variables"
        if "/language.oop5" in url_lower:
            return "oop"
        if "/language.functions" in url_lower:
            return "functions"
        if "/language.control" in url_lower:
            return "control-structures"
        if "/language.operators" in url_lower:
            return "operators"
        if "/language.namespaces" in url_lower:
            return "namespaces"
        if "/language.exceptions" in url_lower or "/language.errors" in url_lower:
            return "error-handling"

        # Function reference subsections
        if "/book." in url_lower or "/function." in url_lower:
            # Extract extension name
            match = re.search(r"/book\.([^.]+)\.", url_lower)
            if match:
                return match.group(1)
            match = re.search(r"/function\.([^-]+)", url_lower)
            if match:
                return match.group(1)

        return "general"

    def parse_page(self, url: str, html: str) -> DocPage | None:
        """Parse a PHP documentation page."""
        soup = BeautifulSoup(html, "html.parser")

        # Detect section
        section = self._detect_section(url)

        # Remove navigation, footer, etc.
        for selector in [
            "nav",
            "footer",
            "header",
            ".layout-footer",
            ".layout-menu",
            ".navbar",
            ".docs-nav",
            ".sidebar",
            "#layout-menu",
            "#breadcrumbs-inner",
            ".edit-bug",
            ".usernotes",
            ".refentry-edit",
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
            # Clean up title
            if " - " in title:
                title = title.split(" - ")[0].strip()
            if "PHP:" in title:
                title = title.replace("PHP:", "").strip()

        if not title:
            return None

        # Detect subsection
        subsection = self._detect_subsection(url, title)

        # Get main content
        main_content = None
        for selector in [
            "#layout-content",
            ".refentry",
            ".sect1",
            ".chapter",
            "main",
            "article",
            ".docs-content",
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
        for code in main_content.select("pre code, pre, .phpcode, .example-contents"):
            code_text = code.get_text(strip=True)
            if code_text and len(code_text) > 20:
                code_examples.append(code_text[:1000])

        # Get breadcrumb
        breadcrumb = ""
        breadcrumb_elem = soup.select_one("#breadcrumbs, .breadcrumb, [aria-label='breadcrumb']")
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
        """Create the PHPDocs collection."""
        create_php_docs_collection(client)


def scrape_php_docs(
    max_pages: int = 0,
    dry_run: bool = False,
    resume: bool = True,
) -> dict:
    """
    Scrape PHP documentation.

    Args:
        max_pages: Maximum pages to scrape (0 = unlimited)
        dry_run: Parse only, don't store
        resume: Resume from checkpoint

    Returns:
        Statistics dict
    """
    config = ScraperConfig(
        min_delay=2.0,
        max_delay=5.0,
        batch_size=6,
        batch_pause_min=15.0,
        batch_pause_max=30.0,
        max_pages=max_pages,
    )

    scraper = PHPDocsScraper(config=config)
    return scraper.scrape(resume=resume, dry_run=dry_run)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Scrape PHP documentation")
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
        logger.info("Starting PHP docs scrape")

        stats = scrape_php_docs(
            max_pages=args.limit,
            dry_run=args.dry_run,
            resume=not args.no_resume,
        )

        print("\n" + "=" * 50)
        print("PHP DOCS SCRAPE SUMMARY")
        print("=" * 50)
        for key, value in stats.items():
            print(f"  {key}: {value}")
        print("=" * 50)

    elif args.command == "status":
        with WeaviateConnection() as client:
            stats = get_php_docs_stats(client)

            print("\n" + "=" * 50)
            print("PHP DOCS COLLECTION STATUS")
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
            create_php_docs_collection(client, force_reindex=True)

        logger.info("Reindexing PHP docs...")
        stats = scrape_php_docs(resume=False)

        print("\n" + "=" * 50)
        print("REINDEX COMPLETE")
        print("=" * 50)
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
