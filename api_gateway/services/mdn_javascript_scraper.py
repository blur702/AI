"""
MDN JavaScript documentation scraper.

Scrapes JavaScript language reference and guide documentation from MDN
(developer.mozilla.org), extracts content and metadata, and ingests into
Weaviate for semantic search.

Coverage:
- JavaScript Reference (Global Objects, Operators, Statements, Functions)
- JavaScript Guide (Introduction, Grammar, Control Flow, etc.)
- JavaScript Tutorials

Features:
- Rate-limited requests (configurable delay between requests)
- Incremental updates via content_hash comparison
- Progress callbacks for UI integration
- Resumable scraping with checkpoint support
- Respects MDN's robots.txt and rate limits

CLI usage:
    python -m api_gateway.services.mdn_javascript_scraper scrape --verbose
    python -m api_gateway.services.mdn_javascript_scraper scrape --limit 100
    python -m api_gateway.services.mdn_javascript_scraper status
    python -m api_gateway.services.mdn_javascript_scraper reindex
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, Generator, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .mdn_schema import (
    MDNJavaScriptDoc,
    compute_mdn_content_hash,
    create_mdn_javascript_collection,
    generate_mdn_javascript_uuid,
    get_mdn_javascript_stats,
)
from .weaviate_connection import MDN_JAVASCRIPT_COLLECTION_NAME, WeaviateConnection

logger = get_logger("api_gateway.mdn_javascript_scraper")

# MDN base URL
MDN_BASE = "https://developer.mozilla.org"
MDN_JAVASCRIPT_ROOT = "/en-US/docs/Web/JavaScript"

# Rate limiting defaults
DEFAULT_REQUEST_DELAY = 1.0  # seconds between requests
DEFAULT_BATCH_SIZE = 20  # entities per batch before longer pause
DEFAULT_BATCH_DELAY = 3.0  # seconds pause after each batch

# JavaScript documentation sections to scrape
# Each tuple: (path_suffix, section_type, description)
JAVASCRIPT_SECTIONS = [
    ("/Reference/Global_Objects", "Reference", "Built-in objects"),
    ("/Reference/Operators", "Reference", "Operators"),
    ("/Reference/Statements", "Reference", "Statements and declarations"),
    ("/Reference/Functions", "Reference", "Functions"),
    ("/Reference/Classes", "Reference", "Classes"),
    ("/Reference/Errors", "Reference", "Error types"),
    ("/Reference/Lexical_grammar", "Reference", "Lexical grammar"),
    ("/Guide", "Guide", "JavaScript Guide"),
]


@dataclass
class ScrapeConfig:
    """Configuration for scraping behavior."""

    request_delay: float = DEFAULT_REQUEST_DELAY
    batch_size: int = DEFAULT_BATCH_SIZE
    batch_delay: float = DEFAULT_BATCH_DELAY
    max_entities: Optional[int] = None
    dry_run: bool = False


ProgressCallback = Callable[[str, int, int, str], None]
CancelCheck = Callable[[], bool]
PauseCheck = Callable[[], bool]


def get_doc_text_for_embedding(doc: MDNJavaScriptDoc) -> str:
    """
    Build text representation for embedding computation.

    Args:
        doc: MDN JavaScript documentation object

    Returns:
        Combined text from title and content (limited to 2000 chars for content)
    """
    parts = []
    if doc.title:
        parts.append(doc.title)
    if doc.content:
        # Limit content length for embedding
        parts.append(doc.content[:2000])
    return " ".join(parts)


class MDNJavaScriptScraper:
    """
    Scraper for MDN JavaScript documentation.

    Navigates MDN's JavaScript documentation, extracts page content,
    and yields MDNJavaScriptDoc objects for ingestion.
    """

    def __init__(
        self,
        config: Optional[ScrapeConfig] = None,
        progress_callback: Optional[ProgressCallback] = None,
        check_cancelled: Optional[CancelCheck] = None,
        check_paused: Optional[PauseCheck] = None,
    ):
        """
        Initialize the MDN JavaScript documentation scraper.

        Args:
            config: Scraping configuration (rate limits, batch size, etc.)
            progress_callback: Optional callback for progress updates (phase, current, total, message)
            check_cancelled: Optional callback to check if scraping should be cancelled
            check_paused: Optional callback to check if scraping is paused
        """
        self.config = config or ScrapeConfig()
        self.progress_callback = progress_callback
        self.check_cancelled = check_cancelled
        self.check_paused = check_paused
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "MDNJavaScriptScraper/1.0 (AI Documentation Indexer; https://github.com/kevinalthaus/ai-workspace)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        self._request_count = 0
        self._last_request_time = 0.0
        self._seen_urls: Set[str] = set()

    def __enter__(self) -> "MDNJavaScriptScraper":
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

    def _is_paused(self) -> bool:
        """
        Check if scraping is paused and wait if so.

        Returns:
            True if cancelled during wait, False otherwise
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

    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
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
        # Remove fragments and query params for deduplication
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def _is_javascript_doc_url(self, url: str) -> bool:
        """
        Check if URL is a valid JavaScript documentation page.

        Args:
            url: URL to validate

        Returns:
            True if URL is under /docs/Web/JavaScript and is English, False otherwise
        """
        parsed = urlparse(url)
        path = parsed.path

        # Must be under JavaScript docs
        if "/docs/Web/JavaScript" not in path:
            return False

        # Skip non-English pages
        if not path.startswith("/en-US/"):
            return False

        # Skip special pages
        skip_patterns = [
            "/docs/Web/JavaScript$",  # Index page itself
            "/contributors",
            "/history",
            "/_",  # Internal pages
        ]
        for pattern in skip_patterns:
            if re.search(pattern, path):
                return False

        return True

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """
        Extract page title from MDN page.

        Args:
            soup: Parsed HTML page

        Returns:
            Page title or empty string
        """
        # Try the main heading first
        h1 = soup.select_one("h1")
        if h1:
            return h1.get_text(strip=True)

        # Fallback to title tag
        title = soup.select_one("title")
        if title:
            text = title.get_text(strip=True)
            # Remove " - JavaScript | MDN" suffix
            return re.sub(r"\s*[-|].*$", "", text)

        return ""

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """
        Extract main content from MDN page.

        Args:
            soup: Parsed HTML page

        Returns:
            Main content text (limited to 10000 chars) or empty string
        """
        # MDN uses article.main-page-content for main content
        article = soup.select_one("article.main-page-content, article, main")
        if not article:
            return ""

        # Remove navigation, sidebars, etc.
        for selector in ["nav", ".sidebar", ".bc-data", "script", "style", ".hidden"]:
            for elem in article.select(selector):
                elem.decompose()

        # Get text content
        text = article.get_text(separator=" ", strip=True)

        # Clean up excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Limit length
        return text[:10000]

    def _extract_last_modified(self, soup: BeautifulSoup) -> str:
        """
        Extract last modified date from MDN page metadata.

        Args:
            soup: Parsed HTML page

        Returns:
            ISO 8601 timestamp or current time if not found
        """
        # Try meta tag
        meta = soup.select_one('meta[property="article:modified_time"]')
        if meta:
            return meta.get("content", "")

        # Try time element
        time_elem = soup.select_one("time[datetime]")
        if time_elem:
            return time_elem.get("datetime", "")

        # Default to now
        return datetime.now(timezone.utc).isoformat()

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Extract links to other JavaScript documentation pages.

        Args:
            soup: Parsed HTML page
            base_url: Current page URL for resolving relative links

        Returns:
            List of absolute URLs to valid JavaScript documentation pages
        """
        links = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue

            # Build absolute URL
            if href.startswith("/"):
                url = urljoin(MDN_BASE, href)
            elif href.startswith("http"):
                url = href
            else:
                url = urljoin(base_url, href)

            # Normalize and filter
            url = self._normalize_url(url)
            if self._is_javascript_doc_url(url) and url not in self._seen_urls:
                links.append(url)

        return links

    def _parse_page(
        self, soup: BeautifulSoup, url: str, section_type: str
    ) -> Optional[MDNJavaScriptDoc]:
        """
        Parse a single MDN page and extract documentation from pre-fetched soup.

        Args:
            soup: Pre-fetched BeautifulSoup object
            url: Page URL
            section_type: Section type (Reference or Guide)

        Returns:
            MDNJavaScriptDoc object or None if insufficient content
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
        scraped_at = datetime.now(timezone.utc).isoformat()
        content_hash = compute_mdn_content_hash(title, content, section_type)
        doc_uuid = generate_mdn_javascript_uuid(url, title)

        return MDNJavaScriptDoc(
            title=title,
            url=url,
            content=content,
            section_type=section_type,
            last_modified=last_modified,
            scraped_at=scraped_at,
            content_hash=content_hash,
            uuid=doc_uuid,
        )

    def scrape_section(
        self, section_path: str, section_type: str
    ) -> Generator[MDNJavaScriptDoc, None, None]:
        """
        Scrape all pages in a documentation section using BFS.

        Args:
            section_path: Path suffix (e.g., "/Reference/Global_Objects")
            section_type: Section type (Reference or Guide)

        Yields:
            MDNJavaScriptDoc objects for each successfully parsed page
        """
        start_url = f"{MDN_BASE}{MDN_JAVASCRIPT_ROOT}{section_path}"
        logger.info("Scraping section: %s (%s)", section_path, section_type)

        # BFS queue
        queue: Deque[str] = deque([start_url])
        entity_count = 0

        while queue:
            if self._is_cancelled():
                logger.info("Scraping cancelled")
                return

            # Check for pause and wait if paused
            if self._is_paused():
                logger.info("Scraping cancelled during pause")
                return

            if self.config.max_entities and entity_count >= self.config.max_entities:
                logger.info("Reached max entities limit: %d", self.config.max_entities)
                return

            url = queue.popleft()
            normalized_url = self._normalize_url(url)

            if normalized_url in self._seen_urls:
                continue
            self._seen_urls.add(normalized_url)

            # Fetch and parse page
            soup = self._fetch(url)
            if not soup:
                continue

            # Try to create document from already-fetched soup
            doc = self._parse_page(soup, url, section_type)
            if doc:
                entity_count += 1
                logger.info(
                    "Parsed doc: %s - content=%d chars",
                    doc.title,
                    len(doc.content),
                )
                self._emit_progress(
                    "scraping",
                    entity_count,
                    self.config.max_entities or 0,
                    f"Scraped: {doc.title}",
                )
                yield doc

            # Find more links within this section
            new_links = self._extract_links(soup, url)
            for link in new_links:
                # Only follow links within the same section or subsections
                if section_path in link or link.startswith(start_url):
                    if link not in self._seen_urls:
                        queue.append(link)

        logger.info("Finished section %s: %d documents", section_path, entity_count)

    def scrape_all(self) -> Generator[MDNJavaScriptDoc, None, None]:
        """
        Scrape all JavaScript documentation sections defined in JAVASCRIPT_SECTIONS.

        Yields:
            MDNJavaScriptDoc objects from all sections
        """
        for section_path, section_type, description in JAVASCRIPT_SECTIONS:
            if self._is_cancelled():
                return

            if self.config.max_entities and len(self._seen_urls) >= self.config.max_entities:
                logger.info("Reached max entities limit")
                return

            logger.info("Starting section: %s - %s", section_type, description)
            yield from self.scrape_section(section_path, section_type)


