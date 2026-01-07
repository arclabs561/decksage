#!/usr/bin/env python3
"""
Annotation system health check.

Comprehensive health check for the annotation system:
- File integrity
- Data quality
- Integration status
- S3 sync status
- System dependencies
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def check_file_integrity(annotations_dir: Path) -> dict[str, Any]:
    """Check integrity of annotation files."""
    issues = []
    warnings = []
    
    # Check for JSONL files
    jsonl_files = list(annotations_dir.glob("*.jsonl"))
    for f in jsonl_files:
        try:
            count = 0
            with open(f) as file:
                for line in file:
                    if line.strip():
                        json.loads(line)  # Validate JSON
                        count += 1
            if count == 0:
                warnings.append(f"Empty file: {f.name}")
        except json.JSONDecodeError as e:
            issues.append(f"Invalid JSON in {f.name}: {e}")
        except Exception as e:
            issues.append(f"Error reading {f.name}: {e}")
    
    return {
        "jsonl_files": len(jsonl_files),
        "issues": issues,
        "warnings": warnings,
        "status": "healthy" if not issues else "unhealthy",
    }


def check_data_quality(annotations_dir: Path) -> dict[str, Any]:
    """Check data quality of annotations."""
    issues = []
    
    # Check integrated file
    integrated_files = list(annotations_dir.glob("*integrated*.jsonl"))
    if not integrated_files:
        issues.append("No integrated annotation file found")
        return {"status": "missing", "issues": issues}
    
    # Check latest integrated file
    latest = max(integrated_files, key=lambda p: p.stat().st_mtime)
    
    annotations = []
    errors = []
    with open(latest) as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    ann = json.loads(line)
                    annotations.append(ann)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue
                except Exception as e:
                    errors.append(f"Line {line_num}: Error - {e}")
                    continue
    
    if errors:
        issues.extend(errors[:5])
        if len(errors) > 5:
            issues.append(f"... and {len(errors) - 5} more errors")
                
                # Validate structure
                    if not ann.get("card1") or not ann.get("card2"):
                    issues.append(f"Missing card names in annotation")
                score = ann.get("similarity_score", -1)
                if not (0 <= score <= 1):
                    issues.append(f"Invalid similarity_score: {score}")
    
    return {
        "integrated_file": str(latest),
        "total_annotations": len(annotations),
        "issues": issues,
        "status": "healthy" if not issues else "unhealthy",
    }


def check_integration_status(annotations_dir: Path) -> dict[str, Any]:
    """Check if integration is up to date."""
    # Check for various source files
    sources = {
        "hand_annotations": list(annotations_dir.glob("hand_batch_*.yaml")),
        "llm_annotations": list(annotations_dir.glob("*_llm_annotations.jsonl")),
        "user_feedback": list(annotations_dir.glob("user_feedback.jsonl")),
        "multi_judge": list(annotations_dir.glob("judgment_*.jsonl")),
    }
    
    # Check if integrated file is newer than source files
    integrated_files = list(annotations_dir.glob("*integrated*.jsonl"))
    if not integrated_files:
        return {"status": "missing", "message": "No integrated file found"}
    
    latest_integrated = max(integrated_files, key=lambda p: p.stat().st_mtime)
    integrated_time = latest_integrated.stat().st_mtime
    
    outdated_sources = []
    for source_name, files in sources.items():
        for f in files:
            if f.stat().st_mtime > integrated_time:
                outdated_sources.append(f"{source_name}: {f.name}")
    
    return {
        "integrated_file": str(latest_integrated),
        "outdated_sources": outdated_sources,
        "status": "up_to_date" if not outdated_sources else "outdated",
    }


def check_s3_sync_status(s3_path: str = "s3://games-collections/annotations/") -> dict[str, Any]:
    """Check S3 sync status."""
    try:
        result = subprocess.run(
            ["s5cmd", "ls", s3_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            files = [line for line in result.stdout.strip().split("\n") if line.strip()]
            return {
                "status": "synced",
                "files_in_s3": len(files),
                "s3_path": s3_path,
            }
        else:
            return {
                "status": "error",
                "error": result.stderr[:200],
            }
    except FileNotFoundError:
        return {
            "status": "s5cmd_not_found",
            "message": "s5cmd not installed",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def check_dependencies() -> dict[str, Any]:
    """Check system dependencies."""
    dependencies = {}
    
    # Check Python packages
    packages = ["pydantic", "pydantic_ai", "fastapi", "uvicorn"]
    for pkg in packages:
        try:
            __import__(pkg.replace("-", "_"))
            dependencies[pkg] = "installed"
        except ImportError:
            dependencies[pkg] = "missing"
    
    # Check tools
    tools = ["s5cmd"]
    for tool in tools:
        try:
            subprocess.run([tool, "--version"], capture_output=True, timeout=2)
            dependencies[tool] = "installed"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            dependencies[tool] = "missing"
    
    missing = [k for k, v in dependencies.items() if v == "missing"]
    
    return {
        "dependencies": dependencies,
        "status": "healthy" if not missing else "missing_dependencies",
        "missing": missing,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Annotation system health check")
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Annotations directory",
    )
    parser.add_argument(
        "--s3-path",
        type=str,
        default="s3://games-collections/annotations/",
        help="S3 path to check",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output health report JSON",
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("ANNOTATION SYSTEM HEALTH CHECK")
    print("=" * 80)
    print()
    
    health_report = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "checks": {},
    }
    
    # File integrity
    print("Checking file integrity...")
    integrity = check_file_integrity(args.annotations_dir)
    health_report["checks"]["file_integrity"] = integrity
    print(f"  Status: {integrity['status']}")
    if integrity["issues"]:
        print(f"  Issues: {len(integrity['issues'])}")
        for issue in integrity["issues"][:5]:
            print(f"    - {issue}")
    if integrity["warnings"]:
        print(f"  Warnings: {len(integrity['warnings'])}")
    
    # Data quality
    print("\nChecking data quality...")
    quality = check_data_quality(args.annotations_dir)
    health_report["checks"]["data_quality"] = quality
    print(f"  Status: {quality['status']}")
    if "total_annotations" in quality:
        print(f"  Annotations: {quality['total_annotations']}")
    if quality["issues"]:
        print(f"  Issues: {len(quality['issues'])}")
    
    # Integration status
    print("\nChecking integration status...")
    integration = check_integration_status(args.annotations_dir)
    health_report["checks"]["integration"] = integration
    print(f"  Status: {integration['status']}")
    if integration.get("outdated_sources"):
        print(f"  Outdated sources: {len(integration['outdated_sources'])}")
    
    # S3 sync
    print("\nChecking S3 sync status...")
    s3_status = check_s3_sync_status(args.s3_path)
    health_report["checks"]["s3_sync"] = s3_status
    print(f"  Status: {s3_status['status']}")
    if "files_in_s3" in s3_status:
        print(f"  Files in S3: {s3_status['files_in_s3']}")
    
    # Dependencies
    print("\nChecking dependencies...")
    deps = check_dependencies()
    health_report["checks"]["dependencies"] = deps
    print(f"  Status: {deps['status']}")
    if deps["missing"]:
        print(f"  Missing: {', '.join(deps['missing'])}")
    
    # Overall health
    all_healthy = all(
        check.get("status") in ["healthy", "up_to_date", "synced"]
        for check in health_report["checks"].values()
    )
    health_report["overall_status"] = "healthy" if all_healthy else "needs_attention"
    
    print("\n" + "=" * 80)
    print("HEALTH CHECK SUMMARY")
    print("=" * 80)
    print(f"Overall status: {health_report['overall_status']}")
    
    # Save report
    if args.output:
        with open(args.output, "w") as f:
            json.dump(health_report, f, indent=2)
        print(f"\n✓ Saved health report: {args.output}")
    
    return 0 if all_healthy else 1


if __name__ == "__main__":
    sys.exit(main())

