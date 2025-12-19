"""
Base Documentation Scraper with Anti-Ban Features.

Provides a robust foundation for scraping documentation sites with:
- Variable rate limiting (randomized delays with jitter)
- Rotating User-Agent strings
- Respect for robots.txt
- Exponential backoff on rate limits (429)
- Browser-like headers
- Request caching
- Checkpoint/resume support
- Configurable politeness settings

Usage:
    class MyDocScraper(BaseDocScraper):
        def __init__(self):
            super().__init__(
                name="my_docs",
                base_url="https://docs.example.com",
                collection_name="MyDocs",
            )

        def get_seed_urls(self) -> list[str]:
            return ["https://docs.example.com/api/"]

        def parse_page(self, url: str, html: str) -> DocPage | None:
            # Parse and return DocPage or None to skip
            ...
"""

import hashlib
import json
import random
import re
import time
from abc import ABC, abstractmethod
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import weaviate
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from api_gateway.services.weaviate_connection import WeaviateConnection
from api_gateway.utils.embeddings import get_embedding
from api_gateway.utils.logger import get_logger

logger = get_logger(__name__)

# Rotating User-Agent strings (common browsers)
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


@dataclass
class DocPage:
    """Represents a parsed documentation page."""

    url: str
    title: str
    content: str
    section: str = "reference"  # library, tutorial, reference, api, guide
    package: str = ""
    version: str = ""
    breadcrumb: str = ""
    code_examples: list[str] = field(default_factory=list)

    def to_properties(self) -> dict[str, Any]:
        """Convert to Weaviate properties dict."""
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content[:10000],  # Truncate for storage
            "section": self.section,
            "package": self.package,
            "version": self.version,
            "breadcrumb": self.breadcrumb,
            "code_examples": "\n---\n".join(self.code_examples[:10]),  # First 10 examples
        }

    def get_embedding_text(self) -> str:
        """Get text for embedding generation."""
        parts = [self.title]
        if self.breadcrumb:
            parts.append(self.breadcrumb)
        parts.append(self.content[:2000])  # Truncate for embedding
        return "\n\n".join(parts)


@dataclass
class ScraperConfig:
    """Configuration for scraper behavior."""

    # Rate limiting
    min_delay: float = 1.0  # Minimum seconds between requests
    max_delay: float = 3.0  # Maximum seconds between requests
    batch_size: int = 10  # Requests before batch pause
    batch_pause_min: float = 5.0  # Minimum batch pause
    batch_pause_max: float = 15.0  # Maximum batch pause

    # Retry settings
    max_retries: int = 3
    backoff_base: float = 2.0  # Exponential backoff base
    backoff_max: float = 60.0  # Maximum backoff seconds

    # Timeouts
    connect_timeout: float = 10.0
    read_timeout: float = 30.0

    # Limits
    max_pages: int = 0  # 0 = unlimited
    max_depth: int = 10  # Maximum link depth from seed URLs

    # Content settings
    max_content_length: int = 10000
    max_embedding_length: int = 2000

    # Politeness
    respect_robots_txt: bool = True
    follow_redirects: bool = True

    # Cache/checkpoint
    checkpoint_interval: int = 50  # Save checkpoint every N pages
    cache_dir: Path = field(default_factory=lambda: Path("data/scraper_cache"))


