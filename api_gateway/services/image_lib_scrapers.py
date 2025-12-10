"""
Image Library Documentation Scrapers.

Scrapers for Pillow (PIL) and OpenCV documentation.

Usage:
    python -m api_gateway.services.image_lib_scrapers pillow scrape
    python -m api_gateway.services.image_lib_scrapers opencv scrape
    python -m api_gateway.services.image_lib_scrapers all scrape --limit 100
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
PILLOW_DOCS_COLLECTION = "PillowDocs"
OPENCV_DOCS_COLLECTION = "OpenCVDocs"


class PillowDocScraper(BaseDocScraper):
    """Scraper for Pillow (PIL Fork) documentation."""

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
            name="pillow_docs",
            base_url="https://pillow.readthedocs.io",
            collection_name=PILLOW_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        return [
            "https://pillow.readthedocs.io/en/stable/",
            "https://pillow.readthedocs.io/en/stable/handbook/index.html",
            "https://pillow.readthedocs.io/en/stable/handbook/tutorial.html",
            "https://pillow.readthedocs.io/en/stable/handbook/concepts.html",
            "https://pillow.readthedocs.io/en/stable/reference/index.html",
            "https://pillow.readthedocs.io/en/stable/reference/Image.html",
            "https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html",
            "https://pillow.readthedocs.io/en/stable/reference/ImageFilter.html",
            "https://pillow.readthedocs.io/en/stable/reference/ImageEnhance.html",
            "https://pillow.readthedocs.io/en/stable/reference/ImageOps.html",
            "https://pillow.readthedocs.io/en/stable/reference/ImageColor.html",
            "https://pillow.readthedocs.io/en/stable/reference/ImageFont.html",
        ]

    def is_valid_url(self, url: str) -> bool:
        if not super().is_valid_url(url):
            return False
        if "/en/stable/" not in url:
            return False
        if "/_modules/" in url or "/_sources/" in url:
            return False
        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        if "/handbook/" in url:
            if "tutorial" in url:
                return "tutorial"
            return "guide"
        if "/reference/" in url:
            return "api"
        return "reference"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_elem = (
            soup.select_one("div[role='main']")
            or soup.select_one("div.document")
            or soup.select_one("main")
        )
        if not content_elem:
            return ""

        for selector in ["nav", ".sphinxsidebar", "script", "style"]:
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
        title = re.sub(r"\s*—\s*Pillow.*$", "", title)
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
            package="pillow",
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
            description="Pillow (PIL Fork) image processing library documentation",
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


class OpenCVDocScraper(BaseDocScraper):
    """Scraper for OpenCV-Python documentation."""

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig(
                min_delay=2.0,
                max_delay=5.0,
                batch_size=12,
                batch_pause_min=15.0,
                batch_pause_max=35.0,
                max_depth=8,
            )

        super().__init__(
            name="opencv_docs",
            base_url="https://docs.opencv.org",
            collection_name=OPENCV_DOCS_COLLECTION,
            config=config,
        )

    def get_seed_urls(self) -> list[str]:
        return [
            # Main documentation
            "https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html",
            "https://docs.opencv.org/4.x/d0/de3/tutorial_py_intro.html",
            # Core operations
            "https://docs.opencv.org/4.x/d7/d16/tutorial_py_table_of_contents_core.html",
            # Image processing
            "https://docs.opencv.org/4.x/d2/d96/tutorial_py_table_of_contents_imgproc.html",
            # Feature detection
            "https://docs.opencv.org/4.x/db/d27/tutorial_py_table_of_contents_feature2d.html",
            # Video analysis
            "https://docs.opencv.org/4.x/da/dd0/tutorial_table_of_content_video.html",
            # Camera calibration
            "https://docs.opencv.org/4.x/d9/db7/tutorial_py_table_of_contents_calib3d.html",
            # Machine learning
            "https://docs.opencv.org/4.x/d6/de2/tutorial_py_table_of_contents_ml.html",
            # Object detection
            "https://docs.opencv.org/4.x/d2/d64/tutorial_table_of_content_objdetect.html",
            # API reference modules
            "https://docs.opencv.org/4.x/modules.html",
        ]

    def is_valid_url(self, url: str) -> bool:
        if not super().is_valid_url(url):
            return False

        # Must be 4.x docs (latest stable)
        if "/4.x/" not in url:
            return False

        # Skip sources and media
        if any(pattern in url for pattern in ["/_sources/", "/_images/", ".png", ".jpg"]):
            return False

        return True

    def _determine_section(self, url: str, soup: BeautifulSoup) -> str:
        if "tutorial" in url:
            return "tutorial"
        if "/modules/" in url or "/group__" in url:
            return "api"
        return "reference"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_elem = (
            soup.select_one("div.contents")
            or soup.select_one("div.doc-content")
            or soup.select_one("article")
            or soup.select_one("main")
        )
        if not content_elem:
            return ""

        for selector in ["nav", ".toc", ".sidebar", "script", "style"]:
            for elem in content_elem.select(selector):
                elem.decompose()

        return content_elem.get_text(separator="\n", strip=True)

    def _extract_code_examples(self, soup: BeautifulSoup) -> list[str]:
        examples = []
        for code_block in soup.select("div.fragment, pre.code, div.highlight pre"):
            code = code_block.get_text(strip=True)
            if code and len(code) > 20:
                # Filter Python code (OpenCV docs have C++/Java/Python)
                if "import cv2" in code or "cv2." in code or "import numpy" in code:
                    examples.append(code[:2000])
        return examples[:10]

    def parse_page(self, url: str, html: str) -> DocPage | None:
        soup = BeautifulSoup(html, "html.parser")

        title_elem = soup.select_one("h1") or soup.select_one("title")
        title = title_elem.get_text(strip=True) if title_elem else ""
        title = re.sub(r"\s*-\s*OpenCV.*$", "", title)

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
            package="opencv-python",
            version="4.x",
            code_examples=self._extract_code_examples(soup),
        )

    def create_collection(self, client) -> None:
        if client.collections.exists(self.collection_name):
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info("Creating collection: %s", self.collection_name)
        client.collections.create(
            name=self.collection_name,
            description="OpenCV-Python computer vision library documentation",
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
    "pillow": PillowDocScraper,
    "opencv": OpenCVDocScraper,
}


def main():
    """CLI entry point."""
    import argparse

    from api_gateway.services.weaviate_connection import WeaviateConnection

    parser = argparse.ArgumentParser(description="Image Library Documentation Scrapers")
    parser.add_argument(
        "library",
        choices=["pillow", "opencv", "all"],
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
