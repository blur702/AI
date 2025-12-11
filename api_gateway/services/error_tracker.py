"""
Error Tracker for PostgreSQL Database.

Stores and manages lint/build errors found during development.
Used by Claude Code hooks to track errors and their resolutions.

Usage:
    # Store a new error
    python -m api_gateway.services.error_tracker store \
        --service "dashboard/frontend" \
        --file "src/App.tsx" \
        --line 42 \
        --message "Type 'string' is not assignable to type 'number'" \
        --severity error

    # Mark error as resolved
    python -m api_gateway.services.error_tracker resolve \
        --error-id "uuid-here" \
        --resolution "Changed parameter type from number to string"

    # Find unresolved errors for a file
    python -m api_gateway.services.error_tracker find \
        --file "src/App.tsx"

    # Store from stdin (JSON)
    echo '{"service":"core","file":"app.py","line":10,"message":"error"}' | \
        python -m api_gateway.services.error_tracker store-stdin

    # List recent errors
    python -m api_gateway.services.error_tracker list --limit 20
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_

from api_gateway.models.database import (
    AsyncSessionLocal,
    Error,
    ErrorSeverity,
)


async def store_error(
    service: str,
    message: str,
    file_path: Optional[str] = None,
    line_number: Optional[int] = None,
    severity: str = "error",
    stack_trace: Optional[str] = None,
) -> str:
    """
    Store a new error in the database.

    Returns:
        The UUID of the created error record.
    """
    # Build context with file info
    context = {}
    if file_path:
        context["file_path"] = file_path
    if line_number:
        context["line_number"] = line_number

    # Map severity string to enum
    severity_enum = ErrorSeverity(severity) if severity in [e.value for e in ErrorSeverity] else ErrorSeverity.error

    async with AsyncSessionLocal() as session:
        error = Error(
            service=service,
            severity=severity_enum,
            message=message,
            stack_trace=stack_trace,
            context=context if context else None,
            resolved=False,
        )
        session.add(error)
        await session.commit()
        await session.refresh(error)
        return error.id


async def resolve_error(
    error_id: str,
    resolution: str,
) -> bool:
    """
    Mark an error as resolved with a resolution description.

    Returns:
        True if error was found and updated, False otherwise.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Error).where(Error.id == error_id)
        )
        error = result.scalar_one_or_none()

        if not error:
            return False

        error.resolved = True
        error.resolved_at = datetime.now(timezone.utc)
        error.resolution = resolution
        await session.commit()
        return True


