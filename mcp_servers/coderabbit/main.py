"""
MCP CodeRabbit Server.

Provides tools for interacting with CodeRabbit reviews on GitHub PRs.
Enables Claude Code to fetch, analyze, and apply CodeRabbit suggestions.

Tools:
    - list_open_prs: List open pull requests
    - get_coderabbit_reviews: Get CodeRabbit reviews for a PR
    - get_pending_fixes: Extract actionable fix suggestions
    - apply_fix: Apply a specific code fix
    - run_linters: Run code linters
    - dismiss_review: Dismiss a CodeRabbit review

Usage:
    python -m mcp_servers.coderabbit.main
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mcp_servers.coderabbit import settings  # noqa: E402

# Configure logging to stderr (required for STDIO transport)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
    force=True,
)
logger = logging.getLogger("mcp.coderabbit")

# Create FastMCP server
mcp = FastMCP("CodeRabbit")


@dataclass
class CodeFix:
    """Represents a code fix suggestion from CodeRabbit."""

    fix_id: str
    file_path: str
    start_line: int
    end_line: int
    old_code: str
    new_code: str
    description: str
    category: str
    review_id: int
    comment_id: int


class GitHubAPI:
    """GitHub API client for CodeRabbit interactions."""

    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
        retries: int = 3,
    ) -> requests.Response:
        """Make an HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"
        for attempt in range(retries):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    params=params,
                    json=json_data,
                    timeout=30,
                )
                if response.status_code in (500, 502, 503, 504):
                    response.raise_for_status()
                return response
            except requests.exceptions.RequestException:
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("Request failed after retries")

    def list_open_prs(self) -> list[dict]:
        """List open pull requests."""
        response = self._request("GET", f"/repos/{self.repo}/pulls", params={"state": "open"})
        response.raise_for_status()
        return response.json()

    def get_pr(self, pr_number: int) -> dict:
        """Get a specific PR."""
        response = self._request("GET", f"/repos/{self.repo}/pulls/{pr_number}")
        response.raise_for_status()
        return response.json()

    def get_pr_reviews(self, pr_number: int) -> list[dict]:
        """Fetch all reviews for a PR."""
        all_reviews = []
        page = 1
        while True:
            response = self._request(
                "GET",
                f"/repos/{self.repo}/pulls/{pr_number}/reviews",
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            reviews = response.json()
            if not reviews:
                break
            all_reviews.extend(reviews)
            page += 1
        return all_reviews

    def get_pr_review_comments(self, pr_number: int) -> list[dict]:
        """Fetch all review comments for a PR."""
        all_comments = []
        page = 1
        while True:
            response = self._request(
                "GET",
                f"/repos/{self.repo}/pulls/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            comments = response.json()
            if not comments:
                break
            all_comments.extend(comments)
            page += 1
        return all_comments

    def get_pr_issue_comments(self, pr_number: int) -> list[dict]:
        """Fetch issue-level comments."""
        all_comments = []
        page = 1
        while True:
            response = self._request(
                "GET",
                f"/repos/{self.repo}/issues/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            comments = response.json()
            if not comments:
                break
            all_comments.extend(comments)
            page += 1
        return all_comments

    def dismiss_review(self, pr_number: int, review_id: int, message: str) -> dict:
        """Dismiss a review."""
        response = self._request(
            "PUT",
            f"/repos/{self.repo}/pulls/{pr_number}/reviews/{review_id}/dismissals",
            json_data={"message": message},
        )
        response.raise_for_status()
        return response.json()


class CodeRabbitParser:
    """Parses CodeRabbit comments to extract fix suggestions."""

    DIFF_PATTERN = re.compile(
        r"```(?:diff|suggestion)?\s*\n([\s\S]*?)\n```",
        re.MULTILINE,
    )

    BEFORE_AFTER_PATTERN = re.compile(
        r"(?:Before|Current|Old).*?```[\w]*\s*\n([\s\S]*?)\n```"
        r"[\s\S]*?"
        r"(?:After|Suggested|New|Fixed).*?```[\w]*\s*\n([\s\S]*?)\n```",
        re.IGNORECASE | re.MULTILINE,
    )

    @staticmethod
    def is_coderabbit_comment(comment: dict) -> bool:
        """Check if a comment is from CodeRabbit."""
        user = comment.get("user", {})
        login = user.get("login", "").lower()
        return "coderabbit" in login

    def parse_comment(self, comment: dict, review_id: int = 0) -> CodeFix | None:
        """Parse a single comment for fix suggestions."""
        if not self.is_coderabbit_comment(comment):
            return None

        body = comment.get("body", "")
        path = comment.get("path", "")
        line = comment.get("line") or comment.get("original_line", 0)
        start_line = comment.get("start_line") or line
        comment_id = comment.get("id", 0)

        if not path:
            return None

        # Try before/after pattern
        match = self.BEFORE_AFTER_PATTERN.search(body)
        if match:
            old_code = match.group(1).strip()
            new_code = match.group(2).strip()
            if old_code != new_code:
                return CodeFix(
                    fix_id=f"fix_{comment_id}",
                    file_path=path,
                    start_line=start_line,
                    end_line=line,
                    old_code=old_code,
                    new_code=new_code,
                    description=self._extract_description(body),
                    category=self._categorize(body),
                    review_id=review_id,
                    comment_id=comment_id,
                )

        # Try diff pattern
        for match in self.DIFF_PATTERN.finditer(body):
            diff_content = match.group(1)
            old_lines, new_lines = self._parse_diff(diff_content)
            if old_lines and new_lines and old_lines != new_lines:
                return CodeFix(
                    fix_id=f"fix_{comment_id}",
                    file_path=path,
                    start_line=start_line,
                    end_line=line,
                    old_code="\n".join(old_lines),
                    new_code="\n".join(new_lines),
                    description=self._extract_description(body),
                    category=self._categorize(body),
                    review_id=review_id,
                    comment_id=comment_id,
                )

        return None

    def _parse_diff(self, content: str) -> tuple[list[str], list[str]]:
        """Parse diff content into old and new lines."""
        old_lines = []
        new_lines = []
        for line in content.split("\n"):
            if line.startswith("-") and not line.startswith("---"):
                old_lines.append(line[1:].strip())
            elif line.startswith("+") and not line.startswith("+++"):
                new_lines.append(line[1:].strip())
            elif not line.startswith("@@"):
                stripped = line.lstrip(" ")
                if stripped:
                    old_lines.append(stripped)
                    new_lines.append(stripped)
        return old_lines, new_lines

    def _extract_description(self, body: str) -> str:
        """Extract description from comment body."""
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith("```") and not line.startswith("-"):
                return line[:200] if len(line) > 200 else line
        return "CodeRabbit suggestion"

    def _categorize(self, body: str) -> str:
        """Categorize the fix based on keywords."""
        body_lower = body.lower()
        if any(kw in body_lower for kw in ["security", "vulnerability", "injection"]):
            return "security"
        if any(kw in body_lower for kw in ["performance", "optimize", "efficient"]):
            return "performance"
        if any(kw in body_lower for kw in ["bug", "error", "fix"]):
            return "bug"
        if any(kw in body_lower for kw in ["type", "typing", "annotation"]):
            return "typing"
        if any(kw in body_lower for kw in ["style", "format", "indent"]):
            return "style"
        return "improvement"


# Global instances
_github_api: GitHubAPI | None = None
_parser = CodeRabbitParser()


def _get_github_api() -> GitHubAPI:
    """Get or create GitHub API instance."""
    global _github_api
    if _github_api is None:
        token = settings.GITHUB_TOKEN or os.getenv("GITHUB_TOKEN", "")
        if not token:
            raise ValueError("GITHUB_TOKEN not set")
        _github_api = GitHubAPI(token, settings.GITHUB_REPO)
    return _github_api


@mcp.tool()
def list_open_prs() -> list[dict[str, Any]]:
    """
    List open pull requests in the repository.

    Returns:
        List of PRs with number, title, state, author, and created_at
    """
    logger.info("Listing open PRs")
    try:
        api = _get_github_api()
        prs = api.list_open_prs()
        return [
            {
                "number": pr["number"],
                "title": pr["title"],
                "state": pr["state"],
                "draft": pr.get("draft", False),
                "author": pr["user"]["login"],
                "created_at": pr["created_at"],
                "url": pr["html_url"],
            }
            for pr in prs
        ]
    except Exception as e:
        logger.exception("Failed to list PRs")
        return [{"error": str(e)}]


@mcp.tool()
def get_coderabbit_reviews(pr_number: int) -> list[dict[str, Any]]:
    """
    Get CodeRabbit reviews for a specific PR.

    Args:
        pr_number: The pull request number

    Returns:
        List of CodeRabbit reviews with id, state, body preview, and submitted_at
    """
    logger.info("Getting CodeRabbit reviews for PR #%d", pr_number)
    try:
        api = _get_github_api()
        reviews = api.get_pr_reviews(pr_number)

        coderabbit_reviews = []
        for review in reviews:
            if _parser.is_coderabbit_comment(review):
                body = review.get("body", "")
                coderabbit_reviews.append({
                    "id": review["id"],
                    "state": review["state"],
                    "body_preview": body[:300] + "..." if len(body) > 300 else body,
                    "submitted_at": review.get("submitted_at"),
                    "commit_id": review.get("commit_id", "")[:7],
                })

        return coderabbit_reviews
    except Exception as e:
        logger.exception("Failed to get reviews")
        return [{"error": str(e)}]


@mcp.tool()
def get_pending_fixes(pr_number: int) -> list[dict[str, Any]]:
    """
    Extract pending fix suggestions from CodeRabbit comments.

    Args:
        pr_number: The pull request number

    Returns:
        List of actionable fixes with fix_id, file_path, description, category,
        old_code, and new_code
    """
    logger.info("Getting pending fixes for PR #%d", pr_number)
    try:
        api = _get_github_api()

        # Get review comments
        review_comments = api.get_pr_review_comments(pr_number)
        issue_comments = api.get_pr_issue_comments(pr_number)

        # Also get reviews to associate review_id
        reviews = api.get_pr_reviews(pr_number)
        coderabbit_review_ids = [
            r["id"] for r in reviews if _parser.is_coderabbit_comment(r)
        ]
        default_review_id = coderabbit_review_ids[0] if coderabbit_review_ids else 0

        fixes = []
        for comment in review_comments + issue_comments:
            fix = _parser.parse_comment(comment, default_review_id)
            if fix:
                fixes.append(asdict(fix))

        logger.info("Found %d pending fixes", len(fixes))
        return fixes
    except Exception as e:
        logger.exception("Failed to get pending fixes")
        return [{"error": str(e)}]


@mcp.tool()
def apply_fix(
    file_path: str,
    old_code: str,
    new_code: str,
    start_line: int = 0,
) -> dict[str, Any]:
    """
    Apply a code fix to a file.

    Args:
        file_path: Path to the file (relative to project root)
        old_code: The code to replace
        new_code: The replacement code
        start_line: Optional line number hint for locating the code

    Returns:
        Result with success status and message
    """
    logger.info("Applying fix to %s", file_path)
    try:
        full_path = Path(settings.PROJECT_ROOT) / file_path

        if not full_path.exists():
            return {"success": False, "message": f"File not found: {file_path}"}

        # Security check - ensure path is within project
        try:
            full_path.resolve().relative_to(Path(settings.PROJECT_ROOT).resolve())
        except ValueError:
            return {"success": False, "message": "Path outside project root"}

        # Read file
        try:
            content = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = full_path.read_text(encoding="latin-1")

        # Try exact match replacement
        if old_code in content:
            new_content = content.replace(old_code, new_code, 1)
            full_path.write_text(new_content, encoding="utf-8")
            return {"success": True, "message": "Applied exact match replacement"}

        # Try line-based replacement
        lines = content.split("\n")
        if start_line > 0 and start_line <= len(lines):
            # Check if old code matches around the line
            old_lines = old_code.split("\n")
            end_line = start_line + len(old_lines)
            if end_line <= len(lines):
                section = "\n".join(lines[start_line - 1 : end_line])
                if _fuzzy_match(section, old_code):
                    lines[start_line - 1 : end_line] = new_code.split("\n")
                    full_path.write_text("\n".join(lines), encoding="utf-8")
                    return {"success": True, "message": "Applied line-based replacement"}

        return {"success": False, "message": "Could not locate code to replace"}

    except Exception as e:
        logger.exception("Failed to apply fix")
        return {"success": False, "message": str(e)}


def _fuzzy_match(text1: str, text2: str) -> bool:
    """Check if two strings match approximately."""
    norm1 = " ".join(text1.split())
    norm2 = " ".join(text2.split())
    return norm1 == norm2 or norm2 in norm1 or norm1 in norm2


@mcp.tool()
def run_linters(fix: bool = True) -> dict[str, Any]:
    """
    Run code linters on the project.

    Args:
        fix: Whether to auto-fix issues (default: True)

    Returns:
        Results for each linter (ruff, black, prettier, eslint)
    """
    logger.info("Running linters (fix=%s)", fix)
    results = {}
    cwd = Path(settings.PROJECT_ROOT)

    # Ruff
    try:
        cmd = ["ruff", "check", "."] + (["--fix"] if fix else [])
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=120)
        results["ruff"] = {
            "success": result.returncode == 0,
            "output": result.stdout.decode()[:500],
        }
    except Exception as e:
        results["ruff"] = {"success": False, "error": str(e)}

    # Black
    try:
        cmd = ["black", "."] if fix else ["black", "--check", "."]
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=120)
        results["black"] = {
            "success": result.returncode == 0,
            "output": result.stdout.decode()[:500],
        }
    except Exception as e:
        results["black"] = {"success": False, "error": str(e)}

    # Prettier
    try:
        cmd = ["npx", "prettier"] + (["--write", "."] if fix else ["--check", "."])
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=120)
        results["prettier"] = {
            "success": result.returncode == 0,
            "output": result.stdout.decode()[:500],
        }
    except Exception as e:
        results["prettier"] = {"success": False, "error": str(e)}

    # ESLint
    try:
        cmd = ["npx", "eslint", "."] + (["--fix"] if fix else [])
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=120)
        results["eslint"] = {
            "success": result.returncode == 0,
            "output": result.stdout.decode()[:500],
        }
    except Exception as e:
        results["eslint"] = {"success": False, "error": str(e)}

    return results


