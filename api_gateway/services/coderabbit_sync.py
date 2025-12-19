"""
CodeRabbit PR Comment Sync to Error Database.

Fetches CodeRabbit review comments from GitHub PRs and stores them
in the PostgreSQL error database with full file/line info.

Usage:
    # Sync errors from a specific PR
    python -m api_gateway.services.coderabbit_sync --pr 6

    # Sync from all open PRs
    python -m api_gateway.services.coderabbit_sync --all-open

    # Dry run (show what would be stored)
    python -m api_gateway.services.coderabbit_sync --pr 6 --dry-run

    # Clear existing CodeRabbit errors before sync
    python -m api_gateway.services.coderabbit_sync --pr 6 --clear-existing

Requirements:
    - GitHub CLI (gh) must be installed and authenticated
    - PostgreSQL database must be running
"""

import argparse
import asyncio
import json
import logging
import re
import subprocess
from dataclasses import dataclass

from sqlalchemy import delete

from api_gateway.models.database import (
    AsyncSessionLocal,
    Error,
    ErrorSeverity,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Patterns to extract severity from CodeRabbit comments
SEVERITY_PATTERNS = {
    "critical": [
        r"Severity:\s*CRITICAL",
        r"_🔴\s*Critical_",
        r"\*\*Bug:\*\*.*CRITICAL",
    ],
    "error": [
        r"_🟠\s*Major_",
        r"Severity:\s*Major",
        r"_⚠️\s*Potential issue_.*_🟠\s*Major_",
    ],
    "warning": [
        r"_🟡\s*Minor_",
        r"Severity:\s*Minor",
        r"_⚠️\s*Potential issue_.*_🟡\s*Minor_",
    ],
    "info": [
        r"_🔵\s*Trivial_",
        r"_🧹\s*Nitpick_",
        r"Severity:\s*Low",
    ],
}


@dataclass
class CodeRabbitComment:
    """Parsed CodeRabbit review comment."""

    file_path: str
    line_number: int | None
    severity: str
    title: str
    body: str
    suggestion: str | None
    pr_number: int
    comment_id: str


def parse_severity(body: str) -> str:
    """Extract severity level from comment body."""
    for severity, patterns in SEVERITY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, body, re.IGNORECASE):
                return severity
    return "warning"  # Default


def parse_title(body: str) -> str:
    """Extract the main issue title from comment body."""
    # Look for bold text at the start
    match = re.search(r"\*\*([^*]+)\*\*", body)
    if match:
        return match.group(1).strip()

    # First line as fallback
    first_line = body.split("\n")[0].strip()
    # Remove markdown formatting
    first_line = re.sub(r"[_*`]", "", first_line)
    return first_line[:200] if first_line else "CodeRabbit Issue"


def parse_suggestion(body: str) -> str | None:
    """Extract code suggestion if present."""
    # Look for diff blocks
    diff_match = re.search(r"```diff\n(.*?)```", body, re.DOTALL)
    if diff_match:
        return diff_match.group(1).strip()

    # Look for suggested fix section
    fix_match = re.search(
        r"<summary>.*Suggested Fix.*</summary>\s*(.*?)</details>", body, re.DOTALL | re.IGNORECASE
    )
    if fix_match:
        return fix_match.group(1).strip()

    return None


def get_pr_comments(pr_number: int, repo: str = "blur702/AI") -> list[dict]:
    """Fetch PR review comments from GitHub API."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{pr_number}/comments"],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        )
        if not result.stdout:
            return []
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch PR comments: {e}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse PR comments JSON: {e}")
        return []


def get_open_prs(repo: str = "blur702/AI") -> list[int]:
    """Get list of open PR numbers."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--json", "number"],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        )
        if not result.stdout:
            return []
        prs = json.loads(result.stdout)
        return [pr["number"] for pr in prs]
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        logger.error(f"Failed to get open PRs: {e}")
        return []


def parse_comments(comments: list[dict], pr_number: int) -> list[CodeRabbitComment]:
    """Parse raw GitHub comments into CodeRabbitComment objects."""
    parsed = []

    for comment in comments:
        # Only process CodeRabbit comments
        user = comment.get("user", {})
        login = user.get("login", "")
        if not login.startswith("coderabbitai"):
            continue

        body = comment.get("body", "")
        if not body:
            continue

        # Skip non-issue comments (approvals, summaries, etc.)
        if "LGTM" in body or "looks good" in body.lower():
            continue

        file_path = comment.get("path", "")
        line_number = comment.get("line") or comment.get("original_line")
        comment_id = str(comment.get("id", ""))

        parsed.append(
            CodeRabbitComment(
                file_path=file_path or "unknown",
                line_number=line_number,
                severity=parse_severity(body),
                title=parse_title(body),
                body=body,
                suggestion=parse_suggestion(body),
                pr_number=pr_number,
                comment_id=comment_id,
            )
        )

    return parsed


