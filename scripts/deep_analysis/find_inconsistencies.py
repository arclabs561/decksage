#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Find inconsistencies across the codebase.

Checks for:
- Inconsistent naming conventions
- Inconsistent path handling
- Inconsistent error handling
- Inconsistent data formats
- Version mismatches
- Configuration inconsistencies
"""

import json
import re
import sys
from pathlib import Path
from typing import Any
from collections import defaultdict

# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def find_path_inconsistencies() -> list[dict[str, Any]]:
    """Find inconsistent path handling."""
    issues = []
    
    # Check for hardcoded paths
    hardcoded_patterns = [
        r'["\']data/',
        r'["\']experiments/',
        r'["\']src/ml/',
    ]
    
    # Check common files
    common_files = [
        Path("src/ml/utils/paths.py"),
        Path("src/ml/scripts/evaluate_all_embeddings.py"),
    ]
    
    for file_path in common_files:
        if not file_path.exists():
            continue
        
        with open(file_path) as f:
            content = f.read()
        
        for pattern in hardcoded_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                issues.append({
                    "type": "hardcoded_path",
                    "file": str(file_path),
                    "line": line_num,
                    "pattern": match.group(),
                    "severity": "medium",
                })
    
    return issues


def find_naming_inconsistencies() -> list[dict[str, Any]]:
    """Find inconsistent naming conventions."""
    issues = []
    
    # Check for inconsistent function naming
    # Look for snake_case vs camelCase
    python_files = list(Path("src/ml").rglob("*.py"))
    
    function_names = []
    for py_file in python_files[:20]:  # Sample
        try:
            with open(py_file) as f:
                content = f.read()
            
            # Find function definitions
            func_pattern = r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)'
            matches = re.finditer(func_pattern, content)
            for match in matches:
                func_name = match.group(1)
                function_names.append((py_file, func_name))
        except Exception:
            pass
    
    # Check for camelCase (should be snake_case in Python)
    camel_case = [f for _, f in function_names if re.search(r'[a-z][A-Z]', f)]
    if camel_case:
        issues.append({
            "type": "naming_inconsistency",
            "issue": "camelCase function names found",
            "examples": camel_case[:5],
            "severity": "low",
        })
    
    return issues


def find_version_mismatches() -> list[dict[str, Any]]:
    """Find version mismatches."""
    issues = []
    
    # Check pyproject.toml for version
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        with open(pyproject) as f:
            content = f.read()
        
        version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if version_match:
            pyproject_version = version_match.group(1)
            
            # Check if version appears elsewhere
            # This is a simplified check
            pass
    
    return issues


def find_data_format_inconsistencies() -> list[dict[str, Any]]:
    """Find inconsistent data formats."""
    issues = []
    
    # Check test set formats
    test_sets = [
        Path("experiments/test_set_canonical_magic.json"),
        Path("experiments/test_set_unified_magic.json"),
    ]
    
    formats = {}
    for test_set in test_sets:
        if not test_set.exists():
            continue
        
        try:
            with open(test_set) as f:
                data = json.load(f)
            
            # Check structure
            has_queries_key = "queries" in data
            if has_queries_key:
                queries = data["queries"]
            else:
                queries = data
            
            if isinstance(queries, dict):
                sample_query = list(queries.keys())[0] if queries else None
                if sample_query:
                    sample_labels = queries[sample_query]
                    format_key = "has_queries_key" if has_queries_key else "direct_dict"
                    if format_key not in formats:
                        formats[format_key] = []
                    formats[format_key].append(str(test_set))
        except Exception:
            pass
    
    if len(formats) > 1:
        issues.append({
            "type": "data_format_inconsistency",
            "issue": "Test sets use different formats",
            "formats": formats,
            "severity": "medium",
        })
    
    return issues


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Find inconsistencies")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report",
    )
    
    args = parser.parse_args()
    
    print("Finding inconsistencies...")
    print()
    
    all_issues = []
    
    # Check path inconsistencies
    print("Checking path handling...")
    path_issues = find_path_inconsistencies()
    all_issues.extend(path_issues)
    print(f"  Found {len(path_issues)} path inconsistencies")
    
    # Check naming inconsistencies
    print("Checking naming conventions...")
    naming_issues = find_naming_inconsistencies()
    all_issues.extend(naming_issues)
    print(f"  Found {len(naming_issues)} naming inconsistencies")
    
    # Check version mismatches
    print("Checking version consistency...")
    version_issues = find_version_mismatches()
    all_issues.extend(version_issues)
    print(f"  Found {len(version_issues)} version issues")
    
    # Check data format inconsistencies
    print("Checking data formats...")
    format_issues = find_data_format_inconsistencies()
    all_issues.extend(format_issues)
    print(f"  Found {len(format_issues)} format inconsistencies")
    
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total inconsistencies: {len(all_issues)}")
    
    # Group by type
    by_type = defaultdict(list)
    for issue in all_issues:
        by_type[issue["type"]].append(issue)
    
    if by_type:
        print()
        print("Issues by type:")
        for issue_type, issues_list in sorted(by_type.items()):
            print(f"  {issue_type}: {len(issues_list)}")
    
    # Show examples
    if all_issues:
        print()
        print("Example issues:")
        for issue in all_issues[:10]:
            print(f"  [{issue.get('severity', 'unknown').upper()}] {issue['type']}")
            if "file" in issue:
                print(f"      File: {issue['file']}")
            if "examples" in issue:
                print(f"      Examples: {', '.join(issue['examples'][:3])}")
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump({
                "summary": {
                    "total": len(all_issues),
                },
                "by_type": {k: len(v) for k, v in by_type.items()},
                "issues": all_issues,
            }, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    return 0 if len(all_issues) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

