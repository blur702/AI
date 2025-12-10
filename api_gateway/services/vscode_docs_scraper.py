"""
VS Code Documentation Scraper.

Scrapes VS Code documentation from code.visualstudio.com
and stores in Weaviate for semantic search.

Includes:
- User documentation (docs/)
- Extension API reference (api/)
- Extension guides and samples

Usage:
    python -m api_gateway.services.vscode_docs_scraper scrape
    python -m api_gateway.services.vscode_docs_scraper scrape --limit 100
    python -m api_gateway.services.vscode_docs_scraper status
"""

import re
from typing import Optional

import weaviate.classes as wvc
from bs4 import BeautifulSoup

from api_gateway.services.base_doc_scraper import (
    BaseDocScraper,
    DocPage,
    ScraperConfig,
)
from api_gateway.utils.logger import get_logger

logger = get_logger(__name__)

# Collection name for VS Code docs
VSCODE_DOCS_COLLECTION = "VSCodeDocs"


class VSCodeDocScraper(BaseDocScraper):
    """Scraper for VS Code documentation."""

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig(
                min_delay=1.5,
                max_delay=4.0,
                batch_size=15,
                batch_pause_min=10.0,
                batch_pause_max=30.0,
                max_depth=8,
                checkpoint_interval=25,
            )

        super().__init__(
            name="vscode_docs",
            base_url="https://code.visualstudio.com",
            collection_name=VSCODE_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        """Return seed URLs for VS Code documentation."""
        return [
            # Main documentation
            "https://code.visualstudio.com/docs",
            # Setup
            "https://code.visualstudio.com/docs/setup/setup-overview",
            "https://code.visualstudio.com/docs/setup/windows",
            "https://code.visualstudio.com/docs/setup/linux",
            "https://code.visualstudio.com/docs/setup/mac",
            # Getting started
            "https://code.visualstudio.com/docs/getstarted/userinterface",
            "https://code.visualstudio.com/docs/getstarted/settings",
            "https://code.visualstudio.com/docs/getstarted/keybindings",
            "https://code.visualstudio.com/docs/getstarted/themes",
            # Editor features
            "https://code.visualstudio.com/docs/editor/codebasics",
            "https://code.visualstudio.com/docs/editor/intellisense",
            "https://code.visualstudio.com/docs/editor/debugging",
            "https://code.visualstudio.com/docs/editor/refactoring",
            "https://code.visualstudio.com/docs/editor/tasks",
            "https://code.visualstudio.com/docs/editor/userdefinedsnippets",
            "https://code.visualstudio.com/docs/editor/command-line",
            "https://code.visualstudio.com/docs/editor/multi-root-workspaces",
            # Languages
            "https://code.visualstudio.com/docs/languages/overview",
            "https://code.visualstudio.com/docs/languages/javascript",
            "https://code.visualstudio.com/docs/languages/typescript",
            "https://code.visualstudio.com/docs/languages/python",
            "https://code.visualstudio.com/docs/languages/java",
            "https://code.visualstudio.com/docs/languages/cpp",
            "https://code.visualstudio.com/docs/languages/csharp",
            "https://code.visualstudio.com/docs/languages/go",
            "https://code.visualstudio.com/docs/languages/rust",
            # Source control
            "https://code.visualstudio.com/docs/sourcecontrol/overview",
            "https://code.visualstudio.com/docs/sourcecontrol/intro-to-git",
            # Terminal
            "https://code.visualstudio.com/docs/terminal/basics",
            "https://code.visualstudio.com/docs/terminal/profiles",
            # Remote development
            "https://code.visualstudio.com/docs/remote/remote-overview",
            "https://code.visualstudio.com/docs/remote/ssh",
            "https://code.visualstudio.com/docs/remote/wsl",
            "https://code.visualstudio.com/docs/remote/containers",
            # Extension API
            "https://code.visualstudio.com/api",
            "https://code.visualstudio.com/api/get-started/your-first-extension",
            "https://code.visualstudio.com/api/get-started/extension-anatomy",
            "https://code.visualstudio.com/api/get-started/wrapping-up",
            # Extension capabilities
            "https://code.visualstudio.com/api/extension-capabilities/overview",
            "https://code.visualstudio.com/api/extension-capabilities/common-capabilities",
            "https://code.visualstudio.com/api/extension-capabilities/theming",
            "https://code.visualstudio.com/api/extension-capabilities/extending-workbench",
            # Extension guides
            "https://code.visualstudio.com/api/extension-guides/overview",
            "https://code.visualstudio.com/api/extension-guides/command",
            "https://code.visualstudio.com/api/extension-guides/webview",
            "https://code.visualstudio.com/api/extension-guides/language-model",
            "https://code.visualstudio.com/api/extension-guides/chat",
            # API references
            "https://code.visualstudio.com/api/references/vscode-api",
            "https://code.visualstudio.com/api/references/contribution-points",
            "https://code.visualstudio.com/api/references/activation-events",
            "https://code.visualstudio.com/api/references/extension-manifest",
            "https://code.visualstudio.com/api/references/commands",
            "https://code.visualstudio.com/api/references/when-clause-contexts",
            # UX Guidelines
            "https://code.visualstudio.com/api/ux-guidelines/overview",
        ]

    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be scraped."""
        if not super().is_valid_url(url):
            return False

        # Must be docs or api pages
        if not ("/docs/" in url or "/api/" in url):
            return False

        # Skip blogs, updates, learn pages
        if any(pattern in url for pattern in ["/blogs/", "/updates/", "/learn/", "/Download"]):
            return False

        # Skip assets
        if any(pattern in url for pattern in ["/assets/", ".png", ".jpg", ".gif", ".svg"]):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        """Determine the documentation section type."""
        if "/api/references/" in url:
            return "api-reference"
        if "/api/extension-guides/" in url:
            return "extension-guide"
        if "/api/extension-capabilities/" in url:
            return "extension-capabilities"
        if "/api/get-started/" in url:
            return "getting-started"
        if "/api/ux-guidelines/" in url:
            return "ux-guidelines"
        if "/api/" in url:
            return "api"
        if "/docs/getstarted/" in url:
            return "getting-started"
        if "/docs/editor/" in url:
            return "editor"
        if "/docs/languages/" in url:
            return "languages"
        if "/docs/remote/" in url:
            return "remote"
        if "/docs/sourcecontrol/" in url:
            return "source-control"
        if "/docs/terminal/" in url:
            return "terminal"
        if "/docs/setup/" in url:
            return "setup"
        return "docs"

    def _extract_category(self, url: str) -> str:
        """Extract category from URL path."""
        # Match patterns like /docs/editor/ or /api/extension-guides/
        match = re.search(r"/(docs|api)/([^/]+)/", url)
        if match:
            return match.group(2).replace("-", " ").title()
        return ""

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        """Extract code examples from the page."""
        examples = []

        # VS Code uses various code block formats
        for code_block in soup.select("pre code, div.monaco-editor, pre.highlight"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:
                examples.append(code[:2000])

        return examples[:10]

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from VS Code docs page."""
        # Try different content selectors
        content_elem = (
            soup.select_one("article.docs-article")
            or soup.select_one("main.main-content")
            or soup.select_one("div.body")
            or soup.select_one("article")
            or soup.select_one("main")
        )

        if not content_elem:
            return ""

        # Remove navigation, header, footer, TOC
        for selector in [
            "nav",
            "header",
            "footer",
            ".sidebar",
            ".toc",
            ".edit-this-article",
            ".feedback",
            "script",
            "style",
        ]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_breadcrumb(self, soup: BeautifulSoup) -> str:
        """Extract breadcrumb navigation."""
        breadcrumb = soup.select_one("nav.breadcrumb, .breadcrumbs, nav[aria-label='breadcrumb']")
        if breadcrumb:
            items = breadcrumb.select("a, span")
            return " > ".join(item.get_text(strip=True) for item in items if item.get_text(strip=True))
        return ""

    def parse_page(self, url: str, html: str) -> DocPage | None:
        """Parse VS Code documentation page."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_elem = (
            soup.select_one("h1.title")
            or soup.select_one("h1")
            or soup.select_one("title")
        )
        title = title_elem.get_text(strip=True) if title_elem else ""

        # Clean up title
        title = re.sub(r"\s*[-|]\s*Visual Studio Code.*$", "", title)
        title = re.sub(r"\s*[-|]\s*VS Code.*$", "", title)

        if not title:
            return None

        # Extract content
        content = self._extract_content(soup)
        if not content or len(content) < 100:
            return None

        # Determine section type
        section = self._determine_section(url, soup)

        # Extract category
        category = self._extract_category(url)

        # Extract code examples
        code_examples = self._extract_code_examples(soup)

        # Extract breadcrumb
        breadcrumb = self._extract_breadcrumb(soup)

        return DocPage(
            url=url,
            title=title,
            content=content,
            section=section,
            package="vscode",
            version="latest",
            breadcrumb=breadcrumb or f"VS Code > {category}" if category else "VS Code",
            code_examples=code_examples,
        )

    def create_collection(self, client) -> None:
        """Create Weaviate collection for VS Code docs."""
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)

        client.collections.create(
            name=self.collection_name,
            description="VS Code documentation including user guide and extension API reference",
            vectorizer_config=wvc.config.Configure.Vectorizer.none(),
            properties=[
                wvc.config.Property(
                    name="url",
                    data_type=wvc.config.DataType.TEXT,
                    description="Documentation page URL",
                ),
                wvc.config.Property(
                    name="title",
                    data_type=wvc.config.DataType.TEXT,
                    description="Page title",
                ),
                wvc.config.Property(
                    name="content",
                    data_type=wvc.config.DataType.TEXT,
                    description="Main text content",
                ),
                wvc.config.Property(
                    name="section",
                    data_type=wvc.config.DataType.TEXT,
                    description="Section type (api, docs, api-reference, extension-guide, etc.)",
                ),
                wvc.config.Property(
                    name="package",
                    data_type=wvc.config.DataType.TEXT,
                    description="Package name (vscode)",
                ),
                wvc.config.Property(
                    name="version",
                    data_type=wvc.config.DataType.TEXT,
                    description="Documentation version",
                ),
                wvc.config.Property(
                    name="breadcrumb",
                    data_type=wvc.config.DataType.TEXT,
                    description="Navigation breadcrumb",
                ),
                wvc.config.Property(
                    name="code_examples",
                    data_type=wvc.config.DataType.TEXT,
                    description="Code examples from the page",
                ),
            ],
        )


def main():
    """CLI entry point."""
    import argparse
    import sys

    from api_gateway.services.weaviate_connection import WeaviateConnection

    parser = argparse.ArgumentParser(description="VS Code Documentation Scraper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape VS Code documentation")
    scrape_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum pages to scrape (0=unlimited)",
    )
    scrape_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse pages without storing",
    )
    scrape_parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh, ignore checkpoint",
    )

    # Status command
    subparsers.add_parser("status", help="Show collection status")

    # Clean command
    subparsers.add_parser("clean", help="Delete collection")

    args = parser.parse_args()

    if args.command == "scrape":
        config = ScraperConfig(max_pages=args.limit) if args.limit > 0 else None
        scraper = VSCodeDocScraper(config=config)
        stats = scraper.scrape(
            resume=not args.no_resume,
            dry_run=args.dry_run,
        )
        print("\nScrape Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    elif args.command == "status":
        with WeaviateConnection() as client:
            if not client.collections.exists(VSCODE_DOCS_COLLECTION):
                print(f"Collection '{VSCODE_DOCS_COLLECTION}' does not exist")
                sys.exit(1)

            collection = client.collections.get(VSCODE_DOCS_COLLECTION)
            response = collection.aggregate.over_all(total_count=True)
            print(f"Collection: {VSCODE_DOCS_COLLECTION}")
            print(f"Total documents: {response.total_count}")

    elif args.command == "clean":
        with WeaviateConnection() as client:
            if client.collections.exists(VSCODE_DOCS_COLLECTION):
                client.collections.delete(VSCODE_DOCS_COLLECTION)
                print(f"Deleted collection: {VSCODE_DOCS_COLLECTION}")
            else:
                print(f"Collection '{VSCODE_DOCS_COLLECTION}' does not exist")


if __name__ == "__main__":
    main()
