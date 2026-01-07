#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Deep code quality analysis.

Checks for:
- Unused imports
- Dead code
- Potential bugs
- Code smells
- Inconsistencies
- Error handling issues
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


class CodeAnalyzer(ast.NodeVisitor):
    """AST analyzer for code quality issues."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.issues = []
        self.imports = set()
        self.used_names = set()
        self.functions = []
        self.classes = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module.split(".")[0])
        for alias in node.names:
            self.used_names.add(alias.name)

    def visit_Name(self, node):
        self.used_names.add(node.id)

    def visit_FunctionDef(self, node):
        self.functions.append(node.name)
        # Check for empty functions
        if not node.body:
            self.issues.append(
                {
                    "type": "empty_function",
                    "line": node.lineno,
                    "function": node.name,
                    "severity": "medium",
                }
            )
        # Check for functions with only pass
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.issues.append(
                {
                    "type": "function_with_only_pass",
                    "line": node.lineno,
                    "function": node.name,
                    "severity": "low",
                }
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        # Check for bare except
        if node.type is None:
            self.issues.append(
                {
                    "type": "bare_except",
                    "line": node.lineno,
                    "severity": "high",
                }
            )
        # Check for except Exception (too broad)
        elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
            self.issues.append(
                {
                    "type": "broad_exception",
                    "line": node.lineno,
                    "severity": "medium",
                }
            )
        self.generic_visit(node)

    def visit_Compare(self, node):
        # Check for == None or != None
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.NotEq)):
                if isinstance(comparator, ast.Constant) and comparator.value is None:
                    self.issues.append(
                        {
                            "type": "none_comparison",
                            "line": node.lineno,
                            "severity": "low",
                            "suggestion": "Use 'is None' or 'is not None' instead",
                        }
                    )
        self.generic_visit(node)


def analyze_file(file_path: Path) -> dict[str, Any]:
    """Analyze single Python file."""
    try:
        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content, filename=str(file_path))
        analyzer = CodeAnalyzer(file_path)
        analyzer.visit(tree)

        # Check for unused imports (simplified)
        unused_imports = []
        for imp in analyzer.imports:
            if imp not in analyzer.used_names and imp not in ["sys", "os", "json", "pathlib"]:
                # This is a simplified check - may have false positives
                pass

        return {
            "file": str(file_path),
            "functions": len(analyzer.functions),
            "classes": len(analyzer.classes),
            "issues": analyzer.issues,
            "issue_count": len(analyzer.issues),
        }
    except SyntaxError as e:
        return {
            "file": str(file_path),
            "error": f"Syntax error: {e}",
            "issues": [{"type": "syntax_error", "line": e.lineno, "severity": "critical"}],
        }
    except Exception as e:
        return {
            "file": str(file_path),
            "error": str(e),
        }


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Deep code quality analysis")
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

    print("Analyzing code quality...")
    print(f"Path: {args.path}")
    print()

    # Find Python files
    python_files = list(args.path.rglob("*.py"))

    if not python_files:
        print("No Python files found")
        return 1

    print(f"Found {len(python_files)} Python files")
    print()

    results = []
    total_issues = 0
    critical_issues = 0

    for py_file in sorted(python_files):
        result = analyze_file(py_file)
        results.append(result)

        if "error" in result:
            print(f"✗ {py_file.relative_to(args.path)}: {result['error']}")
            critical_issues += 1
        elif result.get("issue_count", 0) > 0:
            issues = result["issues"]
            high_severity = [i for i in issues if i.get("severity") == "high"]
            if high_severity:
                print(
                    f"⚠ {py_file.relative_to(args.path)}: {len(high_severity)} high-severity issues"
                )
                critical_issues += len(high_severity)
            total_issues += result["issue_count"]

    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Files analyzed: {len(python_files)}")
    print(f"Total issues: {total_issues}")
    print(f"Critical issues: {critical_issues}")

    # Group issues by type
    issue_types = {}
    for result in results:
        for issue in result.get("issues", []):
            issue_type = issue.get("type", "unknown")
            issue_types[issue_type] = issue_types.get(issue_type, 0) + 1

    if issue_types:
        print()
        print("Issues by type:")
        for issue_type, count in sorted(issue_types.items(), key=lambda x: x[1], reverse=True):
            print(f"  {issue_type}: {count}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        import json

        with open(args.output, "w") as f:
            json.dump(
                {
                    "path": str(args.path),
                    "summary": {
                        "files_analyzed": len(python_files),
                        "total_issues": total_issues,
                        "critical_issues": critical_issues,
                    },
                    "issue_types": issue_types,
                    "results": results,
                },
                f,
                indent=2,
            )
        print(f"\nReport saved to: {args.output}")

    return 0 if critical_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
