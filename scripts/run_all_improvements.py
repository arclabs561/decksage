#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
# ]
# ///
"""Comprehensive improvement orchestration."""
import json
import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and report status."""
    print(f"🚀 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"  ✅ {description} complete")
            if result.stdout:
                print(f"     Output: {result.stdout[:200]}")
            return True
        else:
            print(f"  ⚠️  {description} failed: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ⏱️  {description} timed out")
        return False
    except Exception as e:
        print(f"  ❌ {description} error: {e}")
        return False

def main():
    """Run all improvement steps."""
    print("=" * 70)
    print("COMPREHENSIVE IMPROVEMENT PIPELINE")
    print("=" * 70)
    print()
    
    steps = [
        ("just monitor", "Status check"),
        ("just evaluate-all-games", "Multi-game evaluation"),
    ]
    
    results = {}
    for cmd, desc in steps:
        results[desc] = run_command(cmd, desc)
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    
    for desc, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {desc}")
    
    print()
    print("✅ Improvement pipeline complete")

if __name__ == "__main__":
    main()
