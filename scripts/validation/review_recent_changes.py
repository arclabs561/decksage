#!/usr/bin/env python3
"""
Review recently edited files for common issues and rule violations.

This script is designed to be read by both humans and AI agents.
It checks recently modified files against project rules and themes.

Common Rules & Themes (for AI agents):
- Use PATHS utility instead of hardcoded paths
- Avoid code duplication (check for existing functions before creating new ones)
- Follow data lineage principles (Order 0-6 hierarchy)
- Use type hints (Python 3.11+)
- Prefer uv/uvx over pip
- Use fd not find, rg not grep, bat not cat
- PEP 723 scripts for standalone tools
- Property-based testing for invariants
- No premature abstraction (wait for 3+ occurrences)
- Chesterton's fence: understand before changing
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def get_recent_files(commits: int = 5) -> list[str]:
    """Get list of recently modified files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"HEAD~{commits}..HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return sorted(set(files))
    except subprocess.CalledProcessError:
        return []


def get_staged_files() -> list[str]:
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return sorted(set(files))
    except subprocess.CalledProcessError:
        return []


def check_file_rules(file_path: Path) -> list[dict[str, Any]]:
    """Check a file against common rules."""
    issues = []

    if not file_path.exists() or file_path.suffix != ".py":
        return issues

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return issues

    # Rule: Check for hardcoded paths (should use PATHS utility)
    hardcoded_patterns = [
        r'Path\("data/',
        r'Path\("experiments/',
        r'Path\("src/ml/',
        r'["\']data/',
        r'["\']experiments/',
    ]

    for line_num, line in enumerate(content.splitlines(), 1):
        for pattern in hardcoded_patterns:
            if re.search(pattern, line) and not line.strip().startswith("#"):
                # Skip if it's in the PATHS utility file itself
                if "paths.py" in str(file_path):
                    continue
                issues.append(
                    {
                        "type": "hardcoded_path",
                        "line": line_num,
                        "message": "Consider using PATHS utility from ml.utils.paths",
                        "severity": "medium",
                    }
                )
                break

    # Rule: Check for TODO/FIXME without context
    if "TODO" in content or "FIXME" in content:
        for line_num, line in enumerate(content.splitlines(), 1):
            if ("TODO" in line or "FIXME" in line) and not any(
                keyword in line for keyword in ["# TODO", "# FIXME", "TODO:", "FIXME:"]
            ):
                issues.append(
                    {
                        "type": "todo_format",
                        "line": line_num,
                        "message": "TODO/FIXME should include context (e.g., # TODO: reason)",
                        "severity": "low",
                    }
                )

    return issues


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Review recently edited files for common issues.")
    parser.add_argument(
        "--commits",
        type=int,
        default=5,
        help="Number of commits to look back (default: 5)",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Review staged files instead of recent commits",
    )
    args = parser.parse_args()

    if args.staged:
        files = get_staged_files()
        print("📋 Reviewing staged files...")
    else:
        files = get_recent_files(args.commits)
        print(f"📋 Reviewing files from last {args.commits} commits...")

    if not files:
        print("✅ No files to review")
        return 0

    print(f"Found {len(files)} files to review\n")

    all_issues = []
    for file_path_str in files:
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue

        issues = check_file_rules(file_path)
        if issues:
            all_issues.extend([(file_path, issue) for issue in issues])

    if not all_issues:
        print("✅ No issues found in recently edited files")
        return 0

    print("⚠️  Issues found:\n")
    for file_path, issue in all_issues:
        print(f"{file_path}:{issue['line']}")
        print(f"  [{issue['type']}] {issue['message']}")
        print()

    print(f"\nFound {len(all_issues)} issue(s) in recently edited files")
    print("💡 Tip: Review these against project rules in .cursor/rules/")
    return 1


if __name__ == "__main__":
    sys.exit(main())
