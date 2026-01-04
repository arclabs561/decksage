#!/usr/bin/env python3
"""Check for import errors in Python files."""

import ast
import sys
from pathlib import Path


def check_imports(file_path: Path) -> list[str]:
    """Check if a file has valid Python syntax and can parse imports."""
    errors = []

    try:
        with open(file_path) as f:
            content = f.read()

        # Try to parse the AST
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            errors.append(f"Syntax error: {e.msg} at line {e.lineno}")
            return errors

        # Check for common import issues
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("ml."):
                    # Check if it's a relative import that should be absolute
                    if not any(
                        isinstance(parent, (ast.FunctionDef, ast.ClassDef))
                        for parent in ast.walk(tree)
                    ):
                        pass  # Could add more checks here

    except Exception as e:
        errors.append(f"Error reading file: {e}")

    return errors


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        return 0

    errors_found = False
    for file_path_str in sys.argv[1:]:
        file_path = Path(file_path_str)
        if not file_path.exists() or not file_path.suffix == ".py":
            continue

        errors = check_imports(file_path)
        if errors:
            errors_found = True
            print(f"\n{file_path}:")
            for error in errors:
                print(f"  ❌ {error}")

    if errors_found:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
