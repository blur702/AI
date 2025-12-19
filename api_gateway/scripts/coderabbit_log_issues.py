"""
Utility script to sync CodeRabbit review comments into the errors table.

This lets you persist CodeRabbit issues (file, severity, message, links)
into PostgreSQL via the existing Error model, using service="coderabbit".

Usage (from project root):

    python -m api_gateway.scripts.coderabbit_log_issues import \
        --file coderabbit_comments.json

    python -m api_gateway.scripts.coderabbit_log_issues list

    python -m api_gateway.scripts.coderabbit_log_issues resolve \
        --id <error_id> --resolution "Fixed per PR #6 commit <sha>"
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..models.database import AsyncSessionLocal, Error, ErrorSeverity, init_db
from ..utils.error_logger import log_error, mark_error_resolved
from ..utils.logger import logger


def _detect_severity(body: str) -> ErrorSeverity:
    """
    Best-effort severity mapping based on CodeRabbit comment text.
    """
    text = body.lower()
    if "critical" in text:
        return ErrorSeverity.critical
    if "major" in text:
        return ErrorSeverity.error
    if "minor" in text:
        return ErrorSeverity.warning
    if "nitpick" in text:
        return ErrorSeverity.info
    return ErrorSeverity.info


def _extract_summary(body: str) -> str:
    """
    Extract the first bolded markdown line as the issue summary.
    Falls back to the first non-empty line if no bold section is found.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            # Strip surrounding ** markers
            return stripped.strip("* ").strip()

    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped

    return "CodeRabbit issue"


def _iter_coderabbit_comments(data: Any) -> Iterable[dict[str, Any]]:
    """
    Yield GitHub review comment objects authored by CodeRabbit from JSON.

    The JSON exported by CodeRabbit scripts is expected to be either:
        - a list of comment objects, or
        - an object with a top-level 'comments' key containing that list.
    """
    if isinstance(data, dict) and "comments" in data:
        items = data["comments"]
    else:
        items = data

    if not isinstance(items, list):
        return []

    for comment in items:
        try:
            user = comment.get("user") or {}
            login = user.get("login") or ""
            if "coderabbitai" not in login:
                continue
            yield comment
        except Exception:  # noqa: BLE001
            continue


async def _import_file(path: Path) -> int:
    """
    Import CodeRabbit issues from a JSON file into the errors table.

    Returns the number of Error rows created.
    """
    logger.info("Importing CodeRabbit issues from %s", path)
    # Handle optional UTF-8 BOM in exported JSON
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    data = json.loads(text)

    count = 0
    for comment in _iter_coderabbit_comments(data):
        body = comment.get("body") or ""
        if not body.strip():
            continue

        severity = _detect_severity(body)
        summary = _extract_summary(body)

        context: dict[str, Any] = {
            "path": comment.get("path"),
            "commit_id": comment.get("commit_id"),
            "github_url": comment.get("html_url"),
            "pull_request_url": comment.get("pull_request_url"),
            "raw_body": body,
        }

        await log_error(
            service="coderabbit",
            message=summary,
            severity=severity,
            stack_trace=None,
            context=context,
            job_id=None,
        )
        count += 1

    logger.info("Imported %s CodeRabbit issues from %s", count, path)
    return count


async def _cmd_import(args: argparse.Namespace) -> None:
    total = 0
    for file_arg in args.file:
        path = Path(file_arg)
        if not path.exists():
            logger.warning("File not found: %s", path)
            continue
        total += await _import_file(path)
    print(f"Imported {total} CodeRabbit issue(s) into errors table.")


async def _cmd_list(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as session:
        stmt = select(Error).where(Error.service == "coderabbit").order_by(Error.created_at.desc())
        result = await session.execute(stmt)
        errors: list[Error] = list(result.scalars())

    if not errors:
        print("No CodeRabbit errors found in database.")
        return

    for err in errors:
        status = "resolved" if err.resolved else "open"
        print(
            f"{err.id} [{status}] {err.severity.value} - {err.message} "
            f"(created_at={err.created_at.isoformat()})"
        )


async def _cmd_resolve(args: argparse.Namespace) -> None:
    error_id: str = args.id
    resolution: str | None = args.resolution

    updated = await mark_error_resolved(error_id, resolution=resolution)
    if updated is None:
        print(f"Error not found: {error_id}")
        return

    print(f"Marked CodeRabbit error {error_id} as resolved.")
    if resolution:
        print(f"Resolution: {resolution}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync CodeRabbit review comments into the errors table."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import", help="Import CodeRabbit issues from JSON file(s)."
    )
    import_parser.add_argument(
        "--file",
        "-f",
        nargs="+",
        required=True,
        help="Path(s) to coderabbit_comments.json / fresh_comments.json, etc.",
    )

    subparsers.add_parser("list", help="List CodeRabbit errors stored in the database.")

    resolve_parser = subparsers.add_parser(
        "resolve", help="Mark a CodeRabbit error as resolved with an optional note."
    )
    resolve_parser.add_argument("--id", required=True, help="Error ID to resolve.")
    resolve_parser.add_argument(
        "--resolution",
        "-r",
        required=False,
        help="Resolution description to store with the error.",
    )

    return parser


async def _run_async(argv: list[str] | None = None) -> None:
    """
    Entry point for async commands.

    Ensures database schema (including errors.resolution) is up to date
    before performing any operations.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Ensure schema is initialized/migrated
    try:
        await init_db()
    except Exception as exc:  # noqa: BLE001
        logger.error("Database initialization failed: %s", exc, exc_info=True)
        raise SystemExit(1) from exc

    if args.command == "import":
        await _cmd_import(args)
    elif args.command == "list":
        await _cmd_list(args)
    elif args.command == "resolve":
        await _cmd_resolve(args)
    else:  # pragma: no cover
        parser.print_help()


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_run_async(argv))


if __name__ == "__main__":  # pragma: no cover
    main()