def determine_service(file_path: str) -> str:
    """Determine service name from file path."""
    if "dashboard/frontend" in file_path:
        return "dashboard/frontend"
    if "dashboard/backend" in file_path:
        return "dashboard/backend"
    if "api_gateway" in file_path:
        return "api_gateway"
    if ".github" in file_path:
        return "github_actions"
    if "tests" in file_path:
        return "tests"
    return "coderabbit"


async def clear_coderabbit_errors():
    """Delete all existing CodeRabbit errors from database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(Error).where(Error.service.like("%coderabbit%")))
        await session.commit()
        return result.rowcount


async def store_comment(comment: CodeRabbitComment, dry_run: bool = False) -> str | None:
    """Store a CodeRabbit comment as an error in the database."""
    severity_map = {
        "critical": ErrorSeverity.critical,
        "error": ErrorSeverity.error,
        "warning": ErrorSeverity.warning,
        "info": ErrorSeverity.info,
    }

    service = determine_service(comment.file_path)

    # Build context with full info
    context = {
        "file_path": comment.file_path,
        "pr_number": comment.pr_number,
        "comment_id": comment.comment_id,
        "source": "coderabbit",
    }
    if comment.line_number:
        context["line_number"] = comment.line_number
    if comment.suggestion:
        context["suggestion"] = comment.suggestion[:2000]  # Truncate long suggestions

    # Build message
    message = comment.title
    if comment.file_path and comment.file_path != "unknown":
        loc = f"{comment.file_path}"
        if comment.line_number:
            loc += f":{comment.line_number}"
        message = f"[{loc}] {message}"

    if dry_run:
        logger.info(
            f"[DRY RUN] Would store: {severity_map[comment.severity].value.upper()} - {message[:100]}..."
        )
        return None

    async with AsyncSessionLocal() as session:
        error = Error(
            service=service,
            severity=severity_map.get(comment.severity, ErrorSeverity.warning),
            message=message,
            stack_trace=comment.body[:4000],  # Store full comment body as "stack trace"
            context=context,
            resolved=False,
        )
        session.add(error)
        await session.commit()
        await session.refresh(error)
        return error.id


async def sync_pr(pr_number: int, dry_run: bool = False) -> dict:
    """Sync CodeRabbit comments from a PR to the error database."""
    stats = {"critical": 0, "error": 0, "warning": 0, "info": 0, "total": 0}

    logger.info(f"Fetching comments from PR #{pr_number}...")
    raw_comments = get_pr_comments(pr_number)

    if not raw_comments:
        logger.warning(f"No comments found for PR #{pr_number}")
        return stats

    comments = parse_comments(raw_comments, pr_number)
    logger.info(f"Found {len(comments)} CodeRabbit comments")

    for comment in comments:
        error_id = await store_comment(comment, dry_run)
        stats[comment.severity] += 1
        stats["total"] += 1

        if error_id:
            logger.debug(f"Stored error {error_id}: {comment.title[:50]}...")

    return stats


async def main_async(args):
    """Async main function."""
    if args.clear_existing:
        count = await clear_coderabbit_errors()
        logger.info(f"Cleared {count} existing CodeRabbit errors")

    total_stats = {"critical": 0, "error": 0, "warning": 0, "info": 0, "total": 0}

    if args.all_open:
        pr_numbers = get_open_prs()
        logger.info(f"Found {len(pr_numbers)} open PRs")
    else:
        pr_numbers = [args.pr]

    for pr_num in pr_numbers:
        stats = await sync_pr(pr_num, args.dry_run)
        for key in total_stats:
            total_stats[key] += stats[key]

    # Print summary
    print("\n" + "=" * 50)
    print("CODERABBIT SYNC SUMMARY")
    print("=" * 50)
    print(f"Total comments synced: {total_stats['total']}")
    print(f"  Critical: {total_stats['critical']}")
    print(f"  Error:    {total_stats['error']}")
    print(f"  Warning:  {total_stats['warning']}")
    print(f"  Info:     {total_stats['info']}")
    print("=" * 50)

    if args.dry_run:
        print("\n[DRY RUN] No changes were made to the database")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Sync CodeRabbit PR comments to error database")
    parser.add_argument(
        "--pr",
        type=int,
        help="PR number to sync",
    )
    parser.add_argument(
        "--all-open",
        action="store_true",
        help="Sync all open PRs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be stored without making changes",
    )
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear existing CodeRabbit errors before sync",
    )

    args = parser.parse_args()

    if not args.pr and not args.all_open:
        parser.error("Must specify --pr NUMBER or --all-open")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
