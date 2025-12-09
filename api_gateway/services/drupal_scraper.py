"""
Drupal API scraper for api.drupal.org.

Scrapes Drupal 11.x API documentation from api.drupal.org, extracts entity
metadata (classes, interfaces, functions, hooks, etc.), and ingests into
Weaviate for semantic search.

Features:
- Rate-limited requests (configurable delay between requests)
- Incremental updates via content_hash comparison
- Progress callbacks for UI integration
- Resumable scraping with checkpoint support

CLI usage:
    python -m api_gateway.services.drupal_scraper scrape --verbose
    python -m api_gateway.services.drupal_scraper scrape --limit 100
    python -m api_gateway.services.drupal_scraper status
    python -m api_gateway.services.drupal_scraper reindex
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generator, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .drupal_api_schema import (
    DrupalAPIEntity,
    compute_content_hash,
    create_drupal_api_collection,
    generate_stable_uuid,
    get_collection_stats,
)
from .weaviate_connection import DRUPAL_API_COLLECTION_NAME, WeaviateConnection

logger = get_logger("api_gateway.drupal_scraper")

# Drupal API base URL
DRUPAL_API_BASE = "https://api.drupal.org"
DRUPAL_VERSION = "11.x"

# Rate limiting defaults
DEFAULT_REQUEST_DELAY = 2.0  # seconds between requests
DEFAULT_BATCH_SIZE = 10  # entities per batch before longer pause
DEFAULT_BATCH_DELAY = 5.0  # seconds pause after each batch

# Entity type mappings: listing path -> entity type name
# Based on api.drupal.org URL structure: /api/drupal/{listing_path}/11.x
ENTITY_LISTINGS = {
    "classes": "class",
    "functions": "function",
    "constants": "constant",
    "namespaces": "namespace",
    "services": "service",
    "elements": "element",
}


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


def get_entity_text_for_embedding(entity: DrupalAPIEntity) -> str:
    """
    Build text representation for embedding computation.

    Args:
        entity: Drupal API entity

    Returns:
        Combined text from full_name, signature, and description (limited to 1500 chars for description)
    """
    parts = []
    if entity.full_name:
        parts.append(entity.full_name)
    if entity.signature:
        parts.append(entity.signature)
    if entity.description:
        # Limit description length for embedding
        parts.append(entity.description[:1500])
    return " ".join(parts)


class DrupalAPIScraper:
    """
    Scraper for api.drupal.org Drupal 11.x documentation.

    Navigates the API documentation site, extracts entity information,
    and yields DrupalAPIEntity objects for ingestion.
    """

    def __init__(
        self,
        config: Optional[ScrapeConfig] = None,
        progress_callback: Optional[ProgressCallback] = None,
        check_cancelled: Optional[CancelCheck] = None,
        check_paused: Optional[PauseCheck] = None,
    ):
        """
        Initialize the Drupal API scraper.

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
                "User-Agent": "DrupalAPIScraper/1.0 (AI Documentation Indexer)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        self._request_count = 0
        self._last_request_time = 0.0

    def __enter__(self) -> "DrupalAPIScraper":
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
        """Check if paused and wait. Returns True if cancelled during wait."""
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
            response = self.client.get(url, timeout=60.0)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except httpx.HTTPStatusError as e:
            logger.warning("HTTP %d for %s", e.response.status_code, url)
            return None
        except httpx.RequestError as e:
            logger.warning("Request error for %s: %s", url, e)
            return None
        except httpx.TimeoutException as e:
            logger.warning("Timeout error for %s: %s", url, e)
            return None

    def _extract_namespace(self, full_name: str) -> str:
        """
        Extract PHP namespace from fully qualified name.

        Args:
            full_name: Fully qualified class/interface name (e.g., Drupal\Core\Entity\EntityInterface)

        Returns:
            Namespace portion (e.g., Drupal\Core\Entity) or empty string
        """
        if "\\" in full_name:
            parts = full_name.rsplit("\\", 1)
            return parts[0] if len(parts) > 1 else ""
        return ""

    def _extract_file_path(self, soup: BeautifulSoup, url: str) -> str:
        """
        Extract file path from API page URL or breadcrumb.

        Args:
            soup: Parsed HTML page
            url: Page URL

        Returns:
            File path (e.g., core/lib/Drupal.php) or empty string
        """
        # Try to extract from URL first (most reliable)
        # URL pattern: /api/drupal/path%21to%21file.php/class/ClassName/11.x
        match = re.search(r"/api/drupal/([^/]+\.php)/", url)
        if match:
            # URL uses %21 for path separators, decode to /
            path = match.group(1)
            return path.replace("%21", "/").replace("!", "/")

        # Fallback: Look for breadcrumb link to .php file
        for link in soup.select("a"):
            href = link.get("href", "")
            if ".php" in href and "/api/drupal/" in href:
                match = re.search(r"/api/drupal/([^/]+\.php)", href)
                if match:
                    return match.group(1).replace("%21", "/").replace("!", "/")
        return ""

    def _extract_line_number(self, soup: BeautifulSoup) -> int:
        """
        Extract line number from API page.

        Args:
            soup: Parsed HTML page

        Returns:
            Line number where entity is defined, or 0 if not found
        """
        # Look for "line X" text anywhere in the page
        text = soup.get_text()
        match = re.search(r"line\s+(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0

    def _extract_signature(self, soup: BeautifulSoup) -> str:
        """
        Extract function/class signature from pre or code blocks.

        Args:
            soup: Parsed HTML page

        Returns:
            Code signature (limited to 500 chars) or empty string
        """
        # Look for <pre> blocks containing PHP code
        for pre in soup.select("pre"):
            text = pre.get_text(strip=True)
            # Check if it looks like a PHP declaration
            if any(kw in text for kw in ["class ", "function ", "interface ", "trait ", "abstract ", "final "]):
                # Clean up and limit length
                return text[:500]

        # Fallback: look for code elements
        for code in soup.select("code"):
            text = code.get_text(strip=True)
            if any(kw in text for kw in ["class ", "function ", "interface ", "trait "]):
                return text[:500]
        return ""

    def _extract_parameters(self, soup: BeautifulSoup) -> str:
        """
        Extract parameters as JSON string.

        Args:
            soup: Parsed HTML page

        Returns:
            JSON array of parameter objects with name, type, description
        """
        params = []
        # Look for parameter tables or lists
        # Drupal API shows parameters in tables with Parameter/Description columns
        for table in soup.select("table"):
            headers = [th.get_text(strip=True).lower() for th in table.select("th")]
            if "parameter" in headers or "name" in headers:
                for row in table.select("tbody tr, tr"):
                    cells = row.select("td")
                    if len(cells) >= 2:
                        param = {
                            "name": cells[0].get_text(strip=True),
                            "type": "",
                            "description": cells[-1].get_text(strip=True)[:200],
                        }
                        params.append(param)
        return json.dumps(params)

    def _extract_return_type(self, soup: BeautifulSoup) -> str:
        """
        Extract return type annotation.

        Args:
            soup: Parsed HTML page

        Returns:
            Return type (limited to 100 chars) or empty string
        """
        # Look for "Return value" section
        text = soup.get_text()
        match = re.search(r"Return value\s*[:\n]\s*(\S+)", text)
        if match:
            return match.group(1)[:100]
        return ""

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """
        Extract main description/docblock.

        Args:
            soup: Parsed HTML page

        Returns:
            Description text (limited to 2000 chars) or empty string
        """
        # Get the first substantial paragraph after h1
        h1 = soup.select_one("h1")
        if h1:
            # Get text content after h1, before any tables or code blocks
            description_parts = []
            for sibling in h1.find_next_siblings():
                if sibling.name in ["table", "pre", "h2", "h3"]:
                    break
                if sibling.name == "p":
                    text = sibling.get_text(strip=True)
                    if text:
                        description_parts.append(text)
            if description_parts:
                return " ".join(description_parts)[:2000]

        # Fallback: just get first few paragraphs
        paragraphs = soup.select("p")
        if paragraphs:
            texts = [p.get_text(strip=True) for p in paragraphs[:3]]
            return " ".join(texts)[:2000]
        return ""

    def _extract_deprecated(self, soup: BeautifulSoup) -> str:
        """
        Extract deprecation notice if present.

        Args:
            soup: Parsed HTML page

        Returns:
            Deprecation message (limited to 500 chars) or empty string
        """
        # Look for deprecation warnings
        text = soup.get_text()
        match = re.search(r"(Deprecated[^.]*\.)", text, re.IGNORECASE)
        if match:
            return match.group(1)[:500]
        return ""

    def _extract_see_also(self, soup: BeautifulSoup) -> str:
        """
        Extract related references as JSON array.

        Args:
            soup: Parsed HTML page

        Returns:
            JSON array of related entity names (max 20)
        """
        see_also = []
        # Look for "See also" section
        text = soup.get_text()
        if "See also" in text:
            # Find links near "See also" text
            see_section = soup.find(string=re.compile(r"See also", re.IGNORECASE))
            if see_section:
                parent = see_section.find_parent()
                if parent:
                    for link in parent.find_next_siblings("a"):
                        text = link.get_text(strip=True)
                        if text:
                            see_also.append(text)
                            if len(see_also) >= 20:
                                break
        return json.dumps(see_also)

    def _extract_related_topics(self, soup: BeautifulSoup) -> str:
        """
        Extract related topics/tags as JSON array.

        Args:
            soup: Parsed HTML page

        Returns:
            JSON array of topic names (max 20)
        """
        topics = []
        # Look for topic/group links (usually in sidebar or header)
        for link in soup.select("a"):
            href = link.get("href", "")
            if "/group/" in href or "/topic/" in href:
                text = link.get_text(strip=True)
                if text and text not in topics:
                    topics.append(text)
                    if len(topics) >= 20:
                        break
        return json.dumps(topics)

    def _parse_entity_page(
        self, url: str, entity_type: str, name: str
    ) -> Optional[DrupalAPIEntity]:
        """
        Parse a single entity page and extract metadata.

        Args:
            url: Entity page URL
            entity_type: Type of entity (class, function, interface, etc.)
            name: Entity name

        Returns:
            DrupalAPIEntity object or None if parsing fails
        """
        soup = self._fetch(url)
        if not soup:
            return None

        # Extract full name from h1 (e.g., "class AccessResult")
        h1 = soup.select_one("h1")
        full_name = name
        if h1:
            h1_text = h1.get_text(strip=True)
            # Remove entity type prefix (e.g., "class ", "function ")
            full_name = re.sub(r"^(class|interface|trait|function|constant)\s+", "", h1_text)

        namespace = self._extract_namespace(full_name)
        file_path = self._extract_file_path(soup, url)
        line_number = self._extract_line_number(soup)
        signature = self._extract_signature(soup)
        parameters = self._extract_parameters(soup)
        return_type = self._extract_return_type(soup)
        description = self._extract_description(soup)
        deprecated = self._extract_deprecated(soup)
        see_also = self._extract_see_also(soup)
        related_topics = self._extract_related_topics(soup)

        # Compute content hash and UUID
        content_hash = compute_content_hash(
            signature, parameters, return_type, description
        )
        entity_uuid = generate_stable_uuid(url, full_name)
        scraped_at = datetime.now(timezone.utc).isoformat()

        return DrupalAPIEntity(
            entity_type=entity_type,
            name=name,
            full_name=full_name,
            namespace=namespace,
            file_path=file_path,
            line_number=line_number,
            signature=signature,
            parameters=parameters,
            return_type=return_type,
            description=description,
            deprecated=deprecated,
            see_also=see_also,
            related_topics=related_topics,
            source_url=url,
            language="php",
            content_hash=content_hash,
            scraped_at=scraped_at,
            uuid=entity_uuid,
        )

    def _get_listing_url(self, listing_path: str, page: int = 0) -> str:
        """
        Generate listing page URL with pagination.

        Args:
            listing_path: Path segment (e.g., "classes", "functions")
            page: Page number (0-indexed)

        Returns:
            Full listing URL with optional ?page= parameter
        """
        base_url = f"{DRUPAL_API_BASE}/api/drupal/{listing_path}/{DRUPAL_VERSION}"
        if page > 0:
            return f"{base_url}?page={page}"
        return base_url

    def _parse_listing_soup(
        self, soup: BeautifulSoup, entity_type: str
    ) -> Generator[tuple[str, str, str], None, None]:
        """
        Parse a listing page soup and yield (entity_url, entity_name, namespace) tuples.
        """
        # Find the main table containing entity listings
        table = soup.select_one("table")
        if not table:
            logger.debug("No table found in listing page")
            return

        # Parse table rows (skip header row)
        rows = table.select("tbody tr, tr")
        for row in rows:
            cells = row.select("td")
            if not cells:
                continue

            # First cell contains the entity link
            first_cell = cells[0]
            link = first_cell.select_one("a")
            if not link:
                continue

            href = link.get("href", "")
            name = link.get_text(strip=True)

            if not href or not name:
                continue

            # Extract namespace from table if available (usually 4th column)
            namespace = ""
            if len(cells) >= 4:
                ns_cell = cells[3]
                namespace = ns_cell.get_text(strip=True)

            # Build full URL
            if href.startswith("/"):
                entity_url = urljoin(DRUPAL_API_BASE, href)
            elif href.startswith("http"):
                entity_url = href
            else:
                continue

            # Filter: must be a valid Drupal API entity URL
            # Pattern: /api/drupal/.../class|function|interface/.../11.x
            if "/api/drupal/" in entity_url and DRUPAL_VERSION in entity_url:
                yield (entity_url, name, namespace)

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        Extract next page URL from pagination if present.

        Args:
            soup: Parsed listing page HTML
            current_url: Current page URL (for resolving relative links)

        Returns:
            Absolute URL to next page or None if no pagination
        """
        # Look for "Next >" or pagination links
        next_link = soup.select_one("a[rel='next'], .pager-next a, li.next a")
        if next_link:
            href = next_link.get("href", "")
            if href:
                if href.startswith("/"):
                    return urljoin(DRUPAL_API_BASE, href)
                elif href.startswith("http"):
                    return href
        return None

    def scrape_listing(
        self, listing_path: str, entity_type: str
    ) -> Generator[DrupalAPIEntity, None, None]:
        """
        Scrape all entities from a listing type with pagination.

        Args:
            listing_path: Path segment (e.g., "classes", "functions")
            entity_type: Type of entity for this listing

        Yields:
            DrupalAPIEntity objects for each successfully parsed entity
        """
        logger.info("Scraping %s entities from api.drupal.org/%s", entity_type, listing_path)
        seen_urls: set[str] = set()
        entity_count = 0
        page = 0
        max_pages = 500  # Safety limit

        while page < max_pages:
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

            listing_url = self._get_listing_url(listing_path, page)
            soup = self._fetch(listing_url)
            if not soup:
                break

            found_any = False
            for entity_url, name, namespace in self._parse_listing_soup(soup, entity_type):
                found_any = True
                if entity_url in seen_urls:
                    continue
                seen_urls.add(entity_url)

                if self._is_cancelled():
                    return

                # Check for pause and wait if paused
                if self._is_paused():
                    return

                if self.config.max_entities and entity_count >= self.config.max_entities:
                    return

                entity = self._parse_entity_page(entity_url, entity_type, name)
                if entity:
                    # Override namespace if we extracted it from listing
                    if namespace and not entity.namespace:
                        props = entity.to_properties()
                        props["namespace"] = namespace
                        entity = DrupalAPIEntity(**props)
                    entity_count += 1
                    logger.info(
                        "Parsed entity: %s (%s) - desc=%d chars",
                        entity.full_name,
                        entity.entity_type,
                        len(entity.description),
                    )
                    self._emit_progress(
                        "scraping",
                        entity_count,
                        self.config.max_entities or 0,
                        f"Scraped {entity_type}: {name}",
                    )
                    yield entity
                else:
                    logger.warning("Failed to parse entity page: %s", entity_url)

            # Check for next page
            next_url = self._get_next_page_url(soup, listing_url)
            if next_url and found_any:
                page += 1
                logger.debug("Moving to page %d", page)
            else:
                break

        logger.info("Finished scraping %s: %d entities", listing_path, entity_count)

    def scrape_all(self) -> Generator[DrupalAPIEntity, None, None]:
        """
        Scrape all entity types defined in ENTITY_LISTINGS.

        Yields:
            DrupalAPIEntity objects from all listing types
        """
        for listing_path, entity_type in ENTITY_LISTINGS.items():
            if self._is_cancelled():
                return
            yield from self.scrape_listing(listing_path, entity_type)


def scrape_drupal_api(
    config: Optional[ScrapeConfig] = None,
    progress_callback: Optional[ProgressCallback] = None,
    check_cancelled: Optional[CancelCheck] = None,
    check_paused: Optional[PauseCheck] = None,
) -> Dict[str, Any]:
    """
    Scrape Drupal API and ingest into Weaviate.

    Args:
        config: Scraping configuration
        progress_callback: Optional callback for progress updates
        check_cancelled: Optional callback to check for cancellation
        check_paused: Optional callback to check if paused and wait. Returns True if cancelled.

    Returns:
        Statistics dict with keys: entities, errors, cancelled
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
            emit_progress("setup", 0, 0, "Setting up DrupalAPI collection")
            create_drupal_api_collection(client, force_reindex=False)
            collection = client.collections.get(DRUPAL_API_COLLECTION_NAME)

            if config.dry_run:
                logger.info("Dry run mode - not inserting into Weaviate")

            with DrupalAPIScraper(
                config=config,
                progress_callback=progress_callback,
                check_cancelled=check_cancelled,
                check_paused=check_paused,
            ) as scraper:
                for entity in scraper.scrape_all():
                    if is_cancelled():
                        cancelled = True
                        break

                    # Check for pause and wait if paused
                    if is_paused():
                        cancelled = True
                        break

                    # Check global limit
                    if config.max_entities and entities_processed >= config.max_entities:
                        logger.info("Reached global max entities limit: %d", config.max_entities)
                        break

                    entities_processed += 1
                    logger.info(
                        "Processing entity %d: %s (%s)",
                        entities_processed,
                        entity.full_name,
                        entity.entity_type,
                    )

                    if config.dry_run:
                        logger.info(
                            "[DRY RUN] Would insert: %s (%s)",
                            entity.full_name,
                            entity.entity_type,
                        )
                        continue

                    # Insert into Weaviate with embedding
                    try:
                        text = get_entity_text_for_embedding(entity)
                        logger.debug("Getting embedding for: %s...", text[:100])
                        vector = get_embedding(text)
                        collection.data.insert(
                            entity.to_properties(),
                            uuid=entity.uuid,
                            vector=vector,
                        )
                        entities_inserted += 1

                        if entities_inserted % 10 == 0:
                            emit_progress(
                                "ingesting",
                                entities_inserted,
                                config.max_entities or 0,
                                f"Inserted {entities_inserted} entities",
                            )
                            logger.info("Inserted %d entities so far", entities_inserted)

                    except httpx.TimeoutException as e:
                        errors += 1
                        logger.warning(
                            "Timeout inserting %s: %s",
                            entity.full_name,
                            e,
                        )
                    except httpx.RequestError as e:
                        errors += 1
                        logger.warning(
                            "Request error inserting %s: %s",
                            entity.full_name,
                            e,
                        )
                    except Exception as e:
                        errors += 1
                        logger.warning(
                            "Failed to insert %s: %s",
                            entity.full_name,
                            e,
                        )

        if cancelled:
            emit_progress("cancelled", entities_processed, 0, "Scraping cancelled")
        else:
            emit_progress(
                "complete",
                entities_processed,
                entities_processed,
                f"Completed: {entities_inserted} entities inserted",
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
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    else:
        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(level)


def main(argv: Optional[List[str]] = None) -> None:
    """
    CLI entry point for Drupal API scraper.

    Args:
        argv: Optional command line arguments (for testing)

    Raises:
        SystemExit: On command failure
    """
    parser = argparse.ArgumentParser(
        description="Drupal API scraper for Weaviate ingestion.",
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
        help="Maximum number of entities to scrape.",
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
        help=f"Entities per batch before longer pause (default: {DEFAULT_BATCH_SIZE}).",
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
                stats = get_collection_stats(client)
                logger.info("DrupalAPI collection status: %s", stats)
                print(f"Collection exists: {stats['exists']}")
                print(f"Total entities: {stats['object_count']}")
                if stats["entity_counts"]:
                    print("Entity breakdown:")
                    for etype, count in sorted(stats["entity_counts"].items()):
                        print(f"  {etype}: {count}")

        elif args.command == "reindex":
            with WeaviateConnection() as client:
                logger.info("Reindexing: deleting and recreating collection")
                create_drupal_api_collection(client, force_reindex=True)

            config = ScrapeConfig(
                request_delay=args.delay,
                batch_size=args.batch_size,
                batch_delay=args.batch_delay,
                max_entities=args.limit,
                dry_run=args.dry_run,
            )
            result = scrape_drupal_api(config=config)
            logger.info("Reindex complete: %s", result)

        else:  # scrape
            config = ScrapeConfig(
                request_delay=args.delay,
                batch_size=args.batch_size,
                batch_delay=args.batch_delay,
                max_entities=args.limit,
                dry_run=args.dry_run,
            )
            result = scrape_drupal_api(config=config)
            logger.info("Scrape complete: %s", result)

    except Exception as e:
        logger.exception("Command failed: %s", e)
        exit_code = 1

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
