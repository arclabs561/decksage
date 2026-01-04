#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Prerequisite validation for Tier 0 & Tier 1 scripts.

Validates that all required dependencies, files, and configurations
are available before running validation scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Set up project paths
from ml.utils.path_setup import setup_project_paths
setup_project_paths()

from ml.utils.paths import PATHS
from ml.utils.logging_config import setup_script_logging

logger = setup_script_logging()


def check_optional_dependency(name: str, import_name: str | None = None) -> tuple[bool, str]:
    """Check if an optional dependency is available."""
    import_name = import_name or name
    try:
        __import__(import_name)
        return True, f"{name} available"
    except ImportError:
        return False, f"{name} not available (optional)"


def check_required_file(path: Path, description: str) -> tuple[bool, str]:
    """Check if a required file exists."""
    if path.exists():
        return True, f"{description} found: {path}"
    return False, f"{description} missing: {path}"


def validate_tier0_tier1_prerequisites() -> dict[str, Any]:
    """Validate prerequisites for Tier 0 & Tier 1 scripts."""
    results: dict[str, Any] = {
        "required": {},
        "optional": {},
        "files": {},
        "overall": "pass",
    }
    
    # Required dependencies
    required_deps = {
        "pandas": "pandas",
        "numpy": "numpy",
        "json": "json",
    }
    
    for name, import_name in required_deps.items():
        available, message = check_optional_dependency(name, import_name)
        results["required"][name] = {
            "available": available,
            "message": message,
        }
        if not available:
            results["overall"] = "fail"
    
    # Optional dependencies
    optional_deps = {
        "pydantic_ai": "pydantic_ai",
        "sentence_transformers": "sentence_transformers",
        "gensim": "gensim",
        "scikit-learn": "sklearn",
    }
    
    for name, import_name in optional_deps.items():
        available, message = check_optional_dependency(name, import_name)
        results["optional"][name] = {
            "available": available,
            "message": message,
        }
    
    # Required files
    required_files = {
        "test_set": getattr(PATHS, "test_magic", None),
        "decks": PATHS.decks_all_final,
        "pairs": PATHS.pairs_large,
    }
    
    for name, path in required_files.items():
        if path:
            available, message = check_required_file(path, name)
            results["files"][name] = {
                "available": available,
                "message": message,
            }
            if not available and name in ["test_set", "decks"]:
                results["overall"] = "warn" if results["overall"] == "pass" else "fail"
    
    # Check output directory
    output_dir = PATHS.experiments
    if not output_dir.exists():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            results["files"]["output_dir"] = {
                "available": True,
                "message": f"Created output directory: {output_dir}",
            }
        except Exception as e:
            results["files"]["output_dir"] = {
                "available": False,
                "message": f"Failed to create output directory: {e}",
            }
            results["overall"] = "fail"
    else:
        results["files"]["output_dir"] = {
            "available": True,
            "message": f"Output directory exists: {output_dir}",
        }
    
    return results


def main() -> int:
    """CLI for prerequisite validation."""
    parser = argparse.ArgumentParser(description="Validate prerequisites for Tier 0 & Tier 1")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file (optional)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON format",
    )
    
    args = parser.parse_args()
    
    results = validate_tier0_tier1_prerequisites()
    
    if args.json or args.output:
        from ml.scripts.fix_nuances import safe_json_dump
        
        if args.output:
            safe_json_dump(results, args.output, indent=2)
        if args.json:
            import json
            print(json.dumps(results, indent=2))
    else:
        # Human-readable output
        print("\n" + "=" * 70)
        print("Prerequisite Validation")
        print("=" * 70)
        
        print("\nRequired Dependencies:")
        for name, info in results["required"].items():
            status = "✓" if info["available"] else "✗"
            print(f"  {status} {name}: {info['message']}")
        
        print("\nOptional Dependencies:")
        for name, info in results["optional"].items():
            status = "✓" if info["available"] else "○"
            print(f"  {status} {name}: {info['message']}")
        
        print("\nFiles:")
        for name, info in results["files"].items():
            status = "✓" if info["available"] else "✗"
            print(f"  {status} {name}: {info['message']}")
        
        print(f"\nOverall Status: {results['overall'].upper()}")
    
    return 0 if results["overall"] in ["pass", "warn"] else 1


if __name__ == "__main__":
    sys.exit(main())

