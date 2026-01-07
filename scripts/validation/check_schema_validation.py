#!/usr/bin/env python3
"""
Check that deck loading uses schema validation.

Scans Python files for deck loading functions and reports if they
should use validate_deck_record from ml.data.export_schema.
"""

import re
import sys
from collections.abc import Iterator
from pathlib import Path


# Functions that load deck data
LOAD_PATTERNS = [
    "load_decks",
    "iter_decks",
    "json.loads",
    "json.load",
]

# Exclude patterns
EXCLUDE_PATTERNS = [
    r"__pycache__",
    r"\.pyc$",
    r"test_.*\.py",
    r"src/ml/data/export_schema\.py",  # Schema module itself
    r"src/ml/validation/validators/loader\.py",  # Already uses validation
]


def should_exclude(file_path: Path) -> bool:
    """Check if file should be excluded from checks."""
    path_str = str(file_path)
    return any(re.search(pattern, path_str) for pattern in EXCLUDE_PATTERNS)


def find_unvalidated_loads(file_path: Path) -> Iterator[tuple[int, str, str]]:
    """
    Find unvalidated deck loads in a file.

    Yields:
        (line_number, line_content, issue_description)
    """
    import re

    try:
        content = file_path.read_text()
    except Exception:
        return

    lines = content.split("\n")
    has_validation_import = "validate_deck_record" in content or "DeckExport" in content

    for i, line in enumerate(lines, 1):
        # Check for json.loads/json.load with deck-like patterns
        if re.search(r"json\.(loads?|load)\(", line):
            # Check if it's loading deck data (heuristic: looks for deck_id, cards, etc.)
            if any(keyword in line.lower() for keyword in ["deck", "card", "archetype", "format"]):
                if not has_validation_import:
                    yield (
                        i,
                        line.strip(),
                        "Deck loading without schema validation (consider validate_deck_record)",
                    )


def check_file(file_path: Path) -> list[tuple[int, str, str]]:
    """Check a single file for unvalidated loads."""
    if should_exclude(file_path):
        return []

    if not file_path.suffix == ".py":
        return []

    issues = list(find_unvalidated_loads(file_path))
    return issues


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: check_schema_validation.py <file1> [file2] ...")
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
        print("Found unvalidated deck loads (consider using validate_deck_record):")
        print()
        for file_path, line_num, line_content, issue in all_issues:
            print(f"{file_path}:{line_num}: {issue}")
            print(f"  {line_content}")
            print()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
