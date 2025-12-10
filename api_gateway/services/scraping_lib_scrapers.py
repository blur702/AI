"""
Web Scraping Library Documentation Scrapers.

Scrapers for BeautifulSoup4 and Scrapy documentation.

Usage:
    python -m api_gateway.services.scraping_lib_scrapers beautifulsoup scrape
    python -m api_gateway.services.scraping_lib_scrapers scrapy scrape
    python -m api_gateway.services.scraping_lib_scrapers all scrape --limit 100
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

# Collection names
BS4_DOCS_COLLECTION = "BeautifulSoupDocs"
SCRAPY_DOCS_COLLECTION = "ScrapyDocs"


class BeautifulSoupDocScraper(BaseDocScraper):
    """Scraper for BeautifulSoup4 documentation."""

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig(
                min_delay=1.5,
                max_delay=3.5,
                batch_size=10,
                batch_pause_min=8.0,
                batch_pause_max=20.0,
                max_depth=4,  # BS4 docs are relatively flat
            )

        super().__init__(
            name="beautifulsoup_docs",
            base_url="https://www.crummy.com",
            collection_name=BS4_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        return [
            # Main documentation (single page, but comprehensive)
            "https://www.crummy.com/software/BeautifulSoup/bs4/doc/",
            # Older version docs for reference
            "https://www.crummy.com/software/BeautifulSoup/bs4/doc.zh/",
        ]

    def is_valid_url(self, url: str) -> bool:
        if not super().is_valid_url(url):
            return False

        # Must be BeautifulSoup docs
        if "/BeautifulSoup/" not in url:
            return False

        # Skip non-doc pages
        if any(pattern in url for pattern in ["/download/", "/discussion/"]):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        # BS4 docs are mostly a single page with sections
        return "reference"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_elem = soup.select_one("body") or soup.select_one("main")
        if not content_elem:
            return ""

        for selector in ["nav", "header", "footer", "script", "style"]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        examples = []
        for code_block in soup.select("pre, div.highlight pre"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:
                examples.append(code[:2000])
        return examples[:15]  # BS4 has many examples

    def parse_page(self, url: str, html: str) -> DocPage | None:
        soup = BeautifulSoup(html, "html.parser")

        title_elem = soup.select_one("h1") or soup.select_one("title")
        title = title_elem.get_text(strip=True) if title_elem else "Beautiful Soup Documentation"

        content = self._extract_content(soup)
        if not content or len(content) < 100:
            return None

        return DocPage(
            url=url,
            title=title,
            content=content,
            section=self._determine_section(url, soup),
            package="beautifulsoup4",
            version="4",
            code_examples=self._extract_code_examples(soup),
        )

    def create_collection(self, client) -> None:
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)
        client.collections.create(
            name=self.collection_name,
            description="BeautifulSoup4 HTML/XML parsing library documentation",
            vectorizer_config=wvc.config.Configure.Vectorizer.none(),
            properties=[
                wvc.config.Property(name="url", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="title", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="content", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="section", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="package", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="version", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="breadcrumb", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="code_examples", data_type=wvc.config.DataType.TEXT),
            ],
        )


class ScrapyDocScraper(BaseDocScraper):
    """Scraper for Scrapy documentation."""

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig(
                min_delay=1.5,
                max_delay=4.0,
                batch_size=15,
                batch_pause_min=10.0,
                batch_pause_max=25.0,
                max_depth=6,
            )

        super().__init__(
            name="scrapy_docs",
            base_url="https://docs.scrapy.org",
            collection_name=SCRAPY_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        return [
            # Main documentation
            "https://docs.scrapy.org/en/latest/",
            "https://docs.scrapy.org/en/latest/intro/overview.html",
            "https://docs.scrapy.org/en/latest/intro/tutorial.html",
            # Core concepts
            "https://docs.scrapy.org/en/latest/topics/spiders.html",
            "https://docs.scrapy.org/en/latest/topics/selectors.html",
            "https://docs.scrapy.org/en/latest/topics/items.html",
            "https://docs.scrapy.org/en/latest/topics/item-pipeline.html",
            "https://docs.scrapy.org/en/latest/topics/loaders.html",
            # Advanced
            "https://docs.scrapy.org/en/latest/topics/request-response.html",
            "https://docs.scrapy.org/en/latest/topics/downloader-middleware.html",
            "https://docs.scrapy.org/en/latest/topics/spider-middleware.html",
            "https://docs.scrapy.org/en/latest/topics/extensions.html",
            # Settings and configuration
            "https://docs.scrapy.org/en/latest/topics/settings.html",
            "https://docs.scrapy.org/en/latest/topics/autothrottle.html",
            # API Reference
            "https://docs.scrapy.org/en/latest/topics/api.html",
        ]

    def is_valid_url(self, url: str) -> bool:
        if not super().is_valid_url(url):
            return False

        if not "/en/latest/" in url:
            return False

        if any(pattern in url for pattern in ["/_modules/", "/_sources/"]):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        if "/intro/" in url:
            return "tutorial"
        if "/topics/api" in url or "/api/" in url:
            return "api"
        if "/topics/" in url:
            return "guide"
        return "reference"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_elem = (
            soup.select_one("div.document")
            or soup.select_one("div[role='main']")
            or soup.select_one("main")
        )
        if not content_elem:
            return ""

        for selector in ["nav", ".sphinxsidebar", ".related", "script", "style"]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        examples = []
        for code_block in soup.select("div.highlight pre, pre.literal-block"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:
                examples.append(code[:2000])
        return examples[:10]

    def parse_page(self, url: str, html: str) -> DocPage | None:
        soup = BeautifulSoup(html, "html.parser")

        title_elem = soup.select_one("h1") or soup.select_one("title")
        title = title_elem.get_text(strip=True) if title_elem else ""
        title = re.sub(r"\s*—\s*Scrapy.*$", "", title)
        title = re.sub(r"¶$", "", title)

        if not title:
            return None

        content = self._extract_content(soup)
        if not content or len(content) < 100:
            return None

        return DocPage(
            url=url,
            title=title,
            content=content,
            section=self._determine_section(url, soup),
            package="scrapy",
            version="latest",
            code_examples=self._extract_code_examples(soup),
        )

    def create_collection(self, client) -> None:
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)
        client.collections.create(
            name=self.collection_name,
            description="Scrapy web crawling framework documentation",
            vectorizer_config=wvc.config.Configure.Vectorizer.none(),
            properties=[
                wvc.config.Property(name="url", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="title", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="content", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="section", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="package", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="version", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="breadcrumb", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="code_examples", data_type=wvc.config.DataType.TEXT),
            ],
        )


# Mapping of library names to scraper classes
SCRAPERS = {
    "beautifulsoup": BeautifulSoupDocScraper,
    "scrapy": ScrapyDocScraper,
}


def main():
    """CLI entry point."""
    import argparse
    import sys

    from api_gateway.services.weaviate_connection import WeaviateConnection

    parser = argparse.ArgumentParser(description="Web Scraping Library Documentation Scrapers")
    parser.add_argument(
        "library",
        choices=["beautifulsoup", "scrapy", "all"],
        help="Library to scrape",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape_parser = subparsers.add_parser("scrape", help="Scrape documentation")
    scrape_parser.add_argument("--limit", type=int, default=0, help="Max pages")
    scrape_parser.add_argument("--dry-run", action="store_true")
    scrape_parser.add_argument("--no-resume", action="store_true")

    subparsers.add_parser("status", help="Show collection status")
    subparsers.add_parser("clean", help="Delete collection")

    args = parser.parse_args()

    # Get scrapers to run
    if args.library == "all":
        scrapers_to_run = list(SCRAPERS.items())
    else:
        scrapers_to_run = [(args.library, SCRAPERS[args.library])]

    if args.command == "scrape":
        for name, scraper_class in scrapers_to_run:
            print(f"\n{'='*50}")
            print(f"Scraping {name} documentation...")
            print(f"{'='*50}")

            config = ScraperConfig(max_pages=args.limit) if args.limit > 0 else None
            scraper = scraper_class(config=config)
            stats = scraper.scrape(resume=not args.no_resume, dry_run=args.dry_run)

            print(f"\n{name.title()} Statistics:")
            for key, value in stats.items():
                print(f"  {key}: {value}")

    elif args.command == "status":
        with WeaviateConnection() as client:
            for name, scraper_class in scrapers_to_run:
                collection_name = scraper_class(ScraperConfig()).collection_name
                if client.collections.exists(collection_name):
                    collection = client.collections.get(collection_name)
                    response = collection.aggregate.over_all(total_count=True)
                    print(f"{name}: {response.total_count} documents")
                else:
                    print(f"{name}: Collection does not exist")

    elif args.command == "clean":
        with WeaviateConnection() as client:
            for name, scraper_class in scrapers_to_run:
                collection_name = scraper_class(ScraperConfig()).collection_name
                if client.collections.exists(collection_name):
                    client.collections.delete(collection_name)
                    print(f"Deleted {name} collection")
                else:
                    print(f"{name} collection does not exist")


if __name__ == "__main__":
    main()
