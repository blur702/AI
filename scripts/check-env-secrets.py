#!/usr/bin/env python3
"""
Scan .env files for potential secrets.

This script checks .env and .env.example files to ensure:
1. .env.example files contain only safe placeholder values
2. No actual secrets are committed

Usage:
    python scripts/check-env-secrets.py          # Local check
    python scripts/check-env-secrets.py --ci     # CI mode (stricter)
    python scripts/check-env-secrets.py --fix    # Show safe replacements
"""

import argparse
import re
import sys
from pathlib import Path

# Patterns that indicate a real secret (not a placeholder)
SECRET_PATTERNS = [
    # API Keys (various formats)
    (r'(?i)(api[_-]?key|apikey)\s*=\s*["\']?[a-zA-Z0-9_\-]{20,}["\']?', "API key"),
    (r"(?i)sk-[a-zA-Z0-9]{20,}", "OpenAI API key"),
    (r"(?i)sk_live_[a-zA-Z0-9]{20,}", "Stripe live key"),
    (r"(?i)sk_test_[a-zA-Z0-9]{20,}", "Stripe test key"),
    (r"(?i)xox[baprs]-[a-zA-Z0-9\-]{10,}", "Slack token"),
    (r"(?i)ghp_[a-zA-Z0-9]{36}", "GitHub PAT"),
    (r"(?i)gho_[a-zA-Z0-9]{36}", "GitHub OAuth token"),
    (r'(?i)github_token\s*=\s*["\']?[a-zA-Z0-9_]{30,}', "GitHub token"),
    # AWS
    (r"(?i)AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*=\s*["\']?[a-zA-Z0-9/+=]{40}', "AWS Secret Key"),
    # Database passwords
    (
        r'(?i)(password|passwd|pwd)\s*=\s*["\']?(?!.*(\$\{|your[_-]|changeme|placeholder|example|xxx|password))[a-zA-Z0-9!@#$%^&*()_+\-=]{8,}["\']?',
        "Password",
    ),
    (r"(?i)postgres://[^:]+:[^@]+@", "Database URL with credentials"),
    (r"(?i)mysql://[^:]+:[^@]+@", "Database URL with credentials"),
    (r"(?i)mongodb(\+srv)?://[^:]+:[^@]+@", "MongoDB URL with credentials"),
    # Private keys
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "Private key"),
    (r"-----BEGIN PGP PRIVATE KEY BLOCK-----", "PGP private key"),
    # JWT/Auth secrets
    (
        r'(?i)(jwt[_-]?secret|auth[_-]?secret|secret[_-]?key)\s*=\s*["\']?[a-zA-Z0-9_\-]{32,}["\']?',
        "JWT/Auth secret",
    ),
    # Generic secrets
    (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer token"),
    (r'(?i)token\s*=\s*["\']?[a-zA-Z0-9_\-]{32,}["\']?', "Token"),
]

# Safe placeholder patterns (these are OK)
SAFE_PATTERNS = [
    r"(?i)your[_-]",  # your-api-key, your_password
    r"(?i)changeme",  # changeme
    r"(?i)placeholder",  # placeholder
    r"(?i)example",  # example.com, example-key
    r"(?i)xxx+",  # xxx, xxxx
    r"(?i)replace[_-]?this",  # replace_this
    r"(?i)insert[_-]?here",  # insert_here
    r"(?i)<[^>]+>",  # <your-key-here>
    r"(?i)\$\{[^}]+\}",  # ${VARIABLE}
    r"(?i)localhost",  # localhost URLs are fine
    r"(?i)127\.0\.0\.1",  # localhost IP
    r"(?i)host\.docker\.internal",  # Docker internal
    r"^#",  # Comments
    r"^\s*$",  # Empty lines
]

# File patterns to scan
ENV_FILE_PATTERNS = [
    "**/.env",
    "**/.env.example",
    "**/.env.local",
    "**/.env.*.local",
    "**/.env.production",
    "**/.env.staging",
    "**/.env.development",
]


def is_safe_value(line: str) -> bool:
    """Check if a line contains only safe placeholder values."""
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def scan_file(filepath: Path, ci_mode: bool = False) -> list[dict]:
    """Scan a single file for secrets."""
    issues = []

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [
            {
                "file": str(filepath),
                "line": 0,
                "issue": f"Could not read file: {e}",
                "severity": "error",
            }
        ]

    for line_num, line in enumerate(content.splitlines(), 1):
        # Skip empty lines and comments
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Skip if it's a safe placeholder
        if is_safe_value(line):
            continue

        # Check against secret patterns
        for pattern, secret_type in SECRET_PATTERNS:
            if re.search(pattern, line):
                # Double-check it's not a safe value
                if not is_safe_value(line):
                    issues.append(
                        {
                            "file": str(filepath),
                            "line": line_num,
                            "issue": f"Potential {secret_type} detected",
                            "content": line[:80] + ("..." if len(line) > 80 else ""),
                            "severity": "error",
                        }
                    )
                    break  # One issue per line is enough

    # In CI mode, also flag non-example .env files
    if ci_mode and filepath.name == ".env" or ".env.local" in filepath.name:
        if "example" not in filepath.name.lower():
            issues.append(
                {
                    "file": str(filepath),
                    "line": 0,
                    "issue": "Non-example .env file should not be committed",
                    "severity": "error",
                }
            )

    return issues


def scan_directory(root: Path, ci_mode: bool = False) -> list[dict]:
    """Scan all .env files in directory."""
    all_issues = []

    for pattern in ENV_FILE_PATTERNS:
        for filepath in root.glob(pattern):
            # Skip node_modules and other ignored directories
            if "node_modules" in filepath.parts:
                continue
            if ".git" in filepath.parts:
                continue

            issues = scan_file(filepath, ci_mode)
            all_issues.extend(issues)

    return all_issues


def main():
    parser = argparse.ArgumentParser(description="Scan .env files for secrets")
    parser.add_argument("--ci", action="store_true", help="CI mode (stricter checks)")
    parser.add_argument("--fix", action="store_true", help="Show suggested fixes")
    parser.add_argument("path", nargs="?", default=".", help="Path to scan")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    print(f"Scanning for secrets in: {root}")
    print("-" * 60)

    issues = scan_directory(root, ci_mode=args.ci)

    if not issues:
        print("[OK] No secrets detected in .env files")
        return 0

    # Group by severity
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    for issue in issues:
        severity_icon = "[ERROR]" if issue["severity"] == "error" else "[WARN]"
        print(f"{severity_icon} {issue['file']}:{issue['line']}")
        print(f"  {issue['issue']}")
        if "content" in issue:
            # Mask potential secret
            masked = re.sub(
                r'=\s*["\']?([^"\'\s]{4})[^"\'\s]*["\']?', r"= \1****", issue["content"]
            )
            print(f"  Content: {masked}")
        print()

    if args.fix:
        print("-" * 60)
        print("SUGGESTED FIXES:")
        print("1. Move secrets to a local .env file (not committed)")
        print("2. Use placeholders in .env.example:")
        print("   API_KEY=your-api-key-here")
        print("   DATABASE_PASSWORD=changeme")
        print("   SECRET_KEY=${SECRET_KEY}")
        print("3. Use environment variables or a secrets manager")

    print("-" * 60)
    print(f"Found {len(errors)} error(s), {len(warnings)} warning(s)")

    if errors:
        if args.ci:
            print("\n::error::Secret scan failed! Remove secrets before committing.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
