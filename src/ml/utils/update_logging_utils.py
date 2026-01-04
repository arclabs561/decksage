#!/usr/bin/env python3
"""Utility script to help update remaining files to use new logging.

This script identifies files that still need logging updates.
Run manually to see what needs updating.
"""

from __future__ import annotations

import re
from pathlib import Path


def find_files_needing_update(root: Path = Path("src/ml")) -> dict[str, list[str]]:
    """Find files that need logging updates."""
    results = {
        "basic_config": [],
        "get_logger": [],
        "exc_info": [],
    }

    for py_file in root.rglob("*.py"):
        if "logging_config.py" in str(py_file):
            continue

        content = py_file.read_text()

        # Find basicConfig calls
        if re.search(r"logging\.basicConfig\(", content):
            results["basic_config"].append(str(py_file.relative_to(root)))

        # Find getLogger(__name__) patterns
        if re.search(r"logger\s*=\s*logging\.getLogger\(__name__\)", content):
            results["get_logger"].append(str(py_file.relative_to(root)))

        # Find exc_info=True patterns
        if re.search(r"logger\.(error|warning)\([^)]*exc_info=True", content):
            results["exc_info"].append(str(py_file.relative_to(root)))

    return results


if __name__ == "__main__":
    results = find_files_needing_update()

    print("Files needing logging updates:")
    print(f"\n1. Files with logging.basicConfig(): {len(results['basic_config'])}")
    for f in sorted(results["basic_config"])[:20]:
        print(f"   - {f}")
    if len(results["basic_config"]) > 20:
        print(f"   ... and {len(results['basic_config']) - 20} more")

    print(f"\n2. Files with logging.getLogger(__name__): {len(results['get_logger'])}")
    for f in sorted(results["get_logger"])[:20]:
        print(f"   - {f}")
    if len(results["get_logger"]) > 20:
        print(f"   ... and {len(results['get_logger']) - 20} more")

    print(f"\n3. Files with exc_info=True: {len(results['exc_info'])}")
    for f in sorted(results["exc_info"]):
        print(f"   - {f}")
