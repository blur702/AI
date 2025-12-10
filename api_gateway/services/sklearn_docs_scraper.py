"""
scikit-learn Documentation Scraper.

Scrapes scikit-learn documentation from scikit-learn.org
and stores in Weaviate for semantic search.

Includes:
- API Reference (sklearn modules)
- User Guide
- Examples
- Tutorials

Usage:
    python -m api_gateway.services.sklearn_docs_scraper scrape
    python -m api_gateway.services.sklearn_docs_scraper scrape --limit 100
    python -m api_gateway.services.sklearn_docs_scraper status
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

# Collection name for scikit-learn docs
SKLEARN_DOCS_COLLECTION = "ScikitLearnDocs"


class ScikitLearnDocScraper(BaseDocScraper):
    """Scraper for scikit-learn documentation."""

    def __init__(self, config: ScraperConfig | None = None):
        # scikit-learn-specific config
        if config is None:
            config = ScraperConfig(
                min_delay=1.5,
                max_delay=4.0,
                batch_size=15,
                batch_pause_min=10.0,
                batch_pause_max=25.0,
                max_depth=8,
                checkpoint_interval=25,
            )

        super().__init__(
            name="sklearn_docs",
            base_url="https://scikit-learn.org",
            collection_name=SKLEARN_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        """Return seed URLs for scikit-learn documentation."""
        return [
            # Main documentation
            "https://scikit-learn.org/stable/index.html",
            # User Guide
            "https://scikit-learn.org/stable/user_guide.html",
            # API Reference
            "https://scikit-learn.org/stable/modules/classes.html",
            # Classification
            "https://scikit-learn.org/stable/supervised_learning.html",
            # Preprocessing
            "https://scikit-learn.org/stable/modules/preprocessing.html",
            # Model selection
            "https://scikit-learn.org/stable/modules/cross_validation.html",
            "https://scikit-learn.org/stable/modules/grid_search.html",
            # Clustering
            "https://scikit-learn.org/stable/modules/clustering.html",
            # Dimensionality reduction
            "https://scikit-learn.org/stable/modules/decomposition.html",
            # Ensemble methods
            "https://scikit-learn.org/stable/modules/ensemble.html",
            # Neural networks
            "https://scikit-learn.org/stable/modules/neural_networks_supervised.html",
            # Feature selection
            "https://scikit-learn.org/stable/modules/feature_selection.html",
            # Pipelines
            "https://scikit-learn.org/stable/modules/compose.html",
            # Examples gallery
            "https://scikit-learn.org/stable/auto_examples/index.html",
        ]

    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be scraped."""
        if not super().is_valid_url(url):
            return False

        # Must be in stable docs
        if "/stable/" not in url:
            return False

        # Skip version-specific
        if re.search(r"/\d+\.\d+/", url):
            return False

        # Skip downloads and builds
        if any(pattern in url for pattern in ["/_downloads/", "/_build/", "/_sources/"]):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        """Determine the documentation section type."""
        if "/auto_examples/" in url:
            return "example"
        if "/tutorial/" in url:
            return "tutorial"
        if "/modules/generated/" in url:
            return "api"
        if "/modules/" in url:
            return "guide"
        return "reference"

    def _extract_module_name(self, url: str) -> str:
        """Extract module/class name from URL."""
        # Match patterns like sklearn.ensemble.RandomForestClassifier
        match = re.search(r"/generated/(sklearn\.[^.]+(?:\.[^.]+)*)\.html", url)
        if match:
            return match.group(1)
        return ""

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        """Extract code examples from the page."""
        examples = []

        for code_block in soup.select("div.highlight-python pre, div.highlight-default pre, pre.literal-block"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:
                examples.append(code[:2000])

        return examples[:10]

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from scikit-learn docs page."""
        content_elem = (
            soup.select_one("div.document")
            or soup.select_one("article")
            or soup.select_one("main")
        )

        if not content_elem:
            return ""

        # Remove navigation
        for selector in [
            "nav",
            ".nav",
            ".sphinxsidebar",
            ".related",
            "script",
            "style",
        ]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_breadcrumb(self, soup: BeautifulSoup) -> str:
        """Extract breadcrumb navigation."""
        breadcrumb = soup.select_one(".related li, nav.breadcrumb")
        if breadcrumb:
            return breadcrumb.get_text(" > ", strip=True)
        return ""

    def parse_page(self, url: str, html: str) -> DocPage | None:
        """Parse scikit-learn documentation page."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_elem = soup.select_one("h1") or soup.select_one("title")
        title = title_elem.get_text(strip=True) if title_elem else ""

        # Clean up title
        title = re.sub(r"\s*—\s*scikit-learn.*$", "", title)
        title = re.sub(r"¶$", "", title)

        if not title:
            return None

        content = self._extract_content(soup)
        if not content or len(content) < 100:
            return None

        section = self._determine_section(url, soup)
        module_name = self._extract_module_name(url)
        code_examples = self._extract_code_examples(soup)
        breadcrumb = self._extract_breadcrumb(soup)

        return DocPage(
            url=url,
            title=title,
            content=content,
            section=section,
            package="scikit-learn",
            version="stable",
            breadcrumb=breadcrumb or f"scikit-learn > {module_name}" if module_name else "scikit-learn",
            code_examples=code_examples,
        )

    def create_collection(self, client) -> None:
        """Create Weaviate collection for scikit-learn docs."""
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)

        client.collections.create(
            name=self.collection_name,
            description="scikit-learn documentation including API reference, user guide, and examples",
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
                    description="Section type (api, guide, example, tutorial)",
                ),
                wvc.config.Property(
                    name="package",
                    data_type=wvc.config.DataType.TEXT,
                    description="Package name (scikit-learn)",
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

    parser = argparse.ArgumentParser(description="scikit-learn Documentation Scraper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape_parser = subparsers.add_parser("scrape", help="Scrape scikit-learn documentation")
    scrape_parser.add_argument("--limit", type=int, default=0, help="Maximum pages to scrape")
    scrape_parser.add_argument("--dry-run", action="store_true", help="Parse without storing")
    scrape_parser.add_argument("--no-resume", action="store_true", help="Start fresh")

    subparsers.add_parser("status", help="Show collection status")
    subparsers.add_parser("clean", help="Delete collection")

    args = parser.parse_args()

    if args.command == "scrape":
        config = ScraperConfig(max_pages=args.limit) if args.limit > 0 else None
        scraper = ScikitLearnDocScraper(config=config)
        stats = scraper.scrape(resume=not args.no_resume, dry_run=args.dry_run)
        print("\nScrape Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    elif args.command == "status":
        with WeaviateConnection() as client:
            if not client.collections.exists(SKLEARN_DOCS_COLLECTION):
                print(f"Collection '{SKLEARN_DOCS_COLLECTION}' does not exist")
                sys.exit(1)
            collection = client.collections.get(SKLEARN_DOCS_COLLECTION)
            response = collection.aggregate.over_all(total_count=True)
            print(f"Collection: {SKLEARN_DOCS_COLLECTION}")
            print(f"Total documents: {response.total_count}")

    elif args.command == "clean":
        with WeaviateConnection() as client:
            if client.collections.exists(SKLEARN_DOCS_COLLECTION):
                client.collections.delete(SKLEARN_DOCS_COLLECTION)
                print(f"Deleted collection: {SKLEARN_DOCS_COLLECTION}")
            else:
                print(f"Collection '{SKLEARN_DOCS_COLLECTION}' does not exist")


if __name__ == "__main__":
    main()
