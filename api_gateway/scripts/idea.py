"""
Quick idea/prompt capture CLI for dev sessions.

Captures ideas with minimal friction - just type and go.
Review and organize later.

Usage:
    # Quick capture (just the idea)
    python -m api_gateway.scripts.idea "Build a talking head pipeline"

    # With category
    python -m api_gateway.scripts.idea "Add voice cloning" --category talking-head

    # With context
    python -m api_gateway.scripts.idea "Use FLUX for faces" --context "Working on image generation"

    # With tags
    python -m api_gateway.scripts.idea "Optimize VRAM usage" --tags gpu,performance

    # With priority (0=low, higher=more urgent)
    python -m api_gateway.scripts.idea "Fix lip sync timing" --priority 2

    # List recent ideas
    python -m api_gateway.scripts.idea --list
    python -m api_gateway.scripts.idea --list --limit 20

    # List by category
    python -m api_gateway.scripts.idea --list --category talking-head

    # List uncaptured ideas
    python -m api_gateway.scripts.idea --list --status captured

    # Review an idea (mark as reviewed with notes)
    python -m api_gateway.scripts.idea --review <id> --notes "Good idea, do after v1"

    # Mark as implemented
    python -m api_gateway.scripts.idea --implement <id>

    # Discard an idea
    python -m api_gateway.scripts.idea --discard <id>

    # Search ideas
    python -m api_gateway.scripts.idea --search "voice cloning"

Shortcut (add to your shell profile):
    alias idea="python -m api_gateway.scripts.idea"

    Then just: idea "Your brilliant idea here"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, or_

# Add project root to path
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api_gateway.models.database import (  # noqa: E402
    AsyncSessionLocal,
    Idea,
    IdeaStatus,
    init_db,
)


async def capture_idea(
    prompt: str,
    category: Optional[str] = None,
    context: Optional[str] = None,
    tags: Optional[List[str]] = None,
    priority: int = 0,
    source: str = "dev-session",
    session_id: Optional[str] = None,
) -> Idea:
    """Capture a new idea to the database."""
    async with AsyncSessionLocal() as session:
        idea = Idea(
            prompt=prompt,
            category=category,
            context=context,
            tags=tags,
            priority=priority,
            source=source,
            session_id=session_id,
            status=IdeaStatus.captured,
        )
        session.add(idea)
        await session.commit()
        await session.refresh(idea)
        return idea


async def list_ideas(
    limit: int = 10,
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Idea]:
    """List ideas with optional filters."""
    async with AsyncSessionLocal() as session:
        query = select(Idea).order_by(Idea.created_at.desc())

        if category:
            query = query.where(Idea.category == category)

        if status:
            query = query.where(Idea.status == IdeaStatus(status))

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Idea.prompt.ilike(search_pattern),
                    Idea.context.ilike(search_pattern),
                    Idea.notes.ilike(search_pattern),
                )
            )

        query = query.limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())


async def get_idea(idea_id: str) -> Optional[Idea]:
    """Get a single idea by ID (supports short ID prefix matching)."""
    async with AsyncSessionLocal() as session:
        # Support short ID prefix matching (first 8 chars)
        result = await session.execute(
            select(Idea).where(Idea.id.startswith(idea_id))
        )
        return result.scalar_one_or_none()


async def update_idea_status(
    idea_id: str,
    status: IdeaStatus,
    notes: Optional[str] = None,
) -> Optional[Idea]:
    """Update an idea's status (supports short ID prefix matching)."""
    async with AsyncSessionLocal() as session:
        # Support short ID prefix matching (first 8 chars)
        result = await session.execute(
            select(Idea).where(Idea.id.startswith(idea_id))
        )
        idea = result.scalar_one_or_none()

        if not idea:
            return None

        idea.status = status

        if notes:
            idea.notes = notes

        now = datetime.now(timezone.utc)
        if status == IdeaStatus.reviewed:
            idea.reviewed_at = now
        elif status == IdeaStatus.implemented:
            idea.implemented_at = now

        await session.commit()
        await session.refresh(idea)
        return idea


