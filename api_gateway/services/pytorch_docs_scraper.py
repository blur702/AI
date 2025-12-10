"""
PyTorch Documentation Scraper.

Scrapes PyTorch documentation from pytorch.org/docs
and stores in Weaviate for semantic search.

Includes:
- Tutorials
- API Reference (torch, torch.nn, torch.optim, etc.)
- Notes and best practices

Usage:
    python -m api_gateway.services.pytorch_docs_scraper scrape
    python -m api_gateway.services.pytorch_docs_scraper scrape --limit 100
    python -m api_gateway.services.pytorch_docs_scraper status
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

# Collection name for PyTorch docs
PYTORCH_DOCS_COLLECTION = "PyTorchDocs"


class PyTorchDocScraper(BaseDocScraper):
    """Scraper for PyTorch documentation."""

    def __init__(self, config: ScraperConfig | None = None):
        # PyTorch-specific config with more conservative rate limiting
        if config is None:
            config = ScraperConfig(
                min_delay=1.5,  # 1.5-4 seconds between requests
                max_delay=4.0,
                batch_size=15,
                batch_pause_min=10.0,
                batch_pause_max=30.0,
                max_depth=8,
                checkpoint_interval=25,
            )

        super().__init__(
            name="pytorch_docs",
            base_url="https://pytorch.org",
            collection_name=PYTORCH_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        """Return seed URLs for PyTorch documentation."""
        return [
            # Main documentation index
            "https://pytorch.org/docs/stable/index.html",
            # Core torch module
            "https://pytorch.org/docs/stable/torch.html",
            # Neural network modules
            "https://pytorch.org/docs/stable/nn.html",
            "https://pytorch.org/docs/stable/nn.functional.html",
            # Optimizers
            "https://pytorch.org/docs/stable/optim.html",
            # Tensors
            "https://pytorch.org/docs/stable/tensors.html",
            # Autograd
            "https://pytorch.org/docs/stable/autograd.html",
            # Data loading
            "https://pytorch.org/docs/stable/data.html",
            # CUDA support
            "https://pytorch.org/docs/stable/cuda.html",
            # Distributed training
            "https://pytorch.org/docs/stable/distributed.html",
            # JIT compilation
            "https://pytorch.org/docs/stable/jit.html",
            # Quantization
            "https://pytorch.org/docs/stable/quantization.html",
            # Tutorials index
            "https://pytorch.org/tutorials/index.html",
        ]

    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be scraped."""
        # First check parent validation
        if not super().is_valid_url(url):
            return False

        # Must be docs or tutorials
        if not (
            "/docs/stable/" in url
            or "/docs/main/" in url
            or "/tutorials/" in url
        ):
            return False

        # Skip version-specific docs (we want stable)
        if re.search(r"/docs/\d+\.\d+/", url):
            return False

        # Skip non-English docs
        if re.search(r"/docs/stable/(zh|ja|ko|pt|es|fr|de)/", url):
            return False

        # Skip media/images
        if any(
            pattern in url
            for pattern in ["/_images/", "/_static/", "/_sources/"]
        ):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        """Determine the documentation section type."""
        if "/tutorials/" in url:
            return "tutorial"

        # Check breadcrumb or page structure
        breadcrumb = soup.select_one(".breadcrumb")
        if breadcrumb:
            text = breadcrumb.get_text().lower()
            if "api" in text or "reference" in text:
                return "api"
            if "note" in text:
                return "notes"

        # Check for API-like content
        if soup.select(".class") or soup.select(".function"):
            return "api"

        return "reference"

    def _extract_module_name(self, url: str) -> str:
        """Extract module name from URL."""
        # Match patterns like torch.nn, torch.optim
        match = re.search(r"/docs/stable/(\w+(?:\.\w+)*)\.html", url)
        if match:
            return match.group(1)

        # Try from path
        match = re.search(r"/docs/stable/generated/(\w+(?:\.\w+)*)\.html", url)
        if match:
            return match.group(1)

        return ""

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        """Extract code examples from the page."""
        examples = []

        # Find code blocks
        for code_block in soup.select("div.highlight pre, pre.literal-block"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:  # Skip trivial snippets
                examples.append(code[:2000])  # Truncate long examples

        return examples[:10]  # Limit to 10 examples

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from PyTorch docs page."""
        # Try different content selectors
        content_elem = (
            soup.select_one("article.pytorch-article")
            or soup.select_one("div.pytorch-body")
            or soup.select_one("div.body")
            or soup.select_one("main")
        )

        if not content_elem:
            return ""

        # Remove navigation, header, footer elements
        for selector in [
            "nav",
            "header",
            "footer",
            ".headerlink",
            ".toctree-wrapper",
            "script",
            "style",
        ]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_breadcrumb(self, soup: BeautifulSoup) -> str:
        """Extract breadcrumb navigation."""
        breadcrumb = soup.select_one(".breadcrumb, nav[aria-label='breadcrumb']")
        if breadcrumb:
            items = breadcrumb.select("li, a")
            return " > ".join(item.get_text(strip=True) for item in items if item.get_text(strip=True))
        return ""

    def parse_page(self, url: str, html: str) -> DocPage | None:
        """Parse PyTorch documentation page."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_elem = (
            soup.select_one("h1")
            or soup.select_one("title")
        )
        title = title_elem.get_text(strip=True) if title_elem else ""

        # Clean up title
        title = re.sub(r"\s*—\s*PyTorch.*$", "", title)
        title = re.sub(r"\s*\|\s*PyTorch.*$", "", title)

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
            package="pytorch",
            version="stable",
            breadcrumb=breadcrumb or f"PyTorch > {module_name}" if module_name else "PyTorch",
            code_examples=code_examples,
        )

    def create_collection(self, client) -> None:
        """Create Weaviate collection for PyTorch docs."""
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)

        client.collections.create(
            name=self.collection_name,
            description="PyTorch documentation including API reference and tutorials",
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
                    description="Section type (api, tutorial, reference, notes)",
                ),
                wvc.config.Property(
                    name="package",
                    data_type=wvc.config.DataType.TEXT,
                    description="Package name (pytorch)",
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

    parser = argparse.ArgumentParser(description="PyTorch Documentation Scraper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape PyTorch documentation")
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
        scraper = PyTorchDocScraper(config=config)
        stats = scraper.scrape(
            resume=not args.no_resume,
            dry_run=args.dry_run,
        )
        print("\nScrape Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    elif args.command == "status":
        with WeaviateConnection() as client:
            if not client.collections.exists(PYTORCH_DOCS_COLLECTION):
                print(f"Collection '{PYTORCH_DOCS_COLLECTION}' does not exist")
                sys.exit(1)

            collection = client.collections.get(PYTORCH_DOCS_COLLECTION)
            response = collection.aggregate.over_all(total_count=True)
            print(f"Collection: {PYTORCH_DOCS_COLLECTION}")
            print(f"Total documents: {response.total_count}")

    elif args.command == "clean":
        with WeaviateConnection() as client:
            if client.collections.exists(PYTORCH_DOCS_COLLECTION):
                client.collections.delete(PYTORCH_DOCS_COLLECTION)
                print(f"Deleted collection: {PYTORCH_DOCS_COLLECTION}")
            else:
                print(f"Collection '{PYTORCH_DOCS_COLLECTION}' does not exist")


if __name__ == "__main__":
    main()
