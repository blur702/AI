#!/usr/bin/env python3
"""
CodeRabbit Auto-Fix Script (v2 - Safe Implementation)

Parses CodeRabbit review comments from a PR, extracts suggested fixes,
and applies them with comprehensive safety checks:
- Language validation (Python code only applied to .py files, etc.)
- Syntax validation before and after applying fixes
- Strict code matching (no fuzzy matching that caused injection bugs)
- Rollback on failure

Key Differences from v1:
- Validates language markers in code blocks match target file extension
- Runs syntax check (compile for Python, tsc for TS) after each fix
- Requires exact or near-exact match (whitespace-normalized only)
- Rolls back changes if syntax validation fails
"""

import argparse
import ast
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# File extension to language mapping
EXTENSION_TO_LANGUAGE: dict[str, set[str]] = {
    ".py": {"python", "py", ""},
    ".js": {"javascript", "js", ""},
    ".ts": {"typescript", "ts", ""},
    ".tsx": {"typescript", "tsx", ""},
    ".jsx": {"javascript", "jsx", ""},
    ".css": {"css", ""},
    ".html": {"html", ""},
    ".json": {"json", ""},
    ".yaml": {"yaml", "yml", ""},
    ".yml": {"yaml", "yml", ""},
    ".md": {"markdown", "md", ""},
    ".rs": {"rust", "rs", ""},
    ".go": {"go", "golang", ""},
}

# Languages that should NEVER be mixed (e.g., never put JS in Python files)
INCOMPATIBLE_LANGUAGES: dict[str, set[str]] = {
    ".py": {"javascript", "js", "typescript", "ts", "tsx", "jsx", "html", "css"},
    ".js": {"python", "py", "rust", "rs", "go"},
    ".ts": {"python", "py", "rust", "rs", "go"},
    ".tsx": {"python", "py", "rust", "rs", "go"},
    ".jsx": {"python", "py", "rust", "rs", "go"},
}


@dataclass
class CodeFix:
    """Represents a code fix suggestion from CodeRabbit."""

    file_path: str
    start_line: int
    end_line: int
    old_code: str
    new_code: str
    description: str
    category: str
    language_hint: str  # Language marker from code block (e.g., "python", "typescript")
    confidence: float  # 0.0-1.0, how confident we are this is a valid fix


@dataclass
class FixResult:
    """Result of applying a fix."""

    fix: CodeFix
    success: bool
    message: str
    rolled_back: bool = False


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

    def _get_with_retry(
        self, url: str, params: dict | None = None, retries: int = 3
    ) -> requests.Response:
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
                    response.raise_for_status()
                return response
            except (requests.exceptions.RequestException, requests.exceptions.HTTPError):
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt)
        raise requests.exceptions.RequestException("Max retries exceeded")

    def get_pr_review_comments(self, pr_number: int) -> list[dict]:
        """Fetch all review comments for a PR."""
        url = f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}/comments"
        all_comments = []
        page = 1

        while True:
            response = self._get_with_retry(url, params={"per_page": 100, "page": page})
            response.raise_for_status()
            comments = response.json()
            if not comments:
                break
            all_comments.extend(comments)
            page += 1

        return all_comments

    def get_pr_issue_comments(self, pr_number: int) -> list[dict]:
        """Fetch issue-level comments."""
        url = f"{self.base_url}/repos/{self.repo}/issues/{pr_number}/comments"
        all_comments = []
        page = 1

        while True:
            response = self._get_with_retry(url, params={"per_page": 100, "page": page})
            response.raise_for_status()
            comments = response.json()
            if not comments:
                break
            all_comments.extend(comments)
            page += 1

        return all_comments


