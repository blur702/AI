"""
Web Framework Documentation Scrapers.

Scrapers for Django, Flask, and FastAPI documentation.

Usage:
    python -m api_gateway.services.web_framework_scrapers django scrape
    python -m api_gateway.services.web_framework_scrapers flask scrape
    python -m api_gateway.services.web_framework_scrapers fastapi scrape
    python -m api_gateway.services.web_framework_scrapers all scrape --limit 100
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

# Collection names
DJANGO_DOCS_COLLECTION = "DjangoDocs"
FLASK_DOCS_COLLECTION = "FlaskDocs"
FASTAPI_DOCS_COLLECTION = "FastAPIDocs"


class DjangoDocScraper(BaseDocScraper):
    """Scraper for Django documentation."""

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig(
                min_delay=1.5,
                max_delay=4.0,
                batch_size=15,
                batch_pause_min=10.0,
                batch_pause_max=30.0,
                max_depth=8,
            )

        super().__init__(
            name="django_docs",
            base_url="https://docs.djangoproject.com",
            collection_name=DJANGO_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        return [
            # Latest stable version
            "https://docs.djangoproject.com/en/stable/",
            "https://docs.djangoproject.com/en/stable/intro/",
            "https://docs.djangoproject.com/en/stable/topics/",
            "https://docs.djangoproject.com/en/stable/ref/",
            "https://docs.djangoproject.com/en/stable/howto/",
            # Key topics
            "https://docs.djangoproject.com/en/stable/topics/db/models/",
            "https://docs.djangoproject.com/en/stable/topics/http/views/",
            "https://docs.djangoproject.com/en/stable/topics/forms/",
            "https://docs.djangoproject.com/en/stable/topics/templates/",
            "https://docs.djangoproject.com/en/stable/topics/auth/",
            "https://docs.djangoproject.com/en/stable/ref/contrib/admin/",
            # API Reference
            "https://docs.djangoproject.com/en/stable/ref/models/",
            "https://docs.djangoproject.com/en/stable/ref/views/",
        ]

    def is_valid_url(self, url: str) -> bool:
        if not super().is_valid_url(url):
            return False

        # Must be English stable docs
        if not ("/en/stable/" in url or "/en/5." in url or "/en/4." in url):
            return False

        # Skip version-specific old docs
        if re.search(r"/en/[123]\.\d+/", url):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        if "/intro/" in url:
            return "tutorial"
        if "/howto/" in url:
            return "howto"
        if "/ref/" in url:
            return "api"
        if "/topics/" in url:
            return "guide"
        return "reference"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_elem = soup.select_one("#docs-content") or soup.select_one("main")
        if not content_elem:
            return ""

        for selector in ["nav", ".toc", "script", "style"]:
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
        title = re.sub(r"\s*\|\s*Django.*$", "", title)
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
            package="django",
            version="stable",
            code_examples=self._extract_code_examples(soup),
        )

    def create_collection(self, client) -> None:
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)
        self._create_doc_collection(client, "Django web framework documentation")

    def _create_doc_collection(self, client, description: str) -> None:
        client.collections.create(
            name=self.collection_name,
            description=description,
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


class FlaskDocScraper(BaseDocScraper):
    """Scraper for Flask documentation."""

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
            name="flask_docs",
            base_url="https://flask.palletsprojects.com",
            collection_name=FLASK_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        return [
            "https://flask.palletsprojects.com/en/stable/",
            "https://flask.palletsprojects.com/en/stable/quickstart/",
            "https://flask.palletsprojects.com/en/stable/tutorial/",
            "https://flask.palletsprojects.com/en/stable/patterns/",
            "https://flask.palletsprojects.com/en/stable/api/",
            "https://flask.palletsprojects.com/en/stable/config/",
            "https://flask.palletsprojects.com/en/stable/blueprints/",
            "https://flask.palletsprojects.com/en/stable/extensions/",
        ]

    def is_valid_url(self, url: str) -> bool:
        if not super().is_valid_url(url):
            return False
        if not ("/en/stable/" in url or "/en/latest/" in url or "/en/3." in url):
            return False
        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        if "/quickstart/" in url or "/tutorial/" in url:
            return "tutorial"
        if "/api/" in url:
            return "api"
        if "/patterns/" in url:
            return "patterns"
        return "reference"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_elem = soup.select_one("div.document") or soup.select_one("main")
        if not content_elem:
            return ""

        for selector in ["nav", ".sphinxsidebar", "script", "style"]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        examples = []
        for code_block in soup.select("div.highlight pre"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:
                examples.append(code[:2000])
        return examples[:10]

    def parse_page(self, url: str, html: str) -> DocPage | None:
        soup = BeautifulSoup(html, "html.parser")

        title_elem = soup.select_one("h1") or soup.select_one("title")
        title = title_elem.get_text(strip=True) if title_elem else ""
        title = re.sub(r"\s*—\s*Flask.*$", "", title)
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
            package="flask",
            version="stable",
            code_examples=self._extract_code_examples(soup),
        )

    def create_collection(self, client) -> None:
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)
        client.collections.create(
            name=self.collection_name,
            description="Flask micro-framework documentation",
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


class FastAPIDocScraper(BaseDocScraper):
    """Scraper for FastAPI documentation."""

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
            name="fastapi_docs",
            base_url="https://fastapi.tiangolo.com",
            collection_name=FASTAPI_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        return [
            "https://fastapi.tiangolo.com/",
            "https://fastapi.tiangolo.com/tutorial/",
            "https://fastapi.tiangolo.com/tutorial/first-steps/",
            "https://fastapi.tiangolo.com/tutorial/path-params/",
            "https://fastapi.tiangolo.com/tutorial/query-params/",
            "https://fastapi.tiangolo.com/tutorial/body/",
            "https://fastapi.tiangolo.com/tutorial/dependencies/",
            "https://fastapi.tiangolo.com/tutorial/security/",
            "https://fastapi.tiangolo.com/advanced/",
            "https://fastapi.tiangolo.com/reference/",
        ]

    def is_valid_url(self, url: str) -> bool:
        if not super().is_valid_url(url):
            return False

        # Skip non-English
        if re.search(r"/(de|es|fr|it|ja|ko|pl|pt|ru|tr|zh|uk)/", url):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        if "/tutorial/" in url:
            return "tutorial"
        if "/advanced/" in url:
            return "advanced"
        if "/reference/" in url:
            return "api"
        return "reference"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_elem = soup.select_one("article") or soup.select_one("main")
        if not content_elem:
            return ""

        for selector in ["nav", ".md-sidebar", "script", "style"]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        examples = []
        for code_block in soup.select("div.highlight pre, pre code"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:
                examples.append(code[:2000])
        return examples[:10]

    def parse_page(self, url: str, html: str) -> DocPage | None:
        soup = BeautifulSoup(html, "html.parser")

        title_elem = soup.select_one("h1") or soup.select_one("title")
        title = title_elem.get_text(strip=True) if title_elem else ""
        title = re.sub(r"\s*-\s*FastAPI.*$", "", title)

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
            package="fastapi",
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
            description="FastAPI modern web framework documentation",
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


# Mapping of framework names to scraper classes
SCRAPERS = {
    "django": DjangoDocScraper,
    "flask": FlaskDocScraper,
    "fastapi": FastAPIDocScraper,
}


def main():
    """CLI entry point."""
    import argparse

    from api_gateway.services.weaviate_connection import WeaviateConnection

    parser = argparse.ArgumentParser(description="Web Framework Documentation Scrapers")
    parser.add_argument(
        "framework",
        choices=["django", "flask", "fastapi", "all"],
        help="Framework to scrape",
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
    if args.framework == "all":
        scrapers_to_run = list(SCRAPERS.items())
    else:
        scrapers_to_run = [(args.framework, SCRAPERS[args.framework])]

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
