#!/usr/bin/env python3
"""
CodeRabbit Auto-Fix Script

Parses CodeRabbit review comments from a PR, extracts suggested fixes,
and applies them automatically. Runs in a loop until no more fixable
issues are found or max iterations reached.
"""

import argparse
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class CodeFix:
    """Represents a code fix suggestion from CodeRabbit."""

    file_path: str
    start_line: int
    end_line: int
    old_code: str
    new_code: str
    description: str
    category: str  # e.g., 'security', 'performance', 'style'


@dataclass
class FixResult:
    """Result of applying a fix."""

    fix: CodeFix
    success: bool
    message: str


class GitHubAPI:
    """GitHub API client for fetching PR review comments."""

    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.base_url = "https://api.github.com"
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get_with_retry(self, url: str, params: dict = None, retries: int = 3) -> requests.Response:
        """Make a GET request with retry logic."""
        for attempt in range(retries):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=30,
                )
                if response.status_code in (500, 502, 503, 504):
                    response.raise_for_status() # Raise to trigger retry
                return response
            except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt) # Exponential backoff
        return None # Should not be reached

    def get_pr_reviews(self, pr_number: int) -> list[dict]:
        """Fetch all reviews for a PR."""
        url = f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}/reviews"
        all_reviews = []
        page = 1

        while True:
            response = requests.get(
                url,
                headers=self.headers,
                params={"per_page": 100, "page": page},
                timeout=30,
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
        url = f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}/comments"
        all_comments = []
        page = 1

        while True:
            response = self._get_with_retry(
                url,
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
        """Fetch issue-level comments (including CodeRabbit summary)."""
        url = f"{self.base_url}/repos/{self.repo}/issues/{pr_number}/comments"
        all_comments = []
        page = 1

        while True:
            response = self._get_with_retry(
                url,
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            comments = response.json()
            if not comments:
                break
            all_comments.extend(comments)
            page += 1

        return all_comments


class CodeRabbitParser:
    """Parses CodeRabbit review comments to extract fix suggestions.

    This parser handles multiple comment formats from CodeRabbit:
    1. Diff-style blocks with +/- markers
    2. Before/After code block comparisons
    3. Inline diff suggestions
    """

    # Pattern to match diff-style code blocks
    # Matches: ```diff or ```suggestion followed by content with +/- markers
    # Example:
    #   ```diff
    #   -old_line
    #   +new_line
    #   ```
    DIFF_PATTERN = re.compile(
        r"```(?:diff|suggestion)?\s*\n"  # Opening fence with optional language
        r"([\s\S]*?)"                     # Capture all content (including newlines)
        r"\n```",                          # Closing fence
        re.MULTILINE,
    )

    # Pattern to match before/after code blocks
    # Matches CodeRabbit comments with "Before/Current/Old" and "After/Suggested/New" sections
    # Example:
    #   Before:
    #   ```python
    #   old_code()
    #   ```
    #   After:
    #   ```python
    #   new_code()
    #   ```
    BEFORE_AFTER_PATTERN = re.compile(
        r"(?:Before|Current|Old).*?"      # "Before" label (case-insensitive)
        r"```[\w]*\s*\n"                  # Opening fence with optional language
        r"([\s\S]*?)"                     # Capture old code
        r"\n```"                          # Closing fence
        r"[\s\S]*?"                       # Any text between blocks
        r"(?:After|Suggested|New|Fixed).*?"  # "After" label (case-insensitive)
        r"```[\w]*\s*\n"                  # Opening fence with optional language
        r"([\s\S]*?)"                     # Capture new code
        r"\n```",                          # Closing fence
        re.IGNORECASE | re.MULTILINE,
    )

    # Pattern to match inline suggestions with - and + markers
    # Matches consecutive lines starting with - (removal) and + (addition)
    # Example:
    #   -old_line
    #   +new_line
    INLINE_DIFF_PATTERN = re.compile(
        r"^-\s*(.+)$\n"                   # Line starting with - (removal)
        r"^\+\s*(.+)$",                   # Line starting with + (addition)
        re.MULTILINE,
    )




    def __init__(self):
        self.fixes: list[CodeFix] = []

    def is_coderabbit_comment(self, comment: dict) -> bool:
        """Check if a comment is from CodeRabbit."""
        user = comment.get("user", {})
        login = user.get("login", "")
        return "coderabbit" in login.lower() or "coderabbitai" in login.lower()

    def parse_review_comment(self, comment: dict) -> Optional[CodeFix]:
        """Parse a single review comment for fix suggestions."""
        if not self.is_coderabbit_comment(comment):
            return None

        body = comment.get("body", "")
        path = comment.get("path", "")
        line = comment.get("line") or comment.get("original_line", 0)
        start_line = comment.get("start_line") or line

        # Skip if no file path
        if not path:
            return None

        # Try to extract code suggestion
        fix = self._extract_fix_from_body(body, path, start_line, line)
        return fix

    def _extract_fix_from_body(
        self, body: str, file_path: str, start_line: int, end_line: int
    ) -> Optional[CodeFix]:
        """Extract fix suggestion from comment body."""
        # Try before/after pattern first
        match = self.BEFORE_AFTER_PATTERN.search(body)
        if match:
            old_code = match.group(1).strip()
            new_code = match.group(2).strip()
            if old_code != new_code:
                return CodeFix(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    old_code=old_code,
                    new_code=new_code,
                    description=self._extract_description(body),
                    category=self._categorize_fix(body),
                )

        # Try diff pattern
        for match in self.DIFF_PATTERN.finditer(body):
            diff_content = match.group(1)
            old_lines, new_lines = self._parse_diff_content(diff_content)
            if old_lines and new_lines and old_lines != new_lines:
                return CodeFix(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    old_code="\n".join(old_lines),
                    new_code="\n".join(new_lines),
                    description=self._extract_description(body),
                    category=self._categorize_fix(body),
                )

        return None

    def _parse_diff_content(self, content: str) -> tuple[list[str], list[str]]:
        """Parse diff-style content into old and new lines."""
        old_lines = []
        new_lines = []

        for line in content.split("\n"):
            if line.startswith("-") and not line.startswith("---"):
                old_lines.append(line[1:].strip())
            elif line.startswith("+") and not line.startswith("+++"):
                new_lines.append(line[1:].strip())
            elif not line.startswith("@@"):
                # Context line - add to both
                stripped = line.lstrip(" ")
                if stripped:
                    old_lines.append(stripped)
                    new_lines.append(stripped)

        return old_lines, new_lines

    def _extract_description(self, body: str) -> str:
        """Extract a brief description from the comment."""
        # Take first non-empty line that isn't code
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith("```") and not line.startswith("-"):
                # Truncate if too long
                return line[:200] if len(line) > 200 else line
        return "CodeRabbit suggestion"

    def _categorize_fix(self, body: str) -> str:
        """Categorize the fix based on keywords in the comment."""
        body_lower = body.lower()
        if any(kw in body_lower for kw in ["security", "vulnerability", "injection"]):
            return "security"
        if any(kw in body_lower for kw in ["performance", "optimize", "efficient"]):
            return "performance"
        if any(kw in body_lower for kw in ["deadlock", "buffer", "memory", "leak"]):
            return "bug"
        if any(kw in body_lower for kw in ["type", "typing", "annotation"]):
            return "typing"
        if any(kw in body_lower for kw in ["style", "format", "indent"]):
            return "style"
        return "improvement"

    def parse_all_comments(self, comments: list[dict]) -> list[CodeFix]:
        """Parse all comments and extract fixes."""
        fixes = []
        for comment in comments:
            fix = self.parse_review_comment(comment)
            if fix:
                fixes.append(fix)
        return fixes


class AutoFixer:
    """Applies code fixes to files."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.applied_fixes: list[FixResult] = []

    def apply_fix(self, fix: CodeFix) -> FixResult:
        """Apply a single fix to a file.

        Args:
            fix: The CodeFix to apply

        Returns:
            FixResult indicating success or failure
        """
        file_path = self.repo_root / fix.file_path

        # Validate file exists
        if not file_path.exists():
            return FixResult(fix, False, f"File not found: {fix.file_path}")

        # Validate file is within repo root (security check)
        try:
            file_path.resolve().relative_to(self.repo_root.resolve())
        except ValueError:
            return FixResult(fix, False, f"File path outside repository: {fix.file_path}")

        try:
            # Read file with proper encoding handling
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                # Fallback to latin-1 for files with mixed encoding
                content = file_path.read_text(encoding="latin-1")
            except Exception as e:
                return FixResult(fix, False, f"Failed to read file: {e}")
        except OSError as e:
            return FixResult(fix, False, f"OS error reading file: {e}")

        try:
            # Try exact match replacement
            if fix.old_code in content:
                new_content = content.replace(fix.old_code, fix.new_code, 1)
                try:
                    file_path.write_text(new_content, encoding="utf-8")
                    result = FixResult(fix, True, "Applied exact match")
                    self.applied_fixes.append(result)
                    return result
                except OSError as e:
                    return FixResult(fix, False, f"Failed to write file: {e}")

            # Try line-based replacement
            lines = content.split("\n")
            if fix.start_line > 0 and fix.end_line <= len(lines):
                # Get the relevant lines
                start_idx = fix.start_line - 1
                end_idx = fix.end_line
                old_section = "\n".join(lines[start_idx:end_idx])

                # Check if old code matches approximately
                if self._fuzzy_match(old_section, fix.old_code):
                    try:
                        lines[start_idx:end_idx] = fix.new_code.split("\n")
                        new_content = "\n".join(lines)
                        file_path.write_text(new_content, encoding="utf-8")
                        result = FixResult(fix, True, "Applied line-based match")
                        self.applied_fixes.append(result)
                        return result
                    except OSError as e:
                        return FixResult(fix, False, f"Failed to write file: {e}")

            return FixResult(fix, False, "Could not locate code to replace")

        except Exception as e:
            # Catch any unexpected errors
            return FixResult(fix, False, f"Unexpected error: {type(e).__name__}: {e}")

    def _fuzzy_match(self, text1: str, text2: str) -> bool:
        """Check if two strings match approximately (ignoring whitespace differences)."""
        # Normalize whitespace
        norm1 = " ".join(text1.split())
        norm2 = " ".join(text2.split())

        # Simple similarity check
        if norm1 == norm2:
            return True

        # Check if one contains the other
        if norm2 in norm1 or norm1 in norm2:
            return True

        return False

    def run_linters(self) -> dict[str, bool]:
        """Run linters to auto-fix common issues."""
        results = {}

        # Run ruff fix for Python
        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
                check=False,
            )
            results["ruff"] = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            logger.exception("ruff linter failed")
            results["ruff"] = False

        # Run black for Python formatting
        try:
            result = subprocess.run(
                ["black", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
                check=False,
            )
            results["black"] = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            logger.exception("black formatter failed")
            results["black"] = False

        # Run isort for Python imports
        try:
            result = subprocess.run(
                ["isort", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
                check=False,
            )
            results["isort"] = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            logger.exception("isort failed")
            results["isort"] = False

        # Run prettier for JS/TS
        try:
            result = subprocess.run(
                ["npx", "prettier", "--write", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
                check=False,
            )
            results["prettier"] = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            logger.exception("prettier failed")
            results["prettier"] = False

        # Run ESLint fix for JS/TS
        try:
            result = subprocess.run(
                ["npx", "eslint", "--fix", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
                check=False,
            )
            results["eslint"] = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            logger.exception("eslint failed")
            results["eslint"] = False

        return results


def run_autofix_loop(
    github_api: GitHubAPI,
    pr_number: int,
    max_iterations: int,
    repo_root: Path,
) -> tuple[int, list[FixResult]]:
    """
    Run the auto-fix loop.

    Returns:
        Tuple of (iterations_run, all_fix_results)
    """
    parser = CodeRabbitParser()
    fixer = AutoFixer(repo_root)
    all_results: list[FixResult] = []
    iteration = 0  # Initialize to handle edge case where max_iterations <= 0

    for iteration in range(1, max_iterations + 1):
        logger.info("=" * 60)
        logger.info("Iteration %d/%d", iteration, max_iterations)
        logger.info("=" * 60)

        # Fetch latest comments
        logger.info("Fetching CodeRabbit comments...")
        review_comments = github_api.get_pr_review_comments(pr_number)
        issue_comments = github_api.get_pr_issue_comments(pr_number)

        # Parse fixes
        fixes = parser.parse_all_comments(review_comments + issue_comments)
        logger.info("Found %d potential fixes", len(fixes))

        if not fixes:
            logger.info("No more fixes to apply")
            break

        # Apply fixes
        applied_count = 0
        for fix in fixes:
            logger.info("Applying fix to %s:%d", fix.file_path, fix.start_line)
            logger.info("  Category: %s", fix.category)
            logger.info("  Description: %s...", fix.description[:80])

            result = fixer.apply_fix(fix)
            all_results.append(result)

            if result.success:
                applied_count += 1
                logger.info("  Result: SUCCESS - %s", result.message)
            else:
                logger.info("  Result: SKIPPED - %s", result.message)

        logger.info("Applied %d/%d fixes", applied_count, len(fixes))

        # Run linters to fix additional issues
        logger.info("Running linters...")
        linter_results = fixer.run_linters()
        for linter, success in linter_results.items():
            status = "OK" if success else "SKIPPED"
            logger.info("  %s: %s", linter, status)

        if applied_count == 0:
            logger.info("No fixes applied in this iteration, stopping loop")
            break

        # Small delay before next iteration
        if iteration < max_iterations:
            logger.info("Waiting before next iteration...")
            time.sleep(5)

    return iteration, all_results


def generate_summary(
    iterations: int, results: list[FixResult], output_path: Optional[Path]
) -> str:
    """Generate a markdown summary of the auto-fix run."""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    lines = [
        f"### Iterations: {iterations}",
        f"### Fixes Applied: {len(successful)}",
        f"### Fixes Skipped: {len(failed)}",
        "",
    ]

    if successful:
        lines.append("#### Successfully Applied:")
        for r in successful:
            lines.append(f"- `{r.fix.file_path}:{r.fix.start_line}` - {r.fix.category}")

    if failed:
        lines.append("")
        lines.append("#### Skipped (manual review needed):")
        for r in failed[:10]:  # Limit to first 10
            lines.append(f"- `{r.fix.file_path}:{r.fix.start_line}` - {r.message}")
        if len(failed) > 10:
            lines.append(f"- ... and {len(failed) - 10} more")

    summary = "\n".join(lines)

    if output_path:
        output_path.write_text(summary, encoding="utf-8")

    return summary


def main() -> None:
    """Main entry point for the CodeRabbit auto-fix script."""
    parser = argparse.ArgumentParser(
        description="CodeRabbit Auto-Fix Script - Automatically apply CodeRabbit suggestions to PRs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --repo owner/repo --pr 123
  %(prog)s --repo owner/repo --pr 123 --max-iterations 5
  %(prog)s --repo owner/repo --pr 123 --output-summary summary.md

Environment Variables:
  GITHUB_TOKEN: GitHub personal access token (required)
        """
    )
    parser.add_argument("--repo", required=True, help="Repository in format owner/repo")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum number of fix iterations (default: 3)"
    )
    parser.add_argument(
        "--output-summary",
        help="Path to write summary markdown file"
    )
    args = parser.parse_args()

    # Validate arguments
    if args.max_iterations < 1:
        print("Error: --max-iterations must be at least 1", file=sys.stderr)
        sys.exit(1)

    if "/" not in args.repo:
        print("Error: --repo must be in format owner/repo", file=sys.stderr)
        sys.exit(1)

    # Get GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        print("Please set GITHUB_TOKEN to your GitHub personal access token", file=sys.stderr)
        sys.exit(1)

    # Initialize
    try:
        github_api = GitHubAPI(token, args.repo)
        repo_root = Path.cwd()

        print(f"Repository: {args.repo}")
        print(f"PR Number: {args.pr}")
        print(f"Max Iterations: {args.max_iterations}")
        print(f"Repo Root: {repo_root}")
        print("")

        # Run the auto-fix loop
        iterations, results = run_autofix_loop(
            github_api, args.pr, args.max_iterations, repo_root
        )

        # Generate summary
        output_path = Path(args.output_summary) if args.output_summary else None
        summary = generate_summary(iterations, results, output_path)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(summary)

        # Set output for GitHub Actions
        successful = [r for r in results if r.success]
        if successful:
            # Set output variable for GitHub Actions
            github_output = os.environ.get("GITHUB_OUTPUT")
            if github_output:
                try:
                    with open(github_output, "a", encoding="utf-8") as f:
                        f.write("fixes_applied=true\n")
                except OSError as e:
                    print(f"Warning: Failed to write GitHub output: {e}", file=sys.stderr)

        sys.exit(0)

    except requests.exceptions.RequestException as e:
        print(f"Error: GitHub API request failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
