#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Find and report duplicate code patterns.

Identifies functions/classes that appear multiple times across the codebase.
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def extract_function_signature(node: ast.FunctionDef) -> str:
    """Extract function signature for comparison."""
    args = [arg.arg for arg in node.args.args]
    return f"{node.name}({', '.join(args)})"


def find_duplicate_functions(path: Path) -> dict[str, list[tuple[Path, int]]]:
    """Find duplicate function definitions."""
    duplicates = defaultdict(list)

    for py_file in path.rglob("*.py"):
        try:
            with open(py_file) as f:
                content = f.read()

            tree = ast.parse(content, filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    sig = extract_function_signature(node)
                    # Only track if function has body (not just pass)
                    if node.body and not (
                        len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
                    ):
                        duplicates[sig].append((py_file, node.lineno))
        except Exception:
            continue

    # Filter to only duplicates
    return {sig: locations for sig, locations in duplicates.items() if len(locations) > 1}


def main() -> int:
    """Main entry point."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Find duplicate code")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("src/ml"),
        help="Path to analyze",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report",
    )

    args = parser.parse_args()

    if not args.path.exists():
        print(f"Error: Path not found: {args.path}")
        return 1

    print("Finding duplicate code patterns...")
    print(f"Path: {args.path}")
    print()

    duplicates = find_duplicate_functions(args.path)

    print(f"Found {len(duplicates)} duplicate function patterns")
    print()

    if duplicates:
        print("Top duplicates:")
        for sig, locations in sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[
            :10
        ]:
            print(f"  {sig}: {len(locations)} occurrences")
            for file_path, line in locations[:3]:
                print(f"    - {file_path.relative_to(args.path)}:{line}")
            if len(locations) > 3:
                print(f"    ... and {len(locations) - 3} more")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(
                {
                    "summary": {
                        "total_duplicates": len(duplicates),
                    },
                    "duplicates": {
                        sig: [{"file": str(f), "line": l} for f, l in locations]
                        for sig, locations in duplicates.items()
                    },
                },
                f,
                indent=2,
            )
        print(f"\nReport saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