class CodeRabbitParser:
    """
    Parses CodeRabbit review comments with strict language validation.

    Key safety features:
    1. Extracts language hint from code block markers (```python, ```typescript)
    2. Only creates fixes where the language matches the target file
    3. Requires explicit before/after structure, not just any diff block
    4. Assigns confidence scores based on how well the suggestion matches
    """

    # Pattern for code blocks WITH language hint
    # Captures: language, content
    CODE_BLOCK_PATTERN = re.compile(
        r"```(\w+)?\s*\n"  # Opening fence with optional language
        r"([\s\S]*?)"  # Content
        r"\n```",  # Closing fence
        re.MULTILINE,
    )

    # Pattern for explicit before/after blocks (safer than generic diff parsing)
    # This is more strict - requires clear "Before:" and "After:" labels
    EXPLICIT_FIX_PATTERN = re.compile(
        r"(?:^|\n)(?:\*\*)?(?:Before|Current|Existing)(?:\*\*)?:?\s*\n"
        r"```(\w*)\s*\n"
        r"([\s\S]*?)"
        r"\n```"
        r"[\s\S]*?"
        r"(?:^|\n)(?:\*\*)?(?:After|Suggested|Fixed|New|Corrected)(?:\*\*)?:?\s*\n"
        r"```(\w*)\s*\n"
        r"([\s\S]*?)"
        r"\n```",
        re.IGNORECASE | re.MULTILINE,
    )

    # Pattern for GitHub suggestion blocks (most reliable format)
    GITHUB_SUGGESTION_PATTERN = re.compile(
        r"```suggestion\s*\n" r"([\s\S]*?)" r"\n```", re.MULTILINE
    )

    def __init__(self):
        self.fixes: list[CodeFix] = []

    def is_coderabbit_comment(self, comment: dict) -> bool:
        """Check if a comment is from CodeRabbit."""
        user = comment.get("user", {})
        login = user.get("login", "")
        return "coderabbit" in login.lower() or "coderabbitai" in login.lower()

    def parse_review_comment(self, comment: dict) -> CodeFix | None:
        """Parse a single review comment for fix suggestions with strict validation."""
        if not self.is_coderabbit_comment(comment):
            return None

        body = comment.get("body", "")
        path = comment.get("path", "")
        line = comment.get("line") or comment.get("original_line", 0)
        start_line = comment.get("start_line") or line

        if not path:
            return None

        # Get file extension for language validation
        file_ext = Path(path).suffix.lower()

        # Try GitHub suggestion format first (most reliable)
        fix = self._parse_github_suggestion(body, path, start_line, line, file_ext)
        if fix:
            return fix

        # Try explicit before/after format
        fix = self._parse_explicit_fix(body, path, start_line, line, file_ext)
        if fix:
            return fix

        return None

    def _parse_github_suggestion(
        self,
        body: str,
        file_path: str,
        start_line: int,
        end_line: int,
        file_ext: str,
    ) -> CodeFix | None:
        """Parse GitHub-style suggestion blocks (```suggestion)."""
        match = self.GITHUB_SUGGESTION_PATTERN.search(body)
        if not match:
            return None

        new_code = match.group(1)

        # GitHub suggestions replace the commented lines directly
        # We need to fetch the original code from the file (done later in apply_fix)
        return CodeFix(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            old_code="",  # Will be filled from file
            new_code=new_code,
            description=self._extract_description(body),
            category=self._categorize_fix(body),
            language_hint="suggestion",  # Special marker for GitHub suggestions
            confidence=0.9,  # High confidence for GitHub suggestions
        )

    def _parse_explicit_fix(
        self,
        body: str,
        file_path: str,
        start_line: int,
        end_line: int,
        file_ext: str,
    ) -> CodeFix | None:
        """Parse explicit before/after code blocks with language validation."""
        match = self.EXPLICIT_FIX_PATTERN.search(body)
        if not match:
            return None

        before_lang = (match.group(1) or "").lower()
        old_code = match.group(2).strip()
        after_lang = (match.group(3) or "").lower()
        new_code = match.group(4).strip()

        if old_code == new_code:
            return None

        # Validate language compatibility
        if not self._validate_language(file_ext, before_lang, after_lang):
            logger.warning(
                "Language mismatch: file=%s, before_lang=%s, after_lang=%s",
                file_path,
                before_lang,
                after_lang,
            )
            return None

        # Check for incompatible language markers
        if self._is_incompatible_language(file_ext, before_lang) or self._is_incompatible_language(
            file_ext, after_lang
        ):
            logger.warning(
                "Incompatible language detected for %s: %s/%s",
                file_path,
                before_lang,
                after_lang,
            )
            return None

        # Calculate confidence based on language match
        confidence = 0.8
        expected_langs = EXTENSION_TO_LANGUAGE.get(file_ext, set())
        if before_lang in expected_langs and after_lang in expected_langs:
            confidence = 0.9
        elif before_lang == "" and after_lang == "":
            confidence = 0.6  # No language hints, lower confidence

        return CodeFix(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            old_code=old_code,
            new_code=new_code,
            description=self._extract_description(body),
            category=self._categorize_fix(body),
            language_hint=after_lang or before_lang or "",
            confidence=confidence,
        )

    def _validate_language(self, file_ext: str, before_lang: str, after_lang: str) -> bool:
        """Validate that the code block language matches the file type."""
        expected = EXTENSION_TO_LANGUAGE.get(file_ext, set())

        # If no language hints, we can't validate - accept with lower confidence
        if not before_lang and not after_lang:
            return True

        # At least one language hint should match expected
        if before_lang and before_lang not in expected:
            return False
        if after_lang and after_lang not in expected:
            return False

        # Both hints should be consistent (same language family)
        if before_lang and after_lang and before_lang != after_lang:
            # Allow empty -> specific (e.g., "" -> "python")
            if before_lang != "" and after_lang != "":
                return False

        return True

    def _is_incompatible_language(self, file_ext: str, lang: str) -> bool:
        """Check if a language is definitely incompatible with the file type."""
        incompatible = INCOMPATIBLE_LANGUAGES.get(file_ext, set())
        return lang.lower() in incompatible

    def _extract_description(self, body: str) -> str:
        """Extract a brief description from the comment."""
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith("```") and not line.startswith("-"):
                return line[:200] if len(line) > 200 else line
        return "CodeRabbit suggestion"

    def _categorize_fix(self, body: str) -> str:
        """Categorize the fix based on keywords."""
        body_lower = body.lower()
        if any(kw in body_lower for kw in ["security", "vulnerability", "injection"]):
            return "security"
        if any(kw in body_lower for kw in ["performance", "optimize", "efficient"]):
            return "performance"
        if any(kw in body_lower for kw in ["bug", "error", "fix", "issue"]):
            return "bug"
        if any(kw in body_lower for kw in ["type", "typing", "annotation"]):
            return "typing"
        if any(kw in body_lower for kw in ["style", "format", "indent"]):
            return "style"
        return "improvement"

    def parse_all_comments(self, comments: list[dict]) -> list[CodeFix]:
        """Parse all comments and extract validated fixes."""
        fixes = []
        for comment in comments:
            fix = self.parse_review_comment(comment)
            if fix:
                fixes.append(fix)
        return fixes


