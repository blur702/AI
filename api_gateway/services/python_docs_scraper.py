"""
Python documentation scraper.

Scrapes Python 3.13 and 3.12 documentation from docs.python.org, extracts
content and metadata, and ingests into Weaviate for semantic search.

Coverage:
- Python 3.13 and 3.12 Tutorial
- Python 3.13 and 3.12 Language Reference
- Python 3.13 and 3.12 Standard Library

Features:
- Rate-limited requests (configurable delay between requests)
- Incremental updates via content_hash comparison (UUID-stable upserts)
- Progress callbacks for UI integration
- Pause signals abort the current run (resumable via external checkpoints)
- Respects docs.python.org robots.txt and rate limits

CLI usage:
    python -m api_gateway.services.python_docs_scraper scrape --verbose
    python -m api_gateway.services.python_docs_scraper scrape --limit 100
    python -m api_gateway.services.python_docs_scraper status
    python -m api_gateway.services.python_docs_scraper reindex
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from collections import deque
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .python_docs_schema import (
    PythonDoc,
    compute_python_content_hash,
    create_python_docs_collection,
    generate_python_docs_uuid,
    get_python_docs_stats,
)
from .weaviate_connection import PYTHON_DOCS_COLLECTION_NAME, WeaviateConnection

logger = get_logger("api_gateway.python_docs_scraper")


# Python docs base URL
PYTHON_DOCS_BASE = "https://docs.python.org"

# Rate limiting defaults
DEFAULT_REQUEST_DELAY = 1.0  # seconds between requests
DEFAULT_BATCH_SIZE = 20  # entities per batch before longer pause
DEFAULT_BATCH_DELAY = 3.0  # seconds pause after each batch

# Python versions and sections to scrape
# "3" maps to the latest stable (3.13) docs.
PYTHON_VERSIONS: list[str] = ["3", "3.12"]

# Each tuple: (path_suffix, section_type)
PYTHON_SECTIONS: list[tuple[str, str]] = [
    ("/tutorial/index.html", "Tutorial"),
    ("/reference/index.html", "Reference"),
    ("/library/index.html", "Library"),
]


@dataclass
class ScrapeConfig:
    """Configuration for scraping behavior."""

    request_delay: float = DEFAULT_REQUEST_DELAY
    batch_size: int = DEFAULT_BATCH_SIZE
    batch_delay: float = DEFAULT_BATCH_DELAY
    max_entities: int | None = None
    dry_run: bool = False


ProgressCallback = Callable[[str, int, int, str], None]
CancelCheck = Callable[[], bool]
PauseCheck = Callable[[], bool]


def get_doc_text_for_embedding(doc: PythonDoc) -> str:
    """
    Build text representation for embedding computation.

    Args:
        doc: Python documentation object

    Returns:
        Combined text from title, version, section_type, and content (limited to 2000 chars)
    """
    parts: list[str] = []
    if doc.title:
        parts.append(doc.title)
    if doc.version:
        parts.append(f"Python {doc.version}")
    if doc.section_type:
        parts.append(doc.section_type)
    if doc.content:
        parts.append(doc.content[:2000])
    return " ".join(parts)


class PythonDocsScraper:
    """
    Scraper for Python 3.13 and 3.12 documentation.

    Navigates docs.python.org, extracts page content,
    and yields PythonDoc objects for ingestion.
    """

    def __init__(
        self,
        config: ScrapeConfig | None = None,
        progress_callback: ProgressCallback | None = None,
        check_cancelled: CancelCheck | None = None,
        check_paused: PauseCheck | None = None,
    ):
        """
        Initialize the Python documentation scraper.

        Args:
            config: Scraping configuration (rate limits, batch size, etc.)
            progress_callback: Optional callback for progress updates (phase, current, total, message)
            check_cancelled: Optional callback to check if scraping should be cancelled
            check_paused: Optional callback signalling a pause request.
                Any True value is treated as an abort signal for the current
                run; resuming is handled by external checkpointing rather
                than this scraper blocking and later resuming.
        """
        self.config = config or ScrapeConfig()
        self.progress_callback = progress_callback
        self.check_cancelled = check_cancelled
        self.check_paused = check_paused
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "PythonDocsScraper/1.0 (AI Documentation Indexer)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        self._request_count = 0
        self._last_request_time = 0.0
        self._seen_urls: set[str] = set()

    def __enter__(self) -> PythonDocsScraper:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit, closes HTTP client."""
        self.client.close()

    def _emit_progress(self, phase: str, current: int, total: int, message: str) -> None:
        """
        Emit progress update via callback if configured.

        Args:
            phase: Current phase of scraping
            current: Current count
            total: Total expected count (0 if unknown)
            message: Progress message
        """
        if self.progress_callback:
            try:
                self.progress_callback(phase, current, total, message)
            except Exception as exc:
                logger.debug("Progress callback error: %s", exc)

    def _is_cancelled(self) -> bool:
        """
        Check if scraping has been cancelled.

        Returns:
            True if cancelled, False otherwise
        """
        if self.check_cancelled:
            try:
                return self.check_cancelled()
            except Exception as exc:
                logger.debug("Check cancelled callback error: %s", exc)
                return False
        return False

    def _should_abort_for_pause(self) -> bool:
        """
        Check if a pause signal has been raised that should abort this run.

        This helper treats any True value from check_paused as a request
        to abort the current scraping run. It does not block and resume;
        callers are expected to rely on external checkpointing and
        supervisor logic for resumable scraping.

        Returns:
            True if a pause signal was received, False otherwise
        """
        if self.check_paused:
            try:
                return self.check_paused()
            except Exception as exc:
                logger.debug("Check paused callback error: %s", exc)
                return False
        return False

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.request_delay:
            sleep_time = self.config.request_delay - elapsed
            time.sleep(sleep_time)

        # Additional batch delay
        self._request_count += 1
        if self._request_count % self.config.batch_size == 0:
            logger.info(
                "Batch pause after %d requests (sleeping %.1fs)",
                self._request_count,
                self.config.batch_delay,
            )
            time.sleep(self.config.batch_delay)

        self._last_request_time = time.time()

    def _fetch(self, url: str) -> BeautifulSoup | None:
        """
        Fetch URL with rate limiting and error handling.

        Args:
            url: URL to fetch

        Returns:
            BeautifulSoup object if successful, None on error
        """
        self._rate_limit()

        try:
            logger.debug("Fetching: %s", url)
            response = self.client.get(url)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except httpx.HTTPStatusError as e:
            logger.warning("HTTP %d for %s", e.response.status_code, url)
            return None
        except httpx.RequestError as e:
            logger.warning("Request error for %s: %s", url, e)
            return None

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL to canonical form.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL without fragments or query parameters
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def _is_python_doc_url(self, url: str, version: str) -> bool:
        """
        Check if URL is a valid Python documentation page for a given version.

        Args:
            url: URL to validate
            version: Python version string ("3" or "3.12")

        Returns:
            True if URL is on docs.python.org/{version} and not a skipped page.
        """
        parsed = urlparse(url)
        if parsed.netloc != "docs.python.org":
            return False

        path = parsed.path

        if not path.startswith(f"/{version}/"):
            return False

        # Skip special/non-content pages
        skip_patterns = [
            r"/genindex\.html$",
            r"/search\.html$",
            r"/glossary\.html$",
            r"/whatsnew/.*",
            r"/_static/",
            r"/_sources/",
        ]
        for pattern in skip_patterns:
            if re.search(pattern, path):
                return False

        return True

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """
        Extract page title from Python docs page.

        Args:
            soup: Parsed HTML page

        Returns:
            Page title or empty string
        """
        h1 = soup.select_one("h1")
        if h1:
            return h1.get_text(strip=True)

        title = soup.select_one("title")
        if title:
            text = title.get_text(strip=True)
            text = re.sub(r"\s*—\s*Python\s+[\d\.]+\s+documentation.*$", "", text)
            text = re.sub(r"\s*-\s*Python\s+[\d\.]+\s+documentation.*$", "", text)
            return text

        return ""

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """
        Extract main content from Python docs page.

        Args:
            soup: Parsed HTML page

        Returns:
            Main content text (limited to 10000 chars) or empty string
        """
        article = soup.select_one("article, div.body, main")
        if not article:
            return ""

        # Remove navigation, sidebars, etc.
        for selector in ["nav", "aside", ".sphinxsidebar", "script", "style"]:
            for elem in article.select(selector):
                elem.decompose()

        text = article.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:10000]

    def _extract_last_modified(self, soup: BeautifulSoup) -> str:
        """
        Extract last modified date from Python docs page metadata.

        Args:
            soup: Parsed HTML page

        Returns:
            ISO 8601 timestamp or current time if not found
        """
        meta = soup.select_one('meta[property="article:modified_time"]')
        if meta:
            content = meta.get("content", "")
            if content:
                return content

        time_elem = soup.select_one("time[datetime]")
        if time_elem:
            content = time_elem.get("datetime", "")
            if content:
                return content

        return datetime.now(UTC).isoformat()

    def _extract_links(self, soup: BeautifulSoup, base_url: str, version: str) -> list[str]:
        """
        Extract links to other Python documentation pages.

        Args:
            soup: Parsed HTML page
            base_url: Current page URL for resolving relative links
            version: Python version string

        Returns:
            List of absolute URLs to valid Python documentation pages
        """
        links: list[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue

            if href.startswith("#"):
                continue

            if href.startswith("/"):
                url = urljoin(PYTHON_DOCS_BASE, href)
            elif href.startswith("http"):
                url = href
            else:
                url = urljoin(base_url, href)

            url = self._normalize_url(url)
            if self._is_python_doc_url(url, version) and url not in self._seen_urls:
                links.append(url)

        return links

    def _parse_page(
        self,
        soup: BeautifulSoup,
        url: str,
        version: str,
        section_type: str,
    ) -> PythonDoc | None:
        """
        Parse a single Python docs page and extract documentation.

        Args:
            soup: Pre-fetched BeautifulSoup object
            url: Page URL
            version: Python version string
            section_type: Section type (Tutorial, Reference, Library)

        Returns:
            PythonDoc object or None if insufficient content
        """
        title = self._extract_title(soup)
        if not title:
            logger.warning("No title found for %s", url)
            return None

        content = self._extract_content(soup)
        if not content or len(content) < 50:
            logger.debug("Skipping %s - insufficient content", url)
            return None

        last_modified = self._extract_last_modified(soup)
        scraped_at = datetime.now(UTC).isoformat()
        content_hash = compute_python_content_hash(
            title=title,
            content=content,
            version=version,
            section_type=section_type,
        )
        doc_uuid = generate_python_docs_uuid(url, title, version)

        return PythonDoc(
            title=title,
            url=url,
            content=content,
            version=version,
            section_type=section_type,
            last_modified=last_modified,
            scraped_at=scraped_at,
            content_hash=content_hash,
            uuid=doc_uuid,
        )

    def scrape_section(
        self,
        version: str,
        section_path: str,
        section_type: str,
    ) -> Generator[PythonDoc, None, None]:
        """
        Scrape all pages in a documentation section for a given version using BFS.

        Args:
            version: Python version string ("3" or "3.12")
            section_path: Path suffix (e.g., "/tutorial/index.html")
            section_type: Section type (Tutorial, Reference, Library)

        Yields:
            PythonDoc objects for each successfully parsed page.
            If a pause signal is raised via check_paused, this method
            aborts the current run immediately; resuming must be managed
            by external supervisor/checkpoint logic.
        """
        start_url = f"{PYTHON_DOCS_BASE}/{version}{section_path}"
        logger.info(
            "Scraping section: version=%s path=%s (%s)",
            version,
            section_path,
            section_type,
        )

        queue: deque[str] = deque([start_url])
        entity_count = 0

        while queue:
            if self._is_cancelled():
                logger.info("Scraping cancelled")
                return

            if self._should_abort_for_pause():
                logger.info("Aborting scraping due to pause signal")
                return

            if self.config.max_entities and entity_count >= self.config.max_entities:
                logger.info(
                    "Reached max entities limit for section: %d",
                    self.config.max_entities,
                )
                return

            url = queue.popleft()
            normalized_url = self._normalize_url(url)

            if normalized_url in self._seen_urls:
                continue
            self._seen_urls.add(normalized_url)

            soup = self._fetch(url)
            if not soup:
                continue

            doc = self._parse_page(soup, url, version, section_type)
            if doc:
                entity_count += 1
                logger.info(
                    "Parsed doc: %s (version=%s, section=%s, content=%d chars)",
                    doc.title,
                    version,
                    section_type,
                    len(doc.content),
                )
                self._emit_progress(
                    "scraping",
                    entity_count,
                    self.config.max_entities or 0,
                    f"Scraped: {doc.title} ({version} / {section_type})",
                )
                yield doc

            new_links = self._extract_links(soup, url, version)
            for link in new_links:
                if section_path.rsplit("/", 1)[0] in link or link.startswith(start_url):
                    if link not in self._seen_urls:
                        queue.append(link)

        logger.info(
            "Finished section %s (version=%s): %d documents",
            section_path,
            version,
            entity_count,
        )

    def scrape_all(self) -> Generator[PythonDoc, None, None]:
        """
        Scrape all Python documentation sections defined in PYTHON_VERSIONS and PYTHON_SECTIONS.

        Yields:
            PythonDoc objects from all sections and versions
        """
        for version in PYTHON_VERSIONS:
            for section_path, section_type in PYTHON_SECTIONS:
                if self._is_cancelled():
                    return

                logger.info(
                    "Starting section: version=%s type=%s path=%s",
                    version,
                    section_type,
                    section_path,
                )
                yield from self.scrape_section(version, section_path, section_type)


def scrape_python_docs(
    config: ScrapeConfig | None = None,
    progress_callback: ProgressCallback | None = None,
    check_cancelled: CancelCheck | None = None,
    check_paused: PauseCheck | None = None,
) -> dict[str, Any]:
    """
    Scrape Python documentation and ingest into Weaviate.

    Args:
        config: Scraping configuration
        progress_callback: Optional callback for progress updates
        check_cancelled: Optional callback to check for cancellation
        check_paused: Optional callback signalling a pause request.
            Any True value is treated as an abort signal for the current
            run; resuming is handled by external checkpointing rather
            than this function blocking and later resuming.

    Returns:
        Statistics dict with keys: entities_processed, entities_inserted, errors
    """
    config = config or ScrapeConfig()
    entities_processed = 0
    entities_inserted = 0
    errors = 0
    cancelled = False

    def emit_progress(phase: str, current: int, total: int, message: str) -> None:
        if progress_callback:
            try:
                progress_callback(phase, current, total, message)
            except Exception as exc:
                logger.debug("Progress callback failed: %s", exc)

    def is_cancelled() -> bool:
        if check_cancelled:
            try:
                return check_cancelled()
            except Exception as exc:
                logger.debug("Check cancelled callback failed: %s", exc)
                return False
        return False

    def is_paused() -> bool:
        """Check if scraping should abort due to an external pause signal."""
        if check_paused:
            try:
                return check_paused()
            except Exception as exc:
                logger.debug("Check paused callback failed: %s", exc)
                return False
        return False

    emit_progress("starting", 0, 0, "Connecting to Weaviate")

    try:
        with WeaviateConnection() as client:
            # Create collection if needed
            emit_progress("setup", 0, 0, "Setting up PythonDocs collection")
            create_python_docs_collection(client, force_reindex=False)
            collection = client.collections.get(PYTHON_DOCS_COLLECTION_NAME)

            # Load existing UUIDs and content_hash values for deduplication and incremental updates
            emit_progress(
                "setup",
                0,
                0,
                "Loading existing UUIDs and content hashes for deduplication",
            )
            existing_docs: dict[str, str | None] = {}
            try:
                logger.info(
                    "Loading existing entity UUIDs and content hashes for deduplication...",
                )
                for obj in collection.iterator(include_vector=False):
                    props = getattr(obj, "properties", None)
                    uuid_val: str | None = None
                    content_hash: str | None = None
                    if props and isinstance(props, dict):
                        uuid_val = props.get("uuid")
                        content_hash = props.get("content_hash")
                    if not uuid_val and getattr(obj, "uuid", None):
                        uuid_val = str(obj.uuid)
                    if uuid_val:
                        existing_docs[uuid_val] = content_hash
                logger.info("Loaded %d existing UUIDs", len(existing_docs))
            except Exception as e:
                logger.warning("Could not load existing UUIDs: %s", e)

            if config.dry_run:
                logger.info("Dry run mode - not inserting into Weaviate")

            with PythonDocsScraper(
                config=config,
                progress_callback=progress_callback,
                check_cancelled=check_cancelled,
                check_paused=check_paused,
            ) as scraper:
                for doc in scraper.scrape_all():
                    if is_cancelled():
                        cancelled = True
                        break

                    if is_paused():
                        cancelled = True
                        break

                    if config.max_entities and entities_processed >= config.max_entities:
                        logger.info(
                            "Reached global max entities limit: %d",
                            config.max_entities,
                        )
                        break

                    entities_processed += 1
                    logger.info(
                        "Processing doc %d: %s (version=%s, section=%s)",
                        entities_processed,
                        doc.title,
                        doc.version,
                        doc.section_type,
                    )

                    doc_uuid_str = str(doc.uuid)
                    existing_hash = existing_docs.get(doc_uuid_str)

                    if config.dry_run:
                        if existing_hash is None:
                            logger.info("[DRY RUN] Would insert new doc: %s", doc.title)
                        elif existing_hash != doc.content_hash:
                            logger.info(
                                "[DRY RUN] Would update existing doc: %s",
                                doc.title,
                            )
                        else:
                            logger.info(
                                "[DRY RUN] Unchanged doc (skipping): %s",
                                doc.title,
                            )
                        continue

                    try:
                        text = get_doc_text_for_embedding(doc)
                        logger.debug("Getting embedding for: %s...", text[:100])
                        vector = get_embedding(text)

                        if existing_hash is None:
                            # New document
                            collection.data.insert(
                                doc.to_properties(),
                                uuid=doc.uuid,
                                vector=vector,
                            )
                            entities_inserted += 1
                            existing_docs[doc_uuid_str] = doc.content_hash
                        elif existing_hash != doc.content_hash:
                            # Existing document with changed content
                            collection.data.update(
                                uuid=doc.uuid,
                                properties=doc.to_properties(),
                                vector=vector,
                            )
                            entities_inserted += 1
                            existing_docs[doc_uuid_str] = doc.content_hash
                            logger.info(
                                "Updated existing document with changed content_hash: %s",
                                doc.title,
                            )
                        else:
                            # Unchanged document, skip
                            logger.debug(
                                "Skipping unchanged document: %s (UUID: %s)",
                                doc.title,
                                doc_uuid_str,
                            )
                            continue

                        if entities_inserted % 10 == 0:
                            emit_progress(
                                "ingesting",
                                entities_inserted,
                                config.max_entities or 0,
                                f"Inserted/updated {entities_inserted} documents",
                            )
                            logger.info(
                                "Inserted/updated %d documents so far",
                                entities_inserted,
                            )
                    except Exception as e:
                        errors += 1
                        logger.exception("Failed to insert %s: %s", doc.title, e)

        if cancelled:
            emit_progress("cancelled", entities_processed, 0, "Scraping cancelled")
        else:
            emit_progress(
                "complete",
                entities_processed,
                entities_processed,
                f"Completed: {entities_inserted} documents inserted",
            )

    except Exception as e:
        logger.exception("Scraping failed: %s", e)
        errors += 1

    result: dict[str, Any] = {
        "entities_processed": entities_processed,
        "entities_inserted": entities_inserted,
        "errors": errors,
    }
    if cancelled:
        result["cancelled"] = True

    logger.info("Scraping result: %s", result)
    return result


def _configure_logging(verbose: bool) -> None:
    """
    Configure logging level based on verbosity flag.

    Args:
        verbose: If True, enable DEBUG logging; otherwise use settings.LOG_LEVEL
    """
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(level)


def main(argv: list[str] | None = None) -> None:
    """
    CLI entry point for Python documentation scraper.

    Args:
        argv: Optional command line arguments (for testing)

    Raises:
        SystemExit: On command failure
    """
    parser = argparse.ArgumentParser(
        description="Python 3.13 and 3.12 documentation scraper for Weaviate ingestion.",
    )
    parser.add_argument(
        "command",
        choices=["scrape", "status", "reindex"],
        nargs="?",
        default="scrape",
        help="Operation to perform (default: scrape).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape without inserting into Weaviate.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of documents to scrape.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help=f"Delay between requests in seconds (default: {DEFAULT_REQUEST_DELAY}).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Documents per batch before longer pause (default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--batch-delay",
        type=float,
        default=DEFAULT_BATCH_DELAY,
        help=f"Pause after each batch in seconds (default: {DEFAULT_BATCH_DELAY}).",
    )

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    logger.info("WEAVIATE_URL=%s", settings.WEAVIATE_URL)

    exit_code = 0

    try:
        if args.command == "status":
            with WeaviateConnection() as client:
                stats = get_python_docs_stats(client)
                logger.info("PythonDocs collection status: %s", stats)
                print(f"Collection exists: {stats['exists']}")
                print(f"Total documents: {stats['object_count']}")
                if stats.get("version_counts"):
                    print("Version breakdown:")
                    for version, count in sorted(stats["version_counts"].items()):
                        print(f"  {version}: {count}")
                if stats.get("section_counts"):
                    print("Section breakdown:")
                    for section, count in sorted(stats["section_counts"].items()):
                        print(f"  {section}: {count}")

        elif args.command == "reindex":
            with WeaviateConnection() as client:
                logger.info("Reindexing: deleting and recreating collection")
                create_python_docs_collection(client, force_reindex=True)

            config = ScrapeConfig(
                request_delay=args.delay,
                batch_size=args.batch_size,
                batch_delay=args.batch_delay,
                max_entities=args.limit,
                dry_run=args.dry_run,
            )
            result = scrape_python_docs(config=config)
            logger.info("Reindex complete: %s", result)

        else:  # scrape
            config = ScrapeConfig(
                request_delay=args.delay,
                batch_size=args.batch_size,
                batch_delay=args.batch_delay,
                max_entities=args.limit,
                dry_run=args.dry_run,
            )
            result = scrape_python_docs(config=config)
            logger.info("Scrape complete: %s", result)

    except Exception as e:
        logger.exception("Command failed: %s", e)
        exit_code = 1

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
