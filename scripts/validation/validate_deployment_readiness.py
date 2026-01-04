#!/usr/bin/env python3
"""
Validate deployment readiness.

Checks that deployment-related files are correct and deployment will succeed.
This runs as a pre-push hook when deployment files are changed.
"""

import sys
from pathlib import Path


def check_dockerfile() -> list[str]:
    """Check Dockerfile.api exists and is valid."""
    issues = []
    dockerfile = Path("Dockerfile.api")

    if not dockerfile.exists():
        issues.append("Dockerfile.api not found")
        return issues

    content = dockerfile.read_text()

    # Check for required elements
    if "FROM python:3.11" not in content:
        issues.append("Dockerfile.api should use Python 3.11")

    if "EXPOSE 8000" not in content:
        issues.append("Dockerfile.api should expose port 8000")

    if "/live" not in content:
        issues.append("Dockerfile.api should include /live health check")

    return issues


def check_fly_config() -> list[str]:
    """Check fly.toml exists and is valid."""
    issues = []
    fly_toml = Path("fly.toml")

    if not fly_toml.exists():
        issues.append("fly.toml not found")
        return issues

    content = fly_toml.read_text()

    # Check for required elements
    if "internal_port = 8000" not in content:
        issues.append("fly.toml should set internal_port = 8000")

    if "/live" not in content:
        issues.append("fly.toml should check /live endpoint")

    return issues


def check_deploy_workflow() -> list[str]:
    """Check deploy workflow exists."""
    issues = []
    workflow = Path(".github/workflows/deploy.yml")

    if not workflow.exists():
        issues.append(".github/workflows/deploy.yml not found (deployment will be manual only)")
        return issues

    content = workflow.read_text()

    # Check for required elements
    if "pre-deploy-checks" not in content:
        issues.append("deploy.yml should include pre-deploy-checks job")

    if "flyctl deploy" not in content:
        issues.append("deploy.yml should include flyctl deploy step")

    return issues


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        # No files provided, skip check
        return 0

    # Only run if deployment-related files changed
    changed_files = sys.argv[1:]
    deployment_files = [
        "Dockerfile.api",
        "fly.toml",
        ".github/workflows/deploy.yml",
        "scripts/validate_deployment.sh",
    ]

    relevant_changes = [
        f for f in changed_files if any(df in f for df in deployment_files) or "src/ml/api" in f
    ]

    if not relevant_changes:
        # No deployment files changed, skip
        return 0

    print("🔍 Validating deployment readiness...")
    print(f"   Changed files: {', '.join(relevant_changes)}")
    print("")

    all_issues = []

    # Check Dockerfile
    dockerfile_issues = check_dockerfile()
    if dockerfile_issues:
        all_issues.extend([f"Dockerfile: {issue}" for issue in dockerfile_issues])

    # Check fly.toml
    fly_issues = check_fly_config()
    if fly_issues:
        all_issues.extend([f"fly.toml: {issue}" for issue in fly_issues])

    # Check deploy workflow
    workflow_issues = check_deploy_workflow()
    if workflow_issues:
        all_issues.extend([f"deploy.yml: {issue}" for issue in workflow_issues])

    if all_issues:
        print("⚠️  Deployment readiness issues found:")
        for issue in all_issues:
            print(f"   • {issue}")
        print("")
        print("💡 Fix these before deploying to production.")
        print("   See: docs/AGENT_DEPLOYMENT_GUIDE.md")
        return 1

    print("✅ Deployment readiness checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
