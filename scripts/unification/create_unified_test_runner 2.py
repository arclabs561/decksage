#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Create unified test runner that runs all tests with proper setup.
"""

import subprocess
import sys
from pathlib import Path


def run_all_tests() -> int:
    """Run all tests."""
    print("=" * 70)
    print("Running All Tests")
    print("=" * 70)
    print()

    test_files = list(Path("tests").glob("test_*.py"))

    if not test_files:
        print("No test files found")
        return 1

    print(f"Found {len(test_files)} test files")
    print()

    results = []
    for test_file in sorted(test_files):
        print(f"Running {test_file.name}...", end=" ", flush=True)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                print("✓")
            else:
                print("✗")
                print(f"  {result.stdout}")
                print(f"  {result.stderr}")
            results.append((test_file, result.returncode == 0))
        except subprocess.TimeoutExpired:
            print("⚠ Timeout")
            results.append((test_file, False))
        except Exception as e:
            print(f"✗ Error: {e}")
            results.append((test_file, False))

    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed

    print(f"Passed: {passed}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")

    if failed > 0:
        print()
        print("Failed tests:")
        for test_file, success in results:
            if not success:
                print(f"  - {test_file.name}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
