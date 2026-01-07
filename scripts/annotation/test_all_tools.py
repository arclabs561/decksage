#!/usr/bin/env python3
"""
Test all annotation tools end-to-end.

Validates that all tools work correctly and integrate properly.
"""

import json
import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_tool(tool_name: str, args: list[str], expected_exit: int = 0) -> tuple[bool, str]:
    """Test a tool with given arguments."""
    tool_path = project_root / "scripts" / "annotation" / tool_name
    if not tool_path.exists():
        return False, f"Tool not found: {tool_name}"
    
    try:
        result = subprocess.run(
            [sys.executable, str(tool_path)] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        success = result.returncode == expected_exit
        output = result.stdout + result.stderr
        return success, output
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def test_integration_workflow() -> dict:
    """Test the complete integration workflow."""
    print("Testing integration workflow...")
    
    results = {}
    
    # 1. Review annotations
    print("  1. Testing review_annotations.py...")
    success, output = test_tool("review_annotations.py", [], expected_exit=0)
    results["review"] = {
        "success": success,
        "output_length": len(output),
        "has_summary": "SUMMARY" in output,
    }
    
    # 2. Integrate annotations
    print("  2. Testing integrate_all_annotations.py...")
    test_output = project_root / "annotations" / "test_integration_workflow.jsonl"
    success, output = test_tool(
        "integrate_all_annotations.py",
        ["--output", str(test_output)],
        expected_exit=0,
    )
    results["integrate"] = {
        "success": success,
        "output_length": len(output),
        "has_quality": "Quality score" in output,
        "file_created": test_output.exists() if success else False,
    }
    
    # 3. Validate integration
    if test_output.exists():
        print("  3. Testing validate_integration.py...")
        success, output = test_tool(
            "validate_integration.py",
            [],
            expected_exit=0,
        )
        results["validate"] = {
            "success": success,
            "output_length": len(output),
            "has_validation": "VALIDATION" in output,
        }
    
    # 4. Quality monitoring
    print("  4. Testing quality_monitoring_dashboard.py...")
    test_quality = project_root / "annotations" / "test_quality.json"
    success, output = test_tool(
        "quality_monitoring_dashboard.py",
        ["--output", str(test_quality)],
        expected_exit=1,  # May exit with 1 if quality is low
    )
    results["quality"] = {
        "success": success or "Quality score" in output,
        "output_length": len(output),
        "has_issues": "ISSUES" in output or "RECOMMENDATIONS" in output,
        "file_created": test_quality.exists() if success else False,
    }
    
    return results


def test_generation_tools() -> dict:
    """Test annotation generation tools."""
    print("Testing generation tools...")
    
    results = {}
    
    # Browser annotation tool
    print("  1. Testing browser_annotate.py help...")
    success, output = test_tool("browser_annotate.py", ["--help"], expected_exit=0)
    results["browser_help"] = {
        "success": success,
        "has_usage": "usage" in output.lower() or "help" in output.lower(),
    }
    
    # Complete hand annotations
    print("  2. Testing complete_hand_annotations.py help...")
    success, output = test_tool("complete_hand_annotations.py", ["--help"], expected_exit=0)
    results["complete_help"] = {
        "success": success,
        "has_usage": "usage" in output.lower() or "help" in output.lower(),
    }
    
    # Multi-judge pipeline
    print("  3. Testing setup_multi_judge_pipeline.py help...")
    success, output = test_tool("setup_multi_judge_pipeline.py", ["--help"], expected_exit=0)
    results["multi_judge_help"] = {
        "success": success,
        "has_usage": "usage" in output.lower() or "help" in output.lower(),
    }
    
    return results


def test_file_formats() -> dict:
    """Test that generated files have correct formats."""
    print("Testing file formats...")
    
    results = {}
    annotations_dir = project_root / "annotations"
    
    # Check integrated annotations
    integrated_files = list(annotations_dir.glob("*integrated*.jsonl"))
    if integrated_files:
        test_file = integrated_files[0]
        print(f"  Testing {test_file.name}...")
        
        annotations = []
        try:
            with open(test_file) as f:
                for line in f:
                    if line.strip():
                        annotations.append(json.loads(line))
            
            # Validate format
            required_fields = ["card1", "card2", "similarity_score", "source"]
            valid = all(
                all(field in ann for field in required_fields)
                for ann in annotations
            )
            
            results["integrated_format"] = {
                "file": test_file.name,
                "count": len(annotations),
                "valid": valid,
            }
        except Exception as e:
            results["integrated_format"] = {
                "file": test_file.name,
                "error": str(e),
            }
    
    # Check substitution pairs
    pairs_file = annotations_dir / "substitution_pairs.json"
    if pairs_file.exists():
        print(f"  Testing {pairs_file.name}...")
        try:
            with open(pairs_file) as f:
                pairs = json.load(f)
            
            valid = isinstance(pairs, list) and all(
                isinstance(p, list) and len(p) == 2
                for p in pairs
            )
            
            results["substitution_pairs_format"] = {
                "file": pairs_file.name,
                "count": len(pairs),
                "valid": valid,
            }
        except Exception as e:
            results["substitution_pairs_format"] = {
                "file": pairs_file.name,
                "error": str(e),
            }
    
    # Check test set
    test_set_file = annotations_dir / "test_set.json"
    if test_set_file.exists():
        print(f"  Testing {test_set_file.name}...")
        try:
            with open(test_set_file) as f:
                test_set = json.load(f)
            
            valid = "queries" in test_set and isinstance(test_set["queries"], dict)
            
            results["test_set_format"] = {
                "file": test_set_file.name,
                "queries": len(test_set.get("queries", {})),
                "valid": valid,
            }
        except Exception as e:
            results["test_set_format"] = {
                "file": test_set_file.name,
                "error": str(e),
            }
    
    return results


def main() -> int:
    """Run all tests."""
    print("=" * 80)
    print("ANNOTATION TOOLS TEST SUITE")
    print("=" * 80)
    print()
    
    all_results = {}
    
    # Test integration workflow
    all_results["integration"] = test_integration_workflow()
    print()
    
    # Test generation tools
    all_results["generation"] = test_generation_tools()
    print()
    
    # Test file formats
    all_results["formats"] = test_file_formats()
    print()
    
    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    total_tests = 0
    passed_tests = 0
    
    for category, tests in all_results.items():
        print(f"\n{category.upper()}:")
        for test_name, result in tests.items():
            total_tests += 1
            if isinstance(result, dict):
                success = result.get("success", result.get("valid", False))
                if success:
                    passed_tests += 1
                    print(f"  ✅ {test_name}")
                else:
                    print(f"  ❌ {test_name}: {result.get('error', 'failed')}")
    
    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")
    
    return 0 if passed_tests == total_tests else 1


if __name__ == "__main__":
    sys.exit(main())


