#!/usr/bin/env python3
"""Check for hardcoded paths that should use PATHS utility."""

import re
import sys
from pathlib import Path


# Patterns that indicate hardcoded paths
HARDCODED_PATTERNS = [
    r'["\']data/',
    r'["\']experiments/',
    r'["\']src/ml/',
    r'Path\(["\']data/',
    r'Path\(["\']experiments/',
    r'Path\(["\']src/ml/',
]

# Files that are allowed to have hardcoded paths
ALLOWED_FILES = {
    "src/ml/utils/paths.py",  # Defines PATHS
    "scripts/data_processing/validate_lineage.py",  # Needs to check paths
    "scripts/validation/check_hardcoded_paths.py",  # This file
}


def check_file(file_path: Path) -> list[tuple[int, str]]:
    """Check a single file for hardcoded paths."""
    issues = []

    if str(file_path) in ALLOWED_FILES:
        return issues

    try:
        with open(file_path) as f:
            for line_num, line in enumerate(f, 1):
                for pattern in HARDCODED_PATTERNS:
                    if re.search(pattern, line):
                        # Skip comments and docstrings
                        stripped = line.strip()
                        if (
                            stripped.startswith("#")
                            or stripped.startswith('"""')
                            or stripped.startswith("'''")
                        ):
                            continue
                        issues.append((line_num, line.strip()))
                        break
    except Exception:
        pass

    return issues


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        return 0

    issues_found = False
    for file_path_str in sys.argv[1:]:
        file_path = Path(file_path_str)
        if not file_path.exists() or not file_path.suffix == ".py":
            continue

        issues = check_file(file_path)
        if issues:
            issues_found = True
            print(f"\n{file_path}:")
            for line_num, line in issues:
                print(f"  {line_num}: {line}")
                print("    → Consider using PATHS utility from ml.utils.paths")

    if issues_found:
        print("\n⚠️  Found hardcoded paths. Use PATHS utility for consistency.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