def format_idea(idea: Idea, verbose: bool = False) -> str:
    """Format an idea for display."""
    # Status indicators (ASCII-safe for Windows console)
    status_indicator = {
        IdeaStatus.captured: "[NEW]",
        IdeaStatus.reviewed: "[REV]",
        IdeaStatus.in_progress: "[WIP]",
        IdeaStatus.implemented: "[DONE]",
        IdeaStatus.discarded: "[X]",
    }
    indicator = status_indicator.get(idea.status, "[?]")

    # Priority indicator
    priority_str = ""
    if idea.priority > 0:
        priority_str = f" [P{idea.priority}]"

    # Category
    category_str = ""
    if idea.category:
        category_str = f" [{idea.category}]"

    # Tags
    tags_str = ""
    if idea.tags:
        tags_str = f" #{' #'.join(idea.tags)}"

    # Time
    time_str = idea.created_at.strftime("%Y-%m-%d %H:%M")

    # Short ID (first 8 chars)
    short_id = idea.id[:8]

    if verbose:
        lines = [
            f"{indicator} [{short_id}]{priority_str}{category_str}",
            f"   {idea.prompt}",
            f"   Created: {time_str} | Status: {idea.status.value}",
        ]
        if idea.context:
            lines.append(f"   Context: {idea.context}")
        if idea.notes:
            lines.append(f"   Notes: {idea.notes}")
        if idea.tags:
            lines.append(f"   Tags: {tags_str}")
        return "\n".join(lines)
    else:
        # Truncate prompt for display
        prompt = idea.prompt[:60] + "..." if len(idea.prompt) > 60 else idea.prompt
        return f"{indicator} [{short_id}]{priority_str}{category_str} {prompt}{tags_str}"


async def main():
    parser = argparse.ArgumentParser(
        description="Quick idea/prompt capture for dev sessions"
    )

    # Capture mode (positional argument)
    parser.add_argument(
        "prompt",
        nargs="?",
        help="The idea/prompt to capture"
    )

    # Capture options
    parser.add_argument(
        "--category", "-c",
        help="Category for the idea (e.g., talking-head, ui, refactor)"
    )
    parser.add_argument(
        "--context", "-x",
        help="What you were working on when this idea came up"
    )
    parser.add_argument(
        "--tags", "-t",
        help="Comma-separated tags (e.g., gpu,performance,urgent)"
    )
    parser.add_argument(
        "--priority", "-p",
        type=int,
        default=0,
        help="Priority level (0=low, higher=more urgent)"
    )
    parser.add_argument(
        "--source", "-s",
        default="dev-session",
        help="Where the idea came from (default: dev-session)"
    )
    parser.add_argument(
        "--session",
        help="Session ID to group related ideas"
    )

    # List mode
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List recent ideas"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of ideas to list (default: 10)"
    )
    parser.add_argument(
        "--status",
        choices=["captured", "reviewed", "in_progress", "implemented", "discarded"],
        help="Filter by status"
    )
    parser.add_argument(
        "--search",
        help="Search ideas by keyword"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show more details"
    )

    # Update modes
    parser.add_argument(
        "--review",
        metavar="ID",
        help="Mark an idea as reviewed"
    )
    parser.add_argument(
        "--implement",
        metavar="ID",
        help="Mark an idea as implemented"
    )
    parser.add_argument(
        "--discard",
        metavar="ID",
        help="Discard an idea"
    )
    parser.add_argument(
        "--start",
        metavar="ID",
        help="Mark an idea as in progress"
    )
    parser.add_argument(
        "--notes", "-n",
        help="Notes to add when updating status"
    )

    args = parser.parse_args()

    # Initialize database
    await init_db()

    # Handle update modes
    if args.review:
        idea = await update_idea_status(args.review, IdeaStatus.reviewed, args.notes)
        if idea:
            print(f"[OK] Marked as reviewed: {format_idea(idea)}")
        else:
            print(f"[ERROR] Idea not found: {args.review}")
        return

    if args.implement:
        idea = await update_idea_status(args.implement, IdeaStatus.implemented, args.notes)
        if idea:
            print(f"[OK] Marked as implemented: {format_idea(idea)}")
        else:
            print(f"[ERROR] Idea not found: {args.implement}")
        return

    if args.discard:
        idea = await update_idea_status(args.discard, IdeaStatus.discarded, args.notes)
        if idea:
            print(f"[X] Discarded: {format_idea(idea)}")
        else:
            print(f"[ERROR] Idea not found: {args.discard}")
        return

    if args.start:
        idea = await update_idea_status(args.start, IdeaStatus.in_progress, args.notes)
        if idea:
            print(f"[START] In progress: {format_idea(idea)}")
        else:
            print(f"[ERROR] Idea not found: {args.start}")
        return

    # Handle list mode
    if args.list or args.search:
        ideas = await list_ideas(
            limit=args.limit,
            category=args.category,
            status=args.status,
            search=args.search,
        )

        if not ideas:
            print("No ideas found.")
            return

        print(f"\nIdeas ({len(ideas)} shown):\n")
        for idea in ideas:
            print(format_idea(idea, verbose=args.verbose))
            if args.verbose:
                print()
        return

    # Handle capture mode
    if args.prompt:
        tags = args.tags.split(",") if args.tags else None

        idea = await capture_idea(
            prompt=args.prompt,
            category=args.category,
            context=args.context,
            tags=tags,
            priority=args.priority,
            source=args.source,
            session_id=args.session,
        )

        print(f"[+] Captured: {format_idea(idea)}")
        return

    # No action specified
    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