@mcp.tool()
def dismiss_review(pr_number: int, review_id: int, message: str = "Fixes applied") -> dict[str, Any]:
    """
    Dismiss a CodeRabbit review.

    Args:
        pr_number: The pull request number
        review_id: The review ID to dismiss
        message: Dismissal message

    Returns:
        Result with success status
    """
    logger.info("Dismissing review %d on PR #%d", review_id, pr_number)
    try:
        api = _get_github_api()
        result = api.dismiss_review(pr_number, review_id, message)
        return {"success": True, "state": result.get("state")}
    except Exception as e:
        logger.exception("Failed to dismiss review")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_pr_status(pr_number: int) -> dict[str, Any]:
    """
    Get the current status of a PR including checks and review state.

    Args:
        pr_number: The pull request number

    Returns:
        PR details including mergeable status and review decision
    """
    logger.info("Getting status for PR #%d", pr_number)
    try:
        api = _get_github_api()
        pr = api.get_pr(pr_number)

        return {
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "mergeable": pr.get("mergeable"),
            "mergeable_state": pr.get("mergeable_state"),
            "draft": pr.get("draft", False),
            "head_sha": pr["head"]["sha"][:7],
            "base_branch": pr["base"]["ref"],
            "changed_files": pr.get("changed_files", 0),
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
        }
    except Exception as e:
        logger.exception("Failed to get PR status")
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
