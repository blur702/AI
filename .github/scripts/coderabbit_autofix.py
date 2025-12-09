#!/usr/bin/env python3
"""
CodeRabbit Auto-Fix Script

Parses CodeRabbit review comments from a PR, extracts suggested fixes,
and applies them automatically. Runs in a loop until no more fixable
issues are found or max iterations reached.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


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
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_pr_reviews(self, pr_number: int) -> list[dict]:
        """Fetch all reviews for a PR."""
        url = f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}/reviews"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_pr_review_comments(self, pr_number: int) -> list[dict]:
        """Fetch all review comments for a PR."""
        url = f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}/comments"
        all_comments = []
        page = 1

        while True:
            response = requests.get(
                url,
                headers=self.headers,
                params={"per_page": 100, "page": page},
                timeout=30,
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
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()


class CodeRabbitParser:
    """Parses CodeRabbit review comments to extract fix suggestions."""

    # Pattern to match diff-style code blocks
    DIFF_PATTERN = re.compile(
        r"```(?:diff|suggestion)?\s*\n"
        r"([\s\S]*?)"
        r"\n```",
        re.MULTILINE,
    )

    # Pattern to match before/after code blocks
    BEFORE_AFTER_PATTERN = re.compile(
        r"(?:Before|Current|Old).*?```[\w]*\s*\n([\s\S]*?)\n```"
        r"[\s\S]*?"
        r"(?:After|Suggested|New|Fixed).*?```[\w]*\s*\n([\s\S]*?)\n```",
        re.IGNORECASE | re.MULTILINE,
    )

    # Pattern to match inline suggestions with - and + markers
    INLINE_DIFF_PATTERN = re.compile(
        r"^-\s*(.+)$\n^\+\s*(.+)$",
        re.MULTILINE,
    )

    # Pattern to extract file path from comment
    FILE_PATH_PATTERN = re.compile(r"`([^`]+\.[a-zA-Z]+)`")

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
        """Apply a single fix to a file."""
        file_path = self.repo_root / fix.file_path

        if not file_path.exists():
            return FixResult(fix, False, f"File not found: {fix.file_path}")

        try:
            content = file_path.read_text(encoding="utf-8")

            # Try exact match replacement
            if fix.old_code in content:
                new_content = content.replace(fix.old_code, fix.new_code, 1)
                file_path.write_text(new_content, encoding="utf-8")
                result = FixResult(fix, True, "Applied exact match")
                self.applied_fixes.append(result)
                return result

            # Try line-based replacement
            lines = content.split("\n")
            if fix.start_line > 0 and fix.end_line <= len(lines):
                # Get the relevant lines
                start_idx = fix.start_line - 1
                end_idx = fix.end_line
                old_section = "\n".join(lines[start_idx:end_idx])

                # Check if old code matches approximately
                if self._fuzzy_match(old_section, fix.old_code):
                    lines[start_idx:end_idx] = fix.new_code.split("\n")
                    new_content = "\n".join(lines)
                    file_path.write_text(new_content, encoding="utf-8")
                    result = FixResult(fix, True, "Applied line-based match")
                    self.applied_fixes.append(result)
                    return result

            return FixResult(fix, False, "Could not locate code to replace")

        except Exception as e:
            return FixResult(fix, False, f"Error: {e}")

    def _fuzzy_match(self, text1: str, text2: str, threshold: float = 0.8) -> bool:
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
            subprocess.run(
                ["ruff", "check", "--fix", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
            )
            results["ruff"] = True
        except Exception:
            results["ruff"] = False

        # Run black for Python formatting
        try:
            subprocess.run(
                ["black", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
            )
            results["black"] = True
        except Exception:
            results["black"] = False

        # Run isort for Python imports
        try:
            subprocess.run(
                ["isort", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
            )
            results["isort"] = True
        except Exception:
            results["isort"] = False

        # Run prettier for JS/TS
        try:
            subprocess.run(
                ["npx", "prettier", "--write", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
            )
            results["prettier"] = True
        except Exception:
            results["prettier"] = False

        # Run ESLint fix for JS/TS
        try:
            subprocess.run(
                ["npx", "eslint", "--fix", "."],
                cwd=self.repo_root,
                capture_output=True,
                timeout=120,
            )
            results["eslint"] = True
        except Exception:
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

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"Iteration {iteration}/{max_iterations}")
        print("=" * 60)

        # Fetch latest comments
        print("Fetching CodeRabbit comments...")
        review_comments = github_api.get_pr_review_comments(pr_number)
        issue_comments = github_api.get_pr_issue_comments(pr_number)

        # Parse fixes
        fixes = parser.parse_all_comments(review_comments + issue_comments)
        print(f"Found {len(fixes)} potential fixes")

        if not fixes:
            print("No more fixes to apply")
            break

        # Apply fixes
        applied_count = 0
        for fix in fixes:
            print(f"\nApplying fix to {fix.file_path}:{fix.start_line}")
            print(f"  Category: {fix.category}")
            print(f"  Description: {fix.description[:80]}...")

            result = fixer.apply_fix(fix)
            all_results.append(result)

            if result.success:
                applied_count += 1
                print(f"  Result: SUCCESS - {result.message}")
            else:
                print(f"  Result: SKIPPED - {result.message}")

        print(f"\nApplied {applied_count}/{len(fixes)} fixes")

        # Run linters to fix additional issues
        print("\nRunning linters...")
        linter_results = fixer.run_linters()
        for linter, success in linter_results.items():
            status = "OK" if success else "SKIPPED"
            print(f"  {linter}: {status}")

        if applied_count == 0:
            print("No fixes applied in this iteration, stopping loop")
            break

        # Small delay before next iteration
        if iteration < max_iterations:
            print("\nWaiting before next iteration...")
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


def main():
    parser = argparse.ArgumentParser(description="CodeRabbit Auto-Fix Script")
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--pr", required=True, type=int, help="PR number")
    parser.add_argument(
        "--max-iterations", type=int, default=3, help="Maximum fix iterations"
    )
    parser.add_argument("--output-summary", help="Path to write summary markdown")
    args = parser.parse_args()

    # Get GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)

    # Initialize
    github_api = GitHubAPI(token, args.repo)
    repo_root = Path.cwd()

    print(f"Repository: {args.repo}")
    print(f"PR Number: {args.pr}")
    print(f"Max Iterations: {args.max_iterations}")
    print(f"Repo Root: {repo_root}")

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
            with open(github_output, "a") as f:
                f.write("fixes_applied=true\n")


if __name__ == "__main__":
    main()
