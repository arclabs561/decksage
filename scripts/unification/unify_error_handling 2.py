#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Unify error handling patterns.

Finds and reports broad exception handling for manual review.
"""

import ast
import sys
from pathlib import Path
from typing import Any


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


class ErrorHandlerAnalyzer(ast.NodeVisitor):
    """Analyze error handling patterns."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.broad_exceptions = []
        self.bare_excepts = []

    def visit_ExceptHandler(self, node):
        if node.type is None:
            # Bare except
            self.bare_excepts.append(
                {
                    "line": node.lineno,
                    "severity": "high",
                }
            )
        elif isinstance(node.type, ast.Name):
            if node.type.id == "Exception":
                # Broad exception
                self.broad_exceptions.append(
                    {
                        "line": node.lineno,
                        "severity": "medium",
                    }
                )
        self.generic_visit(node)


def analyze_file(file_path: Path) -> dict[str, Any]:
    """Analyze error handling in file."""
    try:
        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content, filename=str(file_path))
        analyzer = ErrorHandlerAnalyzer(file_path)
        analyzer.visit(tree)

        return {
            "file": str(file_path),
            "broad_exceptions": analyzer.broad_exceptions,
            "bare_excepts": analyzer.bare_excepts,
            "total_issues": len(analyzer.broad_exceptions) + len(analyzer.bare_excepts),
        }
    except Exception as e:
        return {
            "file": str(file_path),
            "error": str(e),
        }


def main() -> int:
    """Main entry point."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Unify error handling")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("src/ml/scripts"),
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

    print("Analyzing error handling patterns...")
    print(f"Path: {args.path}")
    print()

    python_files = list(args.path.rglob("*.py"))

    if not python_files:
        print("No Python files found")
        return 1

    print(f"Found {len(python_files)} Python files")
    print()

    results = []
    total_broad = 0
    total_bare = 0

    for py_file in sorted(python_files):
        result = analyze_file(py_file)
        results.append(result)

        if "error" not in result:
            broad_count = len(result["broad_exceptions"])
            bare_count = len(result["bare_excepts"])
            if broad_count > 0 or bare_count > 0:
                print(f"⚠ {py_file.relative_to(args.path)}: {broad_count} broad, {bare_count} bare")
                total_broad += broad_count
                total_bare += bare_count

    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total broad exceptions: {total_broad}")
    print(f"Total bare excepts: {total_bare}")
    print(f"Total issues: {total_broad + total_bare}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(
                {
                    "summary": {
                        "total_broad": total_broad,
                        "total_bare": total_bare,
                        "total_issues": total_broad + total_bare,
                    },
                    "results": results,
                },
                f,
                indent=2,
            )
        print(f"\nReport saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
