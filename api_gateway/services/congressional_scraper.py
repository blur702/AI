from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Deque, Dict, Generator, List, Optional
from urllib.parse import urlparse

if TYPE_CHECKING:
    import weaviate
    from .base_doc_scraper import DocPage

import httpx
import feedparser
from bs4 import BeautifulSoup

from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .base_doc_scraper import BaseDocScraper, ScraperConfig as DocScraperConfig
from .congressional_schema import (
    CongressionalData,
    compute_congressional_content_hash,
    create_congressional_data_collection,
    generate_congressional_uuid,
    get_congressional_stats,
)
from .weaviate_connection import (
    CONGRESSIONAL_DATA_COLLECTION_NAME,
    WeaviateConnection,
)


logger = get_logger("api_gateway.congressional_scraper")


HOUSE_FEED_URL = "https://housegovfeeds.house.gov/feeds/Member/Json"
DEFAULT_REQUEST_DELAY = 2.0
DEFAULT_BATCH_SIZE = 10
DEFAULT_BATCH_DELAY = 5.0


@dataclass
class ScrapeConfig:
    request_delay: float = DEFAULT_REQUEST_DELAY
    batch_size: int = DEFAULT_BATCH_SIZE
    batch_delay: float = DEFAULT_BATCH_DELAY
    max_members: Optional[int] = None
    max_pages_per_member: int = 5
    max_press_pages: int = 500  # Higher limit for press/news pages
    scrape_rss: bool = True  # Whether to scrape RSS feeds
    discover_newsroom: bool = True  # Whether to discover newsroom pages
    dry_run: bool = False


ProgressCallback = Callable[[str, int, int, str], None]
CancelCheck = Callable[[], bool]
PauseCheck = Callable[[], bool]


@dataclass
class MemberInfo:
    name: str
    state: str
    district: str
    party: str
    chamber: str  # "House" or "Senate"
    website_url: str
    rss_feed_url: str