class BaseDocScraper(ABC):
    """
    Base class for documentation scrapers with anti-ban features.

    Subclasses must implement:
    - get_seed_urls(): Return list of starting URLs
    - parse_page(url, html): Parse HTML and return DocPage or None
    - create_collection(client): Create Weaviate collection if needed
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        collection_name: str,
        config: ScraperConfig | None = None,
    ):
        self.name = name
        self.base_url = base_url
        self.collection_name = collection_name
        self.config = config or ScraperConfig()

        # State
        self._client: httpx.Client | None = None
        self._robots_parser: RobotFileParser | None = None
        self._seen_urls: set[str] = set()
        self._request_count: int = 0
        self._last_request_time: float = 0
        self._current_user_agent: str = random.choice(USER_AGENTS)

        # Statistics
        self.stats = {
            "pages_scraped": 0,
            "pages_skipped": 0,
            "pages_failed": 0,
            "pages_cached": 0,
            "rate_limits_hit": 0,
        }

        # Ensure cache dir exists
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def get_seed_urls(self) -> list[str]:
        """Return list of seed URLs to start scraping from."""
        pass

    @abstractmethod
    def parse_page(self, url: str, html: str) -> DocPage | None:
        """
        Parse HTML content and return DocPage.

        Return None to skip this page (e.g., not a doc page).
        """
        pass

    @abstractmethod
    def create_collection(self, client: "weaviate.WeaviateClient") -> None:
        """Create Weaviate collection if it doesn't exist."""
        pass

    def is_valid_url(self, url: str) -> bool:
        """
        Check if URL should be scraped.

        Override to add custom URL filtering.
        """
        parsed = urlparse(url)
        base_parsed = urlparse(self.base_url)

        # Must be same domain
        if parsed.netloc != base_parsed.netloc:
            return False

        # Skip common non-doc paths
        skip_patterns = [
            r"/search",
            r"/login",
            r"/signup",
            r"/download",
            r"\.(pdf|zip|tar|gz|exe|dmg|pkg)$",
            r"\.(png|jpg|jpeg|gif|svg|ico|webp)$",
            r"\.(css|js|json|xml|woff|woff2|ttf|eot)$",
        ]
        for pattern in skip_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False

        return True

    def extract_links(self, url: str, html: str) -> list[str]:
        """Extract links from HTML for crawling."""
        soup = BeautifulSoup(html, "html.parser")
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Convert to absolute URL
            absolute_url = urljoin(url, href)
            # Remove fragment
            absolute_url = absolute_url.split("#")[0]

            if absolute_url and self.is_valid_url(absolute_url):
                links.append(absolute_url)

        return list(set(links))  # Deduplicate

    def _get_random_delay(self) -> float:
        """Get randomized delay with jitter."""
        base_delay = random.uniform(self.config.min_delay, self.config.max_delay)
        # Add small jitter (up to 20% variation)
        jitter = base_delay * random.uniform(-0.2, 0.2)
        return max(self.config.min_delay, base_delay + jitter)

    def _get_batch_pause(self) -> float:
        """Get randomized batch pause duration."""
        return random.uniform(self.config.batch_pause_min, self.config.batch_pause_max)

    def _rotate_user_agent(self) -> None:
        """Rotate to a new random User-Agent."""
        self._current_user_agent = random.choice(USER_AGENTS)

    def _get_headers(self) -> dict[str, str]:
        """Get browser-like headers."""
        return {
            "User-Agent": self._current_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    def _check_robots_txt(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        if not self.config.respect_robots_txt:
            return True

        if self._robots_parser is None:
            self._robots_parser = RobotFileParser()
            robots_url = urljoin(self.base_url, "/robots.txt")
            try:
                self._robots_parser.set_url(robots_url)
                self._robots_parser.read()
            except Exception as e:
                logger.warning("Failed to read robots.txt: %s", e)
                return True  # Allow if can't read robots.txt

        return self._robots_parser.can_fetch(self._current_user_agent, url)

    def _apply_rate_limit(self) -> None:
        """Apply rate limiting with variable delays."""
        self._request_count += 1

        # Check for batch pause
        if self._request_count % self.config.batch_size == 0:
            pause = self._get_batch_pause()
            logger.info(
                "[%s] Batch pause: %.1fs after %d requests", self.name, pause, self._request_count
            )
            time.sleep(pause)
            # Rotate User-Agent after batch pause
            self._rotate_user_agent()
            return

        # Apply regular delay
        elapsed = time.time() - self._last_request_time
        delay = self._get_random_delay()

        if elapsed < delay:
            sleep_time = delay - elapsed
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def _get_cache_path(self, url: str) -> Path:
        """Get cache file path for URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.config.cache_dir / self.name / f"{url_hash}.html"

    def _get_from_cache(self, url: str) -> str | None:
        """Get cached HTML for URL."""
        cache_path = self._get_cache_path(url)
        if cache_path.exists():
            try:
                return cache_path.read_text(encoding="utf-8")
            except Exception:
                pass
        return None

    def _save_to_cache(self, url: str, html: str) -> None:
        """Save HTML to cache."""
        cache_path = self._get_cache_path(url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cache_path.write_text(html, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to cache %s: %s", url, e)

    def fetch_page(self, url: str, use_cache: bool = True) -> str | None:
        """
        Fetch a page with rate limiting and retries.

        Returns HTML content or None on failure.
        """
        # Check cache first
        if use_cache:
            cached = self._get_from_cache(url)
            if cached:
                self.stats["pages_cached"] += 1
                return cached

        # Check robots.txt
        if not self._check_robots_txt(url):
            logger.info("[%s] Blocked by robots.txt: %s", self.name, url)
            self.stats["pages_skipped"] += 1
            return None

        # Apply rate limiting
        self._apply_rate_limit()

        # Retry loop with exponential backoff
        for attempt in range(self.config.max_retries):
            try:
                response = self._client.get(
                    url,
                    headers=self._get_headers(),
                    follow_redirects=self.config.follow_redirects,
                    timeout=httpx.Timeout(
                        timeout=self.config.read_timeout,
                        connect=self.config.connect_timeout,
                    ),
                )

                # Handle rate limiting
                if response.status_code == 429:
                    self.stats["rate_limits_hit"] += 1
                    backoff = min(
                        self.config.backoff_base ** (attempt + 1), self.config.backoff_max
                    )
                    # Add jitter to backoff
                    backoff *= random.uniform(0.8, 1.2)
                    logger.warning(
                        "[%s] Rate limited (429), backing off %.1fs: %s", self.name, backoff, url
                    )
                    time.sleep(backoff)
                    self._rotate_user_agent()
                    continue

                # Handle server errors
                if response.status_code >= 500:
                    backoff = self.config.backoff_base**attempt
                    logger.warning(
                        "[%s] Server error %d, retrying in %.1fs: %s",
                        self.name,
                        response.status_code,
                        backoff,
                        url,
                    )
                    time.sleep(backoff)
                    continue

                # Handle client errors (skip)
                if response.status_code >= 400:
                    logger.debug("[%s] Client error %d: %s", self.name, response.status_code, url)
                    self.stats["pages_skipped"] += 1
                    return None

                # Success
                html = response.text
                self._save_to_cache(url, html)
                return html

            except httpx.TimeoutException:
                backoff = self.config.backoff_base**attempt
                logger.warning("[%s] Timeout, retrying in %.1fs: %s", self.name, backoff, url)
                time.sleep(backoff)

            except httpx.RequestError as e:
                logger.warning("[%s] Request error: %s - %s", self.name, url, e)
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.backoff_base**attempt)

        self.stats["pages_failed"] += 1
        return None

    def _get_checkpoint_path(self) -> Path:
        """Get checkpoint file path."""
        return self.config.cache_dir / f"{self.name}_checkpoint.json"

    def _save_checkpoint(self, queue: list[str], depth_map: dict[str, int]) -> None:
        """Save scraping progress."""
        checkpoint = {
            "seen_urls": list(self._seen_urls),
            "queue": queue,
            "depth_map": depth_map,
            "stats": self.stats,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        checkpoint_path = self._get_checkpoint_path()
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2))
        logger.info(
            "[%s] Checkpoint saved: %d seen, %d queued", self.name, len(self._seen_urls), len(queue)
        )

    def _load_checkpoint(self) -> tuple[list[str], dict[str, int]] | None:
        """Load checkpoint if exists."""
        checkpoint_path = self._get_checkpoint_path()
        if not checkpoint_path.exists():
            return None

        try:
            checkpoint = json.loads(checkpoint_path.read_text())
            self._seen_urls = set(checkpoint["seen_urls"])
            self.stats = checkpoint["stats"]
            logger.info(
                "[%s] Resumed from checkpoint: %d seen, %d queued",
                self.name,
                len(self._seen_urls),
                len(checkpoint["queue"]),
            )
            return checkpoint["queue"], checkpoint["depth_map"]
        except Exception as e:
            logger.warning("[%s] Failed to load checkpoint: %s", self.name, e)
            return None

    def generate_uuid(self, page: DocPage) -> str:
        """Generate stable UUID for a doc page."""
        import uuid

        key = f"{self.name}:{page.url}"
        return str(uuid.UUID(hashlib.md5(key.encode()).hexdigest()))

    def scrape(
        self,
        resume: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Scrape documentation and store in Weaviate.

        Args:
            resume: Resume from checkpoint if available
            dry_run: Parse pages but don't store

        Returns:
            Statistics dict
        """
        logger.info("[%s] Starting scrape (dry_run=%s)", self.name, dry_run)

        # Initialize HTTP client
        self._client = httpx.Client(
            http2=True,
            follow_redirects=self.config.follow_redirects,
        )

        try:
            # Load checkpoint or initialize
            checkpoint = self._load_checkpoint() if resume else None
            if checkpoint:
                queue, depth_map = checkpoint
            else:
                queue = self.get_seed_urls()
                depth_map = dict.fromkeys(queue, 0)
                self._seen_urls = set()

            # Use context manager for proper resource cleanup
            weaviate_context = WeaviateConnection() if not dry_run else nullcontext()
            with weaviate_context as weaviate_client:
                collection = None
                if not dry_run and weaviate_client is not None:
                    self.create_collection(weaviate_client)
                    collection = weaviate_client.collections.get(self.collection_name)

                pages_processed = 0

                while queue:
                    url = queue.pop(0)
                    current_depth = depth_map.get(url, 0)

                    # Skip if already seen
                    if url in self._seen_urls:
                        continue
                    self._seen_urls.add(url)

                    # Check depth limit
                    if current_depth > self.config.max_depth:
                        continue

                    # Check page limit
                    if self.config.max_pages > 0 and pages_processed >= self.config.max_pages:
                        logger.info(
                            "[%s] Reached max pages limit (%d)", self.name, self.config.max_pages
                        )
                        break

                    # Fetch page
                    html = self.fetch_page(url)
                    if not html:
                        continue

                    # Parse page
                    try:
                        page = self.parse_page(url, html)
                    except Exception as e:
                        logger.warning("[%s] Parse error for %s: %s", self.name, url, e)
                        self.stats["pages_failed"] += 1
                        continue

                    if page is None:
                        self.stats["pages_skipped"] += 1
                        continue

                    # Store in Weaviate
                    if collection is not None:
                        try:
                            uuid = self.generate_uuid(page)
                            embedding_text = page.get_embedding_text()
                            vector = get_embedding(embedding_text)

                            # Check if exists (may raise exception if not found)
                            try:
                                existing = collection.query.fetch_object_by_id(uuid)
                            except Exception:
                                existing = None

                            if existing is not None:
                                collection.data.update(
                                    uuid=uuid,
                                    properties=page.to_properties(),
                                    vector=vector,
                                )
                            else:
                                collection.data.insert(
                                    uuid=uuid,
                                    properties=page.to_properties(),
                                    vector=vector,
                                )
                        except Exception as e:
                            logger.warning("[%s] Failed to store %s: %s", self.name, url, e)
                            self.stats["pages_failed"] += 1
                            continue

                    self.stats["pages_scraped"] += 1
                    pages_processed += 1

                    if pages_processed % 10 == 0:
                        logger.info(
                            "[%s] Progress: %d scraped, %d queued, %d seen",
                            self.name,
                            pages_processed,
                            len(queue),
                            len(self._seen_urls),
                        )

                    # Extract and queue new links
                    new_links = self.extract_links(url, html)
                    for link in new_links:
                        if link not in self._seen_urls and link not in depth_map:
                            queue.append(link)
                            depth_map[link] = current_depth + 1

                    # Save checkpoint periodically
                    if pages_processed % self.config.checkpoint_interval == 0:
                        self._save_checkpoint(queue, depth_map)

                # Final checkpoint
                self._save_checkpoint(queue, depth_map)

            logger.info("[%s] Scrape complete: %s", self.name, self.stats)
            return self.stats

        finally:
            if self._client:
                self._client.close()