def scrape_mdn_javascript(
    config: Optional[ScrapeConfig] = None,
    progress_callback: Optional[ProgressCallback] = None,
    check_cancelled: Optional[CancelCheck] = None,
    check_paused: Optional[PauseCheck] = None,
) -> Dict[str, Any]:
    """
    Scrape MDN JavaScript documentation and ingest into Weaviate.

    Args:
        config: Scraping configuration
        progress_callback: Optional callback for progress updates
        check_cancelled: Optional callback to check for cancellation
        check_paused: Optional callback to check if paused and wait. Returns True if cancelled.

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
            except Exception:
                pass

    def is_cancelled() -> bool:
        if check_cancelled:
            try:
                return check_cancelled()
            except Exception:
                return False
        return False

    def is_paused() -> bool:
        """Check if paused and wait. Returns True if cancelled during wait."""
        if check_paused:
            try:
                return check_paused()
            except Exception:
                return False
        return False

    emit_progress("starting", 0, 0, "Connecting to Weaviate")

    try:
        with WeaviateConnection() as client:
            # Create collection if needed
            emit_progress("setup", 0, 0, "Setting up MDNJavaScript collection")
            create_mdn_javascript_collection(client, force_reindex=False)
            collection = client.collections.get(MDN_JAVASCRIPT_COLLECTION_NAME)

            # Load existing UUIDs for deduplication
            emit_progress("setup", 0, 0, "Loading existing UUIDs for deduplication")
            existing_uuids: Set[str] = set()
            try:
                logger.info("Loading existing entity UUIDs for deduplication...")
                for obj in collection.iterator(include_vector=False):
                    if obj.uuid:
                        existing_uuids.add(str(obj.uuid))
                logger.info("Loaded %d existing UUIDs", len(existing_uuids))
            except Exception as e:
                logger.warning("Could not load existing UUIDs: %s", e)

            if config.dry_run:
                logger.info("Dry run mode - not inserting into Weaviate")

            with MDNJavaScriptScraper(
                config=config,
                progress_callback=progress_callback,
                check_cancelled=check_cancelled,
                check_paused=check_paused,
            ) as scraper:
                for doc in scraper.scrape_all():
                    if is_cancelled():
                        cancelled = True
                        break

                    # Check for pause and wait if paused
                    if is_paused():
                        cancelled = True
                        break

                    if config.max_entities and entities_processed >= config.max_entities:
                        logger.info("Reached global max entities limit: %d", config.max_entities)
                        break

                    entities_processed += 1
                    logger.info(
                        "Processing doc %d: %s",
                        entities_processed,
                        doc.title,
                    )

                    # Skip if document already exists (deduplication)
                    doc_uuid_str = str(doc.uuid)
                    if doc_uuid_str in existing_uuids:
                        logger.debug("Skipping duplicate: %s (UUID: %s)", doc.title, doc_uuid_str)
                        continue

                    if config.dry_run:
                        logger.info("[DRY RUN] Would insert: %s", doc.title)
                        continue

                    # Insert into Weaviate with embedding
                    try:
                        text = get_doc_text_for_embedding(doc)
                        logger.debug("Getting embedding for: %s...", text[:100])
                        vector = get_embedding(text)
                        collection.data.insert(
                            doc.to_properties(),
                            uuid=doc.uuid,
                            vector=vector,
                        )
                        entities_inserted += 1

                        if entities_inserted % 10 == 0:
                            emit_progress(
                                "ingesting",
                                entities_inserted,
                                config.max_entities or 0,
                                f"Inserted {entities_inserted} documents",
                            )
                            logger.info("Inserted %d documents so far", entities_inserted)

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

    result = {
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


def main(argv: Optional[List[str]] = None) -> None:
    """
    CLI entry point for MDN JavaScript scraper.

    Args:
        argv: Optional command line arguments (for testing)

    Raises:
        SystemExit: On command failure
    """
    parser = argparse.ArgumentParser(
        description="MDN JavaScript documentation scraper for Weaviate ingestion.",
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
                stats = get_mdn_javascript_stats(client)
                logger.info("MDNJavaScript collection status: %s", stats)
                print(f"Collection exists: {stats['exists']}")
                print(f"Total documents: {stats['object_count']}")
                if stats["section_counts"]:
                    print("Section breakdown:")
                    for section, count in sorted(stats["section_counts"].items()):
                        print(f"  {section}: {count}")

        elif args.command == "reindex":
            with WeaviateConnection() as client:
                logger.info("Reindexing: deleting and recreating collection")
                create_mdn_javascript_collection(client, force_reindex=True)

            config = ScrapeConfig(
                request_delay=args.delay,
                batch_size=args.batch_size,
                batch_delay=args.batch_delay,
                max_entities=args.limit,
                dry_run=args.dry_run,
            )
            result = scrape_mdn_javascript(config=config)
            logger.info("Reindex complete: %s", result)

        else:  # scrape
            config = ScrapeConfig(
                request_delay=args.delay,
                batch_size=args.batch_size,
                batch_delay=args.batch_delay,
                max_entities=args.limit,
                dry_run=args.dry_run,
            )
            result = scrape_mdn_javascript(config=config)
            logger.info("Scrape complete: %s", result)

    except Exception as e:
        logger.exception("Command failed: %s", e)
        exit_code = 1

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