class CongressionalDocScraper(BaseDocScraper):
    """
    Congressional website scraper built on BaseDocScraper.

    Uses BaseDocScraper for HTTP behavior (rate limiting, robots.txt, link
    extraction) while producing CongressionalData objects for storage in the
    CongressionalData collection.
    """

    def __init__(
        self,
        config: ScrapeConfig,
        progress_callback: Optional[ProgressCallback] = None,
        check_cancelled: Optional[CancelCheck] = None,
        check_paused: Optional[PauseCheck] = None,
    ) -> None:
        # Map congressional scrape config to BaseDocScraper config
        doc_config = DocScraperConfig(
            min_delay=config.request_delay,
            max_delay=config.request_delay,
            batch_size=config.batch_size,
            batch_pause_min=config.batch_delay,
            batch_pause_max=config.batch_delay,
        )

        super().__init__(
            name="congressional_docs",
            base_url="https://house.gov",
            collection_name=CONGRESSIONAL_DATA_COLLECTION_NAME,
            config=doc_config,
        )

        self.scrape_config = config
        self.progress_callback = progress_callback
        self.check_cancelled = check_cancelled
        self.check_paused = check_paused

        self._members: List[MemberInfo] = []
        self._member_by_host: Dict[str, MemberInfo] = {}
        self.members_attempted: int = 0

    # ------------------------------------------------------------------
    # Context manager for HTTP client
    # ------------------------------------------------------------------

    def __enter__(self) -> "CongressionalDocScraper":
        if self._client is None:
            self._client = httpx.Client(
                http2=True,
                follow_redirects=self.config.follow_redirects,
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                logger.exception("Error closing HTTP client")
            finally:
                self._client = None

    # ------------------------------------------------------------------
    # BaseDocScraper abstract methods
    # ------------------------------------------------------------------

    def get_seed_urls(self) -> list[str]:
        """
        Use the House JSON member feed to construct seed URLs.

        Seed URLs are the member website homepages; additional pages are
        discovered via BaseDocScraper.extract_links.
        """
        self._members = self.fetch_member_feed()
        if self.scrape_config.max_members is not None:
            self._members = self._members[: self.scrape_config.max_members]

        self._member_by_host = {}
        for member in self._members:
            host = urlparse(member.website_url).netloc
            if host:
                self._member_by_host[host] = member

        return [m.website_url for m in self._members]

    def parse_page(self, url: str, html: str) -> "DocPage | None":
        """
        Minimal DocPage parser to satisfy BaseDocScraper.

        The congressional pipeline primarily uses CongressionalData objects
        rather than DocPage, but this implementation allows the generic
        BaseDocScraper.scrape() flow to work if needed.
        """
        from .base_doc_scraper import DocPage  # Local import to avoid cycle

        soup = BeautifulSoup(html, "html.parser")
        title = self._extract_title_from_page(soup, url)
        content = self._extract_content_from_page(soup)

        if not content:
            return None

        return DocPage(
            url=url,
            title=title,
            content=content,
            section="congressional",
        )

    def create_collection(self, client: "weaviate.WeaviateClient") -> None:
        create_congressional_data_collection(client)

    # ------------------------------------------------------------------
    # URL filtering / content helpers
    # ------------------------------------------------------------------

    def is_valid_url(self, url: str) -> bool:
        """
        Restrict crawling to *.house.gov and skip non-content paths.
        """
        parsed = urlparse(url)
        base_parsed = urlparse(self.base_url)

        # Must be same root domain (e.g., *.house.gov)
        if not parsed.netloc.endswith(base_parsed.netloc):
            return False

        path = parsed.path.lower()

        # Skip common non-content paths
        blocked_patterns = [
            "/search",
            "/login",
            "/sign-in",
            "/signin",
            "/account",
            "/admin",
        ]
        for pattern in blocked_patterns:
            if pattern in path:
                return False

        # Reuse BaseDocScraper's generic skip patterns for assets/files
        asset_patterns = [
            r"/download",
            r"\.(pdf|zip|tar|gz|exe|dmg|pkg)$",
            r"\.(png|jpg|jpeg|gif|svg|ico|webp)$",
            r"\.(css|js|json|xml|woff|woff2|ttf|eot)$",
        ]
        for pattern in asset_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False

        return True

    def _emit_progress(
        self,
        phase: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback(phase, current, total, message)
        except Exception:
            logger.exception("Progress callback raised an exception")

    def _is_cancelled(self) -> bool:
        try:
            if self.check_cancelled:
                return bool(self.check_cancelled())
        except Exception:
            logger.exception("Cancellation callback raised an exception")
        return False

    def _is_paused(self) -> bool:
        try:
            if self.check_paused:
                return bool(self.check_paused())
        except Exception:
            logger.exception("Pause callback raised an exception")
        return False

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _infer_topic_from_url(self, url: str) -> str:
        """
        Infer a simple topic label from the URL path.

        Uses the first non-empty path segment as a lightweight topic so
        that topic-based filtering is possible in queries.
        """
        parsed = urlparse(url)
        parts = [p for p in (parsed.path or "").split("/") if p]
        return parts[0].lower() if parts else "general"

    def _extract_content_from_page(
        self,
        soup: BeautifulSoup,
    ) -> str:
        if not soup:
            return ""

        container = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id="content")
            or soup.find(class_="content")
            or soup.find(class_="main-content")
        )
        if not container:
            container = soup.body or soup

        for selector in ["header", "nav", "footer", "aside"]:
            for el in container.find_all(selector):
                el.decompose()

        text = container.get_text(separator=" ", strip=True)
        cleaned = self._clean_text(text)
        if len(cleaned) > 10000:
            cleaned = cleaned[:10000]
        return cleaned

    def _extract_title_from_page(
        self,
        soup: BeautifulSoup,
        url: str,
    ) -> str:
        if soup.title and soup.title.string:
            return self._clean_text(soup.title.string)

        h1 = soup.find("h1")
        if h1 and h1.get_text():
            return self._clean_text(h1.get_text())

        parsed = urlparse(url)
        path = parsed.path.rstrip("/").split("/")[-1] or parsed.netloc
        return self._clean_text(path)

    # ------------------------------------------------------------------
    # JSON and RSS fetching (shared client + rate limiting)
    # ------------------------------------------------------------------

    def _fetch_json(self, url: str) -> Optional[Dict[str, Any]]:
        if self._is_cancelled():
            return None
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")

        # Use BaseDocScraper rate limiting
        self._apply_rate_limit()

        try:
            response = self._client.get(
                url,
                timeout=httpx.Timeout(
                    timeout=self.config.read_timeout,
                    connect=self.config.connect_timeout,
                ),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch JSON from %s: %s", url, exc)
            return None

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            logger.warning("Failed to decode JSON from %s: %s", url, exc)
            return None

    def _fetch_rss(self, url: str) -> Optional[str]:
        if self._is_cancelled():
            return None
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")

        self._apply_rate_limit()

        try:
            response = self._client.get(
                url,
                headers=self._get_headers(),
                timeout=httpx.Timeout(
                    timeout=self.config.read_timeout,
                    connect=self.config.connect_timeout,
                ),
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch RSS from %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Member feed and site scraping
    # ------------------------------------------------------------------

    def fetch_member_feed(self) -> List[MemberInfo]:
        logger.info("Fetching House member feed from %s", HOUSE_FEED_URL)
        data = self._fetch_json(HOUSE_FEED_URL)
        if not data:
            return []

        members: List[MemberInfo] = []

        # Handle different feed formats:
        # - {"items": [...]} - simple list
        # - {"members": [...]} - list under members key
        # - {"members": {"member": [...]}} - nested structure from house.gov
        items = data.get("items") or []
        if not items:
            members_data = data.get("members")
            if isinstance(members_data, dict):
                items = members_data.get("member") or []
            elif isinstance(members_data, list):
                items = members_data

        for item in items:
            try:
                # Handle house.gov nested structure: {"member-info": {...}, "website": "..."}
                member_info = item.get("member-info", {})
                if member_info:
                    name = member_info.get("official-name") or member_info.get("namelist") or ""
                    state_data = member_info.get("state", {})
                    if isinstance(state_data, dict):
                        state = state_data.get("postal-code") or ""
                    else:
                        state = str(state_data) if state_data else ""
                    district = member_info.get("district") or ""
                    party = member_info.get("party") or ""
                else:
                    # Fallback for simpler feed formats
                    name = item.get("name") or item.get("FullName") or ""
                    state = item.get("state") or item.get("State") or ""
                    district = item.get("district") or item.get("District") or ""
                    party = item.get("party") or item.get("Party") or ""

                chamber = item.get("chamber") or item.get("Chamber") or "House"
                website_url = (
                    item.get("website") or item.get("WebsiteUrl") or ""
                )
                rss_feed_url = (
                    item.get("rss_feed_url")
                    or item.get("RssFeedUrl")
                    or ""
                )

                if not website_url:
                    continue

                members.append(
                    MemberInfo(
                        name=name,
                        state=state,
                        district=str(district),
                        party=party,
                        chamber=chamber,
                        website_url=website_url,
                        rss_feed_url=rss_feed_url,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to parse member entry: %s", exc)

        logger.info("Parsed %d members from House feed", len(members))
        return members

    def scrape_single_member(
        self,
        member: MemberInfo,
        visited: Optional[set[str]] = None,
    ) -> Generator[CongressionalData, None, None]:
        """
        Scrape a single member's website and yield CongressionalData objects.

        This method is designed to be called by parallel workers, each handling
        a subset of members.

        Args:
            member: The MemberInfo object for the member to scrape.
            visited: Optional set of already-visited URLs to avoid duplicates
                     across multiple calls. If None, a new set is created.

        Yields:
            CongressionalData objects for each page scraped.
        """
        if visited is None:
            visited = set()

        if not member.website_url:
            logger.warning("No website URL for member: %s", member.name)
            return

        queue: Deque[str] = deque([member.website_url])
        pages_scraped_for_member = 0

        while queue and pages_scraped_for_member < self.scrape_config.max_pages_per_member:
            if self._is_cancelled():
                logger.info("Scrape cancelled while processing %s", member.name)
                break

            if self._is_paused():
                logger.info("Scrape paused; waiting before continuing")
                while self._is_paused():
                    time.sleep(1.0)

            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            try:
                html = self.fetch_page(url)
                if not html:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                title = self._extract_title_from_page(soup, url)
                content = self._extract_content_from_page(soup)
                if not content:
                    continue

                topic = self._infer_topic_from_url(url)
                scraped_at = datetime.now(timezone.utc).isoformat()
                content_hash = compute_congressional_content_hash(
                    member_name=member.name,
                    content_text=content,
                    title=title,
                    url=url,
                )
                uuid_str = generate_congressional_uuid(
                    member_name=member.name,
                    url=url,
                )

                data = CongressionalData(
                    member_name=member.name,
                    state=member.state,
                    district=member.district,
                    party=member.party,
                    chamber=member.chamber,
                    title=title,
                    topic=topic,
                    content_text=content,
                    url=url,
                    rss_feed_url=member.rss_feed_url,
                    content_hash=content_hash,
                    scraped_at=scraped_at,
                    uuid=uuid_str,
                )

                pages_scraped_for_member += 1
                yield data

                # Extract and queue new links
                new_links = self.extract_links(soup, url)
                for link in new_links:
                    if link not in visited and link not in queue:
                        queue.append(link)

            except Exception as exc:
                logger.warning(
                    "Failed to process page %s for member %s: %s",
                    url,
                    member.name,
                    exc,
                )
                continue

    def scrape_all_members(self) -> Generator[CongressionalData, None, None]:
        """
        Crawl member websites and yield CongressionalData objects.

        Uses BaseDocScraper.fetch_page and extract_links for site-level
        crawling, while tracking member attempts for higher-level stats.
        """
        members = self.fetch_member_feed()
        if self.scrape_config.max_members is not None:
            members = members[: self.scrape_config.max_members]

        total_members = len(members)
        visited: set[str] = set()

        for idx, member in enumerate(members, start=1):
            if self._is_cancelled():
                logger.info(
                    "Scrape cancelled before processing member %s",
                    member.name,
                )
                break

            self.members_attempted += 1

            self._emit_progress(
                phase="scrape_members",
                current=idx,
                total=total_members,
                message=f"Scraping website for {member.name}",
            )

            queue: List[str] = [member.website_url]
            pages_scraped_for_member = 0

            while queue and pages_scraped_for_member < self.scrape_config.max_pages_per_member:
                if self._is_cancelled():
                    logger.info(
                        "Scrape cancelled while processing %s",
                        member.name,
                    )
                    break

                while self._is_paused():
                    logger.info("Scrape paused; waiting before continuing")
                    time.sleep(1.0)

                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                html = self.fetch_page(url)
                if not html:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                title = self._extract_title_from_page(soup, url)
                content = self._extract_content_from_page(soup)
                if not content:
                    continue

                topic = self._infer_topic_from_url(url)

                scraped_at = datetime.now(timezone.utc).isoformat()
                content_hash = compute_congressional_content_hash(
                    member_name=member.name,
                    content_text=content,
                    title=title,
                    url=url,
                )
                uuid_str = generate_congressional_uuid(
                    member_name=member.name,
                    url=url,
                )

                data = CongressionalData(
                    member_name=member.name,
                    state=member.state,
                    district=member.district,
                    party=member.party,
                    chamber=member.chamber,
                    title=title,
                    topic=topic,
                    content_text=content,
                    url=url,
                    rss_feed_url=member.rss_feed_url,
                    content_hash=content_hash,
                    scraped_at=scraped_at,
                    uuid=uuid_str,
                )

                pages_scraped_for_member += 1
                yield data

                # Discover additional links using BaseDocScraper.extract_links
                new_links = self.extract_links(url, html)
                for link in new_links:
                    if (
                        pages_scraped_for_member
                        + len(queue)
                        >= self.scrape_config.max_pages_per_member
                    ):
                        break
                    if link not in visited and link not in queue:
                        queue.append(link)

    # ------------------------------------------------------------------
    # RSS feed handling
    # ------------------------------------------------------------------

    def parse_rss_feed(
        self,
        rss_url: str,
        member: MemberInfo,
    ) -> List[CongressionalData]:
        """
        Parse an RSS feed for a member using the shared HTTP client and
        rate-limiting behavior.
        """
        if not rss_url:
            return []

        if self._is_cancelled():
            return []

        logger.info("Fetching RSS feed for %s: %s", member.name, rss_url)
        entries: List[CongressionalData] = []

        rss_text = self._fetch_rss(rss_url)
        if not rss_text:
            return entries

        try:
            parsed = feedparser.parse(rss_text)
        except Exception as exc:
            logger.warning("Failed to parse RSS feed %s: %s", rss_url, exc)
            return entries

        for entry in parsed.entries:
            if self._is_cancelled():
                logger.info(
                    "Scrape cancelled while parsing RSS for %s",
                    member.name,
                )
                break

            while self._is_paused():
                logger.info("RSS parsing paused; waiting before continuing")
                time.sleep(1.0)

            try:
                title = getattr(entry, "title", "") or ""
                link = getattr(entry, "link", "") or ""
                summary = getattr(entry, "summary", "") or ""

                if not link:
                    continue

                try:
                    if getattr(entry, "published_parsed", None):
                        published_dt = datetime(
                            *entry.published_parsed[:6],
                            tzinfo=timezone.utc,
                        )
                    else:
                        published_dt = datetime.now(timezone.utc)
                except Exception:
                    published_dt = datetime.now(timezone.utc)

                scraped_at = published_dt.isoformat()
                content_text = self._clean_text(summary)
                topic = self._infer_topic_from_url(link)
                content_hash = compute_congressional_content_hash(
                    member_name=member.name,
                    content_text=content_text,
                    title=title,
                    url=link,
                )
                uuid_str = generate_congressional_uuid(
                    member_name=member.name,
                    url=link,
                )

                entries.append(
                    CongressionalData(
                        member_name=member.name,
                        state=member.state,
                        district=member.district,
                        party=member.party,
                        chamber=member.chamber,
                        content_text=content_text,
                        title=title,
                        topic=topic,
                        url=link,
                        rss_feed_url=member.rss_feed_url,
                        content_hash=content_hash,
                        scraped_at=scraped_at,
                        uuid=uuid_str,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Failed to parse RSS entry for %s: %s",
                    member.name,
                    exc,
                )

        logger.info(
            "Parsed %d entries from RSS feed for %s",
            len(entries),
            member.name,
        )
        return entries


def scrape_congressional_data(
    config: Optional[ScrapeConfig] = None,
    progress_callback: Optional[ProgressCallback] = None,
    check_cancelled: Optional[CancelCheck] = None,
    check_paused: Optional[PauseCheck] = None,
) -> Dict[str, Any]:
    cfg = config or ScrapeConfig()

    stats: Dict[str, Any] = {
        "members_processed": 0,
        "pages_scraped": 0,
        "pages_updated": 0,
        "pages_inserted": 0,
        "errors": 0,
        "cancelled": False,
    }

    if cfg.dry_run:
        logger.info("Running congressional scraper in dry-run mode")

    with WeaviateConnection() as client:
        create_congressional_data_collection(client)
        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        with CongressionalDocScraper(
            cfg,
            progress_callback=progress_callback,
            check_cancelled=check_cancelled,
            check_paused=check_paused,
        ) as scraper:
            try:
                for data in scraper.scrape_all_members():
                    if scraper._is_cancelled():
                        stats["cancelled"] = True
                        logger.info("Scrape cancelled; stopping ingestion loop")
                        break

                    stats["pages_scraped"] += 1

                    if cfg.dry_run:
                        continue

                    try:
                        vector = get_embedding(data.content_text)

                        try:
                            existing = collection.query.fetch_object_by_id(
                                data.uuid
                            )
                        except Exception:
                            existing = None

                        if existing and getattr(
                            existing,
                            "properties",
                            None,
                        ):
                            props = existing.properties or {}
                            if (
                                props.get("content_hash")
                                == data.content_hash
                            ):
                                # Unchanged
                                continue

                            collection.data.update(
                                uuid=data.uuid,
                                properties=data.to_properties(),
                                vector=vector,
                            )
                            stats["pages_updated"] += 1
                        else:
                            collection.data.insert(
                                uuid=data.uuid,
                                properties=data.to_properties(),
                                vector=vector,
                            )
                            stats["pages_inserted"] += 1
                    except Exception as exc:
                        stats["errors"] += 1
                        logger.exception(
                            "Failed to upsert congressional document %s: %s",
                            data.uuid,
                            exc,
                        )
            except Exception as exc:
                stats["errors"] += 1
                logger.exception(
                    "Unexpected error during congressional scraping: %s",
                    exc,
                )

            # Ensure member attempts are counted even if no pages were scraped
            stats["members_processed"] = scraper.members_attempted

        # Optionally log collection stats for visibility
        try:
            col_stats = get_congressional_stats(client)
            logger.info(
                "CongressionalData collection now has %d objects (exists=%s)",
                col_stats.get("object_count", 0),
                col_stats.get("exists", False),
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch CongressionalData collection stats: %s",
                exc,
            )

    return stats


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Congressional website scraper",
    )
    parser.add_argument(
        "command",
        choices=["scrape", "status", "reindex"],
        help="Operation to perform",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape without writing to Weaviate",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of members to scrape",
    )

    args = parser.parse_args()

    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "scrape":
        cfg = ScrapeConfig(
            max_members=args.limit,
            dry_run=args.dry_run,
        )
        result = scrape_congressional_data(cfg)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    if args.command == "status":
        with WeaviateConnection() as client:
            stats = get_congressional_stats(client)
        print(json.dumps(stats, indent=2))
        sys.exit(0)

    if args.command == "reindex":
        cfg = ScrapeConfig(
            max_members=args.limit,
            dry_run=args.dry_run,
        )
        with WeaviateConnection() as client:
            create_congressional_data_collection(client, force_reindex=True)
        result = scrape_congressional_data(cfg)
        print(json.dumps(result, indent=2))
        sys.exit(0)
