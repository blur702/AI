"""
Congressional Voting Records Scraper.

Fetches roll call votes from the Congress.gov API and stores them in Weaviate's
CongressionalData collection with member-level voting positions.

Requires a Congress.gov API key (CONGRESS_API_KEY environment variable).
Get one at: https://api.congress.gov/sign-up/

Usage:
    python -m api_gateway.services.congressional_votes_scraper scrape
    python -m api_gateway.services.congressional_votes_scraper scrape --max-votes 100
    python -m api_gateway.services.congressional_votes_scraper status
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from ..utils.embeddings import get_embedding
from ..utils.logger import get_logger
from .congressional_schema import (
    CongressionalData,
    compute_congressional_content_hash,
    generate_congressional_uuid,
    migrate_add_voting_fields,
)
from .weaviate_connection import (
    CONGRESSIONAL_DATA_COLLECTION_NAME,
    WeaviateConnection,
)

logger = get_logger("api_gateway.congressional_votes_scraper")

# Congress.gov API configuration
CONGRESS_API_BASE = "https://api.congress.gov/v3"
DEFAULT_REQUEST_DELAY = 0.5  # Faster than web scraping since it's an API
DEFAULT_CONGRESS = 119  # Current congress (2025-2026)
DEFAULT_SESSION = 1


@dataclass
class VoteScrapeConfig:
    """Configuration for voting records scraping."""

    congress: int = DEFAULT_CONGRESS
    session: int = DEFAULT_SESSION
    max_votes: int | None = None
    request_delay: float = DEFAULT_REQUEST_DELAY
    dry_run: bool = False


ProgressCallback = Callable[[str, int, int, str], None]
CancelCheck = Callable[[], bool]


@dataclass
class VoteInfo:
    """Information about a single roll call vote."""

    roll_call_number: int
    congress: int
    session: int
    vote_date: str
    vote_question: str
    vote_result: str
    bill_number: str
    bill_title: str
    url: str


@dataclass
class MemberVote:
    """A member's position on a vote."""

    member_name: str
    bioguide_id: str
    state: str
    district: str
    party: str
    vote_position: str  # Yea, Nay, Present, Not Voting


