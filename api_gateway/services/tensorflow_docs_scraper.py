"""
TensorFlow Documentation Scraper.

Scrapes TensorFlow documentation from tensorflow.org
and stores in Weaviate for semantic search.

Includes:
- API Reference (tf, tf.keras, tf.data, etc.)
- Tutorials and guides
- Best practices

Usage:
    python -m api_gateway.services.tensorflow_docs_scraper scrape
    python -m api_gateway.services.tensorflow_docs_scraper scrape --limit 100
    python -m api_gateway.services.tensorflow_docs_scraper status
"""

import re

import weaviate.classes as wvc
from bs4 import BeautifulSoup

from api_gateway.services.base_doc_scraper import (
    BaseDocScraper,
    DocPage,
    ScraperConfig,
)
from api_gateway.utils.logger import get_logger

logger = get_logger(__name__)

# Collection name for TensorFlow docs
TENSORFLOW_DOCS_COLLECTION = "TensorFlowDocs"


class TensorFlowDocScraper(BaseDocScraper):
    """Scraper for TensorFlow documentation."""

    def __init__(self, config: ScraperConfig | None = None):
        # TensorFlow-specific config with conservative rate limiting
        if config is None:
            config = ScraperConfig(
                min_delay=2.0,  # 2-5 seconds between requests
                max_delay=5.0,
                batch_size=12,
                batch_pause_min=15.0,
                batch_pause_max=40.0,
                max_depth=8,
                checkpoint_interval=20,
            )

        super().__init__(
            name="tensorflow_docs",
            base_url="https://www.tensorflow.org",
            collection_name=TENSORFLOW_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        """Return seed URLs for TensorFlow documentation."""
        return [
            # Main API reference
            "https://www.tensorflow.org/api_docs/python/tf",
            # Keras API
            "https://www.tensorflow.org/api_docs/python/tf/keras",
            "https://www.tensorflow.org/api_docs/python/tf/keras/layers",
            "https://www.tensorflow.org/api_docs/python/tf/keras/Model",
            "https://www.tensorflow.org/api_docs/python/tf/keras/optimizers",
            "https://www.tensorflow.org/api_docs/python/tf/keras/losses",
            "https://www.tensorflow.org/api_docs/python/tf/keras/metrics",
            # Data pipeline
            "https://www.tensorflow.org/api_docs/python/tf/data",
            "https://www.tensorflow.org/api_docs/python/tf/data/Dataset",
            # Math operations
            "https://www.tensorflow.org/api_docs/python/tf/math",
            "https://www.tensorflow.org/api_docs/python/tf/linalg",
            # Variables and tensors
            "https://www.tensorflow.org/api_docs/python/tf/Variable",
            "https://www.tensorflow.org/api_docs/python/tf/Tensor",
            # Training
            "https://www.tensorflow.org/api_docs/python/tf/GradientTape",
            "https://www.tensorflow.org/api_docs/python/tf/train",
            # Distribution strategy
            "https://www.tensorflow.org/api_docs/python/tf/distribute",
            # Tutorials index
            "https://www.tensorflow.org/tutorials",
            # Guide index
            "https://www.tensorflow.org/guide",
        ]

    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be scraped."""
        # First check parent validation
        if not super().is_valid_url(url):
            return False

        # Must be docs, tutorials, or guides
        if not (
            "/api_docs/python/" in url
            or "/tutorials/" in url
            or "/guide/" in url
        ):
            return False

        # Skip version-specific docs
        if re.search(r"/api_docs/python/tf/r\d+", url):
            return False

        # Skip experimental/deprecated
        if "/experimental/" in url.lower():
            return False

        # Skip media/static
        if any(
            pattern in url
            for pattern in ["/images/", "/static/", "/_static/"]
        ):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        """Determine the documentation section type."""
        if "/tutorials/" in url:
            return "tutorial"
        if "/guide/" in url:
            return "guide"
        if "/api_docs/python/" in url:
            return "api"
        return "reference"

    def _extract_module_name(self, url: str) -> str:
        """Extract module/class name from URL."""
        # Match patterns like tf.keras.layers
        match = re.search(r"/api_docs/python/(tf(?:/\w+)*)", url)
        if match:
            return match.group(1).replace("/", ".")
        return ""

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        """Extract code examples from the page."""
        examples = []

        # TensorFlow uses devsite-code for code blocks
        for code_block in soup.select("devsite-code pre, pre.prettyprint, div.highlight pre"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:
                examples.append(code[:2000])

        return examples[:10]

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from TensorFlow docs page."""
        # Try different content selectors
        content_elem = (
            soup.select_one("article.devsite-article")
            or soup.select_one("div.devsite-article-body")
            or soup.select_one("main")
            or soup.select_one("article")
        )

        if not content_elem:
            return ""

        # Remove navigation elements
        for selector in [
            "nav",
            "header",
            "footer",
            ".devsite-nav",
            ".devsite-toc",
            "script",
            "style",
        ]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_breadcrumb(self, soup: BeautifulSoup) -> str:
        """Extract breadcrumb navigation."""
        breadcrumb = soup.select_one("nav.devsite-breadcrumb-list, .breadcrumb")
        if breadcrumb:
            items = breadcrumb.select("li a, a")
            return " > ".join(item.get_text(strip=True) for item in items if item.get_text(strip=True))
        return ""

    def parse_page(self, url: str, html: str) -> DocPage | None:
        """Parse TensorFlow documentation page."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_elem = (
            soup.select_one("h1.devsite-page-title")
            or soup.select_one("h1")
            or soup.select_one("title")
        )
        title = title_elem.get_text(strip=True) if title_elem else ""

        # Clean up title
        title = re.sub(r"\s*\|\s*TensorFlow.*$", "", title)
        title = re.sub(r"\s*-\s*TensorFlow.*$", "", title)

        if not title:
            return None

        # Extract content
        content = self._extract_content(soup)
        if not content or len(content) < 100:
            return None

        # Determine section type
        section = self._determine_section(url, soup)

        # Extract module name
        module_name = self._extract_module_name(url)

        # Extract code examples
        code_examples = self._extract_code_examples(soup)

        # Extract breadcrumb
        breadcrumb = self._extract_breadcrumb(soup)

        return DocPage(
            url=url,
            title=title,
            content=content,
            section=section,
            package="tensorflow",
            version="latest",
            breadcrumb=breadcrumb or f"TensorFlow > {module_name}" if module_name else "TensorFlow",
            code_examples=code_examples,
        )

    def create_collection(self, client) -> None:
        """Create Weaviate collection for TensorFlow docs."""
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)

        client.collections.create(
            name=self.collection_name,
            description="TensorFlow documentation including API reference, guides, and tutorials",
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
                    description="Section type (api, tutorial, guide, reference)",
                ),
                wvc.config.Property(
                    name="package",
                    data_type=wvc.config.DataType.TEXT,
                    description="Package name (tensorflow)",
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

    parser = argparse.ArgumentParser(description="TensorFlow Documentation Scraper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape TensorFlow documentation")
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
        scraper = TensorFlowDocScraper(config=config)
        stats = scraper.scrape(
            resume=not args.no_resume,
            dry_run=args.dry_run,
        )
        print("\nScrape Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    elif args.command == "status":
        with WeaviateConnection() as client:
            if not client.collections.exists(TENSORFLOW_DOCS_COLLECTION):
                print(f"Collection '{TENSORFLOW_DOCS_COLLECTION}' does not exist")
                sys.exit(1)

            collection = client.collections.get(TENSORFLOW_DOCS_COLLECTION)
            response = collection.aggregate.over_all(total_count=True)
            print(f"Collection: {TENSORFLOW_DOCS_COLLECTION}")
            print(f"Total documents: {response.total_count}")

    elif args.command == "clean":
        with WeaviateConnection() as client:
            if client.collections.exists(TENSORFLOW_DOCS_COLLECTION):
                client.collections.delete(TENSORFLOW_DOCS_COLLECTION)
                print(f"Deleted collection: {TENSORFLOW_DOCS_COLLECTION}")
            else:
                print(f"Collection '{TENSORFLOW_DOCS_COLLECTION}' does not exist")


if __name__ == "__main__":
    main()
