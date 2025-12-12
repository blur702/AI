from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, List, Optional
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
from .topic_classifier import classify_text


logger = get_logger("api_gateway.congressional_scraper")


HOUSE_FEED_URL = "https://housegovfeeds.house.gov/feeds/Member/Json"
CLERK_VOTES_BASE_URL = "https://clerk.house.gov/evs"
CLERK_VOTES_INDEX_URL = "https://clerk.house.gov/Votes"
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
    scrape_rss: bool = True  # Scrape RSS feeds for press releases
    discover_newsroom: bool = True  # Try common newsroom URL patterns
    dry_run: bool = False
    scrape_votes: bool = False
    max_votes: int = 100
    vote_year: Optional[int] = None


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


@dataclass
class VoteRecord:
    """Individual vote record from clerk.house.gov."""

    roll_number: int
    congress: int
    session: int
    vote_date: str
    vote_question: str
    vote_type: str
    vote_result: str
    bill_number: Optional[str]
    bill_title: Optional[str]
    member_votes: Dict[str, str]  # bioguide_id -> vote (Yea/Nay/Present/Not Voting)


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

    def _get_url_priority(self, url: str) -> int:
        """
        Score URL priority for crawl ordering (lower = higher priority).

        Press releases and news pages are prioritized to ensure they are
        scraped first when crawling member websites.
        """
        path = urlparse(url).path.lower()

        # Highest priority: press releases and news (score 0)
        press_patterns = [
            "/press",
            "/news",
            "/media",
            "/newsroom",
            "/press-release",
            "/pressrelease",
            "/press_release",
            "/releases",
            "/statements",
            "/announcement",
        ]
        for pattern in press_patterns:
            if pattern in path:
                return 0

        # Medium priority: legislation and issues (score 1)
        issue_patterns = [
            "/legislation",
            "/issues",
            "/bills",
            "/votes",
            "/committees",
            "/floor",
        ]
        for pattern in issue_patterns:
            if pattern in path:
                return 1

        # Lower priority: everything else (score 2)
        return 2

    def _sort_queue_by_priority(self, queue: List[str]) -> List[str]:
        """Sort URL queue to prioritize press releases and news."""
        return sorted(queue, key=self._get_url_priority)

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

        # Handle House.gov JSON structure: {"members": {"member": [...]}}
        members_data = data.get("members", {})
        if isinstance(members_data, dict):
            items = members_data.get("member", [])
        else:
            # Fallback for alternative formats
            items = data.get("items") or data.get("members") or []

        for item in items:
            try:
                # House.gov structure has member-info nested object
                member_info = item.get("member-info", {})
                if member_info:
                    # Parse House.gov format
                    name = (
                        member_info.get("official-name")
                        or member_info.get("namelist")
                        or item.get("housegov-display-name")
                        or ""
                    )
                    state_info = member_info.get("state", {})
                    if isinstance(state_info, dict):
                        state = state_info.get("postal-code", "")
                    else:
                        state = str(state_info) if state_info else ""
                    district = member_info.get("district", "")
                    party = member_info.get("caucus") or member_info.get("party", "")
                    website_url = item.get("website", "")
                else:
                    # Fallback for simpler formats
                    name = item.get("name") or item.get("FullName") or ""
                    state = item.get("state") or item.get("State") or ""
                    district = item.get("district") or item.get("District") or ""
                    party = item.get("party") or item.get("Party") or ""
                    website_url = item.get("website") or item.get("WebsiteUrl") or ""

                chamber = "House"  # This feed is House-specific
                rss_feed_url = item.get("rss_feed_url", "")

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

    def scrape_all_members(self) -> Generator[CongressionalData, None, None]:
        """
        Crawl member websites and yield CongressionalData objects.

        Uses BaseDocScraper.fetch_page and extract_links for site-level
        crawling, while tracking member attempts for higher-level stats.
        """
        # Skip member scraping if max_members is 0 (votes-only mode)
        if self.scrape_config.max_members == 0:
            logger.info("Skipping member website scraping (max_members=0)")
            return

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
                # Sort queue by priority (press releases first)
                queue = self._sort_queue_by_priority(queue)
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

    def _is_press_url(self, url: str) -> bool:
        """Check if URL is a press/news page."""
        path = urlparse(url).path.lower()
        press_patterns = [
            "/press", "/news", "/media", "/newsroom",
            "/press-release", "/pressrelease", "/press_release",
            "/releases", "/statements", "/announcement",
            "/media-center", "/mediacenter",
        ]
        return any(pattern in path for pattern in press_patterns)

    def _discover_newsroom_urls(self, member: MemberInfo) -> List[str]:
        """Generate common newsroom URL patterns to try for a member."""
        base = member.website_url.rstrip("/")
        # Only try the most common patterns to avoid excessive requests
        patterns = [
            "/media", "/media-center", "/news", "/newsroom",
        ]
        return [f"{base}{p}" for p in patterns]

    def _extract_pagination_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract pagination links from press listing pages."""
        pagination_links = []
        parsed_base = urlparse(base_url)

        # Common pagination patterns
        pagination_selectors = [
            "a.page-link", "a.pagination-link", ".pagination a",
            "a[rel='next']", ".pager a", ".nav-links a",
            "a.next", "a.older", "a[aria-label*='next']",
            "a[aria-label*='Next']", ".next-page a",
        ]

        for selector in pagination_selectors:
            try:
                for link in soup.select(selector):
                    href = link.get("href")
                    if href:
                        # Handle relative URLs
                        if href.startswith("/"):
                            href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                        elif not href.startswith("http"):
                            continue
                        if href not in pagination_links:
                            pagination_links.append(href)
            except Exception:
                continue

        # Also look for ?page= or /page/ patterns in any links
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "page=" in href or "/page/" in href:
                if href.startswith("/"):
                    href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                elif not href.startswith("http"):
                    continue
                if href not in pagination_links:
                    pagination_links.append(href)

        return pagination_links

    def scrape_single_member(
        self, member: MemberInfo
    ) -> Generator[CongressionalData, None, None]:
        """
        Scrape a single member's website with full press release coverage.

        Uses separate limits for press vs non-press pages:
        - Non-press pages: limited by max_pages_per_member
        - Press pages: limited by max_press_pages (much higher)

        Also discovers newsroom URLs and follows pagination.

        Args:
            member: MemberInfo object with member details

        Yields:
            CongressionalData objects for each scraped page
        """
        visited: set[str] = set()
        press_queue: List[str] = []
        general_queue: List[str] = [member.website_url]
        press_pages_scraped = 0
        general_pages_scraped = 0

        # Discover newsroom URLs if enabled
        if self.scrape_config.discover_newsroom:
            newsroom_urls = self._discover_newsroom_urls(member)
            for url in newsroom_urls:
                if url not in press_queue:
                    press_queue.append(url)

        # Main scraping loop - prioritize press content
        while press_queue or general_queue:
            if self._is_cancelled():
                break

            while self._is_paused():
                time.sleep(1.0)

            # Prioritize press queue, but respect limits
            if press_queue and press_pages_scraped < self.scrape_config.max_press_pages:
                url = press_queue.pop(0)
            elif general_queue and general_pages_scraped < self.scrape_config.max_pages_per_member:
                url = general_queue.pop(0)
            else:
                # Both queues exhausted or limits reached
                break

            # Skip if already visited
            if url in visited:
                continue
            visited.add(url)

            # Fetch the page
            html = self.fetch_page(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            title = self._extract_title_from_page(soup, url)
            content = self._extract_content_from_page(soup)

            # Extract links regardless of content
            new_links = self.extract_links(url, html)
            is_press = self._is_press_url(url)

            # If this is a press listing page, also get pagination links
            if is_press:
                pagination_links = self._extract_pagination_links(soup, url)
                new_links.extend(pagination_links)

            # Add discovered links to appropriate queues
            for link in new_links:
                if link in visited:
                    continue
                if self._is_press_url(link):
                    if link not in press_queue:
                        press_queue.append(link)
                else:
                    if link not in general_queue:
                        general_queue.append(link)

            # Skip pages without content
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

            if is_press:
                press_pages_scraped += 1
            else:
                general_pages_scraped += 1

            yield data

        logger.info(
            "Scraped %s: %d press pages, %d general pages",
            member.name,
            press_pages_scraped,
            general_pages_scraped,
        )

    # ------------------------------------------------------------------
    # Voting record scraping (clerk.house.gov)
    # ------------------------------------------------------------------

    def fetch_vote_xml(self, year: int, roll_number: int) -> Optional[str]:
        """Fetch roll call vote XML from clerk.house.gov."""
        url = f"{CLERK_VOTES_BASE_URL}/{year}/roll{roll_number:03d}.xml"
        return self.fetch_page(url)

    def parse_vote_xml(self, xml_content: str) -> Optional[VoteRecord]:
        """Parse clerk.house.gov roll call vote XML into VoteRecord."""
        try:
            soup = BeautifulSoup(xml_content, "lxml-xml")

            # Extract vote metadata
            vote_metadata = soup.find("vote-metadata")
            if not vote_metadata:
                return None

            congress = int(vote_metadata.find("congress").text) if vote_metadata.find("congress") else 0
            # Session may be ordinal like "1st", "2nd" - extract numeric part
            session_elem = vote_metadata.find("session")
            session = 0
            if session_elem and session_elem.text:
                session_match = re.match(r"(\d+)", session_elem.text)
                session = int(session_match.group(1)) if session_match else 0
            roll_number = int(vote_metadata.find("rollcall-num").text) if vote_metadata.find("rollcall-num") else 0
            vote_date = vote_metadata.find("action-date").text if vote_metadata.find("action-date") else ""
            vote_question = vote_metadata.find("vote-question").text if vote_metadata.find("vote-question") else ""
            vote_type = vote_metadata.find("vote-type").text if vote_metadata.find("vote-type") else ""
            vote_result = vote_metadata.find("vote-result").text if vote_metadata.find("vote-result") else ""

            # Extract bill info if present
            legis_num = vote_metadata.find("legis-num")
            bill_number = legis_num.text if legis_num else None
            vote_desc = vote_metadata.find("vote-desc")
            bill_title = vote_desc.text if vote_desc else None

            # Extract member votes
            member_votes: Dict[str, str] = {}
            vote_data = soup.find("vote-data")
            if vote_data:
                for recorded_vote in vote_data.find_all("recorded-vote"):
                    legislator = recorded_vote.find("legislator")
                    vote_elem = recorded_vote.find("vote")
                    if legislator and vote_elem:
                        bioguide_id = legislator.get("name-id", "")
                        if bioguide_id:
                            member_votes[bioguide_id] = vote_elem.text

            return VoteRecord(
                roll_number=roll_number,
                congress=congress,
                session=session,
                vote_date=vote_date,
                vote_question=vote_question,
                vote_type=vote_type,
                vote_result=vote_result,
                bill_number=bill_number,
                bill_title=bill_title,
                member_votes=member_votes,
            )
        except Exception as exc:
            logger.warning("Failed to parse vote XML: %s", exc)
            return None

    def _find_latest_roll_number(self, year: int) -> int:
        """
        Find the latest roll call vote number for a given year.

        Uses binary search to efficiently probe clerk.house.gov for the
        highest valid roll number.
        """
        # Binary search between 1 and 700 (typical max votes per year)
        low, high = 1, 700
        latest_found = 0

        while low <= high:
            mid = (low + high) // 2
            url = f"{CLERK_VOTES_BASE_URL}/{year}/roll{mid:03d}.xml"

            try:
                if self._client is None:
                    break

                self._apply_rate_limit()
                response = self._client.head(
                    url,
                    timeout=httpx.Timeout(timeout=10.0, connect=5.0),
                )

                if response.status_code == 200:
                    # This roll exists, try higher
                    latest_found = mid
                    low = mid + 1
                else:
                    # This roll doesn't exist, try lower
                    high = mid - 1
            except Exception:
                # Assume not found
                high = mid - 1

        return latest_found

    def scrape_recent_votes(
        self,
        year: int = None,
        max_votes: int = 100,
    ) -> Generator[CongressionalData, None, None]:
        """
        Scrape recent roll call votes and yield CongressionalData objects.

        Each vote becomes a document in the CongressionalData collection with
        the full vote breakdown stored in content_text.
        """
        if year is None:
            year = datetime.now().year

        logger.info("Scraping recent votes for year %d (max %d)", year, max_votes)

        # Find latest roll number by probing (index page doesn't have direct links)
        # Start from a high estimate and binary search down
        latest_roll = self._find_latest_roll_number(year)
        if latest_roll == 0:
            logger.warning("Could not find any votes for year %d", year)
            return

        logger.info("Found latest roll number for %d: %d", year, latest_roll)

        # Scrape votes from latest backwards
        votes_scraped = 0
        for roll_num in range(latest_roll, 0, -1):
            if self._is_cancelled():
                break
            if votes_scraped >= max_votes:
                break

            while self._is_paused():
                time.sleep(1.0)

            xml_content = self.fetch_vote_xml(year, roll_num)
            if not xml_content:
                continue

            vote = self.parse_vote_xml(xml_content)
            if not vote:
                continue

            # Create content text with vote summary
            content_parts = [
                f"Roll Call Vote {vote.roll_number}",
                f"Congress: {vote.congress}, Session: {vote.session}",
                f"Date: {vote.vote_date}",
                f"Question: {vote.vote_question}",
                f"Type: {vote.vote_type}",
                f"Result: {vote.vote_result}",
            ]
            if vote.bill_number:
                content_parts.append(f"Bill: {vote.bill_number}")
            if vote.bill_title:
                content_parts.append(f"Title: {vote.bill_title}")

            # Tally votes
            yea_count = sum(1 for v in vote.member_votes.values() if v == "Yea")
            nay_count = sum(1 for v in vote.member_votes.values() if v == "Nay")
            present_count = sum(1 for v in vote.member_votes.values() if v == "Present")
            not_voting = sum(1 for v in vote.member_votes.values() if v == "Not Voting")
            content_parts.append(f"Yea: {yea_count}, Nay: {nay_count}, Present: {present_count}, Not Voting: {not_voting}")

            content_text = "\n".join(content_parts)

            # Store member votes as JSON in a structured way
            votes_json = json.dumps(vote.member_votes)
            content_text += f"\n\nMember Votes:\n{votes_json}"

            url = f"{CLERK_VOTES_BASE_URL}/{year}/roll{roll_num:03d}.xml"
            title = f"Roll Call {roll_num}: {vote.vote_question[:100]}" if vote.vote_question else f"Roll Call {roll_num}"

            scraped_at = datetime.now(timezone.utc).isoformat()
            content_hash = compute_congressional_content_hash(
                member_name="House of Representatives",
                content_text=content_text,
                title=title,
                url=url,
            )
            uuid_str = generate_congressional_uuid(
                member_name="House Vote Record",
                url=url,
            )

            data = CongressionalData(
                member_name="House of Representatives",
                state="US",
                district="",
                party="",
                chamber="House",
                title=title,
                topic="votes",
                content_text=content_text,
                url=url,
                rss_feed_url="",
                content_hash=content_hash,
                scraped_at=scraped_at,
                uuid=uuid_str,
            )

            votes_scraped += 1
            self._emit_progress(
                phase="scrape_votes",
                current=votes_scraped,
                total=max_votes,
                message=f"Scraped vote {roll_num}: {vote.vote_question[:50]}...",
            )
            yield data

        logger.info("Scraped %d votes for year %d", votes_scraped, year)

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
        "votes_scraped": 0,
        "votes_inserted": 0,
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
                        # Classify document topics before storing
                        try:
                            classification = classify_text(
                                data.title, data.content_text
                            )
                            data.policy_topics = classification.topics
                        except Exception as clf_exc:
                            logger.warning(
                                "Classification failed for %s: %s",
                                data.uuid,
                                clf_exc,
                            )
                            data.policy_topics = []

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

            # Scrape voting records if configured
            if cfg.scrape_votes and not stats["cancelled"]:
                logger.info("Starting vote scraping (max %d votes)", cfg.max_votes)
                vote_year = cfg.vote_year or datetime.now().year

                try:
                    for data in scraper.scrape_recent_votes(
                        year=vote_year,
                        max_votes=cfg.max_votes,
                    ):
                        if scraper._is_cancelled():
                            stats["cancelled"] = True
                            logger.info("Vote scrape cancelled")
                            break

                        stats["votes_scraped"] += 1

                        if cfg.dry_run:
                            continue

                        try:
                            # Classify vote topics before storing
                            try:
                                classification = classify_text(
                                    data.title, data.content_text
                                )
                                data.policy_topics = classification.topics
                            except Exception as clf_exc:
                                logger.warning(
                                    "Vote classification failed for %s: %s",
                                    data.uuid,
                                    clf_exc,
                                )
                                data.policy_topics = []

                            vector = get_embedding(data.content_text)

                            try:
                                existing = collection.query.fetch_object_by_id(
                                    data.uuid
                                )
                            except Exception:
                                existing = None

                            if existing and getattr(existing, "properties", None):
                                props = existing.properties or {}
                                if props.get("content_hash") == data.content_hash:
                                    continue

                                collection.data.update(
                                    uuid=data.uuid,
                                    properties=data.to_properties(),
                                    vector=vector,
                                )
                            else:
                                collection.data.insert(
                                    uuid=data.uuid,
                                    properties=data.to_properties(),
                                    vector=vector,
                                )
                                stats["votes_inserted"] += 1
                        except Exception as exc:
                            stats["errors"] += 1
                            logger.exception(
                                "Failed to upsert vote record %s: %s",
                                data.uuid,
                                exc,
                            )
                except Exception as exc:
                    stats["errors"] += 1
                    logger.exception(
                        "Unexpected error during vote scraping: %s",
                        exc,
                    )

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
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Max pages per member (default: 5, use 0 for unlimited)",
    )
    parser.add_argument(
        "--votes",
        action="store_true",
        help="Also scrape voting records from clerk.house.gov",
    )
    parser.add_argument(
        "--max-votes",
        type=int,
        default=100,
        help="Max voting records to scrape (default: 100)",
    )
    parser.add_argument(
        "--vote-year",
        type=int,
        default=None,
        help="Year for voting records (default: current year)",
    )
    parser.add_argument(
        "--votes-only",
        action="store_true",
        help="Only scrape voting records, skip member websites",
    )

    args = parser.parse_args()

    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "scrape":
        # 0 means unlimited pages
        max_pages = args.max_pages if args.max_pages > 0 else 10000

        # Handle --votes-only: skip member scraping, only scrape votes
        if args.votes_only:
            max_members = 0
            scrape_votes = True
        else:
            max_members = args.limit
            scrape_votes = args.votes

        cfg = ScrapeConfig(
            max_members=max_members,
            max_pages_per_member=max_pages,
            dry_run=args.dry_run,
            scrape_votes=scrape_votes,
            max_votes=args.max_votes,
            vote_year=args.vote_year,
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
        max_pages = args.max_pages if args.max_pages > 0 else 10000

        if args.votes_only:
            max_members = 0
            scrape_votes = True
        else:
            max_members = args.limit
            scrape_votes = args.votes

        cfg = ScrapeConfig(
            max_members=max_members,
            max_pages_per_member=max_pages,
            dry_run=args.dry_run,
            scrape_votes=scrape_votes,
            max_votes=args.max_votes,
            vote_year=args.vote_year,
        )
        with WeaviateConnection() as client:
            create_congressional_data_collection(client, force_reindex=True)
        result = scrape_congressional_data(cfg)
        print(json.dumps(result, indent=2))
        sys.exit(0)
