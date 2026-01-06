#!/usr/bin/env python3
"""
Check that data writes use safe_write context manager.

Scans Python files for direct writes to data directories and reports
if they should use safe_write from ml.utils.lineage.
"""

import re
import sys
from collections.abc import Iterator
from pathlib import Path


# Data directory patterns that should use safe_write
DATA_PATTERNS = [
    r"data/processed/",
    r"data/embeddings/",
    r"data/graphs/",
    r"experiments/.*\.jsonl?",
    r"annotations/.*\.jsonl?",
]

# Patterns that indicate direct writes
WRITE_PATTERNS = [
    r'open\([^)]+["\']w',
    r"\.write\(",
    r"\.to_csv\(",
    r"json\.dump\(",
    r"Path\([^)]+\)\.write_text\(",
    r"Path\([^)]+\)\.write_bytes\(",
]

# Exclude patterns (files that are allowed to write directly)
EXCLUDE_PATTERNS = [
    r"__pycache__",
    r"\.pyc$",
    r"test_.*\.py",  # Tests can write directly
    r"scripts/validation/",  # Validation scripts
    r"src/ml/utils/lineage\.py",  # The lineage module itself
    r"scripts/data_processing/validate_lineage\.py",
]


def should_exclude(file_path: Path) -> bool:
    """Check if file should be excluded from checks."""
    path_str = str(file_path)
    return any(re.search(pattern, path_str) for pattern in EXCLUDE_PATTERNS)


def is_data_path(path_str: str) -> bool:
    """Check if path matches data directory patterns."""
    return any(re.search(pattern, path_str) for pattern in DATA_PATTERNS)


def find_unsafe_writes(file_path: Path) -> Iterator[tuple[int, str, str]]:
    """
    Find unsafe writes in a file.

    Yields:
        (line_number, line_content, issue_description)
    """
    try:
        content = file_path.read_text()
    except Exception:
        return

    lines = content.split("\n")
    in_safe_write = False
    safe_write_indent = 0

    for i, line in enumerate(lines, 1):
        # Track if we're inside a safe_write context
        if "safe_write" in line and "with" in line:
            in_safe_write = True
            # Estimate indent level
            safe_write_indent = len(line) - len(line.lstrip())
        elif in_safe_write:
            # Check if we've exited the context (dedent or end of block)
            current_indent = len(line) - len(line.lstrip())
            if (
                line.strip()
                and current_indent <= safe_write_indent
                and not line.strip().startswith("#")
            ):
                in_safe_write = False

        # Check for write patterns
        for pattern in WRITE_PATTERNS:
            if re.search(pattern, line):
                # Check if path is a data path
                # Extract potential path from line
                path_match = re.search(
                    r'["\']([^"\']*(?:data|experiments|annotations)[^"\']*)["\']', line
                )
                if path_match:
                    path_str = path_match.group(1)
                    if is_data_path(path_str) and not in_safe_write:
                        yield (
                            i,
                            line.strip(),
                            f"Direct write to data path without safe_write: {path_str}",
                        )


def check_file(file_path: Path) -> list[tuple[int, str, str]]:
    """Check a single file for unsafe writes."""
    if should_exclude(file_path):
        return []

    if not file_path.suffix == ".py":
        return []

    issues = list(find_unsafe_writes(file_path))
    return issues


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: check_lineage_usage.py <file1> [file2] ...")
        return 1

    files = [Path(f) for f in sys.argv[1:]]
    all_issues = []

    for file_path in files:
        if not file_path.exists():
            print(f"Warning: {file_path} does not exist", file=sys.stderr)
            continue

        issues = check_file(file_path)
        if issues:
            all_issues.extend([(file_path, *issue) for issue in issues])

    if all_issues:
        print("Found unsafe writes (should use safe_write from ml.utils.lineage):")
        print()
        for file_path, line_num, line_content, issue in all_issues:
            print(f"{file_path}:{line_num}: {issue}")
            print(f"  {line_content}")
            print()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