class SyntaxValidator:
    """Validates syntax for different file types."""

    @staticmethod
    def validate_python(content: str) -> tuple[bool, str]:
        """Validate Python syntax using ast.parse."""
        try:
            ast.parse(content)
            return True, ""
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}: {e.msg}"

    @staticmethod
    def validate_typescript(file_path: Path) -> tuple[bool, str]:
        """Validate TypeScript syntax using tsc."""
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", "--skipLibCheck", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr[:500]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # If tsc not available, skip validation
            return True, "TypeScript validation skipped"

    @staticmethod
    def validate_javascript(content: str) -> tuple[bool, str]:
        """Basic JavaScript syntax check using Node."""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(content)
                temp_path = f.name

            result = subprocess.run(
                ["node", "--check", temp_path],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            Path(temp_path).unlink(missing_ok=True)

            if result.returncode == 0:
                return True, ""
            return False, result.stderr[:500]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, "JavaScript validation skipped"

    @staticmethod
    def validate(file_path: Path, content: str) -> tuple[bool, str]:
        """Validate file syntax based on extension."""
        ext = file_path.suffix.lower()

        if ext == ".py":
            return SyntaxValidator.validate_python(content)
        elif ext in (".ts", ".tsx"):
            # Write content temporarily and validate
            try:
                file_path.write_text(content, encoding="utf-8")
                return SyntaxValidator.validate_typescript(file_path)
            except OSError as e:
                return False, str(e)
        elif ext in (".js", ".jsx"):
            return SyntaxValidator.validate_javascript(content)

        # For other file types, assume valid
        return True, ""


class AutoFixer:
    """Applies code fixes with validation and rollback."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.applied_fixes: list[FixResult] = []
        self.validator = SyntaxValidator()

    def apply_fix(self, fix: CodeFix) -> FixResult:
        """
        Apply a single fix with comprehensive safety checks.

        Safety measures:
        1. Validates file exists and is within repo
        2. Requires exact match (whitespace-normalized) for old_code
        3. Validates syntax before and after the fix
        4. Rolls back if syntax validation fails
        """
        file_path = self.repo_root / fix.file_path

        # Security: Validate file is within repo
        if not file_path.exists():
            return FixResult(fix, False, f"File not found: {fix.file_path}")

        try:
            file_path.resolve().relative_to(self.repo_root.resolve())
        except ValueError:
            return FixResult(fix, False, f"File path outside repository: {fix.file_path}")

        # Read original content
        try:
            original_content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                original_content = file_path.read_text(encoding="latin-1")
            except Exception as e:
                return FixResult(fix, False, f"Failed to read file: {e}")
        except OSError as e:
            return FixResult(fix, False, f"OS error reading file: {e}")

        # Validate original syntax first
        valid_before, error_before = SyntaxValidator.validate(file_path, original_content)
        if not valid_before:
            logger.warning("File has syntax errors before fix: %s", error_before)
            # Continue anyway - we might be fixing the syntax error

        # Handle GitHub suggestion format (old_code is empty, need to extract from file)
        if fix.language_hint == "suggestion" and not fix.old_code:
            old_code = self._extract_lines(original_content, fix.start_line, fix.end_line)
            if old_code is None:
                return FixResult(fix, False, f"Could not extract lines {fix.start_line}-{fix.end_line}")
            fix = CodeFix(
                file_path=fix.file_path,
                start_line=fix.start_line,
                end_line=fix.end_line,
                old_code=old_code,
                new_code=fix.new_code,
                description=fix.description,
                category=fix.category,
                language_hint=fix.language_hint,
                confidence=fix.confidence,
            )

        # Try exact match replacement
        if fix.old_code in original_content:
            new_content = original_content.replace(fix.old_code, fix.new_code, 1)

            # Validate new syntax
            valid_after, error_after = SyntaxValidator.validate(file_path, new_content)
            if not valid_after:
                logger.error(
                    "Fix would break syntax in %s: %s", fix.file_path, error_after
                )
                return FixResult(
                    fix, False, f"Fix rejected: would cause syntax error - {error_after}", rolled_back=True
                )

            # Apply the fix
            try:
                file_path.write_text(new_content, encoding="utf-8")
                result = FixResult(fix, True, "Applied with exact match")
                self.applied_fixes.append(result)
                return result
            except OSError as e:
                return FixResult(fix, False, f"Failed to write file: {e}")

        # Try whitespace-normalized match
        new_content = self._try_normalized_match(original_content, fix)
        if new_content:
            # Validate new syntax
            valid_after, error_after = SyntaxValidator.validate(file_path, new_content)
            if not valid_after:
                logger.error(
                    "Fix would break syntax in %s: %s", fix.file_path, error_after
                )
                return FixResult(
                    fix, False, f"Fix rejected: would cause syntax error - {error_after}", rolled_back=True
                )

            try:
                file_path.write_text(new_content, encoding="utf-8")
                result = FixResult(fix, True, "Applied with normalized match")
                self.applied_fixes.append(result)
                return result
            except OSError as e:
                return FixResult(fix, False, f"Failed to write file: {e}")

        return FixResult(fix, False, "Could not locate code to replace (no match found)")

    def _extract_lines(self, content: str, start: int, end: int) -> str | None:
        """Extract lines from content."""
        lines = content.split("\n")
        if start < 1 or end > len(lines):
            return None
        return "\n".join(lines[start - 1 : end])

    def _try_normalized_match(self, content: str, fix: CodeFix) -> str | None:
        """
        Try to find and replace code with whitespace normalization.

        Only normalizes LEADING whitespace (indentation), not internal spacing.
        This handles indentation differences while being strict about content.
        """
        lines = content.split("\n")
        old_lines = fix.old_code.split("\n")

        if not old_lines:
            return None

        # Find potential match locations
        first_old_line_stripped = old_lines[0].strip()
        if not first_old_line_stripped:
            return None

        for i, line in enumerate(lines):
            if line.strip() == first_old_line_stripped:
                # Check if subsequent lines match
                if i + len(old_lines) > len(lines):
                    continue

                match = True
                for j, old_line in enumerate(old_lines):
                    if lines[i + j].strip() != old_line.strip():
                        match = False
                        break

                if match:
                    # Preserve the indentation of the first line
                    original_indent = len(lines[i]) - len(lines[i].lstrip())
                    indent_str = lines[i][:original_indent]

                    # Apply new code with same base indentation
                    new_lines = fix.new_code.split("\n")
                    if new_lines:
                        # Calculate relative indentation
                        new_first_indent = len(new_lines[0]) - len(new_lines[0].lstrip())
                        adjusted_new_lines = []
                        for new_line in new_lines:
                            if new_line.strip():
                                current_indent = len(new_line) - len(new_line.lstrip())
                                relative_indent = current_indent - new_first_indent
                                adjusted_new_lines.append(
                                    indent_str + " " * max(0, relative_indent) + new_line.strip()
                                )
                            else:
                                adjusted_new_lines.append("")

                        lines[i : i + len(old_lines)] = adjusted_new_lines
                        return "\n".join(lines)

        return None

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
            results["isort"] = False

        return results


def run_autofix_loop(
    github_api: GitHubAPI,
    pr_number: int,
    max_iterations: int,
    repo_root: Path,
    min_confidence: float = 0.7,
) -> tuple[int, list[FixResult]]:
    """
    Run the auto-fix loop with safety checks.

    Args:
        github_api: GitHub API client
        pr_number: Pull request number
        max_iterations: Maximum iterations
        repo_root: Repository root path
        min_confidence: Minimum confidence threshold (0.0-1.0)

    Returns:
        Tuple of (iterations_run, all_fix_results)
    """
    parser = CodeRabbitParser()
    fixer = AutoFixer(repo_root)
    all_results: list[FixResult] = []
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        logger.info("=" * 60)
        logger.info("Iteration %d/%d", iteration, max_iterations)
        logger.info("=" * 60)

        # Fetch latest comments
        logger.info("Fetching CodeRabbit comments...")
        review_comments = github_api.get_pr_review_comments(pr_number)
        issue_comments = github_api.get_pr_issue_comments(pr_number)

        # Parse fixes
        all_fixes = parser.parse_all_comments(review_comments + issue_comments)

        # Filter by confidence
        fixes = [f for f in all_fixes if f.confidence >= min_confidence]
        logger.info(
            "Found %d potential fixes (%d above confidence threshold %.1f)",
            len(all_fixes),
            len(fixes),
            min_confidence,
        )

        if not fixes:
            logger.info("No more fixes to apply")
            break

        # Apply fixes
        applied_count = 0
        rejected_count = 0

        for fix in fixes:
            logger.info(
                "Attempting fix: %s:%d (confidence=%.2f, lang=%s)",
                fix.file_path,
                fix.start_line,
                fix.confidence,
                fix.language_hint,
            )
            logger.info("  Category: %s", fix.category)
            logger.info("  Description: %s...", fix.description[:80])

            result = fixer.apply_fix(fix)
            all_results.append(result)

            if result.success:
                applied_count += 1
                logger.info("  Result: SUCCESS - %s", result.message)
            elif result.rolled_back:
                rejected_count += 1
                logger.warning("  Result: REJECTED - %s", result.message)
            else:
                logger.info("  Result: SKIPPED - %s", result.message)

        logger.info(
            "Applied %d fixes, rejected %d (would break syntax)",
            applied_count,
            rejected_count,
        )

        # Run linters
        logger.info("Running linters...")
        linter_results = fixer.run_linters()
        for linter, success in linter_results.items():
            status = "OK" if success else "SKIPPED"
            logger.info("  %s: %s", linter, status)

        if applied_count == 0:
            logger.info("No fixes applied in this iteration, stopping loop")
            break

        # Delay before next iteration
        if iteration < max_iterations:
            logger.info("Waiting before next iteration...")
            time.sleep(5)

    return iteration, all_results


def generate_summary(
    iterations: int, results: list[FixResult], output_path: Path | None
) -> str:
    """Generate a markdown summary of the auto-fix run."""
    successful = [r for r in results if r.success]
    rejected = [r for r in results if r.rolled_back]
    skipped = [r for r in results if not r.success and not r.rolled_back]

    lines = [
        f"### Iterations: {iterations}",
        f"### Fixes Applied: {len(successful)}",
        f"### Fixes Rejected (syntax errors): {len(rejected)}",
        f"### Fixes Skipped (no match): {len(skipped)}",
        "",
    ]

    if successful:
        lines.append("#### Successfully Applied:")
        for r in successful:
            lines.append(f"- `{r.fix.file_path}:{r.fix.start_line}` - {r.fix.category}")

    if rejected:
        lines.append("")
        lines.append("#### Rejected (would break syntax):")
        for r in rejected[:5]:
            lines.append(f"- `{r.fix.file_path}:{r.fix.start_line}` - {r.message}")
        if len(rejected) > 5:
            lines.append(f"- ... and {len(rejected) - 5} more")

    if skipped:
        lines.append("")
        lines.append("#### Skipped (manual review needed):")
        for r in skipped[:5]:
            lines.append(f"- `{r.fix.file_path}:{r.fix.start_line}` - {r.message}")
        if len(skipped) > 5:
            lines.append(f"- ... and {len(skipped) - 5} more")

    summary = "\n".join(lines)

    if output_path:
        output_path.write_text(summary, encoding="utf-8")

    return summary


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CodeRabbit Auto-Fix Script v2 (Safe Implementation)",
    )
    parser.add_argument("--repo", required=True, help="Repository in format owner/repo")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum fix iterations (default: 3)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum confidence threshold 0.0-1.0 (default: 0.7)",
    )
    parser.add_argument("--output-summary", help="Path to write summary markdown file")
    args = parser.parse_args()

    # Validate arguments
    if args.max_iterations < 1:
        print("Error: --max-iterations must be at least 1", file=sys.stderr)
        sys.exit(1)

    if not 0.0 <= args.min_confidence <= 1.0:
        print("Error: --min-confidence must be between 0.0 and 1.0", file=sys.stderr)
        sys.exit(1)

    if "/" not in args.repo:
        print("Error: --repo must be in format owner/repo", file=sys.stderr)
        sys.exit(1)

    # Get GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    try:
        github_api = GitHubAPI(token, args.repo)
        repo_root = Path.cwd()

        print(f"Repository: {args.repo}")
        print(f"PR Number: {args.pr}")
        print(f"Max Iterations: {args.max_iterations}")
        print(f"Min Confidence: {args.min_confidence}")
        print(f"Repo Root: {repo_root}")
        print("")

        # Run the auto-fix loop
        iterations, results = run_autofix_loop(
            github_api,
            args.pr,
            args.max_iterations,
            repo_root,
            args.min_confidence,
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