async def resolve_errors_by_file(
    file_path: str,
    resolution: str,
) -> int:
    """
    Mark all unresolved errors for a file as resolved.

    Returns:
        Number of errors resolved.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Error).where(
                and_(
                    Error.context["file_path"].astext == file_path,
                    Error.resolved.is_(False),
                )
            )
        )
        errors = result.scalars().all()

        count = 0
        for error in errors:
            error.resolved = True
            error.resolved_at = datetime.now(timezone.utc)
            error.resolution = resolution
            count += 1

        await session.commit()
        return count


async def find_errors(
    file_path: Optional[str] = None,
    service: Optional[str] = None,
    unresolved_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    """
    Find errors matching criteria.

    Returns:
        List of error dictionaries.
    """
    async with AsyncSessionLocal() as session:
        query = select(Error)

        conditions = []
        if file_path:
            conditions.append(Error.context["file_path"].astext == file_path)
        if service:
            conditions.append(Error.service == service)
        if unresolved_only:
            conditions.append(Error.resolved.is_(False))

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Error.created_at.desc()).limit(limit)

        result = await session.execute(query)
        errors = result.scalars().all()

        return [
            {
                "id": e.id,
                "service": e.service,
                "severity": e.severity.value,
                "message": e.message,
                "resolution": e.resolution,
                "file_path": e.context.get("file_path") if e.context else None,
                "line_number": e.context.get("line_number") if e.context else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "resolved": e.resolved,
                "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
            }
            for e in errors
        ]


async def list_errors(
    limit: int = 20,
    include_resolved: bool = False,
) -> list[dict]:
    """List recent errors."""
    return await find_errors(unresolved_only=not include_resolved, limit=limit)


async def get_error_stats() -> dict:
    """Get error statistics."""
    async with AsyncSessionLocal() as session:
        # Count unresolved
        result = await session.execute(
            select(Error).where(Error.resolved.is_(False))
        )
        unresolved = len(result.scalars().all())

        # Count total
        result = await session.execute(select(Error))
        total = len(result.scalars().all())

        # Count by service
        result = await session.execute(
            select(Error).where(Error.resolved.is_(False))
        )
        by_service = {}
        for error in result.scalars().all():
            by_service[error.service] = by_service.get(error.service, 0) + 1

        return {
            "total": total,
            "unresolved": unresolved,
            "resolved": total - unresolved,
            "by_service": by_service,
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Track errors in PostgreSQL database"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # store command
    store_parser = subparsers.add_parser("store", help="Store a new error")
    store_parser.add_argument("--service", required=True, help="Service/app name")
    store_parser.add_argument("--file", help="File path where error occurred")
    store_parser.add_argument("--line", type=int, help="Line number")
    store_parser.add_argument("--message", required=True, help="Error message")
    store_parser.add_argument(
        "--severity",
        choices=["info", "warning", "error", "critical"],
        default="error",
        help="Error severity",
    )
    store_parser.add_argument("--stack-trace", help="Stack trace if available")

    # store-stdin command
    subparsers.add_parser("store-stdin", help="Store error from JSON stdin")

    # resolve command
    resolve_parser = subparsers.add_parser("resolve", help="Mark error as resolved")
    resolve_parser.add_argument("--error-id", help="Error UUID to resolve")
    resolve_parser.add_argument("--file", help="Resolve all errors for this file")
    resolve_parser.add_argument("--resolution", required=True, help="Resolution description")

    # find command
    find_parser = subparsers.add_parser("find", help="Find errors")
    find_parser.add_argument("--file", help="Filter by file path")
    find_parser.add_argument("--service", help="Filter by service")
    find_parser.add_argument("--all", action="store_true", help="Include resolved errors")
    find_parser.add_argument("--limit", type=int, default=50, help="Max results")

    # list command
    list_parser = subparsers.add_parser("list", help="List recent errors")
    list_parser.add_argument("--limit", type=int, default=20, help="Max results")
    list_parser.add_argument("--all", action="store_true", help="Include resolved errors")

    # stats command
    subparsers.add_parser("stats", help="Show error statistics")

    args = parser.parse_args()

    if args.command == "store":
        error_id = asyncio.run(
            store_error(
                service=args.service,
                message=args.message,
                file_path=args.file,
                line_number=args.line,
                severity=args.severity,
                stack_trace=args.stack_trace,
            )
        )
        print(f"Error stored: {error_id}")

    elif args.command == "store-stdin":
        data = json.load(sys.stdin)
        error_id = asyncio.run(
            store_error(
                service=data.get("service", "unknown"),
                message=data.get("message", ""),
                file_path=data.get("file"),
                line_number=data.get("line"),
                severity=data.get("severity", "error"),
                stack_trace=data.get("stack_trace"),
            )
        )
        print(f"Error stored: {error_id}")

    elif args.command == "resolve":
        if args.error_id:
            success = asyncio.run(resolve_error(args.error_id, args.resolution))
            if success:
                print(f"Error {args.error_id} resolved")
            else:
                print(f"Error {args.error_id} not found")
                sys.exit(1)
        elif args.file:
            count = asyncio.run(resolve_errors_by_file(args.file, args.resolution))
            print(f"Resolved {count} errors for {args.file}")
        else:
            print("Error: must specify --error-id or --file")
            sys.exit(1)

    elif args.command == "find":
        errors = asyncio.run(
            find_errors(
                file_path=args.file,
                service=args.service,
                unresolved_only=not args.all,
                limit=args.limit,
            )
        )
        if errors:
            for e in errors:
                status = "RESOLVED" if e["resolved"] else "OPEN"
                loc = f"{e['file_path']}:{e['line_number']}" if e["file_path"] else "N/A"
                print(f"[{status}] {e['severity'].upper()} in {e['service']}")
                print(f"  Location: {loc}")
                print(f"  Message: {e['message']}")
                if e["resolution"]:
                    print(f"  Resolution: {e['resolution']}")
                print(f"  Created: {e['created_at']}")
                print()
        else:
            print("No errors found")

    elif args.command == "list":
        errors = asyncio.run(list_errors(limit=args.limit, include_resolved=args.all))
        if errors:
            for e in errors:
                status = "RESOLVED" if e["resolved"] else "OPEN"
                loc = f"{e['file_path']}:{e['line_number']}" if e["file_path"] else "N/A"
                print(f"[{status}] {e['severity'].upper()} in {e['service']} @ {loc}")
                print(f"  {e['message'][:100]}...")
                print()
        else:
            print("No errors found")

    elif args.command == "stats":
        stats = asyncio.run(get_error_stats())
        print("Error Statistics")
        print("=" * 40)
        print(f"Total errors:      {stats['total']}")
        print(f"Unresolved:        {stats['unresolved']}")
        print(f"Resolved:          {stats['resolved']}")
        print()
        if stats["by_service"]:
            print("Unresolved by service:")
            for service, count in sorted(stats["by_service"].items()):
                print(f"  {service}: {count}")


if __name__ == "__main__":
    main()