class CongressionalVotesScraper:
    """
    Scraper for congressional voting records using Congress.gov API.

    Fetches House roll call votes and individual member voting positions,
    then stores them in the CongressionalData collection.
    """

    def __init__(
        self,
        config: VoteScrapeConfig,
        progress_callback: ProgressCallback | None = None,
        check_cancelled: CancelCheck | None = None,
    ) -> None:
        self.config = config
        self.progress_callback = progress_callback
        self.check_cancelled = check_cancelled
        self._client: httpx.Client | None = None
        self._api_key = os.environ.get("CONGRESS_API_KEY", "")
        self._last_request_time = 0.0

        if not self._api_key:
            logger.warning("CONGRESS_API_KEY not set. Get one at https://api.congress.gov/sign-up/")

    def __enter__(self) -> CongressionalVotesScraper:
        self._client = httpx.Client(
            http2=True,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def _is_cancelled(self) -> bool:
        if self.check_cancelled:
            try:
                return bool(self.check_cancelled())
            except Exception:
                pass
        return False

    def _emit_progress(self, phase: str, current: int, total: int, message: str) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(phase, current, total, message)
            except Exception:
                pass

    def _rate_limit(self) -> None:
        """Apply rate limiting between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.request_delay:
            time.sleep(self.config.request_delay - elapsed)
        self._last_request_time = time.time()

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Make an API request to Congress.gov."""
        if not self._client:
            raise RuntimeError("HTTP client not initialized")

        if not self._api_key:
            logger.error("CONGRESS_API_KEY not set")
            return None

        self._rate_limit()

        url = f"{CONGRESS_API_BASE}{endpoint}"
        request_params = {"api_key": self._api_key, "format": "json"}
        if params:
            request_params.update(params)

        try:
            response = self._client.get(url, params=request_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "API request failed for %s: %s %s",
                endpoint,
                exc.response.status_code,
                exc.response.text[:200],
            )
            return None
        except Exception as exc:
            logger.warning("API request error for %s: %s", endpoint, exc)
            return None

    def fetch_vote_list(
        self, congress: int, session: int, offset: int = 0, limit: int = 250
    ) -> list[dict]:
        """
        Fetch list of House roll call votes.

        Args:
            congress: Congress number (e.g., 119)
            session: Session number (1 or 2)
            offset: Starting offset for pagination
            limit: Number of votes to fetch (max 250)

        Returns:
            List of vote summary dictionaries
        """
        endpoint = f"/house-vote/{congress}/{session}"
        params = {"offset": offset, "limit": min(limit, 250)}

        data = self._api_request(endpoint, params)
        if not data:
            return []

        votes = data.get("houseVotes", [])
        logger.info(
            "Fetched %d votes for Congress %d Session %d (offset %d)",
            len(votes),
            congress,
            session,
            offset,
        )
        return votes

    def fetch_vote_details(self, congress: int, session: int, roll_call: int) -> VoteInfo | None:
        """
        Fetch details for a specific vote.

        Args:
            congress: Congress number
            session: Session number
            roll_call: Roll call vote number

        Returns:
            VoteInfo object or None if fetch failed
        """
        endpoint = f"/house-vote/{congress}/{session}/{roll_call}"
        data = self._api_request(endpoint)

        if not data:
            return None

        vote_data = data.get("houseVote", {})
        if not vote_data:
            return None

        # Extract bill info if available
        bill_info = vote_data.get("bill", {})
        bill_number = ""
        bill_title = ""
        if bill_info:
            bill_type = bill_info.get("type", "")
            bill_num = bill_info.get("number", "")
            if bill_type and bill_num:
                bill_number = f"{bill_type} {bill_num}"
            bill_title = bill_info.get("title", "")

        return VoteInfo(
            roll_call_number=roll_call,
            congress=congress,
            session=session,
            vote_date=vote_data.get("date", ""),
            vote_question=vote_data.get("question", ""),
            vote_result=vote_data.get("result", ""),
            bill_number=bill_number,
            bill_title=bill_title,
            url=f"https://www.congress.gov/roll-call-votes/{congress}/{session}/{roll_call}",
        )

    def fetch_member_votes(self, congress: int, session: int, roll_call: int) -> list[MemberVote]:
        """
        Fetch individual member votes for a roll call.

        Args:
            congress: Congress number
            session: Session number
            roll_call: Roll call vote number

        Returns:
            List of MemberVote objects
        """
        endpoint = f"/house-vote/{congress}/{session}/{roll_call}/members"
        data = self._api_request(endpoint)

        if not data:
            return []

        members = []
        member_votes = data.get("memberVotes", [])

        for mv in member_votes:
            member_info = mv.get("member", {})
            if not member_info:
                continue

            # Extract name
            name = member_info.get("name", "")
            if not name:
                first = member_info.get("firstName", "")
                last = member_info.get("lastName", "")
                name = f"{first} {last}".strip()

            members.append(
                MemberVote(
                    member_name=name,
                    bioguide_id=member_info.get("bioguideId", ""),
                    state=member_info.get("state", ""),
                    district=str(member_info.get("district", "")),
                    party=member_info.get("party", ""),
                    vote_position=mv.get("vote", "Not Voting"),
                )
            )

        logger.debug("Fetched %d member votes for roll call %d", len(members), roll_call)
        return members

    def scrape_votes(self) -> Generator[CongressionalData, None, None]:
        """
        Scrape voting records and yield CongressionalData objects.

        Fetches all available votes for the configured congress/session,
        then for each vote fetches individual member positions.

        Yields:
            CongressionalData objects for each member's vote on each roll call
        """
        congress = self.config.congress
        session = self.config.session
        max_votes = self.config.max_votes

        # Fetch vote list with pagination
        all_votes: list[dict] = []
        offset = 0

        while True:
            if self._is_cancelled():
                logger.info("Vote scraping cancelled")
                break

            votes = self.fetch_vote_list(congress, session, offset=offset)
            if not votes:
                break

            all_votes.extend(votes)
            offset += len(votes)

            if max_votes and len(all_votes) >= max_votes:
                all_votes = all_votes[:max_votes]
                break

            # Check if we got fewer than requested (end of list)
            if len(votes) < 250:
                break

        logger.info("Found %d votes to process", len(all_votes))

        # Process each vote
        for idx, vote_summary in enumerate(all_votes):
            if self._is_cancelled():
                break

            roll_call = (
                vote_summary.get("rollCallVoteNumber")
                or vote_summary.get("rollCallNumber")
                or vote_summary.get("voteNumber")
            )
            if not roll_call:
                continue

            self._emit_progress(
                "scrape_votes",
                idx + 1,
                len(all_votes),
                f"Processing roll call {roll_call}",
            )

            # Fetch vote details
            vote_info = self.fetch_vote_details(congress, session, roll_call)
            if not vote_info:
                logger.warning("Could not fetch details for roll call %d", roll_call)
                continue

            # Fetch member votes
            member_votes = self.fetch_member_votes(congress, session, roll_call)
            if not member_votes:
                logger.warning("No member votes for roll call %d", roll_call)
                continue

            # Create CongressionalData for each member's vote
            for member in member_votes:
                vote_id = f"{congress}-{session}-{roll_call}"

                # Build content text for semantic search
                content_parts = [
                    f"Roll Call Vote {roll_call}",
                    f"Congress {congress}, Session {session}",
                    f"Date: {vote_info.vote_date}",
                    f"Question: {vote_info.vote_question}",
                    f"Result: {vote_info.vote_result}",
                ]
                if vote_info.bill_number:
                    content_parts.append(f"Bill: {vote_info.bill_number}")
                if vote_info.bill_title:
                    content_parts.append(f"Title: {vote_info.bill_title}")
                content_parts.append(
                    f"{member.member_name} ({member.party}-{member.state}) voted: {member.vote_position}"
                )
                content_text = "\n".join(content_parts)

                # Generate stable UUID based on member + vote
                uuid_str = generate_congressional_uuid(
                    member_name=member.member_name,
                    url=f"{vote_info.url}#{member.bioguide_id}",
                )

                content_hash = compute_congressional_content_hash(
                    member_name=member.member_name,
                    content_text=content_text,
                    title=f"Vote on {vote_info.vote_question}",
                    url=vote_info.url,
                )

                data = CongressionalData(
                    member_name=member.member_name,
                    state=member.state,
                    district=member.district,
                    party=member.party,
                    chamber="House",
                    title=f"Vote on {vote_info.vote_question}",
                    topic="vote",
                    content_text=content_text,
                    url=vote_info.url,
                    content_hash=content_hash,
                    scraped_at=datetime.now(UTC).isoformat(),
                    uuid=uuid_str,
                    content_type="vote",
                    vote_id=vote_id,
                    bill_number=vote_info.bill_number,
                    bill_title=vote_info.bill_title,
                    vote_position=member.vote_position,
                    vote_date=vote_info.vote_date,
                    roll_call_number=roll_call,
                    vote_question=vote_info.vote_question,
                    vote_result=vote_info.vote_result,
                    congress=congress,
                    session=session,
                )

                yield data


def scrape_voting_records(
    config: VoteScrapeConfig | None = None,
    progress_callback: ProgressCallback | None = None,
    check_cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    """
    Scrape congressional voting records and store in Weaviate.

    Args:
        config: Scrape configuration (defaults to current congress)
        progress_callback: Optional callback for progress updates
        check_cancelled: Optional callback to check for cancellation

    Returns:
        Dictionary with scrape statistics
    """
    cfg = config or VoteScrapeConfig()

    stats: dict[str, Any] = {
        "votes_processed": 0,
        "member_votes_inserted": 0,
        "member_votes_updated": 0,
        "errors": 0,
        "cancelled": False,
    }

    if cfg.dry_run:
        logger.info("Running voting records scraper in dry-run mode")

    with WeaviateConnection() as client:
        # Ensure collection exists before migration
        from .congressional_schema import create_congressional_data_collection

        create_congressional_data_collection(client)

        # Run migration to add voting fields
        migrate_add_voting_fields(client)

        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        with CongressionalVotesScraper(
            cfg,
            progress_callback=progress_callback,
            check_cancelled=check_cancelled,
        ) as scraper:
            current_roll_call = None

            try:
                for data in scraper.scrape_votes():
                    if scraper._is_cancelled():
                        stats["cancelled"] = True
                        break

                    # Track unique votes
                    if data.roll_call_number != current_roll_call:
                        current_roll_call = data.roll_call_number
                        stats["votes_processed"] += 1

                    if cfg.dry_run:
                        continue

                    try:
                        # Generate embedding
                        vector = get_embedding(data.content_text)

                        # Check for existing record
                        try:
                            existing = collection.query.fetch_object_by_id(data.uuid)
                        except Exception:
                            existing = None

                        if existing and getattr(existing, "properties", None):
                            props = existing.properties or {}
                            if props.get("content_hash") == data.content_hash:
                                # Unchanged
                                continue

                            collection.data.update(
                                uuid=data.uuid,
                                properties=data.to_properties(),
                                vector=vector,
                            )
                            stats["member_votes_updated"] += 1
                        else:
                            collection.data.insert(
                                uuid=data.uuid,
                                properties=data.to_properties(),
                                vector=vector,
                            )
                            stats["member_votes_inserted"] += 1

                    except Exception as exc:
                        stats["errors"] += 1
                        logger.exception(
                            "Failed to store vote for %s on roll call %d: %s",
                            data.member_name,
                            data.roll_call_number,
                            exc,
                        )

            except Exception as exc:
                stats["errors"] += 1
                logger.exception("Unexpected error during vote scraping: %s", exc)

    return stats


def get_voting_stats() -> dict[str, Any]:
    """Get statistics about voting records in the collection."""
    with WeaviateConnection() as client:
        if not client.collections.exists(CONGRESSIONAL_DATA_COLLECTION_NAME):
            return {"exists": False, "vote_count": 0}

        collection = client.collections.get(CONGRESSIONAL_DATA_COLLECTION_NAME)

        # Count vote records
        try:
            from weaviate.classes.query import Filter

            result = collection.aggregate.over_all(
                total_count=True,
                filters=Filter.by_property("content_type").equal("vote"),
            )
            vote_count = result.total_count or 0
        except Exception as exc:
            logger.warning("Could not count votes: %s", exc)
            vote_count = 0

        return {
            "exists": True,
            "vote_count": vote_count,
        }


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Congressional voting records scraper")
    parser.add_argument(
        "command",
        choices=["scrape", "status"],
        help="Operation to perform",
    )
    parser.add_argument(
        "--max-votes",
        type=int,
        default=None,
        help="Maximum number of votes to scrape",
    )
    parser.add_argument(
        "--congress",
        type=int,
        default=DEFAULT_CONGRESS,
        help=f"Congress number (default: {DEFAULT_CONGRESS})",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=DEFAULT_SESSION,
        help=f"Session number (default: {DEFAULT_SESSION})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape without writing to Weaviate",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "scrape":
        cfg = VoteScrapeConfig(
            congress=args.congress,
            session=args.session,
            max_votes=args.max_votes,
            dry_run=args.dry_run,
        )
        result = scrape_voting_records(cfg)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    if args.command == "status":
        stats = get_voting_stats()
        print(json.dumps(stats, indent=2))
        sys.exit(0)
